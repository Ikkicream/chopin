# Catalogue d'alertes de délivrabilité (reverse engineering de Lumail)

Lumail expose chaque problème comme une **alerte persistante** avec une clé de règle stable,
une preuve (evidence), une sévérité et un lien vers un guide de correction. Ce fichier liste
toutes les règles observées dans leur documentation, avec les seuils exacts, pour les
reproduire dans une plateforme. Les clés `domain:*` sont produites par `scripts/dns-audit.mjs`.

## Sommaire
1. Mécanique des alertes (cycle de vie)
2. Authentification du domaine (DNS)
3. Santé d'envoi (métriques)
4. Infrastructure (côté fournisseur, pas DNS)
5. Envois, quotas, facturation, vérification de compte
6. Scores (sender health, campaign delivery score, engagement)
7. Garde-fous par destinataire
8. Domaines de repli (fallback)

---

## 1. Mécanique des alertes

- Chaque alerte = une ligne `Recommendation` avec `ruleKey` stable, `status` OPEN/RESOLVED,
  `severity` INFO/WARNING/ERROR, `evidence` (valeurs observées), `remediationUrl`.
- Ouverture WARNING/ERROR → **une** notification à l'organisation (dédupliquée, avec cooldown).
- **Une alerte ne se résout jamais sur un échec de lookup DNS** : il faut un scan *confirmant*
  l'état sain. (Un timeout DNS ne doit pas fermer `domain:dkim:missing`.)
- Les alertes de métriques exigent des **fenêtres consécutives** au-dessus/au-dessous du
  seuil avec un **échantillon suffisant** : < 50 événements = insuffisant, < 200 = limité ;
  les segments à faible volume restent **neutres** (jamais « à risque »).
- La plateforme **ne modifie jamais le DNS du client** : elle lit, explique, et revérifie.
- Membres : lecture. Owners/admins : rafraîchir les snapshots d'infrastructure.

## 2. Authentification du domaine

