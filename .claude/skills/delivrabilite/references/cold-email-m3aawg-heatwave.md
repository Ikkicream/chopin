# Cold email : position M3AAWG 2025 et liste noire Heatwave (Validity)

> Appris le 28/09/2026 à la demande de Camille. Sources :
> - M3AAWG, *Position on Cold Email*, v1.0, novembre 2025 (M3AAWG-154), https://www.m3aawg.org/sites/default/files/doc_files/m3aawg_position_on_cold_email.2025_0.pdf
> - Heatwave DBL (Validity), https://lookup.validity.tools/ : pages lookup, listing-policy, resources/deceptive-reputation-warming, partners, delist.

## 1. M3AAWG : position sur le cold email (texte intégral, résumé fidèle)

**Définition.** Un « cold email » est un email **non sollicité**, venant d'un expéditeur par ailleurs
légitime et identifiable, qui cherche à créer une relation d'affaires, une vente, une opportunité ou un
autre bénéfice professionnel auprès d'un destinataire **sans relation, lien ni consentement préalable**
avec l'expéditeur ou l'entreprise. Le document vise les pratiques **trompeuses** qui font passer ce cold
email pour une correspondance **un-à-un** alors que c'est du **spam**.

**Les marqueurs du cold email en masse** (tels que M3AAWG les décrit) :
- authentification, liens de désinscription et **personnalisation** (prénom, fonction, société…) ou
  contenu **généré par IA**, pour que chaque mail ait l'air écrit pour ce destinataire ;
- envoi à **intervalles aléatoires** ;
- **domaines sosies** (*lookalike domains* : ils ressemblent à un domaine légitime sans lui être liés,
  ex. paypal-security.com pour paypal.com) ;
- **plusieurs comptes d'envoi**, pour échapper aux filtres anti-spam.

**Position.**
1. Utiliser ou faciliter des méthodes d'envoi trompeuses pour masquer du cold email viole directement
   les valeurs de M3AAWG.
2. Les indicateurs de réputation qui signent le cold email sont notamment : **pièges à spam** (spam traps),
   **listes noires**, fort taux de **rebonds « utilisateur inconnu »**, fort taux de **plaintes**.
3. Sont **particulièrement graves et inacceptables** : contourner les limites de volume, éviter les
   filtres, **masquer les domaines d'envoi**, **simuler artificiellement l'engagement** des abonnés,
   exploiter des failles des messageries ou des plateformes cloud.
4. **Le consentement ne se transfère pas d'un canal à l'autre** : un accord pour être appelé par
   téléphone ne vaut pas accord pour recevoir du cold email.
5. Conclusion : envoyer de l'email non sollicité (dont le cold email) par des méthodes trompeuses est
   une **pratique abusive**.
6. S'ajoute à toutes les bonnes pratiques M3AAWG, notamment les positions sur la **vente de listes
   d'adresses** (www.m3aawg.org/SellingEmailLists) et sur l'**appending** (compléter une base avec des
   emails trouvés ailleurs, www.m3aawg.org/AppendingPosition).

## 2. Heatwave DBL (Validity) : la liste noire du cold email (lancée en septembre 2026)

**Ce que c'est.** Une liste noire de **domaines**, pas d'IP. Elle vise les domaines utilisés pour le
**warming synthétique** : des échanges automatiques entre boîtes contrôlées (ouvertures, réponses,
« important », sortie du spam) qui fabriquent une réputation avant la prospection. C'est exactement ce
que vendent les outils de « warmup ». Au 28/09/2026 : 1,2 M de domaines listés, environ 11 000 ajouts
par jour.

**Comment un domaine est listé.**
- Des signaux arrivent par le Validity Intelligence Network (données des messageries, pièges). Chaque
  message est classé **warming synthétique** ou **prospection à froid active**.
- Un score heuristique pèse l'**âge du domaine**, l'**infrastructure d'envoi** (infrastructure de cold
  email connue), le **contenu** (modèles partagés, personas regroupées, phrases génériques générées).
- Au-dessus du seuil, l'inscription est automatique. Les analystes peuvent revoir.

**Réponse DNS** `<domaine>.bl.validity.tools` → `127.A.S.E` :

