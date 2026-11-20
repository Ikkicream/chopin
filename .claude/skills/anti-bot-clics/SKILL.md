---
name: anti-bot-clics
description: Qualification des clics email et filtrage anti-bot (scanners Safe Links, Proofpoint, Mimecast, Barracuda, préchargements, robots) — distinguer clic brut, scan de sécurité, clic suspect, clic qualifié, visite confirmée et conversion, sans pénaliser les vrais humains. Utiliser pour tout ce qui touche au verdict des clics Mass Email (jobs/clics.py, settings.click_rules), aux KPI de clic remontés aux clients, au lien piège, à la page de rappel comme preuve de visite, ou pour lancer la recherche du cahier des charges.
---

# Anti-bot clics — qualifier un clic email

> Demande de Camille (25/09/2026) : « je ne veux pas donner à mes clients des informations sur des
> clics de bots ». Cahier de recherche complet (26/09/2026) : `references/cahier-recherche.md`.
> Voir aussi `.claude/skills/mass-email/SKILL.md` et `.claude/skills/delivrabilite/SKILL.md`.

## 1. Principes non négociables (cahier § 4, § 9.6, § 18)

1. **Le but est la qualité de la mesure, pas le blocage.** Un scan ne doit pas être compté comme un
   clic humain, mais on ne contourne ni ne bloque jamais une protection (Safe Links, Proofpoint…).
2. **Aucun signal seul ne suffit à exclure** : ni l'IP (cloud, VPN, proxy, NAT d'entreprise), ni le
   délai, ni la signature d'une passerelle, ni le navigateur (falsifiable), ni le JavaScript.
3. **Un clic via Safe Links ou Proofpoint n'est pas exclu définitivement** s'il est suivi d'une vraie
   visite (session first-party, comportement cohérent).
4. **On garde toujours le clic brut** (audit, recalcul quand les règles changent) ; règles, scores et
   motifs sont **versionnés et explicables**.
5. **Un GET ne déclenche jamais d'action irréversible** : désinscription, « oui, rappelez-moi »,
   notification commerciale. Seul un POST (bouton, RFC 8058) le fait.
6. **Honeypot = indice, jamais preuve unique**, jamais pénalisant pour un humain ni pour l'accessibilité.
7. **RGPD** : aucune donnée personnelle lisible dans une URL (jeton signé), identité séparée des logs
   techniques, IP brute à durée courte, pas de fingerprinting intrusif.
8. **Jamais « 100 % humain »** dans un rapport client : on explique que la qualification repose sur des
   signaux techniques et comportementaux.

## 2. Ce qui existe dans Mass Email (état au 26/09/2026)

| Brique | Où | Remarque |
|---|---|---|
| Événements bruts | webhook Sweego dédié → `webhook_events` (`raw_payload.click` = `url`, `ip_address`, `user_agent`, `proxy`) | Ce sont les clics **Sweego** (liens réécrits `t.news…`), pas un redirecteur à nous |
| Verdict humain / robot / suspect | `jobs/clics.py` `classer()`, table `clicks` (`verdict`, `raisons`, `secondes_depuis_envoi`) | 3 statuts seulement (le cahier en propose 6) ; pas de score chiffré |
| Règles | `settings.click_rules` : `piege_actif`, `piege_fenetre_s`, `delai_min_s`, `rafale_liens`, `rafale_fenetre_s`, `proxy_sweego`, `user_agent_vide`, `sans_ouverture`, `user_agents_robots`, `ips_robots` ; écran + `GET/PUT /reglages/clics` | Tout clic dans la fenêtre d'un clic sur le lien piège est « robot » |
| Lien piège | `clics.ajouter_piege()` : lien 1 px transparent en fin de mail | ⚠️ Contenu caché : le guide délivrabilité 2026 le déconseille (seul le préheader peut être caché) et Defender met en quarantaine le texte caché. À réévaluer |
| **Redirecteur first-party** | page de rappel `/api/public/mass-mailing/rappel?t=<jeton signé>` (quand `campaigns.rappel.actif`) : chaque lien du mail y passe, table `rappels` (`action` = visite / accepte / refuse, `ip`, `user_agent`) | C'est déjà l'« option 2/3 » du cahier, mais **les visites n'y sont pas qualifiées** (un scanner crée des « visites ») |
| Désinscription | GET = page de confirmation, POST = désinscription (correctif prêt, `outils-captures/correctifs/desinscription-get-confirmation.patch`) + `list-unsub` one-click | Déployer avant tout nouvel envoi |
| Export clients | `clics.lignes_export()` / CSV : humains seulement (robots en option) | Pas encore de KPI « scan » / « visite confirmée » / « conversion » |

## 3. Le cas réel du 26/09/2026 (palier 4, JAECOO) — à garder comme jeu de test

