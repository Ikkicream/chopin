# Mise en service et exploitation

Les six conditions avant le premier envoi, comment chacune est vérifiée par le code, puis
l'exploitation courante (warm-up, DMARC, alertes, incidents).

## Sommaire
1. Les six conditions et leur vérification
2. Warm-up
3. Progression DMARC
4. Surveillance continue
5. Procédures d'incident

---

## 1. Les six conditions (bloquantes dans `send.ts` pour le marketing)

| # | Condition | Comment elle est remplie | Champ |
|---|---|---|---|
| 1 | Domaine créé dans la **région UE** avant le DNS | `createSendingDomain` exige la région ; `evaluateGoLive(…, { requireEu })` | identité `region` |
| 2 | Sous-domaine dédié, SPF/DKIM du fournisseur vérifiés, **DMARC `p=none` + `rua` lu** | `refreshDomain` : statut fournisseur + `readDmarc()` | `status`, `dmarcPolicyObserved`, `dmarcRuaObserved` |
| 3 | **Webhooks bounces + plaintes** branchés et signés | auto-test : envoi vers `bounced@resend.dev` / `complained@resend.dev` (ou simulateurs SES) puis réception signée des deux événements | `webhookVerifiedAt` |
| 4 | **`List-Unsubscribe` + `List-Unsubscribe-Post`**, endpoint POST sans friction | en-têtes posés par `send.ts` ; endpoint testé par `scripts/selftest.mjs` puis confirmé | `unsubscribeVerifiedAt` |
| 5 | **Google Postmaster Tools** (domaine organisationnel) + **Yahoo Sender Hub** (boucle de plaintes du domaine DKIM `d=`) | inscription manuelle, confirmée dans l'UI | `postmasterConfirmedAt`, `senderHubConfirmedAt` |
| 6 | **Warm-up** démarré | action « démarrer » avec volume cible | `warmupStartedAt`, `warmupTargetPerDay` |

Le transactionnel n'exige que 1, 2, 3. Les adresses des simulateurs passent toujours (pour l'auto-test).
Vérification externe complète : `scripts/golive-check.mjs` (GO / NO-GO).

## 2. Warm-up

- 300–500/jour la 1ʳᵉ semaine (défaut 400), **contacts les plus engagés d'abord**, puis doublement chaque
  semaine jusqu'au volume cible : `warmupDailyCap()` applique le plafond par domaine et par jour UTC.
- Segments ouverts semaine après semaine (`warmupOpenSegments`) : engagés 30 j → 90 j → inscrits récents
  confirmés → 180 j → reste de la liste active. Jamais d'adresses inactives depuis plus de 12 mois.
- Job hebdomadaire : `shouldHoldWarmup()` sur la semaine écoulée (≥ 200 envois) — bounces ≥ 2 % ou
  plaintes ≥ 0,1 % → `warmupHeldWeeks + 1` (on reste au palier).
- Le plafond dépassé renvoie `WARMUP_CAP_REACHED` avec `retryAfterSeconds` jusqu'à minuit UTC : la file
  replanifie, rien n'est perdu.
- Plan imprimable : `scripts/warmup-plan.mjs --target 40000 --start 2026-10-20`.

## 3. Progression DMARC

1. Pendant le warm-up : `p=none` + `rua` vers une boîte **lue** (ou un parseur : Postmark DMARC, dmarcian…).
2. Fin du warm-up, rapports propres (nos sources alignées, pas d'expéditeur légitime oublié) :
   `p=quarantine` — éventuellement une semaine en `t=y` (mode test DMARCbis, remplace `pct`).
3. Puis `p=reject`. En délégation, on écrit nous-mêmes `_dmarc.news.client.com` ; la racine reste au client.

## 4. Surveillance continue

| Signal | Seuil | Action |
|---|---|---|
| Bounces permanents (par domaine, fenêtres consécutives, ≥ 200 envois) | > 2 % warning, > 5 % erreur | retenir le warm-up, nettoyer la liste |
| Plaintes (par délivrés) | > 0,08 % warning, > 0,1 % erreur (Gmail coupe à 0,3 %) | suspendre le marketing du client, audit de la source des contacts |
| Retards de livraison | > 10 % | ralentir, vérifier l'authentification |
| Tenant SES « Sending Status Disabled » | — | bloquer le client, investiguer `ListRecommendations` |
| Resend : bounces compte > 4 % ou spam > 0,08 % | — | risque de suspension de TOUT le compte : couper le client fautif |
| Audit DNS quotidien (`dns-audit.mjs --json`) | erreur | alerte au client (DKIM supprimé, DMARC modifié…) |
| Google Postmaster « Compliance status » | « Needs work » | traiter sous 7 jours |

Une alerte ne se ferme jamais sur un échec de requête DNS, seulement sur un contrôle sain.

## 5. Procédures d'incident

- **Pic de plaintes chez un client** : couper ses envois marketing (le transactionnel continue), exporter
  la source des contacts, exiger un double opt-in, reprendre au palier de warm-up précédent.
- **Tenant SES mis en pause par AWS** : ne pas réactiver avant d'avoir compris la cause ; réactivation =
  état « REINSTATED », surveillé de près.
- **Domaine client dé-vérifié** (record supprimé) : la bascule vers l'autre fournisseur s'applique si le
  domaine y est vérifié ; sinon les envois échouent avec `DOMAIN_NOT_VERIFIED` → prévenir le client.
- **Suspension du compte Resend** : basculer le transactionnel sur SES (identité `mail.` vérifiée chez les
  deux), contacter le support Resend.
- **Client qui part** : voir `delegation.md` §6 (ne pas supprimer la zone tant que ses NS pointent vers nous).
