"""phone_enrich_backend.py — enrichit le téléphone d'un cliqueur (waterfall Basile → Emelia).

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
    for _ in range(tries):
        try:
            return duckdb.connect(str(p), read_only=read_only)
        except Exception as e:  # noqa: BLE001
            if "lock" in str(e).lower():
                time.sleep(2); continue
            raise
    raise RuntimeError(f"verrou persistant sur {p}")


def _pool_contact(email: str) -> dict | None:
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


def _basile_person(prenom: str, nom: str, societe: str) -> dict:
    """Best-effort Basile /people/find → {phone, linkedin}."""
    try:
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        import basile_backend as bb
        filters: dict = {}
        if prenom:
            filters["result_first_name"] = {"include": [prenom]}
        if nom:
            filters["result_last_name"] = {"include": [nom]}
        if societe:
            filters["employer"] = {"include": [societe]}
        if not filters:
            return {}
        res = bb.find("people", filters, limit=5)
        for lead in (res.get("leads") or []):
            d = lead.get("data") or {}
            linkedin = bb._first(d, "profile_url", "linkedin_url", "current_company_profile_url")
            phone = bb._first(d, "phone", "phone_number", "tel")
            if linkedin or phone:
                return {"phone": phone or "", "linkedin": linkedin or ""}
        return {}
    except Exception as e:  # noqa: BLE001
        _log(f"basile err: {e}")
        return {}


def _emelia_phone(linkedin: str) -> str:
    try:
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        import basile_backend as bb
        res = bb.emelia_find_phone(linkedin)
        return ((res or {}).get("value") or "").strip()
    except Exception as e:  # noqa: BLE001
        _log(f"emelia err: {e}")
        return ""


def enrich_phone(site: str, email: str) -> dict:
    """Waterfall Basile → Emelia pour trouver le tél d'un cliqueur. Idempotent (dédup)."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "reason": "no_email"}

    contact = _pool_contact(email)
    if not contact:
        _record_attempt(email, False, "", "no_contact")
        return {"ok": False, "reason": "contact_absent_du_pool"}
    if contact["tel"]:
        return {"ok": True, "phone": contact["tel"], "source": "existing", "skipped": True}

    prev = _already_attempted(email)
    if prev is not None:
        return {"ok": True, "phone": prev[1], "found": bool(prev[0]),
                "source": "cached_attempt", "skipped": True}

    prenom, nom, societe = contact["prenom"], contact["nom"], contact["societe"]
    if not (nom and societe):
        _record_attempt(email, False, "", "insufficient_info")
        return {"ok": False, "reason": "infos_insuffisantes (nom+société requis)"}

    b = _basile_person(prenom, nom, societe)
    phone = (b.get("phone") or "").strip()
    source = "basile"
    if not phone and b.get("linkedin"):
        phone = _emelia_phone(b["linkedin"])
        source = "emelia"

    found = bool(phone)
    _record_attempt(email, found, phone, source if found else "none")
    if found:
        _write_tel(site, email, phone)
        _log(f"{email} -> {phone} (via {source})")
    else:
        _log(f"{email} -> aucun numéro (basile linkedin={bool(b.get('linkedin'))})")
    return {"ok": True, "found": found, "phone": phone, "source": source if found else None}


if __name__ == "__main__":
    # usage: python3 phone_enrich_backend.py <site> <email>
    if len(sys.argv) >= 3:
        import json
        print(json.dumps(enrich_phone(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=2))
    else:
        print("usage: python3 phone_enrich_backend.py <site> <email>")
