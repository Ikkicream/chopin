# Contacts Model — Pool mutualisé Genesis

> Décisions actées 2026-05-22. Source de vérité pour la refonte data du module Acquisition.

## 1. Contexte

Aujourd'hui les contacts vivent dans **2 DBs séparées par site** (`data/crm/lcr.duckdb`, `data/crm/mkd.duckdb`) — pas de partage, dédup à la main par site. Décision user : passer à un **pool mutualisé GLOBAL Genesis** (mutualisation **inter-comptes**), où chaque site/compte pioche dans la même base et où chaque chargement de contact enrichit ce pool commun.

## 2. Modèle de données cible

### 2.1 Architecture en 2 tables

```
data/contacts.duckdb (NOUVEAU — fichier mutualisé Genesis)
   │
   ├─ contacts                          ← MASTER (1 row par email unique)
   │  • id              VARCHAR PK uuid
   │  • email           VARCHAR UNI    ← clé fonctionnelle
   │  • prenom          VARCHAR
   │  • nom             VARCHAR
   │  • societe         VARCHAR
   │  • tel             VARCHAR
   │  • website         VARCHAR
   │  • city            VARCHAR
   │  • dept_code       VARCHAR
   │  • region_code     VARCHAR
   │  • postal_code     VARCHAR (nullable, peut être abandonné)
   │  • sectors         JSON       ← array de secteurs (cf. spec sectoral-qualifier)
   │  • primary_source  VARCHAR    ← source du premier chargement (tally|serper|csv|manual)
   │  • email_score     INTEGER    ← score validator dernière vérif
   │  • email_validation_reasons JSON
   │  • mailnjoy_check  JSON       ← dernière réponse Mailnjoy
   │  • global_blacklisted  BOOLEAN DEFAULT FALSE  ← RGPD : unsub respecté partout
   │  • blacklist_reason    VARCHAR
   │  • blacklisted_at      TIMESTAMP
   │  • created_at      TIMESTAMP
   │  • updated_at      TIMESTAMP
   │
   └─ contact_site_history             ← 1 row par contact × site qui le manipule
      • id                  VARCHAR PK uuid
      • contact_id          VARCHAR FK → contacts.id
      • site_code           VARCHAR    ← lcr|mkd|… (compte+site)
      • account_id          VARCHAR    ← compte propriétaire du site (multi-tenant futur)
      • state               VARCHAR    ← cold_email|prm|lead|crm
      • source              VARCHAR    ← source POUR CE SITE (tally|serper|csv|manual)
      • added_to_site_at    TIMESTAMP
      • state_history       JSON       ← chrono des transitions pour ce site
      • last_action_at      TIMESTAMP
      
      ──── Push Emelia (par site) ────
      • emelia_campaign_id  VARCHAR
      • emelia_contact_id   VARCHAR
      • email_sent_at       TIMESTAMP
      • emelia_opened_at    TIMESTAMP
      • emelia_clicked_at   TIMESTAMP
      • emelia_replied_at   TIMESTAMP
      • emelia_bounced_at   TIMESTAMP
      • emelia_unsubscribed_at TIMESTAMP
      
      ──── Cooldown ────
      • last_contacted_by_site_at  TIMESTAMP  ← copie de email_sent_at pour requête rapide
      
      UNI (contact_id, site_code)  ← un seul état par site pour 1 contact
```

### 2.2 Pourquoi 2 tables et pas une seule

- **contacts** = vérité globale (qui est cette personne, identité)
- **contact_site_history** = relation N-N entre contact et site (état/historique propre à chaque utilisation par un site)

Un contact peut être :
- dans le pool sans qu'aucun site ne l'utilise encore → 0 row dans `contact_site_history`
- utilisé par 1 site → 1 row
- utilisé par 5 sites avec des états différents → 5 rows

## 3. Règles métier

### 3.1 Déduplication (Q8.1)
- **Clé** : email normalisé (`lower()` + `trim()`)
- Si un nouveau contact arrive et que `email` existe déjà :
  - **Update** des champs de `contacts` qui sont NULL (jamais override les valeurs déjà fournies par une autre source)
  - **Insert** d'une nouvelle row dans `contact_site_history` SI le site qui l'ajoute n'y est pas déjà

### 3.2 Cooldown et base repoussoir (Q8.2 — révisé le 2026-08-19)

