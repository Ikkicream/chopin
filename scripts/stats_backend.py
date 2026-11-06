#!/usr/bin/env python3
"""stats_backend.py — Le comportement des destinataires, campagne par campagne.

Pourquoi une table et pas une requête. Les faits d'un envoi sont éparpillés dans
`email_events` : une ligne `sent` porte la campagne et la boîte d'expédition, les lignes
`open`/`click` qui suivent n'en portent aucune (elles arrivent par webhook, identifiées
par l'adresse seule). Les recoller à chaque affichage coûterait une jointure temporelle
sur tout le journal. `campaign_recipients` fige ce recollage : UNE ligne par envoi, avec
ce que le destinataire en a fait.

L'attribution, dite en français : une ouverture appartient au DERNIER envoi fait à cette
adresse avant elle. Si la même adresse est réenvoyée le lendemain, la fenêtre du premier
envoi se ferme au second — aucune ouverture n'est comptée deux fois.

Ce qu'on ne peut pas mesurer, et qu'on n'invente pas :
  - **Sweego en masse ne journalise aucun envoi par destinataire** (un seul appel pour
    toute la liste). Ses rebonds et ses ouvertures existent, mais sans dénominateur : on
    les compte, on ne calcule aucun taux dessus. Ils sont rendus à part, jamais fondus
    dans les taux maildoso — sinon le tableau ment.
  - Un contact supprimé du pool depuis l'envoi n'a plus de secteur ni de département. Sa
    ligne reste, ses dimensions valent « inconnu ».

Reconstruction complète à chaque fois (quelques milliers de lignes, moins d'une seconde) :
pas d'incrémental à maintenir, donc pas de dérive silencieuse.
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

# Volume minimal pour qu'un secteur ou une zone ait le droit d'être appelé « le meilleur ».
# Sous ce seuil, un seul destinataire curieux ferait un taux d'ouverture de 100 %.
MIN_VOLUME_CLASSEMENT = 20


def _pool():
    import pool_pg
    return pool_pg


SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign_recipients (
    site_code     text        NOT NULL,
    email         text        NOT NULL,
    sent_at       timestamptz NOT NULL,
    campaign_id   uuid,
    campagne      text,
    canal         text        NOT NULL DEFAULT 'inconnu',
    mailbox       text,
    contact_id    uuid,
    opened_at     timestamptz,
    open_count    int         NOT NULL DEFAULT 0,
    clicked_at    timestamptz,
    click_count   int         NOT NULL DEFAULT 0,
    bounced_at    timestamptz,
    complained_at timestamptz,
    unsub_at      timestamptz,
    type_adresse  text        NOT NULL DEFAULT 'autre',
    secteur       text,
    dept_code     text,
    region_code   text,
    PRIMARY KEY (site_code, email, sent_at)
);
CREATE INDEX IF NOT EXISTS idx_cr_sent      ON campaign_recipients (site_code, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_cr_secteur   ON campaign_recipients (site_code, secteur);
CREATE INDEX IF NOT EXISTS idx_cr_type      ON campaign_recipients (site_code, type_adresse);
CREATE INDEX IF NOT EXISTS idx_cr_campagne  ON campaign_recipients (campaign_id);

-- L'historique, jour par jour et secteur par secteur.
--
-- Pourquoi une table de plus alors que tout est déjà déductible de `campaign_recipients` :
-- parce que celle-ci est RECONSTRUITE toutes les heures en rejoignant `contacts`. Le jour
-- où un contact quitte le pool (réconciliation, purge RGPD, désinscription), son secteur
-- et son département disparaissent avec lui — et l'envoi de juin change rétroactivement de
-- secteur pour devenir « inconnu ». Un historique qui se réécrit ne permet aucune
-- comparaison dans le temps. `stats_secteur_jour` FIGE la mesure au moment où elle est
-- prise : on n'y écrase jamais un jour déjà clos, on ne complète que le jour courant.
CREATE TABLE IF NOT EXISTS stats_secteur_jour (
    site_code  text NOT NULL,
    jour       date NOT NULL,
    secteur    text NOT NULL,
    envois     int  NOT NULL DEFAULT 0,
    ouvreurs   int  NOT NULL DEFAULT 0,
    cliqueurs  int  NOT NULL DEFAULT 0,
    rebonds    int  NOT NULL DEFAULT 0,
    fige_le    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (site_code, jour, secteur)
);
CREATE INDEX IF NOT EXISTS idx_ssj_jour ON stats_secteur_jour (site_code, jour DESC);
"""

