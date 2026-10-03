#!/usr/bin/env python3
"""imagen_generate.py — Génère des illustrations originales pour le blog via Google Imagen 3 (Vertex AI).

Utilise le compte de service `google-indexing-key.json` (déjà en place pour GA4/GSC).
Style imposé : photographie éditoriale moderne, sans aucun texte/logo dans l'image
(contrairement à popcorn/Higgsfield qui produisait des hiéroglyphes).

PRÉ-REQUIS (UNE seule action sur `lead-machine-mkd`, où le SA est déjà natif) :
1. Activer l'API Vertex AI :
   https://console.cloud.google.com/apis/api/aiplatform.googleapis.com/overview?project=lead-machine-mkd
   → Cliquer "Activer"
   → Attendre ~30 secondes
La facturation est déjà active (GA4 + Indexing API tournent sur ce projet).
Le SA `genesis-indexing@lead-machine-mkd.iam.gserviceaccount.com` est déjà Owner
ou Editor du projet, pas besoin de cross-project IAM.

Coût Imagen 3 : ~0,03 €/image (compute units Vertex AI).

Usage :
  python3 scripts/imagen_generate.py --topic "SMS marketing restaurants" --slug sms-restaurants
  python3 scripts/imagen_generate.py --prompt "<prompt complet>" --slug mon-slug --aspect 1:1
  python3 scripts/imagen_generate.py --topic "..." --slug ... --no-upload  # écrit en local sans pousser emdash
"""
from __future__ import annotations

import argparse
import base64
import json
import random
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent.parent
SA_FILE = BASE_DIR / "google-indexing-key.json"
ENV_FILE = BASE_DIR / ".env"
EMDASH_URL = "http://localhost:4321/_emdash/api"

# Région Vertex AI où Imagen 3 est dispo
REGION = "us-central1"
MODEL = "imagen-3.0-generate-002"
# Projet GCP — on cible le projet hôte du SA, qui a déjà la facturation active
TARGET_PROJECT = "lead-machine-mkd"

# Post-traitement images
TARGET_WIDTH = 800          # largeur cible (16:9 → 800×450 si ratio exact)
JPEG_QUALITY = 88           # bonne qualité visuelle, ~150-300 KB par image
LOGO_PATH = BASE_DIR / "assets" / "logo-lcr.png"
LOGO_WIDTH_RATIO = 0.20     # le logo fait 20% de la largeur de l'image
LOGO_PADDING = 14           # marge top + right en pixels
WHITE_THRESHOLD = 240       # pixels >= 240 sur RGB → transparents (chrome out du fond blanc)
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Casting déterministe pour éviter le biais "young Parisian" sytèmatique de DeepSeek.
# On tire ville + lieu + persona en Python AVANT l'appel LLM, qui devient juste un
# narrateur de la scène imposée. Paris reste possible mais à 1 chance sur 10.
FRENCH_CITIES = [
    "Marseille", "Bordeaux", "Lyon", "Lille", "Toulouse", "Nantes",
    "Strasbourg", "Montpellier", "Nice", "Rennes", "Rouen", "Reims",
    "Le Havre", "Saint-Étienne", "Dijon", "Angers", "Le Mans", "Tours",
    "Aix-en-Provence", "Avignon", "Annecy", "Nîmes", "Paris",
]

SCENE_TYPES = [
    "inside a small independent shop, behind the wooden counter, shelves and product displays in background",
    "in an artisan workshop (atelier d'artisanat) with tools and raw materials visible, leather/wood/metal",
    "at the entrance of a corner bakery, fresh breads on display, early morning light",
    "in a florist shop, surrounded by fresh bouquets, the owner arranging flowers",
    "in a butcher shop or fromagerie, products in glass refrigerated displays",
    "on a busy outdoor market street with stalls of fresh produce, vendors and customers",
    "walking on a cobblestone old-town street with stone or brick buildings, café terraces visible",
    "in a hair salon, modern interior, stylist working with a client",
    "in a bistro kitchen, the chef in white jacket preparing a plate",
    "at a wine bar, owner pouring a glass behind the counter, vintage bottles on shelves",
    "in a small auto-repair garage, mechanic in overalls checking work on a clipboard",
    "in a bookstore, owner organising books on a shelf, warm reading light",
    "in a tea-room or salon de thé, neat tables, owner welcoming a customer",
    "outside on the terrace of their own restaurant, owner-chef arranging menus on tables",
    "in a tobacco-newsagent (tabac-presse), owner behind the counter, magazines visible",
]

