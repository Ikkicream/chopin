# OBJETS D'EMAIL — ce qui fait ouvrir, mesuré

> Écrit le 2026-08-26, après un retour de Camille : « aucune chance que ces objets ouvrent,
> 0 perso sur la forme, le fond, le secteur ». Elle avait raison, et les données le disent.
>
> Sources : Belkins (5,5 M d'emails, 2024, avec Reply.io) · Autobound (130 M d'emails B2B) ·
> Gong · Lavender · Experian · Marketing Dive.

---

## 1. Le classement, par type d'objet

C'est la donnée la plus utile, et celle que j'avais ignorée.

| Type d'objet | Taux d'ouverture | Exemple |
|---|---|---|
| **Question** | **46 %** | « vos mandats après le 11 août ? » |
| Appel à l'action | 44,6 % | « à voir avant septembre » |
| Contient un nombre | 44 % | « 375 000 € par appel » |
| **Description / adjectif** | **39 %** | ~~« marque blanche »~~, ~~« papier coûte »~~ |
| **Nom d'entreprise seul** | **38 %** | ~~« mandats Nantes »~~ |
| Jargon, urgence (« ASAP ») | < 36 % | « offre à ne pas manquer » |
| Salutation générique | < 36 % | « Bonjour cher partenaire » |

**Mes trois objets rejetés par Camille tombaient tous dans les deux dernières catégories
utiles** : « marque blanche » et « papier coûte » sont des descriptions (39 %),
« mandats Nantes » un nom de lieu (38 %). Aucun n'était une question.

---

## 2. La longueur

| Mots | Ouverture |
|---|---|
| 1 | 38 % (pas assez de contexte) |
| **2–4** | **46 %** |
| 7+ | 39 % |
| 9–10 | 34–35 % (tronqué sur mobile) |

Mobile : la coupure tombe vers **30–35 caractères**. Une question courte tient ; une
question longue devient une phrase coupée au milieu.

---

## 3. La personnalisation — et là je m'étais trompé de levier

| | Ouverture | Réponse |
|---|---|---|
| Objet personnalisé | **46 %** | **7 %** |
| Objet non personnalisé | 35 % | 3 % |

**+31 % d'ouverture, et le taux de réponse DOUBLE.** Le prénom dans le corps ajoute encore
41 % de clics.

Mais toute personnalisation ne se vaut pas :

- **Le prénom dans l'OBJET fait perdre 12 % de réponses** (Lavender) : il signale
  l'automatisation, parce que tout le monde le fait.
- **Ce qui marche dans l'objet, c'est le CONTEXTE** : un problème connu, un événement
  déclencheur, un concurrent, une échéance réglementaire.
- **Le prénom, lui, va dans le CORPS**, en ouverture.

### Ce qu'on possède réellement chez LCR

| secteur | société | ville | **prénom** |
|---|---|---|---|
| immobilier (3 869) | 100 % | 98 % | **29 %** |
| agence-marketing (1 113) | 100 % | 76 % | 37 % |

**0 % des prénoms manquants sont dérivables de l'adresse** : ce sont des `contact@`,
`info@`, `agence@`. Aucun dictionnaire ne les récupérera.

**Conséquence à assumer** : 71 % des contacts immobiliers ne recevront jamais de « Bonjour
Marc ». Deux réponses possibles, et la seconde est la bonne :
1. écrire « Bonjour, » pour tout le monde — on perd le levier ;
2. **servir d'abord les 586 contacts qui ont un prénom**, où la personnalisation joue à
   plein, et traiter les autres avec ville + société + secteur.

---

## 4. La casse — la croyance qu'il faut corriger

Le guide `cold-email` affirme que les minuscules gagnent (source Gong). Belkins mesure
autre chose sur 5,5 M d'emails :

| Casse | Ouverture |
|---|---|
| MAJUSCULES | 30 % |
| Première lettre de chaque mot | 29 % |
| minuscules | 29 % |
| Casse mixte | 28 % |
| Première lettre seulement | 25 % |

**L'écart est dans le bruit.** La casse ne décide de rien ; le TYPE d'objet décide de tout.
Les minuscules restent préférables pour l'allure « message interne », mais ce n'est pas
elles qui feront ouvrir.

---

## 5. Les emojis — quand ils marchent, et quand ils tuent

Les données sont contradictoires, et il faut le dire :

- **Experian** : 56 % des marques qui utilisent un emoji constatent une hausse d'ouverture.
- **Études récentes** : l'effet n'est visible qu'**occasionnellement**, surtout en période
  de fêtes.
- **69 % des destinataires signalent un email comme indésirable sur le seul objet.**

### La règle qu'on retient

| | |
|---|---|
| **Un seul emoji, jamais deux** | deux emojis = allure promotionnelle |
| **En fin d'objet, jamais en tête** | en tête il remplace un mot et brouille la lecture mobile |
| **Un emoji qui DIT quelque chose** | 🇫🇷 pour une structure française, 📞 pour un appel — jamais 🚀 🔥 💥 |
| **Jamais dans un premier contact froid B2B** | l'inconnu qui met un emoji vend quelque chose |
| **Jamais avec une urgence** | emoji + « urgent » = signalement quasi assuré |

**Chez LCR** : le drapeau 🇫🇷 a du sens dans le CORPS (« une structure française »), pas
dans l'objet d'un premier contact. On le réserve aux relances, où la relation existe.

---

## 6. Les formules qui fonctionnent

Par ordre de performance mesurée :

