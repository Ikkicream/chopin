#!/usr/bin/env python3
"""
infographic.py — Génération d'infographies PNG professionnelles via Pillow.
Remplace les appels Higgsfield pour les schémas avec texte précis.

Usage:
  python3 infographic.py --type comparison --output /tmp/schema.png \
    --title "RCS vs SMS" \
    --left-header "SMS" --right-header "RCS" \
    --rows '[["Contenu","Texte 160 cars","Images + boutons"],...]' \
    --left-score "4/10" --right-score "9/10"
"""

import json
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FONT_PATH   = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD   = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Palette LCR
WHITE   = (255, 255, 255)
BG      = (248, 249, 250)
BLUE    = (0, 102, 255)
BLUE_L  = (224, 236, 255)
NAVY    = (26, 35, 64)
GREEN   = (0, 196, 140)
GREEN_L = (209, 250, 238)
RED     = (255, 71, 87)
GRAY    = (107, 114, 128)
GRAY_L  = (229, 231, 235)
GRAY_H  = (75, 85, 99)
DARK    = (17, 24, 39)
ROW_ALT = (245, 247, 250)


def load_font(path, size):
    return ImageFont.truetype(path, size)


def rounded_rect(draw, x1, y1, x2, y2, radius, fill=None, outline=None, outline_width=1):
    if fill:
        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill)
    if outline:
        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, outline=outline, width=outline_width)


def shadow_rect(img, x1, y1, x2, y2, radius, shadow_color=(0, 0, 0, 18), offset=4, blur=8):
    """Dessine une ombre portée sous un rectangle arrondi."""
    from PIL import ImageFilter
    shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow_layer)
    sd.rounded_rectangle(
        [x1 + offset, y1 + offset, x2 + offset, y2 + offset],
        radius=radius, fill=shadow_color
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(blur))
    img.paste(shadow_layer, mask=shadow_layer)


