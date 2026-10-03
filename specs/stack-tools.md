# Stack & Outils — Ce qu'on installe vs ce qu'on code

## PRINCIPE
On ne recode rien qui existe. On installe, on branche, on customise le métier.

---

## OUTILS À INSTALLER (0 ligne de code)

### 1. agent-flow — Visualisation graph live
- **Repo** : https://github.com/patoles/agent-flow
- **Ce que ça fait** : Le graph "solar system" des screenshots (agents, fichiers, tool calls, sub-agents en temps réel)
- **Install** :
  ```bash
  git clone https://github.com/patoles/agent-flow
  cd agent-flow
  pnpm i
  pnpm run setup    # configure les hooks Claude Code auto
  pnpm run dev       # lance le dashboard + event relay
  ```
- **Aussi dispo** : Extension VS Code "Agent Flow"
- **Port** : localhost (à proxyer via Nginx pour accès remote)

### 2. agents-observe — Observabilité / logs lisibles
- **Repo** : https://github.com/simple10/agents-observe
- **Ce que ça fait** : Dashboard web avec filtrage, recherche, logs de tous les hook events
- **Install** :
  ```bash
  # Via Claude Code marketplace
  marketplace add simple10/agents-observe
  claude plugin install agents-observe
  # Skill dispo : /observe status|debug|logs|restart
  ```
- **Port** : localhost:4981
- **Utile pour** : Debug quand un agent plante, voir exactement ce qui s'est passé

### 3. claude-code-router — Routage multi-modèle (DeepSeek/Haiku/Sonnet)
- **Repo** : https://github.com/musistudio/claude-code-router
- **Ce que ça fait** : Proxy qui route les requêtes Claude Code vers le modèle de ton choix
- **Install** :
  ```bash
  npm install -g @musistudio/claude-code-router
  ```
- **Config** : `~/.claude-code-router/config.json`
  ```json
  {
    "providers": {
      "anthropic": {
        "api_base_url": "https://api.anthropic.com/v1/messages",
        "api_key": "$ANTHROPIC_API_KEY"
      },
      "deepseek": {
        "api_base_url": "https://api.deepseek.com/chat/completions",
        "api_key": "$DEEPSEEK_API_KEY",
        "transformer": "deepseek"
      }
    },
    "tasks": {
      "default": "anthropic,claude-haiku-4-5-20251001",
      "background": "deepseek,deepseek-chat",
      "think": "anthropic,claude-sonnet-4-6",
      "longContext": "deepseek,deepseek-chat"
    }
  }
  ```
- **Usage** : `ccr code` au lieu de `claude` — switch dynamique avec `/model`
- **Résultat** : 70% des tâches sur DeepSeek ($0.14/M tokens) au lieu de Sonnet ($3/M input)

### 4. claude-usage — Cost tracking dashboard
- **Repo** : https://github.com/phuryn/claude-usage
- **Ce que ça fait** : Dashboard local qui lit les logs JSONL de Claude Code → charts tokens/coûts/sessions
- **Install** :
  ```bash
  git clone https://github.com/phuryn/claude-usage
  cd claude-usage
  # suivre le README pour setup
  ```
- **Complément CLI** : https://github.com/ryoppippi/ccusage (ccusage — rapports mensuels en terminal)

### 5. Claude Code Agent Teams — Swarm natif (rien à installer)
- **Docs** : https://code.claude.com/docs/en/agent-teams
- **Ce que ça fait** : TeammateTool natif dans Claude Code v2.1.32+
- **Setup** :
  ```bash
  # Dans settings.json Claude Code :
  # "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  #
  # Ou en langage naturel :
  # "Set up a team with content-writer, seo-analyst, and outreach specialists"
  ```
- **Features** :
  - Lead agent spawn des teammates
  - Chaque teammate = context window 1M tokens séparé
  - Git worktree isolé par teammate
  - Task list partagée avec dépendances
  - Mailbox inter-agents

### 6. Salesforge MCP — Cold email (alternative à Mailnjoy)
- **Docs** : https://www.salesforge.ai/blog/automate-cold-email-claude-code-salesforge-mcp
- **Ce que ça fait** : Création campagnes, séquences, mailbox monitoring depuis Claude Code
- **Note** : Mailnjoy n'a pas de MCP server publié. Salesforge est l'alternative la plus mature.
  Si tu veux absolument Mailnjoy, on peut coder un MCP server custom qui wrappe leur API.

---

## CE QU'ON CODE NOUS-MÊMES (skills métier)

### 7 Skills Claude Code custom

