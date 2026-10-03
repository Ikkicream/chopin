#!/usr/bin/env python3
"""mass_mailing/infra/auth.py — comptes et sessions de Mass Email, dans PostgreSQL.

Mass Email est sorti de Cheffer le 2026-09-26 (Camille : « le nouveau projet n'a rien à
faire sur DuckDB »). Il a donc ses propres comptes : plus aucune lecture de
`data/auth.duckdb`.

- Mot de passe : bcrypt.
- Double authentification obligatoire : TOTP (RFC 6238, 30 s, 6 chiffres), écrit ici avec
  la bibliothèque standard — une application comme Google Authenticator le lit.
- Activation : un lien à usage unique (48 h) pour choisir son mot de passe et enregistrer
  la double authentification. Aucun mot de passe ne transite en clair.
- Sessions : jeton aléatoire opaque, 7 jours, révocable.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

import bcrypt

from . import pg

DUREE_SESSION_JOURS = 7
DUREE_ACTIVATION_H = 48
EMETTEUR_TOTP = "Mass Email"


def appliquer_schema() -> None:
    pg.ecrire("""
        CREATE TABLE IF NOT EXISTS utilisateurs (
            id               BIGSERIAL PRIMARY KEY,
            identifiant      TEXT        NOT NULL UNIQUE,
            email            TEXT,
            role             TEXT        NOT NULL DEFAULT 'superadmin' CHECK (role IN ('superadmin')),
            mot_de_passe     TEXT,
            totp_secret      TEXT,
            actif            BOOLEAN     NOT NULL DEFAULT false,
            jeton_activation TEXT,
            activation_expire_at TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            derniere_connexion_at TIMESTAMPTZ
        );
        CREATE TABLE IF NOT EXISTS sessions (
            jeton            TEXT        PRIMARY KEY,
            utilisateur_id   BIGINT      NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
            expire_at        TIMESTAMPTZ NOT NULL,
            ip               TEXT,
            user_agent       TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS sessions_expire_idx ON sessions (expire_at);
        -- Clé TOTP proposée à l'activation, GARDÉE tant que le compte n'est pas activé :
        -- recharger la page ne doit pas changer le QR code déjà scanné (vécu le 26/09).
        ALTER TABLE utilisateurs ADD COLUMN IF NOT EXISTS totp_en_attente TEXT;
    """)


# ── TOTP (RFC 6238) ──────────────────────────────────────────────────────────

def nouveau_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, pas: int) -> str:
    cle = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    mac = hmac.new(cle, struct.pack(">Q", pas), hashlib.sha1).digest()
    o = mac[-1] & 0x0F
    return f"{(struct.unpack('>I', mac[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def verifier_totp(secret: str, code: str) -> bool:
    """Tolère ±1 minute (le temps de taper le code, un téléphone un peu en avance)."""
    code = "".join(c for c in (code or "") if c.isdigit())
    if len(code) != 6 or not secret:
        return False
    pas = int(time.time()) // 30
    return any(hmac.compare_digest(_code(secret, pas + d), code) for d in (-2, -1, 0, 1, 2))


def uri_totp(identifiant: str, secret: str) -> str:
    return (f"otpauth://totp/{quote(EMETTEUR_TOTP)}:{quote(identifiant)}"
            f"?secret={secret}&issuer={quote(EMETTEUR_TOTP)}&digits=6&period=30")


# ── Comptes ──────────────────────────────────────────────────────────────────

def creer_invitation(identifiant: str, email: str | None = None) -> str:
    """Crée (ou réinitialise) un compte et rend son jeton d'activation."""
    jeton = secrets.token_urlsafe(32)
    pg.ecrire("""INSERT INTO utilisateurs (identifiant, email, jeton_activation, activation_expire_at, actif)
                 VALUES (%(i)s, %(e)s, %(j)s, now() + make_interval(hours => %(h)s), false)
                 ON CONFLICT (identifiant) DO UPDATE SET jeton_activation = EXCLUDED.jeton_activation,
                      activation_expire_at = EXCLUDED.activation_expire_at, email = COALESCE(EXCLUDED.email, utilisateurs.email)""",
              {"i": identifiant.strip().lower(), "e": email, "j": hashlib.sha256(jeton.encode()).hexdigest(),
               "h": DUREE_ACTIVATION_H})
    return jeton


def lire_invitation(jeton: str) -> dict | None:
    """L'invitation, avec sa clé TOTP en attente (créée au premier affichage, puis stable)."""
    j = hashlib.sha256((jeton or "").encode()).hexdigest()
    u = pg.ligne("""SELECT id, identifiant, totp_en_attente FROM utilisateurs
                     WHERE jeton_activation = %(j)s AND activation_expire_at > now()""", {"j": j})
    if u and not u["totp_en_attente"]:
        pg.ecrire("UPDATE utilisateurs SET totp_en_attente = %(s)s WHERE id = %(i)s AND totp_en_attente IS NULL",
                  {"s": nouveau_secret(), "i": u["id"]})
        u = pg.ligne("SELECT id, identifiant, totp_en_attente FROM utilisateurs WHERE id = %(i)s", {"i": u["id"]})
    return u


def activer(jeton: str, mot_de_passe: str, code: str) -> tuple[dict | None, str]:
    """Fixe le mot de passe et la double authentification. Rend (compte, "") ou (None, motif)."""
    u = lire_invitation(jeton)
    if not u:
        return None, "Ce lien d'activation n'est plus valable (expiré ou déjà utilisé). Demandez-en un nouveau."
    if len(mot_de_passe or "") < 12:
        return None, "Le mot de passe doit faire au moins 12 caractères."
    if not verifier_totp(u["totp_en_attente"], code):
        return None, ("Code à 6 chiffres incorrect. Vérifiez que l'application affiche bien le compte "
                      "« Mass Email: camille » scanné sur CETTE page, et saisissez le code en cours.")
    secret = u["totp_en_attente"]
    pg.ecrire("""UPDATE utilisateurs SET mot_de_passe = %(p)s, totp_secret = %(s)s, actif = true,
                        jeton_activation = NULL, activation_expire_at = NULL, totp_en_attente = NULL
                  WHERE id = %(i)s""",
              {"p": bcrypt.hashpw(mot_de_passe.encode(), bcrypt.gensalt()).decode(), "s": secret, "i": u["id"]})
    pg.ecrire("DELETE FROM sessions WHERE utilisateur_id = %(i)s", {"i": u["id"]})
    return u, ""


def verifier_identifiants(identifiant: str, mot_de_passe: str) -> dict | None:
    u = pg.ligne("SELECT * FROM utilisateurs WHERE identifiant = %(i)s AND actif",
                 {"i": (identifiant or "").strip().lower()})
    # Toujours un bcrypt, même sans compte : le temps de réponse ne trahit pas l'existence.
    empreinte = (u or {}).get("mot_de_passe") or "$2b$12$" + "." * 53
    try:
        ok = bcrypt.checkpw((mot_de_passe or "").encode(), empreinte.encode())
    except ValueError:
        ok = False
    return u if (u and ok) else None


# ── Sessions ─────────────────────────────────────────────────────────────────

def ouvrir_session(utilisateur_id: int, ip: str = "", user_agent: str = "") -> str:
    jeton = "mm_" + secrets.token_urlsafe(40)
    pg.ecrire("""INSERT INTO sessions (jeton, utilisateur_id, expire_at, ip, user_agent)
                 VALUES (%(j)s, %(u)s, now() + make_interval(days => %(d)s), %(ip)s, %(ua)s)""",
              {"j": hashlib.sha256(jeton.encode()).hexdigest(), "u": utilisateur_id, "d": DUREE_SESSION_JOURS,
               "ip": ip[:64], "ua": user_agent[:300]})
    pg.ecrire("UPDATE utilisateurs SET derniere_connexion_at = now() WHERE id = %(u)s", {"u": utilisateur_id})
    pg.ecrire("DELETE FROM sessions WHERE expire_at < now()")
    return jeton


def session(jeton: str) -> dict | None:
    if not jeton or not jeton.startswith("mm_"):
        return None
    return pg.ligne("""SELECT u.id, u.identifiant, u.email, u.role FROM sessions s
                         JOIN utilisateurs u ON u.id = s.utilisateur_id
                        WHERE s.jeton = %(j)s AND s.expire_at > now() AND u.actif""",
                    {"j": hashlib.sha256(jeton.encode()).hexdigest()})


def fermer_session(jeton: str) -> None:
    pg.ecrire("DELETE FROM sessions WHERE jeton = %(j)s", {"j": hashlib.sha256((jeton or "").encode()).hexdigest()})
