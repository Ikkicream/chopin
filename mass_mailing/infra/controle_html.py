#!/usr/bin/env python3
"""mass_mailing/infra/controle_html.py — analyse et remise en forme d'un message HTML.

Demande de Camille (2026-09-25) : à l'import du fichier .html, « faire tous les
contrôles », poser les bonnes balises (page miroir, désabonnement, mentions),
contrôler les liens morts, les filtres anti-spam, les problèmes de HTML — et rendre
une carte de synthèse.

Deux sorties :
- `html_corrige` : le message avec les corrections SÛRES appliquées (balises de base,
  pré-en-tête, lien « version en ligne », alt manquants, scripts retirés, liens de
  désinscription marqués pour Sweego). Rien n'est réécrit dans le fond du message.
- `problemes` : ce qui reste à la main de l'auteur, classé bloquant / avertissement /
  info, avec la raison.

Uniquement la bibliothèque standard (html.parser) : le module ne doit pas dépendre
d'un paquet que le serveur n'a pas.

Sources des règles : doc Sweego (.claude/skills/sweego/SKILL.md — `data-url-type`,
`force_inline_style`, taille maximale 20 Mo) ; pratiques de délivrabilité courantes
(coupure Gmail à ~102 Ko, ratio texte/images, raccourcisseurs d'URL, texte caché).
"""
from __future__ import annotations

import html as _html
import ipaddress
import re
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

LIMITE_GMAIL = 102 * 1024           # au-delà, Gmail coupe le message (« Message tronqué »)
LIMITE_SWEEGO = 20 * 1024 * 1024    # doc Sweego : 20 Mo pièces jointes comprises
VIDES = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
         "source", "track", "wbr"}
INTERDITS = {"script": "bloquant", "iframe": "bloquant", "object": "bloquant", "embed": "bloquant",
             "form": "avertissement", "input": "avertissement", "video": "avertissement",
             "audio": "avertissement"}
RACCOURCISSEURS = {"bit.ly", "tinyurl.com", "goo.gl", "t.co", "ow.ly", "is.gd", "buff.ly",
                   "cutt.ly", "rebrand.ly", "shorturl.at", "tiny.cc", "lnkd.in"}
# Termes qui pèsent dans les filtres (SpamAssassin, filtres Microsoft/Gmail). Leur
# présence n'est pas une faute ; leur accumulation, si.
MOTS_SPAM = [
    "gratuit", "100% gratuit", "urgent", "cliquez ici", "gagnez", "gagner", "offre exclusive",
    "sans engagement", "promo", "promotion", "argent", "cash", "crédit", "remboursé",
    "garanti", "meilleur prix", "dernière chance", "offre limitée", "félicitations",
    "vous avez gagné", "sans frais", "économisez", "prix choc", "achetez maintenant",
    "free", "click here", "buy now", "act now", "limited time", "winner", "cash bonus",
    "risk free", "guarantee", "no cost", "100%", "€€€", "$$$", "!!!",
]
PREFIXES_TROMPEURS = ("re:", "tr:", "fw:", "fwd:", "réf:")


# Adresse trouvée sur la page contact publique de leclientroi.com (2026-09-25).
# Proposée pré-remplie, jamais enregistrée sans validation.
ADRESSE_PROPOSEE = "1 rue du Débarcadère, 92700 Colombes, France"

# Équivalents plus sûrs pour les filtres. Proposés case par case, jamais imposés.
REMPLACEMENTS = {
    "100% gratuit": "offert", "gratuit": "offert", "sans engagement": "résiliable à tout moment",
    "argent": "budget", "garanti": "assuré", "urgent": "important", "cliquez ici": "en savoir plus",
    "gagnez": "obtenez", "gagner": "obtenir", "offre exclusive": "offre réservée", "promotion": "offre",
    "promo": "offre", "cash": "trésorerie", "remboursé": "pris en charge", "meilleur prix": "tarif avantageux",
    "dernière chance": "derniers jours", "offre limitée": "offre valable quelques jours",
    "félicitations": "bravo", "sans frais": "inclus", "économisez": "réduisez vos coûts",
    "prix choc": "prix réduit", "achetez maintenant": "commandez", "!!!": "!", "€€€": "€",
    "free": "included", "click here": "learn more", "buy now": "order", "act now": "get started",
}
_STYLE_CACHE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*[01](px)?\s*[;\"']|max-height\s*:\s*0", re.I)


