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
from infra import controle_html, desinscription, domaines, harmonisation, pg, preferences, rappel, stockage, sweego  # noqa: E402
from jobs import clics, file  # noqa: E402
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


def expediteur(c: dict, profil: dict | None, email_hash: str | None = None) -> dict | None:
    """Le `from` d'un mail : nom, adresse, réponse à — pris sur la campagne (configuré à
    l'étape Message), le profil ne servant que de valeur par défaut.

    Plusieurs sous-domaines : le domaine est choisi par l'empreinte de l'adresse du
    destinataire, donc TOUJOURS le même pour une même personne, et réparti de façon
    stable entre les domaines."""
    p = profil or {}
    domaines = [d for d in (c.get("sending_domains") or []) if d] or \
               ([p["from_email"].rsplit("@", 1)[1]] if p.get("from_email") else [])
    local = (c.get("from_local") or (p.get("from_email") or "").split("@")[0]).strip()
    if not domaines or not local:
        return None
    d = domaines[int(email_hash[:8], 16) % len(domaines)] if email_hash and len(domaines) > 1 else domaines[0]
    return {"from_name": (c.get("from_name") or p.get("from_name") or "").strip(),
            "from_email": f"{local}@{d}", "reply_to": c.get("reply_to") or p.get("reply_to"),
            "campaign_type": c.get("campaign_type") or "market",
            "raison_sociale": p.get("raison_sociale"), "adresse_postale": p.get("adresse_postale")}


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

    ajoute("public", c.get("audience") in ("b2c", "b2b"), "Public choisi : particuliers (B2C) ou professionnels (B2B)")
    if c.get("audience") == "b2c":
        r_dom = domaines.regles()
        pros = sum(1 for x in pg.lignes("""SELECT email_normalized FROM recipients WHERE campaign_id = %(c)s
                                             AND target_version_id = %(t)s AND eligibility_status = 'eligible'
                                             AND submitted_at IS NULL""", {"c": campaign_id, "t": c["target_version_id"]})
                   if domaines.hors_cible(x["email_normalized"], "b2c", r_dom))
        ajoute("b2c", pros == 0, "Campagne B2C : aucune adresse d'entreprise ou d'administration" if pros == 0
               else f"Campagne B2C : {pros} adresse(s) d'entreprise ou d'administration encore dans la cible")
    ajoute("objet", (c["subject"] or "").strip(), "Objet renseigné")
    ajoute("html", html.strip(), "Message HTML présent")
    ajoute("desinscription", True, "Lien de désinscription personnel ajouté en pied de chaque mail")
    ajoute("https", not [l for l in liens if l.lower().startswith("http://")],
           "Tous les liens sont en https", bloquant=False)
    ajoute("jetons", "{{" not in html, "Aucune variable {{…}} oubliée dans le message")
    # Le contrôle complet du message (liens morts, HTML, anti-spam) : ses problèmes
    # bloquants bloquent aussi l'envoi.
    if html.strip():
        an = controle_html.analyser(html, objet=c["subject"] or "", preheader=c["preheader"] or "",
                                    expediteur=profil or {}, url_miroir=desinscription.url_miroir(campaign_id),
                                    rappel=c.get("rappel"))
        bloq = [p["message"] for p in an["problemes"] if p["niveau"] == "bloquant"]
        ajoute("controle_message", not bloq,
               f"Contrôle du message : note {an['score']}/100" + (f" — {'; '.join(bloq)}" if bloq else ", aucun problème bloquant"))
    exp = expediteur(c, profil)
    try:
        verifies = sweego.domaines_verifies()
    except Exception:  # noqa: BLE001
        verifies = None
    doms = c.get("sending_domains") or ([exp["from_email"].split("@")[1]] if exp else [])
    ajoute("expediteur", bool(exp and exp["from_name"]),
           "Expéditeur renseigné" + (f" : {exp['from_name']} <{exp['from_email']}>" if exp else ""))
    ajoute("domaines", bool(doms) and (verifies is None or all(d in verifies for d in doms)),
           "Sous-domaine(s) vérifié(s) chez Sweego : " + (", ".join(doms) or "aucun")
           + ("" if verifies is not None else " (liste Sweego illisible)"))
    # Réputation d'envoi (Camille, 27/09) : IP Sweego et domaine(s) d'envoi absents des listes
    # noires, d'après HetrixTools. Listé → BLOQUANT ; non vérifiable → avertissement.
    try:
        from infra import hetrix
        rep = hetrix.reputation_envoi(doms)
    except Exception as e:  # noqa: BLE001
        rep = {"verifie": False, "ok": None, "raison": str(e)[:120], "elements": []}
    listees = [x for x in rep["elements"] if x["etat"] == "listee"]
    if listees:
        ajoute("reputation", False, "Réputation d'envoi : " + ", ".join(
            f"{x['cible']} listé sur {', '.join(l['rbl'] for l in x['listes']) or 'une liste noire'}" for x in listees))
    elif rep["verifie"] and rep.get("avertissement"):
        # Listé seulement sur une liste de réseau entier (UCEPROTECT 2/3) : on prévient, on ne bloque pas.
        ajoute("reputation", False, "Réputation d'envoi : " + rep.get("raison", ""), bloquant=False)
    elif rep["verifie"]:
        ajoute("reputation", True, "Réputation d'envoi : " + ", ".join(
            f"{x['role']} {x['cible']} propre" for x in rep["elements"]) + " (HetrixTools)")
    else:
        ajoute("reputation", False, f"Réputation d'envoi non vérifiée ({rep.get('raison') or 'HetrixTools'})", bloquant=False)
    ajoute("cible", eligibles > 0 or en_validation > 0,
           f"{eligibles} destinataire(s) éligible(s)"
           + (f", {en_validation} lot(s) encore en validation" if en_validation else ""))
    # Sweego accepte-t-il ce message avec ce profil ? Test à blanc : rien n'est envoyé.
    sw = {"ok": False, "erreur": "non testé"}
    champs = []
    if exp and html.strip() and (c["subject"] or "").strip():
        # Le corps exact qu'enverrait un vrai mail, contrôlé champ par champ (doc Sweego).
        essai = sweego.envoyer_un(destinataire="controle@example.com", subject=c["subject"],
                                  html_str=html, texte="x", expediteur={**exp, "_corps_seulement": True},
                                  campagne=f"mm-{campaign_id}", tags=[etiquette(campaign_id)])
        if essai.get("corps"):
            champs = sweego.valider_corps(essai["corps"], verifies)
        ajoute("champs_sweego", bool(champs) and all(x["ok"] for x in champs),
               "Requête Sweego conforme à la doc (" + (f"{sum(x['ok'] for x in champs)}/{len(champs)} champs" if champs else essai.get("erreur", "")) + ")")
        sw = sweego.envoyer_un(destinataire=exp["from_email"], subject=c["subject"],
                               html_str=desinscription.pied_de_mail(html, 0, exp["from_name"]),
                               texte=sweego.html_vers_texte(html), expediteur=exp,
                               # Étiquette à part : un test à blanc apparaît quand même
                               # dans les logs Sweego et fausserait les stats de la campagne.
                               campagne="mm-preflight", tags=["mm-preflight"],
                               dry_run=True)
    ajoute("sweego", sw.get("ok"), "Sweego accepte le message (test à blanc, rien n'est envoyé)"
           + ("" if sw.get("ok") else f" — {sw.get('erreur')}"))

    ok = all(x["ok"] for x in ctrl if x["bloquant"])
    snap = {"ok": ok, "controles": ctrl, "champs_sweego": champs, "html_hash": c["html_hash"], "subject": c["subject"],
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
        # Les deux modes peuvent partir pendant la validation : en « progressive », chaque
        # lot validé part aussitôt ; en « after_validation », les lots d'envoi ne sont créés
        # qu'à la fin de la validation, et partent alors tous ensemble.
        permis = ("ready_to_schedule", "paused", "scheduled", "validating_list")
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
    c = pg.ligne("""SELECT dispatch_mode,
                           (SELECT count(*) FROM validation_batches v WHERE v.campaign_id = c.id
                             AND v.status <> 'completed') AS restants
                      FROM campaigns c WHERE c.id = %(c)s""", {"c": campaign_id})
    # « Tout d'un coup » : rien ne part tant que la validation n'est pas finie, même si
    # des lots d'envoi existent déjà (le mode a pu changer en cours de route).
    if c and c["dispatch_mode"] == "after_validation" and c["restants"]:
        return 0
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
    camp = pg.ligne("SELECT * FROM campaigns WHERE id = %(c)s", {"c": cid})
    if not expediteur(camp, profil):
        raise ErreurDefinitive("expéditeur non configuré")
    html = stockage.lire(sb["html_storage_key"]).decode("utf-8", "replace")
    html = sweego.nettoyer_html(html)
    # Script de vérification : une seule ligne d'en-tête, un seul pré-en-tête.
    html = harmonisation.harmoniser(html, preheader=camp.get("preheader") or "",
                                    url_miroir=desinscription.url_miroir(cid))[0]
    # Version texte rédigée à l'étape Message si elle existe, sinon conversion automatique.
    texte = (camp.get("text_content") or "").strip() or sweego.html_vers_texte(html)
    tag = etiquette(cid)

    # Suppression relue MAINTENANT, juste avant le départ.
    pg.ecrire("""
        UPDATE recipients r SET send_status = 'skipped', eligibility_status = 'excluded',
                                eligibility_reason = 'suppressed', updated_at = now()
         WHERE r.sending_batch_id = %(s)s AND r.send_status = 'queued'
           AND EXISTS (SELECT 1 FROM suppressions x WHERE x.email_hash = r.email_hash AND """ + pg.SUPPRESSION_ACTIVE.format(t="x") + """
                         AND (x.scope = 'global' OR (x.scope = 'campaign' AND x.scope_id = r.campaign_id)))
    """, {"s": sb_id})
    # Dernier verrou B2C : aucune adresse d'organisation ne part d'une campagne grand public,
    # même si une règle de domaine a changé après la validation.
    if camp.get("audience") == "b2c":
        r_dom = domaines.regles()
        pros = [x["id"] for x in pg.lignes("""SELECT id, email_normalized FROM recipients
                                               WHERE sending_batch_id = %(s)s AND send_status = 'queued'""", {"s": sb_id})
                if domaines.hors_cible(x["email_normalized"], "b2c", r_dom)]
        if pros:
            pg.ecrire("""UPDATE recipients SET send_status = 'skipped', eligibility_status = 'excluded',
                                eligibility_reason = 'hors_cible_b2c', updated_at = now()
                          WHERE id = ANY(%(i)s) AND send_status = 'queued'""", {"i": pros})
    # Pression marketing choisie sur la page de préférences (pause, 1 email par mois).
    preferences.filtre_envoi(sb_id)
    dest = pg.lignes("""SELECT id, email_normalized, email_hash FROM recipients
                         WHERE sending_batch_id = %(s)s AND send_status = 'queued' ORDER BY id""",
                     {"s": sb_id})

    reglage = pg.ligne("SELECT max_rate_per_minute FROM settings")
    piege = bool(clics.regles().get("piege_actif", True))
    rappel_actif = bool((camp.get("rappel") or {}).get("actif"))
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
        exp = expediteur(camp, profil, d["email_hash"])
        corps_html = desinscription.pied_de_mail(html, d["id"], exp["from_name"],
                                                 raison_sociale=exp.get("raison_sociale"),
                                                 adresse=exp.get("adresse_postale"))
        if rappel_actif:
            # Page de rappel : chaque lien de contenu y passe, puis renvoie vers sa cible.
            corps_html = rappel.envelopper_liens(corps_html, cid, d["id"], (camp.get("rappel") or {}).get("redirection") or "")
        if piege:
            corps_html = clics.ajouter_piege(corps_html, d["id"])
        r = envoyeur(destinataire=d["email_normalized"], subject=sb["subject"],
                     html_str=corps_html,
                     texte=texte + desinscription.texte_pied(d["id"]) + (clics.texte_piege(d["id"]) if piege else ""),
                     expediteur=exp,
                     campagne=f"mm-{cid}", tags=[tag],
                     url_desinscription=desinscription.url(d["id"]))
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

SYNCHRO_TOUTES_LES_S = 600      # l'interface l'annonce : « mise à jour toutes les 10 minutes »


def synchroniser_recentes(jours: int = 30) -> int:
    """Resynchronise les stats de toutes les campagnes parties depuis `jours` jours —
    appelé par le worker toutes les 10 min (les logs Sweego ont plusieurs minutes de retard)."""
    n = 0
    for c in pg.lignes("""SELECT id FROM campaigns WHERE started_at > now() - make_interval(days => %(j)s)
                           AND status IN ('sending','paused','completed','completed_with_warnings')""", {"j": jours}):
        synchroniser(str(c["id"]))
        n += 1
    return n


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
                -- Clic : seulement si nous n'avons pas le détail (webhook) de ce destinataire ;
                -- sinon c'est notre filtre anti-robots qui décide (jobs/clics.py).
                clicked_at   = CASE WHEN %(k)s AND NOT EXISTS (SELECT 1 FROM clicks k WHERE k.recipient_id = recipients.id)
                                    THEN COALESCE(clicked_at, %(t)s) ELSE clicked_at END,
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
    # Heure d'ouverture = premier événement d'ouverture/clic non-proxy reçu par webhook (27/09) :
    # `email_last_update` des logs n'est que l'heure de la dernière mise à jour (souvent la livraison).
    pg.ecrire("""
        UPDATE recipients r SET opened_at = w.premier, updated_at = now()
          FROM (SELECT email_hash, min((raw_payload->>'timestamp')::timestamptz) AS premier
                  FROM webhook_events
                 WHERE campaign_id = %(c)s AND event_type IN ('email_opened', 'email_clicked')
                   AND COALESCE(raw_payload->'open'->>'proxy', raw_payload->'click'->>'proxy', 'false') <> 'true'
                 GROUP BY email_hash) w
         WHERE r.campaign_id = %(c)s AND r.email_hash = w.email_hash AND r.opened_at IS NOT NULL
           AND r.opened_at IS DISTINCT FROM w.premier
    """, {"c": campaign_id})
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
                         """ + pg.SUPPRESSION_SUR_CONFLIT,
                      {"m": motif, "u": x.get("swg_uid"), "c": campaign_id})
    # Plainte reçue par WEBHOOK (28/09 : les logs n'avaient pas le drapeau `spam`, la plaignante n'était
    # ni marquée ni supprimée) : marquage du destinataire + suppression globale, définitive.
    pg.ecrire("""UPDATE recipients r SET complained_at = COALESCE(r.complained_at, w.t), updated_at = now()
                   FROM (SELECT email_hash, min((raw_payload->>'timestamp')::timestamptz) AS t FROM webhook_events
                          WHERE campaign_id = %(c)s AND event_type ILIKE '%%complaint%%' GROUP BY email_hash) w
                  WHERE r.campaign_id = %(c)s AND r.email_hash = w.email_hash AND r.complained_at IS NULL""",
              {"c": campaign_id})
    pg.ecrire("""INSERT INTO suppressions (email_hash, email_normalized, reason, source, scope, metadata)
                 SELECT r.email_hash, r.email_normalized, 'complaint', 'sweego', 'global',
                        jsonb_build_object('swg_uid', r.sweego_message_id, 'origine', 'webhook')
                   FROM recipients r WHERE r.campaign_id = %(c)s AND r.complained_at IS NOT NULL
                    AND NOT EXISTS (SELECT 1 FROM suppressions s WHERE s.email_hash = r.email_hash AND s.reason = 'complaint')
                 """ + pg.SUPPRESSION_SUR_CONFLIT, {"c": campaign_id})
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


def declencher_programmations() -> list[str]:
    """Appelé par le worker à chaque tour : les campagnes dont l'heure est venue partent.
    Les contrôles sont refaits au départ ; s'ils échouent, la campagne reste programmée
    et l'erreur est journalisée (rien ne part sur un message devenu invalide)."""
    parties = []
    for c in pg.lignes("""SELECT id FROM campaigns WHERE status = 'scheduled'
                           AND scheduled_at <= now() ORDER BY scheduled_at LIMIT 5"""):
        cid = str(c["id"])
        try:
            snap = preflight(cid, "planification")
            if not snap.get("ok"):
                raise ErreurDefinitive("contrôles avant envoi bloqués au moment du départ")
            autoriser(cid, "planification")
            parties.append(cid)
        except ErreurDefinitive as e:
            pg.ecrire("""UPDATE campaigns SET status = 'paused', paused_at = now(), updated_at = now()
                          WHERE id = %(c)s AND status = 'scheduled'""", {"c": cid})
            with pg.connexion() as cur:
                _audit(cur, cid, "system", "planification", "sending.schedule_failed",
                       f"Départ programmé annulé : {e}")
    return parties


EXECUTEURS = {JOB_ENVOYER: envoyer_lot}
