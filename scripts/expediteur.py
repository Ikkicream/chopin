#!/usr/bin/env python3
"""expediteur.py — chaque contact garde la même adresse d'envoi, pour toujours.

Décision de Camille (2026-08-23) : l'attribution ne suit PAS le secteur — les secteurs
vont changer — mais le contact. Le motif est de la délivrabilité pure : quand un prospect
ouvre ou clique, son client de messagerie enregistre un signal positif pour **cette**
adresse expéditrice. Lui réécrire depuis une autre, c'est repartir de zéro sur sa
réputation auprès de lui, et risquer le classement en indésirable — alors qu'on avait
justement gagné le droit d'arriver en boîte de réception.

Deux états, et la différence compte :

  - **attribuée** : le contact a reçu (ou va recevoir) depuis cette boîte. Si elle est
    pleine aujourd'hui, il attend demain plutôt que de changer d'adresse.
  - **confirmée** : il a ouvert ou cliqué. L'attribution devient intouchable — même une
    boîte mise en pause ne la libère pas, on préfère ne plus lui écrire du tout que lui
    écrire depuis ailleurs.

Les volumes du jour se lisent dans le JOURNAL (`email_events`), pas dans le compteur
`mailboxes.sent_today` : ce compteur vit dans `god_mode.duckdb`, il est perdu dès que le
fichier est verrouillé pendant un envoi — c'est exactement ce qui s'est produit le
2026-08-22 — et les deux copies (DuckDB et PostgreSQL) avaient déjà divergé de 40 à 12.
"""
from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _q(sql: str, params=None) -> list[tuple]:
    import pool_pg
    return pool_pg._q(sql, params or {})


def _ecrire(sql: str, params=None) -> int:
    import pool_pg
    c = pool_pg._conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql, params or {})
            n = cur.rowcount
        c.commit()
        return n
    finally:
        pool_pg._rendre(c)


# ── Volumes du jour, lus dans le journal ──────────────────────────────────────
def envoyes_aujourdhui(site: str) -> dict[str, int]:
    """Envois du jour par boîte, comptés en ENVOIS distincts (adresse, campagne, jour).

    Sert de compteur de quota : il ne peut pas se perdre, contrairement à
    `mailboxes.sent_today`, et il ne peut pas doubler, contrairement à un comptage de
    lignes du journal.
    """
    return {r[0]: int(r[1]) for r in _q("""
        WITH envois AS (
            SELECT DISTINCT ev.email, ev.campaign_id, ev.mailbox
            FROM email_events ev
            WHERE ev.event_type = 'sent' AND ev.site_code = %(site)s
              AND ev.channel = 'maildoso' AND ev.mailbox IS NOT NULL
              AND timezone('Europe/Paris', ev.occurred_at)::date
                  = timezone('Europe/Paris', now())::date)
        SELECT mailbox, count(*) FROM envois GROUP BY 1""", {"site": site})}


def boites(site: str) -> list[dict]:
    """Les boîtes du site avec leur plafond, leur consommation du jour et leur reste."""
    faits = envoyes_aujourdhui(site)
    out = []
    for (email, nom, cap, statut, domaine, hote, port, ident, secret) in _q("""
            SELECT email::text, sender_name, daily_cap, status, domain,
                   smtp_host, smtp_port, username, password_ref
            FROM mailboxes
            WHERE site_code = %(site)s AND provider = 'maildoso' ORDER BY email""",
            {"site": site}):
        envoyes = faits.get(email, 0)
        # Les clés SMTP portent les noms attendus par `maildoso_backend.send_email` :
        # la boîte rendue ici doit pouvoir lui être passée telle quelle.
        out.append({"email": email, "sender_name": nom, "daily_cap": int(cap or 0),
                    "status": statut, "domaine": domaine or email.split("@")[-1],
                    "smtp_host": hote, "smtp_port": port, "username": ident,
                    "password_ref": secret,
                    "envoyes_aujourdhui": envoyes,
                    "reste": max(0, int(cap or 0) - envoyes),
                    "active": statut == "active"})
    return out


# ── Affinité ──────────────────────────────────────────────────────────────────
def affinite(email_contact: str) -> dict | None:
    r = _q("""SELECT boite_expediteur, boite_expediteur_confirmee, boite_expediteur_at
              FROM contacts WHERE email = %(e)s""",
           {"e": (email_contact or "").strip().lower()})
    if not r or not r[0][0]:
        return None
    return {"boite": r[0][0], "confirmee": bool(r[0][1]), "depuis": str(r[0][2] or "")}


