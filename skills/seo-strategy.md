# swarm-seo-strategy — Agent Stratégie SEO

Modèle : Claude Haiku (analyse) → résumé final Sonnet
Cron : lundi 7h UTC
Invoqué avec : `python3 scripts/seo_strategy_agent.py`

## Objectif

Analyser les données Ahrefs collectées quotidiennement, identifier les opportunités, et produire un plan d'action hebdomadaire pour dominer les mots-clés cibles de chaque site.

## Données en entrée

- `memory/seo/{site}-ahrefs-latest.json` — DR, trafic, keywords, concurrents
- `memory/seo/{site}-latest.json` — données enrichies (serp, opportunities)
- `memory/seo/{site}-veille.json` — articles concurrents récents
- `memory/{site}/articles-published.md` — ce qu'on a déjà publié
- `context/{site}/goals.md` — objectifs et mots-clés cibles

## Analyse à produire (par site)

### 1. Content Gaps
- Keywords où les concurrents rankent et pas nous
- Filtrer : volume > 50, KD < 30, pas encore couvert par nos articles
- Sortir les 10 meilleures opportunités

### 2. Quick Wins
- Keywords où on est position 11-20 (presque page 1)
- Identifier la page qui ranke → proposer optimisations (title, H1, contenu)

### 3. Concurrents en progression
- Comparer traffic/keywords des top 5 concurrents vs semaine précédente
- Alerter si un concurrent gagne > 20% de traffic

### 4. Calendrier éditorial
- Proposer les 4 prochains articles à écrire (1/semaine)
- Pour chaque : keyword cible, volume, KD, angle d'attaque, titre suggéré

### 5. Actions techniques
- Pages non indexées à soumettre
- Liens internes à ajouter
- Meta descriptions à optimiser

## Output

1. **Fichier rapport** : `memory/seo/recommendations-{date}.md`
2. **Notification Telegram** : résumé 5 lignes avec les 3 actions prioritaires
3. **Dashboard** : les recommandations apparaissent dans `/api/seo-recommendations`

## Règles

- Ne JAMAIS dépenser plus de 200 crédits Ahrefs pour l'analyse
- Utiliser les données déjà cachées (pas de nouveau fetch)
- Prioriser les keywords à fort ROI (volume élevé + KD faible)
- Toujours vérifier que le keyword n'est pas déjà couvert dans articles-published.md
