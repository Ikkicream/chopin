# /campaign-plan — LCR leclientroi.com — Partir de 0

## Objectif
Générer des leads qualifiés (PME françaises) pour leclientroi.com via cold email + LinkedIn, en utilisant Emelia à 100% de ses capacités.

## Cible

### Segments prioritaires (PME françaises, 2-50 employés)

| Segment | Profil type | Douleur | Proposition LCR |
|---|---|---|---|
| **Restaurants/Bars** | Gérant, 1-10 employés, quartier | Remplir les créneaux creux | SMS géolocalisé rayon 2km, promo flash midi |
| **Commerces locaux** | Propriétaire boutique, centre-ville | Trafic en baisse face au online | SMS drive-to-store, fidélisation |
| **Artisans** | Plombier, serrurier, électricien | Pas de visibilité digitale | SMS pour rappels RDV, avis clients |
| **Immobilier** | Agent immo, indépendant ou agence | Relancer les mandats froids | SMS pour nouvelles annonces, journées portes ouvertes |
| **Salons beauté/coiffure** | Gérant(e), 1-5 employés | No-shows, créneaux vides | SMS rappel RDV + promo dernière minute |

### Persona décideur
- Poste : Gérant, Propriétaire, Directeur, Responsable marketing
- Pas de DPO, pas de DSI → ce sont des PME, c'est le boss qui décide
- Langage : direct, concret, pas de jargon technique
- Motivé par : plus de clients, moins de no-shows, ROI immédiat

---

## Prérequis avant lancement

### 1. Domaine d'envoi (CRITIQUE)
- [ ] NE PAS utiliser leclientroi.com pour le cold email
- [ ] Acheter un domaine dédié (ex: `lcr-contact.com` ou `leclientroi.fr`)
- [ ] Configurer SPF + DKIM + DMARC sur le nouveau domaine
- [ ] Créer 3-5 boîtes mail (camille@lcr-contact.com, contact@lcr-contact.com, etc.)
- [ ] Connecter les boîtes dans Emelia
- [ ] Activer le warmup → **attendre 2-4 semaines**

### 2. Tracking domain
- [ ] Ajouter CNAME : `track.lcr-contact.com` → `emelia.link`

### 3. LinkedIn
- [ ] Connecter 1 compte LinkedIn dans Emelia (plan Start = 1 compte)

### 4. API key Emelia
- [ ] Récupérer sur https://app.emelia.io/settings/api
- [ ] Ajouter EMELIA_API_KEY dans le .env Genesis

---

## Stratégie de prospection

### Phase 1 — Warmup (semaines 1-3) — $0
- Warmup des boîtes mail via Emelia (automatique)
- Pendant ce temps : préparer les listes et rédiger les séquences
- Objectif : délivrabilité 70%+ en inbox

### Phase 2 — Test petit volume (semaine 4) — 50 prospects
- 1 segment test : **Restaurants Île-de-France**
- 50 prospects max (10/jour sur 5 jours)
- Séquence 3 emails
- Mesurer : taux d'ouverture, réponses, bounces
- Si >50% ouverture et <3% bounce → passer en phase 3

### Phase 3 — Scale progressif (semaines 5-8) — 200-500 prospects
- Ouvrir les 5 segments en parallèle
- 30 prospects/jour par boîte × 3 boîtes = 90 prospects/jour
- Campagnes A/B test sur les objets
- LinkedIn en parallèle (visite profil + connexion + message)

### Phase 4 — Automatisation complète (semaine 9+)
- L'agent Genesis gère tout : génération de listes, personnalisation, envoi, monitoring
- Rapport hebdomadaire sur Telegram
- Réponses positives → ajout Twenty CRM automatique

---

## Séquence email type — Segment "Restaurants"

### Email 1 (J+0) — Icebreaker + valeur
**Objet A** : `{{field1}} + SMS géolocalisé = clients en plus dès lundi`
**Objet B** : `Question rapide pour {{field1}}`

```
Salut {{firstName}},

J'ai vu que {{field1}} était sur [ville] — on travaille avec 3 restos
dans le coin qui utilisent le SMS géolocalisé pour remplir les créneaux 
creux (mardi/mercredi midi notamment).

Le principe : tes clients dans un rayon de 2km reçoivent un SMS au bon 
moment. Pas de spam, que du ciblé. Un resto sur [ville] a fait +40% de 
couverts le mardi avec ça.

Dispo 15 min cette semaine ?
https://tidycal.com/1rr6kv1/15-minute-meeting

Juliette
Le Client ROI — SMS marketing géolocalisé
contact@leclientroi.com
leclientroi.com
```

### Email 2 (J+3) — Relance soft
```
{{firstName}},

Je relance vite — j'imagine que t'es sous l'eau avec le service.

Juste pour te dire qu'on a sorti un guide gratuit sur le SMS marketing 
pour les restaurateurs : https://leclientroi.com/guides

Si tu veux tester sur {{field1}} sans engagement, on peut se caler 
un call de 15 min :
https://tidycal.com/1rr6kv1/15-minute-meeting

Juliette
Le Client ROI
contact@leclientroi.com
```

### Email 3 (J+7) — Dernière relance
```
{{firstName}},

Dernier message — si c'est pas le bon moment, aucun souci.

Je te laisse le lien vers notre livre blanc si jamais tu veux creuser 
le sujet plus tard :
https://ik.imagekit.io/rgpdsimplement/Libreblanc.pdf

Sinon, tu peux toujours booker un call quand tu veux :
https://tidycal.com/1rr6kv1/15-minute-meeting

Bonne continuation avec {{field1}}.

Juliette
Le Client ROI
contact@leclientroi.com
```

