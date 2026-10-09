#!/usr/bin/env python3
"""mass_mailing/jobs/score_clics.py — score anti-robot PAR DESTINATAIRE, en calcul parallèle.

Recommandation de l'agent de recherche (26/09/2026,
.claude/skills/anti-bot-clics/references/recommandation.md § 6), validée par Camille le 27/09 :
« un score expliqué et versionné par destinataire », fondé sur des signaux sans liste
(rafale, paire désinscription + autre lien, réseaux distincts), où seul un POST sur la page de
rappel confirme un humain.

DOUBLE CALCUL : ce module n'écrit QUE dans `click_scores`. Le verdict actuel (`clicks.verdict`,
`recipients.clicked_at`, exports clients) n'est pas touché ; on compare pendant un mois avant de
basculer.

Deux horloges : l'heure des clics Sweego est décalée (+600 s constatés le 26/09 sur un envoi) par
rapport à notre serveur. Les fenêtres se calculent donc DANS chaque source (clics Sweego entre eux,
visites de la page de rappel entre elles) ; seule la règle « trop tôt après l'envoi » utilise
l'heure du serveur (visites de rappel vs `submitted_at`).

    scorer(evenements, soumis_a, regles, ips_multi)   fonction PURE (testée)
    calculer(campaign_id)                             relit la base, écrit click_scores
    recalculer_recents()                              appelée par le worker
    comparaison(campaign_id)                          ancien verdict vs nouveau statut
"""
from __future__ import annotations

import ipaddress
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import pg  # noqa: E402

VERSION = "2026-09-v1"

# Réglages par défaut (recommandation § 6). Surchargeables par settings.click_rules["score_v1"].
DEFAUT = {
    "seuils": {"security_scan": -60, "bot_suspected": -25, "human_likely": 15, "human_confirmed": 40},
    "ua_robot_poids": -80, "user_agent_vide_poids": -60,
    "user_agents_robots": ["curl/", "wget/", "python-requests", "python-urllib", "aiohttp", "go-http-client",
                           "java/", "okhttp", "axios/", "node-fetch", "undici", "apache-httpclient",
                           "headlesschrome", "phantomjs", "puppeteer", "playwright", "msie 8.0", "trident/4.0",
                           "googleimageproxy", "yahoomailproxy", "bot", "crawler", "spider", "scanner",
                           "safelinks", "mimecast", "barracuda", "proofpoint", "urldefense"],
    "rafale_liens": 3, "rafale_fenetre_s": 10, "rafale_poids": -60,
    "rafale_forte_liens": 5, "rafale_forte_poids": -80,
    "paire_desinscription_s": 60, "paire_desinscription_poids": -50,
    "reseaux_distincts": 3, "reseaux_fenetre_s": 120, "reseaux_prefixe_v4": 24, "reseaux_prefixe_v6": 48,
    "reseaux_poids": -60,
    "proxy_sweego_poids": -40,
    "delai_rapide_s": 60, "delai_poids": -20,
    "ip_multi_destinataires": 10, "ip_multi_fenetre_s": 600, "ip_multi_poids": -30,
    "ips_robots_poids": -30, "piege_poids": -20, "robot_perdu_poids": -60,
    "isole_bonus": 15, "post_rappel_bonus": 60,
    # Balayage d'un antispam (27/09, La Poste via OVH) : ≥ N destinataires DIFFÉRENTS d'une même
    # messagerie cliquent en moins de X s, dans l'heure qui suit leur envoi.
    "balayage_destinataires": 3, "balayage_fenetre_s": 30, "balayage_delai_max_s": 3600, "balayage_poids": -70,
}

STATUTS = ("security_scan", "bot_suspected", "unknown", "human_likely", "human_confirmed")


def regles() -> dict:
    R = dict(DEFAUT)
    try:
        R.update((pg.valeur("SELECT click_rules FROM settings") or {}).get("score_v1") or {})
    except Exception:  # noqa: BLE001
        pass
    return R


# ── Fonctions pures ─────────────────────────────────────────────────────────

