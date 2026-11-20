# Livrable B — Matrice des règles (26/09/2026)

> Pour chaque règle : sources qui l'utilisent, signal, faux positifs, faux négatifs, coût, verdict
> (fiable seule / seulement combinée / faible ou dangereuse / à exclure) et décision pour Mass Email.
> « Observable chez nous » : **S** = webhook Sweego (url, ip, user_agent, proxy, horodatage décalé),
> **R** = notre redirecteur first-party (page de rappel, désinscription GET, miroir, piège : heure serveur exacte,
> méthode, tous les en-têtes). Références des sources : voir `fiches-sources.md`.

| ID | Règle | Sources | Signal | Faux positifs | Faux négatifs | Coût | Observable | Verdict | Décision V1 (poids) |
|---|---|---|---|---|---|---|---|---|---|
| R01 | UA automatisé explicite (curl, wget, python-requests, Go-http-client, Java/, okhttp, axios, node-fetch, undici, aiohttp, Apache-HttpClient, HeadlessChrome, Puppeteer, Playwright, bot/crawler/spider en mot entier) | Mautic 2c (Matomo DeviceDetector), click-tracker 13, mail-tracker 10, slack-crm 3, Marketo IAB D12 | sous-chaîne / motif ancré | quasi nuls si motifs précis ; élevés avec /outlook/, /security/, /fetch/ (slack-crm) | tous les scanners à UA Chrome banal (BNP, #16263) | nul | S, R | fiable seule **quand elle matche** (rare) | **retenir, −80** ; nettoyer la liste (voir recommandation) |
| R01b | UA vide ou < 10 caractères | slack-crm 3, click-tracker 13, mail-tracker 10 | longueur | proxys qui suppriment l'UA (rare) | — | nul | S, R | fort | **retenir, −60** |
| R01c | UA « Safe Links » historique `MSIE 8.0` / `Trident/4.0` | instantly #773 | sous-chaîne | IE8 réel en 2026 : négligeable | Safe Links moderne à UA Chrome | nul | S, R | fort quand il matche | **retenir dans la liste R01** |
| R01d | Chrome **non réduit** (Chrome/NNN.x.y.z ≠ .0.0.0) | instantly #773 ; Chrome UA reduction (Chrome 101-110) | regex | Chrome d'entreprise gelé/ancien < 101, WebView Android | scanners qui imitent l'UA réduit (BNP : Chrome/148.0.0.0) | nul | S, R | faible seule | **retenir, −15, jamais seule** |
| R02 | Méthode HEAD / OPTIONS / TRACE | instantly #773 ; cahier § 9.2 | méthode HTTP | aucun navigateur ne fait HEAD sur une navigation | la plupart des scanners font GET | nul | **R seulement** (Sweego ne donne pas la méthode) | fiable seule | **V1.5, −60** : journaliser la méthode sur nos routes publiques (aujourd'hui FastAPI répond 405 à HEAD sans rien noter) |
| R03 | Signature de passerelle dans l'URL (safelinks.protection.outlook.com, urldefense, mimecast, cudasvc) | atc0005 5, cardi 6b, gists 7-8, D1, D4-D7 | domaine de réécriture | le **vrai humain** passe aussi par la passerelle (D1 : scan au clic) | mode « Do not rewrite » (D1) : aucune signature | nul | **non observable** : la requête qui nous arrive porte notre URL ; Sweego ne transmet pas le Referer | inutilisable comme score | **écarter du score** ; diagnostic support seulement |
| R03b | Réseau d'un éditeur de sécurité (AS8075 Microsoft, AS14080/26211 Proofpoint…) | IntellectIT 2b (affichage), GoPhish #1607 | ASN | humain derrière une passerelle proxy web d'entreprise (Zscaler…) | fermes de scan sur hébergeurs génériques (BNP : Amazon, ColoCrossing, HostRoyale, Code200) | faible (base ASN) | S, R | faible | **V2, −10, jamais seule** (affichage d'abord) |
| R04 | Clic < N s après l'envoi | Mautic 2c (2 s), slack-crm (5 s / MPP 30 s), notre delai_min_s 15 s, guide délivrabilité (30 s) | délai | humain qui attendait le mail (cahier § 9.4) ; l'écart envoi → remise varie | scanners qui passent à la remise, 20-60 s après l'envoi (#16263, BNP 26 s) | nul | **R exact ; S faux (+600 s observés)** | faible seule | **retenir sur R seulement : < 60 s → −20** ; **désactiver sur S** tant que le décalage Sweego n'est pas mesuré |
| R05-R07 | Rafale de liens distincts (3/3 s, 4/5 s, 5/10 s) | cahier § 10 ; Marketo proximité 0-3 s (D12) ; notre rafale 3/10 s ; SendGrid D8 | nb d'URL distinctes par destinataire et fenêtre | humain qui ouvre 3 onglets très vite (possible à 10 s, rare à 3 s) | scanner lent (1 lien / 30 s) | nul | S (écarts justes), R | **fort** ; très fort à ≥ 5 | **retenir** : ≥ 3 URL / 10 s → −60 ; ≥ 5 URL / 10 s → −80 ; compter **tous** les types de liens (contenu, désinscription, miroir, tel:, piège), pas seulement « contenu » |
| R08 | Presque tous les liens du mail dans une même fenêtre | cahier § 10 ; #16263 (23 hits) ; BNP (9/9 liens) | nb URL demandées / nb URL du mail | aucun humain | scanner partiel | faible (compter les liens au moment de l'envoi) | S, R | fort | **absorbé par R05-R07 (≥ 5 / 10 s)** ; ratio ≥ 80 % en V2 |
| R08b | **Paire désinscription + contenu** à ±60 s | instantly #773 ; BNP | lien de désinscription ET autre lien du même mail | humain qui clique puis se désinscrit dans la minute (rare, sans enjeu KPI) | scanner qui ignore le pied de mail | nul | S, R | fort | **retenir, −50** |
| R08c | Lien piège caché (honeypot 1 px / display:none) | notre `clics.ajouter_piege` ; IntellectIT 2b ; Marketo 2022 (plus documenté en 2026) | hit sur un lien invisible | lecteurs d'écran / navigation clavier si mal fait ; clients qui affichent les liens ; aucun cas BNP | scanners qui ne suivent que les liens visibles | **risque délivrabilité** : Gmail D14 « Don't use HTML and CSS to hide content » ; Defender D3 : texte caché = signal d'évasion | S, R | fort mais redondant (BNP : rafale + paire suffisent) | **supprimer des nouveaux envois** ; garder l'endpoint et le signal pour les mails déjà partis |
| R09 | Même IP sur ≥ N destinataires en 10 min | cahier § 10 (20/10 min) ; SendGrid D8 ; slack-crm (même IP 60 s) | IP × destinataires | NAT d'entreprise (tous les salariés d'une société derrière 1 IP), Apple iCloud Private Relay, CGNAT mobile | fermes à IP tournantes (BNP : 7 IP pour 1 personne) | nul | S, R | seulement combinée | **retenir, −30**, seuil 10 destinataires / 10 min, **uniquement si le domaine du destinataire diffère** ou combinée à une rafale |
| R09b | **Réseaux distincts pour UN destinataire** (≥ 3 /24 ou /48 en 120 s) | Mautic #16263 (3 IP / 30 s), IntellectIT 2b, fusion « echo » 14 ; BNP (5 réseaux / 2 min) | diversité réseau par destinataire | humain Wi-Fi + 4G + VPN en 2 min (≤ 2 réseaux en pratique) | scanner mono-IP | nul (calcul sur préfixe) | S, R | **fort** | **retenir, −60** |
| R10 | ASN cloud / datacenter / VPN | slack-crm (préfixes), GoPhish #1607, IntellectIT (affichage) | ASN | télétravail via VPN d'entreprise hébergé, proxy web cloud (Zscaler, Netskope) | hébergeurs non listés | base ASN (IPtoASN / Team Cymru / GeoLite2) | S, R | faible seule — **interdite seule** (cahier § 9.6) | **V2, −10** |
| R10b | Liste d'IP figée (`ips_robots`) | kb4 15, slack-crm 3, Mautic 2c | IP ∈ liste | IP réattribuées | tout le reste | maintenance | S, R | dangereuse seule | **garder vide ; −30 max, jamais seule** |
| R11 | Pas de visite de landing sous 10 min | cahier § 10 | absence d'événement R | page de rappel inactive ; destination hors de notre domaine | scanners qui suivent la redirection | nul | R | faible | **ne pas appliquer en V1** (la page de rappel n'est pas toujours active ; les liens directs n'y passent pas) |
| R12 | Arrivée sur la landing first-party | MS Customer Insights 1 (page intermédiaire) | GET sur la page de rappel | — (c'est un scanner dans le cas BNP : 8 « visites ») | — | nul | R | **nulle seule** (un scanner fait aussi le GET) | **0 point** : une visite seule ne prouve rien |
| R13 | Page active (JS : visible ≥ 3 s, focus) | GoPhish #1607, click-tracker 13 | beacon JS | JS bloqué | sandbox qui exécute le JS et attend | faible (script + endpoint) | R | faible seule | **V2, +15**, en observation d'abord |
| R14 | Navigation / en-têtes cohérents (Sec-Fetch-Mode=navigate, Sec-Fetch-User=?1, Accept-Language) | fusion 14 (`client_kind`) | en-têtes | navigateurs anciens, webviews | Chrome headless (envoie les mêmes en-têtes) | nul | R | faible seule | **V1.5 : journaliser seulement** (calibration), pas de poids |
| R15 | Formulaire validé serveur (POST « oui » / « non » sur la page de rappel) | MS 1, cahier § 10 | POST avec jeton signé | — | scanner qui soumet un formulaire (jamais vu ; bloqué par la case à cocher et le téléphone pour « oui ») | nul | R | **fort** | **retenir, +60** (POST refus = visite confirmée ; POST oui = conversion) |
| R16 | Conversion métier (rappel accepté, RDV, achat) | cahier § 10 | événement métier | — | — | nul | R | fort | **retenir, +60** (même règle que R15 pour « oui ») |
| R17 | Drapeau `proxy` de Sweego | Sweego (`clicked-proxy` : « Link clicked by a proxy or bot »), Ghost/Mailgun 9 | booléen ESP | méthode inconnue | 0 / 1 712 clics Cheffer ; 0 / 16 BNP | nul | S | moyen (boîte noire) | **retenir, −40** |
| R18 | Clic sans ouverture enregistrée | notre `sans_ouverture` | absence de pixel | images bloquées (Outlook, Gmail pro), MS D1 : ouvertures non fiables | scanner qui charge aussi le pixel | nul | S | **faible / trompeuse** | **passer à 0** (« ignorer ») |
| R19 | Clic isolé cohérent (1-2 URL, 1 réseau, pas de désinscription, > 60 s après la remise si R) | déduit de #16263, #773, D12 | absence de signaux négatifs | — | scanner mono-lien mono-IP (indétectable en V1) | nul | S, R | faible (présomption) | **retenir, +15** → `human_likely` |
| R20 | Lien tel: « cliqué » en HTTP | BNP | URL `tel:` passée par le redirecteur Sweego | humain sur mobile qui touche le numéro (possible) | — | nul | S | faible seule | **compter dans les rafales**, pas de poids propre |
| R21 | Correction manuelle (faux positif signalé) | GoPhish #1607 | action admin | — | — | faible | — | — | **V1 : champ `statut_force` + auteur + motif**, tracé |

## Classification (seuils de départ du cahier, conservés)

```text
score <= -60          security_scan
score -59 à -25       bot_suspected
score -24 à +14       unknown        (compté « clic qualifié non confirmé »)
score +15 à +39       human_likely   (compté « clic qualifié »)
score >= +40          human_confirmed (« visite confirmée » ; « conversion » si POST oui)
```

Score = somme des poids des règles déclenchées sur la **grappe** du destinataire (tous ses hits dans
± 10 min), puis le poids le plus positif de sa propre action (POST). Une règle positive (R15/R16) ne
peut ramener un clic au-dessus de `unknown` que si la grappe n'a **pas** de R01/R01b (UA de robot
explicite) : un POST humain après un scan fait passer **la personne** en `human_confirmed`, mais les
hits du scan restent `security_scan` (on qualifie des événements, puis on agrège par personne).

## Rejeu du cas BNP avec les règles V1 (sans lien piège)

| Lot (heure) | Règles déclenchées | Score | Statut |
|---|---|---:|---|
| Rappel 14:42:47-50, 52.34.76.65, 4 visites | R05 (≥ 3 requêtes / 10 s) −60 ; R04 (26 s après l'envoi, heure R) −20 | −80 | security_scan |
| Rappel 14:42:52-56, 54.70.53.60, 4 visites | R05 −60 ; R04 −20 | −80 | security_scan |
| Sweego 14:52:46-50, 9 URL | R05 fort (≥ 5 URL / 10 s) −80 ; R08b −50 | −130 | security_scan |
| Sweego 14:53:24-26, 3 réseaux | R09b −60 ; R08b (désinscription + tel: < 60 s) −50 | −110 | security_scan |
| Sweego 14:54:02-10, 185.152.39.x | R09b (4 réseaux / 120 s) −60 ; R08b −50 | −110 | security_scan |
| Sweego 14:54:25, 147.185.226.13 | R09b (5 réseaux / 120 s) −60 | −60 | security_scan |
| Contrôle humain 10:56 (Orange IPv6) | R19 +15 ; R15 POST oui +60 | +75 | human_confirmed + conversion |

Résultat identique au verdict actuel (tout « robot » côté BNP) **sans le lien caché**, et en plus les
8 « visites » de la page de rappel sont qualifiées `security_scan` par leurs propres règles.
