# Pipeline enrichissement CSV — 0 coût

## Input
`context/shared/prospects.csv` — 79 263 contacts B2B
Format : `EMAIL STATUS;EMAIL OCCURRENCE FOUND;EMAIL CLASSIFICATION HELPER;email`

## Étape 1 — Parsing email (script Python, 0 API)

Extraire prénom, nom, entreprise depuis le format de l'email :

```
j.dupont@carrefour.com      → J. Dupont, Carrefour
a.abitbol@autobernard.com   → A. Abitbol, Auto Bernard
aaffelou@afflelou.net       → A. Affelou, Afflelou
prenom.nom@entreprise.com   → Prenom Nom, Entreprise
pnom@entreprise.com         → P. Nom, Entreprise
```

### Patterns de parsing (ordre de priorité)
1. `prenom.nom@domain` → split sur `.` → firstName=prenom, lastName=nom
2. `p.nom@domain` → firstName=P., lastName=nom
3. `pnom@domain` → firstName=p (1ère lettre), lastName=nom (reste)
4. `prenom-nom@domain` → split sur `-`
5. `prenom_nom@domain` → split sur `_`
6. `prenomnom@domain` → heuristique (moins fiable, flag pour review)

### Extraction entreprise depuis le domaine
- Supprimer le TLD (.com, .fr, .net, .org, .io, .eu...)
- Supprimer les sous-domaines (mail., smtp., etc.)
- Capitaliser : `carrefour` → `Carrefour`, `bnpparibas` → `BNP Paribas`
- Mapping connu pour les gros groupes (dictionnaire)

### Output
CSV enrichi : `email;firstName;lastName;company;domain;confidence`
- confidence : high (pattern 1-2), medium (pattern 3-5), low (pattern 6)

### Taux attendu
- ~80% en high/medium confidence
- ~15% en low confidence
- ~5% non parsable (emails génériques type info@, contact@, aa@)

## Étape 2 — OSINT open source (top prospects uniquement)

Pour les 200-500 contacts prioritaires sélectionnés pour la campagne :

### CrossLinked (github.com/m8sec/CrossLinked)
```bash
pip install crosslinked
crosslinked -f '{first}.{last}@{domain}' "Carrefour" -o carrefour_employees.csv
```
- Enum LinkedIn par entreprise sans API
- Valide que le contact existe réellement sur LinkedIn
- Gratuit, pas de rate limit dur

### Poastal (github.com/jakecreps/poastal)
```bash
pip install poastal
poastal -e j.dupont@carrefour.com
```
- Retourne le nom associé à l'email
- Vérifie l'existence sur les réseaux sociaux
- Gratuit

### Buster (github.com/sham00n/buster)
```bash
pip install buster
buster -e j.dupont@carrefour.com
```
- Email → nom, infos associées, réseaux
- Gratuit

### Usage dans Genesis
L'agent lance ces outils uniquement sur les contacts sélectionnés pour une campagne (200-500 max), pas sur les 79K.

## Étape 3 — Scrape site web entreprise (icebreaker)

Pour chaque prospect dans la campagne :
```bash
curl -s https://carrefour.com | head -100
```
- Extraire : actualités, produits, baseline, valeurs
- L'agent Claude Sonnet génère l'icebreaker à partir de ces infos
- Gratuit, pas d'API

## Résumé pipeline

```
prospects.csv (79K emails bruts)
  │
  ├── Étape 1 : Python parse → CSV enrichi (prénom/nom/entreprise)
  │   → 0 coût, 100% des contacts, ~80% fiable
  │
  ├── Agent sélectionne 200-500 contacts pour campagne
  │
  ├── Étape 2 : OSINT (CrossLinked/Poastal/Buster) → validation + poste
  │   → 0 coût, uniquement top prospects
  │
  ├── Étape 3 : Scrape site web → contexte pour icebreaker
  │   → 0 coût, curl gratuit
  │
  └── Inject dans Emelia → campagne personnalisée
```

## Outils à installer sur le VPS
```bash
pip install crosslinked poastal buster
```

## Filtrage du CSV pour LCR

Les 79K contacts sont majoritairement des grands groupes. Pour LCR (SMS marketing PME), filtrer :
- Exclure les domaines >500 contacts (Orange, L'Oréal, BNP... = pas la cible PME)
- Garder les domaines 1-10 contacts (PME, artisans, commerces)
- Prioriser les domaines .fr (marché français)
- Prioriser les secteurs : retail, restauration, services, immobilier

Pour MKD (data marketing B2B), les grands groupes SONT la cible :
- Garder les domaines >50 contacts (grands comptes)
- Cibler les contacts avec pattern DPO, data, marketing, digital dans le domaine
