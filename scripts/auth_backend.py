"""
auth_backend.py — User/role system avec session tokens.

Sécurité v2 (2026-05-20) :
  - Hash bcrypt (migration douce depuis SHA-256 à chaque login réussi)
  - MFA TOTP optionnel (pyotp)
  - Log des échecs de login → /var/log/genesis-auth.log (lu par fail2ban)
  - Rate limit IP : 5 essais / 10 min, sinon login refusé
  - TTL session : 7 jours
  - Plus de compte admin par défaut (init_default_users no-op)

Stocké dans DuckDB (data/auth.duckdb).
"""

import duckdb
import uuid
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import bcrypt
except ImportError:  # pragma: no cover
    bcrypt = None  # type: ignore

try:
    import pyotp
except ImportError:  # pragma: no cover
    pyotp = None  # type: ignore

AUTH_DB = Path("/home/autoblog/genesis/data/auth.duckdb")
AUTH_DB.parent.mkdir(parents=True, exist_ok=True)

AUTH_LOG = Path("/var/log/genesis-auth.log")
SESSION_TTL = timedelta(days=7)

# Rate limit en mémoire (par process). Suffisant pour mono-uvicorn.
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
RATE_LIMIT_WINDOW_S = 600   # 10 min
RATE_LIMIT_MAX = 5          # 5 essais


# ── DB ────────────────────────────────────────────────────────────────────────

_SCHEMA_READY = False


def _ensure_schema() -> None:
    """Crée les tables et ajoute les colonnes MFA. Exécuté UNE fois au démarrage."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    conn = duckdb.connect(str(AUTH_DB))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR PRIMARY KEY,
                username VARCHAR UNIQUE,
                password_hash VARCHAR,
                role VARCHAR DEFAULT 'viewer',
                nom VARCHAR,
                prenom VARCHAR,
                email VARCHAR,
                phone VARCHAR DEFAULT '',
                sites VARCHAR DEFAULT '[]',
                totp_secret VARCHAR DEFAULT '',
                totp_enabled BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token VARCHAR PRIMARY KEY,
                user_id VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        """)
        # Migrations MFA — chacune dans son sous-bloc try (DuckDB plante toute la transaction sur erreur)
        existing_cols = {r[0] for r in conn.execute("DESCRIBE users").fetchall()}
        if "totp_secret" not in existing_cols:
            conn.execute("ALTER TABLE users ADD COLUMN totp_secret VARCHAR DEFAULT ''")
        if "totp_enabled" not in existing_cols:
            conn.execute("ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN DEFAULT FALSE")
        if "disabled" not in existing_cols:
            conn.execute("ALTER TABLE users ADD COLUMN disabled BOOLEAN DEFAULT FALSE")
    finally:
        conn.close()
    _SCHEMA_READY = True


def get_db():
    _ensure_schema()
    return duckdb.connect(str(AUTH_DB))


# ── Hashing : bcrypt avec migration douce depuis SHA-256 ──────────────────────

def hash_password(password: str) -> str:
    """Renvoie un hash bcrypt (préfixe $2b$)."""
    if bcrypt is None:
        # Fallback uniquement si bcrypt indispo (ne devrait jamais arriver en prod)
        return "sha256$" + hashlib.sha256(password.encode()).hexdigest()
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, stored_hash: str) -> bool:
    """Vérifie un mdp contre un hash. Accepte bcrypt ET SHA-256 hex (legacy)."""
    if not stored_hash:
        return False
    if stored_hash.startswith("$2") and bcrypt is not None:
        try:
            return bcrypt.checkpw(password.encode(), stored_hash.encode())
        except Exception:
            return False
    if stored_hash.startswith("sha256$"):
        return hmac.compare_digest(stored_hash, "sha256$" + hashlib.sha256(password.encode()).hexdigest())
    # Legacy : SHA-256 brut (64 chars hex)
    if len(stored_hash) == 64:
        return hmac.compare_digest(stored_hash, hashlib.sha256(password.encode()).hexdigest())
    return False


def _is_legacy_hash(stored_hash: str) -> bool:
    """True si le hash est en SHA-256 brut (à migrer vers bcrypt)."""
    return len(stored_hash) == 64 and not stored_hash.startswith("$2") and not stored_hash.startswith("sha256$")


# ── Logging des échecs vers /var/log/genesis-auth.log (pour fail2ban) ─────────

