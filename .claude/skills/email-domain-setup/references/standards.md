# Normes et exigences des boîtes de réception (état au 13 octobre 2026)

À lire pour justifier un choix de configuration, répondre à « est-ce obligatoire ? », ou
interpréter un code de rejet SMTP. Sources primaires entre crochets en fin de section.

## Sommaire
1. Exigences Gmail, Yahoo, Microsoft, Orange, La Poste
2. SPF (RFC 7208)
3. DKIM (RFC 6376, 8301, 8463) et rotation
4. DMARC — désormais RFC 9989 / 9990 / 9991
5. One-click unsubscribe (RFC 8058)
6. BIMI
7. MTA-STS et TLS-RPT
8. APRF (rapports de performance)
9. ARC et DKIM2
10. Outils de suivi à ouvrir
11. Codes de rejet SMTP utiles

---

## 1. Exigences des fournisseurs de boîtes

| | Tous les expéditeurs | Gros expéditeurs |
|---|---|---|
| **Gmail** (≥ ~5 000/jour vers des comptes Gmail personnels, cumulé par domaine principal) | SPF **ou** DKIM ; PTR valide (forward + reverse) ; TLS ; format RFC 5322 (un seul From/To/Subject/Date, Message-ID valide) ; taux de spam < 0,3 % (viser < 0,1 %) ; pas d'usurpation de gmail.com ; DKIM ≥ 1024 bits (2048 recommandé) | SPF **et** DKIM ; DMARC (`p=none` accepté) ; From aligné avec SPF ou DKIM ; one-click unsubscribe + lien visible pour le marketing ; désinscription traitée sous 48 h |
| **Yahoo** | SPF ou DKIM ; spam < 0,3 % ; DNS direct/inverse ; RFC 5321/5322 | SPF et DKIM ; DMARC ≥ `p=none` qui passe (`rua` fortement recommandé) ; alignement relâché accepté ; one-click (RFC 8058 recommandé, mailto accepté) + lien visible ; désinscription sous 2 jours |
| **Microsoft** (Outlook.com/Hotmail/Live, ≥ 5 000/jour, depuis le 5 mai 2025) | rDNS valide, pas d'IP dynamique, ≤ 500 connexions simultanées, ne pas réessayer après un 5xx | SPF **et** DKIM qui passent ; DMARC ≥ `p=none` aligné ; rejet `550 5.7.515` (appliqué aujourd'hui, date de bascule non publiée) |
| **Orange** (MAJ 1ᵉʳ sept. 2026) | SPF, DKIM, DMARC tous exigés ; PTR, HELO FQDN, IP fixe ; TLS ≥ 1.2 ; 2 connexions/IP, 100 messages/connexion, 100 destinataires/message | > 1 000/jour : les trois doivent passer, From aligné ; seuil de plainte 0,6 % qui doit passer à 0,3 % ; RFC 8058 recommandé ; ARC recommandé pour les relais |
| **laposte.net** | IP non autorisée par SPF rejetée ; DKIM fortement recommandé ; DMARC appliqué (publier au minimum `p=none` + `rua`) ; PTR valide | (des éditeurs annoncent SPF+DKIM+DMARC exigés depuis sept. 2025 ; la page officielle est plus souple) |

Calendrier Gmail : exigences en février 2024, one-click obligatoire au 1ᵉʳ juin 2024, perte des
mesures d'atténuation au-dessus de 0,3 % de spam (retour après 7 jours sous le seuil), **rejets
temporaires puis permanents depuis novembre 2025**.

[support.google.com/a/answer/81126 · /14229414 · senders.yahooinc.com/best-practices ·
substrate.office.com/ip-domain-management-snds/postmaster/Policies · postmaster.orange.fr ·
postmaster.laposte.net]

## 2. SPF

