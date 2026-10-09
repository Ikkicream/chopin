# Skill — Pilotage adaptatif de délivrabilité email MTA

> Document fourni par Camille le 27/09/2026 (copie fidèle, formules remises en ligne). Adaptation à
> notre installation (Sweego, Mass Email) : `../SKILL.md`.

## 1. Objet du skill

Ce document définit le comportement attendu d’un agent IA chargé de piloter l’envoi d’emails à grande échelle via un MTA (Mail Transfer Agent), un ESP, ou une couche d’orchestration SMTP.

L’objectif n’est pas de « trouver le quota exact » de Gmail, Outlook, Yahoo, La Poste, Orange ou Free. Les fournisseurs ne publient généralement pas de capacité SMTP fixe, stable et garantie par IP. L’objectif est de :

- partir avec des limites prudentes ;
- mesurer les signaux techniques, réputationnels et comportementaux ;
- apprendre une capacité opérationnelle propre à chaque destination ;
- accélérer progressivement lorsque les signaux sont sains ;
- ralentir immédiatement et automatiquement au premier signe de saturation ou de dégradation de réputation ;
- protéger durablement les IP, les domaines et les destinataires.

Le modèle mental à appliquer est celui du contrôle de congestion réseau : augmentation graduelle tant que le trafic est accepté, réduction nette dès apparition d’un signal de congestion.

## 2. Principe directeur

### 2.1 Aucun quota SMTP universel par IP

Ne jamais affirmer qu’un fournisseur « accepte X emails par jour depuis une IP » sauf si cette limite est explicitement publiée, applicable au cas observé et correctement contextualisée.

Les limites d’acceptation effectives dépendent notamment de :

- l’IP source et sa réputation ;
- le domaine visible dans From: ;
- le domaine de signature DKIM ;
- l’alignement DMARC ;
- le rDNS/PTR et le HELO/EHLO ;
- le volume historique ;
- la régularité du trafic ;
- les connexions SMTP parallèles ;
- le débit instantané ;
- la qualité des listes ;
- les plaintes spam ;
- la qualité d’engagement des destinataires ;
- le contenu, les URLs, les pièces jointes et la structure MIME ;
- le fournisseur et le domaine destinataire ;
- le type de message : transactionnel, marketing opt-in, newsletter, relance, prospection, alertes ;
- les changements récents : nouvelle IP, nouveau domaine, nouveau sous-domaine, nouvelle URL de tracking, changement de créa ou hausse soudaine de volume.

La capacité opérationnelle doit être considérée comme une variable dynamique :

```text
C = f(IP, domaine_DKIM, domaine_From, FAI_destination, réputation, cadence, connexions, qualité_liste, engagement)
```

### 2.2 Courbe de chauffe = plafond, pas objectif obligatoire

Une courbe de chauffe donne une limite supérieure de prudence. Elle ne doit jamais être interprétée comme un volume à atteindre coûte que coûte.

L’agent doit toujours envoyer le minimum entre :

```text
Débit_autorisé = min(Courbe_de_chauffe, Capacité_apprise, Limite_de_risque, Volume_disponible_qualifié)
```

Un faible volume de destinataires récents et engagés vaut mieux qu’une montée artificielle avec des contacts froids ou risqués.

## 3. Sources publiques : ce qu’elles disent réellement

### 3.1 Gmail / Google

Google publie un seuil de catégorisation : les expéditeurs qui envoient environ 5 000 messages ou plus par jour vers des comptes Gmail personnels sont considérés comme des expéditeurs de masse (bulk senders).

Ce seuil :

- est un seuil de conformité, pas une capacité d’acceptation garantie ;
- ne signifie pas qu’une IP peut envoyer 5 000 emails/jour sans throttling ;
- déclenche ou renforce des exigences telles que SPF, DKIM, DMARC, PTR/rDNS, TLS, désabonnement en un clic et contrôle du taux de spam ;
- est évalué autour de l’identité d’expédition, notamment du domaine principal, et non comme un simple quota IP.

