#!/usr/bin/env python3
"""mass_mailing/jobs/clics.py — les clics : capture, filtre anti-robots, export.

Demande de Camille (2026-09-25) : « je ne veux pas donner à mes clients des informations
sur des clics de bots ». Les clics viennent du webhook Sweego (`email_clicked`), le seul
à fournir l'URL, l'IP et le navigateur. Chaque clic passe par des règles paramétrables
(`settings.click_rules`) et reçoit un verdict humain / robot / suspect, avec ses raisons.

Les pièges :
- LIEN PIÈGE : un lien invisible (1 px, transparent, hors navigation clavier) ajouté à
  chaque mail. Aucun humain ne peut le cliquer ; un scanner de sécurité qui « visite »
  tous les liens le suit. Tout clic du même destinataire autour de ce moment est robot.
- DÉLAI : un clic quelques secondes après l'envoi est un scanner (Safe Links, Mimecast…).
- RAFALE : plusieurs liens différents cliqués dans la même poignée de secondes.
- NAVIGATEUR : user-agent vide ou de robot connu ; IP listée comme robot.
- PROXY : le drapeau de Sweego (peu fiable seul : 0 clic sur 1 712 chez Cheffer).
- SANS OUVERTURE : clic sans ouverture préalable → « suspect » (réglable).

Dédoublonnage : un événement Sweego = un clic (`event_id` unique) ; l'export donne une
ligne par destinataire (premier clic humain, liens distincts, nombre de clics).
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import ipaddress
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import adresses, desinscription, pg  # noqa: E402


# ── Capture (appelée par le webhook Cheffer pour les campagnes « mm-… ») ────────

def enregistrer_webhook(data: dict) -> bool:
    """Range l'événement brut, dédoublonné par `event_id`. Ne lève jamais."""
    try:
        camp = str(data.get("campaign_id") or "")
        cid = camp[3:] if camp.startswith("mm-") else None
        try:
            import uuid
            uuid.UUID(cid or "")
        except ValueError:
            return False          # mm-preflight, mm-export : pas une campagne
        email = adresses.normaliser(data.get("recipient") or "")
        n = pg.ecrire("""
            INSERT INTO webhook_events (provider, event_type, email_hash, campaign_id, external_id,
                                        signature_valid, raw_payload)
            VALUES ('sweego', %(t)s, %(h)s, %(c)s::uuid, %(e)s, NULL, %(p)s::jsonb)
            ON CONFLICT DO NOTHING
        """, {"t": data.get("event_type"), "h": adresses.hacher(email) if email else None,
              "c": cid, "e": data.get("event_id") or data.get("swg_uid"),
              "p": json.dumps(data, ensure_ascii=False)})
        return n > 0
    except Exception:  # noqa: BLE001 — le webhook Cheffer ne doit jamais tomber pour nous
        return False


# ── Lien piège ───────────────────────────────────────────────────────────────

CHEMIN_PIEGE = "/api/public/mass-mailing/p"


def url_piege(recipient_id: int) -> str:
    return f"{desinscription.BASE_PUBLIQUE}{CHEMIN_PIEGE}?t={desinscription.jeton(recipient_id)}"


BADGE_TEXTE = "Email envoyé par la technologie Cheffer"


def ajouter_piege(html: str, recipient_id: int) -> str:
    """Badge VISIBLE en fin de message (Camille, 27/09/2026) : « ✉ Email envoyé par la
    technologie Cheffer ». Remplace l'ancien lien invisible de 1 px (contenu caché = mauvais pour
    la délivrabilité). Un humain ne clique presque jamais dessus ; un scanner qui suit tous les
    liens, si. Il mène à la page de préférences (/p : opt-down, pièges anti-robot)."""
    lien = (f'<div style="margin:18px 0 6px;text-align:center;font-family:Arial,sans-serif;font-size:11px;'
            f'line-height:1.4;color:#9a9aa3"><a href="{url_piege(recipient_id)}" '
            'style="color:#9a9aa3;text-decoration:none">&#9993;&nbsp;Email envoyé par la technologie '
            '<span style="text-decoration:underline">Cheffer</span></a></div>')
    i = html.lower().rfind("</body>")
    return html[:i] + lien + html[i:] if i >= 0 else html + lien


