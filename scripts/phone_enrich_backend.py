"""phone_enrich_backend.py — HORS SERVICE depuis le 13/10 (Basile retiré) ; voir enrich_phone.

Ancien fonctionnement (waterfall Basile → Emelia) :

Déclenché quand un contact passe `prm` via un clic Sweego (cf. /api/sweego/webhook).
Best-effort, asynchrone (lancé en thread détaché par le récepteur webhook) :
  1. Basile /people/find (prénom+nom+employeur) → URL LinkedIn (source LKI) + tél direct si présent.
  2. Si pas de tél mais un LinkedIn trouvé → Emelia find_phone(linkedinUrl) (50 crédits si trouvé).
  3. Écrit le numéro dans `tel` (pool contacts.duckdb + acquisition data/crm/<site>.duckdb).
Dédup via table `phone_enrich_attempts` (god_mode.duckdb) : on ne re-dépense pas pour un email
déjà tenté (trouvé OU non).
"""
from __future__ import annotations
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
POOL_DB = BASE_DIR / "data" / "contacts.duckdb"
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    print(f"[phone_enrich] {msg}", flush=True)


def _connect(p: Path, read_only: bool = False, tries: int = 12):
    import duck_pg as _dpg   # lot 3 (08/10)
    if _dpg._est_god(p) and _dpg.actif():
        return _dpg.ConnexionDuckPG()
    for _ in range(tries):
        try:
            return duckdb.connect(str(p), read_only=read_only)
        except Exception as e:  # noqa: BLE001
            if "lock" in str(e).lower():
                time.sleep(2); continue
            raise
    raise RuntimeError(f"verrou persistant sur {p}")


def _pool_pg() -> bool:
    try:
        import pool_ecriture_pg
        return pool_ecriture_pg.actif()
    except Exception:  # noqa: BLE001
        return False


def _pool_contact(email: str) -> dict | None:
    if _pool_pg():   # lot 2 (07/10)
        import pool_pg
        r = pool_pg._q("SELECT prenom, nom, societe, website, tel FROM contacts "
                       "WHERE email = %(e)s LIMIT 1", {"e": (email or "").strip().lower()})
        r = r[0] if r else None
        return None if not r else {"prenom": r[0] or "", "nom": r[1] or "",
                                   "societe": r[2] or "", "website": r[3] or "",
                                   "tel": r[4] or ""}
    c = _connect(POOL_DB, read_only=True)
    try:
        r = c.execute("SELECT prenom, nom, societe, website, tel FROM contacts WHERE email=? LIMIT 1",
                      [email]).fetchone()
    finally:
        c.close()
    if not r:
        return None
    return {"prenom": r[0] or "", "nom": r[1] or "", "societe": r[2] or "",
            "website": r[3] or "", "tel": r[4] or ""}


def _ensure_table(c) -> None:
    c.execute("""CREATE TABLE IF NOT EXISTS phone_enrich_attempts (
        email VARCHAR PRIMARY KEY, attempted_at TIMESTAMP, found BOOLEAN,
        phone VARCHAR, source VARCHAR)""")


def _already_attempted(email: str):
    c = _connect(GOD_DB, read_only=False)
    try:
        _ensure_table(c)
        return c.execute("SELECT found, phone FROM phone_enrich_attempts WHERE email=?",
                         [email]).fetchone()
    finally:
        c.close()


def _record_attempt(email: str, found: bool, phone: str, source: str) -> None:
    c = _connect(GOD_DB, read_only=False)
    try:
        _ensure_table(c)
        c.execute("INSERT OR REPLACE INTO phone_enrich_attempts VALUES (?,?,?,?,?)",
                  [email, datetime.now(timezone.utc), bool(found), phone or "", source or ""])
    finally:
        c.close()


def _write_tel(site: str, email: str, phone: str) -> None:
    if _pool_pg():   # lot 2 (07/10)
        import pool_pg
        pool_pg._ecrire("UPDATE contacts SET tel = %(t)s, updated_at = now() WHERE email = %(e)s "
                        "AND (tel IS NULL OR tel = '')",
                        {"t": phone, "e": (email or "").strip().lower()})
    else:
        c = _connect(POOL_DB, read_only=False)
        try:
            c.execute("UPDATE contacts SET tel=?, updated_at=? WHERE email=? AND (tel IS NULL OR tel='')",
                      [phone, _now(), email])
        finally:
            c.close()
    crm = BASE_DIR / "data" / "crm" / f"{site}.duckdb"
    if crm.exists():
        c = _connect(crm, read_only=False)
        try:
            c.execute("UPDATE acquisition_contacts SET tel=?, updated_at=? "
                      "WHERE email=? AND (tel IS NULL OR tel='')", [phone, _now(), email])
        finally:
            c.close()


def enrich_phone(site: str, email: str) -> dict:
    """Trouvait le tél d'un cliqueur (Basile → Emelia). HORS SERVICE depuis le 13/10 :
    Basile est retiré et Emelia ne cherche un numéro qu'à partir d'un LinkedIn que Basile
    fournissait. On ne note AUCUNE tentative, pour pouvoir rejouer ces cliqueurs le jour
    où un autre fournisseur sera branché."""
    return {"ok": False, "reason": "enrichissement_telephone_desactive"}


if __name__ == "__main__":
    # usage: python3 phone_enrich_backend.py <site> <email>
    if len(sys.argv) >= 3:
        import json
        print(json.dumps(enrich_phone(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=2))
    else:
        print("usage: python3 phone_enrich_backend.py <site> <email>")
