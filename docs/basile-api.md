# Basile API — Documentation (api.basile.cc)

> Doc de référence du connecteur Genesis `scripts/basile_backend.py`. Rédigée d'après le
> skill `skills/basile-b2b-search` (SKILL.md + references). App **app.basile.cc** /
> **docs.basile.cc** : à crosscheck au retour du service (voir §Go-live). Console / clé API :
> https://app.basile.cc/ — Docs éditeur : https://docs.basile.cc/

## 1. C'est quoi

Base de données B2B française : **~26 M sociétés** (registre légal INSEE + LinkedIn + Google
My Business) et **~4,4 M contacts** (dirigeants légaux + profils LinkedIn). On cherche, on
compte, on exporte via l'API comme dans la plateforme web.

## 2. Authentification

- Header `Authorization: <clé brute>` — **SANS** préfixe `Bearer`.
- Header `Content-Type: application/json`.
- Clé générée sur le compte Basile (**plan API requis**). Stockée dans `.env` → `BASILE_KEY`.
- Ne jamais logger ni committer la clé.

```
Authorization: $BASILE_KEY
Content-Type: application/json
```

URL de base : `https://api.basile.cc`

## 3. Endpoints

### Recherche & extraction
| Méthode | Route | Usage |
|---|---|---|
| POST | `/people/find` | Chercher des personnes. Body `{ filters, limit, paginationToken }`. **`limit:1` = compter (gratuit).** |
| POST | `/people/export` | Export CSV personnes (consomme quota). Body `{ filters }` ou `{ ids:[...] }`. |
| POST | `/companies/find` | Chercher des entreprises. Même structure. |
| POST | `/companies/export` | Export CSV entreprises (consomme quota). |
| GET | `/people/:id` · `/people/:id/full` | Fiche brute / enrichie (toutes colonnes). |
| GET | `/companies/:id` · `/companies/:id/full` | Idem entreprises. |

### Suggestions / autocomplete (GET, `?q=` + `?limit=`)
- **Personnes** : `/people/cities/suggest`, `/people/companies/suggest` (employeurs),
  `/people/roles/suggest`, `/people/skills/suggest`, `/people/languages/suggest`,
  `/people/education/suggest`, `/people/names/suggest`, `/people/nationalities/suggest`,
  `/people/age/bounds`, `/people/mandate-count/bounds`, `/people/seniorities`,
  `/people/tenure-buckets`.
- **Entreprises** : `/companies/activity-suggest` (→ IDs concept pour `activity`),
  `/companies/name-suggest`, `/companies/city-suggest`, `/companies/legal-form-suggest`,
  `/companies/siren-suggest`.

### Gestion des clés (session web, pas via clé API)
`GET /api-keys/` · `POST /api-keys/` (renvoie `rawKey` UNE fois) · `DELETE /api-keys/:id`.

## 4. Structure d'une requête `/find`

```json
{ "filters": { ... }, "limit": 100, "paginationToken": "..." }
```
- `filters` : plusieurs filtres = **ET**. Filtre texte = `{ "include": [...], "exclude": [...] }`
  (`include` = OR, `exclude` = NOT).
- Numériques **personnes** = range objet `{ ">=": 10, "<=": 50 }`. Numériques **entreprises** =
  champs `_min`/`_max` simples (ex. `headcount_min`, `capital_max`).
- `limit` : max **100** par page.
- `paginationToken` : curseur opaque renvoyé dans `pagination.nextToken`. ⚠️ Page > 1 nécessite
  un **abonnement actif** (sinon HTTP 402).

## 5. Format de réponse `/find`

```json
{
  "success": true,
  "total": 12345,
  "leads": [ { "_id": "...", "source": "LKI" | "Legal" | "GMB", "data": { ... } } ],
  "pagination": { "nextToken": "..." }
}
```
- `total` = majorant léger (somme des sources, sans dédup cross-source) — bon ordre de grandeur.
- `pagination` **absent** quand il n'y a plus de page.
- `source` : `Legal` (registre), `LKI` (LinkedIn), `GMB` (Google My Business).

## 6. Filtres — personnes (`/people/find`)

⛔ **Pas de filtre « secteur / type d'entreprise » fiable côté personnes** (données LinkedIn
lacunaires). Pour cibler des personnes par secteur → **workflow 2 étapes** (entreprises → SIREN
→ personnes). Voir `context/lcr/acquisition-context.md`.

