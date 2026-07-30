"""
campaign_engine.py — Modèle de campagne unifié multi-canal + scheduler.

Une "campagne unifiée" = un message envoyé sur UN canal (sweego|emelia|maildoso) à une cible
(secteurs, filtrée Mailnjoy valid < 6 mois), étalée dans le temps selon un planning calculé par
`deliverability_agent` (cap dur par canal). Un cron quotidien (`dispatch_due`) exécute le lot du jour.

Table : campaigns_unified (data/god_mode.duckdb).
CLI : `python3 scripts/campaign_engine.py dispatch` (appelé par cron).
"""
from __future__ import annotations

import json
import sys
import uuid as _uuid
from datetime import date as _date, datetime, timezone
from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"

VALID_CHANNELS = ("sweego", "emelia", "maildoso")
ACTIVE_STATUSES = ("scheduled", "running")


def _conn():
    return duckdb.connect(str(GOD_DB))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_table():
    c = _conn()
    try:
        c.execute(
            """CREATE TABLE IF NOT EXISTS campaigns_unified (
                id              VARCHAR,
                site_code       VARCHAR,
                name            VARCHAR,
                channel         VARCHAR,
                message_id      VARCHAR,
                subject         VARCHAR,
                sectors         VARCHAR,        -- JSON array
                target_size     INTEGER,
                schedule_start  DATE,
                cadence         VARCHAR,        -- JSON [{date, count}]
                status          VARCHAR,        -- scheduled|running|paused|done|failed|cancelled
                sent_count      INTEGER,
                last_dispatch_at TIMESTAMP,
                last_dispatch_day DATE,         -- idempotence : 1 dispatch/jour
                last_error      VARCHAR,
                created_by      VARCHAR,
                created_at      TIMESTAMP,
                params          VARCHAR,        -- JSON libre
                PRIMARY KEY (id)
            )"""
        )
    finally:
        c.close()


# ── CRUD ─────────────────────────────────────────────────────────────────────
def create_campaign(site: str, name: str, channel: str, message_id: str, subject: str,
                    sectors: list[str], target_size: int, schedule_start: str,
                    by: str = "ui", regions: list[str] | None = None,
                    depts: list[str] | None = None,
                    engagement: str | None = None) -> dict:
    """Crée + planifie une campagne. Valide la faisabilité via deliverability_agent.
    Refuse si le canal est invalide, la cible vide, ou la cadence infaisable."""
    channel = (channel or "").lower()
    if channel not in VALID_CHANNELS:
        return {"ok": False, "error": f"canal invalide: {channel}"}
    if not name or not message_id or not subject or not sectors or target_size < 1:
        return {"ok": False, "error": "name, message_id, subject, sectors, target_size requis"}

    # Le message doit être résoluble MAINTENANT (évite une campagne qui échouera au dispatch).
    import html_templates_backend as _htb
    if not (_htb.resolve_campaign_message(site, message_id) or {}).get("html"):
        return {"ok": False, "error": f"message introuvable: {message_id}"}

    engagement = (engagement or "").strip() or None
    import contacts_pool_backend as _pool
    if engagement and engagement not in _pool.ENGAGEMENT_FILTERS:
        return {"ok": False, "error": f"filtre engagement invalide: {engagement}"}

    # La cible doit exister : refuse un volume supérieur aux contacts éligibles
    # (sinon la campagne resterait "running" sans jamais atteindre son target).
    available = sum(
        _pool.count_available_for_sector(site, sec, regions=regions or [], depts=depts or [],
                                         engagement=engagement)
        for sec in sectors
    )
    if target_size > available:
        return {"ok": False,
                "error": f"volume trop grand : {target_size} demandés, "
                         f"{available} contacts éligibles",
                "available": available}

    try:
        start = _date.fromisoformat(schedule_start)
    except Exception:
        return {"ok": False, "error": "schedule_start invalide (YYYY-MM-DD)"}

    # Planning + faisabilité (agent délivrabilité)
    import deliverability_agent as da
    plan = da.plan_cadence(site, channel, target_size, start)
    if not plan.get("feasible"):
        return {"ok": False, "error": "cadence infaisable",
                "plan": plan, "explanation": da.explain(plan, channel, target_size)}

    cid = str(_uuid.uuid4())[:12]
    # utm_campaign UNIQUE et STABLE par campagne (attribution GA4 : "quelle campagne a cliqué ?").
    # Format : <slug-du-nom>-<6 hex> — lisible + garanti unique.
    try:
        from utm_tagging import slug_campaign
        utm_campaign = f"{slug_campaign(name)}-{cid[:6]}"
    except Exception:
        utm_campaign = cid
    params = {"utm_campaign": utm_campaign}
    # Ciblage géographique optionnel (codes région / département INSEE)
    if regions:
        params["regions"] = [str(r) for r in regions if r]
    if depts:
        params["depts"] = [str(d) for d in depts if d]
    if engagement:
        params["engagement"] = engagement
    _ensure_table()
    c = _conn()
    try:
        c.execute(
            "INSERT INTO campaigns_unified "
            "(id, site_code, name, channel, message_id, subject, sectors, target_size, "
            " schedule_start, cadence, status, sent_count, last_dispatch_at, last_dispatch_day, "
            " last_error, created_by, created_at, params) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL,?,?,?)",
            [cid, site, name, channel, message_id, subject, json.dumps(sectors), int(target_size),
             start, json.dumps(plan.get("schedule", [])), "scheduled", 0,
             by, _now(), json.dumps(params)],
        )
    finally:
        c.close()
    return {"ok": True, "id": cid, "status": "scheduled", "utm_campaign": utm_campaign, "plan": plan}


