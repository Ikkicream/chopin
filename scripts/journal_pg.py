#!/usr/bin/env python3
"""journal_pg.py — les journaux d'envoi, lus dans PostgreSQL (dernier volet du Lot 1).

`maildoso_sent`, `sweego_events` et `mass_campaigns` vivaient dans `god_mode.duckdb` — le
fichier que le dispatch et le scraping se disputent. C'est ce verrou qui a produit,
le 2026-08-22, 156 lignes de journal en double : l'écriture PostgreSQL passait, la DuckDB
échouait, l'appelant reprenait le marquage. Tant que le volume envoyé se lit dans un
fichier à écrivain unique, la panne se répète.

Tout est ici déduit de `email_events` (et de `mass_sends` pour les envois de masse, que
Sweego ne journalise pas par destinataire — limite du canal, pas un choix).

**Les volumes comptent des ENVOIS, pas des lignes.** `count(DISTINCT (adresse, campagne,
jour))` et non `count(*)` : une reprise de marquage peut toujours écrire deux fois, et un
compteur qui double décide d'un volume d'envoi. Le dédoublonnage et l'index unique
règlent la cause ; ce comptage rend la lecture juste même si elle revient.
"""
from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# La clé d'un envoi réel : une campagne n'écrit jamais deux fois à la même personne le
# même jour. Écrite une fois, utilisée par tous les comptages.
_ENVOI = ("(ev.email, COALESCE(ev.campaign_id, '00000000-0000-0000-0000-000000000000'::uuid), "
          "timezone('UTC', ev.occurred_at)::date)")


def _q(sql: str, params=None) -> list[tuple]:
    import pool_pg
    return pool_pg._q(sql, params or {})


def _decouper(campaign_id: str) -> tuple[str | None, str | None]:
    """« lcr-9e9e6ea4-8e0-2026-07-30 » → (legacy_id « 9e9e6ea4-8e0 », jour « 2026-07-30 »).

    Le canal maildoso encode le jour dans l'identifiant de lot : c'est ce qui rend la
    garde de reprise idempotente par jour. On le redécoupe plutôt que d'ajouter une
    colonne — la forme est fixée par `campaign_engine` et testée ici même.
    """
    if not campaign_id:
        return None, None
    parts = campaign_id.split("-")
    if len(parts) < 6:
        return (f"{parts[1]}-{parts[2]}" if len(parts) >= 3 else campaign_id), None
    return f"{parts[1]}-{parts[2]}", "-".join(parts[3:6])


# ── Garde de reprise ──────────────────────────────────────────────────────────
def deja_servis(campaign_id: str) -> set[str]:
    """Destinataires déjà servis pour CE lot (campagne + jour).

    Remplace `maildoso_backend.already_sent_emails`. Sans cette garde, un process qui
    meurt au milieu d'un lot repioche les contacts déjà contactés au redémarrage. Elle
    lisait `maildoso_sent` — donc le fichier dont le verrou est justement la cause des
    morts en cours de lot.
    """
    legacy, jour = _decouper(campaign_id)
    if not legacy:
        return set()
    sql = """
        SELECT DISTINCT lower(ev.email::text)
        FROM email_events ev JOIN campaigns c ON c.id = ev.campaign_id
        WHERE ev.event_type = 'sent' AND c.legacy_id = %(legacy)s
    """
    p: dict = {"legacy": legacy}
    if jour:
        sql += " AND timezone('UTC', ev.occurred_at)::date = %(jour)s::date"
        p["jour"] = jour
    return {r[0] for r in _q(sql, p)}


def recemment_servis(emails: list[str], days: int) -> set[str]:
    """Parmi ces adresses, celles qui ont reçu un email depuis moins de `days` jours.

    Tous canaux confondus — c'est un progrès sur la version DuckDB, qui n'interrogeait que
    `maildoso_sent` : un contact servi par Sweego ou Emelia passait au travers.
    """
    ems = [(e or "").strip().lower() for e in emails if e]
    if not ems:
        return set()
    return {r[0] for r in _q("""
        SELECT DISTINCT lower(ev.email::text) FROM email_events ev
        WHERE ev.event_type = 'sent' AND lower(ev.email::text) = ANY(%(ems)s)
          AND ev.occurred_at > now() - make_interval(days => %(j)s)
    """, {"ems": ems, "j": int(days)})}


