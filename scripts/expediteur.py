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

from datetime import date as _date, timedelta as _timedelta

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _q(sql: str, params=None) -> list[tuple]:
    import pool_pg
    return pool_pg._q(sql, params or {})


def _ecrire(sql: str, params=None) -> int:
    import pool_pg
    return pool_pg._ecrire(sql, params)


# Combien on s'autorise à monter d'un jour sur l'autre. Le 2026-08-22, le volume est passé
# de 6 à 40 emails par boîte en une nuit — un facteur 6. Ce n'est pas le CHIFFRE qui se
# voit chez un fournisseur, c'est le SAUT : il lit un changement de comportement.
#
# La faille était structurelle : le PLAFOND (40) et le PLAN DU JOUR sont deux nombres
# différents, et seul le plafond était protégé. Une cadence de campagne pouvait demander 40
# quand la moyenne récente était à 14, sans que rien ne s'y oppose.
PROGRESSION_MAX = 1.5        # +50 % par rapport à la moyenne récente
PROGRESSION_PLANCHER = 10    # en dessous, on ne bride pas : la règle n'a plus de sens
JOURS_REFERENCE = 7

# ── La rampe de chauffe ───────────────────────────────────────────────────────
# Décision de Camille, 2026-08-25, sur la base du guide de délivrabilité de Maildoso
# (« limit cold sending to 15 emails per day per mailbox, including follow-ups ») et de la
# réputation constatée côté Maildoso le 24/08 : Google « High », Microsoft « High ».
#
# On repart de 15 et on monte d'UN email par jour pendant 20 jours, jusqu'à 35. Monter par
# paliers d'un seul email est ce qui distingue une chauffe d'un à-coup : le 2026-08-24,
# 29 emails sont partis d'une même adresse en 18 minutes parce que rien ne limitait le
# saut d'un jour sur l'autre.
#
# La rampe est un PLAFOND de plus, jamais un plancher : elle s'ajoute au plafond de la
# boîte et au plafond de progression, et c'est toujours le plus bas des trois qui gagne.
# Une fois le 20e jour passé, elle reste à 35 et cesse d'être la contrainte active si le
# plafond de la boîte est plus bas.
RAMPE_DEBUT = _date(2026, 8, 25)   # premier jour à 15
RAMPE_DEPART = 15
RAMPE_ARRIVEE = 35
RAMPE_PAS = 1                       # +1 par jour → 20 jours pour aller de 15 à 35


# ── La chauffe PROPRE À CHAQUE BOÎTE ─────────────────────────────────────────
# Le guide Maildoso : « Keep each new mailbox in warm-up for at least 14 days before
# starting cold outreach. After that, limit cold sending to 15 emails per day per mailbox. »
#
# Pendant ces 14 jours, la boîte ne fait AUCUN cold email : elle ne reçoit que le trafic de
# chauffe interne de Maildoso (Warmup Enabled, +4/jour jusqu'à 80). Une adresse neuve qui
# démarche dès le premier jour est le cas d'école du domaine grillé.
#
# La rampe de flotte (`plafond_rampe`) et la chauffe individuelle sont DEUX règles
# distinctes, et la plus basse gagne : une boîte de sept semaines suit la rampe décidée le
# 25/08, une boîte née aujourd'hui attend d'abord ses 14 jours.
CHAUFFE_JOURS = 14


def plafond_chauffe(debut: _date | None, jour: _date | None = None) -> int:
    """Ce qu'une boîte peut envoyer en COLD selon son âge propre.

    Rend 0 pendant les 14 premiers jours — pas « un peu », zéro. Ensuite la même pente que
    la flotte : 15 au premier jour utile, +1 par jour, 35 au plus.
    """
    if debut is None:
        return RAMPE_ARRIVEE                    # âge inconnu : on ne bride pas au hasard
    j = jour or _date.today()
    age = (j - debut).days
    if age < CHAUFFE_JOURS:
        return 0
    return min(RAMPE_ARRIVEE, RAMPE_DEPART + (age - CHAUFFE_JOURS) * RAMPE_PAS)


def plafond_rampe(jour: _date | None = None) -> int:
    """Le plafond du jour selon la rampe de chauffe.

    Avant le début de la rampe, elle ne contraint rien (on rend l'arrivée) : une date
    antérieure ne doit pas produire un plafond négatif ni bloquer les envois.
    """
    j = jour or _date.today()
    if j < RAMPE_DEBUT:
        return RAMPE_ARRIVEE
    ecoules = (j - RAMPE_DEBUT).days
    return min(RAMPE_ARRIVEE, RAMPE_DEPART + ecoules * RAMPE_PAS)