PERSONAS = [
    "a man in his fifties with greying hair, working hands, focused expression",
    "a woman in her forties, casual professional outfit, warm smile",
    "a young craftswoman in her late twenties, wearing an apron, hands at work",
    "a senior shopkeeper around 60, glasses, attentive posture",
    "a thirty-year-old male owner, t-shirt and apron, friendly expression",
    "a smiling woman in her thirties behind the counter",
    "a male artisan with a leather apron, beard, calm focused face",
    "a forty-something restaurateur, white chef coat, looking at her phone",
    "a middle-aged saleswoman, well-dressed, mid-conversation with a customer",
    "an experienced baker with flour on his apron, mid-fifties",
]

# STYLE_PREFIX = vraie photo documentaire iPhone/Portra 400. Cassé volontairement
# le rendu "éditorial clean" qui donnait des images type SaaS/illustration.
STYLE_PREFIX = (
    "A photorealistic candid documentary photograph. Shot on iPhone, RAW unprocessed. "
    "Kodak Portra 400 color palette, authentic film grain, natural skin texture with "
    "visible pores and lines, no retouching, no beauty filter. Documentary style that "
    "stops a thumb mid-scroll. Cinematic depth of field — subject sharp, background "
    "softly blurred. Natural daylight, strong side light, real shadows. French "
    "neighborhood authenticity. No commercial styling, no stock-photo smile."
)

# NEGATIVE_PROMPT : tue les rendus illustrés + supprime le texte parasite sur
# signes/ardoises/menus que Imagen a tendance à inventer.
NEGATIVE_PROMPT = (
    "illustration, drawing, painting, sketch, cartoon, anime, manga, 3d render, cgi, "
    "ai art, vector art, flat design, stylized art, octane render, unreal engine, "
    "smooth plastic skin, retouched, beauty filter, hdr, oversaturated, glossy, "
    "advertising mood, stock photo aesthetic, saas aesthetic, purple gradient, neon, "
    "perfect teeth, fake smile, model pose, "
    "readable text on signs, readable chalkboard menu text, readable wall text, "
    "words on walls, captions, watermark, logos with readable text, typography, "
    "low quality, blurry subject, distorted faces, deformed hands, extra fingers"
)


def load_env() -> dict:
    env = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def fresh_token() -> tuple[str, str]:
    """Retourne (access_token, target_project_id). Le SA vient de lead-machine-mkd
    mais on cible TARGET_PROJECT via cross-project IAM."""
    from google.oauth2 import service_account
    import google.auth.transport.requests as gtr

    creds = service_account.Credentials.from_service_account_file(
        str(SA_FILE),
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    creds.refresh(gtr.Request())
    return creds.token, TARGET_PROJECT


def topic_to_scene(topic: str, *, city: str | None = None, scene_type: str | None = None,
                   persona: str | None = None) -> str:
    """Traduit un sujet d'article en description visuelle. La ville, le lieu et
    le persona sont TIRÉS EN PYTHON pour éviter le biais 'young Parisian café'
    auquel DeepSeek revient systématiquement. Le LLM devient juste un narrateur
    de la scène imposée. Override possible via les paramètres."""
    # SystemRandom = vrai aléa (/dev/urandom), évite la collision d'init seed
    # quand le script est lancé en rafale par un cron.
    rng = random.SystemRandom()
    city = city or rng.choice(FRENCH_CITIES)
    scene_type = scene_type or rng.choice(SCENE_TYPES)
    persona = persona or rng.choice(PERSONAS)

    print(f"  [imagen] casting → city={city} · persona={persona[:50]}… · scene={scene_type[:60]}…")

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from llm_call import call_llm
    prompt = (
        f"Tu reçois un sujet d'article de blog en français : « {topic} ».\n\n"
        f"Tu vas écrire UNE description visuelle en ANGLAIS (2-3 phrases) d'une scène "
        f"photographique crédible qui illustre ce sujet de manière INDIRECTE.\n\n"
        f"CONTRAINTES IMPOSÉES (à respecter strictement) :\n"
        f"- Ville : {city} (à mentionner clairement dans la scène)\n"
        f"- Lieu/cadre : {scene_type}\n"
        f"- Personnage principal : {persona}\n"
        f"- Le personnage peut consulter ou montrer un téléphone (smartphone) si pertinent\n"
        f"- Lumière naturelle douce, ambiance authentique française régionale\n\n"
        f"INTERDIT :\n"
        f"- Ne mentionne JAMAIS le sujet textuellement\n"
        f"- Aucun texte / enseigne / affiche / écriture lisible dans la scène\n"
        f"- Pas de guillemets, pas de mots du sujet\n"
        f"- Ne dis pas 'Parisian' sauf si la ville est Paris\n\n"
        f"Format : juste la description, sans préambule."
    )
    try:
        scene = call_llm(prompt, max_tokens=220, temperature=0.7,
                         module="imagen", action="topic-to-scene").strip()
        return scene.strip('"\'')
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ topic_to_scene KO ({e}), fallback")
        return (f"In {city}, {persona} is at work {scene_type.split(',')[0]}, "
                f"warm afternoon light, photorealistic.")


def build_prompt(topic: str | None = None, scene: str | None = None) -> str:
    """Compose un prompt complet. `scene` override `topic`. Si `topic` seul,
    on le traduit en scène via DeepSeek."""
    if scene:
        body = scene
    elif topic:
        body = topic_to_scene(topic)
        print(f"  [imagen] scène traduite : {body[:200]}…")
    else:
        body = ("A natural realistic French business scene with people interacting, "
                "modern setting, warm light")
    return f"{STYLE_PREFIX} {body}"


def generate(prompt: str, aspect: str = "16:9", n: int = 1) -> list[bytes]:
    """Appelle Imagen 3 et retourne les bytes PNG de chaque image."""
    token, project = fresh_token()
    url = (f"https://{REGION}-aiplatform.googleapis.com/v1/projects/{project}/"
           f"locations/{REGION}/publishers/google/models/{MODEL}:predict")
    body = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": max(1, min(n, 4)),
            "aspectRatio": aspect,
            "safetyFilterLevel": "block_only_high",
            "personGeneration": "allow_adult",
            "addWatermark": False,
            "negativePrompt": NEGATIVE_PROMPT,
        },
    }
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body, timeout=90,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Vertex AI HTTP {r.status_code}: {r.text[:400]}")
    preds = r.json().get("predictions", [])
    if not preds:
        raise RuntimeError(f"Aucune prédiction renvoyée. Réponse : {r.text[:300]}")
    return [base64.b64decode(p["bytesBase64Encoded"]) for p in preds]


