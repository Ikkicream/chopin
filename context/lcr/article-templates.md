# LCR — Templates articles & règles de rédaction

## Frontmatter obligatoire
```yaml
---
title: "[Titre avec mot-clé]"
date: "2026-MM-DD"
slug: "[MAX 35 chars, mot-clé uniquement, zéro stop words]"
seo_title: "[mot-clé : bénéfice — MAX 60 chars]"
metadescription: "[mot-clé + bénéfice — MAX 155 chars]"
thumbnail: ""
keyword: "[mot-clé principal]"
category: "[sms-marketing|sms-geolocalise|exemples-sms|outils-sms|secteurs]"
byline: "LeClientROI Editorial"
type: "[VIRAL|BUSINESS|GEO|SECTEUR]"
secteur: "[si applicable, sinon vide]"
status: "draft"
---
```

## Règles slug
- MAX 35 caractères
- OK : sms-garagiste | sms-coiffeur | texte-anniversaire
- PAS OK : sms-geolocalise-pour-garagistes-attirez-plus-de-clients

## Template SECTEUR
1. Intro SEO (2 paragraphes avec mot-clé)
2. Pourquoi le SMS pour [secteur] ? (3 avantages)
3. Comment ça marche (4 étapes)
4. 1 illustration schématique au milieu
5. 3 exemples SMS avec mockup CSS iMessage vert
6. FAQ (2-3 questions)

## Mockup CSS SMS (une seule ligne HTML)
```html
<div style="background:#f2f2f7;border-radius:18px;padding:16px;max-width:320px;margin:16px auto;font-family:-apple-system,sans-serif"><div style="font-size:13px;color:#8e8e93;margin-bottom:8px">NomSender</div><div style="background:#34c759;color:white;padding:12px 16px;border-radius:18px;font-size:15px;line-height:1.4">Texte du SMS ici. STOP 36200</div></div>
```

## Règles rédaction
- 800-1200 mots
- 2 premiers paragraphes : SEO dense avec mot-clé principal
- JAMAIS commencer par "Dans cet article nous allons voir..."
- Paragraphes max 4 lignes
- Min : 5 gras, 2 italiques, 1 citation >, 1 liste
- Année 2026 partout (jamais 2025)

## Validation qualité (20 critères)
SEO : slug ≤35, seo_title ≤60, metadescription ≤155, H1 avec mot-clé, mot-clé dans intro
Contenu : 800-1200 mots, pas "Dans cet article...", 2026, paragraphes ≤4 lignes
SMS (si SECTEUR) : 160 chars, sender ≤11, STOP 36200, zéro emoji, mockup CSS présent
Frontmatter : tous les champs remplis

## CTA HTML à insérer
### CTA Guides
```html
<div style="background:#f0f4ff;border-radius:12px;padding:20px;text-align:center;margin:24px 0"><p style="font-size:16px;font-weight:600;margin-bottom:12px">Découvrez nos guides SMS marketing</p><a href="https://leclientroi.com/guides" style="background:#2563eb;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600">Voir les guides →</a></div>
```

### CTA Lead Magnet
```html
<div style="background:#fef9ec;border:2px solid #f59e0b;border-radius:12px;padding:20px;text-align:center;margin:24px 0"><img src="https://ik.imagekit.io/rgpdsimplement/leadmagnet.png?updatedAt=1770133919455" alt="Livre blanc SMS marketing" style="max-width:120px;margin-bottom:12px"><p style="font-size:16px;font-weight:600;margin-bottom:12px">Téléchargez notre livre blanc gratuit</p><a href="https://ik.imagekit.io/rgpdsimplement/Libreblanc.pdf" style="background:#f59e0b;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600">Télécharger le guide PDF</a></div>
```
