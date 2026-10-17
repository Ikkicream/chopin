# Exemples de requêtes Basile API

Base : `https://api.basile.cc` · Header : `Authorization: <clé brute>` + `Content-Type: application/json`

Tous les exemples utilisent `curl` ; adapter au besoin.

---

## 1. Compter avant d'extraire (TOUJOURS faire ça d'abord)

Combien de CEO en France ? (limit:1 → on lit juste `total`, gratuit)

```bash
curl -s https://api.basile.cc/people/find \
 -H "Authorization: $BASILE_KEY" -H "Content-Type: application/json" \
 -d '{
   "limit": 1,
   "filters": {
     "result_role": { "include": ["CEO","Chief Executive Officer","PDG","Président Directeur Général","Directeur Général","DG","Gérant","Managing Director"] },
     "result_country_code": { "include": ["FR"] },
     "hide_legal_entities": true
   }
 }'
# → lire .total dans la réponse
```

→ Annoncer le nombre factuellement, sans dramatiser. Si `total` ≤ 20 000 : un
export suffit, proposer de lancer. Si > 20 000 : prévoir plusieurs exports (tranches
de 20 000) ou affiner — présenté comme une simple logistique, jamais un blocage.

---

## 2. Personnes — dirigeants actifs d'un département (Legal)

Présidents/gérants actifs dans les Bouches-du-Rhône (13) :

```bash
curl -s https://api.basile.cc/people/find \
 -H "Authorization: $BASILE_KEY" -H "Content-Type: application/json" \
 -d '{
   "limit": 100,
   "filters": {
     "mandate_role": { "include": ["president","gerant"] },
     "result_is_current": true,
     "result_postal_code": { "include": ["13001","13002","13003"] }
   }
 }'
```

> Note : `result_postal_code` est exact. Pour "tout le 13", il vaut souvent mieux
> passer par la recherche **entreprises** filtrée par `headquarters_department_code`
> puis récupérer les dirigeants, ou lister plusieurs codes postaux.

---

## 3. Personnes — directeurs marketing (LinkedIn) par séniorité

```bash
curl -s https://api.basile.cc/people/find \
 -H "Authorization: $BASILE_KEY" -H "Content-Type: application/json" \
 -d '{
   "limit": 100,
   "filters": {
     "result_role": { "include": ["CMO","Chief Marketing Officer","Directeur Marketing","Responsable Marketing","Head of Marketing","VP Marketing"] },
     "current_seniority": { "include": ["C-Level","Director","VP","Head"] }
   }
 }'
```

---

## 4. Entreprises — artisans du bâtiment actifs (NAF) en Île-de-France

```bash
curl -s https://api.basile.cc/companies/find \
 -H "Authorization: $BASILE_KEY" -H "Content-Type: application/json" \
 -d '{
   "limit": 100,
   "filters": {
     "naf_code": { "include": ["41.x","42.x","43.x"] },
     "company_ceased": false,
     "headquarters_region_code": { "include": ["11"] }
   }
 }'
```

---

## 5. Entreprises — par métier via `activity` (concept)

Étape A — trouver l'ID de concept "boulangerie" :
```bash
curl -s "https://api.basile.cc/companies/activity-suggest?q=boulang" \
 -H "Authorization: $BASILE_KEY"
# → récupérer l'id du concept, ex. "boulangerie_patisserie"
```

Étape B — chercher avec :
```bash
curl -s https://api.basile.cc/companies/find \
 -H "Authorization: $BASILE_KEY" -H "Content-Type: application/json" \
 -d '{
   "limit": 100,
   "filters": {
     "activity": { "include": ["boulangerie_patisserie"] },
     "company_ceased": false
   }
 }'
```

---

## 6. Entreprises — commerces bien notés sur Google (GMB)

Restaurants avec note ≥ 4 et ≥ 50 avis :
```bash
curl -s https://api.basile.cc/companies/find \
 -H "Authorization: $BASILE_KEY" -H "Content-Type: application/json" \
 -d '{
   "limit": 100,
   "filters": {
     "activity": { "include": ["restaurant"] },
     "rating_min": 4,
     "reviews_min": 50
   }
 }'
```
> ⚠️ `rating_min`/`reviews_min` restreignent à la source GMB.

