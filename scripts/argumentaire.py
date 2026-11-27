#!/usr/bin/env python3
"""argumentaire.py — Ce qu'on dit au téléphone, et ce qu'on envoie après.

Un commercial qui décroche sans script improvise ; il improvise mal les vingt premières
secondes, et c'est là que tout se joue. Ce module porte, par secteur : l'accroche, la
question qui fait parler, les trois objections qui reviennent toujours avec leur parade,
et la sortie — plus l'email de présentation et sa plaquette PDF, envoyés en un clic après
l'appel.

**Pourquoi par secteur.** « Réactivez votre base clients » ne veut rien dire pour un
agent immobilier : lui, il a des mandats qui dorment et des acquéreurs qui ne rappellent
pas. Le produit est le même, le problème qu'il résout se dit dans les mots du métier.
Un argumentaire générique s'entend comme un argumentaire générique.

**L'ordre des objections n'est pas décoratif** : elles sont rangées par fréquence réelle
d'apparition au téléphone, la plus courante en premier. Un commercial qui panique cherche
dans l'ordre.

Immobilier est complet. Les autres secteurs héritent d'un socle générique honnête — mieux
vaut un texte visiblement générique qu'un faux texte de métier qui sonne creux dès la
deuxième phrase.
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

PRODUIT = {
    "promesse": "des campagnes SMS et email géolocalisées, prêtes à envoyer",
}


def marque(site: str = "lcr") -> dict:
    """L'identité SOUS LAQUELLE on écrit : celle du compte, pas celle de la plateforme.

    Le prospect n'a jamais entendu parler de Cheffer — Cheffer est l'outil interne. Il
    connaît (ou découvre) LeClientROI, la marque qui l'appelle et qui lui vend. Signer
    « Cheffer » revenait à donner le nom du CRM au lieu du nom de l'entreprise : au mieux
    incompréhensible, au pire suspect.
    """
    try:
        from sites_config import load_all_sites
        core = (load_all_sites().get(site) or {}).get("core") or {}
    except Exception:  # noqa: BLE001
        core = {}
    return {
        "nom": core.get("label") or "LeClientROI",
        "domaine": core.get("domain") or "leclientroi.com",
        "url": core.get("url") or f"https://{core.get('domain') or 'leclientroi.com'}",
    }

GENERIQUE = {
    "accroche": (
        "Bonjour {prenom}, {expediteur} de Cheffer. Je vous appelle parce que vous avez "
        "ouvert notre email de la semaine dernière — je ne vous prends que deux minutes."
    ),
    "question": (
        "Aujourd'hui, quand vous voulez faire revenir un client qui n'est pas passé depuis "
        "six mois, vous faites comment ?"
    ),
    "valeur": [
        "On récupère votre base clients, on la nettoie, et on envoie à votre place.",
        "Vous validez le message, nous gérons l'envoi et le suivi.",
        "Vous voyez qui a ouvert, qui a cliqué, qui a répondu.",
    ],
    "sortie": (
        "Je vous propose quinze minutes en visio pour vous montrer sur votre propre base. "
        "Vous préférez plutôt en début ou en fin de semaine ?"
    ),
    "objections": [
        {"objection": "Je n'ai pas le temps",
         "parade": "C'est exactement le sujet : vous n'avez rien à faire. On prépare, vous "
                   "relisez en deux minutes, on envoie. Le temps que ça vous prend, c'est "
                   "celui de cet appel.",
         "pourquoi": "L'objection du temps n'est presque jamais une question d'agenda : "
                     "c'est « je ne vois pas ce que ça me rapporte ». On répond sur "
                     "l'effort, pas sur le calendrier."},
        {"objection": "On le fait déjà en interne",
         "parade": "Très bien — et vous envoyez à quelle fréquence ? La plupart de ceux qui "
                   "me disent ça envoient deux fois par an, faute de temps. Nous, c'est "
                   "tous les mois, sans que vous y pensiez.",
         "pourquoi": "Ne jamais contredire. On demande la fréquence : le chiffre fait le "
                     "travail à notre place."},
        {"objection": "C'est trop cher",
         "parade": "Sur quel budget vous comparez ? Un seul client qui revient couvre le "
                   "mois. Et on commence sans engagement, vous arrêtez quand vous voulez.",
         "pourquoi": "« Trop cher » sans référence n'est pas un prix, c'est un doute. "
                     "On fait donner la référence avant de défendre le prix."},
    ],
}

SECTEURS = {
    "immobilier": {
        "label": "Immobilier",
        # À qui la plaquette s'adresse, dit comme on le dirait à l'oral. « Pour immobilier »
        # sur une couverture, ça se voit que c'est une variable.
        "cible": "les agences immobilières",
        "contexte": (
            "Une agence a deux problèmes qu'elle ne dit jamais spontanément : des mandats "
            "qui expirent sans nouvelle du vendeur, et un fichier d'acquéreurs qu'on "
            "n'appelle plus. La fin du démarchage téléphonique (loi Naegelen, encadrement "
            "de la prospection) rend ce fichier encore plus précieux : c'est ce qu'il reste."
        ),
        "accroche": (
            "Bonjour {prenom}, {expediteur} de Cheffer. Vous avez ouvert notre email sur la "
            "fin du démarchage téléphonique — je vous appelle deux minutes à ce sujet, "
            "parce que ça change concrètement votre prospection."
        ),
        "question": (
            "Vos mandats qui arrivent à échéance, et vos acquéreurs inscrits depuis plus de "
            "six mois : aujourd'hui, qui les relance, et à quelle fréquence ?"
        ),
        "valeur": [
            "Vos acquéreurs reçoivent les nouveaux biens de leur secteur, par SMS, le jour "
            "de la mise en ligne.",
            "Vos vendeurs sous mandat reçoivent un point d'étape automatique — c'est ce qui "
            "évite le mandat qui part à la concurrence.",
            "Vos anciens contacts sont réveillés par une estimation offerte, géolocalisée "
            "à la rue près.",
            "Vous voyez qui a ouvert et qui a cliqué : vous rappelez les tièdes, pas les "
            "froids.",
        ],
        "sortie": (
            "Je vous propose quinze minutes en visio pour vous le montrer sur vos propres "
            "mandats. Plutôt en début ou en fin de semaine ?"
        ),
        "objections": [
            {"objection": "J'ai déjà un logiciel immobilier qui fait ça",
             "parade": "Votre logiciel gère vos biens, il ne fait pas de la prospection. "
                       "Posez-vous la question : la dernière campagne partie de votre "
                       "logiciel, c'était quand ? Nous, on branche Cheffer dessus, on ne "
                       "le remplace pas.",
             "pourquoi": "Ne jamais attaquer l'outil en place — l'agent l'a choisi. On "
                         "déplace le sujet de « gérer » à « prospecter », et on se pose en "
                         "complément, pas en concurrent."},
            {"objection": "Mes clients n'aiment pas être sollicités",
             "parade": "C'est vrai quand c'est un message de masse. Là, on envoie à un "
                       "acquéreur qui cherche un T3 à Tours un T3 à Tours qui vient de "
                       "sortir. Ce n'est pas de la sollicitation, c'est le service qu'il "
                       "attend de vous.",
             "pourquoi": "L'objection porte sur la PERTINENCE, pas sur le canal. On répond "
                         "par un exemple concret et géolocalisé, jamais par un argument "
                         "général sur le SMS."},
            {"objection": "Le RGPD ne me permet pas d'envoyer à ma base",
             "parade": "Si vos clients sont vos clients, la relation contractuelle vous "
                       "autorise à les informer sur des biens équivalents. On nettoie la "
                       "base, on gère les désinscriptions, et chaque message porte le lien "
                       "de retrait. Vous êtes plus en règle qu'avec un fichier Excel.",
             "pourquoi": "Objection sincère et fréquente : elle exige une réponse précise "
                         "et calme. Le retournement final — « plus en règle qu'avec votre "
                         "Excel » — transforme le frein en argument."},
        ],
        "email": {
            "sujet": "Suite à notre échange — {societe}",
            "corps": (
                "Bonjour {prenom},\n\n"
                "Merci pour votre temps au téléphone. Comme convenu, voici en deux lignes "
                "ce que {marque} fait pour une agence comme {societe} :\n\n"
                "• Vos acquéreurs reçoivent les nouveaux biens de leur secteur, par SMS, "
                "le jour de la mise en ligne.\n"
                "• Vos vendeurs sous mandat reçoivent un point d'étape automatique.\n"
                "• Vos anciens contacts sont réveillés par une estimation offerte, "
                "géolocalisée.\n\n"
                "Vous trouverez la présentation complète en pièce jointe "
                "({lien_plaquette}).\n\n"
                "Je reste à votre disposition,\n"
                "{expediteur}\n"
                "{marque} — {url}"
            ),
        },
    },
}


def secteurs_couverts() -> list[str]:
    return sorted(SECTEURS)


def script(secteur: str | None = None) -> dict:
    """Le script d'appel pour ce secteur, avec repli générique explicite."""
    code = (secteur or "").strip().lower()
    fiche = SECTEURS.get(code)
    base = dict(GENERIQUE)
    if fiche:
        base = {**base, **{k: v for k, v in fiche.items() if k not in ("email", "label")}}
    return {
        "secteur": code or "inconnu",
        "label": (fiche or {}).get("label") or (code.capitalize() if code else "Générique"),
        "sur_mesure": bool(fiche),
        "contexte": (fiche or {}).get("contexte"),
        "accroche": base["accroche"],
        "question": base["question"],
        "valeur": base["valeur"],
        "objections": base["objections"],
        "sortie": base["sortie"],
        "produit": PRODUIT,
    }


