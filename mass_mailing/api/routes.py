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
import re
import html as html_lib
import json
import sys
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import adresses, mailnjoy, pg, stockage, sweego  # noqa: E402
from infra import adresses as adresses_mod  # noqa: E402
from jobs import analyze_csv, clics, envoi, file, validation  # noqa: E402
from jobs.file import ErreurDefinitive  # noqa: E402
from infra import controle_html, desinscription, domaines, harmonisation, parcours, redaction  # noqa: E402
from fastapi.responses import JSONResponse, HTMLResponse, Response  # noqa: E402

router = APIRouter(prefix="/api/mass-mailing", tags=["mass-mailing"])
# Sans session : le lien de désinscription est cliqué depuis une boîte mail.
# `/api/public/` est le préfixe que le middleware Cheffer laisse passer.
public_router = APIRouter(prefix="/api/public/mass-mailing", tags=["mass-mailing-public"])

STATUTS_EDITABLES = ("draft", "ready_for_validation", "validation_issue", "ready_to_schedule")
# Le message, l'objet et le mode d'envoi restent modifiables pendant la validation et
# tant que l'envoi n'est que programmé : l'assistant laisse avancer sans attendre
# Mailnjoy (Camille, 2026-09-25). Les contrôles sont refaits au départ.
STATUTS_MESSAGE_EDITABLE = STATUTS_EDITABLES + ("validating_list", "scheduled", "paused")


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


# ── Série quotidienne (courbes de l'accueil) ─────────────────────────────────

@router.get("/stats/serie")
def serie(request: Request, jours: int = 30):
    """Envois, livraisons, ouvertures et clics par jour (heure de Paris), toutes campagnes.
    Lecture seule : sert les courbes des cartes de l'accueil. Les jours sans rien valent 0."""
    _superadmin(request)
    jours = max(7, min(int(jours), 90))
    lignes = pg.lignes("""
        WITH j AS (SELECT generate_series((now() AT TIME ZONE 'Europe/Paris')::date - (%(n)s - 1),
                                          (now() AT TIME ZONE 'Europe/Paris')::date, '1 day')::date AS jour),
             e AS (SELECT (submitted_at AT TIME ZONE 'Europe/Paris')::date AS jour, count(*) n FROM recipients
                    WHERE submitted_at IS NOT NULL GROUP BY 1),
             l AS (SELECT (delivered_at AT TIME ZONE 'Europe/Paris')::date AS jour, count(*) n FROM recipients
                    WHERE delivered_at IS NOT NULL GROUP BY 1),
             o AS (SELECT (opened_at AT TIME ZONE 'Europe/Paris')::date AS jour, count(*) n FROM recipients
                    WHERE opened_at IS NOT NULL GROUP BY 1),
             c AS (SELECT (clicked_at AT TIME ZONE 'Europe/Paris')::date AS jour, count(*) n FROM recipients
                    WHERE clicked_at IS NOT NULL GROUP BY 1),
             -- Rebonds de MASS EMAIL (jobs/rebonds.py, classés par nous, pas l'étiquette Sweego).
             b AS (SELECT (at AT TIME ZONE 'Europe/Paris')::date AS jour,
                          count(DISTINCT email_hash) FILTER (WHERE famille = 'hard') hard,
                          count(DISTINCT email_hash) FILTER (WHERE famille = 'soft') soft
                     FROM rebonds WHERE origine = 'mass_email' GROUP BY 1),
             s AS (SELECT (occurred_at AT TIME ZONE 'Europe/Paris')::date AS jour, count(*) n FROM suppressions
                    WHERE scope = 'global' GROUP BY 1)
        SELECT j.jour, COALESCE(e.n, 0) envoyes, COALESCE(l.n, 0) livres,
               COALESCE(o.n, 0) ouverts, COALESCE(c.n, 0) cliques,
               COALESCE(b.hard, 0) hard, COALESCE(b.soft, 0) soft, COALESCE(s.n, 0) liste_noire
          FROM j LEFT JOIN e USING (jour) LEFT JOIN l USING (jour)
                 LEFT JOIN o USING (jour) LEFT JOIN c USING (jour)
                 LEFT JOIN b USING (jour) LEFT JOIN s USING (jour)
         ORDER BY j.jour""", {"n": jours})
    return {"jours": jours, "serie": [{**x, "jour": x["jour"].isoformat()} for x in lignes]}


# ── Campagnes ────────────────────────────────────────────────────────────────

# Entonnoir d'une campagne (Camille, 30/09) : importés → nettoyage Mailnjoy → autres exclusions →
# éligibles → envoyés → délivrés / non délivrés (hard, soft, refus liés à l'IP : jobs/rebonds.py).
# Chaque étape = la précédente moins ses pertes, pour que les chiffres se lisent de haut en bas.
ENTONNOIR_SQL = """
    SELECT count(*) FILTER (WHERE r.import_status = 'imported') AS importes,
           count(*) FILTER (WHERE r.import_status IN ('duplicate', 'invalid_syntax', 'empty')) AS rejetes_import,
           count(*) FILTER (WHERE r.eligibility_status = 'excluded' AND r.eligibility_reason IN ('risky', 'unknown')) AS mj_risquees,
           count(*) FILTER (WHERE r.eligibility_status = 'excluded' AND r.eligibility_reason IN ('invalid', 'disposable')) AS mj_invalides,
           count(*) FILTER (WHERE r.eligibility_status = 'excluded' AND r.eligibility_reason IN ('role', 'error')) AS mj_autres,
           count(*) FILTER (WHERE r.import_status = 'imported' AND r.eligibility_status = 'pending') AS mj_en_cours,
           count(*) FILTER (WHERE r.eligibility_reason = 'hors_cible_b2c') AS hors_cible,
           count(*) FILTER (WHERE r.eligibility_reason = 'envoye_en_test') AS deja_testes,
           count(*) FILTER (WHERE r.eligibility_reason = 'suppressed') AS liste_noire,
           count(*) FILTER (WHERE r.eligibility_reason LIKE 'preference%%') AS preferences,
           count(*) FILTER (WHERE r.eligibility_status = 'eligible') AS eligibles_envoi,
           count(*) FILTER (WHERE r.eligibility_status = 'eligible' AND r.send_status IN ('pending', 'queued')) AS en_attente,
           count(*) FILTER (WHERE r.send_status IN ('submitted', 'delivered', 'bounced')) AS envoyes_total,
           count(*) FILTER (WHERE r.send_status IN ('rejected', 'failed')) AS refus_sweego,
           count(*) FILTER (WHERE r.send_status = 'submitted' AND r.delivered_at IS NULL) AS en_transit,
           count(*) FILTER (WHERE r.delivered_at IS NOT NULL) AS delivres,
           count(*) FILTER (WHERE r.send_status = 'bounced' AND r.delivered_at IS NULL) AS non_delivres,
           -- Une seule famille par destinataire (revue du 30/09 : un soft puis un hard comptait deux fois).
           count(*) FILTER (WHERE r.send_status = 'bounced' AND fam.f = 'hard') AS nd_hard,
           count(*) FILTER (WHERE r.send_status = 'bounced' AND fam.f = 'soft') AS nd_soft,
           count(*) FILTER (WHERE r.send_status = 'bounced' AND fam.f = 'expediteur') AS nd_ip
      FROM recipients r
      LEFT JOIN LATERAL (SELECT b.famille AS f FROM rebonds b
                          WHERE r.send_status = 'bounced' AND b.email_hash = r.email_hash
                            AND b.campagne = 'mm-' || r.campaign_id::text AND b.famille IN ('hard', 'soft', 'expediteur')
                          ORDER BY CASE b.famille WHEN 'hard' THEN 1 WHEN 'soft' THEN 2 ELSE 3 END LIMIT 1) fam ON TRUE
     WHERE r.campaign_id = c.id AND r.target_version_id = c.target_version_id
"""


def _entonnoir(x: dict) -> dict:
    """Met l'entonnoir en forme (fonction pure, testée) : retenus = importés − écartés Mailnjoy."""
    ecartes = (x.get("mj_risquees") or 0) + (x.get("mj_invalides") or 0) + (x.get("mj_autres") or 0)
    autres = (x.get("hors_cible") or 0) + (x.get("deja_testes") or 0) + (x.get("liste_noire") or 0) + (x.get("preferences") or 0)
    nd = x.get("non_delivres") or 0
    return {
        "importes": x.get("importes") or 0, "rejetes_import": x.get("rejetes_import") or 0,
        "ecartes_mailnjoy": ecartes, "mj_risquees": x.get("mj_risquees") or 0, "mj_invalides": x.get("mj_invalides") or 0,
        "mj_autres": x.get("mj_autres") or 0, "mj_en_cours": x.get("mj_en_cours") or 0,
        "retenus_mailnjoy": (x.get("importes") or 0) - ecartes,
        "autres_exclusions": autres, "hors_cible": x.get("hors_cible") or 0, "deja_testes": x.get("deja_testes") or 0,
        "liste_noire": x.get("liste_noire") or 0, "preferences": x.get("preferences") or 0,
        "eligibles": x.get("eligibles_envoi") or 0, "en_attente": x.get("en_attente") or 0,
        "envoyes": x.get("envoyes_total") or 0, "refus_sweego": x.get("refus_sweego") or 0, "en_transit": x.get("en_transit") or 0,
        "delivres": x.get("delivres") or 0, "non_delivres": nd,
        "nd_hard": x.get("nd_hard") or 0, "nd_soft": x.get("nd_soft") or 0, "nd_ip": x.get("nd_ip") or 0,
        "nd_autre": max(0, nd - (x.get("nd_hard") or 0) - (x.get("nd_soft") or 0) - (x.get("nd_ip") or 0)),
    }


