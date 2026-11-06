# Architecture v2 — Genesis Swarm Agents

## Contexte
Paperclip coûtait $735+ pour 28 agents crashant 74% du temps. Genesis le remplace par une architecture Claude Code native : swarm agents, routage multi-modèle (Sonnet/Haiku/DeepSeek), Emelia pour le cold email + LinkedIn, dashboard agent-flow, et contrôle à distance depuis téléphone.

## Ce qu'on garde de Paperclip
- Instructions agents (prompts, templates, chartes graphiques)
- Credentials API (Telegram, Unsplash, Ahrefs MCP, Twenty CRM, Emdash)
- Bibliothèque images ImageKit (LCR)
- CTAs, mockups CSS, templates frontmatter
- Goals business des 2 sites
- 228 articles .md backlog LCR
- Mémoire agents (CEO memory, CI reports, etc.)

---

## LES 2 PROJETS

### MKD — mkdgroupe.com (WordPress)
- **Business** : Blog B2B — marketing data, RGPD, RCS, SMS pro
- **CMS** : WordPress (WP_SITE_URL=https://mkdgroupe.com)
- **APIs** : Telegram, Unsplash, Higgsfield, Twenty CRM, Emelia
- **Credentials** : ✅ Tous fournis (WP_USERNAME, WP_APP_PASSWORD)

### LCR — leclientroi.com (Emdash CMS)
- **Business** : Blog SEO — SMS marketing local, géolocalisé, RCS, drive-to-store
- **CMS** : Emdash (localhost:4321)
- **APIs** : Telegram, Unsplash, Ahrefs MCP, ImageKit, Emelia
- **228 articles .md** en backlog dans /home/autoblog/blog/articles/
- **Priorité** : campagne cold email PME via Emelia

---

## GOALS

### MKD — mkdgroupe.com
1. **Content SEO** : 1 article/semaine sur WordPress (RGPD, data marketing, RCS)
2. **LinkedIn** : 1 post/semaine via Emelia LinkedIn campaigns
3. **Newsletter** : 1/mois via Resend (quand configuré)
4. **Cold Email B2B** : Prospection DPO/DSI via Emelia (CSV fourni)
5. **Ads Meta** : Créatives + copy (optionnel phase 3)

### LCR — leclientroi.com (PRIORITÉ)
1. **SEO #1 France** : SMS marketing, RCS, location données géolocalisées
2. **Content SEO** : 1 article/semaine sur Emdash
3. **Publication backlog** : 228 articles Arvow (1/jour max)
4. **Cold Email PME** : Campagnes Emelia ciblant restaurants, commerces, artisans, immo, beauté
5. **LinkedIn** : 1 post/semaine via Emelia LinkedIn campaigns
6. **Ads Meta** : Créatives + copy (optionnel phase 3)

---

## ARCHITECTURE

```
TON TÉLÉPHONE (Remote Control / push notifs)
    │
    ▼
VPS 204.168.186.159 — tmux "genesis"
    │
    ├── Claude Code (session persistante 24/7)
    │   ├── claude-code-router → DeepSeek / Haiku / Sonnet
    │   ├── Agent Teams natif (TeammateTool)
    │   ├── /schedule → crons automatiques
    │   └── 10 skills métier (ci-dessous)
    │
    ├── Outils installés (0 code) :
    │   ├── agent-flow → graph live agents (claude-viz)
    │   ├── agents-observe → observabilité / logs
    │   └── claude-usage → cost tracking
    │
    ├── APIs externes :
    │   ├── Emelia → cold email + LinkedIn + verify + warmup
    │   ├── Ahrefs MCP → SEO analysis
    │   ├── Emdash → CMS LCR (localhost:4321)
    │   ├── WordPress → CMS MKD (mkdgroupe.com)
    │   ├── Telegram → notifications + commandes
    │   ├── Unsplash → images articles
    │   └── Twenty CRM → gestion contacts
    │
    └── Dashboard :
        ├── agent-flow → graph temps-réel
        ├── agents-observe → debug / logs
        ├── claude-usage → coûts tokens
        └── custom → dataviz métier (Chart.js)
```

---

## LES 10 SKILLS

### 1. `swarm-orchestrate` — Le Boss
- **Modèle** : Claude Sonnet
- **Déclencheur** : cron lundi 6h UTC, ou commande Telegram/Remote Control
- **Fait** : Consulte la mémoire, décide quoi faire, route vers les bons agents, reporting Telegram
- **Coût** : ~$2-4/semaine

### 2. `swarm-content` — Rédaction & Publication
- **Modèle** : DeepSeek (via claude-code-router)
- **APIs** : WordPress API (MKD), Emdash API (LCR), Unsplash
- **Fait** : Rédige articles SEO (800-1200 mots, frontmatter, CTAs, mockups CSS), validation qualité 20 critères, source images, publie
- **Coût** : ~$0.20-0.50/article

### 3. `swarm-seo` — Analyse & Stratégie
- **Modèle** : Claude Haiku
- **APIs** : Ahrefs MCP (quota 3000 crédits/mois LCR), GSC
- **Fait** : Keywords analysis, content gap, veille concurrents RSS, audit hebdo, brief éditorial
- **Coût** : ~$0.50-1/semaine

### 4. `swarm-outreach` — LinkedIn & Ads
- **Modèle** : DeepSeek
- **API** : Emelia LinkedIn Campaigns API
- **Fait** : Rédige posts LinkedIn (1/semaine par site), prépare copy Meta Ads, publie via Emelia
- **Coût** : ~$0.10-0.30/semaine

### 5. `swarm-email-marketing` — Newsletter
- **Modèle** : DeepSeek
- **API** : Resend (quand configuré) OU Emelia email campaigns
- **Fait** : Newsletter mensuelle (articles du mois, CTAs, images), templates HTML
- **Coût** : ~$0.10-0.20/envoi

### 6. `swarm-cold-email` — Prospection 1-to-1
- **Modèle** : Claude Sonnet (icebreaker humain exige du raisonnement)
- **API** : Emelia REST API (campagnes email)
- **Input** : CSV fourni par l'utilisateur
- **Fait** :
  - Parse le CSV, segmente par secteur/ville/poste
  - Vérifie les emails via Emelia verify-email
  - Génère un icebreaker personnalisé par prospect (scrape site_web/linkedin si fourni)
  - Ton humain obligatoire (voir cold-email-rules.md)
  - Anti-patterns détectés et rejetés automatiquement
- **Ne fait PAS** : email finder (le CSV est fourni complet)
- **Coût** : ~$0.02-0.05/email

### 7. `swarm-campaign` — Orchestration campagnes Emelia
- **Modèle** : Haiku (routing) + Sonnet (via swarm-cold-email)
- **API** : Emelia REST API (71 endpoints)
- **Fait** :
  - Crée la campagne dans Emelia (POST /emails/campaigns)
  - Configure les steps/séquences (3 emails : J+0, J+3, J+7, avec variantes A/B)
  - Injecte les contacts personnalisés (POST /emails/campaign/contacts)
  - Démarre la campagne (POST .../start)
  - Monitoring quotidien stats (GET .../statistics)
  - Pause auto si bounce > 5%
  - Réponses positives → alerte Telegram + ajout Twenty CRM
- **Emelia gère nativement** : envoi, warmup, tracking, SpinText, bounces, A/B test
- **Claude gère** : icebreaker, segmentation, décisions, analyse réponses
- **Coût** : ~$1-3/campagne de 100 prospects

### 8. `swarm-briefing` — Rapport quotidien
- **Modèle** : Claude Haiku
- **API** : Telegram
- **Déclencheur** : cron chaque matin 8h Paris
- **Fait** : Résumé activité 24h, stats GSC, budget restant (Anthropic + DeepSeek), alertes
- **Coût** : ~$0.01/jour

### 9. `swarm-memory` — RAG / Base de connaissance
- **Tech** : Fichiers markdown (pas de base vectorielle)
- **Fait** : Met à jour articles-published.md, keywords-targeted.md, archive rapports, maintient le contexte
- **Structure** :
  ```
  memory/
  ├── mkd/
  │   ├── articles-published.md
  │   ├── keywords-targeted.md
  │   ├── competitors.md
  │   ├── brand-guide.md
  │   └── weekly-reports/
  ├── lcr/
  │   ├── articles-published.md
  │   ├── articles-backlog.md      # 228 .md Arvow
  │   ├── keywords-targeted.md
  │   ├── brand-guide.md
  │   ├── campaign-results.md      # résultats campagnes Emelia
  │   └── weekly-reports/
  └── shared/
      ├── costs-log.json
      └── agent-logs/
  ```

### 10. `swarm-dashboard` — Génération dashboard
- **Tech** : Hooks Claude Code → JSON → HTML statique
- **Fait** : Append les runs dans data.json, régénère la page HTML
- **Inclut** : page health check (connexions live + crédits Anthropic/DeepSeek quotidien)

---

## ROUTAGE MODÈLES (claude-code-router)

| Tâche | Modèle | Pourquoi | Coût/run |
|---|---|---|---|
| Orchestration, décisions | Sonnet | Raisonnement complexe | ~$0.10-0.30 |
| Icebreaker cold email | Sonnet | Ton humain ultra-personnalisé | ~$0.02-0.05 |
| Rédaction articles | DeepSeek | Texte long, formatage | ~$0.02-0.05 |
| Copy LinkedIn/Ads | DeepSeek | Copy créatif simple | ~$0.01-0.03 |
| Analyse SEO / données | Haiku | Parsing données, rapports | ~$0.01-0.03 |
| Validation qualité | Haiku | Checklist 20 critères | ~$0.01 |
| Briefing Telegram | Haiku | Message court formaté | ~$0.005 |
| Segmentation CSV | Haiku | Parsing + routing | ~$0.01 |

**Config router** (`~/.claude-code-router/config.json`) :
```json
{
  "providers": {
    "anthropic": {"api_key": "$ANTHROPIC_API_KEY"},
    "deepseek": {"api_base_url": "https://api.deepseek.com/chat/completions", "api_key": "$DEEPSEEK_API_KEY", "transformer": "deepseek"}
  },
  "tasks": {
    "default": "anthropic,claude-haiku-4-5-20251001",
    "background": "deepseek,deepseek-chat",
    "think": "anthropic,claude-sonnet-4-6"
  }
}
```

**Coût total estimé** : ~$4-10/semaine pour les 2 sites (vs $130+/semaine Paperclip)

---

## OUTILS INSTALLÉS (0 code)

| Outil | Repo | Ce qu'il fait |
|---|---|---|
| agent-flow | github.com/patoles/agent-flow | Graph live agents (solar system viz) |
| agents-observe | github.com/simple10/agents-observe | Observabilité, logs, debug |
| claude-usage | github.com/phuryn/claude-usage | Cost tracking dashboard |
| claude-code-router | github.com/musistudio/claude-code-router | Routage DeepSeek/Haiku/Sonnet |
| Agent Teams | Natif Claude Code v2.1.32+ | Swarm avec TeammateTool |

---

## DASHBOARD

### 4 couches superposées :
1. **agent-flow** → graph live des agents (installé, pas codé)
2. **agents-observe** → logs/debug temps réel (installé, pas codé)
3. **claude-usage** → tokens/coûts (installé, pas codé)
4. **Custom** → dataviz métier (HTML + Chart.js, codé par nous) :
   - Page health check : statut connexions + crédits Anthropic/DeepSeek
   - Data table : runs, modules, coûts, statuts
   - Charts : coûts/jour, articles publiés, ROI par site, campagnes Emelia
   - Campagnes : taux ouverture, réponses, RDV bookés

---

## CONTRÔLE À DISTANCE

### VPS + tmux + Remote Control
```bash
# Session persistante 24/7
ssh → tmux new -s genesis → claude → /remote
# → QR code sur téléphone → contrôle depuis iPhone
```

### Notifications push
- tap-to-tmux → push notif quand l'agent a besoin d'attention
- Telegram → rapports quotidiens + alertes

---

## APIs & CREDENTIALS

| API | Statut | Usage |
|---|---|---|
| ANTHROPIC_API_KEY | ✅ | Sonnet/Haiku via router |
| DEEPSEEK_API_KEY | ✅ | Rédaction/copy via router |
| TELEGRAM_BOT_TOKEN | ✅ | Notifications + commandes |
| UNSPLASH ×2 | ✅ | Images articles MKD + LCR |
| EMDASH (LCR) | ✅ | CMS leclientroi.com |
| WP_USERNAME + APP_PASSWORD | ✅ | CMS mkdgroupe.com |
| TWENTY CRM | ✅ | Gestion contacts/leads |
| HIGGSFIELD | ✅ | Images MKD (optionnel) |
| EMELIA_API_KEY | ❌ À fournir | Cold email + LinkedIn + verify |
| AHREFS MCP | ✅ (à reconnecter) | SEO analysis |
| RESEND_API_KEY | ❌ Optionnel | Newsletter broadcast |
| META_ADS_TOKEN | ❌ Optionnel | Meta Ads (phase 3) |

---

## PHASES D'IMPLÉMENTATION

### Phase 0 — Prérequis (toi)
- [x] DeepSeek API key → fourni
- [x] WP credentials MKD → fourni
- [ ] Emelia API key → à récupérer sur app.emelia.io/settings/api
- [ ] Domaine dédié cold email (ex: lcr-contact.com) + SPF/DKIM/DMARC
- [ ] Warmup 2-4 semaines sur Emelia

### Phase 1 — Setup VPS
1. Backup données Paperclip (articles, mémoire agents)
2. Transférer Genesis sur le VPS
3. Configurer .env, claude-code-router, hooks
4. Installer agent-flow + agents-observe + claude-usage
5. Lancer tmux + Claude Code + /remote

### Phase 2 — Content + Orchestrateur
1. Skill swarm-orchestrate
2. Skill swarm-content
3. Test run complet : brief → article → publication
4. Cron hebdomadaire lundi 6h

### Phase 3 — SEO + Outreach
1. Brancher Ahrefs MCP
2. Skill swarm-seo
3. Skill swarm-outreach (LinkedIn via Emelia)

### Phase 4 — Cold Email (LCR priorité)
1. Skill swarm-cold-email
2. Skill swarm-campaign (orchestration Emelia)
3. Test campagne 50 prospects segment Restaurants
4. Scale progressif 200-500 prospects

### Phase 5 — Dashboard + Monitoring
1. Dashboard custom (health check + dataviz)
2. Vérifier que tout tourne sans Paperclip
3. pm2 stop paperclip

---

## FICHIERS DU PROJET

```
/home/autoblog/genesis/
├── CLAUDE.md                          # Instructions globales
├── .env                               # Clés API
├── context/                           # Contexte métier (RAG)
│   ├── mkd/goals.md
│   ├── lcr/goals.md
│   ├── lcr/article-templates.md
│   ├── lcr/campaign-plan.md           # Plan campagne cold email LCR
│   └── shared/
│       ├── credentials.md
│       ├── cold-email-rules.md
│       ├── emelia-api.md              # 71 endpoints Emelia
│       └── emelia-knowledge/          # Base connaissance Emelia (4 fichiers)
├── specs/                             # Architecture et guides
│   ├── architecture-v2.md             # CE FICHIER
│   ├── stack-tools.md
│   ├── dashboard-specs.md
│   ├── vps-setup.md
│   ├── pre-transfer-checklist.md
│   └── bootstrap-prompt.md
├── skills/                            # 10 skills (à créer)
├── memory/                            # RAG (à initialiser)
├── dashboard/                         # HTML + Chart.js (à créer)
├── backup/                            # Données Paperclip sauvegardées
└── tools/                             # agent-flow, agents-observe (à cloner)
```