def ua_robot(ua: str, motifs: list[str]) -> str | None:
    """Motif de robot trouvé dans le navigateur. Les motifs faits d'une seule « lettre-mot »
    (bot, spider…) se comparent en MOT ENTIER (pas « Cubot », pas « Abbott »)."""
    u = (ua or "").lower()
    for m in motifs:
        m = m.lower()
        if re.fullmatch(r"[a-z]+", m):
            if re.search(rf"(?<![a-z]){re.escape(m)}(?![a-z])", u):
                return m
        elif m in u:
            return m
    return None


def reseau(ip: str, v4: int = 24, v6: int = 48) -> str | None:
    try:
        a = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return None
    return str(ipaddress.ip_network(f"{a}/{v4 if a.version == 4 else v6}", strict=False))


def _max_dans_fenetre(evts: list[dict], fenetre: float, cle) -> int:
    """Plus grand nombre de valeurs DISTINCTES (`cle(e)`) dans une fenêtre glissante."""
    evts = sorted(evts, key=lambda e: e["at"])
    best = 0
    for i, e in enumerate(evts):
        vals = {cle(x) for x in evts[i:] if (x["at"] - e["at"]).total_seconds() <= fenetre}
        best = max(best, len(vals))
    return best


def statut_de(score: int, seuils: dict) -> str:
    if score <= seuils["security_scan"]:
        return "security_scan"
    if score <= seuils["bot_suspected"]:
        return "bot_suspected"
    if score >= seuils["human_confirmed"]:
        return "human_confirmed"
    if score >= seuils["human_likely"]:
        return "human_likely"
    return "unknown"


