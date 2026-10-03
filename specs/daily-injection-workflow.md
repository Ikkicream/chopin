# Workflow d'injection quotidien — Emelia

## Le problème à résoudre
79 263 contacts, 3 tiers, des règles de délivrabilité strictes.
L'agent doit chaque jour :
1. Sélectionner QUI contacter
2. Vérifier les contraintes (pas 2 du même domaine le même jour, pas de doublon)
3. Injecter dans Emelia via API
4. Ne pas dépasser les limites de volume

---

## Architecture : 1 campagne par tier, injection progressive

### On ne crée PAS 79K contacts d'un coup dans Emelia
Emelia gère l'envoi, le timing des steps, les bounces. Mais c'est NOUS qui contrôlons le rythme d'injection des contacts. Un contact ajouté à une campagne = son Step 1 part dans les prochaines heures.

### Stratégie : injection quotidienne par batch
```
Chaque jour à 7h UTC (cron Genesis) :
  → L'agent sélectionne le batch du jour (30-50 contacts)
  → L'agent les injecte dans la campagne Emelia
  → Emelia envoie les Step 1 entre 9h-11h
  → Les Step 2 et Step 3 sont gérés automatiquement par Emelia (J+3, J+7)
```

---

## Fichier de suivi local : `memory/lcr/injection-tracker.json`

L'agent maintient un tracker pour savoir QUI a été contacté, QUAND, et sur QUEL domaine :

```json
{
  "lastInjectionDate": "2026-05-15",
  "totalInjected": 347,
  "totalRemaining": 78916,
  "domainHistory": {
    "carrefour.com": {
      "lastContactDate": "2026-05-15",
      "contactedEmails": ["j.dupont@carrefour.com", "m.martin@carrefour.com"],
      "totalContacted": 2
    },
    "decathlon.com": {
      "lastContactDate": "2026-05-14",
      "contactedEmails": ["a.bernard@decathlon.com"],
      "totalContacted": 1
    }
  },
  "dailyLog": {
    "2026-05-15": {
      "tier1": 20,
      "tier2": 8,
      "tier3": 2,
      "total": 30,
      "domains": ["carrefour.com", "fnac.com", "agence-cocoon.fr", "..."]
    }
  }
}
```

---

## Algorithme de sélection quotidien

```python
# Pseudo-code exécuté chaque matin par l'agent

def select_daily_batch(csv, tracker, config):
    
    today = date.today()
    batch = []
    domains_today = set()
    
    # 1. Déterminer le quota du jour (montée progressive)
    daily_quota = get_daily_quota(tracker, config)
    # Semaine 1-2: 0, S3: 5, S4: 10, S5: 15, S6: 25, S7: 40, S8+: 50
    # Auto-ajusté selon open rate et bounce rate de la veille
    # Voir section "Montée en charge progressive" pour le détail
    
    # 2. Répartition par tier
    tier1_quota = int(daily_quota * 0.60)  # 60% = SMS géolocalisé
    tier2_quota = int(daily_quota * 0.25)  # 25% = agences marketing
    tier3_quota = int(daily_quota * 0.15)  # 15% = grands comptes
    
    # 3. Pour chaque tier, sélectionner les contacts
    for tier, quota in [(tier1, tier1_quota), (tier2, tier2_quota), (tier3, tier3_quota)]:
        
        candidates = get_tier_contacts(csv, tier)
        
        for contact in candidates:
            if len(batch) >= daily_quota:
                break
            
            domain = contact.email.split("@")[1]
            
            # RÈGLE 1 : pas 2 contacts du même domaine le même jour
            if domain in domains_today:
                continue
            
            # RÈGLE 2 : pas déjà contacté (sauf si domaine large et dernière
            #           injection > 7 jours pour ce domaine)
            if contact.email in tracker.contacted_emails:
                continue
            
            # RÈGLE 3 : si domaine contacté hier → skip (espacement 1 jour min)
            if tracker.domain_last_contact(domain) == yesterday:
                continue
            
            # RÈGLE 4 : pas d'email générique
            if contact.email.startswith(("info@", "contact@", "admin@", "support@")):
                continue
            
            # RÈGLE 5 : pas de concurrent (telco)
            if domain in BLACKLIST_DOMAINS:
                continue
            
            batch.append(contact)
            domains_today.add(domain)
    
    return batch
```

