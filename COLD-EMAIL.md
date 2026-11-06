# COLD EMAIL & AUTOMATISATIONS — LeClientROI

> Écrit le 2026-08-25. Décrit ce qui part réellement, pourquoi c'est écrit ainsi, et ce qui
> l'empêche de partir trop vite.

---

## 1. Le fait qui porte tout : la loi Cazenave

**Loi n° 2025-594 du 30 juin 2025, entrée en vigueur le 11 août 2026.** Appeler un
particulier sans son consentement écrit préalable est interdit, tous secteurs confondus.
**Amende jusqu'à 375 000 € par appel** pour une personne morale. Le régime passe de
l'opposition (Bloctel) au consentement explicite.

**C'est déjà arrivé.** La première version de nos emails écrivait « quand le démarchage
téléphonique fermera » — au futur, deux semaines après l'entrée en vigueur. D'où l'absence
d'urgence relevée par Camille : on annonçait un événement passé. Les emails disent
désormais *« Depuis le 11 août… »*.

---

## 2. Ce que la personnalisation peut vraiment dire

Mesuré sur les contacts du site, pas supposé :

| secteur | contactables | société | ville | prénom |
|---|---|---|---|---|
| immobilier | 3 869 | **100 %** | **98 %** | **15 %** |
| agence-marketing | 1 113 | **100 %** | 76 % | 37 % |
| restaurant | 1 162 | 98 % | 98 % | 17 % |

**Le prénom manque sur 85 % des contacts immobiliers.** Ouvrir sur `{{prenom}}` produisait
« Bonjour, » pour la grande majorité — une personnalisation qui n'en est pas une. Les
emails ouvrent donc sur un « Bonjour, » assumé, et personnalisent avec ce qu'on possède
vraiment : **la ville** (dans l'objet et le corps) et **la société**.

Objet réel reçu par une agence nantaise : **« mandats Nantes »**.

Variables utilisables : `prenom`, `nom`, `entreprise`/`societe`, `ville`/`city`,
`expediteur_prenom`, `expediteur_nom`, `UNSUBSCRIBE_LINK`. Toute autre variable **bloque
l'envoi** à ce destinataire (`garde_variables`) — c'est voulu : un email qui part avec
`{{whatever}}` ne se rattrape pas.

---

## 3. Les règles d'écriture, et d'où elles viennent

Source : `skills/cold-email` (Corey Haines), données 2024-2025.

| Règle | Donnée | Application |
|---|---|---|
| Objet 2-4 mots, minuscules | 2 mots = **+60 % d'ouverture** vs 5 | « mandats Nantes », « budgets déplacés » |
| Moins de 75 mots | **+83 % de réponses** | 40 à 80 mots, signature comprise |
| « vous » domine « nous » | — | on ouvre sur leur situation |
| UNE preuve chiffrée | une preuve bat dix fonctions | 8,2 % vs 3,4 % · 10M SMS · 375 000 € |
| CTA d'intérêt | rendez-vous au 1er contact = erreur n°7 | « Le principe en deux minutes » |
| Le gras porte le FAIT | — | la date, le montant, le taux — jamais l'argument |
| Spintax | un texte identique mille fois se reconnaît | 2 à 16 variantes par email |

**Ce qu'on ne fait pas** : pas d'image, pas d'emoji, pas de « cliquez ici » (terme noté par
les filtres — retiré des désinscriptions), pas de faux « Re: », pas de gabarit identique
avec le secteur échangé.

**Deux liens par email** : le CTA de prise de rendez-vous (exigé par le lint) et
`https://leclientroi.com/`. Le guide en conseille zéro au premier contact ; c'est un
arbitrage assumé de Camille, et un lien juste vaut mieux qu'un lien absent.

---

## 4. Les expéditeurs, et pourquoi la signature n'est pas écrite en dur

Huit adresses, **deux pools qui ne se mélangent jamais** :

| usage | adresses | expéditeur |
|---|---|---|
| **adhoc** (campagnes) | j.bernard@, j.durand@, j.juste@, j.nguyen@ | Juliette Bernard / Durand / Juste / Nguyen |
| **mozart** (scénarios) | agence@, info@, news@ | **Pascal Cabral** |
| | immo@ | **Julie Durand** |

La signature utilise `{{expediteur_prenom}} {{expediteur_nom}}` : elle suit la boîte qui
envoie. **Elle disait « Juliette » en dur jusqu'au 2026-08-25** — un prospect recevant un
email de `immo@` (Julie Durand) le voyait signé « Juliette ». Un écart entre le `From` et la
signature est exactement ce que cherchent les filtres, et ce que remarque un lecteur.

**L'affinité prime sur les pools** : un contact déjà servi garde son adresse à vie, même si
elle appartient à l'autre pool. Voir `expediteur.choisir()`.