def scorer(evenements: list[dict], soumis_a: datetime | None, R: dict,
           ips_multi: set[str] | None = None, ips_robots: list[str] | None = None,
           balayage: bool = False) -> dict:
    """Score d'UN destinataire.

    evenements : [{"source": "S"|"R", "at": datetime, "url": str, "type": "contenu"|"desinscription"|
                   "miroir"|"piege"|"visite"|"accepte"|"refuse", "ip": str, "ua": str, "proxy": bool}]
      S = clic Sweego (horloge Sweego), R = page de rappel (horloge serveur).
    Chaque règle compte UNE fois par destinataire (poids non cumulés d'une source à l'autre).
    """
    raisons: list[str] = []
    poids: dict[str, int] = {}

    def applique(cle: str, p: int, texte: str):
        if cle not in poids or p < poids[cle]:
            if cle not in poids:
                raisons.append(texte)
            poids[cle] = p

    S = [e for e in evenements if e["source"] == "S"]
    Rv = [e for e in evenements if e["source"] == "R"]

    # V1-1 navigateur
    for e in evenements:
        ua = (e.get("ua") or "").strip()
        if len(ua) < 10:
            applique("ua", R["user_agent_vide_poids"], "navigateur absent ou tronqué")
        else:
            m = ua_robot(ua, R["user_agents_robots"])
            if m:
                applique("ua", R["ua_robot_poids"], f"navigateur de robot : « {m} »")

    # V1-2 rafale (tous types de liens), par source
    fen = R["rafale_fenetre_s"]
    n_s = _max_dans_fenetre(S, fen, lambda x: x.get("url") or x.get("type")) if S else 0
    n_r = _max_dans_fenetre(Rv, fen, lambda x: (x["at"], x.get("url"))) if Rv else 0  # requêtes
    n = max(n_s, n_r)
    if n >= R["rafale_forte_liens"]:
        applique("rafale", R["rafale_forte_poids"], f"{n} liens en {fen} s (rafale)")
    elif n >= R["rafale_liens"]:
        applique("rafale", R["rafale_poids"], f"{n} liens en {fen} s (rafale)")

    # V1-3 paire désinscription + autre lien (clics Sweego)
    desins = [e for e in S if e.get("type") == "desinscription"]
    autres = [e for e in S if e.get("type") not in ("desinscription",)]
    for d in desins:
        if any(abs((a["at"] - d["at"]).total_seconds()) <= R["paire_desinscription_s"] for a in autres):
            applique("paire", R["paire_desinscription_poids"],
                     f"désinscription + autre lien en moins de {R['paire_desinscription_s']} s")
            break

    # V1-4 réseaux distincts, par source
    def nb_reseaux(evts):
        pts = [e for e in evts if reseau(e.get("ip"), R["reseaux_prefixe_v4"], R["reseaux_prefixe_v6"])]
        return _max_dans_fenetre(pts, R["reseaux_fenetre_s"],
                                 lambda x: reseau(x.get("ip"), R["reseaux_prefixe_v4"], R["reseaux_prefixe_v6"])) if pts else 0
    nr = max(nb_reseaux(S), nb_reseaux(Rv))
    if nr >= R["reseaux_distincts"]:
        applique("reseaux", R["reseaux_poids"], f"{nr} réseaux différents en {R['reseaux_fenetre_s']} s")

    # V1-5 drapeau proxy de Sweego
    if any(e.get("proxy") for e in S):
        applique("proxy", R["proxy_sweego_poids"], "marqué proxy par Sweego")

    # V1-6 trop tôt après l'envoi — HEURE SERVEUR uniquement (page de rappel)
    if soumis_a and Rv:
        d = (min(e["at"] for e in Rv) - soumis_a).total_seconds()
        if 0 <= d < R["delai_rapide_s"]:
            applique("delai", R["delai_poids"], f"première visite {int(d)} s après l'envoi")

    # V1-7 même IP sur plusieurs destinataires de domaines différents
    if ips_multi and any((e.get("ip") or "") in ips_multi for e in evenements):
        applique("ip_multi", R["ip_multi_poids"], "même IP sur plusieurs destinataires d'entreprises différentes")

    # V1-10 balayage d'antispam : plusieurs destinataires de la même messagerie en quelques secondes
    if balayage:
        applique("balayage", R["balayage_poids"],
                 f"clic dans un balayage : ≥ {R['balayage_destinataires']} destinataires de la même messagerie "
                 f"en {R['balayage_fenetre_s']} s (antispam)")

    # Signaux faibles conservés
    if ips_robots:
        for e in evenements:
            try:
                a = ipaddress.ip_address((e.get("ip") or "").strip())
                if any(a in ipaddress.ip_network(c, strict=False) for c in ips_robots):
                    applique("ips_robots", R["ips_robots_poids"], "IP listée comme robot"); break
            except ValueError:
                continue
    # Badge « Email envoyé par la technologie Cheffer » : VISIBLE depuis le 27/09, un curieux peut
    # cliquer → simple indice ; c'est la rafale autour qui signe le scanner.
    if any(e.get("type") == "piege" for e in S):
        applique("piege", R["piege_poids"], "badge Cheffer (lien piège) suivi")
    # Formulaire de préférences envoyé SANS les preuves humaines (champ piège, geste, délai).
    perdus = [e for e in Rv if e.get("type") == "robot_perdu"]
    if perdus:
        applique("robot_perdu", R["robot_perdu_poids"], "formulaire de préférences envoyé par un robot"
                 + (f" ({perdus[0].get('motif')})" if perdus[0].get("motif") else ""))

    # V1-8 clic isolé cohérent / V1-9 réponse sur la page de rappel
    negatifs = sum(poids.values())
    urls = {e.get("url") or e.get("type") for e in S} | {e.get("url") for e in Rv if e.get("type") == "visite"}
    if negatifs == 0 and evenements and len(urls) <= 2 and nr <= 1:
        applique("isole", R["isole_bonus"], "clic isolé et cohérent")
    if any(e.get("type") in ("accepte", "refuse") for e in Rv):
        applique("post", R["post_rappel_bonus"], "réponse envoyée sur la page de rappel (action humaine)")
    elif any(e.get("type") in ("mensuel", "pause", "desinscription") for e in Rv):
        applique("post", R["post_rappel_bonus"], "préférences enregistrées par un humain (formulaire)")

    score = sum(poids.values())
    return {"score": score, "statut": statut_de(score, R["seuils"]), "raisons": raisons}


