#!/usr/bin/env python3
"""mass_mailing/api/routes.py — les routes superadmin de Mass Mailing.

Monté dans l'API Cheffer (`scripts/api.py`) sous `/api/mass-mailing`, mais sans rien
lui emprunter d'autre que la session vérifiée par son middleware
(`request.state.session`). Si ce module plante à l'import, Cheffer démarre quand même
(le montage est gardé par un try/except).

Règles tenues ici :
- **superadmin uniquement**, vérifié côté serveur à chaque route (le menu caché ne
  protège rien) ;
- **aucun traitement long dans une requête HTTP** : l'import CSV et la validation
  passent par la file de jobs ; la route empile et rend la main ;
- **la validation Mailnjoy n'est jamais lancée sans confirmation explicite** : la
  route `validation` exige `confirme: true` ET le nombre d'adresses que l'écran a
  affiché, pour qu'un double-clic ou un écran périmé ne soumette pas autre chose.
"""
from __future__ import annotations

import base64
import binascii
import json
import sys
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import adresses, mailnjoy, pg, stockage, sweego  # noqa: E402
from jobs import analyze_csv, envoi, file, validation  # noqa: E402
from jobs.file import ErreurDefinitive  # noqa: E402
from infra import desinscription  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402

router = APIRouter(prefix="/api/mass-mailing", tags=["mass-mailing"])
# Sans session : le lien de désinscription est cliqué depuis une boîte mail.
# `/api/public/` est le préfixe que le middleware Cheffer laisse passer.
public_router = APIRouter(prefix="/api/public/mass-mailing", tags=["mass-mailing-public"])

STATUTS_EDITABLES = ("draft", "ready_for_validation", "validation_issue", "ready_to_schedule")


def _superadmin(request: Request) -> str:
    sess = getattr(request.state, "session", None) or {}
    if sess.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="Mass Mailing est réservé au superadmin")
    return str(sess.get("username") or sess.get("email") or sess.get("user_id") or "superadmin")


def _audit(campaign_id: str, acteur: str, event: str, resume: str, charge: dict | None = None):
    pg.ecrire("""INSERT INTO campaign_events (campaign_id, actor_type, actor_id, event_type,
                                              summary, payload)
                 VALUES (%(c)s, 'user', %(a)s, %(e)s, %(r)s, %(p)s::jsonb)""",
              {"c": campaign_id, "a": acteur, "e": event, "r": resume,
               "p": json.dumps(charge or {}, ensure_ascii=False, default=str)})


def _campagne(campaign_id: str) -> dict:
    try:
        c = pg.ligne("SELECT * FROM campaigns WHERE id = %(c)s", {"c": campaign_id})
    except Exception:  # noqa: BLE001 — UUID mal formé
        c = None
    if not c:
        raise HTTPException(status_code=404, detail="campagne introuvable")
    return c


# ── Santé ────────────────────────────────────────────────────────────────────

_CACHE_CREDIT: dict = {"t": 0.0, "v": None}


@router.get("/sante")
def sante(request: Request):
    _superadmin(request)
    if time.time() - _CACHE_CREDIT["t"] > 300:
        _CACHE_CREDIT["v"] = mailnjoy.credit()
        _CACHE_CREDIT["t"] = time.time()
    worker = None
    try:
        worker = pg.ligne("""SELECT id, seen_at, info,
                                    extract(epoch FROM now() - seen_at)::int AS age_s
                               FROM workers ORDER BY seen_at DESC LIMIT 1""")
    except Exception:  # noqa: BLE001
        pass
    return {
        "base": pg.sante(),
        "stockage": stockage.sante(),
        "mailnjoy": {"configure": mailnjoy.configure(), **(_CACHE_CREDIT["v"] or {})},
        "sweego": {"configure": sweego.configure()},
        "worker": {"vivant": bool(worker and worker["age_s"] < 120),
                   "vu_il_y_a_s": worker["age_s"] if worker else None},
        "file": file.etat(),
    }


# ── Campagnes ────────────────────────────────────────────────────────────────

