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


# Comptes, sessions et clients sont des tables de PLATEFORME : toujours dans `mass_mailing`,
# quel que soit le client dont la requête porte le schéma (SaaS, 13/10/2026).
def _ecrire(sql, params=None):
    with pg.espace(pg.SCHEMA):
        return pg.ecrire(sql, params)


def _ligne(sql, params=None):
    with pg.espace(pg.SCHEMA):
        return pg.ligne(sql, params)


def appliquer_schema() -> None:
    _ecrire("""
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

        -- SaaS (13/10/2026) : les clients de la plateforme, chacun dans son schéma.
        CREATE TABLE IF NOT EXISTS clients (
            id           BIGSERIAL PRIMARY KEY,
            slug         TEXT        NOT NULL UNIQUE CHECK (slug ~ '^[a-z][a-z0-9_]{1,40}$'),
            nom          TEXT        NOT NULL,
            schema_pg    TEXT        NOT NULL UNIQUE,
            statut       TEXT        NOT NULL DEFAULT 'actif' CHECK (statut IN ('actif','suspendu')),
            -- Un client n'envoie QUE par Resend ou SES (décision du 13/10) : jamais Sweego.
            fournisseur  TEXT        NOT NULL DEFAULT 'resend' CHECK (fournisseur IN ('resend','ses')),
            reply_to     TEXT,
            raison_sociale TEXT,
            adresse_postale TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        ALTER TABLE utilisateurs ADD COLUMN IF NOT EXISTS client_id BIGINT REFERENCES clients(id) ON DELETE CASCADE;
        -- Prénom (13/10) : la phrase de l'accueil s'adresse à la personne (« Camille, votre compte… »).
        ALTER TABLE utilisateurs ADD COLUMN IF NOT EXISTS prenom TEXT;
        ALTER TABLE utilisateurs DROP CONSTRAINT IF EXISTS utilisateurs_role_check;
        ALTER TABLE utilisateurs ADD CONSTRAINT utilisateurs_role_check CHECK (
            (role = 'superadmin' AND client_id IS NULL) OR (role = 'client' AND client_id IS NOT NULL));
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

def creer_invitation(identifiant: str, email: str | None = None, client_id: int | None = None,
                     prenom: str | None = None) -> str:
    """Crée (ou réinitialise) un compte et rend son jeton d'activation. `client_id` → compte client."""
    jeton = secrets.token_urlsafe(32)
    _ecrire("""INSERT INTO utilisateurs (identifiant, email, jeton_activation, activation_expire_at, actif,
                                       role, client_id)
                 VALUES (%(i)s, %(e)s, %(j)s, now() + make_interval(hours => %(h)s), false,
                         %(r)s, %(c)s)
                 ON CONFLICT (identifiant) DO UPDATE SET jeton_activation = EXCLUDED.jeton_activation,
                      activation_expire_at = EXCLUDED.activation_expire_at, email = COALESCE(EXCLUDED.email, utilisateurs.email)""",
              {"i": identifiant.strip().lower(), "e": email, "j": hashlib.sha256(jeton.encode()).hexdigest(),
               "h": DUREE_ACTIVATION_H, "r": "client" if client_id else "superadmin", "c": client_id})
    if prenom and prenom.strip():
        _ecrire("UPDATE utilisateurs SET prenom = %(p)s WHERE identifiant = %(i)s",
                {"p": prenom.strip()[:60], "i": identifiant.strip().lower()})
    return jeton


def transferer_compte(utilisateur_id: int, identifiant: str, email: str | None, prenom: str | None) -> str:
    """Remet un compte à quelqu'un d'autre (recette faite avec l'adresse de Camille, puis
    remise au client, 13/10/2026) : nouvel identifiant/email/prénom, mot de passe et double
    authentification EFFACÉS, sessions fermées, nouveau lien d'activation (rendu)."""
    jeton = secrets.token_urlsafe(32)
    _ecrire("""UPDATE utilisateurs SET identifiant = %(i)s, email = %(e)s, prenom = %(p)s,
                      mot_de_passe = NULL, totp_secret = NULL, totp_en_attente = NULL, actif = false,
                      jeton_activation = %(j)s, activation_expire_at = now() + make_interval(hours => %(h)s)
                WHERE id = %(u)s""",
            {"i": identifiant.strip().lower(), "e": email or None, "p": (prenom or "").strip()[:60] or None,
             "j": hashlib.sha256(jeton.encode()).hexdigest(), "h": DUREE_ACTIVATION_H, "u": utilisateur_id})
    _ecrire("DELETE FROM sessions WHERE utilisateur_id = %(u)s", {"u": utilisateur_id})
    return jeton


def lire_invitation(jeton: str) -> dict | None:
    """L'invitation, avec sa clé TOTP en attente (créée au premier affichage, puis stable)."""
    j = hashlib.sha256((jeton or "").encode()).hexdigest()
    u = _ligne("""SELECT id, identifiant, totp_en_attente FROM utilisateurs
                     WHERE jeton_activation = %(j)s AND activation_expire_at > now()""", {"j": j})
    if u and not u["totp_en_attente"]:
        _ecrire("UPDATE utilisateurs SET totp_en_attente = %(s)s WHERE id = %(i)s AND totp_en_attente IS NULL",
                  {"s": nouveau_secret(), "i": u["id"]})
        u = _ligne("SELECT id, identifiant, totp_en_attente FROM utilisateurs WHERE id = %(i)s", {"i": u["id"]})
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
    _ecrire("""UPDATE utilisateurs SET mot_de_passe = %(p)s, totp_secret = %(s)s, actif = true,
                        jeton_activation = NULL, activation_expire_at = NULL, totp_en_attente = NULL
                  WHERE id = %(i)s""",
              {"p": bcrypt.hashpw(mot_de_passe.encode(), bcrypt.gensalt()).decode(), "s": secret, "i": u["id"]})
    _ecrire("DELETE FROM sessions WHERE utilisateur_id = %(i)s", {"i": u["id"]})
    return u, ""


def verifier_identifiants(identifiant: str, mot_de_passe: str) -> dict | None:
    u = _ligne("SELECT * FROM utilisateurs WHERE identifiant = %(i)s AND actif",
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
    _ecrire("""INSERT INTO sessions (jeton, utilisateur_id, expire_at, ip, user_agent)
                 VALUES (%(j)s, %(u)s, now() + make_interval(days => %(d)s), %(ip)s, %(ua)s)""",
              {"j": hashlib.sha256(jeton.encode()).hexdigest(), "u": utilisateur_id, "d": DUREE_SESSION_JOURS,
               "ip": ip[:64], "ua": user_agent[:300]})
    _ecrire("UPDATE utilisateurs SET derniere_connexion_at = now() WHERE id = %(u)s", {"u": utilisateur_id})
    _ecrire("DELETE FROM sessions WHERE expire_at < now()")
    return jeton


def session(jeton: str) -> dict | None:
    if not jeton or not jeton.startswith("mm_"):
        return None
    return _ligne("""SELECT u.id, u.identifiant, u.email, u.role, u.client_id, u.prenom,
                              c.slug AS client_slug, c.schema_pg AS client_schema, c.statut AS client_statut
                         FROM sessions s
                         JOIN utilisateurs u ON u.id = s.utilisateur_id
                         LEFT JOIN clients c ON c.id = u.client_id
                        WHERE s.jeton = %(j)s AND s.expire_at > now() AND u.actif""",
                    {"j": hashlib.sha256(jeton.encode()).hexdigest()})


def fermer_session(jeton: str) -> None:
    _ecrire("DELETE FROM sessions WHERE jeton = %(j)s", {"j": hashlib.sha256((jeton or "").encode()).hexdigest()})
