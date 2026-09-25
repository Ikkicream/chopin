-- ============================================================================
--  Mass Mailing — schéma PostgreSQL
--
--  Tout vit dans le schéma `mass_mailing`, jamais dans `public` : le module est
--  indépendant jusque dans la base. Aucune de ces tables ne doit être jointe aux
--  tables Cheffer (`public.campaigns`, `public.email_events`…) — ce sont deux
--  métiers différents, deux canaux différents, deux réputations différentes.
--
--  Conventions :
--   - identifiants en UUID, générés côté base ;
--   - horodatages en `timestamptz`, toujours UTC ;
--   - statuts en texte contraint plutôt qu'en ENUM natif : un CHECK se modifie
--     par un simple ALTER, un type ENUM PostgreSQL non ;
--   - l'email est stocké normalisé ET haché : les recherches et les suppressions
--     passent par le hash, le clair n'est lu que pour l'envoi.
--
--  Idempotent : ce fichier peut être rejoué sans rien casser.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS mass_mailing;
SET search_path TO mass_mailing, public;

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid(), digest()


-- ── Profils expéditeur ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sender_profiles (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    TEXT        NOT NULL,
    from_name               TEXT        NOT NULL,
    from_email              TEXT        NOT NULL,
    reply_to                TEXT,
    sending_domain          TEXT        NOT NULL,
    sweego_configuration    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    tracking_settings       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    unsubscribe_settings    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    -- Renseigné par le contrôle DNS, jamais saisi à la main : un domaine qu'on
    -- DÉCLARE authentifié sans l'avoir vérifié est pire que pas de contrôle.
    verified_status         TEXT        NOT NULL DEFAULT 'unknown'
                            CHECK (verified_status IN ('unknown','verified','warning','failed')),
    spf_ok                  BOOLEAN,
    dkim_ok                 BOOLEAN,
    dmarc_ok                BOOLEAN,
    verified_at             TIMESTAMPTZ,
    is_default              BOOLEAN     NOT NULL DEFAULT FALSE,
    active                  BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Un seul profil par défaut, garanti par la base et non par le code applicatif.
CREATE UNIQUE INDEX IF NOT EXISTS sender_profiles_un_seul_defaut
    ON sender_profiles ((is_default)) WHERE is_default;


-- ── Campagnes ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS campaigns (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    internal_name           TEXT        NOT NULL,
    status                  TEXT        NOT NULL DEFAULT 'draft'
                            CHECK (status IN ('draft','ready_for_validation','validating_list',
                                              'validation_issue','ready_to_schedule','scheduled',
                                              'sending','paused','completed','completed_with_warnings',
                                              'failed','cancelled','archived')),
    subject                 TEXT,
    preheader               TEXT,

    html_storage_key        TEXT,          -- chemin du fichier HTML privé
    html_hash               TEXT,          -- empreinte : dit si le message a changé
    text_content            TEXT,
    message_version         INT         NOT NULL DEFAULT 1,

    sender_profile_id       UUID        REFERENCES sender_profiles(id) ON DELETE RESTRICT,
    target_version_id       UUID,          -- FK posée plus bas (dépendance circulaire)
    target_version          INT         NOT NULL DEFAULT 0,

    scheduled_at            TIMESTAMPTZ,
    started_at              TIMESTAMPTZ,
    completed_at            TIMESTAMPTZ,
    paused_at               TIMESTAMPTZ,
    cancellation_reason     TEXT,

    -- Instantanés pris au passage en `sending`, jamais relus depuis la config
    -- vivante : une campagne partie doit pouvoir dire ce qui était vrai AU MOMENT
    -- du départ, même si les réglages ont changé depuis.
    compliance_snapshot     JSONB,
    preflight_snapshot      JSONB,
    provider_config_snapshot JSONB,
    stats_snapshot          JSONB       NOT NULL DEFAULT '{}'::jsonb,

    created_by              TEXT        NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS campaigns_statut_idx   ON campaigns (status, created_at DESC);
CREATE INDEX IF NOT EXISTS campaigns_planif_idx   ON campaigns (scheduled_at)
    WHERE status IN ('scheduled','sending');
CREATE INDEX IF NOT EXISTS campaigns_nom_idx      ON campaigns (lower(internal_name));
-- `progressive` : chaque lot validé part sans attendre les autres (défaut).
-- `after_validation` : on attend toute la validation, comme dans la spec d'origine.
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS dispatch_mode TEXT NOT NULL DEFAULT 'progressive';
ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS campaigns_dispatch_mode_check;
ALTER TABLE campaigns ADD CONSTRAINT campaigns_dispatch_mode_check
    CHECK (dispatch_mode IN ('progressive','after_validation'));


-- ── Versions de cible (un CSV importé = une version figée) ───────────────────
CREATE TABLE IF NOT EXISTS campaign_target_versions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id             UUID        NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    version                 INT         NOT NULL,

    original_filename       TEXT        NOT NULL,
    file_hash               TEXT        NOT NULL,
    storage_key             TEXT        NOT NULL,
    file_size_bytes         BIGINT,
    encoding                TEXT,
    delimiter               TEXT,
    first_column_name       TEXT,
    header_detected         BOOLEAN,

    total_rows              INT         NOT NULL DEFAULT 0,
    extracted_rows          INT         NOT NULL DEFAULT 0,
    unique_emails           INT         NOT NULL DEFAULT 0,
    empty_rows              INT         NOT NULL DEFAULT 0,
    invalid_syntax_count    INT         NOT NULL DEFAULT 0,
    duplicate_count         INT         NOT NULL DEFAULT 0,
    suppression_count       INT         NOT NULL DEFAULT 0,
    validation_eligible_count INT       NOT NULL DEFAULT 0,

    -- Une version figée ne se modifie plus : toute nouvelle cible crée une
    -- version suivante. C'est ce qui rend l'audit possible après coup.
    frozen_at               TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (campaign_id, version)
);
CREATE INDEX IF NOT EXISTS ctv_campagne_idx ON campaign_target_versions (campaign_id, version DESC);
-- Ce que l'analyse a vu et décidé : aperçu, certitude de l'en-tête, échantillon
-- d'erreurs (adresses MASQUÉES). C'est ce qu'affiche l'écran « Résumé de cible ».
ALTER TABLE campaign_target_versions ADD COLUMN IF NOT EXISTS analysis_report JSONB;
-- La décision d'en-tête a-t-elle été imposée par le superadmin (correction
-- explicite) ou devinée ? Une devinette fausse coûte une ligne ; une correction
-- ignorée coûte la confiance dans l'écran.
ALTER TABLE campaign_target_versions ADD COLUMN IF NOT EXISTS header_forced BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS campaigns_target_version_fk;
ALTER TABLE campaigns ADD CONSTRAINT campaigns_target_version_fk
    FOREIGN KEY (target_version_id) REFERENCES campaign_target_versions(id) ON DELETE SET NULL;