Communs : `keyword`, `result_full_name`, `result_first_name`, `result_last_name`, `result_role`
(intitulé de poste — mettre toutes les variantes, cf. `references/job_titles_synonyms.json`),
`result_city`, `result_country_code`, `employer`.
Legal-only : `mandate_role` (`gerant`/`president`/`dg`/…), `siren`, `legal_name`, `legal_form`,
`nationality`, `result_postal_code`, `result_age` (range), `result_is_current` (bool),
`result_total_companies_count` (range).
LinkedIn-only : `current_seniority` (`C-Level`/`Director`/`VP`/`Head`/`Manager`/…),
`current_job_functions`, `skills`, `languages`, `education`, `past_title`, `past_employer`,
`tenure_bucket`, `connection_count`.
Pilotage source : `source` (`Legal`/`LKI`), `with_legal_data`, `with_linkedin_profile`,
`hide_legal_entities: true` (recommandé — masque les personnes morales).

## 7. Filtres — entreprises (`/companies/find`)

Généraux : `keyword`, `name`, `activity` (**métier unifié**, concept = NAF + Google + LinkedIn ;
le plus puissant pour cibler un secteur).
Legal : `naf_code` (préfixe `.x` ex `"41.x"`), `headquarters_naf_code`,
`headquarters_department_code`, `headquarters_region_code`, `headquarters_postal_code`,
`legal_form`, `legal_category` (INSEE, cf. `references/legal_categories.json`), `siren`,
`capital_min`/`capital_max`, `publishable`, `creation_date_min`/`creation_date_max` (année).
Legal+LKI : `headquarters_city`, `headquarters_country_code`, `headcount_min`/`headcount_max`.
LinkedIn : `industry_main`/`company_type` (⚠️ lacunaires, jamais en filtre secteur principal),
`domain`, `followers_min`/`followers_max`.
GMB : `rating_min`/`rating_max`, `reviews_min`/`reviews_max`, `is_opening`.
Spécial : **`company_ceased: false`** (entreprises actives — à mettre par défaut).
Pilotage source : `source` (`Legal`/`LKI`/`GMB`), `with_legal_data`, `with_linkedin_page`.

## 8. Compter, puis extraire (RÈGLE D'OR)

1. **Compter** : `/find` `limit:1` → lire `total` (gratuit en quota).
2. Décider (le connecteur fait ça via `enforce_volume_rules`) :
   - `total` ≤ **20 000** → extraction OK, en passes de 1 000.
   - `total` > 20 000 → **segmenter** (département / NAF / taille / année) avant d'extraire.
3. Extraire (consomme le quota).

## 9. Export & gros volumes

- `/people/export` ou `/companies/export` avec le **même `filters`** que le find, ou `{ "ids":[...] }`.
- Renvoie un CSV enrichi (**~70 colonnes** — livrer COMPLET, ne pas réduire les colonnes).
- Plafonné par plan : header **`X-Export-Max-Rows`** (limite réelle), **`X-Export-Capped: true`**
  (reste des résultats au-delà).
- ⚠️ **Ne JAMAIS faire un seul `/export` géant** : il boucle par 100 en interne → timeout.
  → Mode **bulk** : paginer `/find` pour collecter les IDs, puis `/export` par lots de 1 000
  avec délai entre appels. Géré par `skills/basile-b2b-search/scripts/basile_search.py` (réf) et
  par `scripts/basile_backend.run_segment` (intégration Genesis, écrit dans le pool).

## 10. Limites par plan

| Plan | req/s | req/min | req/jour | Max/export | Quota mensuel |
|---|---|---|---|---|---|
| `api` | 10 | 100 | 50 000 | **20 000** | 250 000 |
| `custom` | 1 000 | 1 000 | 100 000 | 50 000 | 1 000 000 |
| `starter` | — | — | — | 5 000 | 100 000 |

Reset minute/jour en **UTC**. Se fier au header `X-Export-Max-Rows` pour la valeur réelle.

## 11. Codes de réponse

| Code | Sens | Action |
|---|---|---|
| 200 | OK | — |
| 401 | `Unauthorized` | clé invalide/absente → vérifier `Authorization` |
| 402 | `subscription_required` | pagination page > 1 sans abo → **BASILE_BLOCKED** |
| 403 | `api_plan_required` / `api_key_limit_reached` | plan API requis → **BASILE_BLOCKED** |
| 429 | `rate_limit_exceeded` / `daily_limit_exceeded` | respecter `Retry-After` (reprise auto) |
| 500 | erreur serveur | réessayer |