| Octet | Sens |
|---|---|
| A (2e) | ancienneté de l'observation : 0 = moins de 7 j, 1 = 7-30 j, 2 = 30-90 j, 3 = 90-180 j, 4 = plus de 180 j |
| S (3e) | bande de gravité relative de 1 à 100, recalculée toutes les heures (0 = inscription manuelle) |
| E (4e) | 2 = warming seul ; **3 = passé à la prospection réelle** ; 4 = pré-warming (domaine frère d'une famille de warming, listé avant tout envoi) |

NXDOMAIN = pas listé. **La requête DNS est réservée aux partenaires.** Le public a la page de lookup,
limitée à **100 vérifications par jour** : `GET https://lookup.validity.tools/?domain=<domaine>`,
correspondance exacte (un sous-domaine est évalué seul).

**⚠️ Une inscription pour warming est PERMANENTE.** Elle n'expire pas quand on arrête. Seule une revue
qui prouve une **erreur** l'enlève (formulaire /delist, 2 à 5 jours ouvrés). Arrêter le warming ne
suffit pas. Le statut « prospection active » (E = 3) peut redescendre à 2, mais l'observation de warming
reste.

**Qui s'en sert.** Validity recommande aux messageries et aux filtres de sécurité de **filtrer** les
domaines listés, et aux ESP (Sweego…) d'en tenir compte à l'**onboarding** de leurs clients.

**Montée en charge légitime ou warming trompeur** (grille Heatwave) :

| Légitime | Trompeur |
|---|---|
| vrais destinataires consentants | boîtes automatiques en circuit fermé |
| engagement gagné | engagement fabriqué |
| vrai contenu | contenu généré pour tromper les filtres |

## 3. Ce que ça implique chez nous (audit du 28/09/2026)

**Domaines vérifiés sur Heatwave le 28/09/2026, tous « Not currently listed » :** leclientroi.com,
leclient-roi.com, leclientroi.email, news.leclientroi.email, t.news.leclientroi.email,
swg.news.leclientroi.email, leclientroi.app, cheffer.email, mail.cheffer.email, api.cheffer.email.

**Historique de warming synthétique (risque d'inscription permanente, pas de réputation actuelle) :**
- **Emelia : warmup actif sur `juliette@leclientroi.com` du 22/05 au 24/07/2026** : 495 échanges
  « good », 0 spam, 0 rebond. C'est le **domaine principal de la marque**.
- **Maildoso : warmup initial des boîtes `@leclient-roi.com`** (juin 2026, environ 2 semaines).
  Aujourd'hui : 0 service de warmup, `is_premium_warmup = false` sur les 8 boîtes.

**Règles qui en découlent :**
1. **Ne jamais réactiver** un warmup (Emelia, Maildoso ou autre) sur un domaine du groupe. Chez
   Mass Email, la chauffe se fait **uniquement** avec de vrais destinataires (agent de routage,
   skill pilotage-delivrabilite). C'est la « montée légitime » de la grille ci-dessus.
2. Vérifier Heatwave **avant chaque campagne** et **une fois par jour** pour chaque domaine d'envoi
   et de suivi, en même temps que les listes noires HetrixTools. Ne pas dépasser 100 vérifications par
   jour.
3. Si un domaine est listé à l'étape 3 (prospection active) : arrêter tout envoi depuis ce domaine,
   puis décider avec Camille (revue /delist seulement si c'est une vraie erreur).
4. Mass Email (B2C) : le consentement doit exister **pour l'email**. Un accord donné par téléphone ou
   à un tiers ne se transfère pas (M3AAWG § 4). La phrase de consentement doit dire la vérité sur
   l'origine de la liste.
5. Cheffer (B2B, cold email) : c'est le périmètre que vise M3AAWG. Sont à surveiller :
   - le domaine sosie `leclient-roi.com` ;
   - plusieurs boîtes et personas d'envoi ;
   - la personnalisation (prénoms déduits) et le contenu généré ;
   - les intervalles aléatoires ;
   - l'enrichissement d'emails (Basile/Serper = *appending*).
   Garder les indicateurs M3AAWG sous les seuils : pièges, listes noires, rebonds « utilisateur
   inconnu » (validation Mailnjoy), plaintes. Ne jamais faire de prospection à froid depuis
   `leclientroi.com`, le domaine de la plateforme cliente app.leclientroi.com.