Références : Gmail — Email sender guidelines ; Gmail — Sender guidelines FAQ ; Gmail Postmaster Tools ; Gmail SMTP error codes.

### 3.2 Yahoo / AOL

Yahoo reconnaît les expéditeurs de masse et impose des exigences de délivrabilité, mais indique ne pas publier de seuil chiffré universel pour qualifier un expéditeur comme bulk sender.

Référence : Yahoo Sender Hub — FAQ.

### 3.3 La Poste

Les conditions de La Poste prévoient que le fournisseur peut fixer des limites sur le nombre maximal d’envois ou la fréquence d’envoi. Elles ne fournissent pas une grille universelle de débit par IP destinée aux expéditeurs externes.

Références : La Poste — Conditions générales ; Postmaster La Poste.

### 3.4 Microsoft / Outlook / Hotmail

Les retours SMTP Microsoft peuvent signaler une limitation temporaire par réputation ou comportement d’envoi. L’erreur 451 4.7.650 est fréquemment associée à une limitation temporaire de l’IP, à investiguer avec la réputation, la cadence et l’authentification.

Référence indicative : Microsoft Q&A — 451 4.7.650.

### 3.5 Règle de communication

Formulation autorisée :

> Les fournisseurs publient parfois des seuils de conformité ou de catégorisation, mais publient rarement une capacité SMTP fixe et garantie par IP. La cadence admissible est apprise à partir des réponses SMTP, de la réputation et des résultats observés.

Formulation interdite, sauf preuve source spécifique et contexte explicite :

> Gmail accepte toujours X emails par heure et par IP.

## 4. Périmètre de décision

L’agent ne pilote jamais un débit global unique. Il doit définir des files et des limites indépendantes.

### 4.1 Clé minimale de segmentation

Utiliser au minimum cette clé de décision :

```text
sending_ip
+ envelope_from_domain
+ dkim_signing_domain
+ campaign_or_stream_type
+ recipient_provider_group
+ recipient_domain_or_mx_group
```

Exemple :

```text
203.0.113.10
+ bounce.example.com
+ mail.example.com
+ marketing_optin
+ gmail
+ gmail.com / google MX
```

### 4.2 Groupes de destinations à isoler

Créer au minimum des queues distinctes pour :

- Gmail et Google Workspace ;
- Microsoft consumer : Outlook.com, Hotmail, Live, MSN ;
- Microsoft 365 / Exchange Online, lorsque l’identification est possible ;
- Yahoo et AOL ;
- Orange / Wanadoo ;
- La Poste ;
- Free ;
- SFR / Numericable ;
- autres webmails français pertinents selon le trafic ;
- grands domaines B2B à fort volume ;
- long tail B2B, regroupé avec prudence par MX ou domaine ;
- destinations inconnues ou nouvelles, avec profil conservateur.

Ne jamais réduire le débit de toutes les destinations parce qu’un seul fournisseur retourne des 4xx.

## 5. Données à collecter

### 5.1 Logs SMTP obligatoires

Pour chaque tentative d’envoi, conserver au minimum :

```json
{
  "timestamp": "ISO-8601",
  "message_id": "internal-message-id",
  "campaign_id": "campaign-or-stream",
  "stream_type": "transactional|marketing_optin|newsletter|other",
  "sending_ip": "IPv4-or-IPv6",
  "helo": "mail.example.com",
  "envelope_from_domain": "bounce.example.com",
  "from_domain": "example.com",
  "dkim_domain": "mail.example.com",
  "recipient_domain": "gmail.com",
  "recipient_mx_group": "google",
  "provider_group": "gmail",
  "smtp_host": "destination-mx",
  "smtp_status_code": 250,
  "enhanced_status_code": "2.0.0",
  "smtp_response": "accepted response",
  "attempt_number": 1,
  "queue_age_seconds": 0,
  "delivery_state": "accepted|deferred|hard_bounce|soft_bounce|expired",
  "latency_ms": 0,
  "connection_id": "smtp-connection-id"
}
```

