# Demande de délisting SURBL — leclient-roi.com

- Où : http://www.surbl.org/surbl-analysis → chercher `leclient-roi.com` → « Request delisting » (formulaire, réponse sous 24-72 h en général).
- Constaté le 2026-07-07 : `leclient-roi.com.multi.surbl.org` → 127.0.0.64 (liste ABUSE).
- En parallèle : ouvrir un ticket au support Maildoso (c'est leur infra d'envoi/warmup, ils ont l'habitude).

## Texte à coller dans le formulaire (EN)

Subject: Delisting request for leclient-roi.com (legitimate business domain)

Hello,

I am requesting the removal of leclient-roi.com from the SURBL ABUSE list.

leclient-roi.com is a secondary sending domain owned and operated by Le Client ROI,
a French B2B company (primary website: https://leclientroi.com — note that the
domain simply 301-redirects there, which is standard practice to protect the
primary domain's reputation, not a throwaway setup).

Facts about the domain:
- Registered on 2026-06-23 by our company; same ownership as leclientroi.com.
- DNS fully authenticated: SPF, DKIM (2048-bit) and a strict DMARC policy
  (p=reject; pct=100) are in place and passing.
- Email activity so far consists only of the mailbox warm-up service of our
  email infrastructure provider (Maildoso) and a handful of internal test
  messages to our own founder's address. No marketing or bulk email has been
  sent from this domain yet.
- All future mail will be low-volume, targeted French B2B correspondence with
  a working unsubscribe mechanism and a monitored reply address.

We believe the listing is a false positive triggered by the domain's young age
and its redirect to our primary site. We would appreciate a review and removal.

I am happy to provide any additional verification you may need.

Best regards,
Camille Afchain
Le Client ROI — https://leclientroi.com
contact@leclientroi.com

## Après le délisting

- Re-vérifier : `dig +short leclient-roi.com.multi.surbl.org` (vide = délisté).
- Relancer un mail-tester pour confirmer la disparition de URIBL_ABUSE_SURBL (−1.9 pts).

---

## Kit complet formulaire de removal (2026-07-08)

- WHOIS vérifié : REDACTED FOR PRIVACY (Dynadot, via Maildoso) → le champ « proof of ownership » est requis : screenshot du dashboard Maildoso (compte camille@leclientroi.com) montrant le domaine + la facture/receipt, infos de paiement masquées.
- Body source US-ASCII (quoted-printable, 1541 o) : template LCR agence-marketing/first, généré dans le scratchpad session (voir conversation) — régénérable via email_templates + quopri.
- IP d'envoi : pool spf.pinkproof.net (18 IP, cf. section précédente), IP observée 169.255.56.72.
- Politique anti-spam : page à publier sur leclientroi.com (URL cible proposée : https://leclientroi.com/politique-anti-spam) — texte bilingue ci-dessous, publiable via le CMS emdash (pipeline LCR existant).

### Texte de la politique anti-spam (à publier tel quel)

Politique anti-spam / Anti-Spam Policy — Le Client ROI

FR — Le Client ROI s'engage à ne jamais promouvoir ses sites web (leclientroi.com, leclient-roi.com) par des messages non sollicités envoyés en masse. Nos communications par email se limitent à : (1) des emails transactionnels et de service ; (2) des newsletters envoyées uniquement aux personnes inscrites ; (3) une correspondance professionnelle individualisée adressée à des contacts B2B dans le respect du cadre légal français et européen (art. L.34-5 CPCE, lignes directrices CNIL) : pertinence professionnelle du message, identification claire de l'expéditeur, et moyen simple et gratuit de s'opposer à toute nouvelle sollicitation. Toute demande de désinscription est honorée immédiatement et définitivement (liste de suppression). Nous n'autorisons aucun affilié ni tiers à promouvoir nos sites par email. Pour signaler un abus : contact@leclientroi.com.

EN — Le Client ROI never advertises its websites (leclientroi.com, leclient-roi.com) through unsolicited bulk messages. Our email communications are limited to: (1) transactional and service emails; (2) newsletters sent only to opted-in subscribers; (3) individualized professional correspondence addressed to B2B contacts in compliance with the French and EU legal framework (art. L.34-5 CPCE, CNIL guidelines): professional relevance, clear sender identification, and a simple free opt-out honored immediately and permanently (suppression list). No affiliate or third party is authorized to advertise our websites by email. To report abuse: contact@leclientroi.com.

### Champ « Description of web site and organization »

Le Client ROI (https://leclientroi.com) is a French SaaS company founded and operated in France. It provides SMS marketing, RCS messaging and local communication tools to French SMEs and local businesses (restaurants, retail, services). The company operates more than 10 million SMS per year for 500+ business customers. The domain under review, leclient-roi.com, hosts no content of its own: it is a secondary domain owned by the same company, permanently 301-redirected to the primary website, and used exclusively as a sending domain for low-volume professional email — a standard practice to keep transactional/website traffic and outbound email on separate domains. It is fully authenticated with SPF, DKIM (2048-bit) and a strict DMARC policy (p=reject; pct=100).

### Champ « Explanation »

The web site is not advertised through unsolicited bulk messaging by us or by anyone else. Since the domain's registration (2026-06-23), the only email activity has been the automated mailbox warm-up service of our infrastructure provider (Maildoso) and a handful of internal test messages sent to our own founder's mailbox. No marketing campaign has been sent from this domain yet. Going forward, the domain will carry only individualized, low-volume professional correspondence addressed to publicly listed French business contacts, in compliance with the French/EU B2B framework (art. L.34-5 CPCE and CNIL guidelines): professional relevance of the message, clear identification of the sender (company name, physical contact details, phone number), and a visible, free, one-click opt-out in every message, honored immediately through a permanent suppression list. We work with no affiliates and no third-party mailers; nobody else is authorized to send email mentioning our web sites. Our published anti-spam policy explicitly prohibits advertising our web sites through unsolicited bulk messages.
