#!/usr/bin/env python3
"""mass_mailing/infra/harmonisation.py — le « script de vérification » de l'en-tête et
du pied de chaque mail (Camille, 2026-09-26).

Constat sur un BAT JAECOO reçu dans Gmail : deux lignes « voir la version en ligne »
(la nôtre + celle de la newsletter, dont le lien était « # »), deux pré-en-têtes cachés,
et deux pieds de désinscription (celui de la newsletter + le nôtre). Règles :

EN-TÊTE — une seule ligne : le texte du pré-en-tête à gauche, « | », puis « Voir la
    version en ligne » à droite (vers la page miroir). Si la newsletter a déjà sa ligne
    « version en ligne », c'est ELLE qui est réécrite (on garde sa place et son style) ;
    sinon la ligne est ajoutée en haut. Un seul pré-en-tête caché.
PIED — si la newsletter a déjà un lien de désinscription, il reçoit le lien personnel et
    rien n'est ajouté ; sinon le pied Cheffer est ajouté (voir desinscription.pied_de_mail).

Idempotent : repasser le script sur un HTML déjà harmonisé ne change rien. Il s'applique
à la lecture (aperçu, page miroir) et à l'envoi : le HTML enregistré n'est pas modifié.
"""
from __future__ import annotations

import html as _h
import re

RE_MIROIR = re.compile(r"(?i)version\s+(en\s+ligne|web|navigateur)|voir\s+en\s+ligne|dans\s+(votre|le)\s+navigateur"
                       r"|view\s+(it\s+)?(online|in\s+(your\s+)?browser)|web\s+version")
RE_DESINSCRIPTION = re.compile(r"(?i)d[ée]sinscri|d[ée]sabonn|unsubscribe|opt-?out")
RE_CACHE = re.compile(r"(?is)display\s*:\s*none|mso-hide\s*:\s*all|max-height\s*:\s*0")


def _texte(fragment: str) -> str:
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"(?is)<[^>]+>", " ", fragment or ""))).strip()


def a_desinscription(html: str, *, marque_seulement: bool = False) -> bool:
    """La newsletter porte-t-elle déjà son propre lien de désinscription ?
    `marque_seulement` : ne compte que les liens marqués data-url-type="unsub" — ceux que
    l'envoi rebranche sur NOTRE désinscription (un lien non marqué pointe peut-être ailleurs)."""
    for m in re.finditer(r"(?is)(<a\b[^>]*>)(.*?)</a\s*>", html or ""):
        if re.search(r'(?i)data-url-type=["\']unsub', m.group(1)):
            return True
        if not marque_seulement and RE_DESINSCRIPTION.search(_texte(m.group(2))):
            return True
    return False


def _ligne(preheader: str, url_miroir: str) -> str:
    gauche = _h.escape(preheader or "")
    return ('<table class="mm-entete" role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            'style="font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:16px;color:#7D7D7D;">'
            f'<tr><td align="left" style="padding:0 8px 0 0;color:#7D7D7D;">{gauche}</td>'
            f'<td align="right" style="white-space:nowrap;color:#7D7D7D;">{"|&nbsp; " if gauche else ""}'
            f'<a href="{_h.escape(url_miroir, quote=True)}" style="color:#7D7D7D;text-decoration:underline;">'
            'Voir la version en ligne</a></td></tr></table>')


def _debut_corps(html: str) -> int:
    m = re.search(r"(?is)<body\b[^>]*>", html)
    return m.end() if m else 0


def _zone_entete(html: str) -> tuple[int, int]:
    """Du début du corps au premier contenu « lourd » (image ou texte long) : là où
    vivent pré-en-têtes et lignes « version en ligne »."""
    d = _debut_corps(html)
    fin = len(html)
    for m in re.finditer(r"(?is)<img\b|<h[1-6]\b", html[d:]):
        fin = d + m.start()
        break
    return d, fin


