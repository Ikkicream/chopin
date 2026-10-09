#!/usr/bin/env python3
"""mass_mailing/jobs/capacite.py — pilotage adaptatif de délivrabilité (apprentissage de capacité).

Skill : .claude/skills/pilotage-delivrabilite/ (document de Camille, 27/09/2026). Contrôle de
congestion PAR FILE (IP d'envoi + domaine d'identité + type de flux + messagerie destinataire) :
on part de limites prudentes, on mesure les réponses SMTP (2xx / 4xx / 5xx), les plaintes et les
désinscriptions, on augmente lentement quand c'est sain et on réduit nettement au premier signal.

    ingerer()          webhook_events (delivered / soft_bounce / hard_bounce) → smtp_reponses
    classer_reponse()  taxonomie § 6.4 (fonction PURE, testée)
    evaluer()          met à jour capacite_files + écrit capacite_decisions (format § 15)
    tableau()          ce que montre l'onglet « Capacité » (max/jour et max/heure, par IP et messagerie)

Aucune affirmation de quota fournisseur : tout est « appris sur nos envois » (hypothèse = vrai).
Une nouvelle IP d'envoi ou un nouveau domaine d'identité crée ses propres files, chauffe à zéro.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import pg  # noqa: E402

PARIS = ZoneInfo("Europe/Paris")
FENETRE_ENVOI = (8, 22)          # Camille, 27/09 : Mass Email envoie de 8h à 22h
REPRISE_APRES_PAUSE_H = 48       # reprise prudente 48 h après la dernière suspension (30/09)
HEURES_FENETRE = FENETRE_ENVOI[1] - FENETRE_ENVOI[0]
ECHANTILLON_MIN_24H = 20

# Profils de départ (skill § 5 = source § 9, valeurs basses = prudentes) : débit/h, plafond J1, hausse/jour.
PROFILS = {
    "gmail": (100, 300, 1.15), "microsoft": (50, 150, 1.10), "yahoo": (50, 100, 1.10),
    "orange": (40, 100, 1.10), "laposte": (40, 100, 1.10), "free": (40, 100, 1.10), "sfr": (40, 100, 1.10),
    "icloud": (40, 100, 1.10), "bouygues": (40, 100, 1.10), "gmx": (40, 100, 1.10), "autres": (100, 150, 1.15),
}
NOMS = {"gmail": "Gmail", "microsoft": "Outlook / Hotmail", "yahoo": "Yahoo / AOL", "orange": "Orange", "laposte": "La Poste",
        "free": "Free", "sfr": "SFR", "icloud": "iCloud", "bouygues": "Bouygues", "gmx": "GMX", "autres": "Autres (B2B…)"}


def groupe_de(domaine: str) -> str:
    d = (domaine or "").lower().strip()
    base = d.split(".")[0]
    if d in ("gmail.com", "googlemail.com"):
        return "gmail"
    if base in ("outlook", "hotmail", "live") or d == "msn.com":
        return "microsoft"
    if base in ("yahoo", "aol") or d == "ymail.com":
        return "yahoo"
    if d in ("orange.fr", "wanadoo.fr"):
        return "orange"
    if d == "laposte.net":
        return "laposte"
    if d in ("free.fr", "aliceadsl.fr", "libertysurf.fr"):
        return "free"
    if d in ("sfr.fr", "neuf.fr", "club-internet.fr", "numericable.fr"):
        return "sfr"
    if d in ("icloud.com", "me.com", "mac.com"):
        return "icloud"
    if d == "bbox.fr":
        return "bouygues"
    if base == "gmx":
        return "gmx"
    return "autres"


# ── Taxonomie SMTP (source § 6.4) ─────────────────────────────────────────────

_LIMITE = re.compile(r"rate|too many|throttl|try again later|\bTS0\d|4\.7\.65[0-2]|4\.7\.28|S3115|maximum number of connections|OFR_?(104|109|98[89]|990)|temporarily deferred|slow down", re.I)
_POLITIQUE = re.compile(r"spam|policy|blocked|blacklist|block list|reputation|5\.7\.1\b|5\.7\.515|OFR_?(506|536)|GU_EIB", re.I)
_AUTH = re.compile(r"5\.7\.(26|27|30|32|40)|dmarc|spf|dkim|unauthenticated|not authenticated", re.I)
_INCONNU = re.compile(r"5\.1\.1|user unknown|unknown user|no such user|mailbox (not found|unavailable|does not exist)|recipient (address )?rejected|invalid recipient|account (has been )?disabled|mailbox is disabled|does not exist", re.I)
_DOMAINE = re.compile(r"5\.1\.2|domain not found|host not found|no mx|nxdomain", re.I)
_PLEINE = re.compile(r"mailbox full|over ?quota|quota exceeded|4\.2\.2|5\.2\.2|insufficient storage", re.I)
_GRIS = re.compile(r"greylist|graylist|try again in", re.I)
_OCCUPE = re.compile(r"service (not )?available|busy|4\.3\.\d|4\.4\.\d|connection|timed? ?out", re.I)
_CONTENU = re.compile(r"content|url|link|message (was )?rejected as|5\.7\.0.*(content|url)", re.I)


def classer_reponse(etat: str, code: int | None, texte: str) -> str:
    """accepted / transient_* / permanent_* (fonction PURE)."""
    t = texte or ""
    if etat == "accepted" or (code and 200 <= code < 300):
        return "accepted"
    temporaire = etat in ("deferred", "soft_bounce") or (code is not None and 400 <= code < 500)
    if temporaire:
        if _PLEINE.search(t):
            return "transient_mailbox_full"
        if _GRIS.search(t):
            return "transient_greylisting"
        if _LIMITE.search(t):
            return "transient_rate_limit"
        if _OCCUPE.search(t):
            return "transient_server_busy"
        return "transient_unknown"
    if _AUTH.search(t):
        return "permanent_authentication"
    if _INCONNU.search(t):
        return "permanent_invalid_recipient"
    if _DOMAINE.search(t):
        return "permanent_invalid_domain"
    if _POLITIQUE.search(t):
        return "permanent_policy_or_spam"
    if _CONTENU.search(t):
        return "permanent_content_or_url"
    return "permanent_unknown"


def _codes(texte: str, response_code) -> tuple[int | None, str | None]:
    code = None
    try:
        code = int(response_code) if response_code not in (None, "") else None
    except (TypeError, ValueError):
        code = None
    m = re.search(r"\b([245]\d\d)[ -]+([245]\.\d{1,3}\.\d{1,3})?", texte or "")
    if m:
        code = code or int(m.group(1))
    etendu = m.group(2) if m and m.group(2) else None
    return code, etendu


def analyser_evenement(event_type: str, p: dict) -> dict | None:
    """Une réponse SMTP normalisée à partir d'un événement webhook Sweego (fonction PURE)."""
    t = (event_type or "").lower().replace("-", "_")
    if t not in ("delivered", "soft_bounce", "hard_bounce"):
        return None
    d = str(p.get("details") or "")
    ip = re.search(r"\bsrc=([0-9a-fA-F:.]+)", d)
    zone = re.search(r"\bSender/([A-Za-z0-9_\-]+)", d)
    mx = re.search(r"\bmx=([^\s\[]+)", d)
    dest = str(p.get("recipient") or "").lower()
    etat = {"delivered": "accepted", "soft_bounce": "deferred", "hard_bounce": "hard_bounce"}[t]
    code, etendu = _codes(d, p.get("response_code"))
    if etat == "accepted":
        code = code if code and 200 <= code < 300 else 250
    reponse = d.split(" (", 1)[1][:400] if " (" in d else d[-400:]
    return {
        "event_id": str(p.get("event_id") or p.get("swg_uid") or ""),
        "at": p.get("timestamp"), "sending_ip": ip.group(1) if ip else "inconnue",
        "identite": (p.get("domain_from") or "inconnu").lower(), "flux": (p.get("campaign_type") or "market").lower(),
        "domaine_dest": dest.rsplit("@", 1)[-1] if "@" in dest else "", "mx": mx.group(1) if mx else None,
        "zone_sweego": zone.group(1) if zone else None, "etat": etat, "code": code, "code_etendu": etendu,
        "categorie": classer_reponse(etat, code, d), "reponse": reponse,
    }


