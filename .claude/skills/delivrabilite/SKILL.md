---
name: delivrabilite
description: Délivrabilité email 2026 — règles des messageries (Gmail, Microsoft, Yahoo, Orange, La Poste, Free, SFR), SPF/DKIM/DMARC (RFC 9989), désinscription un clic RFC 8058, Feedback-ID, warm-up, débits, codes de refus, monitoring (Postmaster, SNDS, Signal Spam), HTML/objet/préheader, IA des messageries, réactivation des inactifs, checklist pré-envoi. Utiliser avant tout envoi en masse, pour lire un taux de livraison/rebond/ouverture, choisir un domaine ou un débit, relire un HTML ou un objet, ou diagnostiquer un placement en spam (Mass Email, Cheffer, Sweego, Maildoso).
---

# Délivrabilité email 2026

> Guide complet de Camille (26/09/2026), avec toutes les sources : `references/guide-delivrabilite-2026.md`.
> Audit réel de notre domaine (26/09) : `/home/autoblog/outils-captures/mm-audit/audit_delivrabilite.md`.
> Voir aussi `.claude/skills/mass-email/`, `.claude/skills/anti-bot-clics/`, `.claude/skills/sweego/`.

## 1. Les trois couches (guide, intro)

Un email arrive en boîte de réception s'il coche : **(1)** une authentification alignée (SPF, DKIM,
DMARC, désinscription un clic), **(2)** un taux de plainte < 0,1 % (jamais ≥ 0,3 %), **(3)** un contenu
lisible par les filtres ET par les IA des messageries (texte HTML réel, premières lignes utiles).
Depuis nov. 2025 Gmail **rejette** (plus seulement filtrer) ; Microsoft depuis mai 2025 (`550 5.7.515`,
SPF **et** DKIM doivent passer) ; La Poste depuis sept. 2025 ; Orange exige DMARC et, au-delà de
1 000 mails/jour, un clic + `Feedback-ID` + preuve de consentement.

## 2. Règles à appliquer sans y penser

- **Plaintes** : cible < 0,10 % (Gmail), alerte 0,10 %, crise 0,30 % ; Yahoo et Orange 0,3 %.
- **Hard bounces** : ~0,2 % normal, **> 1 % = problème de liste ou d'import** (stopper).
- **Un `421` veut dire « ralentis »** : on espace, on ne renvoie jamais plus vite. `4xx` = retenter ;
  `5xx` utilisateur inconnu = supprimer, ne jamais retenter.
- **« Livré » ≠ boîte de réception.** Les ouvertures sont faussées par Apple MPP (55-60 %) :
  **piloter aux clics humains par fournisseur**, aux réponses et aux conversions.
- **Gmail « gros expéditeur »** : ~5 000/jour vers Gmail, compté sur le **domaine principal**
  (sous-domaines additionnés), statut **définitif**.
- **Nouveau domaine ou sous-domaine = ~6 semaines de chauffe** (M3AAWG) ; une IP dédiée seulement
  au-delà de ~50 000 mails/mois, et envoyée régulièrement.
- **Warm-up** : les plus engagés d'abord, répartition égale entre fournisseurs, plafonds par
  fournisseur au début (AWS : 150 vers Gmail le J1), **pause au premier 421 ou plainte**. Jamais de
  « chauffe artificielle » (fausses ouvertures, boîtes complices).
- **Débits de référence** (KumoMTA / Orange) : Gmail 5 connexions × 50 msg ; Outlook 5 × 50 ;
  Yahoo 20 msg/connexion, pause 2 h sur `[TS04]` ; iCloud 10 × 5 ; **Orange 2 connexions par IP**,
  100 msg/connexion, 100 destinataires/message.
- **Aucun texte caché hors préheader.** Microsoft Defender (sept. 2026) met en quarantaine le texte
  invisible ; toute instruction adressée à une IA = prompt injection = phishing.
- **Jamais d'emoji dans le nom d'expéditeur** ; dans l'objet, un seul, Emoji ≤ 12.0, sans ZWJ ni teinte.
- **Pas de faux « RE: » / « TR: »** ; objet en rapport avec le contenu (L34-5 CPCE).
- **Désinscription** : un clic RFC 8058 = POST sans redirection ni confirmation, effectif < 48 h,
  **idempotent** (Gmail « Gérer les abonnements » envoie des doublons) ; le GET affiche une page
  (option « recevoir moins »). Liens de désinscription valables indéfiniment.

