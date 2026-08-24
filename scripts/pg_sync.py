#!/usr/bin/env python3
"""pg_sync.py — PROMOTION des contacts propres de DuckDB vers PostgreSQL.

Modèle en entonnoir (décision user 2026-08-19) : DuckDB fait le scraping, le nettoyage, la
vérification Mailnjoy et l'enrichissement ; PostgreSQL ne reçoit QUE ce qui a franchi tous
les contrôles. Le critère unique est dans `pg_gate.ELIGIBILITE_SQL`.

Ce n'est donc PAS un miroir : une écriture DuckDB sur un contact sale ne produit rien côté
PostgreSQL, et un contact qui se salit après coup en est RETIRÉ. Son journal `email_events`
reste — il est indexé sur l'adresse, donc le blocage de 120 jours lui survit.

**Best-effort, et strictement best-effort.** Un échec PostgreSQL ne doit JAMAIS faire échouer
une écriture DuckDB : à ce stade, PostgreSQL n'est qu'une copie. Mais un échec silencieux
serait pire que pas de copie du tout — on croirait les bases alignées alors qu'elles
divergent. Chaque échec est donc compté et journalisé, et `sync_health()` remonte le compteur
pour que la divergence se voie (leçon du 19/08 : trois bugs de renvoi et un mode maintenance
inopérant venaient tous d'un échec avalé en silence).

Désactivable à chaud par PG_SYNC=0 dans .env, sans toucher au code.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

_LOCK = threading.Lock()
_ECHECS: list[dict] = []       # les 50 derniers, pour diagnostic
_COMPTEURS = {"ok": 0, "echec": 0}
_DSN: str | None = None
_ACTIF: bool | None = None


def _env(cle: str) -> str:
    try:
        for ligne in ENV_FILE.read_text().splitlines():
            if ligne.startswith(cle + "="):
                return ligne.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def actif() -> bool:
    """Double écriture activée ? Lue une fois par process."""
    global _ACTIF, _DSN
    if _ACTIF is None:
        _DSN = _env("PG_DSN")
        _ACTIF = bool(_DSN) and _env("PG_SYNC") != "0"
    return _ACTIF


def _conn():
    """Connexion prise dans le pool partagé de `pool_pg`, jamais ouverte à neuf.

    Ce module est sur le chemin le plus chaud du système : chaque contact scrapé déclenche
    `promote_contact`, qui déclenche à son tour un `sync_contact_site` par site — soit deux
    à trois écritures. Ouvrir une connexion pour chacune, c'est autant d'allers-retours TCP
    et de forks côté serveur ; une passe de collecte de 500 contacts en produisait 1 500.
    Le pool ramène ça à quelques connexions réutilisées.

    Repli sur une connexion directe si `pool_pg` est indisponible : ce module doit rester
    utilisable seul, y compris depuis un script lancé hors de l'API.
    """
    try:
        import pool_pg
        return pool_pg._conn(), True
    except Exception:  # noqa: BLE001
        import psycopg2
        return psycopg2.connect(_DSN), False


def _rendre(c, pooled: bool) -> None:
    if pooled:
        import pool_pg
        pool_pg._rendre(c)
    else:
        c.close()


def _echec(operation: str, e: Exception, detail: dict) -> None:
    with _LOCK:
        _COMPTEURS["echec"] += 1
        _ECHECS.append({"op": operation, "erreur": f"{type(e).__name__}: {e}"[:200],
                        "detail": detail, "at": datetime.now(timezone.utc).isoformat()})
        del _ECHECS[:-50]
    print(f"[pg_sync] ÉCHEC {operation} : {type(e).__name__}: {str(e)[:150]} — {detail}",
          flush=True)


def _executer(operation: str, sql: str, params: tuple, detail: dict) -> bool:
    if not actif():
        return False
    try:
        c, pooled = _conn()
        try:
            with c:
                with c.cursor() as cur:
                    cur.execute(sql, params)
        finally:
            _rendre(c, pooled)
        with _LOCK:
            _COMPTEURS["ok"] += 1
        return True
    except Exception as e:  # noqa: BLE001
        _echec(operation, e, detail)
        return False


def sync_health() -> dict:
    """Compteurs de la double écriture. `echec` doit rester à 0."""
    with _LOCK:
        return {"actif": actif(), **_COMPTEURS, "derniers_echecs": list(_ECHECS[-5:])}


# ── Contacts ──────────────────────────────────────────────────────────────────

def promote_contact(contact_id: str) -> bool:
    """Fait franchir la porte à un contact — ou l'en retire s'il n'y a plus sa place.

    Une seule fonction pour les deux sens : appelée après CHAQUE écriture le concernant,
    elle relit son éligibilité dans DuckDB et met PostgreSQL en conformité. Séparer
    « promouvoir » et « retirer » obligerait chaque appelant à savoir dans quel sens il va,
    et c'est exactement le genre de décision qu'on finit par oublier quelque part.
    """
    if not actif() or not contact_id:
        return False
    try:
        import pg_gate
        # Depuis le 2026-08-20, PostgreSQL accueille TOUT LE MONDE : on lit le contact quel
        # que soit son état, et c'est l'état qui dira à qui on a le droit d'écrire. La
        # lecture « éligible ou rien » supprimait de la base un contact devenu mauvais —
        # et on le re-scrapait trois semaines plus tard, faute de s'en souvenir.
        d = pg_gate.contact_tel_quel(contact_id)
    except Exception as e:  # noqa: BLE001
        _echec("promote_contact/lecture", e, {"contact_id": contact_id})
        return False

    if d is None:
        # Disparu du pool pour de bon : là, oui, on retire.
        return _retirer_par_id(contact_id)

    mn = d.get("mailnjoy_check") or {}
    if isinstance(mn, str):
        try:
            mn = json.loads(mn)
        except Exception:
            mn = {}
    secteurs = d.get("sectors") or []
    if isinstance(secteurs, str):
        try:
            secteurs = json.loads(secteurs)
        except Exception:
            secteurs = []

    ok = _executer("promote_contact", """
        INSERT INTO contacts (id, email, prenom, nom, societe, tel, website, city,
            dept_code, region_code, postal_code, sectors, primary_source, email_score,
            mailnjoy_decision, mailnjoy_checked_at, mailnjoy_check, global_blacklisted,
            created_at, updated_at, etat, etat_motif, etat_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, false, now(), now(),
                %s,%s,now())
        ON CONFLICT (email) DO UPDATE SET
            prenom = COALESCE(EXCLUDED.prenom, contacts.prenom),
            nom = COALESCE(EXCLUDED.nom, contacts.nom),
            societe = COALESCE(EXCLUDED.societe, contacts.societe),
            tel = COALESCE(EXCLUDED.tel, contacts.tel),
            website = COALESCE(EXCLUDED.website, contacts.website),
            city = COALESCE(EXCLUDED.city, contacts.city),
            dept_code = COALESCE(EXCLUDED.dept_code, contacts.dept_code),
            region_code = COALESCE(EXCLUDED.region_code, contacts.region_code),
            sectors = EXCLUDED.sectors,
            email_score = EXCLUDED.email_score,
            mailnjoy_decision = EXCLUDED.mailnjoy_decision,
            mailnjoy_checked_at = EXCLUDED.mailnjoy_checked_at,
            mailnjoy_check = EXCLUDED.mailnjoy_check,
            etat = EXCLUDED.etat,
            etat_motif = EXCLUDED.etat_motif,
            etat_at = now(),
            updated_at = now()
    """, (d.get("id"), (d.get("email") or "").strip().lower(), d.get("prenom"), d.get("nom"),
          d.get("societe"), d.get("tel"), d.get("website"), d.get("city"), d.get("dept_code"),
          d.get("region_code"), d.get("postal_code"), secteurs, d.get("primary_source"),
          d.get("email_score"), mn.get("decision"), mn.get("checked_at"),
          json.dumps(mn) if mn else None,
          d.get("etat") or "a_verifier", d.get("etat_motif")),
        {"email": d.get("email")})

    # L'état par site suit le contact : sans lui, la pioche PostgreSQL considérerait un
    # contact déjà promu `lead` comme du cold email disponible.
    if ok:
        try:
            import pg_gate
            for site in pg_gate.sites_du_contact(contact_id):
                st = pg_gate.etat_site(contact_id, site)
                if st:
                    sync_contact_site(contact_id, site, st["state"], st.get("source") or "",
                                      st.get("history"))
        except Exception as e:  # noqa: BLE001
            _echec("promote_contact/etats", e, {"contact_id": contact_id})
    return ok


def _retirer_par_id(contact_id: str) -> bool:
    """Retire un contact devenu inéligible. Le journal survit (clé étrangère SET NULL)."""
    return _executer("retirer_contact", "DELETE FROM contacts WHERE id = %s",
                     (contact_id,), {"contact_id": contact_id})


def retirer_par_email(email: str) -> bool:
    """Retrait quand on ne dispose que de l'adresse (désabonnement, plainte, rebond)."""
    em = (email or "").strip().lower()
    if not em:
        return False
    return _executer("retirer_contact", "DELETE FROM contacts WHERE email = %s",
                     (em,), {"email": em})