# ── Base : ingestion ──────────────────────────────────────────────────────────

def ingerer(limite: int = 5000) -> int:
    dernier = pg.valeur("SELECT COALESCE(max(webhook_id), 0) FROM smtp_reponses") or 0
    evts = pg.lignes("""SELECT id, event_type, campaign_id, email_hash, raw_payload, received_at FROM webhook_events
                         WHERE id > %(d)s AND replace(event_type, '-', '_') IN ('delivered', 'soft_bounce', 'hard_bounce')
                         ORDER BY id LIMIT %(l)s""", {"d": dernier, "l": limite})
    n = 0
    for e in evts:
        r = analyser_evenement(e["event_type"], e["raw_payload"] or {})
        if not r or not r["event_id"]:
            continue
        r["groupe"] = groupe_de(r["domaine_dest"])
        at = r["at"] or e["received_at"]
        n += pg.ecrire("""INSERT INTO smtp_reponses (event_id, webhook_id, at, campaign_id, email_hash, sending_ip, identite,
                                flux, groupe, domaine_dest, mx, zone_sweego, etat, code, code_etendu, categorie, reponse)
                          VALUES (%(ev)s, %(w)s, %(at)s, %(c)s, %(h)s, %(ip)s, %(id)s, %(fx)s, %(g)s, %(dd)s, %(mx)s,
                                  %(z)s, %(et)s, %(co)s, %(ce)s, %(ca)s, %(re)s)
                          ON CONFLICT (event_id) DO NOTHING""",
                       {"ev": r["event_id"], "w": e["id"], "at": at, "c": e["campaign_id"], "h": e["email_hash"],
                        "ip": r["sending_ip"], "id": r["identite"], "fx": r["flux"], "g": r["groupe"],
                        "dd": r["domaine_dest"], "mx": r["mx"], "z": r["zone_sweego"], "et": r["etat"],
                        "co": r["code"], "ce": r["code_etendu"], "ca": r["categorie"], "re": r["reponse"]}) or 0
    return n


