# Filtres `POST /companies/find`

Body : `{ "filters": { ... }, "limit": 100, "paginationToken": "..." }`

Chaque filtre texte = `{ "include": [...], "exclude": [...] }`.
Chaque filtre numérique = un champ `_min` / `_max` simple (nombre), PAS un objet range.
Plusieurs filtres = **ET**. `include` = OR ; `exclude` = NOT.

Trois sources : **Legal** (registre/INSEE), **LKI** (LinkedIn), **GMB** (Google My
Business). Certains filtres restreignent à une/des source(s).

## Filtres généraux (multi-sources)

| Filtre | Ce que ça fait | Matching | Source |
|---|---|---|---|
| `keyword` | Recherche large (nom + description + spécialités…) | full-text + contains | les 3 |
| `name` | Nom d'entreprise (contains) | contains | les 3 |
| `activity` | **Métier unifié** : IDs de concept expansés en NAF + catégories Google + industries LinkedIn. Le plus puissant pour cibler un secteur | concept | les 3 |

## Filtres Legal uniquement

| Filtre | Ce que ça fait | Matching |
|---|---|---|
| `naf_code` | Code(s) NAF. Préfixe possible avec `.x` (ex. `"41.x"` = tout le 41) | exact / wildcard préfixe |
| `headquarters_naf_code` | NAF du siège | exact |
| `headquarters_department_code` | Département du siège (ex. `75`, `13`) | exact |
| `headquarters_region_code` | Région du siège | exact |
| `headquarters_postal_code` | Code postal du siège | exact |
| `legal_form` | Forme juridique (texte, ex. "SAS, société par actions simplifiée") | exact |
| `legal_category` | Code catégorie juridique INSEE (ex. `5710`=SAS). Voir legal_categories.json | exact |
| `siren` | SIREN exact | exact |
| `capital_min` / `capital_max` | Capital social (€) | range |
| `publishable` | `true`/`false` (diffusable) | booléen |
| `creation_date_min` / `creation_date_max` | Année de création (ex. `"2015"`) | range années |

## Filtres Legal + LKI (excluent GMB)

| Filtre | Ce que ça fait | Matching |
|---|---|---|
| `headquarters_city` | Ville du siège | exact |
| `headquarters_country_code` | Code pays (ex. `FR`) | exact |
| `headcount_min` / `headcount_max` | Effectif (nb salariés). Chevauchement de bande | range |

## Filtre spécial : actif/cessé

| Filtre | Valeur | Effet |
|---|---|---|
| `company_ceased` | `false` (recommandé) | garde uniquement les entreprises **actives** (basé sur le statut consolidé). `true` = uniquement cessées. **Mettre `false` par défaut.** |

## Filtres LinkedIn uniquement

⚠️ `industry_main` et `company_type` viennent de LinkedIn et sont **lacunaires/peu
fiables** (et restreignent à la source LKI). Pour cibler un **secteur**, préférer
**`activity`** (concept unifié) ou **`naf_code`** (registre, fiable). N'utiliser
`industry_main`/`company_type` qu'en complément, jamais comme filtre secteur principal.

| Filtre | Ce que ça fait | Matching |
|---|---|---|
| `industry_main` | Secteur LinkedIn (peu fiable — voir avertissement) | exact |
| `company_type` | Type (ex. "Privately Held", "Public Company") — peu fiable | exact |
| `domain` | Domaine web (contains) | contains |
| `followers_min` / `followers_max` | Taille/followers de la page LinkedIn | range |

## Filtres Google My Business uniquement

| Filtre | Ce que ça fait | Matching |
|---|---|---|
| `rating_min` / `rating_max` | Note Google (0–5) | range |
| `reviews_min` / `reviews_max` | Nombre d'avis Google | range |
| `is_opening` | `true` : ouvert le dimanche | booléen |

## Filtres de pilotage de source

| Filtre | Valeur | Effet |
|---|---|---|
| `source` | `"Legal"`, `"LKI"` ou `"GMB"` | force une seule source |
| `with_legal_data` | `true` | registre seulement |
| `with_linkedin_page` | `true` | LinkedIn seulement |

## Bonnes pratiques

- **Cibler un métier** : préférer `activity` (utiliser `GET /companies/activity-suggest?q=...`
  pour récupérer l'ID de concept). Sinon `naf_code` direct (ex. bâtiment =
  `{ "include": ["41.x","42.x","43.x"] }` — wildcard préfixe).
- **Entreprises actives** : `"company_ceased": false`.
- **France** : `headquarters_country_code: { "include": ["FR"] }` ou filtrer par
  `headquarters_department_code` / `headquarters_postal_code`.
- **Commerces locaux à fort contact tél** : filtrer `activity` + `rating_min`
  (GMB) → mais attention, ça restreint à GMB.
- **Combiner taille + métier + géo** : `activity` + `headcount_min/max` +
  `headquarters_department_code`.

## Routes de suggestion (autocomplete) — GET

- `/companies/activity-suggest?q=` (→ IDs de concept pour `activity`)
- `/companies/name-suggest?q=`
- `/companies/city-suggest?q=`
- `/companies/legal-form-suggest?q=`
- `/companies/siren-suggest?q=`

## Fiche complète d'une entreprise

`GET /companies/:id/full` → toutes les colonnes (légal + LinkedIn + GMB + contacts).
