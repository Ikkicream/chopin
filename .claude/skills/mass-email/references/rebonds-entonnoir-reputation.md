# Rebonds, liste noire globale, risque d'adresse, entonnoir, réputation (30/09/2026)

Documentation technique du lot livré le 30/09/2026. Voir aussi le skill `risque-adresses` (le pourquoi,
les chiffres de l'enquête) et `delivrabilite/references/cold-email-m3aawg-heatwave.md`.

## 1. Vue d'ensemble

```
Sweego (logs de TOUT le compte)
   │  toutes les heures (worker)             chaque jour (worker)
   ▼                                          ▼
jobs/rebonds.importer(jours=3) ──► rebonds ──► jobs/risque_adresses.apprendre() ──► risque_modele
   │ classer() : hard / soft / expediteur / technique
   ▼
suppressions (scope global) : hard_bounce, soft_bounce   ← relue avant chaque lot (envoi.envoyer_lot)
   │
   ▼
API : /stats/rebonds · /stats/serie · /campaigns/{id}/rebonds · /campaigns/{id}/entonnoir · /campaigns/{id}/risque
   ▼
UI : cartes Soft / Hard / Liste noire (accueil) · panneau Soft / Hard / Refus IP (fiche) · colonne Performance = entonnoir
```

## 2. `jobs/rebonds.py`

| Élément | Rôle |
|---|---|
| `classer(texte, code, type_sweego)` | Fonction pure : réponse SMTP → `(famille, cause)`. L'ordre des motifs compte : technique → déjà supprimée → **refus liés à l'expéditeur AVANT les motifs d'adresse** (« too many errors », 4.7.65x, « Service refusé OFR… ») → inactivité/désactivée → soft (4.2.1, boîte pleine) → domaine invalide → inconnue → politique/spam. Sinon : 5xx = hard, 4xx = expediteur. |
| `origine_de(ip, campaign_id)` | `mass_email` (campagne `mm-…` ou IP 204.168.186.159), `plateforme_lcr` (188.245.184.71), `autre`. |
| `importer(jours, debut)` | `POST /logs` Sweego (`status: undelivered`) par domaine d'envoi, 500 par page ; un 422 = domaine sans log, on passe. Upsert dans `rebonds` (clé `swg_uid`), puis `alimenter_liste_noire()`. |
| `alimenter_liste_noire()` | hard → `hard_bounce` (un `soft_bounce` existant est promu) ; soft → `soft_bounce` (rien si une ligne existe). **Les refus `expediteur` n'entrent jamais.** Plainte et désinscription ne sont jamais rétrogradées. |
| `stats_campagne(id)` | hard / soft / expediteur + causes, pour la fiche. |
| Schéma | table `rebonds`, index `email_hash` et `campagne` ; contrainte `suppressions_reason_check` élargie à `soft_bounce`. |

Lancement à la main : `sudo -u autoblog python3 mass_mailing/jobs/rebonds.py 2026-08-01`.
Sweego refuse (422) une fenêtre trop ancienne : partir au plus tôt du 1er août.

## 3. `jobs/risque_adresses.py`

| Élément | Rôle |
|---|---|
| `facteurs(email, mailnjoy, deja_ouvert)` | domaine, messagerie (`capacite.groupe_de`), verdict Mailnjoy (**suffixé `·yahoo` pour Yahoo/AOL**, angle mort), déjà ouvert, chiffres, séparateurs. |
| `entrainer(donnees)` | Bayes naïf, lissage de Laplace (α = 2) ; un domaine vu moins de 30 fois cède la place à sa messagerie. |
| `probabilite(modele, f)` | → `(p, [(facteur, multiplicateur)])` ; la messagerie est ignorée quand le domaine a son propre poids (pas de double compte). |
| `evaluer` / `auc` | Découpage 70 / 30, AUC par rangs, taux réels par niveau. |
| `apprendre()` | Relit Sweego + verdicts Mailnjoy (`public.contacts.mailnjoy_check`, `recipients.validation_provider_status`) → `risque_modele` (version, modèle, évaluation). Worker : une fois par jour. |
| `scorer_campagne(id)` | Lecture seule : niveau par destinataire restant, hard attendus. **Ne décide rien** : aucun envoi n'est bloqué par le modèle aujourd'hui. |

Niveaux : faible < 5 % ≤ moyen < 15 % ≤ élevé < 30 % ≤ très élevé. Mesure du 30/09 après revue : AUC 0,80 (« déjà ouvert » retiré, voir § 9). Apprentissage chaque nuit à 3 h.

## 4. L'entonnoir (`api/routes.py`)

`ENTONNOIR_SQL` = sous-requête LATERAL sur `recipients` de la version de cible courante ; `_entonnoir()` la met en forme.

| Étape | Calcul |
|---|---|
| Importés | `import_status = 'imported'` (doublons / syntaxe à part) |
| − écartés par Mailnjoy | `eligibility_status = 'excluded'` et raison ∈ risky, unknown (risquées), invalid, disposable (invalides), role, error (génériques) |
| = Retenus par Mailnjoy | importés − écartés |
| − autres exclusions | `envoye_en_test`, `hors_cible_b2c`, `suppressed` (liste noire) |
| = Éligibles | `eligibility_status = 'eligible'` |
| − en attente | éligibles encore `pending` / `queued` (réserve du routage) |
| = Envoyés | `submitted`, `delivered`, `bounced` (+ refus Sweego `rejected` / `failed` à part) |
| − non délivrés | `bounced` sans `delivered_at` ; détail hard / soft / IP par jointure sur `rebonds` (campagne `mm-<id>`) |
| = Délivrés | `delivered_at IS NOT NULL` |

La liste des campagnes joint la même sous-requête et regroupe ses colonnes sous la clé `entonnoir`
(les colonnes brutes sont retirées par la regex `AS (\w+)` sur `ENTONNOIR_SQL`).

## 5. Réputation d'envoi (`infra/hetrix.py`)

- `etat_moniteur(m)` : `propre`, `listee`, `reseau`, `non_surveille`.
- **`reseau` = listé UNIQUEMENT sur `LISTES_RESEAU`** (UCEPROTECT niveaux 2 et 3). Ces listes inscrivent tout le
  réseau de l'hébergeur, pas notre IP : c'est un avertissement, sans blocage. Le 30/09, le niveau 3 avait suspendu
  le routage d'Omoda.
- Préflight (`envoi.preflight`) : `listee` = bloquant ; `reseau` = avertissement non bloquant.
- Routage (`routage.vague`) : suspend seulement sur `listee`.
- UI : `listeBloquante()` / `reseauSeul()` dans `_surveillance.tsx`. Cette copie de `LISTES_RESEAU` doit rester
  alignée avec la liste du serveur.

## 6. Plaintes et heure d'ouverture (`jobs/envoi.synchroniser`)

- Une plainte reçue par **webhook** marque `recipients.complained_at` et crée une suppression `complaint`
  globale. Avant le 28/09, seul le drapeau `spam` des logs était lu, et la plaignante n'était pas bloquée.
- `opened_at` = premier `email_opened` / `email_clicked` non-proxy du webhook (avant : l'heure de livraison).

## 7. Interface (`genesis-ui/src/app/mass-email/`, dossier NON versionné)

- `page.tsx` : 2e rangée de cartes (Soft bounces, Hard bounces, Liste noire globale). La carte Envoyés reprend l'entonnoir cumulé.
- `[id]/page.tsx` : panneau Soft / Hard / Refus liés à l'IP ; carte Envoyés = entonnoir ; « Écartés avant départ » détaillé.
- `_performance.tsx` : colonne Performance = entonnoir (barre à l'échelle des importés, popover étape par étape).
- `_surveillance.tsx` : badge orange « réseau Sweego » pour UCEPROTECT 2/3.
- Sauvegardes : `/home/autoblog/sauvegardes/mass-email-*-20260930*`.

## 8. Tests

`cd /home/autoblog/genesis/mass_mailing && python3 -m unittest tests.test_rebonds tests.test_risque_adresses tests.test_reputation tests.test_routage tests.test_capacite tests.test_balayage tests.test_score_clics`

## 9. Revue de code du 30/09/2026 (3 relecteurs en parallèle) et corrections

| Défaut confirmé | Correction |
|---|---|
| `appliquer_schema()` retirait puis remettait la contrainte de `suppressions` à chaque GET (verrou exclusif, fenêtre sans contrainte) | faite une fois par process, et seulement si `soft_bounce` manque, en une transaction ; retirée des routes GET |
| « connection timed out » (panne réseau vers un MX valide) classé hard : 5 bonnes adresses en liste noire | classé `technique` ; garde générale « un 4xx n'est jamais une adresse morte » ; `reclasser()` + retrait automatique des suppressions `sweego_logs` que plus aucun rebond ne justifie |
| les codes à points (5.1.1…) matchaient des adresses IP du journal | IP effacées du texte avant classement |
| soft bounce = bannissement définitif | **quarantaine de 60 jours** (`pg.SUPPRESSION_ACTIVE`, relue par `envoi` et `validation`) |
| désinscription ou plainte perdue si l'adresse avait déjà un soft/hard (`ON CONFLICT DO NOTHING`) | `pg.SUPPRESSION_SUR_CONFLIT` : une raison plus forte remplace toujours la plus faible |
| `/campaigns/{id}/risque` en 500 (exp(-5,4) arrondi à 0 puis log(0)) | tri sur le poids brut |
| fuite de la cible via « déjà ouvert » (AUC gonflée à 0,83) | facteur retiré : **AUC honnête 0,80** |
| AUC fausse avec les ex æquo | rangs moyens (Mann-Whitney) |
| « queued » appris comme délivré | seules les livraisons prouvées comptent |
| apprentissage (≈ 2 min) dans la boucle du worker en pleine journée | chaque nuit à 3 h, heure de Paris |
| liste des campagnes à ≈ 1 s (964 ms de compilation JIT) | `SET LOCAL jit = off` + index `recipients (campaign_id, target_version_id)` : 29 ms |
| entonnoir : pauses de préférences et verdicts en attente de finalisation non comptés ; hard+soft comptés deux fois | `preferences` dans les autres exclusions ; `mj_en_cours` = éligibilité en attente ; une seule famille par destinataire |
| entrée HetrixTools en texte ignorée (Spamhaus + UCEPROTECT 3 aurait été pris pour « réseau ») | entrées texte conservées, noms normalisés |
| UI : page d'accueil qui plante si `rbl` est nul ; entonnoir et rebonds figés sur la fiche ; cause `temporaire_autre` absente | corrigés |
