#!/usr/bin/env python3
"""mass_mailing/jobs/engagement.py — ouverts et cliqueurs d'une campagne, classés humain / robot / ?.

Demande de Camille (15/10/2026) : une seule page « ouverts + cliqueurs », un filtre, un export
de l'un ou de l'autre, et pour chaque ouverture ou clic un verdict : humain, robot, ou « ? »
quand c'est impossible à déterminer.

Pourquoi : sur la campagne Zylio, la grande majorité des ouvertures sont des scanners de
sécurité (Microsoft 365 / Defender, Google Workspace, passerelles d'entreprise) qui ouvrent
l'email 5 à 60 s après l'envoi, depuis un centre de données, avec un navigateur figé
(Chrome 109 / Chrome 42). Les compter comme des ouvertures fausse le taux d'ouverture et
l'A/B test.

Sources :
- Resend : chaque `email.opened` / `email.clicked` porte IP, navigateur et horodatage
  (webhook_events.raw_payload) ; le délai se mesure depuis `data.created_at` (l'envoi).
- Sweego (espace interne) : chaque `email_opened` porte aussi IP, navigateur et horodatage
  (raw_payload.open, 16/10/2026 : « ce n'est pas le même routeur mais j'ai besoin des mêmes
  retours ») ; le délai se mesure depuis `recipients.submitted_at`. Les clics Sweego sont déjà
  classés dans `clicks` (jobs/clics.py, « suspect » devient « ? »). Une ouverture antérieure au
  webhook (sans événement) reste « ? ».

Règles d'une ouverture, dans l'ordre (la première qui tranche gagne) :
 1. navigateur de robot (headless, bot, crawler, curl…)                         → robot
 2. proxy d'affichage d'une messagerie (Gmail, Front) : chargé quand on lit     → humain
 3. navigateur réduit à « Mozilla/5.0 » : Apple Mail Protection de la vie privée,
    qui précharge les images sans que la personne lise forcément                  → ?
 3b. IP du proxy d'images Gmail (66.249.80.0/20) : préchargement ou lecture      → ?
 4. IP d'un centre de données connu (Microsoft, Google, Amazon)                  → robot
 5. moins de 60 s après l'envoi                                                  → robot
 6. ouvertures du même destinataire depuis 3 IP ou plus en moins d'une heure    → robot
 7. client mail identifié (Outlook, Office, Apple Mail macOS, Thunderbird, mobile) → humain
 8. navigateur moderne, IP de fournisseur d'accès, plus d'une minute après       → humain
 9. le reste                                                                     → ?
Un destinataire est « humain » si au moins une de ses ouvertures l'est, sinon « ? » si une
l'est, sinon « robot ».
"""
from __future__ import annotations

import csv
import io
import ipaddress
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import pg  # noqa: E402

HUMAIN, ROBOT, INCONNU = "humain", "robot", "?"
DELAI_SCANNER_S = 60

# Plages des grands hébergeurs : une ouverture qui en vient n'est pas un lecteur derrière son écran.
CENTRES_DE_DONNEES = {
    "Microsoft (Microsoft 365 / Azure)": ["4.128.0.0/9", "13.64.0.0/11", "20.0.0.0/8", "40.64.0.0/10",
                                           "48.192.0.0/10", "52.96.0.0/12", "72.144.0.0/14", "74.224.0.0/11",
                                           "104.40.0.0/13", "137.116.0.0/15", "168.61.0.0/16", "191.232.0.0/13"],
    "Google": ["74.125.0.0/16", "66.249.64.0/19", "64.233.160.0/19", "209.85.128.0/17", "108.177.0.0/17",
               "34.0.0.0/9", "35.184.0.0/13", "2600:1900::/28", "2001:4860::/32"],
    "Amazon (AWS)": ["3.0.0.0/9", "13.208.0.0/12", "16.0.0.0/8", "18.0.0.0/8", "34.192.0.0/10", "44.192.0.0/10",
                     "50.16.0.0/14", "52.0.0.0/11", "52.192.0.0/11", "54.0.0.0/8", "98.80.0.0/12",
                     "100.20.0.0/14", "107.20.0.0/14", "2600:1f00::/24"],
}
_RESEAUX = [(nom, ipaddress.ip_network(c)) for nom, liste in CENTRES_DE_DONNEES.items() for c in liste]

UA_ROBOT = re.compile(r"headless|bot\b|crawler|spider|python|curl|wget|go-http|java/|phantom|scanner|preview", re.I)
UA_PROXY_LECTURE = {"googleimageproxy": "Gmail (image chargée à l'affichage)",
                    "frontapp.com imageproxy": "Front (image chargée à l'affichage)"}
