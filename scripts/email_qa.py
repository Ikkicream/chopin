"""
email_qa.py — Recette (QA) de tous les messages avant envoi.

Lint chaque source de message d'un site (Templates/structures, Cold emails, Messages validés)
via le MÊME rendu que l'envoi (résolveur unifié : cold emails emballés en HTML conforme,
variables de fusion whitelistées). Les corrections automatiques (emballage lang/charset/title
+ footer désinscription pour les cold emails) sont déjà appliquées par le résolveur ; ce script
VÉRIFIE et REMONTE ce qui reste à corriger à la main (ex. adresse postale, contraste).

CLI : python3 scripts/email_qa.py [site]   (défaut lcr)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

import email_lint_backend as elb
import html_templates_backend as htb


def qa_site(site: str = "lcr", save: bool = True) -> dict:
    opts = htb.campaign_message_options(site)
    results = []
    for g in opts["groups"]:
        for item in g["items"]:
            msg = htb.resolve_campaign_message(site, item["id"])
            if not msg or not msg.get("html"):
                results.append({"group": g["key"], "name": item["name"], "error": "message introuvable"})
                continue
            lint = elb.run_lint(msg["html"])
            # Persiste le résultat pour que le badge UI reflète la recette (sans clic manuel).
            if save and lint.get("ok"):
                if g["key"] == "template":
                    elb.save_result(site, "structure", item["id"].split(":", 1)[1], lint, by="recette")
                elif g["key"] == "version":
                    elb.save_result(site, "version", item["id"].split(":", 1)[1], lint, by="recette")
            if not lint.get("ok"):
                results.append({"group": g["key"], "name": item["name"], "error": lint.get("error")})
                continue
            counts = lint.get("counts", {})
            remaining = [f'{i.get("rule")}({i.get("category")})'
                         for i in lint.get("issues", []) if i.get("severity") == "error"]
            results.append({
                "group": g["key"], "name": item["name"], "id": item["id"],
                "score": lint.get("global_score"),
                "errors": counts.get("errors", 0), "warnings": counts.get("warnings", 0),
                "blocking": lint.get("blocking"),
                "remaining_errors": remaining,
            })
    return {"site": site, "results": results}


if __name__ == "__main__":
    site = sys.argv[1] if len(sys.argv) > 1 else "lcr"
    out = qa_site(site)
    print(f"=== Recette emails — {site} ===")
    for r in out["results"]:
        if r.get("error"):
            print(f"  [{r['group']:8}] {r['name']:18} ⚠ {r['error']}")
            continue
        flag = "🔴 BLOQUANT" if r["blocking"] else ("🟠" if r["errors"] else "🟢")
        line = f"  [{r['group']:8}] {r['name']:18} {flag} score={r['score']} err={r['errors']} warn={r['warnings']}"
        if r["remaining_errors"]:
            line += " | reste: " + ", ".join(r["remaining_errors"][:6])
        print(line)
    print(json.dumps(out, ensure_ascii=False))
