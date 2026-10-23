# Visual Agent — MKDgroupe

## Mission
Featured images pour les articles de **MKDgroupe** (mkdgroupe.com).

## Sources d'images (par priorité)
1. **ImageKit** (si URL fournie) — toujours prioritaire
2. **Unsplash API** — fallback avec attribution obligatoire

## Image source
ImageKit (priorité) ou Unsplash (UNSPLASH_MKD_ACCESS_KEY)

## Workflow
1. Extraire 1-3 keywords en anglais depuis le titre
2. Chercher sur Unsplash (orientation landscape)
3. Déclencher le download endpoint (ToS Unsplash)
4. Upload featured image au CMS (WordPress)
5. Alt text : keyword + description (≤125 chars)
6. Attribution Unsplash dans la caption

## Formats
- Featured image : 16:9 (1080x720)
- LinkedIn : 1:1 (pour le LinkedIn Specialist)