| Skill | Fichier | Modèle via router | API externe |
|---|---|---|---|
| `swarm-orchestrate` | skills/orchestrate.md | Sonnet (think) | Telegram |
| `swarm-content` | skills/content.md | DeepSeek (background) | WP API / Emdash / Unsplash |
| `swarm-seo` | skills/seo.md | Haiku (default) | Ahrefs MCP / GSC |
| `swarm-outreach` | skills/outreach.md | DeepSeek (background) | Zernio (LinkedIn) |
| `swarm-email-marketing` | skills/email-marketing.md | DeepSeek (background) | Resend |
| `swarm-cold-email` | skills/cold-email.md | Sonnet (think) | Salesforge MCP / Mailnjoy |
| `swarm-campaign` | skills/campaign.md | Haiku + Sonnet | Salesforge MCP / Mailnjoy |
| `swarm-briefing` | skills/briefing.md | Haiku (default) | Telegram |
| `swarm-dashboard` | skills/dashboard.md | — | JSON → HTML |
| `swarm-memory` | skills/memory.md | — | Fichiers MD |

### Dashboard custom (la couche métier par-dessus agent-flow)
- **Page unique HTML** servie par Nginx
- **Données** : JSON généré par les hooks post-run
- **Charts** : Chart.js (coûts/jour, articles publiés, ROI par site)
- **Data table** : vanilla JS (runs, modules, coûts, statuts)
- **Se combine avec** : agent-flow (graph) + agents-observe (debug)

---

## STRUCTURE FICHIERS SUR LE VPS

```
/home/autoblog/genesis/
├── .claude/
│   └── settings.json          # hooks, agent teams, router config
├── skills/
│   ├── orchestrate.md         # Skill orchestrateur
│   ├── content.md             # Skill rédaction/publication
│   ├── seo.md                 # Skill analyse SEO
│   ├── outreach.md            # Skill LinkedIn/Ads
│   ├── email-marketing.md     # Skill newsletter
│   ├── cold-email.md          # Skill prospection 1-to-1
│   ├── campaign.md            # Skill séquences email
│   ├── briefing.md            # Skill rapport Telegram
│   ├── dashboard.md           # Skill génération dashboard
│   └── memory.md              # Skill mémoire/RAG
├── memory/
│   ├── mkd/                   # Contexte mkdgroupe.com
│   ├── lcr/                   # Contexte leclientroi.com
│   └── shared/                # Credentials, costs, logs
├── dashboard/
│   ├── index.html             # Dashboard custom
│   ├── data.json              # Données des runs
│   └── assets/                # Chart.js, CSS
├── tools/
│   ├── agent-flow/            # git clone
│   └── agents-observe/        # plugin installé
├── .env                       # Toutes les clés API
└── CLAUDE.md                  # Instructions globales pour Claude Code
```

---

## ORDRE D'INSTALLATION

### Phase 0 — Prérequis (toi)
- [ ] Créer compte DeepSeek → récupérer DEEPSEEK_API_KEY
- [ ] Créer app password WordPress MKD → WP_USERNAME + WP_APP_PASSWORD
- [ ] (Optionnel) S'inscrire Resend → RESEND_API_KEY
- [ ] (Optionnel) Vérifier si Mailnjoy a une API ou passer à Salesforge

### Phase 1 — Setup base (terminal Claude Code)
1. Créer la structure `/home/autoblog/genesis/`
2. Copier le contexte (memory/) depuis les fichiers Genesis_kill_paperclips
3. Configurer `.env` avec toutes les clés
4. Installer `claude-code-router` + configurer le routage DeepSeek/Haiku/Sonnet
5. Écrire `CLAUDE.md` (instructions globales)

### Phase 2 — Installer les outils
1. `agent-flow` → graph live
2. `agents-observe` → observabilité
3. `claude-usage` → cost tracking
4. Configurer Nginx pour servir les dashboards

### Phase 3 — Écrire les skills
1. `swarm-orchestrate` (le cerveau)
2. `swarm-content` (rédaction + publication)
3. `swarm-seo` (analyse Ahrefs/GSC)
4. Tester un run complet : brief → article → publication

### Phase 4 — Email & Outreach
1. `swarm-outreach` (LinkedIn)
2. `swarm-email-marketing` (newsletter)
3. `swarm-cold-email` + `swarm-campaign` (prospection)

### Phase 5 — Dashboard custom + arrêt Paperclip
1. Dashboard HTML avec dataviz métier
2. Vérifier que tout tourne sans Paperclip
3. `pm2 stop paperclip`

---

## COÛT ESTIMÉ DE LA NOUVELLE ARCHITECTURE

| Composant | Coût/semaine | Détail |
|---|---|---|
| Orchestrateur (Sonnet) | $2-4 | 1-2 runs/semaine, raisonnement complexe |
| Content (DeepSeek) | $0.20-0.50 | 2 articles/semaine, ~1000 tokens/article |
| SEO (Haiku) | $0.50-1 | Analyse Ahrefs + GSC hebdo |
| Outreach (DeepSeek) | $0.10-0.30 | 2 posts LinkedIn/semaine |
| Cold Email (Sonnet) | $0.50-2 | Variable selon campagnes |
| Briefing (Haiku) | $0.10-0.20 | 1 rapport/jour |
| Infra (agent-flow etc) | $0 | Open source, tourne sur le VPS |
| **TOTAL** | **$3.50-8/semaine** | **vs $130+/semaine avec Paperclip** |

**$20 de budget = 2.5 à 5 semaines** au lieu de 1.3 jours