# ── Volumes du jour, lus dans le journal ──────────────────────────────────────
def volumes(site: str, jours: int = JOURS_REFERENCE) -> dict[str, dict]:
    """Par boîte : ce qui est parti AUJOURD'HUI, et la moyenne des derniers jours actifs.

    Les deux d'un seul trait. Séparées, ces deux mesures faisaient deux agrégats sur
    `email_events` — et `boites()` est appelé pour CHAQUE destinataire d'un lot : cent
    soixante requêtes pour un lot de quatre-vingts, afin de lire des nombres qui bougent
    d'une unité entre deux envois.

    Un envoi = un couple (adresse, campagne). La même unité des deux côtés : compter les
    adresses distinctes d'un côté et les envois de l'autre revenait à soustraire des
    grandeurs différentes, et rognait l'autorisation les jours où deux campagnes touchent
    les mêmes personnes.
    """
    lignes = _q("""
        WITH envois AS (
            SELECT DISTINCT ev.mailbox, ev.email, ev.campaign_id,
                   timezone('Europe/Paris', ev.occurred_at)::date AS jour
            FROM email_events ev
            WHERE ev.event_type = 'sent' AND ev.site_code = %(site)s
              AND ev.channel = 'maildoso' AND ev.mailbox IS NOT NULL
              AND ev.occurred_at >= now() - make_interval(days => %(j)s)),
        par_jour AS (
            SELECT mailbox, jour, count(*) AS n FROM envois GROUP BY 1, 2)
        SELECT mailbox,
               COALESCE(sum(n) FILTER (
                   WHERE jour = timezone('Europe/Paris', now())::date), 0) AS aujourdhui,
               COALESCE(round(avg(n) FILTER (
                   WHERE jour < timezone('Europe/Paris', now())::date)), 0) AS moyenne
        FROM par_jour GROUP BY 1""", {"site": site, "j": int(jours)})
    return {r[0]: {"aujourdhui": int(r[1] or 0), "moyenne": int(r[2] or 0)} for r in lignes}


def envoyes_aujourdhui(site: str) -> dict[str, int]:
    """Envois du jour par boîte. Conservée pour les appelants qui n'ont besoin que de ça."""
    return {k: v["aujourdhui"] for k, v in volumes(site).items()}


def moyenne_recente(site: str, jours: int = JOURS_REFERENCE) -> dict[str, int]:
    """Moyenne d'envois par boîte sur ses derniers JOURS ACTIFS.

    Les jours sans envoi sont exclus : une pause de week-end ou une campagne terminée
    ferait sinon chuter la moyenne, et le lendemain le moindre lot paraîtrait un saut.
    """
    return {k: v["moyenne"] for k, v in volumes(site, jours).items()}


