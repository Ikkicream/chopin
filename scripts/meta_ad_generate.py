#!/usr/bin/env python3
"""meta_ad_generate.py — Génère un copy Meta ad LeClientROI (JSON 6 clés) + l'image
photographique candide associée via Imagen 3.

Pipeline :
1. DeepSeek (avec le system prompt copywriter senior) génère le JSON copy à partir
   des paramètres (secteur, style, angle, douleur, promesse)
2. On extrait `image_brief` du JSON
3. Imagen 3 génère l'image (aspect 1:1 par défaut, style photo doc iPhone/Portra)
4. Upload emdash → retourne le JSON enrichi avec `image_url`

Usage :
  python3 scripts/meta_ad_generate.py \\
    --secteur restauration \\
    --style "Vérité qui pique" \\
    --angle "Douleur concrète et datée" \\
    --douleur "besoin urgent de mardi 12 novembre : formule entrée + plat du jour + verre de vin à l'ardoise" \\
    --promesse "Mardi 12 novembre : formule entrée + plat du jour + verre de vin à l'ardoise"

  # ou avec randomisation des paramètres (pour test rapide) :
  python3 scripts/meta_ad_generate.py --secteur restauration --random-rest
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "data" / "meta_ads"

# Styles d'accroche disponibles (à passer en CLI ou random)
STYLE_OPTIONS = [
    "Vérité qui pique",
    "Question rentre-dedans",
    "Chiffre choc",
    "Détail visuel évocateur",
    "Ironie tendre",
]

# Angles narratifs
ANGLE_OPTIONS = [
    "Douleur concrète et datée",
    "Bénéfice contre-intuitif",
    "Comparaison voisinage",
    "Récit du gérant qui change",
]


# System prompt fourni par Camille (copywriter senior LeClientROI Meta ads)
SYSTEM_PROMPT = """Tu es copywriter senior pour LeClientROI (service français : SMS + email géolocalisé pour commerçants 45-65 ans).

⚠️ CIBLE DE L'AD = LE PATRON DU COMMERCE (Un restaurateur français de 55-65 ans, gérant indépendant d'une pizzeria ou d'un bistrot de quartier, salle vide en semaine, sous pression des plateformes de livraison). PAS son client final.
L'accroche parle de SA douleur de GÉRANT : sa boutique/salle vide, son manque de passage, ses clients qui l'oublient.
✗ FAUX (parle au client) : "Mardi 7h, vous cherchez un bouquet frais ?"
✓ JUSTE (parle au gérant) : "Boutique vide ce mardi matin ?"
Le "vous" de l'accroche = TOUJOURS le patron, jamais l'acheteur.

🔒 ANCRAGE MÉTIER OBLIGATOIRE — secteur : {secteur}.
L'accroche, la solution, le primary_text ET le image_brief DOIVENT parler de la réalité CONCRÈTE de CE métier, jamais d'une copy passe-partout qui marcherait pour n'importe quel commerce.

OFFRE : on prévient par SMS les voisins du quartier (3 000 à 6 000 dans un rayon de 5 km) qui ont accepté de recevoir des offres · l'IA rédige, vous validez, une équipe humaine accompagne · +35% de passage en moyenne · 500+ commerces clients · 18 millions de Français inscrits dans toute la France · démo 15 min sans CB.
TON : Concret, vocabulaire du comptoir. INTERDIT : plateforme, solution, logiciel, outil, SaaS, leads, ROI, funnel, scaler, digitaliser, transformer, IA (en accroche), campagne, spam, booster, opt-in, base de données, contacts qualifiés. Pas d'anglicisme ni de jargon que ta mère ne comprendrait pas.