### 5.2 Événements réputationnels et comportementaux

Agréger, par fenêtre de temps et par clé de segmentation :

- acceptations SMTP 2xx ;
- deferrals / réponses temporaires 4xx ;
- rebonds définitifs 5xx ;
- codes SMTP exacts et texte de réponse ;
- délai avant acceptation ;
- nombre de retries ;
- messages expirés après durée maximale de queue ;
- plaintes spam ;
- désabonnements ;
- ouvertures, avec prudence méthodologique ;
- clics ;
- réponses humaines ;
- conversions lorsque disponibles ;
- blocs listés ou alertes de réputation ;
- métriques Gmail Postmaster lorsque accessibles.

### 5.3 Limites des ouvertures

Les ouvertures ne doivent pas être considérées comme une mesure fiable de lecture humaine : Apple Mail Privacy Protection, proxy d’images et outils de sécurité peuvent les gonfler ou les fausser.

L’agent doit pondérer plus fortement :

- plaintes spam ;
- bounces définitifs ;
- deferrals et acceptation SMTP ;
- clics, réponses et conversions ;
- désabonnements ;
- ouvertures comme signal secondaire.

## 6. Classification des réponses SMTP

### 6.1 Succès : 2xx

Exemples : 250 2.0.0, 250 OK.

Interprétation : le serveur destinataire accepte le message pour traitement. Cela ne garantit ni l’arrivée en boîte de réception, ni l’absence de classement spam.

Action :

- compter comme acceptation ;
- actualiser le débit accepté ;
- ne pas accélérer sur une seule réponse ;
- utiliser une fenêtre statistique minimale.

### 6.2 Réponse temporaire : 4xx

Exemples : 421, 450, 451, 452, et réponses enrichies 4.7.x.

Interprétation : le message peut être réessayé. Le motif peut être une boîte pleine, un incident distant, du greylisting, une politique temporaire, une limitation de débit, une réputation insuffisante, ou une saturation.

Action générale :

- ne pas supprimer l’adresse immédiatement ;
- classer le motif lorsque le code et le texte le permettent ;
- limiter le débit de la queue concernée si la réponse indique un throttling ou si la fréquence dépasse le seuil de risque ;
- appliquer un retry avec backoff exponentiel et jitter ;
- ne jamais marteler le même MX.

### 6.3 Réponse définitive : 5xx

Exemples : 550, 551, 552, 553, 554.

Interprétation : échec réputé définitif ou nécessitant une intervention manuelle. Cependant, le texte SMTP doit être analysé : certains 5xx sont des refus de contenu, de politique ou de réputation et ne signifient pas nécessairement que l’adresse est invalide.

Action :

- user unknown, mailbox not found, domaine inexistant : suppression définitive de l’adresse ;
- politique, spam, réputation ou authentification : ne pas supprimer automatiquement l’adresse sans classification ; suspendre ou ralentir la source concernée ;
- analyser les motifs récurrents par FAI, IP, domaine, URL et campagne.

### 6.4 Taxonomie recommandée

Classer chaque réponse dans une catégorie :

```text
accepted
transient_rate_limit
transient_server_busy
transient_greylisting
transient_mailbox_full
transient_unknown
permanent_invalid_recipient
permanent_invalid_domain
permanent_policy_or_spam
permanent_authentication
permanent_content_or_url
permanent_unknown
```

La catégorisation doit utiliser le code SMTP, le code amélioré, le texte de réponse, le fournisseur et l’historique récent.

## 7. Algorithme de débit adaptatif

### 7.1 État par queue

Pour chaque queue, stocker :