@router.get("/campaigns")
def liste(request: Request):
    _superadmin(request)
    return {"campaigns": pg.lignes("""
        SELECT c.id, c.internal_name, c.status, c.subject, c.dispatch_mode,
               c.created_at, c.updated_at, c.created_by, c.target_version,
               tv.original_filename, tv.unique_emails, tv.validation_eligible_count,
               (SELECT count(*) FROM validation_batches v WHERE v.campaign_id = c.id) AS lots,
               (SELECT count(*) FROM validation_batches v
                 WHERE v.campaign_id = c.id AND v.status = 'completed') AS lots_valides,
               (SELECT COALESCE(sum(eligible_count), 0) FROM validation_batches v
                 WHERE v.campaign_id = c.id) AS eligibles,
               st.envoyes, st.livres, st.ouverts, st.cliques, st.rebonds,
               ev.summary AS derniere_activite, ev.created_at AS derniere_activite_le
          FROM campaigns c
          LEFT JOIN LATERAL (
               SELECT count(*) FILTER (WHERE r.send_status IN ('submitted','delivered','bounced')) AS envoyes,
                      count(*) FILTER (WHERE r.delivered_at IS NOT NULL) AS livres,
                      count(*) FILTER (WHERE r.opened_at IS NOT NULL) AS ouverts,
                      count(*) FILTER (WHERE r.clicked_at IS NOT NULL) AS cliques,
                      count(*) FILTER (WHERE r.bounced_at IS NOT NULL) AS rebonds
                 FROM recipients r WHERE r.campaign_id = c.id
                  AND r.target_version_id = c.target_version_id) st ON TRUE
          LEFT JOIN LATERAL (
               SELECT summary, created_at FROM campaign_events e
                WHERE e.campaign_id = c.id ORDER BY e.created_at DESC LIMIT 1) ev ON TRUE
          LEFT JOIN campaign_target_versions tv ON tv.id = c.target_version_id
         WHERE c.status <> 'archived'
         ORDER BY c.created_at DESC
    """)}


@router.post("/campaigns")
async def creer(request: Request):
    acteur = _superadmin(request)
    b = await request.json()
    nom = (b.get("internal_name") or "").strip()
    if not nom:
        raise HTTPException(status_code=422, detail="nom de campagne requis")
    mode = b.get("dispatch_mode") or "progressive"
    if mode not in ("progressive", "after_validation"):
        raise HTTPException(status_code=422, detail="mode d'envoi inconnu")
    c = pg.ligne("""INSERT INTO campaigns (internal_name, subject, preheader, dispatch_mode, created_by)
                    VALUES (%(n)s, %(s)s, %(p)s, %(m)s, %(a)s) RETURNING id""",
                 {"n": nom[:200], "s": (b.get("subject") or "").strip()[:250] or None,
                  "p": (b.get("preheader") or "").strip()[:250] or None, "m": mode, "a": acteur})
    _audit(str(c["id"]), acteur, "campaign.created", f"Campagne « {nom} » créée")
    return {"id": str(c["id"])}