Destinataire `@bnpparibas.com` (passerelle de sécurité d'entreprise) :
- 16:42:46 : **les 9 liens du mail ouverts en ~4 s**, dont le lien `tel:`, le lien de désinscription
  (qui a désinscrit la personne : bug du GET) et le lien piège ; **8 « visites »** sur la page de rappel ;
  1 « ouverture ».
- Navigateur annoncé : **Chrome 148 / Windows 10, parfaitement banal** ; `proxy: false` ;
  IP 185.152.39.39 puis 147.185.226.13 (deux IP en quelques minutes).
- Événements webhook arrivés ~10 min après les faits ; nouvelle rafale identique quelques minutes plus tard.
- Verdict actuel : 15 clics « robot » (grâce au piège et à la rafale) → correct.
- Leçons : le navigateur ne prouve rien ; la **rafale + le piège** suffisent ici ; une passerelle rescanne ;
  **tout GET à effet de bord est dangereux** (désinscription, visite de rappel comptée).

## 4. Écarts avec le cahier (à combler, par ordre d'impact)

1. **Qualifier les visites de la page de rappel** comme les clics (rafale, piège, délai), et ne notifier
   le responsable qu'après un POST « oui » (déjà le cas) — ne jamais compter une « visite » brute au client.
2. **Score chiffré + 6 statuts** (`raw`, `security_scan`, `bot_suspected`, `unknown`, `human_likely`,
   `human_confirmed`) avec motifs versionnés, au lieu de 3 verdicts.
3. **Confirmation post-clic** : la page de rappel est une landing first-party → une vraie session
   (temps passé, visibilité, formulaire) fait passer en `human_confirmed` ; le formulaire validé = conversion.
4. **Signatures de passerelles** (Safe Links, urldefense, Mimecast, cudasvc…) comme signal pondéré,
   **rafale par IP sur plusieurs destinataires** (R09), méthode HEAD/OPTIONS (R02, possible seulement
   sur NOTRE redirecteur, pas sur les liens Sweego).
5. **KPI client** séparés : clic brut (audit), scans, suspects, clics qualifiés, visites confirmées,
   conversions (cahier § 12).
6. **Remplacer ou encadrer le lien piège caché** (risque délivrabilité, voir skill délivrabilité § 5).
7. **RGPD** : durée de conservation de `clicks.ip` / `rappels.ip` / `user_agent`, hash d'IP pour les
   rafales, mention dans le registre de traitement.

## 5. Lancer la recherche (le cahier)

Le cahier est un prompt pour un agent de recherche (web + GitHub) : lire chaque source du § 6 et § 7,
fiche par source (§ 8), matrice de règles, comparatif d'architectures, recommandation MVP au format
imposé du § 17 (commence par `RECOMMANDATION :`).

- Donner à l'agent : `references/cahier-recherche.md` en entier + le § 2 et le § 3 de ce fichier
  (ce qui existe, le cas réel) pour qu'il recommande **à partir de notre existant**.
- Travail en lecture seule côté serveur : aucune modification de code, aucun envoi.
- Résultat à ranger dans `references/recommandation.md` (+ `references/fiches-sources.md`), puis
  mettre à jour ce SKILL.md (§ 4 → règles V1 retenues, seuils, statuts).
- Implémentation ensuite, un sujet à la fois, captures avant / après (voir skill mass-email § 8).

## 6. Seuils de départ (hypothèses du cahier § 10, à calibrer sur nos données)

| Règle | Effet | Notre équivalent actuel |
|---|---:|---|
| R01 UA automatisé explicite (curl, python-requests…) | −80 | `user_agents_robots` |
| R02 HEAD / OPTIONS / TRACE | −50 | — (redirecteur à nous seulement) |
| R03 Signature de passerelle | −20 à −30 | — |
| R04 Clic < 10 s après livraison | −15 | `delai_min_s` (exclusion, à transformer en pondération) |
| R05-R07 Rafales 3 / 4 / 5 liens en 3 / 5 / 10 s | −25 / −40 / −60 | `rafale_liens` / `rafale_fenetre_s` |
| R08 Tous les liens dans la même fenêtre | −40 | (piège + rafale) |
| R09 Même IP sur 20 destinataires en 10 min | −50 | — |
| R10 ASN cloud / proxy / VPN | −10 | `ips_robots` (liste figée : à éviter seule) |
| R11 Pas de landing sous 10 min | −25 | — |
| R12-R16 Session, page active, navigation, formulaire, conversion | +20 à +60 | page de rappel (`rappels`) |

Classification : ≤ −60 `security_scan` · −59 à −25 `bot_suspected` · −24 à +14 `unknown` ·
+15 à +39 `human_likely` · ≥ +40 `human_confirmed`.

Requête simple du guide délivrabilité (§ 7), utile en première approche : ignorer les clics < 30 s
après la livraison et les rafales de ≥ 3 clics dans la même seconde.
