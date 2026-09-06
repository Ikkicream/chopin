# Claude-Viz — Specs UX/UI pour Swarm Dashboard

## Analyse des screenshots claude-viz

### Ce que montre claude-viz (le projet dans les images)
C'est un dashboard temps-reel qui visualise un agent Claude Code et ses sub-agents pendant qu'ils travaillent. Il fonctionne via les **hooks Claude Code** (PreToolUse, PostToolUse, SubAgentStop) qui emettent des events captures par un serveur WebSocket, rendu dans un canvas HTML.

---

## COMPOSANTS UX/UI IDENTIFIES

### 1. GRAPH CENTRAL — Vue "Solar System"
**Ce qu'on voit** :
- Agent principal au centre (gros robot orange avec glow pulsant)
- Orbites concentriques autour (cercles gris subtils)
- Fichiers touches = noeuds bleus (icone type TS/MD/JSON + nom)
- Sub-agents = petits robots oranges/roses en peripherie
- Lignes de connexion colorees :
  - **Cyan** = lecture/tool call actif
  - **Violet** = lien sub-agent
  - **Jaune/Vert** = edit/write
- Badges sur les fichiers : compteur de fois touche (cercle rouge/bleu avec chiffre)
- Points colores sur les fichiers : vert=lu, jaune=modifie, rouge=erreur/test fail

**Effets visuels** :
- Glow orange chaud sur l'agent central (pulsation)
- Halo bleu sur les fichiers actifs
- Cercle violet autour de l'agent qui travaille (image 4)
- Lignes qui s'animent quand les donnees circulent
- Fond noir profond type "espace" avec grille subtile

### 2. TOP BAR — Status global
- **Token counter** : `72.0k / 1000.0k` (barre de progression)
- **Pourcentage** : `7.2%` (colore selon usage : vert<30%, jaune<70%, rouge>70%)
- **Modele** : `claude-opus-4-7[1m]`
- **Status connexion** : badge vert "connected"
- **Nom du projet** : `claude-viz`
- **Mode** : `LIVE DISPATCH`

### 3. SIDEBAR DROITE — Panels d'info

#### Panel SUB-AGENTS
- Liste des sub-agents spawnes
- Nom de chaque tache (ex: "Refactor auth module")
- Indicateur de statut (actif/termine/erreur)

#### Panel FILES SEEN
- Liste des fichiers touches par l'agent
- Points colores par statut :
  - Rouge = fichier test / erreur
  - Jaune = fichier modifie
  - Bleu = fichier lu
  - Vert = fichier cree
- Chemin relatif tronque avec `...`

#### Panel EVENT STREAM
- Flux temps-reel des events hook
- Format : `PRETOOLUSE` / `POSTTOOLUSE` / `SUBAGENTSTOP`
- Chemin du fichier ou commande
- Badge colore du type de tool : `WebFetch` (bleu), `Edit` (jaune), `Bash` (vert)

### 4. BOTTOM BAR — Legende + Terminal
- **Legende tools** : Read (bleu), Edit (jaune), Write (vert), Bash (orange), Grep (cyan), Sub-agent (violet), Web (rose)
- **Terminal LIVE** : mini terminal montrant la derniere commande bash en cours
- Indicateur `BASH - LIVE` avec cercle vert

---

## ADAPTATION POUR NOTRE SWARM

### Architecture du dashboard

```
┌─────────────────────────────────────────────────────────┐
│  TOP BAR                                                │
│  MKD | LCR  [switch]    Budget: $4.23/$20    Connected  │
├──────────────────────────────┬──────────────────────────┤
│                              │  SIDEBAR                 │
│   GRAPH CENTRAL              │                          │
│   (Solar System View)        │  [MODULES]               │
│                              │  Orchestrateur  running  │
│     ┌──── SEO ────┐         │  Content        idle     │
│     │              │         │  SEO            done     │
│     │   ┌──────┐   │         │  Outreach       idle     │
│   OUT──│ BOSS  │──CONT      │                          │
│  REACH │       │  ENT       │  [DERNIERE TACHE]        │
│     │   └──────┘   │         │  Article: sms-boulanger │
│     │              │         │  Status: publie          │
│     └── MEMORY ───┘         │  Cout: $0.08             │
│                              │  Duree: 3m 22s           │
│                              │                          │
│                              │  [EVENT STREAM]          │
│                              │  10:03 SEO → brief LCR  │
│                              │  10:05 Content → redige  │
│                              │  10:08 Content → publie  │
│                              │  10:09 Orchestr → report │
├──────────────────────────────┴──────────────────────────┤
│  BOTTOM : Data Table + Charts (toggle)                  │
│                                                          │
│  [TABLE VIEW]                                            │
│  Module    | Derniere tache      | Cout  | Statut       │
│  ──────────┼─────────────────────┼───────┼──────────    │
│  Content   | Article SMS boulang | $0.08 | OK           │
│  SEO       | Analyse Ahrefs W18  | $0.03 | OK           │
│  Outreach  | Post LinkedIn       | $0.02 | OK           │
│                                                          │
│  [CHART VIEW]                                            │
│  ▓▓▓▓▓▓░░░░ Cout/jour    ████░░ Articles publies       │
│  ▓▓░░░░░░░░ Tokens/module ████░░ Success rate           │
└─────────────────────────────────────────────────────────┘
```

