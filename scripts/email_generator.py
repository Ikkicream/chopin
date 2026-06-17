#!/usr/bin/env python3
"""
email_generator.py — Génère les séquences cold email par secteur pour LCR (move upmarket).

Principe (Option A, décidée 2026-05-25) :
- Part des angles + brouillons VALIDÉS dans context/lcr/sector-angles.md.
- DeepSeek (via llm_call) finalise en HTML conforme à cold-email-rules.md (persona Juliette,
  CTA TidyCal, ≤150 mots, interdits FR).
- Un validateur code (validate_email) BLOQUE tout écart → le draft est marqué non conforme.
- Sortie au format steps Emelia (compatible get_default_steps).

Ce module NE PUSH RIEN. Il génère + valide. Le stockage (draft/approved) et le branchement
au pipeline sont les incréments suivants.

CLI dry-run :
    python3 scripts/email_generator.py --site lcr --sector banque
    python3 scripts/email_generator.py --site lcr --sector education-formation
"""

import argparse
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from llm_call import call_llm_json  # noqa: E402

ANGLES_FILE = BASE_DIR / "context" / "lcr" / "sector-angles.md"
RULES_FILE = BASE_DIR / "context" / "shared" / "cold-email-rules.md"

CTA_URL = "https://tidycal.com/1rr6kv1/15-minute-meeting"

# Numéro de téléphone de Juliette (signature). Laissé vide tant que non renseigné par le user.
PHONE = "07 44 30 66 03"

# Liens vers les pages SECTEUR de leclientroi.com (insérés en <a href> dans les emails).
SECTOR_LINKS = {
    "immobilier": "https://leclientroi.com/secteurs/immobilier",
    "restaurant": "https://leclientroi.com/secteurs/sms-restauration",
    "retail":     "https://leclientroi.com/secteurs/sms-retail-franchise",
}
# Ressources générales (fallback quand le secteur n'a pas de page dédiée + liens variés).
RESOURCE_LINKS = {
    "guide":    "https://leclientroi.com/guides",
    "app":      "https://leclientroi.com/fonctionnalites/app-mobile",
    "fidelite": "https://leclientroi.com/fonctionnalites/qr-code",
    "accueil":  "https://leclientroi.com",
}


def site_link(sector: str) -> str:
    """Lien à insérer dans l'email : page du secteur si elle existe, sinon le guide."""
    return SECTOR_LINKS.get(sector) or RESOURCE_LINKS["guide"]


# Signature Juliette : icône + téléphone (si renseigné) + lien site + désinscription RGPD obligatoire.
SIGNATURE_HTML = (
    '<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:18px;border-top:1px solid #e5e5e5;padding-top:12px"><tr>'
    '<td style="vertical-align:middle;padding-right:10px">'
    '<img src="https://ik.imagekit.io/rgpdsimplement/mail.png" alt="Le Client ROI" width="40" height="40" style="display:block;border-radius:8px">'
    '</td>'
    '<td style="vertical-align:middle;font-size:13px;color:#555;line-height:1.5">'
    '<strong style="color:#171717">Juliette</strong> · Le Client ROI<br>'
    + (f'☎️ <a href="tel:+33{PHONE.replace(" ", "")[1:]}" style="color:#555;text-decoration:none">{PHONE}</a> · ' if PHONE else '')
    + '<a href="https://leclientroi.com" style="color:#7E22CE">leclientroi.com</a> · contact@leclientroi.com'
    '</td></tr></table>'
    '<p style="font-size:12px;color:#888;margin-top:8px"><a href="{{UNSUBSCRIBE_LINK}}" style="color:#888">Me retirer de la liste</a></p>'
)

# Secteur DB -> sous-chaîne reconnaissable du titre de section dans sector-angles.md.
# Tout secteur absent de cette table est EXCLU (industrie, agro, autre, petits volumes).
SECTOR_SECTION = {
    "agence-marketing":    "agence marketing",
    "banque":              "banque",
    "assurance":           "assurance",
    "luxe-mode":           "luxe",
    "tourisme":            "tourisme",
    "medias-presse":       "médias",
    "immobilier":          "immobilier",
    "retail":              "retail",
    "restaurant":          "restaurant",
    "education-formation": "ducation",   # matche "Éducation / Formation"
}
EXCLUDED = {"industrie", "agroalimentaire", "autre"}