🔢 DISCIPLINE DES CHIFFRES — un commerce local touche un QUARTIER, pas la France entière. Ne mélange JAMAIS les deux échelles :
• ÉCHELLE LOCALE (le chiffre qu'on "prévient" pour CE commerce) = entre 3 000 et 6 000 voisins dans un rayon de ~5 km. Utilise ~4 700 voisins ici. C'est CE chiffre qui reçoit le SMS.
• ÉCHELLE NATIONALE = 18 millions de Français inscrits dans toute la France. C'est une preuve de SÉRIEUX de la marque ("le plus grand réseau de France"), JAMAIS le nombre de gens qu'on prévient pour une boutique. ✗ INTERDIT : "on prévient 18M de voisins", "18M de voisins du quartier", "vos 18 millions de clients".
• +35% = hausse moyenne de passage. · 97% = taux de lecture des SMS en 3 min. · 500+ = commerces déjà clients.
• N'INVENTE aucun autre chiffre (pas de "+200%", pas de "10 000 ventes", pas de prix bidon). Reste sur ces chiffres-là.

MÉTHODE (tu es consultant senior, pas un robot à remplir des cases) : 1) HOOK la douleur réelle de CE métier, 2) MONTRE que tu la comprends, 3) APPORTE le mécanisme (SMS aux voisins du quartier), 4) PROUVE avec un chiffre crédible, 5) fais agir. Chaque mot doit donner envie de réserver la démo.

Réponds avec UN SEUL objet JSON, rien d'autre. Pas de ```, pas de texte avant/après, pas de variantes multiples. Premier caractère = {{, dernier = }}. Exactement ces 6 clés :

{{"accroche":"4-10 mots, BRILLANTE selon le style imposé, ANCRÉE dans le métier (un mot/objet du métier), peut contenir un chiffre si le style le demande, sans marque","solution":"UNE phrase 6-12 mots, l'uppercut : ce que LeClientROI fait POUR CE MÉTIER, avec un chiffre LOCAL crédible (3 000 à 6 000 voisins, +35%, 97%) ou un mécanisme","primary_text":"2-3 phrases max 220 caractères pour Meta, qui nomment le métier et son produit","headline":"3-6 mots, bénéfice, sans point final","description":"10-16 mots avec LeClientROI ou un chiffre","cta":"un parmi: Réserver, En savoir plus, S'inscrire, Découvrir, Demander une démo, Obtenir un audit","image_brief":"1 phrase EN ANGLAIS décrivant la photo idéale pour CETTE ad : le patron de CE métier précis dans son lieu de travail, avec les éléments visibles du métier, en lien avec la douleur/solution. Candid, documentaire."}}

🎯 L'ACCROCHE EST L'ARME N°1 — elle doit STOPPER LE POUCE en 0,5 seconde. Tu es un copywriter de génie (niveau meilleure agence de Paris), pas un robot qui remplit des cases.
STYLE IMPOSÉ pour cette ad : « {style} ». Frontal mais respectueux — on réveille, on n'insulte pas.

RÈGLES D'UNE ACCROCHE QUI TUE (best practices 2026) :
• SPÉCIFIQUE et concrète : un chiffre, un jour, une heure, un objet du métier. Le flou tue ; le détail vend.
• UNE seule émotion forte : surprise, peur de rater, indignation, ou sourire — choisis-en une et frappe fort.
• Sois MALIN, DRÔLE ou CHOQUANT si ça sert le message. OSE. Mais reste VRAI et respecte le gérant : on le RÉVEILLE, on ne l'humilie jamais.
• Parle au GÉRANT (sa douleur/fierté de patron), JAMAIS à son client final.
• 4 à 10 mots, lisible en une fraction de seconde. Zéro superlatif corporate, zéro point d'exclamation criard.
ACCROCHES MORTES INTERDITES (bannies) : "Boostez votre visibilité", "Développez votre clientèle", "La solution pour…", "Et si on parlait de…", "Augmentez votre chiffre d'affaires" — tout ce qui pourrait servir à n'importe quel commerce.

La SOLUTION enchaîne comme un uppercut : le mécanisme CONCRET de LeClientROI + le déclic ("ah, c'est donc ça"). Surtout pas une redite molle de l'accroche.

VARIE à chaque génération : ne réutilise pas toujours "97%" ni "vous validez". Alterne les chiffres LOCAUX (3 000 à 6 000 voisins du quartier, +35% de passage, 97% de lecture, 500 commerces clients) et les tournures de l'accroche. 18M reste réservé à l'échelle nationale. Surprends — mais reste ANCRÉ dans le métier.

Paramètres : secteur={secteur}, angle={angle}, douleur={douleur}, promesse={promesse}.