### Les vues du dashboard

#### Vue 1 — LIVE GRAPH (comme claude-viz)
- Agent orchestrateur au centre avec glow
- 4 modules autour en orbite (Content, SEO, Outreach, Memory)
- Quand un module travaille : ligne animee + halo colore
- Fichiers/articles produits apparaissent comme noeuds
- Animations particules quand un article est publie

#### Vue 2 — DATA TABLE
- Tableau tri/filtre de tous les runs
- Colonnes : Date, Module, Site (MKD/LCR), Tache, Modele (Sonnet/Haiku/DeepSeek), Tokens, Cout, Statut, Duree
- Clic sur une ligne = detail du run (log lisible en markdown)
- Export CSV

#### Vue 3 — DATAVIZ / CHARTS
- **Cout par jour** : Line chart (7/30 jours)
- **Cout par module** : Donut chart (Content/SEO/Outreach/Orchestrateur)
- **Cout par site** : Bar chart (MKD vs LCR)
- **Articles publies** : Counter + calendar heatmap
- **Success rate** : Gauge (% de runs reussis)
- **Tokens usage** : Stacked bar (input vs output, par modele)
- **ROI** : Cout par article publie (target: < $1/article)

#### Vue 4 — AGENT DETAIL
- Clic sur un module dans le graph ou la table
- Instructions de l'agent (AGENTS.md rendu)
- Historique des runs (timeline)
- Metriques : cout total, articles produits, taux de succes
- Logs du dernier run (markdown lisible, pas JSON brut)

---

## SKILLS / FONCTIONS A IMPLEMENTER

### Skill 1 : `swarm-orchestrate`
```
Declencheur : cron lundi 6h UTC, ou commande Telegram
Input : site (mkd|lcr|both)
Fait :
  1. Consulte la memoire (articles publies, keywords cibles)
  2. Decide quoi faire cette semaine
  3. Route vers Content, SEO, ou Outreach
  4. Attend les resultats
  5. Log dans dashboard.json
  6. Envoie recap Telegram
```

### Skill 2 : `swarm-content`
```
Declencheur : appel de l'orchestrateur
Input : brief SEO + site cible
Modele : DeepSeek
Fait :
  1. Redige article (800-1200 mots, frontmatter, CTAs)
  2. Source image Unsplash
  3. Validation qualite (20 criteres)
  4. Publie sur WordPress (MKD) ou Emdash (LCR)
  5. Log cout + resultat
```

### Skill 3 : `swarm-seo`
```
Declencheur : appel de l'orchestrateur
Input : site cible
Modele : Haiku
Fait :
  1. Analyse Ahrefs (keywords, content gap)
  2. Analyse GSC (clics, impressions)
  3. Veille concurrents (RSS)
  4. Genere brief editorial
  5. Log cout + resultat
```

### Skill 4 : `swarm-outreach`
```
Declencheur : appel de l'orchestrateur
Input : type (linkedin|email|ads|newsletter) + site
Modele : DeepSeek
Fait :
  1. Redige le contenu (post, email, ad copy)
  2. Publie si API dispo (Zernio pour LinkedIn)
  3. Ou genere le draft pour validation humaine
  4. Log cout + resultat
```

### Skill 5 : `swarm-dashboard`
```
Declencheur : hook PostToolUse de chaque skill
Input : event data (module, tache, cout, statut, log)
Fait :
  1. Append dans dashboard.json
  2. Regenere le HTML statique du dashboard
  3. Servie par Nginx sur le VPS
```

### Skill 6 : `swarm-memory`
```
Declencheur : apres chaque run
Input : resultat du run
Fait :
  1. Met a jour articles-published.md
  2. Met a jour keywords-targeted.md
  3. Archive le rapport hebdo
  4. Maintient le contexte pour les prochains runs
```

### Skill 7 : `swarm-briefing`
```
Declencheur : cron chaque matin 8h Paris
Input : site (both)
Modele : Haiku
Fait :
  1. Resume activite des dernieres 24h
  2. Stats GSC si dispo
  3. Budget restant
  4. Envoie sur Telegram
```

