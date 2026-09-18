---
name: cold-email-engine
description: >
  Spécification d'intégration d'un séquenceur cold email MAISON (custom, sans
  Instantly/Smartlead) branché sur des boîtes SMTP/IMAP Maildoso, pour
  l'acquisition LeClientROI. Couvre : connexion SMTP/IMAP, schéma de base de
  données, boucle d'envoi (rotation des boîtes, throttling, ramp-up, heures
  ouvrées), spintax, threading des relances, détection de réponse/bounce/
  désinscription par IMAP, suppression list, conformité RGPD, et la séquence
  cold email au format machine. Utiliser DÈS QUE la tâche consiste à
  construire, modifier ou opérer le séquenceur custom, intégrer l'envoi cold
  email dans le code, gérer l'état des envois/réponses, ou brancher les boîtes
  Maildoso sur du code maison. Compléments : maildoso.md (infra/délivrabilité),
  coldemail.md (copywriting).
---

# Cold Email Engine — Séquenceur custom LeClientROI

Boîtes fournies par Maildoso = SMTP/IMAP standard. Maildoso ne fait QUE
l'hébergement, le warmup et la délivrabilité. Toute la logique d'envoi
(planification, rotation, relances, arrêt sur réponse) est à implémenter ici.

**Règle de sécurité absolue : aucun envoi cold tant qu'une boîte n'est pas
`active` (warmup Maildoso terminé, ~14 j). Le moteur doit refuser d'envoyer
depuis une boîte non active.**

Stack cible : Python sur VPS Hetzner, SQLite pour l'état transactionnel
(volume faible, écritures fréquentes), PM2 pour la supervision. DuckDB
optionnel en couche analytique sur export.

---

## 1. Connexion aux boîtes Maildoso

Récupérer les identifiants par boîte dans Maildoso (ou via "Export accounts") :

- **SMTP** : host, port `587` (STARTTLS) ou `465` (SSL), username = adresse
  complète, password.
- **IMAP** : host, port `993` (SSL), mêmes identifiants. Sert à lire les
  réponses.

Ne jamais stocker les mots de passe en clair dans le code. Variables
d'environnement ou fichier `.env` hors VCS, référencés par `password_ref`.

---

## 2. Schéma de base de données (SQLite)

```sql
CREATE TABLE mailboxes (
  id            INTEGER PRIMARY KEY,
  email         TEXT UNIQUE NOT NULL,
  domain        TEXT NOT NULL,
  smtp_host     TEXT NOT NULL,
  smtp_port     INTEGER NOT NULL,
  imap_host     TEXT NOT NULL,
  imap_port     INTEGER NOT NULL DEFAULT 993,
  username      TEXT NOT NULL,
  password_ref  TEXT NOT NULL,          -- clé vers le secret, pas le mdp
  status        TEXT NOT NULL DEFAULT 'warming', -- warming|active|paused
  warmup_until  DATE,                   -- date de fin de réchauffe
  daily_cap     INTEGER NOT NULL DEFAULT 10,
  sent_today    INTEGER NOT NULL DEFAULT 0,
  last_reset    DATE
);

CREATE TABLE prospects (
  id          INTEGER PRIMARY KEY,
  email       TEXT UNIQUE NOT NULL,
  first_name  TEXT,
  last_name   TEXT,
  company     TEXT,
  city        TEXT,
  sector      TEXT,                      -- resto|auto|immo|beaute|retail|artisan
  source      TEXT,
  validated   INTEGER NOT NULL DEFAULT 0,
  status      TEXT NOT NULL DEFAULT 'new', -- new|active|replied|bounced|unsubscribed|completed
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE campaigns (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  sector      TEXT,
  status      TEXT NOT NULL DEFAULT 'draft', -- draft|running|paused
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- définition de la séquence (étapes) par campagne
CREATE TABLE sequence_steps (
  id            INTEGER PRIMARY KEY,
  campaign_id   INTEGER NOT NULL,
  step_number   INTEGER NOT NULL,        -- 1,2,3,4
  delay_days    INTEGER NOT NULL,        -- délai depuis l'étape précédente
  subject_spintax TEXT NOT NULL,
  body_spintax    TEXT NOT NULL,
  UNIQUE(campaign_id, step_number)
);

-- état d'un prospect dans une campagne (machine à états)
CREATE TABLE enrollments (
  id              INTEGER PRIMARY KEY,
  prospect_id     INTEGER NOT NULL,
  campaign_id     INTEGER NOT NULL,
  mailbox_id      INTEGER,              -- boîte fixe sur tout le thread
  current_step    INTEGER NOT NULL DEFAULT 0,
  next_send_at    TIMESTAMP,            -- quand envoyer la prochaine étape
  thread_msgid    TEXT,                 -- Message-ID du 1er mail (threading)
  status          TEXT NOT NULL DEFAULT 'active', -- active|replied|stopped|completed
  UNIQUE(prospect_id, campaign_id)
);

CREATE TABLE messages_sent (
  id            INTEGER PRIMARY KEY,
  enrollment_id INTEGER NOT NULL,
  mailbox_id    INTEGER NOT NULL,
  step_number   INTEGER NOT NULL,
  rfc_msgid     TEXT NOT NULL,          -- Message-ID RFC généré
  subject       TEXT,
  body          TEXT,
  sent_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE events (
  id          INTEGER PRIMARY KEY,
  prospect_id INTEGER,
  mailbox_id  INTEGER,
  type        TEXT NOT NULL,            -- sent|reply|bounce|unsubscribe
  payload     TEXT,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE suppression (
  email      TEXT PRIMARY KEY,
  reason     TEXT NOT NULL,             -- replied|bounced|unsubscribed|manual
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 3. Spintax resolver

Résoudre `{a|b|c}` (y compris imbriqué) à CHAQUE envoi : une combinaison unique
par mail. C'est le levier de délivrabilité numéro un côté contenu.

```python
import random, re