-- ── Destinataires ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS recipients (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    target_version_id       UUID        NOT NULL REFERENCES campaign_target_versions(id) ON DELETE CASCADE,
    campaign_id             UUID        NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,

    email_normalized        TEXT        NOT NULL,
    email_hash              TEXT        NOT NULL,
    original_row_number     INT,

    import_status           TEXT        NOT NULL DEFAULT 'imported'
                            CHECK (import_status IN ('imported','duplicate','invalid_syntax','empty')),
    validation_status       TEXT        NOT NULL DEFAULT 'pending'
                            CHECK (validation_status IN ('pending','valid','risky','invalid',
                                                         'unknown','disposable','role','error')),
    validation_provider_status TEXT,      -- le statut BRUT du fournisseur, jamais réécrit
    validation_reason       TEXT,
    validated_at            TIMESTAMPTZ,

    eligibility_status      TEXT        NOT NULL DEFAULT 'pending'
                            CHECK (eligibility_status IN ('pending','eligible','excluded')),
    eligibility_reason      TEXT,
    suppression_status      TEXT,

    send_status             TEXT        NOT NULL DEFAULT 'pending'
                            CHECK (send_status IN ('pending','queued','submitted','delivered',
                                                   'bounced','rejected','failed','skipped')),
    sending_batch_id        UUID,
    sweego_message_id       TEXT,
    submitted_at            TIMESTAMPTZ,
    delivered_at            TIMESTAMPTZ,
    opened_at               TIMESTAMPTZ,
    clicked_at              TIMESTAMPTZ,
    bounced_at              TIMESTAMPTZ,
    bounce_type             TEXT,
    complained_at           TIMESTAMPTZ,
    unsubscribed_at         TIMESTAMPTZ,
    provider_raw_metadata   JSONB,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Un même email ne peut figurer qu'une fois dans une version de cible : la
-- déduplication est garantie par la base, pas seulement par le job d'import.
CREATE UNIQUE INDEX IF NOT EXISTS recipients_unicite
    ON recipients (target_version_id, email_hash);
CREATE INDEX IF NOT EXISTS recipients_a_valider
    ON recipients (target_version_id) WHERE validation_status = 'pending';
CREATE INDEX IF NOT EXISTS recipients_a_envoyer
    ON recipients (campaign_id) WHERE eligibility_status = 'eligible' AND send_status = 'pending';
CREATE INDEX IF NOT EXISTS recipients_hash_idx   ON recipients (email_hash);
CREATE INDEX IF NOT EXISTS recipients_lot_idx    ON recipients (sending_batch_id);
ALTER TABLE recipients ADD COLUMN IF NOT EXISTS validation_batch_id UUID;
CREATE INDEX IF NOT EXISTS recipients_lot_validation_idx ON recipients (validation_batch_id);


-- ── Lots de validation Mailnjoy ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS validation_batches (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id             UUID        NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    target_version_id       UUID        NOT NULL REFERENCES campaign_target_versions(id) ON DELETE CASCADE,
    provider                TEXT        NOT NULL DEFAULT 'mailnjoy',
    sequence_number         INT         NOT NULL,
    total_recipients        INT         NOT NULL,
    processed_count         INT         NOT NULL DEFAULT 0,
    status                  TEXT        NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','running','completed','failed','cancelled')),
    external_reference      TEXT,
    attempts                INT         NOT NULL DEFAULT 0,
    submitted_at            TIMESTAMPTZ,
    completed_at            TIMESTAMPTZ,
    error_code              TEXT,
    error_message           TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (target_version_id, sequence_number)
);
CREATE INDEX IF NOT EXISTS vb_a_traiter ON validation_batches (campaign_id, status);
-- Compteurs d'issue du lot, écrits à la finalisation : la fiche campagne les
-- additionne au lieu de recompter 100 000 destinataires à chaque affichage.
ALTER TABLE validation_batches ADD COLUMN IF NOT EXISTS eligible_count INT NOT NULL DEFAULT 0;
ALTER TABLE validation_batches ADD COLUMN IF NOT EXISTS excluded_count INT NOT NULL DEFAULT 0;
ALTER TABLE validation_batches ADD COLUMN IF NOT EXISTS decisions JSONB;
ALTER TABLE validation_batches ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;


-- ── Lots d'envoi Sweego ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sending_batches (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id             UUID        NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    sequence_number         INT         NOT NULL,
    recipients_count        INT         NOT NULL,
    status                  TEXT        NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','scheduled','dispatching','completed',
                                              'failed','cancelled','skipped')),
    scheduled_for           TIMESTAMPTZ,
    dispatched_at           TIMESTAMPTZ,
    completed_at            TIMESTAMPTZ,
    external_reference      TEXT,
    attempts                INT         NOT NULL DEFAULT 0,
    accepted_count          INT         NOT NULL DEFAULT 0,
    rejected_count          INT         NOT NULL DEFAULT 0,
    rate_limit_snapshot     JSONB,
    error_code              TEXT,
    error_message           TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (campaign_id, sequence_number)
);
CREATE INDEX IF NOT EXISTS sb_a_partir ON sending_batches (status, scheduled_for)
    WHERE status IN ('pending','scheduled');