def _row_to_dict(r) -> dict:
    cols = ["id", "site_code", "name", "channel", "message_id", "subject", "sectors",
            "target_size", "schedule_start", "cadence", "status", "sent_count",
            "last_dispatch_at", "last_dispatch_day", "last_error", "created_by",
            "created_at", "params"]
    d = dict(zip(cols, r))
    for k in ("sectors", "cadence", "params"):
        try:
            d[k] = json.loads(d[k]) if d.get(k) else ([] if k != "params" else {})
        except Exception:
            d[k] = [] if k != "params" else {}
    for k in ("schedule_start", "last_dispatch_at", "last_dispatch_day", "created_at"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    d["progress"] = round((d["sent_count"] or 0) / d["target_size"] * 100) if d.get("target_size") else 0
    return d


_SELECT = ("SELECT id, site_code, name, channel, message_id, subject, sectors, target_size, "
           "schedule_start, cadence, status, sent_count, last_dispatch_at, last_dispatch_day, "
           "last_error, created_by, created_at, params FROM campaigns_unified")


def list_campaigns(site: str) -> list[dict]:
    _ensure_table()
    c = _conn()
    try:
        rows = c.execute(_SELECT + " WHERE site_code=? ORDER BY created_at DESC", [site]).fetchall()
    finally:
        c.close()
    return [_row_to_dict(r) for r in rows]


def get_campaign(cid: str) -> dict | None:
    _ensure_table()
    c = _conn()
    try:
        r = c.execute(_SELECT + " WHERE id=?", [cid]).fetchone()
    finally:
        c.close()
    return _row_to_dict(r) if r else None


def update_campaign(site: str, cid: str, patch: dict, by: str = "ui") -> dict:
    """Modifie une campagne existante (fiche « Éditer » de l'UI).

    Toujours modifiables : nom, objet, message, ciblage (secteurs / zones / engagement)
    — le dispatch pioche des contacts frais chaque jour, ces changements ne valent donc
    que pour les envois restants.
    Volume et date de lancement : uniquement tant qu'aucun envoi n'a eu lieu, car la
    cadence est recalculée de zéro et les compteurs déjà consommés la rendraient fausse.
    """
    camp = get_campaign(cid)
    if not camp or camp.get("site_code") != site:
        return {"ok": False, "error": "campagne introuvable"}
    if camp.get("status") in ("done", "cancelled"):
        return {"ok": False, "error": f"campagne {camp['status']} — non modifiable"}

    import contacts_pool_backend as _pool
    import html_templates_backend as _htb

    sent = int(camp.get("sent_count") or 0)
    params = dict(camp.get("params") or {})
    sets: list[str] = []
    vals: list = []

    if "name" in patch:
        name = (patch.get("name") or "").strip()
        if not name:
            return {"ok": False, "error": "nom requis"}
        sets.append("name=?"); vals.append(name)
    if "subject" in patch:
        subject = (patch.get("subject") or "").strip()
        if not subject:
            return {"ok": False, "error": "objet requis"}
        sets.append("subject=?"); vals.append(subject)
    if "message_id" in patch:
        mid = (patch.get("message_id") or "").strip()
        if not (_htb.resolve_campaign_message(site, mid) or {}).get("html"):
            return {"ok": False, "error": f"message introuvable: {mid}"}
        sets.append("message_id=?"); vals.append(mid)

    # ── Ciblage ──
    sectors = camp.get("sectors") or []
    if "sectors" in patch:
        sectors = [s for s in (patch.get("sectors") or []) if s]
        if not sectors:
            return {"ok": False, "error": "au moins un secteur requis"}
        sets.append("sectors=?"); vals.append(json.dumps(sectors))
    for key in ("regions", "depts"):
        if key in patch:
            vs = [str(v) for v in (patch.get(key) or []) if v]
            if vs:
                params[key] = vs
            else:
                params.pop(key, None)
    if "engagement" in patch:
        eng = (patch.get("engagement") or "").strip()
        if eng and eng not in _pool.ENGAGEMENT_FILTERS:
            return {"ok": False, "error": f"filtre engagement invalide: {eng}"}
        if eng:
            params["engagement"] = eng
        else:
            params.pop("engagement", None)

    # ── Volume / date de lancement : avant le 1er envoi seulement ──
    target = int(camp.get("target_size") or 0)
    start = str(camp.get("schedule_start") or "")[:10]
    replan = ("target_size" in patch and int(patch["target_size"] or 0) != target) or \
             ("schedule_start" in patch and (patch.get("schedule_start") or "").strip()[:10] != start)
    if replan and sent > 0:
        return {"ok": False,
                "error": f"volume et date non modifiables après le 1er envoi ({sent} déjà envoyés) — "
                         "annule la campagne et recrée-la"}
    if "target_size" in patch:
        target = int(patch.get("target_size") or 0)
        if target < 1:
            return {"ok": False, "error": "volume invalide"}
    if "schedule_start" in patch:
        try:
            start = _date.fromisoformat((patch.get("schedule_start") or "").strip()[:10]).isoformat()
        except Exception:
            return {"ok": False, "error": "date de lancement invalide (YYYY-MM-DD)"}

    # La cible doit rester atteignable dès que le ciblage OU le volume bouge.
    if replan or any(k in patch for k in ("sectors", "regions", "depts", "engagement")):
        available = sum(
            _pool.count_available_for_sector(site, sec,
                                             regions=params.get("regions") or [],
                                             depts=params.get("depts") or [],
                                             engagement=params.get("engagement"))
            for sec in sectors
        )
        if target > available:
            return {"ok": False,
                    "error": f"volume trop grand : {target} demandés, {available} contacts éligibles",
                    "available": available}

    if replan:
        import deliverability_agent as da
        plan = da.plan_cadence(site, camp["channel"], target, _date.fromisoformat(start))
        if not plan.get("feasible"):
            return {"ok": False, "error": "cadence infaisable", "plan": plan,
                    "explanation": da.explain(plan, camp["channel"], target)}
        sets.append("target_size=?"); vals.append(int(target))
        sets.append("schedule_start=?"); vals.append(_date.fromisoformat(start))
        sets.append("cadence=?"); vals.append(json.dumps(plan.get("schedule", [])))

    if params != (camp.get("params") or {}):
        sets.append("params=?"); vals.append(json.dumps(params))
    if not sets:
        return {"ok": True, "id": cid, "unchanged": True, "campaign": camp}

    _ensure_table()
    c = _conn()
    try:
        c.execute(f"UPDATE campaigns_unified SET {', '.join(sets)} WHERE id=?", vals + [cid])
    finally:
        c.close()
    return {"ok": True, "id": cid, "campaign": get_campaign(cid)}


def set_status(cid: str, status: str, error: str | None = None) -> bool:
    _ensure_table()
    c = _conn()
    try:
        c.execute("UPDATE campaigns_unified SET status=?, last_error=? WHERE id=?",
                  [status, error, cid])
    finally:
        c.close()
    return True


# ── Dispatch (scheduler) ───────────────────────────────────────────────────────
def _todays_allowance(camp: dict, today: _date) -> int:
    """Nb d'emails autorisés aujourd'hui : cumul prévu par la cadence jusqu'à
    aujourd'hui inclus, moins le déjà-envoyé — un jour de dispatch manqué est donc
    rattrapé dès le lendemain, pas seulement après la fin de la cadence. Borné au
    plus gros lot quotidien de la cadence pour respecter le cap du canal."""
    cadence = camp.get("cadence") or []
    sent = camp.get("sent_count", 0) or 0
    target = camp.get("target_size", 0) or 0
    if not cadence:
        return max(0, target - sent)
    expected = sum(int(s.get("count", 0)) for s in cadence
                   if str(s.get("date", "")) <= today.isoformat())
    if today.isoformat() > str(cadence[-1].get("date", "")):
        expected = max(expected, target)  # cadence finie : tout le reliquat
    daily_cap = max(int(s.get("count", 0)) for s in cadence)
    return max(0, min(expected - sent, daily_cap))


def dispatch_campaign(cid: str, today: _date | None = None, dry_run: bool = False) -> dict:
    """Exécute le lot du jour pour une campagne. Idempotent par jour."""
    today = today or _date.today()
    camp = get_campaign(cid)
    if not camp:
        return {"ok": False, "error": "introuvable"}
    if camp["status"] not in ACTIVE_STATUSES:
        return {"ok": False, "error": f"statut {camp['status']} (pas dispatchable)"}
    if camp.get("last_dispatch_day") == today.isoformat():
        return {"ok": False, "error": "déjà dispatché aujourd'hui", "skipped": True}
    if str(camp.get("schedule_start", ""))[:10] > today.isoformat():
        return {"ok": False, "error": "pas encore commencé", "skipped": True}

    allowance = _todays_allowance(camp, today)
    remaining = (camp["target_size"] or 0) - (camp["sent_count"] or 0)
    n = min(allowance, remaining)
    if n <= 0:
        if remaining <= 0:
            set_status(cid, "done")
            return {"ok": True, "done": True, "sent": 0}
        return {"ok": True, "sent": 0, "note": "rien prévu aujourd'hui"}

    # Pioche les contacts éligibles (Mailnjoy valid < 6 mois) sur tous les secteurs,
    # restreinte aux zones géo de la campagne si définies (params.regions / params.depts)
    import contacts_pool_backend as pool
    site = camp["site_code"]
    geo = camp.get("params") or {}
    contacts: list[dict] = []
    seen = set()
    for sec in camp.get("sectors", []):
        for ct in pool.pick_for_campaign(site, sec, limit=n - len(contacts),
                                         regions=geo.get("regions"), depts=geo.get("depts"),
                                         engagement=geo.get("engagement")):
            if ct.get("email") and ct["email"] not in seen:
                seen.add(ct["email"]); contacts.append(ct)
        if len(contacts) >= n:
            break
    contacts = contacts[:n]
    emails = [ct["email"] for ct in contacts if ct.get("email")]
    if not emails:
        return {"ok": True, "sent": 0, "note": "aucun contact éligible aujourd'hui"}

    if dry_run:
        return {"ok": True, "dry_run": True, "would_send": len(emails)}

    sent = _send_batch(camp, contacts, emails, today)
    if not sent.get("ok"):
        set_status(cid, "running", error=sent.get("error"))
        return sent

    # MAJ compteurs + statut
    new_sent = (camp["sent_count"] or 0) + sent.get("sent", 0)
    done = new_sent >= camp["target_size"]
    c = _conn()
    try:
        c.execute("UPDATE campaigns_unified SET sent_count=?, status=?, last_dispatch_at=?, "
                  "last_dispatch_day=?, last_error=NULL WHERE id=?",
                  [new_sent, "done" if done else "running", _now(), today, cid])
    finally:
        c.close()
    return {"ok": True, "sent": sent.get("sent", 0), "total_sent": new_sent, "done": done}


def _send_batch(camp: dict, contacts: list[dict], emails: list[str], today: _date) -> dict:
    """Envoi d'un lot via le canal de la campagne."""
    channel = camp["channel"]
    site = camp["site_code"]
    import html_templates_backend as htb
    msg = htb.resolve_campaign_message(site, camp["message_id"])
    if not msg or not msg.get("html"):
        return {"ok": False, "error": "message introuvable"}
    # utm_campaign unique de la campagne (attribution GA4)
    utm_campaign = (camp.get("params") or {}).get("utm_campaign") or camp["id"]

    if channel == "sweego":
        import sweego_backend as sw
        from contacts_pool_backend import mark_pushed_to_emelia
        campaign_id = f"{site}-{camp['id']}-{today.isoformat()}"
        res = sw.send_campaign(campaign_id, camp["subject"], msg["html"], emails, dry_run=False,
                               utm_campaign=utm_campaign, utm_source="sweego")
        if not res.get("ok"):
            return res
        for ct in contacts:
            try:
                mark_pushed_to_emelia(ct["id"], site, campaign_id, "")
            except Exception:
                pass
        try:
            sw.record_campaign(site, camp["name"], campaign_id, camp["subject"],
                               ",".join(camp.get("sectors", [])), camp["message_id"],
                               len(emails), res.get("transaction_id"), by="scheduler")
        except Exception:
            pass
        return {"ok": True, "sent": res.get("sent", len(emails))}

    if channel == "emelia":
        import emelia_campaign_manager as ecm
        from contacts_pool_backend import mark_pushed_to_emelia
        # Crée la campagne Emelia au 1er dispatch (1 step = le message), réutilise ensuite.
        params = camp.get("params") or {}
        emelia_cid = params.get("emelia_campaign_id")
        if not emelia_cid:
            try:
                created = ecm.create_emelia_campaign(f"{site.upper()}-{camp['name']}"[:60])
                emelia_cid = (created.get("campaign") or {}).get("_id") or created.get("_id")
                if not emelia_cid:
                    return {"ok": False, "error": "création campagne Emelia échouée"}
                # Tag le HTML avec le bon plan (cold email) + utm unique de la campagne
                tagged_html = msg["html"]
                try:
                    from utm_tagging import tag_links
                    tagged_html = tag_links(msg["html"], "coldemail", "email", utm_campaign)
                except Exception:
                    pass
                ecm.configure_steps(emelia_cid, ecm.build_newsletter_steps(tagged_html, camp["subject"]))
                try:
                    ecm.configure_settings(emelia_cid)
                except Exception:
                    pass
                params["emelia_campaign_id"] = emelia_cid
                _save_params(camp["id"], params)
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"setup Emelia: {e}"}

        # 1) Les contacts d'abord : Emelia refuse de démarrer une campagne sans
        #    destinataire (« You must have at least one recipient to start campaign »).
        added = 0
        for ct in contacts:
            contact = {"email": ct["email"], "firstName": ct.get("prenom", ""),
                       "lastName": ct.get("nom", ""), "field1": ct.get("societe", "")}
            try:
                if ecm.add_contact(emelia_cid, contact):
                    added += 1
                    mark_pushed_to_emelia(ct["id"], site, emelia_cid, "")
            except Exception:
                pass

        # 2) Démarrage, une seule fois par campagne. La réponse DOIT être vérifiée :
        #    sur refus Emelia laisse la campagne en DRAFT tout en ayant accepté les
        #    contacts — sans ce contrôle le dispatch comptait des envois fantômes et
        #    posait le cooldown sur des contacts qui n'ont jamais rien reçu.
        if added and not params.get("emelia_started"):
            import requests as _rq
            _st = _rq.post(f"{ecm.EMELIA_URL}/emails/campaigns/{emelia_cid}/start",
                           headers=ecm.HEADERS, timeout=15)
            if _st.status_code >= 400:
                try:
                    _detail = _st.json().get("error") or _st.text[:200]
                except Exception:
                    _detail = _st.text[:200]
                # On NE supprime pas la campagne : son id est déjà enregistré dans les
                # params et les contacts y sont poussés — le prochain dispatch la
                # réutilisera et retentera le démarrage.
                return {"ok": False,
                        "error": f"Emelia refuse de démarrer la campagne "
                                 f"({_st.status_code}) : {_detail}"}
            params["emelia_started"] = True
            _save_params(camp["id"], params)
        return {"ok": True, "sent": added}

    if channel == "maildoso":
        import maildoso_backend as md
        from contacts_pool_backend import mark_pushed_to_emelia
        campaign_id = f"{site}-{camp['id']}-{today.isoformat()}"
        res = md.send_batch(campaign_id, camp["subject"], msg["html"], contacts,
                            site=site, utm_campaign=utm_campaign)
        if not res.get("ok"):
            return res
        ok_emails = set(res.get("sent_emails", []))
        for ct in contacts:
            if ct.get("email") in ok_emails:
                try:
                    mark_pushed_to_emelia(ct["id"], site, campaign_id, "")
                except Exception:
                    pass
        # Ramp-up : ajuste les caps/jour des boîtes après chaque campagne (idempotent/jour)
        try:
            import maildoso_ramp
            maildoso_ramp.adjust_caps(site)
        except Exception:
            pass
        return {"ok": True, "sent": res.get("sent", 0)}

    return {"ok": False, "error": f"canal non supporté: {channel}"}


