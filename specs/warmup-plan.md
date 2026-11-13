# Warmup Plan — Genesis (LCR + MKD)

> Document obligatoire — décrit le plan de chauffe (ramp-up) de chaque sender Gmail/SMTP utilisé pour le cold email via Emelia. **Tout push Emelia DOIT respecter le quota journalier du sender** (calculé par `daily_warmup_quota(sender_email)` dans `scripts/workflow_emelia_push.py`).

## 1. Pourquoi un warmup

Un compte Gmail neuf ne peut pas envoyer 100 cold emails par jour sans se faire flagger comme spam par les FAIs (Gmail/Outlook/Yahoo). **2 à 4 semaines de ramp-up** sont nécessaires pour bâtir une "IP reputation" propre. Aller trop vite = blacklist (Spamhaus, Barracuda) = 30+ jours de pénurie de délivrabilité.

Source : https://emelia.io/fr/hub/email-warmup-chauffe-adresse-email

## 2. Plans de chauffe disponibles

### Plan A — Conservateur Emelia (DÉFAUT pour Genesis)

Recommandé par Emelia pour les comptes Gmail standards / petits volumes (< 100/j cible).

| Phase | Jours | Volume/jour | Notes |
|---|---|---:|---|
| Phase 1 — Démarrage | J1 - J3 | **10** | Premiers contacts, surveillance bounce |
| Phase 2 — Stabilisation | J4 - J7 | **20** | Doubler le volume initial |
| Phase 3 — Montée | J8 - J14 | **35** | Aller au-delà du seuil "petits comptes" |
| Phase 4 — Croisière | J15 - J21 | **50** | Volume normal d'opération |
| Phase 5 — Plein régime | J22 - J28 | **75** | Pour scaler progressivement |
| **Plateau** | **J29+** | **100** | Limite saine long-terme Gmail standard |

C'est le plan utilisé par `daily_warmup_quota()` quand `daily_max_override IS NULL` dans la table `email_senders`.

### Plan B — Agressif "IP Warming Planner" (override manuel)

Plus agressif, conçu pour scaler vers de gros volumes (10k/jour) en 30 jours. À utiliser **uniquement** sur un sender dédié bien configuré (DKIM/SPF/DMARC OK, domaine établi).

| Jour | Volume/jour | Increment |
|---|---:|---:|
| 1 | 36 | 0 |
| 2 | 44 | 8 |
| 3 | 54 | 9 |
| 4 | 65 | 11 |
| 5 | 79 | 14 |
| 6 | 96 | 17 |
| 7 | 116 | 20 |
| 8 | 141 | 25 |
| 9 | 171 | 30 |
| 10 | 208 | 37 |
| 14 | 451 | 79 |
| 21 | 1 750 | 308 |
| 28 | 6 789 | 1 195 |
| 30 | 10 000 | 1 760 |

Pour activer ce plan sur un sender :
```sql
UPDATE email_senders
SET daily_max_override = ? -- valeur du tableau pour le jour J
WHERE sender_email = ?;
```
Ou écrire un script auto qui set `daily_max_override` chaque matin selon ce tableau.

## 3. Sender LCR — État au 2026-05-22

| Champ | Valeur |
|---|---|
| `sender_email` | `juliette@leclientroi.com` |
| `sender_name` | "Juliette Assistante" |
| `emelia_provider_id` | `6982242b1e54d84898f7380f` |
| **`warmup_start_date`** | **2026-05-22** (= J1) |
| Plan actif | **A — Conservateur** |
| Plateau attendu | 2026-06-19 (J29) |

Quota auj. **J1 = 10 emails**.

## 4. Garde-fou code

### Fonction `daily_warmup_quota(sender_email, today=None) -> int`

Définie dans `scripts/workflow_emelia_push.py`. Calcule le nombre max d'envois autorisés aujourd'hui :

```python
def daily_warmup_quota(sender_email: str, today: date = None) -> int:
    """Retourne le quota journalier autorisé selon le plan de chauffe.
    Lit la row email_senders. Si daily_max_override est set, le retourne tel quel.
    Sinon applique Plan A (conservateur)."""
    row = duckdb_query("SELECT warmup_start_date, daily_max_override FROM email_senders WHERE sender_email = ?", [sender_email])
    if not row:
        return 0  # sender inconnu = 0 envoi (safety)
    start, override = row
    if override is not None:
        return override
    days = (today or date.today() - start).days + 1  # J1 = jour 1
    if days <= 3:   return 10
    if days <= 7:   return 20
    if days <= 14:  return 35
    if days <= 21:  return 50
    if days <= 28:  return 75
    return 100  # plateau
```

### Branchement dans `push_prospect()`

Avant `POST /emails/campaign/contacts`, vérifier :
```python
sent_today = count_emails_sent_today(sender_email)
quota = daily_warmup_quota(sender_email)
if sent_today >= quota:
    return {"pushed": False, "reason": f"warmup_quota_reached_{sent_today}/{quota}"}
```

`count_emails_sent_today` lit la table `emelia_events` filtrée sur `event_type='SENT'` + `received_at >= today_00:00`.

## 5. Suivi opérationnel

### Dashboard / sidebar
Afficher pour chaque sender actif : `J{N}/quota_jour {sent}/{quota}`.
Ex: `juliette@leclientroi.com — J1 — 0/10`.

### Alerte
- Si `sent_today / quota > 0.9` → warn jaune dans UI
- Si `sent_today >= quota` → bloc dur push (déjà géré par push_prospect)
- Si bounce_rate sur les 7 derniers jours > 5% → PAUSE auto du sender + alerte Telegram

### Cron quotidien (à brancher)
Un script `scripts/warmup_daily_check.py` doit tourner chaque matin 7h UTC :
1. Pour chaque sender actif : calcule le jour de warmup et le quota
2. Si `bounced_rate_7d > 5%` ou `unsubscribed_rate_7d > 2%` → met `status='paused'`
3. Log l'état dans `logs/warmup.log` + notif Telegram si paused

## 6. Override manuel (cas exceptionnels)

Pour augmenter manuellement le quota d'un sender (ex: campagne ponctuelle après warmup complet) :
```sql
UPDATE email_senders SET daily_max_override = 200, notes = 'Override 2026-06-15 campagne X'
WHERE sender_email = 'juliette@leclientroi.com';
```
Pour revenir au calcul auto : `SET daily_max_override = NULL`.

## 7. Historique des décisions

- **2026-05-22** : Création du plan, démarrage warmup `juliette@leclientroi.com` Plan A (conservateur). Source recommandation : Emelia hub (https://emelia.io/fr/hub/email-warmup-chauffe-adresse-email).
- **2026-05-22** : Tableau "IP Warming Planner" agressif (10k/30j) documenté comme alternative B mais NON activé par défaut. Activable via `daily_max_override`.
