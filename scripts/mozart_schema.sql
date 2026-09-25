-- ── Mozart : scénarios d'automatisation d'emails ─────────────────────────────
-- Un scénario est un GRAPHE : des nœuds (déclencheur, délai, email, condition) reliés
-- par des liens. Il est stocké tel que l'éditeur le manipule — c'est le même objet des
-- deux côtés, donc rien à traduire, donc rien à désynchroniser.
CREATE TABLE IF NOT EXISTS mozart_scenarios (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    site_code   text NOT NULL,
    nom         text NOT NULL,
    description text,
    statut      text NOT NULL DEFAULT 'brouillon',
    graphe      jsonb NOT NULL DEFAULT '{"nodes":[],"edges":[]}'::jsonb,
    cree_le     timestamptz NOT NULL DEFAULT now(),
    modifie_le  timestamptz NOT NULL DEFAULT now(),
    cree_par    text,
    CONSTRAINT mozart_statut_chk CHECK (statut IN ('brouillon', 'actif', 'pause', 'archive'))
);
-- Le pixel d'ouverture, scénario par scénario. Le guide de délivrabilité de Maildoso le
-- déconseille (Gmail le note), mais le couper partout priverait les commerciaux de la
-- liste des ouvreurs. Défaut à vrai : on ne retire pas une mesure sans le demander.
ALTER TABLE mozart_scenarios ADD COLUMN IF NOT EXISTS suivi_ouverture boolean NOT NULL DEFAULT true;

CREATE INDEX IF NOT EXISTS idx_mozart_site ON mozart_scenarios (site_code, statut);

-- Où en est CHAQUE contact dans CHAQUE scénario. C'est l'état d'exécution : sans lui, un
-- redémarrage perdrait tout le monde en cours de route.
CREATE TABLE IF NOT EXISTS mozart_inscriptions (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario_id   uuid NOT NULL REFERENCES mozart_scenarios(id) ON DELETE CASCADE,
    email         citext NOT NULL,
    contact_id    uuid REFERENCES contacts(id) ON DELETE SET NULL,
    noeud_courant text,
    statut        text NOT NULL DEFAULT 'en_cours',
    inscrit_le    timestamptz NOT NULL DEFAULT now(),
    agir_a        timestamptz,          -- quand le prochain pas doit être joué
    termine_le    timestamptz,
    motif_sortie  text,
    -- Un contact n'entre QU'UNE FOIS dans un scénario donné : sans cette contrainte, un
    -- déclencheur qui se réévalue toutes les heures le réinscrirait à chaque passage et
    -- lui enverrait la même séquence en boucle.
    CONSTRAINT mozart_une_inscription UNIQUE (scenario_id, email)
);
CREATE INDEX IF NOT EXISTS idx_mozart_a_jouer ON mozart_inscriptions (agir_a)
    WHERE statut = 'en_cours';
CREATE INDEX IF NOT EXISTS idx_mozart_insc_scenario ON mozart_inscriptions (scenario_id, statut);

-- Le journal des pas franchis : c'est lui qui porte les statistiques du scénario.
-- En AJOUT SEUL, comme `email_events` — un compteur qu'on incrémente se perd, un journal
-- se relit.
CREATE TABLE IF NOT EXISTS mozart_passages (
    id          bigserial PRIMARY KEY,
    scenario_id uuid NOT NULL REFERENCES mozart_scenarios(id) ON DELETE CASCADE,
    noeud_id    text NOT NULL,
    email       citext NOT NULL,
    type_noeud  text NOT NULL,
    resultat    text,                  -- 'envoye', 'ouvert', 'clique', 'rien', 'refuse'…
    detail      text,
    quand       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mozart_passages ON mozart_passages (scenario_id, noeud_id, quand DESC);

-- Ajouts du 2026-08-24 : un scénario peut être un MODÈLE qu'on duplique au lieu de le
-- modifier. Le cadenas est une protection contre soi-même, pas une méfiance.
ALTER TABLE mozart_scenarios ADD COLUMN IF NOT EXISTS est_modele boolean NOT NULL DEFAULT false;
ALTER TABLE mozart_scenarios ADD COLUMN IF NOT EXISTS verrouille boolean NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS idx_mozart_modeles ON mozart_scenarios (site_code, est_modele);
