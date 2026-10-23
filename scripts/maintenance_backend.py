#!/usr/bin/env python3
"""maintenance_backend.py — Mode maintenance de la plateforme.

L'état vit dans un simple fichier JSON, PAS dans DuckDB, et c'est délibéré : il est lu à
chaque affichage de la page de login, donc par des visiteurs non authentifiés, et DuckDB
n'admet qu'un seul écrivain. Faire passer ce chemin public par la base, c'est ajouter de la
contention sur le verrou qui a déjà tué le dispatch du 19/08 — et se retrouver avec une page
de login en erreur pendant qu'un scrape écrit.

Règle de sécurité : le mode maintenance ne DOIT PAS enfermer dehors les administrateurs.
`login_allowed()` laisse toujours passer les rôles admin/superadmin.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = BASE_DIR / "memory" / "maintenance.json"

# Rôles qui traversent la maintenance (sinon : plus personne ne peut la désactiver).
BYPASS_ROLES = ("admin", "superadmin")

DEFAULT_MESSAGE = ("Cheffer est en maintenance planifiée. "
                   "La plateforme sera de nouveau disponible sous peu.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ouvert(degrade: bool = False) -> dict:
    return {"enabled": False, "message": DEFAULT_MESSAGE, "since": None,
            "by": "", "eta": "", "degraded": degrade}


def get_status() -> dict:
    """État courant. Ne lève jamais.

    Le défaut est « ouvert » : un incident de lecture ne doit pas couper l'accès à toute la
    plateforme. Mais un fichier PRÉSENT et illisible n'est pas la même chose qu'un fichier
    absent — c'est un incident, et il doit être bruyant. Un mode maintenance qui ne
    s'applique pas en silence est pire que pas de mode maintenance du tout : on croit le
    site fermé alors qu'il est ouvert. (Vécu le 19/08/2026 : fichier écrit en 0600 par root,
    illisible par l'utilisateur `autoblog` qui fait tourner l'API.)
    """
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {
            "enabled": bool(raw.get("enabled")),
            "message": raw.get("message") or DEFAULT_MESSAGE,
            "since": raw.get("since"),
            "by": raw.get("by") or "",
            "eta": raw.get("eta") or "",
            "degraded": False,
        }
    except FileNotFoundError:
        return _ouvert()  # jamais activée : situation normale
    except Exception as e:  # noqa: BLE001
        print(f"[maintenance] état ILLISIBLE ({type(e).__name__}: {e}) — "
              f"plateforme laissée ouverte, corriger {STATE_FILE}", flush=True)
        return _ouvert(degrade=True)


def set_status(enabled: bool, message: str = "", by: str = "", eta: str = "") -> dict:
    """Active ou lève la maintenance. Écriture atomique (rename), pour qu'une lecture
    concurrente ne tombe jamais sur un fichier à moitié écrit."""
    current = get_status()
    payload = {
        "enabled": bool(enabled),
        "message": (message or "").strip() or DEFAULT_MESSAGE,
        # `since` marque le DÉBUT de la maintenance en cours : on ne le remet à jour que
        # sur une vraie transition, sinon un simple changement de message ferait croire
        # que la maintenance vient de commencer.
        "since": _now() if (enabled and not current["enabled"]) else current.get("since"),
        "by": by or current.get("by") or "",
        "eta": (eta or "").strip(),
    }
    if not enabled:
        payload["since"] = None

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(STATE_FILE.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        # INDISPENSABLE : mkstemp crée en 0600. Ce fichier est écrit tantôt par root (CLI),
        # tantôt par l'utilisateur applicatif (API) — et relu par les deux. Sans ce chmod,
        # une bascule faite en ligne de commande reste invisible à l'API : la maintenance
        # semble activée et ne l'est pas.
        os.chmod(tmp, 0o644)
        os.replace(tmp, STATE_FILE)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise
    return payload


# Combien de temps demander à l'équipe d'attendre. Une durée ANNONCÉE vaut mieux qu'un
# écran qui dit « revenez plus tard » : sans elle, chacun réessaie toutes les trente
# secondes, ce qui fait exactement le bruit qu'on cherchait à éviter.
DELAI_DEFAUT_MIN = 15


def acces_autorise(role: str) -> bool:
    """Ce rôle peut-il utiliser la plateforme MAINTENANT ?

    `login_allowed` ne gardait que la porte d'entrée : une session déjà ouverte continuait
    de naviguer pendant une correction, avec des menus qui répondent 500 et des appels qui
    partent pour rien. C'est la plainte de Camille du 2026-08-25. Ce contrôle-ci s'applique
    à CHAQUE appel, pas seulement au login.
    """
    if not get_status()["enabled"]:
        return True
    return (role or "") in BYPASS_ROLES


def refus(role: str = "") -> dict:
    """Le corps de réponse d'un appel refusé pour cause de maintenance.

    Porte la durée à attendre : l'écran peut alors afficher un compte à rebours plutôt
    qu'un message vague.
    """
    st = get_status()
    return {"maintenance": True,
            "error": "plateforme en maintenance",
            "message": st.get("message") or DEFAULT_MESSAGE,
            "eta": st.get("eta") or "",
            "retry_minutes": DELAI_DEFAUT_MIN,
            "since": st.get("since")}


def login_allowed(role: str) -> bool:
    """Un login peut-il aboutir dans l'état courant ?

    Sans cette vérification côté serveur, la page de maintenance ne serait que cosmétique :
    n'importe qui gardant un onglet ouvert ou appelant l'API directement continuerait à
    entrer.
    """
    if not get_status()["enabled"]:
        return True
    return (role or "") in BYPASS_ROLES


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "on":
        print(json.dumps(set_status(True, " ".join(sys.argv[2:]), by="cli"), indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "off":
        print(json.dumps(set_status(False, by="cli"), indent=2))
    else:
        print(json.dumps(get_status(), indent=2))
        print("\nUsage : maintenance_backend.py [on [message] | off]")
