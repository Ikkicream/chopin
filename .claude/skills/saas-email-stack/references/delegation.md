# Délégation des sous-domaines clients (Route 53) et alternatives

À lire pour accompagner un client dans la délégation, installer les serveurs de noms « marque
blanche », ou choisir entre délégation, records copiés, Entri et Domain Connect.
Faits vérifiés au 13/10/2026.

## Sommaire
1. Principe et ordre des opérations
2. Installation : jeux de serveurs réutilisables et marque blanche
3. Vérifier une délégation
4. Pièges côté client
5. DNSSEC, CAA, DMARC
6. Départ d'un client : risque de reprise du sous-domaine
7. Domaines de tracking (Cloudflare for SaaS)
8. Écrire chez l'hébergeur du client : Entri, Domain Connect, token Cloudflare
9. Quotas et coûts

---

## 1. Principe et ordre des opérations

Le client pose, **une seule fois**, des enregistrements NS pour `news.client.com` vers nos serveurs.
Tout le reste est écrit par la plateforme dans la zone Route 53 dédiée.

Ordre imposé par le cache DNS négatif (900 s par défaut) : **créer la zone ET écrire tous les records
avant** de donner les NS au client. Sinon un résolveur qui interroge trop tôt met « n'existe pas » en
cache pendant 15 minutes.

1. Vérifier que le nom n'est pas déjà enregistré sur la plateforme (unicité).
2. Créer les identités chez les fournisseurs (région figée) → récupérer DKIM, MAIL FROM.
3. `CreateHostedZone` (avec un jeu de serveurs réutilisable) → 4 NS.
4. `ChangeResourceRecordSets` (UPSERT, lot atomique) : DKIM, MAIL FROM (MX + SPF), DMARC du
   sous-domaine, tracking, CAA si besoin. `GetChange` → `INSYNC` (en général < 60 s).
5. Donner au client le tableau NS (`assets/client-guide-delegation.md`), TTL 3600 conseillé.
6. Job : `checkDelegation()` jusqu'à ce que le sous-domaine réponde avec nos NS, puis vérification fournisseur.
7. Zone toujours pas déléguée après 7 jours → supprimée (le tenant ne « réserve » pas le nom).

## 2. Installation : jeux de serveurs réutilisables et marque blanche

Sans jeu réutilisable, chaque zone reçoit 4 NS différents : instructions différentes par client.
Avec un jeu réutilisable, **tous les clients reçoivent les mêmes 4 NS**.

```bash
aws route53 create-reusable-delegation-set --caller-reference platform-ns-1
# → DelegationSet.Id (N…) et 4 NameServers ; mettre l'Id dans ROUTE53_DELEGATION_SET_IDS
```
- 100 zones par jeu par défaut, 100 jeux par compte (les deux relevables) : lister plusieurs jeux,
  séparés par des virgules ; `route53.ts` passe au suivant quand l'un est plein.
- Un jeu ne s'attache qu'à la création d'une zone (impossible de changer les NS d'une zone ensuite).
- Deux zones du même nom (ou parent/enfant) ne peuvent pas partager les mêmes serveurs
  (`ConflictingDomainExists`) : en cas de réinscription, réutiliser la zone existante.

Serveurs « marque blanche » (`ns1.plateforme-dns.com` … `ns4`) — optionnel, masque AWS :
1. Relever les IPv4/IPv6 des 4 NS du jeu (`dig A`, `dig AAAA`).
2. Dans la zone `plateforme-dns.com` : 8 records A/AAAA `ns1`–`ns4`.
3. Mettre à jour SOA et NS des zones avec ces noms.
4. Déclarer les **glue records** chez le registrar de `plateforme-dns.com`.
5. TTL ≤ 60 s pendant les tests, puis NS 172800 et SOA minimum 900.
Utiliser un domaine dédié au DNS (pas le domaine produit) : une erreur de glue coupe tous les clients.

## 3. Vérifier une délégation

```bash
dig +trace news.client.com NS                        # chemin complet
dig +norec NS news.client.com @<NS du parent>        # section AUTHORITY = nos 4 NS
dig +norec SOA news.client.com @<un de nos NS>       # drapeau aa attendu
```
`domains/dns-check.ts → checkDelegation()` fait l'équivalent via un résolveur public : délégué si
les NS renvoyés sont exactement les nôtres, « partiel » si seulement certains.

## 4. Pièges côté client