def texte_piege(recipient_id: int) -> str:
    return f"\n{BADGE_TEXTE} : {url_piege(recipient_id)}\n"


# ── Classification ───────────────────────────────────────────────────────────

def regles() -> dict:
    return pg.valeur("SELECT click_rules FROM settings") or {}


def _type_lien(url: str) -> str:
    u = url or ""
    if CHEMIN_PIEGE in u:
        return "piege"
    if desinscription.CHEMIN in u or "/unsubscribe" in u.lower():
        return "desinscription"
    if desinscription.CHEMIN_MIROIR in u:
        return "miroir"
    return "contenu"


def _ip_robot(ip: str, cidrs: list[str]) -> bool:
    try:
        a = ipaddress.ip_address(ip)
        return any(a in ipaddress.ip_network(c, strict=False) for c in cidrs)
    except ValueError:
        return False


def traiter(limite: int = 2000) -> int:
    """Transforme les événements de clic reçus en lignes `clicks`, puis reclasse les
    campagnes touchées. Idempotent : un event_id déjà traité est ignoré."""
    evts = pg.lignes("""SELECT id, campaign_id, raw_payload FROM webhook_events
                         WHERE provider = 'sweego' AND processed_at IS NULL
                         ORDER BY id LIMIT %(l)s""", {"l": limite})
    touchees = set()
    for e in evts:
        p = e["raw_payload"] or {}
        erreur = None
        try:
            if "click" in str(p.get("event_type", "")).lower() and e["campaign_id"]:
                clic = p.get("click") or {}
                swg = p.get("swg_uid")
                r = pg.ligne("""SELECT id, submitted_at FROM recipients
                                 WHERE campaign_id = %(c)s AND (sweego_message_id = %(u)s
                                       OR email_normalized = %(m)s) ORDER BY (sweego_message_id = %(u)s) DESC LIMIT 1""",
                             {"c": e["campaign_id"], "u": swg,
                              "m": adresses.normaliser(p.get("recipient") or "")})
                quand = datetime.fromisoformat(str(p.get("timestamp")).replace("Z", "+00:00")) \
                    if p.get("timestamp") else datetime.now(timezone.utc)
                if quand.tzinfo is None:
                    quand = quand.replace(tzinfo=timezone.utc)
                delai = int((quand - r["submitted_at"]).total_seconds()) if r and r["submitted_at"] else None
                pg.ecrire("""INSERT INTO clicks (event_id, campaign_id, recipient_id, swg_uid, url, type_lien,
                                                 ip, user_agent, proxy_sweego, clicked_at, secondes_depuis_envoi)
                             VALUES (%(ev)s, %(c)s, %(r)s, %(u)s, %(url)s, %(t)s, %(ip)s, %(ua)s, %(px)s, %(q)s, %(d)s)
                             ON CONFLICT (event_id) DO NOTHING""",
                          {"ev": p.get("event_id") or f"{swg}:{p.get('timestamp')}", "c": e["campaign_id"],
                           "r": r["id"] if r else None, "u": swg, "url": clic.get("url"),
                           "t": _type_lien(clic.get("url")), "ip": clic.get("ip_address"),
                           "ua": clic.get("user_agent"), "px": clic.get("proxy"), "q": quand, "d": delai})
                touchees.add(str(e["campaign_id"]))
            elif "unsub" in str(p.get("event_type", "")).lower() and e["campaign_id"]:
                touchees.add(str(e["campaign_id"]))
        except Exception as ex:  # noqa: BLE001
            erreur = str(ex)[:300]
        pg.ecrire("UPDATE webhook_events SET processed_at = now(), process_error = %(e)s WHERE id = %(i)s",
                  {"e": erreur, "i": e["id"]})
    for cid in touchees:
        classer(cid)
    return len(evts)