# Le jour courant bouge encore (une ouverture peut arriver ce soir), les jours passés non.
# On ne réécrit donc que la fenêtre récente — au-delà, la mesure est définitive.
FIGEAGE = """
INSERT INTO stats_secteur_jour (site_code, jour, secteur, envois, ouvreurs, cliqueurs, rebonds)
SELECT site_code, sent_at::date, secteur,
       count(*), count(opened_at), count(clicked_at), count(bounced_at)
FROM campaign_recipients
WHERE sent_at >= now() - interval '7 days'
GROUP BY site_code, sent_at::date, secteur
ON CONFLICT (site_code, jour, secteur) DO UPDATE
   SET envois = EXCLUDED.envois, ouvreurs = EXCLUDED.ouvreurs,
       cliqueurs = EXCLUDED.cliqueurs, rebonds = EXCLUDED.rebonds, fige_le = now();

-- Rattrapage : les jours plus anciens que la fenêtre qui ne sont pas encore figés (premier
-- passage, ou reprise après une panne du cron).
INSERT INTO stats_secteur_jour (site_code, jour, secteur, envois, ouvreurs, cliqueurs, rebonds)
SELECT site_code, sent_at::date, secteur,
       count(*), count(opened_at), count(clicked_at), count(bounced_at)
FROM campaign_recipients
WHERE sent_at < now() - interval '7 days'
GROUP BY site_code, sent_at::date, secteur
ON CONFLICT (site_code, jour, secteur) DO NOTHING;
"""


# ── Le type d'adresse ─────────────────────────────────────────────────────────
# Racines de « boîte de service » : `agenceannecy@`, `agence.a2pcolmar@`, `locationsud@`
# ne sont dans aucune liste noire — ce sont des boîtes d'agence, pas des personnes. Pour
# la STATISTIQUE elles comptent comme génériques.
#
# ⚠️ Ce classement n'est PAS la liste noire de `email_validator`. Celle-ci REFUSE une
# adresse à la collecte et n'agit que sur des correspondances exactes ; celui-ci se
# contente de RANGER un envoi déjà parti, et peut donc se permettre d'être plus large.
# Les confondre ferait refuser à la collecte des adresses qu'on veut seulement compter à
# part.
PREFIXES_GENERIQUES = (
    "agence", "contact", "info", "accueil", "secretariat", "cabinet", "direction",
    "gestion", "location", "transaction", "syndic", "commercial", "service", "immo",
    "boutique", "magasin", "resa", "reservation", "booking", "welcome",
)

