#!/usr/bin/env python3
"""followup_backend.py — Suivi commercial : attribution des rappels et journal d'appels.

Deux principes de conception, hérités des erreurs de la journée du 2026-08-19 :

1. **L'état se met à jour, le journal ne se réécrit jamais.** `contact_followup` porte l'état
   courant, `followup_events` garde chaque interaction. Un CRM qui écrase « dernier appel »
   à chaque appel perd la relation : on ne sait plus ce qui a été dit ni combien de fois on
   a relancé. C'est exactement ce qui rendait `contact_site_history` inexploitable.

2. **L'attribution est exclusive et traçable.** Un contact appartient à un commercial à la
   fois, contrainte d'unicité en base — sans quoi deux commerciaux appellent le même
   prospect à une heure d'intervalle. Chaque prise et chaque libération laissent une ligne
   au journal, avec qui et quand.

Règles d'accès, appliquées ICI et pas dans l'interface : un commercial voit ses contacts et
le vivier non attribué, jamais ceux d'un collègue. Un administrateur voit tout et distribue.
Le contrôle côté serveur est le seul qui compte — l'interface peut être contournée.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

ROLES_ADMIN = ("admin", "superadmin")
ROLE_COMMERCIAL = "commercial"

STATUTS = ("a_faire", "en_cours", "a_relancer", "gagne", "perdu", "injoignable")
STATUTS_OUVERTS = ("a_faire", "en_cours", "a_relancer")

_POOL = None


def _dsn() -> str:
    for ligne in (BASE_DIR / ".env").read_text().splitlines():
        if ligne.startswith("PG_DSN="):
            return ligne.split("=", 1)[1].strip()
    raise RuntimeError("PG_DSN absent de .env")


def _conn():
    global _POOL
    import psycopg2.pool
    if _POOL is None:
        _POOL = psycopg2.pool.ThreadedConnectionPool(1, 8, _dsn())
    return _POOL.getconn()


def _rendre(c):
    if _POOL is not None:
        _POOL.putconn(c)


def _now():
    return datetime.now(timezone.utc)


# ── Lecture ───────────────────────────────────────────────────────────────────

_COLONNES = ["contact_id", "email", "site_code", "prenom", "nom", "societe", "tel",
             "website", "city", "dept_code", "prenom_source", "state", "followup_id",
             "statut", "assigned_to", "assigned_at", "next_action_at", "last_call_at",
             "outcome", "notes", "last_open_at", "last_click_at", "opens", "clicks",
             "nb_interactions", "flash", "flash_at"]


def _ligne(r) -> dict:
    d = dict(zip(_COLONNES, r))
    for k in ("assigned_at", "next_action_at", "last_call_at", "last_open_at",
              "last_click_at", "flash_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


def lister(site: str, role: str, username: str, vue: str = "mes") -> dict:
    """Contacts à rappeler, filtrés selon le rôle de l'appelant.

    `vue` : 'mes' (les miens) | 'vivier' (non attribués) | 'tous' (administrateurs).
    Un commercial qui demande 'tous' est ramené à 'mes' — silencieusement côté données, mais
    la réponse porte `vue_appliquee` pour que l'interface puisse le dire honnêtement.
    """
    est_admin = role in ROLES_ADMIN
    vue_demandee = vue
    if not est_admin and vue == "tous":
        vue = "mes"

    where = ["site_code = %(site)s"]
    params: dict = {"site": site, "moi": username}
    if vue == "mes":
        where.append("assigned_to = %(moi)s")
    elif vue == "vivier":
        where.append("assigned_to IS NULL")

    sql = f"""
        SELECT contact_id, email, site_code, prenom, nom, societe, tel, website, city,
               dept_code, prenom_source, state, followup_id, statut, assigned_to,
               assigned_at, next_action_at, last_call_at, outcome, notes,
               last_open_at, last_click_at, opens, clicks, nb_interactions,
               flash, flash_at
        FROM v_a_rappeler
        WHERE {' AND '.join(where)}
        ORDER BY
            -- Les contacts épinglés d'abord : c'est le sens même de l'épingle, « celui-là,
            -- je le rappelle tout à l'heure ».
            flash DESC,
            flash_at DESC NULLS LAST,
            -- Puis les relances dues : c'est un engagement pris envers le prospect.
            (next_action_at IS NOT NULL AND next_action_at <= now()) DESC,
            next_action_at ASC NULLS LAST,
            last_click_at DESC NULLS LAST
    """
    c = _conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql, params)
            lignes = [_ligne(r) for r in cur.fetchall()]
            # Compteurs de tous les onglets, pour que l'interface n'ait pas à deviner ce
            # qu'elle affichera avant de cliquer.
            cpt = _compteurs(cur, site, username)
    finally:
        c.rollback()
        _rendre(c)

    # `total` = le chiffre du tableau de bord ; l'écart avec `suivis` est le nombre de
    # contacts repérés mais pas encore enrichis, donc absents de cette liste. L'écran le
    # dit plutôt que de laisser croire qu'il en manque sans raison.
    total = _total_pool(site)
    if total is None or total < cpt["suivis"]:
        total = cpt["suivis"]

    return {"site": site, "vue_demandee": vue_demandee, "vue_appliquee": vue,
            "est_admin": est_admin, "contacts": lignes,
            "compteurs": {"mes": cpt["mes"], "vivier": cpt["vivier"],
                          "tous": cpt["suivis"] if est_admin else None,
                          "en_retard": cpt["en_retard"],
                          "suivis": cpt["suivis"], "total": total,
                          "flashs": cpt.get("flashs", 0),
                          "retires": cpt.get("retires", 0),
                          "en_attente": max(0, total - cpt["suivis"] - cpt.get("retires", 0))}}


# ── Compteurs (pastille du menu) ──────────────────────────────────────────────
# Le tableau de bord annonce « À rappeler : 75 » (leads + PRM du pool) tandis que cette
# liste en montre 61 : un contact n'entre dans PostgreSQL qu'une fois enrichi. Plutôt que
# de laisser deux écrans se contredire, on renvoie les DEUX chiffres et l'écart.

_CACHE_POOL: dict = {}
_TTL_POOL = 120.0   # secondes : le pool est en DuckDB, un seul écrivain à la fois


def _total_pool(site: str) -> int | None:
    """Leads + PRM du pool — le chiffre de la tuile « À rappeler » du tableau de bord.

    Mis en cache 2 minutes : la pastille est rafraîchie en boucle par chaque onglet ouvert,
    et `contacts.duckdb` n'accepte qu'un écrivain — inutile d'aller le déranger à chaque fois.
    """
    import time
    e = _CACHE_POOL.get(site)
    if e and (time.time() - e[0]) < _TTL_POOL:
        return e[1]
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        import contacts_pool_backend as pool
        etats = (pool.stats_for_site(site) or {}).get("by_state") or {}
        valeur = int(etats.get("lead", 0) or 0) + int(etats.get("prm", 0) or 0)
    except Exception:
        # Pool indisponible (verrou d'écriture) : on ne casse pas la pastille pour autant,
        # l'appelant se rabattra sur le nombre de suivis PostgreSQL.
        valeur = None
    _CACHE_POOL[site] = (time.time(), valeur)
    return valeur


# Objectif d'appels par jour et par commercial. Un chiffre rond, assumé comme un repère
# de motivation et non comme une norme : il sert à donner une barre à remplir le matin.
OBJECTIF_APPELS_JOUR = 10


def _appels_du_jour(cur, site: str, username: str) -> int:
    """Appels consignés aujourd'hui par cette personne, en heure de Paris.

    En UTC, un appel passé à 1 h du matin compterait pour la veille. Le serveur tourne en
    UTC, la comparaison se fait donc explicitement en Europe/Paris — même règle que la
    fenêtre d'envoi.
    """
    cur.execute("""
        SELECT count(*) FROM followup_events
        WHERE site_code = %(site)s AND auteur = %(moi)s AND type = 'appel'
          AND (occurred_at AT TIME ZONE 'Europe/Paris')::date
              = (now() AT TIME ZONE 'Europe/Paris')::date
    """, {"site": site, "moi": username})
    return int(cur.fetchone()[0] or 0)


def _compteurs(cur, site: str, username: str) -> dict:
    """Les quatre compteurs PostgreSQL, en une requête."""
    cur.execute("""
        SELECT count(*) FILTER (WHERE assigned_to = %(moi)s),
               count(*) FILTER (WHERE assigned_to IS NULL),
               count(*),
               count(*) FILTER (WHERE assigned_to = %(moi)s
                                  AND next_action_at IS NOT NULL
                                  AND next_action_at <= now()),
               count(*) FILTER (WHERE flash)
        FROM v_a_rappeler WHERE site_code = %(site)s
    """, {"site": site, "moi": username})
    mes, vivier, suivis, retard, flashs = cur.fetchone()
    # Les contacts retirés ne sont plus dans la vue : sans ce comptage, l'écart avec le
    # total du pool les ferait passer pour « en attente d'enrichissement ».
    cur.execute("""SELECT count(*) FROM contact_followup
                   WHERE site_code = %(site)s AND retire_at IS NOT NULL""",
                {"site": site})
    retires = cur.fetchone()[0]
    return {"mes": mes, "vivier": vivier, "suivis": suivis, "en_retard": retard,
            "flashs": flashs, "retires": retires}


def compter(site: str, role: str, username: str) -> dict:
    """Compteurs de la liste d'appels, sans charger les fiches.

    Appelée en boucle par la pastille du menu : elle ne lit que des `count(*)`.

    - `total`      : ce qu'affiche le tableau de bord (leads + PRM du pool).
    - `suivis`     : ce que cette liste sait montrer (contacts déjà dans PostgreSQL).
    - `en_attente` : l'écart — des contacts identifiés mais pas encore enrichis.
    - `pastille`   : le nombre à afficher pour CE rôle. Un commercial ne voit que ses
      contacts et le vivier : lui montrer 75 lui promettrait un travail qu'il ne verra pas.
    """
    est_admin = role in ROLES_ADMIN
    c = _conn()
    try:
        with c.cursor() as cur:
            cpt = _compteurs(cur, site, username)
            cpt["appels_jour"] = _appels_du_jour(cur, site, username)
    finally:
        c.rollback()
        _rendre(c)

    total = _total_pool(site)
    if total is None or total < cpt["suivis"]:
        total = cpt["suivis"]
    cpt.update({
        "site": site,
        "total": total,
        "en_attente": max(0, total - cpt["suivis"] - cpt.get("retires", 0)),
        "pastille": total if est_admin else (cpt["mes"] + cpt["vivier"]),
        "est_admin": est_admin,
        "objectif_jour": OBJECTIF_APPELS_JOUR,
    })
    return cpt

def journal(site: str, email: str, limite: int = 50) -> list[dict]:
    """Historique des interactions, du plus récent au plus ancien."""
    c = _conn()
    try:
        with c.cursor() as cur:
            cur.execute("""SELECT occurred_at, auteur, type, detail, meta
                           FROM followup_events
                           WHERE site_code = %s AND email = %s
                           ORDER BY occurred_at DESC LIMIT %s""",
                        [site, (email or "").strip().lower(), limite])
            return [{"at": r[0].isoformat(), "auteur": r[1], "type": r[2],
                     "detail": r[3], "meta": r[4]} for r in cur.fetchall()]
    finally:
        c.rollback()
        _rendre(c)


def commerciaux() -> list[dict]:
    """Comptes pouvant recevoir une attribution. Lu depuis auth.duckdb, la source des rôles."""
    import sys
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    try:
        # Ouverture commune : en lecture seule, DuckDB met l'instance en cache avec une
        # configuration que l'authentification — qui ÉCRIT dans cette base — ne peut plus
        # rejoindre. Voir `duck_ouverture`.
        from duck_ouverture import ouvrir as _ouvrir
        a = _ouvrir(BASE_DIR / "data" / "auth.duckdb")
    except Exception:
        return []
    try:
        rows = a.execute("""SELECT username, prenom, nom, role, sites FROM users
                            WHERE COALESCE(disabled, FALSE) = FALSE
                              AND role IN ('commercial', 'admin', 'superadmin')
                            ORDER BY role, username""").fetchall()
    finally:
        a.close()
    out = []
    for u, p, n, r, sites in rows:
        try:
            liste = json.loads(sites) if isinstance(sites, str) else (sites or [])
        except Exception:
            liste = []
        out.append({"username": u, "nom_complet": " ".join(x for x in (p, n) if x) or u,
                    "role": r, "sites": liste})
    return out


# ── Écriture ──────────────────────────────────────────────────────────────────

def _garantir_suivi(cur, site: str, email: str, contact_id: str | None) -> str:
    """Crée la ligne de suivi si elle n'existe pas. Retourne son id."""
    cur.execute("""INSERT INTO contact_followup (email, site_code, contact_id)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (email, site_code) DO UPDATE
                     SET contact_id = COALESCE(contact_followup.contact_id, EXCLUDED.contact_id)
                   RETURNING id""", [email, site, contact_id])
    return cur.fetchone()[0]