---

## 5. Les cinq automatisations Mozart

Choisies sur les volumes réels, pas au jugé.

| # | Scénario | Cible | Messages |
|---|---|---|---|
| 1 | Immobilier — nouveaux arrivants | 3 869 | first → relance1 → relance2 |
| 2 | Agences marketing — nouveaux arrivants | 1 113 | first → relance1 → relance2 |
| 3 | Agences — lisent mais ne cliquent pas | 1 113 | lelead:first → relance1 |
| 4 | Immobilier — reprise à froid 90 j | 3 869 | relance2 seule (rupture) |
| 5 | Restaurant — **en attente d'argumentaire** | 1 162 | *aucun* |

**Tous en brouillon.** Mettre en route un envoi automatique n'est pas une décision d'outil.

Trois principes dans chaque graphe :
- **J+1 avant le premier message** — le contact vient d'être collecté et vérifié.
- **Les relances ne partent qu'aux non-réactifs** — relancer quelqu'un qui a ouvert, c'est
  le punir d'avoir lu. Le scénario 3 trie sur le **clic** et non l'ouverture : ceux qui ont
  cliqué sont déjà en conversation.
- **Délais croissants, J+4 puis J+7** — au-delà, une relance ne relance plus, elle recommence.

**Le scénario 5 dort sur le premier gisement de la collecte** : 1 979 fiches restaurant en
trente jours, aucun argumentaire (en attente depuis le 2026-08-23).

---

## 6. Ce qui empêche un scénario de tout envoyer d'un coup

C'est le point le plus important de ce document.

Un scénario ne décide pas de ce qu'il envoie : **les adresses décident.**

- Une adresse neuve n'envoie **rien pendant 14 jours** (chauffe), puis monte de **15 à 35
  par jour**. Les quatre boîtes Mozart, créées le 25/08, sont muettes **jusqu'au 8 septembre**.
- Quatre plafonds s'appliquent, **le plus bas gagne** : plafond Maildoso, plafond de
  progression (+50 % de la moyenne des 7 derniers jours actifs), rampe de flotte, chauffe
  individuelle.
- **`inscrire()` n'inscrit jamais plus que 7 jours de capacité réelle.** Sans cette borne,
  il prenait 500 contacts par passage et le cron tourne toutes les heures : douze mille
  personnes en file pour soixante envois par jour. Ces contacts auraient attendu des mois,
  reçu un message périmé, et la fenêtre de non-recontact de 120 jours les aurait bloqués
  entre-temps.
- **4 minutes minimum entre deux envois d'une même boîte**, contrôlées avant le SMTP.
- **Fenêtre 09:01–18:30, du lundi au samedi**, heure de Paris.

La page `/site/{code}/mozart` affiche la capacité du jour, les adresses en chauffe avec leur
date de sortie, la file en attente et le nombre de jours pour la vider. **Avant la liste des
scénarios**, parce que c'est ce qu'il faut savoir avant d'activer.

---

## 7. Envoyer un test

Le BAT de l'écran passe par Emelia — donc ni la bonne signature ni le bon expéditeur. Pour
un test fidèle, passer par le chemin réel :

```python
import maildoso_backend as md, expediteur as ex
import email_templates_backend as tb, html_templates_backend as htb
boites = {b['email']: b for b in ex.boites('lcr')}
t   = tb._get_one('lcr', 'immobilier', 'first')
msg = htb.resolve_campaign_message('lcr', 'cold:immobilier:first')
md.send_email('vous@exemple.fr', t['subject'], html=msg['html'], site='lcr',
              campaign_id='bat',                       # < 6 segments = exempté des 120 jours
              contact={'email': 'vous@exemple.fr', 'societe': 'ORPI Nantes', 'city': 'Nantes'},
              mailbox=boites['immo@leclient-roi.com'], suivi_ouverture=False)
```

Deux pièges : un `campaign_id` à **six segments ou plus** est traité comme un lot de
campagne et retombe sous la fenêtre de 120 jours ; et l'écart de **4 minutes par boîte**
s'applique aussi aux tests — pour en envoyer plusieurs d'affilée, changer d'adresse.

---

## 8. Où est quoi

| Quoi | Où |
|---|---|
| Les 24 cold emails | `email_templates` (god_mode.duckdb), écran `/site/{code}/cold-email` |
| Écriture et lint | `email_templates_backend.py`, `email_generator.validate_email` |
| Mots à risque, spintax, liens | `qualite_message.py` |
| Variables autorisées | `garde_variables.py` |
| Les 5 automatisations | `mozart_automations_lcr.py` |
| Capacité et borne de file | `mozart.capacite_jour()`, `mozart.inscrire()` |
| Expéditeurs et chauffe | `expediteur.py`, écran `/site/{code}/setup/expediteurs` |