# ── Base ─────────────────────────────────────────────────────────────────────

def _ips_multi(campaign_id: str, R: dict) -> set[str]:
    """IP vues sur ≥ N destinataires de domaines différents en moins de X s (clics + visites)."""
    lignes = pg.lignes("""
        SELECT k.ip, split_part(r.email_normalized, '@', 2) AS dom, k.clicked_at AS at, k.recipient_id AS rid
          FROM clicks k JOIN recipients r ON r.id = k.recipient_id WHERE k.campaign_id = %(c)s AND k.ip IS NOT NULL
        UNION ALL
        SELECT v.ip, split_part(r.email_normalized, '@', 2), v.created_at, v.recipient_id
          FROM rappels v JOIN recipients r ON r.id = v.recipient_id
         WHERE v.campaign_id = %(c)s AND NOT v.test AND v.ip IS NOT NULL""", {"c": campaign_id})
    par_ip: dict[str, list] = {}
    for x in lignes:
        par_ip.setdefault(x["ip"], []).append(x)
    out = set()
    for ip, xs in par_ip.items():
        xs.sort(key=lambda x: x["at"])
        for i, a in enumerate(xs):
            doms = {x["dom"] for x in xs[i:] if (x["at"] - a["at"]).total_seconds() <= R["ip_multi_fenetre_s"]}
            if len(doms) >= R["ip_multi_destinataires"]:
                out.add(ip); break
    return out


def balayages(clics: list[dict], R: dict) -> set:
    """Identifiants des clics pris dans un balayage d'antispam. clics : [{id, at, domaine, recipient_id,
    secondes_depuis_envoi}] (clics Sweego). Fonction pure (testée)."""
    from jobs.capacite import groupe_de
    par: dict[str, list[dict]] = {}
    for k in clics:
        d = k.get("secondes_depuis_envoi")
        if d is not None and d > R["balayage_delai_max_s"]:
            continue
        par.setdefault(groupe_de(k["domaine"] or ""), []).append(k)
    out = set()
    for xs in par.values():
        xs.sort(key=lambda x: x["at"])
        for i, a in enumerate(xs):
            dans = [x for x in xs[i:] if (x["at"] - a["at"]).total_seconds() <= R["balayage_fenetre_s"]]
            if len({x["recipient_id"] for x in dans}) >= R["balayage_destinataires"]:
                out.update(x["id"] for x in dans)
    return out


def balayages_campagne(campaign_id: str, R: dict | None = None) -> set:
    R = R or regles()
    return balayages(pg.lignes("""SELECT k.id, k.clicked_at AS at, k.recipient_id, k.secondes_depuis_envoi,
                                         split_part(r.email_normalized, '@', 2) AS domaine
                                    FROM clicks k JOIN recipients r ON r.id = k.recipient_id
                                   WHERE k.campaign_id = %(c)s""", {"c": campaign_id}), R)