1. **Question sur un problème connu** — « vos mandats après le 11 août ? »
2. **Événement déclencheur** — « la loi Cazenave et vous »
3. **Connexion commune** — « via [nom] »
4. **Nombre qui interpelle** — « 375 000 € par appel »

### Ce qu'on n'écrit jamais

- Le prénom dans l'objet (−12 % de réponses)
- « Re: » ou « Fwd: » simulés (destruction de confiance)
- Une urgence inventée (« ASAP », « dernière chance ») : sous 36 %
- Plus d'un point d'exclamation, ou d'interrogation multiple (−36 %)
- Un mot en majuscules au milieu d'une phrase
- Le nom de notre produit — il ne dit rien au lecteur qui ne nous connaît pas

---

## 7. Le contrôle automatique

`qualite_message.controler()` refuse déjà les excès de forme (capitales dans l'objet,
exclamations en rafale, symboles monétaires). Ce document ajoute la règle qu'aucun code ne
peut vérifier : **un objet doit poser une question ou nommer un événement, pas décrire un
produit.**

Test à faire avant d'envoyer : *si je reçois cet objet d'un inconnu, est-ce que je me
demande de quoi il parle — ou est-ce que je sais déjà qu'on me vend quelque chose ?*

---

## 8. Les tics qui trahissent une machine

> Ajouté le 2026-08-26, sur un relevé de Camille : « comment je reconnais un email écrit
> par l'IA ? l'utilisation du caractère — impossible qu'un humain le tape, encore moins un
> Français, il ne sait pas le taper sur son clavier. »

Elle a raison, et c'était mesurable : **83 tirets cadratins dans 24 emails** que j'avais
écrits. Aucun clavier AZERTY ne produit « — » sans manipulation. Un lecteur français ne
saura pas dire pourquoi, mais il sentira que ce n'est pas une main humaine.

| Tic | Pourquoi il trahit | Ce qu'on écrit |
|---|---|---|
| `—` tiret cadratin | absent des claviers français | une virgule, un deux-points, ou un point |
| `–` tiret demi-cadratin | idem | un trait d'union ordinaire |
| `mot?` sans espace | typographie anglaise | espace **fine insécable** (U+202F) |
| objet tout en minuscules | lu comme une production machine en français | majuscule initiale |

**L'espace fine insécable, et pas une espace ordinaire** : avec une espace normale, le
« ? » peut basculer seul à la ligne suivante dans une boîte de réception étroite. Cela se
voit immédiatement.

`qualite_message.tics_ia()` les détecte et `typographie_fr()` les corrige.

**Un piège rencontré en écrivant cette règle** : ma première version insérait une espace
avant TOUT point-virgule, y compris celui qui termine une entité HTML. `l&rsquo;acquisition`
devenait `l&rsquo ;acquisition`, affiché tel quel dans l'email. Le point-virgule est donc
exclu de la règle : une règle typographique n'a pas à connaître le HTML.

---

## 9. Ce qui donne un visage à un expéditeur inconnu

Ajouté à la signature des 24 emails : **« Retrouvez-nous sur LinkedIn »**
(`https://fr.linkedin.com/company/leclientroi`). Une page d'entreprise consultable vaut
mieux qu'une promesse : elle permet de vérifier qui écrit avant de répondre.

---

## 10. Un objet doit VOULOIR DIRE quelque chose

> Camille, le 2026-08-26 : « les objets ne veulent rien dire. *Et vos clients, le SMS*, ça
> ne veut rien dire. »

C'est la règle qui manquait, et aucune donnée ne la remplace. J'avais optimisé la FORME —
question, 2 à 4 mots, minuscules — jusqu'à écrire des phrases amputées qui cochaient les
cases sans rien demander.

| Objet creux | Pourquoi | Objet qui demande quelque chose |
|---|---|---|
| « Et vos clients, le SMS ? » | phrase amputée, aucun verbe | **« Vos clients réclament du SMS ? »** |
| « Vos mandats après août ? » | après août, et alors ? | **« Vos mandats sans démarchage ? »** |
| « Je referme ? » | on referme quoi ? | **« On en reste là ? »** |
| « Qui appelle-t-on en urgence ? » | qui appelle qui ? | **« Vos dépannages viennent d'où ? »** |

**Le test** : lire l'objet seul, sans le corps. S'il ne pose pas une question à laquelle le
destinataire peut répondre dans sa tête, il ne vaut rien — même s'il fait deux mots et
qu'il finit par un point d'interrogation.

---

## 11. Écrire en français, pas en français traduit

Trois tournures qui trahissent l'outil plus sûrement qu'un tiret cadratin :

| Ce qui sent la traduction | Ce qu'on dit vraiment |
|---|---|
| « Vous semblez suivre l'acquisition pour X » | « Vous vous occupez sans doute du développement commercial chez X » |
| « sur des contacts consentants » | « auprès de gens qui ont accepté d'être contactés » |
| « Ces budgets cherchent une sortie » | « Ces budgets doivent bien aller quelque part » |

**Et une faute de construction à ne jamais refaire** : `{{entreprise}}` employé comme SUJET
du verbe. « Quand l'un d'eux vous demande du SMS, **Agence Pixel passe la main ?** » parle
de l'entreprise du lecteur à la troisième personne alors qu'on s'adresse à lui. On écrit
« **vous** passez la main ? ». La variable de société se place après une préposition — « chez
{{entreprise}} », « sous le nom de {{entreprise}} » — jamais devant un verbe conjugué.
