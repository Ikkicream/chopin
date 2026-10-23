# Connecter votre domaine d'envoi à {{PLATEFORME}}

*Guide à transmettre à votre client ou à son prestataire informatique. Les éléments entre
`{{…}}` sont remplis automatiquement par la plateforme.*

Pour que vos emails partent **de votre propre adresse** (`{{EXPEDITEUR}}`) et arrivent en boîte
de réception, nous utilisons un sous-domaine dédié : **`{{SOUS_DOMAINE}}`**. Votre domaine
principal, votre site et vos boîtes mail ne changent pas.

Deux façons de faire — choisissez celle qui vous convient :

## Option A (recommandée) — Déléguer le sous-domaine, une seule fois

Vous ajoutez **{{NB_NS}} enregistrements NS** chez votre hébergeur DNS (OVH, Gandi, GoDaddy,
Cloudflare, IONOS…). Ensuite, nous gérons nous-mêmes toute la configuration technique d'envoi
(signatures DKIM, retour des erreurs, suivi des liens), et vous n'aurez plus jamais à intervenir,
même si nous changeons d'infrastructure.

| Type | Nom / Hôte | Valeur |
|---|---|---|
{{LIGNES_NS}}

Points d'attention :
- Le **nom** est `{{ETIQUETTE}}` (certains hébergeurs veulent `{{SOUS_DOMAINE}}` complet ; s'ils
  ajoutent automatiquement votre domaine, ne le tapez pas deux fois).
- Ne créez **aucun autre enregistrement** sur `{{ETIQUETTE}}` (ni A, ni MX, ni CNAME).
- Sur Cloudflare : les NS ne sont jamais « proxifiés », rien à changer.
- Votre domaine utilise DNSSEC ? Rien à faire de plus : la délégation fonctionne sans
  enregistrement DS.

Délai : de quelques minutes à quelques heures. La plateforme vérifie automatiquement et vous
prévient dès que c'est actif.

## Option B — Ajouter les enregistrements vous-même

Si votre politique interne interdit la délégation, ajoutez les enregistrements ci-dessous.
Vous devrez recommencer si la configuration change.

| Type | Nom / Hôte | Valeur | Priorité |
|---|---|---|---|
{{LIGNES_RECORDS}}

- Sur Cloudflare, chaque enregistrement CNAME doit être en **DNS only** (nuage gris).
- Copiez les valeurs, ne les retapez pas.

## Dans les deux cas : la politique DMARC de votre domaine

Si votre domaine principal n'a pas encore d'enregistrement DMARC, ajoutez-le (il protège votre
marque contre l'usurpation) :

| Type | Nom | Valeur |
|---|---|---|
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:{{ADRESSE_RAPPORTS_DMARC}}` |

S'il en existe déjà un, **ne le dupliquez pas** : il ne doit y en avoir qu'un. Nous vous
proposerons de le renforcer (`p=quarantine`) une fois la montée en charge terminée.

## Et ensuite ?

1. Vérification automatique du domaine (vous recevez un email).
2. Nous inscrivons le domaine aux outils de suivi de Google et Yahoo (avec votre accord).
3. Montée en charge progressive : environ 400 envois par jour la première semaine, vers vos
   contacts les plus actifs, puis doublement chaque semaine. C'est ce qui construit la réputation
   de votre domaine auprès de Gmail, Outlook et Orange.

Une question ? {{CONTACT_SUPPORT}}