def _remplir(texte: str, contact: dict, expediteur: str, m: dict,
             lien_plaquette: str = "") -> str:
    return (texte or "").format(
        prenom=(contact.get("prenom") or "").strip() or "bonjour",
        societe=(contact.get("societe") or "votre agence").strip(),
        expediteur=expediteur or f"l'équipe {m['nom']}",
        marque=m["nom"], url=m["url"],
        lien_plaquette=lien_plaquette or "en pièce jointe",
    ).replace("Bonjour bonjour,", "Bonjour,")


def email_presentation(secteur: str, contact: dict, expediteur: str = "",
                       site: str = "lcr", lien_plaquette: str = "") -> dict:
    """Sujet, corps texte ET corps HTML de l'email de présentation.

    Les deux versions disent la même chose : le texte pour les clients qui ne rendent pas
    l'HTML (et pour la délivrabilité — un email sans partie texte se fait remarquer), l'HTML
    pour les liens cliquables vers le site et vers la plaquette.
    """
    m = marque(site)
    fiche = SECTEURS.get((secteur or "").strip().lower())
    modele = (fiche or {}).get("email") or {
        "sujet": "Suite à notre échange",
        "corps": ("Bonjour {prenom},\n\nMerci pour votre temps au téléphone. Vous "
                  "trouverez notre présentation en pièce jointe ({lien_plaquette}).\n\n"
                  "Je reste à votre disposition,\n{expediteur}\n{marque} — {url}"),
    }
    sujet = _remplir(modele["sujet"], contact, expediteur, m)
    corps = _remplir(modele["corps"], contact, expediteur, m, lien_plaquette)
    return {"sujet": sujet, "corps": corps,
            "html": _html(corps, m, lien_plaquette),
            "marque": m, "sur_mesure": bool(fiche)}