@router.get("/campaigns/{campaign_id}/entonnoir")
def entonnoir_campagne(campaign_id: str, request: Request):
    _superadmin(request)
    _campagne(campaign_id)
    x = pg.ligne("SELECT e.* FROM campaigns c LEFT JOIN LATERAL (" + ENTONNOIR_SQL + ") e ON TRUE WHERE c.id = %(c)s",
                 {"c": campaign_id})
    return _entonnoir(x or {})


@router.get("/campaigns")
def liste(request: Request, archives: bool = False):
    _superadmin(request)
    # JIT de PostgreSQL désactivé pour CETTE requête (revue du 30/09 : 964 ms de compilation pour 19 ms
    # d'exécution, le coût estimé dépassant jit_above_cost).
    with pg.connexion() as cur:
        cur.execute("SET LOCAL jit = off")
        cur.execute("""
        SELECT ent.*, c.id, c.internal_name, c.status, c.subject, c.dispatch_mode,
               c.created_at, c.updated_at, c.created_by, c.target_version,
               tv.original_filename, tv.unique_emails, tv.validation_eligible_count,
               tv.total_rows, fam.safe, fam.risky, fam.spam, fam.non_verifies,
               (SELECT count(*) FROM validation_batches v WHERE v.campaign_id = c.id) AS lots,
               (SELECT count(*) FROM validation_batches v
                 WHERE v.campaign_id = c.id AND v.status = 'completed') AS lots_valides,
               (SELECT COALESCE(sum(eligible_count), 0) FROM validation_batches v
                 WHERE v.campaign_id = c.id) AS eligibles,
               st.envoyes, st.livres, st.ouverts, st.cliques, st.rebonds, st.ouvertures_uniques, st.plaintes,
               st.debut_envoi, st.fin_envoi, c.scheduled_at,
               ev.summary AS derniere_activite, ev.created_at AS derniere_activite_le
          FROM campaigns c
          LEFT JOIN LATERAL (
               SELECT count(*) FILTER (WHERE r.send_status IN ('submitted','delivered','bounced')) AS envoyes,
                      count(*) FILTER (WHERE r.delivered_at IS NOT NULL) AS livres,
                      count(*) FILTER (WHERE r.opened_at IS NOT NULL) AS ouverts,
                      count(*) FILTER (WHERE r.clicked_at IS NOT NULL) AS cliques,
                      count(*) FILTER (WHERE r.bounced_at IS NOT NULL) AS rebonds,
                      -- Colonnes Début / Fin du tableau (Camille, 27/09) : premier et dernier mail parti.
                      min(r.submitted_at) AS debut_envoi, max(r.submitted_at) AS fin_envoi,
                      -- Mini-carte « Webmails » : ouvertures uniques hors robots, plaintes.
                      count(*) FILTER (WHERE r.send_status IN ('submitted','delivered','bounced') AND (r.opened_at IS NOT NULL AND NOT EXISTS (SELECT 1 FROM clicks k WHERE k.recipient_id = r.id
                                                                     AND k.verdict = 'robot'))) AS ouvertures_uniques,
                      count(*) FILTER (WHERE r.send_status IN ('submitted','delivered','bounced') AND (EXISTS (SELECT 1 FROM suppressions s WHERE s.reason = 'complaint'
                                         AND s.metadata->>'swg_uid' = r.sweego_message_id)
                            OR EXISTS (SELECT 1 FROM webhook_events w WHERE w.event_type ILIKE '%%complaint%%'
                                         AND w.campaign_id = r.campaign_id AND w.email_hash = r.email_hash))) AS plaintes
                 FROM recipients r WHERE r.campaign_id = c.id
                  AND r.target_version_id = c.target_version_id) st ON TRUE
          -- Familles Mailnjoy (consigne Camille 2026-09-25) : Safe = valides (rôle compris),
          -- Risky = risquées + inconnues, Spam = invalides + jetables (pièges compris).
          LEFT JOIN LATERAL (
               SELECT count(*) FILTER (WHERE r.validation_status IN ('valid','role')) AS safe,
                      count(*) FILTER (WHERE r.validation_status IN ('risky','unknown')) AS risky,
                      count(*) FILTER (WHERE r.validation_status IN ('invalid','disposable')) AS spam,
                      count(*) FILTER (WHERE r.validation_status IN ('pending','error')) AS non_verifies
                 FROM recipients r WHERE r.target_version_id = c.target_version_id
                  AND r.import_status = 'imported' AND r.eligibility_reason IS DISTINCT FROM 'suppressed') fam ON TRUE
          LEFT JOIN LATERAL (
               SELECT summary, created_at FROM campaign_events e
                WHERE e.campaign_id = c.id ORDER BY e.created_at DESC LIMIT 1) ev ON TRUE
          LEFT JOIN LATERAL (""" + ENTONNOIR_SQL + """) ent ON TRUE
          LEFT JOIN campaign_target_versions tv ON tv.id = c.target_version_id
         WHERE (c.status = 'archived') = %(archives)s
         ORDER BY c.created_at DESC
    """, {"archives": archives})
        lignes = [dict(r) for r in cur.fetchall()]
    # Les colonnes brutes de l'entonnoir sont regroupées sous « entonnoir » (les autres clés ne changent pas).
    brutes = set(re.findall(r"\bAS (\w+)", ENTONNOIR_SQL))
    return {"campaigns": [{**{k: v for k, v in x.items() if k not in brutes}, "entonnoir": _entonnoir(x)} for x in lignes]}


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
    public = b.get("audience")
    if public not in ("b2c", "b2b"):
        raise HTTPException(status_code=422, detail="choisissez le public : particuliers (B2C) ou professionnels (B2B)")
    # Valeurs par défaut de l'expéditeur : celles du profil par défaut, sur le
    # sous-domaine choisi par Camille (news.leclientroi.email, 2026-09-25).
    p = envoi.profil_defaut() or {}
    c = pg.ligne("""INSERT INTO campaigns (internal_name, subject, preheader, dispatch_mode, created_by,
                                           from_name, from_local, reply_to, sending_domains, audience)
                    VALUES (%(n)s, %(s)s, %(p)s, %(m)s, %(a)s, %(fn)s, %(fl)s, %(rt)s, %(sd)s, %(pu)s) RETURNING id""",
                 {"n": nom[:200], "s": (b.get("subject") or "").strip()[:250] or None,
                  "p": (b.get("preheader") or "").strip()[:250] or None, "m": mode, "a": acteur,
                  "fn": p.get("from_name"), "fl": (p.get("from_email") or "info@").split("@")[0] or "info",
                  "rt": p.get("reply_to"), "sd": ["news.leclientroi.email"], "pu": public})
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
    # L'expéditeur RÉEL (celui de la campagne, le profil ne servant que de valeur par
    # défaut) : c'est lui que l'écran doit montrer, pas le profil.
    exp = envoi.expediteur(c, profil) if profil or c.get("from_local") else None
    return {"campaign": c, "cible": tv, "lots": lots, "envois": envois, "jobs": jobs,
            "journal": journal, "decisions": decisions, "profil": profil, "expediteur": exp,
            "stats": envoi.statistiques(campaign_id),
            "progression": validation.progression(campaign_id),
            "parcours": parcours.calculer(campaign_id)}


@router.patch("/campaigns/{campaign_id}")
async def modifier(campaign_id: str, request: Request):
    acteur = _superadmin(request)
    c = _campagne(campaign_id)
    if c["status"] not in STATUTS_MESSAGE_EDITABLE:
        raise HTTPException(status_code=409, detail=f"campagne verrouillée (« {c['status']} »)")
    b = await request.json()
    champs = {k: (b.get(k) or "").strip()[:250] or None
              for k in ("internal_name", "subject", "preheader") if k in b}
    if "dispatch_mode" in b and b["dispatch_mode"] in ("progressive", "after_validation"):
        champs["dispatch_mode"] = b["dispatch_mode"]
    for k in ("from_name", "reply_to"):
        if k in b:
            champs[k] = (b.get(k) or "").strip()[:200] or None
    if "from_local" in b:
        loc = (b.get("from_local") or "").strip().lower()
        if loc and not re.fullmatch(r"[a-z0-9._+-]{1,64}", loc):
            raise HTTPException(status_code=422, detail="partie avant @ invalide")
        champs["from_local"] = loc or None
    if b.get("reply_to") and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", b["reply_to"].strip()):
        raise HTTPException(status_code=422, detail="adresse de réponse invalide")
    if "text_content" in b:
        champs["text_content"] = (b.get("text_content") or "")[:100000] or None
    if "campaign_type" in b and b["campaign_type"] in ("market", "newsletter"):
        champs["campaign_type"] = b["campaign_type"]
    if "audience" in b:
        if b["audience"] not in ("b2c", "b2b"):
            raise HTTPException(status_code=422, detail="public inconnu (b2c ou b2b)")
        champs["audience"] = b["audience"]
    if "sending_domains" in b:
        doms = [str(d).strip().lower() for d in (b.get("sending_domains") or []) if str(d).strip()]
        try:
            verifies = sweego.domaines_verifies()
        except Exception:  # noqa: BLE001
            verifies = None
        if verifies is not None and any(d not in verifies for d in doms):
            raise HTTPException(status_code=422, detail="domaine non vérifié chez Sweego")
        champs["sending_domains"] = doms or None
    if not champs:
        return {"ok": True}
    sets = ", ".join(f"{k} = %({k})s" for k in champs)
    pg.ecrire(f"UPDATE campaigns SET {sets}, preflight_snapshot = NULL, updated_at = now() "
              f"WHERE id = %(id)s", {**champs, "id": campaign_id})
    _audit(campaign_id, acteur, "campaign.updated", "Campagne modifiée", {"champs": list(champs)})
    if "audience" in champs and champs["audience"] != c.get("audience"):
        r = domaines.reevaluer(campaign_id)
        _audit(campaign_id, acteur, "campaign.audience",
               f"Public : {'particuliers (B2C)' if champs['audience'] == 'b2c' else 'professionnels (B2B)'}"
               f" — {r['exclues']} adresse(s) écartée(s), {r['reintegrees']} réintégrée(s)", r)
    _recalculer_statut(campaign_id)
    return {"ok": True}