def sync_blacklist(email: str, reason: str = "") -> bool:
    """Un contact blacklisté est MARQUÉ, jamais retiré.

    Il l'était jusqu'au 2026-08-23 : hérité du modèle en entonnoir, où PostgreSQL ne
    devait contenir que du contactable. Ce modèle est tombé le 2026-08-20 — PostgreSQL
    accueille tout le monde et `etat` dit à qui on a le droit d'écrire — mais cette
    fonction-là avait gardé le vieux réflexe. Elle faisait donc disparaître le contact de
    tous les écrans jusqu'à la réconciliation du lendemain matin, qui le réinsérait :
    l'effacer, c'est perdre la mémoire de l'avoir écarté, et le re-scraper plus tard.

    La contrepartie du marquage est déjà en place : la pioche d'envoi exige `etat = 'ok'`,
    et `global_blacklisted` la barre une seconde fois."""
    em = (email or "").strip().lower()
    if not em:
        return False
    return _executer("blacklist_contact", """
        UPDATE contacts SET global_blacklisted = true,
                            blacklist_reason = COALESCE(NULLIF(%s, ''), blacklist_reason),
                            blacklisted_at = now(),
                            etat = 'spam',
                            etat_motif = COALESCE(NULLIF(%s, ''), 'blacklisté'),
                            etat_at = now(), updated_at = now()
        WHERE email = %s
    """, (reason, reason, em), {"email": em})