def _fin_element(html: str, debut: int, tag: str) -> int:
    """Position juste après la balise fermante qui équilibre celle ouverte à `debut`."""
    prof, i = 0, debut
    motif = re.compile(rf"(?is)<(/?){tag}\b[^>]*?(/?)>")
    for m in motif.finditer(html, debut):
        if m.group(1):
            prof -= 1
        elif not m.group(2):
            prof += 1
        if prof == 0:
            return m.end()
    return len(html)


def _texte(fragment: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"(?s)<[^>]+>", " ", fragment))).strip()


def blocs_caches(html: str) -> list[dict]:
    """Éléments masqués (hors pré-en-tête Cheffer), avec leur texte."""
    out = []
    for m in re.finditer(r"(?is)<(div|span|p|td|table|a|font)\b([^>]*)>", html):
        attrs = m.group(2)
        st = re.search(r'(?i)style\s*=\s*"([^"]*)"|style\s*=\s*\'([^\']*)\'', attrs)
        style = (st.group(1) or st.group(2)) if st else ""
        if not style or not _STYLE_CACHE.search(style + ";"):
            continue
        if re.search(r"(?i)mm-preheader|mm-piege|aria-hidden", attrs):
            continue
        fin = _fin_element(html, m.start(), m.group(1))
        out.append({"index": len(out), "debut": m.start(), "fin": fin, "texte": _texte(html[m.start():fin])[:200]})
    # on ne garde que les blocs les plus extérieurs
    garde = [b for b in out if not any(o is not b and o["debut"] <= b["debut"] and b["fin"] <= o["fin"] for o in out)]
    return [{"index": i, "debut": b["debut"], "fin": b["fin"], "texte": b["texte"]} for i, b in enumerate(garde)]


def liens_vides(html: str) -> list[dict]:
    out = []
    for m in re.finditer(r"(?is)<a\b([^>]*)>(.*?)</a\s*>", html):
        href = re.search(r'(?i)href\s*=\s*["\']([^"\']*)["\']', m.group(1))
        if href is not None and href.group(1).strip() in ("", "#"):
            img = re.search(r'(?i)<img[^>]*(?:alt|src)\s*=\s*["\']([^"\']*)', m.group(2))
            texte = _texte(m.group(2)) or (f"[image {img.group(1)[-40:]}]" if img else "[sans texte]")
            out.append({"index": len(out), "texte": texte[:80]})
    return out