def confirmer(email_contact: str) -> bool:
    """Le prospect a ouvert ou cliqué : son adresse expéditrice devient intouchable.

    Appelée par les webhooks et le pixel d'ouverture. Ne crée jamais d'attribution — on ne
    confirme que ce qui existe : un signal d'engagement sans envoi tracé serait suspect.
    """
    return _ecrire("""
        UPDATE contacts SET boite_expediteur_confirmee = true
        WHERE email = %(e)s AND boite_expediteur IS NOT NULL
          AND NOT boite_expediteur_confirmee""",
        {"e": (email_contact or "").strip().lower()}) > 0


def choisir(email_contact: str, site: str, disponibles: list[dict] | None = None) -> dict | None:
    """La boîte à utiliser pour ce contact, maintenant. None = ne pas lui écrire aujourd'hui.

    Trois cas, dans cet ordre :

    1. **Affinité existante et boîte utilisable** → on la reprend, quoi qu'il arrive.
    2. **Affinité existante mais boîte pleine ou en pause** → None. Le contact attend.
       C'est un choix : perdre un envoi aujourd'hui coûte moins cher que de brûler le
       capital de réputation acquis auprès de ce destinataire. Une affinité CONFIRMÉE
       n'est jamais réattribuée, même si la boîte est désactivée pour de bon.
    3. **Aucune affinité** → la boîte active la moins chargée du jour, puis on l'inscrit.
       L'équilibrage se fait donc à l'attribution, une fois par contact et pour toujours.
    """
    em = (email_contact or "").strip().lower()
    dispo = disponibles if disponibles is not None else boites(site)
    par_email = {b["email"]: b for b in dispo}

    a = affinite(em)
    if a:
        b = par_email.get(a["boite"])
        if b and b["active"] and b["reste"] > 0:
            return b
        return None

    libres = [b for b in dispo if b["active"] and b["reste"] > 0]
    if not libres:
        return None
    # Moins chargée d'abord, puis plafond le plus large : à consommation égale, on remplit
    # celle qui peut le plus, pour garder de la marge sur les autres en fin de journée.
    libres.sort(key=lambda b: (b["envoyes_aujourdhui"], -b["daily_cap"], b["email"]))
    choisie = libres[0]
    _ecrire("""
        UPDATE contacts SET boite_expediteur = %(b)s, boite_expediteur_at = now()
        WHERE email = %(e)s AND boite_expediteur IS NULL""",
        {"b": choisie["email"], "e": em})
    return choisie


def repartition(site: str) -> dict:
    """Combien de contacts par boîte, et combien confirmés — pour l'écran et les alertes."""
    lignes = _q("""
        SELECT COALESCE(boite_expediteur, '(non attribué)'),
               count(*), count(*) FILTER (WHERE boite_expediteur_confirmee)
        FROM contacts ct
        WHERE EXISTS (SELECT 1 FROM contact_sites cs
                      WHERE cs.contact_id = ct.id AND cs.site_code = %(site)s)
        GROUP BY 1 ORDER BY 2 DESC""", {"site": site})
    return {r[0]: {"contacts": int(r[1]), "confirmes": int(r[2])} for r in lignes}


def rattraper_historique(site: str) -> dict:
    """Attribue rétroactivement, depuis le journal, la boîte qui a RÉELLEMENT écrit.

    Sans ce rattrapage, les 965 contacts déjà servis repartiraient sur une boîte tirée au
    hasard à leur prochaine relance — exactement ce que l'affinité doit empêcher, et sur
    la population qui a le plus à perdre : celle qui a déjà reçu quelque chose.

    La boîte retenue est celle du PREMIER envoi tracé : c'est elle qui a créé la relation
    dans le client de messagerie du destinataire. Confirme dans la foulée ceux qui ont
    ouvert ou cliqué. Idempotent — ne touche jamais une attribution déjà posée.
    """
    attribues = _ecrire("""
        WITH premier AS (
            SELECT DISTINCT ON (ev.email) ev.email, ev.mailbox
            FROM email_events ev
            WHERE ev.event_type = 'sent' AND ev.channel = 'maildoso'
              AND ev.site_code = %(site)s AND ev.mailbox IS NOT NULL
            ORDER BY ev.email, ev.occurred_at)
        UPDATE contacts ct SET boite_expediteur = premier.mailbox,
                               boite_expediteur_at = now()
        FROM premier
        WHERE ct.email = premier.email AND ct.boite_expediteur IS NULL""",
        {"site": site})

    confirmes = _ecrire("""
        UPDATE contacts ct SET boite_expediteur_confirmee = true
        WHERE ct.boite_expediteur IS NOT NULL AND NOT ct.boite_expediteur_confirmee
          AND EXISTS (SELECT 1 FROM email_events ev
                      WHERE ev.email = ct.email AND ev.site_code = %(site)s
                        AND ev.event_type IN ('open', 'click')
                        AND COALESCE((ev.meta->>'proxy')::boolean, false) = false)""",
        {"site": site})
    return {"attribues": attribues, "confirmes": confirmes,
            "repartition": repartition(site)}
