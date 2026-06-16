# STATE — Genesis (à lire EN PREMIER au démarrage de session)

> Source de vérité unique pour reprendre le projet sans re-expliquer le contexte.
> À mettre à jour AVANT toute fin de session ('à demain', 'j'en ai marre', etc.).

## Dernière mise à jour
2026-06-16 (V2 préambules action_type + bascule crons agentiques + humanizer fix + refonte scrapper région-continu)

## 🔝 REPRISE 2026-06-16 (suite) — Refonte du scrapper (autoscrape région-continu)

**Demande user :** le scrapper "automatique" ne l'était pas (s'arrêtait sur estimation crédits + volume cible). Veut : choisir juste secteur + RÉGION, scraper EN CONTINU dans l'ordre des départements tant que Serper ne stoppe pas réellement, retry quotidien au blocage, statut "Région finie" à l'épuisement, libellé région correct, plus de champ volume.

**FAIT (corrige + améliore + testé) :**
- **`god_mode_agents.serper_places`** : détecte le refus EXPLICITE de Serper (HTTP 429/402/403) → lève `SERPER_BLOCKED_STATUS` au lieu d'avaler en `[]` (avant : un blocage passait pour "ville vide"). Testé live : appel normal → flag reste None, 10 places.
- **`autoscrape_backend.py` réécrit** : `run_autoscrape(region=…)` enchaîne TOUS les départements de la région (triés par code), toutes villes pop≥10k. **Supprimé** : credit-floor préemptif + volume cible + stall-heuristic. **Seul arrêt** = vrai blocage Serper / stop manuel / épuisement (→ statut `done` "Région X finie"). Reprise : `memory/autoscrape/{site}-region-progress.json` (depts_done). Garde-temps 6 h (anti-zombie). Activité = **1 ligne par run** (plus 1 par ville) : start_scrape + scrape de fin uniques avec scope région.
- **`daily_retry()` + crons PM2** `genesis-autoscrape-retry-lcr` (06:00) / `-mkd` (06:10) : si région `blocked_serper` et Serper repasse (1 appel test) → reprend en skippant les depts finis.
- **`api.py`** : `/autoscrape/start` accepte `region` (drop `target_valid`), `/scrape/live-activity` fenêtre de match élargie 10min→12h + expose `scope`/`message`/statut métier.
- **Frontend `scrapper/page.tsx`** : autoscrape sur RÉGION (dept optionnel), champ Volume cible supprimé, libellé région corrigé (`SelectValue` rendait le code "11" → force `{r.name}`), carte statut montre scope + dépts faits, table activité montre "Région finie"/"⛔ Serper" + périmètre. Build OK, dashboard+UI restart.

**Testé :** géo (Bretagne→22,29,35,56 ; Corse→2A,2B ; IDF→75..95), orchestration mockée (blocage→`blocked_serper`, persistance `depts_done`, reprise skip), serper réel, build UI, crons.

- **Corse + DOM-TOM EXCLUS** (correction user : périmètre = France métropolitaine seule). `workflow_geo.EXCLUDED_REGION_CODES={94,01,02,03,04,06}` + `EXCLUDED_DEPT_CODES={2A,2B,971-978}` + helpers `metropole_regions/departments/cities`. Câblés sur les 3 endpoints `/geo/*` ET l'autoscrape (`_ordered_region_depts`, listing villes). Résultat : 12 régions continentales, 0 ville Corse/DOM. NB : dept "94" (Val-de-Marne, IDF) ≠ région "94" (Corse) — pas de collision.

**RESTE scrapper (optionnel) :** un vrai run live de bout en bout via l'UI (clic user) pour confirmer pool+Mailnjoy ; étendre le retry à d'autres sites si besoin.



## 🔝 REPRISE 2026-06-16 — V2 préambules action_type (RESTE #1 fait)