def corriger(html: str, action: str, params: dict) -> tuple[str, dict]:
    """Applique une correction demandée depuis la carte d'analyse. Renvoie (html, info)."""
    info: dict = {}
    if action == "liens_vides":
        urls = params.get("urls") or {}          # {index: url} ; "*" = pour tous
        tous = (params.get("tous") or "").strip()
        compteur = {"i": -1, "n": 0}
        def _r(m):
            href = re.search(r'(?i)href\s*=\s*["\']([^"\']*)["\']', m.group(1))
            if href is None or href.group(1).strip() not in ("", "#"):
                return m.group(0)
            compteur["i"] += 1
            url = (urls.get(str(compteur["i"])) or tous or "").strip()
            if not re.match(r"(?i)^(https?://|mailto:|tel:)", url):
                return m.group(0)
            compteur["n"] += 1
            attrs = re.sub(r'(?i)\s*href\s*=\s*["\'][^"\']*["\']', "", m.group(1))
            return f'<a href="{_html.escape(url, quote=True)}"{attrs}>{m.group(2)}</a>'
        html = re.sub(r"(?is)<a\b([^>]*)>(.*?)</a\s*>", _r, html)
        info["liens_corriges"] = compteur["n"]
    elif action == "mots_spam":
        choisis = [x for x in (params.get("remplacements") or []) if x.get("mot") in REMPLACEMENTS]
        n = 0
        def _txt(seg: str) -> str:
            nonlocal n
            for x in choisis:
                mot, par = x["mot"], x.get("par") or REMPLACEMENTS[x["mot"]]
                def _cas(m):
                    t = m.group(0)
                    return par.upper() if t.isupper() and len(t) > 1 else (par[:1].upper() + par[1:] if t[:1].isupper() else par)
                seg, k = re.subn(re.escape(mot) if not mot[0].isalnum() else rf"(?i)\b{re.escape(mot)}\b", _cas, seg)
                n += k
            return seg
        morceaux = re.split(r"(?is)(<style\b.*?</style\s*>|<script\b.*?</script\s*>|<[^>]+>)", html)
        html = "".join(p if (p.startswith("<")) else _txt(p) for p in morceaux)
        info["remplacements"] = n
    elif action == "texte_cache":
        blocs = blocs_caches(html)
        garder = set(params.get("garder") or [])
        preheader = None
        for b in sorted(blocs, key=lambda b: b["debut"], reverse=True):
            if b["index"] in garder:
                continue
            if params.get("en_preheader") == b["index"]:
                preheader = b["texte"]
            html = html[:b["debut"]] + html[b["fin"]:]
        info["retires"] = len([b for b in blocs if b["index"] not in garder])
        if preheader:
            info["preheader"] = preheader
    return html, info


