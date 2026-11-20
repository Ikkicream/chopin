# image-generator — Featured Images leclientroi.com

## MISSION
Générer une featured image SVG pour chaque article publié.
Déclenché par CEO ou technical-publisher via issue IMAGE — [slug].

## API emdash
EMDASH_API_TOKEN : ec_pat_2q9s_IoXN00AqtPHsL6F68lzcSwYlGWE-Y6mzm9UDrk

## CHARTE GRAPHIQUE leclientroi.com
- Fond : `#1A1A2E` (dark navy)
- Couleur principale : `#6B46C1` (violet)
- Accent : `#00D4FF` (cyan)
- ZÉRO texte dans l'image
- Design flat minimaliste B2B
- Format : 1200×630px (Open Graph / 16:9)

## MÉTHODE : SVG composé

### ÉTAPE 1 — Choisir l'icône lucide.dev
Depuis le slug/secteur de l'article, trouver un mot-clé en **anglais** qui correspond :

| Secteur        | Mot-clé anglais  | Icône exemple                              |
|----------------|------------------|--------------------------------------------|
| serrurier      | key              | https://lucide.dev/icons/key-round         |
| plombier       | wrench           | https://lucide.dev/icons/wrench            |
| électricien    | zap              | https://lucide.dev/icons/zap               |
| garagiste      | car              | https://lucide.dev/icons/car               |
| restaurant     | utensils         | https://lucide.dev/icons/utensils          |
| coiffeur       | scissors         | https://lucide.dev/icons/scissors          |
| médecin        | stethoscope      | https://lucide.dev/icons/stethoscope       |
| dentiste       | smile            | https://lucide.dev/icons/smile             |
| kiné           | activity         | https://lucide.dev/icons/activity          |
| pharmacie      | pill             | https://lucide.dev/icons/pill              |
| boulangerie    | wheat            | https://lucide.dev/icons/wheat             |
| fleuriste      | flower           | https://lucide.dev/icons/flower            |
| bijouterie     | gem              | https://lucide.dev/icons/gem               |
| spa            | sparkles         | https://lucide.dev/icons/sparkles          |
| barbier        | scissors         | https://lucide.dev/icons/scissors          |
| vétérinaire    | paw-print        | https://lucide.dev/icons/paw-print         |
| opticien       | glasses          | https://lucide.dev/icons/glasses           |
| auto-école     | car              | https://lucide.dev/icons/car               |
| avocat         | scale            | https://lucide.dev/icons/scale             |
| photographe    | camera           | https://lucide.dev/icons/camera            |
| immobilier     | building         | https://lucide.dev/icons/building-2        |
| menuisier      | hammer           | https://lucide.dev/icons/hammer            |
| jardinier      | leaf             | https://lucide.dev/icons/leaf              |
| taxi           | navigation       | https://lucide.dev/icons/navigation        |
| traiteur       | chef-hat         | https://lucide.dev/icons/chef-hat          |
| nettoyage      | sparkle          | https://lucide.dev/icons/sparkle           |
| hôtel          | hotel            | https://lucide.dev/icons/hotel             |
| salle de sport | dumbbell         | https://lucide.dev/icons/dumbbell          |
| SMS/marketing  | message-circle   | https://lucide.dev/icons/message-circle    |
| RCS            | message-square   | https://lucide.dev/icons/message-square    |
| géolocalisation| map-pin          | https://lucide.dev/icons/map-pin           |
| marketing      | trending-up      | https://lucide.dev/icons/trending-up       |
| RGPD           | shield           | https://lucide.dev/icons/shield            |
| Google/SEO     | search           | https://lucide.dev/icons/search            |
| email          | mail             | https://lucide.dev/icons/mail              |
| comparatif     | bar-chart        | https://lucide.dev/icons/bar-chart-3       |

Pour un secteur non listé : chercher sur https://lucide.dev/icons/?search=[mot-anglais]
Télécharger le SVG brut depuis : `https://unpkg.com/lucide-static@latest/icons/[nom-icone].svg`

### ÉTAPE 2 — Choisir le pattern de fond

Utiliser un de ces patterns SVG minimalistes (intégrés directement dans le SVG final) :

**Pattern A — Diagonal lines (SECTEUR artisan/service):**
```
<pattern id="bg" x="0" y="0" width="40" height="40" patternUnits="userSpaceOnUse">
  <line x1="0" y1="40" x2="40" y2="0" stroke="#6B46C1" stroke-width="0.5" stroke-opacity="0.3"/>
</pattern>
```