**FAIT cette session :**
- **Constat dry-run** : le préambule V1 (texte dans le playbook) **ne suffit PAS** — DeepSeek inventait systématiquement (2/2 runs) `create_article`/`update_article` pour `seo-strategist` → l'agent ne produisait **aucun `seo_reco` valide** (tout skippé). Donc pas un bruit cosmétique : sortie vide.
- **Enum exhaustif ajouté** aux 6 playbooks filtrés (`skills/seo-strategist|content-writer|internal-linking|linkedin-specialist|competitive-intel|graphiste.md`) : bloc « `action_type` AUTORISÉ — liste EXHAUSTIVE » juste après le JSON, + redirection explicite des synonymes tentants (ex seo-strategist : « tu ne rédiges pas d'article → `seo_reco` + `tags.type:content_gap` »).
- **Enforcement central dans `agent_core.decide()`** (la vraie correction, le playbook seul étant trop faible face au raisonnement du modèle) :
  - `ALLOWED_ACTION_TYPES` (dict par nom d'agent, source de vérité = filtres des `_agentic_writer`).
  - La liste autorisée est injectée dans le **prompt système** (domine le playbook) comme CONTRAINTE DURE.
  - Garde-fou : 1 passe de **réparation** si le modèle viole l'enum, puis **filtrage final** des items hors-enum (ne polluent plus `agent_actions`).
  - Nouveau param `allowed_actions` sur `decide()` **et** `run_cycle()` (rétrocompatible, fallback sur le dict).
- **Split content-writer** : `content_agent` et `brief_agent` partagent le playbook `content-writer.md`. `content_agent` passe `allowed_actions=["write_article"]`, `brief_agent` `["write_article","propose_article"]` → fini la fuite `propose_article` skippée côté content_agent.
- **Validation dry-run des 7 agents** : tous émettent désormais UNIQUEMENT des types valides (seo_reco / write_article / add_internal_link / linkedin_post(ou plan:[]) / intel_signal / generate_header). Zéro skip « non géré », garde-fou jamais déclenché (respect dès la 1ʳᵉ passe). `humanizer` volontairement **exclu** du dict (pas de filtre côté writer, comportement libre préservé).
- **Note** : `skills/briefing.md` (send_briefing/telegram) n'est chargé par AUCUN agent agentique (`genesis-briefing` = `scripts/briefing.py` déterministe ; `brief_agent` lit `content-writer.md`). Son préambule V1 est mort → laissé tel quel, à nettoyer un jour.

**FAIT (suite) — bascule crons agentiques :**
- **5 crons PM2 créés en `--agentic --live` sur lcr** (les agents n'avaient AUCUN cron avant — le STATE 06-10 surestimait l'existant) : `genesis-brief` (08h L/M/V), `genesis-seo-strategy` (09h L/M/V), `genesis-internal-linking` (12h L/M/V), `genesis-linkedin` (13h L/M/V), `genesis-competitor` (07h Lundi). Pipeline cohérent avec content-lcr (10h) + graphiste (11h). Tous `--no-autorestart`, `pm2 save` fait.
- **Risque maîtrisé** : en live ces 5 agents n'écrivent que dans des JSON internes (recos/queues) — aucun post LinkedIn réel ni publication externe. La partie outward reste content/graphiste (déjà live lcr).
- **1ʳᵉ exécution live OK** (exit 0 sur les 5) : actions réelles loggées dans `agent_actions`, toutes enum-propres (seo_reco, intel_signal, write_article, add_internal_link, linkedin plan:[]). L'éval aura de la matière à J+7.
- `content-mkd` laissé tel quel (publish 401, décision user) ; `ecosystem.config.js` est OBSOLÈTE (3 crons orchestrator morts) → source de vérité = `pm2 save` / dump.pm2.

**RESTE (prochaine session, par priorité) :**
1. **MKD publish 401** (action user : régénérer App Password WP, voir DÉCISIONS EN ATTENTE plus bas).
2. ~~**humanizer invente des action_type / plante**~~ **CORRIGÉ 16/06** : la vraie cause du plantage nocturne était `humanize_article.py` qui faisait `exit 1` à chaque run — `check_constraints` échouait car le filet déterministe ne forçait le frontmatter original que si le LLM en produisait un (or DeepSeek le supprime souvent). Fixes : (a) frontmatter original réinjecté TOUJOURS, (b) strip déterministe des `---` en corps au lieu de rejeter, (c) `DEFAULT_PROMPT` repointé de `/tmp/cmux-drop-*.md` (éphémère) vers `skills/humanizer.md` (identique, stable), (d) `humanizer → ["humanize_article"]` ajouté à `ALLOWED_ACTION_TYPES`. Validé live (exit 0, frontmatter intact, `.bak` créé). **Résidu** : la mémoire de l'agent garde 8 erreurs périmées → il reste en `plan:[]` par prudence ; se résorbe en ~qq jours (noops chassent les erreurs de la fenêtre recall=10) ou via purge manuelle des lignes `agent_actions agent=humanizer status=error` (refusée par le classifier ce jour, à autoriser si on veut accélérer).
3. **🆕 internal-linking & linkedin manquent la liste d'articles dans leur snapshot** (sources=gsc,ga4 seulement) → internal-linking détourne `add_internal_link` en « fetch », linkedin reste en `plan:[]`. Ajouter une source `articles` à `observe()` pour ces 2 agents pour qu'ils agissent vraiment.
4. **🆕 Pollution test agent_actions (16/06)** : `create_article`/`update_article`/`propose_article` en `done` issus de mes dry-runs d'avant le fix. Inoffensif (eval les skippe) mais à purger si on veut une table propre (delete manuel DB).
5. **Évaluation post-cron** : laisser tourner 1-2 semaines, vérifier que `evaluate()` passe de `evaluated:0` à des outcomes réels, affiner les seuils.
6. **Migrer humanize_article + gen_agents_state vers text_utils.slugify** (cosmétique).

**DÉCISIONS EN ATTENTE (user) :** MKD publish 401 (régénérer App Password WP — détail dans la section REPRISE 2026-06-09 soir).

## 🔝 REPRISE 2026-06-10 — Chantiers 1/2/5/6

## 🔝 REPRISE 2026-06-10 — Chantiers 1/2/5/6

**FAIT cette session :**
- **Chantier 1 (pilote)** : `seo_strategy_agent.py --agentic --live` migré sur `agent_core.run_cycle`. Pattern copié de `content_agent.run_agentic`. Test dry-run validé. Reste 4 agents à migrer (#12 pending : internal_linking, linkedin, competitor, brief).
- **Chantier 2** : préambule action_type/target ajouté à 6 playbooks → `skills/seo-strategist.md`, `content-writer.md`, `internal-linking.md`, `linkedin-specialist.md`, `competitive-intel.md`, `briefing.md`. Format JSON strict imposé : `{reasoning, plan: [{action_type, target, why, tags}]}`. Chaque playbook ajoute le périmètre (un seul article par cycle pour content-writer, max 6 recos pour seo-strategist, etc.).
- **Chantier 5** : `scripts/text_utils.py` créé avec `slugify()` (NFD + diacritiques). `content_agent._slugify` réexporté pour compat. À réutiliser dans humanize_article et autres.
- **Chantier 6** : legacy /agents complètement viré
  - **Backend `scripts/api.py`** : suppression d'AGENTS_REGISTRY (10 agents hardcodés), AGENT_CRONS_FILE, _load_agent_crons, _save_agent_crons, AGENT_COSTS, FREQ_MULTIPLIERS, endpoints `/api/agents`, `/api/agents/{site}`, `/api/agents/{site}/{agent_id}/cron`, `/api/agents/{site}/planner`, `/api/agents/{agent_id}/instructions` (variante sans site). -7072 chars dans api.py. Gardés : `/api/agents/{site}/state` + `/api/agents/{site}/{agent_id}/instructions`.
  - **UI `genesis-ui/.../agents/page.tsx`** : page refondue ne consomme plus que `/state` et `/instructions`. Table « Catalogue conceptuel » + Planner supprimés. Card unique « État PM2 réel » + Sheet playbook. Mapping `skillIdFromPm()` pour mettre un bouton « Voir playbook » sur les jobs PM2 pertinents (content/seo/humanizer).
  - Build OK, restart dashboard + UI OK, page agents répond 200, snapshot état `12 agents PM2` à jour.

**FAIT (suite session 2026-06-10) :**
- **Chantier 1 complet** : les 4 derniers agents migrés sur `agent_core` (`brief_agent`, `linkedin_agent`, `internal_linking_agent`, `competitor_analyzer`) avec `--agentic --live`. Tous testés dry-run : la boucle observe→recall→decide→act tourne, le LLM raisonne contextuellement (ex `linkedin_agent` : « plan: [] car pas d'article récent à promouvoir »). Total : **6 agents agentiques** (content-lcr/mkd, seo-strategy, internal-linking, linkedin, competitor, brief + humanizer = 7).
- **Hardening `agent_core._conn()`** : retry-backoff exponentiel sur `Conflicting lock` DuckDB (api.py FastAPI garde un handle long-lived). 6 tentatives, ~30s max. Plus de crash transitoire en parallèle de l'API.
- **Popup preview articles** (chantier #16) : Dialog sur `/site/[code]/articles` qui rend le markdown via `marked` (GFM) avec style proche du blog public. Bouton « Aperçu » visible sur tous les articles (proposal seul affiché si pas de markdown). Largeur fixée 4xl (~900px).
- **Imagen 3 (Vertex AI)** branché : compte de service `genesis-indexing@lead-machine-mkd` + facturation + rôle `aiplatform.user`. Script `scripts/imagen_generate.py`. Cible projet `lead-machine-mkd`.
- **Style photo doc iPhone/Portra 400** validé : nouveau `STYLE_PREFIX` (vraie photo candide, grain authentique, no SaaS aesthetic) + `NEGATIVE_PROMPT` qui kill illustration/3D/texte parasite. Plus de « dessin ».
- **Diversité géographique/personas** : casting Python (`SystemRandom`) avant l'appel LLM — 23 villes, 15 types de lieu, 10 personas. Fini « young Parisian in café » systématique.
- **Module Meta ads** (`scripts/meta_ad_generate.py`) : génère copy JSON 7 clés (accroche/solution/primary_text/headline/description/cta/image_brief) selon le system prompt LeClientROI senior copywriter + génère l'image associée. Coût ~0,033 €/ad.
- **🆕 Agent graphiste autonome** (`scripts/graphiste_agent.py` + `skills/graphiste.md`) :
  - Architecture séparée : content_agent fait le texte (sans image), graphiste fait l'image en post-traitement
  - Boucle agent_core : scan emdash posts sans `seo.image` → LLM choisit l'article + rédige le brief image → Imagen 3 photo doc → upload emdash → PUT seo.image
  - Cron PM2 `genesis-graphiste` (`0 11 * * *`), 1 article/jour. Backlog actuel : 21 articles sans image → 21 jours pour rattraper (ajustable).
  - Playbook strict : interdit illustration/3D/SaaS aesthetic/jeune Parisienne. Force patron 45-65 dans son commerce, ancrage métier visible, ville française variée.
  - Test live validé : agent immobilier ~50 ans avec lunettes en RDV client (https://blog.leclientroi.com/_emdash/api/media/file/01KTSGPSSF6KTV6QJZQDS7QJ6F.jpg)
- **content_agent** : branchement image header retiré (responsabilité passée au graphiste). content_agent publie sans image, graphiste enrichit après.

**RESTE (prochaine session, par priorité) :**
1. **V2 préambules playbooks** : ajouter la liste **exhaustive** des `action_type` acceptés dans chaque préambule `skills/*.md` (V1 actuelle est permissive → le LLM invente `audit_indexation`, `fix_gsc_permissions`, `fetch_articles` à côté des types attendus). Ne casse rien (les `_agentic_writer` filtrent), mais coupe le bruit.
2. **MKD publish 401** (action user : régénérer App Password WP)
3. **Migrer humanize_article + gen_agents_state vers text_utils.slugify** (cosmétique, pas urgent)
4. **Basculer les crons PM2 en `--agentic --live`** : actuellement seuls `content-lcr` et `humanizer` sont en agentique. Les autres (`seo-strategy`, `linkedin`, `internal-linking`, `competitor`, `brief` si crons existent) restent en mode classique. À basculer une fois la V2 préambules faite, pour ne pas pousser de signaux faux pendant l'itération.
5. **Évaluation post-cron** : laisser tourner les agents en mode agentique 1-2 semaines, mesurer les outcomes via `evaluate()`, affiner.

**DÉCISIONS EN ATTENTE (user) :**

## 🔝 REPRISE 2026-06-09 (nuit) — Boucle complète + humanizer + UI

**FAIT cette session (après-midi/soir/nuit) — gros chantier :**

### Boucle agentique (étape 2)
- `agent_core.evaluate()` + cron PM2 quotidien 02:00 (lcr) / 02:05 (mkd)
- 3 crons morts supprimés (briefing/crm-sync/campaign-status)
- `gen_agents_state.py` + endpoint `/api/agents/{site}/state`
- `content_agent.py --agentic` (boucle `agent_core.run_cycle`)

### Cleanup pipeline emdash (étape 3)
- Fix `publish_lcr` schema emdash : `data={title,content}` + `seo` top-level
- Fix `md_to_portable_text` : skip H1 du body (emdash affiche `data.title`), parse `**…**`/`*…*` en marks `strong`/`em`, ignore les `---`, splitte `Label : « citation »` en label-gras + blockquote, passe citations pures `« … »` en blockquote
- `ARTICLE_PROMPT` ré-écrit pour interdire à la source : préfixes `H2:`/`H3:`, labels `## Introduction`/`## Conclusion`, `---` dans le corps. Force `*Exemple : ...*` en italique.
- Slugifier `_slugify()` centralisé avec normalisation NFD (plus de `fidéliser → fidliser`)

### Test live de bout en bout
- Article LCR publié : https://blog.leclientroi.com/posts/comment-fideliser-vos-clients-avec-des-sms-personnalises (HTTP 200, slug propre avec accents, gras/blockquotes/italiques OK)
- Pilote humanizer sur 1 article backlog Arvow validé (agents-immobilier, 19k→11k chars, blacklist purgée, structure préservée)

### Agent humanizer (skill + cron PM2)
- Skill : `skills/humanizer.md` (prompt cmux-drop) + `skills/humanizer-tone.md` (préambule ton marketing-coach injecté en tête du user prompt)
- `scripts/humanize_article.py` : CLI standalone (peut traiter 1 article manuellement) — temp 0.85, filets déterministes (frontmatter forcé, `2025→2026` dans le corps)
- `scripts/humanizer_agent.py` : agent agentique sur `agent_core` (observe articles backlog par score scaffolding, recall, decide via DeepSeek, act = invoke humanize_article)
- Cron PM2 `genesis-humanizer` : `0 4 * * *`, `--site shared --live` → 1 article/jour, ~7 mois pour 212 articles backlog

### UI page /agents refondue
- Genesis-ui : nouvelle Card "État PM2 réel" en tête, lit `/api/agents/{site}/state`, affiche nom/cron lisible/statut/dernier run/exit code + badge "agent_core" si `--agentic` dans args
- Ancienne table renommée "Catalogue conceptuel (legacy)" — conservée pour transition, mais source de vérité = vraie PM2

**RESTE (prochaine session) :**
1. **MKD publish 401** : action user (régénérer App Password WP, voir DÉCISIONS EN ATTENTE)
2. **Migrer les autres agents** sur `agent_core` (seo-strategist, editorial-manager, internal-linking…) sur le pattern `content_agent.run_agentic`
3. **Première vraie évaluation** : le 16/06 02:00 UTC, `evaluate()` mesurera le delta GA4 sur l'article SMS personnalisés du 9 juin (J+7 minimum)
4. **Premier batch humanizer** : nuit du 09→10 juin 04:00, 1 article du backlog (top score actuel : `2025-11-21-automatisation-sms-marketing-workflows-et-scenarios-pour-2025.md` score 13)
5. **Slug v4 résiduels SQLite** : les slugs `-v2/-v3/-v4` sont soft-deleted dans `ec_posts` mais l'UNIQUE constraint les retient. Si on veut les libérer, intervention manuelle DB (refusée par claude classifier, à faire main).

**DÉCISIONS EN ATTENTE (user) :**

## 🔝 REPRISE 2026-06-09 (soir) — Boucle complète + content_agent migré

**FAIT cette session (après-midi/soir) :**
- **`agent_core.evaluate()`** : feedback nocturne, mesure delta réel par action (gsc_position:{kw} → traffic_strategist-like ; fallback gsc_clicks_total ; fallback ga4_sessions_total). Verdict `validated`/`failed`/`neutral` (seuils ±0.5pt pour position, ±5% pour métriques agrégées). Idempotent (LEFT JOIN sur action_id). Filtres : actions `done`, âge ∈ [7d, 30d]. CLI : `python3 scripts/agent_core.py --mode evaluate --site lcr`. Test fixture passé : 1 outcome écrit (delta +1292 sessions, validated).
- **Cron PM2 evaluate** : `genesis-agent-evaluate-lcr` (`0 2 * * *`) + `genesis-agent-evaluate-mkd` (`5 2 * * *`), `--no-autorestart`, dump persisté.
- **3 agents MORTS supprimés** : `pm2 delete genesis-briefing genesis-crm-sync genesis-campaign-status` + save. `orchestrator.py` n'existe plus → décision tranchée (suppression, pas restauration).
- **`scripts/gen_agents_state.py`** : snapshot `pm2 jlist` → `memory/agents-pm2-state.json` (atomic). Exclut services longs (dashboard/ui/mailnjoy-drain). Filtre par suffixe `-lcr`/`-mkd` (sinon global). 11 agents listés.
- **Endpoint `/api/agents/{site}/state`** dans `scripts/api.py` (juste avant `/planner`) : lit le snapshot, refresh inline si >5min, retourne `{generated_at, host, age_s, agents}` filtrés site+globaux. Testé : lcr et mkd voient 9 agents chacun (2 spécifiques + 7 globaux).
- **`content_agent.py --agentic`** : nouveau mode pilotage `agent_core.run_cycle` (observe gsc/ga4/ahrefs, recall, decide via DeepSeek, act via `_agentic_writer(item, snapshot, site, env, dry_run)`). Mode classique préservé. Test dry-run lcr : la boucle a raisonné explicitement « action précédente sans outcome → noop ce cycle », 1 noop écrit dans agent_actions avec reasoning intelligent. **La boucle agentique est OPÉRATIONNELLE de bout en bout.**

**RESTE (prochaine session, dans l'ordre) :**
1. **Page UI /agents** : consommer `/api/agents/{site}/state` (au lieu de `/api/agents/{site}`) — card "État PM2 réel" avec nom/cron/statut/dernier run/badge couleur. Backend prêt.
2. Brancher le cron PM2 `genesis-content-lcr` sur le mode `--agentic` (actuellement encore mode legacy) une fois la publication réparée. **Avant** ça : régler les bugs publish (lcr 500, mkd 401 — décision en attente).
3. Migrer les autres agents (seo-strategist, editorial-manager, etc.) sur `agent_core` — pattern à copier depuis `content_agent.run_agentic`.
4. Enrichir `skills/content-writer.md` (et autres) avec un préambule explicite "tu dois renvoyer un plan {action_type, target}" pour aider `decide()`.

**DÉCISIONS EN ATTENTE (user) :**
- **MKD publish 401** : WordPress répond `incorrect_password` → l'App Password est révoqué/invalide. **Action manuelle requise** : aller dans WP admin → Utilisateur camille.afchain@protonmail.com → Application Passwords → en générer un nouveau, puis remplacer `WP_APP_PASSWORD` dans `.env` (sans guillemets autour). Puis `pm2 restart genesis-dashboard`.
- ~~LCR publish 500~~ **RÉPARÉ** : le schéma emdash a évolué — `data.{excerpt,description,tags}` rejetés (`ec_posts has no column named description`). Fix dans `publish_lcr` : `data={title,content}` + `seo={title,description}` au top-level (validé create 201 + publish 200 sur draft de test).

**LIMITES connues :** GSC via le compte de service = encore **403** (grant propriété pas pris ; les données GSC passent par MCP Ahrefs / seed). GA4 OK.

**RÈGLE gravée :** MAJ `AGENTS.md` + `ARCHITECTURE.md` à CHAQUE fin de session touchant aux agents → lancer `sudo -u autoblog python3 scripts/gen_agents_doc.py`.

---


## Goal en cours
Tester le pipeline **Workflow LCR** de bout en bout (Serper → DeepSeek qualifier → push Emelia → cold email envoyé).
Mail test attendu sur afchain.camille@gmail.com via la campagne workflow-lcr-restaurant.

## Done (état réel observé en DB + logs)
- Spec workflow validée → specs/workflow-prospection.md (2026-05-21)
- Migration DB `scrappe` : colonnes region_code, dept_code, population, qualifier_*, emelia_* en place
- Workflow runner branché en cron : `30 6 * * 1-5` → logs/workflow.log
- Contact test 'Test Restaurant Camille / afchain.camille@gmail.com' inséré le 2026-05-21 19:30, status=validated, emelia_segment_id=6a0f5d290eb6f73f1f6149ec (workflow-lcr-restaurant), pushed dans Emelia
- Cron du 2026-05-22 06:30 : 30 prospects scrapés (Loire-Atlantique 44), **11 contacts poussés Emelia** (immobilier 2, restaurant 4, garagiste 1, coiffeur 2, artisan 2). MKD skippé (god_mode_state.enabled=False).

## Blocked / à vérifier
- **Campagne Emelia démarrée ?** Le push contact ≠ envoi mail. Tant que la campagne workflow-lcr-restaurant est en pause côté UI Emelia, rien ne part. À vérifier via API ou UI Emelia.
- Boîte gmail afchain.camille@gmail.com : pas encore checké si le mail test est arrivé.

## Next action (à faire MAINTENANT en reprenant)
1. Interroger l'API Emelia → statut de la campagne workflow-lcr-restaurant (running ? paused ?)
2. Si paused → Start dans l'UI Emelia
3. Vérifier réception du mail dans afchain.camille@gmail.com
4. Une fois validé end-to-end → activer le site MKD (god_mode_state.enabled=True pour 'mkd')

## Rappels importants
- User : autoblog (`su - autoblog` depuis root)
- Path : /home/autoblog/genesis
- Toujours lancer claude DANS tmux : `tmux new -s genesis` ou `tmux attach -t genesis`. Une session SSH qui coupe sans tmux = perte du contexte conversation.
- Clés Emelia : EMELIA_API_KEY_LCR / EMELIA_API_KEY_MKD dans .env, fallback EMELIA_API_KEY
- Budget : <$10/semaine total
- Quota Emelia : 50 contacts/site/jour max

## Historique des sessions récentes
- 2026-06-03 : **Campagnes cold-email AUTOMATISÉES** (gros chantier, plan approuvé). NOUVEAU auto_campaign_backend.py (tables auto_campaigns + auto_campaign_runs dans god_mode.duckdb, CRUD, idempotence 1/sender/jour) + auto_campaign_runner.py (orchestrateur PROCESS DÉTACHÉ : cap = min(target, warmup_quota − sent_today) ; boucle sur le PUSH pas l'envoi async ; pick pool → push_batch_to_campaign ; si pool sec + source=autoscrape → run_autoscrape(dept) inline → re-pick ; arrêts target/pool_exhausted/scrape_blocked/no_progress(3)/timeout(4h)/stop/pause ; statut fichier ; alerte Telegram). workflow_emelia_push.py : + ensure_campaign_for_auto (réutilise get_or_create_campaign) + push_batch_to_campaign. api.py : endpoints /api/sites/{site}/auto-campaigns/* (admin, Popen détaché) + /api/campaigns/{id}/stats-by-day + BAT /api/sites/{site}/templates/{sector}/{kind}/send-test. UI : campaigns/page.tsx REFONTE (gestionnaire auto : création secteur+sender+source+cible, table pause/resume/stop/run/delete, statut+alerte) ; cold-email/page.tsx + champ BAT ; dashboard AutoCampaignsSection (cards logo+stats agrégées + chevron stats/jour + global). ⚠️ CRON PM2 NON armé : create bloqué par classifier (= décision go-live user vers vrais prospects). Pour activer : pm2 start scripts/auto_campaign_runner.py --name genesis-auto-campaigns-lcr --interpreter python3 --cron-restart '0 7 * * 1-5' --no-autorestart -- --site lcr (idem mkd 15 7) + pm2 save. Testé DRY-RUN ok (cap 30, 228 dispo pool immo). PAS de test d'envoi réel (= vrais cold emails) : via BAT (adresse perso) puis Run manuel quand le user décide. Puis /code-review ultra.
- 2026-06-02 (fix compteurs UI faux) : « Tous (5793) » de la page Acquisition etait faux = stats_for_site comptait COUNT(*) contact_site_history (incluant ~2748 ORPHELINS : historiques de contacts supprimes par le nettoyage Mailnjoy). FIX : stats_for_site (JOIN contacts + COUNT DISTINCT email) -> vrai total 3045 (cold_email 3040, lead 4, prm 1). + cleanup run_cleanup supprime desormais contact_site_history en cascade avec le contact (plus d_orphelins futurs). Purge des orphelins existants PROPOSEE mais NON faite (bloquee par classifier comme destructive ; le JOIN les exclut deja de l_affichage). Exports livres sur Bureau Mac : TOUS contacts lcr (3045), mailnjoy VALID (3018), non-immo non-verifiables (13).
- 2026-06-02 : **cleanup auto en fin d_autoscrape ENFIN fonctionnel**. Le hook auto-cleanup etait sur l_endpoint scrape MANUEL (god_mode_api), mais l_autoscrape (process detache) ne le traversait pas -> auto_cleanup_triggered=0, jamais lance. FIX : run_autoscrape enchaine cb.run_cleanup_drain(mode=unverified, source=auto-scrape) dans le meme process apres le scrape (statut "cleaning", champ cum[cleanup], respecte le stop flag). UI : autoActive inclut "cleaning" + affichage nettoyage. api.py status checks incluent "cleaning". Validé : dept 48 coiffeur -> 7 scrapes -> cleanup_batch source=auto-scrape (1 validé, 6 supprimés). Visible badge Automatique dans page Cleanup.
- 2026-06-01 (autoscrape — heartbeat + multi-select) : (1) secteur en MULTI-SELECT badges (lib/sectors, 16 predefinis) au lieu d_un input libre dans la card autoscrape. (2) heartbeat intra-ville : scrape_sector(heartbeat_cb) appelé à chaque page Serper -> autoscrape_backend met le statut à jour en direct (examinés/gardés live + current_detail ville/secteur) -> plus de faux "figé" sur ville longue (le statut ne s_ecrivait qu_en fin de secteur). NB : sur des arrondissements déjà scrapés, dedup => peu de nouveaux + pagination longue (normal). Le run en cours d_un fix garde l_ancien code (process déjà lancé) ; le fix s_applique au prochain run.
- 2026-06-01 (autoscrape — fix conflit DuckDB) : runs arrondissements renvoyaient examined=0 + faux "blocked_credits". Cause : scrape_sector CRASHAIT sur les vérifs anti-doublon (gm.email_recently_validated/email_in_pending) en conflit DuckDB cross-process avec l_API (lignes hors try/except) -> 0 resultat -> heuristique zero_streak criait blocage credit a tort (credits OK 2099). FIX : (1) god_mode_agents.scrape_sector wrappe tout le traitement par commerce en try/except + retry -> un verrou transitoire saute le commerce, ne tue plus la ville. (2) autoscrape_backend : zero_streak ne declenche blocked_credits que si solde reellement bas (<=floor*3), sinon statut stalled ; seuil 3->5. Validé : test 75 immobilier sous API live -> 42 contacts (Paris 1er 16, 2e 15, 3e 6, 4e 5) au lieu de 0. Un 75 complet = ~300 contacts.
- 2026-06-01 (autoscrape — arrondissements) : Paris/Lyon/Marseille = 1 commune INSEE unique dans la geo => autoscrape ne faisait qu_~18 contacts pour tout Paris. Ajout `ARRONDISSEMENTS` + `_expand_arrondissements` dans autoscrape_backend : dept 75 -> 20 villes (Paris 1er..20e), 69 -> +Lyon 1-9e, 13 -> +Marseille 1-16e. Serper localise bien par arrondissement (verifie), dedup email evite les doublons. city stocke stocke Paris 16e. Pas de restart API (chaque autoscrape = nouveau process lisant le fichier a jour).
- 2026-06-01 (autoscrape v2 — robuste) : le 1er autoscrape (thread DANS l'API) a planté en cours (dept 92 immobilier, 32/34 villes, ~290 contacts SAUVÉS quand même) sur `_duckdb.ConnectionException: Can't open a connection to same database file with a different configuration` — conflit de connexions DuckDB intra-process (le thread scrape vs les requêtes API). RÉARCHITECTURÉ en **process DÉTACHÉ** : `autoscrape_backend.py` a un `main()` (--site --dept --sectors) qui écrit l'avancement dans `memory/autoscrape/<site>-status.json` (heartbeat updated_at) et lit un flag `<site>-stop.flag`. Endpoints api.py : start = Popen `start_new_session=True` (détaché, survit aux restarts API), status = lit le fichier (+ marque 'interrupted' si pas de heartbeat >5min), stop = pose le flag. Plus de `_active_autoscrape` en mémoire. Bonus : log `start_scrape` par (ville,secteur) (auto=True) → l'autoscrape est désormais VISIBLE dans le panneau 'Activité des scrapes' (qui matche start_scrape↔scrape). Testé : dept 78 restaurant détaché → statut fichier OK, stop flag → arrêt propre (Versailles, 13 gardés), process sort proprement. LEÇON : ne jamais faire tourner un job DB-lourd long comme thread de l'API (genesis-dashboard = 334 restarts + conflits DuckDB) ; process détaché + statut fichier.
- 2026-06-01 : **Autoscrape département** (demande user, ras-le-bol des paramètres). Nouveau `scripts/autoscrape_backend.py` : `run_autoscrape(site, sectors, dept)` scrape TOUTES les villes pop>=10k du dept (≈35-42/dept) ville par ville via scrape_sector, en continu, jusqu'à épuisement OU blocage crédits Serper. Détection blocage : proactif (solde snapshot serper-balance.json − conso god_mode_serper_calls < credit_floor=60) + réactif (3 villes vides d'affilée). Alerte Telegram + statut 'blocked_credits'. Endpoints api.py (admin-gated via request.state.session.role) : POST /autoscrape/start {sectors,dept}, GET /autoscrape/status, POST /autoscrape/stop ; registre `_active_autoscrape` (1 job global). UI scrapper : card '🤖 Autoscrape' en haut de l'onglet Lancer (réutilise sectors + selectedDept), progression live (villes X/Y, gardés, crédits restants) + stop + bandeau alerte blocage. Testé live : dept 92 (34 villes), 1 ville Boulogne → 15 gardés, crédits 2396→2392. Diag timeout user : geo/live-activity rapides (ms), session=7j, nginx genesis-api proxy_read_timeout=120s ; le timeout venait probablement d'un scrape manuel géant (266 villes IDF — l'UI envoyait toutes les villes si aucune cochée). L'autoscrape (async, lancement instantané) élimine les timeouts de requête.
- 2026-05-31 (fix logique scrape par-ville) : BUG corrigé — `scrape_sector` (god_mode_agents) traitait `max_results` comme un plafond GLOBAL alors que l'UI promettait 'par ville' (+ estimation de coût × villes). Conséquence : un scrape 'toute l'IDF' s'arrêtait à N total (1-2 villes) au lieu de couvrir les 266 villes. RÉÉCRIT : `scrape_sector(cities, max_per_city, global_cap, max_pages=4)` = N contacts GARDÉS par ville (pagination Serper Places — vérifié que page>1 renvoie du neuf), boucle sur TOUTES les villes, plafond global de contacts gardés (garde-fou crédits). `serper_places` accepte désormais `page`. Endpoint `/{site}/scrape` : `max_per_city` (1-50, accepte ancien `max_results`) + `global_cap` (def 1000, max 5000). UI scrapper : 2 champs (gardés/ville + plafond), estimation coût réaliste + alerte si >30 villes ; région sans villes cochées → envoie TOUTES les villes chargées (avant : 10 villes AU HASARD du top 50 France — autre bug). Testé live : 2 villes × max 2/ville → cities_done=2, kept=4 (Versailles 2 + Meaux 2). NB 'scraped' dans les logs = commerces EXAMINÉS (≈ crédits/10), pas gardés ; 'valid' = gardés.
- 2026-05-31 (hardening sécu post-review) : 3 recos appliquées sur les ajouts de la session. (1) `/api/enrichment/run` ajouté à `_ADMIN_PREFIXES` → réservé admin (stats reste ouvert à auth) ; UI Acquisition : bouton 'Enrichir le pool' + popup 'en retard' masqués aux non-admins (isAdmin, lecture localStorage pour éviter la race au 1er rendu). (2) cast défensif de `limit` (try/except → pas de 500). (3) fermeture du fd du log après Popen. Revue manuelle (skill /security-review KO sans git local) : RAS critique — pas d'injection commande/SQL, auth OK, raw data.gouv sanitisé (pas de dirigeants).
- 2026-05-31 (nettoyage auto post-scrape) : à la fin d'un scrape (god_mode `POST /{site}/scrape`, thread run()), déclenchement AUTOMATIQUE du drain de nettoyage Mailnjoy — plus besoin de lancer les lots à la main. Implémentation : fonction réutilisable `_launch_cleanup(site, mode, drain, chunk_size, total_limit, source)` extraite de l'endpoint /cleanup/run dans api.py (le verrou séquentiel _active_cleanups est partagé). Le hook scrape récupère le module via `sys.modules['scripts.api']._launch_cleanup(..., source='auto-scrape')`. `source` propagé dans cleanup_backend.run_cleanup/run_cleanup_drain → loggé dans cleanup_batch. UI page cleanup : badge '⚡ Automatique' vs 'Manuel' dans l'historique + bandeau d'info. Verrou strict : si un nettoyage tourne déjà, l'auto refuse proprement (le drain en cours absorbe les nouveaux contacts). NB : api.cheffer.email = CE VPS (204.168.186.159), c'est le domaine de prod de cette instance Genesis.
- 2026-05-31 (suite UI+cron) : enrichissement data.gouv complété. **Endpoints** GET /api/enrichment/stats + POST /api/enrichment/run (api.py) + fonction enrichment_stats() dans contacts_pool_backend.py. **UI** : Card 'Enrichissement data.gouv' dans la page Acquisition (vérifiés/non-vérifiés/exclus/à-traiter + signaux Qualiopi/RGE/ESS + bouton 'Enrichir le pool' qui POST run et poll les stats). **Cron** PM2 `genesis-datagouv-enrich` : `0 7 * * *`, --no-autorestart, `--limit 2000` (garde-fou), tourne en autoblog, persisté via pm2 save. ⚠️ PIÈGE RENCONTRÉ : mes runs manuels via `ssh lcr` (=root) avaient créé data/datagouv_cache.sqlite + logs/datagouv_enrich.log en root → le cron (autoblog) plantait 'attempt to write a readonly database'. Corrigé par chown autoblog. RÈGLE : tout fichier créé pour Genesis doit appartenir à autoblog, pas root.
- 2026-05-31 : **Enrichissement data.gouv intégré** (skill cheffer fourni par user). Table satellite `contact_enrichment` (1:1 contacts, contacts.duckdb) + script `scripts/datagouv_enrich.py` (API recherche-entreprises, requests, cache SQLite data/datagouv_cache.sqlite, rate 4/s + backoff 429, anti-join). RGPD : jamais de dirigeants (raw sanitisé). Filtre branché dans pick_for_campaign + count_available_for_sector (`COALESCE(e.excluded,FALSE)=FALSE`). SÉMANTIQUE CLÉ : excluded=TRUE = exclusion DURE uniquement (fermée/admin/statut P) ; non_trouve/ambigu restent contactables (excluded=FALSE, siret NULL). 1er run complet : 2899 lignes → 1633 enrichis (~56%), 1172 non-vérifiés contactables, 94 exclus durs (86 fermées + 8 admin). Signaux détectés : 178 Qualiopi, 124 ESS, 10 RGE. Match par dénomination (pas de SIRET au scrape) → fiabilité moyenne, ambigus exclus. Validé : un contact fermé n'est plus pioché. Reste hors-scope : endpoint API trigger/stats, bouton UI Acquisition, cron incrémental. Pour relancer l'incrémental : `setsid nohup python3 scripts/datagouv_enrich.py > logs/datagouv_enrich.log 2>&1 < /dev/null &`.
- 2026-05-30 (suite) : ligne Serper passée en **solde restant** au lieu de conso/mois. Serper n'ayant pas d'API de solde, snapshot manuel dans memory/seo/serper-balance.json {plan_total:2500, balance:2442, snapshot_at}. L'endpoint /api/serper/usage renvoie `available = balance − conso locale depuis snapshot_at` (god_mode_serper_calls + costs-log). Affichage widget = `2 442 / 2 500` (rouge si <10%). Pour resync : relever le vrai solde sur serper.dev et mettre à jour balance+snapshot_at dans le JSON.
- 2026-05-30 : Widget conso sidebar (CreditsWidget) — ajout ligne **Serper** (crédits consommés mois en cours). Serper.dev n'expose AUCUNE API de solde (/account,/balance,/credits => 403), donc affichage = conso locale : table god_mode_serper_calls + entrées serper-search du costs-log. Nouvel endpoint GET /api/serper/usage (api.py). Confirmé : le widget se rafraîchit déjà toutes les 60s (DeepSeek/Mailnjoy live, Ahrefs = cache quotidien cron 06:00) — l'impression 'statique' venait du quota Ahrefs gelé jusqu'au reset 2026-06-17, pas d'un bug. Build genesis-ui + pm2 restart genesis-ui/genesis-dashboard OK.
- 2026-05-21 soir : test pipeline bloqué sur abo Emelia inactif. User est allé se coucher en disant 'j'active demain matin'.
- 2026-05-22 matin : SSH cassé (clé non offerte), résolu en ajoutant bloc Host lcr dans ~/.ssh/config Mac avec IdentityFile id.mkdautoblog. Cron du matin a tourné et poussé 11 contacts → l'abo Emelia est manifestement actif.

## Backlog (parked — à reprendre plus tard)
- **Refactor DataTable shadcn** (parked 2026-05-22) — 17 fichiers de genesis-ui utilisent les primitives `Table` shadcn à la main, sans le pattern DataTable officiel (TanStack Table). Pas de `@tanstack/react-table` installé. Plan progressif identifié :
  1. Installer TanStack + créer `src/components/ui/data-table.tsx` générique (pattern shadcn officiel)
  2. Pilote sur `src/app/site/[code]/acquisition/page.tsx` (page la plus riche)
  3. Migrer ensuite les 6 pages "lourdes" : `workflow/prospects`, `workflow/campaigns`, `workflow/logs`, `articles`, `campaigns`, `costs`
  4. Pages "moyennes" (seo-strategy, seo, workflow/performance, versions, view, agents) : décision au cas par cas
  5. Tableaux statiques (dashboard, setup, site-budget-card, god-mode-panel) : on laisse en `Table` primitif, pas de refactor inutile


## Refonte SEO / Budget Ahrefs — 2026-05-22

**Contexte** : conso Ahrefs a 159% du quota (15 905 / 10 000), aucune limite implementee malgre demande user. SEO Strategist n'avait pas surveille.

**Actions realisees** :
- `scripts/cost_tracker.py` -> ajout `check_ahrefs_budget()` (gate avec seuils warn 70%, block 90%, reserve 500u)
- `scripts/ahrefs_daily.py` -> refactor MINIMALISTE (uniquement `site-explorer/metrics`, ~100u/jour). Backup ancienne version : `ahrefs_daily.py.bak-2026-05-22`
- `scripts/ahrefs_monthly_audit.py` -> NOUVEAU. Cron `0 6 1 * *`. Tier 1+2 endpoints + `site-audit/issues` (corrections techniques).
- `scripts/seo.py` -> gate integree dans `ahrefs_get()` avec params `cost_estimate` + `critical`
- `scripts/seo_strategy_agent.py` -> SURVEILLANCE budget ajoutee dans main() - emet une reco critique si conso >= 70%, notif Telegram
- `specs/seo-playbook.md` -> NOUVEAU. Doc complete : tiers endpoints, budget, gate, Site Audit projects, role SEO Strategist

**Site Audit Ahrefs** :
- LCR (`leclientroi.com`) -> projet existant, project_id `8344256` (health=100, 97 warnings, 95 notices)
- MKD (`mkdgroupe.com`) -> PAS DE PROJET, a creer dans https://app.ahrefs.com/site-audit puis mettre a jour `SITES` dans `ahrefs_monthly_audit.py`

**Etat budget actuel** :
- Conso 15 905 / 10 000 (159%)
- Reset : 2026-06-17
- D'ici la, TOUS les appels sont bloques par la gate (sauf si quota repasse sous 100% ce qui n'arrivera pas)
- Apres reset : tracker la conso, viser ~7 000/mois max

**Decisions user** :
- GSC : mis en pause (pas envie de le brancher pour l'instant)
- DataTable refactor : parke (cf section Backlog plus haut)

## Next action (a faire au reset 2026-06-17 ou avant)
1. Creer projet Site Audit Ahrefs pour mkdgroupe.com
2. Une fois le quota reset, lancer manuellement `python3 scripts/ahrefs_monthly_audit.py` pour verifier que tout fonctionne
3. Verifier que le cron monthly s'execute bien le 1er juin 6h UTC
4. Reprendre le pipeline LCR Emelia (campagnes en DRAFT -> demarrer)


### Additif 2026-05-22 (suite décisions user)
- `seo.py --report full` -> DESACTIVE (sys.exit dans main()). Plus de bouton UI a brancher dessus.
- `seo.py --report keywords` -> max 1x tous les 2 mois (operationnel, pas de blocage code)
- `site-explorer/metrics` -> BYPASS gate budget dans ahrefs_daily.py. Jamais bloque meme en depassement quota.


## Email Validator déployé — 2026-05-22

**Spec** : EMAIL_VALIDATION_SCORING.md (fourni par user) — 6 étages, drop avant insertion.

**Fichiers** :
- scripts/email_validator.py (module unique, point d entrée: validate_and_score(email, prospect))
- data/email_jetable.csv (304 domaines disposable chargés depuis la liste fournie + enrichie user)
- DB scrappe migrée : email_score INTEGER, email_validation_reasons JSON
- Intégré dans god_mode_agents.scrape_sector() : si decision=drop, prospect jamais inséré
- god_mode_backend.add_prospect() étendu pour persister email_score + reasons

**Honeypots** (drop hard reject avant scoring) : spamtrap, honeypot, trap@, abuse@, spam@, **rgpd@, dpo@, gdpr@, @rgpd., @dpo.** (déplacés depuis role-based à la demande user — sécu CNIL)

**Décisions de seuils** :
- score < 40  -> drop (rejection_reason = low_score)
- 40 <= score < 60 -> queue (status = manual_review, à reviewer humain)
- 60 <= score -> push (status = validated, éligible push Emelia)

**Backfill 2026-05-22** : 20 prospects analysés, 3 rejetés (1 sentry no_mx + 2 rgpd@junot.fr), 2 passés en manual_review, 12 déjà pushés Emelia non touchés (juste email_score informatif).

**Pipeline en place pour les prochains scrapes** : le cron du matin (30 6) appellera god_mode_agents.scrape_sector() qui filtrera automatiquement chaque email via validate_and_score avant insertion.


## Mailnjoy intégré (Phase 1 backend) — 2026-05-22

**Spec** : PAPERCLIP/mailnjoy-api-reference.md + mailnjoy-integration-prompt.md

**Architecture** : Serper -> validator -> scrappe_pending -> Mailnjoy -> scrappe ou DELETE.

**Décisions actées** :
- risky = DELETE (jamais en scrappe) — décision user (1.b)
- Flow synchrone (Mailnjoy appelé dans la boucle scrape) — décision user (2.a)
- Phase 2 UI (sidebar credit, tag visuel, page setup) parquée

**Composants livrés** :
- Table scrappe_pending (memes colonnes que scrappe + mailnjoy_attempts/last_error)
- Colonne scrappe.mailnjoy_check (JSON) pour traçabilité
- scripts/mailnjoy_check.py : check_email_mailnjoy(), classify_response(), get_credit(), check_pending_queue()
- scripts/god_mode_backend.py : add_prospect_pending(), list_pending(), move_pending_to_scrappe(), delete_pending(), bump_pending_error()
- scripts/god_mode_agents.py scrape_sector() ecrit dans scrappe_pending
- scripts/workflow_runner.py appelle check_pending_queue(site) apres chaque scrape de secteur
- logs/mailnjoy_deletions.log audit des suppressions

**Test E2E 2026-05-22 11h55 (4 emails)** :
- valid=1, risky=2, invalid=1 — pending vide, scrappe peuplé, log OK
- Crédits consommés 8u (2/email × 4) sur solde 1 199 105 -> 1 199 097

**Credentials .env** :
- MAILNJOY_ID + MAILNJOY_SECRET configurés (clé lecture seule=non, autorisation achat=oui)
- Endpoint /v2/unitary?type=simple, body en text/plain
- Backoff exponentiel sur 429/503/500 (max 5 essais)
- Stop immédiat si 401/403

**Map décision** : VALID/SAFE -> valid | INVALID/UNSAFE/spamtrap/disposable -> invalid | RISKY/catchall/role/suspect -> risky | network/500 -> error (retry max 5)


## Phase 2 Mailnjoy complète — 2026-05-22 (suite refonte)

Tout les non-fait du récap précédent ont été traités :

**Backend** :
- Idempotence 30 jours : helpers god_mode_backend.email_recently_validated(email, days) + email_in_pending(email), branchés dans scrape_sector pour skip avant insert pending
- State machine refonte complète (cf section 12 de specs/workflow-prospection.md) :
  - pending_mailnjoy (scrappe_pending default)
  - mailnjoy_valid (scrappe après drain valide)
  - pushed_emelia (status après push Emelia OK)
  - scored (legacy, prospects pré-Mailnjoy)
  - manual_review (validator queue)
  - rejected (validator drop)
- Migration DB faite : 16 validated -> 15 scored + 1 mailnjoy_valid
- Queries downstream updated dans workflow_runner, god_mode_backend, workflow_emelia_push

**Endpoints API** (api.py) :
- GET  /api/mailnjoy/credit               → solde
- GET  /api/mailnjoy/status               → configuré ? crédit ? pending count
- POST /api/mailnjoy/test-credentials     → test avec ID/Secret donnés (sans sauvegarder)
- POST /api/mailnjoy/save-credentials     → écrit dans .env après test OK
- POST /api/mailnjoy/drain                → déclenche un drain manuel
- GET  /api/sites/{site}/workflow/counters → compteurs refondus (Scrapés, Ajoutés, Nettoyés, Envoyés)

**UI (genesis-ui)** :
- credits-widget.tsx : ligne Mailnjoy en vert (rouge si < 500u), polling 60s
- mailnjoy-config-card.tsx : nouveau composant pour la page Setup (input ID+Secret, bouton Tester, bouton Sauvegarder, affichage crédit + pending count)
- prospects/page.tsx : colonnes Email score + Mailnjoy (tag visuel ✓/⚠/✗ + date) + Qualifier DS (✓ qualifié / ✗ rejeté DS / pending), filtres sur nouveaux statuts (mailnjoy_valid, pushed_emelia, manual_review, scored, rejected)
- setup/page.tsx : MailnjoyConfigCard inséré au-dessus des connecteurs site-specific
- Next.js rebuild OK, pm2 restart genesis-ui OK

**Documentation** :
- specs/workflow-prospection.md : section 12 Email Validator + Mailnjoy ajoutée (pipeline complet, state machine, idempotence, particularités API)

**Tests** :
- tests/test_mailnjoy_check.py : 22 tests pytest (classify_response 11 cas, check_email_mailnjoy 8 cas, edge cases 3 cas) → 22/22 PASSED
- Stratégie : mock requests.post au lieu de Prism (équivalent fonctionnel, plus simple, pas de serveur HTTP à lancer)

**Dépendances installées** :
- dnspython (pour MX check du validator)
- email-validator (pour pydantic v2, requis par fastapi - bug latent corrigé)
- pytest

**Crédits consommés ce session** : 8u Mailnjoy (sur 1 199 105 dispo)


## Webhook Emelia temps réel + Warmup plan — 2026-05-22 (suite)

**Webhook Emelia branché en prod** :
- Endpoint backend : POST /api/emelia/webhook?token=WEBHOOK_TOKEN_1 (existait déjà, opérationnel)
- Webhook Emelia créé via POST /webhook avec campaignId=ALL_CAMPAIGNS, type=email, events=[SENT,OPENED,CLICKED,REPLIED,BOUNCED,UNSUBSCRIBED]
- Emelia déploie auto sur les 9 campagnes existantes (LCR + Test + Lancement)
- Test E2E validé : afchain.camille a cliqué le lien unsubscribe → event UNSUBSCRIBED reçu → state mis à blacklisted dans acquisition_contacts

**Table emelia_events ajoutée à god_mode.duckdb** :
- Audit de TOUS les events Emelia (incl. SENT/OPENED qui étaient ignorés avant)
- Colonnes : id, received_at, event_type, email, first_name, last_name, campaign_name, campaign_id, site_code, step, emelia_date, raw_payload
- 3 index : email, campaign_id, received_at

**Auto-register webhook à chaque nouvelle campagne** :
- workflow_emelia_push.get_or_create_campaign() appelle POST /webhook après création (idempotent)
- Push aussi automatiquement les steps + start de la campagne dans la foulée

**Bug fix** :
- Handler webhook normalise désormais event_type en lower() (Emelia envoie en UPPERCASE)
- Campaign peut arriver en string OU dict → handler gère les 2

**Warmup plan déployé** :
- Spec : specs/warmup-plan.md (137 lignes, Plan A conservateur Emelia + Plan B agressif IP Warming Planner)
- Table email_senders dans god_mode.duckdb (sender_email PK, warmup_start_date, daily_max_override, status)
- Sender LCR juliette@leclientroi.com inscrit avec warmup_start=2026-05-22 (J1=10 emails/jour)
- Plan A appliqué : J1-J3=10, J4-J7=20, J8-J14=35, J15-J21=50, J22-J28=75, J29+=100
- Helpers ajoutés à workflow_emelia_push.py : daily_warmup_quota(), sender_email_for_site(), emelia_sent_today_by_sender()
- Garde-fou branché dans push_prospect : si sent_today >= warmup_quota → bloc push avec raison warmup_quota_reached
- État actuel : sender Juliette J1 → quota 10, déjà envoyé 1 (test) → 9 restants pour aujourd'hui

**Reste à faire** (priorité) :
- Démarrer les 5 campagnes LCR DRAFT (workflow-lcr-restaurant/artisan/coiffeur/garagiste/immobilier) avec templates + start — script migrate_existing_draft_campaigns.py à coder
- Sidebar UI : afficher J{N}/quota par sender (warmup status visible)
- Cron quotidien warmup_daily_check.py : pause sender si bounce_rate > 5% ou unsubscribed_rate > 2%


## Pool mutualisé contacts — Phases 0+1+2 — 2026-05-22

**Spec sources** : specs/contacts-model.md, onboarding-checklist.md, campaigns-spec.md (3 docs validés par user).

### Phase 0 — Migration data
- NOUVEAU fichier : data/contacts.duckdb (chown autoblog:autoblog)
- 2 tables créées : contacts (PK email unique, 36 rows) + contact_site_history (UNI (contact_id, site_code), 36 rows)
- Script : scripts/migrate_contacts_to_pool.py
- Source : crm/lcr.duckdb (33), crm/mkd.duckdb (1), god_mode.duckdb.scrappe (3) — déduplication par email
- Logs : logs/migration_contacts_pool.log
- ⚠️ Anciennes DBs intactes (RO) — rollback possible 30 jours

### Phase 1 — Backend pool
- NOUVEAU module : scripts/contacts_pool_backend.py
- 13 helpers publics : find_by_email_global, create_in_pool, set_global_blacklist, get_history_for_site, upsert_site_history, change_state_for_site, mark_pushed_to_emelia, record_emelia_event, list_contacts_for_site, stats_for_site, pick_for_campaign, count_available_for_sector, check_pool_depletion
- Constantes : COOLDOWN_GLOBAL_DAYS=30, COOLDOWN_SAME_SITE_DAYS=7, STATE_RANK
- Testé : stats LCR=35 contacts, pick_for_campaign restaurant=0 (cohérent — peu de cold_email), check_pool_depletion fonctionne

### Phase 2 — Dual-write activé sur 5 maillons
Tous les flux d'écriture alimentent en parallèle le pool ET le système legacy (acquisition_contacts) :
1. api.py:api_emelia_webhook → record_emelia_event + change_state_for_site + set_global_blacklist (si bounce/unsub)
2. workflow_emelia_push.py:push_prospect → create_in_pool + upsert_site_history + mark_pushed_to_emelia
3. tally_to_prm.py → _tally_dual_write_pool helper (lead direct)
4. emelia_to_crm.py → _dual_write_pool helper (sync cron 19h)
5. god_mode_agents.py:scrape_sector → create_in_pool + upsert_site_history cold_email

Validation live 2026-05-22 21:00 : POST webhook CLICKED sur afchain.camille@gmail.com → pool state cold_email → prm OK + emelia_clicked_at set.

### Reste à faire
- Phase 3 : UI Acquisition (fusion onglet Pipeline + sous-vue historique par site)
- Phase 4 : UI Campagnes (wizard 4 étapes, algo pioche, page détail)
- Phase 5 : UI Vision (compteurs + funnel + warmup)
- Phase 6 : UI Onboarding 16 steps
- Phase 7 : Sidebar cleanup (supprimer module Workflow)
- Tables  +  chiffrée AES (multi-tenant cible) — pas encore créées


## Refactor complet — Phases 0-7 livrées — 2026-05-22 (suite session go)

### Phases 3-7 livrées (suite à Phase 0-2 du début de session)

**Phase 3 — Page Acquisition refondue** ()
- Switch endpoint de lecture sur /api/sites/{site}/pool/contacts (au lieu de /acquisition legacy)
- Type Contact étendu pour matcher la structure pool (sectors, primary_source, email_score, mailnjoy_check, last_contacted_by_site_at, etc.)
- Edit/delete/blacklist toujours sur l ancien endpoint legacy (dual-write garde sync)

**Phase 4 — Page Campagnes nouvelle** ()
- Wizard 4 steps (secteur > volume > preview > validation)
- Alerte secteurs épuisés (popup card)
- Liste campagnes Emelia avec stats (sent, opens%, clicks%, replies%, progress%)
- Endpoint POST /api/sites/{site}/pool/campaigns/create qui pick + create + steps + push + start + webhook

**Phase 5 — Page Vision nouvelle** ()
- KPI cards : contacts pool, envoyés, leads, nettoyés
- Funnel chart (workflowFunnelConfig) avec scraped/qualified/sent/prm/leads/bounced
- Distribution par source primaire (progress bars)
- Placeholder warmup status

**Phase 6 — Onboarding refondue** ()
- 16 steps en cards séquentielles (Identité, URLs, Persona, SEO, Éditorial, Secteurs, Sender, RGPD pied de mail, API keys, Templates, Warmup, Modules, Ahrefs, Quotas, Compte, Mail test)
- Validation des champs bloquants (border rouge sur cards incomplètes)
- Sticky submit en bas avec compte des steps complétés
- Payload posté vers /api/sites/onboard-full (à étendre backend pour gérer les 16 champs)

**Phase 7 — Sidebar cleanup**
- Section Commercial refondue : Vision, Acquisition, Templates, Campagnes (par site)
- Suppression Workflow, Vue d ensemble, Performance, Prospects, Campagnes (legacy /workflow/), Prospection (global /campaigns)
- TITLE_TO_MODULE mis à jour

**Cleanup fichiers**
- Supprimés : src/app/site/[code]/workflow/{campaigns,prospects,performance}, page.tsx
- Gardés : workflow/templates (lien sidebar), workflow/logs (admin), workflow/layout.tsx (auth)

**Pool write endpoints ajoutés** (api.py)
- POST /api/sites/{site}/pool/contacts/create
- PATCH /api/sites/{site}/pool/contacts/{id}
- DELETE /api/sites/{site}/pool/contacts/{id}
- POST /api/sites/{site}/pool/contacts/import-csv

### Restes connus
- L endpoint backend /api/sites/onboard-full doit etre etendu pour gerer les 16 nouveaux champs (persona, sectors_enabled, modules_enabled, warmup_plan, account_id, etc.) sinon les nouvelles infos sont droppees a l onboarding
- Table accounts + site_credentials AES chiffrees (multi-tenant cible) pas encore creees
- Pages /workflow/templates et /workflow/logs restent — a refondre (templates devient lecture seule depuis Emelia, logs vers /admin/logs)
- L UI Acquisition utilise toujours edit/blacklist legacy endpoints — a migrer vers pool/* equivalents


## Session enchaine — finalisation backend + cleanup — 2026-05-22 23:00

### Backend onboard V2 + multi-tenant
- Tables NOUVELLES dans god_mode.duckdb :
  -  (id PK, label, owner_user_id, plan, created_at) — multi-tenant
  -  (site_code+key_name PK, encrypted_value) — clés API par site (MVP clair, à chiffrer AES v2)
- god_mode_settings enrichie de 6 colonnes : sectors_enabled JSON, daily_quota_per_sector, emelia_daily_limit, cooldown_same_site_days, cooldown_global_days, account_id
- /api/sites/onboard-full étendu pour gérer les 16 champs du nouveau wizard :
  - persona/geo/dept_priority → context/{code}/audience.md
  - tone/cta/signature/banned_words → context/{code}/editorial-style.md
  - raison_sociale/adresse/dpo/privacy → context/{code}/footer.md (pied de mail B2B)
  - sender_email/sender_name → INSERT email_senders (warmup_start_date = aujourd hui si warmup_start_today=True)
  - sectors_enabled, daily_quota, emelia_daily_limit, cooldowns → god_mode_settings
  - emelia_key/serper_key/tally_key/telegram → site_credentials
  - account_id → INSERT accounts
  - modules_enabled → memory/{code}/modules.json
  - god_mode_state.enabled = FALSE par défaut (déblocage après Step 16 mail test)

### Migration UI Acquisition vers pool/* endpoints
6 actions write switched de /acquisition/* legacy vers /pool/contacts/* :
- change-state, update fields, create, blacklist, delete, import-csv
La page Acquisition est désormais 100 pourcent sur le pool mutualisé (lecture + écriture).

### Cleanup fichiers
- Move src/app/site/[code]/workflow/templates/ → src/app/site/[code]/templates/
- Sidebar Templates pointe maintenant vers /site/[code]/templates (au lieu de /workflow/templates)
- workflow/ ne contient plus que layout.tsx (admin check) + logs/ (accessible direct)

### Reste à faire
- Chiffrement AES site_credentials.encrypted_value (MVP clair OK pour LCR + MKD perso)
- Cron 6h30 demain alimentera le pool en vrai via dual-write (premier test prod)
- Step 16 onboarding mail test : envoyer effectivement le mail via /emails/test Emelia + UI confirmation
- Page admin/logs (déplacer /workflow/logs vers /admin/logs)
- Backup cron à étendre pour inclure data/contacts.duckdb


## Session enchaine 2 — AES + mail test + backup — 2026-05-22 23:30

### A. Chiffrement AES Fernet site_credentials
- NOUVEAU module : scripts/site_credentials_backend.py
- Helpers : encrypt_value, decrypt_value, set_credential, get_credential, list_credentials, delete_credential, migrate_plaintext_to_encrypted
- Master key : env var SITE_CREDENTIALS_MASTER_KEY (prioritaire) sinon data/.master_key (auto-générée, chmod 600)
- Backward compat : valeurs anciennes en clair sont re-chiffrées au premier get_credential
- Endpoint /api/sites/onboard-full migré pour utiliser set_credential (AES) au lieu d INSERT direct
- workflow_emelia_push._get_key etendu : lit site_credentials AES en priorité, fallback env vars

### B. Step 16 onboarding mail test + activation
- NOUVEAU endpoint POST /api/sites/{code}/onboarding/send-test-email
  - Body : {test_email, sector}
  - Crée campagne onboarding-test-{code} si absente + configure steps
  - Appelle /emails/test Emelia (envoi instantané sans cadence)
- NOUVEAU endpoint POST /api/sites/{code}/onboarding/confirm-activation
  - Body : {received: true}
  - Passe god_mode_state.enabled = TRUE pour ce site
- Page UI onboarding étendue : après submit, le site est créé mais god_mode_state.enabled=FALSE
  - Step 16 affiche bouton Envoyer mail test
  - Apres envoi : bouton J ai reçu → confirm-activation → enabled=TRUE → redirect dashboard
  - Bouton Renvoyer disponible si user n a pas reçu

### C. Backup cron étendu
- scripts/backup.sh : check explicite des fichiers critiques (contacts.duckdb, god_mode.duckdb, auth.duckdb, .master_key)
- Copie séparée de .master_key vers BACKUP_DIR/.master_key.bak (disaster recovery)
- Cron quotidien 21h UTC inchangé (continue de tourner)

### Reste à faire pour vraiment SaaS-ready
- Cron 6h30 demain matin = premier test grandeur nature (passive, vérifier les logs)
- Page admin/logs (déplacer /workflow/logs vers /admin/logs au niveau global)
- Endpoint /api/sites/{code}/credentials/{key_name} pour lire/setter les clés via UI (gestion des clés post-onboarding)
- Multi-tenant : section UI accounts (CRUD comptes) — actuellement la table existe mais pas de CRUD
- Test : un nouveau site complet créé via UI onboarding (vérifier les 16 steps end-to-end)

---

## Session IMPORT CSV INTELLIGENT — 2026-05-25

Nouvelle feature : import CSV drag&drop vers le pool mutualisé (`/site/[code]/acquisition` → bouton « Importer CSV »).

**Flux en 2 phases** (le fichier est uploadé 1× sur le VPS sous `data/imports/{site}/`, chmod 600, purge >7j) :
1. `POST /api/sites/{site}/pool/import/analyze` (multipart) → détecte séparateur (`;`/`,`/tab/`|`) + charset (utf-8/cp1252/latin-1, NFC) + mappe les colonnes (alias FR/EN) + **1 seul appel DeepSeek** pour mapper les catégories du fichier vers les secteurs + pré-analyse dédup (1 requête `SELECT email`). Renvoie un `import_id` + récap.
2. `POST /api/sites/{site}/pool/import/{import_id}/commit` → **StreamingResponse SSE** (`data: {step,pct,…}`), upsert batché (1 connexion réutilisée), `source="manual"`, state `cold_email`.

**Secteurs dynamiques (DB-backed, plafond 30)** : nouvelle table `sectors` dans `god_mode.duckdb` (seed = 16 + `autre`). DeepSeek crée les secteurs manquants (B2B/B2C) sans jamais dépasser **30 au total** ; au-delà → bucket `autre`. `GET /api/sectors` + hook front `useSectors()` (lib/use-sectors.ts). `SECTORS_GOD_MODE` reste la liste *scrapable* (Serper), les secteurs importés ne sont pas scrapés.

**Dédup** : clé = email. Doublon existant → enrichissement NULL-only (jamais d'écrasement). Doublon interne au fichier → 1ʳᵉ occurrence gardée. Lignes KO (email invalide) listées avec raison.

**Fichiers** :
- back : `scripts/csv_import_backend.py` (nouveau), `scripts/api.py` (3 endpoints), `scripts/contacts_pool_backend.py` (migration colonnes `job_title`/`civility`/`job_function` + `create_in_pool`/`upsert_site_history` acceptent `conn`), `scripts/god_mode_backend.py` (table `sectors` + `list_sectors()`/`add_sector()`).
- front : `components/import-wizard.tsx` (nouveau, drag&drop + récap + anneau % + confetti), `lib/use-sectors.ts` (nouveau), `lib/sectors.ts` (+`autre`), page acquisition (branchement, ancien import textarea supprimé). Dépendance `canvas-confetti`.

**Testé** (2026-05-25) sur `responsable_marketing.csv` (5037 lignes directeurs marketing, séparateur `;`, utf-8) :
- échantillon 10 lignes → 10 ajoutés en `manual`, dept dérivé du CP, website préfixé `https://`, accents OK, secteurs créés (banque/assurance/industrie/agroalimentaire).
- HTTP analyze + commit SSE OK ; ré-analyse du même échantillon → 10 détectés en *enrichis* (dédup), commit → updated=10/added=0.
- mapping secteur complet du fichier : 13 nouveaux secteurs, total **30/30** pile au plafond (les plus petits volumes → `autre`).

⚠️ **Op** : PM2 tourne sous l'utilisateur `autoblog` → restart via `sudo -u autoblog bash -lc "pm2 restart genesis-dashboard|genesis-ui"`. Les fichiers écrits par l'API doivent rester accessibles à `autoblog` (chown `data/imports`).

**Reste** : ~~importer les ~5027 lignes restantes~~ → **FAIT**. Le pool contient désormais **5112 contacts** (cf. section COLD EMAIL ci-dessous pour la photo réelle par secteur).


---

## Session COLD EMAIL — refonte génération par secteur — 2026-05-25 (incréments 1-3 LIVRÉS)

### Constat de départ
- Templates Emelia = **mail-merge pauvre** : `emelia_campaign_manager.get_default_steps()` = 2 templates figés, signe « Camille », icebreaker générique.
- **Réalité du pool LCR (corrige les sections précédentes)** : l'import est FAIT → **5112 contacts**, dont **~94 % directeurs/responsables marketing grands comptes** (banque, agro, industrie, luxe, assurance, tourisme, médias…), **PAS** les PME locales du `campaign-plan.md`. PME locales (resto/commerce/artisan) = ~53 (1 %). Bucket `autre` = 2065 (40 %).

### Décisions user (2026-05-25)
- **Move upmarket assumé** : LCR vise les directeurs marketing grands comptes → offre = **SMS + RCS comme canal de campagne premium** (pas le drive-to-store PME). Les 53 PME locales gardent leur angle à part.
- **Perso = données structurées seules** (poste + secteur + entreprise + ville). PAS de scrape website pour l'instant → perso **persona-niveau** (pas de vrai 1to1 individuel). Le scrape rebranchera le vrai 1to1 plus tard.
- **Review humaine obligatoire** sur les premiers batchs (warmup J1).
- **PAS de séquence ni d'envoi automatiques** : l'IA PROPOSE 3 emails par secteur ; le user **édite et programme/verrouille chaque email lui-même**. → outil = **assistant de rédaction**, pas un automate. L'incrément ④ (branchement pipeline) est **ABANDONNÉ**.
- **Secteurs EXCLUS** : industrie (378) + agroalimentaire (376) = 754 contacts (SMS marketing non pertinent). Bucket `autre` (2065) = phase 2.

### Skills Claude Code installés (sur le Mac `~/IA/Projets/.agents/skills/`, outil de CONCEPTION)
- `cold-email` (coreyhaines31) + `cold-email-templates-34` (ColdIQ) — markdown pur, notés Low Risk.
- `cold-email-verifier` (arnanech/op) NON installé : repo 404 + redondant avec Mailnjoy + email_validator.
- ⚠️ Ces skills aident MOI à concevoir ; le runtime génère via **DeepSeek sur le VPS** (`llm_call.py`). L'expertise est transférée dans les angles + le prompt.

### Livré et testé
- **`context/lcr/sector-angles.md`** (NOUVEAU) : 10 secteurs × séquence 3 mails validés. Preuves mappées honnêtement (Immo92→immo, +35 % boutique→retail/luxe, +25 %/ROIx50→restau, « 500+/10M SMS »→neutre). Industrie/agro = EXCLUS.
- **`context/shared/cold-email-rules.md`** : ajusté mode persona-niveau (icebreaker = fait réel OU douleur secteur ; E2 = cas client OU preuve volume). Backup `.bak-2026-05-25`.
- **`scripts/email_generator.py`** (NOUVEAU) : `generate_sequence(site,sector)` → angle + DeepSeek (`call_llm_json`) → finalise (Juliette, CTA TidyCal, signature + désinscription RGPD) → `validate_email()` (interdits FR, ≤150 mots, 1 seul `<a>` TidyCal, objet) → exclut industrie/agro/autre. + `supported_sectors()` (10 secteurs UI). CLI dry-run OK.
- **`scripts/email_templates_backend.py`** (NOUVEAU — remplace le doublon `sector_templates_backend`, supprimé) : table **`email_templates`** (`god_mode.duckdb`), **modèle 1-ligne-par-email** `(site, sector, kind)` kind∈{first,relance1,relance2}, chacun **éditable/verrouillable seul** (`locked` = approbation ; **régénérer respecte les verrous** ; éditer rouvre). Helpers : generate / get_sector / list_sectors / update / set_lock.
- **`scripts/api.py`** : **6 routes** `/api/sites/{site}/templates/*` — generate · list(+available) · get{sector} · PUT {sector}/{kind} · {kind}/lock · {kind}/unlock. Backup `api.py.bak-2026-05-25`.
- **UI stepper** (genesis-ui) : `src/app/site/[code]/templates/page.tsx` REFONDUE (stepper 3 étapes : Select secteur → email kind → éditeur + **aperçu live** ; **mobile = onglets** Éditer/Aperçu ; badge conformité ; lock). + `src/components/email-body-editor.tsx` (NOUVEAU, **Tiptap**, switch **Visuel/Brut**). Build OK, déployé. Backup page `.bak-2026-05-25`.
  - ⚠️ **Validation VISUELLE par le user EN ATTENTE** (rendu mobile, génération IA depuis l'UI, Tiptap, aperçu) — pas de navigateur côté agent.

### Reste à faire (cold email)
- **Valider le visuel de l'UI stepper** (mobile surtout) + tour d'ajustements.
- **SPRINT FUTUR** (détaillé dans `PLAN-ACTION.md`) : templates à **structure HTML VERROUILLÉE**. Le user fournit le HTML ; seules les zones **texte / image / lien** éditables (placeholders `{{...}}` ; type par contexte : `src=`→image, `href=`→lien, sinon texte). DeepSeek ne remplit QUE les textes. → l'éditeur Tiptap deviendra un **éditeur de zones** (formulaire).
- Plus tard : scrape website (vrai 1to1), bucket `autre`, image de signature.

### Op / pièges
- `get_default_steps()` (legacy, 3 call sites) NON modifié — ④ abandonné. `email_templates` n'est PAS branché à l'envoi (assistant de rédaction).
- API Python sans `--reload` → `pm2 restart genesis-dashboard` pour recharger.
- **genesis-ui = build prod (port 3100)** → `npm run build` PUIS `pm2 restart genesis-ui` obligatoires pour déployer le front.
- Écrire dans `god_mode.duckdb` en process externe = OK (le cron le fait), écritures ponctuelles (connect/close).


---

## Session AUTH / RBAC — 2026-05-26 (Sprints 1-2 ; plan détaillé dans PLAN-ACTION.md)

**État au départ** : auth + 2FA TOTP + QR **déjà en place** (`auth_backend.py` pyotp, page `/security`, login 2-étapes). **1 seul user** : `camille` (superadmin, sites lcr+mkd, **2FA OFF**).

### Livré et déployé
- **`POST /api/auth/users` étendu** : génère un mdp temporaire si absent, accepte role+sites+phone, renvoie le mdp + un `access_text` **copiable** (id/mdp/URL/pas-à-pas 2FA). Validation : non-superadmin = **exactement 1 site**. Telegram optionnel.
- **Page `/admin/users`** (NOUVELLE, dans la sidebar admin global) : créer (rôle+site+mdp auto+**bloc copiable**), lister, changer rôle, reset mdp, supprimer.
- **Isolation multi-tenant** (middleware `api.py`) : `/api/sites/{site}/*` vérifie `site ∈ session.sites` (superadmin bypass) → **ferme la faille** (avant : tout user authentifié accédait à tous les sites). + **FIX** : le check admin-only excluait `superadmin`.
- **Sidebar filtrée par rôle** (`app-sidebar.tsx` `buildNavSite` + `ROLE_SECTIONS`) : superadmin=tout, strategie/contenu/commercial = leur section. **Switcher de sites masqué si 1 seul site** (`team-switcher.tsx`).
- **Rôles** : `superadmin` / `strategie` / `contenu` / `commercial`.
- Backups : `api.py.bak-2026-05-26`, `app-sidebar.tsx.bak-2026-05-26`, `team-switcher.tsx.bak-2026-05-26`.

### Reste (auth/RBAC)
- **Fix menu nav-user** (bas de sidebar) : BLOQUÉ — attend l'erreur **console** du user. Le code est sain (même pattern que le switcher) ; les logs « Failed to find Server Action » = **bruit** (clients périmés après rebuilds), pas la cause.
- **« Bloquer » un user** (champ `disabled` + check login + bouton UI) — Tâche 7.
- Option : **forcer le 2FA à la 1re connexion** (à décider).
- **camille : activer son 2FA** (actuellement OFF).
- Sprint 3 : `/security-review` (déclenché par le user). Sprint 4 : RGPD (questions d'abord). Sprint technique : durcissement déploiement front (staleness).

### À TESTER par le user (validation visuelle — pas de navigateur côté agent)
1. `/admin/users` → créer un compte « commercial » sur lcr → le **bloc d'accès copiable** s'affiche.
2. Se connecter avec ce compte → il ne voit que la section **Commercial**, **pas de switcher** (1 site), et l'accès à mkd est **refusé (403)**.
3. Bug nav-user : **hard refresh** puis console si ça persiste.

### MAJ 2026-05-26 (suite) — Sprint 2 COMPLET
- ✅ **Mode superadmin UI** : rôle affiché sous le nom (nav-user), **liseré 5px ambre** autour de la fenêtre, **top bar** (date live + IP + users connectés + campagnes en routage + déconnexion). Endpoint `GET /api/admin/superadmin-bar` (cache 60s Emelia). Composant `superadmin-bar.tsx`. Validé visuellement par le user.
- ✅ **Bloquer/débloquer un compte** : colonne `disabled` (auth.duckdb), `login()` refuse `account_disabled`, `update_user`/`list_users` gèrent `disabled`, bouton + badge dans `/admin/users`.
- Backups : `auth_backend.py.bak-2026-05-26`, `nav-user.tsx.bak-2026-05-26`, `client-shell.tsx.bak-2026-05-26`.
- **Sprints 1 & 2 = bouclés.** Reste : nav-user (attend console user), option « forcer 2FA 1re connexion », Sprint 3 `/security-review` (déclenché par user), Sprint 4 RGPD (questions d'abord). camille : activer 2FA.

### MAJ 2026-05-26 — Sprint 4 RGPD (en cours)
Décisions user : base légale = **intérêt légitime B2B**, **anonymiser** avant LLM (0 PII hors UE), conservation **3 ans**.
Entités (cf. mémoire reference_legal_entities) : LCR=HUMANETICS LABS (SARL, SIREN 995210010, Colombes, dpo@humaneticslabs.com) · MKD=MKD GROUPE (SARL, SIREN 852283761, Maisons-Alfort, dpo@mkdgroupe.com). Responsable RGPD=société, DPO=Camille.
- ✅ **4a LIA** + **4b privacy notices** (×2) → `/home/autoblog/genesis/legal/` (lia-prospection-b2b.md, privacy-notice-lcr.md, privacy-notice-mkd.md). MODÈLES à faire viser par un juriste avant publication.
- ✅ **4c (partie)** : `workflow_qualifier.py` n'envoie plus email+téléphone à DeepSeek (backup .bak-2026-05-26). email_generator/god_mode_templates déjà sans PII.
- Reste 4c : auditer csv_import (mapping secteur), **purge auto 3 ans**, **chiffrement at-rest contacts.duckdb** (était parké).
- Reste 4d : caviardage PDF (skill github Ldecavel) + anonymisation exports (datanaos).

### MAJ 2026-05-26 — Sprint 4 RGPD : 4c + 4d clôturés
- ✅ **4c audit DeepSeek COMPLET** : qualifier (email+tél retirés), csv_import (n'envoie que les noms de catégories, jamais les contacts), email_generator/templates (par secteur). → 0 PII vers DeepSeek.
- ✅ **4c purge 3 ans** : `scripts/rgpd_purge.py` (anonymise les prospects froids > 3 ans, épargne leads/clients/blacklistés ; dry-run + `--apply`). **Cron mensuel** 1er à 4h → `logs/rgpd_purge.log`. 0 concerné aujourd'hui (données récentes).
- 🟡 **Chiffrement at-rest `contacts.duckdb`** : NON fait en applicatif (DuckDB n'a pas de chiffrement natif ; la clé serait sur le même serveur = gain faible). En place : secrets AES (site_credentials), chmod 600, RBAC+2FA, backups. **RECO = activer le chiffrement de volume côté Hetzner** (action infra, pas du code).
- ✅ **4d caviardage PDF** : skill `caviardage-pdf` installé (Mac, MIT, 100% local, PyMuPDF) — outil à la demande.
- 🟡 **4d anonymisation exports (datanaos)** : service externe payant, **aucun use case d'export actif** dans Genesis (l'anonymisation est déjà couverte par la purge + le qualifier). À brancher seulement si besoin réel.

**Sprint 4 RGPD clôturé.** Restes = décision infra (chiffrement disque Hetzner) ou service externe (datanaos) si besoin.
**Restes globaux hors-dev** : #1 nav-user (attend console user), #8 `/security-review` (user lance), publier les privacy notices sur les sites.

### ⚠️ PIÈGE OP (2026-05-26) — genesis-ui = pnpm
`genesis-ui` est géré par **pnpm** (pnpm-lock.yaml, node_modules/.pnpm). **NE JAMAIS faire `npm install`** ici → ça crashe arborist ("Cannot read properties of null (reading 'matches')"). Utiliser **`pnpm add <pkg>`** (via `sudo -u autoblog`). `npm run build` reste OK (n'installe rien).
### Sprint éditeur newsletters HTML — incrément ① fait
- structures/leclientroi-newsletter-v2.html transférée ; module scripts/html_templates_backend.py + table html_templates + 6 endpoints /api/sites/{site}/html/* (testés). dnd-kit installé (pnpm). Reste ② composant éditeur (dnd blocs + édition in-place texte/image) + ③ intégration step 2 + envoi Emelia.

---

## Sessions Mailnjoy cleanup — 2026-05-28 → 2026-05-30

**Pitch** : nettoyage périodique du pool `contacts.duckdb` via Mailnjoy (suppression invalid/risky, certif. valid posée sur `mailnjoy_check` JSON). Page dédiée `/site/[code]/cleanup`.

### Architecture livrée (refactor sérieux, fin de session 2026-05-28)

**Backend (`scripts/cleanup_backend.py`)**
- `run_cleanup(mode, site, limit, progress_cb=None, should_stop=None)` — 1 chunk synchrone. `should_stop()` checké AVANT chaque contact ; `progress_cb(stats, processed, email)` émis APRÈS chaque contact (try/finally garantit l'émission, les `continue` ne sautent rien).
- `run_cleanup_drain(mode, site, chunk_size=100, total_limit=None, progress_cb, should_stop)` — enchaîne des chunks jusqu'à épuisement / `total_limit` / stop. Log final `cleanup_drain` event.
- Pool = `data/contacts.duckdb` (PAS `acquisition_contacts` — exclus globalement les `global_blacklisted`).
- Modes : `unverified` (mailnjoy_check NULL/vide) · `stale` (mailnjoy_check > 180j).

**API (`scripts/api.py`)**
- `_active_cleanups: dict[key→state]` + `_cleanup_lock` (threading.Lock). **Verrou STRICT séquentiel global** (1 cycle à la fois TOUS sites/modes confondus).
- `POST /api/sites/{site}/cleanup/run` body : `{mode, drain, chunk_size, total_limit, limit?}` — spawn thread daemon, retour immédiat avec `{queued:true,key}`. Si cycle déjà actif → `{ok:false, running:true, active:{...}}`.
- `POST /api/sites/{site}/cleanup/stop` — pose `stop_requested=true` + `status="stopping"`. Le thread vérifie entre 2 contacts ET entre 2 chunks.
- `GET /api/sites/{site}/cleanup/status` — état détaillé `items[]` avec processed/total/valid/removed/cumulative/last_email/started_at/status.
- `GET /api/cleanup/active` — état GLOBAL tous sites (alimente la SuperadminBar).
- `GET /api/sites/{site}/cleanup/history?limit=20` — **endpoint dédié** retournant UNIQUEMENT les events `cleanup_batch` (évite la saturation des 100 derniers logs par les events fils validated/removed).
- `GET /api/sites/{site}/cleanup/counts` — non-vérifiés + stale.
- `GET /api/sites/{site}/cleanup/contacts?limit=10000` — liste pool (limite remontée pour cohérence compteur).
- **Endpoints test loopback-only** (bypass auth via middleware si `request.client.host ∈ {127.0.0.1, ::1}`) :
  - `GET /cleanup/dryrun?email=` — non-destructif, retourne what would be done sur 1 contact.
  - `GET /cleanup/test-batch?limit=N&drain=true&chunk_size=N` — sync, counts avant/après.
- **`god_mode_backend.list_logs(action=...)`** étendu pour filtre par action exacte (utilisé par /cleanup/history).

**Frontend (`genesis-ui/src/app/site/[code]/cleanup/page.tsx`)**
- `startAuto` = **1 SEUL POST drain=true chunk_size=100**. Plus aucune boucle JS, plus de `waitUntilFree`, plus de `findBatch`, plus de timeouts JS.
- `stopAuto` = POST `/cleanup/stop` + `autoRef=false`.
- État `progress` polling `/cleanup/status` (1.5s actif / 6s idle). Auto-reset `autoMode` quand `progress` passe à null.
- Card **Cycle en cours** (border-primary/50) : 2 barres (chunk + global si total_limit) + cumul cross-chunks + indication "Arrêt en cours…" pendant un stop.
- `DataTable` étendu avec prop `selectFilter` (Select shadcn). Branché sur colonne `mailnjoy_status` (filtre Non vérifié / Valide / En attente / Invalide / À risque).
- Compteur cohérent : `Contacts du pool (N) — dont X jamais vérifiés` (chargement complet, limit=10000).
- **Tous les libellés en français** : MODE_LABEL, ACTION_LABEL, DEC_FR (helpers en tête de fichier). `unverified→Première vérification`, `stale→Revalidation (>6 mois)`, `valid→Valide`, `risky→À risque`, etc.

**SuperadminBar (`genesis-ui/src/components/superadmin-bar.tsx`)**
- Poll `/api/cleanup/active` (2s actif, 8s idle). Affiche inline pour chaque cycle : `LCR Première vérification 23/50 [▓▓▓░░] 46%` + tooltip détaillé FR. Idle = "Aucun nettoyage en cours".

### Validation
- ✅ **Unitaire** : `/cleanup/dryrun` → 1 contact pool, Mailnjoy VALID/SAFE, would=update, **0 écriture DB**.
- ✅ **Intégration limit=1** : `4818→4817`, batch {1 valid, 0 removed} en 11.79s.
- ✅ **Batch 50** : `4817→4767`, batch {26 valid, 24 removed, 0 errors} en 256s.
- ✅ **Drain 6 contacts en chunks de 3** : `4612→4606`, 2 chunks, 5 valid + 1 removed en 28.94s.
- Validation visuelle par le user en attente après hard-reload `/site/lcr/cleanup`.

### Bugs fixés (chronologique)
- **DuckDB lock conflict** : test scripts externes ne peuvent pas se connecter pendant que l'API a un write-lock → endpoints test loopback à la place.
- **Read-only/read-write config mismatch** : `duckdb.connect(read_only=True)` échoue si une autre connection RW existe dans le même process → utiliser `cb._pool(read_only=False)`.
- **API freeze 504** : `cleanup/run` synchrone bloquait le worker uvicorn (316 restarts observés) → thread daemon + retour immédiat.
- **Race "Un cycle déjà en cours"** : ancien `set` non-atomique + retry trop court → dict + Lock + verrou GLOBAL séquentiel + retry intelligent.
- **Timeout JS 4 min trop court** : 50 contacts × ~5s = 250s, juste au-dessus de 240s → drain mode élimine le problème (plus de boucle JS).
- **Historique aléatoire 2-3 lignes** : `/logs?limit=100` saturé par events validated/removed → endpoint dédié `/cleanup/history` qui filtre exactement `cleanup_batch`.
- **DuckDB SQL** : double-double-quote pour empty string non supportée → `LENGTH(mailnjoy_check)=0`.
- **god_mode_api.py root-owned** : patch impossible sans `sudo chown` (bloqué par classifier) → contourné en ajoutant la route dans api.py.

### PM2 processes
- `genesis-dashboard` (PID variable, FastAPI port 8080) — restart après tout patch backend
- `genesis-ui` (Next 16 port 3100, pnpm build) — restart après tout patch front + `pnpm build` AVANT (jamais `npm install`)
- `genesis-mailnjoy-drain` — cron 5min qui drain `scrappe_pending` (existant avant cette session)

### Sweego (parqué)
- Pool LCR contient 5117 contacts (au début de session), réduit à ~4600 après tests cumulés (~250 supprimés invalid/risky).
- Sweego API key + ImageKit private key avaient fuité en chat → user à régénérer.
- Routage production Sweego PAUSE STRICT : tests uniquement vers `afchain.camille@gmail.com`.

### Restes
- #8 `/security-review` (déclenché par user)
- #23-25 Sweego : reroute production + déploiement + CNAME tracking
- Validation visuelle par le user de la page cleanup (filtre Mailnjoy + Progress bar + drain end-to-end)