---

## 7. Entreprises — taille + secteur + capital

PME (10-250 sal.) en informatique, capital ≥ 50k€ :
```bash
curl -s https://api.basile.cc/companies/find \
 -H "Authorization: $BASILE_KEY" -H "Content-Type: application/json" \
 -d '{
   "limit": 100,
   "filters": {
     "naf_code": { "include": ["62.x"] },
     "headcount_min": 10, "headcount_max": 250,
     "capital_min": 50000,
     "company_ceased": false
   }
 }'
```

---

## 8. Exclure (exclude)

Tous les gérants SAUF dans le secteur de la coiffure, hors Paris :
```bash
curl -s https://api.basile.cc/people/find \
 -H "Authorization: $BASILE_KEY" -H "Content-Type: application/json" \
 -d '{
   "limit": 1,
   "filters": {
     "mandate_role": { "include": ["gerant"] },
     "result_city": { "exclude": ["Paris"] }
   }
 }'
```

---

## 8b. Personnes par SECTEUR/type d'entreprise — workflow 2 étapes (OBLIGATOIRE)

⛔ Pas de filtre secteur fiable côté personnes. Pour « des dirigeants dans le BTP » :

**Étape 1 — les entreprises du secteur** (récupérer siren + nom) :
```bash
curl -s https://api.basile.cc/companies/find \
 -H "Authorization: $BASILE_KEY" -H "Content-Type: application/json" \
 -d '{
   "limit": 100,
   "filters": {
     "naf_code": { "include": ["41.x","42.x","43.x"] },
     "company_ceased": false,
     "headquarters_department_code": { "include": ["69"] }
   }
 }'
# → dans chaque lead : data.siren et data.legal_name / data.company_name
```

**Étape 2a — les DIRIGEANTS de ces entreprises** (par SIREN, précis) :
```bash
curl -s https://api.basile.cc/people/find \
 -H "Authorization: $BASILE_KEY" -H "Content-Type: application/json" \
 -d '{
   "limit": 100,
   "filters": {
     "siren": { "include": ["552100554","443061841","..."] },
     "result_is_current": true
   }
 }'
```

**Étape 2b — les SALARIÉS LinkedIn de ces entreprises** (par nom) :
```bash
curl -s https://api.basile.cc/people/find \
 -H "Authorization: $BASILE_KEY" -H "Content-Type: application/json" \
 -d '{
   "limit": 100,
   "filters": {
     "employer": { "include": ["Bouygues Construction","Eiffage"] },
     "result_role": { "include": ["Conducteur de travaux","Chef de chantier"] }
   }
 }'
```
> 💡 Compter les entreprises d'abord (étape 1, `limit:1`). Si > quelques centaines,
> affiner avant de réinjecter les SIREN/noms.

---

## 9. Pagination (page suivante)

```bash
# 1re page → récupérer pagination.nextToken
# page suivante :
curl -s https://api.basile.cc/people/find \
 -H "Authorization: $BASILE_KEY" -H "Content-Type: application/json" \
 -d '{ "limit": 100, "paginationToken": "<nextToken>", "filters": { ... } }'
```
> ⚠️ Page > 1 nécessite un abonnement actif (sinon HTTP 402).

---

## 10. Export CSV (jusqu'à 20 000/export sur le plan API)

Même `filters` que le find ; renvoie un CSV enrichi. Confirmer le total avant
(ton neutre, pas de dramatisation). Après l'export, proposer de **retravailler le
fichier** (retirer hors-cible, dédoublonner, prioriser) — voir SKILL.md.
```bash
curl -s https://api.basile.cc/people/export \
 -H "Authorization: $BASILE_KEY" -H "Content-Type: application/json" \
 -d '{ "filters": { ... } }' -o export.csv
```
Ou export d'une sélection d'IDs :
```bash
curl -s https://api.basile.cc/people/export \
 -H "Authorization: $BASILE_KEY" -H "Content-Type: application/json" \
 -d '{ "ids": ["id1","id2","id3"] }' -o export.csv
```
Headers de réponse utiles : `X-Export-Max-Rows`, `X-Export-Capped: true` (si tronqué).