def classer(campaign_id: str) -> dict:
    """(Re)classe tous les clics d'une campagne selon les règles en vigueur."""
    R = regles()
    agents = [a.lower() for a in R.get("user_agents_robots", [])]
    clics = pg.lignes("""SELECT k.*, r.opened_at FROM clicks k LEFT JOIN recipients r ON r.id = k.recipient_id
                          WHERE k.campaign_id = %(c)s ORDER BY k.recipient_id, k.clicked_at""", {"c": campaign_id})
    par_dest: dict = {}
    for k in clics:
        par_dest.setdefault(k["recipient_id"], []).append(k)
    compte = {"humain": 0, "robot": 0, "suspect": 0}
    from jobs import score_clics
    bal = score_clics.balayages_campagne(campaign_id)   # balayage d'antispam multi-destinataires (27/09)
    for _, liste in par_dest.items():
        pieges = [k["clicked_at"] for k in liste if k["type_lien"] == "piege"]
        for k in liste:
            raisons, verdict = [], "humain"
            if k["type_lien"] == "piege" and len({x["url"] for x in liste}) >= 3:
                raisons.append("badge Cheffer suivi avec d'autres liens")
            fen_p = R.get("piege_fenetre_s", 120)
            if any(abs((k["clicked_at"] - p).total_seconds()) <= fen_p for p in pieges) and k["type_lien"] != "piege":
                # Badge VISIBLE depuis le 27/09 : il faut au moins 2 AUTRES liens dans la même
                # fenêtre pour classer la visite en robot (un humain curieux ne clique que lui).
                autres = {x["url"] for x in liste if x["type_lien"] != "piege"
                          and any(abs((x["clicked_at"] - p).total_seconds()) <= fen_p for p in pieges)}
                if len(autres) >= 2:
                    raisons.append("même visite que le lien piège")
            if R.get("proxy_sweego", True) and k["proxy_sweego"]:
                raisons.append("marqué proxy par Sweego")
            if k["secondes_depuis_envoi"] is not None and k["secondes_depuis_envoi"] < R.get("delai_min_s", 15):
                raisons.append(f"clic {k['secondes_depuis_envoi']} s après l'envoi (scanner)")
            fen = R.get("rafale_fenetre_s", 10)
            voisins = {x["url"] for x in liste if x["type_lien"] == "contenu"
                       and abs((x["clicked_at"] - k["clicked_at"]).total_seconds()) <= fen}
            if len(voisins) >= R.get("rafale_liens", 3):
                raisons.append(f"{len(voisins)} liens cliqués en {fen} s (rafale)")
            if k["id"] in bal:
                raisons.append("balayage antispam : plusieurs destinataires de la même messagerie en quelques secondes")
            ua = (k["user_agent"] or "").lower()
            if not ua and R.get("user_agent_vide", True):
                raisons.append("navigateur absent")
            elif any(a in ua for a in agents):
                raisons.append("navigateur de robot : " + next(a for a in agents if a in ua))
            if k["ip"] and _ip_robot(k["ip"], R.get("ips_robots", [])):
                raisons.append("IP listée comme robot")
            if raisons:
                verdict = "robot"
            elif not k["opened_at"] and R.get("sans_ouverture", "suspect") == "suspect":
                verdict, raisons = "suspect", ["clic sans ouverture enregistrée"]
            compte[verdict] += 1
            pg.ecrire("UPDATE clicks SET verdict = %(v)s, raisons = %(r)s WHERE id = %(i)s",
                      {"v": verdict, "r": raisons, "i": k["id"]})
    # Le « clic » d'un destinataire = son premier clic HUMAIN sur un lien de contenu.
    pg.ecrire("""
        UPDATE recipients r SET clicked_at = x.premier, updated_at = now()
          FROM (SELECT recipient_id, min(clicked_at) AS premier FROM clicks
                 WHERE campaign_id = %(c)s AND verdict = 'humain' AND type_lien IN ('contenu','miroir')
                 GROUP BY recipient_id) x
         WHERE r.id = x.recipient_id
    """, {"c": campaign_id})
    pg.ecrire("""
        UPDATE recipients r SET clicked_at = NULL, updated_at = now()
         WHERE r.campaign_id = %(c)s AND r.clicked_at IS NOT NULL
           AND EXISTS (SELECT 1 FROM clicks k WHERE k.recipient_id = r.id)
           AND NOT EXISTS (SELECT 1 FROM clicks k WHERE k.recipient_id = r.id AND k.verdict = 'humain'
                             AND k.type_lien IN ('contenu','miroir'))
    """, {"c": campaign_id})
    return compte