Produis ton JSON maintenant."""


def generate_copy(secteur: str, style: str, angle: str, douleur: str, promesse: str) -> dict:
    """Appelle DeepSeek avec le system prompt copywriter et retourne le JSON 7 clés."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from llm_call import call_llm_json

    system = SYSTEM_PROMPT.format(secteur=secteur, style=style, angle=angle,
                                  douleur=douleur, promesse=promesse)
    user_prompt = (
        f"Tu as les paramètres en system. Produis maintenant ton JSON pour : "
        f"secteur={secteur}, style={style}, angle={angle}, "
        f"douleur=« {douleur} », promesse=« {promesse} »."
    )
    out = call_llm_json(user_prompt, system=system, max_tokens=900, temperature=0.85,
                       module="meta-ad", action=f"copy-{secteur[:30]}", site="lcr")
    return out


def generate_image(image_brief: str, slug: str, aspect: str = "1:1") -> tuple[bytes, str | None]:
    """Génère l'image Imagen à partir du brief copy + upload emdash. Retourne (bytes, url)."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    if "imagen_generate" in sys.modules:
        del sys.modules["imagen_generate"]
    from imagen_generate import STYLE_PREFIX, generate as imagen_gen, postprocess, upload_emdash, load_env
    # On préfixe le brief par notre STYLE_PREFIX (iPhone/Portra/film grain)
    full_prompt = f"{STYLE_PREFIX} {image_brief}"
    raw = imagen_gen(full_prompt, aspect=aspect, n=1)[0]
    # Pas de logo ni overlay : Camille les fait elle-même dans Meta
    jpeg = postprocess(raw, overlay_text=None, with_logo=False)
    env = load_env()
    url = upload_emdash(jpeg, f"{slug}.jpg", env)
    return jpeg, url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secteur", required=True,
                    help="Métier ciblé (restauration, fleuriste, opticien, boulanger…)")
    ap.add_argument("--style", default="Vérité qui pique",
                    help="Style d'accroche (Vérité qui pique, Chiffre choc…)")
    ap.add_argument("--angle", default="Douleur concrète et datée")
    ap.add_argument("--douleur", required=True,
                    help="Description précise de la douleur du gérant")
    ap.add_argument("--promesse", required=True,
                    help="Promesse concrète à activer (date, offre, événement)")
    ap.add_argument("--aspect", default="1:1", choices=["1:1", "16:9", "4:3"])
    ap.add_argument("--slug", default=None,
                    help="Slug pour fichier (auto si absent)")
    ap.add_argument("--random-rest", action="store_true",
                    help="Randomise style/angle parmi les options pré-définies")
    args = ap.parse_args()

    if args.random_rest:
        rng = random.SystemRandom()
        args.style = rng.choice(STYLE_OPTIONS)
        args.angle = rng.choice(ANGLE_OPTIONS)
        print(f"[meta-ad] casting → style={args.style!r} angle={args.angle!r}")

    if not args.slug:
        args.slug = f"meta-ad-{args.secteur}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    print(f"[meta-ad] secteur={args.secteur} style={args.style!r}")
    print(f"[meta-ad] 1/2 génération du copy via DeepSeek…")
    copy = generate_copy(args.secteur, args.style, args.angle, args.douleur, args.promesse)

    print(f"\n=== COPY GÉNÉRÉ ===")
    for k, v in copy.items():
        print(f"  {k}: {v}")

    print(f"\n[meta-ad] 2/2 génération image via Imagen 3 ({args.aspect})…")
    print(f"  brief: {copy.get('image_brief', '(absent)')[:200]}")
    jpeg, image_url = generate_image(copy["image_brief"], args.slug, aspect=args.aspect)

    # Sauvegarde locale
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img_path = OUT_DIR / f"{args.slug}.jpg"
    img_path.write_bytes(jpeg)
    json_path = OUT_DIR / f"{args.slug}.json"
    result = {**copy, "image_local": str(img_path), "image_url": image_url,
              "params": {"secteur": args.secteur, "style": args.style, "angle": args.angle,
                         "douleur": args.douleur, "promesse": args.promesse,
                         "aspect": args.aspect},
              "generated_at": datetime.now(timezone.utc).isoformat()}
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n  ✓ image: {img_path} ({len(jpeg)//1024} KB)")
    if image_url:
        print(f"  ✓ url:   {image_url}")
    print(f"  ✓ json:  {json_path}")


if __name__ == "__main__":
    main()
