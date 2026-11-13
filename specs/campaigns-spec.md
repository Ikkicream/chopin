# Campagnes — Spec UX + algorithme

> Page `/site/[code]/campaigns` — création et lancement de campagnes Emelia par association template × secteur.

## 1. Vue d'ensemble

Une **campagne** = association d'un **template email** avec un **secteur d'activité** ciblé, avec des **paramètres d'envoi** (durée, volume/jour, sender). La page Campagnes est l'unique point d'entrée pour lancer un envoi cold email.

```
Template (1 secteur)        +        Secteur (= filtre du pool)
        +
Réglages (durée campagne, vol/jour, sender)
        =
Campagne lancée vers les "meilleurs contacts" du pool mutualisé
```

## 2. UX Page `/site/[code]/campaigns`

### 2.1 Vue liste (page principale)

```
┌─ HEADER ──────────────────────────────────────────────────────────────┐
│  Campagnes — LCR                                  [+ Nouvelle campagne]│
└────────────────────────────────────────────────────────────────────────┘

┌─ FILTRES ─────────────────────────────────────────────────────────────┐
│  [Tous statuts ▾] [Tous secteurs ▾] [Recherche nom...]                 │
└────────────────────────────────────────────────────────────────────────┘

┌─ LISTE CAMPAGNES (table shadcn) ──────────────────────────────────────┐
│ Nom               │ Secteur     │ Statut     │ Envoyés/Vol │ Ouverts │ Clics │ Réponses │ Actions │
├───────────────────┼─────────────┼────────────┼─────────────┼─────────┼───────┼──────────┼─────────┤
│ Restaurant Mai-26 │ restaurant  │ ▶ RUNNING  │ 23/50       │ 14 (60%)│ 3 (13%)│ 1 (4%)   │ ⏸ ⚙   │
│ Coiffeur Q1      │ coiffeur    │ ⏸ PAUSED   │ 12/30       │ 8       │ 2     │ 0        │ ▶ ⚙   │
│ Immo Lyon       │ immobilier  │ ✓ DONE     │ 30/30       │ 22 (73%)│ 7 (23%)│ 3 (10%)  │ 📊    │
│ Artisan T1      │ artisan     │ 📝 DRAFT   │ 0/0         │ -       │ -     │ -        │ ▶ ⚙ 🗑 │
└───────────────────┴─────────────┴────────────┴─────────────┴─────────┴───────┴──────────┴─────────┘
```

### 2.2 Création nouvelle campagne (modal/sheet en 4 étapes)

#### Step 1 — Template + Secteur

```
┌────────────────────────────────────────────────────┐
│ Nouvelle campagne                          1/4     │
├────────────────────────────────────────────────────┤
│                                                    │
│  Template à utiliser :                             │
│  ┌──────────────────────────────────────────────┐ │
│  │ ◯ Restaurant — "Réservations remplies en 48h"│ │
│  │ ◉ Immobilier — "Des acheteurs prêts à visiter"│ │
│  │ ◯ Coiffeur — "Salon plein de monde"          │ │
│  │ ◯ Artisan — "+10 chantiers par mois"         │ │
│  └──────────────────────────────────────────────┘ │
│                                                    │
│  Secteur cible (héritier du template choisi) :     │
│  immobilier  ✓ (autodéterminé)                     │
│                                                    │
│  Multi-secteur autorisé ? ☐                        │
│  (Cocher pour cibler aussi les contacts avec      │
│   plusieurs secteurs incluant immobilier)         │
│                                                    │
│                              [Annuler] [Suivant →] │
└────────────────────────────────────────────────────┘
```

#### Step 2 — Volume + Durée

```
┌────────────────────────────────────────────────────┐
│ Nouvelle campagne                          2/4     │
├────────────────────────────────────────────────────┤
│                                                    │
│  Sender : juliette@leclientroi.com                 │
│  Warmup actuel : J3 — quota max 10/jour           │
│                                                    │
│  Volume cible total : [____ ] contacts             │
│      (suggestion : 30 = 3 jours à 10/jour)        │
│                                                    │
│  Volume max par jour : [10] (≤ quota warmup)      │
│                                                    │
│  Date de début : [22/05/2026]                     │
│  Date de fin estimée : auto (3 jours)             │
│                                                    │
│  Sending hours : 08:00 → 20:00 Brussels (Emelia)  │
│                                                    │
│  ⚠ Alerte : 47 contacts disponibles dans le pool   │
│    pour "immobilier" qui respectent les filtres    │
│    (cooldown, blacklist, etc.)                     │
│                                                    │
│                       [← Préc.] [Suivant →]        │
└────────────────────────────────────────────────────┘
```

#### Step 3 — Aperçu des contacts ciblés