# ── Évaluation : décisions par file (source § 7, format § 15) ─────────────────

def cle_de(ip, identite, flux, groupe) -> str:
    return f"{ip}|{identite}|{flux}|{groupe}"


def decider(etat: dict, m1: dict, m24: dict, aujourd_hui, maintenant: datetime | None = None) -> dict:
    """Décision PURE pour une file. `etat` : debit_heure, plafond_jour, derniere_hausse, jour_chauffe,
    groupe, etat ; m1 / m24 : métriques 1 h / 24 h. Renvoie {decision, etat, debit, motif, confiance}."""
    hausse = PROFILS.get(etat["groupe"], PROFILS["autres"])[2]
    debit = float(etat["debit_heure"])
    tent24 = m24["tentes"]
    plaintes24 = (m24["plaintes"] / m24["acceptes"] * 100) if m24["acceptes"] else 0.0
    if m24["critiques"] >= 2 or plaintes24 > 0.3:
        motif = (f"{m24['critiques']} refus de politique / spam / authentification sur 24 h" if m24["critiques"] >= 2
                 else f"plaintes {plaintes24:.2f} % > 0,3 %")
        return {"decision": "suspendre", "etat": "paused", "debit": debit, "motif": motif, "confiance": "élevée"}
    maintenant = maintenant or datetime.now(timezone.utc)
    # Reprise après pause (30/09 : Orange restait en pause pour toujours — sans envoi, « échantillon
    # insuffisant » maintenait la pause indéfiniment). 48 h après la DERNIÈRE suspension, sans nouvelle
    # plainte ni refus critique (vérifié juste au-dessus), la file repart à débit réduit de moitié.
    if etat.get("etat") == "paused":
        susp = etat.get("derniere_suspension")
        if susp is None or (maintenant - susp).total_seconds() >= REPRISE_APRES_PAUSE_H * 3600:
            return {"decision": "reprendre", "etat": "recovery", "debit": max(5.0, debit * 0.5),
                    "motif": f"reprise prudente : {REPRISE_APRES_PAUSE_H} h sans plainte ni refus critique depuis la suspension",
                    "confiance": "moyenne"}
        reste = REPRISE_APRES_PAUSE_H - (maintenant - susp).total_seconds() / 3600
        return {"decision": "maintenir", "etat": "paused", "debit": debit,
                "motif": f"en pause : reprise possible dans {reste:.0f} h si aucune nouvelle plainte", "confiance": "élevée"}
    # Période d'observation (source § 15 « réévaluation ») : pas de nouvelle baisse tant que la
    # précédente n'a pas eu le temps de produire son effet (1 h après un freinage, 24 h sinon).
    reduit = etat.get("dernier_reduit")
    depuis_baisse = (maintenant - reduit).total_seconds() if reduit else None
    if m1["limites"] >= 1:
        if depuis_baisse is not None and depuis_baisse < 3600:
            return {"decision": "maintenir", "etat": "throttled", "debit": debit,
                    "motif": "freinage en cours : déjà réduit il y a moins d'1 h, en observation", "confiance": "élevée"}
        return {"decision": "reduire", "etat": "throttled", "debit": max(5.0, debit * 0.5),
                "motif": f"{m1['limites']} réponse(s) de limitation de débit (4xx) sur 1 h", "confiance": "élevée"}
    taux_def1 = (m1["differes"] / m1["tentes"]) if m1["tentes"] else 0.0
    taux_hb24 = (m24["rebonds"] / tent24) if tent24 else 0.0
    if (m1["tentes"] >= 10 and taux_def1 > 0.05) or (tent24 >= ECHANTILLON_MIN_24H and taux_hb24 > 0.02):
        motif = (f"différés {taux_def1:.1%} sur 1 h" if taux_def1 > 0.05 else f"rebonds durs {taux_hb24:.1%} sur 24 h")
        if depuis_baisse is not None and depuis_baisse < 86400:
            return {"decision": "maintenir", "etat": "cautious", "debit": debit,
                    "motif": f"{motif} ; déjà réduit il y a moins de 24 h, en observation", "confiance": "moyenne"}
        return {"decision": "reduire", "etat": "cautious", "debit": max(5.0, debit * 0.7), "motif": motif, "confiance": "moyenne"}
    if tent24 < ECHANTILLON_MIN_24H:
        return {"decision": "maintenir", "etat": etat.get("etat") or "warming", "debit": debit,
                "motif": f"échantillon insuffisant ({tent24} tentatives sur 24 h, {ECHANTILLON_MIN_24H} requises)", "confiance": "faible"}
    if etat.get("derniere_hausse") == aujourd_hui:
        return {"decision": "maintenir", "etat": etat.get("etat") or "warming", "debit": debit,
                "motif": "sain ; une seule hausse par jour", "confiance": "moyenne"}
    return {"decision": "augmenter", "etat": "warming" if etat.get("jour_chauffe", 0) < 30 else "stable",
            "debit": debit * hausse, "motif": f"sain sur 24 h ({tent24} tentatives, rebonds {taux_hb24:.1%}, aucun freinage)",
            "confiance": "moyenne"}


