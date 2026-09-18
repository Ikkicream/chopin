# PLAN — Module « Test email » (newsletters) via `@emailens/cli`

> Statut : **IMPLÉMENTÉ** (2026-05-27). Plan validé par Camille (install global épinglé · lint+analyze · progression par étapes · bouton sur structures + versions).

## 0. Contexte réel du projet (analyse de l'existant)

| Élément | Réalité Genesis |
|---|---|
| Frontend | Next.js 16 (`genesis-ui`, **pnpm**, port 3100). Page cible : `src/app/site/[code]/newsletters/page.tsx` (composant `ItemCard` = 1 ligne par structure/version) |
| Backend | **FastAPI Python** (`scripts/api.py`, port 8080) — PAS de route API Next.js. Tout passe par le backend Python |
| Génération emails | HTML **brut** : newsletters = `structures/*.html` éditées → versions (`html_templates` via `html_templates_backend.py`). Cold emails = DeepSeek (`email_generator.py`). **Pas de React Email / MJML** |
| Envoi | Emelia API (`rawHtml:true`). Newsletters : pas encore câblées à l'envoi |
| Validation existante | `email_validator.py` = validation d'**adresses** (MX, jetable, RGPD). `email_generator.validate_email` = corps cold (mots/CTA). **Aucun linter HTML email** → c'est le trou que `@emailens/cli` comble (zéro recouvrement) |
| Node sur VPS | **v22.22.2 + npx 10.9.7** ✅ (le CLI peut tourner sur le VPS) |

## 1. Architecture du workflow (emailens au centre)

```
[Page newsletters]  clic "Tester" sur une ligne (à côté de Éditer)
        │  POST { html }  (ou ref structure/version)
        ▼
[FastAPI]  /api/sites/{site}/html/lint
        │  1. écrit le HTML dans un fichier temp (/tmp)
        │  2. subprocess:  emailens lint <tmp> --json        (checks : tags, liens, images,
        │                                                      vars template, poids, compat, spam, a11y)
        │  3. subprocess:  emailens analyze <tmp> --json     (score compat par client → score global)
        │  4. parse JSON → normalise en { score, blocking, counts, issues[] }
        │  5. persiste le dernier résultat (table newsletter_lint)
        ▼
[Réponse JSON structurée]  → la page affiche la Card résultat + stocke le badge score sur la ligne
```

**Local & RGPD :** `lint` et `analyze` tournent **100 % localement** sur le VPS (moteur `@emailens/engine` + données caniemail, aucune sortie réseau du contenu). ✅ conforme. La commande `emailens fix` (corrige via Claude/Anthropic = envoi externe) **n'est PAS câblée**. Les templates ne contiennent de toute façon aucune donnée perso (HTML marketing + `{{firstName}}`).

## 2. Modules à installer

- **VPS (global, isolé du projet) :** `npm install -g @emailens/cli@0.3.4` (entraîne `@emailens/engine`). **Version épinglée.**
  - ⚠️ NE PAS l'ajouter à `genesis-ui/package.json` (projet pnpm → conflit npm connu). C'est un outil système, pas une dép front.
  - Alternative possible : `npx @emailens/cli@0.3.4` à la demande (plus lent à froid, pas de global). → recommandation : **install global épinglé**.
- **Backend Python :** aucune nouvelle dép (stdlib `subprocess` + `json` + `tempfile`).
- **Front :** aucune nouvelle dép (Dialog/Card shadcn déjà présents).

## 3. Fichiers à créer / modifier

**Backend (Python)**
- 🆕 `scripts/email_lint_backend.py` — cœur :
  - `run_lint(html: str, skip: list[str] = []) -> dict` : fichier temp → `emailens lint --json` + `emailens analyze --json` → parse → normalise.
  - Contrat de sortie par issue : `{ status: 'ok'|'warning'|'error', category, rule, message, client?, details? }`.
  - Calcul `score` global (0-100) + `blocking` (bool) selon seuils.
  - `save_result(site, ref, result)` / `get_result(site, ref)` → table DuckDB.
  - Table `newsletter_lint(site_code, target_type, target_ref, score, n_errors, n_warnings, blocking, json, tested_at)`.