```
┌────────────────────────────────────────────────────┐
│ Nouvelle campagne                          3/4     │
├────────────────────────────────────────────────────┤
│                                                    │
│  30 contacts seront pushés (selon ordre tri) :     │
│                                                    │
│  ┌──────────────────────────────────────────────┐ │
│  │ # │ Email                  │ Source  │ Score │ │
│  ├──┼────────────────────────┼─────────┼───────┤ │
│  │ 1 │ jean@agence-immo.fr   │ tally   │ 85    │ │
│  │ 2 │ contact@nexity.fr     │ tally   │ 80    │ │
│  │ 3 │ p.bernard@nantes.com  │ serper  │ 90    │ │
│  │ ...│                       │         │       │ │
│  │30 │ info@immo-rennes.fr   │ csv     │ 65    │ │
│  └──────────────────────────────────────────────┘ │
│                                                    │
│  Tri appliqué :                                    │
│  1. Source (tally > serper > csv)                  │
│  2. Email score Mailnjoy décroissant               │
│  3. updated_at desc                                │
│                                                    │
│  [Voir les 17 autres contacts non retenus] ⓘ      │
│                                                    │
│                       [← Préc.] [Suivant →]        │
└────────────────────────────────────────────────────┘
```

#### Step 4 — Validation finale

```
┌────────────────────────────────────────────────────┐
│ Nouvelle campagne                          4/4     │
├────────────────────────────────────────────────────┤
│                                                    │
│  Récap :                                           │
│  • Nom : Immobilier Mai-26                        │
│  • Template : "Des acheteurs prêts à visiter"     │
│  • Sender : juliette@leclientroi.com              │
│  • 30 contacts (immobilier)                       │
│  • 10/jour pendant 3 jours                        │
│  • Début : aujourd'hui 22/05                      │
│                                                    │
│  ☐ Envoyer 1 mail test à camille@... avant ?      │
│                                                    │
│              [← Préc.] [Annuler] [🚀 Lancer]      │
└────────────────────────────────────────────────────┘
```

## 3. Algorithme de pioche "meilleurs contacts" (côté backend)

### 3.1 Requête principale (cf. specs/contacts-model.md §3.5)

```sql
SELECT c.*, csh.*
FROM contacts c
LEFT JOIN contact_site_history csh
    ON c.id = csh.contact_id AND csh.site_code = :site
WHERE
    -- Secteur cible (multi-sector OR clause si la campagne le permet)
    json_extract(c.sectors, '$') LIKE '%' || :sector || '%'
    -- Pas blacklisté globalement (RGPD)
    AND c.global_blacklisted = FALSE
    -- Pas déjà engagé sur ce site (cold_email = OK, prm/lead/crm = pas re-prospecter)
    AND (csh.state IS NULL OR csh.state = 'cold_email')
    -- Cooldown re-push même site = 7 jours
    AND (
        csh.last_contacted_by_site_at IS NULL
        OR csh.last_contacted_by_site_at < NOW() - INTERVAL 7 DAY
    )
    -- Cooldown global cross-site = 30 jours
    AND NOT EXISTS (
        SELECT 1 FROM contact_site_history csh2
        WHERE csh2.contact_id = c.id
          AND csh2.site_code != :site
          AND csh2.last_contacted_by_site_at > NOW() - INTERVAL 30 DAY
    )
ORDER BY
    -- Priorité source : tally > serper > csv > manual
    CASE c.primary_source
        WHEN 'tally'  THEN 0
        WHEN 'serper' THEN 1
        WHEN 'csv'    THEN 2
        ELSE 3
    END,
    -- Email score (Mailnjoy validé > non validé)
    c.email_score DESC NULLS LAST,
    -- Frais d'abord
    c.updated_at DESC
LIMIT :requested_count
```

### 3.2 Cas où moins de contacts dispo que demandé

Si l'admin demande 30 contacts pour "immobilier" mais que la requête ne retourne que 17 :
- **Step 3 du wizard** affiche un warning : "⚠ Seuls 17 contacts disponibles, campagne ajustée à 17"
- Le user peut choisir : (a) lancer avec 17, (b) annuler et faire du scrape Serper pour enrichir le pool, (c) ouvrir le secteur à "multi-secteur" si certains contacts ont aussi des secteurs voisins
- **Alerte popup à la connexion** ([Q5] décision user) si _au moins un_ secteur a < 10 contacts dispo pour ce site

### 3.3 Sender = warmup quota
Le `volume_max_par_jour` est plafonné par le `daily_warmup_quota(sender_email)` (cf. specs/warmup-plan.md). Si l'admin met 20 alors que le quota J1=10, l'UI corrige en silence à 10 et affiche un message.

## 4. États d'une campagne