# La fonction SQL est ENGENDRÉE depuis les listes de `email_validator` à chaque
# reconstruction : une seule source de vérité. Si Camille ajoute `devis@` à la liste noire,
# la statistique le reclasse au prochain passage sans qu'on touche à deux endroits.
def _sql_type_adresse() -> str:
    import email_validator as ev
    generiques = sorted(ev.GENERIC_INBOX)
    fonctions = sorted(ev.FORBIDDEN_LOCAL_PARTS - ev.GENERIC_INBOX)
    gabarits = sorted(ev.PLACEHOLDER_LOCALS)

    def lit(vals):
        return ", ".join("'" + v.replace("'", "''") + "'" for v in vals)

    prefixes = " OR ".join(
        "nu LIKE '" + r.replace("'", "''") + "%'" for r in PREFIXES_GENERIQUES)

    return f"""
CREATE OR REPLACE FUNCTION type_adresse(adresse text) RETURNS text AS $$
DECLARE
    local text;
    nu    text;
BEGIN
    IF adresse IS NULL OR position('@' in adresse) = 0 THEN RETURN 'autre'; END IF;
    local := lower(split_part(adresse, '@', 1));
    nu    := regexp_replace(local, '[.\\-_]', '', 'g');
    IF nu IN ({lit(gabarits)})   THEN RETURN 'gabarit'; END IF;
    IF nu IN ({lit(generiques)}) THEN RETURN 'generique'; END IF;
    -- contact2@, info75@ : même boîte générique, un chiffre en plus
    IF regexp_replace(nu, '\\d+$', '') IN ({lit(generiques)}) THEN RETURN 'generique'; END IF;
    IF nu IN ({lit(fonctions)})  THEN RETURN 'fonction'; END IF;
    -- prenom.nom / p.nom : une personne nommée, testé AVANT les racines de service
    -- (`direction.martin@` reste une boîte de service, `marie.agence@` n'existe pas)
    IF local ~ '^[a-zà-ÿ]{{2,}}[.\\-_][a-zà-ÿ]{{2,}}$'
       AND NOT ({prefixes}) THEN RETURN 'nominative'; END IF;
    IF {prefixes} THEN RETURN 'generique'; END IF;
    -- initiale.nom (a.chapuis@) : une personne aussi
    IF local ~ '^[a-zà-ÿ][.\\-_][a-zà-ÿ]{{2,}}$' THEN RETURN 'nominative'; END IF;
    RETURN 'autre';
END;
$$ LANGUAGE plpgsql IMMUTABLE;
"""


# ── Reconstruction ────────────────────────────────────────────────────────────
RECONSTRUCTION = """
TRUNCATE campaign_recipients;

-- Les lignes fantômes de la migration, écartées à la lecture.
--
-- La bascule vers PostgreSQL a rejoué 405 envois maildoso déjà journalisés, sous le canal
-- `inconnu` et sans campagne. Purgés du journal le 2026-08-21
-- (`scripts/purge_doublons_journal.py`) ; ce filtre reste en place comme garde-fou, au cas
-- où une réimportation en referait.
--
-- Il ne collapse QUE cette signature — canal inconnu, issu de la reprise, avec un jumeau
-- le même jour sur un canal connu. Deux envois réels le même jour à la même adresse (deux
-- campagnes dispatchées le même matin : 7 cas en juillet-août) restent DEUX envois : les
-- fondre en un seul effacerait de la statistique un email que la personne a bel et bien
-- reçu.
WITH envois AS (
    SELECT e.occurred_at AS sent_at,
           lower(e.email::text) AS email,
           e.site_code, e.contact_id, e.campaign_id,
           COALESCE(e.channel, 'inconnu') AS canal,
           e.mailbox,
           lead(e.occurred_at) OVER (PARTITION BY e.site_code, lower(e.email::text)
                                     ORDER BY e.occurred_at) AS fin_fenetre
    FROM email_events e
    WHERE e.event_type = 'sent'
      AND NOT (e.channel = 'inconnu'
               AND e.meta->>'source' = 'contact_site_history'
               AND EXISTS (SELECT 1 FROM email_events m
                           WHERE m.event_type = 'sent' AND m.channel <> 'inconnu'
                             AND m.email = e.email AND m.site_code = e.site_code
                             AND m.occurred_at::date = e.occurred_at::date))
),
reactions AS (
    SELECT v.site_code, v.email, v.sent_at,
           min(r.occurred_at) FILTER (WHERE r.event_type = 'open')      AS opened_at,
           count(*)           FILTER (WHERE r.event_type = 'open')      AS open_count,
           min(r.occurred_at) FILTER (WHERE r.event_type = 'click')     AS clicked_at,
           count(*)           FILTER (WHERE r.event_type = 'click')     AS click_count,
           min(r.occurred_at) FILTER (WHERE r.event_type = 'bounce')    AS bounced_at,
           min(r.occurred_at) FILTER (WHERE r.event_type = 'complaint') AS complained_at,
           min(r.occurred_at) FILTER (WHERE r.event_type = 'unsub')     AS unsub_at
    FROM envois v
    LEFT JOIN email_events r
           ON lower(r.email::text) = v.email
          AND r.site_code = v.site_code
          AND r.event_type <> 'sent'
          AND r.occurred_at >= v.sent_at
          AND (v.fin_fenetre IS NULL OR r.occurred_at < v.fin_fenetre)
    GROUP BY v.site_code, v.email, v.sent_at
)
INSERT INTO campaign_recipients (
    site_code, email, sent_at, campaign_id, campagne, canal, mailbox, contact_id,
    opened_at, open_count, clicked_at, click_count, bounced_at, complained_at, unsub_at,
    type_adresse, secteur, dept_code, region_code)
SELECT DISTINCT ON (v.site_code, v.email, v.sent_at)
       v.site_code, v.email, v.sent_at, v.campaign_id, c.name, v.canal, v.mailbox,
       v.contact_id,
       x.opened_at, COALESCE(x.open_count, 0), x.clicked_at, COALESCE(x.click_count, 0),
       x.bounced_at, x.complained_at, x.unsub_at,
       type_adresse(v.email),
       COALESCE(ct.sectors[1], 'inconnu'),
       COALESCE(ct.dept_code, 'inconnu'),
       COALESCE(ct.region_code, 'inconnu')
FROM envois v
LEFT JOIN reactions x ON x.site_code = v.site_code AND x.email = v.email
                      AND x.sent_at = v.sent_at
LEFT JOIN campaigns c ON c.id = v.campaign_id
LEFT JOIN contacts  ct ON ct.id = v.contact_id
                       OR (v.contact_id IS NULL AND ct.email::text = v.email)
ORDER BY v.site_code, v.email, v.sent_at, ct.updated_at DESC NULLS LAST;
"""


