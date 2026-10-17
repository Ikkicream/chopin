# Endpoints Basile API

Base : `https://api.basile.cc`
Auth : header `Authorization: <clé brute>` (pas de `Bearer`). `Content-Type: application/json`.

## Recherche & extraction

| Méthode | Route | Usage |
|---|---|---|
| POST | `/people/find` | Chercher des personnes. Body `{ filters, limit, paginationToken }`. Renvoie `{ success, total, leads, pagination }`. **Utiliser limit:1 pour compter.** |
| POST | `/people/export` | Export CSV personnes (consomme quota). Body `{ filters }` ou `{ ids:[...] }`. |
| POST | `/companies/find` | Chercher des entreprises. Même structure. |
| POST | `/companies/export` | Export CSV entreprises (consomme quota). |
| GET | `/people/:id` | Fiche brute d'une personne. |
| GET | `/people/:id/full` | Fiche enrichie complète (toutes colonnes). |
| GET | `/companies/:id` | Fiche brute d'une entreprise. |
| GET | `/companies/:id/full` | Fiche enrichie complète. |

## Suggestions / autocomplete (GET, `?q=` + `?limit=`)

Personnes :
`/people/cities/suggest` · `/people/companies/suggest` (employeurs) ·
`/people/roles/suggest` · `/people/skills/suggest` · `/people/languages/suggest` ·
`/people/education/suggest` · `/people/names/suggest` · `/people/nationalities/suggest` ·
`/people/age/bounds` · `/people/mandate-count/bounds` · `/people/seniorities` ·
`/people/tenure-buckets`

Entreprises :
`/companies/activity-suggest` (→ IDs concept pour `activity`) ·
`/companies/name-suggest` · `/companies/city-suggest` ·
`/companies/legal-form-suggest` · `/companies/siren-suggest`

## Gestion des clés API (session web requise, pas via clé API)

| Méthode | Route | Usage |
|---|---|---|
| GET | `/api-keys/` | Lister ses clés. |
| POST | `/api-keys/` | Créer une clé. Body `{ name? }`. Renvoie `rawKey` (UNE seule fois). Plan API requis. |
| DELETE | `/api-keys/:id` | Désactiver une clé. |

## Codes de réponse à connaître

| Code | Signification | Que faire |
|---|---|---|
| 200 | OK | — |
| 401 | `Unauthorized` | Clé API invalide/absente. Vérifier le header `Authorization`. |
| 402 | `subscription_required` | Pagination (page > 1) sans abonnement actif. |
| 403 | `api_plan_required` / `api_key_limit_reached` | Plan API requis pour générer une clé / quota de clés atteint. |
| 429 | `rate_limit_exceeded` / `daily_limit_exceeded` | Trop de requêtes. Respecter le header `Retry-After` (secondes). |
| 500 | erreur serveur | Réessayer. |

## Rate limits (selon le plan)

| Plan | req/seconde | req/minute | req/jour |
|---|---|---|---|
| `api` | 10 | 100 | 50 000 |
| `custom` | 1 000 | 1 000 | 100 000 |

Reset minute/jour en **UTC**. En cas de 429, attendre `Retry-After`.

## Limites d'export (par plan)

| Plan | Max par export | Quota mensuel |
|---|---|---|
| `api` | **20 000** | 250 000 |
| `custom` | **50 000** | 1 000 000 |
| `starter` | 5 000 | 100 000 |

**Aujourd'hui, les plans avec clé API sont à 20 000/export.** La vraie limite du
user est renvoyée en temps réel dans le header `X-Export-Max-Rows` ;
`X-Export-Capped: true` = il reste des résultats au-delà. 429
`export_limit_reached` si le quota mensuel est épuisé.

**Gros volumes / au-delà d'un export** : ⚠️ ne JAMAIS faire un seul `/export`
géant (il boucle par 100 en interne → timeout). Utiliser le script
`scripts/basile_search.py export …` qui bascule en **mode bulk** (collecte des IDs
via `/find` paginé, puis `/export` par lots `{ "ids": [...] }`, avec délai entre
appels + reprise sur 429). Pour dépasser le quota d'un export, découper aussi en
sous-segments (département, NAF, année, taille…). Ton : encourageant, jamais alarmiste.