# ── Lecture et export ────────────────────────────────────────────────────────

def synthese(campaign_id: str) -> dict:
    tot = pg.lignes("""SELECT verdict, type_lien, count(*) n, count(DISTINCT recipient_id) d
                         FROM clicks WHERE campaign_id = %(c)s GROUP BY 1, 2""", {"c": campaign_id})
    raisons = pg.lignes("""SELECT unnest(raisons) AS raison, count(*) n FROM clicks
                            WHERE campaign_id = %(c)s GROUP BY 1 ORDER BY 2 DESC""", {"c": campaign_id})
    return {"totaux": tot, "raisons": raisons, "regles": regles()}


def lignes_export(campaign_id: str, inclure_robots: bool = False) -> list[dict]:
    """Une ligne par destinataire ayant cliqué (dédoublonné)."""
    filtre = "" if inclure_robots else "AND k.verdict = 'humain'"
    return pg.lignes(f"""
        SELECT r.email_normalized AS email,
               min(k.clicked_at) FILTER (WHERE k.verdict = 'humain') AS premier_clic_humain,
               max(k.clicked_at) AS dernier_clic,
               count(*) FILTER (WHERE k.verdict = 'humain') AS clics_humains,
               count(*) FILTER (WHERE k.verdict <> 'humain') AS clics_ecartes,
               string_agg(DISTINCT k.url, ' | ') FILTER (WHERE k.type_lien = 'contenu') AS liens,
               (array_agg(k.ip ORDER BY k.clicked_at))[1] AS ip,
               (array_agg(k.user_agent ORDER BY k.clicked_at))[1] AS navigateur,
               string_agg(DISTINCT array_to_string(k.raisons, ', '), ' | ') FILTER (WHERE k.verdict <> 'humain') AS raisons_ecart,
               bool_or(k.verdict = 'humain') AS humain
          FROM clicks k JOIN recipients r ON r.id = k.recipient_id
         WHERE k.campaign_id = %(c)s AND k.type_lien IN ('contenu','miroir') {filtre}
         GROUP BY r.email_normalized ORDER BY premier_clic_humain NULLS LAST
    """, {"c": campaign_id})


def csv_clics(campaign_id: str, inclure_robots: bool = False) -> str:
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    cols = ["email", "premier_clic_humain", "dernier_clic", "clics_humains", "liens", "ip", "navigateur"]
    if inclure_robots:
        cols += ["clics_ecartes", "raisons_ecart"]
    w.writerow(cols)
    for l in lignes_export(campaign_id, inclure_robots):
        w.writerow([l[c].isoformat() if hasattr(l[c], "isoformat") else ("" if l[c] is None else l[c]) for c in cols])
    return "﻿" + out.getvalue()   # BOM : Excel ouvre les accents correctement


# ── Lien de téléchargement signé (envoi par email) ───────────────────────────

def jeton_export(campaign_id: str, inclure_robots: bool, jours: int = 7) -> str:
    exp = int((datetime.now(timezone.utc) + timedelta(days=jours)).timestamp())
    base = f"{campaign_id}.{int(inclure_robots)}.{exp}"
    sig = hmac.new(desinscription._secret(), f"mm-export:{base}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{base}.{sig}"


def lire_jeton_export(t: str) -> tuple[str, bool] | None:
    try:
        cid, rob, exp, sig = t.split(".")
    except ValueError:
        return None
    base = f"{cid}.{rob}.{exp}"
    ok = hmac.compare_digest(sig, hmac.new(desinscription._secret(), f"mm-export:{base}".encode(),
                                           hashlib.sha256).hexdigest()[:32])
    if not ok or int(exp) < datetime.now(timezone.utc).timestamp():
        return None
    return cid, rob == "1"
