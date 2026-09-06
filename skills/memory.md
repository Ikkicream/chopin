# swarm-memory — Gestion Mémoire RAG

Pas de modèle IA — manipulation de fichiers uniquement
Invoquer après chaque publication ou action importante

## Variables requises à l'appel
- SITE : lcr | mkd
- SLUG : slug de l'article publié
- TITLE : titre de l'article
- KEYWORD : mot-clé principal
- CATEGORY : catégorie (LCR) ou tag (MKD)
- COST_USD : coût estimé de l'action (float, ex: 0.0250)
- MODEL : modèle utilisé (ex: deepseek-chat, claude-haiku-4-5-20251001)

```bash
set -a; source /home/autoblog/genesis/.env; set +a
cd /home/autoblog/genesis
TODAY=$(date -u +%Y-%m-%d)
WEEK=$(date -u +%Y-W%V)
```

## 1. Mettre à jour articles-published.md

```bash
# Format : | DATE | SLUG | TITLE | CATEGORY | TYPE | WEEK |
LINE="| ${TODAY} | ${SLUG} | ${TITLE} | ${CATEGORY} | ${WEEK} |"

echo "$LINE" >> memory/${SITE}/articles-published.md
echo "✅ articles-published.md mis à jour (${SITE})"
```

## 2. Mettre à jour keywords-targeted.md

```bash
# Format : | DATE | KEYWORD | WEEK | SLUG | STATUS |
LINE="| ${TODAY} | ${KEYWORD} | ${WEEK} | ${SLUG} | published |"

echo "$LINE" >> memory/${SITE}/keywords-targeted.md
echo "✅ keywords-targeted.md mis à jour"
```

## 3. Mettre à jour costs-log.json

```bash
python3 << 'PYEOF'
import json
from datetime import datetime, timezone
import os

log_path = '/home/autoblog/genesis/memory/shared/costs-log.json'
with open(log_path, 'r') as f:
    data = json.load(f)

data['entries'].append({
    'date': datetime.now(timezone.utc).isoformat(),
    'week': os.environ.get('WEEK', ''),
    'module': 'swarm-content',
    'site': os.environ.get('SITE', ''),
    'action': 'article_published',
    'slug': os.environ.get('SLUG', ''),
    'cost_usd': float(os.environ.get('COST_USD', '0')),
    'model': os.environ.get('MODEL', 'deepseek-chat')
})

with open(log_path, 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print('✅ costs-log.json mis à jour')
PYEOF
```

## 4. Rapport hebdomadaire (si lundi)

```bash
DAY_OF_WEEK=$(date -u +%u)  # 1=lundi

if [ "$DAY_OF_WEEK" = "1" ]; then
  REPORT_DIR="memory/${SITE}/weekly-reports"
  mkdir -p "$REPORT_DIR"
  REPORT_FILE="${REPORT_DIR}/${WEEK}.md"

  # Lire les articles de cette semaine
  WEEK_ARTICLES=$(grep "$WEEK" memory/${SITE}/articles-published.md 2>/dev/null || echo "Aucun article cette semaine")

  # Calculer le coût de la semaine
  WEEK_COST=$(python3 -c "
import json
with open('memory/shared/costs-log.json') as f:
    data = json.load(f)
cost = sum(e.get('cost_usd', 0) for e in data.get('entries', []) if e.get('week') == '${WEEK}' and e.get('site') == '${SITE}')
print(f'{cost:.4f}')
")

  cat > "$REPORT_FILE" << EOF
# Rapport ${SITE^^} — ${WEEK}

## Articles publiés
${WEEK_ARTICLES}

## Budget
- Total ${SITE^^} cette semaine : \$${WEEK_COST}

## Généré le
$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

  echo "✅ Rapport hebdomadaire créé : $REPORT_FILE"
fi
```

## 5. Archiver les anciens articles backlog LCR (si SITE=lcr)

```bash
if [ "$SITE" = "lcr" ]; then
  # Marquer l'article source comme traité (renommer avec préfixe "published-")
  SOURCE_FILE=$(find /home/autoblog/blog/articles -name "*${SLUG}*" 2>/dev/null | head -1)
  if [ -n "$SOURCE_FILE" ]; then
    # Ne pas déplacer — juste noter dans le log que cet article est traité
    echo "Source backlog : $SOURCE_FILE → slug enregistré dans articles-published.md"
  fi
fi
```

## Structure des fichiers mémoire

### memory/lcr/articles-published.md
```
# Articles publiés — LCR leclientroi.com

| Date | Slug | Titre | Catégorie | Semaine |
|------|------|-------|-----------|---------|
```

### memory/mkd/articles-published.md
```
# Articles publiés — MKD mkdgroupe.com

| Date | Slug | Titre | Catégorie | Semaine |
|------|------|-------|-----------|---------|
```

### memory/lcr/keywords-targeted.md
```
# Mots-clés ciblés — LCR

| Date | Mot-clé | Semaine | Slug | Statut |
|------|---------|---------|------|--------|
```

### memory/mkd/keywords-targeted.md
```
# Mots-clés ciblés — MKD

| Date | Mot-clé | Semaine | Slug | Statut |
|------|---------|---------|------|--------|
```

### memory/shared/costs-log.json
```json
{
  "entries": []
}
```