```json
{
  "queue_key": "ip+identity+stream+provider",
  "state": "warming|stable|cautious|throttled|paused|recovery",
  "rate_limit_per_hour": 100,
  "rate_limit_per_minute": 2,
  "max_connections": 1,
  "max_messages_per_connection": 20,
  "warmup_ceiling_per_day": 1000,
  "learned_safe_rate_per_hour": 100,
  "defer_rate": 0.0,
  "hard_bounce_rate": 0.0,
  "complaint_rate": 0.0,
  "last_throttle_at": null,
  "last_rate_change_at": "ISO-8601",
  "consecutive_healthy_windows": 0,
  "consecutive_unhealthy_windows": 0
}
```

### 7.2 Fenêtres de mesure

Évaluer au moins :

- fenêtre courte : 5 à 15 minutes, pour détecter une saturation rapide ;
- fenêtre intermédiaire : 1 heure, pour les ajustements de débit ;
- fenêtre journalière : 24 heures, pour la chauffe, les plaintes, les hard bounces et la qualité d’engagement.

Ne pas prendre de décision de montée uniquement sur une fenêtre de quelques messages. Définir un volume minimal d’observation.

### 7.3 Indicateurs de santé

Pour chaque queue :

```text
Taux_defer      = 4xx / (2xx + 4xx + 5xx)
Taux_hardbounce = hard_bounces / messages_tentés
Taux_plainte    = plaintes / messages_livrés (ou acceptés) × 100
```

Un score de santé peut être implémenté, mais les règles de sécurité doivent toujours primer. Exemple indicatif :

```text
health_score =
  + acceptation_smtp_pondérée
  - pénalité_defer_rate
  - pénalité_hard_bounce_rate
  - pénalité_plainte
  - pénalité_erreurs_authentification
  - pénalité_volatilité_du_débit
```

### 7.4 Règle d’augmentation additive

Si toutes les conditions suivantes sont réunies :

- volume d’observation suffisant ;
- taux de deferrals sous le seuil ;
- aucun code de throttling critique ;
- hard bounces sous le seuil ;
- plaintes sous le seuil ;
- aucune alerte d’authentification ou de réputation ;
- la queue est sous son plafond de chauffe ;

alors augmenter lentement :

```text
nouveau_débit = min(débit_actuel × 1,10 à 1,25, plafond_de_chauffe, capacité_apprise)
```

Valeur par défaut prudente : +10 % à +20 % par période de décision. Pour une IP neuve, une hausse journalière est généralement plus sûre qu’une hausse toutes les quelques minutes.

### 7.5 Règle de réduction multiplicative

Si l’agent détecte :

- une réponse explicitement liée au rate limiting ;
- une hausse nette du taux de 4xx ;
- un code de réputation ou de politique ;
- une explosion de hard bounces ;
- une hausse de plaintes ;

alors appliquer :

```text
nouveau_débit = débit_actuel × 0,25 à 0,50
max_connections = 1
```

Valeur par défaut : réduction de 50 %.

En cas de signal sévère ou répété :

```text
queue_state = paused
pause_duration = 30 minutes à plusieurs heures selon le fournisseur et le motif
```

### 7.6 Exemple de pseudocode

```python
for queue in queues:
    metrics = compute_metrics(queue, windows=["15m", "1h", "24h"])
    signal = classify_queue_health(metrics, queue.smtp_error_patterns)

    if signal in ["critical_reputation", "critical_policy", "critical_authentication"]:
        queue.pause()
        queue.max_connections = 0
        alert_ops(queue, signal)

    elif signal == "explicit_throttle":
        queue.rate *= 0.50
        queue.max_connections = 1
        queue.schedule_retry_with_backoff()
        queue.state = "throttled"

    elif signal == "degrading":
        queue.rate *= 0.70
        queue.max_connections = max(1, queue.max_connections - 1)
        queue.state = "cautious"

    elif signal == "healthy" and queue.has_minimum_sample():
        queue.rate = min(queue.rate * 1.15, queue.warmup_ceiling, queue.learned_safe_rate)
        queue.state = "warming" if queue.is_warming else "stable"

    persist(queue)
```

Ce pseudocode est un cadre de décision, non une implémentation prête à exécuter sans paramétrage.