- 10 termes déclenchant une requête DNS maximum (`include`, `a`, `mx`, `ptr`, `exists`,
  `redirect`) → au-delà, `permerror`. 2 « void lookups » maximum. `ptr` à ne pas publier.
  Deux enregistrements SPF sur le même nom → `permerror`.
- **Le SPF du Return-Path compte, pas celui du From.** Un sous-domaine de retour par fournisseur
  évite de saturer le SPF de la racine et évite l'aplatissement (flattening), fragile quand les
  plages IP du fournisseur changent.
- `~all` sur les domaines qui envoient (DMARC traite softfail et hardfail pareil, et `-all` casse
  le transfert ; Gmail peut rejeter un hardfail avant même DMARC). `v=spf1 -all` sur les domaines
  qui n'envoient jamais.

[rfc-editor.org/rfc/rfc7208]

## 3. DKIM

- RFC 8301 : ≥ 1024 bits obligatoire, 2048 recommandé ; rsa-sha1 déprécié. Une clé 2048 bits en
  TXT dépasse 255 caractères : la découper en plusieurs chaînes (le CNAME vers le fournisseur évite
  le problème et permet la rotation).
- Ed25519 (RFC 8463, `k=ed25519`) : toujours en **double signature** avec RSA (Microsoft et Yahoo
  ne le vérifieraient pas ; support Gmail incertain).
- Rotation (M3AAWG) : au moins tous les 6 mois ; publier le nouveau sélecteur avant de basculer,
  garder l'ancien publié quelques jours à quelques semaines, révoquer avec `p=` vide, ne jamais
  réutiliser un sélecteur. Avec Easy DKIM (SES), les CNAME Brevo ou SendGrid, le fournisseur tourne
  les clés pour vous.

## 4. DMARC — RFC 9989 / 9990 / 9991 (mai 2026)

