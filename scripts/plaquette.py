#!/usr/bin/env python3
"""plaquette.py — La présentation PDF jointe à l'email, taillée par secteur.

Une plaquette d'une page, générée à la volée. Pas de fichier à maintenir dans un dossier
partagé, pas de version qui traîne : le texte vient de `argumentaire.py`, donc la plaquette
et le script d'appel disent toujours la même chose. Le jour où l'argumentaire change, la
plaquette change avec lui — c'est tout l'intérêt de la fabriquer plutôt que de la stocker.

Une page, et une seule : personne ne lit la deuxième. Trois blocs — le problème du métier,
ce qu'on fait, comment ça se passe — et un contact en pied.
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

ROSE = (219, 39, 119)
ENCRE = (24, 24, 27)
GRIS = (113, 113, 122)


def _txt(s: str) -> str:
    """fpdf2 en police standard écrit en latin-1 : on remplace ce qui n'y entre pas plutôt
    que de laisser l'export échouer sur une apostrophe typographique."""
    return (s.replace("’", "'").replace("—", "-").replace("•", "-")
             .replace("…", "...").replace("«", '"').replace("»", '"')
             .replace(" ", " ").replace(" ", " "))


def construire(secteur: str, societe: str = "") -> bytes:
    from fpdf import FPDF
    import argumentaire as ar

    s = ar.script(secteur)
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_margins(18, 18, 18)

    # Bandeau
    pdf.set_fill_color(*ROSE)
    pdf.rect(0, 0, 210, 26, style="F")
    pdf.set_xy(18, 8)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, "Cheffer", align="L")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(18, 16)
    pdf.cell(0, 6, _txt(ar.PRODUIT["promesse"]), align="L")

    pdf.set_xy(18, 36)
    pdf.set_text_color(*ENCRE)
    pdf.set_font("Helvetica", "B", 15)
    cible = (ar.SECTEURS.get((secteur or "").lower()) or {}).get("cible") \
        or f"les professionnels du secteur {s['label'].lower()}"
    titre = f"Pour {cible}" + (f" - {societe}" if societe else "")
    pdf.multi_cell(174, 8, _txt(titre))
    pdf.ln(2)

    if s.get("contexte"):
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(*GRIS)
        pdf.multi_cell(174, 5.5, _txt(s["contexte"]))
        pdf.ln(4)

    pdf.set_text_color(*ENCRE)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, _txt("Ce que nous faisons pour vous"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10.5)
    for ligne in s["valeur"]:
        pdf.set_x(18)
        pdf.multi_cell(174, 6, _txt("-  " + ligne))
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, _txt("Comment ça se passe"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10.5)
    for i, etape in enumerate((
        "Nous récupérons votre base clients et nous la nettoyons.",
        "Vous relisez le message — deux minutes, pas plus.",
        "Nous envoyons, nous suivons, et vous voyez qui a ouvert et qui a cliqué.",
    ), start=1):
        pdf.set_x(18)
        pdf.multi_cell(174, 6, _txt(f"{i}.  " + etape))
    pdf.ln(6)

    pdf.set_draw_color(*ROSE)
    pdf.set_line_width(0.6)
    y = pdf.get_y()
    pdf.line(18, y, 192, y)
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GRIS)
    pdf.multi_cell(174, 5.5, _txt(
        "Sans engagement : vous arrêtez quand vous voulez. Désinscription en un clic sur "
        "chaque message, base nettoyée et conforme.\n"
        # `contact@cheffer.email` figurait ici alors que le domaine n'a AUCUN MX : tout ce
        # qu'on écrivait à cette adresse rebondissait. Adresse de contact confirmée par
        # Camille le 2026-08-23. Le domaine cheffer.email ne sert qu'à l'API
        # (api.cheffer.email) ; il ne reçoit pas d'email.
        "contact@leclientroi.com  -  https://leclientroi.com"))
    return bytes(pdf.output())


def nom_fichier(secteur: str) -> str:
    code = (secteur or "presentation").strip().lower().replace(" ", "-")
    return f"cheffer-{code}.pdf"


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Plaquette PDF par secteur")
    ap.add_argument("--secteur", default="immobilier")
    ap.add_argument("--sortie", default="/tmp/plaquette.pdf")
    a = ap.parse_args()
    Path(a.sortie).write_bytes(construire(a.secteur))
    print(f"{a.sortie} — {Path(a.sortie).stat().st_size} octets")