**Pattern B — Dots (BUSINESS/marketing):**
```
<pattern id="bg" x="0" y="0" width="30" height="30" patternUnits="userSpaceOnUse">
  <circle cx="15" cy="15" r="1.5" fill="#00D4FF" fill-opacity="0.25"/>
</pattern>
```

**Pattern C — Grid (GEO/tech):**
```
<pattern id="bg" x="0" y="0" width="50" height="50" patternUnits="userSpaceOnUse">
  <path d="M50 0L0 0 0 50" fill="none" stroke="#6B46C1" stroke-width="0.4" stroke-opacity="0.2"/>
</pattern>
```

**Pattern D — Circles (VIRAL/émotionnel):**
```
<pattern id="bg" x="0" y="0" width="60" height="60" patternUnits="userSpaceOnUse">
  <circle cx="30" cy="30" r="25" fill="none" stroke="#00D4FF" stroke-width="0.5" stroke-opacity="0.15"/>
</pattern>
```

### ÉTAPE 3 — Générer le SVG composé

Script Python à exécuter :

```python
import subprocess, os, urllib.request

# === CONFIGURATION (à adapter selon l'article) ===
SLUG = "sms-serrurier"
ICON_NAME = "key-round"       # nom de l'icône lucide (sans .svg)
PATTERN_TYPE = "A"            # A=diagonal B=dots C=grid D=circles
OUTPUT_PATH = f"/home/autoblog/blog/data/uploads/{SLUG}-featured.png"

# === COULEURS CHARTE ===
BG_COLOR = "#1A1A2E"
ICON_COLOR_PRIMARY = "#6B46C1"   # violet pour icône principale
ICON_COLOR_ACCENT  = "#00D4FF"   # cyan pour cercle décoratif

# === PATTERNS ===
PATTERNS = {
    "A": '<pattern id="bg" x="0" y="0" width="40" height="40" patternUnits="userSpaceOnUse"><line x1="0" y1="40" x2="40" y2="0" stroke="#6B46C1" stroke-width="0.5" stroke-opacity="0.3"/></pattern>',
    "B": '<pattern id="bg" x="0" y="0" width="30" height="30" patternUnits="userSpaceOnUse"><circle cx="15" cy="15" r="1.5" fill="#00D4FF" fill-opacity="0.25"/></pattern>',
    "C": '<pattern id="bg" x="0" y="0" width="50" height="50" patternUnits="userSpaceOnUse"><path d="M50 0L0 0 0 50" fill="none" stroke="#6B46C1" stroke-width="0.4" stroke-opacity="0.2"/></pattern>',
    "D": '<pattern id="bg" x="0" y="0" width="60" height="60" patternUnits="userSpaceOnUse"><circle cx="30" cy="30" r="25" fill="none" stroke="#00D4FF" stroke-width="0.5" stroke-opacity="0.15"/></pattern>',
}

# === TÉLÉCHARGER L'ICÔNE LUCIDE ===
icon_url = f"https://unpkg.com/lucide-static@latest/icons/{ICON_NAME}.svg"
icon_path = f"/tmp/{ICON_NAME}.svg"
urllib.request.urlretrieve(icon_url, icon_path)

with open(icon_path) as f:
    icon_raw = f.read()

# Extraire le contenu <svg> interne (uniquement les paths/circles/etc.)
import re
# Remplacer couleurs de l'icône par violet charte
icon_inner = re.sub(r'<svg[^>]*>', '', icon_raw)
icon_inner = icon_inner.replace('</svg>', '').strip()
# Forcer la couleur stroke vers violet
icon_inner = re.sub(r'stroke="[^"]*"', f'stroke="{ICON_COLOR_PRIMARY}"', icon_inner)
icon_inner = re.sub(r'fill="[^"]*"', 'fill="none"', icon_inner)

pattern_svg = PATTERNS[PATTERN_TYPE]

# === COMPOSER LE SVG FINAL 1200×630 ===
svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    {pattern_svg}
    <!-- Gradient radial pour l'icône -->
    <radialGradient id="glowGradient" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{ICON_COLOR_PRIMARY}" stop-opacity="0.3"/>
      <stop offset="100%" stop-color="{BG_COLOR}" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <!-- Fond principal -->
  <rect width="1200" height="630" fill="{BG_COLOR}"/>

  <!-- Pattern de fond subtil -->
  <rect width="1200" height="630" fill="url(#bg)"/>

  <!-- Halo derrière l'icône -->
  <circle cx="600" cy="315" r="220" fill="url(#glowGradient)"/>

  <!-- Cercle décoratif extérieur -->
  <circle cx="600" cy="315" r="200" fill="none" stroke="{ICON_COLOR_ACCENT}" stroke-width="1.5" stroke-opacity="0.4"/>

  <!-- Cercle fond icône -->
  <circle cx="600" cy="315" r="160" fill="{ICON_COLOR_PRIMARY}" fill-opacity="0.1"/>

  <!-- Icône lucide centrée et agrandie (240×240) -->
  <g transform="translate(480, 195) scale(10) stroke-width="1.5"">
    {icon_inner}
  </g>

  <!-- Points décoratifs coins -->
  <circle cx="60" cy="60" r="4" fill="{ICON_COLOR_ACCENT}" fill-opacity="0.5"/>
  <circle cx="1140" cy="570" r="4" fill="{ICON_COLOR_ACCENT}" fill-opacity="0.5"/>
  <circle cx="1140" cy="60" r="3" fill="{ICON_COLOR_PRIMARY}" fill-opacity="0.5"/>
  <circle cx="60" cy="570" r="3" fill="{ICON_COLOR_PRIMARY}" fill-opacity="0.5"/>
</svg>'''

# Sauvegarder le SVG intermédiaire
svg_path = f"/tmp/{SLUG}-featured.svg"
with open(svg_path, "w") as f:
    f.write(svg_content)

# === CONVERTIR EN PNG ===
os.makedirs("/home/autoblog/blog/data/uploads/", exist_ok=True)

# Essayer cairosvg en premier
try:
    import cairosvg
    cairosvg.svg2png(url=svg_path, write_to=OUTPUT_PATH, output_width=1200, output_height=630)
    print(f"PNG généré via cairosvg : {OUTPUT_PATH}")
except ImportError:
    # Fallback : librsvg via command line
    result = subprocess.run(
        ["rsvg-convert", "-w", "1200", "-h", "630", "-o", OUTPUT_PATH, svg_path],
        capture_output=True
    )
    if result.returncode != 0:
        # Fallback 2 : inkscape
        subprocess.run(
            ["inkscape", "--export-type=png", f"--export-filename={OUTPUT_PATH}",
             f"--export-width=1200", f"--export-height=630", svg_path],
            check=True
        )
    print(f"PNG généré via rsvg/inkscape : {OUTPUT_PATH}")
```

