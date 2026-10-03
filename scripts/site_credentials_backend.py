#!/usr/bin/env python3
"""
site_credentials_backend.py — Stockage chiffré AES (Fernet) des clés API par site.

Source de vérité : data/god_mode.duckdb table `site_credentials`.
Clé maître : env var `SITE_CREDENTIALS_MASTER_KEY` (Fernet base64). Si absente, génère
et persiste dans `data/.master_key` (chmod 600). En prod, mettre cette key dans systemd env.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import duckdb
from cryptography.fernet import Fernet, InvalidToken

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "data" / "god_mode.duckdb"
MASTER_KEY_FILE = BASE_DIR / "data" / ".master_key"


def _ensure_master_key() -> bytes:
    """Récupère la clé maître Fernet, ou la génère et la persiste si absente."""
    # 1. env var prioritaire
    env_key = os.environ.get("SITE_CREDENTIALS_MASTER_KEY")
    if env_key:
        return env_key.encode() if isinstance(env_key, str) else env_key

    # 2. fichier .master_key
    if MASTER_KEY_FILE.exists():
        return MASTER_KEY_FILE.read_bytes().strip()

    # 3. génère + persiste
    key = Fernet.generate_key()
    MASTER_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MASTER_KEY_FILE.write_bytes(key)
    try:
        MASTER_KEY_FILE.chmod(0o600)
    except Exception:
        pass
    print(f"[site_credentials] generated new master key at {MASTER_KEY_FILE} (chmod 600)")
    return key


def _fernet() -> Fernet:
    return Fernet(_ensure_master_key())


def encrypt_value(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> Optional[str]:
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return None


def set_credential(site_code: str, key_name: str, plain_value: str) -> bool:
    """INSERT or REPLACE dans site_credentials avec encrypted_value chiffré."""
    if not plain_value:
        return False
    encrypted = encrypt_value(plain_value)
    c = duckdb.connect(str(DB_PATH))
    try:
        c.execute("""
            INSERT OR REPLACE INTO site_credentials
            (site_code, key_name, encrypted_value, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, [site_code, key_name, encrypted])
    finally:
        c.close()
    return True


def get_credential(site_code: str, key_name: str) -> Optional[str]:
    """SELECT + decrypt. Retourne le plaintext ou None."""
    c = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        row = c.execute(
            "SELECT encrypted_value FROM site_credentials WHERE site_code = ? AND key_name = ?",
            [site_code, key_name]
        ).fetchone()
    finally:
        c.close()
    if not row or not row[0]:
        return None
    # Backward compat : valeurs anciennes (clair) — détecter par préfixe Fernet
    val = row[0]
    if not val.startswith("gAAAAA"):
        # legacy plaintext — re-chiffrer
        try:
            set_credential(site_code, key_name, val)
            return val
        except Exception:
            return val
    return decrypt_value(val)


def list_credentials(site_code: str) -> dict:
    """Retourne les noms de clés (sans les valeurs) pour un site."""
    c = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = c.execute(
            "SELECT key_name, updated_at FROM site_credentials WHERE site_code = ?",
            [site_code]
        ).fetchall()
    finally:
        c.close()
    return {kn: str(ts) for kn, ts in rows}


def delete_credential(site_code: str, key_name: str) -> bool:
    c = duckdb.connect(str(DB_PATH))
    try:
        c.execute(
            "DELETE FROM site_credentials WHERE site_code = ? AND key_name = ?",
            [site_code, key_name]
        )
    finally:
        c.close()
    return True


def migrate_plaintext_to_encrypted() -> dict:
    """One-shot : re-chiffre toutes les valeurs en clair de site_credentials."""
    c = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = c.execute(
            "SELECT site_code, key_name, encrypted_value FROM site_credentials"
        ).fetchall()
    finally:
        c.close()

    migrated = 0
    already_encrypted = 0
    for site_code, key_name, value in rows:
        if not value:
            continue
        if value.startswith("gAAAAA"):
            already_encrypted += 1
            continue
        set_credential(site_code, key_name, value)
        migrated += 1
    return {"migrated": migrated, "already_encrypted": already_encrypted}


if __name__ == "__main__":
    # CLI helper
    import sys
    if len(sys.argv) < 2:
        print("Usage: site_credentials_backend.py {migrate|set|get|list} ...")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "migrate":
        print(migrate_plaintext_to_encrypted())
    elif cmd == "set":
        site, key, val = sys.argv[2], sys.argv[3], sys.argv[4]
        print({"ok": set_credential(site, key, val)})
    elif cmd == "get":
        site, key = sys.argv[2], sys.argv[3]
        v = get_credential(site, key)
        print({"value": "***" if v else None})
    elif cmd == "list":
        print(list_credentials(sys.argv[2]))