## 8. Backoff et politique de retry

### 8.1 Objectif

Le retry doit maximiser les chances de remise sans augmenter la pression sur le fournisseur distant. Une reprise agressive après un 4xx peut prolonger ou aggraver le throttling.

### 8.2 Stratégie recommandée

Pour les erreurs transitoires :

```text
retry_delay = min(base_delay × 2^attempt, max_delay) + jitter
```

Paramètres initiaux indicatifs :

| Tentative | Délai de base indicatif |
|---|---|
| 1 | 10 à 20 minutes |
| 2 | 30 à 60 minutes |
| 3 | 2 à 4 heures |
| 4 | 6 à 12 heures |
| 5+ | 12 à 24 heures selon SLA |

Appliquer du jitter aléatoire pour éviter que des milliers de messages soient renvoyés exactement au même instant.

### 8.3 Exceptions

- Les flux transactionnels peuvent nécessiter une politique plus courte, avec une durée de queue limitée par leur valeur métier.
- Les campagnes marketing tolèrent généralement des retries plus lents et plus longs.
- Un message dont la valeur expire rapidement ne doit pas être remis plusieurs jours après son utilité commerciale.
- Un 4xx de type mailbox full ne doit pas nécessairement déclencher la même baisse globale qu’un 421 4.7.x de rate limiting.

### 8.4 Durée maximale de queue

Définir une durée maximale distincte selon le flux :

| Flux | Durée maximale indicative |
|---|---|
| OTP / mot de passe / sécurité | Minutes à quelques heures selon SLA |
| Transactionnel non urgent | 24 à 72 h |
| Marketing / newsletter | 24 à 72 h, selon pertinence de campagne |
| Prospection | Souvent 24 h maximum ; ne pas envoyer une offre devenue obsolète |

À expiration, enregistrer le motif `expired_after_transient_failure` et analyser la queue concernée.

## 9. Profils initiaux prudents

Ces valeurs sont des garde-fous de démarrage, non des règles officielles des FAI ni des objectifs de volume. Elles doivent être ajustées par le système d’apprentissage décrit dans ce document.

Hypothèses : IP dédiée neuve ou peu réputée, domaine correctement authentifié, audience opt-in de bonne qualité, trafic marketing non critique.

| Destination | Débit initial indicatif | Connexions initiales | Hausse maximale initiale | Réaction au throttling |
|---|---|---|---|---|
| Gmail / Google | 50–150 messages/h | 1 | +10–20 % / jour | -50 %, pause 10–30 min, reprise 1 connexion |
| Outlook / Hotmail / Live | 25–100 messages/h | 1 | +10–15 % / jour | -50 %, retries ralentis, analyser 451 4.7.650 |
| Yahoo / AOL | 25–100 messages/h | 1 | +10–15 % / jour | -50 %, allonger backoff |
| Orange / Wanadoo | 25–75 messages/h | 1 | +10–15 % / jour | -50 %, isoler la queue et lire la réponse SMTP |
| La Poste / Free / SFR | 25–75 messages/h | 1 | +10–15 % / jour | -50 %, hausse lente et logs détaillés |
| Long tail B2B | 100–300 messages/h total | 1–3 | +15–20 % / jour | Freinage ciblé par MX/domaine |

Pour une IP déjà établie avec historique stable, les limites peuvent être beaucoup plus élevées. L’agent ne doit jamais supposer cette capacité : il doit la dériver des données observées.

## 10. Chauffe IP et domaine

### 10.1 Prérequis avant toute chauffe

Ne jamais démarrer une chauffe si les fondations techniques ne sont pas validées :