def _audit_log(event: str, ip: str = "", username: str = "", extra: str = "") -> None:
    """Ligne au format parsable par fail2ban : `2026-05-20T...Z EVENT ip=... user=... ...`."""
    try:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = f"{ts} {event} ip={ip or '-'} user={username or '-'}"
        if extra:
            line += " " + extra
        with open(AUTH_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        # Si le log n'est pas writable, on ne casse pas l'auth
        pass


# ── Rate limit IP ─────────────────────────────────────────────────────────────

def _is_rate_limited(ip: str) -> bool:
    if not ip:
        return False
    now = time.time()
    bucket = _LOGIN_ATTEMPTS.setdefault(ip, [])
    # Purge ancien
    cutoff = now - RATE_LIMIT_WINDOW_S
    bucket[:] = [t for t in bucket if t > cutoff]
    return len(bucket) >= RATE_LIMIT_MAX


def _record_attempt(ip: str) -> None:
    if not ip:
        return
    _LOGIN_ATTEMPTS.setdefault(ip, []).append(time.time())


# ── CRUD users ────────────────────────────────────────────────────────────────

def create_user(username, password, role="viewer", nom="", prenom="", email="", phone="", sites="[]"):
    conn = get_db()
    user_id = str(uuid.uuid4())[:8]
    try:
        conn.execute("""
            INSERT INTO users (id, username, password_hash, role, nom, prenom, email, phone, sites)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [user_id, username, hash_password(password), role, nom, prenom, email, phone, sites])
        conn.close()
        return user_id
    except Exception:
        conn.close()
        return None


def list_users():
    conn = get_db()
    result = conn.execute(
        "SELECT id, username, role, nom, prenom, email, created_at, phone, sites, totp_enabled, "
        "COALESCE(disabled, FALSE) "
        "FROM users ORDER BY created_at"
    ).fetchall()
    conn.close()
    import json as _json
    return [
        {
            "id": r[0], "username": r[1], "role": r[2], "nom": r[3], "prenom": r[4],
            "email": r[5], "created_at": str(r[6]), "phone": r[7] or "",
            "sites": _json.loads(r[8]) if r[8] else [],
            "mfa_enabled": bool(r[9]),
            "disabled": bool(r[10]),
        }
        for r in result
    ]


def delete_user(user_id):
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE user_id = ?", [user_id])
    conn.execute("DELETE FROM users WHERE id = ?", [user_id])
    conn.close()


def update_user(user_id, data):
    conn = get_db()
    fields, values = [], []
    for k in ["role", "nom", "prenom", "email", "phone", "sites", "disabled"]:
        if k in data:
            fields.append(f"{k} = ?")
            values.append(data[k])
    if data.get("password"):
        fields.append("password_hash = ?")
        values.append(hash_password(data["password"]))
    if fields:
        values.append(user_id)
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
    conn.close()


# ── Login / MFA ───────────────────────────────────────────────────────────────

def login(username, password, totp_code: str = "", ip: str = ""):
    """
    Renvoie un dict si OK, ou un dict {"error": ...} sinon.
    Si MFA est activé et totp_code manquant/invalide : renvoie {"mfa_required": True}.
    """
    if _is_rate_limited(ip):
        _audit_log("AUTH_RATELIMIT", ip=ip, username=username)
        return {"error": "rate_limit", "retry_after_s": RATE_LIMIT_WINDOW_S}

    conn = get_db()
    row = conn.execute(
        "SELECT id, password_hash, role, nom, prenom, totp_secret, totp_enabled, sites, COALESCE(disabled, FALSE) "
        "FROM users WHERE username = ?",
        [username],
    ).fetchone()
    if not row:
        conn.close()
        _record_attempt(ip)
        _audit_log("AUTH_FAIL", ip=ip, username=username, extra="reason=unknown_user")
        return {"error": "invalid_credentials"}

    user_id, stored_hash, role, nom, prenom, totp_secret, totp_enabled, sites, disabled = row

    if not verify_password(password, stored_hash):
        conn.close()
        _record_attempt(ip)
        _audit_log("AUTH_FAIL", ip=ip, username=username, extra="reason=bad_password")
        return {"error": "invalid_credentials"}

    if disabled:
        conn.close()
        _audit_log("AUTH_FAIL", ip=ip, username=username, extra="reason=account_disabled")
        return {"error": "account_disabled"}

    # Migration douce SHA-256 → bcrypt
    if _is_legacy_hash(stored_hash) and bcrypt is not None:
        try:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                         [hash_password(password), user_id])
        except Exception:
            pass

    # Vérification MFA si activée
    if totp_enabled:
        if not totp_code:
            conn.close()
            return {"mfa_required": True, "user_id": user_id}
        if pyotp is None or not totp_secret:
            conn.close()
            _audit_log("AUTH_FAIL", ip=ip, username=username, extra="reason=mfa_misconfigured")
            return {"error": "mfa_misconfigured"}
        if not pyotp.TOTP(totp_secret).verify(totp_code, valid_window=1):
            conn.close()
            _record_attempt(ip)
            _audit_log("AUTH_FAIL", ip=ip, username=username, extra="reason=bad_totp")
            return {"error": "invalid_totp"}

    # Succès : nouvelle session
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + SESSION_TTL
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        [token, user_id, datetime.now(timezone.utc).isoformat(), expires.isoformat()],
    )
    # Nettoyage des sessions expirées
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", [datetime.now(timezone.utc).isoformat()])
    conn.close()

    _audit_log("AUTH_OK", ip=ip, username=username)

    import json as _json
    sites_list = _json.loads(sites) if sites else []
    return {
        "token": token, "user_id": user_id, "role": role,
        "nom": nom, "prenom": prenom, "username": username,
        "sites": sites_list, "mfa_enabled": bool(totp_enabled),
    }


def verify_session(token):
    if not token:
        return None
    conn = get_db()
    result = conn.execute("""
        SELECT s.user_id, u.username, u.role, u.nom, u.prenom, u.phone, u.sites, u.totp_enabled
        FROM sessions s JOIN users u ON s.user_id = u.id
        WHERE s.token = ? AND s.expires_at > ?
    """, [token, datetime.now(timezone.utc).isoformat()]).fetchone()
    conn.close()
    if not result:
        return None
    import json as _json
    sites_list = _json.loads(result[6]) if result[6] else []
    return {
        "user_id": result[0], "username": result[1], "role": result[2],
        "nom": result[3], "prenom": result[4], "phone": result[5] or "",
        "sites": sites_list, "mfa_enabled": bool(result[7]),
    }


def logout(token):
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE token = ?", [token])
    conn.close()


def count_online_users() -> int:
    """Nombre d'utilisateurs distincts ayant une session non expirée (≈ connectés)."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT count(DISTINCT user_id) FROM sessions WHERE expires_at > ?",
            [datetime.now(timezone.utc).isoformat()],
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def reset_password(user_id):
    """Génère un nouveau mdp aléatoire (16 chars) et le retourne en clair une fois."""
    new_pass = secrets.token_urlsafe(12)
    conn = get_db()
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", [hash_password(new_pass), user_id])
    conn.execute("DELETE FROM sessions WHERE user_id = ?", [user_id])  # Force re-login
    conn.close()
    return new_pass


def send_password_telegram(phone, username, password):
    import os, requests
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token or not phone:
        return False
    msg = f"Votre acces Genesis :\nIdentifiant: {username}\nMot de passe: {password}\nURL: https://api.cheffer.email"
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": phone, "text": msg}, timeout=10,
        )
        return True
    except Exception:
        return False


# ── MFA TOTP ──────────────────────────────────────────────────────────────────

def mfa_setup_start(user_id: str) -> dict:
    """Génère un secret TOTP (non encore activé), retourne URI + QR code PNG base64."""
    if pyotp is None:
        return {"error": "pyotp not installed"}
    conn = get_db()
    row = conn.execute("SELECT username FROM users WHERE id = ?", [user_id]).fetchone()
    if not row:
        conn.close()
        return {"error": "user not found"}
    username = row[0]
    secret = pyotp.random_base32()
    conn.execute("UPDATE users SET totp_secret = ?, totp_enabled = FALSE WHERE id = ?", [secret, user_id])
    conn.close()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="Genesis")

    # Génère le QR code en PNG base64 pour affichage direct dans une <img src="data:image/png;base64,...">
    qr_b64 = ""
    try:
        import qrcode, io, base64
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        pass

    return {"secret": secret, "uri": uri, "qr_png_base64": qr_b64}


