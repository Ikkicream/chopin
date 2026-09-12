# RAG / Mémoire — Architecture technique

## Le besoin
Nos agents doivent se souvenir de :
1. **Qui a été contacté** (79K prospects, statuts, historique)
2. **Ce qui a été publié** (articles, keywords ciblés)
3. **Les règles métier** (templates, CTAs, ton, délivrabilité)
4. **Les résultats** (stats campagnes, coûts, rapports)
5. **Le contexte entre sessions** (un agent qui reprend le lendemain doit savoir ce qu'il a fait hier)

## Les 3 couches — on en utilise DEUX, pas une seule

---

### COUCHE 1 — claude-mem (mémoire inter-sessions) — INSTALLÉ
**Repo** : https://github.com/thedotmack/claude-mem (89K+ stars)

**Ce que ça fait** :
- Capture automatiquement tout ce que Claude fait (tool calls, fichiers lus, commandes)
- Compresse en résumés sémantiques
- Stocke dans SQLite local + ChromaDB vector search
- Au démarrage de chaque session → injecte le contexte des sessions précédentes
- Claude "se souvient" de ce qu'il a fait hier, la semaine dernière, etc.

**Install** :
```bash
npx claude-mem install
# → Service local port 37777
# → S'active automatiquement via hooks Claude Code
```

**Pourquoi** : Sans ça, chaque fois qu'on lance Claude Code dans tmux, il repart de zéro. Avec claude-mem, il sait que "hier j'ai injecté 30 contacts Tier 1 dans Emelia, le bounce rate était de 2%, j'ai publié un article sur le SMS boulangerie".

**⚠️ Sécurité** : Pas d'auth sur le port 37777. OK sur notre VPS dédié (pas de serveur partagé), mais on bloque le port dans le firewall :
```bash
ufw deny 37777/tcp  # bloqué de l'extérieur, accessible en local uniquement
```

---

### COUCHE 2 — knowledge-rag (base de connaissance documents) — INSTALLÉ
**Repo** : https://github.com/lyonzin/knowledge-rag

**Ce que ça fait** :
- Drop des fichiers (MD, PDF, CSV, JSON) dans un dossier
- Indexe automatiquement avec embeddings locaux (pas d'API externe)
- 12 outils MCP pour chercher dans la base
- Hybrid search (sémantique + keyword)
- Reranking intégré
- **100% local, 0 API, 0 coût**

**Install** :
```bash
# Via Claude Code
marketplace add lyonzin/knowledge-rag
# OU manuellement
git clone https://github.com/lyonzin/knowledge-rag
cd knowledge-rag && pip install -r requirements.txt
```

**Ce qu'on indexe dedans** :
```
knowledge-rag/documents/
├── emelia-api.md                    # 71 endpoints Emelia
├── emelia-knowledge/                # 4 fichiers délivrabilité, workflow, LinkedIn
├── cold-email-rules.md             # Ton, interdits, signature
├── article-templates.md            # Templates LCR
├── prospect-tiers.md               # 3 tiers de segmentation
├── daily-injection-workflow.md     # Workflow quotidien Emelia
├── deliverability-rules.md         # Règles délivrabilité
└── campaign-plan.md                # Plan campagne LCR
```

**Pourquoi** : Quand l'agent doit rédiger un icebreaker, il cherche "quelles sont les règles cold email" → knowledge-rag retourne les chunks pertinents de cold-email-rules.md. Quand il doit créer une campagne Emelia, il cherche "comment créer une campagne steps" → retourne les bons endpoints de emelia-api.md.

---

### COUCHE 3 — Fichiers markdown structurés (tracking opérationnel)

**Pas de techno, juste des fichiers que l'agent lit/écrit** :

```
memory/
├── lcr/
│   ├── injection-tracker.json      # Qui a été contacté, quand, quel domaine
│   ├── articles-published.md       # Liste des articles publiés
│   ├── keywords-targeted.md        # Mots-clés ciblés et statut
│   ├── campaign-results.md         # Résultats campagnes Emelia par semaine
│   └── weekly-reports/
│       ├── 2026-W18.md
│       └── 2026-W19.md
├── mkd/
│   ├── articles-published.md
│   └── keywords-targeted.md
└── shared/
    ├── costs-log.json              # Coûts par module/jour
    └── agent-logs/                 # Logs lisibles de chaque run
```

**Pourquoi** : Pour le tracking opérationnel (qui a été contacté, combien ça a coûté), un JSON/MD suffit. Pas besoin de vector search pour savoir si "j.dupont@carrefour.com a déjà été contacté" → c'est un lookup par clé, pas une recherche sémantique.

---

## Comment les 3 couches interagissent

```
┌─────────────────────────────────────────────────┐
│  Claude Code (session tmux)                      │
│                                                  │
│  Démarre → claude-mem injecte le contexte        │
│            "Hier tu as injecté 30 contacts,      │
│             publié 1 article, bounce 2%"         │
│                                                  │
│  Agent a une question sur Emelia ?                │
│  → knowledge-rag search "comment configurer      │
│    les steps d'une campagne Emelia"              │
│  → Retourne les chunks pertinents de             │
│    emelia-api.md                                 │
│                                                  │
│  Agent doit injecter des contacts ?               │
│  → Lit memory/lcr/injection-tracker.json         │
│  → Vérifie les domaines déjà contactés           │
│  → Sélectionne le batch du jour                  │
│  → Écrit le résultat dans le tracker             │
│                                                  │
│  Fin de session → claude-mem sauvegarde          │
│  automatiquement le résumé                       │
└─────────────────────────────────────────────────┘
```

## Résumé techno

| Couche | Techno | Coût | Ce qu'elle gère |
|---|---|---|---|
| **Mémoire sessions** | claude-mem (SQLite + ChromaDB) | $0 | Continuité entre sessions |
| **Knowledge base** | knowledge-rag (embeddings locaux + MCP) | $0 | Docs, règles, API docs |
| **Tracking ops** | Fichiers JSON/MD | $0 | Prospects, coûts, articles |

**Total coût RAG : $0** — tout tourne en local sur le VPS, pas d'API payante.

## Ce qu'on N'utilise PAS (et pourquoi)

| Techno | Pourquoi non |
|---|---|
| Voyage AI embeddings | API payante, on a des embeddings locaux gratuits |
| Pinecone | Cloud, payant, nos données partent chez eux |
| LangChain | Overkill, trop de dépendances, on a knowledge-rag qui fait mieux en plus simple |
| Obsidian | Nécessite une UI desktop, pas adapté à un VPS headless |
| Base vectorielle custom | knowledge-rag fait déjà le job |

## Install sur le VPS

```bash
# 1. claude-mem (mémoire inter-sessions)
npx claude-mem install
ufw deny 37777/tcp  # sécuriser le port

# 2. knowledge-rag (base de connaissance)
cd /home/autoblog/genesis/tools
git clone https://github.com/lyonzin/knowledge-rag
cd knowledge-rag && pip install -r requirements.txt

# 3. Indexer les documents
cp /home/autoblog/genesis/context/shared/emelia-api.md documents/
cp /home/autoblog/genesis/context/shared/cold-email-rules.md documents/
cp -r /home/autoblog/genesis/context/shared/emelia-knowledge/ documents/
cp /home/autoblog/genesis/context/lcr/article-templates.md documents/
cp /home/autoblog/genesis/context/lcr/campaign-plan.md documents/
cp /home/autoblog/genesis/specs/prospect-tiers.md documents/
cp /home/autoblog/genesis/specs/daily-injection-workflow.md documents/
# → knowledge-rag indexe automatiquement

# 3. Les fichiers memory/ sont créés par les agents au premier run
mkdir -p /home/autoblog/genesis/memory/{lcr,mkd,shared}
```