def _journaliser(cur, site: str, email: str, auteur: str, type_: str,
                 detail: str = "", meta: dict | None = None) -> None:
    cur.execute("""INSERT INTO followup_events (email, site_code, auteur, type, detail, meta)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                [email, site, auteur, type_, detail or None, json.dumps(meta or {})])


def _contact_id(cur, site: str, email: str) -> str | None:
    cur.execute("""SELECT ct.id FROM contacts ct
                   JOIN contact_sites cs ON cs.contact_id = ct.id AND cs.site_code = %s
                   WHERE ct.email = %s""", [site, email])
    r = cur.fetchone()
    return r[0] if r else None


def _peut_agir(cur, site: str, email: str, role: str, username: str) -> tuple[bool, str]:
    """Le demandeur a-t-il la main sur ce contact ?

    Un administrateur, toujours. Un commercial, seulement si le contact lui est attribué ou
    n'appartient à personne — sinon il écrirait dans le suivi d'un collègue, et deux
    versions de la même relation cohabiteraient.
    """
    if role in ROLES_ADMIN:
        return True, ""
    if role != ROLE_COMMERCIAL:
        return False, "rôle sans accès au suivi commercial"
    cur.execute("SELECT assigned_to FROM contact_followup WHERE email = %s AND site_code = %s",
                [email, site])
    r = cur.fetchone()
    proprio = r[0] if r else None
    if proprio in (None, username):
        return True, ""
    return False, f"contact attribué à {proprio}"


def assigner(site: str, email: str, vers: str | None, role: str, username: str) -> dict:
    """Attribue (ou libère si `vers` est None) un contact à un commercial."""
    email = (email or "").strip().lower()
    if not email:
        return {"ok": False, "error": "email manquant"}

    c = _conn()
    try:
        with c:
            with c.cursor() as cur:
                autorise, motif = _peut_agir(cur, site, email, role, username)
                if not autorise:
                    return {"ok": False, "error": motif}
                # Un commercial ne peut s'attribuer qu'à lui-même : autoriser l'inverse
                # ferait de la distribution une action sans responsable identifié.
                if role not in ROLES_ADMIN and vers not in (None, username):
                    return {"ok": False, "error": "seul un administrateur peut attribuer à un tiers"}
                if vers:
                    connus = {u["username"] for u in commerciaux()}
                    if vers not in connus:
                        return {"ok": False, "error": f"compte inconnu ou sans accès : {vers}"}

                _garantir_suivi(cur, site, email, _contact_id(cur, site, email))
                cur.execute("""UPDATE contact_followup
                               SET assigned_to = %s,
                                   assigned_at = CASE WHEN %s IS NULL THEN NULL ELSE now() END,
                                   assigned_by = %s, updated_at = now()
                               WHERE email = %s AND site_code = %s""",
                            [vers, vers, username, email, site])
                _journaliser(cur, site, email, username,
                             "assignation" if vers else "desassignation",
                             f"attribué à {vers}" if vers else "remis au vivier",
                             {"vers": vers})
        return {"ok": True, "email": email, "assigned_to": vers}
    finally:
        _rendre(c)


# ── Attribution automatique ───────────────────────────────────────────────────
# Décidé par le user le 2026-08-19 : un rappel qui n'appartient à personne n'est appelé par
# personne. Les 60 contacts du vivier attendaient depuis le 7 août. Ils partent donc d'office
# chez le commercial nommé ci-dessous, dès leur entrée dans la liste, et un balayage rattrape
# ceux qui seraient passés par un autre chemin.
#
# Deux garde-fous :
#   1. On ne touche JAMAIS un contact déjà attribué — c'est le rôle du `WHERE ... IS NULL`
#      posé sur l'`ON CONFLICT`. Sans lui, une attribution automatique volerait à un
#      commercial un prospect qu'il est en train d'appeler.
#   2. Si le compte nommé n'existe pas, est désactivé, ou n'a pas ce site, on n'attribue à
#      PERSONNE. Se rabattre sur « le premier commercial venu » ferait changer de
#      destinataire au premier compte créé, sans que personne ne l'ait décidé.

COMMERCIAL_PAR_DEFAUT = "Romeo"
AUTEUR_AUTO = "attribution-auto"

_CACHE_DEFAUT: dict = {}
_TTL_DEFAUT = 600.0


def commercial_par_defaut(site: str) -> str | None:
    """Le compte qui reçoit les rappels d'office sur ce site, ou None s'il n'y en a pas.

    Mis en cache 10 min : la fonction est appelée à chaque contact promu, et la liste des
    comptes vit dans DuckDB — inutile de l'ouvrir à chaque fois.
    """
    import time
    e = _CACHE_DEFAUT.get(site)
    if e and (time.time() - e[0]) < _TTL_DEFAUT:
        return e[1]
    vers = None
    try:
        for u in commerciaux():
            if u["username"].lower() != COMMERCIAL_PAR_DEFAUT.lower():
                continue
            if u["role"] == ROLE_COMMERCIAL and (not u["sites"] or site in u["sites"]):
                vers = u["username"]
            break
    except Exception:
        # Base des comptes momentanément illisible : on n'attribue rien plutôt que d'écrire
        # un nom qu'on n'a pas pu vérifier. Le balayage suivant rattrapera.
        vers = None
    _CACHE_DEFAUT[site] = (time.time(), vers)
    return vers


def attribuer_auto(site: str, email: str | None = None,
                   contact_id: str | None = None) -> dict:
    """Attribue au commercial par défaut les rappels que personne n'a pris.

    Sans `email` ni `contact_id` : balaie tout le vivier du site (rattrapage de nuit).
    Avec l'un des deux : ne traite que ce contact (à sa promotion en lead / PRM).

    N'écrase jamais une attribution existante, et journalise chaque prise pour qu'on
    puisse dire, six mois plus tard, pourquoi ce prospect est chez celui-là.
    """
    vers = commercial_par_defaut(site)
    if not vers:
        return {"ok": False, "attribues": 0,
                "motif": f"aucun commercial « {COMMERCIAL_PAR_DEFAUT} » actif sur {site}"}

    params = {"site": site, "vers": vers, "par": AUTEUR_AUTO}
    filtre = ""
    if email:
        params["email"] = (email or "").strip().lower()
        filtre = "AND v.email = %(email)s"
    elif contact_id:
        params["cid"] = contact_id
        filtre = "AND v.contact_id = %(cid)s"

    c = _conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute(f"""
                    INSERT INTO contact_followup (email, site_code, contact_id, assigned_to,
                                                  assigned_at, assigned_by, statut)
                    SELECT v.email, v.site_code, v.contact_id, %(vers)s, now(), %(par)s, 'a_faire'
                    FROM v_a_rappeler v
                    WHERE v.site_code = %(site)s AND v.assigned_to IS NULL {filtre}
                    ON CONFLICT (email, site_code) DO UPDATE
                       SET assigned_to = EXCLUDED.assigned_to,
                           assigned_at = now(),
                           assigned_by = EXCLUDED.assigned_by,
                           updated_at  = now()
                       -- Le contact déjà pris par un collègue n'est pas touché, et ne
                       -- ressort donc pas dans le RETURNING : rien n'est journalisé.
                       WHERE contact_followup.assigned_to IS NULL
                    RETURNING email
                """, params)
                pris = [r[0] for r in cur.fetchall()]
                for em in pris:
                    _journaliser(cur, site, em, AUTEUR_AUTO, "assignation",
                                 f"attribué d'office à {vers}",
                                 {"vers": vers, "automatique": True})
    finally:
        _rendre(c)

    return {"ok": True, "vers": vers, "attribues": len(pris), "emails": pris[:20]}


def basculer_flash(site: str, email: str, role: str, username: str) -> dict:
    """Épingle ou dépingle un contact : il remonte en tête de la liste d'appels.

    C'est un marque-page, pas un statut. Il ne dit rien de la relation avec le prospect —
    seulement « celui-là, je le rappelle tout à l'heure ». Il n'entre donc pas au journal :
    consigner « épinglé / dépinglé » dix fois par jour noierait les vraies interactions.
    """
    email = (email or "").strip().lower()
    if not email:
        return {"ok": False, "error": "email manquant"}
    c = _conn()
    try:
        with c:
            with c.cursor() as cur:
                autorise, motif = _peut_agir(cur, site, email, role, username)
                if not autorise:
                    return {"ok": False, "error": motif}
                _garantir_suivi(cur, site, email, _contact_id(cur, site, email))
                cur.execute("""UPDATE contact_followup
                               SET flash = NOT COALESCE(flash, false),
                                   flash_at = CASE WHEN COALESCE(flash, false)
                                                   THEN NULL ELSE now() END,
                                   updated_at = now()
                               WHERE email = %s AND site_code = %s
                               RETURNING flash""", [email, site])
                flash = cur.fetchone()[0]
    finally:
        _rendre(c)
    return {"ok": True, "email": email, "flash": flash}


def retirer(site: str, email: str, role: str, username: str,
            annuler: bool = False) -> dict:
    """Retire un contact de la liste d'appels — ou l'y remet si `annuler`.

    On ne SUPPRIME pas : le contact reste dans le référentiel, son journal aussi. Une
    suppression réelle serait de toute façon sans effet, `pg_reconcile` le rétablissant au
    passage suivant puisqu'il reste éligible. Le retrait, lui, tient : la vue
    `v_a_rappeler` l'exclut, donc la liste ET les compteurs.
    """
    email = (email or "").strip().lower()
    if not email:
        return {"ok": False, "error": "email manquant"}
    c = _conn()
    try:
        with c:
            with c.cursor() as cur:
                autorise, motif = _peut_agir(cur, site, email, role, username)
                if not autorise:
                    return {"ok": False, "error": motif}
                _garantir_suivi(cur, site, email, _contact_id(cur, site, email))
                if annuler:
                    cur.execute("""UPDATE contact_followup
                                   SET retire_at = NULL, retire_par = NULL, updated_at = now()
                                   WHERE email = %s AND site_code = %s""", [email, site])
                    _journaliser(cur, site, email, username, "statut",
                                 "remis dans la liste d'appels")
                else:
                    cur.execute("""UPDATE contact_followup
                                   SET retire_at = now(), retire_par = %s,
                                       flash = false, flash_at = NULL, updated_at = now()
                                   WHERE email = %s AND site_code = %s""",
                                [username, email, site])
                    # Celui-là entre au journal : c'est une décision sur le prospect, et on
                    # doit pouvoir dire six mois plus tard qui l'a écarté et quand.
                    _journaliser(cur, site, email, username, "statut",
                                 "retiré de la liste d'appels")
    finally:
        _rendre(c)
    return {"ok": True, "email": email, "retire": not annuler}


def enregistrer_appel(site: str, email: str, role: str, username: str,
                      statut: str | None = None, outcome: str = "",
                      note: str = "", next_action_at: str | None = None,
                      est_un_appel: bool = True) -> dict:
    """Consigne une interaction : issue, statut, note, prochaine relance.

    Tout est optionnel sauf l'identité de l'auteur : on peut poser une note sans changer de
    statut, ou reprogrammer une relance sans avoir eu quelqu'un au téléphone.
    """
    email = (email or "").strip().lower()
    if not email:
        return {"ok": False, "error": "email manquant"}
    if statut and statut not in STATUTS:
        return {"ok": False, "error": f"statut inconnu : {statut}"}

    c = _conn()
    try:
        with c:
            with c.cursor() as cur:
                autorise, motif = _peut_agir(cur, site, email, role, username)
                if not autorise:
                    return {"ok": False, "error": motif}

                _garantir_suivi(cur, site, email, _contact_id(cur, site, email))
                # Un commercial qui traite un contact du vivier se l'attribue de fait :
                # sinon il resterait « à prendre » alors que quelqu'un s'en occupe déjà.
                cur.execute("""UPDATE contact_followup
                               SET assigned_to = COALESCE(assigned_to, %s),
                                   assigned_at = COALESCE(assigned_at, now()),
                                   statut       = COALESCE(%s, statut),
                                   outcome      = COALESCE(NULLIF(%s, ''), outcome),
                                   notes        = COALESCE(NULLIF(%s, ''), notes),
                                   last_call_at = CASE WHEN %s THEN now() ELSE last_call_at END,
                                   next_action_at = CASE WHEN %s = '' THEN NULL
                                                         WHEN %s IS NULL THEN next_action_at
                                                         ELSE %s::timestamptz END,
                                   updated_at = now()
                               WHERE email = %s AND site_code = %s""",
                            [username, statut, outcome, note, est_un_appel,
                             next_action_at, next_action_at, next_action_at, email, site])

                if est_un_appel:
                    _journaliser(cur, site, email, username, "appel",
                                 outcome or note or "appel passé",
                                 {"statut": statut, "relance": next_action_at})
                elif note:
                    _journaliser(cur, site, email, username, "note", note)
                if statut:
                    _journaliser(cur, site, email, username, "statut",
                                 f"statut → {statut}", {"statut": statut})
                if next_action_at:
                    _journaliser(cur, site, email, username, "relance",
                                 f"relance programmée au {next_action_at}",
                                 {"at": next_action_at})

                cur.execute("""SELECT statut, assigned_to, next_action_at, last_call_at
                               FROM contact_followup WHERE email = %s AND site_code = %s""",
                            [email, site])
                r = cur.fetchone()
        return {"ok": True, "email": email, "statut": r[0], "assigned_to": r[1],
                "next_action_at": r[2].isoformat() if r[2] else None,
                "last_call_at": r[3].isoformat() if r[3] else None}
    finally:
        _rendre(c)


if __name__ == "__main__":
    import sys
    site = sys.argv[1] if len(sys.argv) > 1 else "lcr"
    print(json.dumps({"commerciaux": commerciaux(),
                      "apercu": lister(site, "superadmin", "camille", "tous")["compteurs"]},
                     indent=2, ensure_ascii=False))