def draw_comparison(
    title: str,
    subtitle: str,
    left_header: str,
    right_header: str,
    rows: list,          # [["Critère", "val gauche", "val droite"], ...]
    left_score: str,
    right_score: str,
    watermark: str = "leclientroi.com",
    width: int = 800,
) -> Image.Image:
    """Tableau comparatif 2 colonnes."""

    ROW_H   = 52
    HEADER_H = 56
    SCORE_H  = 54
    PAD     = 32
    COL_GAP = 16
    TOP     = 110     # espace pour titre
    n_rows  = len(rows)
    height  = TOP + HEADER_H + n_rows * ROW_H + SCORE_H + PAD * 2

    img = Image.new("RGBA", (width, height), WHITE)
    draw = ImageDraw.Draw(img)

    f_title    = load_font(FONT_BOLD,   26)
    f_sub      = load_font(FONT_PATH,   13)
    f_header   = load_font(FONT_BOLD,   16)
    f_crit     = load_font(FONT_BOLD,   12)
    f_val      = load_font(FONT_PATH,   12)
    f_score    = load_font(FONT_BOLD,   15)
    f_water    = load_font(FONT_PATH,   11)

    # Fond général
    draw.rectangle([0, 0, width, height], fill=BG)

    # Bande titre
    draw.rectangle([0, 0, width, TOP - 8], fill=WHITE)

    # Titre
    draw.text((PAD, 22), title, font=f_title, fill=NAVY)
    if subtitle:
        draw.text((PAD, 58), subtitle, font=f_sub, fill=GRAY)

    # Watermark
    ww = draw.textlength(watermark, font=f_water)
    draw.text((width - ww - PAD, 22), watermark, font=f_water, fill=BLUE)

    # Colonnes
    col_w = (width - PAD * 2 - COL_GAP) // 2
    lx1, lx2 = PAD, PAD + col_w
    rx1, rx2 = PAD + col_w + COL_GAP, width - PAD

    table_bottom = TOP + HEADER_H + n_rows * ROW_H + SCORE_H

    # Ombres
    shadow_rect(img, lx1, TOP, lx2, table_bottom, radius=14)
    shadow_rect(img, rx1, TOP, rx2, table_bottom, radius=14)

    draw_layer = ImageDraw.Draw(img)

    # Fond colonnes
    rounded_rect(draw_layer, lx1, TOP, lx2, table_bottom, 14, fill=WHITE)
    rounded_rect(draw_layer, rx1, TOP, rx2, table_bottom, 14, fill=WHITE)

    # Headers
    rounded_rect(draw_layer, lx1, TOP, lx2, TOP + HEADER_H, 14, fill=GRAY_H)
    # Bas header = carré
    draw_layer.rectangle([lx1, TOP + HEADER_H // 2, lx2, TOP + HEADER_H], fill=GRAY_H)

    rounded_rect(draw_layer, rx1, TOP, rx2, TOP + HEADER_H, 14, fill=BLUE)
    draw_layer.rectangle([rx1, TOP + HEADER_H // 2, rx2, TOP + HEADER_H], fill=BLUE)

    # Texte headers
    lhw = draw_layer.textlength(left_header, font=f_header)
    rhw = draw_layer.textlength(right_header, font=f_header)
    draw_layer.text(((lx1 + lx2) // 2 - lhw // 2, TOP + HEADER_H // 2 - 10), left_header, font=f_header, fill=WHITE)
    draw_layer.text(((rx1 + rx2) // 2 - rhw // 2, TOP + HEADER_H // 2 - 10), right_header, font=f_header, fill=WHITE)

    # Lignes critères
    for i, row in enumerate(rows):
        crit, lval, rval = row[0], row[1], row[2]
        ry = TOP + HEADER_H + i * ROW_H
        row_bg = ROW_ALT if i % 2 == 0 else WHITE

        draw_layer.rectangle([lx1 + 1, ry, lx2 - 1, ry + ROW_H], fill=row_bg)
        draw_layer.rectangle([rx1 + 1, ry, rx2 - 1, ry + ROW_H], fill=row_bg)

        # Séparateur horizontal
        draw_layer.line([(lx1 + 8, ry), (lx2 - 8, ry)], fill=GRAY_L, width=1)
        draw_layer.line([(rx1 + 8, ry), (rx2 - 8, ry)], fill=GRAY_L, width=1)

        cy = ry + ROW_H // 2

        # Critère (petit label gris à gauche de chaque colonne)
        draw_layer.text((lx1 + 12, cy - 14), crit, font=f_crit, fill=GRAY)
        draw_layer.text((rx1 + 12, cy - 14), crit, font=f_crit, fill=GRAY)

        # Valeurs
        draw_layer.text((lx1 + 12, cy + 2), lval, font=f_val, fill=DARK)
        draw_layer.text((rx1 + 12, cy + 2), rval, font=f_val, fill=BLUE)

    # Score
    score_y = TOP + HEADER_H + n_rows * ROW_H

    draw_layer.rectangle([lx1 + 1, score_y, lx2 - 1, score_y + SCORE_H], fill=GRAY_L)
    draw_layer.rectangle([rx1 + 1, score_y, rx2 - 1, score_y + SCORE_H], fill=GREEN_L)

    # Coins bas arrondis
    draw_layer.rounded_rectangle([lx1, score_y, lx2, table_bottom], radius=14, fill=GRAY_L)
    draw_layer.rectangle([lx1, score_y, lx2, score_y + 14], fill=GRAY_L)

    draw_layer.rounded_rectangle([rx1, score_y, rx2, table_bottom], radius=14, fill=GREEN_L)
    draw_layer.rectangle([rx1, score_y, rx2, score_y + 14], fill=GREEN_L)

    lsw = draw_layer.textlength(left_score, font=f_score)
    rsw = draw_layer.textlength(right_score, font=f_score)
    draw_layer.text(((lx1 + lx2) // 2 - lsw // 2, score_y + 18), left_score, font=f_score, fill=GRAY_H)
    draw_layer.text(((rx1 + rx2) // 2 - rsw // 2, score_y + 18), right_score, font=f_score, fill=GREEN)

    # Bordures colonnes
    rounded_rect(draw_layer, lx1, TOP, lx2, table_bottom, 14, outline=GRAY_L, outline_width=1)
    rounded_rect(draw_layer, rx1, TOP, rx2, table_bottom, 14, outline=BLUE_L, outline_width=2)

    return img.convert("RGB")


def draw_flowchart(
    title: str,
    subtitle: str,
    steps: list,         # [{"label": "ENTREPRISE", "color": BLUE, "items": [...], "icon": ""}]
    arrows: list,        # [{"from": 0, "to": 1, "label": "RCS API", "color": CYAN}]
    note: str = "",
    watermark: str = "leclientroi.com",
    width: int = 800,
) -> Image.Image:
    """Flowchart horizontal N étapes."""

    BOX_W    = (width - 48) // len(steps) - 16
    BOX_H    = 160
    TOP      = 90
    PAD      = 24
    height   = TOP + BOX_H + 80 + (30 if note else 0)

    img = Image.new("RGBA", (width, height), WHITE)
    draw = ImageDraw.Draw(img)

    f_title  = load_font(FONT_BOLD,  22)
    f_sub    = load_font(FONT_PATH,  12)
    f_label  = load_font(FONT_BOLD,  11)
    f_item   = load_font(FONT_PATH,  10)
    f_arrow  = load_font(FONT_PATH,   9)
    f_water  = load_font(FONT_PATH,  11)

    draw.rectangle([0, 0, width, height], fill=BG)
    draw.rectangle([0, 0, width, TOP - 8], fill=WHITE)

    draw.text((PAD, 18), title, font=f_title, fill=NAVY)
    if subtitle:
        draw.text((PAD, 50), subtitle, font=f_sub, fill=GRAY)

    ww = draw.textlength(watermark, font=f_water)
    draw.text((width - ww - PAD, 18), watermark, font=f_water, fill=BLUE)

    n = len(steps)
    total_w = n * BOX_W + (n - 1) * 48
    start_x = (width - total_w) // 2
    box_y   = TOP

    box_centers = []

    for i, step in enumerate(steps):
        bx1 = start_x + i * (BOX_W + 48)
        bx2 = bx1 + BOX_W
        color = step.get("color", BLUE)
        if isinstance(color, str):
            color = tuple(int(color.lstrip("#")[j:j+2], 16) for j in (0, 2, 4))

        shadow_rect(img, bx1, box_y, bx2, box_y + BOX_H, radius=12)
        d2 = ImageDraw.Draw(img)

        d2.rounded_rectangle([bx1, box_y, bx2, box_y + BOX_H], radius=12, fill=WHITE)
        d2.rounded_rectangle([bx1, box_y, bx2, box_y + 34], radius=12, fill=color)
        d2.rectangle([bx1, box_y + 22, bx2, box_y + 34], fill=color)
        d2.rounded_rectangle([bx1, box_y, bx2, box_y + BOX_H], radius=12, outline=(*color, 255) if len(color) == 3 else color, width=2)

        lw = d2.textlength(step["label"], font=f_label)
        d2.text((bx1 + (BOX_W - lw) // 2, box_y + 10), step["label"], font=f_label, fill=WHITE)

        for j, item in enumerate(step.get("items", [])):
            d2.text((bx1 + 10, box_y + 44 + j * 22), f"• {item}", font=f_item, fill=DARK)

        box_centers.append((bx1 + BOX_W // 2, box_y + BOX_H // 2))

    # Flèches
    d3 = ImageDraw.Draw(img)
    for arrow in arrows:
        fi, ti = arrow["from"], arrow["to"]
        c = arrow.get("color", BLUE)
        if isinstance(c, str):
            c = tuple(int(c.lstrip("#")[j:j+2], 16) for j in (0, 2, 4))
        lbl = arrow.get("label", "")

        x1 = start_x + fi * (BOX_W + 48) + BOX_W
        x2 = start_x + ti * (BOX_W + 48)
        ay = box_centers[fi][1]

        d3.line([(x1, ay), (x2, ay)], fill=c, width=2)
        d3.polygon([(x2, ay), (x2 - 9, ay - 5), (x2 - 9, ay + 5)], fill=c)

        if lbl:
            lw2 = d3.textlength(lbl, font=f_arrow)
            d3.text(((x1 + x2) // 2 - lw2 // 2, ay - 14), lbl, font=f_arrow, fill=c)

    # Note bas
    if note:
        d3.text((PAD, TOP + BOX_H + 20), note, font=f_item, fill=GRAY)

    return img.convert("RGB")


def generate_rcs_comparison(output_path: str):
    rows = [
        ["Contenu",           "Texte 160 caracteres",    "Images, videos, boutons"],
        ["Taux d'ouverture",  "45 - 55 %",               "70 - 80 %"],
        ["Accuse de lecture", "Non",                     "Oui"],
        ["Sender ID",         "11 caracteres max",       "Logo verifie"],
        ["Analytics",         "Limite",                  "Clics + ouvertures + conversions"],
    ]
    img = draw_comparison(
        title="RCS vs SMS",
        subtitle="Comparaison des deux canaux de messagerie pour les entreprises",
        left_header="SMS",
        right_header="RCS",
        rows=rows,
        left_score="Score global : 4 / 10",
        right_score="Score global : 9 / 10",
        watermark="leclientroi.com",
    )
    img.save(output_path, "PNG", optimize=True)
    print(f"Saved: {output_path}")
    return output_path


def generate_rcs_flowchart(output_path: str):
    steps = [
        {"label": "ENTREPRISE",    "color": "#E07B00",
         "items": ["CRM / API", "Campagne RCS", "Templates valides"]},
        {"label": "OPERATEUR RCS", "color": "#0066FF",
         "items": ["Routage", "Verification", "Fallback SMS"]},
        {"label": "SMARTPHONE",    "color": "#00C48C",
         "items": ["Android 9+", "Images & Boutons", "Accuse de lecture"]},
    ]
    arrows = [
        {"from": 0, "to": 1, "label": "RCS API",  "color": "#0066FF"},
        {"from": 1, "to": 2, "label": "Livraison", "color": "#00C48C"},
    ]
    img = draw_flowchart(
        title="Comment fonctionne le RCS",
        subtitle="Flux de communication entre l'entreprise et le smartphone",
        steps=steps,
        arrows=arrows,
        note="Fallback automatique vers SMS si le destinataire n'est pas compatible RCS",
        watermark="leclientroi.com",
    )
    img.save(output_path, "PNG", optimize=True)
    print(f"Saved: {output_path}")
    return output_path


if __name__ == "__main__":
    generate_rcs_flowchart("/tmp/schema_rcs_flow.png")
    generate_rcs_comparison("/tmp/schema_rcs_comp.png")
    print("Done.")
