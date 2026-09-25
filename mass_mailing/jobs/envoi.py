#!/usr/bin/env python3
"""mass_mailing/jobs/envoi.py — du lot validé au mail parti, puis les statistiques.

    preflight(campagne)      contrôles avant envoi → instantané figé
    autoriser(campagne)      feu vert du superadmin → statut `sending` + jobs d'envoi
    envoyer_lot(job)         UN lot d'envoi : 1 appel Sweego par destinataire
    synchroniser(campagne)   relit les logs Sweego → livrés, ouverts, cliqués, rebonds

Règles tenues :
- **1 destinataire = 1 mail**, par construction (`sweego.envoyer_un`).
- **La liste de suppression est relue juste avant chaque lot** : une désinscription
  arrivée pendant la validation est respectée.
- **Jamais de double envoi** : un destinataire passe `queued → submitted` UNE fois ;
  un appel au résultat incertain (délai dépassé) est marqué `failed` et n'est PAS
  rejoué automatiquement.
- **Rien ne part sans feu vert** : un lot d'envoi n'est expédié que si la campagne est
  en `sending`, ce que seule la route « Autoriser l'envoi » décide.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import desinscription, pg, stockage, sweego  # noqa: E402
from jobs import file  # noqa: E402
from jobs.file import ErreurDefinitive  # noqa: E402

JOB_ENVOYER = "campaign.dispatch_sweego_batch"
FILS_ENVOI = 4


def etiquette(campaign_id: str) -> str:
    """Étiquette Sweego de la campagne (≤ 20 caractères, [A-Za-z0-9-])."""
    return "mm-" + str(campaign_id).replace("-", "")[:12]


def _audit(cur, cid, acteur_type: str, acteur: str | None, event: str, resume: str, charge=None):
    cur.execute("""INSERT INTO campaign_events (campaign_id, actor_type, actor_id, event_type,
                                                summary, payload)
                   VALUES (%(c)s, %(t)s, %(a)s, %(e)s, %(r)s, %(p)s::jsonb)""",
                {"c": cid, "t": acteur_type, "a": acteur, "e": event, "r": resume,
                 "p": json.dumps(charge or {}, ensure_ascii=False, default=str)})


def profil_defaut() -> dict | None:
    return pg.ligne("""SELECT * FROM sender_profiles WHERE active AND is_default LIMIT 1""")


# ── Contrôles avant envoi ────────────────────────────────────────────────────

def preflight(campaign_id: str, acteur: str) -> dict:
    c = pg.ligne("SELECT * FROM campaigns WHERE id = %(c)s", {"c": campaign_id})
    if not c:
        raise ErreurDefinitive("campagne introuvable")
    profil = pg.ligne("SELECT * FROM sender_profiles WHERE id = %(p)s AND active",
                      {"p": c["sender_profile_id"]}) if c["sender_profile_id"] else profil_defaut()
    html = stockage.lire(c["html_storage_key"]).decode("utf-8", "replace") if c["html_storage_key"] else ""
    liens = sweego.liens_du_html(html)
    eligibles = pg.valeur("""SELECT count(*) FROM recipients WHERE campaign_id = %(c)s
                               AND target_version_id = %(t)s AND eligibility_status = 'eligible'""",
                          {"c": campaign_id, "t": c["target_version_id"]}) or 0
    en_validation = pg.valeur("""SELECT count(*) FROM validation_batches WHERE campaign_id = %(c)s
                                   AND status IN ('pending','running')""", {"c": campaign_id}) or 0

    ctrl = []
    def ajoute(cle, ok, libelle, bloquant=True):
        ctrl.append({"cle": cle, "ok": bool(ok), "libelle": libelle, "bloquant": bloquant})

    ajoute("objet", (c["subject"] or "").strip(), "Objet renseigné")
    ajoute("html", html.strip(), "Message HTML présent")
    ajoute("desinscription", True, "Lien de désinscription personnel ajouté en pied de chaque mail")
    ajoute("https", not [l for l in liens if l.lower().startswith("http://")],
           "Tous les liens sont en https", bloquant=False)
    ajoute("jetons", "{{" not in html, "Aucune variable {{…}} oubliée dans le message")
    ajoute("profil", profil is not None, "Profil expéditeur actif"
           + (f" : {profil['from_name']} <{profil['from_email']}>" if profil else ""))
    ajoute("cible", eligibles > 0 or (c["dispatch_mode"] == "progressive" and en_validation > 0),
           f"{eligibles} destinataire(s) éligible(s)"
           + (f", {en_validation} lot(s) encore en validation" if en_validation else ""))
    # Sweego accepte-t-il ce message avec ce profil ? Test à blanc : rien n'est envoyé.
    sw = {"ok": False, "erreur": "non testé"}
    if profil and html.strip() and (c["subject"] or "").strip():
        sw = sweego.envoyer_un(destinataire=profil["from_email"], subject=c["subject"],
                               html_str=desinscription.pied_de_mail(html, 0, profil["from_name"]),
                               texte=sweego.html_vers_texte(html), expediteur=profil,
                               # Étiquette à part : un test à blanc apparaît quand même
                               # dans les logs Sweego et fausserait les stats de la campagne.
                               campagne="mm-preflight", tags=["mm-preflight"],
                               dry_run=True)
    ajoute("sweego", sw.get("ok"), "Sweego accepte le message (test à blanc, rien n'est envoyé)"
           + ("" if sw.get("ok") else f" — {sw.get('erreur')}"))

    ok = all(x["ok"] for x in ctrl if x["bloquant"])
    snap = {"ok": ok, "controles": ctrl, "html_hash": c["html_hash"], "subject": c["subject"],
            "profil_id": str(profil["id"]) if profil else None, "eligibles": eligibles,
            "fait_le": datetime.now(timezone.utc).isoformat(), "par": acteur}
    with pg.connexion() as cur:
        cur.execute("""UPDATE campaigns SET preflight_snapshot = %(s)s::jsonb,
                              sender_profile_id = COALESCE(sender_profile_id, %(p)s),
                              updated_at = now() WHERE id = %(c)s""",
                    {"s": json.dumps(snap, default=str), "p": profil["id"] if profil else None,
                     "c": campaign_id})
        _audit(cur, campaign_id, "user", acteur, "preflight.run",
               "Contrôles avant envoi : " + ("tous au vert" if ok else "bloqués"),
               {"controles": [x for x in ctrl if not x["ok"]]})
    return snap


# ── Feu vert ─────────────────────────────────────────────────────────────────

def autoriser(campaign_id: str, acteur: str) -> dict:
    with pg.connexion() as cur:
        cur.execute("SELECT * FROM campaigns WHERE id = %(c)s FOR UPDATE", {"c": campaign_id})
        c = cur.fetchone()
        if not c:
            raise ErreurDefinitive("campagne introuvable")
        snap = c["preflight_snapshot"] or {}
        if not snap.get("ok"):
            raise ErreurDefinitive("les contrôles avant envoi ne sont pas au vert")
        if snap.get("html_hash") != c["html_hash"] or snap.get("subject") != c["subject"]:
            raise ErreurDefinitive("le message a changé depuis les contrôles : relancez-les")
        permis = ("ready_to_schedule", "paused") + (
            ("validating_list",) if c["dispatch_mode"] == "progressive" else ())
        if c["status"] not in permis:
            raise ErreurDefinitive(f"envoi impossible depuis « {c['status']} »")
        profil = pg.ligne("SELECT * FROM sender_profiles WHERE id = %(p)s",
                          {"p": c["sender_profile_id"]})
        cur.execute("""UPDATE campaigns SET status = 'sending', started_at = COALESCE(started_at, now()),
                              paused_at = NULL, compliance_snapshot = %(cs)s::jsonb,
                              provider_config_snapshot = %(pc)s::jsonb, updated_at = now()
                        WHERE id = %(c)s""",
                    {"c": campaign_id,
                     "cs": json.dumps({"autorise_par": acteur, "le": datetime.now(timezone.utc),
                                       "preflight": snap, "un_pour_un": True}, default=str),
                     "pc": json.dumps({"fournisseur": "sweego", "route": "/send (1 destinataire)",
                                       "etiquette": etiquette(campaign_id),
                                       "profil": {k: profil[k] for k in ("from_name", "from_email", "reply_to", "sending_domain")}
                                       if profil else None}, default=str)})
        _audit(cur, campaign_id, "user", acteur, "sending.authorized", "Envoi autorisé")
    n = empiler_lots(campaign_id)
    return {"ok": True, "lots_empiles": n}


def empiler_lots(campaign_id: str) -> int:
    """Un job par lot d'envoi en attente — appelé au feu vert, et à chaque lot validé
    si la campagne envoie déjà (mode progressif)."""
    n = 0
    for sb in pg.lignes("""SELECT id, sequence_number FROM sending_batches
                            WHERE campaign_id = %(c)s AND status = 'pending'
                            ORDER BY sequence_number""", {"c": campaign_id}):
        if file.empiler(JOB_ENVOYER, campaign_id=campaign_id,
                        payload={"sending_batch_id": str(sb["id"])},
                        idempotency_key=f"dispatch:{sb['id']}", priority=50 + sb["sequence_number"]):
            n += 1
    return n


# ── Un lot d'envoi ───────────────────────────────────────────────────────────

def envoyer_lot(job: dict, *, envoyeur=sweego.envoyer_un) -> dict:
    sb_id = (job.get("payload") or {}).get("sending_batch_id")
    with pg.connexion() as cur:
        cur.execute("""SELECT sb.*, c.status AS c_status, c.subject, c.html_storage_key,
                              c.sender_profile_id
                         FROM sending_batches sb JOIN campaigns c ON c.id = sb.campaign_id
                        WHERE sb.id = %(s)s FOR UPDATE OF sb""", {"s": sb_id})
        sb = cur.fetchone()
        if not sb:
            raise ErreurDefinitive("lot d'envoi introuvable")
        if sb["status"] in ("completed", "skipped", "cancelled"):
            return {"deja_traite": True}
        if sb["c_status"] != "sending":
            # Pas de feu vert (ou pause) : le lot attend, le job ne sert à rien.
            raise ErreurDefinitive(f"campagne en « {sb['c_status']} » : lot non envoyé")
        cur.execute("""UPDATE sending_batches SET status = 'dispatching', attempts = attempts + 1
                        WHERE id = %(s)s""", {"s": sb_id})
    cid = str(sb["campaign_id"])
    profil = pg.ligne("SELECT * FROM sender_profiles WHERE id = %(p)s", {"p": sb["sender_profile_id"]})
    if not profil:
        raise ErreurDefinitive("profil expéditeur introuvable")
    html = stockage.lire(sb["html_storage_key"]).decode("utf-8", "replace")
    html = sweego.nettoyer_html(html)
    texte = sweego.html_vers_texte(html)
    tag = etiquette(cid)

    # Suppression relue MAINTENANT, juste avant le départ.
    pg.ecrire("""
        UPDATE recipients r SET send_status = 'skipped', eligibility_status = 'excluded',
                                eligibility_reason = 'suppressed', updated_at = now()
         WHERE r.sending_batch_id = %(s)s AND r.send_status = 'queued'
           AND EXISTS (SELECT 1 FROM suppressions x WHERE x.email_hash = r.email_hash
                         AND (x.scope = 'global' OR (x.scope = 'campaign' AND x.scope_id = r.campaign_id)))
    """, {"s": sb_id})
    dest = pg.lignes("""SELECT id, email_normalized FROM recipients
                         WHERE sending_batch_id = %(s)s AND send_status = 'queued' ORDER BY id""",
                     {"s": sb_id})

    reglage = pg.ligne("SELECT max_rate_per_minute FROM settings")
    intervalle = 60.0 / max(1, int(reglage["max_rate_per_minute"]))
    verrou, prochain = threading.Lock(), [time.monotonic()]

    def cadence():
        with verrou:
            attente = prochain[0] - time.monotonic()
            prochain[0] = max(prochain[0], time.monotonic()) + intervalle
        if attente > 0:
            time.sleep(attente)

    def un(d):
        cadence()
        r = envoyeur(destinataire=d["email_normalized"], subject=sb["subject"],
                     html_str=desinscription.pied_de_mail(html, d["id"], profil["from_name"]),
                     texte=texte + desinscription.texte_pied(d["id"]), expediteur=profil,
                     campagne=f"mm-{cid}", tags=[tag])
        # Écrit tout de suite : si le worker meurt en route, on sait qui est parti.
        if r.get("ok"):
            pg.ecrire("""UPDATE recipients SET send_status = 'submitted', submitted_at = now(),
                                sweego_message_id = %(u)s,
                                provider_raw_metadata = %(m)s::jsonb, updated_at = now()
                          WHERE id = %(i)s AND send_status = 'queued'""",
                      {"i": d["id"], "u": r.get("swg_uid"),
                       "m": json.dumps({"transaction_id": r.get("transaction_id")})})
        else:
            pg.ecrire("""UPDATE recipients SET send_status = 'failed', updated_at = now(),
                                provider_raw_metadata = %(m)s::jsonb
                          WHERE id = %(i)s AND send_status = 'queued'""",
                      {"i": d["id"], "m": json.dumps({"erreur": r.get("erreur"),
                                                      "incertain": r.get("incertain", False)})})
        return r

    with ThreadPoolExecutor(FILS_ENVOI) as ex:
        res = list(ex.map(un, dest))
    acceptes = sum(1 for r in res if r.get("ok"))
    rejetes = len(res) - acceptes
    erreurs = sorted({r.get("erreur") for r in res if not r.get("ok")} - {None})[:5]

    with pg.connexion() as cur:
        cur.execute("""UPDATE sending_batches SET status = %(st)s, dispatched_at = now(),
                              completed_at = now(), accepted_count = %(a)s, rejected_count = %(r)s,
                              error_message = %(e)s WHERE id = %(s)s""",
                    {"s": sb_id, "a": acceptes, "r": rejetes,
                     "st": "completed" if acceptes or not rejetes else "failed",
                     "e": "; ".join(erreurs) or None})
        _audit(cur, cid, "worker", None, "sending.batch_dispatched",
               f"Lot {sb['sequence_number']} : {acceptes} mail(s) parti(s)"
               + (f", {rejetes} refusé(s)" if rejetes else ""), {"erreurs": erreurs})
        _terminer_si_fini(cur, cid)
    return {"lot": sb["sequence_number"], "acceptes": acceptes, "rejetes": rejetes}


def _terminer_si_fini(cur, cid) -> None:
    cur.execute("""SELECT
        (SELECT count(*) FROM validation_batches WHERE campaign_id = %(c)s AND status <> 'completed') AS v,
        (SELECT count(*) FROM sending_batches WHERE campaign_id = %(c)s
          AND status IN ('pending','scheduled','dispatching')) AS e,
        (SELECT count(*) FROM sending_batches WHERE campaign_id = %(c)s AND status = 'failed') AS ko""",
                {"c": cid})
    x = cur.fetchone()
    if x["v"] == 0 and x["e"] == 0:
        st = "completed_with_warnings" if x["ko"] else "completed"
        cur.execute("""UPDATE campaigns SET status = %(s)s, completed_at = now(), updated_at = now()
                        WHERE id = %(c)s AND status = 'sending'""", {"s": st, "c": cid})
        if cur.rowcount:
            _audit(cur, cid, "worker", None, "sending.completed",
                   "Envoi terminé" + (" avec des lots en erreur" if x["ko"] else ""))


# ── Statistiques ─────────────────────────────────────────────────────────────

def synchroniser(campaign_id: str) -> dict:
    """Relit les logs Sweego de la campagne et met à jour chaque destinataire.

    Les statuts Sweego sont cumulatifs : un message `clicked-human` a été livré et
    ouvert. Les ouvertures « proxy » (antispam, préchargement) sont comptées à part :
    elles ne prouvent pas qu'un humain a lu le mail."""
    c = pg.ligne("SELECT started_at FROM campaigns WHERE id = %(c)s", {"c": campaign_id})
    if not c or not c["started_at"]:
        return {"ok": False, "raison": "rien n'est encore parti"}
    debut = (c["started_at"] - timedelta(days=1)).date().isoformat()
    fin = (date.today() + timedelta(days=1)).isoformat()
    logs = sweego.logs_campagne(etiquette(campaign_id), debut, fin)
    livres = ("delivered", "opened-proxy", "opened-human", "clicked-proxy", "clicked-human")
    maj = 0
    for x in logs:
        st = x.get("status") or ""
        ouvert_h = any(not o.get("is_proxy") for o in (x.get("tracking_open") or [])) \
            or st in ("opened-human", "clicked-human")
        maj += pg.ecrire("""
            UPDATE recipients SET
                delivered_at = CASE WHEN %(l)s THEN COALESCE(delivered_at, %(t)s) ELSE delivered_at END,
                opened_at    = CASE WHEN %(o)s THEN COALESCE(opened_at, %(t)s) ELSE opened_at END,
                clicked_at   = CASE WHEN %(k)s THEN COALESCE(clicked_at, %(t)s) ELSE clicked_at END,
                bounced_at   = CASE WHEN %(b)s THEN COALESCE(bounced_at, %(t)s) ELSE bounced_at END,
                send_status  = CASE WHEN %(b)s THEN 'bounced' WHEN %(l)s THEN 'delivered' ELSE send_status END,
                provider_raw_metadata = COALESCE(provider_raw_metadata, '{}'::jsonb)
                                        || jsonb_build_object('sweego_status', %(st)s::text,
                                                              'proxy_seul', %(px)s),
                updated_at = now()
             WHERE campaign_id = %(c)s AND sweego_message_id = %(u)s
        """, {"c": campaign_id, "u": x.get("swg_uid"), "st": st,
              "t": x.get("email_last_update") or datetime.now(timezone.utc),
              "l": st in livres, "o": ouvert_h, "k": st == "clicked-human",
              "b": st == "undelivered", "px": st in ("opened-proxy", "clicked-proxy") and not ouvert_h})
    # Rebond définitif ou plainte : l'adresse entre dans la liste de suppression, pour
    # toutes les campagnes (le webhook Cheffer ignore les campagnes « mm-… »).
    for x in logs:
        motif = "complaint" if x.get("spam") else (
            "hard_bounce" if x.get("status") == "undelivered"
            and "hard" in str(x.get("bounce_type") or "").lower() else None)
        if motif:
            pg.ecrire("""INSERT INTO suppressions (email_hash, email_normalized, reason, source, scope, metadata)
                         SELECT email_hash, email_normalized, %(m)s, 'sweego', 'global',
                                jsonb_build_object('swg_uid', %(u)s::text)
                           FROM recipients WHERE campaign_id = %(c)s AND sweego_message_id = %(u)s
                         ON CONFLICT DO NOTHING""",
                      {"m": motif, "u": x.get("swg_uid"), "c": campaign_id})
    stats = statistiques(campaign_id)
    pg.ecrire("UPDATE campaigns SET stats_snapshot = %(s)s::jsonb WHERE id = %(c)s",
              {"s": json.dumps({**stats, "synchro": datetime.now(timezone.utc).isoformat()}),
               "c": campaign_id})
    return {"ok": True, "messages_sweego": len(logs), "mis_a_jour": maj, "stats": stats}