# ── Volumes ───────────────────────────────────────────────────────────────────
def envois_par_jour(site: str, legacy_id: str) -> list[dict]:
    """Ce qui est réellement parti pour cette campagne, jour par jour et par canal.

    Remplace `campaign_engine.journal_envois`. Les envois de masse Sweego viennent de
    `mass_sends` : le canal ne journalise pas par destinataire, seul le nombre est connu.
    """
    lignes: dict[str, dict] = {}
    for jour, canal, n in _q(f"""
            SELECT timezone('UTC', ev.occurred_at)::date AS j, ev.channel,
                   count(DISTINCT {_ENVOI})
            FROM email_events ev JOIN campaigns c ON c.id = ev.campaign_id
            WHERE ev.event_type = 'sent' AND c.legacy_id = %(legacy)s AND ev.site_code = %(site)s
            GROUP BY 1, 2""", {"legacy": legacy_id, "site": site}):
        e = lignes.setdefault(str(jour), {"jour": str(jour), "volume": 0, "canal": canal})
        e["volume"] += int(n)
    for jour, n in _q("""
            SELECT timezone('UTC', created_at)::date AS j, sum(recipients_count)
            FROM mass_sends WHERE site_code = %(site)s AND campaign_ref LIKE %(prefixe)s
            GROUP BY 1""", {"site": site, "prefixe": f"{site}-{legacy_id}-%"}):
        e = lignes.setdefault(str(jour), {"jour": str(jour), "volume": 0, "canal": "sweego"})
        e["volume"] += int(n or 0)
    return sorted(lignes.values(), key=lambda x: x["jour"], reverse=True)


def envois_de_campagne(site: str, legacy_id: str) -> tuple[list[str], str | None]:
    """Les adresses réellement servies par cette campagne, et la date du dernier envoi.

    Remplace la lecture de `reconcile_from_sent_log` — le rattrapage d'une campagne
    arrêtée en cours de lot, dont c'est justement le scénario de panne.
    """
    r = _q("""
        SELECT DISTINCT lower(ev.email::text)
        FROM email_events ev JOIN campaigns c ON c.id = ev.campaign_id
        WHERE ev.event_type = 'sent' AND c.legacy_id = %(legacy)s AND ev.site_code = %(site)s
    """, {"legacy": legacy_id, "site": site})
    d = _q("""
        SELECT max(ev.occurred_at) FROM email_events ev JOIN campaigns c ON c.id = ev.campaign_id
        WHERE ev.event_type = 'sent' AND c.legacy_id = %(legacy)s AND ev.site_code = %(site)s
    """, {"legacy": legacy_id, "site": site})
    return [x[0] for x in r], (str(d[0][0]) if d and d[0][0] else None)


def stats_canal(site: str, canal: str = "maildoso") -> dict:
    """Envois et erreurs d'un canal pour ce site.

    `errors` est rendu à 0 : `email_events` n'a pas de type « échec d'envoi » (contrainte
    de la table), et le journal DuckDB qu'il remplace n'en contenait aucun sur 1 462 lignes
    — la branche existait sans avoir jamais servi. Si un jour on veut compter les échecs,
    c'est un type d'événement à ajouter, pas une colonne de statut à ressusciter.
    """
    r = _q(f"""SELECT count(DISTINCT {_ENVOI}) FROM email_events ev
               WHERE ev.event_type = 'sent' AND ev.site_code = %(site)s
                 AND ev.channel = %(canal)s""", {"site": site, "canal": canal})
    return {"sent": int(r[0][0] or 0) if r else 0, "errors": 0}


def volume_par_boite(site: str, depuis) -> dict[str, dict]:
    """Envois par boîte expéditrice depuis `depuis`, et volume du dernier jour actif.

    C'est la lecture qui pilote la montée en charge (`maildoso_ramp`) : elle décide
    combien chaque boîte a le droit d'envoyer demain. La compter sur des lignes plutôt que
    sur des envois — 316 au lieu de 160 le 22/08 — aurait fait croire les boîtes saturées.
    """
    lignes = _q(f"""
        WITH envois AS (
            SELECT DISTINCT ON ({_ENVOI}) ev.mailbox,
                   timezone('UTC', ev.occurred_at)::date AS jour
            FROM email_events ev
            WHERE ev.event_type = 'sent' AND ev.site_code = %(site)s
              AND ev.channel = 'maildoso' AND ev.mailbox IS NOT NULL
              AND ev.occurred_at >= %(depuis)s
            ORDER BY {_ENVOI}, ev.occurred_at)
        SELECT mailbox, jour, count(*) FROM envois GROUP BY 1, 2""",
        {"site": site, "depuis": depuis})
    out: dict[str, dict] = {}
    for boite, jour, n in lignes:
        e = out.setdefault(boite, {"envoyes": 0, "dernier_jour": None, "dernier_jour_envoyes": 0})
        e["envoyes"] += int(n)
        if e["dernier_jour"] is None or str(jour) > e["dernier_jour"]:
            e["dernier_jour"] = str(jour)
            e["dernier_jour_envoyes"] = int(n)
    return out


