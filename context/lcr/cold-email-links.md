# Cold email LCR — liens, ressources & signature (instructions de génération)

> Source de vérité des liens à insérer dans les cold emails. Appliqué par `scripts/email_generator.py`
> (mapping `SECTOR_LINKS` / `RESOURCE_LINKS` + signature). Mettre à jour ICI quand les URLs changent.

## Liens par secteur (insérer en `<a href>` dans chaque email)
- immobilier → https://leclientroi.com/secteurs/immobilier
- restaurant → https://leclientroi.com/secteurs/sms-restauration
- automobile / garagiste → https://leclientroi.com/secteurs/sms-automobile
- beauté / coiffeur → https://leclientroi.com/secteurs/beaute-bien-etre
- retail / commerce → https://leclientroi.com/secteurs/sms-retail-franchise

## Ressources générales (fallback si le secteur n'a pas de page dédiée, ou pour varier)
- Guide → https://leclientroi.com/guides
- App mobile → https://leclientroi.com/fonctionnalites/app-mobile
- Fidélité (QR code) → https://leclientroi.com/fonctionnalites/qr-code
- Accueil → https://leclientroi.com

## Règles appliquées à la génération
1. **CHAQUE email** contient au moins **un lien `<a href>` vers le site** (page du secteur si elle existe, sinon une ressource), **EN PLUS** du CTA TidyCal.
2. Le **mot du secteur** (ou un mot-clé sectoriel évident) est mis en **`<strong>`**.
3. **Signature Juliette** ajoutée automatiquement : icône `https://ik.imagekit.io/rgpdsimplement/mail.png` + « Juliette · Le Client ROI » + **téléphone** (constante `PHONE` dans `email_generator.py`) + `leclientroi.com` + lien de désinscription RGPD.
4. Format **texte épuré** (pas de HTML lourd), corps **≤ 150 mots** (hors signature), **1 seul CTA** TidyCal.

## Renseigné
- `PHONE` (téléphone de Juliette) = **07 44 30 66 03** (lien `tel:+33744306603` dans la signature). Défini dans `scripts/email_generator.py`.
