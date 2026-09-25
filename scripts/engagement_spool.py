#!/usr/bin/env python3
"""engagement_spool.py — file de secours des ouvertures et des clics.

Pourquoi ce fichier existe (constat du 2026-09-21) : le pixel d'ouverture
(`/api/track/open`) écrivait directement dans `contacts.duckdb`, base à UN SEUL
écrivain, et avalait l'échec dans un `print`. Le nettoyage nocturne ayant gardé le
verrou de 03:00 à 13:40, une journée entière d'ouvertures est partie au néant — le
pixel renvoyait son GIF 200, l'email s'affichait, personne ne voyait rien. C'est
Camille qui l'a remarqué : « 1 ouvreur seulement versus 40 d'habitude ».

Le principe : un engagement qu'on ne peut pas écrire tout de suite n'est pas perdu,
il est déposé dans un fichier JSONL et rejoué dès que la base se libère. Écrire une
ligne dans un fichier ne peut pas être bloqué par un verrou DuckDB — c'est ce qui
rend le dépôt fiable là où l'écriture directe ne l'est pas.

Format d'une ligne : {"site", "email", "kind", "channel", "at"}
  kind : "open" | "click"
  at   : horodatage ISO de l'engagement RÉEL, pas celui du rejeu. Un rejeu qui
         réécrirait `now()` daterait toutes les ouvertures de l'heure du déblocage
         et fausserait les statistiques par jour.

Usage :
  from engagement_spool import deposer, rejouer
  deposer("lcr", "a@b.com", "open", "maildoso")
  rejouer()            # renvoie {"rejoues": n, "restants": m, "erreurs": k}
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SPOOL_DIR = BASE_DIR / "data" / "spool"
SPOOL = SPOOL_DIR / "engagement.jsonl"

# Au-delà, on arrête d'empiler : si la base est bloquée depuis si longtemps, le
# problème n'est pas le spool, et un fichier qui grossit sans fin est un second
# incident par-dessus le premier.
MAX_LIGNES = 50_000


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def deposer(site: str, email: str, kind: str, channel: str = "maildoso",
            at: str | None = None) -> bool:
    """Dépose un engagement dans la file. Ne lève jamais : un pixel ne doit pas
    échouer à cause de sa propre file de secours."""
    try:
        SPOOL_DIR.mkdir(parents=True, exist_ok=True)
        if SPOOL.exists() and SPOOL.stat().st_size > MAX_LIGNES * 120:
            return False
        ligne = json.dumps({"site": site or "lcr", "email": (email or "").strip().lower(),
                            "kind": kind, "channel": channel or "maildoso",
                            "at": at or _maintenant()}, ensure_ascii=False)
        with SPOOL.open("a", encoding="utf-8") as f:
            f.write(ligne + "\n")
        return True
    except Exception:
        return False


def en_attente() -> int:
    """Nombre d'engagements en attente de rejeu (0 si la file n'existe pas)."""
    try:
        if not SPOOL.exists():
            return 0
        with SPOOL.open(encoding="utf-8") as f:
            return sum(1 for l in f if l.strip())
    except Exception:
        return 0


def rejouer(limite: int = 5000) -> dict:
    """Rejoue la file dans le pool. Les lignes qui échouent encore sont RÉÉCRITES
    dans la file : on ne perd rien, on réessaiera au prochain passage.

    La réécriture passe par un fichier temporaire puis un `replace` atomique, pour
    qu'une coupure au milieu du rejeu ne tronque pas la file.
    """
    out = {"rejoues": 0, "restants": 0, "erreurs": 0}
    if not SPOOL.exists():
        return out

    try:
        lignes = [l for l in SPOOL.read_text(encoding="utf-8").splitlines() if l.strip()]
    except Exception as e:  # noqa: BLE001
        out["erreurs"] = 1
        out["detail"] = str(e)[:200]
        return out
    if not lignes:
        return out

    sys.path.insert(0, str(BASE_DIR / "scripts"))
    try:
        import contacts_pool_backend as _cpb
    except Exception as e:  # noqa: BLE001
        out["erreurs"] = len(lignes)
        out["detail"] = f"import impossible: {str(e)[:150]}"
        return out

    restants: list[str] = []
    for i, l in enumerate(lignes):
        if i >= limite:
            restants.append(l)
            continue
        try:
            d = json.loads(l)
        except Exception:  # ligne illisible : on la jette, la garder ne mène nulle part
            out["erreurs"] += 1
            continue
        try:
            _cpb.record_engagement(d.get("site") or "lcr", d.get("email") or "",
                                   d.get("kind") or "open", d.get("channel") or "maildoso",
                                   at=d.get("at"))
            out["rejoues"] += 1
        except Exception:  # noqa: BLE001  (verrou toujours tenu, le plus souvent)
            restants.append(l)

    out["restants"] = len(restants)
    try:
        if restants:
            fd, tmp = tempfile.mkstemp(dir=str(SPOOL_DIR), prefix=".engagement-", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("\n".join(restants) + "\n")
            os.replace(tmp, SPOOL)
        else:
            SPOOL.unlink(missing_ok=True)
    except Exception as e:  # noqa: BLE001
        out["erreurs"] += 1
        out["detail"] = f"reecriture file: {str(e)[:150]}"
    return out


if __name__ == "__main__":
    print(json.dumps(rejouer(), ensure_ascii=False))