-- Envoi au fil de la validation (Camille, 2026-09-25) : un lot validé donne
-- UN lot d'envoi, sans attendre les autres. Le lien est 1-pour-1 et unique :
-- finaliser deux fois le même lot ne peut pas créer deux envois.
ALTER TABLE sending_batches ADD COLUMN IF NOT EXISTS validation_batch_id UUID
    REFERENCES validation_batches(id) ON DELETE CASCADE;
CREATE UNIQUE INDEX IF NOT EXISTS sb_un_envoi_par_lot
    ON sending_batches (validation_batch_id) WHERE validation_batch_id IS NOT NULL;


-- ── Liste de suppression ─────────────────────────────────────────────────────
-- Appliquée AVANT CHAQUE LOT, pas seulement à l'import : entre l'import et le
-- départ d'un lot il peut s'écouler des heures, et une désinscription arrivée
-- entre-temps doit être respectée.
CREATE TABLE IF NOT EXISTS suppressions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_hash              TEXT        NOT NULL,
    email_normalized        TEXT,
    reason                  TEXT        NOT NULL
                            CHECK (reason IN ('unsubscribe','hard_bounce','complaint',
                                              'manual','import','provider')),
    source                  TEXT        NOT NULL,
    scope                   TEXT        NOT NULL DEFAULT 'global'
                            CHECK (scope IN ('global','sender_profile','campaign')),
    scope_id                UUID,
    occurred_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata                JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS suppressions_unicite
    ON suppressions (email_hash, scope, COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid));
