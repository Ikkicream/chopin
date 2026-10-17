#!/usr/bin/env python3
"""mass_mailing/jobs/resend_webhook.py — événements Resend → espace du bon client (SaaS, 13/10/2026).

Un seul webhook pour tout le compte Resend (1 endpoint en offre gratuite, 5 en Pro) : chaque
mail porte le tag `tenant` (slug client), qui désigne le schéma où ranger l'événement.

1. Signature Svix vérifiée sur le corps BRUT (en-têtes `svix-id`, `svix-timestamp`,
   `svix-signature`), horodatage à ±5 min. Sans signature valide : 401, rien n'est écrit.
   Écrit avec la bibliothèque standard (HMAC-SHA256), comme le TOTP de `infra/auth.py`.
2. Dédoublonnage sur `svix-id` (Resend livre « au moins une fois », sans ordre garanti).
3. Effets, dans le schéma du client :
   - `email.delivered/opened/clicked` → horodatages du destinataire ;
   - `email.bounced` Permanent → suppression `hard_bounce` ; Temporary → statut seulement ;
   - `email.complained` → suppression `complaint` (la plus forte) ;
   - `email.suppressed` → suppression `provider` (Resend refuse déjà cette adresse).

Le secret de signature (`whsec_…`) est rangé dans le stockage privé du module, jamais en clair
dans le code ni dans l'interface.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from infra import adresses, clients, pg, stockage

SECRET = stockage.RACINE / ".secret_resend_webhook"
TOLERANCE_S = 300


def enregistrer_secret(whsec: str) -> None:
    stockage.RACINE.mkdir(parents=True, exist_ok=True)
    fd = os.open(SECRET, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(whsec.strip())


def _secret() -> bytes | None:
    if not SECRET.exists():
        return None
    s = SECRET.read_text().strip()
    return base64.b64decode(s.split("_", 1)[1] if s.startswith("whsec_") else s)


def signature_valide(corps: bytes, svix_id: str, svix_ts: str, svix_sig: str, maintenant: float | None = None) -> bool:
    cle = _secret()
    if not cle or not (svix_id and svix_ts and svix_sig):
        return False
    try:
        if abs((maintenant or time.time()) - int(svix_ts)) > TOLERANCE_S:
            return False
    except ValueError:
        return False
    signe = f"{svix_id}.{svix_ts}.".encode() + corps
    attendu = base64.b64encode(hmac.new(cle, signe, hashlib.sha256).digest()).decode()
    for morceau in svix_sig.split():
        version, _, sig = morceau.partition(",")
        if version == "v1" and hmac.compare_digest(sig, attendu):
            return True
    return False


def _tags(data: dict) -> dict:
    t = data.get("tags") or {}
    if isinstance(t, list):          # selon les versions : liste {name, value} ou objet
        return {x.get("name"): x.get("value") for x in t if isinstance(x, dict)}
    return t


def traiter(evenement: dict, svix_id: str) -> dict:
    """Range UN événement déjà authentifié. Rend {ok, client, effet}."""
    typ = evenement.get("type") or ""
    data = evenement.get("data") or {}
    tags = _tags(data)
    slug = (tags.get("tenant") or "").strip()
    fiche = clients.par_slug(slug) if slug and slug != "interne" else None
    if typ.startswith("domain."):
        return {"ok": True, "client": None, "effet": "domaine (relu par l'onboarding)"}
    if not fiche:
        return {"ok": True, "client": None, "effet": f"ignoré : tag tenant inconnu ({slug or 'absent'})"}
    destinataire = ((data.get("to") or [None])[0] or "").strip().lower()
    msg_id = data.get("email_id") or ""
    with pg.espace(fiche["schema_pg"]):
        n = pg.ecrire("""INSERT INTO webhook_events (provider, event_type, email_hash, external_id,
                                                    signature_valid, raw_payload, processed_at)
                         VALUES ('resend', %(t)s, %(h)s, %(x)s, true, %(p)s, now())
                         ON CONFLICT (provider, external_id) WHERE external_id IS NOT NULL DO NOTHING""",
                      {"t": typ, "h": adresses.hacher(adresses.normaliser(destinataire)) if destinataire else None,
                       "x": svix_id, "p": json.dumps(evenement)})
        if n == 0:
            return {"ok": True, "client": slug, "effet": "doublon ignoré"}
        cond = "(provider_message_id = %(m)s OR sweego_message_id = %(m)s)"
        effet = typ
        if typ == "email.delivered":
            pg.ecrire(f"UPDATE recipients SET send_status = 'delivered', delivered_at = COALESCE(delivered_at, now()), updated_at = now() WHERE {cond}", {"m": msg_id})
        elif typ == "email.opened":
            pg.ecrire(f"UPDATE recipients SET opened_at = COALESCE(opened_at, now()), updated_at = now() WHERE {cond}", {"m": msg_id})
        elif typ == "email.clicked":
            pg.ecrire(f"UPDATE recipients SET clicked_at = COALESCE(clicked_at, now()), updated_at = now() WHERE {cond}", {"m": msg_id})
        elif typ in ("email.bounced", "email.complained", "email.suppressed", "email.failed"):
            b = data.get("bounce") or {}
            permanent = typ != "email.bounced" or (b.get("type") or "").lower() == "permanent"
            pg.ecrire(f"""UPDATE recipients SET send_status = 'bounced', bounced_at = COALESCE(bounced_at, now()),
                             bounce_type = %(bt)s,
                             complained_at = CASE WHEN %(c)s THEN now() ELSE complained_at END,
                             updated_at = now() WHERE {cond}""",
                      {"m": msg_id, "bt": f"{b.get('type') or typ}/{b.get('subType') or ''}"[:80],
                       "c": typ == "email.complained"})
            raison = {"email.complained": "complaint", "email.suppressed": "provider",
                      "email.failed": "provider"}.get(typ, "hard_bounce")
            if destinataire and permanent and typ != "email.failed":
                pg.ecrire("""INSERT INTO suppressions (email_hash, email_normalized, reason, source, scope, metadata)
                             VALUES (%(h)s, %(e)s, %(r)s, 'resend', 'global', %(md)s) """ + pg.SUPPRESSION_SUR_CONFLIT,
                          {"h": adresses.hacher(adresses.normaliser(destinataire)), "e": destinataire, "r": raison,
                           "md": json.dumps({"type": typ, "bounce": b, "email_id": msg_id})})
                effet += f" → suppression {raison}"
    return {"ok": True, "client": slug, "effet": effet}
