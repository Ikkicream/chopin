#!/usr/bin/env python3
"""opportunites.py — Du « je signe » au contrat signé.

Le tunnel s'arrêtait au rappel. Quand un prospect disait oui au téléphone, il n'y avait
nulle part où le dire : le commercial notait dans un carnet, prévenait quelqu'un de vive
voix, et l'affaire vivait dans une messagerie. Ce module ferme la boucle.

**Trois états, et rien de plus** — chaque état correspond à un geste réel de quelqu'un :

    à valider  →  contrat envoyé  →  signé
                                 ↘   perdu

  - `a_valider` : le commercial a eu un oui. Il ne vend pas seul : il transmet.
  - `contrat_envoye` : le responsable a vu l'opportunité et a envoyé le contrat.
  - `signe` / `perdu` : la fin, dans un sens ou dans l'autre.

Un état de plus serait un état que personne ne mettrait à jour.

**L'origine du lead est FIGÉE à la création.** D'où vient ce prospect — scraping Serper ou
Basile, import manuel, formulaire, campagne qui l'a fait cliquer — est recopié dans
l'opportunité au moment où elle naît. Si le contact est nettoyé, réattribué ou supprimé six
mois plus tard, on saura toujours ce qui a produit cette vente. Une opportunité qui perd sa
provenance ne permet plus de savoir ce qui marche, donc plus de décider où investir.

**Le montant et la commission ne sont pas devinés.** Ils sont saisis par le responsable au
moment du contrat. Tant qu'ils sont vides, la page Ventes le dit au lieu d'afficher zéro.
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

ETATS = {
    "a_valider": {"label": "À valider", "aide": "Le commercial a eu un accord verbal",
                  "ordre": 1},
    "contrat_envoye": {"label": "Contrat envoyé", "aide": "En attente de signature",
                       "ordre": 2},
    "signe": {"label": "Signé", "aide": "Client", "ordre": 3},
    "perdu": {"label": "Perdu", "aide": "L'affaire ne se fera pas", "ordre": 4},
}

COMMISSION_DEFAUT = 10.0   # %, modifiable par opportunité

SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunites (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    site_code      text NOT NULL,
    email          text NOT NULL,
    contact_id     uuid,
    -- Identité recopiée : la fiche client doit rester lisible même si le contact bouge.
    societe        text,
    prenom         text,
    nom            text,
    tel            text,
    ville          text,
    dept_code      text,
    secteur        text,
    -- Provenance figée au moment du oui.
    origine        text,
    origine_detail text,
    -- Qui vend, qui valide.
    commercial     text NOT NULL,
    responsable    text,
    -- L'argent, saisi et non deviné.
    montant_mensuel numeric(10,2),
    commission_pct  numeric(5,2),
    -- Le cycle.
    statut         text NOT NULL DEFAULT 'a_valider',
    notes          text,
    cree_le        timestamptz NOT NULL DEFAULT now(),
    maj_le         timestamptz NOT NULL DEFAULT now(),
    contrat_le     timestamptz,
    signe_le       timestamptz,
    perdu_motif    text,
    UNIQUE (site_code, email)
);
CREATE INDEX IF NOT EXISTS idx_opp_statut ON opportunites (site_code, statut, cree_le DESC);
CREATE INDEX IF NOT EXISTS idx_opp_commercial ON opportunites (commercial);
"""


def _pool():
    import pool_pg
    return pool_pg


def _assurer() -> None:
    p = _pool()
    c = p._conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute(SCHEMA)
    finally:
        p._rendre(c)


LIBELLE_ORIGINE = {
    "serper": "Scraping Google Places",
    "basile": "Registre B2B (Basile)",
    "manual": "Import manuel",
    "sweego": "Campagne email de masse",
    "tally": "Formulaire du site",
}


