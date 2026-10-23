#!/usr/bin/env python3
"""mass_mailing/jobs/placement.py — sommes-nous en boîte de réception ou en Spam ? (21/10/2026)

« Livré » veut seulement dire que le serveur a accepté le mail : il peut l'avoir rangé en Spam. Aucun
fournisseur ne le dit. Le 21/10, Gmail a accepté 600 mails de Zylio ; son robot les a tous ouverts
3 s après la livraison ; une seule personne les a lus. Le mail de test de Camille, livré, est
introuvable hors du dossier Spam.

Ce module DÉDUIT le placement de chaque file (messagerie ou famille de serveurs) à partir de ce qui
ne ment pas : les ouvertures de vraies personnes (infra/ouvertures : box, réseau d'entreprise,
Outlook bureau, proxy d'images Gmail) et les clics humains sur le contenu. Les ouvertures de robots
prouvent seulement que le mail est arrivé quelque part.

    verdicts_ouverture(identite)   {destinataire: humain | apple | machine} (Resend : IP + logiciel)
    verdict_placement(...)         fonction PURE : boite_probable | spam_probable | inconnu
    mesurer(identite)              les signaux de chaque file sur 7 jours + le verdict
    suivre(campaign_id, identite)  écrit dans le journal de la campagne quand un verdict CHANGE

Seuils (guide § 4 « Diagnostiquer » : « clics stables partout sauf chez un fournisseur = placement
en spam chez ce fournisseur » ; alerte à −30 %) :
    au moins MIN_LIVRES livrés sur 7 jours, sinon « inconnu » ;
    0 vraie ouverture → spam probable ;
    taux humain < 30 % de celui des autres files (≥ 100 livrés chez elles) → spam probable.
Conséquence (jobs/routage.planifier) : la file passe en SONDE, quelques mails par vague, le temps
de voir si des humains réapparaissent.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import pg  # noqa: E402
from jobs import capacite  # noqa: E402

MIN_LIVRES = 50
RATIO_ALERTE = 0.30
MIN_LIVRES_REFERENCE = 100
JOURS = 7
BOITE, SPAM, INCONNU = "boite_probable", "spam_probable", "inconnu"


def verdicts_ouverture(identite: str, depuis=None) -> dict[int, str]:
    """{recipient_id: humain|apple|machine} pour les ouvertures qui portent IP et logiciel (Resend).
    Les autres (Sweego : ni IP ni logiciel) n'y sont pas : l'appelant garde l'ouverture brute."""
    from infra import ouvertures
    evs = pg.lignes("""
        SELECT r.id, w.raw_payload::jsonb #>> '{data,open,ipAddress}' AS ip, w.raw_payload::jsonb #>> '{data,open,userAgent}' AS ua,
               EXTRACT(EPOCH FROM (w.received_at - r.delivered_at)) AS secondes
          FROM recipients r JOIN campaigns c ON c.id = r.campaign_id
          JOIN webhook_events w ON w.provider = 'resend' AND w.event_type = 'email.opened'
                               AND w.raw_payload::jsonb #>> '{data,email_id}' = r.provider_message_id
         WHERE r.provider_message_id IS NOT NULL AND %(i)s = ANY(COALESCE(c.sending_domains, ARRAY[%(i)s]))
           AND (%(d)s::timestamptz IS NULL OR r.submitted_at >= %(d)s)""", {"i": identite, "d": depuis})
    par: dict[int, list[str]] = {}
    for e in evs:
        par.setdefault(e["id"], []).append(ouvertures.classer(ouvertures.organisation(e["ip"] or ""), e["ua"] or "", e["secondes"])[0])
    return {i: ouvertures.verdict_destinataire(v) for i, v in par.items()}


def ouvertures_campagne(campaign_id: str) -> dict | None:
    """UNE définition de « ouvert » pour tout l'écran d'une campagne (Camille, 21/10/2026 : la carte disait
    255 ouverts / 20 %, la barre par webmail ~6 %, le routage encore autre chose). « Ouvert » = une vraie
    personne : ouverture classée humaine (IP + logiciel) ou clic humain sur le lien du message.
    Renvoie {humains, apple, machines} (ensembles d'id destinataires), ou None si les ouvertures de la
    campagne ne portent ni IP ni logiciel (Sweego) : l'appelant garde alors son ancienne règle."""
    from infra import ouvertures
    evs = pg.lignes("""
        SELECT r.id, w.raw_payload::jsonb #>> '{data,open,ipAddress}' AS ip, w.raw_payload::jsonb #>> '{data,open,userAgent}' AS ua,
               EXTRACT(EPOCH FROM (w.received_at - r.delivered_at)) AS secondes
          FROM recipients r
          JOIN webhook_events w ON w.provider = 'resend' AND w.event_type = 'email.opened'
                               AND w.raw_payload::jsonb #>> '{data,email_id}' = r.provider_message_id
         WHERE r.campaign_id = %(c)s AND r.provider_message_id IS NOT NULL""", {"c": campaign_id})
    if not evs:
        return None
    par: dict[int, list[str]] = {}
    for e in evs:
        par.setdefault(e["id"], []).append(ouvertures.classer(ouvertures.organisation(e["ip"] or ""), e["ua"] or "", e["secondes"])[0])
    cliqueurs = {x["recipient_id"] for x in pg.lignes(
        """SELECT DISTINCT recipient_id FROM clicks WHERE campaign_id = %(c)s AND verdict = 'humain'
              AND type_lien = 'contenu' AND recipient_id IS NOT NULL""", {"c": campaign_id})}
    v = {i: ouvertures.verdict_destinataire(x) for i, x in par.items()}
    humains = {i for i, x in v.items() if x == "humain"} | cliqueurs
    return {"humains": humains, "apple": {i for i, x in v.items() if x == "apple"} - humains,
            "machines": {i for i, x in v.items() if x == "machine"} - humains}