class _Analyseur(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pile: list[str] = []
        self.mal_fermees: list[str] = []
        self.balises: dict[str, int] = {}
        self.liens: list[dict] = []
        self.images: list[dict] = []
        self.texte: list[str] = []
        self.dans_lien: dict | None = None
        self.caches = 0
        self.doctype = False
        self.charset = False
        self.viewport = False
        self.titre = False
        self.css_externe = 0
        self.style_bloc = 0
        self._ignore = 0          # dans <style>/<script>/<title> : pas du texte visible

    def handle_decl(self, decl):
        if decl.lower().startswith("doctype"):
            self.doctype = True

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        self.balises[tag] = self.balises.get(tag, 0) + 1
        if tag not in VIDES:
            self.pile.append(tag)
        if tag in ("style", "script", "title"):
            self._ignore += 1
            if tag == "style":
                self.style_bloc += 1
            if tag == "title":
                self.titre = True
        if tag == "meta":
            if "charset" in a or "charset=" in a.get("content", "").lower():
                self.charset = True
            if a.get("name", "").lower() == "viewport":
                self.viewport = True
        if tag == "link" and "stylesheet" in a.get("rel", "").lower():
            self.css_externe += 1
        st = a.get("style", "").replace(" ", "").lower()
        if any(x in st for x in ("display:none", "font-size:0", "font-size:1px", "visibility:hidden")) \
                and "preheader" not in a.get("class", "") and "mm-preheader" not in a.get("class", ""):
            self.caches += 1
        if tag == "a":
            self.dans_lien = {"href": a.get("href", "").strip(), "texte": "",
                              "unsub": a.get("data-url-type") == "unsub"}
            self.liens.append(self.dans_lien)
        if tag == "img":
            self.images.append({"src": a.get("src", "").strip(), "alt": "alt" in a,
                                "width": "width" in a or "width" in st})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VIDES and self.pile and self.pile[-1] == tag:
            self.pile.pop()

    def handle_endtag(self, tag):
        if tag in ("style", "script", "title") and self._ignore:
            self._ignore -= 1
        if tag == "a":
            self.dans_lien = None
        if tag in VIDES:
            return
        if tag in self.pile:
            while self.pile and self.pile[-1] != tag:
                self.mal_fermees.append(self.pile.pop())
            self.pile.pop()
        else:
            self.mal_fermees.append(f"/{tag}")

    def handle_data(self, data):
        if self._ignore:
            return
        self.texte.append(data)
        if self.dans_lien is not None:
            self.dans_lien["texte"] += data


def _pb(liste, niveau, categorie, message, detail=None, action=None):
    liste.append({"niveau": niveau, "categorie": categorie, "message": message, "detail": detail, "action": action})


def verifier_lien(url: str) -> dict:
    """Le lien répond-il ? HEAD d'abord (léger), GET si le serveur refuse HEAD."""
    ua = {"User-Agent": "Mozilla/5.0 (compatible; CheffEmailLinkCheck/1.0)"}
    try:
        r = requests.head(url, allow_redirects=True, timeout=8, headers=ua)
        if r.status_code in (403, 405, 400, 501) or r.status_code >= 500:
            r = requests.get(url, allow_redirects=True, timeout=10, headers=ua, stream=True)
            r.close()
        return {"url": url, "code": r.status_code, "final": r.url if r.url != url else None,
                "ok": r.status_code < 400}
    except requests.RequestException as e:
        return {"url": url, "code": None, "ok": False, "erreur": type(e).__name__}


def _domaine(u: str) -> str:
    return (urlparse(u).hostname or "").lower().removeprefix("www.")


def analyser(html: str, *, objet: str = "", preheader: str = "", expediteur: dict | None = None,
             url_miroir: str | None = None, tester_liens: bool = True,
             rappel: dict | None = None) -> dict:
    problemes: list[dict] = []
    corrections: list[str] = []
    brut = html or ""
    if not brut.strip():
        _pb(problemes, "bloquant", "Structure", "Le fichier est vide.")
        return {"score": 0, "problemes": problemes, "corrections": [], "liens": [], "html_corrige": ""}

    a = _Analyseur()
    try:
        a.feed(brut)
        a.close()
    except Exception as e:  # noqa: BLE001
        _pb(problemes, "bloquant", "Structure", "Le HTML n'a pas pu être lu.", str(e)[:200])
    texte = re.sub(r"\s+", " ", _html.unescape(" ".join(a.texte))).strip()
    h = brut

    # ── Corrections sûres ────────────────────────────────────────────────────
    for tag, niveau in INTERDITS.items():
        n = a.balises.get(tag, 0)
        if not n:
            continue
        if tag == "script":
            h = re.sub(r"(?is)<script\b.*?</script\s*>", "", h)
            corrections.append(f"{n} bloc(s) <script> retiré(s) : les messageries les suppriment et les filtres anti-spam les sanctionnent.")
        else:
            _pb(problemes, niveau, "Structure", f"Balise <{tag}> présente ({n}) : non supportée par les messageries.",
                "Gmail et Outlook l'ignorent ou la suppriment ; remplacez-la par une image cliquable ou un lien.")
    if not a.doctype:
        h = "<!DOCTYPE html>\n" + h
        corrections.append("Déclaration <!DOCTYPE html> ajoutée.")
    if not re.search(r"(?is)<html\b", h):
        h = re.sub(r"(?is)^(<!DOCTYPE html>\s*)", r"\1<html lang=\"fr\"><head></head><body>", h, count=1) + "</body></html>"
        corrections.append("Structure <html>/<head>/<body> ajoutée.")
    if not re.search(r"(?is)<head\b", h):
        h = re.sub(r"(?is)(<html\b[^>]*>)", r"\1<head></head>", h, count=1)
    if not re.search(r"(?is)<body\b", h):
        h = re.sub(r"(?is)(</head\s*>)", r"\1<body>", h, count=1)
        h = re.sub(r"(?is)(</html\s*>)", r"</body>\1", h, count=1)
        corrections.append("Balise <body> ajoutée.")
    ajout_head = []
    if not a.charset:
        ajout_head.append('<meta charset="utf-8">')
        corrections.append("Encodage UTF-8 déclaré (sans lui, les accents peuvent s'afficher mal).")
    if not a.viewport:
        ajout_head.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
        corrections.append("Balise viewport ajoutée (affichage mobile).")
    if not a.titre and objet:
        ajout_head.append(f"<title>{_html.escape(objet)}</title>")
        corrections.append("Titre du document renseigné avec l'objet.")
    if ajout_head:
        h = re.sub(r"(?is)(<head\b[^>]*>)", r"\1" + "".join(ajout_head), h, count=1)

    # feuilles de style externes : téléchargées et intégrées dans un bloc <style>
    css_ko = []
    def _css(m):
        href = re.search(r'(?i)href\s*=\s*["\']([^"\']+)', m.group(0))
        url = href.group(1) if href else ""
        if not url.lower().startswith(("http://", "https://")):
            css_ko.append(url or "(sans adresse)")
            return m.group(0)
        try:
            r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200 and len(r.content) < 300_000:
                return f"<style>/* intégré depuis {url} */\n{r.text}</style>"
        except requests.RequestException:
            pass
        css_ko.append(url)
        return m.group(0)
    avant = h
    h = re.sub(r"(?is)<link\b[^>]*rel\s*=\s*[\"']?stylesheet[^>]*>", _css, h)
    nb_css = len(re.findall(r"/\* intégré depuis ", h)) - len(re.findall(r"/\* intégré depuis ", avant))
    if nb_css:
        corrections.append(f"{nb_css} feuille(s) de style externe(s) téléchargée(s) et intégrée(s) au message (Gmail et Outlook ignorent les liens vers un fichier CSS).")

    # alt manquants
    nb_sans_alt = 0
    def _alt(m):
        nonlocal nb_sans_alt
        tag = m.group(0)
        if re.search(r"\balt\s*=", tag, re.I):
            return tag
        nb_sans_alt += 1
        return re.sub(r"(?i)<img\b", '<img alt=""', tag, count=1)
    h = re.sub(r"(?is)<img\b[^>]*>", _alt, h)
    if nb_sans_alt:
        corrections.append(f"Attribut alt ajouté à {nb_sans_alt} image(s) (sans lui, une image bloquée laisse un trou et les filtres le notent).")

    # liens de désinscription de l'auteur → marqués pour Sweego
    nb_unsub = 0
    def _unsub(m):
        nonlocal nb_unsub
        tag, contenu = m.group(1), m.group(2)
        if "data-url-type" in tag.lower():
            return m.group(0)
        if re.search(r"(?i)d[ée]sinscri|d[ée]sabonn|unsubscribe|opt-?out", tag + contenu):
            nb_unsub += 1
            return tag[:-1] + ' data-url-type="unsub">' + contenu + "</a>"
        return m.group(0)
    h = re.sub(r"(?is)(<a\b[^>]*>)(.*?)</a\s*>", _unsub, h)
    if nb_unsub:
        corrections.append(f"{nb_unsub} lien(s) de désinscription marqué(s) data-url-type=\"unsub\" : Sweego les compte comme désinscriptions, pas comme clics.")

    # En-tête harmonisé (script de vérification, 2026-09-26) : un seul pré-en-tête caché,
    # une seule ligne « pré-en-tête | Voir la version en ligne » — celle de la newsletter
    # réécrite si elle existe.
    from .harmonisation import harmoniser
    h, notes = harmoniser(h, preheader=preheader, url_miroir=url_miroir or "")
    if notes:
        corrections.append("En-tête harmonisé : " + " ; ".join(notes) + ".")

    # ── Conformité ───────────────────────────────────────────────────────────
    exp = expediteur or {}
    _pb(problemes, "info", "Conformité",
        "Pied de message ajouté à chaque envoi : identité de l'expéditeur, raison de la réception et lien de désinscription personnel.",
        "Obligatoire en prospection électronique (CNIL / art. L34-5 CPCE). Sweego ajoute aussi l'en-tête List-Unsubscribe.")
    if not (exp.get("adresse_postale") or "").strip():
        _pb(problemes, "avertissement", "Conformité", "Adresse postale de l'expéditeur absente du pied de message.",
            "Recommandée (et exigée par la loi américaine CAN-SPAM).",
            action={"type": "adresse", "proposition": ADRESSE_PROPOSEE,
                    "raison_sociale": exp.get("raison_sociale") or exp.get("from_name") or ""})
    if not preheader:
        _pb(problemes, "info", "Délivrabilité", "Pas de pré-en-tête.",
            "Sans lui, les messageries affichent le début du texte (souvent « Voir la version en ligne »).")

    # ── Taille ───────────────────────────────────────────────────────────────
    taille = len(h.encode("utf-8"))
    if taille > LIMITE_SWEEGO:
        _pb(problemes, "bloquant", "Structure", f"Message de {taille / 1048576:.1f} Mo : au-delà de la limite Sweego (20 Mo).")
    elif taille > LIMITE_GMAIL:
        _pb(problemes, "avertissement", "Compatibilité", f"Message de {taille // 1024} Ko : Gmail le coupera (au-delà de ~102 Ko).",
            "Le bas du message, avec le lien de désinscription, deviendrait invisible. Allégez le HTML (styles, commentaires, images en base64).")

    # ── Structure ────────────────────────────────────────────────────────────
    mal = [t for t in a.mal_fermees if t not in ("p", "li", "td", "tr", "th", "option")]
    if mal:
        _pb(problemes, "avertissement", "Structure", f"{len(mal)} balise(s) mal fermée(s) ou orpheline(s).",
            ", ".join(sorted(set(mal))[:10]))
    if a.pile:
        restants = [t for t in a.pile if t not in ("p", "li", "td", "tr", "th", "html", "body", "head")]
        if restants:
            _pb(problemes, "avertissement", "Structure", f"{len(restants)} balise(s) jamais fermée(s).", ", ".join(restants[:10]))
    if css_ko:
        _pb(problemes, "avertissement", "Compatibilité", f"{len(css_ko)} feuille(s) de style externe(s) introuvable(s) : ignorée(s) par Gmail et Outlook.",
            "Impossible de la télécharger pour l'intégrer : " + ", ".join(css_ko[:3]))
    if a.style_bloc:
        _pb(problemes, "info", "Compatibilité", "Styles dans un bloc <style> : ils seront passés en ligne par Sweego à l'envoi (option force_inline_style).")
    if re.search(r"(?i)src=[\"']data:image", h):
        _pb(problemes, "avertissement", "Images", "Images intégrées en base64 : alourdissent le message et sont bloquées par Outlook.",
            "Hébergez les images et utilisez une URL https.")
    if "{{" in h:
        _pb(problemes, "bloquant", "Structure", "Variables {{…}} présentes : elles partiraient telles quelles.",
            ", ".join(sorted(set(re.findall(r"\{\{[^}]*\}\}", h)))[:5]))

    # ── Images ───────────────────────────────────────────────────────────────
    imgs = [i for i in a.images if i["src"]]
    if imgs and len(texte) < 300:
        _pb(problemes, "avertissement" if texte else "bloquant", "Anti-spam",
            f"{len(imgs)} image(s) pour {len(texte)} caractère(s) de texte : message « tout image ».",
            "Les filtres pénalisent les messages sans vrai texte. Visez au moins 500 caractères de texte.")
    rel_img = [i["src"] for i in imgs if not re.match(r"(?i)^(https?:|cid:|data:)", i["src"])]
    if rel_img:
        _pb(problemes, "bloquant", "Images", f"{len(rel_img)} image(s) avec un chemin relatif : elles ne s'afficheront pas.", rel_img[0][:120])
    if [i for i in imgs if i["src"].lower().startswith("http://")]:
        _pb(problemes, "avertissement", "Images", "Image(s) en http:// : certaines messageries les bloquent.")

    # ── Liens ────────────────────────────────────────────────────────────────
    hrefs = [l for l in a.liens]
    vides = liens_vides(h)
    if rappel and rappel.get("actif"):
        # Page de rappel active : à l'envoi, chaque lien hors miroir et désinscription (et
        # hors tel:/mailto:) passe par elle ; les boutons vides y mènent aussi, puis vers
        # la redirection choisie. Un lien vide n'est donc plus un problème.
        contenu = [l for l in hrefs if l["href"].lower().startswith(("http://", "https://"))
                   and not (url_miroir and l["href"].startswith(url_miroir.split("?")[0]))]
        # Le « se désabonner » d'origine (data-url-type="unsub") reçoit le lien de
        # désinscription à l'envoi : il ne compte pas parmi les liens vers la page.
        vides = [m for m in re.finditer(r'(?is)<a\b[^>]*>', h)
                 if re.search(r'(?is)\bhref=(["\'])\s*#?\s*\1', m.group(0))
                 and not re.search(r'(?i)data-url-type=["\']unsub', m.group(0))]
        _pb(problemes, "info", "Liens",
            f"Page de rappel active : {len(contenu) + len(vides)} lien(s) mèneront à la page de consentement"
            + (f", dont {len(vides)} bouton(s) sans adresse" if vides else "") + ".",
            f"Après la réponse, redirection vers la cible du lien, ou {rappel.get('redirection') or 'la redirection choisie'} pour les boutons sans adresse. "
            "Le lien miroir, la désinscription et les liens téléphone restent tels quels.")
    elif vides:
        _pb(problemes, "avertissement", "Liens", f"{len(vides)} lien(s) vide(s) ou « # » : quelle adresse doivent-ils ouvrir ?",
            None, action={"type": "liens_vides", "liens": vides})
    rel = [l["href"] for l in hrefs if l["href"] and not re.match(r"(?i)^(https?:|mailto:|tel:|#)", l["href"])]
    if rel:
        _pb(problemes, "bloquant", "Liens", f"{len(rel)} lien(s) relatif(s) : ils ne mèneront nulle part.", rel[0][:120])
    http = sorted({l["href"] for l in hrefs if l["href"].lower().startswith("http://")})
    if http:
        _pb(problemes, "avertissement", "Liens", f"{len(http)} lien(s) non sécurisé(s) en http://.", http[0][:120])
    courts = sorted({l["href"] for l in hrefs if _domaine(l["href"]) in RACCOURCISSEURS})
    if courts:
        _pb(problemes, "avertissement", "Anti-spam", "Lien(s) raccourci(s) (bit.ly…) : fortement pénalisés par les filtres.", courts[0])
    ip = []
    for l in hrefs:
        try:
            ipaddress.ip_address(urlparse(l["href"]).hostname or "")
            ip.append(l["href"])
        except ValueError:
            pass
    if ip:
        _pb(problemes, "bloquant", "Anti-spam", "Lien(s) vers une adresse IP : signature typique d'hameçonnage.", ip[0])
    trompeurs = []
    for l in hrefs:
        m = re.search(r"(?i)\b((?:https?://)?(?:www\.)?[a-z0-9-]+\.[a-z]{2,}(?:\.[a-z]{2,})?)\b", l["texte"] or "")
        if m and l["href"].startswith("http"):
            d_txt = _domaine(m.group(1) if "://" in m.group(1) else "https://" + m.group(1))
            if d_txt and d_txt != _domaine(l["href"]) and not _domaine(l["href"]).endswith("." + d_txt):
                trompeurs.append(f"« {l['texte'].strip()[:40]} » → {_domaine(l['href'])}")
    if trompeurs:
        _pb(problemes, "avertissement", "Anti-spam", "Texte de lien affichant un autre domaine que la destination.", trompeurs[0])
    if len(hrefs) > 25:
        _pb(problemes, "avertissement", "Anti-spam", f"{len(hrefs)} liens : beaucoup pour un email (au-delà de ~25, les filtres se méfient).")

    etat_liens: list[dict] = []
    a_tester = sorted({l["href"] for l in hrefs if l["href"].lower().startswith(("http://", "https://"))
                       and not (url_miroir and l["href"] == url_miroir)})
    if tester_liens and a_tester:
        with ThreadPoolExecutor(8) as ex:
            etat_liens = list(ex.map(verifier_lien, a_tester[:60]))
        morts = [x for x in etat_liens if not x["ok"] and x.get("code") in (404, 410)
                 or (not x["ok"] and x.get("erreur") in ("ConnectionError",))]
        douteux = [x for x in etat_liens if not x["ok"] and x not in morts]
        if morts:
            _pb(problemes, "bloquant", "Liens", f"{len(morts)} lien(s) mort(s).",
                "; ".join(f"{x['url'][:80]} ({x.get('code') or x.get('erreur')})" for x in morts[:5]))
        if douteux:
            _pb(problemes, "avertissement", "Liens", f"{len(douteux)} lien(s) qui répondent mal (refus, délai, erreur serveur).",
                "; ".join(f"{x['url'][:80]} ({x.get('code') or x.get('erreur')})" for x in douteux[:5]))

    # ── Anti-spam : objet et texte ───────────────────────────────────────────
    if not objet.strip():
        _pb(problemes, "bloquant", "Délivrabilité", "Objet vide.")
    else:
        lettres = [c for c in objet if c.isalpha()]
        if lettres and sum(c.isupper() for c in lettres) / len(lettres) > 0.5 and len(lettres) > 6:
            _pb(problemes, "avertissement", "Anti-spam", "Objet majoritairement en MAJUSCULES.")
        if objet.count("!") > 1 or "?!" in objet:
            _pb(problemes, "avertissement", "Anti-spam", "Plusieurs points d'exclamation dans l'objet.")
        if objet.strip().lower().startswith(PREFIXES_TROMPEURS):
            _pb(problemes, "avertissement", "Anti-spam", "Objet commençant par RE:/TR: sans échange préalable : jugé trompeur.")
        if len(objet) > 70:
            _pb(problemes, "info", "Délivrabilité", f"Objet de {len(objet)} caractères : coupé sur mobile au-delà de ~40-70.")
    corpus = f"{objet} {texte}".lower()
    trouves = [m for m in MOTS_SPAM if m in corpus]
    rempl = [{"mot": m, "par": REMPLACEMENTS[m]} for m in trouves if m in REMPLACEMENTS]
    if len(trouves) >= 3:
        _pb(problemes, "avertissement", "Anti-spam", f"{len(trouves)} expressions à risque pour les filtres.", ", ".join(trouves[:10]),
            action={"type": "mots_spam", "remplacements": rempl} if rempl else None)
    elif trouves:
        _pb(problemes, "info", "Anti-spam", "Expression(s) à surveiller.", ", ".join(trouves),
            action={"type": "mots_spam", "remplacements": rempl} if rempl else None)
    mots = re.findall(r"\b[^\W\d_]{4,}\b", texte)
    if mots and sum(m.isupper() for m in mots) / len(mots) > 0.15:
        _pb(problemes, "avertissement", "Anti-spam", "Beaucoup de mots en MAJUSCULES dans le texte.")
    if texte.count("!") > 5:
        _pb(problemes, "avertissement", "Anti-spam", f"{texte.count('!')} points d'exclamation dans le texte.")
    caches = blocs_caches(h)
    if caches:
        _pb(problemes, "avertissement", "Anti-spam", f"{len(caches)} bloc(s) de texte caché (display:none, taille 0…).",
            "Le texte caché est une technique de spammeur ; seul le pré-en-tête est admis.",
            action={"type": "texte_cache", "blocs": caches})

    poids = {"bloquant": 25, "avertissement": 7, "info": 0}
    score = max(0, 100 - sum(poids[p["niveau"]] for p in problemes))
    ordre = {"bloquant": 0, "avertissement": 1, "info": 2}
    problemes.sort(key=lambda p: ordre[p["niveau"]])
    return {"score": score, "problemes": problemes, "corrections": corrections, "liens": etat_liens,
            "taille_octets": taille, "nb_liens": len(hrefs), "nb_images": len(imgs),
            "nb_caracteres_texte": len(texte), "html_corrige": h,
            "bloquant": any(p["niveau"] == "bloquant" for p in problemes)}