def _metriques(f: dict, depuis: datetime) -> dict:
    r = pg.ligne("""SELECT count(*) AS tentes,
                           count(*) FILTER (WHERE etat = 'accepted') AS acceptes,
                           -- Par CATÉGORIE, pas par l'étiquette Sweego (qui appelle parfois « hard_bounce » un 451).
                           count(*) FILTER (WHERE categorie LIKE 'transient%%') AS differes,
                           count(*) FILTER (WHERE categorie LIKE 'permanent%%') AS rebonds,
                           count(*) FILTER (WHERE categorie = 'transient_rate_limit') AS limites,
                           count(*) FILTER (WHERE categorie IN ('permanent_policy_or_spam', 'permanent_authentication')) AS critiques
                      FROM smtp_reponses WHERE sending_ip = %(ip)s AND identite = %(id)s AND flux = %(fx)s
                       AND groupe = %(g)s AND at > %(d)s""",
                 {"ip": f["sending_ip"], "id": f["identite"], "fx": f["flux"], "g": f["groupe"], "d": depuis})
    m = {k: int(v or 0) for k, v in r.items()}
    # Plaintes = DESTINATAIRES distincts : Sweego renvoie la même plainte toutes les 15 min avec un
    # nouvel event_id (28/09 : 1 plainte comptée 7 fois).
    m["plaintes"] = int(pg.valeur("""SELECT count(DISTINCT lower(w.raw_payload->>'recipient')) FROM webhook_events w
                                      WHERE w.event_type ILIKE '%%complaint%%' AND w.received_at > %(d)s
                                        AND w.raw_payload->>'domain_from' = %(id)s
                                        AND split_part(lower(w.raw_payload->>'recipient'), '@', 2) = ANY(%(doms)s)""",
                                  {"d": depuis, "id": f["identite"], "doms": _domaines_du_groupe(f)}) or 0)
    return m