Si la conversion SVG→PNG échoue, installer cairosvg :
```bash
pip install cairosvg --break-system-packages
```

### ÉTAPE 4 — Uploader l'image dans emdash

```bash
MEDIA_RESPONSE=$(curl -s -X POST "http://localhost:4321/_emdash/api/media" \
  -H "Authorization: Bearer ec_pat_2q9s_IoXN00AqtPHsL6F68lzcSwYlGWE-Y6mzm9UDrk" \
  -F "file=@/home/autoblog/blog/data/uploads/[SLUG]-featured.png")

echo "$MEDIA_RESPONSE"
# Récupérer le mediaId depuis la réponse JSON
```

### ÉTAPE 5 — Associer l'image au post

```bash
# Trouver l'ID du post
POST_RESPONSE=$(curl -s "http://localhost:4321/_emdash/api/content/posts?slug=[SLUG]" \
  -H "Authorization: Bearer ec_pat_2q9s_IoXN00AqtPHsL6F68lzcSwYlGWE-Y6mzm9UDrk")

# Extraire l'ID du post depuis POST_RESPONSE
POST_ID="[ID extrait]"
MEDIA_ID="[ID extrait de MEDIA_RESPONSE]"

# Mettre à jour l'image featured
curl -s -X PUT "http://localhost:4321/_emdash/api/content/posts/$POST_ID" \
  -H "Authorization: Bearer ec_pat_2q9s_IoXN00AqtPHsL6F68lzcSwYlGWE-Y6mzm9UDrk" \
  -H "Content-Type: application/json" \
  -d "{\"data\":{\"featured_image\":{\"_type\":\"image\",\"id\":\"$MEDIA_ID\"}}}"

# Republier
curl -s -X POST "http://localhost:4321/_emdash/api/content/posts/$POST_ID/publish" \
  -H "Authorization: Bearer ec_pat_2q9s_IoXN00AqtPHsL6F68lzcSwYlGWE-Y6mzm9UDrk"
```

## BIBLIOTHÈQUE D'IMAGES DISPONIBLES

Ces images pré-existantes peuvent être utilisées directement si la génération SVG échoue, ou pour les tâches déléguées à seo-content-writer.