---

## Injection dans Emelia — étape par étape

### Le matin (cron 7h UTC = 8h Paris)

```
1. L'agent charge le CSV + le tracker

2. L'agent exécute l'algorithme de sélection → batch de 30-50 contacts

3. Pour chaque contact du batch :
   
   a. Vérifier l'email via Emelia
      POST https://api.emelia.io/tools/verify-email
      Body: {"email": "j.dupont@carrefour.com"}
      → Attendre le résultat (async)
      GET https://api.emelia.io/tools/verify-email/{jobId}
      → Si invalide → skip, marquer dans le tracker
   
   b. Enrichir (parsing email → prénom/nom/entreprise)
      j.dupont@carrefour.com → firstName: "J.", lastName: "Dupont", field1: "Carrefour"
   
   c. Générer l'icebreaker (Claude Sonnet, ~150 mots)
      → Scrape rapide du site web de l'entreprise (curl)
      → Génère un message personnalisé
      → L'injecte dans le champ field2 ou directement dans le step via SpinText
   
   d. Injecter le contact dans la campagne Emelia
      POST https://api.emelia.io/emails/campaign/contacts
      Body: {
        "id": "campaign_tier1_id",
        "contact": {
          "email": "j.dupont@carrefour.com",
          "firstName": "J.",
          "lastName": "Dupont",
          "field1": "Carrefour",
          "field2": "[icebreaker personnalisé]"
        }
      }

4. Mettre à jour le tracker (memory/lcr/injection-tracker.json)

5. Log dans le dashboard (data.json)

6. Si c'est le premier batch du jour → vérifier les stats de la veille :
   GET https://api.emelia.io/emails/campaigns/{id}/statistics
   → Si bounce > 5% → PAUSE auto → alerte Telegram
   → Si open rate < 30% → alerte Telegram (revoir les objets)
```

### Emelia prend le relais automatiquement

```
9h-11h : Emelia envoie les Step 1 (emails du batch du jour)
         → Respecte ses propres limites par boîte mail
         → Distribue sur les heures de bureau

J+3 :    Emelia envoie automatiquement les Step 2 (relance)
         → Uniquement aux contacts qui n'ont pas répondu
         → Pas besoin d'intervention de l'agent

J+7 :    Emelia envoie automatiquement les Step 3 (dernière relance)
         → Idem, auto

Continu : Emelia gère les bounces, les désabonnements, le tracking
          → L'agent consulte les stats quotidiennement
```

---

## Campagnes Emelia — structure

### Option A : 1 campagne par tier (recommandé)
```
Campagne "LCR-TIER1-Mai2026" → contacts retail/hôtel/immo
Campagne "LCR-TIER2-Mai2026" → contacts agences/marketing
Campagne "LCR-TIER3-Mai2026" → contacts grands comptes
```
Chaque campagne a ses propres steps/séquences adaptés au tier.
L'agent injecte les contacts dans la bonne campagne selon leur tier.

### Option B : 1 campagne par segment (plus granulaire)
```
Campagne "LCR-Restaurants-Mai2026"
Campagne "LCR-Hotels-Mai2026"
Campagne "LCR-Immo-Mai2026"
Campagne "LCR-Agences-Mai2026"
```
Plus de travail à setup mais messages plus ciblés.

### Création des campagnes (une seule fois, au début)
```bash
# L'agent crée les campagnes
POST /emails/campaigns → {name: "LCR-TIER1-Mai2026"} → campaignId_tier1
POST /emails/campaigns → {name: "LCR-TIER2-Mai2026"} → campaignId_tier2
POST /emails/campaigns → {name: "LCR-TIER3-Mai2026"} → campaignId_tier3

# Configure les steps pour chaque campagne
PATCH /emails/campaigns/{campaignId_tier1}/steps → séquence 3 emails Tier 1
PATCH /emails/campaigns/{campaignId_tier2}/steps → séquence 3 emails Tier 2
PATCH /emails/campaigns/{campaignId_tier3}/steps → séquence 3 emails Tier 3

# Configure les providers (boîtes mail)
PATCH /emails/campaigns/{id}/providers → sélectionne les boîtes warmées

# Démarre les campagnes
POST /emails/campaigns/{id}/start
# → À partir de là, tout contact ajouté recevra la séquence automatiquement
```

