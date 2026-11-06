# Évaluation de l'intérêt légitime (LIA) — Prospection commerciale B2B

> Document interne (registre RGPD). À conserver, non publié. Daté du 2026-05-26.
> ⚠️ Modèle solide conforme RGPD, à faire viser par un conseil juridique avant usage opposable.

## 0. Responsables de traitement concernés
- **HUMANETICS LABS** — SARL, SIREN 995210010, 1 rue du Débarcadère, 92700 Colombes. Site : leclientroi.com. Contact DPO : dpo@humaneticslabs.com.
- **MKD GROUPE** — SARL, SIREN 852283761, 35 rue de la Belle Image, 94700 Maisons-Alfort. Site : mkdgroupe.com. Contact DPO : dpo@mkdgroupe.com.
- DPO / référent désigné : Camille Afchain.

Le traitement (prospection commerciale B2B via l'outil « Genesis ») est identique pour les deux responsables ; chacun reste responsable de traitement pour ses propres prospects.

## 1. Description du traitement
- **Finalité** : prospection commerciale **entre professionnels (B2B)** — envoi d'emails de démarchage (cold email) proposant des services marketing (SMS/RCS pour HumaneticsLabs/leclientroi.com ; data marketing/SMS pour MKD GROUPE).
- **Personnes concernées** : professionnels (dirigeants, responsables/directeurs marketing, gérants) d'entreprises cibles.
- **Données traitées** : nom, prénom, **adresse email professionnelle**, téléphone professionnel (le cas échéant), fonction/poste, nom de l'entreprise, secteur d'activité, ville/département, site web. **Aucune donnée sensible.**
- **Sources** : informations professionnelles publiquement accessibles (recherche web via Serper, sites des entreprises), import de fichiers professionnels.
- **Sous-traitants** : Emelia (envoi des emails, UE-France), Mailnjoy (vérification de validité des emails), Serper (recherche web, US), DeepSeek (génération de texte, Chine — **sans aucune donnée personnelle**, cf. §4), Hetzner (hébergement, Allemagne/UE).

## 2. Test de finalité — l'intérêt est-il légitime ?
La prospection commerciale est un intérêt légitime **expressément reconnu** par le considérant 47 du RGPD et par la doctrine de la CNIL pour le B2B. L'intérêt poursuivi (développer l'activité commerciale en démarchant des professionnels sur leur messagerie professionnelle, pour des produits/services en lien avec leur activité) est **réel, actuel et licite**. ✅

## 3. Test de nécessité — le traitement est-il proportionné ?
Le démarchage ciblé suppose nécessairement de traiter les coordonnées professionnelles des prospects ; il n'existe pas de moyen moins intrusif d'atteindre la finalité.
**Minimisation appliquée** : seules des **données professionnelles** sont traitées (pas de données personnelles au sens vie privée, pas de données sensibles) ; vérification préalable des emails (Mailnjoy) pour éviter les envois inutiles ; ciblage par secteur pertinent. ✅

## 4. Test de mise en balance — droits et libertés des personnes
- **Attentes raisonnables** : un professionnel dont l'email pro est public s'attend raisonnablement à recevoir des sollicitations commerciales en lien avec son activité (B2B). L'objet de l'email correspond aux missions de la personne (ex. responsable marketing démarché sur une solution marketing).
- **Impact** : faible. Données professionnelles uniquement, pas de profilage intrusif, pas de décision automatisée produisant des effets juridiques.
- **Mesures de sauvegarde** (réduisent l'impact, font pencher la balance en faveur du traitement) :
  1. **Droit d'opposition immédiat** : lien de désinscription dans chaque email (Emelia), opposition respectée définitivement (blacklist).
  2. **Anonymisation vis-à-vis de l'IA hors UE** : le moteur de génération (DeepSeek, Chine) **ne reçoit aucune donnée identifiante** (ni nom, ni email, ni téléphone) — il ne travaille que sur des angles sectoriels ; le qualifier n'envoie que des données d'entreprise (secteur, ville, site), jamais email/téléphone.
  3. **Durée de conservation limitée** : 3 ans à compter du dernier contact (recommandation CNIL B2B), puis suppression/anonymisation.
  4. **Sécurité** : accès restreint (rôles, double authentification 2FA, isolation par site), chiffrement des secrets, hébergement UE (Hetzner, Allemagne).
  5. **Transparence** : politique de confidentialité accessible mentionnant le traitement, les droits et le contact DPO.

**Conclusion** : la mise en balance est **favorable**. Les intérêts commerciaux des responsables ne portent pas une atteinte disproportionnée aux droits et libertés des personnes, compte tenu du caractère B2B, de la minimisation et des mesures de sauvegarde. L'intérêt légitime est une base légale **valable** pour ce traitement (art. 6.1.f RGPD). ✅

## 5. Réexamen
À réévaluer en cas de changement de finalité, d'élargissement des données, ou au moins tous les 24 mois.