def _save_params(cid: str, params: dict) -> None:
    c = _conn()
    try:
        c.execute("UPDATE campaigns_unified SET params=? WHERE id=?", [json.dumps(params), cid])
    finally:
        c.close()


def dispatch_due(today: _date | None = None) -> dict:
    """Cron quotidien : dispatch toutes les campagnes actives dues aujourd'hui."""
    today = today or _date.today()
    # Avant d'envoyer : vérifie les crédits d'envoi et alerte l'admin (Telegram) si bas/épuisés.
    try:
        import credit_alerts
        credit_alerts.check_and_alert()
    except Exception:  # noqa: BLE001
        pass
    _ensure_table()
    c = _conn()
    try:
        ids = [r[0] for r in c.execute(
            "SELECT id FROM campaigns_unified WHERE status IN ('scheduled','running') "
            "AND schedule_start <= ?", [today]).fetchall()]
    finally:
        c.close()
    results = []
    for cid in ids:
        try:
            results.append({"id": cid, **dispatch_campaign(cid, today)})
        except Exception as e:  # noqa: BLE001
            results.append({"id": cid, "ok": False, "error": str(e)})
            set_status(cid, "running", error=str(e))
    return {"ok": True, "dispatched": len(ids), "results": results}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dispatch"
    if cmd == "dispatch":
        print(json.dumps(dispatch_due(), ensure_ascii=False, default=str))
    else:
        print(f"usage: {sys.argv[0]} dispatch")