### Skill 8 : `swarm-email-marketing`
```
Declencheur : appel de l'orchestrateur (1x/mois)
Input : site (mkd|lcr), articles du mois, liste subscribers
Modele : DeepSeek
API : Resend (newsletter broadcast)
Fait :
  1. Recupere les articles publies ce mois
  2. Redige la newsletter HTML (template + tone of voice du site)
  3. Insere les CTAs, images, liens articles
  4. Envoie via Resend API a la liste subscribers
  5. Log : taux ouverture, clics (si webhook Resend configure)
```

### Skill 9 : `swarm-cold-email`
```
Declencheur : appel de l'orchestrateur ou commande manuelle
Input : fichier CSV de prospection, template de campagne, site
Modele : Claude Sonnet (le ton humain EXIGE du raisonnement fin)
API : Mailnjoy MCP
Fait :
  1. Parse le CSV (colonnes: email, prenom, entreprise, poste, secteur, site_web, linkedin...)
  2. Pour CHAQUE prospect, genere un email 1-to-1 :
     - Icebreaker personnalise (scrape le site/LinkedIn du prospect, trouve un fait precis)
     - Pas de formules robotiques ("J'espere que vous allez bien", "Je me permets de...")
     - Ton direct, humain, conversationnel
     - Proposition de valeur adaptee au secteur du prospect
     - CTA simple (1 question, pas 3 liens)
     - Objet court et intriguant (pas de "Partenariat" ou "Opportunite")
  3. Genere les variantes A/B pour l'objet
  4. Preview pour validation humaine (ou envoi auto si flag --auto)
  5. Log : prospect, email envoye, variante, cout
```

### Skill 10 : `swarm-campaign-orchestrator`
```
Declencheur : commande manuelle ou cron
Input : campaign config (CSV, templates, sequences, timing)
Modele : Haiku (routing) + Sonnet (redaction icebreaker)
API : Mailnjoy MCP
Fait :
  1. Charge le CSV et segmente par :
     - Secteur (immobilier, artisan, commerce, restauration...)
     - Taille entreprise
     - Poste du contact (CEO, marketing, commercial)
  2. Selectionne le template de sequence adapte au segment :
     - Email 1 : Icebreaker + valeur (J+0)
     - Email 2 : Relance soft avec cas client (J+3)
     - Email 3 : Derniere relance avec urgence douce (J+7)
  3. Pour chaque prospect, appelle swarm-cold-email pour personnaliser
  4. Planifie l'envoi via Mailnjoy :
     - Throttling : max 50 emails/jour (delivrabilite)
     - Horaires : 9h-11h ou 14h-16h (taux ouverture max)
     - Evite lundi matin et vendredi apres-midi
  5. Tracking :
     - Ouvertures, clics, reponses (webhook Mailnjoy)
     - Auto-stop si taux bounce > 5%
     - Rapport quotidien dans le dashboard
  6. Log complet dans dashboard.json
```

### Regles cold email — TON ET STYLE

```
INTERDITS (detection automatique, rejet si present) :
- "J'espere que vous allez bien"
- "Je me permets de vous contacter"
- "N'hesitez pas a"
- "Cordialement" (utiliser "A bientot", prenom, ou rien)
- "Suite a notre dernier echange" (s'il n'y en a pas eu)
- Plus de 5 lignes par paragraphe
- Plus de 150 mots total
- Plus de 1 CTA
- Emojis dans l'objet
- "RE:" ou "FWD:" fake dans l'objet

OBLIGATOIRES :
- Icebreaker = 1 fait REEL sur le prospect (pas generique)
  Exemples OK :
    "J'ai vu que [entreprise] venait de lancer [produit] - le timing est parfait"
    "Votre post LinkedIn sur [sujet] m'a fait reagir"
    "Je travaille avec 3 [meme secteur] dans votre zone"
  Exemples KO :
    "Votre entreprise semble interessante"
    "En tant que professionnel du secteur"
- Max 3 phrases avant le CTA
- CTA = 1 question simple ("Un call de 15 min jeudi ?")
- Signature courte (prenom + poste + tel, pas de banniere HTML)
```

### Exemple email genere par le skill :

```
Objet : SMS geolocalise pour [ville] — 3 clients en ont parle

Salut [Prenom],

J'ai vu que [entreprise] avait 2 agences sur [ville] — c'est exactement 
le profil qui cartonne avec le SMS geolocalise (on a un [concurrent local] 
qui fait +40% de trafic en boutique avec ca).

Concretement : vos clients dans un rayon de 2km recoivent un SMS 
au bon moment. Pas de spam, que du cible.

Un call de 15 min pour voir si ca colle avec votre setup ?

[Prenom]
[Poste] — Le Client ROI
06 XX XX XX XX
```

---