### Ensuite chaque jour : juste l'injection
```bash
# L'agent ajoute les contacts du batch quotidien
POST /emails/campaign/contacts → {id: campaignId_tier1, contact: {...}}
POST /emails/campaign/contacts → {id: campaignId_tier1, contact: {...}}
POST /emails/campaign/contacts → {id: campaignId_tier2, contact: {...}}
# ... × 30-50 contacts
```

Emelia fait le reste : timing, envoi, follow-up, tracking.

---

## Contrôle délivrabilité — résumé des garde-fous

| Règle | Qui l'applique | Comment |
|---|---|---|
| Max 1 contact/entreprise/jour | **L'agent** (tracker JSON) | Check domaine avant injection |
| Max 30-50 contacts/jour total | **L'agent** (daily_quota) | Compteur dans l'algorithme |
| Max 80-100 emails/boîte/jour | **Emelia** (config campagne) | Paramètre dans les settings |
| Envoi 9h-11h / 14h-16h | **Emelia** (horaires campagne) | Config dans update settings |
| Pas de bounce > 5% | **L'agent** (check stats) | GET /statistics chaque matin |
| Warmup 2-4 semaines | **Emelia** (warmup auto) | Activé sur chaque boîte mail |
| SpinText variations | **Emelia** (natif) | Dans le contenu des steps |
| Vérification email avant envoi | **Emelia** (verify-email) | POST /tools/verify-email |
| Icebreaker personnalisé | **Claude Sonnet** | Généré avant injection |
| Tracking domaine personnalisé | **DNS** (CNAME) | track.lcr-contact.com → emelia.link |
| Blacklist concurrents | **L'agent** (filtre) | orange.com, sfr.fr, bouygues* exclus |

---

## Timeline d'une journée type

```
07:00 UTC — Cron Genesis déclenche l'agent swarm-campaign
07:01      — Charge tracker + CSV
07:02      — Check stats campagne J-1 (bounces, ouvertures, réponses)
07:03      — Si alerte → Telegram + pause si nécessaire
07:05      — Algorithme sélection → batch 30-50 contacts
07:10      — Vérification emails batch (Emelia verify, ~2 min)
07:15      — Enrichissement (parsing email → prénom/nom/entreprise)
07:20      — Génération icebreakers (Sonnet, ~5 min pour 50 contacts)
07:30      — Injection batch dans Emelia (POST /campaign/contacts × 50)
07:35      — Mise à jour tracker + dashboard
07:36      — Rapport Telegram : "30 contacts injectés (18 Tier1, 8 Tier2, 4 Tier3)"
07:37      — Agent se met en veille jusqu'à demain

09:00-11:00 — Emelia envoie les Step 1 automatiquement
Tout au long de la journée — Emelia gère les Step 2/3 des jours précédents
18:00      — Agent peut optionnellement checker les réponses et alerter
```

---

## Montée en charge progressive (basé sur le guide délivrabilité Emelia)

Le warmup n'est pas juste les boîtes mail — c'est aussi le volume d'envoi qui doit monter graduellement. Un domaine neuf qui envoie 50 emails jour 1 = flagué comme suspect.

### Courbe de montée

| Semaine | Phase | Contacts/jour | Par boîte mail | Boîtes | Total/semaine |
|---|---|---|---|---|---|
| 1-2 | Warmup pur | 0 | 0 | 3 | 0 — Emelia chauffe les boîtes |
| 3 | Warmup + micro-test | 5 | ~2 | 3 | 25 |
| 4 | Test | 10 | ~3-4 | 3 | 50 |
| 5 | Ramp up | 15 | ~5 | 3 | 75 |
| 6 | Ramp up | 25 | ~8 | 3 | 125 |
| 7 | Accélération | 40 | ~13 | 3 | 200 |
| 8 | Croisière | 50 | ~17 | 3 | 250 |
| 10+ | Scale (+ boîtes) | 80-100 | ~20 | 5 | 400-500 |
| 12+ | Full scale | 150+ | ~25-30 | 5-10 | 750+ |