**RÈGLE ABSOLUE** : dès qu'une personne a reçu **un** email, elle est inscrite dans la
base repoussoir `email_suppression` (flag `contactable = 0` + date de l'envoi) et **ne
reçoit plus rien pendant 120 jours**, tous sites et tous canaux confondus.

```
COOLDOWN_DAYS = SUPPRESSION_DAYS = 120   (contacts_pool_backend.py)
```

Deux barrières redondantes, parce qu'une seule peut échouer en silence :

| Barrière | Support | Rôle |
|---|---|---|
| Cooldown du pool | `contact_site_history.last_contacted_by_site_at` | filtre de la pioche (même site + cross-site) |
| Base repoussoir | `email_suppression` | registre par **adresse**, écrit à chaque envoi, survit à la suppression du contact du pool |

La base repoussoir fait foi : elle est indexée sur l'email normalisé, pas sur l'id du
contact. Un contact purgé puis re-scrapé demain retrouve donc son blocage — c'est
précisément le trou par lequel passaient les renvois en boucle.

**Pourquoi 120 et non 7** : le cooldown même-site était à 7 jours. Sur août 2026 cela a
produit 1 189 envois pour 724 destinataires (39 % de redites), et jusqu'à 98 renvois sur
100 le 15/08 — les contacts touchés début août redevenaient éligibles au bout d'une
semaine, et le tri (source puis score) les ramenait en tête devant les contacts frais.
Ne jamais redescendre sans décision utilisateur explicite.

**Tri de la pioche** : les contacts jamais sollicités par le site passent AVANT tous les
autres (`NEVER_CONTACTED_FIRST_SQL`). On épuise le pool frais avant de recontacter qui que
ce soit.

**Libération** : automatique. Les requêtes filtrent sur `last_sent_at`, donc une adresse
redevient éligible d'elle-même à J+120 ; `release_expired()` ne fait que remettre le flag
à 1 pour la lisibilité.

### 3.3 Blacklist GLOBALE (Q8.4)
Si **`contacts.global_blacklisted = TRUE`** :
- Aucun site ne peut le pusher
- Plus aucune campagne possible (RGPD)
- Status `contact_site_history.state` pour tous les sites concernés → `blacklisted`

Déclenchement automatique :
- Event Emelia `UNSUBSCRIBED` ou `BOUNCED` reçu par n'importe quel site → set `global_blacklisted=TRUE`

### 3.4 Transition Tally (Q6)
Si un contact A existe déjà (ex: source serper, state=cold_email pour LCR) et qu'il **soumet un Tally form LCR** :
- Pas de row supplémentaire dans `contacts`
- Update de la row `contact_site_history (contact_id=A, site_code=lcr)` : state passe de `cold_email` → `lead`
- Note dans `state_history` : "promu lead via tally:<form_id>"

### 3.5 Algorithme "pioche depuis le pool" (Q3.1 + Q8.3)
Pour la page Campagnes, quand l'admin demande "30 contacts du secteur restaurant pour LCR" :

```sql
SELECT c.*, csh.*
FROM contacts c
LEFT JOIN contact_site_history csh
    ON c.id = csh.contact_id AND csh.site_code = 'lcr'
WHERE
    json_extract(c.sectors, '$') LIKE '%restaurant%'
    AND c.global_blacklisted = FALSE
    AND (csh.state IS NULL OR csh.state IN ('cold_email'))  -- jamais pushé ou cold uniquement
    AND (
        -- jamais contacté par ce site
        csh.last_contacted_by_site_at IS NULL
        OR
        -- contacté il y a > 120 jours (Q3.2, révisé 2026-08-19)
        csh.last_contacted_by_site_at < NOW() - INTERVAL 120 DAY
    )
    -- cooldown global
    AND NOT EXISTS (
        SELECT 1 FROM contact_site_history csh2
        WHERE csh2.contact_id = c.id
          AND csh2.last_contacted_by_site_at > NOW() - INTERVAL 120 DAY
          AND csh2.site_code != 'lcr'
    )
    -- base repoussoir : toute adresse ayant reçu un email dans les 120 jours
    AND NOT EXISTS (
        SELECT 1 FROM email_suppression sup
        WHERE sup.email = lower(c.email)
          AND sup.contactable = 0
          AND sup.last_sent_at > NOW() - INTERVAL 120 DAY
    )
ORDER BY
    -- 1. Source : tally(0) > serper(1) > csv(2) > manual(3)
    CASE c.primary_source
        WHEN 'tally' THEN 0
        WHEN 'serper' THEN 1
        WHEN 'csv' THEN 2
        ELSE 3
    END,
    -- 2. email_score décroissant (Mailnjoy validé > non validé)
    c.email_score DESC NULLS LAST,
    -- 3. plus récent en premier
    c.updated_at DESC
LIMIT 30;
```

## 4. Migration depuis l'existant (Q8.5)

Script one-shot `scripts/migrate_contacts_to_pool.py` :

```
1. Créer data/contacts.duckdb avec les 2 tables
2. Lire crm/lcr.duckdb.acquisition_contacts → INSERT contacts (uniquement nouvelle row si email pas déjà vu) + INSERT contact_site_history (site_code='lcr')
3. Lire crm/mkd.duckdb.acquisition_contacts → IDEM (site_code='mkd')
4. Lire god_mode.duckdb.scrappe (status IN ['mailnjoy_valid', 'pushed_emelia']) → INSERT contacts (dedup email) + INSERT contact_site_history (mapper status scrappe → state acquisition)
5. Garder crm/lcr.duckdb + crm/mkd.duckdb + scrappe en RO pour fallback rollback 30 jours
6. Logger toutes les opérations dans logs/migration_contacts_pool.log
```

**Mapping scrappe.status → contact_site_history.state** :
| scrappe.status | new state |
|---|---|
| mailnjoy_valid | cold_email (jamais pushé) |
| pushed_emelia | cold_email (déjà pushé, last_contacted = contacted_at) |
| rejected | (skip — pas dans pool) |
| manual_review | cold_email (avec note manual_review) |
| scored | (skip — legacy pré-Mailnjoy) |

## 5. Tables existantes à archiver / supprimer

| Table actuelle | Devient |
|---|---|
| `data/crm/lcr.duckdb.acquisition_contacts` | Archive RO 30 jours puis supprimer |
| `data/crm/mkd.duckdb.acquisition_contacts` | Archive RO 30 jours puis supprimer |
| `data/god_mode.duckdb.scrappe` | Archive RO 30 jours puis supprimer |
| `data/god_mode.duckdb.scrappe_pending` | **À garder** (file d'attente Mailnjoy, court-terme) |
| `data/god_mode.duckdb.emelia_events` | **À garder** (audit) |
| `data/god_mode.duckdb.email_senders` | **À garder** (warmup) |
| `data/god_mode.duckdb.god_mode_*` | **À garder** (state, settings, campaigns scheduled, templates, logs, serper_calls) |

## 6. Impact sur le code

| Fichier | Modif |
|---|---|
| `scripts/acquisition_backend.py` | Refactor complet : nouveaux helpers `create_in_pool()`, `find_by_email_global()`, `get_history_for_site()`, `change_state_for_site()`, `pick_for_campaign(site, sector, limit)` |
| `scripts/god_mode_agents.py` `scrape_sector()` | Ne pousse plus dans scrappe_pending puis scrappe → pousse direct dans `contacts` + `contact_site_history` (état "available", pas encore pushé) |
| `scripts/workflow_emelia_push.py` `push_prospect()` | Lit depuis `contact_site_history`, update state + emelia_* |
| `scripts/emelia_to_crm.py` | Update via `change_state_for_site()` |
| Webhook handler `api.py:api_emelia_webhook` | Update via `change_state_for_site()` + check `global_blacklisted` |
| `scripts/tally_to_prm.py` | `create_in_pool()` puis `change_state_for_site('lead')` |
| `genesis-ui/src/app/site/[code]/acquisition/page.tsx` | Affichage : 1 ligne par contact, mais sous-vue "historique par site" disponible |
| `genesis-ui/src/app/site/[code]/campaigns/page.tsx` | Bouton "Pioche depuis le pool" appelle `pick_for_campaign()` |

## 7. Risques & questions résiduelles

1. **RGPD (B2B only, posture allégée)** — Genesis cible exclusivement le cold email B2B vers des contacts professionnels publics (sites web, annuaires, Pages Jaunes). La doctrine CNIL 2026 reste favorable pour le B2B sous réserve de : (a) opt-out fonctionnel dans chaque mail (géré par Emelia), (b) mention identité expéditeur dans le pied (cf. onboarding step 8), (c) sources publiques licites. Les garde-fous techniques retenus (blacklist globale, base repoussoir 120j) servent **autant la qualité business** (ne pas spammer un contact 3 fois en 1 mois) **que la conformité**. Pas de paranoïa "CNIL 4% CA" à entretenir.

2. **Concurrence cross-comptes** — Premier arrivé = locké 120 jours pour les autres (cooldown + base repoussoir, cf. §3.2).

3. **Volume** — DuckDB tient 100k+ contacts. On est très loin (35 rows aujourd'hui).

4. **Backup** — Nouvelle DB à inclure dans cron `backup.sh`.

## 8. ✅ Validation user (actée 2026-05-22)

- [x] Schéma 2 tables `contacts` + `contact_site_history` validé
- [x] ~~Cooldown global 30 jours, re-push même site 7 jours~~ → **120 jours partout + base repoussoir** (révisé le 2026-08-19, cf. §3.2)
- [x] Blacklist globale via Emelia UNSUBSCRIBE/BOUNCE validée (RGPD allégé B2B mais respect du choix utilisateur garanti)
- [x] Migration douce (archive 30j puis suppression) validée