### Liens obligatoires dans chaque séquence

| Élément | URL | Quand |
|---|---|---|
| **Booking démo** | https://tidycal.com/1rr6kv1/15-minute-meeting | CTA dans chaque email |
| **Site LCR** | https://leclientroi.com/ | Signature |
| **Email contact** | contact@leclientroi.com | Signature |
| **Guide gratuit** | https://leclientroi.com/guides | Email 2 (relance) |
| **Livre blanc PDF** | https://ik.imagekit.io/rgpdsimplement/Libreblanc.pdf | Email 3 (dernière relance) |

### Expéditeur & Signature
- **Expéditeur** : juliette@leclientroi.com (connectée dans Emelia)
- **Signature** :
```
Juliette
Le Client ROI — SMS marketing géolocalisé
contact@leclientroi.com
leclientroi.com
```

---

## Sourcing des prospects

### Méthode unique — CSV fourni par l'utilisateur
```
L'utilisateur fournit le fichier CSV de prospection.

Format attendu :
email,firstName,lastName,field1,field2
jean.dupont@restaurant.com,Jean,Dupont,Le Petit Bistrot,Gérant

L'agent :
  1. Parse le CSV
  2. Segmente par secteur/ville/poste (colonnes field1, field2)
  3. Vérifie les emails via Emelia (POST /tools/verify-email)
  4. Supprime les invalides/bounces probables
  5. Génère un icebreaker personnalisé par prospect (Claude Sonnet)
  6. Injecte les contacts dans la campagne Emelia
```

### Colonnes CSV supportées (format flexible)

**Format CSV actuel (prospects.csv — 79 263 contacts) :**
```
EMAIL STATUS;EMAIL OCCURRENCE FOUND;EMAIL CLASSIFICATION HELPER;email
valid;unique;B2B (domain);prenom.nom@entreprise.com
```
- Séparateur : `;`
- 4 colonnes : status, occurrence, classification, email
- Pas de prénom/nom/entreprise en colonnes séparées
- **L'agent doit extraire le prénom/nom/entreprise depuis l'adresse email et le domaine**

**Profil des contacts :**
- 79 263 contacts B2B vérifiés (status=valid)
- 23 383 domaines uniques
- Majoritairement grands groupes français (Orange, L'Oréal, BNP, Carrefour, Total, Capgemini...)
- À segmenter intelligemment pour LCR (cibler les contacts pertinents SMS marketing)

**Enrichissement par l'agent :**
```
Email : j.dupont@carrefour.com
  → Prénom probable : J.
  → Domaine : carrefour.com
  → Entreprise : Carrefour
  → Scrape carrefour.com pour icebreaker contextualisé
  → Field1 dans Emelia : "Carrefour"
  → Field2 dans Emelia : poste (si trouvé via scrape)
```

**Format idéal (si CSV enrichi fourni plus tard) :**
| Colonne | Requis | Usage |
|---|---|---|
| email | ✅ | Adresse email du prospect |
| firstName | ✅ | Prénom (personnalisation) |
| lastName | ✅ | Nom |
| field1 | ✅ | Nom de l'entreprise ({{field1}} dans les templates) |
| field2 | Optionnel | Poste / Secteur / Ville |
| site_web | Optionnel | URL du site (pour scraper l'icebreaker) |
| linkedin_url | Optionnel | Profil LinkedIn |
| notes | Optionnel | Notes manuelles |

---

## KPIs de suivi

| Métrique | Cible | Action si hors cible |
|---|---|---|
| Taux d'ouverture | >50% | Revoir les objets, vérifier warmup |
| Taux de réponse | >5% | Revoir le copywriting, l'icebreaker |
| Taux de bounce | <3% | Améliorer la vérification email |
| Taux de plainte | <0.1% | Ralentir le volume, revoir le ciblage |
| RDV bookés | >2%  | Affiner le CTA, le segment |
| Coût par RDV | <5€ | Optimiser les segments rentables |

---

## Budget Emelia

| Poste | Coût estimé |
|---|---|
| Plan Start | 37€/mois |
| Crédits email finder (1000) | 19€ (one-time) |
| Domaine dédié | ~10€/an |
| **Total démarrage** | **~66€** |
| **Coût mensuel récurrent** | **37€/mois** |

---

## Intégration avec Genesis

```
Agent swarm-campaign :
  1. Charge le CSV ou lance le scraper LinkedIn
  2. Vérifie les emails via Emelia API
  3. Génère les icebreakers personnalisés via Claude Sonnet
  4. Crée la campagne + steps + contacts via Emelia API
  5. Lance la campagne
  6. Monitoring quotidien via Emelia stats API
  7. Réponses positives → alerte Telegram + ajout Twenty CRM
  8. Rapport hebdomadaire dans le dashboard Genesis
```

**Emelia fait** : envoi, warmup, tracking, A/B test, bounces, SpinText, verify email
**Claude fait** : parser le CSV, segmenter, icebreaker personnalisé, analyse des réponses, orchestration
**L'utilisateur fait** : fournir le CSV, acheter le domaine, valider les séquences
**Pas de doublon** : chacun fait ce qu'il fait le mieux