### Règles de la montée
- **Jamais doubler le volume d'un jour à l'autre** — augmenter de 20-30% max par semaine
- **Checker les métriques avant de monter** :
  - Taux d'ouverture > 25% → OK pour monter
  - Taux d'ouverture 18-25% → rester au palier actuel 1 semaine de plus
  - Taux d'ouverture < 18% → REDESCENDRE d'un palier, investiguer (revoir objets, ciblage, warmup)
  - Bounce > 3% → STOP, nettoyer la liste
  - Bounce > 5% → PAUSE campagne, alerter
- **Le volume inclut les follow-ups** : si 50 contacts injectés il y a 3 jours reçoivent leur Step 2 aujourd'hui, ça compte dans le volume total de la boîte mail
- **Ajouter des boîtes mail pour scaler**, pas augmenter le volume par boîte au-delà de 30/jour

### Impact sur l'algorithme de sélection

```python
def get_daily_quota(tracker, config):
    """Le quota augmente automatiquement selon la semaine et les métriques"""
    
    weeks_since_start = (today - config["campaign_start_date"]).days // 7
    
    # Courbe de montée
    ramp_schedule = {
        0: 0, 1: 0,      # warmup pur
        2: 5,             # micro-test
        3: 10,            # test
        4: 15,            # ramp
        5: 25,            # ramp
        6: 40,            # accélération
        7: 50,            # croisière
    }
    
    base_quota = ramp_schedule.get(weeks_since_start, 50)  # 50 par défaut après semaine 7
    
    # Ajuster selon les métriques de la veille
    yesterday_stats = get_emelia_stats(campaign_id, "yesterday")
    
    if yesterday_stats["open_rate"] < 0.18:
        base_quota = max(5, base_quota - 10)  # redescendre
        alert_telegram("⚠️ Open rate < 18%, quota réduit à " + str(base_quota))
    
    if yesterday_stats["bounce_rate"] > 0.05:
        base_quota = 0  # STOP
        pause_campaign(campaign_id)
        alert_telegram("🛑 Bounce > 5%, campagne en PAUSE")
    
    if yesterday_stats["bounce_rate"] > 0.03:
        base_quota = max(5, base_quota // 2)  # diviser par 2
        alert_telegram("⚠️ Bounce > 3%, quota réduit à " + str(base_quota))
    
    # Scale avec les boîtes mail
    num_mailboxes = len(config["mailboxes"])
    max_per_mailbox = 30
    hard_cap = num_mailboxes * max_per_mailbox
    
    return min(base_quota, hard_cap)
```

### Projection avec la montée

| Semaine | Contacts/jour | Cumulé fin de semaine | % du Tier 1 couvert |
|---|---|---|---|
| 3 | 5 | 25 | 0.8% |
| 4 | 10 | 75 | 2.3% |
| 5 | 15 | 150 | 4.7% |
| 6 | 25 | 275 | 8.6% |
| 7 | 40 | 475 | 14.8% |
| 8 | 50 | 725 | 22.7% |
| 10 | 80 | 1,285 | 40.2% |
| 12 | 150 | 2,585 | 80.8% |
| 13 | 150 | 3,200 | **100% Tier 1** |

Tier 1 (3200 contacts) couvert en **~13 semaines** avec la montée progressive.
Tier 2 (1900) en parallèle, couvert en **~10 semaines**.

### Le warmup Emelia fait quoi pendant les semaines 1-2 ?
Emelia envoie et reçoit des emails automatiques entre tes boîtes et un réseau de boîtes "amies". Ça crée de l'historique de conversations normales sur ton domaine, ce qui dit aux providers (Gmail, Outlook) : "ce domaine est légitime, pas du spam". Tu n'as rien à faire — juste attendre.
