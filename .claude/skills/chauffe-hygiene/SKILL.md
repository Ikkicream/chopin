---
name: chauffe-hygiene
description: Carnet VIVANT de chauffe (warm-up IP / domaine / adresse) et d'hygiène de liste de Mass Email — la méthode réellement appliquée par la plateforme, les seuils, les leçons validées campagne après campagne, et le journal généré chaque nuit. LIRE au début de toute session Mass Email, avant de lancer, router ou juger une campagne, avant de lire un taux d'ouverture, et après chaque bilan de nuit pour en tirer les leçons.
---

# Chauffe et hygiène — le carnet de Mass Email

> Créé le 20/10/2026 à la demande de Camille : « sur le serveur, pour que tu apprennes de chaque campagne ».
> - **Journal automatique** : `references/journal-campagnes.md`, réécrit chaque nuit à 5 h (Paris) par
>   `mass_mailing/jobs/bilan_campagnes.py` (photo par campagne dans `mass_mailing.bilans_campagne`).
> - **Leçons** : § 5 ci-dessous, écrites À LA MAIN par Claude, seulement quand les chiffres les prouvent.
> - Théorie complète : `../delivrabilite/`, `../pilotage-delivrabilite/`, `../anti-bot-clics/`, `../mass-email/`.

## 0. Routine à chaque session
1. Lire le journal (`references/journal-campagnes.md`) : alertes, « Qui ouvre », rebonds, plaintes.
2. Comparer aux leçons du § 5 : une leçon contredite par 2 campagnes est révisée ou retirée.
3. Écrire une leçon nouvelle au § 5 seulement avec : la campagne, les chiffres, l'effectif, le niveau de preuve.
4. Rendre compte à Camille en 📋 Bilan (court, un dossier à la fois).

## 1. Chauffe : ce que la plateforme applique (code, pas théorie)
| Étage | Règle | Où |
|---|---|---|
| Adresse expéditrice | Plan par semaines : **400 → 800 → 1 600 → 2 000/jour** (Zylio, départ 14/10/2026), plafonné par le fournisseur si besoin | `expediteurs.warmup_plan`, `clients.plafond_du_jour` |
| Heure | Budget de la vague = plafond du jour × part de la journée écoulée dans la fenêtre | `routage._borner_warmup` |
| Messagerie (file) | Départ prudent par webmail (débit/h, plafond J1, hausse/jour : Gmail 100/300/×1,15 ; Outlook 50/150/×1,10 ; autres 40/100/×1,10 ; B2B 100/150/×1,15) | `capacite.PROFILS` |
| Hausse | **Une seule par jour**, seulement si 24 h saines et ≥ 20 tentatives | `capacite.decider` |
| Freinage | 4xx de limitation → débit ÷ 2 ; différés > 5 % (1 h) ou rebonds durs > 2 % (24 h) → × 0,7 | idem |
| Pause | Plaintes > 0,3 % ou ≥ 2 refus critiques (politique / spam / auth) en 24 h → pause, reprise à 50 % après 48 h | idem |
| Fenêtre | Client : lun-ven 9 h-18 h étalé (réglable par campagne) ; interne : 8 h-22 h | `envoi.fenetre` |
| Priorité | Messageries qui ouvrent ≥ 5 % (ouvertures **humaines**, plus le taux brut depuis le 21/10) à plein débit, les autres à 30 % ; < 3 % restent à 30 % | `routage.planifier`, `_taux_par_groupe` |
| Files pro | Domaines pro rangés par leur VRAI serveur (MX) : Google Workspace, Microsoft 365, passerelles (Proofpoint, Mimecast…), OVH, autres | `infra/mx.py`, `capacite.groupe_de` |
| Placement | File « spam probable » (0 humain, ou < 30 % du taux humain des autres, ≥ 50 livrés sur 7 j) → **sonde 2 mails/vague**, servie en premier | `jobs/placement.py` |
| Vague | ≤ 10 % par domaine destinataire ; une file ≤ 2 × sa part de la réserve ; domaines déjà lus et adresses à faible risque d'abord | `routage.choisir`, `plafonds_equilibre`, `_ordre_de_passage` |
| Domaine coupé | 1 plainte, ou ≥ 3 rebonds définitifs faisant ≥ 10 % de ses envois | `routage.domaines_a_bloquer` |
| Avant chaque vague | Bilan de la vague d'avant dans le journal (`routage.analyse`) | `routage.analyser_vague_precedente` |

Interdits à vie : warm-up synthétique (Heatwave & co.), envoi groupé (1 destinataire = 1 mail).

