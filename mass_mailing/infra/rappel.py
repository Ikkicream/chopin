#!/usr/bin/env python3
"""mass_mailing/infra/rappel.py — la page de rappel (consentement) d'une campagne.

Demande de Camille (2026-09-26), sur le modèle de la page de consentement SMS de
LeClientRoi (app.leclientroi.com/sms/c/…) :

    lien du mail → page « Souhaitez-vous être recontacté ? » (logo de la newsletter,
    téléphone, case de consentement) → Oui : demande horodatée + email au responsable
    du call center → dans tous les cas, redirection vers le lien d'origine.

Ce qui fait preuve pour la CNIL :
- chaque version du formulaire est FIGÉE (table `formulaires_rappel`) et reste
  consultable publiquement, même après modification des réglages ;
- chaque réponse (table `rappels`) garde la version lue, le texte exact de la case
  cochée, l'heure du serveur, l'IP et le navigateur.

Le lien du mail porte un jeton signé (campagne, destinataire, lien d'origine) : on ne
peut ni fabriquer un faux lien, ni rediriger vers un site choisi par un tiers.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html as _h
import json
import re
from urllib.parse import urlparse

from . import desinscription

CHEMIN = "/api/public/mass-mailing/rappel"
CHEMIN_FORMULAIRE = "/api/public/mass-mailing/rappel/formulaire"

TEXTE_CONSENTEMENT = "J'accepte d'être rappelé(e) par {annonceur}, à qui mes coordonnées sont transmises."


# ── Réglages ─────────────────────────────────────────────────────────────────

def extraire_logo(html_str: str) -> str | None:
    """Le logo principal de la newsletter : la première image hébergée en ligne, hors
    pixels de suivi (1×1) et hors bandeau « voir la version en ligne »."""
    for m in re.finditer(r'(?is)<img\b[^>]*>', html_str or ""):
        balise = m.group(0)
        src = re.search(r'(?is)\bsrc=["\']([^"\']+)["\']', balise)
        if not src or not src.group(1).lower().startswith(("http://", "https://")):
            continue
        if re.search(r'(?is)\b(width|height)=["\']?1(px)?["\'\s>]', balise):
            continue
        return src.group(1)
    return None


def premier_lien(html_str: str) -> str | None:
    """Le premier lien de contenu : la redirection par défaut quand un lien n'en a pas."""
    for u in re.findall(r'(?is)<a\b[^>]*\bhref=["\']([^"\']+)["\']', html_str or ""):
        if _a_envelopper(u, ""):
            return u
    return None