def _attribuer_rappel(contact_id: str, site_code: str) -> None:
    """Un contact qui devient `lead` ou `prm` entre dans la liste d'appels : on l'attribue
    d'office au commercial par défaut du site.

    Sans cela il atterrit dans le vivier, où il attend que quelqu'un pense à le prendre —
    c'est ce qui a laissé 60 prospects sans le moindre appel depuis le 7 août.

    Best-effort, comme tout ce fichier : une attribution ratée ne doit pas faire échouer la
    synchronisation de l'état. Le balayage de `pg_reconcile` rattrapera.
    """
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        import followup_backend as fb
        fb.attribuer_auto(site_code, contact_id=contact_id)
    except Exception as e:  # noqa: BLE001
        _echec("attribuer_rappel", e, {"contact_id": contact_id, "site": site_code})


def sync_contact_site(contact_id: str, site_code: str, state: str = "cold_email",
                      source: str = "", historique: list | None = None) -> bool:
    """Upsert de l'état contact × site. `ON CONFLICT DO UPDATE` : impossible de ne rien
    faire en silence, contrairement à l'UPDATE nu qui a produit 18 renvois en août."""
    ok = _executer("sync_contact_site", """
        INSERT INTO contact_sites (id, contact_id, site_code, state, source, added_at,
                                   last_action_at, state_history)
        VALUES (gen_random_uuid(), %s, %s, %s, %s, now(), now(), %s)
        ON CONFLICT (contact_id, site_code) DO UPDATE SET
            state = EXCLUDED.state,
            last_action_at = now(),
            state_history = EXCLUDED.state_history
    """, (contact_id, site_code, state or "cold_email", source or None,
          json.dumps(historique or [])), {"contact_id": contact_id, "site": site_code})
    if ok and (state or "") in ("lead", "prm"):
        _attribuer_rappel(contact_id, site_code)
    return ok


# ── Le journal comportemental ─────────────────────────────────────────────────