- SPF valide et aligné ;
- DKIM valide, clé et sélecteur correctement gérés ;
- DMARC publié, au minimum p=none pendant l’observation initiale si cela convient à la politique de l’organisation ;
- rDNS/PTR de l’IP vers un FQDN valide ;
- FQDN qui résout vers l’IP lorsque l’infrastructure l’exige ;
- HELO/EHLO cohérent ;
- TLS opérationnel ;
- adresses From, Reply-To, Return-Path cohérentes ;
- en-têtes List-Unsubscribe et List-Unsubscribe-Post: List-Unsubscribe=One-Click pour les flux marketing soumis aux exigences bulk ;
- lien de désabonnement visible et réellement fonctionnel ;
- gestion immédiate des désabonnements ;
- politique de suppression des hard bounces ;
- tracking domain cohérent et réputé ;
- absence de redirections ou URLs manifestement risquées ;
- segmentation des destinataires par récence et engagement.

### 10.2 Ordre de ciblage

Pendant une chauffe, privilégier dans cet ordre :

1. destinataires ayant récemment ouvert, cliqué, répondu ou acheté ;
2. abonnés récents avec consentement prouvable ;
3. clients actifs ;
4. abonnés anciens mais dont l’activité est connue ;
5. segments inactifs seulement après stabilisation ;
6. ne pas utiliser de listes louées, achetées ou insuffisamment documentées.

### 10.3 Rythme plutôt que pics

Le trafic doit être réparti sur la journée. Éviter :

- l’envoi de tout le volume en quelques minutes ;
- l’alternance entre zéro trafic pendant des semaines et pic massif ;
- l’ajout soudain de nombreux sous-domaines ou nouvelles IP ;
- le changement simultané d’IP, domaine, créa, URL de tracking et segment.

Changer une variable à la fois afin de conserver une capacité d’attribution lors d’un incident.

## 11. Réputation, conformité et qualité de liste

### 11.1 Le débit ne compense jamais une mauvaise liste

Un pilotage de cadence ne corrige pas :

- l’absence de consentement ;
- les adresses obsolètes ;
- les adresses pièges ou collectées sans transparence ;
- la pression marketing excessive ;
- le contenu trompeur ;
- l’absence de désabonnement ;
- un taux de plaintes élevé.

Si ces problèmes existent, ralentir peut réduire les dégâts mais ne rétablit pas durablement la délivrabilité.

### 11.2 Bonnes pratiques de gouvernance

Pour les flux marketing :

- stocker la preuve de consentement, sa date, sa source et la finalité ;
- permettre un désabonnement simple, immédiat et spécifique au canal ;
- respecter les suppressions dans toutes les plateformes et sous-traitants ;
- appliquer une politique de réengagement puis de suppression des inactifs ;
- séparer les flux transactionnels et promotionnels ;
- mettre en place une liste de suppression globale ;
- surveiller les signaux de fraude et d’inscriptions malveillantes ;
- documenter les responsabilités entre donneur d’ordre, ESP, MTA et sous-traitants.

### 11.3 Indicateurs d’alerte

Les seuils exacts doivent être adaptés au contexte, mais l’agent doit déclencher une investigation quand il observe :

- une hausse soudaine des 4xx pour une destination ;
- une hausse des 5xx par rapport au baseline ;
- des plaintes spam non négligeables ;
- une chute de clics et réponses sur des segments auparavant actifs ;
- un volume de désabonnements anormal ;
- une baisse de réputation dans les outils postmaster ;
- l’apparition de motifs SMTP liés à l’authentification, au spam ou à une politique ;
- une augmentation de l’âge moyen des messages en queue ;
- une hausse de la durée nécessaire avant l’acceptation SMTP.

## 12. Gestion d’incident

### 12.1 Incident de throttling

Symptômes : 421, 450, 451, 452, 4.7.x, hausse des deferrals, baisse d’acceptation, latence SMTP accrue.

Actions immédiates :

1. identifier la queue concernée : IP, identité, flux et fournisseur ;
2. réduire le débit de 50 % au minimum ;
3. ramener les connexions à 1 ;
4. suspendre temporairement les nouveaux lots si le signal est fort ;
5. activer backoff et jitter ;
6. vérifier les changements des dernières 24–72 h ;
7. vérifier la santé SPF, DKIM, DMARC, rDNS, HELO et TLS ;
8. analyser les segments, URLs, contenus et plaintes ;
9. ne reprendre qu’après amélioration mesurée ;
10. remonter lentement, pas par retour instantané au débit antérieur.

