#!/usr/bin/env python3
"""mass_mailing/infra/cles_api.py — clés d'API saisies par le superadmin (20/10/2026).

Camille colle la clé DeepSeek dans l'espace superadmin au lieu de la donner dans une conversation
(où elle est masquée par des *). La clé :
- est testée auprès du fournisseur AVANT d'être enregistrée (une clé refusée n'écrase rien) ;
- est chiffrée en base (Fernet) ; la clé de chiffrement vit dans un fichier hors base, lisible
  par autoblog seul — une sauvegarde de la base seule ne livre donc aucune clé ;
- n'est JAMAIS renvoyée à l'écran : seulement « configurée », sa fin (…9e09) et sa source.
Sans clé en base, on retombe sur `DEEPSEEK_API_KEY` de l'environnement ou de genesis/.env.
"""
from __future__ import annotations

import os
from pathlib import Path

import requests
from cryptography.fernet import Fernet, InvalidToken

from . import pg

BASE_DIR = Path(__file__).resolve().parents[2]
FICHIER_CHIFFREMENT = BASE_DIR / "data" / ".mm_cle_chiffrement"

# nom → (variable d'environnement de repli, URL de contrôle qui rend le solde)
FOURNISSEURS = {"deepseek": ("DEEPSEEK_API_KEY", "https://api.deepseek.com/user/balance")}


def appliquer_schema() -> None:
    with pg.espace(pg.SCHEMA):
        pg.ecrire("""
            CREATE TABLE IF NOT EXISTS cles_api (
                nom          TEXT        PRIMARY KEY,
                chiffree     TEXT        NOT NULL,
                fin          TEXT        NOT NULL,
                maj_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
                maj_par      TEXT
            )""")


def _fernet() -> Fernet:
    if not FICHIER_CHIFFREMENT.exists():
        FICHIER_CHIFFREMENT.write_bytes(Fernet.generate_key())
        os.chmod(FICHIER_CHIFFREMENT, 0o600)
    return Fernet(FICHIER_CHIFFREMENT.read_bytes().strip())


def _depuis_env(nom: str) -> str:
    var = FOURNISSEURS[nom][0]
    cle = os.environ.get(var, "")
    env = BASE_DIR / ".env"
    if not cle and env.exists():
        for ligne in env.read_text().splitlines():
            ligne = ligne.strip()
            if ligne.startswith(f"{var}="):
                cle = ligne.split("=", 1)[1].strip().strip("'\"")
                break
    return cle


def lire(nom: str) -> str:
    """La clé à utiliser : celle du superadmin si elle existe, sinon celle de l'environnement."""
    try:
        with pg.espace(pg.SCHEMA):
            l = pg.ligne("SELECT chiffree FROM cles_api WHERE nom = %(n)s", {"n": nom})
        if l:
            return _fernet().decrypt(l["chiffree"].encode()).decode()
    except (InvalidToken, OSError):
        pass      # fichier de chiffrement perdu : on retombe sur l'environnement
    return _depuis_env(nom)


def tester(nom: str, cle: str) -> dict:
    """Interroge le fournisseur. Rend {"ok": bool, "solde": "32.56 USD" | None, "erreur": str | None}."""
    try:
        r = requests.get(FOURNISSEURS[nom][1], headers={"Authorization": f"Bearer {cle}"}, timeout=15)
    except requests.RequestException as e:
        return {"ok": False, "solde": None, "erreur": f"fournisseur injoignable : {e.__class__.__name__}"}
    if r.status_code in (401, 403):
        return {"ok": False, "solde": None, "erreur": "clé refusée par le fournisseur"}
    if r.status_code != 200:
        return {"ok": False, "solde": None, "erreur": f"réponse {r.status_code} du fournisseur"}
    infos = (r.json().get("balance_infos") or [{}])[0]
    solde = f"{infos['total_balance']} {infos.get('currency', '')}".strip() if infos.get("total_balance") else None
    return {"ok": True, "solde": solde, "erreur": None}


def enregistrer(nom: str, cle: str, par: str) -> dict:
    cle = (cle or "").strip()
    if nom not in FOURNISSEURS:
        raise ValueError("fournisseur inconnu")
    if len(cle) < 20 or "*" in cle or any(c.isspace() for c in cle):
        raise ValueError("clé invalide (trop courte, avec des espaces ou des *)")
    t = tester(nom, cle)
    if not t["ok"]:
        raise ValueError(t["erreur"])
    with pg.espace(pg.SCHEMA):
        pg.ecrire("""INSERT INTO cles_api (nom, chiffree, fin, maj_par) VALUES (%(n)s, %(c)s, %(f)s, %(p)s)
                     ON CONFLICT (nom) DO UPDATE SET chiffree = EXCLUDED.chiffree, fin = EXCLUDED.fin,
                                                     maj_at = now(), maj_par = EXCLUDED.maj_par""",
                  {"n": nom, "c": _fernet().encrypt(cle.encode()).decode(), "f": cle[-4:], "p": par})
    return t


def retirer(nom: str) -> bool:
    with pg.espace(pg.SCHEMA):
        return bool(pg.ecrire("DELETE FROM cles_api WHERE nom = %(n)s", {"n": nom}))


def etat(nom: str) -> dict:
    """Ce que l'écran a le droit de voir : jamais la clé."""
    with pg.espace(pg.SCHEMA):
        l = pg.ligne("SELECT fin, maj_at, maj_par FROM cles_api WHERE nom = %(n)s", {"n": nom})
    if l:
        return {"nom": nom, "configuree": True, "source": "superadmin", "fin": l["fin"],
                "maj_at": l["maj_at"], "maj_par": l["maj_par"]}
    env = _depuis_env(nom)
    return {"nom": nom, "configuree": bool(env), "source": ".env" if env else None,
            "fin": env[-4:] if env else None, "maj_at": None, "maj_par": None}