# ── Envois de masse (Sweego) ──────────────────────────────────────────────────
def enregistrer_envoi_masse(id_: str, site: str, name: str, campaign_ref: str, subject: str,
                            sector: str, message_id: str, count: int,
                            transaction_id: str, by: str = "ui") -> bool:
    import pool_pg
    c = pool_pg._conn()
    try:
        with c.cursor() as cur:
            cur.execute("""
                INSERT INTO mass_sends (id, site_code, name, campaign_ref, campaign_id,
                    subject, sector, message_id, recipients_count, transaction_id,
                    status, created_by)
                VALUES (%s,%s,%s,%s,
                        (SELECT id FROM campaigns WHERE %s LIKE '%%' || legacy_id || '%%' LIMIT 1),
                        %s,%s,%s,%s,%s,'sent',%s)
                ON CONFLICT (id) DO NOTHING
            """, (id_, site, name, campaign_ref, campaign_ref, subject, sector,
                  message_id, int(count or 0), transaction_id, by))
        c.commit()
        return True
    finally:
        pool_pg._rendre(c)


def lister_envois_masse(site: str) -> list[dict]:
    return [{"id": r[0], "name": r[1], "campaign_id": r[2], "subject": r[3], "sector": r[4],
             "recipients_count": int(r[5] or 0), "transaction_id": r[6], "status": r[7],
             "created_at": str(r[8])}
            for r in _q("""
                SELECT id, name, campaign_ref, subject, sector, recipients_count,
                       transaction_id, status, created_at
                FROM mass_sends WHERE site_code = %(site)s ORDER BY created_at DESC""",
                {"site": site})]


# ── Lectures brutes pour les tableaux de bord ─────────────────────────────────
# Rendues dans la MÊME forme que les requêtes DuckDB qu'elles remplacent — y compris
# l'identifiant de dispatch « {site}-{campagne}-{jour} », reconstruit ici. Le découpage
# par jour, le passage à l'heure de Paris et le regroupement par campagne restent donc
# inchangés côté appelant : on remplace la source, pas la logique d'affichage.

_REF = ("%(site)s || '-' || c.legacy_id || '-' || "
        "to_char(timezone('UTC', ev.occurred_at), 'YYYY-MM-DD')")


def envois_bruts(site: str, depuis) -> list[tuple]:
    """(instant, adresse, identifiant de dispatch) — un tuple par ENVOI distinct."""
    return [(r[0], r[1], r[2]) for r in _q(f"""
        SELECT DISTINCT ON ({_ENVOI})
               ev.occurred_at, lower(ev.email::text),
               CASE WHEN c.legacy_id IS NULL THEN NULL ELSE {_REF} END
        FROM email_events ev LEFT JOIN campaigns c ON c.id = ev.campaign_id
        WHERE ev.event_type = 'sent' AND ev.site_code = %(site)s
          AND ev.channel = 'maildoso' AND ev.occurred_at >= %(depuis)s
        ORDER BY {_ENVOI}, ev.occurred_at""", {"site": site, "depuis": depuis})]


def masse_brute(site: str, depuis) -> list[tuple]:
    """(instant, nombre de destinataires, identifiant de dispatch)."""
    return [(r[0], int(r[1] or 0), r[2]) for r in _q("""
        SELECT created_at, recipients_count, campaign_ref FROM mass_sends
        WHERE site_code = %(site)s AND created_at >= %(depuis)s""",
        {"site": site, "depuis": depuis})]


def rebonds_bruts(site: str, depuis) -> list[tuple]:
    """(instant, adresse) pour les rebonds durs et les plaintes."""
    return [(r[0], r[1]) for r in _q("""
        SELECT ev.occurred_at, lower(ev.email::text) FROM email_events ev
        WHERE ev.site_code = %(site)s AND ev.event_type IN ('bounce', 'complaint')
          AND ev.occurred_at >= %(depuis)s""", {"site": site, "depuis": depuis})]


# Le tableau de bord raisonne encore en vocabulaire Sweego : on le lui rend tel quel
# plutôt que de lui imposer le vocabulaire du journal au milieu d'un portage.
_VERS_SWEEGO = {"open": "email_opened", "click": "email_clicked",
                "bounce": "hard_bounce", "complaint": "complaint", "unsub": "list_unsub"}


def evenements_canal(site: str, canal: str = "sweego") -> list[tuple]:
    """(type d'événement Sweego, adresse, instant) — tout l'historique d'un canal."""
    return [(_VERS_SWEEGO.get(r[0], r[0]), r[1], r[2]) for r in _q("""
        SELECT ev.event_type, lower(ev.email::text), ev.occurred_at FROM email_events ev
        WHERE ev.site_code = %(site)s AND ev.channel = %(canal)s
          AND ev.event_type IN ('open', 'click', 'bounce', 'complaint')""",
        {"site": site, "canal": canal})]


def totaux_masse(site: str) -> tuple[int, object]:
    """(destinataires cumulés, date du premier envoi de masse)."""
    r = _q("""SELECT COALESCE(sum(recipients_count), 0), min(created_at)
              FROM mass_sends WHERE site_code = %(site)s""", {"site": site})
    return (int(r[0][0] or 0), r[0][1]) if r else (0, None)