def _domaines_du_groupe(f: dict) -> list[str]:
    return [x["domaine_dest"] for x in pg.lignes(
        "SELECT DISTINCT domaine_dest FROM smtp_reponses WHERE groupe = %(g)s AND identite = %(id)s",
        {"g": f["groupe"], "id": f["identite"]})]


def evaluer() -> int:
    maintenant = datetime.now(timezone.utc)
    aujourd_hui = maintenant.astimezone(PARIS).date()
    files = pg.lignes("""SELECT DISTINCT sending_ip, identite, flux, groupe FROM smtp_reponses
                          WHERE at > now() - interval '30 days'""")
    for f in files:
        cle = cle_de(f["sending_ip"], f["identite"], f["flux"], f["groupe"])
        etat = pg.ligne("SELECT * FROM capacite_files WHERE cle = %(c)s", {"c": cle})
        if not etat:
            debit, plafond, _ = PROFILS.get(f["groupe"], PROFILS["autres"])
            pg.ecrire("""INSERT INTO capacite_files (cle, sending_ip, identite, flux, groupe, etat, debit_heure, plafond_jour)
                         VALUES (%(c)s, %(ip)s, %(id)s, %(fx)s, %(g)s, 'warming', %(d)s, %(p)s)""",
                      {"c": cle, "ip": f["sending_ip"], "id": f["identite"], "fx": f["flux"], "g": f["groupe"], "d": debit, "p": plafond})
            _journal(cle, "creer", "warming", None, debit, "nouvelle file : profil de départ prudent (skill § 5)", "—",
                     {}, f, plafond)
            etat = pg.ligne("SELECT * FROM capacite_files WHERE cle = %(c)s", {"c": cle})
        prm = {"ip": f["sending_ip"], "id": f["identite"], "fx": f["flux"], "g": f["groupe"]}
        m1 = _metriques(f, maintenant - timedelta(hours=1))
        m24 = _metriques(f, maintenant - timedelta(hours=24))
        jours = int(pg.valeur("""SELECT count(DISTINCT (at AT TIME ZONE 'Europe/Paris')::date) FROM smtp_reponses
                                  WHERE sending_ip = %(ip)s AND identite = %(id)s AND flux = %(fx)s AND groupe = %(g)s
                                    AND etat = 'accepted'""", prm) or 0)
        # Capacité apprise : plus gros volume horaire ACCEPTÉ sans aucune limitation dans l'heure.
        apprise = int(pg.valeur("""SELECT COALESCE(max(n), 0) FROM (
                                     SELECT date_trunc('hour', at) h, count(*) FILTER (WHERE etat = 'accepted') n,
                                            count(*) FILTER (WHERE categorie = 'transient_rate_limit') lim
                                       FROM smtp_reponses WHERE sending_ip = %(ip)s AND identite = %(id)s
                                        AND flux = %(fx)s AND groupe = %(g)s GROUP BY 1) x WHERE lim = 0""", prm) or 0)
        base = PROFILS.get(f["groupe"], PROFILS["autres"])
        plafond = int(base[1] * base[2] ** max(0, jours - 1))
        susp = pg.valeur("SELECT max(at) FROM capacite_decisions WHERE cle = %(c)s AND decision = 'suspendre'", {"c": cle})
        d = decider({**etat, "jour_chauffe": jours, "groupe": f["groupe"], "derniere_suspension": susp}, m1, m24, aujourd_hui, maintenant)
        ancien = float(etat["debit_heure"])
        pg.ecrire("""UPDATE capacite_files SET etat = %(e)s, debit_heure = %(d)s, plafond_jour = %(p)s,
                            capacite_apprise_heure = GREATEST(capacite_apprise_heure, %(a)s), jour_chauffe = %(j)s,
                            derniere_hausse = CASE WHEN %(h)s THEN %(auj)s ELSE derniere_hausse END,
                            dernier_reduit = CASE WHEN %(r)s THEN now() ELSE dernier_reduit END,
                            pause_jusqu_a = CASE WHEN %(s)s THEN now() + interval '6 hours' ELSE pause_jusqu_a END,
                            metriques = %(m)s::jsonb, maj = now() WHERE cle = %(c)s""",
                  {"e": d["etat"], "d": round(d["debit"], 2), "p": plafond, "a": apprise, "j": jours,
                   "h": d["decision"] == "augmenter", "r": d["decision"] == "reduire", "s": d["decision"] == "suspendre", "auj": aujourd_hui, "m": json.dumps({"1h": m1, "24h": m24}), "c": cle})
        # On ne journalise que les CHANGEMENTS (et la 1re évaluation du jour), pas chaque tour.
        dernier = pg.ligne("SELECT decision, etat, at FROM capacite_decisions WHERE cle = %(c)s ORDER BY at DESC LIMIT 1", {"c": cle})
        if (not dernier or d["decision"] != "maintenir" or dernier["etat"] != d["etat"]
                or dernier["at"].astimezone(PARIS).date() != aujourd_hui):
            _journal(cle, d["decision"], d["etat"], ancien, d["debit"], d["motif"], d["confiance"], {"1h": m1, "24h": m24}, f, plafond)
    return len(files)