def reconstruire() -> dict:
    """Rebâtit `campaign_recipients` depuis le journal. Idempotent."""
    p = _pool()
    c = p._conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute(SCHEMA)
                cur.execute(_sql_type_adresse())
                cur.execute(RECONSTRUCTION)
                cur.execute(FIGEAGE)
                cur.execute("SELECT count(*) FROM campaign_recipients")
                n = cur.fetchone()[0]
                cur.execute("""SELECT count(*) FROM email_events
                               WHERE event_type <> 'sent'""")
                evts = cur.fetchone()[0]
                cur.execute("""SELECT count(*) FROM email_events e
                               WHERE e.event_type <> 'sent' AND NOT EXISTS (
                                 SELECT 1 FROM campaign_recipients r
                                 WHERE r.email = lower(e.email::text)
                                   AND r.site_code = e.site_code
                                   AND e.occurred_at >= r.sent_at)""")
                orphelins = cur.fetchone()[0]
    finally:
        p._rendre(c)
    promus = _affiner_nominatives()
    # Stéphane observe ce que la reconstruction vient de rendre mesurable. Sa mémoire suit
    # donc exactement le même rythme que les statistiques — jamais en retard sur elles.
    try:
        import stephane
        stephane.observer("lcr")
    except Exception:  # noqa: BLE001 — l'agent ne doit pas casser la statistique
        pass
    p2 = _pool()
    jours_figes = p2._q("SELECT count(*) FROM stats_secteur_jour")[0][0]
    return {"ok": True, "envois": n, "evenements": evts, "orphelins": orphelins,
            "nominatives_reconnues": promus, "lignes_historique": jours_figes}


def _affiner_nominatives() -> int:
    """`adrien@immolim.com` n'a ni point ni tiret : SQL ne peut pas savoir que c'est un
    prénom. Le dictionnaire de `name_extract`, lui, le sait. On repasse donc sur les seules
    lignes classées « autre » — quelques centaines — et on promeut celles qui portent un
    prénom reconnu."""
    import name_extract as ne
    p = _pool()
    c = p._conn()
    promus = 0
    try:
        with c:
            with c.cursor() as cur:
                cur.execute("SELECT DISTINCT email FROM campaign_recipients "
                            "WHERE type_adresse = 'autre'")
                a_promouvoir = [(e,) for (e,) in cur.fetchall()
                                if (ne.extraire(e) or {}).get("prenom")]
                if a_promouvoir:
                    cur.executemany("UPDATE campaign_recipients SET type_adresse = "
                                    "'nominative' WHERE email = %s", a_promouvoir)
                    promus = len(a_promouvoir)
    finally:
        p._rendre(c)
    return promus


