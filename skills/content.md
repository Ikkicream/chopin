# swarm-content — Rédaction & Publication

Modèle : DeepSeek (background)
Invoqué avec : SITE=lcr ou SITE=mkd

## Initialisation

```bash
set -a; source /home/autoblog/genesis/.env; set +a
cd /home/autoblog/genesis
TODAY=$(date -u +%Y-%m-%d)
WEEK=$(date -u +%Y-W%V)
```

---

## SITE=lcr — Publication depuis le backlog Arvow

### Étape 1 : Sélectionner l'article non publié

```bash
# Lister les slugs déjà publiés
PUBLISHED_SLUGS=$(grep -oP '(?<=\| )[a-z0-9-]+(?= \|)' memory/lcr/articles-published.md 2>/dev/null || echo "")

# Lister les articles du backlog (plus ancien en premier)
ls /home/autoblog/blog/articles/*.md | sort | while read FILE; do
  SLUG=$(basename "$FILE" .md | sed 's/^[0-9-]*-//')
  if ! echo "$PUBLISHED_SLUGS" | grep -q "^${SLUG}$"; then
    echo "$FILE"
    break
  fi
done
```

Lire le fichier sélectionné et extraire le frontmatter YAML + le corps markdown.

### Étape 2 : Adapter l'article pour 2026

1. **Date** : remplacer la date frontmatter par `$TODAY`
2. **Années** : remplacer toutes les occurrences de "2025" par "2026" dans title, body, et frontmatter
3. **Slug** : vérifier MAX 35 caractères
   - Si slug > 35 chars : raccourcir en gardant le mot-clé principal (supprimer stop words)
   - Exemple : "sms-geolocalise-pour-garagistes-guide-complet" → "sms-garagiste-geolocalise"
4. **Frontmatter manquant** : inférer depuis le contenu si ces champs sont absents :
   - `seo_title` : max 60 chars, format "mot-clé : bénéfice principal"
   - `metadescription` : max 155 chars avec mot-clé + bénéfice
   - `keyword` : extraire du titre ou du contenu
   - `category` : choisir parmi sms-marketing | sms-geolocalise | exemples-sms | outils-sms | secteurs
   - `byline` : "LeClientROI Editorial"
   - `type` : VIRAL | BUSINESS | GEO | SECTEUR selon le contenu

### Étape 3 : Enrichir si < 800 mots

Compter les mots du body (hors frontmatter). Si < 800 mots :
- Ajouter une section `## FAQ` avec 2-3 questions pertinentes et réponses de 2-3 phrases
- Ajouter une section `## Points clés à retenir` avec 3-4 bullets
- Ne JAMAIS commencer par "Dans cet article nous allons voir..."

Si type=SECTEUR : vérifier présence de 3 exemples SMS avec mockup CSS :
```html
<div style="background:#f2f2f7;border-radius:18px;padding:16px;max-width:320px;margin:16px auto;font-family:-apple-system,sans-serif"><div style="font-size:13px;color:#8e8e93;margin-bottom:8px">NomSender</div><div style="background:#34c759;color:white;padding:12px 16px;border-radius:18px;font-size:15px;line-height:1.4">Texte du SMS ici 160 chars max. STOP 36200</div></div>
```
Sender ≤ 11 chars, STOP 36200 obligatoire, 0 emoji dans le SMS.

### Étape 4 : Insérer les CTAs

Après le 3ème paragraphe du body, insérer le CTA Guides :
```html
<div style="background:#f0f4ff;border-radius:12px;padding:20px;text-align:center;margin:24px 0"><p style="font-size:16px;font-weight:600;margin-bottom:12px">Découvrez nos guides SMS marketing</p><a href="https://leclientroi.com/guides" style="background:#2563eb;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600">Voir les guides →</a></div>
```

Avant le dernier paragraphe (conclusion), insérer le CTA Lead Magnet :
```html
<div style="background:#fef9ec;border:2px solid #f59e0b;border-radius:12px;padding:20px;text-align:center;margin:24px 0"><img src="https://ik.imagekit.io/rgpdsimplement/leadmagnet.png?updatedAt=1770133919455" alt="Livre blanc SMS marketing" style="max-width:120px;margin-bottom:12px"><p style="font-size:16px;font-weight:600;margin-bottom:12px">Téléchargez notre livre blanc gratuit</p><a href="https://ik.imagekit.io/rgpdsimplement/Libreblanc.pdf" style="background:#f59e0b;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600">Télécharger le guide PDF</a></div>
```