def _journal(cle, decision, etat, ancien, nouveau, motif, confiance, metriques, f, plafond) -> None:
    m24 = (metriques or {}).get("24h") or {}
    texte = (f"File : IP {f['sending_ip']} | identité {f['identite']} | {f['flux']} | {NOMS.get(f['groupe'], f['groupe'])}\n"
             f"Fenêtre : 24 h — tentés {m24.get('tentes', 0)}, acceptés {m24.get('acceptes', 0)}, "
             f"différés {m24.get('differes', 0)}, rebonds durs {m24.get('rebonds', 0)}, plaintes {m24.get('plaintes', 0)}\n"
             f"Décision : {decision} — débit {'' if ancien is None else f'{ancien:.0f}/h → '}{nouveau:.0f}/h ; plafond de chauffe {plafond}/jour\n"
             f"Motif : {motif}\nConfiance : {confiance} — capacité APPRISE sur nos envois (hypothèse, pas un quota publié)")
    pg.ecrire("""INSERT INTO capacite_decisions (cle, decision, etat, ancien, nouveau, motif, confiance, hypothese, metriques, texte)
                 VALUES (%(c)s, %(d)s, %(e)s, %(a)s, %(n)s, %(m)s, %(co)s, true, %(me)s::jsonb, %(t)s)""",
              {"c": cle, "d": decision, "e": etat, "a": ancien, "n": round(nouveau, 2), "m": motif, "co": confiance,
               "me": json.dumps(metriques or {}), "t": texte})