# ── Agrégations ───────────────────────────────────────────────────────────────
# Une seule expression de mesure, réutilisée partout : ouvreurs UNIQUES sur envois. On
# compte les personnes, pas les ouvertures — un destinataire qui rouvre dix fois le même
# email ne vaut pas dix ouvreurs, et les proxys antispam en ouvrent beaucoup.
MESURES = """
    count(*)                                                        AS envois,
    count(opened_at)                                                AS ouvreurs,
    count(clicked_at)                                               AS cliqueurs,
    count(bounced_at)                                               AS rebonds,
    count(complained_at)                                            AS plaintes,
    round(100.0 * count(opened_at)  / NULLIF(count(*), 0), 1)::float8 AS taux_ouverture,
    round(100.0 * count(clicked_at) / NULLIF(count(*), 0), 1)::float8 AS taux_clic,
    round(100.0 * count(bounced_at) / NULLIF(count(*), 0), 1)::float8 AS taux_rebond
"""

_COLONNES = ["envois", "ouvreurs", "cliqueurs", "rebonds", "plaintes",
             "taux_ouverture", "taux_clic", "taux_rebond"]


def _lignes(sql: str, params: tuple, cle: str) -> list[dict]:
    p = _pool()
    out = []
    for r in p._q(sql, params):
        d = {cle: r[0]}
        d.update(dict(zip(_COLONNES, r[1:])))
        out.append(d)
    return out


def _filtre(site: str, jours: int | None) -> tuple[str, tuple]:
    where = "WHERE site_code = %s"
    params: tuple = (site,)
    if jours:
        where += " AND sent_at >= now() - (%s || ' days')::interval"
        params = (site, str(jours))
    return where, params


def resume(site: str = "lcr", jours: int | None = None) -> dict:
    where, params = _filtre(site, jours)
    p = _pool()
    r = p._q(f"SELECT {MESURES} FROM campaign_recipients {where}", params)[0]
    d = dict(zip(_COLONNES, r))
    d["campagnes"] = p._q(
        f"SELECT count(DISTINCT COALESCE(campagne, 'sans campagne')) "
        f"FROM campaign_recipients {where}", params)[0][0]
    d["periode"] = p._q(
        f"SELECT min(sent_at)::date::text, max(sent_at)::date::text "
        f"FROM campaign_recipients {where}", params)[0]
    return d


def par_canal(site: str = "lcr", jours: int | None = None) -> list[dict]:
    where, params = _filtre(site, jours)
    return _lignes(f"SELECT canal, {MESURES} FROM campaign_recipients {where} "
                   f"GROUP BY canal ORDER BY envois DESC", params, "canal")


def par_type_adresse(site: str = "lcr", jours: int | None = None) -> list[dict]:
    where, params = _filtre(site, jours)
    return _lignes(f"SELECT type_adresse, {MESURES} FROM campaign_recipients {where} "
                   f"GROUP BY type_adresse ORDER BY envois DESC", params, "type")


def par_secteur(site: str = "lcr", jours: int | None = None, limite: int = 10) -> list[dict]:
    where, params = _filtre(site, jours)
    return _lignes(f"SELECT secteur, {MESURES} FROM campaign_recipients {where} "
                   f"GROUP BY secteur ORDER BY envois DESC LIMIT {int(limite)}",
                   params, "secteur")


def par_zone(site: str = "lcr", jours: int | None = None, limite: int = 10) -> list[dict]:
    where, params = _filtre(site, jours)
    lignes = _lignes(f"SELECT dept_code, {MESURES} FROM campaign_recipients {where} "
                     f"GROUP BY dept_code ORDER BY envois DESC LIMIT {int(limite)}",
                     params, "dept")
    return [dict(l, libelle=_nom_dept(l["dept"])) for l in lignes]


