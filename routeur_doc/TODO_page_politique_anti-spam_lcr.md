# TODO URGENT — Publier la page « Politique anti-spam » sur leclientroi.com

**Contexte** (2026-07-08) : le domaine d'envoi cold email `leclient-roi.com` (Maildoso, canal
maildoso de Cheffer) était listé sur SURBL ABUSE. Une demande de délisting a été soumise et
**acceptée en traitement** par SURBL le 2026-07-08. Le formulaire cite une politique anti-spam
publiée à l'URL ci-dessous : **les reviewers SURBL vont vérifier ce lien sous 24-72 h, la page
doit exister au plus vite**. Dossier complet : `routeur_doc/surbl_delisting_leclient-roi.md`.

## À faire

1. Créer une page publique sur **leclientroi.com** (CMS emdash — pipeline LCR habituel,
   `EMDASH_API_TOKEN` / `EMDASH_API_URL` dans `.env`, cf. `publish_agent.py` / `modules_backend.py`) :
   - **URL cible : `https://leclientroi.com/politique-anti-spam`** (c'est l'URL déclarée à SURBL).
     Si le CMS impose un préfixe (ex. `/blog/politique-anti-spam`), publier là où c'est possible
     et LE SIGNALER en fin de session pour qu'on mette à jour SURBL si besoin.
   - **Titre** : « Politique anti-spam / Anti-Spam Policy »
   - **Contenu** : le texte bilingue EXACT ci-dessous, sans le modifier (il correspond mot pour
     mot à ce qui a été déclaré à SURBL). Mise en forme libre (deux sections FR/EN).
   - Page **publique, indexable, accessible sans login**, pérenne (ne jamais la dépublier).
2. Vérifier après publication : `curl -s -o /dev/null -w "%{http_code}" https://leclientroi.com/politique-anti-spam` → 200 (et contenu visible sans JS de préférence).
3. Bonus si facile : ajouter un lien vers la page dans le footer du site.
4. Consigner l'URL finale dans `STATE.md` et dans `routeur_doc/surbl_delisting_leclient-roi.md`.

## Contenu exact de la page

**Politique anti-spam / Anti-Spam Policy — Le Client ROI**

FR — Le Client ROI s'engage à ne jamais promouvoir ses sites web (leclientroi.com,
leclient-roi.com) par des messages non sollicités envoyés en masse. Nos communications par
email se limitent à : (1) des emails transactionnels et de service ; (2) des newsletters
envoyées uniquement aux personnes inscrites ; (3) une correspondance professionnelle
individualisée adressée à des contacts B2B dans le respect du cadre légal français et
européen (art. L.34-5 CPCE, lignes directrices CNIL) : pertinence professionnelle du message,
identification claire de l'expéditeur, et moyen simple et gratuit de s'opposer à toute
nouvelle sollicitation. Toute demande de désinscription est honorée immédiatement et
définitivement (liste de suppression). Nous n'autorisons aucun affilié ni tiers à promouvoir
nos sites par email. Pour signaler un abus : contact@leclientroi.com.

EN — Le Client ROI never advertises its websites (leclientroi.com, leclient-roi.com) through
unsolicited bulk messages. Our email communications are limited to: (1) transactional and
service emails; (2) newsletters sent only to opted-in subscribers; (3) individualized
professional correspondence addressed to B2B contacts in compliance with the French and EU
legal framework (art. L.34-5 CPCE, CNIL guidelines): professional relevance, clear sender
identification, and a simple free opt-out honored immediately and permanently (suppression
list). No affiliate or third party is authorized to advertise our websites by email.
To report abuse: contact@leclientroi.com.