def calculer(campaign_id: str) -> dict:
    R = regles()
    try:
        ips_robots = (pg.valeur("SELECT click_rules FROM settings") or {}).get("ips_robots") or []
    except Exception:  # noqa: BLE001
        ips_robots = []
    evts: dict[int, list] = {}
    bal = balayages_campagne(campaign_id, R)
    dest_bal = set()
    for k in pg.lignes("""SELECT id, recipient_id, clicked_at, url, type_lien, ip, user_agent, proxy_sweego
                            FROM clicks WHERE campaign_id = %(c)s AND recipient_id IS NOT NULL""", {"c": campaign_id}):
        if k["id"] in bal:
            dest_bal.add(k["recipient_id"])
        evts.setdefault(k["recipient_id"], []).append({
            "source": "S", "at": k["clicked_at"], "url": k["url"], "type": k["type_lien"],
            "ip": k["ip"], "ua": k["user_agent"], "proxy": k["proxy_sweego"]})
    for v in pg.lignes("""SELECT recipient_id, created_at, url_destination, action, ip, user_agent
                            FROM rappels WHERE campaign_id = %(c)s AND NOT test AND recipient_id IS NOT NULL""",
                       {"c": campaign_id}):
        evts.setdefault(v["recipient_id"], []).append({
            "source": "R", "at": v["created_at"], "url": v["url_destination"], "type": v["action"],
            "ip": v["ip"], "ua": v["user_agent"], "proxy": False})
    for v in pg.lignes("""SELECT recipient_id, created_at, action, motif, ip, user_agent FROM preferences_evenements
                            WHERE campaign_id = %(c)s AND recipient_id IS NOT NULL""", {"c": campaign_id}):
        evts.setdefault(v["recipient_id"], []).append({
            "source": "R", "at": v["created_at"], "url": "/p", "type": v["action"], "motif": v["motif"],
            "ip": v["ip"], "ua": v["user_agent"], "proxy": False})
    if not evts:
        return {"destinataires": 0}
    soumis = {x["id"]: x["submitted_at"] for x in pg.lignes(
        "SELECT id, submitted_at FROM recipients WHERE id = ANY(%(i)s)", {"i": list(evts)})}
    multi = _ips_multi(campaign_id, R)
    compte = {s: 0 for s in STATUTS}
    for rid, liste in evts.items():
        s = scorer(liste, soumis.get(rid), R, multi, ips_robots, rid in dest_bal)
        compte[s["statut"]] += 1
        pg.ecrire("""INSERT INTO click_scores (campaign_id, recipient_id, score, statut, raisons, version_regles, calcule_at)
                     VALUES (%(c)s, %(r)s, %(s)s, %(t)s, %(x)s, %(v)s, now())
                     ON CONFLICT (campaign_id, recipient_id) DO UPDATE
                        SET score = EXCLUDED.score, statut = EXCLUDED.statut, raisons = EXCLUDED.raisons,
                            version_regles = EXCLUDED.version_regles, calcule_at = now()""",
                  {"c": campaign_id, "r": rid, "s": s["score"], "t": s["statut"], "x": s["raisons"], "v": VERSION})
    return {"destinataires": len(evts), **compte}


def recalculer_recents(minutes: int = 20) -> int:
    """Campagnes avec un clic ou une visite de rappel récents → score recalculé (worker)."""
    cids = pg.lignes("""SELECT DISTINCT campaign_id FROM clicks WHERE created_at > now() - make_interval(mins => %(m)s)
                        UNION SELECT DISTINCT campaign_id FROM rappels
                         WHERE created_at > now() - make_interval(mins => %(m)s) AND NOT test
                        UNION SELECT DISTINCT campaign_id FROM preferences_evenements
                         WHERE created_at > now() - make_interval(mins => %(m)s) AND campaign_id IS NOT NULL""", {"m": minutes})
    for x in cids:
        calculer(str(x["campaign_id"]))
    return len(cids)


def comparaison(campaign_id: str) -> dict:
    """Ancien verdict (par destinataire : humain s'il a au moins un clic humain) vs nouveau statut."""
    lignes = pg.lignes("""
        SELECT s.statut,
               CASE WHEN bool_or(k.verdict = 'humain') THEN 'humain'
                    WHEN bool_or(k.verdict = 'suspect') THEN 'suspect'
                    WHEN bool_or(k.verdict = 'robot') THEN 'robot' ELSE 'sans clic' END AS ancien,
               count(DISTINCT s.recipient_id) AS n
          FROM click_scores s LEFT JOIN clicks k ON k.recipient_id = s.recipient_id AND k.campaign_id = s.campaign_id
         WHERE s.campaign_id = %(c)s GROUP BY s.recipient_id, s.statut""", {"c": campaign_id})
    tab: dict[str, dict[str, int]] = {}
    for x in lignes:
        tab.setdefault(x["ancien"], {}).setdefault(x["statut"], 0)
        tab[x["ancien"]][x["statut"]] += 1
    return {"version": VERSION, "tableau": tab}