## 3. Configuration cible (guide § 2)

| Élément | Cible 2026 |
|---|---|
| Domaines | un sous-domaine par flux (marketing ≠ transactionnel), même domaine organisationnel pour From, Return-Path, DKIM `d=`, liens, images, Reply-To lu |
| SPF | `~all` sur un domaine qui envoie (`-all` seulement pour ceux qui n'envoient rien), ≤ 8 lookups, ≤ 2 void lookups, pas de flattening, pas de `ptr` |
| DKIM | RSA 2048, `d=` sur notre domaine, rotation tous les 6 mois, `h=` inclut List-Unsubscribe + List-Unsubscribe-Post, sur-signature, jamais `l=`, `x=` ≤ 48 h |
| DMARC (RFC 9989) | `p=none` → `quarantine; t=y` → `quarantine` → `reject; sp=reject; np=reject`, avec `rua`. **Plus de `pct`, `rf`, `ri`** |
| En-têtes | `List-Unsubscribe` (HTTPS jeton opaque + mailto) + `List-Unsubscribe-Post: List-Unsubscribe=One-Click` ; `Feedback-ID: a:b:c:SenderId` stable ; `Message-ID` portant l'id de campagne |
| Tracking | sous-domaine à la marque en HTTPS (`clic.news.…`), une seule redirection, aucun raccourcisseur, texte du lien = destination |
| Monitoring | Google Postmaster Tools v2, Yahoo Sender Hub (Insights), SNDS/JMRP (IP dédiée), **Signal Spam** (seule boucle Orange/SFR/La Poste), La Poste via Validity, rapports DMARC |

## 4. HTML, objet, préheader, IA (guide § 5, 6, 8)

- HTML5, UTF-8 quoted-printable, version texte **fidèle** au HTML, **< 80 Ko** de HTML (Gmail coupe
  vers 102 Ko), lignes ≤ 998 caractères, **styles critiques en inline** (La Poste et SFR neutralisent
  `<style>` depuis 2025), ≥ 500 caractères de vrai texte (prix, date, code, CTA en texte, pas en image).
- Objet : l'essentiel dans **33 caractères**, 50 au total. Préheader < 90 caractères qui complète
  l'objet, puis espaceurs. **La première phrase visible = offre + date absolue + action** : c'est ce
  que les IA (Apple Intelligence, Gemini, Copilot) résument. Dates absolues (« lundi 5 octobre 2026
  à 23 h 59 »), conditions en bas, un objectif par email, inviter à répondre.
- JSON-LD Promotions (`DiscountOffer`, `PromotionCard`) dans le `<head>` : badge et date de fin dans
  l'onglet Promotions de Gmail.

## 5. Notre installation face au guide (constats du 26/09/2026)

Domaine d'envoi Mass Email : `news.leclientroi.email` (Sweego, IP partagée).

| Point | État | Action |
|---|---|---|
| DMARC | ✅ `p=reject` + rua (Cloudflare DMARC) | Retirer `pct=100` et `rf=afrf` (retirés par RFC 9989), ajouter `sp=reject; np=reject` sur leclientroi.email |
| SPF Return-Path `swg.news…` | `include:spf.swg-srv.net -all` | Guide : `~all` sur un domaine qui envoie (à valider avec Sweego) |
| DKIM | ✅ CNAME Sweego, 2048 bits | Vérifier sur un mail reçu (« Afficher l'original ») que `h=` couvre List-Unsubscribe(-Post) |
| Tracking | ✅ `t.news.leclientroi.email` → `t.sweego.co` | MAIS nos propres liens (désinscription, miroir, **page de rappel**) sont sur `mail.cheffer.email` : domaine organisationnel différent du From (M3AAWG) → prévoir un sous-domaine `…leclientroi.email` |
| List-Unsubscribe one-click | Codé (`sweego.envoyer_un(url_desinscription=)`), **pas encore en ligne** | Redémarrer le worker ; vérifier l'en-tête reçu |
| Désinscription GET | Désinscrivait sur un simple GET (scanner BNP) | Correctif prêt (GET = page, POST = action), à déployer |
| Feedback-ID | ❌ absent | Obligatoire chez Orange au-delà de 1 000/jour ; utile pour Postmaster (en-tête `headers` Sweego, ≤ 5 en-têtes perso) |
| Lien piège caché (anti-bot) | 1 px transparent en fin de mail | **Contraire à la règle « rien de caché hors préheader »** (Defender) → réévaluer, voir skill anti-bot-clics |
| Réputation | 🟠 domaine partagé avec la plateforme LeClientRoi (~16 % de rebonds durs sur 7 j), Microsoft ~0,4 % d'ouvertures | Sous-domaine réservé à Mass Email, chauffé ~6 semaines |
| Monitoring | ❌ ni Postmaster Tools, ni Yahoo Sender Hub, ni Signal Spam, ni SNDS | À ouvrir (Postmaster et Sender Hub : vérification DNS) |
| BIMI | Enregistrement sur leclientroi.email sans certificat (aucun effet Gmail) | Apple Business (gratuit) plus rentable pour l'iPhone |
| Consentement | Liste JAECOO de source tierce, phrase « vous êtes client… » | Risque CNIL (L34-5) et plaintes : documenter l'origine, corriger la phrase |
| Contenu JAECOO | 30,8 Ko, 6 767 caractères de texte, 5 images avec alt | ✅ poids et ratio ; vérifier objet (33 car.) et première phrase |
| Envois du 26/09 | 309 envoyés, 305 livrés, 4 rebonds (1,3 %), **0 ouverture humaine** | Signal d'indésirables : suivre les clics humains par fournisseur, pas les ouvertures |

## 6. Outils

Les scripts du guide (`audit_dns.py`, `lint_email.py`, `analyse_objet.py`, `dmarc_rua_resume.py`,
`generer_eml.py`, `segmentation_engagement.sql`, `desinscription_one_click.py`) **ne sont pas sur le
serveur Genesis** au 26/09/2026 (le guide les place dans un dossier `outils/` qui n'existe pas ici).
En attendant : `dig` (voir § 2 du guide, « Vérifier en 30 secondes »), `mass_mailing/infra/controle_html.py`
(analyse HTML à l'import), et l'audit de l'agent. Outils libres cités : parsedmarc, checkdmarc,
mailpit, rspamd.

**Toujours linter le vrai `.eml`** (Gmail → « Afficher l'original » → « Télécharger »), pas le HTML de
l'éditeur : l'ESP ajoute ses en-têtes, sa réécriture de liens et son pixel.

## 7. Checklists (guide § 11, résumé)

- **Une fois (puis chaque mois)** : sous-domaines alignés, SPF `~all` ≤ 8 lookups, DKIM 2048 +
  rotation, DMARC vers `reject` + `np`, tracking à la marque, endpoint RFC 8058, Feedback-ID,
  Postmaster / Sender Hub / Signal Spam, logo.
- **Chaque campagne (sur le BAT réel)** : objet 33/50, expéditeur stable sans emoji, préheader < 90,
  première phrase = offre + date + action, ≥ 500 caractères de texte, < 80 Ko, styles inline, version
  texte fidèle, aucun texte caché, aucun raccourcisseur ni http, option « recevoir moins »,
  cible = engagés (inactifs ≤ 5 % de la cible), test de résumé IA.
- **Après envoi (J+1 à J+7)** : codes de refus par fournisseur, clics humains par fournisseur vs
  moyenne des 5 dernières campagnes, taux de spam Postmaster < 0,10 %, plaintes Signal Spam / JMRP
  traitées comme désinscriptions, rapports DMARC.

## 8. Réactivation des inactifs (guide § 9)

Inactivité jugée sur les clics et signaux hors email (jamais sur l'ouverture seule). Segments A (0-30 j)
à E (> 365 j, plus d'envoi marketing). Inactifs en petits lots (≤ 5 % de la cible), les moins anciens
d'abord, Gmail à part ; séquence 3 emails (valeur → choix « recevoir moins » → dernière chance), puis
sunset. Réactivation attendue : 2 à 5 %.