def par_campagne(site: str = "lcr", jours: int | None = None, limite: int = 10) -> list[dict]:
    where, params = _filtre(site, jours)
    return _lignes(f"SELECT COALESCE(campagne, 'sans campagne'), {MESURES} "
                   f"FROM campaign_recipients {where} GROUP BY 1 "
                   f"ORDER BY envois DESC LIMIT {int(limite)}", params, "campagne")


def comparaison_secteurs(site: str = "lcr", jours: int | None = None) -> list[dict]:
    """TOUS les secteurs, sollicités ou non — la table d'analyse sectorielle.

    Le tableau « par secteur » ne montre que ce qui est parti. Il ne peut donc pas répondre
    à la question qui vient juste après : **quels secteurs dorment en base sans qu'on leur
    ait jamais écrit ?** Aujourd'hui la réponse est « tous sauf l'immobilier » — 1 706 des
    1 712 envois. C'est précisément ce qu'il faut voir pour décider quoi tester ensuite.

    Chaque ligne porte donc trois choses qui ne viennent pas du même endroit :
      - `rang` : ce que la politique des secteurs dit d'en faire (prioritaire/secondaire) ;
      - `contacts_ok` : ce qui est disponible en base, donc envoyable demain ;
      - `recul` : ce que la mesure vaut. « suffisant » au-delà du volume minimal,
        « à confirmer » en dessous, « jamais sollicité » à zéro envoi. Sans cette colonne,
        un secteur à 4 envois et 2 ouvertures afficherait 50 % et passerait pour le
        meilleur de tous.
    """
    p = _pool()
    where, params = _filtre(site, jours)
    envois = {r[0]: r for r in p._q(f"""
        SELECT secteur, count(*), count(opened_at), count(clicked_at), count(bounced_at),
               round(100.0 * count(opened_at)  / NULLIF(count(*), 0), 1)::float8,
               round(100.0 * count(clicked_at) / NULLIF(count(*), 0), 1)::float8,
               max(sent_at)::date::text
        FROM campaign_recipients {where} GROUP BY secteur""", params)}

    dispo = {r[0]: r[1] for r in p._q("""
        SELECT COALESCE(sectors[1], 'inconnu'), count(*) FROM contacts
        WHERE etat = 'ok' GROUP BY 1""")}

    rangs: dict[str, str] = {}
    catalogue: dict[str, str] = {}
    try:
        import secteurs_backend as sb
        pol = sb.politique(site)
        for rang in sb.RANGS:
            for code in (pol.get(rang) or []):
                rangs[code] = rang
        catalogue = {c: f.get("label", c) for c, f in sb.CATALOGUE.items()}
    except Exception:  # noqa: BLE001 — la politique est un ornement ici, pas la donnée
        pass

    connus = set(envois) | set(dispo) | set(catalogue)
    out = []
    for code in connus:
        e = envois.get(code)
        n = e[1] if e else 0
        out.append({
            "secteur": code,
            "libelle": catalogue.get(code, code),
            "rang": rangs.get(code, "non classé"),
            "contacts_ok": dispo.get(code, 0),
            "envois": n,
            "ouvreurs": e[2] if e else 0,
            "cliqueurs": e[3] if e else 0,
            "rebonds": e[4] if e else 0,
            "taux_ouverture": e[5] if e else None,
            "taux_clic": e[6] if e else None,
            "dernier_envoi": e[7] if e else None,
            "recul": ("suffisant" if n >= MIN_VOLUME_CLASSEMENT
                      else "jamais sollicité" if n == 0 else "à confirmer"),
        })
    # Les secteurs mesurés d'abord (par taux), puis les dormants (par volume disponible) :
    # les deux moitiés du tableau ne répondent pas à la même question.
    out.sort(key=lambda l: (l["envois"] == 0, -(l["taux_ouverture"] or 0), -l["contacts_ok"]))
    return out


