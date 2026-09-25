#!/usr/bin/env python3
"""mass_mailing/infra/stockage.py — les fichiers privés du module (CSV et HTML).

La spec demande un « stockage objet privé S3-compatible ». Il n'y en a pas sur ce
VPS, et en monter un pour quelques centaines de Mo serait de l'infrastructure pour
rien. Ce module en tient donc le RÔLE sur disque local, avec les trois propriétés
qui comptent :

- **Privé** — un répertoire en 0700, des fichiers en 0600, hors de toute racine
  servie par Next.js ou FastAPI. Aucun chemin n'est exposé au navigateur : le
  frontend ne manipule que des `storage_key` opaques.
- **Adressé par contenu** — la clé est dérivée du SHA-256. Déposer deux fois le
  même fichier ne crée pas deux copies, et le hash exigé par la spec (« conserver
  hash du HTML et du CSV ») est la clé elle-même : impossible qu'ils divergent.
- **Atomique** — écriture dans un temporaire puis `rename`. Un worker ne peut
  jamais lire un CSV à moitié écrit.

Le jour où un vrai stockage objet arrive, seules `deposer`, `lire` et `supprimer`
changent : le reste du module ne connaît que des clés.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent   # …/genesis
RACINE = Path(os.environ.get("MASS_MAILING_STOCKAGE",
                             BASE_DIR / "data" / "mass_mailing"))

GENRES = {"csv": ".csv", "html": ".html"}

# Plafond de sécurité codé en dur, AU-DESSUS du réglage `settings.max_csv_bytes` :
# même un réglage saisi de travers ne doit pas pouvoir faire avaler 2 Go au worker.
PLAFOND_ABSOLU = 200 * 1024 * 1024

_CLE = re.compile(r"^(csv|html)/[0-9a-f]{2}/[0-9a-f]{64}\.(csv|html)$")


class StockageErreur(ValueError):
    """Dépôt ou lecture refusés : fichier trop gros, vide, clé invalide."""


def _chemin(cle: str) -> Path:
    """Clé → chemin. Refuse tout ce qui ne sort pas de `deposer` (traversée `../`)."""
    if not _CLE.match(cle or ""):
        raise StockageErreur("clé de stockage invalide")
    return RACINE / cle


def _preparer(dossier: Path) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    for d in [dossier, *dossier.parents]:
        if d == RACINE.parent:
            break
        os.chmod(d, 0o700)


def deposer(contenu: bytes, genre: str, *, taille_max: int | None = None) -> dict:
    """Range le contenu et renvoie `{storage_key, sha256, taille, deja_present}`.

    Idempotent : un contenu déjà présent n'est pas réécrit.
    """
    if genre not in GENRES:
        raise StockageErreur(f"genre inconnu : {genre}")
    if not contenu:
        raise StockageErreur("fichier vide")
    plafond = min(taille_max or PLAFOND_ABSOLU, PLAFOND_ABSOLU)
    if len(contenu) > plafond:
        raise StockageErreur(
            f"fichier trop volumineux : {len(contenu) / 1048576:.1f} Mo "
            f"(maximum {plafond / 1048576:.0f} Mo)")

    empreinte = hashlib.sha256(contenu).hexdigest()
    cle = f"{genre}/{empreinte[:2]}/{empreinte}{GENRES[genre]}"
    cible = _chemin(cle)
    if cible.exists():
        return {"storage_key": cle, "sha256": empreinte, "taille": len(contenu),
                "deja_present": True}

    _preparer(cible.parent)
    tmp = cible.with_name(f".{cible.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenu)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, cible)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return {"storage_key": cle, "sha256": empreinte, "taille": len(contenu),
            "deja_present": False}


def lire(cle: str) -> bytes:
    """Relit un fichier et VÉRIFIE son empreinte : un fichier altéré est refusé."""
    chemin = _chemin(cle)
    if not chemin.exists():
        raise StockageErreur("fichier introuvable dans le stockage")
    contenu = chemin.read_bytes()
    attendu = chemin.stem
    if hashlib.sha256(contenu).hexdigest() != attendu:
        raise StockageErreur("empreinte du fichier altérée")
    return contenu


def existe(cle: str) -> bool:
    try:
        return _chemin(cle).exists()
    except StockageErreur:
        return False


def supprimer(cle: str) -> bool:
    chemin = _chemin(cle)
    if chemin.exists():
        chemin.unlink()
        return True
    return False


def purger(genre: str, jours: int, cles_protegees: set[str] | None = None) -> dict:
    """Supprime les fichiers plus vieux que `jours` (rétention de `settings`).

    `cles_protegees` : fichiers encore référencés par une campagne non archivée —
    c'est à l'appelant de les fournir, ce module ne lit pas la base.
    """
    if genre not in GENRES:
        raise StockageErreur(f"genre inconnu : {genre}")
    protegees = cles_protegees or set()
    limite = time.time() - jours * 86400
    supprimes = gardes = 0
    for f in (RACINE / genre).glob("*/*"):
        if f.name.startswith("."):
            continue
        cle = f"{genre}/{f.parent.name}/{f.name}"
        if f.stat().st_mtime < limite and cle not in protegees:
            f.unlink()
            supprimes += 1
        else:
            gardes += 1
    return {"genre": genre, "supprimes": supprimes, "gardes": gardes}


def sante() -> dict:
    try:
        _preparer(RACINE)
        sonde = RACINE / f".sonde.{os.getpid()}"
        sonde.write_bytes(b"ok")
        sonde.unlink()
        libre = os.statvfs(RACINE)
        return {"ok": True, "racine": str(RACINE),
                "libre_go": round(libre.f_bavail * libre.f_frsize / 1e9, 1)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "erreur": str(e)[:200]}


if __name__ == "__main__":
    import json
    print(json.dumps(sante(), ensure_ascii=False, indent=1))
