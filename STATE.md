# STATE — Genesis (à lire EN PREMIER au démarrage de session)

> Source de vérité unique pour reprendre le projet sans re-expliquer le contexte.
> À mettre à jour AVANT toute fin de session ('à demain', 'j'en ai marre', etc.).

## Dernière mise à jour
2026-05-22 17:50 UTC (warmup plan + webhook Emelia opérationnel temps réel)

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