def boites(site: str, usage: str | None = None) -> list[dict]:
    """Les boîtes du site avec leur plafond, leur consommation du jour et leur reste.

    `reste` tient compte de DEUX limites, la plus basse gagnant : le plafond journalier
    (que la montée en charge ajuste) et le plafond de progression (qu'on ne dépasse pas
    d'un jour sur l'autre). Les deux au même endroit, parce que tout ce qui envoie lit
    `reste` — campagnes comme scénarios. Une limite posée ailleurs serait une limite
    qu'un chemin d'envoi peut ignorer.
    """
    vol = volumes(site)
    out = []
    for (email, nom, cap, statut, domaine, hote, port, ident, secret,
         pause, motif_pause, usage_boite, debut_chauffe) in _q("""
            SELECT email::text, sender_name, daily_cap, status, domain,
                   smtp_host, smtp_port, username, password_ref,
                   pause_jusqu_a, pause_motif, usage, warmup_debut
            FROM mailboxes
            WHERE site_code = %(site)s AND provider = 'maildoso'
              AND (%(usage)s IS NULL OR usage = %(usage)s)
            ORDER BY email""",
            {"site": site, "usage": usage}):
        v = vol.get(email) or {}
        envoyes = v.get("aujourdhui", 0)
        # Une boîte au repos (plainte, pic de rebonds) est inutilisable, exactement comme
        # une boîte désactivée. Voir `refroidissement` : la pause se lève toute seule à
        # l'échéance, et les contacts qui lui sont attitrés attendent plutôt que de
        # changer d'expéditeur.
        au_repos = pause is not None
        # Les clés SMTP portent les noms attendus par `maildoso_backend.send_email` :
        # la boîte rendue ici doit pouvoir lui être passée telle quelle.
        plafond_jour = int(cap or 0)
        moyenne = v.get("moyenne", 0)
        # En dessous du plancher, la règle de progression ne s'applique pas : une boîte
        # qui a envoyé 3 emails hier doit pouvoir en envoyer 10 aujourd'hui sans qu'on
        # crie au saut.
        # Sans historique — boîte neuve, sortie de repos, ou inactive depuis une semaine —
        # on repart du PLANCHER, jamais du plafond. Le repli sur `plafond_jour` annulait la
        # règle dans le seul cas où elle compte : une adresse qui n'a rien envoyé depuis
        # sept jours et repart à 40, c'est exactement le saut qu'on interdit ailleurs.
        progressif = max(PROGRESSION_PLANCHER, int(moyenne * PROGRESSION_MAX))
        # Trois limites, la plus basse gagne : le plafond de la boîte, le plafond de
        # progression (pas de saut d'un jour sur l'autre) et la rampe de chauffe (le
        # calendrier). Aucune ne peut être contournée par les deux autres.
        # QUATRE limites désormais, la plus basse gagnant : le plafond de la boîte (ce que
        # Maildoso accepte réellement), le plafond de progression, la rampe de flotte, et
        # la chauffe propre à cette adresse. Une boîte de moins de 14 jours rend 0 : elle
        # est visible dans les écrans, mais elle n'envoie rien.
        rampe = plafond_rampe()
        chauffe = plafond_chauffe(debut_chauffe)
        effectif = min(plafond_jour, progressif, rampe, chauffe)
        out.append({"email": email, "sender_name": nom, "daily_cap": plafond_jour,
                    "status": "au_repos" if au_repos else statut,
                    "domaine": domaine or email.split("@")[-1],
                    "smtp_host": hote, "smtp_port": port, "username": ident,
                    "password_ref": secret,
                    "envoyes_aujourdhui": envoyes,
                    "moyenne_recente": moyenne,
                    "plafond_rampe": rampe,
                    "plafond_chauffe": chauffe,
                    "usage": usage_boite,
                    "warmup_debut": str(debut_chauffe) if debut_chauffe else None,
                    "en_chauffe": chauffe == 0,
                    "plafond_effectif": effectif,
                    "reste": 0 if au_repos else max(0, effectif - envoyes),
                    "au_repos_jusqu_a": str(pause) if pause else None,
                    "au_repos_motif": motif_pause,
                    "active": statut == "active" and not au_repos})
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


def choisir(email_contact: str, site: str, disponibles: list[dict] | None = None,
            usage: str | None = None) -> dict | None:
    """La boîte à utiliser pour ce contact, maintenant. None = ne pas lui écrire aujourd'hui.

    Trois cas, dans cet ordre :

    1. **Affinité existante et boîte utilisable** → on la reprend, quoi qu'il arrive.
    2. **Affinité existante mais boîte pleine ou en pause** → None. Le contact attend.
       C'est un choix : perdre un envoi aujourd'hui coûte moins cher que de brûler le
       capital de réputation acquis auprès de ce destinataire. Une affinité CONFIRMÉE
       n'est jamais réattribuée, même si la boîte est désactivée pour de bon.
    3. **Aucune affinité** → la boîte active la moins chargée du jour, puis on l'inscrit.
       L'équilibrage se fait donc à l'attribution, une fois par contact et pour toujours.

    `usage` ('adhoc' ou 'mozart') sépare les PREMIÈRES attributions : depuis le 2026-08-25,
    les scénarios Mozart ont leurs propres adresses pour ne pas se disputer le volume des
    campagnes. **L'affinité prime sur cette séparation** : un contact déjà lié à une
    adresse la garde, même si elle appartient à l'autre pool. Sans cette précédence, un
    prospect déjà démarché par une campagne aurait attendu indéfiniment en entrant dans un
    scénario — sa boîte n'étant pas dans la liste proposée — ou aurait changé
    d'expéditeur, ce qui remet à zéro la réputation acquise auprès de LUI.
    """
    em = (email_contact or "").strip().lower()
    # L'affinité se cherche parmi TOUTES les boîtes du site, jamais dans le sous-ensemble.
    toutes = disponibles if disponibles is not None else boites(site)
    par_email = {b["email"]: b for b in toutes}
    # La première attribution, elle, respecte l'usage demandé.
    dispo = [b for b in toutes if usage is None or b.get("usage") == usage]

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


# ── Le tableau des adresses, pour l'écran de configuration ───────────────────

