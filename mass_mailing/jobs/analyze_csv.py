#!/usr/bin/env python3
"""mass_mailing/jobs/analyze_csv.py — job `campaign.analyze_csv`.

Du fichier déposé à une version de cible en base : décodage, séparateur, en-tête,
première colonne, normalisation, dédoublonnage, syntaxe, liste de suppression.

Deux moitiés, séparées exprès :

- `analyser(octets)` est PURE — ni base, ni disque. Elle se teste sur des chaînes
  et sert aussi l'aperçu instantané de l'écran d'import (`apercu`).
- `executer(job)` est la moitié écrivante, en UNE transaction : version de cible,
  destinataires, pointeur de campagne et journal d'audit arrivent ensemble ou pas
  du tout.

Ce que ce job ne fait JAMAIS : soumettre la liste à Mailnjoy. La spec l'interdit
(« ne jamais soumettre automatiquement la liste après upload ») — la validation
coûte des crédits et reste un geste explicite du superadmin.

Invariant vérifié à chaque analyse, et que les tests contrôlent :

    lignes brutes = vides + syntaxe invalide + uniques + doublons
"""
from __future__ import annotations

import csv
import io
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import adresses, pg, stockage  # noqa: E402
from jobs.file import ErreurDefinitive  # noqa: E402

import psycopg2.extras  # noqa: E402

JOB_TYPE = "campaign.analyze_csv"

SEPARATEURS = (";", ",", "\t")
NOMS_SEPARATEURS = {";": "point-virgule", ",": "virgule", "\t": "tabulation"}

# Libellés d'en-tête reconnus sans hésitation (comparés en minuscules, sans accents
# ni ponctuation superflue).
EN_TETES = {"email", "emails", "e-mail", "e-mails", "mail", "mails", "courriel",
            "adresse", "adresse email", "adresse e-mail", "adresse mail",
            "email address", "e-mail address", "address", "contact"}

# Statuts depuis lesquels la cible peut encore changer. Au-delà (validation en
# cours, planifiée, en envoi…) la cible est figée : la remplacer ferait partir la
# campagne vers une audience que personne n'a validée.
STATUTS_MODIFIABLES = ("draft", "ready_for_validation", "validation_issue", "ready_to_schedule")

APERCU_LIGNES = 10
ECHANTILLON_ERREURS = 20


# ── Moitié pure ──────────────────────────────────────────────────────────────

def decoder(donnees: bytes) -> tuple[str, str]:
    """Octets → texte. UTF-8 (avec ou sans BOM) d'abord, puis les exports Excel."""
    if donnees.startswith(b"\xef\xbb\xbf"):
        return donnees[3:].decode("utf-8", errors="replace"), "utf-8-bom"
    if donnees.startswith((b"\xff\xfe", b"\xfe\xff")):
        # Excel « Texte Unicode » : UTF-16, séparé par tabulations.
        return donnees.decode("utf-16", errors="replace").lstrip("﻿"), "utf-16"
    try:
        return donnees.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        # Excel français enregistre en Windows-1252. Les adresses sont en ASCII,
        # seuls les en-têtes accentués (« Adresse électronique ») en dépendent.
        return donnees.decode("cp1252", errors="replace"), "windows-1252"


def _lignes_non_vides(texte: str, n: int = 50) -> list[str]:
    out = []
    for l in texte.splitlines():
        if l.strip():
            out.append(l)
            if len(out) >= n:
                break
    return out


def detecter_separateur(texte: str) -> str | None:
    """Le séparateur qui découpe l'échantillon en un nombre de colonnes le plus
    CONSTANT (et > 1). `None` : fichier à une seule colonne.

    `csv.Sniffer` n'est pas utilisé : sur un fichier d'une colonne d'emails il
    « détecte » volontiers `.` ou `@` comme séparateur.
    """
    echantillon = _lignes_non_vides(texte)
    if not echantillon:
        return None
    meilleur, meilleur_score = None, (0.0, 0)
    for sep in SEPARATEURS:
        largeurs = [len(r) for r in csv.reader(echantillon, delimiter=sep)]
        largeur, freq = Counter(largeurs).most_common(1)[0]
        if largeur < 2:
            continue
        score = (freq / len(largeurs), largeur)
        if score > meilleur_score:
            meilleur, meilleur_score = sep, score
    return meilleur


