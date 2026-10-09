# Guide Délivrabilité Email 2026

Sep 26, 2026 · @Camille

> Copie fidèle du guide fourni par Camille le 26/09/2026. Synthèse actionnable et écarts avec notre
> installation : `../SKILL.md`. Les outils cités en section 10 (`audit_dns.py`, `lint_email.py`…)
> ne sont PAS sur le serveur Genesis à cette date.

En 2026, un email arrive en boîte de réception s'il coche trois couches : une authentification alignée sans faille (SPF, DKIM, DMARC, désinscription en un clic), un taux de plainte sous 0,1 %, et un contenu lisible aussi bien par les filtres que par les assistants IA des messageries.

## 1. Ce qui a changé en 2025-2026 : les règles des messageries

Depuis novembre 2025, Gmail ne se contente plus de filtrer : il rejette. Microsoft rejette depuis mai 2025, La Poste applique ses règles depuis septembre 2025, et Orange exige désormais DMARC. Le socle commun est le même partout : SPF et DKIM alignés, DMARC publié, désinscription en un clic, moins de 0,3 % de plaintes.

### Exigences par fournisseur

| Fournisseur | Seuil « gros expéditeur » | Authentification | Désinscription | Plaintes | Refus typique |
| --- | --- | --- | --- | --- | --- |
| [Gmail](https://support.google.com/a/answer/81126?hl=en) | Environ 5 000 messages/jour vers des comptes Gmail personnels, comptés par domaine principal. Statut [permanent](https://support.google.com/a/answer/14229414?hl=en) | SPF **et** DKIM, DMARC `p=none` minimum, From aligné sur SPF ou DKIM. PTR valide, TLS, RFC 5322 | Un clic RFC 8058 + lien visible, traité sous 48 h (marketing seulement) | Cible < 0,10 %, jamais ≥ 0,30 % | `550 5.7.26`, `421 4.7.28`, `550 5.7.1` |
| [Yahoo / AOL](https://senders.yahooinc.com/best-practices/) | [Aucun seuil chiffré](https://senders.yahooinc.com/faqs/) | SPF et DKIM, DMARC `p=none` minimum qui doit passer, alignement | Un clic (POST « très recommandé »), sous 2 jours | < 0,3 % | 421/451 temporaires, 553/554 définitifs |
| [Microsoft Outlook.com](https://support.microsoft.com/en-us/outlook/fix-ndr-error-550-5-7-515-in-outlook-com) | 5 000 messages/jour vers Outlook.com, Hotmail, Live | SPF **et** DKIM doivent passer tous les deux, DMARC `p=none` minimum, alignement | Recommandée, pas imposée | Aucun seuil publié | `550 5.7.515` |
| [Apple iCloud](https://support.apple.com/en-us/102322) | Aucun | SPF, DKIM, DMARC publié, PTR | Lien de désinscription | Pas de boucle de plaintes | Contact : icloudadmin@apple.com |
| [Orange](https://postmaster.orange.fr/index.html) | Plus de 1 000 messages/jour pour les règles renforcées | SPF, DKIM, **DMARC requis**, PTR, IP statique, HELO en FQDN. TLS 1.2 et ARC fortement recommandés | Un clic RFC 8058 + en-tête Feedback-ID au format Google (> 1 000/jour) | 0,6 % déclenche des protections, passage progressif à 0,3 % | Codes `OFR` (voir plus bas) |
| [La Poste](https://postmaster.laposte.net/contents/quelles-sont-les-specifications-techniques-a-respecter-pour-emettre-des-emails-vers-laposte-net) | Aucun | Rejet si l'IP n'est pas autorisée par SPF. DKIM fortement recommandé. DMARC `p=none` minimum **avec rua** | Lien de désinscription | Boucle de plaintes via Validity | Rejet sans DKIM valide |
| [Free](https://postmaster.free.fr/) | Aucun | Page non mise à jour : aucune règle SPF, DKIM ou DMARC publiée | — | — | `550 spam detected`, `500 Too many spams from your IP` (blocage jusqu'à 24 h) |
| SFR | Page postmaster inaccessible lors de la recherche | À vérifier sur postmaster.sfr.fr | — | Boucle via Signal Spam | `GU_EIB_04` (taux de spam), `GU_EIB_02` (adresses invalides) |

Points qui piègent souvent :

- **Microsoft est plus strict que Gmail sur un point.** SPF et DKIM doivent passer tous les deux, alors qu'un seul des deux suffit à DMARC.
- **Le statut de gros expéditeur Gmail est définitif.** Une seule journée à 5 000 envois suffit, et le compte se fait sur le domaine principal : tous les sous-domaines s'additionnent.
- **La désinscription en un clic ne concerne que le marketing** chez Gmail. Un lien mailto dans le corps ne suffit pas ([FAQ Google](https://support.google.com/a/answer/14229414?hl=en)).
- **Orange applique la règle des 1 000 envois par jour.** Au-delà, Feedback-ID et un clic sont exigés, ainsi qu'un site décrivant l'entreprise et la preuve du consentement.

### Chronologie des changements

| Date | Changement |
| --- | --- |
| Sept. 2026 | Microsoft Defender for Office 365 met en quarantaine les emails contenant des instructions cachées pour l'IA (section 8) |
| 27 août 2026 | M3AAWG publie ses [Sender Best Common Practices v4.0](https://www.m3aawg.org/sites/default/files/doc_files/m3aawg-sender-best-common-practices-aug-27-2026.pdf) |
| Juin 2026 | Microsoft relance [SNDS](https://www.spamresource.com/2026/06/snds-and-jmrp-in-transition.html) avec de nouveaux contrôles d'accès. Les rapports JMRP sont caviardés |
| Mai 2026 | DMARCbis publié : [RFC 9989](https://www.rfc-editor.org/rfc/rfc9989.html) (protocole), RFC 9990 (rapports agrégés), [RFC 9991](https://www.rfc-editor.org/rfc/rfc9991.html) (rapports d'échec) |
| 14 avril 2026 | [Apple Business](https://www.apple.com/newsroom/2026/03/introducing-apple-business-a-new-all-in-one-platform-for-businesses-of-all-sizes/) remplace Apple Business Connect, logo de marque dans Mail inclus |
| 8 janv. 2026 | Gmail lance l'[AI Inbox](https://blog.google/products-and-platforms/products/gmail/gmail-is-entering-the-gemini-era/) et les AI Overviews |
| Nov. 2025 | Gmail durcit l'application : rejets temporaires **et** définitifs des messages non conformes ([Spam Resource](https://www.spamresource.com/2025/11/google-warns-sender-requirements.html)) |
| 27 oct. 2025 | Yahoo Sender Hub ajoute [Insights](https://www.spamresource.com/2025/10/yahoo-sender-hub-now-with-insights.html) : taux de plainte et volume par domaine DKIM |
| 30 sept. 2025 | Date initiale de retrait des tableaux de réputation de Postmaster Tools, ensuite [reportée](https://support.google.com/a/answer/16594218?hl=en) |
| 11 sept. 2025 | Gmail trie l'onglet Promotions par [pertinence](https://www.spamresource.com/2025/09/relevance-comes-to-gmail-promo-tab.html) et ajoute la vue Achats |
| 9 sept. 2025 | La Poste applique SPF, DKIM et DMARC ([DMARCwise](https://dmarcwise.io/blog/laposte-new-requirements-2025)) |
| Mi-août 2025 | Orange annonce l'abaissement de son seuil de plaintes vers 0,3 % ([Suped](https://www.suped.com/blog/orange-fr-postmaster-is-tightening-the-screws-what-their-august-2025-deliverability-updates-mean-for-you)) |
| 8 juil. 2025 | Gmail lance [« Gérer les abonnements »](https://blog.google/products-and-platforms/products/gmail/new-manage-subscriptions-unsubscribe/) : expéditeurs triés par fréquence, désinscription en un geste |
| 5 mai 2025 | Microsoft impose ses règles aux gros expéditeurs, rejet `550 5.7.515` ([dmarcian](https://dmarcian.com/microsoft-enforces-spf-dkim-dmarc/)) |
| Fév. – juin 2024 | Gmail et Yahoo imposent authentification, un clic et seuil de plaintes |

### Codes de refus à connaître

Gmail ([liste officielle](https://knowledge.workspace.google.com/admin/support/troubleshooting/gmail-smtp-errors-and-codes?hl=en)) :

| Code | Cause | Action |
| --- | --- | --- |
| `421 4.7.26` / `550 5.7.26` | Non authentifié, ou bloqué par la politique DMARC du domaine | Vérifier SPF, DKIM et alignement |
| `421 4.7.27` / `550 5.7.27` | Échec SPF | Ajouter l'IP ou l'include de l'ESP |
| `421 4.7.30` / `550 5.7.30` | Échec DKIM | Vérifier clé publiée et sélecteur |
| `421 4.7.32` / `550 5.7.32` | From non aligné sur SPF ou DKIM | Signer avec `d=` sur votre domaine |
| `421 4.7.40` / `550 5.7.40` | Pas d'enregistrement DMARC | Publier au moins `p=none` |
| `451 4.7.23`, `550 5.7.25` | Reverse DNS absent ou incohérent | Corriger le PTR |
| `421 4.7.29` / `550 5.7.29` | Pas de TLS | Activer STARTTLS |
| `421 4.7.28` | Taux inhabituel de messages non sollicités depuis votre IP, domaine DKIM, domaine SPF ou domaine d'URL | Réduire le volume, cibler les actifs |
| `550 5.7.1` | Réputation très basse de l'IP ou du domaine, ou en-têtes From / Message-ID invalides | Pause, audit, reprise progressive |

Orange ([postmaster, mis à jour le 1er sept. 2026](https://postmaster.orange.fr/index.html)) : `OFR_104` trop de connexions simultanées, `OFR_107` pas de PTR, `OFR_109` trop de messages par connexion, `OFR_397/398` SPF, `OFR_515` échec DMARC, `OFR_535` pas de signature DKIM, `OFR_506/536` spam suspecté, `OFR_988` à `990` limitation liée à la réputation. Limites : 2 connexions simultanées par IP, 100 messages par connexion, 100 destinataires par message.

### Signal Spam, le cas français

[Signal Spam](https://www.signal-spam.fr/feedback-loop/) fédère Orange, SFR, La Poste, OVH et des ESP comme Brevo et Splio. Sa boucle de rétroaction est la seule qui donne accès aux plaintes des abonnés Orange. Un signalement y vaut demande de désinscription. L'accès passe par une déclaration de conformité validée par un comité, et la [charte](https://www.signal-spam.fr/charte-deontologie/) impose l'en-tête `X-SignalSpam-CID` et une désinscription effective sous 72 h.

## 2. Authentification : la configuration cible

La cible 2026 : un sous-domaine par flux, SPF en `~all` sous 8 lookups, DKIM RSA 2048 signé avec votre domaine et renouvelé tous les 6 mois, DMARC monté jusqu'à `p=reject` avec rapports, et un logo de marque via BIMI et Apple Business.

### Architecture de domaines

Les [Sender BCP v4.0 du M3AAWG](https://www.m3aawg.org/sites/default/files/doc_files/m3aawg-sender-best-common-practices-aug-27-2026.pdf) (août 2026) demandent un même domaine organisationnel partout : Return-Path, From, DKIM `d=`, HELO, reverse DNS, Reply-To et liens. Séparer marketing et transactionnel par sous-domaine protège vos confirmations de commande si une campagne dérape.

| Élément | Marketing | Transactionnel |
| --- | --- | --- |
| From | `offres@news.exemple.fr` | `commande@notif.exemple.fr` |
| Return-Path (SPF) | `bounce@bounce.news.exemple.fr` (CNAME vers l'ESP) | `bounce@bounce.notif.exemple.fr` |
| DKIM `d=` | `news.exemple.fr` | `notif.exemple.fr` |
| Liens et tracking | `clic.news.exemple.fr` | `clic.notif.exemple.fr` |
| Images | `img.exemple.fr` | `img.exemple.fr` |
| Reply-To | Une boîte lue, pas un no-reply | Service client |

Un nouveau sous-domaine part d'une réputation « inconnue », même sous un domaine établi : comptez en moyenne 6 semaines de montée en charge (M3AAWG). Préférez `offres.exemple.fr` à un domaine cousin comme `exemple-offres.com`.

### SPF

- **10 lookups maximum.** Les termes `include`, `a`, `mx`, `ptr`, `exists` et `redirect` comptent ; `ip4`, `ip6` et `all` ne comptent pas. Au-delà : `permerror` ([RFC 7208 §4.6.4](https://www.rfc-editor.org/rfc/rfc7208.html)).
- **2 « void lookups » maximum** (include qui ne répond rien). C'est le piège des outils résiliés dont l'include reste dans l'enregistrement.
- **`~all` plutôt que `-all` sur un domaine qui envoie.** C'est la position du M3AAWG, d'[Al Iverson](https://www.spamresource.com/2024/05/ask-al-spf-all-or-all-updated-for-2024.html) et de [Mailhardener](https://www.mailhardener.com/blog/why-mailhardener-recommends-spf-softfail-over-fail). Un `-all` peut faire rejeter le message avant même l'évaluation DMARC ([RFC 9989 §7.1](https://www.rfc-editor.org/rfc/rfc9989.html)). Gardez `v=spf1 -all` pour les domaines qui n'envoient rien.
- **Pas d'aplatissement (flattening) automatique.** Les IP figées vieillissent. Chez Mailhardener, après l'ajout d'une IP par un fournisseur, environ un email sur 20 échouait ([étude de cas](https://www.mailhardener.com/blog/do-not-flatten-spf)). Préférez un sous-domaine par fournisseur.
- **Pas de `ptr`, pas de macro `%{h}`.** Une faille de ce type a permis de contourner DMARC chez un fournisseur en 2023 ([Proofpoint](https://www.proofpoint.com/us/blog/email-and-cloud-threats/proofpoint-discloses-valimail-spf-macro-vulnerability)).

```dns
; Domaine principal (Google Workspace + support)
exemple.fr.                 TXT "v=spf1 include:_spf.google.com include:mail.zendesk.com ~all"
; Return-Path marketing : généralement un CNAME fourni par l'ESP
bounce.news.exemple.fr.     CNAME <cible-fournie-par-l-esp>.
; Domaine qui n'envoie jamais
exemple-parking.fr.         TXT "v=spf1 -all"
```

### DKIM

- **RSA 2048 bits.** Google le recommande, le M3AAWG juge 1024 bits « à la limite de l'attaque » ([rotation BCP](https://www.m3aawg.org/DKIMKeyRotation)). Yahoo accepte encore 1024 bits.
- **`d=` sur votre domaine**, sinon DKIM ne compte pas pour DMARC. Une double signature ESP + client est une bonne pratique : elle alimente les boucles de plaintes basées sur DKIM.
- **Rotation au moins tous les 6 mois**, par exemple en avril et octobre. Ne réutilisez jamais un nom de sélecteur (`nl-202610`) et publiez la clé suivante à l'avance. `p=` vide révoque une clé.
- **Signez les en-têtes de désinscription.** La [RFC 8058](https://www.rfc-editor.org/rfc/rfc8058.html) impose que List-Unsubscribe et List-Unsubscribe-Post figurent dans `h=`. Sur-signez aussi From, To, Subject, Date, Message-ID et Reply-To ([Spam Resource](https://www.spamresource.com/2024/11/tuesday-tip-dkim-oversigning-enable-it.html)).
- **Jamais de tag `l=`.** Il permet d'ajouter du contenu non signé qui passe quand même DKIM, DMARC et BIMI ([CSA](https://certified-senders.org/blog/dkim-body-length-a-serious-weakness-with-the-rise-of-domain-based-reputation/)).
- **Expiration courte contre le rejeu.** Mettez un `x=` de 48 h maximum pour le bulk (CSA) et re-signez lors des retentatives ([Halon](https://halon.io/blog/the-dkim-replay-attack-and-how-to-mitigate)).
- **Ed25519 seulement en seconde signature.** Selon [Red Sift (avril 2026)](https://redsift.com/blog/ed25519-dkim-support-weak-keys), Gmail l'ignore, Microsoft 365 renvoie une erreur de syntaxe et Yahoo un échec permanent. La Poste, GMX, Fastmail et Proton le vérifient.
- **DKIM2 n'est pas pour 2026.** Le brouillon IETF en est à la version 06 du 28 août 2026 ([datatracker](https://datatracker.ietf.org/doc/draft-ietf-dkim-dkim2-bcp/)).

```bash
# Générer une paire de clés RSA 2048 (si vous signez vous-même)
openssl genrsa -out nl-202610.private 2048
openssl rsa -in nl-202610.private -pubout -outform der | openssl base64 -A
```

```dns
; Clé publique (couper en chaînes de 255 caractères max dans l'interface DNS)
nl-202610._domainkey.news.exemple.fr.  TXT "v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA..."
; Délégation à l'ESP (rotation gérée par lui)
esp1._domainkey.news.exemple.fr.       CNAME esp1.news.exemple.fr.dkim.esp.example.
```

```text
DKIM-Signature: v=1; a=rsa-sha256; c=relaxed/relaxed; d=news.exemple.fr; s=nl-202610;
 t=1790400000; x=1790572800;
 h=from:from:to:to:subject:subject:date:date:message-id:message-id:reply-to:reply-to:
   list-unsubscribe:list-unsubscribe-post:mime-version:content-type; bh=...; b=...
```

### DMARC : RFC 9989 depuis mai 2026

DMARCbis est publié en [RFC 9989](https://www.rfc-editor.org/rfc/rfc9989.html) et remplace la RFC 7489. Trois changements vous concernent :

1. `pct` disparaît, remplacé par `t=y` (mode test : le récepteur applique un niveau en dessous de la politique publiée).
2. `np` couvre les sous-domaines inexistants, cible favorite des usurpateurs.
3. La découverte du domaine organisationnel se fait par « DNS tree walk », et non plus par la Public Suffix List.

Les tags `rf` et `ri` disparaissent aussi, et `v=DMARC1` doit rester en premier.

| Étape | Enregistrement `_dmarc` | Durée | Critère pour passer à la suivante |
| --- | --- | --- | --- |
| 0 | SPF et DKIM alignés en place | 48 h avant DMARC ([Google](https://knowledge.workspace.google.com/admin/security/recommended-dmarc-rollout)) | Les en-têtes Authentication-Results montrent `dkim=pass` sur votre `d=` |
| 1 | `v=DMARC1; p=none; rua=mailto:dmarc@exemple.fr` | 2 à 4 semaines | Tous les flux légitimes identifiés dans les rapports (ESP, CRM, facturation, support) |
| 2 | `v=DMARC1; p=quarantine; t=y; rua=...` | 2 semaines | Pas de flux légitime en échec |
| 3 | `v=DMARC1; p=quarantine; rua=...` | 2 à 4 semaines | Conformité > 98 % sur les IP connues |
| 4 | `v=DMARC1; p=reject; sp=reject; np=reject; rua=...` | Cible | Surveillance continue des rapports |

```dns
_dmarc.exemple.fr.   TXT "v=DMARC1; p=reject; sp=reject; np=reject; adkim=r; aspf=r; rua=mailto:dmarc@exemple.fr"
; Si les rapports partent vers un prestataire, celui-ci doit publier une autorisation :
exemple.fr._report._dmarc.prestataire.example.  TXT "v=DMARC1"
```

Ne mettez pas `pct` : il est retiré par la RFC 9989, et BIMI chez Gmail exige `pct=100` ou son absence. Pour lire les rapports, utilisez `dmarc_rua_resume.py` (section 10), [parsedmarc](https://github.com/domainaware/parsedmarc) (déjà compatible RFC 9990) ou le résumé hebdomadaire gratuit de [Postmark DMARC](https://dmarc.postmarkapp.com/).

### Logo de marque : BIMI et Apple Business

| Messagerie | Sans certificat | CMC | VMC |
| --- | --- | --- | --- |
| Gmail | Rien | Logo | Logo + coche bleue |
| Apple Mail (BIMI) | Rien | [Non supporté](https://www.encryptionconsulting.com/bimi-with-vmc-and-cmc/) | Logo |
| Yahoo / AOL | [Logo si DMARC appliqué, volume et réputation suffisants](https://senders.yahooinc.com/bimi/) | Logo | Logo + coche |
| La Poste, Fastmail | [Support BIMI](https://bimigroup.org/bimi-infographic/) | Logo | Logo |
| Microsoft | Pas de BIMI | — | — |

- **Prérequis Gmail** ([Google](https://knowledge.workspace.google.com/admin/security/set-up-bimi)) : DMARC en `quarantine` ou `reject` sans `pct` partiel. Logo SVG `baseProfile="tiny-ps"` version 1.2, carré, fond plein, 32 Ko maximum.
- **VMC ou CMC.** Le VMC exige une marque déposée. Le CMC ([BIMI Group](https://bimigroup.org/announcing-common-mark-certificates/)) exige un logo utilisé publiquement depuis 12 mois, prouvé par archive.org.
- **Prix relevés en décembre 2025** ([DMARCTrust](https://www.dmarctrust.com/blog/cmc-vmc-bimi-new-offering)) : VMC 1 350 à 1 752 $/an, CMC 990 à 1 416 $/an selon l'émetteur.
- **Apple Business** ([Branded Mail](https://support.apple.com/guide/business/intro-to-branded-mail-abcb761b19d2/web)) affiche le logo dans Mail sans certificat. Il faut DKIM (SPF seul ne suffit pas), DMARC conforme, une organisation vérifiée par Apple et un logo approuvé. Jusqu'à 100 domaines, 7 jours ouvrés d'examen. C'est le meilleur rapport coût/effet pour l'iPhone, qui pèse 62 % des ouvertures ([Litmus, juillet 2026](https://www.litmus.com/email-client-market-share)).

```dns
default._bimi.exemple.fr.  TXT "v=BIMI1; l=https://img.exemple.fr/bimi/logo.svg; a=https://img.exemple.fr/bimi/vmc.pem"
```

### MTA-STS, TLS-RPT, ARC

Ces protocoles protègent surtout le courrier entrant et pèsent peu sur la délivrabilité sortante. MTA-STS n'est déployé que sur 0,3 % des domaines ([scan de février 2026](https://dmarcguard.io/blog/mta-sts-vs-dane/)). Gmail le supporte, pas DANE. ARC ne concerne que les services qui transfèrent des emails (listes, redirections). Orange et Yahoo le recommandent, mais un brouillon IETF d'avril 2026 propose de le déclarer historique au profit de DKIM2 ([datatracker](https://datatracker.ietf.org/doc/draft-ietf-dmarc-arc-to-historic/)).

```dns
_mta-sts.exemple.fr.   TXT "v=STSv1; id=20261001T000000Z;"
_smtp._tls.exemple.fr. TXT "v=TLSRPTv1; rua=mailto:tlsrpt@exemple.fr"
; + https://mta-sts.exemple.fr/.well-known/mta-sts.txt :
;   version: STSv1
;   mode: testing        (puis enforce)
;   mx: mx1.exemple.fr
;   max_age: 1296000
```

### Vérifier en 30 secondes

```bash
dig +short TXT exemple.fr | grep spf1
dig +short TXT _dmarc.exemple.fr
dig +short TXT nl-202610._domainkey.news.exemple.fr
dig +short TXT default._bimi.exemple.fr
dig +short -x 203.0.113.10
python3 audit_dns.py news.exemple.fr --selectors nl-202610 --ip 203.0.113.10
```

## 3. Infrastructure d'envoi

Restez sur IP partagée tant que vous envoyez moins de 50 000 emails par mois. Au-delà, une IP dédiée se chauffe sur 3 à 6 semaines, avec un reverse DNS cohérent, un débit adapté à chaque fournisseur et des en-têtes exacts au caractère près.

### IP partagée ou dédiée

| ESP | Seuil pour une IP dédiée |
| --- | --- |
| [SendGrid](https://www.twilio.com/en-us/resource-center/email-guide-ip-warm-up) | Plus de 50 000 emails par mois |
| [Mailgun](https://documentation.mailgun.com/docs/mailgun/email-best-practices/ip_address) | Plus de 50 000 par semaine ; sous 5 000 par jour, le partagé suffit |
| [Postmark](https://postmarkapp.com/guides/dedicated-vs-shared-ips-for-email-when-to-use-each) | Au moins 300 000 par mois |
| [Amazon SES](https://docs.aws.amazon.com/ses/latest/dg/dedicated-ip.html) | Volumes « importants, réguliers et prévisibles », avec au moins quelques centaines d'envois par fournisseur et par mois |

Une IP dédiée envoyée irrégulièrement est pire qu'une IP partagée bien tenue : sa réputation s'efface. SendGrid considère qu'une IP inactive 30 jours doit être réchauffée.

### Warm-up : IP et domaine

&#91;embedded content: Twilio SendGrid, Generic IP Warm Up Schedule · 21 jours\]

Le volume double presque chaque jour la première semaine, puis progresse d'environ 30 % par jour. Les règles qui vont avec :

- **Les plus engagés d'abord.** Les premiers jours partent vers les contacts ayant cliqué dans les 30 derniers jours, puis on élargit.
- **Répartition égale entre fournisseurs.** Ne pas envoyer tout le volume du jour vers Gmail.
- **Plafonds par fournisseur au début.** Le guide [AWS](https://aws.amazon.com/blogs/messaging-and-targeting/guide-to-ip-and-domain-warming-and-migrating-to-amazon-ses/) démarre à 150 envois vers Gmail le jour 1.
- **Pause au premier signal.** Si des 421 ou des plaintes apparaissent, on reste au palier et on attend avant d'augmenter.
- **Le domaine se chauffe aussi.** Comptez 6 semaines en moyenne pour un nouveau domaine ou sous-domaine. Le M3AAWG précise que les pratiques de « chauffe artificielle » (fausses ouvertures, réseaux de boîtes complices) sont déconseillées et peuvent être illégales ([Sender BCP 2026](https://www.m3aawg.org/sites/default/files/doc_files/m3aawg-sender-best-common-practices-aug-27-2026.pdf)).

Protocole complet depuis zéro (tests à 10 emails, rampe adaptative, système d'apprentissage) : Warm-up de zéro et apprentissage

### Reverse DNS, HELO, IPv6

Règles du M3AAWG (août 2026), aujourd'hui exigées par les grands fournisseurs :

- Un seul PTR par IP, qui résout exactement vers la même IP (FCrDNS).
- Un nom de serveur, pas un nom générique : `mta3.news.exemple.fr`, jamais `pool-dhcp-203-0-113-10`.
- HELO/EHLO = ce même nom, résolvable, jamais une IP entre crochets.
- Le domaine du HELO a un MX, des boîtes `postmaster@` et `abuse@` qui fonctionnent, et une page web.
- En IPv6, Gmail exige un PTR IPv6 valide et une authentification ; sinon, erreur `550-5.7.1 ... IPv6 sending guidelines` ([Google](https://support.google.com/a/answer/81126)).

### Débit par fournisseur

Valeurs par défaut de la communauté KumoMTA ([shaping.toml](https://raw.githubusercontent.com/KumoCorp/kumomta/main/assets/policy-extras/shaping.toml)) et limites publiées par [Orange](https://postmaster.orange.fr/index.html) :

| Fournisseur | Connexions simultanées | Messages par connexion | Particularité |
| --- | --- | --- | --- |
| Gmail | 5 (tout le fournisseur) | 50 | TLS exigé |
| Outlook / Office 365 | 5 | 50 | — |
| Yahoo | Non fixé | 20 | Suspendre 2 h sur un différé `[TS04]` |
| Apple iCloud | 10 | 5 | — |
| Orange | **2 par IP** (limite officielle) | 100 | 100 destinataires par message maximum, TLS |
| Par défaut | 10 | 100 | 100 messages/s |

Un `421` signifie « ralentissez » : on espace, on ne renvoie pas plus vite.

### Rebonds

- `4xx` : remettre en file et retenter. Ce n'est jamais un échec définitif : les récepteurs pratiquent le greylisting.
- `5xx` « utilisateur inconnu » : supprimer immédiatement, ne jamais retenter.
- Soft bounces répétés : retirer une adresse qui rebondit au moins deux fois de suite sur deux semaines ou plus (M3AAWG).
- Comptes Gmail supprimés pour inactivité de 2 ans (observé dès avril 2025) : à traiter comme des hard bounces ([Spam Resource](https://www.spamresource.com/2025/04/it-continues-google-moves-forward-with.html)).

### En-têtes : la version exacte

```text
From: Camille de Exemple <camille@news.exemple.fr>
Reply-To: Service client Exemple <bonjour@exemple.fr>
Subject: =?utf-8?b?Vm9zIDMgbm91dmVhdXTDqXMgZCdvY3RvYnJlICgtMjAgJSBqdXNxdSdhdSA1LzEw?=
 =?utf-8?b?KSDwn42C?=
Date: Sat, 26 Sep 2026 13:01:18 +0200
Message-ID: <octobre26.u8f3k2.39ffa57d@news.exemple.fr>
List-Unsubscribe: <https://news.exemple.fr/u/u8f3k2.octobre26.3f9a1c>,
 <mailto:unsub-u8f3k2@news.exemple.fr?subject=unsubscribe>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
Feedback-ID: octobre26:newsletter:fr:exemple
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="b1"
```

- **List-Unsubscribe** porte une URL HTTPS avec un jeton opaque, jamais l'email en clair. Le mailto en complément sert aux clients qui ne gèrent pas le POST.
- **List-Unsubscribe-Post** contient exactement `List-Unsubscribe=One-Click`. Les deux en-têtes doivent être dans le `h=` de DKIM ([RFC 8058](https://www.rfc-editor.org/rfc/rfc8058.html)).
- **Feedback-ID** suit le format `a:b:c:SenderId` : un SenderId stable, pas de valeur unique par message. L'en-tête doit être signé par un domaine vérifié dans Postmaster Tools ([Google](https://support.google.com/a/answer/6254652)). Orange l'exige au-delà de 1 000 envois par jour.
- **Message-ID** unique et valide. Depuis que Microsoft caviarde l'adresse d'expéditeur dans les rapports JMRP (2026), encodez-y l'identifiant de campagne pour relier une plainte à un envoi ([Spam Resource](https://www.spamresource.com/2026/06/snds-and-jmrp-in-transition.html)).

### L'endpoint de désinscription en un clic

La messagerie envoie un `POST` HTTPS sur l'URL de List-Unsubscribe, avec le corps `List-Unsubscribe=One-Click`. L'expéditeur ne doit pas rediriger, ni demander de connexion ou de confirmation. La désinscription doit être effective sous 48 h chez Google et 2 jours chez Yahoo. La page « Gérer les abonnements » de Gmail déclenche ce même POST, parfois en double : selon Chad White, les désinscriptions brutes ont bondi de 200 à 300 % pour une hausse réelle modeste ([Zeta](https://www.zetaglobal.com/resource-center/gmail-manage-subscriptions-tool/)). Dédupliquez avant de conclure.

```python
@app.post("/u/<token>")
def one_click(token):
    ids = verify(token)                      # jeton HMAC : contact + campagne
    if ids is None:
        abort(404)
    if request.form.get("List-Unsubscribe") != "One-Click":
        abort(400)
    unsubscribe(*ids, source="one-click")    # idempotent : un doublon ne change rien
    return "", 200                           # jamais de redirection
```

Le GET sur la même URL, quand un humain clique, affiche une page avec l'alternative « recevoir moins d'emails » (code complet : `desinscription_one_click.py`).

## 4. Monitoring et analyse

Google retire ses tableaux de réputation et le taux d'ouverture est faussé par Apple. Trois indicateurs restent fiables : le taux de spam Gmail, les clics par fournisseur de messagerie et le taux de conformité DMARC. Surveillez-les chaque jour d'envoi.

### Les outils des fournisseurs

| Outil | Ce qu'il donne en 2026 | Condition d'accès |
| --- | --- | --- |
| [Google Postmaster Tools v2](https://support.google.com/a/answer/14668346?hl=en) | Compliance Status et son diagnostic « Deliverability analysis », taux de spam, boucle de plaintes (via Feedback-ID), authentification, chiffrement, erreurs de livraison. Les tableaux de réputation IP et domaine sont [annoncés en retrait](https://support.google.com/a/answer/16594218?hl=en) | Domaine vérifié par DNS, volume suffisant vers Gmail |
| [Yahoo Sender Hub](https://senders.yahooinc.com/complaint-feedback-loop/) | Boucle de plaintes (ARF) et, depuis octobre 2025, Insights : taux de plainte et volume par domaine DKIM, sous 24 à 48 h | Messages signés DKIM, domaine vérifié |
| [Microsoft SNDS](https://www.spamresource.com/2026/06/snds-and-jmrp-in-transition.html) + JMRP | Données par IP, plaintes au format ARF. Depuis 2026, adresse caviardée, corps supprimé, liens valables 30 jours | IP dédiée ; SNDS relancé en juin 2026 sur substrate.office.com |
| [Signal Spam](https://www.signal-spam.fr/feedback-loop/) | Plaintes des abonnés Orange, SFR, La Poste, traitées comme désinscriptions | Déclaration de conformité validée |
| [La Poste](https://postmaster.laposte.net/) | Boucle de plaintes par IP | Inscription via Validity |
| Apple iCloud | Aucune boucle de plaintes ([Apple](https://support.apple.com/en-us/102322)) | — |

Un détail change la lecture du taux de spam Gmail : il ne compte que les messages signés DKIM, arrivés en boîte de réception de destinataires engagés, puis signalés. Envoyer à des inactifs ne « dilue » donc pas ce taux.

### Seuils d'alerte

| Indicateur | Cible | Alerte | Source |
| --- | --- | --- | --- |
| Taux de spam Gmail (Postmaster) | < 0,10 % | ≥ 0,10 % ; crise à 0,30 % | [Google](https://support.google.com/a/answer/81126?hl=en) |
| Taux de plainte Yahoo | < 0,3 % | 0,3 % | [Yahoo](https://senders.yahooinc.com/best-practices/) |
| Taux de plainte Orange | < 0,3 % | 0,3 % à 0,6 % selon l'étape | [Orange](https://postmaster.orange.fr/index.html) |
| Conformité DMARC (rapports rua) | > 98 % des volumes légitimes | Toute IP légitime sous 90 % | Recommandation de ce guide |
| Hard bounces par campagne | Proche de 0,2 % (moyenne Brevo France) | > 1 % : problème de collecte ou d'import | [Brevo, données 2024](https://email-rocks.com/chiffres-email-marketing-2025-brevo/) ; seuil : recommandation |
| Clics par fournisseur | Stable d'une campagne à l'autre | Baisse de 30 % sur un seul fournisseur | Recommandation de ce guide |

### Repères de performance

| Étude | Périmètre | Ouverture | Clic | Désinscription |
| --- | --- | --- | --- | --- |
| [Brevo 2025](https://email-rocks.com/chiffres-email-marketing-2025-brevo/) | 11,9 milliards d'emails, entreprises françaises, 2024 | 33,9 % | 4,32 % | 0,41 % |
| [MailerLite](https://www.mailerlite.com/blog/compare-your-email-performance-metrics-industry-benchmarks) | Europe, déc. 2024 – nov. 2025 | 45,08 % | 2,04 % | 0,23 % |
| [Klaviyo](https://www.klaviyo.com/uk/blog/email-marketing-benchmarks-open-click-and-conversion-rates) | Campagnes e-commerce, 205 000 marques, fév. 2026 | 31 % | 1,69 % | — |

Les taux d'ouverture sont gonflés par Apple Mail Privacy Protection, qui touche 55 à 60 % des ouvertures ([Litmus, juillet 2026](https://www.litmus.com/email-client-market-share)). Brevo inclut ces ouvertures machine par défaut depuis le 6 février 2025 ([EmailTooltester](https://www.emailtooltester.com/en/blog/apple-mpp-open-rate/)). Pilotez aux clics et aux conversions.

Placement en boîte de réception pour les audiences françaises, mesuré par comptes témoins en 2024 ([Validity 2025](https://www.validity.com/wp-content/uploads/2025/03/2025-Benchmark-Report-FINAL.pdf)) :

| Fournisseur | Part de l'audience FR | En boîte de réception |
| --- | --- | --- |
| Gmail | 37,7 % | 94,1 % |
| Orange | 9,2 % | 93,3 % |
| Yahoo | 5,9 % | 90,9 % |
| Microsoft | 18,3 % | 90,2 % |
| Apple | 2,4 % | 86,7 % |

La France atteint 91,4 %, contre 83,5 % en moyenne mondiale. Microsoft reste le plus difficile au niveau mondial (75,6 % en boîte, 14,6 % en spam). Beaucoup de fournisseurs français filtrent avec la technologie Vade.

### Diagnostiquer

| Symptôme | Cause probable | Action |
| --- | --- | --- |
| Clics stables partout sauf chez un fournisseur | Placement en spam chez ce fournisseur | Limiter ce fournisseur aux actifs 30 jours pendant 2 semaines, lire ses codes de refus |
| `421 4.7.28` chez Gmail | Pic de volume ou taux de spam en hausse | Baisser le volume, n'envoyer qu'aux actifs, reprendre par paliers |
| Taux de spam Postmaster > 0,1 % | Une campagne ou une source d'inscription | Isoler via le Feedback-ID, couper le segment ou la source |
| Conformité DMARC < 98 % | Un outil qui signe avec son propre domaine | `dmarc_rua_resume.py` : IP à 0 % d'alignement DKIM = domaine d'authentification personnalisé manquant |
| Hausse des hard bounces | Import, faute de frappe, formulaire sans vérification | Double saisie ou validation en temps réel, bloquer la source |
| Plaintes en hausse après une réactivation | Adresses dormantes | Arrêter la séquence, repasser ces contacts en sunset |

### Tests de placement

Les outils à comptes témoins (GlockApps, Validity Everest, Inbox Monster) et les testeurs rapides (mail-tester.com) servent à valider un nouveau template, un nouveau domaine ou une nouvelle IP. Leurs comptes n'ont aucun historique d'engagement : le résultat n'est qu'une tendance, pas le placement réel de vos abonnés actifs.

### Routine

- **Chaque envoi** : erreurs de livraison par fournisseur, clics par fournisseur, `lint_email.py` sur le BAT réel.
- **Chaque semaine** : taux de spam Postmaster Tools et Yahoo Insights, synthèse DMARC, plaintes Signal Spam.
- **Chaque mois** : segmentation d'engagement (section 9), `audit_dns.py`, vérification des listes noires (Spamhaus, Abusix).
- **Tous les 6 mois** : rotation des clés DKIM.

## 5. Code HTML de l'email

Le HTML qui délivre et s'affiche bien en 2026 tient en six règles :

1. Doctype HTML5.
2. UTF-8 en quoted-printable.
3. Une version texte fidèle au HTML.
4. Moins de 80 Ko de HTML.
5. Des styles critiques en inline, car La Poste et SFR neutralisent `<style>` depuis 2025.
6. Du vrai texte plutôt que des images. Le VML reste utile pour Outlook classique.

### Doctype et `<head>`

Le consensus est `<!DOCTYPE html>`. Rémi Parmentier le résume ainsi : le plus court, et suffisant pour déclencher le mode standard ([hteumeuleu](https://www.hteumeuleu.com/2016/which-doctype-should-you-use-in-html-emails/)). Gmail, Yahoo, Outlook.com et Orange appliquent de toute façon un doctype HTML5, et Outlook classique ignore le doctype ([Email on Acid](https://www.emailonacid.com/blog/article/email-development/doctype-the-black-sheep-of-html-email-design/)). Le XHTML 1.0 Transitional n'ajoute que des octets. En HTML5, les images laissent un espace dessous : ajoutez `display:block`.

```html
<!DOCTYPE html>
<html lang="fr" dir="ltr" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=yes">
  <meta name="x-apple-disable-message-reformatting">
  <meta name="format-detection" content="telephone=no, date=no, address=no, email=no, url=no">
  <meta name="color-scheme" content="light dark">
  <meta name="supported-color-schemes" content="light dark">
  <title>Même texte que l'objet</title>
  <!--[if mso]><noscript><xml><o:OfficeDocumentSettings>
    <o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->
  <style>:root{color-scheme:light dark;supported-color-schemes:light dark;}</style>
</head>
<body class="body" xml:lang="fr">
  <div role="article" aria-roledescription="email" aria-label="Vos 3 nouveautés d'octobre" lang="fr" dir="ltr">
    <!-- préheader, puis contenu en styles inline -->
  </div>
</body>
</html>
```

Source : le template de [goodemailcode.com](https://www.goodemailcode.com/email-code/template) (Mark Robbins). Trois détails comptent :

- **`lang` sur le conteneur**, pas seulement sur `<html>`, car les webmails suppriment `<html>`.
- **`aria-label` plutôt qu'`aria-labelledby`**, car les clients préfixent les `id`.
- **Pas de `<header>`, `<footer>` ni `<main>`** : ils entrent en conflit avec les repères de la page du webmail ([goodemailcode](https://www.goodemailcode.com/email-accessibility/aria-landmarks-in-html-email)).

Piège Gmail : une règle `@` imbriquée dans un `@media` fait supprimer tout le bloc `<style>` ([email-bugs #21](https://github.com/hteumeuleu/email-bugs/issues/21)).

### Encodage, MIME, longueur de ligne

| Point | Règle | Pourquoi |
| --- | --- | --- |
| Charset | UTF-8 partout (meta, en-têtes MIME) | Évite les caractères cassés et les règles de filtrage liées aux jeux de caractères exotiques |
| Content-Transfer-Encoding | `quoted-printable` | Le base64 sans charset UTF-8 déclenche `MIME_BASE64_TEXT` (jusqu'à 1,7 point SpamAssassin) ; avec UTF-8, il est accepté ([MIMEEval.pm](https://raw.githubusercontent.com/apache/spamassassin/trunk/lib/Mail/SpamAssassin/Plugin/MIMEEval.pm)) |
| Longueur de ligne | 998 caractères maximum, 78 recommandés ([RFC 5322 §2.1.1](https://datatracker.ietf.org/doc/html/rfc5322#section-2.1.1)) | Les minifieurs (MJML 5 inclus) mettent tout sur une ligne, d'où des rejets `550 Maximum line length exceeded`. Le quoted-printable coupe à 76 caractères et règle le problème |
| Version texte | multipart/alternative, générée depuis le HTML | L'absence de texte ne coûte que 0,1 point (`MIME_HTML_ONLY`), mais une version texte différente du HTML coûte jusqu'à 2,8 points (`MPART_ALT_DIFF_COUNT`, [50\_scores.cf](https://raw.githubusercontent.com/apache/spamassassin/trunk/rules/50_scores.cf)) |
| 8bit | À éviter | Exige l'extension 8BITMIME du serveur d'en face ([RFC 6152](https://datatracker.ietf.org/doc/html/rfc6152)) |
| Contenu caché | Le préheader, et rien d'autre | Google : ne pas utiliser HTML et CSS pour cacher du contenu ([consignes](https://support.google.com/a/answer/81126)) |

`generer_eml.py` (section 10) produit exactement cette structure. `lint_email.py` vérifie les lignes trop longues, l'encodage et l'écart texte/HTML.

### Poids et clipping Gmail

Gmail coupe le message vers **102 Ko de HTML** et affiche « \[Message tronqué\] ». Seule la partie HTML compte, pas les en-têtes ni la version texte, et le poids des images n'entre pas en jeu. Le seuil monte vers 110 Ko en base64 ([Spam Resource](https://www.spamresource.com/2022/01/what-is-gmail-clipping-and-what-to-do.html)). Google ne documente pas ce seuil, et des coupures ont été observées dès 99 Ko ([email-bugs #41](https://github.com/hteumeuleu/email-bugs/issues/41)).

Gardez une marge : **80 Ko maximum** avant l'ajout du tracking par l'ESP ([Email on Acid](https://www.emailonacid.com/blog/article/email-development/gmail-email-clipping/)). Si le lien de désinscription tombe dans la partie coupée, les plaintes augmentent. Pour réduire le poids :

- minifier sans tout mettre sur une ligne ;
- supprimer les commentaires et les tableaux imbriqués inutiles ;
- raccourcir les URL de tracking ;
- mesurer le HTML réellement envoyé, pas celui de l'éditeur.

CSS dans Gmail ([doc Google](https://developers.google.com/workspace/gmail/design/css), [caniemail](https://raw.githubusercontent.com/hteumeuleu/caniemail/main/_features/html-style.md)) :

- `<style>` est supporté dans `<head>`, pas dans `<body>`.
- La limite est d'environ 16 Ko de `<style>` selon les tests de Rémi Parmentier.
- Seul le sélecteur d'attribut `[class~=valeur]` fonctionne.
- `<style>` disparaît quand le message est transféré.
- Les applications Gmail utilisées avec un compte non Google (GANGA) ne lisent aucun `<style>`.

### Alerte France : La Poste et SFR neutralisent `<style>`

Depuis l'été 2025, les webmails de La Poste et de SFR commentent le `<style>` du `<head>`, en réponse à la technique de phishing « Kobold letters ». Media queries, `@font-face`, `:hover` et `prefers-color-scheme` disparaissent. SFR est passé de 226 à 196 fonctionnalités supportées, La Poste de 205 à 176 ([caniemail, août 2025](https://raw.githubusercontent.com/hteumeuleu/caniemail/main/_posts/2025-08-01-july-updates.md), [email-bugs #161](https://github.com/hteumeuleu/email-bugs/issues/161)). Web.de a fait de même en avril 2025.

La seule réponse : tous les styles critiques en inline (couleurs, tailles, largeurs, espacements), une mise en page « hybride » qui tient sans media query, et `<style>` réservé aux améliorations. `lint_email.py` signale un email qui dépend trop des classes.

### Outlook

- **Outlook classique reste supporté jusqu'en 2029 au moins** ([Microsoft Learn](https://learn.microsoft.com/en-us/microsoft-365-apps/outlook/get-started/guide-product-availability)). La bascule par défaut vers le nouvel Outlook est repoussée à mars 2027 pour les entreprises, et aucune date de fin n'est annoncée ([Born City](https://borncity.com/win/2026/02/23/outlook-new-microsoft-extends-opt-out-period-for-companies-until-2027/)).
- **Le nouvel Outlook pour Windows** utilise le moteur web d'Outlook.com. Outlook classique et l'application Microsoft 365 gardent le moteur de Word ([Litmus](https://www.litmus.com/blog/a-guide-to-rendering-differences-in-microsoft-outlook-clients)).
- **On garde donc** les tableaux fantômes dans `[if mso]`, le VML pour les boutons et fonds, et `PixelsPerInch 96`.
- **Poids d'Outlook** : 5,83 % des ouvertures tous clients confondus ([Litmus, juillet 2026](https://www.litmus.com/email-client-market-share)), beaucoup plus en B2B.

```html
<!-- Bouton "bulletproof" : VML pour Outlook classique, HTML pour les autres -->
<!--[if mso]>
<v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word"
  href="https://www.exemple.fr/nouveautes" style="height:48px;v-text-anchor:middle;width:260px;"
  arcsize="12%" stroke="f" fillcolor="#1a56db">
  <w:anchorlock/>
  <center style="color:#ffffff;font-family:Arial,sans-serif;font-size:16px;font-weight:bold;">Voir les 3 nouveautés</center>
</v:roundrect>
<![endif]-->
<!--[if !mso]><!-->
<a href="https://www.exemple.fr/nouveautes" style="display:inline-block;padding:14px 28px;background:#1a56db;
   color:#ffffff;font:bold 16px Arial,sans-serif;text-decoration:none;border-radius:6px;">Voir les 3 nouveautés</a>
<!--<![endif]-->
```

### Images et ratio texte/image

La règle des « 60/40 » est un mythe. Dans le test d'[Email on Acid](https://www.emailonacid.com/blog/article/email-deliverability/does-text-to-image-ratio-affect-deliverability/), au-delà de 500 caractères de texte, le ratio n'avait aucun effet sur 23 filtres. Dans SpamAssassin actuel, les règles de ratio `HTML_IMAGE_RATIO_*` sont neutralisées (0,001 point). En revanche, `HTML_IMAGE_ONLY_*` (images avec 0 à 3 200 octets de texte) pèse jusqu'à environ 2,8 points, et `HTML_SHORT_LINK_IMG_1` jusqu'à 2,2 points ([50\_scores.cf](https://raw.githubusercontent.com/apache/spamassassin/trunk/rules/50_scores.cf)).

Le vrai risque est donc l'email tout-image avec peu de texte. Il est aussi illisible pour les IA de résumé (section 8).

- Au moins 500 caractères de texte HTML réel, et le prix, la date, le code et le CTA en texte.
- `width` en attribut + `style="width:100%;max-width:600px;height:auto"`, images exportées en 2x, `display:block`.
- `alt` descriptif sur chaque image de contenu, `alt=""` sur les images décoratives.
- Pas de WebP : Outlook classique ne l'affiche pas et Gmail le convertit en JPG ([caniemail](https://raw.githubusercontent.com/hteumeuleu/caniemail/main/_features/image-webp.md)). Outlook classique n'affiche que la première image d'un GIF animé : mettez le message dans celle-ci.
- Images hébergées sur votre propre sous-domaine (`img.exemple.fr`), en HTTPS.

### Préheader

Technique à jour depuis 2023 ([Litmus](https://www.litmus.com/blog/the-little-known-preview-text-hack-you-may-want-to-use-in-every-email), [goodemailcode](https://www.goodemailcode.com/email-code/preheader)). Le caractère `&#847;` seul ne fonctionne plus dans Yahoo, AOL et Apple Mail 16.4 : il faut le mélange ci-dessous. Placez-le juste après `<body>`.

```html
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">
  Le récap en 10 secondes : 3 nouveautés, -20 % jusqu'au lundi 5 octobre.
</div>
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">
  &#847; &zwnj; &nbsp; &#8199; &shy; &#847; &zwnj; &nbsp; &#8199; &shy; &#847; &zwnj; &nbsp; &#8199; &shy;
  <!-- répéter une vingtaine de fois -->
</div>
```

Les espaceurs remplissent la zone d'aperçu pour que « Voir la version en ligne » ou le menu n'y apparaissent pas.

### Dark mode

| Comportement | Clients ([Litmus, fév. 2025](https://www.litmus.com/blog/the-ultimate-guide-to-dark-mode-for-email-marketers)) |
| --- | --- |
| Aucun changement | Apple Mail, Gmail webmail, Yahoo, AOL |
| Inversion partielle | Outlook.com, applications Outlook |
| Inversion complète | Gmail iOS, Outlook 2021 et Office 365 sous Windows |

`prefers-color-scheme` marche dans Apple Mail, Outlook.com, les applications Outlook et Orange. Il ne marche pas dans Gmail, ni chez SFR et La Poste depuis juillet 2025 ([caniemail](https://raw.githubusercontent.com/hteumeuleu/caniemail/main/_features/css-at-media-prefers-color-scheme.md)). Les applications Gmail n'acceptent que `color-scheme: light only` (testé en septembre 2026).

```css
@media (prefers-color-scheme: dark) {
  .bg:not([class^="x_"]) { background:#1c2128 !important; }  /* Apple Mail, Outlook apps */
}
[data-ogsb] .bg { background:#1c2128 !important; }             /* Outlook.com en mode sombre */
/* Gmail, inversion forcée : texte blanc conservé (hors GANGA) */
u + .body .gmail-blend-screen { background:#000; mix-blend-mode:screen; }
u + .body .gmail-blend-difference { background:#000; mix-blend-mode:difference; }
```

Sources : [Outlook.com](https://www.hteumeuleu.com/2021/emails-react-outlook-com-dark-mode/) et [blend modes Gmail](https://www.hteumeuleu.com/2021/fixing-gmail-dark-mode-css-blend-modes/). Pour les logos, utilisez un PNG transparent avec un léger contour clair, lisible sur les deux fonds.

### Accessibilité

L'Acte européen sur l'accessibilité s'applique depuis le 28 juin 2025. Il vise notamment l'e-commerce, la banque et le transport, et exempte les micro-entreprises (moins de 10 salariés et 2 M€ de CA). Les textes ne mentionnent pas l'email ([Temesis](https://www.temesis.com/blog/synthese-des-nouvelles-reglementations-encadrant-laccessibilite-numerique-en-france/), [Badsender](https://www.badsender.com/en/guides/accessibility-and-email-2/)). Les emails transactionnels d'un service couvert sont les plus exposés ; c'est une interprétation, pas un texte. De toute façon, un email accessible est aussi un email lisible par les IA :

- `lang` sur `<html>` et sur le conteneur, `role="presentation"` sur les tableaux de mise en page ;
- une vraie hiérarchie `<h1>` à `<h3>` ;
- `alt` partout, contraste d'au moins 4,5:1 ;
- texte de 14 à 16 px minimum, interligne 1,5, texte aligné à gauche ;
- liens explicites (jamais « cliquez ici »), zones cliquables de 44 × 44 px minimum ;
- aucun texte dans les images ([Litmus](https://www.litmus.com/blog/ultimate-guide-accessible-emails)).

### AMP et email interactif

AMP pour l'email fonctionne encore dans Gmail (sur inscription), Yahoo et Mail.ru ([Google](https://developers.google.com/workspace/gmail/ampemail)). Mais la spécification n'a reçu que des corrections de coquilles depuis 2023, et Outlook.com a abandonné son aperçu ([Buttondown](https://buttondown.com/blog/whatever-happened-to-amp-email)). C'est une niche qui impose trois versions à maintenir. L'interactivité en CSS (`:checked`) est affaiblie par le nouvel Outlook Mac et par la perte de `<style>` chez La Poste et SFR.

### Frameworks et références

| Projet | Version au 26/09/2026 | Étoiles GitHub | À retenir |
| --- | --- | --- | --- |
| [MJML](https://github.com/mjmlio/mjml) | 5.4.1 | 18 248 | v5 : minification htmlnano, `mj-include` désactivé par défaut, Node 20+ |
| [React Email](https://github.com/resend/react-email) | 6.11.0 | 19 776 | v6 : un seul paquet `react-email`, émulateur dark mode, Tailwind 4 |
| [Maizzle](https://maizzle.com/docs/upgrade-guide) | 6.1.7 | 1 614 | v6 : composants Vue, Tailwind 4, Vite |
| [jsx-email](https://github.com/shellscape/jsx-email) | 3.2.1 | 1 261 | Alternative à React Email |
| [Cerberus](https://github.com/emailmonday/Cerberus) | — | 5 137 | Templates « hybrid » de référence |
| [caniemail](https://github.com/hteumeuleu/caniemail) | — | 945 | Plus de 300 fonctionnalités testées sur 41 clients, dont Orange, SFR et La Poste |
| [email-bugs](https://github.com/hteumeuleu/email-bugs/issues) | — | 576 | Les bugs de rendu en cours, classés par client |

Le fichier `template_reference.html` (section 10) applique tout ce qui précède : doctype, head, préheader, conteneur accessible, styles inline, bouton en texte, JSON-LD Promotions, dark mode progressif.

## 6. Objet, préheader, expéditeur et emojis

Les règles, en bref :

- **Objet** : l'essentiel dans les 33 premiers caractères, la seule longueur affichée en entier partout, et 50 caractères au total.
- **Emoji** : un seul, daté d'Emoji 12.0 ou avant, plutôt en fin d'objet, jamais dans le nom d'expéditeur.
- **Préheader** : moins de 90 caractères. Sur iPhone, un résumé IA le remplace : la première phrase du corps compte désormais autant que lui.

### Ce qui s'affiche vraiment

Mesures d'[EmailTooltester](https://www.emailtooltester.com/en/blog/email-subject-lines-character-limit/) (tests d'août 2026) :

| Client | Objet visible | Préheader visible |
| --- | --- | --- |
| Gmail app, Android (Pixel 7) | 33 car. | 37 car. |
| Gmail app, Android (Galaxy S22 Ultra) | 36 car. | 40 car. |
| Gmail app, iPhone 14 | 37 car. | 39 car. |
| Apple Mail, iPad | 39 car. | 75 car. |
| Apple Mail, iPhone 14 / SE | 48 car. | 99 car. |
| Outlook web (1 400 px) | \~51 car. | Selon l'objet |
| Gmail web (1 400 px) | \~88 car. | Selon l'objet |

Ce que disent les données de performance (des corrélations, pas des lois) :

- **[MailerLite](https://www.mailerlite.com/blog/compare-your-email-performance-metrics-industry-benchmarks)** (3,6 millions de campagnes, déc. 2024 – nov. 2025) : les campagnes les plus ouvertes ont 45 % de chances en plus d'avoir un objet de 20 à 40 caractères, 23 % d'avoir un préheader personnalisé, 21 % d'avoir un emoji.
- **[Klaviyo](https://www.klaviyo.com/blog/subject-lines-best-practices)** (mai 2025) : objets de moins de 5 mots, environ 30 à 40 % d'ouverture médiane ; de 5 à 10 mots, moins de 30 %.
- **Jay Schwedelson** ([oct. 2025](https://unbound.hubspot.com/blog/jay-schwedelsons-no-bs-guide-to-whats-working-in-email-marketing-right-now)) : un objet de 3 mots avec préheader vide a donné +25 % d'ouvertures. Aucune taille d'échantillon publiée.

### Le préheader face aux résumés IA

- **Apple Mail.** Avec Apple Intelligence, un résumé remplace l'aperçu dans la liste des messages. La fonction est disponible en français depuis iOS 18.4 (31 mars 2025), activée par défaut, sur iPhone 15 Pro et suivants ([Apple](https://www.apple.com/newsroom/2025/03/apple-intelligence-features-expand-to-new-languages-and-regions-today/), [Knak](https://knak.com/blog/apple-intelligence-ios18-2/)). Ni le préheader, ni l'alt, ni le balisage n'influencent ce résumé. Seuls comptent le nom d'expéditeur, l'objet et le texte visible.
- **Gmail.** Les résumés Gemini s'affichent dans l'email ouvert, pas dans la liste. L'extraction automatique d'offres peut remplacer l'aperçu par un encart promo, avec parfois une mauvaise remise ou une mauvaise date ([Chad White, CMSWire](https://www.cmswire.com/digital-marketing/weve-lost-preview-text-for-email-are-subject-lines-next/)). Le balisage JSON-LD de la section 8 fiabilise cet encart.
- **Outlook.** La fonction Copilot « Prioritize » remplace la première ligne par un résumé ([Microsoft](https://support.microsoft.com/en-us/outlook/copilot-outlook/prioritize-my-inbox)).
- **Le risque.** Selon [Validity](https://www.validity.com/wp-content/uploads/2025/03/2025-Benchmark-Report-FINAL.pdf), les résumés inexacts font baisser l'engagement et augmenter les plaintes.

En pratique, écrivez deux préheaders. Le premier est le préheader caché : moins de 90 caractères ([Litmus](https://www.litmus.com/blog/the-ultimate-guide-to-preview-text-support)), il complète l'objet sans le répéter. Le second est la première phrase visible du corps : elle dit l'offre, la date et l'action, parce que c'est elle que l'IA résume.

### Emojis : ce que disent les données

| Étude | Résultat |
| --- | --- |
| [Search Engine Journal](https://www.searchenginejournal.com/emojis-in-subject-lines/378280/), tests A/B sur 3,9 millions d'emails (2020) | Ouvertures : la version sans emoji gagne 53 % des tests. Clics : la version avec emoji gagne 65 % des tests. Plus de désinscriptions et de plaintes avec emoji (7 campagnes sur 10) |
| [Nielsen Norman Group](https://www.nngroup.com/articles/emojis-email/) (2020) | L'emoji attire l'œil (33 % contre 9 %) mais n'augmente pas l'intention d'ouvrir, et génère 26 % de sentiment négatif en plus |
| [MailerLite](https://www.mailerlite.com/blog/compare-your-email-performance-metrics-industry-benchmarks) (2025) | Les campagnes les plus ouvertes ont 21 % de chances en plus d'avoir un emoji |
| [Schwedelson](https://unbound.hubspot.com/blog/jay-schwedelsons-no-bs-guide-to-whats-working-in-email-marketing-right-now) (2025) | Les emojis « négatifs » (💔 😢 ⚠️) : +17 % d'ouvertures en moyenne |
| Le fameux « +73 % » | Faux : c'est 73 % de marketeurs sondés qui *pensent* que les emojis aident ([Omnisend](https://www.omnisend.com/blog/email-marketing-statistics/)) |

Côté délivrabilité, aucune règle SpamAssassin ne vise les emojis de l'objet ([20\_head\_tests.cf](https://svn.apache.org/repos/asf/spamassassin/trunk/rules/20_head_tests.cf)). Validity mesurait déjà en 2017 un effet limité sur le placement ([Marketing Dive](https://www.marketingdive.com/news/study-certain-emojis-in-email-subject-lines-boost-read-rates/443439/)). Le risque passe par les plaintes. Testez donc sur votre base en mesurant les clics et les plaintes, jamais les ouvertures.

### Emojis qui s'affichent partout

- **Rendu.** Gmail affiche ses propres emojis, en images, sur tous les systèmes ([Litmus](https://www.litmus.com/blog/emoji-support-in-email-can-your-subscribers-see-them)). Outlook pour Windows les affiche souvent en noir et blanc. Un emoji non supporté devient un carré « ☐ » ([Klaviyo](https://help.klaviyo.com/hc/en-us/articles/115005257048)).
- **La limite est Windows 10.** Il s'arrête à Emoji 12.0 (2019) et reste très utilisé malgré sa fin de support en octobre 2025 ([Emojipedia](https://emojipedia.org/microsoft)). Windows 11 23H2 va jusqu'à Emoji 15.1. Emoji 16.0 (2024) et 17.0 (2025) arrivent sur les appareils en 2026 ([Emojipedia](https://emojipedia.org/emoji-17.0)).
- **Règle.** Emojis de version 12.0 ou antérieure uniquement. Pas de séquence ZWJ (👩‍💻), pas de teinte de peau. Ajoutez le sélecteur U+FE0F aux symboles à présentation texte par défaut (❤️ ☀️ ✈️ 🛍️ 🏷️), sinon ils s'affichent en noir et blanc.

Vérifié avec la librairie `emoji` 2.16 (version Emoji entre parenthèses) :

| Statut | Emojis |
| --- | --- |
| Sûrs (0.6 à 5) | 🔥 ✨ 🎁 🚀 🎉 (le top 5 d'usage selon [Moosend](https://moosend.com/blog/emojis-in-subject-lines-survey/)), 🍂 🎄 ⏰ 📦 ✅ 💡 📅 ⚡ 🎯 👉 💌 📣 🌿 (0.6) ; 🛒 🥂 (3) ; 🤩 🧡 (5) |
| Sûrs avec U+FE0F | ❤️ ☀️ ✈️ ⚠️ (0.6) ; 🛍️ 🏷️ (0.7) |
| Limite (11 et 12) | 🥳 (11) : passé sur les systèmes de 2018 et plus |
| À éviter | 🫶 🥹 🫠 (14), 🩷 🪿 🫨 (15), 🙂‍↔️ 🍋‍🟩 (15.1), 🫩 🫆 (16), 👩‍💻 (séquence ZWJ), 👍🏽 (teinte) |

**Jamais d'emoji dans le nom d'expéditeur.** Les consignes Gmail interdisent les emojis qui imitent des éléments graphiques ([Google](https://support.google.com/mail/answer/81126?hl=en)). Al Iverson rapporte un blocage intermittent chez Gmail dû à une coche emoji dans le nom ([Spam Resource, juin 2025](https://www.spamresource.com/2025/06/gmail-says-no-funny-or-smiley-business.html)).

### Encodage de l'objet

Un objet avec accents ou emoji doit être encodé en « encoded-words » [RFC 2047](https://www.rfc-editor.org/rfc/rfc2047) : `=?utf-8?B?...?=` (base64) ou `=?utf-8?Q?...?=` (quoted-printable).

- Un encoded-word fait 75 caractères maximum.
- Un caractère multi-octets ne doit jamais être coupé entre deux encoded-words.
- L'UTF-8 brut dans l'en-tête exige SMTPUTF8 de bout en bout ([RFC 6532](https://www.rfc-editor.org/rfc/rfc6532)).

Coût d'une erreur dans SpamAssassin 4.0 ([50\_scores.cf](https://svn.apache.org/repos/asf/spamassassin/tags/spamassassin_current_release_4.0.x/rules/50_scores.cf)) : `SUBJECT_NEEDS_ENCODING` jusqu'à 0,8 point, `SUBJ_ILLEGAL_CHARS` jusqu'à 1,5 point. Ne construisez jamais l'en-tête à la main : laissez la librairie encoder.

```python
from email.message import EmailMessage
msg = EmailMessage()
msg["Subject"] = "Vos 3 nouveautés d'octobre (-20 % jusqu'au 5/10) 🍂"   # encodage RFC 2047 automatique
msg["From"] = "Camille de Exemple <camille@news.exemple.fr>"
print(msg.as_string().splitlines()[0:3])
# Subject: Vos 3 =?utf-8?q?nouveaut=C3=A9s_d=27octobre_=28-20_=25_jusqu=27au_5?=
#  =?utf-8?b?LzEwKSDwn42C?=
```

### Mots « spam », majuscules, faux RE:

- **Les listes de mots interdits sont un mythe.** Al Iverson : les filtres jugent le consentement, pas le contenu ([Spam Resource, 2024](https://www.spamresource.com/2024/09/tiny-tip-tuesday-285-spam-trigger-words.html)). Laura Atkins a montré un email avec deux « FREE » en capitales et quatre « ! » noté −7,2 dans SpamAssassin ([Word to the Wise](https://www.wordtothewise.com/2016/06/can-we-put-the-free-myth-to-bed/)).
- **Les filtres sont statistiques.** Les fournisseurs déploient des modèles de langage entraînés sur le spam et le phishing, et le placement en spam mondial est passé de 4,5 % à 8,6 % au fil de 2024 (Validity 2025). Ce qui fait plonger un email, c'est le vocabulaire de l'arnaque combiné à une réputation faible, pas un mot isolé.
- **Les majuscules pèsent peu pour les filtres** (`SUBJ_ALL_CAPS` = 0,5 point) mais beaucoup pour les humains.
- **Les faux « RE: » et « TR: » sont interdits.** Gmail les proscrit hors vraies réponses. En France, l'article [L34-5 du CPCE](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000042155961/) interdit un objet sans rapport avec le service proposé.

### Ce qui marche, avec les données disponibles

- **Le nom d'expéditeur d'abord.** 94,5 % des consommateurs disent que reconnaître l'expéditeur compte ([Mailjet, 2024](https://www.mailjet.com/blog/email-best-practices/get-more-email-opens/)). Un test MailerLite donne +3,81 % d'ouvertures avec un nom de personne. La meilleure formule : « Prénom de Marque », stable dans le temps.
- **Le prénom seul ne suffit pas.** Klaviyo note qu'il « ne fait pas grand-chose » seul ; la personnalisation par le comportement (produit vu, catégorie achetée) pèse plus.
- **Chiffres et questions.** Selon Schwedelson, commencer par un chiffre ou poser une question donne environ +20 % d'ouvertures ([LinkedIn](https://www.linkedin.com/posts/schwedelson_20-increased-open-rares-3-email-subject-activity-7317943460005642245-Q7bu)). Les chiffres servent aussi l'IA : un prix, un pourcentage ou une date sont extraits tels quels.
- **Formulations « confirmé ».** Schwedelson relève que « Accès validé » augmente les chances d'apparaître en priorité sur Apple Mail. À n'utiliser que si c'est vrai : sinon c'est un objet trompeur, et les plaintes suivent.

Modèles d'objets à adapter (exemples de ce guide, à tester) :

| Modèle | Exemple |
| --- | --- |
| Bénéfice chiffré + échéance | -20 % sur l'automne jusqu'à dimanche |
| Nouveauté concrète | Nouveau : la veste qui pèse 380 g |
| Question personnelle | Camille, on garde votre taille en stock ? |
| Contenu utile | 3 erreurs qui abîment un parquet |
| Rappel d'échéance réelle | Vos 1 200 points expirent le 31 octobre |
| Transactionnel (vrai uniquement) | Commande 4512 expédiée, livraison jeudi |

### L'outil

```bash
python3 analyse_objet.py --objet "Vos 3 nouveautés d'octobre (-20 % jusqu'au 5/10) 🍂" \
  --preheader "Le récap en 10 secondes : 3 nouveautés, -20 % jusqu'au lundi 5 octobre." \
  --expediteur "Camille de Exemple"
python3 analyse_objet.py --csv historique.csv     # colonnes : objet, delivres, clics
```

Il affiche la troncature client par client, la version Emoji de chaque caractère, le sélecteur U+FE0F manquant, les majuscules, les faux RE:, l'encodage RFC 2047, la similarité objet/préheader et les défauts du nom d'expéditeur.

## 7. Tracking : pixel, liens, domaines

Le pixel d'ouverture ne mesure plus la lecture, mais il ne pénalise pas s'il est servi depuis votre domaine. Ce qui pénalise, ce sont les domaines de liens : Gmail note la réputation de chaque domaine d'URL présent dans vos emails. D'où un sous-domaine de tracking à votre marque, en HTTPS, et aucun raccourcisseur public.

### Le pixel d'ouverture en 2026

- **Il ne prouve plus la lecture.** Apple Mail Privacy Protection précharge les images via les serveurs d'Apple, et touche 55 à 60 % des ouvertures ([Litmus, juillet 2026](https://www.litmus.com/email-client-market-share)).
- **Chaque outil compte différemment.** Brevo inclut ces ouvertures machine par défaut depuis le 6 février 2025. Mailchimp permet de les exclure pour les envois postérieurs au 22 juin 2024. MailerLite, Kit et GetResponse ne le permettent pas ([EmailTooltester](https://www.emailtooltester.com/en/blog/apple-mpp-open-rate/)). Comparer des taux d'ouverture entre outils n'a donc aucun sens.
- **L'ouverture garde deux usages.** D'abord comme signal secondaire quand elle est marquée « non machine » par l'ESP. Ensuite pour repérer une chute brutale par fournisseur, en tendance.
- **Où le placer.** Juste après le préheader plutôt qu'en bas : un email tronqué par Gmail ne charge pas ce qui suit la coupure. C'est une recommandation de prudence, pas une règle documentée par Google.
- **Un seul pixel, sur votre domaine.** Chaque pixel publicitaire ou de retargeting tiers ajoute un domaine, une requête et une dépendance à la réputation d'un autre. `lint_email.py` les compte.

### Liens et domaines de tracking

- **Gmail suit la réputation des domaines d'URL.** Le code `421 4.7.28` existe dans une variante « containing one of your URL domains » ([Google](https://knowledge.workspace.google.com/admin/support/troubleshooting/gmail-smtp-errors-and-codes?hl=en)). Un domaine de redirection partagé par tous les clients d'un ESP vous fait donc partager la réputation des autres.
- **Un domaine de tracking à votre marque.** Créez `clic.news.exemple.fr` en CNAME vers l'ESP, avec un certificat HTTPS. Le M3AAWG donne en exemple des liens sur le même sous-domaine que le From ([Sender BCP 2026](https://www.m3aawg.org/sites/default/files/doc_files/m3aawg-sender-best-common-practices-aug-27-2026.pdf)).
- **Aucun raccourcisseur public** (bit.ly, tinyurl, etc.). Ils sont massivement utilisés par les spammeurs et masquent la destination, pour le filtre comme pour l'humain.
- **Le moins de domaines différents possible.** Chaque domaine de lien ou d'image est vérifié contre les listes de blocage d'URL : un seul partenaire listé contamine l'email.
- **Texte du lien = destination.** Un lien affichant `www.exemple.fr` qui mène ailleurs est un signal classique de phishing.
- **HTTPS partout, redirections minimales.** Une seule redirection de tracking, pas de chaîne.
- **Liens de désinscription valables indéfiniment.** Les fournisseurs peuvent voir que vous continuez d'envoyer après une désinscription ([Spam Resource](https://www.spamresource.com/2024/04/gmail-subscription-management-is-coming.html)).

| Pratique | Verdict |
| --- | --- |
| Pixel et liens sur un sous-domaine à votre marque, en HTTPS | Passe |
| Paramètres UTM sur les liens | Neutre (attention au poids) |
| Domaine de redirection partagé de l'ESP | Risque partagé avec les autres clients |
| Plusieurs pixels tiers (publicité, retargeting) | Pénalise : domaines et dépendances en plus |
| Liens en `http://` | Pénalise : contenu mixte, avertissements |
| Raccourcisseur public | Pénalise fortement |
| Lien vers une adresse IP brute | Pénalise fortement |
| Texte d'URL différent de la destination | Signal de phishing |

### Mesurer sans les ouvertures

Les indicateurs à suivre : clics uniques humains, clics par fournisseur, conversions et revenu par email délivré, réponses, désinscriptions, plaintes.

En B2B, les passerelles de sécurité des entreprises ouvrent souvent tous les liens d'un email dès sa réception, ce qui fabrique de faux clics. Filtre simple : ignorer les clics survenus dans les 30 secondes après la livraison, et les rafales de 3 clics ou plus dans la même seconde. Ces seuils sont une heuristique à calibrer sur vos données.

```sql
-- Premier clic "humain" par contact et par campagne (PostgreSQL / DuckDB)
WITH clicks AS (
  SELECT c.contact_id, c.campaign_id, c.event_at,
         c.event_at - d.event_at AS delai,
         COUNT(*) OVER (PARTITION BY c.contact_id, c.campaign_id,
                        date_trunc('second', c.event_at)) AS clics_meme_seconde
  FROM email_events c
  JOIN email_events d
    ON d.contact_id = c.contact_id AND d.campaign_id = c.campaign_id
   AND d.event_type = 'delivered'
  WHERE c.event_type = 'click'
)
SELECT contact_id, campaign_id, MIN(event_at) AS premier_clic_humain
FROM clicks
WHERE delai > INTERVAL '30 seconds' AND clics_meme_seconde < 3
GROUP BY contact_id, campaign_id;
```

Cette requête est testée : sur un jeu d'essai, elle écarte une rafale de 3 clics survenue 4 secondes après la livraison et garde le clic humain survenu 2 heures plus tard. C'est ce « clic humain » qui alimente la segmentation de la section 9.

## 8. Être remonté comme important par les IA des messageries

Aucune IA de messagerie n'obéit à l'expéditeur. Toutes classent sur trois choses : la relation (réponses, contacts, fréquence d'interaction), le caractère daté et actionnable du contenu, et le texte HTML réel des premières lignes. Ce sont vos trois leviers, plus les données structurées Gmail.

### Ce que chaque IA lit, et comment elle trie

| Assistant | Ce qu'il fait | Signaux documentés |
| --- | --- | --- |
| [Gmail AI Inbox](https://blog.google/products-and-platforms/products/gmail/gmail-is-entering-the-gemini-era/) (Gemini 3, janv. 2026 ; US et anglais au lancement, ouvert aux abonnés AI Pro et Plus en [mai 2026](https://techcrunch.com/2026/05/19/you-can-now-talk-to-your-gmail-inbox-as-seen-at-google-io-2026/)) | Briefing en deux blocs : « Suggested to-dos » et « Topics to catch up on » | Personnes VIP déduites de la fréquence d'échange, des contacts et du contenu ; factures, rappels de rendez-vous |
| [Marqueurs d'importance Gmail](https://support.google.com/mail/answer/186543?hl=en) | Marque « important » | Qui vous écrivez et combien, emails ouverts, emails répondus, mots-clés des emails lus, étoiles, archivages, suppressions |
| [Promotions « Les plus pertinents »](https://techcrunch.com/2025/09/11/gmail-makes-it-easier-to-track-upcoming-package-deliveries) (sept. 2025, mobile, comptes perso) | Trie l'onglet par engagement, ajoute des rappels d'offres | Les marques avec lesquelles l'utilisateur interagit le plus |
| [Gmail summary cards](https://workspaceupdates.googleblog.com/2025/05/gemini-summary-cards-gmail-app.html) (mai 2025) | Résumé automatique en haut des longs fils | Anglais, offres payantes |
| [Apple Intelligence](https://support.apple.com/en-gb/guide/iphone/iph9ae667055/26/ios/26) (iOS 18.2 puis 26, français inclus) | Catégories, Priority Messages, résumé qui **remplace l'aperçu** dans la liste | Un email « time-sensitive » de Promotions ou Transactions remonte aussi dans Principal ([Apple](https://support.apple.com/en-gb/guide/iphone/iphfe4a36baf/ios)) |
| [Outlook Copilot « Prioritize »](https://support.microsoft.com/en-us/outlook/copilot-outlook/prioritize-my-inbox) | Priorité haute, normale ou basse, première ligne remplacée par un résumé | Personnes du fil, fonctions, contenu, action requise. Ignore les messages marqués « faible importance » par l'expéditeur et les contenus trop courts |
| [Outlook Focused Inbox](https://support.microsoft.com/en-us/outlook/what-is-focused-inbox) | Sépare Prioritaire et Autres | Interactions passées ; écarte le bulk et l'automatique |
| Yahoo Mail ([Catch Up](https://www.yahooinc.com/press/yahoo-rolls-out-new-catch-up-feature-to-help-users-tackle-inbox-overload) juin 2025, [Mail Planner](https://www.mediapost.com/publications/article/413827/yahoo-reinvents-ad-formats-ai-experiences.html) mars 2026) | Résumés d'une ligne, garder ou supprimer, calendrier et to-do automatiques | [Dates, horaires, confirmations, factures, codes](https://help.yahoo.com/kb/SLN36900.html) |
| Agents tiers ([Superhuman](https://techcrunch.com/2025/02/19/superhuman-introduces-ai-powered-categorization-to-reduce-spammy-emails-in-your-inbox), [Shortwave](https://www.shortwave.com/docs/guides/ai-assistant/), [Perplexity Email Assistant](https://www.marktechpost.com/2025/09/22/perplexity-launches-an-ai-email-assistant-agent-for-gmail-and-outlook-aimed-at-scheduling-drafting-and-inbox-triage/)) | Étiquettes « marketing », « needs reply », archivage automatique | Aucune consigne publiée pour les expéditeurs ; le marketing sans valeur est archivé |

Deux conséquences directes. Sur iPhone, le préheader est remplacé par un résumé dès que l'utilisateur a activé Apple Intelligence. Et envoyer à des inactifs « entraîne le modèle à ne pas vous faire remonter » ([Klaviyo, mai 2026](https://www.klaviyo.com/blog/ai-email-marketing-inbox-optimization)).

### Les règles d'écriture qui fonctionnent

1. **Premier écran = résumé.** Offre, code, date limite et appel à l'action dans les 100 à 150 premiers caractères de texte visible ([Inbox Monster, juin 2026](https://inboxmonster.com/blog/improve-ai-email-summaries-6-practical-fixes)).
2. **Un objectif par email.** Si l'email ne tient pas en deux phrases utiles, c'est un problème de conception (Klaviyo). Si vous ne le résumez pas en dix mots, l'IA non plus (Inbox Monster).
3. **Tout en texte HTML réel.** Apple ne lit pas l'attribut alt pour ses résumés ([tests Knak, août 2026](https://knak.com/blog/apple-intelligence-ios18-2/)). Un email tout-image donne « trop court pour être résumé », ou un résumé du pied de page ([Action Rocket](https://www.actionrocket.co/blog/ai-summaries-in-email-clients)). En HTML vivant, les résumés reprennent deux fois plus de détails (Inbox Monster).
4. **Dates absolues.** Écrire « lundi 5 octobre 2026 à 23 h 59 », jamais « ce week-end ». Les IA extraient les échéances : to-dos Gmail, « time-sensitive » Apple, Mail Planner Yahoo.
5. **L'offre séparée des conditions.** Les petites lignes vont en bas, sinon l'IA les remonte dans le résumé ([webinar Inbox Monster / SendGrid](https://inboxmonster.com/blog/ai-and-the-inbox-webinar-optimizing-for-ai-summaries-extractions)).
6. **Objet aligné sur le corps.** Un objet qui promet autre chose que le contenu produit un résumé qui le contredit ([Litmus](https://www.litmus.com/blog/ai-generated-summaries)).
7. **Données transactionnelles complètes en texte.** Nom du marchand, numéro de commande, numéro de suivi : Apple Wallet les extrait pour le suivi de colis (Knak).
8. **Provoquer la réponse.** Une réponse est le signal le plus fort des marqueurs Gmail et du statut VIP. Utilisez une adresse lue, une question simple, et invitez à ajouter l'expéditeur aux contacts.

Bloc d'ouverture type, à placer juste après le logo :

```html
<h1 style="margin:0 0 12px;font-size:26px;line-height:1.25;">
  -20 % sur la gamme automne jusqu'au lundi 5 octobre
</h1>
<p style="margin:0 0 16px;">
  L'essentiel : votre code <strong>OCTOBRE20</strong> donne -20 % sur les 3 nouveaux modèles,
  valable jusqu'au <strong>lundi 5 octobre 2026 à 23 h 59</strong>. Livraison en 48 h.
</p>
<a href="https://www.exemple.fr/nouveautes" style="...">Voir les 3 modèles</a>
```

### Données structurées Gmail (JSON-LD)

Les [annotations de l'onglet Promotions](https://developers.google.com/workspace/gmail/promotab/overview) affichent un badge d'offre, un code, une date de fin, une carte ou un carrousel produit. Elles se placent dans le `<head>`, sans inscription préalable :

```html
<head>
<script type="application/ld+json">
[{
  "@context": "http://schema.org/",
  "@type": "DiscountOffer",
  "description": "-20 % sur la gamme automne",
  "discountCode": "OCTOBRE20",
  "availabilityStarts": "2026-09-29T08:00:00+02:00",
  "availabilityEnds": "2026-10-05T23:59:00+02:00",
  "offerPageUrl": "https://www.exemple.fr/nouveautes",
  "merchantHomepageUrl": "https://www.exemple.fr"
},
{
  "@context": "http://schema.org/",
  "@type": "PromotionCard",
  "image": "https://img.exemple.fr/octobre26/modele-a.jpg",
  "url": "https://www.exemple.fr/modele-a",
  "headline": "Modèle A, 30 % plus léger",
  "price": 79.00,
  "priceCurrency": "EUR",
  "discountValue": 20.00,
  "position": 1
}]
</script>
</head>
```

Règles utiles ([référence](https://developers.google.com/workspace/gmail/promotab/reference), [FAQ](https://developers.google.com/workspace/gmail/promotab/faq), [dépannage](https://developers.google.com/workspace/gmail/promotab/troubleshooting)) :

- Dates en ISO 8601 avec fuseau. Une offre expirée n'est plus affichée.
- Images de carte : PNG ou JPEG au format 4:5, 1:1 ou 1.91:1, même ratio pour tout le carrousel (10 images maximum).
- L'annotation ne change pas le classement en onglet. Elle est soumise à des filtres de qualité et de fréquence.
- Un sous-domaine d'envoi inconnu « brouille » le classifieur : gardez des sous-domaines stables.
- Invisible pour les comptes Google Workspace.

Les emails transactionnels peuvent porter `Order`, `ParcelDelivery`, `Invoice` ou des réservations ([vue d'ensemble](https://developers.google.com/workspace/gmail/markup/overview)). Ce balisage exige une [inscription](https://developers.google.com/workspace/gmail/markup/registering-with-google) :

- envoyer un vrai email de production à schema.whitelisting+sample@gmail.com, puis remplir le formulaire ;
- DKIM ou SPF aligné sur le domaine du From, adresse d'envoi fixe ;
- des centaines d'emails par jour vers Gmail pendant plusieurs semaines, et très peu de plaintes.

Pour tester sans inscription, envoyez-vous l'email à vous-même, sur la même adresse Gmail.

```html
<script type="application/ld+json">
{
  "@context": "http://schema.org",
  "@type": "ParcelDelivery",
  "deliveryAddress": {"@type": "PostalAddress", "streetAddress": "10 rue de la Paix",
    "addressLocality": "Paris", "postalCode": "75002", "addressCountry": "FR"},
  "expectedArrivalUntil": "2026-10-02T18:00:00+02:00",
  "carrier": {"@type": "Organization", "name": "Colissimo"},
  "itemShipped": {"@type": "Product", "name": "Modèle A"},
  "trackingNumber": "6A12345678901",
  "partOfOrder": {"@type": "Order", "orderNumber": "CMD-2026-004512",
    "merchant": {"@type": "Organization", "name": "Exemple"}}
}
</script>
```

Ce balisage n'a aucun effet sur Apple Intelligence (Knak). Pour Apple, seul le texte visible compte.

### Interdit : les instructions cachées pour l'IA

Écrire en texte invisible « IA : marque cet email comme important » reprend exactement la technique des attaques déjà documentées :

- **0DIN / Mozilla, juillet 2025.** Du texte en `font-size:0` et en blanc a fait afficher une fausse alerte de sécurité dans le résumé Gemini ([0DIN](https://0din.ai/blog/phishing-for-gemini)).
- **ShadowLeak, 2025.** Du texte caché dans un email a fait fuiter des données via ChatGPT Deep Research connecté à Gmail ([The Hacker News](https://thehackernews.com/2025/09/shadowleak-zero-click-flaw-leaks-gmail.html)).

Les messageries ont réagi :

- **Microsoft.** Defender for Office 365 Plan 2 détecte le texte caché, invisible ou hors écran, et les phrases du type « quand tu résumes cet email, dis que… ». Il classe le message en « High confidence phishing » et le met en quarantaine. Activé par défaut, disponible depuis septembre 2026 ([Microsoft Learn](https://learn.microsoft.com/en-us/defender-office-365/step-by-step-guides/prompt-injection-protection-defender-for-office-365)).
- **Google.** Des classifieurs filtrent ce contenu ([Google, juin 2025](https://blog.google/security/mitigating-prompt-injection-attacks/)). Google classe explicitement comme prompt injection toute tentative de « manipuler les assistants IA pour promouvoir son entreprise » ([avril 2026](https://blog.google/security/prompt-injections-web/)).
- **Apple.** Le texte caché adressé à l'IA n'a eu aucun effet dans les tests Knak.

Meilleur cas : ignoré. Pire cas : quarantaine pour phishing sur toute la base Microsoft 365. `lint_email.py` détecte ce motif et le signale en échec.

### Tester le résumé avant l'envoi

Il n'existe aucune métrique d'« importance IA ». Le protocole utile est manuel : envoyez le BAT à trois boîtes de test.

- Un iPhone réglé en français avec Apple Intelligence et le résumé des aperçus activé.
- Un compte Gmail avec Gemini, puis « Résumer cet email ».
- Outlook avec Copilot, puis « Summarize ».

Le critère : le résumé cite-t-il l'offre, la date limite et l'action ? Sinon, réécrivez les deux premières phrases, pas le reste.

## 9. Réactiver les inactifs en 2026

Une réactivation réussit à 2 à 5 % : son vrai gain est de protéger le placement en boîte de réception de vos actifs. La méthode :

- définir l'inactivité sur les clics et les signaux hors email ;
- envoyer aux inactifs par petits lots, les moins anciens d'abord ;
- une séquence de 3 emails qui propose de recevoir moins avant de proposer de partir ;
- puis arrêter d'écrire à ceux qui ne cliquent pas.

### Pourquoi c'est un sujet de délivrabilité

- **Les fournisseurs le demandent.** Google : « envisagez de désinscrire les destinataires qui n'ouvrent pas ou ne lisent pas vos messages » ([consignes](https://support.google.com/mail/answer/81126)). Yahoo : envoyer à des gens qui ne lisent pas « nuit à vos indicateurs et à votre réputation » ([Yahoo](https://senders.yahooinc.com/best-practices/)).
- **Le filtrage Gmail repose sur l'engagement.** En cas de difficulté, Al Iverson conseille de n'écrire pendant 30 jours qu'aux contacts actifs sur les 9 à 12 derniers mois ([Spam Resource](https://www.spamresource.com/2024/02/isp-deliverability-guide-gmail-updated.html)).
- **Les adresses dormantes deviennent des pièges.** Une adresse inactive depuis 12 mois peut être recyclée en spam trap ([Validity](https://www.validity.com/blog/what-is-a-spam-trap/)), et Google supprime les comptes inutilisés depuis 2 ans.
- **Les nouvelles interfaces exposent les expéditeurs trop fréquents.** « Gérer les abonnements » de Gmail trie les expéditeurs par fréquence et désinscrit en un geste. L'AI Inbox apprend de l'absence d'interaction.
- **Le gain est mesurable.** Chez un expéditeur SendGrid (données 2020), l'arrêt des envois aux inactifs a doublé le taux d'ouverture sur l'année et réduit de 65 % les touches de spam traps ([Twilio](https://www.twilio.com/en-us/blog/insights/email-sunset-policy)).
- **Peu le font.** Seuls 23,9 % des expéditeurs ont une politique de sunset ([Mailjet, 2025](https://www.mailjet.com/blog/deliverability/understanding-email-sunset-policies/)).

### Définir l'inactivité

Signaux fiables : clic humain, réponse, achat, visite identifiée, produit consulté, connexion à l'app. L'ouverture ne compte que si l'ESP la marque « non machine ».

Kath Pay rappelle que seules 2 actions consommateur sur 14 sont attribuées à l'email (DMA 2023) : juger l'activité sur l'email seul, c'est couper des clients actifs ([MarTech](https://martech.org/how-to-create-a-re-engagement-strategy-that-doesnt-insult-your-subscribers/)). Distinguez aussi deux cas :

- la **réactivation email** : l'abonné ne clique plus ;
- la **réactivation client** : l'acheteur a dépassé son cycle d'achat habituel.

Fenêtres « engagé » selon la fréquence d'envoi ([Klaviyo](https://help.klaviyo.com/hc/en-us/articles/360037527052)) :

| Fréquence d'envoi | Fenêtre d'engagement |
| --- | --- |
| Quotidienne | 30 jours |
| 3 fois par semaine | 60 jours |
| 2 fois par semaine | 90 jours |
| Hebdomadaire | 180 jours |
| Mensuelle | 275 jours |

### Les segments et leurs règles d'envoi

Paliers inspirés de [Suped](https://www.suped.com/learn/email-deliverability/what-is-the-risk-of-sending-email-to-inactive-users) et de Klaviyo, calculés par `segmentation_engagement.sql` (section 10) pour un rythme hebdomadaire :

| Segment | Dernier signal fiable | Règle d'envoi |
| --- | --- | --- |
| 0 Nouveau | Inscrit depuis moins de 30 jours | Séquence de bienvenue |
| A Actif | 0 à 30 jours | Toutes les campagnes |
| B Tiède | 31 à 90 jours | Campagnes principales, fréquence réduite |
| C Refroidi | 91 à 180 jours | 1 à 2 emails par mois, meilleurs contenus, envoyés après les actifs |
| D Réactivation | 181 à 365 jours | Séquence de réactivation uniquement |
| E Sunset | Plus de 365 jours, ou jamais engagé après 180 jours | Plus d'envoi marketing |

Badsender conseille de lancer la réactivation dès 3 à 6 mois d'inactivité, car les chances chutent après 6 mois ([Badsender](https://www.badsender.com/en/2020/09/21/noel-address-inactive-contacts/)).

### Envoyer aux inactifs sans abîmer la réputation

- **Petits lots.** Les inactifs ne doivent pas dépasser 5 % de la cible active ([Actito](http://cdn3.actito.com/fe/actito-documentation/fr/docs/Using_the_inactivity_template/) : 1 250 inactifs maximum pour 25 000 actifs), ou 10 % du volume quotidien ([Practical Ecommerce](https://www.practicalecommerce.com/how-to-re-engage-email-subscribers-right)).
- **Les moins anciens d'abord.** On traite de 181 jours vers 365, ou par décile de score de propension ([Zeta](https://www.zetaglobal.com/resource-center/email-reactivation-campaigns-dormant-subscribers/)).
- **Gmail à part.** Chez Gmail, ne réactivez que les contacts qui ont au moins un signal hors ouverture (visite, achat), en lots dédiés ([Suped](https://www.suped.com/learn/email-deliverability/what-is-the-risk-of-sending-email-to-inactive-users)).
- **Arrêt immédiat** si les plaintes ou les `421` montent.
- **Pas d'IP ni de sous-domaine « poubelle ».** Gmail pèse la réputation du domaine, et le M3AAWG déconseille les domaines cousins.

### La séquence type

Synthèse de [Kath Pay](https://martech.org/9-steps-to-make-a-reactivation-program-that-really-work/), [Klaviyo](https://help.klaviyo.com/hc/en-us/articles/360017518492) et [Zeta](https://www.zetaglobal.com/fr/ressources/articles/la-reactivation-e-mail-pour-maximiser-le-roi) :

| Étape | Quand | Contenu | Objectif |
| --- | --- | --- | --- |
| 1. Valeur | J0 | Ce qui a changé depuis la dernière visite : nouveautés, services, retours gratuits. Pas de remise. Plusieurs blocs cliquables | Un clic |
| 2. Choix | J+7 | Format texte personnel : tout garder, 1 email par mois, thèmes, pause, ou partir. L'option « moins » au-dessus du lien de désinscription | Un clic sur une préférence |
| 3. Dernière chance | J+14 | L'offre (si elle est rentable par rapport à la valeur client) ou une perte réelle (points, statut). Date d'arrêt explicite | Un clic |
| Délai de grâce | J+21 à J+24 | Aucun envoi | — |
| Sortie | J+24 | Passage en sunset. Autre canal si disponible : SMS, push, app ([Splio](https://splio.com/comment-reveiller-sa-base-de-contacts-inactifs/)) | — |

Pendant la séquence, on suspend les campagnes classiques pour ces contacts. Est réactivé celui qui clique, pas celui qui ouvre ([Badsender](https://www.badsender.com/en/2025/01/23/ecommerce-emailing/)).

### Le copywriting qui fonctionne

- **La valeur, pas la culpabilité.** Évitez « Vous nous manquez » et montrez ce qui est nouveau (Kath Pay).
- **La curiosité avant la remise.** Klaviyo préfère « Pourquoi vous ne reviendrez pas à votre ancienne routine du matin » à « -50 % » ([Klaviyo](https://www.klaviyo.com/blog/sunset-flow)).
- **La remise en dernier.** Les contacts réactivés par une promotion sont souvent opportunistes et redeviennent vite inactifs (Badsender). Pesez l'offre par rapport à la valeur client. Un montant en euros fait généralement mieux qu'un pourcentage (étude Return Path citée par [Adobe](https://experienceleague.adobe.com/en/docs/deliverability-learn/deliverability-best-practice-guide/additional-resources/generic-resources/re-engagement)).
- **L'aversion à la perte, seulement si elle est vraie.** Points qui expirent, statut VIP qui tombe, compte supprimé : Strava et Withings l'utilisent ([EmailTooltester](https://www.emailtooltester.com/en/blog/reengagement-email-examples/)).
- **L'opt-down dans le corps de l'email.** La page « Gérer les abonnements » de Gmail court-circuite votre centre de préférences ([Chad White via Zeta](https://www.zetaglobal.com/resource-center/gmail-manage-subscriptions-tool/)). Chez METRO AG, un bloc « pouce haut / pouce bas » par thème, placé au-dessus du lien de désinscription, a réduit les désinscriptions jusqu'à 10 % ([Really Good Emails](https://reallygoodemails.com/school/blog/unsubscribes-list-growth-soft-opt-out)).
- **Un bloc de réactivation dans la newsletter.** Chez un client de Badsender, 11 % ont cliqué « continuer à recevoir », et le bloc a généré 8 ventes contre 1 sans lui.
- **Une question seulement si vous agissez sur la réponse** (Badsender).

Objets relevés dans les sources, avec une adaptation française proposée (aucune n'a de données A/B publiées) :

| Marque | Original | Adaptation |
| --- | --- | --- |
| Android Authority | Are you there? | Vous êtes toujours là ? |
| Venmo | It's been a while… here's what you missed | Ce que vous avez manqué depuis mars |
| Cuisinart | Pssst… we have a question for you | Psst… une question rapide |
| Zapier | \[Action Required\] Confirm your email preferences | Vos préférences en 30 secondes |
| Withings | Your VIP pass runs out today | Votre statut VIP expire aujourd'hui |
| ReadyMag | You'll be unsubscribed from ReadyMag emails | Sans nouvelles, on arrête le 15 octobre |
| Klaviyo (exemple) | Is it time to say goodbye? | On se dit au revoir ? |
| Splio (FR) | Psst, cela fait plus d'un an que vous ne nous avez pas lu ? | — |

Email 2 complet, à envoyer en texte brut ou HTML minimal (exemple de ce guide) :

```text
De : Camille de Exemple <camille@news.exemple.fr>
Objet : Camille, on continue ?
Préheader : Tout, 1 email par mois, ou rien : choisissez en 10 secondes.

Bonjour Camille,

Vous recevez nos emails depuis 2024, mais vous ne les lisez plus beaucoup.
C'est peut-être trop souvent, ou pas le bon sujet. Dites-nous ce qui vous convient :

-> Tout garder : https://www.exemple.fr/pref/tout
-> 1 email par mois, les nouveautés seulement : https://www.exemple.fr/pref/mensuel
-> Seulement les offres de -20 % et plus : https://www.exemple.fr/pref/offres
-> Ne plus rien recevoir : https://www.exemple.fr/u/TOKEN

Sans clic de votre part avant le jeudi 15 octobre, nous arrêterons de vous écrire.
Vous pourrez revenir quand vous voudrez.

Camille, pour l'équipe Exemple
P.S. Une question ? Répondez à cet email, je lis tout.
```

Cet email coche les signaux que les IA de tri remontent (section 8) : un nom de personne connu, une date d'échéance explicite, une action demandée et une invitation à répondre.

### Ce qu'il faut attendre

- **Taux de réactivation** : 2 à 5 % ([Inbox Monster, 2026](https://inboxmonster.com/blog/the-monster-guide-to-reengagement)). Kath Pay prévoit 1 à 2 % de conversion.
- **Automatisation « acheteurs perdus »** : 1,96 % de clics et 0,52 % de conversion chez Omnisend ([2026](https://www.omnisend.com/blog/win-back-email/)).
- **Segments inactifs** : ils cliquent à 0,6-0,7 % et se désinscrivent trois fois plus qu'ils ne cliquent (Badsender).
- **Le mythe des « 45 % réactivés ».** L'étude Return Path disait autre chose : 45 % des destinataires ont ensuite lu des messages *ultérieurs*, et l'email de réactivation lui-même n'a fait que 12 % d'ouverture ([Adobe](https://experienceleague.adobe.com/en/docs/deliverability-learn/deliverability-best-practice-guide/additional-resources/generic-resources/re-engagement)).

À suivre par étape : clics, plaintes (arrêt au-dessus de 0,1 %), désinscriptions, et surtout le taux de spam Postmaster et les clics par fournisseur des actifs, avant et après le sunset. Mesurez aussi, 90 jours plus tard, la part des réactivés redevenus inactifs.

### Score d'engagement

Pondérations publiées par [Seventh Sense](https://www.theseventhsense.com/blog/email-engagement-scoring-segmentation) : clic = 1, réponse = 5, ouverture = 0,33. Chez eux, les contacts engagés représentent 30 à 50 % de la base mais 85 à 95 % du revenu email. Les poids achat et visite ci-dessous sont à calibrer sur vos données :

```sql
-- Score d'engagement sur 90 jours (PostgreSQL)
SELECT contact_id,
       5.0  * COUNT(*) FILTER (WHERE event_type = 'reply')
     + 1.0  * COUNT(*) FILTER (WHERE event_type = 'click')
     + 0.33 * COUNT(*) FILTER (WHERE event_type = 'open' AND NOT COALESCE(is_machine_open, FALSE))
       AS score_email_90j
FROM email_events
WHERE event_at >= NOW() - INTERVAL '90 days'
GROUP BY contact_id;
-- À additionner : +3 par commande, +0,5 par visite identifiée (pondérations à calibrer)
```

## 10. Boîte à outils : scripts d'audit

Sept outils testés le 26/09/2026 couvrent l'audit complet d'un envoi : DNS, message réel, objet, rapports DMARC, segmentation et désinscription. Ils sont dans le dossier `outils/` du projet, sans dépendance lourde (Python 3.8+).

Code complet de chaque outil : Code source des outils

| Fichier | Ce qu'il vérifie | Commande |
| --- | --- | --- |
| `audit_dns.py` | MX, SPF (lookups, void lookups, terminaison), DMARC, taille des clés DKIM, BIMI, MTA-STS, TLS-RPT, PTR/FCrDNS | `python3 audit_dns.py news.exemple.fr --selectors s1 s2 --ip 203.0.113.10` |
| `lint_email.py` | En-têtes (one-click, DKIM h=, alignement, Feedback-ID), MIME, poids/clipping Gmail, préheader, ratio texte/images, alt, pixels, liens, raccourcisseurs, texte caché, prompt injection, tokens non remplacés, JSON-LD | `python3 lint_email.py campagne.eml` |
| `analyse_objet.py` | Longueur, troncature par client, emojis (version Unicode, ZWJ, FE0F), majuscules, faux RE:, encodage RFC 2047, préheader, nom d'expéditeur ; mode historique CSV avec test statistique | `python3 analyse_objet.py --objet "..." --preheader "..."` |
| `dmarc_rua_resume.py` | Rapports DMARC agrégés (.xml, .gz, .zip) : volume, conformité et alignement par IP source | `python3 dmarc_rua_resume.py ./rapports/` |
| `segmentation_engagement.sql` | Segments A à E sur l'engagement réel (hors ouvertures machine), KPIs par fournisseur (Gmail, Orange, Free…), RFM | PostgreSQL, adaptable BigQuery |
| `generer_eml.py` | Construit un MIME conforme : multipart/alternative, UTF-8 QP, Subject RFC 2047, List-Unsubscribe + Post, Feedback-ID | `python3 generer_eml.py template_reference.html > test.eml` |
| `desinscription_one_click.py` | Endpoint RFC 8058 (POST sans redirection, jeton HMAC) + page d'opt-down | `pip install flask` puis lancer |

Installation : `pip install dnspython emoji` (et `flask` pour l'endpoint). Le vrai `.eml` d'une campagne se récupère dans Gmail via « Afficher l'original » puis « Télécharger l'original » : c'est ce fichier qu'il faut linter, pas le HTML de l'éditeur, car l'ESP y ajoute ses en-têtes, sa réécriture de liens et son pixel.

Sortie réelle de `lint_email.py` sur un email volontairement mauvais :

```text
[ECHEC    ] Texte caché      Instructions adressées à une IA dans du texte caché : traité comme prompt injection / phishing.
[ECHEC    ] Ratio            Email quasi 100 % image : illisible images bloquées, pour les filtres et pour les IA.
[ECHEC    ] Liens            Raccourcisseur public (bit.ly) : utilisez un domaine de tracking à votre marque.
[ECHEC    ] Liens            Texte « www.mabanque.fr » mais lien vers evil.example.net (signal phishing).
[ECHEC    ] Personnalisation Balises non remplacées : ['{{first_name}}']
[ATTENTION] Préheader        L'aperçu commence par « voir dans le navigateur » : gaspillage.
```

Mode historique de `analyse_objet.py` : exportez vos campagnes (colonnes `objet, delivres, clics`) et le script compare le taux de clic moyen par campagne selon chaque caractéristique d'objet, avec un test de permutation. Il mesure les clics et non les ouvertures, faussées par Apple MPP.

```text
Caractéristique            Camp.  CTR avec  CTR sans    Écart  p-value
emoji                         11     2.13%     1.93%     +10%    0.040 *
question                      10     2.14%     1.93%     +11%    0.038 *
chiffre                       17     1.80%     2.12%     -15%    0.000 *
```

(Données de démonstration générées aléatoirement : elles illustrent la sortie, pas un résultat.)

Extrait simplifié d'`audit_dns.py` : le compte récursif des lookups SPF, première cause de `permerror` silencieux quand on empile les outils (ESP, CRM, support, facturation).

```python
def walk(self, domain, depth=0):
    spf = [t for t in txt_records(domain) if t.lower().startswith("v=spf1")]
    if not spf:
        if depth > 0:
            self.void += 1          # > 2 void lookups = permerror (RFC 7208 §4.6.4)
        return None
    for term in spf[0].split()[1:]:
        t = term.lstrip("+-~?").lower()
        if t.startswith(("include:", "redirect=")):
            self.lookups += 1
            self.walk(t.split(":" if ":" in t else "=", 1)[1], depth + 1)
        elif t in ("a", "mx", "ptr") or t.startswith(("a:", "mx:", "exists:", "ptr:")):
            self.lookups += 1       # > 10 lookups = permerror
```

Pour un suivi continu plutôt qu'un audit ponctuel : [parsedmarc](https://github.com/domainaware/parsedmarc) (rapports DMARC vers Elasticsearch/Grafana) et [checkdmarc](https://github.com/domainaware/checkdmarc) (SPF/DMARC/MTA-STS en CLI).

## 11. Checklist pré-envoi

Trois listes : la configuration à valider une fois (puis chaque mois), le contrôle de chaque campagne, et le suivi après envoi.

### Configuration (une fois, puis `audit_dns.py` chaque mois)

- [ ] Sous-domaines séparés marketing / transactionnel, alignés sur From, Return-Path, DKIM, liens
- [ ] SPF en `~all`, 8 lookups maximum, aucun include d'outil résilié
- [ ] DKIM RSA 2048 avec `d=` sur votre domaine, rotation planifiée tous les 6 mois
- [ ] DMARC publié avec `rua`, trajectoire vers `p=reject` + `np=reject`, sans `pct`
- [ ] PTR et HELO cohérents (FCrDNS) si IP dédiée, TLS actif
- [ ] Domaine de tracking et d'images à votre marque, en HTTPS
- [ ] Endpoint de désinscription RFC 8058 : POST sans redirection, effectif sous 48 h, idempotent
- [ ] Feedback-ID avec un SenderId stable ; domaine vérifié dans Postmaster Tools et Yahoo Sender Hub
- [ ] SNDS (IP dédiée), boucles La Poste (Validity) et Signal Spam (Orange, SFR)
- [ ] Logo : BIMI (VMC ou CMC) pour Gmail et Yahoo, Apple Business pour Apple Mail

### Chaque campagne (sur le BAT réel, téléchargé en .eml)

- [ ] `lint_email.py` : zéro échec
- [ ] Objet : l'essentiel dans 33 caractères, 50 au total, 1 emoji maximum en Emoji ≤ 12.0, pas de faux RE:
- [ ] Nom d'expéditeur reconnaissable, stable, sans emoji ; Reply-To lu
- [ ] Préheader de moins de 90 caractères qui complète l'objet, suivi des espaceurs
- [ ] Première phrase visible = offre + date absolue + action (c'est elle que l'IA résume)
- [ ] Au moins 500 caractères de texte HTML réel ; prix, code, date et CTA en texte, alt sur chaque image
- [ ] HTML sous 80 Ko avant tracking ; styles critiques en inline (La Poste, SFR)
- [ ] Version texte générée depuis le HTML, UTF-8 quoted-printable
- [ ] JSON-LD Promotions (`DiscountOffer`) cohérent avec l'email, dates ISO avec fuseau
- [ ] Aucun texte caché hors préheader, aucune instruction adressée à une IA
- [ ] Aucun raccourcisseur, aucun lien http, texte des liens = destination
- [ ] Option « recevoir moins » au-dessus du lien de désinscription
- [ ] Cible : segments A et B (et C selon le calendrier) ; les inactifs D en lots ≤ 5 % de la cible, pas en masse
- [ ] Test de résumé : iPhone avec Apple Intelligence, Gmail avec Gemini, Outlook avec Copilot

### Après l'envoi (J+1 à J+7)

- [ ] Erreurs de livraison par fournisseur (codes Gmail, `550 5.7.515`, codes `OFR`)
- [ ] Clics humains par fournisseur, comparés à la moyenne des 5 dernières campagnes
- [ ] Taux de spam Postmaster Tools < 0,10 %, Yahoo Insights < 0,3 %
- [ ] Plaintes Signal Spam et JMRP traitées comme désinscriptions
- [ ] Rapports DMARC : aucune nouvelle IP légitime non alignée
- [ ] Mise à jour des segments d'engagement, contacts sans clic après la séquence passés en sunset

## Experts, dépôts GitHub et sources

Les références ci-dessous ont toutes été ouvertes le 26/09/2026. Ce qui n'a pas pu être confirmé sur une source primaire a été retiré du guide ou signalé comme tel.

### Les experts à suivre

| Expert | Structure | Pour quoi le lire |
| --- | --- | --- |
| Al Iverson | [Spam Resource](https://www.spamresource.com/) | Veille quotidienne : Gmail, Microsoft SNDS/JMRP, Yahoo, SPF, DMARC |
| Laura Atkins | [Word to the Wise](https://www.wordtothewise.com/) | Engagement, réactivation, filtrage ([réactivation, déc. 2025](https://www.wordtothewise.com/2025/12/lets-talk-reengagement/)) |
| Chad S. White | Oracle, [Email Marketing Rules](https://www.emailmarketingrules.com/), CMSWire | Inactifs, préférences, impact des IA sur l'aperçu |
| Kath Pay | Holistic Email Marketing, [MarTech](https://martech.org/author/kath-pay/) | Réactivation sans « vous nous manquez », séquences |
| Rémi Parmentier (FR) | [hteumeuleu.com](https://www.hteumeuleu.com/), caniemail, email-bugs | Code HTML, support des clients dont Orange, SFR, La Poste |
| Mark Robbins | [goodemailcode.com](https://www.goodemailcode.com/) | Template de base, préheader, accessibilité |
| Jay Schwedelson | SubjectLine.com, Worldata | Tests d'objets à grande échelle |
| Badsender (FR) | [badsender.com](https://www.badsender.com/) | Accessibilité, e-commerce, inactifs |
| MailSoar (FR) | [mailsoar.com](https://www.mailsoar.com/tips/reengage-inactive-subscribers/) | Délivrabilité appliquée aux FAI français |
| M3AAWG | [Sender BCP v4.0, août 2026](https://www.m3aawg.org/sites/default/files/doc_files/m3aawg-sender-best-common-practices-aug-27-2026.pdf) | La référence de l'industrie : domaines, rDNS, warm-up, rebonds |
| Mailhardener | [Blog](https://www.mailhardener.com/blog/do-not-flatten-spf) | SPF, DKIM, DMARC en profondeur |
| Knak, Inbox Monster | [Knak](https://knak.com/blog/apple-intelligence-ios18-2/), [Inbox Monster](https://inboxmonster.com/blog/improve-ai-email-summaries-6-practical-fixes) | Tests concrets des résumés IA |

### Dépôts GitHub utiles

Étoiles et dernière activité relevées via l'API GitHub le 26/09/2026.

| Dépôt | Étoiles | Dernière activité | Usage |
| --- | --- | --- | --- |
| [domainaware/parsedmarc](https://github.com/domainaware/parsedmarc) | \~1 300 | 24/09/2026 | Rapports DMARC (dont RFC 9990) vers Elasticsearch, Grafana, Splunk |
| [domainaware/checkdmarc](https://github.com/domainaware/checkdmarc) | 321 | 21/09/2026 | Audit SPF, DMARC, MTA-STS, TLS-RPT, BIMI en ligne de commande |
| [liuch/dmarc-srg](https://github.com/liuch/dmarc-srg) | 300 | 09/09/2026 | Visionneuse de rapports DMARC auto-hébergée |
| [resend/react-email](https://github.com/resend/react-email) | 19 776 | 23/09/2026 | Emails en React |
| [mjmlio/mjml](https://github.com/mjmlio/mjml) | 18 248 | 10/09/2026 | Framework d'emails responsives |
| [emailmonday/Cerberus](https://github.com/emailmonday/Cerberus) | 5 137 | 14/09/2026 | Templates hybrides de référence |
| [maizzle/framework](https://github.com/maizzle/framework) | 1 614 | 16/09/2026 | Emails avec Tailwind CSS |
| [hteumeuleu/caniemail](https://github.com/hteumeuleu/caniemail) | 945 | 16/09/2026 | Support CSS/HTML par client |
| [hteumeuleu/email-bugs](https://github.com/hteumeuleu/email-bugs) | 576 | Actif en 2026 | Bugs de rendu en cours |
| [axllent/mailpit](https://github.com/axllent/mailpit) | 10 454 | 20/09/2026 | Serveur SMTP de test local avec aperçu |
| [postalserver/postal](https://github.com/postalserver/postal) | 16 829 | 19/09/2026 | Plateforme d'envoi auto-hébergée |
| [KumoCorp/kumomta](https://github.com/KumoCorp/kumomta) | 544 | 24/09/2026 | MTA haut volume, règles de débit par fournisseur |
| [rspamd/rspamd](https://github.com/rspamd/rspamd) | 2 534 | 26/09/2026 | Filtre antispam, pour tester ses emails |
| [apache/spamassassin](https://github.com/apache/spamassassin) | 344 | 26/09/2026 | Règles et scores cités dans ce guide |
| [authindicators/svg-ps-converters](https://bimigroup.org/svg-conversion-tools-released/) | — | — | Conversion d'un logo en SVG Tiny PS pour BIMI |

### Sources principales

**Standards** : [RFC 7208](https://www.rfc-editor.org/rfc/rfc7208.html) (SPF) · [RFC 6376](https://www.rfc-editor.org/rfc/rfc6376.html) (DKIM) · [RFC 8058](https://www.rfc-editor.org/rfc/rfc8058.html) (désinscription un clic) · [RFC 9989](https://www.rfc-editor.org/rfc/rfc9989.html) (DMARCbis) · [RFC 9991](https://www.rfc-editor.org/rfc/rfc9991.html) · [RFC 5322](https://www.rfc-editor.org/rfc/rfc5322) · [RFC 2047](https://www.rfc-editor.org/rfc/rfc2047) · [RFC 8461](https://www.rfc-editor.org/rfc/rfc8461.html) (MTA-STS) · [RFC 8460](https://www.rfc-editor.org/rfc/rfc8460.html) (TLS-RPT)

**Fournisseurs de messagerie** : [Google, consignes expéditeurs](https://support.google.com/a/answer/81126?hl=en) · [Google, FAQ](https://support.google.com/a/answer/14229414?hl=en) · [Google, codes SMTP](https://knowledge.workspace.google.com/admin/support/troubleshooting/gmail-smtp-errors-and-codes?hl=en) · [Google, Postmaster Tools v2](https://support.google.com/a/answer/14668346?hl=en) · [Google, balisage email](https://developers.google.com/workspace/gmail/markup/overview) · [Google, annotations Promotions](https://developers.google.com/workspace/gmail/promotab/overview) · [Yahoo, bonnes pratiques](https://senders.yahooinc.com/best-practices/) · [Microsoft, 550 5.7.515](https://support.microsoft.com/en-us/outlook/fix-ndr-error-550-5-7-515-in-outlook-com) · [Microsoft, Copilot Prioritize](https://support.microsoft.com/en-us/outlook/copilot-outlook/prioritize-my-inbox) · [Microsoft Defender, prompt injection](https://learn.microsoft.com/en-us/defender-office-365/step-by-step-guides/prompt-injection-protection-defender-for-office-365) · [Apple, postmaster iCloud](https://support.apple.com/en-us/102322) · [Apple, catégories Mail](https://support.apple.com/en-gb/guide/iphone/iphfe4a36baf/ios) · [Apple, Branded Mail](https://support.apple.com/guide/business/intro-to-branded-mail-abcb761b19d2/web) · [Orange postmaster](https://postmaster.orange.fr/index.html) · [La Poste postmaster](https://postmaster.laposte.net/) · [Free postmaster](https://postmaster.free.fr/) · [Signal Spam](https://www.signal-spam.fr/feedback-loop/)

**Études et données** : [Litmus, parts de marché des clients (juillet 2026)](https://www.litmus.com/email-client-market-share) · [Validity, Benchmark 2025](https://www.validity.com/wp-content/uploads/2025/03/2025-Benchmark-Report-FINAL.pdf) · [EmailTooltester, longueurs d'objet (août 2026)](https://www.emailtooltester.com/en/blog/email-subject-lines-character-limit/) · [MailerLite, benchmarks 2025](https://www.mailerlite.com/blog/compare-your-email-performance-metrics-industry-benchmarks) · [Klaviyo, benchmarks 2026](https://www.klaviyo.com/uk/blog/email-marketing-benchmarks-open-click-and-conversion-rates) · [Brevo 2025 via Email Rocks](https://email-rocks.com/chiffres-email-marketing-2025-brevo/) · [Klaviyo, IA et boîte de réception (mai 2026)](https://www.klaviyo.com/blog/ai-email-marketing-inbox-optimization) · [0DIN, injection dans Gemini](https://0din.ai/blog/phishing-for-gemini) · [Google, prompt injections sur le web (avril 2026)](https://blog.google/security/prompt-injections-web/)