## 2. Hygiène de liste
- Import : validation Mailnjoy (ou fichier « déjà vérifié »), doublons et syntaxe retirés, exclusions (liste noire globale, déjà testés, hors cible).
- Rebond dur ou plainte → suppression définitive (liste noire globale de l'espace).
- Messagerie retirée automatiquement de la campagne si ≥ 5 % d'adresses mortes sur ≥ 10 envois (`routage.exclusions_auto`).
- Désinscription un clic (RFC 8058) dans chaque mail ; pied avec raison sociale et adresse postale.

## 3. Seuils d'alerte du journal (`bilan_campagnes.SEUILS`)
Rebonds durs > 2 % des envoyés · plaintes > 0,3 % des livrés · désinscriptions > 1 % · plus de 40 % des
ouvertures en moins de 60 s (le taux brut ment).

## 4. Lire une ouverture : qui ouvre vraiment
Chaque ouverture Resend porte une IP et un logiciel. `mass_mailing/infra/ouvertures.py` les classe :
- **humain sûr** : box ou réseau d'entreprise (Orange, Free, SFR, Bouygues…), Outlook bureau (« ms-office »), proxy d'images Gmail (« ggpht ») ;
- **Apple Mail** : « Mozilla/5.0 » seul via Cloudflare / Fastly / Akamai = préchargement automatique (lu ou non : inconnu) ;
- **machine** : antivirus et passerelles (Microsoft 365, scanner Google 74.125.x « Edge 12 », Amazon, Proofpoint…).
Le taux à piloter = **humains sûrs** (+ Apple en fourchette haute). Le taux brut ne sert qu'à détecter les machines.
Les clics suivent la même logique (verdict anti-robots `clicks.verdict`, skill `anti-bot-clics`).

## 5. Leçons validées (à la main, avec preuve)
### L1 — 20/10/2026 · Kick off Zylio (B2B immobilier, Resend) · preuve FORTE
- 138 ouvertures brutes (29,3 %) = **24 humains sûrs (5,1 %)** + 28 Apple Mail + **86 machines** (Microsoft 365 51, scanner Google 30, Amazon…).
- Les réseaux d'agences (Century 21, Orpi, Foncia) sont derrière des antivirus : ouvertures en quelques secondes, aucune humaine.
- Conséquence : ne JAMAIS juger une campagne B2B, ni prioriser une messagerie, sur le taux brut.
### L2 — 20/10/2026 · Kick off Zylio · preuve MOYENNE (à confirmer)
- Domaines pro 23 humains sûrs / 388 livrés ; adresses perso (Gmail, Orange, SFR, Yahoo) 1 / 83.
- Domaines à 1 seul contact ouvrent plus que les réseaux (5+ contacts) — écart non significatif sur 472 envois.
### L3 — 21/10/2026 · Kick off Zylio, premiers clics suivis (Resend) · preuve FORTE
- 33 clics en 20 à 80 s après la livraison, 17 destinataires (Century 21, Nexity, Foncia…) : **100 % robots**.
- Microsoft 4.251.36.x visite TOUS les liens, désinscription comprise, et sa signature navigateur est un Windows ordinaire :
  seule l'IP (whois MSFT) le trahit. Règles ajoutées dans `jobs/clics.py` : IP de centre de données ; contenu + désinscription
  dans la même visite. La visite du lien de désinscription ne désinscrit pas (confirmation requise) : 0 perte.
- Conséquence : un « clic » B2B n'est un signal que s'il vient d'une box / d'un réseau d'entreprise, plusieurs minutes après.
### L4 — 21/10/2026 · Kick off Zylio, après-midi tout Gmail · preuve FORTE
- 456 mails vers Gmail en un après-midi : **2 vraies ouvertures sur 501 livrés (0,4 %)** contre 5,8 % ailleurs ; le robot Gmail
  (IP Google 66.249 / 74.125, « Chrome/42 ») ouvre chaque mail **3 s** après la livraison. Mail test de Camille : livré, introuvable hors Spam.
- Google Workspace (orpi.com…) : 1,0 % → même filtre, même verdict. Orange 11,6 %, OVH 12,3 %, passerelles 6,8 % : boîte probable.
- Causes côté moteur : (1) priorité sur l'ouverture brute (le robot Gmail = 18 %) ; (2) les agences B2B en PAUSE depuis 12 h 14
  car le conseil type de Resend contient « reputation » → lu comme refus anti-spam ; (3) aucune règle par domaine.
- Conséquence : un fournisseur se juge à ses ouvertures humaines comparées aux autres, jamais au brut ; un rebond Resend se classe
  par son type (`categorie_resend`), jamais par les mots de son texte.
### À vérifier
- PIRAINO (interne, Sweego) : Gmail 87 % « humain » selon la règle des 60 s → impossible ; Sweego ne donne pas l'IP
  de l'ouverture : chercher ce qui ouvre (proxy Gmail qui précharge ?) avant toute leçon B2C.