def _recalculer_statut(campaign_id: str) -> None:
    """draft ↔ ready_for_validation selon que message ET cible sont présents."""
    pg.ecrire("""
        UPDATE campaigns c SET status = CASE
            WHEN tv.validation_eligible_count > 0 THEN 'ready_for_validation'
            ELSE 'draft' END, updated_at = now()
          FROM campaign_target_versions tv
         WHERE c.id = %(c)s AND tv.id = c.target_version_id
           AND c.status IN ('draft', 'ready_for_validation')
    """, {"c": campaign_id})


# ── Message HTML ─────────────────────────────────────────────────────────────

@router.post("/campaigns/{campaign_id}/dupliquer")
async def dupliquer(campaign_id: str, request: Request):
    """Copie une campagne SANS sa cible : message (HTML, objet, pré-en-tête, version
    texte), expéditeur, domaines, type, mode d'envoi et page de rappel. La copie repart en
    brouillon, sans fichier, sans validation, sans statistiques (Camille, 2026-09-26)."""
    acteur = _superadmin(request)
    c = _campagne(campaign_id)
    b = await request.json() if (await request.body()) else {}
    nom = (b.get("internal_name") or f"{c['internal_name']} (copie)").strip()[:200]
    n = pg.ligne("""INSERT INTO campaigns (internal_name, subject, preheader, text_content, dispatch_mode,
                                           created_by, from_name, from_local, reply_to, sending_domains,
                                           campaign_type, sender_profile_id, rappel, audience)
                    SELECT %(n)s, subject, preheader, text_content, dispatch_mode, %(a)s, from_name,
                           from_local, reply_to, sending_domains, campaign_type, sender_profile_id, rappel, audience
                      FROM campaigns WHERE id = %(c)s RETURNING id""", {"n": nom, "a": acteur, "c": campaign_id})
    nid = str(n["id"])
    if c.get("html_storage_key"):
        d = stockage.deposer(stockage.lire(c["html_storage_key"]), "html", taille_max=5 * 1024 * 1024)
        pg.ecrire("UPDATE campaigns SET html_storage_key = %(k)s, html_hash = %(h)s WHERE id = %(c)s",
                  {"k": d["storage_key"], "h": d["sha256"], "c": nid})
    _audit(nid, acteur, "campaign.created", f"Campagne « {nom} » créée par duplication de « {c['internal_name']} »",
           {"source": campaign_id})
    _audit(campaign_id, acteur, "campaign.duplicated", f"Dupliquée en « {nom} »", {"copie": nid})
    _recalculer_statut(nid)
    return {"id": nid}


@router.post("/campaigns/{campaign_id}/html")
async def deposer_html(campaign_id: str, request: Request):
    acteur = _superadmin(request)
    c = _campagne(campaign_id)
    if c["status"] not in STATUTS_MESSAGE_EDITABLE:
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
    # Tel qu'il partira : en-tête harmonisé (l'éditeur enregistre alors la version propre).
    html = harmonisation.harmoniser(html, preheader=c.get("preheader") or "",
                                    url_miroir=desinscription.url_miroir(campaign_id))[0]
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


@router.get("/campaigns/{campaign_id}/destinataires")
def destinataires(campaign_id: str, request: Request, page: int = 1, q: str = "", filtre: str = "tout"):
    """Les adresses importées, EN CLAIR, paginées (Camille, 2026-09-26 : voir ce qui a
    réellement été importé, sans doute possible). Superadmin seulement ; lecture seule."""
    _superadmin(request)
    c = _campagne(campaign_id)
    if not c["target_version_id"]:
        return {"total": 0, "par_page": 50, "page": 1, "lignes": [], "compte": {}}
    par_page = 50
    page = max(1, int(page))
    conds = ["target_version_id = %(t)s"]
    params: dict = {"t": c["target_version_id"]}
    if q.strip():
        conds.append("email_normalized ILIKE %(q)s")
        params["q"] = f"%{q.strip().lower()}%"
    if filtre == "retenues":
        conds.append("import_status = 'imported'")
    elif filtre == "ecartees":
        conds.append("(import_status <> 'imported' OR eligibility_status = 'excluded')")
    ou = " AND ".join(conds)
    total = pg.valeur(f"SELECT count(*) FROM recipients WHERE {ou}", params) or 0
    lignes = pg.lignes(f"""SELECT original_row_number AS ligne, email_normalized AS email, import_status,
                                  validation_status, eligibility_status, eligibility_reason, send_status
                             FROM recipients WHERE {ou}
                            ORDER BY original_row_number NULLS LAST, id
                            LIMIT %(l)s OFFSET %(o)s""", {**params, "l": par_page, "o": (page - 1) * par_page})
    compte = pg.ligne("""SELECT count(*) AS lignes,
                                count(*) FILTER (WHERE import_status = 'imported') AS retenues,
                                count(*) FILTER (WHERE import_status <> 'imported' OR eligibility_status = 'excluded') AS ecartees
                           FROM recipients WHERE target_version_id = %(t)s""", {"t": c["target_version_id"]})
    return {"total": total, "par_page": par_page, "page": page, "lignes": lignes, "compte": compte}


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


BAT_MAX_ADRESSES = 5


@router.post("/campaigns/{campaign_id}/bat")
def envoyer_bat(campaign_id: str, request: Request, corps: dict):
    """BAT : le message de la campagne, tel qu'il partira, à 1-5 adresses de test.

    Doc Sweego (skills/sweego/doc/api/send-send-post.api.md) : le champ `bat` n'existe
    que pour le SMS. Un BAT email est donc un `/send` réel — il part et compte dans le
    quota — UN appel par adresse (jamais de mail de groupe). Même HTML nettoyé, même
    version texte, même expéditeur, même pied de mail que l'envoi réel ; étiquette
    `mm-bat` à part pour ne pas fausser les statistiques, aucun destinataire créé."""
    acteur = _superadmin(request)
    c = _campagne(campaign_id)
    brutes = corps.get("adresses") or []
    if not isinstance(brutes, list):
        raise HTTPException(status_code=422, detail="adresses : une liste est attendue")
    adresses, refusees = [], []
    for b in brutes:
        e = adresses_mod.normaliser(str(b))
        (adresses if e and adresses_mod.syntaxe_valide(e) else refusees).append(e or str(b))
    adresses = list(dict.fromkeys(adresses))
    if refusees:
        raise HTTPException(status_code=422, detail="adresse(s) invalide(s) : " + ", ".join(refusees))
    if not adresses:
        raise HTTPException(status_code=422, detail="indiquez au moins une adresse")
    if len(adresses) > BAT_MAX_ADRESSES:
        raise HTTPException(status_code=422, detail=f"{BAT_MAX_ADRESSES} adresses au plus par BAT")
    if not (c.get("subject") or "").strip() or not c.get("html_storage_key"):
        raise HTTPException(status_code=409, detail="il faut un objet et un message HTML avant un BAT")
    profil = pg.ligne("SELECT * FROM sender_profiles WHERE id = %(p)s",
                      {"p": c["sender_profile_id"]}) if c.get("sender_profile_id") else envoi.profil_defaut()
    if not envoi.expediteur(c, profil):
        raise HTTPException(status_code=409, detail="expéditeur non configuré (étape Message)")
    html = sweego.nettoyer_html(stockage.lire(c["html_storage_key"]).decode("utf-8", "replace"))
    html = harmonisation.harmoniser(html, preheader=c.get("preheader") or "",
                                    url_miroir=desinscription.url_miroir(campaign_id))[0]
    texte = (c.get("text_content") or "").strip() or sweego.html_vers_texte(html)
    resultats = []
    for e in adresses:
        exp = envoi.expediteur(c, profil, adresses_mod.hacher(e))
        corps_html = desinscription.pied_de_mail(html, 0, exp["from_name"],
                                                 raison_sociale=exp.get("raison_sociale"),
                                                 adresse=exp.get("adresse_postale"))
        if (c.get("rappel") or {}).get("actif"):
            # Comme l'envoi réel ; destinataire 0 = réponses marquées « test ».
            corps_html = rappel_mod.envelopper_liens(corps_html, campaign_id, 0, (c.get("rappel") or {}).get("redirection") or "",
                                                     email=e)
        # Aligné sur l'envoi réel (27/09) : badge Cheffer (lien piège visible), lignes du pied en
        # version texte, en-tête List-Unsubscribe one-click. Destinataire 0 = liens de test.
        piege = bool(clics.regles().get("piege_actif", True))
        if piege:
            corps_html = clics.ajouter_piege(corps_html, 0)
        r = sweego.envoyer_un(destinataire=e, subject=c["subject"],
                              html_str=corps_html,
                              texte=texte + desinscription.texte_pied(0) + (clics.texte_piege(0) if piege else ""),
                              expediteur=exp, campagne="mm-bat", tags=["mm-bat"],
                              url_desinscription=desinscription.url(0))
        resultats.append({"adresse": e, "ok": bool(r.get("ok")), "erreur": r.get("erreur"),
                          "de": exp["from_email"]})
    _audit(campaign_id, acteur, "bat.sent",
           f"BAT envoyé à {sum(x['ok'] for x in resultats)}/{len(resultats)} adresse(s)",
           {"resultats": resultats})
    return {"resultats": resultats}


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
    if rid == 0:
        return True, ""          # lien d'un BAT (destinataire 0) : aucun effet, on peut tout essayer
    r = pg.ligne("SELECT id, campaign_id, email_hash, email_normalized FROM recipients WHERE id = %(i)s",
                 {"i": rid})
    if not r:
        return False, "Ce lien de désinscription n'est plus valide."
    pg.ecrire("""INSERT INTO suppressions (email_hash, email_normalized, reason, source, scope, metadata)
                 VALUES (%(h)s, %(e)s, 'unsubscribe', 'lien', 'global', %(m)s::jsonb)
                 """ + pg.SUPPRESSION_SUR_CONFLIT,
              {"h": r["email_hash"], "e": r["email_normalized"],
               "m": json.dumps({"campaign_id": str(r["campaign_id"]), "recipient_id": rid})})
    pg.ecrire("""UPDATE recipients SET unsubscribed_at = COALESCE(unsubscribed_at, now()),
                        updated_at = now() WHERE id = %(i)s""", {"i": rid})
    _audit(str(r["campaign_id"]), "désinscription", "unsubscribe",
           f"Désinscription de {adresses.masquer(r['email_normalized'])}")
    return True, ""


