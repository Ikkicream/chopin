# CONTRÔLES — ce qu'il faut vérifier avant de dire « c'est fait »

> Écrit le 2026-08-25, après avoir livré une page morte en croyant l'avoir vérifiée.
> Chaque ligne ici vient d'une erreur réelle, pas d'une bonne pratique générale.

---

## 0. La règle qui les résume toutes

**Un message de succès n'est pas une vérification.** Il faut interroger *ce que le système
fait*, pas *ce qu'un outil dit avoir fait.

| Ce qui a menti | Ce qu'il fallait regarder |
|---|---|
| `✓ Compiled successfully` | le contrôle de types, puis le fichier réellement livré |
| un test vert écrit par moi | des données que je n'ai pas réparées moi-même |
| « le correctif est posé » | le journal de production, après coup |

---

## 1. Interface (Next.js)

### 1.1 Le build ne prouve RIEN
`next.config.ts` porte `typescript: { ignoreBuildErrors: true }`. **« ✓ Compiled
successfully » ne veut pas dire que la page s'ouvre.**

Le 2026-08-25 : un script de modification a échoué *avant* d'enregistrer le fichier, mais le
suivant a quand même ajouté la référence à la constante. Résultat livré en production :
`Uncaught ReferenceError: STYLE_CADRE is not defined` — sidebar plantée, **toute la page
morte**. Le build était vert.

```bash
cd genesis-ui && npx tsc --noEmit        # DOIT rendre zéro erreur
python3 tests/test_interface_compile.py  # le fige
```

### 1.2 Après un `sed`/script sur un fichier, relire ce qui a été écrit
Un script Python qui lève une exception après un `replace` mais **avant** le `write_text`
laisse le fichier intact — et si un second script s'exécute ensuite, il travaille sur une
base différente de celle qu'on croit. Toujours `grep` le résultat attendu après coup.

### 1.3 Vérifier le fichier LIVRÉ, pas le source
```bash
grep -rl "ma-classe-css" .next/static/chunks/   # la règle est-elle dans le bundle ?
```

### 1.4 Reconstruire l'interface casse les onglets ouverts
Les identifiants d'action changent à chaque build → `Failed to find Server Action` sur les
onglets restés ouverts. Le bandeau `NouvelleVersion` (via `/api/ui-build`) prévient
désormais. **Pour une correction qui touche les données ou le serveur, préférer la
maintenance** :
```bash
python3 scripts/maintenance_backend.py on "Correction en cours, retour dans 15 minutes."
python3 scripts/maintenance_backend.py off
```

### 1.5 Le cache du navigateur
Symptôme qui désigne le cache à coup sûr : **ça marche en navigation privée, pas dans le
profil normal.** Next sert ses pages prérendues en `s-maxage=31536000` ; nginx force
désormais `no-store` sur le document HTML et garde le cache d'un an sur `/_next/static/`.

### 1.6 Une page déclarée côté serveur doit être atteignable
La sidebar ne se servait de la liste du serveur que pour FILTRER : une page déclarée mais
absente du code restait invisible. Arrivé **trois fois** (Mozart, Onoff, Adresses d'envoi).
`tests/test_menu_et_droits.py` vérifie les deux moitiés du contrat.

---

## 2. Envois d'emails

### 2.1 Ne jamais vérifier une protection sur des données qu'on vient de réparer
Le 2026-08-24 : compteur par boîte validé sur un rattrapage manuel de la veille. Le chemin
de PRODUCTION n'écrivait toujours rien. **J'ai validé ma réparation, pas le mécanisme.**
→ Le seul contrôle qui compte interroge `email_events`, le journal de ce qui est
réellement parti.

### 2.2 Ne pas toucher à la configuration d'envoi pendant qu'un dispatch tourne
Le 2026-08-25 : quatre boîtes insérées en base pendant un dispatch → il en a happé une,
neuve, le jour même. Puis l'arrêt du dispatch a **brûlé la journée** (7 emails au lieu de
80), le marqueur `last_dispatch_day` bloquant toute reprise.
→ `_lot_abandonne()` autorise maintenant la reprise d'un lot mort. **Mais l'insertion d'une
adresse d'envoi reste un acte de production : dispatch à l'arrêt.**

### 2.3 Restaurer un service qu'on a interrompu ne se demande pas
J'ai attendu un accord pour relancer un envoi programmé que j'avais moi-même coupé. La
fenêtre s'est vidée. Réparer sa propre casse fait partie du travail.

