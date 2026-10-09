-- Connecteur Onoff Business — journal local des événements téléphoniques.
--
-- Pourquoi une table locale alors que l'API expose déjà les journaux : l'API Onoff est
-- réservée au plan Max, tandis que le webhook fonctionne indépendamment. Le webhook est
-- donc la source PRIMAIRE, l'API un enrichissement. Sans cette table, une messagerie non
-- lue disparaîtrait de l'écran dès que l'abonnement change.
--
-- Tout est en IF NOT EXISTS : le fichier s'applique à chaque démarrage sans rien casser.

CREATE TABLE IF NOT EXISTS onoff_evenements (
    id             text PRIMARY KEY,          -- `id` du log Onoff, sert de clé d'idempotence
    site_code      text NOT NULL,
    type           text NOT NULL,             -- CDR | VM | RECORDING | SMS
    direction      text,                      -- INBOUND | OUTBOUND
    statut         text,                      -- ANSWERED | MISSED_CALL | VMS | BUSY | ...
    membre_nom     text,
    membre_email   text,
    numero_onoff   text,                      -- la ligne Onoff utilisée
    numero_externe text,                      -- l'interlocuteur, en E.164 quand c'est possible
    nom_externe    text,
    societe_externe text,
    debut          timestamptz,
    fin            timestamptz,
    duree_s        integer,
    texte          text,                      -- corps du SMS
    url_audio      text,                      -- messagerie ou enregistrement
    duree_audio_s  integer,
    notes          text,
    brut           jsonb NOT NULL DEFAULT '{}'::jsonb,
    lu_at          timestamptz,               -- NULL = non lu (messagerie)
    recu_at        timestamptz NOT NULL DEFAULT now()
);

-- La messagerie non lue est LA requête de la page répondeur : elle doit rester instantanée
-- même quand la table aura des dizaines de milliers de lignes.
CREATE INDEX IF NOT EXISTS idx_onoff_non_lu
    ON onoff_evenements (site_code, debut DESC)
    WHERE type = 'VM' AND lu_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_onoff_site_debut
    ON onoff_evenements (site_code, debut DESC);

-- Rapprochement avec le CRM : retrouver tous les échanges d'un numéro donné.
CREATE INDEX IF NOT EXISTS idx_onoff_numero
    ON onoff_evenements (site_code, numero_externe, debut DESC);