@public_router.get("/desinscription", response_class=HTMLResponse)
def desinscription_page(t: str = ""):
    """Affiche une CONFIRMATION, ne désinscrit pas : les scanners de sécurité des entreprises
    (Defender Safe Links, Proofpoint, Mimecast…) ouvrent tous les liens d'un mail, un GET qui
    désinscrit les ferait désinscrire à la place du destinataire (vu le 26/09 : BNP Paribas)."""
    if desinscription.lire_jeton(t) is None:
        return HTMLResponse(_PAGE.format(titre="Lien invalide",
                                         texte="Ce lien de désinscription n'est pas valide."), status_code=400)
    bouton = (f'<form method="post" action="?t={html_lib.escape(t)}" style="margin-top:22px">'
              '<button type="submit" style="background:#111;color:#fff;border:0;border-radius:10px;'
              'padding:12px 22px;font-size:15px;cursor:pointer">Confirmer ma désinscription</button></form>')
    return _PAGE.format(titre="Se désinscrire ?",
                        texte="Vous ne recevrez plus nos emails." + bouton)


@public_router.post("/desinscription", response_class=HTMLResponse)
def desinscription_un_clic(t: str = ""):
    """RFC 8058 (bouton « Se désinscrire » de Gmail/Outlook, POST sans interaction) ET bouton
    « Confirmer » de la page ci-dessus : c'est le POST, et lui seul, qui désinscrit. Idempotent."""
    ok, msg = _desinscrire(t)
    if not ok:
        return HTMLResponse(_PAGE.format(titre="Lien invalide", texte=msg), status_code=400)
    return _PAGE.format(titre="Vous êtes désinscrit(e)",
                        texte="Vous ne recevrez plus nos emails. Merci et à bientôt.")


# ── Planification ────────────────────────────────────────────────────────────

@router.post("/campaigns/{campaign_id}/planifier")
async def planifier(campaign_id: str, request: Request):
    """Programme l'envoi à `date` (ISO, fuseau inclus), ou tout de suite si `date` est nul.
    Les contrôles avant envoi sont refaits maintenant ET au moment du départ."""
    acteur = _superadmin(request)
    c = _campagne(campaign_id)
    b = await request.json()
    from datetime import datetime, timezone
    quand = None
    if b.get("date"):
        try:
            quand = datetime.fromisoformat(str(b["date"]).replace("Z", "+00:00"))
        except ValueError as e:
            raise HTTPException(status_code=422, detail="date illisible") from e
        if quand.tzinfo is None:
            raise HTTPException(status_code=422, detail="la date doit porter son fuseau horaire")
        if quand <= datetime.now(timezone.utc):
            raise HTTPException(status_code=422, detail="la date est déjà passée")
    if c["status"] not in ("ready_to_schedule", "scheduled", "paused", "validating_list"):
        raise HTTPException(status_code=409, detail=f"programmation impossible depuis « {c['status']} »")
    snap = envoi.preflight(campaign_id, acteur)
    if not snap.get("ok"):
        raise HTTPException(status_code=409, detail="contrôles avant envoi bloqués : " + ", ".join(
            x["libelle"] for x in snap["controles"] if x["bloquant"] and not x["ok"]))
    if quand is None:
        try:
            return {**envoi.autoriser(campaign_id, acteur), "immediat": True}
        except ErreurDefinitive as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
    pg.ecrire("""UPDATE campaigns SET status = 'scheduled', scheduled_at = %(q)s, updated_at = now()
                  WHERE id = %(c)s""", {"q": quand, "c": campaign_id})
    _audit(campaign_id, acteur, "sending.scheduled", f"Envoi programmé le {quand.isoformat()}")
    return {"ok": True, "scheduled_at": quand.isoformat()}


@router.post("/campaigns/{campaign_id}/deplanifier")
def deplanifier(campaign_id: str, request: Request):
    acteur = _superadmin(request)
    c = _campagne(campaign_id)
    if c["status"] != "scheduled":
        raise HTTPException(status_code=409, detail="aucun envoi programmé")
    en_validation = pg.valeur("""SELECT count(*) FROM validation_batches WHERE campaign_id = %(c)s
                                   AND status IN ('pending','running','failed')""", {"c": campaign_id})
    pg.ecrire("""UPDATE campaigns SET status = %(s)s, scheduled_at = NULL, updated_at = now()
                  WHERE id = %(c)s""",
              {"s": "validating_list" if en_validation else "ready_to_schedule", "c": campaign_id})
    _audit(campaign_id, acteur, "sending.unscheduled", "Programmation annulée")
    return {"ok": True}


# ── Contrôle du message ──────────────────────────────────────────────────────

@router.post("/campaigns/{campaign_id}/html/analyse")
async def analyser_html(campaign_id: str, request: Request):
    """Analyse complète d'un HTML importé : corrections sûres + problèmes restants.
    N'enregistre RIEN : l'écran montre la carte, puis enregistre `html_corrige`."""
    _superadmin(request)
    c = _campagne(campaign_id)
    b = await request.json()
    profil = envoi.profil_defaut() if not c["sender_profile_id"] else pg.ligne(
        "SELECT * FROM sender_profiles WHERE id = %(p)s", {"p": c["sender_profile_id"]})
    import asyncio
    return await asyncio.to_thread(
        controle_html.analyser, b.get("html") or "",
        objet=b.get("objet") if b.get("objet") is not None else (c["subject"] or ""),
        preheader=b.get("preheader") if b.get("preheader") is not None else (c["preheader"] or ""),
        expediteur=profil or {}, url_miroir=desinscription.url_miroir(campaign_id),
        tester_liens=b.get("tester_liens", True), rappel=c.get("rappel"))


@public_router.get("/vue", response_class=HTMLResponse)
def page_miroir(c: str = ""):
    """« Voir la version en ligne » : le message tel qu'envoyé, sans le pied personnel."""
    cid = desinscription.lire_jeton_miroir(c)
    camp = pg.ligne("SELECT html_storage_key, preheader FROM campaigns WHERE id = %(c)s", {"c": cid}) if cid else None
    if not camp or not camp["html_storage_key"]:
        return HTMLResponse(_PAGE.format(titre="Message introuvable",
                                         texte="Ce lien n'est pas ou plus valide."), status_code=404)
    html = harmonisation.harmoniser(stockage.lire(camp["html_storage_key"]).decode("utf-8", "replace"),
                                    preheader=camp.get("preheader") or "", url_miroir=desinscription.url_miroir(cid))[0]
    return HTMLResponse(html, headers={"X-Robots-Tag": "noindex"})


@router.get("/domaines")
def lister_domaines(request: Request):
    """Sous-domaines déclarés chez Sweego ; `cheffer` = celui qu'utilise le cold email."""
    _superadmin(request)
    try:
        doms = sweego.domaines(force=True)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Sweego injoignable : {str(e)[:150]}") from e
    cheffer = sweego._env("SWEEGO_DOMAIN", "")
    return {"domaines": [{**d, "cheffer": d["domain"] == cheffer} for d in doms]}


@router.get("/campaigns/{campaign_id}/sweego/champs")
def champs_sweego(campaign_id: str, request: Request):
    """La requête exacte qu'enverrait un vrai mail, contrôlée champ par champ contre la
    doc Sweego (Body parameters). Rien n'est envoyé."""
    _superadmin(request)
    c = _campagne(campaign_id)
    profil = envoi.profil_defaut() if not c["sender_profile_id"] else pg.ligne(
        "SELECT * FROM sender_profiles WHERE id = %(p)s", {"p": c["sender_profile_id"]})
    exp = envoi.expediteur(c, profil)
    if not exp:
        return {"champs": [], "erreur": "expéditeur non configuré"}
    essai = sweego.envoyer_un(destinataire="destinataire@example.com", subject=c["subject"] or "",
                              html_str="<p>…</p>" if c["html_storage_key"] else "", texte="…",
                              expediteur={**exp, "_corps_seulement": True},
                              campagne=f"mm-{campaign_id}", tags=[envoi.etiquette(campaign_id)])
    corps = essai.get("corps")
    if not corps:   # refusé par le contrôle : on reconstruit pour montrer QUELS champs
        from copy import deepcopy
        corps = {"channel": "email", "provider": "sweego", "campaign-type": exp["campaign_type"],
                 "campaign-id": f"mm-{campaign_id}", "campaign-tags": [envoi.etiquette(campaign_id)],
                 "subject": c["subject"] or "", "from": {"email": exp["from_email"], "name": exp["from_name"]},
                 "recipients": [{"email": "destinataire@example.com"}],
                 "message-html": "<p>…</p>" if c["html_storage_key"] else "", "message-txt": "…",
                 "force_inline_style": True, "dry-run": False}
        if exp.get("reply_to"):
            corps["reply-to"] = {"email": exp["reply_to"]}
    try:
        verifies = sweego.domaines_verifies()
    except Exception:  # noqa: BLE001
        verifies = None
    return {"champs": sweego.valider_corps(corps, verifies), "from": exp["from_email"],
            "domaines": c["sending_domains"] or []}