@router.get("/campaigns/{campaign_id}")
def fiche(campaign_id: str, request: Request):
    _superadmin(request)
    c = _campagne(campaign_id)
    tv = None
    if c["target_version_id"]:
        tv = pg.ligne("SELECT * FROM campaign_target_versions WHERE id = %(t)s",
                      {"t": c["target_version_id"]})
    lots = pg.lignes("""SELECT sequence_number, status, total_recipients, processed_count,
                               eligible_count, excluded_count, decisions, error_message,
                               started_at, completed_at
                          FROM validation_batches WHERE campaign_id = %(c)s
                         ORDER BY sequence_number""", {"c": campaign_id})
    envois = pg.lignes("""SELECT sequence_number, status, recipients_count, accepted_count,
                                 rejected_count, dispatched_at, error_message
                            FROM sending_batches WHERE campaign_id = %(c)s
                           ORDER BY sequence_number""", {"c": campaign_id})
    jobs = pg.lignes("""SELECT id, job_type, status, attempts, last_error, created_at, finished_at
                          FROM jobs WHERE campaign_id = %(c)s
                         ORDER BY id DESC LIMIT 20""", {"c": campaign_id})
    journal = pg.lignes("""SELECT created_at, actor_type, actor_id, event_type, summary
                             FROM campaign_events WHERE campaign_id = %(c)s
                            ORDER BY created_at DESC LIMIT 50""", {"c": campaign_id})
    decisions = pg.lignes("""SELECT validation_status AS statut, count(*) AS n
                               FROM recipients WHERE target_version_id = %(t)s
                                AND import_status = 'imported'
                              GROUP BY 1 ORDER BY 2 DESC""",
                          {"t": c["target_version_id"]}) if c["target_version_id"] else []
    profil = pg.ligne("""SELECT id, name, from_name, from_email, reply_to, sending_domain
                           FROM sender_profiles WHERE id = COALESCE(%(p)s,
                                (SELECT id FROM sender_profiles WHERE is_default AND active LIMIT 1))""",
                      {"p": c["sender_profile_id"]})
    return {"campaign": c, "cible": tv, "lots": lots, "envois": envois, "jobs": jobs,
            "journal": journal, "decisions": decisions, "profil": profil,
            "stats": envoi.statistiques(campaign_id),
            "progression": validation.progression(campaign_id)}


@router.patch("/campaigns/{campaign_id}")
async def modifier(campaign_id: str, request: Request):
    acteur = _superadmin(request)
    c = _campagne(campaign_id)
    if c["status"] not in STATUTS_EDITABLES:
        raise HTTPException(status_code=409, detail=f"campagne verrouillée (« {c['status']} »)")
    b = await request.json()
    champs = {k: (b.get(k) or "").strip()[:250] or None
              for k in ("internal_name", "subject", "preheader") if k in b}
    if "dispatch_mode" in b and b["dispatch_mode"] in ("progressive", "after_validation"):
        champs["dispatch_mode"] = b["dispatch_mode"]
    if not champs:
        return {"ok": True}
    sets = ", ".join(f"{k} = %({k})s" for k in champs)
    pg.ecrire(f"UPDATE campaigns SET {sets}, preflight_snapshot = NULL, updated_at = now() "
              f"WHERE id = %(id)s", {**champs, "id": campaign_id})
    _audit(campaign_id, acteur, "campaign.updated", "Campagne modifiée", {"champs": list(champs)})
    _recalculer_statut(campaign_id)
    return {"ok": True}


def _recalculer_statut(campaign_id: str) -> None:
    """draft ↔ ready_for_validation selon que message ET cible sont présents."""
    pg.ecrire("""
        UPDATE campaigns c SET status = CASE
            WHEN c.subject IS NOT NULL AND c.html_storage_key IS NOT NULL
             AND tv.validation_eligible_count > 0 THEN 'ready_for_validation'
            ELSE 'draft' END, updated_at = now()
          FROM campaign_target_versions tv
         WHERE c.id = %(c)s AND tv.id = c.target_version_id
           AND c.status IN ('draft', 'ready_for_validation')
    """, {"c": campaign_id})


# ── Message HTML ─────────────────────────────────────────────────────────────

@router.post("/campaigns/{campaign_id}/html")
async def deposer_html(campaign_id: str, request: Request):
    acteur = _superadmin(request)
    c = _campagne(campaign_id)
    if c["status"] not in STATUTS_EDITABLES:
        raise HTTPException(status_code=409, detail=f"campagne verrouillée (« {c['status']} »)")
    html = ((await request.json()).get("html") or "")
    if not html.strip():
        raise HTTPException(status_code=422, detail="HTML vide")
    try:
        d = stockage.deposer(html.encode("utf-8"), "html", taille_max=5 * 1024 * 1024)
    except stockage.StockageErreur as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if d["sha256"] == c["html_hash"]:
        return {"ok": True, "inchange": True}
    pg.ecrire("""UPDATE campaigns SET html_storage_key = %(k)s, html_hash = %(h)s,
                        text_content = %(t)s, message_version = message_version + 1,
                        preflight_snapshot = NULL, updated_at = now()
                  WHERE id = %(c)s""",
              {"k": d["storage_key"], "h": d["sha256"], "t": sweego.html_vers_texte(html),
               "c": campaign_id})
    _audit(campaign_id, acteur, "message.updated", "Message HTML mis à jour",
           {"html_hash": d["sha256"], "liens": len(sweego.liens_du_html(html))})
    _recalculer_statut(campaign_id)
    return {"ok": True, "html_hash": d["sha256"]}