UA_CLIENT_MAIL = [("microsoft outlook", "Outlook"), ("ms-office", "Outlook (Office)"), ("msoffice", "Outlook (Office)"),
                  ("trident/7.0", "Outlook (moteur Windows)"), ("thunderbird", "Thunderbird"),
                  ("iphone", "iPhone"), ("ipad", "iPad"), ("android", "Android")]


PROXY_GMAIL = ipaddress.ip_network("66.249.80.0/20")


def _proxy_gmail(ip: str | None) -> bool:
    try:
        a = ipaddress.ip_address(ip or "")
    except ValueError:
        return False
    return a.version == 4 and a in PROXY_GMAIL


def centre_de_donnees(ip: str | None) -> str | None:
    try:
        a = ipaddress.ip_address(ip or "")
    except ValueError:
        return None
    return next((nom for nom, n in _RESEAUX if a.version == n.version and a in n), None)


def _quand(x: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(str(x).replace("Z", "+00:00")) if x else None
    except ValueError:
        return None


def classer_evenement(ua: str | None, ip: str | None, delai_s: float | None, nb_ip_heure: int = 1) -> tuple[str, str]:
    """Fonction pure : (verdict, raison) d'une ouverture ou d'un clic."""
    u = (ua or "").strip()
    ul = u.lower()
    if not u:
        return INCONNU, "navigateur absent"
    if UA_ROBOT.search(u):
        return ROBOT, "navigateur de robot (" + UA_ROBOT.search(u).group(0) + ")"
    for cle, nom in UA_PROXY_LECTURE.items():
        if cle in ul:
            return HUMAIN, nom
    if u == "Mozilla/5.0":
        return INCONNU, "Apple Mail (protection de la vie privée) : préchargement automatique possible"
    if _proxy_gmail(ip):
        # 16/10/2026 (PIRAINO) : 481 des 553 adresses Gmail « ouvertes » 5 à 60 min après l'envoi par
        # le proxy d'images Google — préchargement, et une vraie lecture passe par le même proxy.
        return INCONNU, "Gmail : images chargées par le proxy Google (préchargement ou lecture, indiscernables)"
    dc = centre_de_donnees(ip)
    if dc:
        return ROBOT, f"IP de centre de données : {dc} (scanner de sécurité)"
    if delai_s is not None and delai_s < DELAI_SCANNER_S:
        return ROBOT, f"{int(delai_s)} s après l'envoi (scanner de sécurité)"
    if nb_ip_heure >= 3:
        return ROBOT, f"{nb_ip_heure} IP différentes en moins d'une heure (passerelle de sécurité)"
    for cle, nom in UA_CLIENT_MAIL:
        if cle in ul:
            return HUMAIN, f"client mail : {nom}"
    if "macintosh" in ul and "safari" not in ul and "chrome" not in ul:
        return HUMAIN, "client mail : Apple Mail (Mac)"
    m = re.search(r"(chrome|firefox|safari|edg)/(\d+)", ul)
    if m and delai_s is not None:
        return HUMAIN, f"navigateur ({m.group(1).capitalize()}), connexion de particulier ou d'entreprise"
    return INCONNU, "impossible à déterminer"


def _evenements(campaign_id: str, typ: str) -> list[dict]:
    """Événements Resend (et ouvertures Sweego) d'une campagne, du plus ancien au plus récent."""
    cle = "open" if typ == "email.opened" else "click"
    evts = pg.lignes(f"""
        SELECT r.id AS recipient_id, r.email_normalized AS email, r.variante,
               w.raw_payload->'data'->>'created_at' AS envoye,
               w.raw_payload->'data'->'{cle}'->>'timestamp' AS quand,
               w.raw_payload->'data'->'{cle}'->>'ipAddress' AS ip,
               w.raw_payload->'data'->'{cle}'->>'userAgent' AS ua,
               w.raw_payload->'data'->'{cle}'->>'link' AS lien
          FROM webhook_events w
          JOIN recipients r ON r.campaign_id = %(c)s
                           AND r.provider_message_id = w.raw_payload->'data'->>'email_id'
         WHERE w.provider = 'resend' AND w.event_type = %(t)s
           AND w.raw_payload->'data'->'tags'->>'campaign' = %(tag)s""", {"c": campaign_id, "t": typ, "tag": f"mm-{campaign_id}"})
    if typ == "email.opened":
        # Sweego : mêmes champs, autre forme (les clics Sweego viennent de la table `clicks`).
        evts += pg.lignes("""
            SELECT r.id AS recipient_id, r.email_normalized AS email, r.variante,
                   to_json(r.submitted_at)#>>'{}' AS envoye,
                   w.raw_payload->>'timestamp' AS quand,
                   w.raw_payload->'open'->>'ip_address' AS ip,
                   w.raw_payload->'open'->>'user_agent' AS ua,
                   NULL AS lien
              FROM webhook_events w
              JOIN recipients r ON r.campaign_id = %(c)s AND r.sweego_message_id = w.raw_payload->>'swg_uid'
             WHERE w.provider = 'sweego' AND w.event_type = 'email_opened' AND w.campaign_id = %(c)s""",
                          {"c": campaign_id})
    return sorted(evts, key=lambda e: _quand(e["quand"]) or datetime.max.replace(tzinfo=timezone.utc))


def _classer_liste(evts: list[dict]) -> list[dict]:
    par_dest: dict = {}
    for e in evts:
        e["quand"], envoye = _quand(e["quand"]), _quand(e["envoye"])
        e["delai_s"] = (e["quand"] - envoye).total_seconds() if e["quand"] and envoye else None
        par_dest.setdefault(e["recipient_id"], []).append(e)
    for liste in par_dest.values():
        for e in liste:
            proches = {x["ip"] for x in liste if x["quand"] and e["quand"] and abs((x["quand"] - e["quand"]).total_seconds()) <= 3600}
            e["verdict"], e["raison"] = classer_evenement(e["ua"], e["ip"], e["delai_s"], len(proches))
    return evts


def _source(raison: str) -> str:
    """Raison d'un robot → libellé court de la source (pour la vue par domaine)."""
    if "centre de données : " in raison:
        return raison.split("centre de données : ")[1].replace(" (scanner de sécurité)", "")
    if "après l'envoi" in raison:
        return "ouverture immédiate (scanner)"
    if "IP différentes" in raison:
        return "passerelle de sécurité (plusieurs IP)"
    return raison


def _verdict_global(verdicts: list[str]) -> str:
    return HUMAIN if HUMAIN in verdicts else (INCONNU if INCONNU in verdicts else ROBOT)


def ouvertures_humaines(campaign_id: str) -> dict[int, str]:
    """recipient_id → verdict des destinataires ayant ouvert (pour l'A/B test)."""
    par: dict = {}
    for e in _classer_liste(_evenements(campaign_id, "email.opened")):
        par.setdefault(e["recipient_id"], []).append(e["verdict"])
    return {r: _verdict_global(v) for r, v in par.items()}


def engagement(campaign_id: str) -> dict:
    """Une ligne par destinataire ayant ouvert ou cliqué, plus la vue par domaine."""
    lignes: dict = {}

    def ligne(rid, email, variante):
        return lignes.setdefault(rid, {"email": email, "domaine": email.split("@")[-1], "variante": variante,
                                       "ouverture": None, "clic": None})

    ouv = _classer_liste(_evenements(campaign_id, "email.opened"))
    par: dict = {}
    for e in ouv:
        par.setdefault(e["recipient_id"], []).append(e)
    for rid, liste in par.items():
        v = _verdict_global([e["verdict"] for e in liste])
        decisif = next(e for e in liste if e["verdict"] == v)
        ligne(rid, liste[0]["email"], liste[0]["variante"])["ouverture"] = {
            "verdict": v, "raison": decisif["raison"], "premiere": liste[0]["quand"],
            "premiere_humaine": next((e["quand"] for e in liste if e["verdict"] == HUMAIN), None),
            "n": len(liste), "n_robot": sum(e["verdict"] == ROBOT for e in liste),
            "detail": [{"quand": e["quand"], "delai_s": e["delai_s"], "ip": e["ip"], "ua": e["ua"],
                        "verdict": e["verdict"], "raison": e["raison"]} for e in liste]}
    # Destinataires ouverts sans événement détaillé (Sweego, ou webhook antérieur) : « ? ».
    for r in pg.lignes("""SELECT id, email_normalized AS email, variante, opened_at FROM recipients
                           WHERE campaign_id = %(c)s AND opened_at IS NOT NULL""", {"c": campaign_id}):
        if r["id"] not in par:
            ligne(r["id"], r["email"], r["variante"])["ouverture"] = {
                "verdict": INCONNU, "raison": "ouverture sans détail (IP et navigateur non transmis)",
                "premiere": r["opened_at"], "premiere_humaine": None, "n": 1, "n_robot": 0, "detail": []}

    # Clics : Resend (classés ici) + Sweego (déjà classés par jobs/clics.py).
    clics: dict = {}
    for e in _classer_liste(_evenements(campaign_id, "email.clicked")):
        clics.setdefault(e["recipient_id"], {"email": e["email"], "variante": e["variante"], "evts": []})["evts"].append(
            {"quand": e["quand"], "verdict": e["verdict"], "raison": e["raison"], "lien": e["lien"]})
    for k in pg.lignes("""SELECT k.recipient_id, r.email_normalized AS email, r.variante, k.clicked_at, k.verdict,
                                 k.raisons, k.url FROM clicks k JOIN recipients r ON r.id = k.recipient_id
                           WHERE k.campaign_id = %(c)s AND k.type_lien IN ('contenu', 'miroir')
                           ORDER BY k.clicked_at""", {"c": campaign_id}):
        clics.setdefault(k["recipient_id"], {"email": k["email"], "variante": k["variante"], "evts": []})["evts"].append(
            {"quand": k["clicked_at"], "verdict": INCONNU if k["verdict"] == "suspect" else k["verdict"],
             "raison": ", ".join(k["raisons"] or []) or ("clic sans ouverture enregistrée" if k["verdict"] == "suspect" else "aucun signe de robot"),
             "lien": k["url"]})
    for rid, c in clics.items():
        ev = c["evts"]
        v = _verdict_global([e["verdict"] for e in ev])
        ligne(rid, c["email"], c["variante"])["clic"] = {
            "verdict": v, "raison": next(e["raison"] for e in ev if e["verdict"] == v), "premier": ev[0]["quand"],
            "n": len(ev), "liens": " | ".join(sorted({e["lien"] for e in ev if e["lien"]}))}

    # Domaines : où les ouvertures sont-elles des robots ?
    dom: dict = {}
    for l in lignes.values():
        if not l["ouverture"]:
            continue
        d = dom.setdefault(l["domaine"], {"domaine": l["domaine"], "ouverts": 0, HUMAIN: 0, ROBOT: 0, INCONNU: 0, "sources": set()})
        d["ouverts"] += 1
        d[l["ouverture"]["verdict"]] += 1
        for x in l["ouverture"]["detail"]:
            if x["verdict"] == ROBOT:
                d["sources"].add(_source(x["raison"]))
    domaines = []
    for d in dom.values():
        d["sources"] = sorted(d["sources"])
        d["verdict"] = ROBOT if d[ROBOT] == d["ouverts"] else (HUMAIN if d[HUMAIN] else INCONNU)
        domaines.append(d)
    domaines.sort(key=lambda d: (-d[ROBOT], -d["ouverts"], d["domaine"]))

    out = sorted(lignes.values(), key=lambda l: str((l["ouverture"] or l["clic"] or {}).get("premiere") or
                                                    (l["clic"] or {}).get("premier") or ""), reverse=True)
    tot = {"ouverts": {k: sum(1 for l in out if l["ouverture"] and l["ouverture"]["verdict"] == k) for k in (HUMAIN, ROBOT, INCONNU)},
           "cliqueurs": {k: sum(1 for l in out if l["clic"] and l["clic"]["verdict"] == k) for k in (HUMAIN, ROBOT, INCONNU)}}
    return {"lignes": out, "domaines": domaines, "totaux": tot}


def csv_engagement(campaign_id: str, quoi: str = "ouverts", verdicts: list[str] | None = None) -> str:
    """Export « ouverts » ou « cliqueurs » ; verdicts = filtre (humain, robot, ?), tous par défaut."""
    cle = "clic" if quoi == "cliqueurs" else "ouverture"
    garde = set(verdicts or [HUMAIN, ROBOT, INCONNU])
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    if cle == "ouverture":
        w.writerow(["email", "domaine", "version", "verdict", "raison", "premiere_ouverture", "premiere_ouverture_humaine", "ouvertures", "dont_robots", "a_clique"])
    else:
        w.writerow(["email", "domaine", "version", "verdict", "raison", "premier_clic", "clics", "liens"])
    f = lambda x: x.isoformat() if hasattr(x, "isoformat") else ("" if x is None else x)  # noqa: E731
    for l in engagement(campaign_id)["lignes"]:
        x = l[cle]
        if not x or x["verdict"] not in garde:
            continue
        if cle == "ouverture":
            w.writerow([l["email"], l["domaine"], l["variante"] or "", x["verdict"], x["raison"], f(x["premiere"]),
                        f(x["premiere_humaine"]), x["n"], x["n_robot"], "oui" if l["clic"] else "non"])
        else:
            w.writerow([l["email"], l["domaine"], l["variante"] or "", x["verdict"], x["raison"], f(x["premier"]), x["n"], x["liens"]])
    return "﻿" + out.getvalue()