def mfa_setup_confirm(user_id: str, totp_code: str) -> dict:
    """Active le MFA après vérification d'un code valide."""
    if pyotp is None:
        return {"error": "pyotp not installed"}
    conn = get_db()
    row = conn.execute("SELECT totp_secret FROM users WHERE id = ?", [user_id]).fetchone()
    if not row or not row[0]:
        conn.close()
        return {"error": "no pending secret"}
    secret = row[0]
    if not pyotp.TOTP(secret).verify(totp_code, valid_window=1):
        conn.close()
        return {"error": "invalid_totp"}
    conn.execute("UPDATE users SET totp_enabled = TRUE WHERE id = ?", [user_id])
    conn.close()
    return {"ok": True}


def mfa_disable(user_id: str) -> dict:
    conn = get_db()
    conn.execute("UPDATE users SET totp_secret = '', totp_enabled = FALSE WHERE id = ?", [user_id])
    conn.close()
    return {"ok": True}


# ── Logs / historique ─────────────────────────────────────────────────────────

def log_login(user_id, username, ip="", user_agent=""):
    """Conservé pour compat — réussites uniquement (déjà loggué via _audit_log côté login())."""
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO login_logs (id, user_id, username, ip, user_agent) "
            "VALUES (nextval('login_logs_seq'), ?, ?, ?, ?)",
            [user_id, username, ip, user_agent],
        )
    except Exception:
        import random
        try:
            conn.execute(
                "INSERT INTO login_logs (id, user_id, username, ip, user_agent) VALUES (?, ?, ?, ?, ?)",
                [random.randint(100000, 999999), user_id, username, ip, user_agent],
            )
        except Exception:
            pass
    conn.close()


def get_login_logs(limit=50):
    conn = get_db()
    try:
        result = conn.execute(
            "SELECT username, ip, user_agent, created_at FROM login_logs "
            "ORDER BY created_at DESC LIMIT ?",
            [limit],
        ).fetchall()
        conn.close()
        return [{"username": r[0], "ip": r[1], "user_agent": r[2], "date": str(r[3])} for r in result]
    except Exception:
        conn.close()
        return []


# ── No-op default init (ancien comportement supprimé pour des raisons de sécurité) ─

def init_default_users():
    """No-op. Avant : créait un compte admin/genesis2026 — backdoor permanente.
    On laisse l'admin créer les users via la UI."""
    return
