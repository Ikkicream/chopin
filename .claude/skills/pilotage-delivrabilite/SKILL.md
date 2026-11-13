---
name: pilotage-delivrabilite
description: Pilotage adaptatif de la délivrabilité (contrôle de congestion par file) — apprendre à chaque campagne, par IP d'envoi + domaine d'identité + type de flux + messagerie destinataire, une capacité opérationnelle (max/jour, max/heure), à partir des réponses SMTP (2xx/4xx/5xx), plaintes, désinscriptions et engagement ; augmenter lentement quand c'est sain, réduire nettement au premier signal. Utiliser pour tout calcul de volume ou de cadence d'envoi Mass Email, l'onglet « Capacité » de la page d'accueil, l'ajout d'une nouvelle IP d'envoi, la lecture d'un code SMTP, ou pour préparer le routage intelligent (vagues par messagerie).
---

# Pilotage adaptatif de délivrabilité — adaptation Mass Email

> Document de référence de Camille (27/09/2026), intégral : `references/skill-source.md`.
> Voir aussi `delivrabilite/`, `mass-email/`, `hetrixtools/`, `sweego/`.

## 1. Règles non négociables (source § 2, 3.5, 14)

1. **Aucun quota publié par IP** : ne jamais écrire « La Poste accepte X mails/jour de telle IP ». On écrit :
   « capacité **apprise** sur nos envois » et on marque clairement ce qui est une **hypothèse**.
2. **Débit autorisé = min(courbe de chauffe, capacité apprise, limite de risque, volume qualifié disponible)**.
   La courbe de chauffe est un **plafond**, jamais un objectif.
3. **Une file par destination** : un incident chez Orange ne ralentit jamais Gmail.
4. **Augmenter lentement (+10 à +20 %), réduire nettement (−50 %)**, pause au signal sévère.
5. Les **ouvertures** sont un signal secondaire (Apple MPP, scanners) ; les plaintes, rebonds définitifs,
   refus temporaires et clics humains pèsent plus.
6. Jamais pour contourner une protection, relancer un désinscrit/plaignant, ou chauffer avec une liste douteuse.

## 2. Ce que Sweego permet (et ne permet pas)

Sweego est un **ESP** : on ne pilote **ni les connexions SMTP, ni les retries** (Sweego les gère, avec ses
propres files par messagerie : `Sender/orange`, `Sender/yahoo_us`, `Sender/microsoft`…). Nos leviers :
**volume par file et par heure** (vagues), **heure d'envoi**, **choix des destinataires**, **pause d'une file**.

Données disponibles par message (webhook dédié `mass-email` → `webhook_events`) :
- `details` : `ACCEPTED` / `REJECTED[…]` / différé, **`src=<IP d'envoi>`**, file Sweego `Sender/<zone>`,
  `mx=<serveur destinataire>`, réponse SMTP complète ; `response_code` sur les rebonds ;
- `domain_from` (domaine d'identité / DKIM), `campaign_type` (market/newsletter), Return-Path `swg.<domaine>` ;
- événements : `delivered`, `soft_bounce` / `soft-bounce` (4xx), `hard_bounce` (5xx), `complaint`,
  `list_unsub`, `email_opened`, `email_clicked` (voir anti-bot pour le tri robot/humain).

⚠️ L'IP `185.255.28.17` est **partagée** avec d'autres clients Sweego : la capacité apprise ne reflète que
NOTRE trafic ; ce qu'on chauffe vraiment, c'est **notre domaine** auprès de chaque messagerie.

## 3. Clé de file (source § 4.1 adaptée)

```text
IP d'envoi (src=) + domaine d'identité (domain_from / DKIM) + type de flux (campaign_type) + groupe messagerie
```
Groupes : gmail, microsoft (outlook/hotmail/live/msn), yahoo (yahoo/aol/ymail), orange (orange/wanadoo),
laposte, free, sfr (sfr/neuf/club-internet), icloud, bouygues, gmx, **autres** (long tail B2B, prudent).
**Une nouvelle IP ou un nouveau domaine d'identité crée automatiquement ses propres files** (chauffe à zéro).

## 4. Taxonomie SMTP (source § 6.4) — `jobs/capacite.py` `classer_reponse()`

`accepted`, `transient_rate_limit` (421/451 4.7.x, « rate », « too many », « throttl », `TS0x`, `4.7.650`,
`4.7.28`, `OFR_104/109/988-990`), `transient_server_busy`, `transient_greylisting`, `transient_mailbox_full`,
`transient_unknown`, `permanent_invalid_recipient` (5.1.1, user unknown), `permanent_invalid_domain` (5.1.2),
`permanent_policy_or_spam` (5.7.1 spam/policy/blocked, `OFR_506/536`, `5.7.515`), `permanent_authentication`
(5.7.26/27/30/32/40, DMARC/SPF/DKIM), `permanent_content_or_url`, `permanent_unknown`.

## 5. Profils de départ (source § 9, valeurs basses = prudentes)

| Groupe | Débit initial | Plafond jour J1 | Hausse |
|---|---|---|---|
| gmail | 100/h | 300 | +15 %/jour sain |
| microsoft | 50/h | 150 | +10 %/jour |
| yahoo | 50/h | 100 | +10 %/jour |
| orange, laposte, free, sfr | 40/h | 100 | +10 %/jour |
| icloud, bouygues, gmx | 40/h | 100 | +10 %/jour |
| autres (long tail B2B) | 100/h (total) | 150 | +15 %/jour |

Fenêtre d'envoi Mass Email : **8h-22h** (Camille, 27/09) → max/jour ≤ débit/h × heures de la fenêtre.

## 6. Décisions (source § 7) — une fois par évaluation, par file

- **Critique** (≥ 2 refus politique/spam/authentification sur 24 h, ou plaintes > 0,3 %) → `paused`.
- **Freinage explicite** (≥ 1 `transient_rate_limit` sur 1 h) → débit × 0,5, `throttled`.
- **Dégradation** (différés > 5 % sur 1 h, ou rebonds durs > 2 % sur 24 h) → × 0,7, `cautious`.
- **Sain** avec échantillon suffisant (≥ 20 tentatives sur 24 h) → au plus **une hausse par jour** :
  × 1,15 (gmail, autres) ou × 1,10, borné par le plafond de chauffe ; `warming` puis `stable`.
- **Capacité apprise** = plus gros volume horaire **accepté sans signal** observé (elle ne baisse qu'après incident).
- Chaque décision est écrite au format § 15 (file, fenêtre, métriques, décision, ancien → nouveau, motif,
  confiance, hypothèse) dans `capacite_decisions`.

## 7. Où c'est (27/09/2026)

- `mass_mailing/jobs/capacite.py` : ingestion des réponses (webhook → `smtp_reponses`), états
  `capacite_files`, décisions `capacite_decisions`, `tableau()` pour l'écran. Worker : toutes les 15 min.
- Écran : page d'accueil Mass Email, onglet **« Capacité »** : par IP, le max/jour et max/heure
  recommandés aujourd'hui ; par messagerie, l'état, le jour de chauffe, les taux 24 h et la dernière décision.
- Suite prévue : l'agent de routage (vagues par messagerie, bilan à +1 h, meilleure heure) consomme ces
  capacités — il n'envoie jamais au-delà de `max_aujourdhui`.