def spin(text: str) -> str:
    pattern = re.compile(r'\{([^{}]*)\}')
    while True:
        m = pattern.search(text)
        if not m:
            return text
        choice = random.choice(m.group(1).split('|'))
        text = text[:m.start()] + choice + text[m.end():]
```

Puis interpoler les variables prospect : `{{prénom}}`, `{{entreprise}}`,
`{{ville}}`, `{{secteur}}`, `{{prénom_expéditeur}}`. Si une variable manque,
préférer une formulation neutre plutôt qu'un trou (gérer un fallback par champ).

---

## 4. Construction de l'email (texte brut + threading + RGPD)

```python
import email.utils, uuid
from email.message import EmailMessage

def build_email(mailbox, prospect, subject, body, thread_msgid=None):
    msg = EmailMessage()
    rfc_id = email.utils.make_msgid(domain=mailbox['domain'])
    msg['Message-ID'] = rfc_id
    msg['From'] = f"{prospect['sender_name']} <{mailbox['email']}>"
    msg['To'] = prospect['email']
    msg['Date'] = email.utils.formatdate(localtime=True)
    msg['Subject'] = subject

    # Threading des relances : même fil que le 1er mail
    if thread_msgid:
        msg['In-Reply-To'] = thread_msgid
        msg['References'] = thread_msgid

    # RGPD : header de désinscription obligatoire
    msg['List-Unsubscribe'] = f"<mailto:{mailbox['email']}?subject=unsubscribe>"
    msg['List-Unsubscribe-Post'] = "List-Unsubscribe=One-Click"

    # TEXTE BRUT UNIQUEMENT — jamais de set_content multipart/HTML
    msg.set_content(body, subtype='plain', charset='utf-8')
    return msg, rfc_id
```

Règles dures :
- `text/plain` strict. Aucun HTML, aucun pixel de tracking, aucune image.
- Étape 1 : nouveau `Message-ID`, objet normal → stocké dans `thread_msgid`.
- Étapes 2-4 : `In-Reply-To`/`References` = `thread_msgid`, objet `Re: …`.
- `List-Unsubscribe` header + une ligne de désinscription en clair dans le corps
  des relances (cf. séquence).

---

## 5. Boucle d'envoi (planification, rotation, throttling)

Cadence et garde-fous :

- **Ramp-up par boîte** depuis le passage `active` : semaine 1 → 10/j,
  S2 → 20/j, S3 → 30/j, plafond 40/j. `daily_cap` mis à jour automatiquement.
- **Heures ouvrées FR uniquement** : lun-ven, 9h-18h Europe/Paris. Pas de
  week-end, pas de nuit.
- **Délai aléatoire** entre deux envois : 30-180 s. Jamais de rafale.
- **Rotation** : répartir sur toutes les boîtes `active`, jamais épuiser une
  boîte avant les autres.
- **Boîte fixe par thread** : un prospect garde la même `mailbox_id` sur toute
  la séquence (cohérence d'expéditeur).
- **Reset quotidien** de `sent_today` à minuit.

```python
def runnable_now() -> bool:
    from datetime import datetime
    import zoneinfo
    now = datetime.now(zoneinfo.ZoneInfo("Europe/Paris"))
    return now.weekday() < 5 and 9 <= now.hour < 18