# Métadonnées d'affichage des secteurs supportés (= ceux qui ont un angle dans sector-angles.md).
SECTOR_META = {
    "agence-marketing":    ("🏢", "Agences marketing"),
    "banque":              ("🏦", "Banque"),
    "assurance":           ("🛡️", "Assurance"),
    "luxe-mode":           ("👜", "Luxe / Mode"),
    "tourisme":            ("✈️", "Tourisme"),
    "medias-presse":       ("📰", "Médias / Presse"),
    "immobilier":          ("🏠", "Immobilier"),
    "retail":              ("🛍️", "Retail"),
    "restaurant":          ("🍽️", "Restaurant"),
    "education-formation": ("🎓", "Éducation / Formation"),
}


def supported_sectors() -> list[dict]:
    """Secteurs proposables dans l'UI (ceux qui ont un angle rédigé)."""
    return [{"code": k, "emoji": e, "label": l} for k, (e, l) in SECTOR_META.items()]

# Interdits FR (cf. cold-email-rules.md) — détection casse-insensible sur le texte nettoyé.
# (« Cher/Chère [Prénom] » est traité à part, en salutation, pour éviter « décrocher ».)
BANNED = [
    "j'espère que vous allez bien", "je me permets", "n'hésitez pas",
    "cordialement", "suite à notre dernier échange",
    "en tant que professionnel du secteur", "votre entreprise semble intéressante",
    "je prends la liberté",
]

EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF←-⇿⌀-⏿]"
)
TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    """HTML -> texte brut (pour compter mots / chercher interdits)."""
    txt = re.sub(r"<br\s*/?>", " ", html, flags=re.I)
    txt = re.sub(r"</p>", " ", txt, flags=re.I)
    txt = TAG_RE.sub("", txt)
    return re.sub(r"\s+", " ", txt).strip()


def load_angle(sector: str) -> str | None:
    """Extrait le bloc markdown du secteur depuis sector-angles.md (angle + E1/E2/E3 rédigés)."""
    key = SECTOR_SECTION.get(sector)
    if not key or not ANGLES_FILE.exists():
        return None
    blocks = ("\n" + ANGLES_FILE.read_text(encoding="utf-8")).split("\n## ")
    for blk in blocks:
        header = blk.splitlines()[0].lower() if blk.strip() else ""
        if key in header:
            return "## " + blk.strip()
    return None


def validate_email(subject: str, body_html: str) -> list[str]:
    """Renvoie la liste des violations de cold-email-rules.md (vide = conforme)."""
    errors: list[str] = []
    text = _strip_html(body_html)
    low = (subject + " " + text).lower()

    for b in BANNED:
        if b in low:
            errors.append(f"interdit présent : « {b.strip()} »")

    # « Cher/Chère [Prénom] » : seulement en salutation (début de corps), pas dans « décrocher ».
    if re.match(r"(bonjour\s+)?ch[eèé]re?s?\b", text.strip(), re.I):
        errors.append("salutation « Cher/Chère » (utiliser le prénom seul)")

    words = len(text.split())
    if words > 150:
        errors.append(f"corps > 150 mots ({words})")

    # Compter les ancres <a> vers TidyCal (1 attendu), pas les occurrences de l'URL.
    cta = len(re.findall(r'href="[^"]*tidycal\.com/1rr6kv1', body_html))
    if cta == 0:
        errors.append("CTA TidyCal absent")
    elif cta > 1:
        errors.append(f"plus d'1 CTA TidyCal ({cta})")

    if EMOJI_RE.search(subject):
        errors.append("emoji dans l'objet")
    if len(subject) > 55:
        errors.append(f"objet trop long ({len(subject)} car.)")
    if not subject.strip():
        errors.append("objet vide")
    return errors