## ARCHITECTURE EMAIL COMPLETE

```
                    ┌─────────────────────┐
                    │   ORCHESTRATEUR     │
                    │   (decide quoi      │
                    │    envoyer et quand) │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────┴──────┐  ┌─────┴──────┐  ┌─────┴──────────┐
    │ EMAIL MARKETING│  │ COLD EMAIL │  │ CAMPAIGN ORCH. │
    │ (newsletter)   │  │ (1-to-1)   │  │ (sequences)    │
    │ Resend API     │  │ Mailnjoy   │  │ Mailnjoy       │
    │ DeepSeek       │  │ Sonnet     │  │ Haiku+Sonnet   │
    └────────────────┘  └────────────┘  └────────────────┘
              │                │                │
              └────────────────┼────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │   FICHIER CSV       │
                    │   prospects.csv     │
                    │   + enrichissement  │
                    │   (scrape site/LI)  │
                    └─────────────────────┘
```

---

## TECH STACK DASHBOARD

### Frontend (statique, pas de framework)
- **HTML/CSS/JS** vanilla (pas de React, pas de build)
- **Canvas 2D** pour le graph solar system (ou Three.js pour le 3D)
- **Chart.js** pour les dataviz
- **CSS Grid** pour le layout responsive
- **CSS animations** pour les effets glow/pulse
- **WebSocket** (optionnel) pour le live, sinon polling JSON toutes les 10s

### Backend (minimal)
- **Fichier JSON** mis a jour par les hooks Claude Code
- **Nginx** sert le HTML + le JSON
- Pas de serveur Node/Python necessaire

### Effets visuels (inspires de claude-viz)
```css
/* Glow pulsant agent central */
@keyframes agent-pulse {
  0%, 100% { box-shadow: 0 0 20px rgba(255,165,0,0.6); }
  50% { box-shadow: 0 0 40px rgba(255,165,0,0.9); }
}

/* Ligne animee entre agents */
@keyframes flow-line {
  0% { stroke-dashoffset: 20; }
  100% { stroke-dashoffset: 0; }
}

/* Halo quand un module travaille */
@keyframes working-halo {
  0% { transform: scale(1); opacity: 0.8; }
  100% { transform: scale(1.5); opacity: 0; }
}

/* Particules quand article publie */
@keyframes publish-burst {
  0% { transform: scale(0); opacity: 1; }
  100% { transform: scale(3); opacity: 0; }
}
```

### Palette couleurs (dark theme comme claude-viz)
```
Background:     #0a0a0f (noir profond)
Surface:        #1a1a2e (panels sidebar)
Agent central:  #ff8c00 (orange chaud)
Content module: #00d4ff (cyan)
SEO module:     #6b46c1 (violet)
Outreach module:#22c55e (vert)
Memory:         #f59e0b (jaune)
Success:        #22c55e (vert)
Error:          #ef4444 (rouge)
Text primary:   #e2e8f0
Text secondary: #64748b
Grid/orbits:    #1e293b
```

---

## DONNEES DU DASHBOARD (schema JSON)

```json
{
  "meta": {
    "lastUpdate": "2026-05-05T10:09:00Z",
    "budgetTotal": 2000,
    "budgetSpent": 423,
    "budgetUnit": "cents"
  },
  "modules": [
    {
      "id": "orchestrator",
      "name": "Orchestrateur",
      "model": "claude-sonnet-4-6",
      "status": "idle",
      "color": "#ff8c00",
      "totalRuns": 12,
      "totalCost": 145,
      "successRate": 0.92
    },
    {
      "id": "content",
      "name": "Content",
      "model": "deepseek",
      "status": "running",
      "color": "#00d4ff",
      "totalRuns": 8,
      "totalCost": 89,
      "successRate": 0.88,
      "currentTask": "Article SMS boulangerie"
    }
  ],
  "runs": [
    {
      "id": "run_001",
      "date": "2026-05-05T10:03:00Z",
      "module": "content",
      "site": "lcr",
      "task": "Redaction article SMS boulangerie",
      "model": "deepseek",
      "tokensIn": 2400,
      "tokensOut": 1800,
      "costCents": 5,
      "duration": 202,
      "status": "success",
      "output": "Article publie: /blog/sms-boulangerie",
      "log": "Brief recu du SEO module\n→ Redaction 950 mots\n→ QC 19/20\n→ Image Unsplash OK\n→ Publie sur Emdash\n→ CTAs inseres"
    }
  ],
  "sites": {
    "mkd": {
      "articlesPublished": 6,
      "totalCost": 189,
      "lastArticle": "2026-04-22"
    },
    "lcr": {
      "articlesPublished": 264,
      "totalCost": 234,
      "lastArticle": "2026-04-30"
    }
  }
}
```