def verdict_placement(groupe: str, livres: int, humains: int, apple: int, taux_reference: float | None) -> tuple[str, str]:
    """Fonction PURE. taux_reference = taux humain des AUTRES files (None si elles ont trop peu de livrés)."""
    if livres < MIN_LIVRES:
        return INCONNU, f"{livres} livré(s) sur {JOURS} j, {MIN_LIVRES} requis pour juger"
    # iCloud : Apple Mail précharge tout, l'ouverture humaine n'y est jamais visible ; le préchargement
    # (fait à la réception en boîte) compte comme signal.
    signal = humains + (apple if groupe == "icloud" else 0)
    taux = signal / livres
    if signal == 0:
        return SPAM, f"0 vraie ouverture sur {livres} livrés en {JOURS} j"
    if taux_reference and taux < RATIO_ALERTE * taux_reference:
        return SPAM, (f"{taux:.1%} d'ouvertures humaines contre {taux_reference:.1%} ailleurs "
                      f"(moins de {RATIO_ALERTE:.0%}) sur {livres} livrés")
    return BOITE, f"{taux:.1%} d'ouvertures humaines sur {livres} livrés" + (
        f" (ailleurs {taux_reference:.1%})" if taux_reference else "")


def mesurer(identite: str) -> dict[str, dict]:
    """{groupe: {livres, humains, apple, machines, etat, motif}} sur les 7 derniers jours."""
    capacite.charger_mx()
    lignes = pg.lignes("""
        SELECT r.id, split_part(r.email_normalized, '@', 2) AS d,
               EXISTS (SELECT 1 FROM clicks k WHERE k.recipient_id = r.id AND k.verdict = 'humain' AND k.type_lien = 'contenu') AS clic
          FROM recipients r JOIN campaigns c ON c.id = r.campaign_id
         WHERE r.delivered_at > now() - make_interval(days => %(j)s)
           AND %(i)s = ANY(COALESCE(c.sending_domains, ARRAY[%(i)s]))""", {"i": identite, "j": JOURS})
    if not lignes:
        return {}
    verdicts = verdicts_ouverture(identite, None)
    stats: dict[str, dict] = {}
    for x in lignes:
        s = stats.setdefault(capacite.groupe_de(x["d"]), {"livres": 0, "humains": 0, "apple": 0, "machines": 0})
        v = verdicts.get(x["id"])
        s["livres"] += 1
        s["humains"] += int(v == "humain" or x["clic"])
        s["apple"] += int(v == "apple" and not x["clic"])
        s["machines"] += int(v == "machine" and not x["clic"])
    for g, s in stats.items():
        autres_l = sum(t["livres"] for h, t in stats.items() if h != g)
        autres_h = sum(t["humains"] for h, t in stats.items() if h != g)
        ref = (autres_h / autres_l) if autres_l >= MIN_LIVRES_REFERENCE else None
        s["etat"], s["motif"] = verdict_placement(g, s["livres"], s["humains"], s["apple"], ref)
    return stats


SCHEMA = """
CREATE TABLE IF NOT EXISTS placement_etats (
    identite TEXT NOT NULL,
    groupe   TEXT NOT NULL,
    etat     TEXT NOT NULL,
    motif    TEXT,
    at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (identite, groupe)
)
"""


def suivre(campaign_id: str, identite: str) -> dict[str, dict]:
    """Mesure, et écrit dans le journal de la campagne chaque verdict qui change. Renvoie la mesure."""
    from jobs import envoi
    pg.ecrire(SCHEMA)
    stats = mesurer(identite)
    avant = {x["groupe"]: x["etat"] for x in pg.lignes("SELECT groupe, etat FROM placement_etats WHERE identite = %(i)s",
                                                       {"i": identite})}
    for g, s in stats.items():
        if s["etat"] == avant.get(g):
            continue
        pg.ecrire("""INSERT INTO placement_etats (identite, groupe, etat, motif) VALUES (%(i)s, %(g)s, %(e)s, %(m)s)
                     ON CONFLICT (identite, groupe) DO UPDATE SET etat = EXCLUDED.etat, motif = EXCLUDED.motif, at = now()""",
                  {"i": identite, "g": g, "e": s["etat"], "m": s["motif"]})
        if s["etat"] == INCONNU and g not in avant:
            continue
        libelle = {SPAM: "SPAM PROBABLE → file en sonde", BOITE: "boîte de réception probable", INCONNU: "pas assez de données"}[s["etat"]]
        with pg.connexion() as cur:
            envoi._audit(cur, campaign_id, "worker", "routage", "routage.placement",
                         f"{capacite.NOMS.get(g, g)} : {libelle} — {s['motif']}")
    return stats