def record_event(email: str, event_type: str, site_code: str, channel: str,
                 contact_id: str | None = None, campaign_legacy_id: str | None = None,
                 mailbox: str | None = None, provider_msg_id: str | None = None,
                 url: str | None = None, at: datetime | None = None,
                 meta: dict | None = None) -> bool:
    """Ajoute un événement au journal. En ajout seul : jamais de mise à jour.

    `campaign_legacy_id` est l'id court DuckDB (`fd0dc221-b44`) ; la correspondance vers
    l'uuid PostgreSQL est faite en SQL pour éviter un aller-retour.
    """
    email = (email or "").strip().lower()
    if not email or not event_type:
        return False
    # `record_engagement` passe une date au format ISO (chaîne) : sans conversion,
    # PostgreSQL ne saurait pas typer le paramètre dans le COALESCE.
    if isinstance(at, str):
        try:
            at = datetime.fromisoformat(at)
        except ValueError:
            at = None
    if at is not None and at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return _executer("record_event", """
        INSERT INTO email_events (occurred_at, email, contact_id, site_code, campaign_id,
                                  channel, event_type, url, mailbox, provider_msg_id, meta)
        VALUES (COALESCE(%s, now()), %s,
                (SELECT id FROM contacts WHERE email = %s),
                %s,
                (SELECT id FROM campaigns WHERE legacy_id = %s),
                %s, %s, %s, %s, %s, %s)
    """, (at, email, email, site_code or "lcr", campaign_legacy_id, channel or "inconnu",
          event_type, url, mailbox, provider_msg_id, json.dumps(meta or {})),
        {"email": email, "type": event_type})


def record_send(email: str, site_code: str, contact_id: str | None = None,
                campaign_id: str = "", channel: str = "maildoso",
                mailbox: str | None = None, provider_msg_id: str | None = None) -> bool:
    """Un envoi. C'est CET événement qui pilote la fenêtre de 120 jours via `v_suppression`,
    d'où l'importance qu'il ne soit jamais manqué."""
    court = None
    if campaign_id:
        parts = campaign_id.split("-")
        court = f"{parts[1]}-{parts[2]}" if len(parts) >= 3 else campaign_id
    return record_event(email, "sent", site_code, channel, contact_id=contact_id,
                        campaign_legacy_id=court, mailbox=mailbox,
                        provider_msg_id=provider_msg_id)


# ── Campagnes ─────────────────────────────────────────────────────────────────

def sync_campaign(d: dict) -> bool:
    """Recopie une campagne. Indispensable et pas cosmétique : `record_send` rattache chaque
    envoi à sa campagne via `legacy_id`. Sans ce miroir, une campagne créée après la bascule
    n'existerait pas côté PostgreSQL, et TOUS ses envois entreraient au journal avec
    `campaign_id = NULL` — le reporting par campagne, qui est la raison d'être du journal,
    serait muet sur les campagnes récentes.
    """
    secteurs = d.get("sectors") or []
    if isinstance(secteurs, str):
        try:
            secteurs = json.loads(secteurs)
        except Exception:
            secteurs = []
    cadence = d.get("cadence") or []
    if isinstance(cadence, str):
        try:
            cadence = json.loads(cadence)
        except Exception:
            cadence = []
    params = d.get("params") or {}
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except Exception:
            params = {}
    legacy = str(d.get("id") or "")
    if not legacy:
        return False
    import uuid as _uuid
    new_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"cheffer:campaign:{legacy}"))
    return _executer("sync_campaign", """
        INSERT INTO campaigns (id, site_code, name, channel, message_id, subject, sectors,
            target_size, schedule_start, cadence, status, sent_count, last_dispatch_at,
            last_dispatch_day, last_error, params, created_by, created_at, legacy_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now(), %s)
        ON CONFLICT (legacy_id) DO UPDATE SET
            name = EXCLUDED.name, subject = EXCLUDED.subject, sectors = EXCLUDED.sectors,
            target_size = EXCLUDED.target_size, cadence = EXCLUDED.cadence,
            status = EXCLUDED.status, sent_count = EXCLUDED.sent_count,
            last_dispatch_at = EXCLUDED.last_dispatch_at,
            last_dispatch_day = EXCLUDED.last_dispatch_day,
            last_error = EXCLUDED.last_error, params = EXCLUDED.params
    """, (new_id, d.get("site_code"), d.get("name"), d.get("channel"), d.get("message_id"),
          d.get("subject"), secteurs, int(d.get("target_size") or 0), d.get("schedule_start"),
          json.dumps(cadence), d.get("status") or "scheduled", int(d.get("sent_count") or 0),
          d.get("last_dispatch_at"), d.get("last_dispatch_day"), d.get("last_error"),
          json.dumps(params), d.get("created_by"), legacy),
        {"campagne": legacy})