def provenance(site: str, email: str) -> dict:
    """D'où vient ce lead — reconstitué au moment où l'opportunité naît, puis figé.

    Trois sources d'information, de la plus précise à la plus grossière : la campagne qui
    l'a fait cliquer (on sait exactement quel message a marché), l'état commercial du
    contact (a-t-il rempli un formulaire ?), et à défaut la source de collecte.
    """
    p = _pool()
    origine, detail = "inconnue", ""
    try:
        r = p._q("""SELECT primary_source, created_at::date::text
                    FROM contacts WHERE email::text = %s""", (email,))
        if r:
            origine = LIBELLE_ORIGINE.get(r[0][0] or "", r[0][0] or "inconnue")
            detail = f"collecté le {r[0][1]}"
    except Exception:  # noqa: BLE001
        pass
    try:
        r = p._q("""SELECT campagne, clicked_at::date::text, opened_at::date::text
                    FROM campaign_recipients
                    WHERE site_code = %s AND email = %s
                    ORDER BY clicked_at DESC NULLS LAST, sent_at DESC LIMIT 1""",
                 (site, email))
        if r:
            camp, clic, ouv = r[0]
            if clic:
                detail = f"a cliqué le {clic} dans « {camp or 'une campagne'} » · {detail}"
            elif ouv:
                detail = f"a ouvert le {ouv} dans « {camp or 'une campagne'} » · {detail}"
    except Exception:  # noqa: BLE001
        pass
    try:
        r = p._q("""SELECT state, source FROM contact_sites cs
                    JOIN contacts c ON c.id = cs.contact_id
                    WHERE cs.site_code = %s AND c.email::text = %s""", (site, email))
        if r and (r[0][1] or "").lower() in ("tally", "formulaire", "form"):
            origine = LIBELLE_ORIGINE["tally"]
    except Exception:  # noqa: BLE001
        pass
    return {"origine": origine, "detail": detail.strip(" ·")}


def creer(site: str, email: str, commercial: str, notes: str = "") -> dict:
    """« Le client dit oui. » Crée l'opportunité et la met dans la file du responsable."""
    _assurer()
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "error": "email invalide"}
    p = _pool()
    fiche = {}
    try:
        r = p._q("""SELECT id::text, societe, prenom, nom, tel, city, dept_code,
                           COALESCE(sectors[1], '')
                    FROM contacts WHERE email::text = %s""", (email,))
        if r:
            k = ["contact_id", "societe", "prenom", "nom", "tel", "ville", "dept_code", "secteur"]
            fiche = dict(zip(k, r[0]))
    except Exception:  # noqa: BLE001
        pass
    prov = provenance(site, email)
    c = p._conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute("""
                    INSERT INTO opportunites (site_code, email, contact_id, societe, prenom,
                        nom, tel, ville, dept_code, secteur, origine, origine_detail,
                        commercial, notes, commission_pct)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (site_code, email) DO UPDATE SET
                        maj_le = now(),
                        notes = COALESCE(NULLIF(EXCLUDED.notes,''), opportunites.notes)
                    RETURNING id::text, statut, (xmax = 0) AS creee
                """, (site, email, fiche.get("contact_id"), fiche.get("societe"),
                      fiche.get("prenom"), fiche.get("nom"), fiche.get("tel"),
                      fiche.get("ville"), fiche.get("dept_code"), fiche.get("secteur"),
                      prov["origine"], prov["detail"], commercial, notes or None,
                      COMMISSION_DEFAUT))
                oid, statut, creee = cur.fetchone()
    finally:
        p._rendre(c)
    # La fiche d'appel doit porter la trace : le commercial suivant doit savoir que
    # l'affaire est déjà remontée, sinon il rappelle un client signé.
    try:
        import followup_backend as fb
        fb.journaliser(site, email, commercial, "opportunite",
                       "Accord verbal — opportunité transmise au responsable")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "id": oid, "statut": statut, "nouvelle": bool(creee),
            "societe": fiche.get("societe") or email, "origine": prov["origine"]}


_COLS = ["id", "email", "societe", "prenom", "nom", "tel", "ville", "dept_code", "secteur",
         "origine", "origine_detail", "commercial", "responsable", "montant_mensuel",
         "commission_pct", "statut", "notes", "cree_le", "contrat_le", "signe_le",
         "perdu_motif"]