def _lum(hexa: str) -> float:
    h = hexa.lstrip("#")
    if len(h) == 3:
        h = "".join(x * 2 for x in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _saturation(hexa: str) -> float:
    h = hexa.lstrip("#")
    if len(h) == 3:
        h = "".join(x * 2 for x in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    mx, mn = max(r, g, b), min(r, g, b)
    return 0 if mx == 0 else (mx - mn) / mx


def extraire_theme(html_str: str) -> dict:
    """Les couleurs de la page, prises dans la newsletter : fond clair de page, fond sombre
    dominant pour la carte, bouton d'action (couleur vive s'il y en a une, sinon pilule
    blanche comme les boutons de la newsletter), police."""
    from collections import Counter
    h = html_str or ""
    fonds = Counter(x.upper() for x in re.findall(
        r'(?i)(?:background(?:-color)?\s*:\s*|bgcolor=["\'])(#[0-9a-f]{6}|#[0-9a-f]{3})\b', h))
    clairs = [c for c, _ in fonds.most_common() if _lum(c) > 0.85 and c not in ("#FFFFFF", "#FFF")]
    sombres = [c for c, _ in fonds.most_common() if _lum(c) < 0.25]
    vives = [c for c, _ in fonds.most_common() if _saturation(c) > 0.45 and 0.15 < _lum(c) < 0.85]
    sombre = sombres[0] if sombres else "#111827"
    accent = vives[0] if vives else "#FFFFFF"
    famille = "Arial, Helvetica, sans-serif"
    for m in re.finditer(r'(?i)font-family\s*:\s*([^;>]+)', h):
        v = m.group(1).replace("&quot;", '"').replace("&#39;", "'")
        if not v.lstrip().startswith(('"', "'")):
            v = v.split('"')[0]            # fin de l'attribut style="…"
        v = re.sub(r'["\']', "", v).strip().rstrip(",")
        if v:
            famille = v if "," in v else f"{v}, Arial, Helvetica, sans-serif"
            break
    return {"fond": clairs[0] if clairs else "#F4F4F4", "carte": sombre,
            "bouton": accent, "bouton_texte": sombre if _lum(accent) > 0.6 else "#FFFFFF",
            "police": famille[:120]}


def config_par_defaut(c: dict, html_str: str) -> dict:
    annonceur = (c.get("from_name") or "").strip()
    return {
        "actif": False,
        "annonceur": annonceur,
        "logo": extraire_logo(html_str),
        "question": "Envie de l'essayer ?",
        "message": "Laissez votre numéro : un conseiller vous rappelle pour réserver votre essai.",
        "bouton_oui": "Oui, rappelez-moi",
        "bouton_non": "Non merci, voir le site",
        "redirection": premier_lien(html_str) or "",
        "email_responsable": "",
        "politique_url": "https://leclientroi.com/legal/confidentialite",
        "cgu_url": "https://leclientroi.com/legal/cgu",
        "contact_rgpd": (c.get("reply_to") or "").strip() or "contact@leclientroi.com",
        "conservation": "3 ans à compter de votre demande",
        "theme": extraire_theme(html_str),
    }


CHAMPS_TEXTE = ("annonceur", "logo", "question", "message", "bouton_oui", "bouton_non",
                "redirection", "email_responsable", "politique_url", "cgu_url",
                "contact_rgpd", "conservation")


def nettoyer_config(brut: dict, base: dict) -> dict:
    """Garde les seuls champs connus ; les URL doivent être http(s)."""
    out = {k: v for k, v in base.items() if k != "theme"}   # le thème se recalcule, jamais figé
    out["actif"] = bool(brut.get("actif", base.get("actif")))
    for k in CHAMPS_TEXTE:
        if k in brut:
            out[k] = str(brut.get(k) or "").strip()[:1000]
    for k in ("logo", "redirection", "politique_url", "cgu_url"):
        if out.get(k) and not out[k].lower().startswith(("http://", "https://")):
            raise ValueError(f"{k} : une adresse http(s) est attendue")
    if out.get("email_responsable") and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", out["email_responsable"]):
        raise ValueError("email du responsable invalide")
    if out["actif"]:
        manque = [k for k in ("annonceur", "redirection", "email_responsable") if not out.get(k)]
        if manque:
            raise ValueError("pour activer la page, renseignez : " + ", ".join(manque))
    return out


def texte_consentement(config: dict) -> str:
    return TEXTE_CONSENTEMENT.format(annonceur=config.get("annonceur") or "l'annonceur")


def empreinte(config: dict) -> str:
    utile = {k: config.get(k) for k in CHAMPS_TEXTE if k != "email_responsable"}
    utile["theme"] = config.get("theme")
    return hashlib.sha256(json.dumps(utile, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]


# ── Jetons et liens ──────────────────────────────────────────────────────────

def _signe(charge: str) -> str:
    mac = hmac.new(desinscription._secret(), f"mm-rappel:{charge}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac[:16]).decode().rstrip("=")


def jeton(campaign_id: str, recipient_id: int, destination: str, email: str = "") -> str:
    donnees = [str(campaign_id), int(recipient_id), destination] + ([email] if email else [])
    charge = base64.urlsafe_b64encode(json.dumps(donnees, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{charge}.{_signe(charge)}"


def lire_jeton(t: str) -> tuple[str, int, str, str] | None:
    """(campagne, destinataire, destination, email signé ou "")."""
    try:
        charge, sig = (t or "").rsplit(".", 1)
        if not hmac.compare_digest(sig, _signe(charge)):
            return None
        d = json.loads(base64.urlsafe_b64decode(charge + "=" * (-len(charge) % 4)))
        return str(d[0]), int(d[1]), str(d[2]), (str(d[3]) if len(d) > 3 else "")
    except Exception:  # noqa: BLE001 — jeton abîmé = lien invalide
        return None


def url(campaign_id: str, recipient_id: int, destination: str, email: str = "") -> str:
    return f"{desinscription.BASE_PUBLIQUE}{CHEMIN}?t={jeton(campaign_id, recipient_id, destination, email)}"


def _a_envelopper(href: str, balise: str) -> bool:
    h = (href or "").strip()
    if not h.lower().startswith(("http://", "https://")):
        return False                      # mailto:, tel:, #, vide
    if h.startswith(desinscription.BASE_PUBLIQUE):
        return False                      # désinscription, miroir, piège : nos propres liens
    if re.search(r'(?i)data-url-type=["\']unsub', balise):
        return False
    return True


def envelopper_liens(html_str: str, campaign_id: str, recipient_id: int, defaut: str = "", email: str = "") -> str:
    """Chaque lien de contenu passe par la page de rappel, qui renvoie ensuite vers lui.
    Les liens vides (« # », sans adresse) — les boutons « Réservez un essai » laissés
    sans cible dans la newsletter — mènent aussi à la page, puis vers `defaut`."""
    def remplacer(m: re.Match) -> str:
        balise = m.group(0)
        href = re.search(r'(?is)\bhref=(["\'])(.*?)\1', balise)
        if not href:
            return balise
        cible = _h.unescape(href.group(2)).strip()
        if defaut and cible in ("", "#") and not re.search(r'(?i)data-url-type=["\']unsub', balise):
            cible = defaut
        elif not _a_envelopper(cible, balise):
            return balise
        nouveau = _h.escape(url(campaign_id, recipient_id, cible, email), quote=True)
        return balise[:href.start(2)] + nouveau + balise[href.end(2):]
    return re.sub(r'(?is)<a\b[^>]*>', remplacer, html_str or "")


# ── Téléphone ────────────────────────────────────────────────────────────────

def normaliser_telephone(brut: str) -> str | None:
    """Numéro français (06…, +33 6…) ou international (+XX…, 8 à 15 chiffres)."""
    s = re.sub(r"[\s.\-()]", "", brut or "")
    if re.fullmatch(r"0[1-9]\d{8}", s):
        return "+33" + s[1:]
    if re.fullmatch(r"(\+|00)33[1-9]\d{8}", s):
        return "+33" + s[-9:]
    if re.fullmatch(r"(\+|00)[1-9]\d{7,14}", s):
        return "+" + s.lstrip("+").removeprefix("00")
    return None


# ── La page ──────────────────────────────────────────────────────────────────

def _css(t: dict) -> str:
    return f"""
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;background:{t['fond']};font-family:{t['police']};color:#111}}
.cadre{{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:32px 16px}}
.carte{{width:100%;max-width:520px;border-radius:24px;overflow:hidden;box-shadow:0 20px 40px -20px rgba(0,0,0,.35)}}
.haut{{background:#fff;padding:18px 28px;text-align:center}}.haut img{{height:64px;max-width:100%;object-fit:contain}}
.milieu{{background:{t['carte']};color:#fff;padding:32px 28px;text-align:center}}
h1{{font-size:26px;line-height:1.2;margin:0 0 10px;letter-spacing:-.01em}}.sous{{color:rgba(255,255,255,.78);font-size:15px;line-height:1.5;margin:0 0 24px}}
form{{text-align:left}}label.champ{{display:block;font-size:13px;color:rgba(255,255,255,.8);margin:0 0 6px}}
input[type=tel],input[type=email]{{width:100%;padding:14px 16px;border-radius:12px;border:1px solid rgba(255,255,255,.25);background:#fff;color:#111;font-size:16px;font-family:inherit}}
input:focus-visible,button:focus-visible,a:focus-visible{{outline:3px solid {t['bouton'] if t['bouton'] != '#FFFFFF' else '#9CA3AF'};outline-offset:2px}}
.groupe{{margin-bottom:16px}}.pour{{font-size:13px;color:rgba(255,255,255,.7);margin:0 0 16px;overflow-wrap:anywhere}}.pour b{{color:#fff;font-weight:600}}
.case{{display:flex;gap:10px;align-items:flex-start;font-size:13px;line-height:1.45;color:rgba(255,255,255,.8);cursor:pointer}}.case input{{margin-top:2px;width:18px;height:18px;flex:none}}
.boutons{{display:flex;flex-direction:column;gap:10px;padding-top:20px}}
.b{{display:block;width:100%;padding:15px 18px;border-radius:30px;font-weight:700;font-size:14px;letter-spacing:.06em;text-transform:uppercase;text-align:center;cursor:pointer;border:0;font-family:inherit}}
.b-oui{{background:{t['bouton']};color:{t['bouton_texte']}}}.b-non{{background:transparent;border:1px solid rgba(255,255,255,.35);color:#fff;text-transform:none;letter-spacing:0;font-weight:600}}
.info{{font-size:12px;line-height:1.5;color:rgba(255,255,255,.6);margin:16px 0 0;text-align:center}}
details{{margin-top:12px;font-size:12px;color:rgba(255,255,255,.7);text-align:left}}summary{{cursor:pointer;text-align:center;text-decoration:underline}}details p{{margin:8px 0}}details a{{color:#fff}}
.erreur{{background:#fee2e2;color:#991b1b;border-radius:12px;padding:10px 12px;font-size:13px;margin-bottom:16px}}
.bas{{background:#fff;padding:14px 28px;text-align:center;font-size:12px;color:#9ca3af}}.bas a{{color:#9ca3af}}
.archive{{background:#FEF3C7;color:#111;font-size:13px;padding:10px 16px;text-align:center;border-radius:12px;margin-bottom:12px}}
"""


_POLICES_SYSTEME = {"arial", "helvetica", "sans-serif", "serif", "georgia", "verdana", "tahoma", "system-ui", "times new roman"}


def rendre_page(config: dict, *, t: str = "", email: str = "", destination: str = "",
                erreur: str = "", telephone: str = "", archive: str = "") -> str:
    """La page, en HTML autonome, aux couleurs et à la police de la newsletter."""
    e = lambda x: _h.escape(str(x or ""), quote=True)  # noqa: E731
    theme = {**extraire_theme(""), **(config.get("theme") or {})}
    annonceur = e(config.get("annonceur"))
    dest = destination or config.get("redirection") or ""
    site = e(domaine(dest) or dest)
    premiere = theme["police"].split(",")[0].strip().strip("'\"")
    police = "" if premiere.lower() in _POLICES_SYSTEME else (
        f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family={_h.escape(premiere.replace(" ", "+"))}:wght@400;600;700&display=swap">')
    logo = f'<img src="{e(config.get("logo"))}" alt="{annonceur}">' if config.get("logo") else f'<b>{annonceur}</b>'
    lecture = bool(archive)
    off = "disabled" if lecture else ""
    champ_email = (f'<p class="pour">Pour : <b>{e(email)}</b></p><input type="hidden" name="email" value="{e(email)}">' if email else
                   f'<div class="groupe"><label class="champ" for="email">Votre email</label>'
                   f'<input id="email" name="email" type="email" autocomplete="email" {off}></div>')
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex, nofollow">
<title>{e(config.get("question"))} — {annonceur}</title>{police}<style>{_css(theme)}</style></head><body>
<div class="cadre"><div style="width:100%;max-width:520px">
{f'<div class="archive">{e(archive)}</div>' if archive else ''}
<div class="carte">
<div class="haut">{logo}</div>
<div class="milieu">
<h1>{e(config.get("question"))}</h1>
<p class="sous">{e(config.get("message"))}</p>
{f'<div class="erreur" role="alert">{e(erreur)}</div>' if erreur else ''}
<form method="post" action="{desinscription.BASE_PUBLIQUE}{CHEMIN}">
<input type="hidden" name="t" value="{e(t)}">
{champ_email}
<div class="groupe"><label class="champ" for="tel">Votre numéro</label>
<input id="tel" name="telephone" type="tel" autocomplete="tel" inputmode="tel" placeholder="06 12 34 56 78" value="{e(telephone)}" {off}></div>
<label class="case"><input type="checkbox" name="consent" value="1" {off}><span>{e(texte_consentement(config))}</span></label>
<div class="boutons">
<button class="b b-oui" type="submit" name="action" value="accepte" {off}>{e(config.get("bouton_oui"))}</button>
<button class="b b-non" type="submit" name="action" value="refuse" formnovalidate {off}>{e(config.get("bouton_non"))}</button>
</div></form>
<p class="info">Oui : votre numéro et votre email sont transmis à {annonceur} pour vous rappeler. Non : rien n'est transmis. Dans les deux cas, vous arrivez ensuite sur {site}.</p>
<details><summary>Vos données</summary>
<p><b>Responsable :</b> {annonceur}, collecte par LeClientRoi.</p>
<p><b>Pourquoi :</b> vous rappeler au sujet de cette offre (essai, rendez-vous). Base légale : votre consentement.</p>
<p><b>Quoi :</b> email, téléphone, date et heure de votre réponse, adresse IP. Transmis à {annonceur} uniquement, jamais revendus.</p>
<p><b>Combien de temps :</b> {e(config.get("conservation"))}.</p>
<p><b>Vos droits :</b> accès, rectification, effacement, opposition, retrait du consentement à tout moment : <a href="mailto:{e(config.get("contact_rgpd"))}">{e(config.get("contact_rgpd"))}</a>. Réclamation possible auprès de la CNIL (cnil.fr).</p>
</details>
</div>
<div class="bas"><a href="{e(config.get("cgu_url"))}" target="_blank" rel="noopener">CGU</a> · <a href="{e(config.get("politique_url"))}" target="_blank" rel="noopener">Confidentialité</a> · Consentement horodaté par LeClientRoi</div>
</div></div></div></body></html>"""


def rendre_merci(config: dict, destination: str, secondes: int = 3) -> str:
    """Après un « oui » : merci, puis la redirection au bout de `secondes` (balise meta,
    sans script ; un lien permet de passer tout de suite)."""
    e = lambda x: _h.escape(str(x or ""), quote=True)  # noqa: E731
    theme = {**extraire_theme(""), **(config.get("theme") or {})}
    dest = destination if destination.lower().startswith(("http://", "https://")) else "https://leclientroi.com"
    premiere = theme["police"].split(",")[0].strip().strip("'\"")
    police = "" if premiere.lower() in _POLICES_SYSTEME else (
        f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family={_h.escape(premiere.replace(" ", "+"))}:wght@400;600;700&display=swap">')
    logo = f'<img src="{e(config.get("logo"))}" alt="{e(config.get("annonceur"))}">' if config.get("logo") else f'<b>{e(config.get("annonceur"))}</b>'
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex, nofollow">
<meta http-equiv="refresh" content="{int(secondes)};url={e(dest)}">
<title>Merci — {e(config.get("annonceur"))}</title>{police}<style>{_css(theme)}
.coche{{width:56px;height:56px;border-radius:50%;margin:0 auto 16px;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,.12)}}
.barre{{height:3px;border-radius:3px;background:rgba(255,255,255,.15);overflow:hidden;margin:24px 0 12px}}
.barre span{{display:block;height:100%;background:{theme['bouton'] if theme['bouton'] != '#FFFFFF' else '#fff'};animation:mm-progres {int(secondes)}s linear forwards}}
@keyframes mm-progres{{from{{width:0}}to{{width:100%}}}}@media (prefers-reduced-motion:reduce){{.barre span{{animation:none;width:100%}}}}
</style></head><body>
<div class="cadre"><div style="width:100%;max-width:520px"><div class="carte">
<div class="haut">{logo}</div>
<div class="milieu" role="status">
<div class="coche" aria-hidden="true"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg></div>
<h1>Merci !</h1>
<p class="sous" style="margin-bottom:0">Nous allons vous rappeler dès qu'un conseiller est disponible.</p>
<div class="barre" aria-hidden="true"><span></span></div>
<p class="info" style="margin:0">Redirection vers {e(domaine(dest) or dest)}… <a href="{e(dest)}" style="color:#fff">Continuer maintenant</a></p>
</div></div></div></div></body></html>"""


def url_formulaire(formulaire_id: str) -> str:
    return f"{desinscription.BASE_PUBLIQUE}{CHEMIN_FORMULAIRE}/{formulaire_id}"


# ── Notification au responsable du call center ──────────────────────────────

def notification(config: dict, campagne: str, email: str, telephone: str, quand: str, preuve: str) -> tuple[str, str, str]:
    """(objet, html, texte) de l'email envoyé au responsable pour chaque « Oui »."""
    e = lambda x: _h.escape(str(x or ""))  # noqa: E731
    objet = f"Demande de rappel — {telephone} — {campagne}"[:200]
    lignes = [("Téléphone", telephone), ("Email", email), ("Campagne", campagne),
              ("Demande faite le", quand), ("Consentement", "oui, case cochée par le prospect")]
    html = ("<!doctype html><html><body style=\"font-family:Arial,sans-serif;color:#111;font-size:14px\">"
            f"<p>Bonjour,</p><p>Un prospect demande à être rappelé par téléphone pour <b>{e(config.get('annonceur'))}</b>. "
            "Merci de le rappeler pour confirmer son numéro et lui proposer un essai ou une démonstration.</p>"
            "<table cellpadding=\"6\" style=\"border-collapse:collapse\">"
            + "".join(f"<tr><td style=\"color:#666\">{e(k)}</td><td><b>{e(v)}</b></td></tr>" for k, v in lignes)
            + f"</table><p style=\"color:#666;font-size:12px\">Formulaire lu par le prospect (preuve CNIL) : "
              f"<a href=\"{e(preuve)}\">{e(preuve)}</a></p></body></html>")
    texte = ("Bonjour,\n\nUn prospect demande à être rappelé par téléphone pour "
             f"{config.get('annonceur')}.\n\n" + "\n".join(f"{k} : {v}" for k, v in lignes)
             + f"\n\nFormulaire lu par le prospect (preuve CNIL) : {preuve}\n")
    return objet, html, texte


def domaine(u: str) -> str:
    try:
        return urlparse(u).netloc
    except Exception:  # noqa: BLE001
        return ""