def harmoniser(html: str, *, preheader: str = "", url_miroir: str = "") -> tuple[str, list[str]]:
    """(HTML harmonisé, ce qui a été fait). Ne lève jamais."""
    notes: list[str] = []
    h = html or ""
    if not h.strip() or not url_miroir:
        return h, notes
    try:
        # 1. Nos anciennes lignes miroir (avant le 26/09) disparaissent : une seule ligne.
        h, n = re.subn(r'(?is)<div class="mm-miroir"[^>]*>.*?</div>', "", h)
        if n:
            notes.append("ancienne ligne « version en ligne » Cheffer retirée")

        # 2. Pré-en-tête : un seul bloc caché en tête. Sans pré-en-tête de campagne, on
        #    reprend le texte caché d'origine s'il y en a un.
        d, f = _zone_entete(h)
        caches = [m for m in re.finditer(r"(?is)<(div|span|p)\b([^>]*)>(.*?)</\1\s*>", h[d:f])
                  if RE_CACHE.search(m.group(2)) and "mm-preheader" not in m.group(2)
                  and "mm-piege" not in m.group(2) and not re.search(r"(?is)<(table|img|a)\b", m.group(3))]
        if not preheader and caches:
            preheader = _texte(caches[0].group(3))[:200]
        for m in reversed(caches):
            h = h[:d + m.start()] + h[d + m.end():]
        if caches:
            notes.append(f"{len(caches)} pré-en-tête(s) caché(s) en double retiré(s)")
        if preheader:
            bloc = (f'<div class="mm-preheader" style="display:none;max-height:0;overflow:hidden;opacity:0;'
                    f'mso-hide:all">{_h.escape(preheader)}&#8199;&#65279;&#847;</div>')
            if "mm-preheader" in h:
                h = re.sub(r'(?is)<div class="mm-preheader"[^>]*>.*?</div>', lambda _m: bloc, h, count=1)
            else:
                d = _debut_corps(h)
                h = h[:d] + bloc + h[d:]

        # 3. La ligne d'en-tête : la nôtre si elle existe déjà (mise à jour), sinon celle de
        #    la newsletter réécrite à sa place, sinon ajoutée juste après le pré-en-tête.
        ligne = _ligne(preheader, url_miroir)
        if "mm-entete" in h:
            h = re.sub(r'(?is)<table class="mm-entete".*?</table>', lambda _m: ligne, h, count=1)
        else:
            d, f = _zone_entete(h)
            cible = None
            for m in re.finditer(r"(?is)<a\b[^>]*>(.*?)</a\s*>", h[d:f]):
                if RE_MIROIR.search(_texte(m.group(1))):
                    cible = d + m.start()
                    break
            if cible is not None:
                # Le plus petit bloc qui contient ce lien (td, p ou div) : on remplace son
                # contenu, en gardant la balise (largeur, marges, fond de la newsletter).
                ouvertures = [m for m in re.finditer(r"(?is)<(td|p|div)\b[^>]*>", h[:cible])]
                remplace = False
                for o in reversed(ouvertures):
                    balise = o.group(1).lower()
                    if re.search(rf"(?is)</{balise}\s*>", h[o.end():cible]):
                        continue          # bloc déjà refermé avant le lien : pas le bon
                    fin = re.search(rf"(?is)</{balise}\s*>", h[cible:])
                    if fin and len(_texte(h[o.end():cible + fin.start()])) < 250:
                        h = h[:o.end()] + ligne + h[cible + fin.start():]
                        remplace = True
                        break
                if remplace:
                    notes.append("ligne « version en ligne » de la newsletter réécrite : pré-en-tête | lien")
            if "mm-entete" not in h:
                d = _debut_corps(h)
                m = re.search(r'(?is)<div class="mm-preheader"[^>]*>.*?</div>', h[d:])
                pos = d + m.end() if m else d
                h = (h[:pos] + '<div style="max-width:600px;margin:0 auto;padding:8px 12px;">' + ligne + "</div>" + h[pos:])
                notes.append("ligne d'en-tête ajoutée : pré-en-tête | Voir la version en ligne")
    except Exception as e:  # noqa: BLE001 — un HTML exotique ne doit jamais bloquer un envoi
        notes.append(f"harmonisation partielle ({type(e).__name__})")
    return h, notes