| Clé | Sévérité | Déclencheur | Correction |
|---|---|---|---|
| `domain:dmarc:missing` | ERROR | Pas de `_dmarc` sur le domaine ni sur ses parents | TXT `_dmarc` `v=DMARC1; p=none; rua=mailto:…` |
| `domain:dmarc:malformed` | ERROR | Ne commence pas par `v=DMARC1`, `p=` absent/invalide, CNAME sur `_dmarc` | Corriger la syntaxe |
| `domain:dmarc:multiple` | ERROR | 2+ TXT DMARC au même nom | En garder un seul |
| `domain:dmarc:monitoring-only` | WARNING | `p=none` (ou `sp=none` hérité pour un sous-domaine) | Passer `quarantine` puis `reject` **sur le domaine qui publie la politique** (souvent la racine) |
| `domain:dkim:missing` / `failed` / `weak` | ERROR | CNAME/TXT DKIM absents, ou clé < 2048 bits | Copier les enregistrements exacts du fournisseur ; DNS only sur Cloudflare |
| `domain:identity:not-verified` | ERROR | Identité non vérifiée chez le fournisseur | Ajouter vérification + SPF + DKIM + MAIL FROM |
| `domain:mail-from:incomplete` | ERROR | MX ou SPF manquant sur le sous-domaine MAIL FROM (`ses.<domaine>` chez Lumail) | MX `10 feedback-smtp.<region>.amazonses.com` + TXT `v=spf1 include:amazonses.com ~all` |
| `domain:bimi:malformed` | INFO | `default._bimi` présent mais pas `v=BIMI1` + `l=https://…` | Corriger ou supprimer (BIMI n'est jamais requis) |

Points de détail utiles :
- **Héritage DMARC** : pour `hey.melvynx.com`, Lumail lit `_dmarc.hey.melvynx.com` puis, à défaut,
  `_dmarc.melvynx.com` et affiche « Inherited from melvynx.com ». L'alerte nomme le domaine d'envoi,
  mais l'enregistrement à modifier est celui de la racine. Si la racine a `sp=none`, le sous-domaine
  reste en surveillance même avec `p=reject`.
- **Erreurs typiques DMARC** listées par Lumail : CNAME sur `_dmarc`, deux TXT, `p=` manquant, `v=DMARC` (typo).
- **Ne pas passer à `p=reject`** tant que d'autres plateformes (Google Workspace, helpdesk, autre ESP)
  envoient avec le domaine sans SPF/DKIM aligné.
- **Easy DKIM « legacy »** : si l'ancien jeu de CNAME existe, ne pas en ajouter un second sur le même nom.

## 3. Santé d'envoi

| Alerte | Seuils | Base | Sortie d'alerte |
|---|---|---|---|
| Bounce permanent soutenu | WARNING > **2 %**, ERROR > **5 %** | bounces permanents / **envoyés** | fenêtres consécutives < 2 % |
| Plaintes soutenues | WARNING ≈ **0,08 %**, ERROR > **0,1 %** | plaintes FBL / **délivrés** | fenêtres consécutives < seuil warning |
| Retards de livraison | > **10 %** des envoyés retardés | delivery-delay / envoyés | fenêtres consécutives < 10 % |
| Bounces « blocklist / spam » | ≥ **10** bounces ET ≥ **2 %** des envoyés avec diagnostics de type liste noire | texte des bounces reçus | < 10 événements ou < 2 % |

Règles associées :
- Les adresses en bounce permanent ou en plainte sont **supprimées automatiquement** (suppression list) ;
  ne jamais les réimporter. Réactivation possible mais refusée pour les hard bounces sauf `force`.
- Le taux de plainte ne couvre que les FAI qui envoient des feedback loops : une couverture manquante
  n'est **pas** une liste propre.
- « Delivered » = accepté par le serveur destinataire, **pas** placé en boîte de réception.
- Envoyer plus pour « diluer » le taux de bounce aggrave la situation.

## 4. Infrastructure (fournisseur — pas de correction DNS possible)

| Alerte | Signification |
|---|---|
| Feedback bounce/plainte non connecté | Le topic de feedback (SNS) manque sur l'identité : les événements n'arrivent plus |
| Suivi d'événements désactivé | Configuration set désactivé : nouveaux envois rejetés |
| Destination d'événements non saine | Destinations bounce/complaint/delivery manquantes : métriques périmées |
| Envoi suspendu (compte) | Pause au niveau du compte SES ; le fallback ne contourne pas |
| IP dédiée : pool manquant / pas prête / warmup bloqué à 0 % | Le trafic de test et le simulateur ne chauffent pas l'IP |

## 5. Envois, quotas, facturation

| Alerte | Correction |
|---|---|
| Message rejected / send failed | Lire le code fournisseur : `MailFromDomainNotVerifiedException` → MAIL FROM ; identité non vérifiée → vérif ; paramètres invalides → from/to/subject/headers |
| Sending rate exceeded / daily quota | Trois plafonds distincts : débit/s (transitoire, retry), quota SES 24 h, quota du plan (le surplus d'une campagne n'est **pas** mis en file) |
| Recipient rate limited | Voir §7 |
| Email used fallback domain | Réparer le domaine **primaire** |
| Limite mensuelle 80 % / 95 % / 100 % | Upgrade ou attendre le reset ; campagnes parquées, workflows en pause, rien n'est perdu |
| Paiement en retard / pause admin | Envois et workflows parqués |
| Vérification additionnelle / refus / demande d'infos | Formulaire : site, réseau social, taille de liste, usage prévu |
| Campagne bloquée par la vérification de contenu | Cold email et phishing refusés ; une phrase « vous êtes inscrit » ne guérit pas une liste achetée |
| Campagne en échec partiel / erreur de rendu HTML | Corriger puis « retry remaining » |

## 6. Scores

**Sender health (score de confiance 0–100, 30 jours)** — sert à garder l'envoi déverrouillé.
Entrées : bounces, plaintes, ouvertures, clics sur 30 jours. Formule exacte non publiée.
Dégradation (plainte, bounces élevés + faible engagement) → pause de la vérification automatique.

**Campaign delivery score (tableau de bord)** — formule publiée :
```
score = 100 − 5 × bounce% − 10 × complaint% − 0,5 × unsubscribe%   (borné 0–100)
95–100 excellent · 80–94 bon · 60–79 à surveiller · 0–59 critique
```

**Engagement score** — `min(50, open% / 0,6) + min(50, click% / 0,2)` (30 % d'ouverture et 10 % de
clic = 100). Ouvertures classées humain / bot (Apple MPP, proxy Gmail, scanners de sécurité,
même email ouvert depuis plusieurs navigateurs) — classification informative, ne modifie pas les taux.

**Content score** — 11 critères, voir `scripts/content-score.mjs`.

**Déverrouillage du compte** — mode limité à la création (tests vers soi uniquement) ;
la vérification DNS du domaine **déverrouille automatiquement** l'envoi (3 000 emails/mois en gratuit).

## 7. Garde-fous par destinataire (recipient rate guards)

Partagés par campagnes, workflows, API transactionnelle et SMTP :

| Règle | Limite |
|---|---|
| Fréquence | **5** envois acceptés / **10 min** glissantes par adresse |
| Fréquence | **20** envois acceptés / **24 h** glissantes par adresse |
| Cooldown | **24 h** sans envoi après un bounce « recipient rate throttled » ou « mailbox full » |

- L'adresse est **hashée** (SHA-256 de l'enveloppe normalisée) avant stockage Redis.
- Refus à la mise en file : HTTP **429** `{"code":"RECIPIENT_RATE_LIMITED","retryAfter":86400}` + `Retry-After`.
- Refus au moment de l'envoi : la ligne passe `SKIPPED`, jamais réessayée pour une campagne.
- Les destinataires de test (domaines fixtures) contournent le garde-fou.
- Le transactionnel passe en **voie prioritaire** (TIME_SENSITIVE) devant le bulk.

## 8. Domaines de repli

- Priorités 1 → 2 → 3 sur d'autres domaines vérifiés de l'organisation.
- Utilisés seulement pour des échecs **domaine/identité** (MAIL FROM invalide, identité rejetée),
  jamais pour quota, throttling ou configuration set manquant.
- Même nom affiché et même partie locale, seul le domaine change.
- Un repli réussi est **mis en cache 10 min** (org + domaine primaire) : les envois suivants sautent le primaire.
- Notification admin à chaque repli ; si aucun repli ne marche → notification urgente et arrêt des retries permanents.
