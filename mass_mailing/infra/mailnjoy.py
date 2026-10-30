#!/usr/bin/env python3
"""mass_mailing/infra/mailnjoy.py — validation d'adresses, copie autonome.

COPIE AUTONOME de la logique de `scripts/mailnjoy_check.py` (Camille, 2026-09-25 :
« copies autonomes »). Aucune importation de `scripts/` : Mass Mailing ne doit pas
tomber quand Genesis bouge.

DEUX DIFFÉRENCES ASSUMÉES avec l'original, et il faut les connaître :

1. **L'original ne renvoie que `valid` / `risky` / `invalid`** — il sert un pipeline
   de cold email où tout ce qui n'est pas sûr est tué sur place. Ici la politique
   d'éligibilité est CONFIGURABLE (table `settings`), donc on conserve le détail :
   `catch_all`, `disposable`, `role`, `unknown` sortent distincts. Écraser ces
   nuances côté connecteur rendrait la politique produit inapplicable.

2. **L'original garde les adresses de rôle** (`contact@`, `agence@`) parce que
   c'est le cœur de cible du cold email B2B local — une règle inverse y avait tué
   2 735 bons contacts en deux mois. Ici on ne décide pas : on REMONTE l'attribut
   `role`, et c'est la politique qui tranche.

⚠️ L'API Mailnjoy est **UNITAIRE** : `/v2/unitary`, un email par appel. Il n'existe
ni API bulk, ni SFTP branché, ni webhook. Un « lot de 1 000 » est donc une unité de
travail INTERNE — 1 000 appels HTTP séquencés — et non un appel fournisseur.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"

API_BASE = "https://api.mailnjoy.com"
UNITARY_URL = f"{API_BASE}/v2/unitary"
CREDIT_URL = f"{API_BASE}/v1/credit"

# Statuts renvoyés, alignés sur la contrainte CHECK de `recipients.validation_status`.
DECISIONS = ("valid", "risky", "invalid", "unknown", "disposable", "role", "error")


def _env(cle: str, defaut: str = "") -> str:
    v = os.environ.get(cle)
    if v:
        return v
    if ENV_FILE.exists():
        for ligne in ENV_FILE.read_text().splitlines():
            ligne = ligne.strip()
            if ligne.startswith(f"{cle}=") and not ligne.startswith("#"):
                return ligne.split("=", 1)[1].strip().strip('"').strip("'")
    return defaut


def _headers() -> dict:
    return {"mailnjoy-id": _env("MAILNJOY_ID"),
            "mailnjoy-secret": _env("MAILNJOY_SECRET"),
            "Content-Type": "text/plain"}


def configure() -> bool:
    return bool(_env("MAILNJOY_ID") and _env("MAILNJOY_SECRET"))


def classer(brut: dict) -> tuple[str, str]:
    """Réponse Mailnjoy → (décision, motif lisible).

    La v2 emballe la charge utile dans `unitaryCheck` : on déballe si présent.
    """
    p = brut.get("unitaryCheck") if isinstance(brut, dict) and "unitaryCheck" in brut else (brut or {})
    statut = (p.get("status") or "").upper()
    categorie = (p.get("category") or "").upper()
    attrs = p.get("attributs", {}) or {}

    def attr(nom: str) -> bool:
        a = attrs.get(nom, {})
        return bool(a.get("value")) if isinstance(a, dict) else bool(a)

    if attr("spamtrap"):
        return "invalid", "spamtrap"
    if attr("disposable"):
        return "disposable", "adresse jetable"
    if statut in ("INVALID", "INCORRECT", "FULL"):
        return "invalid", f"statut {statut.lower()}"
    if categorie == "UNSAFE":
        return "invalid", "catégorie unsafe"
    if statut == "SUSPECT":
        return "risky", "statut suspect"
    if attr("catchall") or categorie == "RISKY":
        # Un catch-all accepte tout puis rebondit plus tard : ce n'est ni valide ni
        # invalide, c'est un pari. La politique décide, pas le connecteur.
        return "risky", "catch-all ou catégorie risky"
    if statut == "VALID" and categorie in ("VERY_SAFE", "SAFE"):
        # L'attribut `role` remonte avec le verdict valide : il informe la politique
        # sans écraser un résultat que Mailnjoy juge sûr.
        return ("role", "adresse de rôle, délivrable") if attr("role") else ("valid", "délivrable")
    if statut == "VALID":
        return "risky", f"valide mais catégorie {categorie.lower() or 'inconnue'}"
    return "unknown", f"statut {statut.lower() or 'absent'}"


def verifier(email: str, tentatives: int = 5) -> dict:
    """Vérifie UNE adresse. Ne lève jamais.

    Renvoie {ok, decision, reason, raw, status_code, error}. `ok=False` signale une
    erreur d'appel — à distinguer d'un verdict négatif, qui est un `ok=True` avec
    une décision `invalid` : confondre les deux ferait relancer indéfiniment des
    adresses que Mailnjoy a déjà tranchées.
    """
    if not configure():
        return {"ok": False, "decision": "error", "reason": "configuration absente",
                "raw": None, "status_code": 0, "error": "MAILNJOY_ID/SECRET manquants"}

    attente = 1.0
    derniere = ""
    for _ in range(tentatives):
        try:
            r = requests.post(f"{UNITARY_URL}?type=simple", data=email,
                              headers=_headers(), timeout=30)
            sc = r.status_code

            if sc == 200:
                brut = r.json()
                decision, motif = classer(brut)
                return {"ok": True, "decision": decision, "reason": motif,
                        "raw": brut, "status_code": 200, "error": None}
            if sc == 400:
                return {"ok": True, "decision": "invalid", "reason": "email malformé",
                        "raw": None, "status_code": 400, "error": None}
            if sc == 401:
                return {"ok": False, "decision": "error", "reason": "authentification refusée",
                        "raw": None, "status_code": 401,
                        "error": f"401 Mailnjoy : {(r.text or '').strip()[:200]}"}
            if sc == 403:
                # Crédit épuisé : erreur DÉFINITIVE, jamais réessayée. Relancer ne
                # fait que brûler du temps sur un compte à sec.
                return {"ok": False, "decision": "error", "reason": "crédit épuisé",
                        "raw": None, "status_code": 403, "error": "crédit Mailnjoy insuffisant"}
            if sc in (429, 500, 503):
                pause = r.headers.get("Retry-After")
                time.sleep(min(float(pause) if pause else attente, 30))
                attente = min(attente * 2, 30)
                derniere = f"http_{sc}"
                continue
            derniere = f"http_{sc}: {(r.text or '')[:120]}"
            break
        except requests.RequestException as e:
            derniere = str(e)[:150]
            time.sleep(attente)
            attente = min(attente * 2, 30)

    return {"ok": False, "decision": "error", "reason": "appel échoué",
            "raw": None, "status_code": 0, "error": derniere or "inconnu"}


def credit() -> dict:
    """Crédits restants. Sert au garde-fou : on refuse de démarrer une validation de
    48 000 adresses avec 200 crédits en banque."""
    if not configure():
        return {"ok": False, "erreur": "configuration absente"}
    try:
        r = requests.get(CREDIT_URL, headers=_headers(), timeout=20)
        if r.status_code != 200:
            return {"ok": False, "erreur": f"http {r.status_code}", "statut": r.status_code}
        # `/v1/credit` renvoie un ENTIER NU dans le corps (« 979010 »), pas du JSON.
        # Un `.json().get(...)` casse dessus — constaté le 2026-09-25.
        corps = (r.text or "").strip()
        try:
            return {"ok": True, "credit": int(corps), "brut": corps}
        except ValueError:
            d = r.json()
            reste = d.get("credit", d.get("credits", d.get("remaining")))
            return {"ok": True, "credit": reste, "brut": d}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "erreur": str(e)[:200]}


def sante() -> dict:
    if not configure():
        return {"ok": False, "configure": False, "erreur": "MAILNJOY_ID/SECRET manquants"}
    c = credit()
    return {"ok": c.get("ok", False), "configure": True,
            "credit": c.get("credit"), "erreur": c.get("erreur")}


if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) > 1 and "@" in sys.argv[1]:
        print(json.dumps(verifier(sys.argv[1]), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(sante(), ensure_ascii=False, indent=1))