@router.post("/campaigns/{campaign_id}/redaction/proposer")
async def proposer_redaction(campaign_id: str, request: Request):
    """Objet (+2 variantes), pré-en-tête et version texte proposés à partir du HTML.
    Rien n'est enregistré : l'écran propose, l'utilisateur garde ou modifie."""
    acteur = _superadmin(request)
    c = _campagne(campaign_id)
    b = await request.json()
    html = b.get("html") or (stockage.lire(c["html_storage_key"]).decode("utf-8", "replace")
                             if c["html_storage_key"] else "")
    if not html.strip():
        raise HTTPException(status_code=422, detail="importez d'abord le message HTML")
    exp = envoi.expediteur(c, envoi.profil_defaut())
    import asyncio
    try:
        r = await asyncio.to_thread(redaction.proposer, html,
                                    expediteur=f"{exp['from_name']} <{exp['from_email']}>" if exp else "",
                                    objet_actuel=c["subject"] or "")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"proposition impossible : {str(e)[:200]}") from e
    _audit(campaign_id, acteur, "message.proposal", "Objet, pré-en-tête et version texte proposés",
           {"modele": r.get("modele"), "jetons": r.get("usage")})
    return r


# ── Clics ────────────────────────────────────────────────────────────────────

@router.get("/campaigns/{campaign_id}/clics")
def clics_campagne(campaign_id: str, request: Request, robots: bool = False):
    _superadmin(request)
    _campagne(campaign_id)
    clics.traiter()                         # ce qui vient d'arriver, sans attendre le worker
    lignes = clics.lignes_export(campaign_id, inclure_robots=robots)
    detail = pg.lignes("""SELECT k.clicked_at, r.email_normalized AS email, k.url, k.type_lien, k.ip,
                                 k.user_agent, k.verdict, k.raisons, k.secondes_depuis_envoi
                            FROM clicks k LEFT JOIN recipients r ON r.id = k.recipient_id
                           WHERE k.campaign_id = %(c)s ORDER BY k.clicked_at DESC LIMIT 500""", {"c": campaign_id})
    return {"synthese": clics.synthese(campaign_id), "destinataires": lignes, "detail": detail}


