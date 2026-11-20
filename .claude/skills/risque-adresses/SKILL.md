---
name: risque-adresses
description: Agent « adresses à risque » de Mass Email — prédit, avant l'envoi, la probabilité qu'une adresse rebondisse en HARD (même validée par Mailnjoy), classe les rebonds Sweego (hard / soft / refus liés à l'IP) et alimente la liste noire globale. Utiliser pour lire un taux de rebond, répondre à Sweego sur les hard bounces, décider quoi écarter d'une liste, expliquer pourquoi une adresse « valide » a rebondi, ou réapprendre le modèle.
---

# Adresses à risque et rebonds (Mass Email)

Créé le 30/09/2026, après que Sweego a signalé « beaucoup trop de hard bounces » alors que les
listes Mass Email étaient nettoyées par Mailnjoy.

## 1. Ce que l'enquête du 30/09 a établi

1. **Le compteur « hardbounce » de Sweego mélange trois choses.** Sur 5 516 échecs (août-septembre) :
   - **3 620 vraies adresses mortes** : 550 5.1.1 inconnue, 5.5.0 indisponible, 554.30 désactivée,
     5.2.1 bloquée pour inactivité, déjà dans la liste de suppression de Sweego ;
   - **1 672 refus liés à NOTRE IP**, que Sweego étiquette pourtant « hard » : Free « 451 too many
     errors from your ip », Orange « 421 Service refusé OFR005 », Microsoft « 451 4.7.652 ».
     L'adresse est bonne : **jamais en liste noire** ;
   - **198 soft**, à cause du destinataire : boîte pleine, boîte inactive.
2. **97 % de ces échecs ne viennent PAS de Mass Email.** Ils viennent de la **plateforme LeClientRoi**
   (serveur 188.245.184.71, expéditeur `lcr@news.leclientroi.email`). Elle partage le **même compte
   Sweego**, le **même domaine** et la **même IP 185.255.28.17**. Ce sont les campagnes des clients
   (« Laverie des sneakers », « Inauguration Omoda / Kia Cambrai »…), envoyées sur des listes jamais
   passées par Mailnjoy : **16,6 % de hard**, avec des pics à 58 % (20/09). Elle réécrit même à des
   adresses déjà supprimées (362 « DROP[suppressed] »).
3. **Mass Email seul : 5 hard + 2 soft sur 1 919 envois (0,3 %)**. Le nettoyage marche.
4. **Mailnjoy « VALID/SAFE » : 0 hard sur 1 869 adresses, SAUF chez Yahoo/AOL (5 sur 50 = 10 %).**
   Une vérification SMTP demande « acceptes-tu cette adresse ? » sans envoyer. Yahoo et AOL disent
   oui à tout, puis refusent les comptes désactivés au moment de l'envoi (« 554 30 This mailbox is
   disabled »). Aucun vérificateur ne peut voir ça : c'est un **angle mort**, pas une erreur de Mailnjoy.
5. **Le facteur n° 1, c'est la messagerie.** Taux de hard sur 29 186 adresses au sort connu :

   | Messagerie | Hard |
   |---|---|
   | gmail.com, icloud.com | ≈ 1,4 % |
   | hotmail / live / outlook | ≈ 5 % |
   | orange.fr | 15 % |
   | yahoo.fr | 19 % |
   | wanadoo.fr | 25 % |
   | yahoo.com | 28 % |
   | free.fr | 30 % |
   | sfr.fr | 33 % |
   | laposte.net | 35 % |
   | aol.com | 36 % |
   | bbox.fr | 39 % |
   | neuf.fr | 41 % |

   Raison : les boîtes des fournisseurs d'accès ferment quand on change de box, et Yahoo/AOL
   désactivent les comptes inactifs. Gmail ne ferme presque jamais.
   La forme de l'adresse (chiffres, points, année) ne compte presque pas.

## 2. Le code