### Étape 5 : Chercher une image Unsplash

```bash
KEYWORD_EN=$(echo "$KEYWORD" | python3 -c "import sys; k=sys.stdin.read().strip(); translate={'sms':'sms marketing','marketing':'marketing','garagiste':'mechanic garage','coiffeur':'hairdresser salon','restaurant':'restaurant','immo':'real estate'}; print(translate.get(k.split()[0].lower(), k))")

IMG_DATA=$(curl -s "https://api.unsplash.com/search/photos?query=${KEYWORD_EN}&orientation=landscape&per_page=1&client_id=${UNSPLASH_LCR_ACCESS_KEY}" | \
  python3 -c "
import sys, json
d = json.load(sys.stdin)
if d.get('results'):
    r = d['results'][0]
    img_url = r['urls']['regular']
    alt = r.get('alt_description') or r['user']['name'] + ' on Unsplash'
    print(img_url + '|' + alt)
else:
    print('https://ik.imagekit.io/rgpdsimplement/newshebdo.png|SMS Marketing')
")
IMG_URL=$(echo "$IMG_DATA" | cut -d'|' -f1)
IMG_ALT=$(echo "$IMG_DATA" | cut -d'|' -f2)
```

### Étape 6 : Générer 2 schémas Higgsfield AI

Générer 2 infographies professionnelles via Higgsfield AI (`scripts/generate_images.py`).

**Construire le contenu des schémas selon le type d'article :**

- SECTEUR → Schéma 1 : tableau comparatif "Avant SMS / Après SMS pour [secteur]" (2 colonnes avec métriques) | Schéma 2 : stats clés du secteur (barres avec chiffres réels)
- BUSINESS → Schéma 1 : flow processus en 4-5 étapes (ex: Prospect → CRM → Campagne → Réponse → CRM) | Schéma 2 : comparaison 2 colonnes avec/sans le produit
- GEO → Schéma 1 : rayon de proximité avec stats de conversion par distance | Schéma 2 : entonnoir drive-to-store (Envoi → Ouverture → Clic → Visite → Achat)
- VIRAL → Schéma 1 : timeline "Moments clés" avec dates et taux d'ouverture | Schéma 2 : exemples de messages avec taux estimés par type d'occasion

Écrire et exécuter ce script Python pour lancer la génération :

```python
import json, sys
sys.path.insert(0, '/home/autoblog/genesis/scripts')
from generate_images import generate_article_schemas, load_env

env = load_env()

# Adapter le contenu selon l'article réel
schema_contents = [
    {
        "key": "kschema01",
        "content": "[CONTENU SCHEMA 1 — description précise des données, chiffres et structure]",
        "alt": "[Description alt text schéma 1]",
        "caption": "[Légende schéma 1 — source si applicable]",
        "filename": f"{SLUG}-schema1.png"
    },
    {
        "key": "kschema02",
        "content": "[CONTENU SCHEMA 2 — description précise des données, chiffres et structure]",
        "alt": "[Description alt text schéma 2]",
        "caption": "[Légende schéma 2 — source si applicable]",
        "filename": f"{SLUG}-schema2.png"
    }
]

# POST_ID sera rempli après création du draft (étape 8)
# Appel en deux temps : d'abord générer les URLs, puis insérer après création
urls = generate_article_schemas(None, schema_contents, env)
print("URLs générées:", urls)

# Sauvegarder pour insertion post-publication
with open('/tmp/schema_urls.json', 'w') as f:
    json.dump({"schemas": schema_contents, "urls": urls}, f)
```

Exécuter : `python3 /tmp/gen_schemas.py`

Les URLs Emdash retournées seront insérées dans l'article à l'étape 8.