def tick(db):
    if not runnable_now():
        return
    for mb in active_mailboxes_with_quota(db):       # status=active, sent_today<daily_cap
        enr = next_due_enrollment(db, mb)            # next_send_at<=now, status=active, prospect pas supprimé
        if not enr:
            continue
        step = get_step(db, enr['campaign_id'], enr['current_step'] + 1)
        subject = spin(interp(step['subject_spintax'], enr))
        body    = spin(interp(step['body_spintax'], enr))
        thread  = enr['thread_msgid'] if enr['current_step'] > 0 else None
        if thread:
            subject = "Re: " + base_subject(enr)
        msg, rfc_id = build_email(mb, prospect(enr), subject, body, thread)
        send_smtp(mb, msg)                           # refuse si mb['status']!='active'
        record_sent(db, enr, mb, step, rfc_id, subject, body)
        if enr['current_step'] == 0:
            set_thread_msgid(db, enr, rfc_id)
        advance_step(db, enr, step, all_steps_done=is_last_step(step))
        increment_sent_today(db, mb)
        sleep(random.randint(30, 180))
```

`advance_step` : si dernière étape → `enrollments.status='completed'` ; sinon
`current_step += 1` et `next_send_at = prochain jour ouvré à +delay_days`.

---

## 6. Poller IMAP (réponses / bounces / désinscriptions)

Tourner toutes les 5-10 min. Pour chaque boîte, lire les non-lus et classer.
**C'est l'élément le plus critique d'un séquenceur custom : ne JAMAIS relancer
quelqu'un qui a répondu ou s'est désinscrit.**

```python
def classify(message) -> str:
    sender  = (message.get('From') or '').lower()
    subject = (message.get('Subject') or '').lower()
    text    = extract_text(message).lower()
    if any(k in sender for k in ('mailer-daemon', 'postmaster')) \
       or 'delivery has failed' in text or 'undeliverable' in text:
        return 'bounce'
    if any(k in text for k in ('désinscri', 'desinscri', 'me désabonner',
            'stop', 'ne plus me', 'unsubscribe', 'retirez-moi')):
        return 'unsubscribe'
    return 'reply'

def poll(db, mb):
    for message in fetch_unseen(mb):
        kind = classify(message)
        p = find_prospect_by_email(db, sender_email(message))
        if not p:
            continue
        log_event(db, p, mb, kind, raw=message)
        if kind == 'reply':
            set_status(db, p, 'replied'); stop_enrollments(db, p)
            add_suppression(db, p['email'], 'replied')   # plus jamais de cold auto
            notify_human(p)                              # à toi de traiter le thread chaud
        elif kind == 'unsubscribe':
            set_status(db, p, 'unsubscribed'); stop_enrollments(db, p)
            add_suppression(db, p['email'], 'unsubscribed')
        elif kind == 'bounce':
            set_status(db, p, 'bounced'); stop_enrollments(db, p)
            add_suppression(db, p['email'], 'bounced')
