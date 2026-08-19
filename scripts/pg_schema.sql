-- ============================================================================
-- pg_schema.sql — Référentiel Cheffer sur PostgreSQL
-- Migration du 2026-08-19. Idempotent : rejouable sans effet de bord.
--
-- Frontière avec DuckDB : DuckDB garde l'entonnoir de scraping (scrappe_pending,
-- scrappe, scrappe_rejected, autoscrape_targets) — écrit par un seul processus, la
-- nuit, et jetable. PostgreSQL prend tout ce que l'API, les crons, les webhooks et
-- l'interface lisent et écrivent en même temps.
-- ============================================================================

-- ── Contacts ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contacts (
    id                       uuid PRIMARY KEY,
    email                    citext NOT NULL UNIQUE,
    prenom                   text,
    nom                      text,
    societe                  text,
    tel                      text,
    website                  text,
    city                     text,
    dept_code                text,
    region_code              text,
    postal_code              text,
    -- Tableau natif et non JSON : aujourd'hui le filtrage se fait en
    -- `sectors::VARCHAR LIKE '%immobilier%'`, soit un scan complet à chaque pioche.
    sectors                  text[] NOT NULL DEFAULT '{}',
    primary_source           text,
    email_score              integer,
    email_validation_reasons jsonb,
    -- La décision Mailnjoy sort du JSON : elle est dans le WHERE de chaque pioche,
    -- elle doit donc être indexable.
    mailnjoy_decision        text,
    mailnjoy_checked_at      timestamptz,
    mailnjoy_check           jsonb,
    global_blacklisted       boolean NOT NULL DEFAULT false,
    blacklist_reason         text,
    blacklisted_at           timestamptz,
    job_title                text,
    civility                 text,
    job_function             text,
    logo_url                 text,
    client_since             timestamptz,
    created_at               timestamptz NOT NULL DEFAULT now(),
    updated_at               timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_contacts_sectors     ON contacts USING gin (sectors);
CREATE INDEX IF NOT EXISTS idx_contacts_mailnjoy    ON contacts (mailnjoy_decision, mailnjoy_checked_at);
CREATE INDEX IF NOT EXISTS idx_contacts_blacklist   ON contacts (global_blacklisted) WHERE global_blacklisted;
CREATE INDEX IF NOT EXISTS idx_contacts_geo         ON contacts (dept_code, region_code);

-- ── Relation contact × site : L'ÉTAT, et rien d'autre ───────────────────────
-- L'ancienne `contact_site_history` mêlait 23 colonnes d'état ET d'événements
-- (email_sent_at, last_opened_at, emelia_clicked_at…), chacune écrasée à chaque
-- nouvel événement. L'historique était donc perdu à l'écriture. Les événements
-- partent dans `email_events`; ici ne reste que l'état.
CREATE TABLE IF NOT EXISTS contact_sites (
    id             uuid PRIMARY KEY,
    contact_id     uuid NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    site_code      text NOT NULL,
    account_id     text,
    state          text NOT NULL DEFAULT 'cold_email',
    source         text,
    added_at       timestamptz NOT NULL DEFAULT now(),
    last_action_at timestamptz,
    state_history  jsonb NOT NULL DEFAULT '[]',
    notes          text,
    UNIQUE (contact_id, site_code)
);

CREATE INDEX IF NOT EXISTS idx_contact_sites_site  ON contact_sites (site_code, state);
CREATE INDEX IF NOT EXISTS idx_contact_sites_state ON contact_sites (state);

-- ── Enrichissement data.gouv (1:1) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contact_enrichment (
    contact_id  uuid PRIMARY KEY REFERENCES contacts(id) ON DELETE CASCADE,
    excluded    boolean NOT NULL DEFAULT false,
    raw         jsonb,
    enriched_at timestamptz NOT NULL DEFAULT now()
);

-- ── Campagnes ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS campaigns (
    id                uuid PRIMARY KEY,
    site_code         text NOT NULL,
    name              text NOT NULL,
    channel           text NOT NULL,
    message_id        text,
    subject           text,
    sectors           text[] NOT NULL DEFAULT '{}',
    target_size       integer NOT NULL DEFAULT 0,
    schedule_start    date,
    cadence           jsonb NOT NULL DEFAULT '[]',
    status            text NOT NULL DEFAULT 'scheduled',
    sent_count        integer NOT NULL DEFAULT 0,
    last_dispatch_at  timestamptz,
    last_dispatch_day date,
    last_error        text,
    params            jsonb NOT NULL DEFAULT '{}',
    created_by        text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    legacy_id         text UNIQUE          -- id court DuckDB, le temps de la bascule
);

CREATE INDEX IF NOT EXISTS idx_campaigns_site ON campaigns (site_code, status);

-- ── LE JOURNAL COMPORTEMENTAL ───────────────────────────────────────────────
-- En AJOUT SEUL : une ligne par événement, jamais modifiée. C'est ce qui permet de
-- répondre à « combien d'ouvertures sur la campagne du 3 août » — impossible
-- aujourd'hui, où seule la dernière ouverture par contact est conservée.
CREATE TABLE IF NOT EXISTS email_events (
    id              bigserial PRIMARY KEY,
    occurred_at     timestamptz NOT NULL,
    -- L'email et non l'id du contact comme clé de vérité : le registre doit survivre
    -- à la purge d'un contact du pool. Sans ça, un contact supprimé puis re-scrapé
    -- repartait vierge le lendemain — c'est la boucle de renvois d'août 2026.
    email           citext NOT NULL,
    contact_id      uuid REFERENCES contacts(id) ON DELETE SET NULL,
    site_code       text NOT NULL,
    campaign_id     uuid REFERENCES campaigns(id) ON DELETE SET NULL,
    channel         text NOT NULL,
    event_type      text NOT NULL,
    url             text,
    mailbox         text,
    provider_msg_id text,
    meta            jsonb NOT NULL DEFAULT '{}',
    CONSTRAINT email_events_type_chk CHECK (event_type IN
        ('sent','delivered','open','click','bounce','complaint','unsub','reply'))
);

-- La fréquence d'envoi : « cette adresse a-t-elle reçu quelque chose récemment ? »
CREATE INDEX IF NOT EXISTS idx_events_sent      ON email_events (email, occurred_at DESC)
    WHERE event_type = 'sent';
CREATE INDEX IF NOT EXISTS idx_events_campaign  ON email_events (campaign_id, event_type, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_contact   ON email_events (contact_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_day       ON email_events (site_code, occurred_at DESC);

-- ── Boîtes d'envoi et warmup ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mailboxes (
    email        citext PRIMARY KEY,
    site_code    text NOT NULL,
    sender_name  text,
    provider     text,
    provider_id  text,
    domain       text,
    smtp_host    text,
    smtp_port    integer,
    imap_host    text,
    imap_port    integer,
    username     text,
    password_ref text,
    status       text NOT NULL DEFAULT 'active',
    daily_cap    integer NOT NULL DEFAULT 40,
    sent_today   integer NOT NULL DEFAULT 0,
    last_reset   date,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mailbox_ramp_log (
    id          bigserial PRIMARY KEY,
    mailbox     citext NOT NULL,
    day         date NOT NULL,
    old_cap     integer,
    new_cap     integer,
    reason      text,
    sent_window integer,
    err_window  integer,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- ── Segments ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS segments (
    id         uuid PRIMARY KEY,
    site_code  text NOT NULL,
    name       text NOT NULL,
    rules      jsonb NOT NULL DEFAULT '{}',
    last_count integer,
    counted_at timestamptz,
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    legacy_id  text UNIQUE
);

-- ── Vues dérivées : ce qui remplace du code défensif par du SQL ─────────────
-- La base repoussoir devient une CONSÉQUENCE du journal, plus une table à tenir à
-- jour. Les trois bugs de renvoi du 19/08/2026 n'existaient que parce que « a reçu
-- un email » était recopié à la main dans trois endroits.
CREATE OR REPLACE VIEW v_suppression AS
SELECT email,
       max(occurred_at)                        AS last_sent_at,
       max(occurred_at) + interval '120 days'  AS release_at,
       count(*)                                AS sends
FROM email_events
WHERE event_type = 'sent'
GROUP BY email;

CREATE OR REPLACE VIEW v_contact_engagement AS
SELECT contact_id,
       max(occurred_at) FILTER (WHERE event_type = 'sent')  AS last_sent_at,
       count(*)         FILTER (WHERE event_type = 'sent')  AS sends,
       count(*)         FILTER (WHERE event_type = 'open')  AS opens,
       count(*)         FILTER (WHERE event_type = 'click') AS clicks,
       max(occurred_at) FILTER (WHERE event_type = 'open')  AS last_open_at,
       max(occurred_at) FILTER (WHERE event_type = 'click') AS last_click_at
FROM email_events
WHERE contact_id IS NOT NULL
GROUP BY contact_id;