def _logo_with_transparency() -> Image.Image | None:
    """Charge le logo et transforme le fond blanc en transparent (chroma key blanc)."""
    if not LOGO_PATH.exists():
        return None
    logo = Image.open(LOGO_PATH).convert("RGBA")
    pixels = logo.load()
    w, h = logo.size
    for x in range(w):
        for y in range(h):
            r, g, b, a = pixels[x, y]
            if r >= WHITE_THRESHOLD and g >= WHITE_THRESHOLD and b >= WHITE_THRESHOLD:
                pixels[x, y] = (255, 255, 255, 0)
    return logo


def _draw_overlay_text(img: Image.Image, text: str) -> None:
    """Dessine 5 mots max en bas à gauche, blanc + ombre noire pour lisibilité partout."""
    words = text.split()[:5]
    label = " ".join(words).upper()
    if not label:
        return
    draw = ImageDraw.Draw(img)
    w, h = img.size
    # Taille de police ≈ 6% de la hauteur, ajustée pour ne pas dépasser 90% de la largeur
    size = max(18, int(h * 0.065))
    try:
        font = ImageFont.truetype(FONT_PATH, size=size)
    except Exception:  # noqa: BLE001
        font = ImageFont.load_default()
    # Mesure pour positionner sur la diag bas-gauche avec marge
    bbox = draw.textbbox((0, 0), label, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = 24
    y = h - th - 30
    # Ombre noire (4 directions) pour lisibilité sur tout fond
    for dx, dy in [(-2, -2), (-2, 2), (2, -2), (2, 2), (0, 2), (2, 0)]:
        draw.text((x + dx, y + dy), label, font=font, fill=(0, 0, 0, 255))
    draw.text((x, y), label, font=font, fill=(255, 255, 255, 255))


def postprocess(content: bytes, *, overlay_text: str | None = None,
                with_logo: bool = True) -> bytes:
    """Resize 800px → JPEG quality 88 + logo top-right + texte optionnel bas-gauche.
    Retourne les bytes JPEG (toujours < 1 MB pour une image éditoriale)."""
    img = Image.open(BytesIO(content)).convert("RGB")
    # Resize en gardant le ratio
    w, h = img.size
    if w != TARGET_WIDTH:
        new_h = int(h * TARGET_WIDTH / w)
        img = img.resize((TARGET_WIDTH, new_h), Image.LANCZOS)
        w, h = TARGET_WIDTH, new_h

    # Logo top-right
    if with_logo:
        logo = _logo_with_transparency()
        if logo is not None:
            lw = int(w * LOGO_WIDTH_RATIO)
            lh = int(logo.height * lw / logo.width)
            logo = logo.resize((lw, lh), Image.LANCZOS)
            # paste avec mask alpha
            img_rgba = img.convert("RGBA")
            img_rgba.alpha_composite(logo, (w - lw - LOGO_PADDING, LOGO_PADDING))
            img = img_rgba.convert("RGB")

    # Texte overlay 5 mots max, bas-gauche
    if overlay_text:
        _draw_overlay_text(img, overlay_text)

    out = BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return out.getvalue()


def upload_emdash(content: bytes, filename: str, env: dict) -> str | None:
    """Upload une image dans emdash et retourne l'URL publique. None si KO."""
    tok = env.get("EMDASH_API_TOKEN")
    if not tok:
        print("  ⚠ EMDASH_API_TOKEN absent du .env, skip upload")
        return None
    r = requests.post(
        f"{EMDASH_URL}/media",
        headers={"Authorization": f"Bearer {tok}", "Origin": "http://localhost:4321"},
        files={"file": (filename, content, "image/png")},
        timeout=60,
    )
    if r.status_code not in (200, 201):
        print(f"  ⚠ Upload emdash HTTP {r.status_code}: {r.text[:200]}")
        return None
    item = r.json().get("data", {}).get("item", {})
    # Construction de l'URL publique : emdash retourne storageKey, on assemble vers le CDN
    rel = item.get("url") or item.get("publicUrl") or ""
    if rel:
        return ("https://blog.leclientroi.com" + rel) if rel.startswith("/") else rel
    storage_key = item.get("storageKey")
    if storage_key:
        return f"https://blog.leclientroi.com/_emdash/media/{storage_key}"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", help="Prompt complet (override --topic)")
    ap.add_argument("--topic", help="Sujet d'article (prompt généré automatiquement)")
    ap.add_argument("--slug", required=True, help="Slug pour nommer le fichier")
    ap.add_argument("--aspect", default="16:9",
                    choices=["16:9", "1:1", "4:3", "9:16", "3:4"],
                    help="Ratio (16:9 par défaut pour featured image, 1:1 pour LinkedIn)")
    ap.add_argument("--n", type=int, default=1, help="Nombre d'images à générer (1-4)")
    ap.add_argument("--out-dir", default=str(BASE_DIR / "data" / "generated_images"))
    ap.add_argument("--no-upload", action="store_true",
                    help="Skip upload emdash, écrit en local seulement")
    ap.add_argument("--overlay-text", default=None,
                    help="Texte à incruster en bas-gauche (max 5 mots, UPPERCASE auto)")
    ap.add_argument("--no-logo", action="store_true",
                    help="Désactive l'overlay du logo LCR en haut à droite")
    ap.add_argument("--raw", action="store_true",
                    help="Sortie PNG brut Imagen, sans resize ni overlay (debug)")
    args = ap.parse_args()

    if not (args.prompt or args.topic):
        ap.error("--prompt ou --topic requis")

    prompt = args.prompt if args.prompt else build_prompt(args.topic)
    print(f"[imagen] aspect={args.aspect} n={args.n}")
    print(f"[imagen] prompt: {prompt[:200]}{'…' if len(prompt) > 200 else ''}")

    images = generate(prompt, aspect=args.aspect, n=args.n)
    print(f"[imagen] {len(images)} image(s) générée(s)")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    env = load_env() if not args.no_upload else {}

    results = []
    for i, img in enumerate(images):
        suffix = "png" if args.raw else "jpg"
        fname = (f"{args.slug}-{i+1}.{suffix}" if args.n > 1
                 else f"{args.slug}.{suffix}")
        if args.raw:
            final_bytes = img
        else:
            final_bytes = postprocess(img, overlay_text=args.overlay_text,
                                      with_logo=not args.no_logo)
        local = out_dir / fname
        local.write_bytes(final_bytes)
        print(f"  ✓ local: {local} ({len(final_bytes)//1024} KB)")
        url = None
        if not args.no_upload:
            try:
                url = upload_emdash(final_bytes, fname, env)
                if url:
                    print(f"  ✓ emdash: {url}")
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠ upload emdash KO: {e}")
        results.append({"local": str(local), "emdash_url": url})

    print(json.dumps({"images": results,
                      "generated_at": datetime.now(timezone.utc).isoformat()},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