**Règles pour le champ `content` de chaque schéma :**
- Décrire précisément le type de visuel (flowchart, tableau, barres, entonnoir...)
- Inclure les données réelles de l'article (chiffres, pourcentages, noms d'étapes)
- Mentionner les couleurs souhaitées : electric blue (#0066FF) primaire, vert (#00C48C) positif, rouge (#FF4757) négatif
- Toujours en anglais (le prompt Higgsfield est en anglais, les textes dans l'image seront en français)

### Étape 7 : Convertir Markdown → Portable Text

Écrire et exécuter ce script Python pour convertir le body markdown en blocs Portable Text :

```python
import json, re, uuid

def make_key():
    return 'k' + uuid.uuid4().hex[:8]

def make_span(text, marks=None):
    return {"_type": "span", "_key": make_key(), "text": text, "marks": marks or []}

def parse_inline(text):
    """Parse inline markdown (bold, italic) en spans."""
    spans = []
    pattern = re.compile(r'(\*\*(.+?)\*\*|\*(.+?)\*|(.+?)(?=\*\*|\*|$))', re.DOTALL)
    i = 0
    while i < len(text):
        if text[i:i+2] == '**':
            end = text.find('**', i+2)
            if end != -1:
                spans.append(make_span(text[i+2:end], ['strong']))
                i = end + 2
                continue
        elif text[i] == '*':
            end = text.find('*', i+1)
            if end != -1:
                spans.append(make_span(text[i+1:end], ['em']))
                i = end + 1
                continue
        # Collect normal text until next marker
        next_marker = len(text)
        for m in ['**', '*']:
            pos = text.find(m, i)
            if pos != -1 and pos < next_marker:
                next_marker = pos
        if next_marker > i:
            spans.append(make_span(text[i:next_marker]))
        i = next_marker
    return spans if spans else [make_span(text)]

def md_to_portable_text(markdown_body):
    blocks = []
    lines = markdown_body.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # Skip empty lines
        if not line.strip():
            i += 1
            continue

        # HTML blocks (CTAs, mockups) — passer tel quel
        if line.strip().startswith('<') and not line.strip().startswith('<br'):
            html_lines = [line]
            i += 1
            while i < len(lines) and (lines[i].strip() and not lines[i].strip().startswith('#')):
                if lines[i].strip():
                    html_lines.append(lines[i])
                i += 1
            html_block = '\n'.join(html_lines)
            blocks.append({"_type": "htmlBlock", "_key": make_key(), "html": html_block})
            continue

        # Headings
        h_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if h_match:
            level = len(h_match.group(1))
            style = {1: 'h1', 2: 'h2', 3: 'h3', 4: 'h4'}.get(level, 'h4')
            blocks.append({
                "_type": "block", "_key": make_key(),
                "style": style, "markDefs": [],
                "children": [make_span(h_match.group(2))]
            })
            i += 1
            continue

        # Blockquote
        if line.startswith('>'):
            text = line.lstrip('> ').strip()
            blocks.append({
                "_type": "block", "_key": make_key(),
                "style": "blockquote", "markDefs": [],
                "children": parse_inline(text)
            })
            i += 1
            continue

        # Bullet list
        bullet_match = re.match(r'^[-*+]\s+(.+)$', line)
        if bullet_match:
            blocks.append({
                "_type": "block", "_key": make_key(),
                "style": "normal", "listItem": "bullet", "level": 1,
                "markDefs": [], "children": parse_inline(bullet_match.group(1))
            })
            i += 1
            continue

        # Numbered list
        num_match = re.match(r'^\d+\.\s+(.+)$', line)
        if num_match:
            blocks.append({
                "_type": "block", "_key": make_key(),
                "style": "normal", "listItem": "number", "level": 1,
                "markDefs": [], "children": parse_inline(num_match.group(1))
            })
            i += 1
            continue

        # Normal paragraph (accumulate until blank line or heading)
        para_lines = [line]
        i += 1
        while i < len(lines):
            next_line = lines[i].rstrip()
            if not next_line.strip():
                break
            if re.match(r'^#{1,6}\s', next_line):
                break
            if next_line.startswith('>') or re.match(r'^[-*+]\s', next_line) or re.match(r'^\d+\.\s', next_line):
                break
            if next_line.strip().startswith('<'):
                break
            para_lines.append(next_line)
            i += 1

        text = ' '.join(para_lines)
        blocks.append({
            "_type": "block", "_key": make_key(),
            "style": "normal", "markDefs": [],
            "children": parse_inline(text)
        })

    return blocks

# Usage : lire depuis stdin
import sys
body = sys.stdin.read()
blocks = md_to_portable_text(body)
print(json.dumps(blocks, ensure_ascii=False))
```

Exécuter : `echo "$BODY_MARKDOWN" | python3 /tmp/md_to_pt.py > /tmp/portable_text.json`

### Étape 8 : Publier sur Emdash

```bash
PORTABLE_TEXT=$(cat /tmp/portable_text.json)

# 1. Créer le draft
RESPONSE=$(curl -s -X POST "http://localhost:4321/_emdash/api/content/posts" \
  -H "Authorization: Bearer ${EMDASH_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "
import json, sys
payload = {
    'slug': '${SLUG}',
    'status': 'draft',
    'data': {
        'title': '${TITLE}',
        'featured_image': {
            'id': '', 'provider': 'external',
            'src': '${IMG_URL}', 'width': 1080, 'height': 720,
            'alt': '${IMG_ALT}'
        },
        'content': json.loads(open('/tmp/portable_text.json').read())
    },
    'seo': {
        'title': '${SEO_TITLE}',
        'description': '${META_DESC}'
    }
}
print(json.dumps(payload))
")")

POST_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['item']['id'])")
echo "Draft créé : $POST_ID"

# 2. Publier (Origin header obligatoire — anti-CSRF Emdash)
curl -s -X POST "http://localhost:4321/_emdash/api/content/posts/${POST_ID}/publish" \
  -H "Authorization: Bearer ${EMDASH_API_TOKEN}" \
  -H "Origin: http://localhost:4321" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Publié:', d.get('data',{}).get('item',{}).get('status','?'))"
```

### Étape 8b : Insérer les schémas Higgsfield dans l'article

Après avoir obtenu `$POST_ID`, insérer les 2 schémas générés à l'étape 6 dans l'article :

```python
import json, sys
sys.path.insert(0, '/home/autoblog/genesis/scripts')
from generate_images import insert_into_article, load_env

env = load_env()
post_id = "POST_ID_ICI"  # remplacer par la valeur réelle

data = json.load(open('/tmp/schema_urls.json'))
schemas_input = data['schemas']
urls = data['urls']

# Reconstruire la liste pour insert_into_article
emdash_schemas = []
for sc, url in zip(schemas_input, urls):
    emdash_schemas.append({
        "key": sc["key"],
        "url": url,
        "alt": sc["alt"],
        "caption": sc["caption"]
    })

ok = insert_into_article(post_id, emdash_schemas, env["EMDASH_API_TOKEN"])
print("Schémas insérés et republié :", ok)
```

Exécuter : `python3 /tmp/insert_schemas.py`

### Étape 9 : Vérifier la publication

```bash
sleep 3
curl -s "http://localhost:4321/_emdash/api/content/posts?limit=1" \
  -H "Authorization: Bearer ${EMDASH_API_TOKEN}" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
item = d['data']['items'][0]
slug = item['slug']
print(f'Status: {item[\"status\"]} | Slug: {slug} | Titre: {item[\"data\"][\"title\"][:50]}')
print(f'URL publique : https://blog.leclientroi.com/posts/{slug}')
"
```

Note : l'URL publique est toujours `https://blog.leclientroi.com/posts/{slug}` (avec le préfixe `/posts/`).

---

## SITE=mkd — Veille RSS + Rédaction + WordPress

### Étape 1 : Veille RSS concurrents

```bash
python3 -c "
import urllib.request
from xml.etree import ElementTree as ET

feeds = [
    'https://rss.app/feeds/aeiR14C99xJAFyor.xml',
]

articles = []
for url in feeds:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            tree = ET.parse(resp)
            for item in tree.findall('.//item')[:5]:
                title = item.findtext('title', '')
                link = item.findtext('link', '')
                desc = item.findtext('description', '')
                if title:
                    articles.append({'title': title, 'link': link, 'desc': desc[:150]})
    except Exception as e:
        print(f'Erreur feed {url}: {e}')

for a in articles:
    print(f'- {a[\"title\"]}')
    print(f'  {a[\"link\"]}')
"
```

### Étape 2 : Choisir le sujet MKD

1. Lire `memory/mkd/keywords-targeted.md` → noter les mots-clés déjà traités
2. Parmi les titres RSS collectés, identifier un angle non encore traité
3. Si aucun angle RSS pertinent, choisir parmi :
   - RGPD marketing B2B 2026 / conformité email
   - RCS : messagerie riche pour entreprises
   - SMS marketing B2B : acquisition, nurturing
   - Location de fichiers prospects France
   - Data marketing : enrichissement, segmentation
4. Définir : KEYWORD_MKD, TITLE_MKD, SLUG_MKD (≤35 chars)

### Étape 3 : Rédiger l'article MKD

Rédiger 800-1200 mots en français, ton professionnel B2B :
- H1 avec le mot-clé principal dans le premier paragraphe
- 3-4 sections H2 logiques
- Min 5 **gras**, 2 *italiques*, 1 > citation, 1 liste à puces
- Année 2026 partout
- Ne jamais commencer par "Dans cet article..."
- Conclusion avec CTA vers https://mkdgroupe.com/contact

Format de sortie : HTML (pas markdown), car WordPress attend du HTML dans `content`.

### Étape 4 : Chercher une image Unsplash (MKD)

```bash
IMG_DATA=$(curl -s "https://api.unsplash.com/search/photos?query=${KEYWORD_MKD_EN}&orientation=landscape&per_page=1&client_id=${UNSPLASH_MKD_ACCESS_KEY}" | \
  python3 -c "
import sys, json
d = json.load(sys.stdin)
if d.get('results'):
    r = d['results'][0]
    print(r['urls']['regular'] + '|' + (r.get('alt_description') or r['user']['name']))
else:
    print('https://ik.imagekit.io/rgpdsimplement/footer.jpg|MKD marketing')
")
IMG_URL_MKD=$(echo "$IMG_DATA" | cut -d'|' -f1)
IMG_ALT_MKD=$(echo "$IMG_DATA" | cut -d'|' -f2)
```

### Étape 5 : Publier sur WordPress

```bash
AUTH=$(python3 -c "import base64; print(base64.b64encode('${WP_USERNAME}:${WP_APP_PASSWORD}'.encode()).decode())")

WP_RESPONSE=$(curl -s -X POST "${WP_SITE_URL}/wp-json/wp/v2/posts" \
  -H "Authorization: Basic ${AUTH}" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "
import json
payload = {
    'title': '${TITLE_MKD}',
    'content': '''${CONTENT_HTML_MKD}''',
    'slug': '${SLUG_MKD}',
    'status': 'publish',
    'excerpt': '${META_DESC_MKD}',
    'featured_media': 0
}
print(json.dumps(payload))
")")

WP_ID=$(echo "$WP_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id','ERROR'))")
WP_URL=$(echo "$WP_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('link','?'))")
echo "WP publié : ID=$WP_ID — $WP_URL"
```

### Étape 6 : Logger en mémoire

Invoquer `skills/memory.md` avec SITE=mkd, SLUG=$SLUG_MKD, TITLE=$TITLE_MKD.

---

## Validation qualité (20 critères — vérifier avant publication)

**SEO :** slug ≤35 chars | seo_title ≤60 chars | metadescription ≤155 chars | H1 contient le mot-clé | mot-clé dans les 2 premiers paragraphes

**Contenu :** 800-1200 mots | ne commence pas par "Dans cet article" | année 2026 | paragraphes ≤4 lignes | min 5 gras | min 2 italiques | 1 citation | 1 liste

**SMS si SECTEUR :** 3 mockups CSS | texte ≤160 chars | sender ≤11 chars | STOP 36200 | 0 emoji

**Frontmatter :** tous les champs remplis (title, date, slug, seo_title, metadescription, keyword, category, byline, type)

**Images :** 2 schémas Higgsfield générés et visibles sur l'URL publique | `htmlBlock` utilisé (jamais `html`) | pas d'inline style= ni de data: URI | Origin header sur tous les POST Emdash