DMARCbis est publié : **RFC 9989** (protocole), **RFC 9990** (rapports agrégés), **RFC 9991**
(rapports d'échec). Ils rendent RFC 7489 et RFC 9091 obsolètes. Les enregistrements restent
`v=DMARC1` ; les anciens tags sont ignorés.

| Tag | Statut | Rôle |
|---|---|---|
| `v` | requis, en premier | `DMARC1` |
| `p` | requis | `none` · `quarantine` · `reject` |
| `sp` | optionnel | politique des sous-domaines existants |
| `np` | **nouveau** | politique des sous-domaines **inexistants** (à défaut `sp`, puis `p`) |
| `adkim`, `aspf` | optionnels | `r` (relâché, défaut) ou `s` (strict) |
| `rua`, `ruf` | optionnels | destinations des rapports (`mailto:`) |
| `fo` | optionnel | options des rapports d'échec |
| `psd` | **nouveau** | `y` (suffixe public), `n` (« je suis le domaine organisationnel »), `u` (défaut) |
| `t` | **nouveau** | `y` = mode test : la politique s'applique un cran en dessous (reject→quarantine, quarantine→none). Remplace `pct` |
| `pct`, `rf`, `ri` | **supprimés** | ignorés par les récepteurs DMARCbis |

- **Découverte** : le « DNS tree walk » remplace la Public Suffix List — jusqu'à 8 requêtes en
  remontant les labels, arrêt sur `psd=y|n`. En pratique : publier sur la racine suffit pour
  tous les sous-domaines, sauf hiérarchie de plus de 8 labels.
- **Rapports externes** : si `rua` pointe vers un autre domaine, celui-ci doit publier
  `<domaine>._report._dmarc.<destination>` TXT `v=DMARC1;` (wildcard autorisé).
- **Rapports agrégés (RFC 9990)** : nouvel espace de noms XML `urn:ietf:params:xml:ns:dmarc-2.0`,
  champs `np`, `testing`, `discovery_method` ; un rapport par domaine de politique et par jour UTC.
- **Rapports d'échec (RFC 9991)** : peu envoyés par les grands fournisseurs ; les rapports agrégés
  restent la méthode recommandée.
- Exemples de la RFC 9989 :
  `v=DMARC1; p=none; rua=mailto:dmarc-feedback@example.com` ·
  `v=DMARC1; p=quarantine; rua=mailto:dmarc-feedback@example.com; t=y`

**Progression recommandée** : `p=none` + `rua` (2–4 semaines, inventaire de tous les expéditeurs)
→ `p=quarantine; t=y` → `p=quarantine` → `p=reject`, en ajoutant `np=reject` sur la racine.
Ne pas passer à `reject` tant qu'un outil (CRM, helpdesk, facturation) envoie sans DKIM aligné.
La RFC 9989 déconseille `p=reject` aux domaines de messagerie grand public (listes de diffusion).

[rfc-editor.org/rfc/rfc9989 · /rfc9990 · /rfc9991]

## 5. One-click unsubscribe (RFC 8058)

En-têtes obligatoires sur tout email marketing / abonnement (pas sur le transactionnel) :
```
List-Unsubscribe: <https://click.client.com/u/opaque-token>, <mailto:unsub@news.client.com?subject=unsub>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```
- L'URL HTTPS reçoit un `POST` avec le corps `List-Unsubscribe=One-Click` : désinscrire
  immédiatement, sans page de confirmation ni cookie, et répondre 200/202.
- Les deux en-têtes doivent être couverts par la signature DKIM.
- Garder aussi un lien visible dans le corps. Traiter sous 48 h (Gmail) / 2 jours (Yahoo).
- SES : `ListManagementOptions` ou en-têtes personnalisés ; Resend : `headers` à l'envoi ;
  Brevo l'ajoute automatiquement.

## 6. BIMI

- Spécification encore en draft (`draft-brand-indicators-for-message-identification-14`).
- Enregistrement : `default._bimi.<domaine>` TXT
  `v=BIMI1; l=https://exemple.com/bimi/logo.svg; a=https://exemple.com/bimi/vmc.pem`
- Prérequis : DMARC `quarantine` ou `reject` appliqué à 100 % sur le domaine organisationnel et
  sur le domaine du From, `sp` différent de `none` (traiter `t=y` comme disqualifiant tant que ce
  n'est pas clarifié).
- Logo SVG Tiny PS (`baseProfile="tiny-ps"`, `version="1.2"`), carré, ≥ 96 px, ≤ 32 Ko, sans script.
- **Gmail** : VMC ou CMC (CMC = pas de marque déposée mais logo affiché publiquement ~12 mois) ;
  coche bleue uniquement avec un VMC. **Apple** : VMC. **Yahoo** : pas de certificat exigé
  (expéditeurs en volume avec bonne réputation). Affiché aussi par La Poste, Fastmail.

## 7. MTA-STS et TLS-RPT

Protègent la **réception** sur les MX du domaine — inutiles pour un sous-domaine d'envoi sans MX ;
à déployer sur la racine qui reçoit du courrier.
```
_mta-sts.client.com   TXT "v=STSv1; id=20261013T000000Z"
https://mta-sts.client.com/.well-known/mta-sts.txt :
  version: STSv1
  mode: testing          (puis enforce)
  mx: client-com.mail.protection.outlook.com
  max_age: 604800
_smtp._tls.client.com TXT "v=TLSRPTv1; rua=mailto:tls-reports@client.com"
```
Côté envoi, ce qui compte est que le MTA du fournisseur propose TLS (exigé par Gmail ; TLS ≥ 1.2
chez Orange).

## 8. APRF — Aggregate Performance Reporting

- **Statut** : adopté par le groupe de travail IETF MAILMAINT le 8 octobre 2026 →
  `draft-ietf-mailmaint-aprf-00` (9 oct. 2026). Successeur de
  `draft-brotman-aggregate-performance-reporting` (-00 mars 2026, -01 sept. 2026). Pas encore une RFC.
- **Principe** : le fournisseur de boîte envoie chaque jour à l'expéditeur un rapport JSON de
  **classement** (inbox / indésirable, éventuellement promotions / transféré) et d'**engagement**
  (positif / neutre / négatif) par domaine et sélecteur **DKIM** (pas par domaine du From).
- **Enregistrement** (recherche du plus spécifique au plus général) :
  `<s>._aprf._domainkey.<d>` → `*._aprf._domainkey.<d>` → `_aprf._domainkey.<d>` (nouveau en WG-00)
  ```
  v=APRFv1;rua=mailto:reports@example.org
  v=APRFv1;rua=mailto:reports@example.org;sdi=MsgInfo,^
  ```
  `sdi=<en-tête>,<séparateur>` (optionnel) segmente par un en-tête interne signé DKIM ; attention,
  les valeurs de segment apparaissent en clair dans les rapports.
- **Destination externe** : autorisation par `<sélecteur>.<domaine DKIM>._aprf.<domaine destination>`.
- **Rapports** : un jour UTC, `multipart/report` + pièce jointe `application/json` (gzip possible),
  objet commençant par `APRF: `, fichier `<aaaammjj>_<domaine DKIM>_<sélecteur>_<source>`.
- **Qui envoie** : Comcast/Xfinity uniquement, en bêta. Google co-auteur, mais pas d'envoi constaté.
- **Recommandation** : publier un wildcard par domaine DKIM (coût nul) et prévoir une boîte qui
  ingère les rapports JSON. `dns-plan.mjs --aprf` le génère.

[datatracker.ietf.org/doc/draft-ietf-mailmaint-aprf · mindbaz.com (article APRF) · spamresource.com]

## 9. ARC et DKIM2

- **ARC** (RFC 8617, expérimental) : un draft propose de le passer en statut historique (avril 2026).
  Inutile pour un SaaS qui envoie ; Orange le recommande encore aux relais.
- **DKIM2** (`draft-ietf-dkim-dkim2-spec-06`, août 2026) : chaîne de garde, en-têtes
  `DKIM2-Signature` et `Message-Instance`, détection du rejeu. Pas encore déployable.

## 10. Outils de suivi à ouvrir

| Outil | Ce qu'il donne | Inscription |
|---|---|---|
| Google Postmaster Tools v2 | tableau « Compliance status » (Compliant / Needs work / No data), taux de spam ; agrégé au domaine principal | vérification DNS TXT du domaine |
| Microsoft SNDS + JMRP | réputation par IP, boucle de plaintes | IP dédiées seulement |
| Yahoo Sender Hub | boucle de plaintes (par domaine DKIM `d=`), Insights | par domaine DKIM |
| Rapports DMARC (`rua`) | qui envoie avec votre domaine, taux d'alignement | parseur (dmarcian, Valimail, Postmark DMARC gratuit…) |
| APRF | placement et engagement (Comcast) | enregistrement DNS |

## 11. Codes de rejet SMTP utiles

| Code | Signification |
|---|---|
| Gmail `421 4.7.0` / `550 5.7.25` | PTR invalide |
| Gmail `421 4.7.26` / `550 5.7.26` | non authentifié, SPF `-all` en échec ou DMARC reject |
| Gmail `421 4.7.27` / `550 5.7.27` | gros expéditeur, SPF en échec |
| Gmail `421 4.7.29` / `550 5.7.29` | gros expéditeur sans TLS |
| Gmail `421 4.7.30` / `550 5.7.30` | gros expéditeur, DKIM en échec |
| Gmail `421 4.7.32` | From non aligné |
| Gmail `421 4.7.40` / `550 5.7.40` | pas de DMARC |
| Gmail `550 5.7.24` | entrées SPF suspectes |
| Microsoft `550 5.7.515` | niveau d'authentification insuffisant (≥ 5 000/jour) |
| Microsoft `550 5.7.509` | votre propre `p=reject` appliqué |
| Orange `519` / `535` / `515` / `107` | SPF / pas de DKIM / DMARC reject / pas de PTR |