def par_secteur_zone(site: str = "lcr", jours: int | None = None,
                     minimum: int = 5) -> list[dict]:
    """Le croisement secteur × département : où un secteur donné répond-il le mieux ?

    Filtré au volume minimal dès la source — un croisement produit beaucoup de cases à un
    ou deux envois, qui n'apprennent rien et noieraient les vraies.
    """
    where, params = _filtre(site, jours)
    p = _pool()
    lignes = p._q(f"""
        SELECT secteur, dept_code, count(*), count(opened_at), count(clicked_at),
               round(100.0 * count(opened_at) / NULLIF(count(*), 0), 1)::float8
        FROM campaign_recipients {where}
        GROUP BY secteur, dept_code HAVING count(*) >= {int(minimum)}
        ORDER BY count(*) DESC""", params)
    return [{"secteur": r[0], "dept": r[1], "libelle": _nom_dept(r[1]), "envois": r[2],
             "ouvreurs": r[3], "cliqueurs": r[4], "taux_ouverture": r[5]} for r in lignes]


def evolution_secteur(site: str = "lcr", jours: int = 90) -> list[dict]:
    """La série jour par jour, lue dans l'historique FIGÉ — pas dans la table reconstruite.

    C'est tout l'intérêt de `stats_secteur_jour` : un contact sorti du pool depuis n'efface
    pas rétroactivement le secteur de l'envoi de juin.
    """
    p = _pool()
    lignes = p._q("""
        SELECT jour::text, secteur, envois, ouvreurs, cliqueurs
        FROM stats_secteur_jour
        WHERE site_code = %s AND jour >= current_date - (%s || ' days')::interval
        ORDER BY jour, secteur""", (site, str(jours)))
    return [{"jour": r[0], "secteur": r[1], "envois": r[2], "ouvreurs": r[3],
             "cliqueurs": r[4]} for r in lignes]


def _nom_dept(code: str) -> str:
    if not code or code == "inconnu":
        return "Département inconnu"
    try:
        import workflow_geo as wg
        for d in wg.list_departments():
            if d["code"] == code:
                return f"{code} {d['name']}"
    except Exception:  # noqa: BLE001
        pass
    return code


def extremes(site: str = "lcr", jours: int | None = None,
             minimum: int = MIN_VOLUME_CLASSEMENT) -> dict:
    """Le meilleur et le pire, par secteur et par zone — la carte du haut de page.

    Deux garde-fous. D'abord un volume minimal : un secteur à 3 envois dont 1 ouverture
    afficherait 33 % et écraserait tout le reste. Ensuite, si AUCUN groupe n'atteint ce
    volume, on ne désigne personne — mieux vaut une carte qui dit « pas encore assez de
    recul » qu'un classement tiré de trois emails.
    """
    def palmares(lignes: list[dict], cle: str) -> dict:
        eligibles = [l for l in lignes if l["envois"] >= minimum and l[cle] != "inconnu"]
        if not eligibles:
            return {"meilleur": None, "pire": None, "eligibles": 0,
                    "motif": f"aucun groupe n'atteint {minimum} envois"}
        classe = sorted(eligibles, key=lambda l: (l["taux_ouverture"] or 0, l["taux_clic"] or 0))
        if len(classe) == 1:
            # Un seul groupe au-dessus du seuil : il n'est ni le meilleur ni le pire, il
            # est le seul. Le désigner comme les deux à la fois n'apprendrait rien.
            return {"meilleur": classe[0], "pire": None, "eligibles": 1,
                    "motif": "un seul groupe atteint le volume minimal — pas de comparaison possible"}
        return {"meilleur": classe[-1], "pire": classe[0], "eligibles": len(eligibles),
                "motif": None}

    return {"secteur": palmares(par_secteur(site, jours, limite=100), "secteur"),
            "zone": palmares(par_zone(site, jours, limite=100), "dept"),
            "minimum": minimum}


def tableau_de_bord(site: str = "lcr", jours: int | None = None,
                    limite: int = 10) -> dict:
    """Tout ce qu'affiche la page, en un seul aller-retour."""
    return {
        "site": site, "jours": jours,
        "resume": resume(site, jours),
        "extremes": extremes(site, jours),
        "canaux": par_canal(site, jours),
        "types_adresse": par_type_adresse(site, jours),
        "secteurs": par_secteur(site, jours, limite),
        "zones": par_zone(site, jours, limite),
        "campagnes": par_campagne(site, jours, limite),
        "comparaison_secteurs": comparaison_secteurs(site, jours),
        "secteur_zone": par_secteur_zone(site, jours),
        "evolution": evolution_secteur(site, jours or 90),
        "angles_morts": angles_morts(site),
    }