CREATE INDEX IF NOT EXISTS suppressions_hash_idx ON suppressions (email_hash);


-- ── Journal d'audit ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS campaign_events (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    campaign_id             UUID        REFERENCES campaigns(id) ON DELETE CASCADE,
    actor_type              TEXT        NOT NULL
                            CHECK (actor_type IN ('user','worker','webhook','system')),
    actor_id                TEXT,
    event_type              TEXT        NOT NULL,
    summary                 TEXT,
    payload                 JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS campaign_events_idx ON campaign_events (campaign_id, created_at DESC);


-- ── File de jobs (choix (a) : PostgreSQL, pas de Redis) ──────────────────────
-- Le verrou de concurrence est `FOR UPDATE SKIP LOCKED` : plusieurs workers
-- peuvent dépiler la même table sans jamais traiter deux fois la même ligne.
-- C'est ce qui remplace BullMQ, sans ajouter d'infrastructure.
CREATE TABLE IF NOT EXISTS jobs (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_type                TEXT        NOT NULL,
    campaign_id             UUID        REFERENCES campaigns(id) ON DELETE CASCADE,
    payload                 JSONB       NOT NULL DEFAULT '{}'::jsonb,
    -- Deux jobs de même clé ne coexistent jamais : c'est l'idempotence exigée
    -- par la spec, garantie par un index plutôt que par la prudence du code.
    idempotency_key         TEXT,
    status                  TEXT        NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','running','completed','failed','dead')),
    priority                INT         NOT NULL DEFAULT 100,
    attempts                INT         NOT NULL DEFAULT 0,
    max_attempts            INT         NOT NULL DEFAULT 5,
    run_after               TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_at               TIMESTAMPTZ,
    locked_by               TEXT,
    started_at              TIMESTAMPTZ,
    finished_at             TIMESTAMPTZ,
    last_error              TEXT,
    result                  JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS jobs_idempotence
    ON jobs (idempotency_key) WHERE idempotency_key IS NOT NULL
                                AND status IN ('pending','running');
CREATE INDEX IF NOT EXISTS jobs_a_depiler
    ON jobs (status, run_after, priority) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS jobs_campagne_idx ON jobs (campaign_id, created_at DESC);


-- ── Réglages du module ───────────────────────────────────────────────────────
-- Une seule ligne, contrainte par la base : `settings` n'est pas une table de
-- lignes mais un document unique. Sans cette contrainte, une deuxième ligne
-- apparaît un jour et plus personne ne sait laquelle fait foi.
CREATE TABLE IF NOT EXISTS settings (
    id                      BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    eligibility_policy      JSONB       NOT NULL DEFAULT '{
        "deliverable": "eligible", "risky": "excluded", "catch_all": "excluded",
        "unknown": "excluded", "invalid": "excluded", "disposable": "excluded",
        "role": "excluded", "suppressed": "excluded"}'::jsonb,
    validation_batch_size   INT         NOT NULL DEFAULT 1000,
    sending_batch_size      INT         NOT NULL DEFAULT 500,
    max_recipients_per_campaign INT     NOT NULL DEFAULT 100000,
    max_rate_per_minute     INT         NOT NULL DEFAULT 600,
    daily_cap               INT,
    sending_windows         JSONB       NOT NULL DEFAULT '[]'::jsonb,
    double_confirm_threshold INT        NOT NULL DEFAULT 5000,
    csv_retention_days      INT         NOT NULL DEFAULT 90,
    results_retention_days  INT         NOT NULL DEFAULT 365,
    require_unsubscribe     BOOLEAN     NOT NULL DEFAULT TRUE,
    blocking_content_checks JSONB       NOT NULL DEFAULT '["unsubscribe","http_links","subject"]'::jsonb,
    alert_emails            JSONB       NOT NULL DEFAULT '[]'::jsonb,
    alert_thresholds        JSONB       NOT NULL DEFAULT '{"bounce_rate": 0.05, "complaint_rate": 0.001}'::jsonb,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by              TEXT
);
-- Appels Mailnjoy simultanés. 1 tant que le débit réel n'est pas mesuré : un
-- parallélisme deviné qui déclenche des 429 est plus lent que le séquentiel.
ALTER TABLE settings ADD COLUMN IF NOT EXISTS mailnjoy_concurrency INT NOT NULL DEFAULT 1;
ALTER TABLE settings ADD COLUMN IF NOT EXISTS max_csv_bytes BIGINT NOT NULL DEFAULT 52428800;  -- 50 Mo
INSERT INTO settings (id) VALUES (TRUE) ON CONFLICT (id) DO NOTHING;