### 2.4 Après un envoi, regarder le journal réel
```sql
SELECT mailbox, count(DISTINCT (email, campaign_id)), min(occurred_at), max(occurred_at)
  FROM email_events WHERE event_type='sent' AND occurred_at::date = CURRENT_DATE
 GROUP BY 1;
```
Ce qu'on y cherche : une boîte qui concentre tout, un écart inférieur à 4 min, un débit
supérieur à 15/h par adresse.

---

## 3. Données (pool DuckDB ↔ PostgreSQL)

### 3.1 Une écriture DuckDB doit avoir son miroir PostgreSQL
`mark_email_rejected` n'écrivait que dans DuckDB : chaque rejet laissait une fiche
« à vérifier » fantôme dans PostgreSQL, **pour toujours**. 1 561 rejets par jour.
→ Toute fonction qui écarte, blackliste ou rejette doit appeler `pg_sync`.

### 3.2 `pg_reconcile` ne réaligne que les colonnes CITÉES
Ajouter une colonne au schéma sans l'ajouter à son `UPDATE` la fait dériver en silence.
Et **ne jamais y mettre `updated_at = now()`** : c'est la dernière clé de tri de la pioche.

### 3.3 Une protection ne doit pas reposer sur une colonne qu'un autre travail réécrit
La fiche de test était protégée par `etat = 'exclu'` — que `pg_reconcile` remet à `ok`
chaque nuit depuis le pool. La protection tient sur `est_test`, que personne d'autre ne
touche.

### 3.4 DuckDB : un seul écrivain, et 80 % de la RAM par défaut
`memory_limit` mesuré à **6 Gio sur une machine de 7,7** → le noyau tue des processus au
hasard, y compris un dispatch en cours. Plafonné à 2 Gio + `preserve_insertion_order =
false` (qui a fait passer une requête de >1 Gio à 65 Mo).

---

## 4. Chiffres affichés

### 4.1 Un taux ne peut pas dépasser 100 %
162,5 % d'ouverture le 2026-08-25 : on divisait « les personnes ayant ouvert ce jour-là »
par « les emails envoyés ce jour-là » — deux populations sans rapport. **Numérateur et
dénominateur doivent porter sur les mêmes personnes** (cohorte).

### 4.2 Un chiffre lent cache souvent une mauvaise requête, pas un volume
76 s pour le tableau de bord → 0,83 s. Deux causes : des sous-requêtes corrélées, et une
liste lue dans DuckDB (3,70 s) que PostgreSQL rend en 0,06 s. **Mesurer avant d'ajouter un
cache** : une table matérialisée aurait masqué le problème et ajouté une invalidation à
maintenir.

---

## 5. API tierces

### 5.1 La documentation d'un fournisseur n'est pas la vérité
Onoff, le 2026-08-25 : `status=USED` documenté en majuscules → refusé ; `used` accepté.
`startDate`/`endDate` obligatoires mais non documentés. Enveloppes `callLogs` /
`messagesLogs` nommées nulle part — une enveloppe inconnue rend **une liste vide sans
erreur**, et l'écran affiche « aucun appel » alors que le fournisseur en a.
→ Toujours éprouver contre l'API réelle avant d'affirmer ce qu'elle fait.

### 5.2 Un délai trop court fabrique de fausses pannes
Ahrefs coupé à 3 s alors qu'il oscille entre 200 ms et 5,9 s. Et le message d'action
accusait la clé **dans tous les cas** — il envoyait chercher un problème là où il n'y en
avait pas. → 8 s, une seconde tentative, et une CAUSE (`cle` / `service` / `reseau`).

---

## 6. Système

### 6.1 Un fichier créé en `root` bloque le cron `autoblog`
Arrivé plusieurs fois. Après toute exécution manuelle en root :
```bash
find /home/autoblog/genesis -user root -newermt "-1 day" | head
chown autoblog:autoblog <fichiers>
```

### 6.2 Un test rouge en permanence n'est plus lu
Trois tests ont viré au rouge pour des raisons qui n'étaient PAS des défauts : une fenêtre
d'envoi fermée le soir, une prémisse périmée par la migration, une chaîne de caractères
changée par une réécriture. **Corriger la prémisse du test, jamais son résultat** — et
faire porter l'assertion sur la RÈGLE, pas sur son orthographe.