Le connecteur pose le flag `BASILE_BLOCKED_STATUS` sur 402/403 (blocage métier) — même esprit
que `SERPER_BLOCKED_STATUS`.

## 12. Enrichissement Emelia (emails nominatifs / téléphones)

API distincte (`https://api.emelia.io`, clé `EMELIA_API_KEY` déjà en `.env`). Basile donne les
emails **génériques** (gratuits) ; Emelia trouve les **emails nominatifs** et **portables**
(payant, à l'unité, opt-in). Détails : `skills/basile-b2b-search/references/enrichment_emelia.md`
et `docs/emelia-api.md`. Règle : annoncer le coût et demander validation avant chaque lot.

## 12bis. ✅ Confirmé en live (2026-06-17)

Tests réels effectués (clé API active) :
- **Auth OK**, `count` gratuit OK (15 M sociétés actives, 284 k « CEO/PDG/Gérant »).
- **`naf_code`** : format exact `"56.10A"`. **Pas de wildcard `.x`** (`"56.1"` → 0).
- **`activity`** : préfixe **`concept:`** obligatoire (`concept:restaurant_table` → 364 k). Trouver
  l'ID via `activity-suggest` (`value:"concept:xxx"`).
- **Géo entreprises** : `headquarters_department_code` / `headquarters_region_code` → **0** (ne pas
  utiliser). Utiliser **`headquarters_postal_code`** (exact 5 chiffres, pas de préfixe `"69"`) ou
  **`headquarters_city`** en **MAJUSCULES** (`"LYON"`, via `city-suggest`).
- **FIELD MAP `data` CONFIRMÉ** (et câblé dans `lead_to_prospect`) :
  - *companies* : `company_name`, `legal_name`, `siren`, `email` (générique), `phone` (`+33…`),
    `headquarters_city` (MAJ), `headquarters_postal_code`, `naf_code`, `naf_code_label`,
    `activity_domain`, `headcount_min/max`, `capital`, `legal_form`, `x_gmb{…}`. Pas de `website` à
    plat (parfois dans `x_gmb`).
  - *people* (dirigeants Legal via SIREN) : `result_first_name`, `result_last_name`, `result_city`,
    `result_age`, `siren`, `current_company_name`. **PAS d'email ni de phone.**
- **Rendement email** : ~15 % des sociétés ont un email, ~2 % net après validation. Dirigeants = 0
  email. → Basile = liste + nom + SIREN ; contactabilité réelle via **Emelia**.
- **Validateur** : `"basile"` ajouté à `LICIT_SOURCES` (`email_validator.py`) — sinon tout droppé
  `rgpd_source_non_publique`. Registre légal = source publique (décision RGPD à confirmer si besoin).

## 13. Go-live — reste à faire (UX + scale)

Reste après les tests ci-dessus :

1. **Clé** : `echo "BASILE_KEY=sk_live_xxx" >> /home/autoblog/genesis/.env`.
2. **Smoke test count** (gratuit) :
   ```bash
   python3 scripts/basile_backend.py count companies '{"naf_code":{"include":["56.10A"]},"company_ceased":false,"headquarters_department_code":{"include":["69"]}}'
   ```
3. **Vérifier le FIELD MAP** : faire un `find` brut et inspecter `leads[0].data` pour confirmer les
   vrais noms de champs (email, prenom/nom, role, siren, ville…). Ajuster `lead_to_prospect()` dans
   `scripts/basile_backend.py` (bloc « FIELD MAP — à confirmer »).
4. **Dry-run d'un segment** (compte + normalise, AUCUNE écriture) :
   ```bash
   python3 scripts/basile_backend.py segment people '<filters>' --site lcr --sector restaurant --dept 69
   ```
   → vérifier `samples` (3 prospects normalisés) + `rule.action`.
5. **Live d'une passe de 1 000** (`--live`) → vérifier l'insertion dans `scrappe_pending` ET le
   pool `contacts.duckdb` (`primary_source='basile'`), puis le drain Mailnjoy.
6. Crosscheck cette doc contre docs.basile.cc (filtres/limites à jour).