def lister(site: str, statut: str = "", commercial: str = "") -> list[dict]:
    _assurer()
    where, args = ["site_code = %s"], [site]
    if statut:
        where.append("statut = %s"); args.append(statut)
    if commercial:
        where.append("commercial = %s"); args.append(commercial)
    lignes = _pool()._q(f"""
        SELECT id::text, email, societe, prenom, nom, tel, ville, dept_code, secteur,
               origine, origine_detail, commercial, responsable,
               montant_mensuel::float8, commission_pct::float8, statut, notes,
               cree_le::text, contrat_le::text, signe_le::text, perdu_motif
        FROM opportunites WHERE {' AND '.join(where)}
        ORDER BY CASE statut WHEN 'a_valider' THEN 0 WHEN 'contrat_envoye' THEN 1
                             WHEN 'signe' THEN 2 ELSE 3 END, cree_le DESC""", tuple(args))
    return [dict(zip(_COLS, r)) for r in lignes]


def changer(site: str, oid: str, statut: str, par: str, **champs) -> dict:
    """Fait avancer une opportunité. Les horodatages sont posés par le SERVEUR : une date
    de signature saisie à la main finit toujours par mentir."""
    if statut not in ETATS:
        return {"ok": False, "error": f"état inconnu : {statut}"}
    _assurer()
    sets = ["statut = %s", "maj_le = now()"]
    args: list = [statut]
    if statut == "contrat_envoye":
        sets.append("contrat_le = COALESCE(contrat_le, now())")
        sets.append("responsable = COALESCE(%s, responsable)"); args.append(par)
    if statut == "signe":
        sets.append("signe_le = COALESCE(signe_le, now())")
    for cle, colonne in (("montant_mensuel", "montant_mensuel"),
                         ("commission_pct", "commission_pct"),
                         ("notes", "notes"), ("perdu_motif", "perdu_motif"),
                         ("responsable", "responsable")):
        if champs.get(cle) not in (None, ""):
            sets.append(f"{colonne} = %s"); args.append(champs[cle])
    args += [site, oid]
    p = _pool()
    c = p._conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute(f"UPDATE opportunites SET {', '.join(sets)} "
                            f"WHERE site_code = %s AND id = %s RETURNING email", tuple(args))
                r = cur.fetchone()
    finally:
        p._rendre(c)
    if not r:
        return {"ok": False, "error": "opportunité introuvable"}
    try:
        import followup_backend as fb
        fb.journaliser(site, r[0], par, "opportunite",
                       f"Opportunité → {ETATS[statut]['label']}")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "id": oid, "statut": statut}


def ventes(site: str) -> dict:
    """Le récapitulatif commercial : ce qui est signé, ce qui est en cours, les commissions.

    Le revenu récurrent est mensuel : on l'affiche tel quel ET en annuel, parce que les
    deux servent — le mensuel pour piloter, l'annuel pour se situer.
    """
    _assurer()
    p = _pool()
    def bloc(statut: str) -> dict:
        r = p._q("""SELECT count(*), COALESCE(sum(montant_mensuel), 0)::float8,
                           count(montant_mensuel)
                    FROM opportunites WHERE site_code = %s AND statut = %s""",
                 (site, statut))[0]
        return {"nombre": r[0], "mrr": r[1], "chiffres_saisis": r[2]}
    par_commercial = [{"commercial": r[0], "signes": r[1], "mrr": r[2],
                       "commission_mensuelle": r[3]}
                      for r in p._q("""
        SELECT commercial, count(*),
               COALESCE(sum(montant_mensuel), 0)::float8,
               COALESCE(sum(montant_mensuel * commission_pct / 100), 0)::float8
        FROM opportunites WHERE site_code = %s AND statut = 'signe'
        GROUP BY commercial ORDER BY 3 DESC""", (site,))]
    signe = bloc("signe")
    return {
        "site": site,
        "a_valider": bloc("a_valider"),
        "contrat_envoye": bloc("contrat_envoye"),
        "signe": signe,
        "perdu": bloc("perdu"),
        "mrr": signe["mrr"],
        "arr": signe["mrr"] * 12,
        "commissions_mensuelles": sum(c["commission_mensuelle"] for c in par_commercial),
        "par_commercial": par_commercial,
        "commission_defaut": COMMISSION_DEFAUT,
        "etats": ETATS,
    }
