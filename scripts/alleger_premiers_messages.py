#!/usr/bin/env python3
"""Allège les PREMIERS messages déjà enregistrés : moins de liens, plus d'image.

Le guide de délivrabilité de Maildoso demande d'éviter liens et images au tout premier
contact, et une signature sans photo. Le code de génération a été corrigé le 2026-08-25
(`email_generator` n'ajoute plus le lien secteur au premier email, la signature est passée
en texte) — mais les modèles DÉJÀ en base gardent l'ancienne forme. Ce script les reprend.

Ce qu'il fait, et rien d'autre :
  - dans les messages `first` : transforme les liens NON essentiels en texte simple —
    l'ancre reste lisible, le href disparaît. Le CTA de prise de rendez-vous et le lien de
    désinscription sont conservés : le premier est la raison d'être du message, le second
    est obligatoire ;
  - retire les images, quelle que soit l'étape : signature S3 comme illustrations.

`--dry-run` par défaut. Rien n'est écrit sans `--apply`.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

DB = Path(__file__).resolve().parent.parent / "data" / "god_mode.duckdb"

# Les liens qu'on garde, quoi qu'il arrive.
ESSENTIELS = ("api.cheffer.email/api/book", "tidycal.com", "unsubscribe", "{{UNSUBSCRIBE")


def _essentiel(url: str) -> bool:
    u = (url or "").lower()
    return any(marqueur.lower() in u for marqueur in ESSENTIELS)


def dedaigner_liens(html: str) -> tuple[str, int]:
    """Remplace `<a href=…>texte</a>` par `texte` pour les liens non essentiels."""
    retires = 0

    def _rw(m: re.Match) -> str:
        nonlocal retires
        url, contenu = m.group(1), m.group(2)
        if _essentiel(url):
            return m.group(0)
        retires += 1
        return contenu

    out = re.sub(r'<a\s[^>]*href="([^"]*)"[^>]*>(.*?)</a>', _rw, html or "", flags=re.S | re.I)
    return out, retires


def retirer_images(html: str) -> tuple[str, int]:
    """Retire les <img>, et le <p> qui ne contenait qu'elles."""
    n = len(re.findall(r"<img\b", html or "", flags=re.I))
    out = re.sub(r"<p[^>]*>\s*(?:<img[^>]*>\s*)+</p>", "", html or "", flags=re.I)
    out = re.sub(r"<img[^>]*>", "", out, flags=re.I)
    return out, n


def _connexion(lecture_seule: bool):
    """DuckDB n'accepte qu'un écrivain : on patiente au lieu d'échouer sèchement."""
    import duckdb
    derniere = None
    for _ in range(12):
        try:
            return duckdb.connect(str(DB), read_only=lecture_seule)
        except Exception as e:  # noqa: BLE001
            derniere = e
            time.sleep(5)
    raise derniere


def main() -> int:
    appliquer = "--apply" in sys.argv
    con = _connexion(lecture_seule=not appliquer)
    try:
        lignes = con.execute(
            "SELECT site_code, sector, kind, body_html FROM email_templates ORDER BY 1,2,3"
        ).fetchall()

        modifies = 0
        for site, secteur, kind, html in lignes:
            avant = html or ""
            apres, imgs = retirer_images(avant)
            liens = 0
            if kind == "first":
                apres, liens = dedaigner_liens(apres)
            if apres == avant:
                continue
            modifies += 1
            print(f"  {site}/{secteur}/{kind} : "
                  f"{liens} lien(s) déliés, {imgs} image(s) retirée(s)")
            if appliquer:
                con.execute(
                    "UPDATE email_templates SET body_html = ?, updated_by = ?, updated_at = now() "
                    "WHERE site_code = ? AND sector = ? AND kind = ?",
                    [apres, "allegement-delivrabilite", site, secteur, kind])

        print(f"\n{modifies} modèle(s) concerné(s) sur {len(lignes)}.")
        if not appliquer:
            print("Rien n'a été écrit. Relancer avec --apply pour appliquer.")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