@router.get("/campaigns/{campaign_id}/html")
def lire_html(campaign_id: str, request: Request):
    _superadmin(request)
    c = _campagne(campaign_id)
    if not c["html_storage_key"]:
        return {"html": None}
    html = stockage.lire(c["html_storage_key"]).decode("utf-8", errors="replace")
    liens = sweego.liens_du_html(html)
    bas = html.lower()
    return {"html": html, "controles": {
        "desinscription": "unsub" in bas or "désinscri" in bas or "desinscri" in bas,
        "liens_http": [l for l in liens if l.lower().startswith("http://")],
        "nb_liens": len(liens),
    }}


# ── Cible CSV ────────────────────────────────────────────────────────────────

@router.post("/campaigns/{campaign_id}/csv")
async def deposer_csv(campaign_id: str, request: Request):
    """Dépôt du CSV : stockage + aperçu immédiat + job d'analyse. Rien n'est soumis à
    Mailnjoy ici."""
    acteur = _superadmin(request)
    c = _campagne(campaign_id)
    if c["status"] not in STATUTS_EDITABLES:
        raise HTTPException(status_code=409, detail=f"cible verrouillée (« {c['status']} »)")
    b = await request.json()
    try:
        donnees = base64.b64decode(b.get("contenu_base64") or "", validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(status_code=422, detail="fichier mal encodé") from e
    reglages = pg.ligne("SELECT max_csv_bytes FROM settings")
    try:
        d = stockage.deposer(donnees, "csv", taille_max=reglages["max_csv_bytes"])
    except stockage.StockageErreur as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    en_tete = b.get("en_tete")
    if en_tete is not None and not isinstance(en_tete, bool):
        en_tete = None
    apercu = analyze_csv.apercu(donnees, en_tete)
    nom = (b.get("filename") or "cible.csv")[:255]
    job = file.empiler(analyze_csv.JOB_TYPE, campaign_id=campaign_id,
                       payload={"storage_key": d["storage_key"], "original_filename": nom,
                                "en_tete": en_tete, "acteur": acteur},
                       idempotency_key=f"analyze:{campaign_id}:{d['sha256']}:{en_tete}",
                       priority=10)
    _audit(campaign_id, acteur, "target.uploaded", f"Fichier « {nom} » déposé",
           {"file_hash": d["sha256"], "taille": d["taille"], "en_tete": en_tete})
    return {"ok": True, "apercu": apercu, "job": job, "taille": d["taille"], "fichier": nom}


# ── Validation Mailnjoy ──────────────────────────────────────────────────────

@router.get("/campaigns/{campaign_id}/validation/estimation")
def estimation(campaign_id: str, request: Request):
    _superadmin(request)
    c = _campagne(campaign_id)
    n = 0
    if c["target_version_id"]:
        n = pg.valeur("""SELECT count(*) FROM recipients WHERE target_version_id = %(t)s
                           AND import_status = 'imported' AND eligibility_status = 'pending'""",
                      {"t": c["target_version_id"]}) or 0
    r = pg.ligne("SELECT validation_batch_size, mailnjoy_concurrency FROM settings")
    cr = mailnjoy.credit()
    # Débit mesuré le 2026-09-25 : ~1,55 adresse/s à 10 appels simultanés.
    par_s = 0.155 * max(1, int(r["mailnjoy_concurrency"]))
    return {"adresses": int(n), "credits_disponibles": cr.get("credit"),
            "credit_ok": bool(cr.get("ok")) and int(cr.get("credit") or 0) >= int(n),
            "lots": -(-int(n) // int(r["validation_batch_size"])) if n else 0,
            "duree_estimee_min": round(int(n) / par_s / 60) if n else 0,
            "statut": c["status"]}


@router.post("/campaigns/{campaign_id}/validation")
async def lancer_validation(campaign_id: str, request: Request):
    acteur = _superadmin(request)
    c = _campagne(campaign_id)
    b = await request.json()
    if b.get("confirme") is not True:
        raise HTTPException(status_code=422, detail="confirmation explicite requise")
    if c["status"] != "ready_for_validation":
        raise HTTPException(status_code=409,
                            detail=f"validation impossible depuis « {c['status']} »")
    attendu = estimation(campaign_id, request)["adresses"]
    if int(b.get("adresses") or -1) != attendu:
        raise HTTPException(status_code=409,
                            detail="la cible a changé depuis l'affichage : rechargez la page")
    job = file.empiler(validation.JOB_CREER, campaign_id=campaign_id,
                       payload={"acteur": acteur}, idempotency_key=f"creer_lots:{campaign_id}",
                       priority=5)
    _audit(campaign_id, acteur, "validation.requested",
           f"Validation Mailnjoy confirmée pour {attendu} adresses")
    return {"ok": True, "job": job}


@router.post("/campaigns/{campaign_id}/relancer")
def relancer(campaign_id: str, request: Request):
    """« Relancer les lots en erreur » : seuls les lots en échec et leurs jobs morts."""
    acteur = _superadmin(request)
    _campagne(campaign_id)
    n = pg.ecrire("""UPDATE validation_batches SET status = 'pending', error_code = NULL,
                            error_message = NULL
                      WHERE campaign_id = %(c)s AND status = 'failed'""", {"c": campaign_id})
    j = file.relancer_morts(campaign_id=campaign_id)
    _audit(campaign_id, acteur, "validation.retried", f"{n} lot(s) relancé(s)")
    return {"ok": True, "lots": n, "jobs": j}


@router.post("/campaigns/{campaign_id}/archiver")
def archiver(campaign_id: str, request: Request):
    acteur = _superadmin(request)
    c = _campagne(campaign_id)
    if c["status"] in ("validating_list", "scheduled", "sending"):
        raise HTTPException(status_code=409, detail="impossible d'archiver une campagne en cours")
    pg.ecrire("UPDATE campaigns SET status = 'archived', updated_at = now() WHERE id = %(c)s",
              {"c": campaign_id})
    _audit(campaign_id, acteur, "campaign.archived", "Campagne archivée")
    return {"ok": True}


@router.get("/campaigns/{campaign_id}/invalides")
def invalides(campaign_id: str, request: Request):
    """Échantillon d'adresses écartées, MASQUÉES — jamais la liste en clair."""
    _superadmin(request)
    c = _campagne(campaign_id)
    if not c["target_version_id"]:
        return {"lignes": []}
    lignes = pg.lignes("""SELECT original_row_number, email_normalized, import_status,
                                 validation_status, eligibility_reason
                            FROM recipients WHERE target_version_id = %(t)s
                             AND eligibility_status = 'excluded'
                           ORDER BY original_row_number LIMIT 200""",
                       {"t": c["target_version_id"]})
    for l in lignes:
        l["email_normalized"] = adresses.masquer(l["email_normalized"])
    return {"lignes": lignes}


# ── Envoi ────────────────────────────────────────────────────────────────────

@router.get("/profils")
def profils(request: Request):
    _superadmin(request)
    return {"profils": pg.lignes("""SELECT id, name, from_name, from_email, reply_to, sending_domain,
                                           verified_status, is_default, active
                                      FROM sender_profiles ORDER BY is_default DESC, name""")}


@router.post("/campaigns/{campaign_id}/preflight")
def lancer_preflight(campaign_id: str, request: Request):
    acteur = _superadmin(request)
    _campagne(campaign_id)
    try:
        return envoi.preflight(campaign_id, acteur)
    except ErreurDefinitive as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("/campaigns/{campaign_id}/envoyer")
async def autoriser_envoi(campaign_id: str, request: Request):
    """Le feu vert. Exige `confirme: true` : rien ne part sur un simple clic égaré."""
    acteur = _superadmin(request)
    _campagne(campaign_id)
    if (await request.json()).get("confirme") is not True:
        raise HTTPException(status_code=422, detail="confirmation explicite requise")
    try:
        return envoi.autoriser(campaign_id, acteur)
    except ErreurDefinitive as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("/campaigns/{campaign_id}/pause")
def mettre_en_pause(campaign_id: str, request: Request):
    """Aucun NOUVEAU lot ne part ; le lot en cours se termine."""
    acteur = _superadmin(request)
    n = pg.ecrire("""UPDATE campaigns SET status = 'paused', paused_at = now(), updated_at = now()
                      WHERE id = %(c)s AND status = 'sending'""", {"c": campaign_id})
    if not n:
        raise HTTPException(status_code=409, detail="la campagne n'est pas en cours d'envoi")
    _audit(campaign_id, acteur, "sending.paused", "Envoi mis en pause")
    return {"ok": True}


@router.post("/campaigns/{campaign_id}/stats")
def rafraichir_stats(campaign_id: str, request: Request):
    _superadmin(request)
    _campagne(campaign_id)
    try:
        return envoi.synchroniser(campaign_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"logs Sweego illisibles : {str(e)[:200]}") from e


# ── Désinscription publique ──────────────────────────────────────────────────

_PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{titre}</title>
<style>body{{font-family:system-ui,-apple-system,sans-serif;background:#f6f6f7;color:#222;
display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
main{{background:#fff;border:1px solid #e5e5e5;border-radius:14px;padding:36px 40px;max-width:440px;
text-align:center}}h1{{font-size:20px;margin:0 0 10px}}p{{color:#666;line-height:1.5;margin:0}}</style>
</head><body><main><h1>{titre}</h1><p>{texte}</p></main></body></html>"""


def _desinscrire(t: str) -> tuple[bool, str]:
    rid = desinscription.lire_jeton(t)
    if rid is None:
        return False, "Ce lien de désinscription n'est pas valide."
    r = pg.ligne("SELECT id, campaign_id, email_hash, email_normalized FROM recipients WHERE id = %(i)s",
                 {"i": rid})
    if not r:
        return False, "Ce lien de désinscription n'est plus valide."
    pg.ecrire("""INSERT INTO suppressions (email_hash, email_normalized, reason, source, scope, metadata)
                 VALUES (%(h)s, %(e)s, 'unsubscribe', 'lien', 'global', %(m)s::jsonb)
                 ON CONFLICT DO NOTHING""",
              {"h": r["email_hash"], "e": r["email_normalized"],
               "m": json.dumps({"campaign_id": str(r["campaign_id"]), "recipient_id": rid})})
    pg.ecrire("""UPDATE recipients SET unsubscribed_at = COALESCE(unsubscribed_at, now()),
                        updated_at = now() WHERE id = %(i)s""", {"i": rid})
    _audit(str(r["campaign_id"]), "désinscription", "unsubscribe",
           f"Désinscription de {adresses.masquer(r['email_normalized'])}")
    return True, ""


@public_router.get("/desinscription", response_class=HTMLResponse)
def desinscription_page(t: str = ""):
    ok, msg = _desinscrire(t)
    if ok:
        return _PAGE.format(titre="Vous êtes désinscrit(e)",
                            texte="Vous ne recevrez plus nos emails. Merci et à bientôt.")
    return HTMLResponse(_PAGE.format(titre="Lien invalide", texte=msg), status_code=400)


@public_router.post("/desinscription")
def desinscription_un_clic(t: str = ""):
    """RFC 8058 (bouton « Se désinscrire » de Gmail) : POST, sans interaction."""
    ok, msg = _desinscrire(t)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True}
