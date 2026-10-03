# Emelia — Règles de délivrabilité

## Setup technique OBLIGATOIRE

### DNS Authentication (requis depuis 2024)
- **SPF** : autoriser les serveurs d'envoi
- **DKIM** : signer les emails cryptographiquement
- **DMARC** : politique d'alignement SPF+DKIM
- Sans ça → emails rejetés par Google/Yahoo/Microsoft

### Tracking domain personnalisé
- Ajouter un CNAME DNS : `track.tondomaine.com` → `emelia.link`
- NE JAMAIS utiliser de raccourcisseurs (bit.ly, etc.)
- Le tracking dégrade légèrement la délivrabilité → le désactiver si possible

## Warmup

### Règles
- **2-4 semaines obligatoires** avant d'envoyer en volume
- Un nouveau domaine qui envoie 50+ emails jour 1 = flagué comme suspect
- Le warmup d'Emelia crée des conversations artificielles entre providers
- Critique pour les nouveaux domaines sans historique

### Stratégie domaine
- **Domaine principal** : uniquement pour marché niche, ultra-personnalisé, 20-50 emails/jour max
- **Domaines séparés** (recommandé) : protège la réputation du domaine principal
- Permet de scaler indépendamment et de tester

## Volumes d'envoi

### Limites quotidiennes par boîte mail
- **Démarrage** : max 30 nouveaux contacts/jour
- **Croisière** : cap à 80-100 emails total/jour par boîte
- Les steps s'accumulent : Step 1 + Step 2 + Step 3 = total
- Distribuer les envois sur les heures de bureau (8h-18h)

### Scaling multi-sender
- Connecter plusieurs boîtes mail à 1 campagne
- Les limites s'appliquent PAR ADRESSE, pas en agrégé
- Ex : 10 boîtes × 80 emails = 800 emails/jour

## Contenu — Triggers spam à éviter

### INTERDIT
- Language commercial excessif ("Offre limitée", "Garantie", "Agissez maintenant")
- TEXTE EN MAJUSCULES et ponctuation excessive (!!!)
- Pression d'urgence + mots "gratuit"/"argent"
- Images personnalisées custom (détériore la délivrabilité)
- Pièces jointes directes (utiliser Google Drive links)
- HTML riche : couleurs, bold excessif, mise en forme complexe
- Raccourcisseurs d'URL (bit.ly, etc.)

### RECOMMANDÉ
- Ton conversationnel, comme un humain
- Plain text (le plus authentique)
- Liens en https:// uniquement, le moins possible
- Signature HTML professionnelle = OK (exception)
- SpinText : varier les formulations (20 spintext × 3 options = millions de variantes uniques)

## Bounce et liste

### Hygiène
- Bases de données fraîches (éviter les listes de +6 mois)
- Supprimer les bounces connus avant envoi
- Construire via LinkedIn scraping plutôt que bases achetées
- Vérifier les emails via Emelia verify-email AVANT d'ajouter aux campagnes

### Seuils
- Taux de plainte max : 0.3% (0.1% recommandé)
- Si dépassé → délivrabilité réduite automatiquement ou blocage
- Inclure un lien de désinscription pour éviter les signalements manuels

## Ciblage

### Règles
- NE JAMAIS envoyer à plusieurs contacts de la même entreprise LE MÊME JOUR
- Les grandes entreprises ont des serveurs sécurisés : plusieurs envois le même jour = blocage
- Max 1 contact par entreprise par jour — mais on peut contacter d'autres personnes du même groupe les jours suivants

## Indicateurs de performance

| Taux d'ouverture | Diagnostic |
|---|---|
| 30%+ | Excellent (cold email B2B) |
| 18-30% | Correct, on continue |
| <18% | Problème → revoir objets, ciblage, warmup, redescendre le volume |

Note : les 70% du guide Emelia concernent des campagnes ultra-ciblées. En cold email B2B sur des listes larges, 18-25% c'est la réalité terrain.

## Follow-up
- Répondre professionnellement aux refus (maintient la réputation)
- Espacer les steps raisonnablement (pas de séquence agressive)
- Séquences agressives → risque de blocage/signalement spam