@router.get("/campaigns/{campaign_id}/clics.csv")
def clics_csv(campaign_id: str, request: Request, robots: bool = False):
    acteur = _superadmin(request)
    _campagne(campaign_id)
    _audit(campaign_id, acteur, "export.clicks", "Export des clics téléchargé" + (" (avec robots)" if robots else ""))
    return Response(clics.csv_clics(campaign_id, robots), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="clics-{campaign_id[:8]}.csv"'})


@router.post("/campaigns/{campaign_id}/clics/envoyer")
async def clics_envoyer(campaign_id: str, request: Request):
    """Envoie à une adresse un lien de téléchargement signé, valable 7 jours."""
    acteur = _superadmin(request)
    c = _campagne(campaign_id)
    b = await request.json()
    dest = (b.get("email") or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", dest):
        raise HTTPException(status_code=422, detail="adresse invalide")
    lien = (f"{desinscription.BASE_PUBLIQUE}/api/public/mass-mailing/export?t="
            f"{clics.jeton_export(campaign_id, bool(b.get('robots')))}")
    exp = envoi.expediteur(c, envoi.profil_defaut())
    html = (f"<p>Bonjour,</p><p>L'export des clics de la campagne « {c['internal_name']} » est prêt.</p>"
            f'<p><a href="{lien}">Télécharger le fichier (CSV)</a></p>'
            "<p>Le lien est valable 7 jours. Seuls les clics humains sont inclus"
            + (", robots compris avec la raison de leur exclusion" if b.get("robots") else "") + ".</p>")
    r = sweego.envoyer_un(destinataire=dest, subject=f"Export des clics — {c['internal_name']}",
                          html_str=html, texte=f"Export des clics : {lien} (valable 7 jours)",
                          expediteur={**exp, "campaign_type": "market"}, campagne="mm-export", tags=["mm-export"])
    if not r.get("ok"):
        raise HTTPException(status_code=502, detail=r.get("erreur"))
    _audit(campaign_id, acteur, "export.clicks_sent", f"Lien d'export des clics envoyé à {adresses.masquer(dest)}")
    return {"ok": True}


# ── Surveillance HetrixTools (27/09) : badges de la page d'accueil + CRUD des moniteurs ──

def _hetrix(fn, *args):
    from infra import hetrix
    try:
        return fn(*args)
    except hetrix.ErreurHetrix as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/stats/rebonds")
def stats_rebonds(request: Request):
    """Soft / hard bounces (jobs/rebonds.py) : Mass Email, tout le compte Sweego par émetteur, liste noire globale."""
    _superadmin(request)
    from jobs import rebonds
    par = pg.lignes("""SELECT origine, famille, count(DISTINCT email_hash) AS n FROM rebonds
                        WHERE famille <> 'technique' GROUP BY 1, 2""")
    out: dict = {}
    for x in par:
        out.setdefault(x["origine"], {"hard": 0, "soft": 0, "expediteur": 0})[x["famille"]] = x["n"]
    liste = {x["reason"]: x["n"] for x in pg.lignes(
        "SELECT reason, count(*) n FROM suppressions WHERE scope = 'global' GROUP BY 1")}
    envoyes = pg.valeur("SELECT count(*) FROM recipients WHERE submitted_at IS NOT NULL") or 0
    return {"mass_email": {**out.get("mass_email", {"hard": 0, "soft": 0, "expediteur": 0}), "envoyes": envoyes},
            "compte_sweego": out, "liste_noire": {"total": sum(liste.values()), **liste},
            "maj": pg.valeur("SELECT max(at) FROM rebonds")}


@router.get("/campaigns/{campaign_id}/rebonds")
def rebonds_campagne(campaign_id: str, request: Request):
    _superadmin(request)
    _campagne(campaign_id)
    from jobs import rebonds
    return rebonds.stats_campagne(campaign_id)


@router.get("/campaigns/{campaign_id}/risque")
def risque_campagne(campaign_id: str, request: Request, restants: bool = True):
    """Agent « adresses à risque » : probabilité de hard bounce par destinataire (lecture seule)."""
    _superadmin(request)
    _campagne(campaign_id)
    from jobs import risque_adresses
    r = risque_adresses.scorer_campagne(campaign_id, restants)
    r["detail"] = r.get("detail", [])[:200]
    return r


@router.get("/campaigns/{campaign_id}/reputation")
def reputation_campagne(campaign_id: str, request: Request):
    """Badge « Réputation d'envoi » : IP Sweego + domaine(s) d'envoi de la campagne vs listes noires."""
    _superadmin(request)
    c = _campagne(campaign_id)
    from infra import hetrix
    doms = c.get("sending_domains") or []
    if not doms:
        exp = envoi.expediteur(c, envoi.profil_defaut())
        doms = [exp["from_email"].split("@")[1]] if exp else []
    return hetrix.reputation_envoi(doms)


@router.get("/campaigns/{campaign_id}/routage")
def routage_campagne(campaign_id: str, request: Request):
    """Bloc « Routage intelligent » de la fiche : vagues, réserve par messagerie, prochaine vague."""
    _superadmin(request)
    _campagne(campaign_id)
    from jobs import routage
    return routage.etat(campaign_id)


@router.get("/capacite")
def capacite_envoi(request: Request):
    """Onglet « Capacité » : max/jour et max/heure APPRIS par IP d'envoi et par messagerie
    (skill pilotage-delivrabilite, jobs/capacite.py)."""
    _superadmin(request)
    from jobs import capacite
    return capacite.tableau()


@router.get("/capacite/decisions")
def capacite_decisions(request: Request, cle: str = "", limite: int = 20):
    _superadmin(request)
    return {"decisions": pg.lignes("""SELECT at, decision, etat, ancien, nouveau, motif, confiance, texte
                                        FROM capacite_decisions WHERE cle = %(c)s ORDER BY at DESC LIMIT %(l)s""",
                                   {"c": cle, "l": max(1, min(100, limite))})}


@router.get("/surveillance")
def surveillance(request: Request):
    _superadmin(request)
    from infra import hetrix
    return _hetrix(hetrix.resume)


@router.get("/surveillance/uptime/{monitor_id}")
def surveillance_detail(monitor_id: str, request: Request):
    _superadmin(request)
    from infra import hetrix
    if not re.fullmatch(r"[A-Za-z0-9]{8,64}", monitor_id):
        raise HTTPException(status_code=422, detail="identifiant de moniteur invalide")
    return _hetrix(hetrix.detail_uptime, monitor_id)


def _corps_site(b: dict) -> tuple[str, str, str, str]:
    nom = re.sub(r"[^A-Za-z0-9 .\-]", "", (b.get("nom") or "").strip())[:60]
    url = (b.get("url") or "").strip()
    if not nom or not re.fullmatch(r"https?://[^\s]{4,500}", url):
        raise HTTPException(status_code=422, detail="nom (lettres, chiffres, espaces, points, tirets) et URL http(s) requis")
    codes = (b.get("codes") or "200").strip()
    if not re.fullmatch(r"\d{3}(,\d{3})*", codes):
        raise HTTPException(status_code=422, detail="codes HTTP : ex. 200 ou 200,301")
    return nom, url, (b.get("mot_cle") or "").strip()[:128], codes


@router.post("/surveillance/uptime")
async def surveillance_ajouter(request: Request):
    acteur = _superadmin(request)
    from infra import hetrix
    nom, url, mot, codes = _corps_site(await request.json())
    r = _hetrix(hetrix.ajouter_site, nom, url, mot, codes)
    _audit_global(acteur, "surveillance.ajout", f"Moniteur « {nom} » ajouté ({url})")
    return r


@router.put("/surveillance/uptime/{monitor_id}")
async def surveillance_modifier(monitor_id: str, request: Request):
    acteur = _superadmin(request)
    from infra import hetrix
    nom, url, mot, codes = _corps_site(await request.json())
    r = _hetrix(hetrix.modifier_site, monitor_id, nom, url, mot, codes)
    _audit_global(acteur, "surveillance.modification", f"Moniteur « {nom} » modifié")
    return r


@router.delete("/surveillance/uptime/{monitor_id}")
def surveillance_supprimer(monitor_id: str, request: Request):
    acteur = _superadmin(request)
    from infra import hetrix
    r = _hetrix(hetrix.supprimer_uptime, monitor_id)
    _audit_global(acteur, "surveillance.suppression", f"Moniteur {monitor_id} supprimé")
    return r


@router.post("/surveillance/blacklist")
async def surveillance_blacklist_ajouter(request: Request):
    acteur = _superadmin(request)
    from infra import hetrix
    b = await request.json()
    cible = (b.get("cible") or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9.\-]{3,253}|\d{1,3}(\.\d{1,3}){3}", cible):
        raise HTTPException(status_code=422, detail="cible : un nom de domaine ou une adresse IPv4")
    r = _hetrix(hetrix.ajouter_blacklist, cible, (b.get("libelle") or "").strip()[:60])
    _audit_global(acteur, "surveillance.blacklist", f"Surveillance liste noire ajoutée : {cible}")
    return r


@router.delete("/surveillance/blacklist/{cible}")
def surveillance_blacklist_supprimer(cible: str, request: Request):
    acteur = _superadmin(request)
    from infra import hetrix
    r = _hetrix(hetrix.supprimer_blacklist, cible)
    _audit_global(acteur, "surveillance.blacklist", f"Surveillance liste noire retirée : {cible}")
    return r


def _audit_global(acteur: str, evenement: str, resume: str) -> None:
    """Journal hors campagne (la table d'audit exige une campagne) : journal du serveur."""
    import logging
    logging.getLogger("mass_mailing").info("%s %s : %s", acteur, evenement, resume)


@router.get("/campaigns/{campaign_id}/clics/score")
def score_clics_campagne(campaign_id: str, request: Request):
    """Score anti-robot EN TEST (double calcul, jobs/score_clics.py) : comparaison avec l'ancien
    verdict et détail par destinataire (adresse masquée). N'affecte aucun export client."""
    _superadmin(request)
    _campagne(campaign_id)
    from jobs import score_clics
    lignes = pg.lignes("""SELECT s.recipient_id, s.score, s.statut, s.raisons, s.version_regles, s.calcule_at,
                                 r.email_normalized,
                                 CASE WHEN bool_or(k.verdict = 'humain') THEN 'humain'
                                      WHEN bool_or(k.verdict = 'suspect') THEN 'suspect'
                                      WHEN bool_or(k.verdict = 'robot') THEN 'robot' ELSE 'sans clic' END AS ancien
                            FROM click_scores s JOIN recipients r ON r.id = s.recipient_id
                            LEFT JOIN clicks k ON k.recipient_id = s.recipient_id AND k.campaign_id = s.campaign_id
                           WHERE s.campaign_id = %(c)s
                           GROUP BY s.recipient_id, s.score, s.statut, s.raisons, s.version_regles, s.calcule_at, r.email_normalized
                           ORDER BY s.score""", {"c": campaign_id})
    return {"version": score_clics.VERSION,
            "destinataires": [{"adresse": adresses_mod.masquer(x["email_normalized"]), "score": x["score"],
                               "statut": x["statut"], "raisons": x["raisons"], "ancien": x["ancien"],
                               "calcule_at": x["calcule_at"]} for x in lignes]}


@router.get("/campaigns/{campaign_id}/webmails")
def webmails_campagne(campaign_id: str, request: Request):
    """Compteurs PAR DOMAINE destinataire (envoyés, délivrés, ouvertures uniques hors robots,
    plaintes) pour le classement des webmails : le regroupement Gmail / Outlook / Orange…
    et le classement se font dans l'interface (_webmails.ts, testé). Aucune adresse renvoyée."""
    _superadmin(request)
    c = _campagne(campaign_id)
    lignes = pg.lignes(f"""
        SELECT split_part(r.email_normalized, '@', 2) AS domaine,
               count(*) AS sent,
               count(*) FILTER (WHERE r.delivered_at IS NOT NULL) AS delivered,
               count(*) FILTER (WHERE (r.opened_at IS NOT NULL AND NOT EXISTS (SELECT 1 FROM clicks k WHERE k.recipient_id = r.id
                                                                     AND k.verdict = 'robot'))) AS unique_opens,
               count(*) FILTER (WHERE (EXISTS (SELECT 1 FROM suppressions s WHERE s.reason = 'complaint'
                                         AND s.metadata->>'swg_uid' = r.sweego_message_id)
                            OR EXISTS (SELECT 1 FROM webhook_events w WHERE w.event_type ILIKE '%%complaint%%'
                                         AND w.campaign_id = r.campaign_id AND w.email_hash = r.email_hash))) AS complaints
          FROM recipients r
         WHERE r.campaign_id = %(c)s AND r.send_status IN ('submitted', 'delivered', 'bounced')
         GROUP BY 1 ORDER BY 2 DESC""", {"c": campaign_id})
    return {"campaign": {"id": str(c["id"]), "internal_name": c["internal_name"], "subject": c["subject"],
                          "started_at": c.get("started_at")},
            "domaines": lignes}


@router.get("/campaigns/{campaign_id}/domaines")
def domaines_campagne(campaign_id: str, request: Request):
    """Domaines de la cible, classés grand public / entreprise / administration (contrôle B2C)."""
    _superadmin(request)
    _campagne(campaign_id)
    return domaines.repartition(campaign_id)


@router.get("/reglages/domaines")
def regles_domaines(request: Request):
    _superadmin(request)
    return {**domaines.regles(), "grand_public_integres": sorted(domaines.GRAND_PUBLIC)}


@router.put("/reglages/domaines")
async def maj_regles_domaines(request: Request):
    """Reclasse un domaine : {"domaine": "x.fr", "classe": "grand_public"|"entreprise"|null}
    (null = retour à la règle automatique). Si `campaign_id` est donné, sa cible est réévaluée."""
    acteur = _superadmin(request)
    b = await request.json()
    d = (b.get("domaine") or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9.-]+\.[a-z0-9-]{2,}", d):
        raise HTTPException(status_code=422, detail="nom de domaine invalide")
    classe = b.get("classe")
    if classe not in ("grand_public", "entreprise", None):
        raise HTTPException(status_code=422, detail="classe inconnue")
    r = domaines.regles()
    r["grand_public"] = [x for x in r["grand_public"] if x != d] + ([d] if classe == "grand_public" else [])
    r["entreprise"] = [x for x in r["entreprise"] if x != d] + ([d] if classe == "entreprise" else [])
    pg.ecrire("UPDATE settings SET domain_rules = %(r)s::jsonb, updated_at = now(), updated_by = %(a)s",
              {"r": json.dumps(r), "a": acteur})
    res = {**r}
    if b.get("campaign_id"):
        c = _campagne(b["campaign_id"])
        res["reevaluation"] = domaines.reevaluer(str(c["id"]))
        _audit(str(c["id"]), acteur, "domaines.regle",
               f"{d} classé « {classe or 'automatique'} » — {res['reevaluation']['exclues']} écartée(s), "
               f"{res['reevaluation']['reintegrees']} réintégrée(s)", {"domaine": d, "classe": classe})
        _recalculer_statut(str(c["id"]))
    return res


@router.get("/reglages/clics")
def regles_clics(request: Request):
    _superadmin(request)
    return clics.regles()


@router.put("/reglages/clics")
async def maj_regles_clics(request: Request):
    acteur = _superadmin(request)
    b = await request.json()
    actuelles = clics.regles()
    for k in ("piege_actif", "proxy_sweego", "user_agent_vide"):
        if k in b:
            actuelles[k] = bool(b[k])
    for k, lo, hi in (("piege_fenetre_s", 0, 3600), ("delai_min_s", 0, 3600), ("rafale_liens", 2, 50), ("rafale_fenetre_s", 1, 600)):
        if k in b:
            actuelles[k] = max(lo, min(hi, int(b[k])))
    if "sans_ouverture" in b and b["sans_ouverture"] in ("suspect", "humain"):
        actuelles["sans_ouverture"] = b["sans_ouverture"]
    if "user_agents_robots" in b:
        actuelles["user_agents_robots"] = [str(x).strip().lower() for x in b["user_agents_robots"] if str(x).strip()][:200]
    if "ips_robots" in b:
        import ipaddress
        ips = []
        for x in b["ips_robots"]:
            try:
                ips.append(str(ipaddress.ip_network(str(x).strip(), strict=False)))
            except ValueError:
                raise HTTPException(status_code=422, detail=f"IP ou plage invalide : {x}")
        actuelles["ips_robots"] = ips
    pg.ecrire("UPDATE settings SET click_rules = %(r)s::jsonb, updated_at = now(), updated_by = %(a)s",
              {"r": json.dumps(actuelles), "a": acteur})
    # Les règles changent : on reclasse les campagnes qui ont des clics.
    for x in pg.lignes("SELECT DISTINCT campaign_id FROM clicks"):
        clics.classer(str(x["campaign_id"]))
    return actuelles


@public_router.get("/sante/worker")
def sante_worker():
    """Surveillé par HetrixTools (mot-clé « worker-ok »). Le worker ne donne signe de vie
    qu'ENTRE deux jobs (un lot de validation dure ~15 min) : OK s'il s'est manifesté depuis
    moins de 3 min OU s'il traite un job commencé depuis moins d'une heure."""
    vu = pg.valeur("SELECT now() - max(seen_at) < interval '3 minutes' FROM workers")
    occupe = pg.valeur("""SELECT count(*) FROM jobs WHERE status = 'running'
                           AND started_at > now() - interval '1 hour'""")
    if vu or occupe:
        return {"etat": "worker-ok", "occupe": bool(occupe)}
    return JSONResponse({"etat": "worker-ko"}, status_code=503)


@public_router.get("/p", response_class=HTMLResponse)
def piege(request: Request, t: str = ""):
    """Cible du badge « ✉ Email envoyé par la technologie Cheffer » (lien piège VISIBLE, 27/09) :
    note la visite (un scanner suit tous les liens) et affiche la page de préférences. Un GET ne
    change rien. Jeton invalide : même page neutre, sans formulaire utile (rien à apprendre)."""
    from infra import preferences
    ctx = preferences.contexte(t)
    if not (ctx and ctx.get("test")):
        preferences.journaliser(ctx, "visite", _ip(request), request.headers.get("user-agent") or "")
    if not ctx:
        return HTMLResponse(preferences.merci("Ce lien n’est plus valide."), status_code=200)
    return HTMLResponse(preferences.page(t, ctx.get("from_name")),
                        headers={"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store"})


@public_router.post("/p", response_class=HTMLResponse)
async def piege_formulaire(request: Request, t: str = ""):
    """Formulaire d'opt-down. N'agit QUE si les preuves humaines sont réunies ; sinon répond
    « c'est enregistré » sans rien faire (le robot est « perdu ») et journalise le motif."""
    from infra import preferences
    form = {k: str(v) for k, v in (await request.form()).items()}
    t = form.get("t") or t
    ctx = preferences.contexte(t)
    ip, ua = _ip(request), request.headers.get("user-agent") or ""
    motif = "jeton invalide" if not ctx else preferences.verifier_humain(form, t)
    if ctx and ctx.get("test"):
        return HTMLResponse(preferences.merci("Aperçu d’un BAT : rien n’est enregistré."))
    if motif:
        preferences.journaliser(ctx, "robot_perdu", ip, ua, motif)
        return HTMLResponse(preferences.merci())
    preferences.appliquer(ctx, form["choix"])
    preferences.journaliser(ctx, form["choix"], ip, ua)
    _audit(str(ctx["campaign_id"]), "destinataire", "preferences",
           f"Préférence « {preferences.CHOIX[form['choix']]} » pour {adresses_mod.masquer(ctx['email_normalized'])}")
    return HTMLResponse(preferences.merci())


@public_router.get("/export")
def export_public(t: str = ""):
    j = clics.lire_jeton_export(t)
    if not j:
        return HTMLResponse(_PAGE.format(titre="Lien expiré", texte="Ce lien d'export n'est plus valide."), status_code=410)
    cid, robots = j
    return Response(clics.csv_clics(cid, robots), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="clics-{cid[:8]}.csv"'})


@router.post("/campaigns/{campaign_id}/html/corriger")
async def corriger_html(campaign_id: str, request: Request):
    """Applique une correction proposée par la carte d'analyse (liens vides, expressions
    à risque, texte caché). Renvoie le HTML corrigé ; l'écran relance l'analyse."""
    _superadmin(request)
    _campagne(campaign_id)
    b = await request.json()
    if b.get("action") not in ("liens_vides", "mots_spam", "texte_cache"):
        raise HTTPException(status_code=422, detail="action inconnue")
    html, info = controle_html.corriger(b.get("html") or "", b["action"], b.get("params") or {})
    return {"html": html, "info": info}


@router.put("/profil-expediteur")
async def maj_profil_expediteur(request: Request):
    """Raison sociale et adresse postale du pied de message (profil par défaut)."""
    acteur = _superadmin(request)
    b = await request.json()
    adresse = (b.get("adresse_postale") or "").strip()[:300]
    if len(adresse) < 10:
        raise HTTPException(status_code=422, detail="adresse postale trop courte")
    p = envoi.profil_defaut()
    if not p:
        raise HTTPException(status_code=409, detail="aucun profil expéditeur par défaut")
    pg.ecrire("""UPDATE sender_profiles SET raison_sociale = %(r)s, adresse_postale = %(a)s, updated_at = now()
                  WHERE id = %(i)s""", {"r": (b.get("raison_sociale") or "").strip()[:200] or None, "a": adresse, "i": p["id"]})
    return {"ok": True, "par": acteur}


# ── Page de rappel (consentement) — Camille, 2026-09-26 ──────────────────────
# Réglages dans l'étape Planification ; page publique sur le modèle de la page de
# consentement SMS de LeClientRoi ; chaque réponse horodatée, preuve CNIL publique.
from infra import rappel as rappel_mod  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402


def _html_campagne(c: dict) -> str:
    return stockage.lire(c["html_storage_key"]).decode("utf-8", "replace") if c.get("html_storage_key") else ""


def _config_rappel(c: dict) -> dict:
    base = rappel_mod.config_par_defaut(c, _html_campagne(c))
    # Le thème (couleurs, police) vient toujours de la newsletter actuelle.
    return {**base, **(c.get("rappel") or {}), "theme": base["theme"]}


def _version_rappel(campaign_id: str, config: dict) -> str:
    """La version figée du formulaire pour ces réglages (créée au premier besoin)."""
    emp = rappel_mod.empreinte(config)
    pg.ecrire("""INSERT INTO formulaires_rappel (campaign_id, empreinte, config, texte_consentement, html)
                 VALUES (%(c)s, %(e)s, %(cfg)s::jsonb, %(t)s, %(h)s)
                 ON CONFLICT (campaign_id, empreinte) DO NOTHING""",
              {"c": campaign_id, "e": emp, "t": rappel_mod.texte_consentement(config),
               "cfg": json.dumps({k: v for k, v in config.items() if k != "email_responsable"}, ensure_ascii=False),
               "h": rappel_mod.rendre_page(config)})
    return str(pg.valeur("SELECT id FROM formulaires_rappel WHERE campaign_id = %(c)s AND empreinte = %(e)s",
                         {"c": campaign_id, "e": emp}))


@router.get("/campaigns/{campaign_id}/rappel")
def lire_rappel(campaign_id: str, request: Request):
    _superadmin(request)
    c = _campagne(campaign_id)
    config = _config_rappel(c)
    versions = pg.lignes("""SELECT id::text, created_at FROM formulaires_rappel
                             WHERE campaign_id = %(c)s ORDER BY created_at DESC""", {"c": campaign_id})
    return {"config": config, "enregistre": c.get("rappel") is not None,
            "apercu": rappel_mod.url(campaign_id, 0, config.get("redirection") or ""),
            "lien_public": rappel_mod.url(campaign_id, -1, config.get("redirection") or ""),
            "versions": [{**v, "url": rappel_mod.url_formulaire(v["id"])} for v in versions]}


@router.put("/campaigns/{campaign_id}/rappel")
async def enregistrer_rappel(campaign_id: str, request: Request):
    acteur = _superadmin(request)
    c = _campagne(campaign_id)
    if c["status"] in ("completed", "completed_with_warnings", "cancelled", "archived"):
        raise HTTPException(status_code=409, detail="campagne terminée : la page ne se modifie plus")
    try:
        config = rappel_mod.nettoyer_config(await request.json(), _config_rappel(c))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    # Les liens du message changent de destination : les contrôles avant envoi sont à refaire.
    pg.ecrire("UPDATE campaigns SET rappel = %(r)s::jsonb, preflight_snapshot = NULL, updated_at = now() WHERE id = %(c)s",
              {"c": campaign_id, "r": json.dumps(config, ensure_ascii=False)})
    version = _version_rappel(campaign_id, config) if config["actif"] else None
    _audit(campaign_id, acteur, "rappel.updated",
           "Page de rappel " + ("activée" if config["actif"] else "désactivée"), {"version": version})
    return {"ok": True, "config": config, "version": version}


@router.get("/campaigns/{campaign_id}/rappels")
def lister_rappels(campaign_id: str, request: Request, tests: bool = False):
    _superadmin(request)
    _campagne(campaign_id)
    lignes = pg.lignes("""SELECT r.id, r.action, r.email, r.telephone, r.consentement, r.created_at,
                                 r.notifie_a, r.notifie_at, r.notification_erreur, r.test, r.ip,
                                 r.formulaire_id::text
                            FROM rappels r WHERE r.campaign_id = %(c)s AND r.action <> 'visite'
                             AND (%(t)s OR NOT r.test) ORDER BY r.created_at DESC LIMIT 2000""",
                       {"c": campaign_id, "t": tests})
    compte = pg.ligne("""SELECT count(*) FILTER (WHERE action = 'visite') visites,
                                count(DISTINCT COALESCE(recipient_id::text, email)) FILTER (WHERE action = 'visite') visiteurs,
                                count(*) FILTER (WHERE action = 'accepte') acceptes,
                                count(*) FILTER (WHERE action = 'refuse') refus
                           FROM rappels WHERE campaign_id = %(c)s AND (%(t)s OR NOT test)""",
                      {"c": campaign_id, "t": tests})
    for x in lignes:
        x["preuve"] = rappel_mod.url_formulaire(x["formulaire_id"]) if x["formulaire_id"] else None
    return {"rappels": lignes, "compte": compte}


@router.get("/campaigns/{campaign_id}/rappels.csv")
def exporter_rappels(campaign_id: str, request: Request):
    _superadmin(request)
    c = _campagne(campaign_id)
    import csv
    import io
    lignes = pg.lignes("""SELECT created_at, action, email, telephone, consentement, texte_consentement,
                                 ip, formulaire_id::text
                            FROM rappels WHERE campaign_id = %(c)s AND action <> 'visite' AND NOT test
                           ORDER BY created_at""", {"c": campaign_id})
    f = io.StringIO()
    w = csv.writer(f, delimiter=";")
    w.writerow(["horodatage_utc", "reponse", "email", "telephone", "consentement", "texte_accepte",
                "ip", "formulaire_lu"])
    for x in lignes:
        w.writerow([x["created_at"].isoformat(), "oui" if x["action"] == "accepte" else "non", x["email"],
                    x["telephone"] or "", "oui" if x["consentement"] else "non", x["texte_consentement"] or "",
                    x["ip"] or "", rappel_mod.url_formulaire(x["formulaire_id"]) if x["formulaire_id"] else ""])
    nom = re.sub(r"[^A-Za-z0-9_-]+", "-", c["internal_name"])[:40]
    return Response("﻿" + f.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="rappels-{nom}.csv"'})


def _ip(request: Request) -> str:
    h = request.headers
    return (h.get("cf-connecting-ip") or h.get("x-real-ip")
            or (h.get("x-forwarded-for") or "").split(",")[0].strip()
            or (request.client.host if request.client else ""))


def _contexte_rappel(t: str):
    """(campagne, config, destinataire, email, destination) d'un jeton — ou None."""
    lu = rappel_mod.lire_jeton(t)
    if not lu:
        return None
    cid, rid, dest, email_jeton = lu
    c = pg.ligne("SELECT * FROM campaigns WHERE id = %(c)s", {"c": cid})
    if not c:
        return None
    # L'email : celui du destinataire, sinon celui porté (signé) par le lien — l'adresse
    # de test d'un BAT. Le prospect n'a alors qu'à donner son numéro.
    email = (pg.valeur("SELECT email_normalized FROM recipients WHERE id = %(r)s AND campaign_id = %(c)s",
                       {"r": rid, "c": cid}) if rid > 0 else None) or (email_jeton or None)
    # rid > 0 : un destinataire de la campagne ; 0 : test (BAT, aperçu) ; -1 : lien public
    # générique (collé dans un SMS, un site…) — réponses réelles, email demandé sur la page.
    return c, _config_rappel(c), rid, email, dest


@public_router.get("/rappel", response_class=HTMLResponse)
def page_rappel(request: Request, t: str = ""):
    ctx = _contexte_rappel(t)
    if not ctx:
        return HTMLResponse(_PAGE.format(titre="Lien invalide", texte="Ce lien n'est pas ou plus valide."), status_code=400)
    c, config, rid, email, dest = ctx
    if not config.get("actif"):
        return RedirectResponse(dest or config.get("redirection") or "https://leclientroi.com", status_code=302)
    version = _version_rappel(str(c["id"]), config)
    pg.ecrire("""INSERT INTO rappels (campaign_id, recipient_id, formulaire_id, action, email, url_destination,
                                      ip, user_agent, test)
                 VALUES (%(c)s, %(r)s, %(v)s, 'visite', %(e)s, %(d)s, %(ip)s, %(ua)s, %(test)s)""",
              {"c": c["id"], "r": rid if rid > 0 else None, "v": version, "e": email, "d": dest, "ip": _ip(request),
               "ua": (request.headers.get("user-agent") or "")[:500], "test": rid == 0})
    return rappel_mod.rendre_page(config, t=t, email=email or "", destination=dest)


@public_router.post("/rappel", response_class=HTMLResponse)
async def repondre_rappel(request: Request):
    form = await request.form()
    t = str(form.get("t") or "")
    ctx = _contexte_rappel(t)
    if not ctx:
        return HTMLResponse(_PAGE.format(titre="Lien invalide", texte="Ce lien n'est pas ou plus valide."), status_code=400)
    c, config, rid, email_connu, dest = ctx
    cible = dest or config.get("redirection") or "https://leclientroi.com"
    if not config.get("actif"):
        return RedirectResponse(cible, status_code=303)
    action = "accepte" if form.get("action") == "accepte" else "refuse"
    email = email_connu or adresses_mod.normaliser(str(form.get("email") or ""))
    version = _version_rappel(str(c["id"]), config)
    commun = {"c": c["id"], "r": rid if rid > 0 else None, "v": version, "d": dest, "ip": _ip(request),
              "ua": (request.headers.get("user-agent") or "")[:500], "test": rid == 0}
    if action == "refuse":
        pg.ecrire("""INSERT INTO rappels (campaign_id, recipient_id, formulaire_id, action, email, consentement,
                                          url_destination, ip, user_agent, test)
                     VALUES (%(c)s, %(r)s, %(v)s, 'refuse', %(e)s, false, %(d)s, %(ip)s, %(ua)s, %(test)s)""",
                  {**commun, "e": email or None})
        return RedirectResponse(cible, status_code=303)

    tel_saisi = str(form.get("telephone") or "")
    tel = rappel_mod.normaliser_telephone(tel_saisi)
    erreur = ("Indiquez un email valide." if not (email and adresses_mod.syntaxe_valide(email))
              else "Indiquez un numéro de téléphone valide (ex. 06 12 34 56 78)." if not tel
              else "Cochez la case pour accepter d'être recontacté(e)." if form.get("consent") != "1" else "")
    if erreur:
        return HTMLResponse(rappel_mod.rendre_page(config, t=t, email=email_connu or "", destination=dest,
                                                   erreur=erreur, telephone=tel_saisi), status_code=422)
    texte = rappel_mod.texte_consentement(config)
    rid_ligne = pg.valeur("""INSERT INTO rappels (campaign_id, recipient_id, formulaire_id, action, email, telephone,
                                                  consentement, texte_consentement, url_destination, ip, user_agent, test)
                             VALUES (%(c)s, %(r)s, %(v)s, 'accepte', %(e)s, %(tel)s, true, %(txt)s, %(d)s,
                                     %(ip)s, %(ua)s, %(test)s)
                             RETURNING id""", {**commun, "e": email, "tel": tel, "txt": texte})
    # Email au responsable du call center : UN mail, UN destinataire.
    resp = config.get("email_responsable")
    if resp:
        quand = pg.valeur("SELECT to_char(created_at AT TIME ZONE 'Europe/Paris', 'DD/MM/YYYY à HH24:MI:SS') FROM rappels WHERE id = %(i)s", {"i": rid_ligne})
        objet, h, txt = rappel_mod.notification(config, c["internal_name"] + (" (TEST)" if rid == 0 else " (lien public)" if rid < 0 else ""),
                                                email, tel, quand, rappel_mod.url_formulaire(version))
        profil = pg.ligne("SELECT * FROM sender_profiles WHERE id = %(p)s", {"p": c["sender_profile_id"]}) \
            if c.get("sender_profile_id") else envoi.profil_defaut()
        exp = envoi.expediteur(c, profil)
        r = sweego.envoyer_un(destinataire=resp, subject=objet, html_str=h, texte=txt,
                              expediteur={**exp, "campaign_type": "transac", "reply_to": None},
                              campagne="mm-rappel", tags=["mm-rappel"]) if exp else {"ok": False, "erreur": "expéditeur non configuré"}
        pg.ecrire("""UPDATE rappels SET notifie_a = %(a)s, notifie_at = CASE WHEN %(ok)s THEN now() END,
                                        notification_erreur = %(err)s WHERE id = %(i)s""",
                  {"a": resp, "ok": bool(r.get("ok")), "err": None if r.get("ok") else str(r.get("erreur"))[:300], "i": rid_ligne})
    # Page de remerciement 3 s, puis la redirection (Camille, 2026-09-26).
    return HTMLResponse(rappel_mod.rendre_merci(config, cible))


@public_router.get("/rappel/formulaire/{formulaire_id}", response_class=HTMLResponse)
def formulaire_archive(formulaire_id: str):
    """La version exacte du formulaire qu'un prospect a lue — publique, pour la CNIL."""
    if not re.fullmatch(r"[0-9a-f-]{36}", formulaire_id or ""):
        return HTMLResponse(_PAGE.format(titre="Formulaire introuvable", texte=""), status_code=404)
    f = pg.ligne("""SELECT config, to_char(created_at AT TIME ZONE 'Europe/Paris', 'DD/MM/YYYY à HH24:MI') AS le
                      FROM formulaires_rappel WHERE id = %(i)s""", {"i": formulaire_id})
    if not f:
        return HTMLResponse(_PAGE.format(titre="Formulaire introuvable", texte=""), status_code=404)
    return rappel_mod.rendre_page(f["config"], archive=f"Version archivée du formulaire, en ligne depuis le {f['le']} (heure de Paris). Référence {formulaire_id}.")


@router.get("/campaigns/{campaign_id}/rappel/rendu")
def rendu_rappel(campaign_id: str, request: Request):
    """Le HTML de la page de rappel pour l'aperçu de l'étape Planification. Lecture seule :
    passer par le lien public compterait une visite."""
    _superadmin(request)
    c = _campagne(campaign_id)
    config = _config_rappel(c)
    return {"actif": bool(config.get("actif")),
            "html": rappel_mod.rendre_page(config, email="prospect@exemple.fr",
                                           destination=config.get("redirection") or "")}