### 12.2 Incident de hard bounces

Symptômes : hausse de 550 5.1.1, user unknown, domaine inexistant ou boîtes inexistantes.

Actions :

1. arrêter immédiatement le segment ou la source de données suspecte ;
2. supprimer les adresses manifestement invalides ;
3. calculer les taux par acquisition source, campagne, ancienneté et domaine ;
4. vérifier l’import ou la transformation de données ;
5. mettre en quarantaine les sources douteuses ;
6. ne pas réchauffer l’IP avec une population de faible qualité.

### 12.3 Incident de réputation / spam

Symptômes : refus de politique, plaintes, baisse de réputation Postmaster, acceptation mais baisse de performance, augmentation de messages en spam.

Actions :

1. ralentir ou suspendre le marketing concerné ;
2. maintenir séparément les flux transactionnels légitimes si leur réputation est isolée ;
3. exclure les inactifs ;
4. réduire la fréquence de contact ;
5. vérifier les mécanismes d’opt-in et de désabonnement ;
6. analyser les modifications de contenu, domaine de tracking ou expéditeur ;
7. traiter la cause avant de relancer la volumétrie.

## 13. Architecture recommandée

### 13.1 Composants

```text
Source de campagnes / API
        ↓
Validation conformité et éligibilité destinataire
        ↓
Segmentation (engagement, récence, FAI, domaine, flux)
        ↓
Routeur de queues par IP + identité + destination
        ↓
Rate limiter adaptatif / token buckets
        ↓
MTA / SMTP pool
        ↓
Collecteur logs SMTP + webhooks ESP
        ↓
Moteur de classification des erreurs
        ↓
Moteur de réputation et décision
        ↓
Mise à jour des limites et alerting Ops
```

### 13.2 Modèle token bucket

Un token bucket par queue permet de limiter le débit moyen tout en autorisant de faibles rafales contrôlées.

Paramètres :

```text
refill_rate = messages/seconde autorisés
bucket_capacity = burst maximal autorisé
connection_limit = connexions SMTP simultanées
```

Règle : réduire à la fois refill_rate et bucket_capacity lors d’un throttling. Réduire le débit seul sans limiter le burst peut encore provoquer des pics nocifs.

### 13.3 Mise à jour persistante

Conserver l’historique des limites apprises. Au redémarrage, ne pas repartir automatiquement à une capacité très haute. Appliquer une pénalité de prudence après :

- une longue interruption de trafic ;
- un changement d’IP ;
- un changement de domaine ;
- une modification majeure de contenu ou tracking ;
- un incident récent ;
- une perte d’accès aux métriques de réputation.

## 14. Politique de sécurité et garde-fous

L’agent doit refuser ou escalader toute demande visant à :

- contourner les protections anti-spam d’un fournisseur ;
- envoyer des emails non sollicités ou sans base légale appropriée ;
- dissimuler l’identité de l’expéditeur ;
- créer des domaines jetables pour échapper à une réputation dégradée ;
- recommencer l’envoi vers des destinataires désabonnés, en hard bounce ou ayant déposé plainte ;
- ignorer les 4xx et augmenter le débit de force ;
- acheter, louer ou enrichir des listes sans contrôle de provenance et consentement ;
- falsifier les mécanismes SPF, DKIM, DMARC, les entêtes ou les mécanismes de désabonnement.

La mission du skill est l’optimisation de la délivrabilité d’un trafic légitime, consenti et techniquement conforme — jamais le contournement des protections des destinataires.

## 15. Format de recommandations attendu de l’agent

À chaque recommandation de débit, l’agent doit produire :