| Erreur | Symptôme | Correction |
|---|---|---|
| Nom saisi en entier chez un hébergeur qui ajoute le domaine | `news.client.com.client.com` | saisir `news` seulement |
| Changer les serveurs de noms du domaine au lieu d'ajouter des NS | tout le domaine (site, mails) bascule chez nous | ce sont des enregistrements NS sur `news`, pas les « nameservers » du domaine |
| Anciens records `news` laissés dans la zone parente | réponses incohérentes, NXDOMAIN | supprimer tout autre record sur ce nom |
| Seulement 2 des 4 NS | fonctionne par intermittence | poser les 4 |
| DS ajouté sans zone signée | SERVFAIL (DNSSEC « bogus ») | ne pas ajouter de DS |

## 5. DNSSEC, CAA, DMARC

- **DNSSEC** : parent signé + enfant non signé **sans DS** = délégation « insecure », valide. Signer
  les zones enfants imposerait une clé KMS et un DS chez chaque client : pas en V1.
- **CAA** : une autorité de certification remonte l'arbre ; le CAA du parent s'applique au sous-domaine.
  Si le client restreint ses CA, publier dans la zone enfant un CAA autorisant l'AC du tracking
  (Cloudflare : `letsencrypt.org`, `pki.goog`, `ssl.com`, `sectigo.com`).
- **DMARC** : avec un From `@news.client.com`, notre `_dmarc.news.client.com` s'applique (sinon le
  `sp=` de la racine). `service.ts` reprend la politique de la racine si elle est déjà
  `quarantine`/`reject` : on n'affaiblit jamais une politique existante. Ne **jamais** publier `psd=n`
  dans la zone enfant (le sous-domaine deviendrait son propre domaine organisationnel et casserait
  l'alignement avec `client.com`). DKIM `d=news.client.com` s'aligne en mode relâché, pas si la
  racine impose `adkim=s`.

## 6. Départ d'un client : risque de reprise du sous-domaine

Si la zone est supprimée alors que le client garde ses NS vers des serveurs Route 53, un tiers peut
créer une zone du même nom et envoyer des emails « de » ce client. Procédure :
1. Désactiver l'envoi, retirer DKIM / MAIL FROM de la zone (la garder **vide**, ~0,10 $/mois).
2. Demander au client de retirer ses NS ; vérifier avec `checkDelegation()` (`found` vide).
3. Seulement alors : `deleteDelegatedZone()`.
Surveiller les délégations orphelines (NS encore présents, client parti) dans le job quotidien.

## 7. Domaines de tracking (Cloudflare for SaaS)

Pour des liens `https://click.news.client.com/r/…` avec certificat automatique :
- Zone Cloudflare de la plateforme avec un hôte de repli (`tracking.plateforme.com`).
- `POST /zones/{zone_id}/custom_hostnames` `{ hostname, ssl: { method: "http", type: "dv" } }`.
- Dans la zone déléguée : `click.news.client.com CNAME tracking.plateforme.com` — on l'écrit
  nous-mêmes, le client n'a rien à faire. Prêt quand `status` et `ssl.status` = `active`.
- 100 hostnames inclus (Free/Pro/Business), puis 0,10 $/hostname (50 000 max).
- Le suivi des clics est fait par la plateforme (redirection `/r/…`), identique pour Resend et SES :
  le tracking natif SES (`awstrack.me`) exige un CloudFront + certificat par domaine.

## 8. Écrire chez l'hébergeur du client

| Option | Coût | NS possible ? | Remarques |
|---|---|---|---|
| Token Cloudflare du client | gratuit | oui | `email-domain-setup/scripts/cloudflare-apply.mjs` (simulation par défaut) |
| **Entri** | à partir de 249 $/mois (600 domaines/an) | non documenté | 60–70 hébergeurs, fusion SPF, préserve un DMARC existant ; utilisé par Customer.io |
| **Domain Connect** | gratuit | NS optionnel selon l'hébergeur | template à faire accepter (GitHub Domain-Connect/Templates) puis activer chez chaque hébergeur : IONOS, Cloudflare, GoDaddy, Vercel, WordPress.com… OVH non listé |
| Records copiés | gratuit | — | toujours proposé en secours |

Recommandation : délégation NS avec instructions par hébergeur (OVH, Gandi, GoDaddy, Cloudflare,
IONOS) ; Entri plus tard si le volume d'onboarding le justifie.

## 9. Quotas et coûts Route 53

| Élément | Valeur |
|---|---|
| Zone hébergée | 0,50 $/mois (25 premières), puis 0,10 $ ; gratuite si supprimée sous 12 h |
| Requêtes | 0,40 $/million (premier milliard) |
| Zones par compte | 500 au départ, relevable (Service Quotas, us-east-1) |
| Records par zone | 10 000 |
| `ChangeResourceRecordSets` | lot atomique ; UPSERT compte double ; `PriorRequestNotComplete` si un changement est en cours sur la zone |
| Débit API | 50 requêtes en rafale puis 10/s ; `CreateHostedZone` 40 puis 2/s |
