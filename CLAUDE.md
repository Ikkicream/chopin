# Genesis — Swarm Agents pour mkdgroupe.com & leclientroi.com

## Ce projet
Système multi-agents Claude Code remplaçant Paperclip (qui coûtait $735+ pour 28 agents crashant 74% du temps).
Architecture : 1 orchestrateur Sonnet + agents spécialisés routés via DeepSeek/Haiku selon la tâche.

## Fichiers importants
- `specs/architecture-v2.md` — Architecture complète, modules, coûts, phases
- `specs/stack-tools.md` — Stack technique, outils à installer, ordre d'installation
- `specs/dashboard-specs.md` — Specs UX/UI dashboard (agent-flow + custom)
- `context/` — Tout le contexte métier récupéré de Paperclip
- `memory/` — Base de connaissances RAG (articles, keywords, rapports)
- `skills/` — Les 10 skills des agents
- `.env` — Clés API (NE JAMAIS COMMITTER)

## Les 2 sites
- **MKD** — mkdgroupe.com (WordPress) — B2B data marketing, RGPD, RCS
- **LCR** — leclientroi.com (Emdash CMS localhost:4321) — SMS marketing local

## Règles
- Budget strict : ne jamais dépasser $10/semaine total
- Routage modèles : Sonnet = orchestration/cold email uniquement, Haiku = SEO/briefing, DeepSeek = rédaction/outreach
- 1 article/semaine max par site
- Cold email : max 50/jour, ton humain obligatoire (voir context/shared/cold-email-rules.md)
- Toujours logger les coûts dans memory/shared/costs-log.json

## Commandes utiles
```bash
# Services sur ce VPS
pm2 list                                    # voir les processes
curl -s http://localhost:4321/_emdash/api/content/posts?limit=5 -H "Authorization: Bearer ec_pat_2q9s_IoXN00AqtPHsL6F68lzcSwYlGWE-Y6mzm9UDrk"   # API Emdash LCR
curl -s http://127.0.0.1:3100/api/health    # API Paperclip (à arrêter après migration)
```