def _html(texte: str, m: dict, lien_plaquette: str = "") -> str:
    """Le même message, avec les liens vivants. Volontairement sobre : un cold email chargé
    en images et en styles part en onglet Promotions.

    Les remplacements passent par des JETONS avant d'être transformés en balises. En
    remplaçant directement, le second remplacement retombait dans le `href` produit par le
    premier — la marque devenait `<a href="<a href="…">` et le lien cassait. Un jeton ne
    contient ni URL ni nom de marque : il ne peut pas être réécrit par le tour suivant.
    """
    import html as _h

    JETON_MARQUE, JETON_URL, JETON_PJ = "\x00M\x00", "\x00U\x00", "\x00P\x00"
    brut = texte
    if lien_plaquette:
        brut = brut.replace(lien_plaquette, JETON_PJ)
    brut = brut.replace(m["url"], JETON_URL).replace(m["nom"], JETON_MARQUE)

    def lien(url: str, libelle: str) -> str:
        return (f'<a href="{_h.escape(url, quote=True)}" target="_blank" rel="noopener" '
                f'style="color:#0066FF;text-decoration:underline">{_h.escape(libelle)}</a>')

    lignes = []
    for para in brut.split("\n"):
        p = _h.escape(para)
        p = p.replace(JETON_MARQUE, lien(m["url"], m["nom"]))
        p = p.replace(JETON_URL, lien(m["url"], m["domaine"]))
        if lien_plaquette:
            p = p.replace(JETON_PJ, lien(lien_plaquette, "la télécharger ici"))
        lignes.append(p if p.strip() else "&nbsp;")
    corps = "<br>".join(lignes)
    return ('<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
            'font-size:15px;line-height:1.55;color:#18181b">' + corps + "</div>")