def _clean_body(body: str) -> str:
    """Nettoie une signature parasite générée par DeepSeek + force des <p>. N'appose PAS la signature
    (faite après _ensure_sector_link, pour que le lien secteur ne soit pas avalé par le nettoyage)."""
    # Retirer toute signature inventée (Camille / Juliette / LeClientROI en fin).
    body = re.sub(r"<p[^>]*>\s*(Camille|Juliette)\b.*?</p>\s*$", "", body, flags=re.S | re.I)
    body = re.sub(r"(Camille|Juliette)\s*<br>.*?(LeClientROI|Le Client ROI).*$", "", body, flags=re.S | re.I)
    body = body.strip()
    if "<p>" not in body and "<p " not in body:
        body = "".join(f"<p>{p.strip()}</p>" for p in body.split("\n\n") if p.strip())
    body = body.replace("\n", "<br>")
    return body


def to_emelia_steps(emails: list[dict]) -> list[dict]:
    """Convertit [{subject, body_html, delay_days}] au format steps Emelia."""
    delays = [(0, "MINUTES"), (3, "DAYS"), (7, "DAYS")]
    steps = []
    for i, em in enumerate(emails):
        amount, unit = delays[i] if i < len(delays) else (7, "DAYS")
        steps.append({
            "delay": {"amount": amount, "unit": unit},
            "versions": [{
                "subject": em["subject"],
                "disabled": False,
                "message": em["body_html"],
                "rawHtml": True,
                "attachments": [],
            }],
        })
    return steps


SYSTEM = (
    "Tu es Juliette, commerciale chez Le Client ROI (plateforme SMS + RCS marketing), et une "
    "EXPERTE du cold email B2B et de l'ICE BREAKER. Tu écris à des directeurs / responsables "
    "marketing de moyennes et grandes entreprises. Ton style : humain, conversationnel, "
    "contractions, zéro jargon corporate — on doit croire qu'un humain l'a écrit, pas un robot.\n"
    "La recette qui convertit :\n"
    "• E1 (1er contact) : ICE BREAKER = accroche qui montre qu'on s'est intéressé à SON monde "
    "(secteur / fonction), puis une QUESTION OUVERTE qui engage la réflexion, puis une proposition "
    "de valeur concise, puis un CTA à FAIBLE engagement (10-15 min). Jamais de pitch agressif.\n"
    "• E2 (relance) : angle neuf + PREUVE SOCIALE chiffrée + rappel du différenciateur, CTA soft.\n"
    "• E3 (breakup) : honnête, respecte le temps du prospect, donne la PERMISSION de dire non "
    "(« un simple non me va »), reste mémorable, porte ouverte.\n"
    "Tu respectes À LA LETTRE les règles fournies. Réponds UNIQUEMENT en JSON valide, sans texte autour."
)


def build_prompt(sector: str, angle_block: str, rules: str) -> str:
    lien = site_link(sector)
    return f"""=== RÈGLES COLD EMAIL (à respecter à la lettre) ===
{rules}

=== ANGLE & BROUILLONS VALIDÉS POUR LE SECTEUR « {sector} » ===
{angle_block}

=== MISSION ===
Écris une VRAIE séquence cold email B2B de 3 emails (E1 J+0, E2 J+3, E3 J+7) pour ce secteur.
L'angle ci-dessus est ta base d'idées — REFORMULE-le pour que ça sonne vivant et personnel,
jamais comme un publipostage. Garde les preuves autorisées et l'esprit du secteur.

EXIGENCES DE QUALITÉ (style cold email qui obtient des réponses) :
- E1 commence par un ICE BREAKER ancré sur le secteur / la fonction du destinataire
  (PAS « Bonjour, nous proposons… »), enchaîne sur une QUESTION OUVERTE, puis la valeur, puis le CTA.
- Ton parlé, phrases courtes, contractions. Bannis « je me permets », « n'hésitez pas », le jargon.
- INTERDIT les formules cliché d'IA : « c'est mission impossible », « Curieux de voir comment ? », « ROI x50 », « j'espère que vous allez bien ». Sois SPÉCIFIQUE et concret (un chiffre, un détail du métier), comme un humain qui connaît vraiment le secteur.
- E2 : une preuve sociale CHIFFRÉE et concrète. E3 : breakup qui donne la permission de dire non.

CONTRAINTES DE FORMAT :
- Chaque paragraphe dans un <p>…</p> distinct.
- Le CTA (prise de RDV) est UNIQUEMENT ce lien, une seule fois par email, en <a href="{CTA_URL}">…</a>.
- En PLUS du CTA, insère dans le corps AU MOINS UN lien vers le site en <a href="{lien}">texte parlant</a> (page du secteur / ressource).
- Quand le nom du secteur (ou un mot-clé sectoriel évident) apparaît dans le texte, mets-le en <strong>…</strong>.
- Variables autorisées : {{{{firstName}}}} (prénom), {{{{field1}}}} (entreprise).
- N'INVENTE PAS de signature ni de lien de désinscription : ils sont ajoutés automatiquement.
- Objet court (2-4 mots, minuscule, sans emoji), ≤ 150 mots par email.
- E2 et E3 apportent un angle NEUF (pas « je me permets de relancer »). E3 = breakup.

Réponds STRICTEMENT en JSON :
[
  {{"subject": "...", "body_html": "<p>...</p>", "delay_days": 0}},
  {{"subject": "...", "body_html": "<p>...</p>", "delay_days": 3}},
  {{"subject": "...", "body_html": "<p>...</p>", "delay_days": 7}}
]"""