- la queue concernée ;
- les métriques observées et leur fenêtre temporelle ;
- la décision : augmenter, maintenir, réduire, suspendre ou reprendre ;
- l’ancien et le nouveau débit ;
- le nombre maximal de connexions ;
- le motif SMTP ou réputationnel ;
- la durée de la prochaine période d’observation ;
- les actions de diagnostic associées ;
- le niveau de confiance ;
- une indication claire lorsqu’il s’agit d’une hypothèse plutôt que d’une donnée officielle.

Exemple :

```text
Queue : IP 203.0.113.10 | DKIM mail.example.com | marketing opt-in | Gmail
Fenêtre : 60 minutes
Volume tenté : 120
Acceptés : 104 (86,7 %)
Deferrals : 15 (12,5 %), dont 10 réponses 421 4.7.x
Hard bounces : 1 (0,8 %)
Décision : Réduire
Débit : 120/h → 60/h
Connexions : 2 → 1
Retry : backoff initial 30 min, jitter ±20 %
État : throttled
Diagnostic : probable rate limiting Gmail ; vérifier hausse de volume et réputation Postmaster
Réévaluation : après 30 min et au moins 30 nouvelles tentatives
Confiance : élevée
```

## 16. Checklist avant lancement

### Technique

- SPF valide
- DKIM valide
- DMARC publié et aligné
- PTR/rDNS valide
- HELO/EHLO cohérent
- TLS actif
- From, Reply-To, Return-Path cohérents
- Tracking domains vérifiés
- Désabonnement fonctionnel
- One-click unsubscribe configuré si nécessaire
- Gestion hard bounce et suppressions active
- Logs SMTP détaillés disponibles
- Queues séparées par destination
- Rate limiter et backoff testés

### Données et conformité

- Finalité et base légale documentées
- Preuve de consentement disponible lorsque requise
- Source d’acquisition connue
- Suppressions synchronisées
- Inactifs exclus ou traités dans une campagne de réengagement séparée
- Segments de chauffe composés de contacts engagés
- Pas de liste achetée ou non documentée

### Exploitation

- Profil de débit initial défini
- Seuils de pause et d’alerte configurés
- Monitoring temps réel disponible
- Responsable d’escalade identifié
- Plan de rollback prêt
- Test à faible volume effectué

## 17. Résumé exécutable par un agent

```text
1. Vérifier conformité et authentification avant envoi.
2. Segmenter les files par IP, domaine d’identité, type de flux et fournisseur destinataire.
3. Démarrer sous une limite de chauffe prudente.
4. Envoyer d’abord aux contacts les plus engagés et aux listes les plus propres.
5. Mesurer 2xx, 4xx, 5xx, plaintes, désabonnements, engagement et réputation.
6. En cas de signaux sains, augmenter graduellement, sans dépasser le plafond de chauffe ni la capacité apprise.
7. Au premier signal de throttling ou de dégradation, réduire fortement la queue concernée, limiter les connexions et appliquer un backoff.
8. Ne pas pénaliser les autres fournisseurs pour un incident localisé.
9. Ne jamais traiter les ouvertures comme l’unique preuve de qualité.
10. Ne jamais utiliser ce système pour contourner les protections anti-spam ou envoyer des messages non sollicités.
11. Consigner chaque décision, son motif, ses métriques et son effet.
12. Réapprendre continuellement les limites par fournisseur, identité d’envoi et type de flux.
```

## 18. Références publiques de départ

- Gmail — Email sender guidelines
- Gmail — Sender guidelines FAQ
- Gmail — SMTP errors and codes
- Gmail — Postmaster Tools
- Yahoo Sender Hub — FAQ
- La Poste — Conditions générales
- La Poste — Postmaster
- Microsoft Q&A — 451 4.7.650
- Mailgun — IP addresses and sending volume

Note : les blogs et retours d’expérience d’ESP ou d’experts MTA peuvent servir à proposer des profils initiaux. Ils ne doivent jamais être présentés comme des limites officielles de fournisseurs de messagerie.