def max_aujourdhui(f: dict) -> int:
    """Débit autorisé = min(courbe de chauffe, débit × heures de la fenêtre) ; 0 si en pause."""
    if f["etat"] == "paused" and f.get("pause_jusqu_a") and f["pause_jusqu_a"] > datetime.now(timezone.utc):
        return 0
    return int(min(f["plafond_jour"], float(f["debit_heure"]) * HEURES_FENETRE))


def tableau() -> dict:
    """Onglet « Capacité » : par IP d'envoi (et domaine d'identité), le total ; par messagerie, le détail."""
    files = pg.lignes("SELECT * FROM capacite_files ORDER BY sending_ip, identite, groupe")
    envoyes_auj = {(x["sending_ip"], x["identite"], x["flux"], x["groupe"]): x["n"] for x in pg.lignes(
        """SELECT sending_ip, identite, flux, groupe, count(*) n FROM smtp_reponses
            WHERE (at AT TIME ZONE 'Europe/Paris')::date = (now() AT TIME ZONE 'Europe/Paris')::date GROUP BY 1, 2, 3, 4""")}
    ips: dict[str, dict] = {}
    for f in files:
        dern = pg.ligne("SELECT decision, motif, confiance, at, texte FROM capacite_decisions WHERE cle = %(c)s ORDER BY at DESC LIMIT 1",
                        {"c": f["cle"]})
        mx = max_aujourdhui(f)
        deja = envoyes_auj.get((f["sending_ip"], f["identite"], f["flux"], f["groupe"]), 0)
        ligne = {"cle": f["cle"], "groupe": f["groupe"], "nom": NOMS.get(f["groupe"], f["groupe"]), "flux": f["flux"],
                 "etat": f["etat"], "jour_chauffe": f["jour_chauffe"], "debit_heure": round(float(f["debit_heure"])),
                 "plafond_jour": f["plafond_jour"], "max_aujourdhui": mx, "deja_aujourdhui": deja,
                 "restant_aujourdhui": max(0, mx - deja), "capacite_apprise_heure": f["capacite_apprise_heure"],
                 "metriques": f["metriques"], "derniere_decision": dern, "maj": f["maj"]}
        k = f"{f['sending_ip']}|{f['identite']}"
        ip = ips.setdefault(k, {"sending_ip": f["sending_ip"], "identite": f["identite"], "files": [],
                                "max_aujourdhui": 0, "max_heure": 0, "deja_aujourdhui": 0})
        ip["files"].append(ligne)
        ip["max_aujourdhui"] += mx
        ip["max_heure"] += 0 if mx == 0 else round(float(f["debit_heure"]))
        ip["deja_aujourdhui"] += deja
    return {"fenetre": f"{FENETRE_ENVOI[0]}h-{FENETRE_ENVOI[1]}h", "ips": list(ips.values()),
            "avertissement": "Capacités APPRISES sur nos propres envois (aucun fournisseur ne publie de quota par IP)."}


def corriger_suppressions() -> int:
    """Source § 6.2 : on ne supprime JAMAIS une adresse sur une réponse temporaire (4xx). Sweego
    étiquette parfois « hard_bounce » un 451 (ex. Microsoft S3115, limite de connexions, 26/09) :
    la suppression automatique posée par la synchro des logs est retirée."""
    return pg.ecrire("""DELETE FROM suppressions s
                         WHERE s.reason = 'hard_bounce' AND s.source = 'sweego'
                           AND EXISTS (SELECT 1 FROM smtp_reponses r WHERE r.email_hash = s.email_hash
                                         AND r.etat = 'hard_bounce' AND r.categorie LIKE 'transient%%')
                           AND NOT EXISTS (SELECT 1 FROM smtp_reponses r WHERE r.email_hash = s.email_hash
                                             AND r.categorie LIKE 'permanent%%')""") or 0


def tourner() -> dict:
    ing = ingerer()
    return {"ingeres": ing, "suppressions_corrigees": corriger_suppressions(), "files": evaluer()}