def _ensure_sector_link(body: str, lien: str) -> str:
    """Garantit un lien vers le site DANS LE CORPS (hors signature) : si DeepSeek ne l'a pas mis,
    on rend le 1er mot en gras (= le secteur) cliquable vers sa page ; sinon on ajoute un lien."""
    if not body or lien in body:
        return body
    m = re.search(r"<strong>(.*?)</strong>", body)
    if m:
        return body.replace(m.group(0), f'<a href="{lien}"><strong>{m.group(1)}</strong></a>', 1)
    return body + f'<p><a href="{lien}">En savoir plus sur notre solution</a></p>'


def generate_sequence(site: str, sector: str) -> dict:
    """Génère + valide la séquence d'un secteur. Ne push rien."""
    if sector in EXCLUDED or sector not in SECTOR_SECTION:
        return {"sector": sector, "excluded": True,
                "reason": "secteur exclu ou sans angle (industrie/agro/autre/petit volume)"}

    angle = load_angle(sector)
    if not angle:
        return {"sector": sector, "excluded": True, "reason": "angle introuvable dans sector-angles.md"}

    rules = RULES_FILE.read_text(encoding="utf-8")
    prompt = build_prompt(sector, angle, rules)

    raw = call_llm_json(prompt, system=SYSTEM, max_tokens=2000, temperature=0.6,
                        module="cold_email", action=f"gen-seq-{sector}", site=site)

    emails = raw if isinstance(raw, list) else raw.get("emails", [raw])
    emails = emails[:3]

    all_errors: dict[int, list[str]] = {}
    for i, em in enumerate(emails):
        corps = _clean_body(em.get("body_html", ""))            # 1. retire la fausse signature DeepSeek
        corps = _ensure_sector_link(corps, site_link(sector))   # 2. garantit le lien secteur (sur corps propre)
        errs = validate_email(em.get("subject", ""), corps)     # valide le corps SANS la signature (≤150 mots)
        em["body_html"] = corps + SIGNATURE_HTML                # 3. appose la vraie signature Juliette
        if errs:
            all_errors[i + 1] = errs

    return {
        "sector": sector,
        "excluded": False,
        "emails": emails,
        "steps": to_emelia_steps(emails),
        "valid": not all_errors,
        "validation_errors": all_errors,
    }


def _cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="lcr")
    ap.add_argument("--sector", required=True)
    args = ap.parse_args()

    res = generate_sequence(args.site, args.sector)
    if res.get("excluded"):
        print(f"⏭️  {args.sector} EXCLU — {res['reason']}")
        return
    print(f"=== Séquence {args.sector} (site {args.site}) — conforme: {res['valid']} ===\n")
    for i, em in enumerate(res["emails"], 1):
        print(f"--- E{i} (J+{em.get('delay_days', '?')}) ---")
        print(f"Objet : {em.get('subject', '')}")
        print(_strip_html(em.get("body_html", "")))
        print()
    if res["validation_errors"]:
        print("⚠️  VIOLATIONS :")
        for step, errs in res["validation_errors"].items():
            print(f"  E{step}: " + " | ".join(errs))
    else:
        print("✅ Conforme à cold-email-rules.md")


if __name__ == "__main__":
    _cli()