def statistiques(campaign_id: str) -> dict:
    return pg.ligne("""
        SELECT count(*) FILTER (WHERE send_status IN ('submitted','delivered','bounced')) AS envoyes,
               count(*) FILTER (WHERE delivered_at IS NOT NULL) AS livres,
               count(*) FILTER (WHERE bounced_at IS NOT NULL) AS rebonds,
               count(*) FILTER (WHERE opened_at IS NOT NULL) AS ouverts,
               count(*) FILTER (WHERE (provider_raw_metadata->>'proxy_seul')::boolean) AS ouverts_proxy,
               count(*) FILTER (WHERE clicked_at IS NOT NULL) AS cliques,
               count(*) FILTER (WHERE unsubscribed_at IS NOT NULL) AS desinscrits,
               count(*) FILTER (WHERE send_status = 'failed') AS echecs,
               count(*) FILTER (WHERE send_status = 'skipped') AS ecartes
          FROM recipients WHERE campaign_id = %(c)s
    """, {"c": campaign_id})


def apres_lot_valide(campaign_id: str) -> None:
    """Appelé APRÈS la transaction qui a validé un lot : si la campagne envoie déjà
    (mode progressif), le nouveau lot d'envoi part ; et si c'était le dernier lot et
    que tout est déjà parti, la campagne se termine."""
    st = pg.valeur("SELECT status FROM campaigns WHERE id = %(c)s", {"c": campaign_id})
    if st != "sending":
        return
    empiler_lots(campaign_id)
    with pg.connexion() as cur:
        _terminer_si_fini(cur, campaign_id)


EXECUTEURS = {JOB_ENVOYER: envoyer_lot}
