#!/usr/bin/env python3
"""Mesurer, page par page, ce qui déborde sur petit écran.

Demande de Camille (2026-08-26) : rendre l'interface utilisable sur mobile « sans toucher à
la version desktop », en vérifiant « 1 par 1 ».

Le contrôle est volontairement étroit et mesurable : **la page déborde-t-elle
horizontalement ?** C'est le défaut qui rend un écran inutilisable au doigt — on scrolle de
côté pour lire, les boutons partent hors champ. Le reste (densité, taille des cibles) se
juge à l'œil, pas par un script qui prétendrait le mesurer.

Un débordement CONTENU ne compte pas : une table large qui glisse dans sa propre boîte à
défilement est un choix correct, pas un défaut. Seuls les éléments qui poussent le corps de
page entier sont comptés — et le script les NOMME, sinon on corrige à l'aveugle.

Usage :
    python3 scripts/audit_responsive.py                  # 390 px, toutes les pages
    python3 scripts/audit_responsive.py --largeur 768    # tablette
    python3 scripts/audit_responsive.py --page cold_email
"""
from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

AUTH_DB = RACINE / "data" / "auth.duckdb"
OUTIL = Path("/home/autoblog/outils-captures/audit-responsive.mjs")
BASE = "https://api.cheffer.email"
SITE = "lcr"
PREFIXE = "capture-"

# 390 px = iPhone 14/15 en portrait, la largeur la plus contraignante encore courante.
# 768 px = tablette portrait, le point où le menu bascule en tiroir.
LARGEURS = (390, 768)


def _session() -> tuple[str, str]:
    import duckdb
    c = duckdb.connect(str(AUTH_DB))
    try:
        uid = c.execute("SELECT id FROM users WHERE lower(username) = 'camille'").fetchone()[0]
        jeton = PREFIXE + secrets.token_urlsafe(24)
        c.execute("INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                  [jeton, uid, datetime.now(timezone.utc).isoformat(),
                   (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()])
    finally:
        c.close()
    return jeton, uid


def _nettoyer() -> None:
    import duckdb
    c = duckdb.connect(str(AUTH_DB))
    try:
        c.execute("DELETE FROM sessions WHERE token LIKE ?", [PREFIXE + "%"])
    finally:
        c.close()


def _pages(seulement: str = "") -> list[dict]:
    import roles_backend as rbk
    beta = rbk.pages_beta()
    out = []
    for p in rbk.PAGES:
        if p.get("masque_menu"):
            continue
        if seulement and p["cle"] != seulement:
            continue
        out.append({"cle": p["cle"], "url": p["url"].replace("{site}", SITE),
                    "beta": p["cle"] in beta})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--largeur", type=int, default=0, help="une seule largeur")
    ap.add_argument("--page", default="", help="une seule page")
    ap.add_argument("--attente", type=int, default=3500)
    args = ap.parse_args()

    pages = _pages(args.page)
    largeurs = (args.largeur,) if args.largeur else LARGEURS
    if not pages:
        print("Aucune page à mesurer.")
        return 1

    _nettoyer()
    jeton, _ = _session()
    resultats: list[dict] = []
    try:
        for largeur in largeurs:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                             encoding="utf-8") as f:
                json.dump({"base": BASE, "jeton": jeton, "largeur": largeur,
                           "attente": args.attente, "pages": pages}, f)
                chemin = f.name
            r = subprocess.run(["node", str(OUTIL), chemin], cwd=str(OUTIL.parent),
                               capture_output=True, text=True, timeout=60 * len(pages) + 120)
            Path(chemin).unlink(missing_ok=True)
            for ligne in r.stdout.splitlines():
                try:
                    resultats.append(json.loads(ligne))
                except json.JSONDecodeError:
                    pass
            if r.returncode and not resultats:
                print(r.stderr[:400])
    finally:
        _nettoyer()

    en_faute = [x for x in resultats if x.get("debord", 0) > 1]
    for largeur in largeurs:
        lot = [x for x in resultats if x.get("largeur") == largeur]
        mauvais = [x for x in lot if x.get("debord", 0) > 1]
        print(f"\n{largeur} px — {len(lot) - len(mauvais)}/{len(lot)} page(s) sans débordement")
        for x in sorted(mauvais, key=lambda y: -y.get("debord", 0)):
            print(f"  ✗ {x['page']:<24} +{x['debord']:>4} px   {', '.join(x.get('coupables') or [])[:90]}")
        for x in lot:
            if x.get("erreur"):
                print(f"  ! {x['page']:<24} {x['erreur']}")

    print("\n" + "=" * 62)
    print(f"{len(en_faute)} page(s) débordent." if en_faute
          else "Aucune page ne déborde.")
    return 1 if en_faute else 0


if __name__ == "__main__":
    raise SystemExit(main())