- ✏️ `scripts/api.py` — 2 routes :
  - `POST /api/sites/{site}/html/lint` → `{ html, ref?, target_type? }` → run + persist → résultat.
  - `GET /api/sites/{site}/html/lint?ref=...` → dernier résultat stocké (pour afficher le badge au chargement).

**Frontend (Next)**
- ✏️ `src/app/site/[code]/newsletters/page.tsx` :
  - Bouton **« Tester »** dans `ItemCard`, à côté de « Éditer/Ouvrir ».
  - Pendant le test : **spinner + progression par étapes** (labels : « Upload → Compat clients → Liens → Images → Spam → A11y → Terminé ») dans une Card.
  - Après : **Card résultat** = gros **score global**, badge bloquant/OK, liste erreurs (rouge) / warnings (ambre) groupées par catégorie (message + règle + client).
  - **Badge score** persistant à droite de chaque ligne (lu via le GET au chargement).

## 4. Règles bloquant / non-bloquant (seuils configurables)

| Check | Sévérité | Bloque l'envoi ? |
|---|---|---|
| Balises HTML cassées | error | ✅ |
| Liens cassés / href vide / http non sécurisé | error | ✅ |
| Variables template non résolues (`{{...}}` orphelines) | error | ✅ |
| Score spam > seuil (def. 5) | error | ✅ |
| Poids email > seuil (def. 102 Ko Gmail clip) | warning | ❌ |
| Image sans alt / sans dimensions | warning | ❌ |
| Incompat client mineure | warning | ❌ |

Exit codes emailens : `0` clean / `1` erreurs / `2` warnings → mappés sur `blocking`.

## 5. Variables d'environnement

- **Aucune obligatoire** (lint/analyze sont locaux).
- Optionnel : `EMAILENS_SPAM_THRESHOLD=5`, `EMAILENS_SKIP=` (checks à désactiver), `EMAILENS_BIN=emailens`.
- (`ANTHROPIC_API_KEY` seulement si on activait `fix` — hors scope.)

## 6. CI/CD (optionnel)

- Genesis n'est pas un repo git (pas de pipeline). Si souhaité plus tard : `scripts/lint_newsletters.sh` → `emailens lint structures/*.html --fail-on-warning` (exit 0/1) en hook pré-déploiement. **Non prioritaire.**

## 7. Ce qui manque aujourd'hui (gap)

- [ ] `@emailens/cli` pas installé sur le VPS.
- [ ] Table `newsletter_lint` inexistante.
- [ ] Routes `/html/lint` inexistantes.
- [ ] Bouton « Tester » + Card résultat inexistants.

## 8. Points à confirmer à l'implémentation

- **Schéma JSON exact** de `emailens lint/analyze --json` : à capturer au 1er run en bac à sable (le classifier a bloqué l'exécution préalable — légitime). Le parser sera adapté au schéma réel.
- **Revue supply-chain** : paquet récent + mono-mainteneur → au minimum version épinglée ; idéalement inspection rapide du code avant install globale.

## 9. Décisions à valider (toi)

1. **Install** : global épinglé `@emailens/cli@0.3.4` (reco) **ou** npx à la demande ?
2. **Scope** : `lint` seul (cœur) **ou** `lint` + `analyze` (score compat par client) ? (reco : les deux, sans screenshots = pas de navigateur headless = léger). On exclut `fix` (externe).
3. **Progression** : labels d'étapes simulés (léger, reco) **ou** vrai streaming SSE par check (plus lourd) ?
4. **Cible du bouton** : sur les **structures de base** ET les **versions sauvegardées** (reco) ou versions seulement ?