def _libelle(cellule: str) -> str:
    return " ".join(cellule.strip().strip("\"'").lower().replace("_", " ").split()) \
        .replace("é", "e").replace("è", "e").rstrip(" :")


def detecter_en_tete(premieres: list[str]) -> tuple[bool, bool, str]:
    """(en-tête ?, certain ?, motif) d'après les premières cellules non vides."""
    if not premieres:
        return False, True, "fichier vide"
    tete = premieres[0]
    if adresses.syntaxe_valide(adresses.normaliser(tete)):
        return False, True, "la première ligne est déjà une adresse"
    lib = _libelle(tete)
    if lib in EN_TETES or "mail" in lib or "courriel" in lib:
        return True, True, f"libellé reconnu : « {tete.strip()[:40]} »"
    suite = premieres[1:6]
    valides = sum(adresses.syntaxe_valide(adresses.normaliser(c)) for c in suite)
    if "@" not in tete:
        if suite and valides >= max(1, len(suite) // 2):
            return True, True, "texte sans @ suivi d'adresses"
        return True, False, "texte sans @, mais la suite n'est pas faite d'adresses"
    # Un @ dans une cellule invalide : plutôt une adresse abîmée qu'un titre.
    return False, False, "la première ligne ressemble à une adresse mal formée"


def motif_invalidite(email: str) -> str:
    if not email:
        return "vide après nettoyage"
    if "@" not in email:
        return "pas de @"
    if email.count("@") > 1:
        return "plusieurs @"
    local, domaine = email.split("@")
    if not local:
        return "partie avant @ vide"
    if "." not in domaine:
        return "domaine sans extension"
    if " " in email:
        return "espace dans l'adresse"
    if len(email) > 254 or len(local) > 64:
        return "trop longue"
    return "caractère ou format non accepté"


def analyser(donnees: bytes, en_tete: bool | None = None) -> dict:
    """Analyse complète. `en_tete` : décision imposée par le superadmin, sinon devinée.

    Renvoie les métadonnées, les compteurs, un rapport (adresses masquées) et
    `destinataires` : une entrée par adresse DISTINCTE, valide ou non, dans l'ordre
    de première apparition.
    """
    texte, encodage = decoder(donnees)
    texte = texte.replace("\x00", "")
    sep = detecter_separateur(texte)
    # Une seule colonne : la ligne entière est la cellule, virgules comprises —
    # « jean@x.fr, » ne doit pas perdre sa moitié à cause d'un séparateur supposé.
    if sep is None:
        lignes = [[l] if l.strip() else [] for l in texte.splitlines()]
    else:
        lignes = list(csv.reader(io.StringIO(texte, newline=""), delimiter=sep))

    premieres = [r[0] for r in lignes if r and r[0].strip()][:6]
    devine, certain, motif = detecter_en_tete(premieres)
    force = en_tete is not None
    avec_en_tete = en_tete if force else devine

    # L'en-tête est la première ligne NON VIDE, pas forcément la ligne 1.
    debut = 0
    nom_colonne = None
    if avec_en_tete:
        while debut < len(lignes) and not (lignes[debut] and lignes[debut][0].strip()):
            debut += 1
        if debut < len(lignes):
            nom_colonne = lignes[debut][0].strip()[:200]
            debut += 1

    total = vides = invalides = doublons = 0
    vus: dict[str, int] = {}            # hash → index dans `destinataires`
    destinataires: list[dict] = []
    erreurs: list[dict] = []
    apercu: list[dict] = []
    motifs = Counter()

    for i in range(debut, len(lignes)):
        rang = i + 1                    # numéro de ligne physique, 1 = première
        total += 1
        brut = lignes[i][0] if lignes[i] else ""
        if not brut.strip():
            vides += 1
            statut = "empty"
            email = ""
        else:
            email = adresses.normaliser(brut)
            if adresses.syntaxe_valide(email):
                h = adresses.hacher(email)
                if h in vus:
                    doublons += 1
                    statut = "duplicate"
                else:
                    vus[h] = len(destinataires)
                    destinataires.append({"ligne": rang, "email": email, "hash": h,
                                          "statut": "imported"})
                    statut = "imported"
            else:
                invalides += 1
                statut = "invalid_syntax"
                m = motif_invalidite(email)
                motifs[m] += 1
                if len(erreurs) < ECHANTILLON_ERREURS:
                    erreurs.append({"ligne": rang, "valeur": adresses.masquer(email or brut.strip()),
                                    "motif": m})
                # Gardée une fois, pour pouvoir la montrer ; jamais soumise.
                h = adresses.hacher(email or brut.strip())
                if h not in vus:
                    vus[h] = len(destinataires)
                    destinataires.append({"ligne": rang, "email": email or brut.strip()[:320],
                                          "hash": h, "statut": "invalid_syntax"})
        if len(apercu) < APERCU_LIGNES:
            apercu.append({"ligne": rang, "valeur": brut.strip()[:320],
                           "normalise": email, "statut": statut})

    uniques = sum(1 for d in destinataires if d["statut"] == "imported")
    assert total == vides + invalides + uniques + doublons, "invariant de comptage rompu"

    return {
        "encodage": encodage,
        "separateur": sep,
        "separateur_nom": NOMS_SEPARATEURS.get(sep, "aucun (une seule colonne)"),
        "colonnes": max((len(r) for r in lignes), default=0),
        "en_tete": avec_en_tete,
        "en_tete_force": force,
        "en_tete_devine": devine,
        "en_tete_certain": certain if not force else True,
        "en_tete_motif": motif,
        "nom_colonne": nom_colonne,
        "compteurs": {"lignes_brutes": total, "vides": vides, "syntaxe_invalide": invalides,
                      "uniques": uniques, "doublons": doublons,
                      "extraites": total - vides},
        "motifs_invalidite": dict(motifs.most_common()),
        "erreurs": erreurs,
        "apercu": apercu,
        "destinataires": destinataires,
    }


def apercu(donnees: bytes, en_tete: bool | None = None) -> dict:
    """Ce que l'écran d'import affiche tout de suite après le dépôt, avant le job.

    Analyse complète mais sans rien écrire. Les adresses de l'aperçu restent en
    clair : c'est une réponse au superadmin, pas un log ni un rapport stocké.
    """
    r = analyser(donnees, en_tete)
    r.pop("destinataires")
    return r


# ── Moitié écrivante ─────────────────────────────────────────────────────────

def _reglages() -> dict:
    return pg.ligne("SELECT max_csv_bytes, max_recipients_per_campaign FROM settings") or {
        "max_csv_bytes": 50 * 1024 * 1024, "max_recipients_per_campaign": 100000}


def _supprimes(hashes: list[str], campaign_id: str) -> dict[str, str]:
    """hash → motif, pour les adresses de la liste de suppression (globale ou
    propre à cette campagne)."""
    if not hashes:
        return {}
    lignes = pg.lignes("""
        SELECT DISTINCT ON (email_hash) email_hash, reason
          FROM suppressions
         WHERE email_hash = ANY(%(h)s)
           AND (scope = 'global' OR (scope = 'campaign' AND scope_id = %(c)s))
         ORDER BY email_hash, occurred_at
    """, {"h": hashes, "c": campaign_id})
    return {l["email_hash"]: l["reason"] for l in lignes}


def executer(job: dict) -> dict:
    """Point d'entrée du worker. Lève `ErreurDefinitive` quand réessayer est vain."""
    p = job.get("payload") or {}
    campaign_id = job.get("campaign_id")
    cle = p.get("storage_key")
    nom = (p.get("original_filename") or "cible.csv")[:255]
    en_tete = p.get("en_tete")
    acteur = p.get("acteur") or "inconnu"
    if not campaign_id or not cle:
        raise ErreurDefinitive("charge utile incomplète : campaign_id et storage_key requis")
    if en_tete is not None and not isinstance(en_tete, bool):
        raise ErreurDefinitive("en_tete doit être true, false ou absent")

    reglages = _reglages()
    try:
        donnees = stockage.lire(cle)
    except stockage.StockageErreur as e:
        raise ErreurDefinitive(f"fichier inutilisable : {e}") from e
    if len(donnees) > reglages["max_csv_bytes"]:
        raise ErreurDefinitive(
            f"fichier trop volumineux ({len(donnees) / 1048576:.1f} Mo, "
            f"maximum {reglages['max_csv_bytes'] / 1048576:.0f} Mo)")
    empreinte = cle.rsplit("/", 1)[1].split(".")[0]

    a = analyser(donnees, en_tete)
    c = a["compteurs"]
    if c["uniques"] > reglages["max_recipients_per_campaign"]:
        raise ErreurDefinitive(
            f"{c['uniques']} adresses uniques, au-delà du maximum de "
            f"{reglages['max_recipients_per_campaign']} par campagne")

    valides = [d for d in a["destinataires"] if d["statut"] == "imported"]
    supprimes = _supprimes([d["hash"] for d in valides], campaign_id)
    eligibles_mailnjoy = len(valides) - len(supprimes)

    rapport = {k: a[k] for k in ("separateur_nom", "colonnes", "en_tete_devine",
                                 "en_tete_certain", "en_tete_motif",
                                 "motifs_invalidite", "erreurs")}
    # L'aperçu stocké est MASQUÉ : il vit en base, donc il obéit à la règle des logs.
    rapport["apercu"] = [{**l, "valeur": adresses.masquer(l["valeur"]),
                          "normalise": adresses.masquer(l["normalise"])}
                         for l in a["apercu"]]
    rapport["suppressions"] = dict(Counter(supprimes.values()))

    with pg.connexion() as cur:
        cur.execute("""SELECT status, target_version_id, subject, html_storage_key
                         FROM campaigns WHERE id = %(c)s FOR UPDATE""", {"c": campaign_id})
        camp = cur.fetchone()
        if not camp:
            raise ErreurDefinitive("campagne introuvable")
        if camp["status"] not in STATUTS_MODIFIABLES:
            raise ErreurDefinitive(
                f"cible verrouillée : la campagne est en « {camp['status']} »")

        # Idempotence : même fichier, même décision d'en-tête, déjà la cible
        # courante et pas encore figée → rien à refaire.
        cur.execute("""
            SELECT id, version FROM campaign_target_versions
             WHERE id = %(v)s AND file_hash = %(h)s AND header_detected = %(e)s
               AND frozen_at IS NULL
        """, {"v": camp["target_version_id"], "h": empreinte, "e": a["en_tete"]})
        existante = cur.fetchone()
        if existante:
            return {"target_version_id": str(existante["id"]),
                    "version": existante["version"], "deja_importe": True,
                    "compteurs": c, "eligibles_mailnjoy": eligibles_mailnjoy}

        cur.execute("""SELECT COALESCE(max(version), 0) + 1 AS v
                         FROM campaign_target_versions WHERE campaign_id = %(c)s""",
                    {"c": campaign_id})
        version = cur.fetchone()["v"]

        cur.execute("""
            INSERT INTO campaign_target_versions
                (campaign_id, version, original_filename, file_hash, storage_key,
                 file_size_bytes, encoding, delimiter, first_column_name,
                 header_detected, header_forced, total_rows, extracted_rows,
                 unique_emails, empty_rows, invalid_syntax_count, duplicate_count,
                 suppression_count, validation_eligible_count, analysis_report)
            VALUES (%(c)s, %(v)s, %(nom)s, %(h)s, %(k)s, %(taille)s, %(enc)s, %(sep)s,
                    %(col)s, %(et)s, %(force)s, %(tot)s, %(ext)s, %(uni)s, %(vid)s,
                    %(inv)s, %(dbl)s, %(sup)s, %(elig)s, %(rap)s::jsonb)
            RETURNING id
        """, {"c": campaign_id, "v": version, "nom": nom, "h": empreinte, "k": cle,
              "taille": len(donnees), "enc": a["encodage"], "sep": a["separateur"],
              "col": a["nom_colonne"], "et": a["en_tete"], "force": a["en_tete_force"],
              "tot": c["lignes_brutes"], "ext": c["extraites"], "uni": c["uniques"],
              "vid": c["vides"], "inv": c["syntaxe_invalide"], "dbl": c["doublons"],
              "sup": len(supprimes), "elig": eligibles_mailnjoy,
              "rap": json.dumps(rapport, ensure_ascii=False)})
        tv_id = cur.fetchone()["id"]

        # Suppression et syntaxe tranchées dès l'import : ces adresses ne partiront
        # pas chez Mailnjoy (crédits) et `create_validation_batches` ne prend que
        # import_status = 'imported' AND eligibility_status = 'pending'.
        rangs = []
        for d in a["destinataires"]:
            if d["statut"] == "invalid_syntax":
                rangs.append((tv_id, campaign_id, d["email"], d["hash"], d["ligne"],
                              "invalid_syntax", "invalid", "syntaxe (import)",
                              "excluded", "invalid_syntax", None))
            elif d["hash"] in supprimes:
                rangs.append((tv_id, campaign_id, d["email"], d["hash"], d["ligne"],
                              "imported", "pending", None,
                              "excluded", "suppressed", supprimes[d["hash"]]))
            else:
                rangs.append((tv_id, campaign_id, d["email"], d["hash"], d["ligne"],
                              "imported", "pending", None, "pending", None, None))
        psycopg2.extras.execute_values(cur, """
            INSERT INTO recipients
                (target_version_id, campaign_id, email_normalized, email_hash,
                 original_row_number, import_status, validation_status,
                 validation_reason, eligibility_status, eligibility_reason,
                 suppression_status)
            VALUES %s
            ON CONFLICT (target_version_id, email_hash) DO NOTHING
        """, rangs, page_size=1000)

        # Nouvelle cible = validation et préflight à refaire (règles de transition).
        pret = bool(camp["subject"] and camp["html_storage_key"] and eligibles_mailnjoy > 0)
        cur.execute("""
            UPDATE campaigns
               SET target_version_id = %(tv)s, target_version = %(v)s,
                   status = %(s)s, preflight_snapshot = NULL, updated_at = now()
             WHERE id = %(c)s
        """, {"tv": tv_id, "v": version, "c": campaign_id,
              "s": "ready_for_validation" if pret else "draft"})

        cur.execute("""
            INSERT INTO campaign_events (campaign_id, actor_type, actor_id, event_type,
                                         summary, payload)
            VALUES (%(c)s, 'worker', %(a)s, 'target.imported', %(r)s, %(p)s::jsonb)
        """, {"c": campaign_id, "a": acteur,
              "r": (f"Cible v{version} importée : {c['uniques']} adresses uniques, "
                    f"{eligibles_mailnjoy} à valider"),
              "p": json.dumps({"target_version_id": str(tv_id), "fichier": nom,
                               "file_hash": empreinte, "compteurs": c,
                               "suppressions": len(supprimes),
                               "statut_precedent": camp["status"]}, ensure_ascii=False)})

    return {"target_version_id": str(tv_id), "version": version, "deja_importe": False,
            "compteurs": c, "suppressions": len(supprimes),
            "eligibles_mailnjoy": eligibles_mailnjoy,
            "en_tete": a["en_tete"], "en_tete_certain": a["en_tete_certain"]}


if __name__ == "__main__":
    # Aperçu en ligne de commande : python3 jobs/analyze_csv.py fichier.csv [oui|non]
    chemin = Path(sys.argv[1])
    force = {"oui": True, "non": False}.get(sys.argv[2]) if len(sys.argv) > 2 else None
    r = apercu(chemin.read_bytes(), force)
    r["apercu"] = [{**l, "valeur": adresses.masquer(l["valeur"]),
                    "normalise": adresses.masquer(l["normalise"])} for l in r["apercu"]]
    print(json.dumps(r, ensure_ascii=False, indent=1))