-- ── Webhooks bruts ───────────────────────────────────────────────────────────
-- Tout événement entrant est d'abord écrit tel quel, AVANT interprétation :
-- si le traitement se trompe, la source reste rejouable.
CREATE TABLE IF NOT EXISTS webhook_events (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider                TEXT        NOT NULL,
    event_type              TEXT,
    email_hash              TEXT,
    campaign_id             UUID,
    external_id             TEXT,
    signature_valid         BOOLEAN,
    raw_payload             JSONB       NOT NULL,
    processed_at            TIMESTAMPTZ,
    process_error           TEXT,
    received_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS webhook_a_traiter ON webhook_events (provider, received_at)
    WHERE processed_at IS NULL;
-- Rejeu impossible : un même événement fournisseur n'est traité qu'une fois.
CREATE UNIQUE INDEX IF NOT EXISTS webhook_unicite
    ON webhook_events (provider, external_id) WHERE external_id IS NOT NULL;


-- ── Battement de cœur des workers ────────────────────────────────────────────
-- Le bandeau de santé dit « worker arrêté » si plus rien n'a battu depuis 2 min :
-- sans ça, une file qui ne se vide plus ressemble à une file qui travaille.
CREATE TABLE IF NOT EXISTS workers (
    id                      TEXT        PRIMARY KEY,
    seen_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    info                    JSONB
);