def angles_morts(site: str = "lcr") -> dict:
    """Ce que la page ne peut PAS mesurer, affiché sur la page elle-même.

    Sweego envoie en masse : un seul appel pour toute la liste, donc aucun envoi
    journalisé par destinataire. Ses rebonds et ses ouvertures existent bel et bien, mais
    sans dénominateur — les fondre dans les taux ci-dessus donnerait un taux d'ouverture
    calculé sur des envois qu'on n'a jamais comptés. On les sort donc à part.
    """
    p = _pool()
    orphelins = p._q("""
        SELECT COALESCE(e.channel, 'inconnu'), e.event_type, count(*)
        FROM email_events e
        WHERE e.site_code = %s AND e.event_type <> 'sent'
          AND NOT EXISTS (SELECT 1 FROM campaign_recipients r
                          WHERE r.email = lower(e.email::text)
                            AND r.site_code = e.site_code
                            AND e.occurred_at >= r.sent_at)
        GROUP BY 1, 2 ORDER BY 3 DESC
    """, (site,))
    return {
        "evenements_sans_envoi": [
            {"canal": c, "type": t, "nombre": n} for c, t, n in orphelins],
        "explication": ("Événements reçus pour des adresses dont l'envoi n'a jamais été "
                        "journalisé par destinataire — envois de masse Sweego pour "
                        "l'essentiel. Comptés ici, exclus des taux."),
    }


if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser(description="Statistiques d'engagement")
    ap.add_argument("commande", choices=["reconstruire", "tableau"], nargs="?",
                    default="tableau")
    ap.add_argument("--site", default="lcr")
    ap.add_argument("--jours", type=int, default=None)
    a = ap.parse_args()
    if a.commande == "reconstruire":
        print(json.dumps(reconstruire(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(tableau_de_bord(a.site, a.jours), ensure_ascii=False,
                         indent=2, default=str))


def engagement_par_campagne(site: str = "lcr") -> dict:
    """{campaign_id: engagement} — pour enrichir la liste des campagnes.

    Le tableau des campagnes affichait ce qui était PARTI (envoyé / cible) sans jamais dire
    ce que ça avait donné. Deux campagnes à 100 % d'envoi n'ont pourtant rien à voir si
    l'une ouvre à 35 % et l'autre à 5 %.

    Indexé sur DEUX clés : l'uuid PostgreSQL et l'identifiant court hérité de DuckDB
    (`legacy_id`, ex. `fd0dc221-b44`). Motif : `campaign_recipients` porte l'uuid, mais
    `list_campaigns` — qui alimente le tableau — rend l'identifiant court. Sans les deux,
    la jointure tombe à vide et toutes les colonnes affichent un tiret.
    """
    p = _pool()
    try:
        lignes = p._q("""
            SELECT r.campaign_id::text, c.legacy_id, count(*), count(r.opened_at),
                   count(r.clicked_at),
                   round(100.0 * count(r.opened_at)  / NULLIF(count(*), 0), 1)::float8,
                   round(100.0 * count(r.clicked_at) / NULLIF(count(*), 0), 1)::float8
            FROM campaign_recipients r
            LEFT JOIN campaigns c ON c.id = r.campaign_id
            WHERE r.site_code = %s AND r.campaign_id IS NOT NULL
            GROUP BY r.campaign_id, c.legacy_id""", (site,))
    except Exception:  # noqa: BLE001 — table absente : la liste des campagnes doit vivre sans
        return {}
    out: dict = {}
    for uuid, legacy, n, ouv, clics, tx_o, tx_c in lignes:
        mesure = {"journalises": n, "ouvreurs": ouv, "cliqueurs": clics,
                  "taux_ouverture": tx_o, "taux_clic": tx_c}
        for cle in (uuid, legacy):
            if cle:
                out[cle] = mesure
    return out