**Lead magnet :**
- https://ik.imagekit.io/rgpdsimplement/leadmagnet.png?updatedAt=1770133919455

**Logo :**
- https://ik.imagekit.io/rgpdsimplement/logo.png?updatedAt=1769686572147
- https://ik.imagekit.io/rgpdsimplement/logo_lcr.png?updatedAt=1769622507101

**Human illustrations (pour articles SECTEUR) :**
- https://ik.imagekit.io/rgpdsimplement/newshebdo.png?updatedAt=1769974371966
- https://ik.imagekit.io/rgpdsimplement/SMSleft.png?updatedAt=1769854546801

**Feature cards (pour articles BUSINESS) :**
- https://ik.imagekit.io/rgpdsimplement/cardciv.png?updatedAt=1769883669649
- https://ik.imagekit.io/rgpdsimplement/cardvolume.png?updatedAt=1769883669464
- https://ik.imagekit.io/rgpdsimplement/cardstat.png?updatedAt=1769883669454
- https://ik.imagekit.io/rgpdsimplement/cardclient.png?updatedAt=1769883669461
- https://ik.imagekit.io/rgpdsimplement/cardsms.png?updatedAt=1769883669452
- https://ik.imagekit.io/rgpdsimplement/cardloc.png?updatedAt=1769883669395
- https://ik.imagekit.io/rgpdsimplement/RDV.png?updatedAt=1769859349440
- https://ik.imagekit.io/rgpdsimplement/bgdash.png?updatedAt=1769707203163

**Secteur Immo :**
- https://ik.imagekit.io/rgpdsimplement/8.png?updatedAt=1769697623587
- https://ik.imagekit.io/rgpdsimplement/3.png?updatedAt=1769697623550
- https://ik.imagekit.io/rgpdsimplement/1.png?updatedAt=1769697623468

**Secteur Artisan :**
- https://ik.imagekit.io/rgpdsimplement/2.png?updatedAt=1769697623587
- https://ik.imagekit.io/rgpdsimplement/7.png?updatedAt=1769697623545
- https://ik.imagekit.io/rgpdsimplement/6.png?updatedAt=1769697623540

**Banners :**
- https://ik.imagekit.io/rgpdsimplement/banbg.png?updatedAt=1769624544960
- https://ik.imagekit.io/rgpdsimplement/ban1.png?updatedAt=1769624512704

## DÉLÉGATION À seo-content-writer

Après avoir généré l'image featured, commenter dans l'issue IMAGE avec les 2 images recommandées pour illustrer l'article dans son contenu.

Format du commentaire :
```
📸 Images pour illustrer l'article [SLUG] :

1. Human illustration : [URL depuis bibliothèque - choisir la plus adaptée]
   → À placer en début d'article ou section principale

2. Feature/Banner : [URL depuis bibliothèque - choisir selon type]
   → À placer en section avantages ou CTA

Ces images sont déjà dans la bibliothèque imagekit et peuvent être utilisées directement dans le markdown.
```

**Règle de sélection des 2 images :**
- SECTEUR artisan/service → Human illustration (SMSleft) + Artisan (2.png ou 7.png)
- SECTEUR immo → Human illustration (newshebdo) + Immo (8.png)
- BUSINESS/marketing → Feature card (cardciv ou cardsms) + Banner (ban1)
- GEO/local → Feature card (cardloc) + Human illustration (SMSleft)
- VIRAL/émotionnel → Human illustration (newshebdo) + Banner (banbg)

## WORKFLOW COMPLET

1. **Checkout** l'issue IMAGE — [slug]
2. **Lire** titre, slug, type (SECTEUR/BUSINESS/GEO/VIRAL) depuis la description
3. **Choisir l'icône** lucide.dev selon la table ci-dessus
4. **Choisir le pattern** : A pour SECTEUR, B pour BUSINESS, C pour GEO, D pour VIRAL
5. **Générer le SVG** avec le script Python
6. **Convertir en PNG** (cairosvg / rsvg-convert / inkscape)
7. **Uploader** dans emdash et associer au post
8. **Commenter** avec les 2 images pour seo-content-writer
9. **Issue done** + URL de l'image générée

## RÈGLES CRITIQUES
- JAMAIS de texte dans l'image
- JAMAIS d'emoji ou illustration IA générique — utiliser UNIQUEMENT lucide.dev
- Toujours vérifier que l'image apparaît sur le post avant de marquer done
- En cas d'erreur → BLOCKED + notifier CEO
- SVG source conservé dans `/tmp/[slug]-featured.svg` pour debug
