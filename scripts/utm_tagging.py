"""utm_tagging.py — pose automatiquement les UTM sur les liens SORTANTS de Genesis.

But : que GA4 sache d'où viennent les visites (cold-email, newsletter…) au lieu de tout
ranger dans « Direct ». On ne tague QUE les liens vers les domaines possédés (leclientroi /
mkdgroupe). Les liens externes (tidycal, stripe…) et les placeholders ({{UNSUBSCRIBE_LINK}})
sont laissés intacts. Un lien déjà tagué (utm_*) n'est pas re-tagué.

Réutilisé par : emelia_campaign_manager (cold-email) et sweego_backend (newsletter).
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

OWNED_DOMAINS = ["leclientroi.com", "mkdgroupe.com"]
_HREF = re.compile(r'(href\s*=\s*)(["\'])(.*?)\2', re.I)


def _is_owned(host: str, domains) -> bool:
    host = (host or "").lower().split(":")[0]
    return any(host == d or host.endswith("." + d) for d in domains)


def slug_campaign(name: str) -> str:
    """Nom de campagne propre pour utm_campaign : minuscules, tirets, sans accents/espaces."""
    s = (name or "").strip().lower()
    s = (s.replace("é", "e").replace("è", "e").replace("ê", "e").replace("à", "a")
           .replace("ç", "c").replace("'", "-"))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "campagne"


def tag_url(url: str, source: str, medium: str, campaign: str, domains=OWNED_DOMAINS) -> str:
    if not url:
        return url
    u = url.strip()
    if u[:2] == "{{" or u[:1] in "#?" or u.startswith(("mailto:", "tel:", "data:")):
        return url
    try:
        p = urlsplit(u)
    except Exception:
        return url
    if not p.scheme.lower().startswith("http") or not _is_owned(p.netloc, domains):
        return url
    q = parse_qsl(p.query, keep_blank_values=True)
    if any(k.lower().startswith("utm_") for k, _ in q):  # déjà tagué -> on respecte
        return url
    q += [("utm_source", source), ("utm_medium", medium)]
    if campaign:
        q.append(("utm_campaign", campaign))
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), p.fragment))


def tag_links(html: str, source: str, medium: str, campaign: str = "", domains=OWNED_DOMAINS) -> str:
    """Tague tous les href vers un domaine possédé dans un corps HTML."""
    if not html:
        return html
    camp = slug_campaign(campaign) if campaign else ""

    def _repl(m):
        return m.group(1) + m.group(2) + tag_url(m.group(3), source, medium, camp, domains) + m.group(2)

    return _HREF.sub(_repl, html)


if __name__ == "__main__":  # petit test
    sample = ('<p>Voir <a href="https://leclientroi.com/secteurs/immobilier">notre offre</a> '
              'ou <a href="https://tidycal.com/x">RDV</a> · '
              '<a href="{{UNSUBSCRIBE_LINK}}">désinscription</a></p>')
    print(tag_links(sample, "coldemail", "email", "Immobilier 92"))