def tableau(site: str) -> dict:
    """Toutes les adresses d'envoi, avec ce qu'elles ont réellement produit.

    Les volumes sont lus dans `email_events` — le journal des envois RÉELLEMENT partis —
    et jamais dans `mailboxes.sent_today` : ce compteur vit dans DuckDB, se perd sous
    verrou, et les deux copies avaient déjà divergé de 40 à 12 le 2026-08-23.
    """
    volumes = _q("""
        SELECT mailbox,
               count(DISTINCT (email, campaign_id, (occurred_at AT TIME ZONE 'Europe/Paris')::date))
                 AS total,
               count(DISTINCT (email, campaign_id)) FILTER (
                 WHERE (occurred_at AT TIME ZONE 'Europe/Paris')::date
                       = (now() AT TIME ZONE 'Europe/Paris')::date)                AS aujourdhui,
               count(DISTINCT (email, campaign_id)) FILTER (
                 WHERE (occurred_at AT TIME ZONE 'Europe/Paris')::date
                       = (now() AT TIME ZONE 'Europe/Paris')::date - 1)            AS hier,
               count(DISTINCT (email, campaign_id)) FILTER (
                 WHERE occurred_at >= now() - interval '7 days')                   AS sept_jours,
               max(occurred_at)                                                    AS dernier
          FROM email_events
         WHERE site_code = %(site)s AND event_type = 'sent' AND mailbox IS NOT NULL
         GROUP BY 1""", {"site": site})
    par_boite = {v[0]: v for v in volumes}

    # Engagement par boîte : une adresse qui n'obtient plus d'ouverture se voit ici avant
    # de se voir dans les rebonds.
    eng = {r[0]: {"ouvreurs": int(r[1]), "cliqueurs": int(r[2])} for r in _q("""
        SELECT e.mailbox,
               count(DISTINCT e.email) FILTER (WHERE o.email IS NOT NULL),
               count(DISTINCT e.email) FILTER (WHERE c.email IS NOT NULL)
          FROM email_events e
          LEFT JOIN email_events o ON o.email = e.email AND o.event_type = 'open'
                                  AND o.occurred_at >= e.occurred_at
          LEFT JOIN email_events c ON c.email = e.email AND c.event_type = 'click'
                                  AND c.occurred_at >= e.occurred_at
         WHERE e.site_code = %(site)s AND e.event_type = 'sent'
           AND e.mailbox IS NOT NULL AND e.occurred_at >= now() - interval '30 days'
         GROUP BY 1""", {"site": site})}

    lignes = []
    for b in boites(site):
        v = par_boite.get(b["email"])
        e = eng.get(b["email"]) or {}
        envoyes_30j = int(v[4]) if v else 0
        lignes.append({
            "email": b["email"],
            "expediteur": b["sender_name"],
            "usage": b.get("usage") or "adhoc",
            "statut": b["status"],
            "actif": b["active"],
            "en_chauffe": b.get("en_chauffe", False),
            "chauffe_debut": b.get("warmup_debut"),
            "chauffe_fin": (str(_date.fromisoformat(b["warmup_debut"])
                                + _timedelta(days=CHAUFFE_JOURS))
                            if b.get("warmup_debut") else None),
            "plafond_maildoso": b["daily_cap"],
            "plafond_rampe": b.get("plafond_rampe"),
            "plafond_chauffe": b.get("plafond_chauffe"),
            "plafond_effectif": b["reste"] + b["envoyes_aujourdhui"],
            "aujourdhui": int(v[2]) if v else 0,
            "hier": int(v[3]) if v else 0,
            "sept_jours": envoyes_30j,
            "total": int(v[1]) if v else 0,
            "reste": b["reste"],
            "moyenne_recente": b.get("moyenne_recente", 0),
            "dernier_envoi": str(v[5]) if v and v[5] else None,
            "ouvreurs_30j": e.get("ouvreurs", 0),
            "cliqueurs_30j": e.get("cliqueurs", 0),
            "au_repos_jusqu_a": b.get("au_repos_jusqu_a"),
            "motif_repos": b.get("motif_repos"),
        })

    lignes.sort(key=lambda x: (x["usage"], x["email"]))
    return {
        "boites": lignes,
        "totaux": {
            "adhoc": sum(1 for l in lignes if l["usage"] == "adhoc"),
            "mozart": sum(1 for l in lignes if l["usage"] == "mozart"),
            "en_chauffe": sum(1 for l in lignes if l["en_chauffe"]),
            "envoyes_aujourdhui": sum(l["aujourdhui"] for l in lignes),
            "envoyes_hier": sum(l["hier"] for l in lignes),
            "envoyes_total": sum(l["total"] for l in lignes),
            "capacite_restante": sum(l["reste"] for l in lignes),
        },
        "rampe": {"depart": RAMPE_DEPART, "arrivee": RAMPE_ARRIVEE, "pas": RAMPE_PAS,
                  "debut": str(RAMPE_DEBUT), "aujourdhui": plafond_rampe(),
                  "chauffe_jours": CHAUFFE_JOURS},
    }