| Fichier | Rôle |
|---|---|
| `mass_mailing/jobs/rebonds.py` | `classer()` classe un échec en hard / soft / expediteur / technique (testé sur des cas réels) ; `importer()` relit les logs Sweego de **tout le compte** (toutes les heures dans le worker, 3 jours glissants) → table `rebonds` + liste noire globale `suppressions` (`hard_bounce`, `soft_bounce`) ; `stats_campagne()` |
| `mass_mailing/jobs/risque_adresses.py` | Bayes naïf lisible ; `apprendre()` chaque jour (worker) → table `risque_modele` ; `scorer_campagne(id)` en lecture seule |
| `tests/test_rebonds.py`, `tests/test_risque_adresses.py` | tests |
| API | `GET /stats/rebonds`, `/stats/serie` (+ hard, soft, liste_noire), `/campaigns/{id}/rebonds`, `/campaigns/{id}/risque` |
| Écran | accueil : cartes Soft bounces, Hard bounces, Liste noire globale ; fiche campagne : panneau Soft / Hard / Refus liés à l'IP |

**Règles de la liste noire :**
- hard → `hard_bounce`, définitif ;
- soft (boîte pleine ou inactive) → `soft_bounce`, **quarantaine de 60 jours** ;
- refus liés à l'IP → **jamais** en liste ;
- une raison plus forte n'est jamais rétrogradée (plainte > désinscription > hard > soft) ;
- un soft passe en hard si un rebond définitif arrive ensuite.

Le moteur de capacité (`capacite.corriger_suppressions`) retire les suppressions créées à tort sur
un 4xx. Il laisse les `soft_bounce` en place (vérifié le 30/09).

## 3. Le modèle de risque

`risque = P(hard | domaine, messagerie, verdict Mailnjoy (+ angle mort Yahoo), chiffres, séparateurs)`

« Déjà ouvert » a été retiré à la revue du 30/09 : il fuyait la cible. Le modèle réapprend chaque nuit à 3 h.

- Appris sur nos envois réels (Sweego, tout le compte). Lissage de Laplace. Un domaine vu moins de
  30 fois est remplacé par sa messagerie.
- Le verdict Mailnjoy est un facteur **à part chez Yahoo/AOL** : `VALID/SAFE·yahoo`.
- Mesure du 30/09 après la revue (sans fuite), sur des adresses jamais vues : **AUC 0,80**. Hard réels par niveau :

  | Niveau | Seuil | Hard réels |
  |---|---|---|
  | faible | < 5 % | 2,8 % |
  | moyen | < 15 % | 8,9 % |
  | élevé | < 30 % | 19 % |
  | très élevé | ≥ 30 % | 35 % |

  Écarter « très élevé » retire 14 % d'une liste brute et **43 % de ses hard**. Écarter à partir
  d'« élevé » retire 29 % de la liste et **72 % des hard**.
- Exemples :

  | Adresse | Risque |
  |---|---|
  | Gmail validé | 0 % |
  | laposte.net validé | 0,4 % |
  | laposte.net non vérifié | 37 % |
  | neuf.fr non vérifié | 43 % |
  | Yahoo validé | 22 % (10 % constaté : le modèle est prudent) |
  | AOL validé | 40 % |

**Usage recommandé (à décider avec Camille avant d'en faire une règle d'envoi) :**
- ne jamais envoyer une liste **non vérifiée** ;
- Yahoo/AOL **validés** : les envoyer à part, en petite quantité, en dernier (l'agent de routage
  retire déjà automatiquement une messagerie à ≥ 5 % d'adresses mortes) ;
- sur une liste brute, écarter « très élevé ».

## 4. Répondre à Sweego

Leur dire, chiffres à l'appui :
1. leur « hardbounce » inclut des 4xx liés à l'IP (Free, Orange, Microsoft) ;
2. le volume vient de la plateforme LeClientRoi, pas de Mass Email (0,3 %) ;
3. nous importons désormais leurs échecs dans notre liste noire globale.

**Le vrai correctif est côté plateforme LeClientRoi :**
- valider ses listes avant envoi ;
- respecter les suppressions ;
- idéalement, un domaine et une IP séparés de Mass Email. La même IP fait payer à Mass Email les
  erreurs de l'autre (Free : « too many errors from your ip »).