```

`stop_enrollments` passe tous les enrollments du prospect en `stopped`.
Vérifier la suppression list AVANT chaque envoi (jointure ou check explicite).

---

## 7. Kill-switch & monitoring

Pauser automatiquement pour protéger les domaines :

- **Bounce rate** > 3 % sur les 100 derniers envois d'une boîte → `status='paused'`
  pour cette boîte + alerte.
- **Bounce rate** > 5 % global → pause de toutes les campagnes.
- Surveiller le score de délivrabilité Maildoso ; sous 80 → pause + investiguer.
- Logs : chaque envoi/erreur SMTP/réponse dans `events`. Export DuckDB pour les
  stats (taux de réponse par secteur, par boîte, par variante).

PM2 : un process `engine` (boucle d'envoi) + un process `poller` (IMAP).
Reset `sent_today` via cron à 00:00 Europe/Paris.

---

## 8. Séquence cold email (format machine)

Spintax dense, à charger dans `sequence_steps`. Variables prospect interpolées
au runtime. Une campagne = un secteur (override de l'étape 1).

```yaml
sequence_base:
  # Approche SETTING : conversation -> permission -> faire parler -> insight.
  # Pas de pitch frontal. L'offre n'apparaît pas dans l'email 1.
  - step: 1
    delay_days: 0
    subject: "{petite question {{ville}}|question rapide|{{entreprise}} — une question}"
    body: |
      {Bonjour|Bonjour} {{prénom}},

      {Vous gérez|Vous tenez|Vous dirigez} {{entreprise}} à {{ville}}.

      {Question rapide, sans détour|Juste une question|Une vraie question} : {aujourd'hui, comment vous faites pour|comment vous vous y prenez pour} faire revenir les {clients|gens} {déjà venus une fois|qui sont déjà passés} ?

      {Si c'est un sujet pour vous en ce moment|Si ça vous parle}, {je vous partage une idée simple|j'ai une idée à vous montrer} — {sinon aucun souci, je n'insiste pas|sinon dites-le et je vous laisse tranquille}.

      {{prénom_expéditeur}}

  - step: 2
    delay_days: 3
    subject: "Re:"
    body: |
      {Bonjour|Re} {{prénom}},

      {En une ligne|Je reformule plus simplement} : {faire revenir vos clients du quartier|ramener du monde {en boutique|chez vous}}, {c'est un sujet en ce moment ou pas du tout|c'est d'actualité pour vous} ?

      {Un "oui" et je vous envoie un exemple concret sur {{ville}}|Si oui, je vous montre comment d'autres {{secteur}} s'y prennent}.

      Pour ne plus rien recevoir, répondez "stop".

      {{prénom_expéditeur}}

  - step: 3
    delay_days: 3
    subject: "Re:"
    body: |
      {Bonjour|Bonjour} {{prénom}},

      {La plupart des {{secteur}}|Beaucoup de commerces} {perdent le contact avec|oublient} leurs anciens clients {faute de temps|par manque de temps}, pas faute d'envie.

      {Et vous, c'est plutôt|Vous, vous diriez que c'est} le temps, l'outil, ou {ce n'est pas une priorité|pas le bon moment} ?

      {Répondez en un mot, j'adapte ce que je vous montre|Dites-moi et je rebondis}.

      Pour ne plus rien recevoir, répondez "stop".

      {{prénom_expéditeur}}

  - step: 4
    delay_days: 4
    subject: "Re:"
    body: |
      {Bonjour|Bonjour} {{prénom}},

      {Sans retour|Pas de réponse}, {je n'insiste plus|je vous laisse tranquille}.

      {Juste pour apprendre|Une dernière question qui m'aide vraiment} : {qu'est-ce qui a fait que ça n'a pas accroché|c'était quoi le frein} ? {Pas le moment, pas le sujet, ou pas clair|Mauvais timing, ou pas pour vous} ?

      {Un mot suffit|Même deux mots m'aident}, {merci d'avance|et ça me rendrait service}.

      {Belle journée|Bonne continuation},
      {{prénom_expéditeur}}

# Override de la QUESTION d'ouverture (étape 1) par secteur : remplace le mot
# "clients/gens" et l'objet pour coller au métier, sans réintroduire de pitch.
sector_overrides:
  resto:
    subject: "{une question {{entreprise}}|{{ville}}, vos tables}"
    q1: "comment vous faites pour faire revenir les clients qui sont déjà venus dîner une fois"
  auto:
    subject: "{une question {{entreprise}}|entretien {{ville}}}"
    q1: "comment vous faites pour que les clients d'une révision reviennent pour la suivante"
  immo:
    subject: "{une question {{entreprise}}|vos contacts {{ville}}}"
    q1: "comment vous réactivez les estimations et visites passées"
  beaute:
    subject: "{une question {{ville}}|vos clientes}"
    q1: "comment vous faites revenir les clientes qui espacent leurs RDV"
  retail:
    subject: "{une question {{entreprise}}|{{ville}}}"
    q1: "comment vous faites revenir les gens déjà venus une fois en boutique"
  artisan:
    subject: "{une question {{entreprise}}|{{ville}}}"
    q1: "comment vous relancez vos anciens clients"
```

---

## 9. Pré-flight (avant le 1er envoi, à J+14)

- [ ] Toutes les boîtes `active` (warmup terminé), score Maildoso ≥ 80
- [ ] Identifiants SMTP/IMAP chargés, mots de passe hors VCS
- [ ] `runnable_now()` respecte heures ouvrées FR + jours ouvrés
- [ ] `daily_cap` en ramp-up (10 → 40), `sent_today` resetté chaque nuit
- [ ] Délai aléatoire 30-180 s actif
- [ ] Texte brut strict, aucun tracking d'ouverture, aucun lien (sauf Global
      Custom Domain Tracking Maildoso activé)
- [ ] `List-Unsubscribe` header + ligne "stop" dans le corps
- [ ] Threading `In-Reply-To`/`References` vérifié sur les relances
- [ ] Poller IMAP en route : reply/bounce/unsub stoppent la séquence + suppression
- [ ] Suppression list vérifiée AVANT chaque envoi
- [ ] Kill-switch bounce rate (3 % boîte / 5 % global) armé
- [ ] ≥ 2 campagnes (secteurs) prêtes en parallèle
- [ ] Spam check passé sur chaque variante (mailmeteor)

---

## 10. Voir aussi
- `maildoso.md` — infra, architecture domaines, règles de délivrabilité.
- `coldemail.md` — principes de copywriting et variantes secteur.