```
DRAFT
  ↓ (admin valide)
PENDING_START
  ↓ (cron côté Emelia détecte les conditions OK)
RUNNING
  ↓ (volume cible atteint OU date de fin OU paused manuel)
PAUSED / DONE
  ↓ (admin reprend)
RUNNING (si paused)
```

**État `DONE`** est définitif. Pour re-prospecter le même secteur → créer une nouvelle campagne.

## 5. Page détail campagne `/site/[code]/campaigns/{id}`

Affiche en temps réel (via webhook Emelia → table `emelia_events`) :

```
┌─ HEADER ──────────────────────────────────────────────────────────────┐
│  Immobilier Mai-26                            ▶ RUNNING  [⏸ Pauser]   │
│  Démarré le 22/05/2026  •  Sender juliette@leclientroi.com            │
└────────────────────────────────────────────────────────────────────────┘

┌─ KPI ─────────────────────────────────────────────────────────────────┐
│   Volume : 23 / 30 envoyés                                            │
│   Ouverts : 14 (60%)    Cliqués : 3 (13%)   Répondus : 1 (4%)          │
│   Bounces : 1 (4%)      Désabos : 0                                    │
│   Reste à envoyer : 7  (sera fini d'ici 1 jour à 10/j)                 │
└────────────────────────────────────────────────────────────────────────┘

┌─ TIMELINE EVENTS (depuis emelia_events) ──────────────────────────────┐
│  17:45  📥 contact@agence-test.fr : OPENED                            │
│  17:43  🖱️ jean@nexity.fr : CLICKED                                    │
│  17:30  💬 m.bernard@... : REPLIED  (→ promoted to lead)              │
│  17:25  📤 30 contacts envoyés aujourd'hui                            │
│  ...                                                                    │
└────────────────────────────────────────────────────────────────────────┘

┌─ TABLE CONTACTS DE LA CAMPAGNE ───────────────────────────────────────┐
│  Email | Source | Status | Sent at | Opened | Clicked | Replied      │
│  ...                                                                    │
└────────────────────────────────────────────────────────────────────────┘
```

## 6. Alerte "secteur épuisé" (Q5)

À la connexion utilisateur (login → arrivée sur dashboard), un check rapide :

```python
def check_sector_pool_depletion(site_code: str) -> list[dict]:
    """Pour chaque secteur activé du site, compte les contacts disponibles
    (mêmes filtres que la requête de pioche)."""
    result = []
    for sector in SITE_SETTINGS[site_code].sectors_enabled:
        count = query_available_contacts_count(site_code, sector)
        if count < ALERT_THRESHOLD:  # défaut 10
            result.append({"sector": sector, "available": count})
    return result
```

**Popup affichée** :
```
⚠ Pool faible pour certains secteurs :
   • coiffeur : 4 contacts disponibles
   • garagiste : 7 contacts disponibles

   Actions possibles :
   • Lancer un scrape Serper sur ces secteurs
   • Importer un CSV
   • Élargir la zone géographique
```

## 7. Endpoints API requis (à coder)

| Endpoint | Méthode | Rôle |
|---|---|---|
| `/api/sites/{site}/campaigns` | GET | Liste les campagnes du site |
| `/api/sites/{site}/campaigns` | POST | Crée une nouvelle campagne (DRAFT) |
| `/api/sites/{site}/campaigns/{id}` | GET | Détail campagne + stats temps réel |
| `/api/sites/{site}/campaigns/{id}` | PATCH | Modifier paramètres (avant launch) |
| `/api/sites/{site}/campaigns/{id}/preview-contacts` | GET | Aperçu des contacts qui seront pushés (algo §3.1) |
| `/api/sites/{site}/campaigns/{id}/launch` | POST | Démarre la campagne (push initial Emelia) |
| `/api/sites/{site}/campaigns/{id}/pause` | POST | Met en pause |
| `/api/sites/{site}/campaigns/{id}/resume` | POST | Reprend |
| `/api/sites/{site}/campaigns/{id}/test-send` | POST | Envoie 1 mail test à un email donné (cf. POST /emails/test Emelia) |
| `/api/sites/{site}/sectors/pool-alert` | GET | Retourne les secteurs avec pool < threshold |

## 8. Validation user requise

- [ ] Wizard 4 étapes OK ou trop long ?
- [ ] Volume cible + volume/jour : c'est un range "envoyé d'un coup" ou réparti dans le temps ? (proposé : réparti, Emelia respecte le sendingHours + dailyLimit)
- [ ] Re-push autorisé après 7 jours OU après "fin de campagne précédente + 7 jours" ?
- [ ] Affichage des contacts non-retenus (step 3) utile ou source de confusion ?
- [ ] Bouton "Envoi mail test" en step 4 (envoi via `POST /emails/test`) suffisant ?
