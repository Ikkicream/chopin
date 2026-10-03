-- ============================================================================
-- pg_schema_crm.sql — Suivi commercial (mini-CRM) sur PostgreSQL
-- Créé le 2026-08-19. Idempotent : rejouable sans effet de bord.
--
-- Deux tables, et la séparation entre elles est le point de conception :
--   `contact_followup`  = l'ÉTAT courant d'un contact (à qui il est attribué, où il en est)
--   `followup_events`   = le JOURNAL des interactions, en ajout seul
--
-- C'est la même leçon que `email_events` : un CRM qui écrase « dernier appel » à chaque
-- appel perd l'historique de la relation, et personne ne peut plus dire ce qui a été dit
-- ni combien de fois on a relancé. L'état se met à jour, le journal ne se réécrit jamais.
-- ============================================================================

-- ── L'état courant ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contact_followup (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Clé sur l'ADRESSE et non sur l'id du contact : le suivi commercial doit survivre à
    -- la sortie du contact du référentiel (rebond, désabonnement, purge). Un prospect
    -- qu'on rappelle ne disparaît pas parce que son email est devenu non délivrable.
    email          citext NOT NULL,
    site_code      text   NOT NULL,
    contact_id     uuid REFERENCES contacts(id) ON DELETE SET NULL,

    -- Attribution : UN commercial à la fois. `assigned_to` porte le `username` et non l'id,
    -- pour rester lisible dans le journal et survivre à une recréation de compte.
    assigned_to    text,
    assigned_at    timestamptz,
    assigned_by    text,

    statut         text NOT NULL DEFAULT 'a_faire',
    next_action_at timestamptz,          -- rappel programmé
    last_call_at   timestamptz,
    outcome        text,                 -- issue du dernier échange
    notes          text,                 -- bloc-notes libre, écrasable (le journal, lui, non)

    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),

    -- Un seul suivi par contact et par site : sans ça, deux commerciaux pourraient créer
    -- chacun le leur et s'appeler l'un après l'autre le même prospect.
    UNIQUE (email, site_code),
    CONSTRAINT followup_statut_chk CHECK (statut IN
        ('a_faire', 'en_cours', 'a_relancer', 'gagne', 'perdu', 'injoignable'))
);

-- Épinglage et retrait, ajoutés le 2026-08-19.
-- `flash` : le commercial remonte un contact en tête de sa liste pour le rappeler plus
-- tard dans la journée. C'est un marque-page, pas un statut : il ne dit rien de la
-- relation, seulement de l'ordre d'appel.
-- `retire_at` : le contact sort de la liste d'appels SANS disparaître de la base. Le
-- supprimer pour de bon serait sans effet — `pg_reconcile` le rétablirait à 6 h 30
-- puisqu'il reste éligible. Un retrait est réversible et laisse une trace.
ALTER TABLE contact_followup ADD COLUMN IF NOT EXISTS flash      boolean NOT NULL DEFAULT false;
ALTER TABLE contact_followup ADD COLUMN IF NOT EXISTS flash_at   timestamptz;
ALTER TABLE contact_followup ADD COLUMN IF NOT EXISTS retire_at  timestamptz;
ALTER TABLE contact_followup ADD COLUMN IF NOT EXISTS retire_par text;

CREATE INDEX IF NOT EXISTS idx_followup_assigne  ON contact_followup (site_code, assigned_to, statut);
CREATE INDEX IF NOT EXISTS idx_followup_relance  ON contact_followup (next_action_at)
    WHERE statut IN ('a_faire', 'en_cours', 'a_relancer');
CREATE INDEX IF NOT EXISTS idx_followup_contact  ON contact_followup (contact_id);

-- ── Le journal des interactions, en ajout seul ──────────────────────────────
CREATE TABLE IF NOT EXISTS followup_events (
    id          bigserial PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    email       citext NOT NULL,
    site_code   text   NOT NULL,
    auteur      text   NOT NULL,        -- username de qui a agi
    type        text   NOT NULL,        -- assignation | appel | note | statut | relance
    detail      text,                   -- ce qui a été dit ou décidé
    meta        jsonb  NOT NULL DEFAULT '{}',
    CONSTRAINT followup_events_type_chk CHECK (type IN
        ('assignation', 'desassignation', 'appel', 'note', 'statut', 'relance'))
);

CREATE INDEX IF NOT EXISTS idx_fevents_email ON followup_events (email, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_fevents_site  ON followup_events (site_code, occurred_at DESC);

-- ── Vue de travail : le contact, son suivi et son dernier signal d'intérêt ──
-- Regroupée ici pour que l'API n'ait pas à réécrire cette jointure à chaque endpoint —
-- c'est la duplication de requêtes qui fait diverger deux écrans censés dire la même chose.
-- Recréée et non « remplacée » : PostgreSQL refuse de changer l'ordre ou le nom des
-- colonnes d'une vue existante, et cette vue en gagne deux (flash, flash_at).
DROP VIEW IF EXISTS v_a_rappeler;
CREATE VIEW v_a_rappeler AS
SELECT
    ct.id                AS contact_id,
    ct.email,
    cs.site_code,
    ct.prenom, ct.nom, ct.societe, ct.tel, ct.website, ct.city, ct.dept_code,
    ct.prenom_source,
    cs.state,
    f.id                 AS followup_id,
    COALESCE(f.statut, 'a_faire')  AS statut,
    f.assigned_to, f.assigned_at, f.next_action_at, f.last_call_at, f.outcome, f.notes,
    COALESCE(f.flash, false) AS flash, f.flash_at,
    eng.last_open_at, eng.last_click_at, eng.opens, eng.clicks,
    (SELECT count(*) FROM followup_events fe
      WHERE fe.email = ct.email AND fe.site_code = cs.site_code) AS nb_interactions
FROM contacts ct
JOIN contact_sites cs        ON cs.contact_id = ct.id
LEFT JOIN contact_followup f ON f.email = ct.email AND f.site_code = cs.site_code
LEFT JOIN v_contact_engagement eng ON eng.contact_id = ct.id
WHERE cs.state IN ('lead', 'prm')
  AND NOT ct.global_blacklisted
  -- Un contact retiré de la liste d'appels reste en base, avec son journal : il ne
  -- remonte simplement plus dans la liste ni dans les compteurs.
  AND f.retire_at IS NULL;
