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
import math
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import clients, controle_html, desinscription, domaines, fournisseurs, harmonisation, pg, preferences, rappel, stockage, sweego  # noqa: E402
from jobs import clics, file  # noqa: E402
from jobs.file import ErreurDefinitive  # noqa: E402

JOB_ENVOYER = "campaign.dispatch_sweego_batch"
PARIS = ZoneInfo("Europe/Paris")

# ── Fenêtre d'envoi (13/10/2026) ─────────────────────────────────────────────
# Camille : « le mode avion va faire envoyer quel jour, sur quel créneau, sur quelle plage ? ».
# Avant : un client envoyait à n'importe quelle heure, week-end compris, son plafond du jour
# en une rafale (600/min). Désormais chaque lot n'envoie QUE dans la fenêtre de sa campagne,
# et (client) répartit son plafond du jour heure par heure sur la plage.
FENETRE_INTERNE = {"debut": 8, "fin": 22, "jours": [1, 2, 3, 4, 5, 6, 7], "etale": False}
FENETRE_CLIENT = {"debut": 9, "fin": 18, "jours": [1, 2, 3, 4, 5], "etale": True}
JOURS_FR = ["", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def fenetre(camp: dict) -> dict:
    d = FENETRE_INTERNE if pg.schema_courant() == pg.SCHEMA else FENETRE_CLIENT
    debut, fin = camp.get("envoi_heure_debut"), camp.get("envoi_heure_fin")
    f = {"debut": d["debut"] if debut is None else int(debut), "fin": d["fin"] if fin is None else int(fin),
         "jours": sorted({int(j) for j in (camp.get("envoi_jours") or d["jours"])}) or d["jours"],
         "etale": d["etale"] if camp.get("envoi_etale") is None else bool(camp.get("envoi_etale"))}
    if f["fin"] <= f["debut"]:
        f["fin"] = min(24, f["debut"] + 1)
    return f


def dans_fenetre(f: dict, t: datetime) -> bool:
    t = t.astimezone(PARIS)
    return t.isoweekday() in f["jours"] and f["debut"] <= t.hour < f["fin"]


def prochaine_ouverture(f: dict, t: datetime) -> datetime:
    """Prochain début de plage d'un jour autorisé, STRICTEMENT après t (heure de Paris)."""
    t = t.astimezone(PARIS)
    for k in range(0, 9):
        j = (t + timedelta(days=k)).replace(hour=f["debut"], minute=2, second=0, microsecond=0)
        if j > t and j.isoweekday() in f["jours"]:
            return j
    return t + timedelta(days=1)


def part_de_la_journee(f: dict, t: datetime) -> float:
    """Part du plafond du jour autorisée à l'heure t : 1/n de la plage par heure entamée."""
    if not f["etale"]:
        return 1.0
    t = t.astimezone(PARIS)
    n = max(1, f["fin"] - f["debut"])
    return max(0.0, min(1.0, (t.hour - f["debut"] + 1) / n))
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
            "raison_sociale": p.get("raison_sociale"), "adresse_postale": p.get("adresse_postale"),
            # Espace client (SaaS) : le tag `tenant` route les événements Resend vers ce schéma.
            "tenant": pg.schema_courant()[4:] if pg.schema_courant() != pg.SCHEMA else ""}


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

    ajoute("public", c.get("audience") in ("b2c", "b2b", "mixte"), "Public choisi : particuliers (B2C), professionnels (B2B) ou mixte")
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
                                    rappel=c.get("rappel"), ligne_entete=c.get("entete_version_en_ligne") is not False)
        bloq = [p["message"] for p in an["problemes"] if p["niveau"] == "bloquant"]
        ajoute("controle_message", not bloq,
               f"Contrôle du message : note {an['score']}/100" + (f" — {'; '.join(bloq)}" if bloq else ", aucun problème bloquant"))
    exp = expediteur(c, profil)
    fourn = fournisseurs.module()          # Sweego (interne) ou Resend/SES (client)
    nom_f = fournisseurs.libelle()
    try:
        verifies = fourn.domaines_verifies()
    except Exception:  # noqa: BLE001
        verifies = None
    doms = c.get("sending_domains") or ([exp["from_email"].split("@")[1]] if exp else [])
    ajoute("expediteur", bool(exp and exp["from_name"]),
           "Expéditeur renseigné" + (f" : {exp['from_name']} <{exp['from_email']}>" if exp else ""))
    ajoute("domaines", bool(doms) and (verifies is None or all(d in verifies for d in doms)),
           f"Sous-domaine(s) vérifié(s) chez {nom_f} : " + (", ".join(doms) or "aucun")
           + ("" if verifies is not None else f" (liste {nom_f} illisible)"))
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
        essai = fourn.envoyer_un(destinataire="controle@example.com", subject=c["subject"],
                                  html_str=html, texte="x", expediteur={**exp, "_corps_seulement": True},
                                  campagne=f"mm-{campaign_id}", tags=[etiquette(campaign_id)],
                                  # Comme un vrai envoi : sans lui, Resend refuse (désinscription en un clic obligatoire).
                                  url_desinscription=desinscription.url(0))
        if essai.get("corps"):
            champs = fourn.valider_corps({**essai["corps"], "_marketing": False} if nom_f != "Sweego" else essai["corps"], verifies)
        ajoute("champs_sweego", bool(champs) and all(x["ok"] for x in champs),
               f"Requête {nom_f} conforme à la doc (" + (f"{sum(x['ok'] for x in champs)}/{len(champs)} champs" if champs else essai.get("erreur", "")) + ")")
        sw = fourn.envoyer_un(destinataire=exp["from_email"], subject=c["subject"],
                               html_str=desinscription.pied_de_mail(html, 0, exp["from_name"]),
                               texte=sweego.html_vers_texte(html), expediteur=exp,
                               # Étiquette à part : un test à blanc apparaît quand même
                               # dans les logs Sweego et fausserait les stats de la campagne.
                               campagne="mm-preflight", tags=["mm-preflight"],
                               url_desinscription=desinscription.url(0),
                               dry_run=True)
    ajoute("sweego", sw.get("ok"), f"{nom_f} accepte le message (test à blanc, rien n'est envoyé)"
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
                     "pc": json.dumps({"fournisseur": fournisseurs.nom(), "route": "1 destinataire par appel",
                                       "etiquette": etiquette(campaign_id),
                                       "profil": {k: profil[k] for k in ("from_name", "from_email", "reply_to", "sending_domain")}
                                       if profil else None}, default=str)})
        _audit(cur, campaign_id, "user", acteur, "sending.authorized", "Envoi autorisé")
    if pg.schema_courant() != pg.SCHEMA:
        # Espace client : routage par messagerie (vagues horaires, capacité apprise, warm-up).
        from jobs import routage
        routage.inscrire(campaign_id, acteur)
        return {"ok": True, "routage": True}
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
    # Campagne routée : les nouveaux lots validés rejoignent la RÉSERVE de l'agent de routage.
    from jobs import routage
    if routage.est_routee(campaign_id):
        return pg.ecrire("""UPDATE sending_batches SET status = 'scheduled'
                             WHERE campaign_id = %(c)s AND status = 'pending'""", {"c": campaign_id}) and 0
    n = 0
    for sb in pg.lignes("""SELECT id, sequence_number FROM sending_batches
                            WHERE campaign_id = %(c)s AND status = 'pending'
                            ORDER BY sequence_number""", {"c": campaign_id}):
        cle = f"dispatch:{sb['id']}"
        # Lot déjà tenté (reprise après pause/stop, 16/10/2026) : l'ancien job garde la clé ; on
        # en prend une neuve, sauf si un job de ce lot attend déjà (pas de doublon).
        if pg.valeur("""SELECT 1 FROM jobs WHERE job_type = %(t)s AND status IN ('pending','running')
                          AND payload->>'sending_batch_id' = %(s)s""", {"t": JOB_ENVOYER, "s": str(sb["id"])}):
            continue
        if pg.valeur("SELECT 1 FROM jobs WHERE idempotency_key = %(k)s", {"k": cle}):
            cle += f":reprise:{int(time.time())}"
        if file.empiler(JOB_ENVOYER, campaign_id=campaign_id,
                        payload={"sending_batch_id": str(sb["id"])},
                        idempotency_key=cle, priority=50 + sb["sequence_number"]):
            n += 1
    return n


# ── Stop et reprise (16/10/2026) ─────────────────────────────────────────────
# Camille : « une fonction pour la mettre en pause mais aussi pour la stopper, ce qui a pour
# conséquence de clore la campagne ; permet une relance en 2 clics ».
# Pause = rien de nouveau ne part, reprise par « Autoriser l'envoi ».
# Stop  = la campagne est close (statut « cancelled », affiché « Stoppée ») : lot en cours
#         interrompu, lots et jobs en attente annulés, routage coupé. Les destinataires non
#         envoyés gardent leur place : « Relancer » les remet en route (bouton + confirmation).
STATUTS_STOPPABLES = ("sending", "paused", "scheduled")


def stopper(campaign_id: str, acteur: str) -> dict:
    with pg.connexion() as cur:
        cur.execute("SELECT status FROM campaigns WHERE id = %(c)s FOR UPDATE", {"c": campaign_id})
        c = cur.fetchone()
        if not c:
            raise ErreurDefinitive("campagne introuvable")
        if c["status"] not in STATUTS_STOPPABLES:
            raise ErreurDefinitive(f"impossible de stopper une campagne « {c['status']} »")
        cur.execute("""UPDATE campaigns SET status = 'cancelled', stoppee_le = now(), statut_avant_stop = %(s)s,
                              paused_at = NULL, updated_at = now() WHERE id = %(c)s""",
                    {"c": campaign_id, "s": c["status"]})
        cur.execute("""UPDATE sending_batches SET status = 'cancelled'
                        WHERE campaign_id = %(c)s AND status IN ('pending','scheduled')""", {"c": campaign_id})
        cur.execute("""UPDATE jobs SET status = 'completed', last_error = 'annulé : campagne stoppée'
                        WHERE campaign_id = %(c)s AND job_type = %(t)s AND status = 'pending'""",
                    {"c": campaign_id, "t": JOB_ENVOYER})
        cur.execute("SELECT to_regclass('routage_campagnes') IS NOT NULL AS r")
        if cur.fetchone()["r"]:
            cur.execute("UPDATE routage_campagnes SET actif = false WHERE campaign_id = %(c)s", {"c": campaign_id})
        cur.execute("""SELECT count(*) FILTER (WHERE send_status = 'queued') AS restants,
                              count(*) FILTER (WHERE submitted_at IS NOT NULL) AS partis
                         FROM recipients WHERE campaign_id = %(c)s""", {"c": campaign_id})
        n = cur.fetchone()
        _audit(cur, campaign_id, "user", acteur, "sending.stopped",
               f"Campagne stoppée : {n['partis']} mail(s) parti(s), {n['restants']} gardé(s) pour une relance")
    return {"ok": True, "partis": n["partis"], "restants": n["restants"]}


def relancer_stoppee(campaign_id: str, acteur: str) -> dict:
    """Remet en route une campagne stoppée : ses destinataires non envoyés repartent, avec les
    mêmes contrôles que le feu vert (`autoriser`)."""
    with pg.connexion() as cur:
        cur.execute("SELECT status, stoppee_le FROM campaigns WHERE id = %(c)s FOR UPDATE", {"c": campaign_id})
        c = cur.fetchone()
        if not c or c["status"] != "cancelled" or not c["stoppee_le"]:
            raise ErreurDefinitive("seule une campagne stoppée peut être relancée ainsi")
        cur.execute("""SELECT count(*) AS n FROM recipients WHERE campaign_id = %(c)s AND send_status = 'queued'""",
                    {"c": campaign_id})
        if not cur.fetchone()["n"]:
            raise ErreurDefinitive("plus aucun destinataire à envoyer : rien à relancer")
        cur.execute("""UPDATE sending_batches SET status = 'pending'
                        WHERE campaign_id = %(c)s AND status = 'cancelled'
                          AND EXISTS (SELECT 1 FROM recipients r WHERE r.sending_batch_id = sending_batches.id
                                        AND r.send_status = 'queued')""", {"c": campaign_id})
        # Passage par « paused » : `autoriser` refait les contrôles et choisit routage ou lots.
        cur.execute("UPDATE campaigns SET status = 'paused', paused_at = now(), updated_at = now() WHERE id = %(c)s",
                    {"c": campaign_id})
    try:
        r = autoriser(campaign_id, acteur)
    except ErreurDefinitive as e:
        raise ErreurDefinitive(f"campagne remise en pause, relance refusée : {e}") from e
    with pg.connexion() as cur:
        _audit(cur, campaign_id, "user", acteur, "sending.restarted", "Campagne stoppée relancée")
    return r


# ── Un lot d'envoi ───────────────────────────────────────────────────────────

def envoyer_lot(job: dict, *, envoyeur=None) -> dict:
    # Fournisseur de l'espace courant : Sweego en interne, Resend/SES pour un client.
    envoyeur = envoyeur or fournisseurs.module().envoyer_un
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
        if sb["status"] == "scheduled":
            # Lot remis en RÉSERVE du routage (pause, A/B test) : c'est l'agent qui le resservira.
            return {"en_reserve": True}
        if sb["c_status"] in ("paused", "cancelled"):
            # Pause ou stop (16/10/2026) : le lot attend la reprise — ce n'est pas un échec
            # (avant : job « mort » et bandeau « Un traitement a échoué » sur la fiche).
            return {"en_attente": sb["c_status"]}
        if sb["c_status"] != "sending":
            # Pas de feu vert : le lot attend, le job ne sert à rien.
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
                                    url_miroir=desinscription.url_miroir(cid),
                                    ligne_entete=camp.get("entete_version_en_ligne") is not False)[0]
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
    dest = pg.lignes("""SELECT id, email_normalized, email_hash, variante FROM recipients
                         WHERE sending_batch_id = %(s)s AND send_status = 'queued' ORDER BY id""",
                     {"s": sb_id})
    # A/B test (15/10/2026) : chaque destinataire de l'échantillon reçoit SA version ; pendant le
    # test, un destinataire hors échantillon ne part pas — il retourne en réserve.
    from jobs import ab_test
    if ab_test.retenir(cid):
        hors = [d["id"] for d in dest if not d.get("variante")]
        if hors:
            reserve = pg.valeur("""SELECT id FROM sending_batches WHERE campaign_id = %(c)s AND status = 'scheduled'
                                    ORDER BY sequence_number LIMIT 1""", {"c": cid})
            if not reserve:
                seq = (pg.valeur("SELECT COALESCE(max(sequence_number), 0) FROM sending_batches WHERE campaign_id = %(c)s",
                                 {"c": cid}) or 0) + 1
                reserve = pg.valeur("""INSERT INTO sending_batches (campaign_id, sequence_number, recipients_count, status)
                                       VALUES (%(c)s, %(s)s, %(n)s, 'scheduled') RETURNING id""",
                                    {"c": cid, "s": seq, "n": len(hors)})
            pg.ecrire("UPDATE recipients SET sending_batch_id = %(b)s WHERE id = ANY(%(i)s) AND send_status = 'queued'",
                      {"b": reserve, "i": hors})
        dest = [d for d in dest if d.get("variante")]
        # Le plafond de warm-up garde les N premiers : on ordonne le lot pour que, place après place,
        # la version en retard sur toute la campagne passe d'abord (sinon l'ordre par id avantageait A, 15/10).
        partis = {x["variante"]: x["n"] for x in pg.lignes(
            """SELECT variante, count(*) AS n FROM recipients WHERE campaign_id = %(c)s
                 AND variante IS NOT NULL AND send_status <> 'queued' GROUP BY variante""", {"c": cid})}
        dest = ordre_rattrapage(dest, partis)
    versions = {}
    for v, x in ab_test.contenus(cid).items():
        h = harmonisation.harmoniser(sweego.nettoyer_html(x["html"]), preheader=x["preheader"],
                                     url_miroir=desinscription.url_miroir(cid),
                                     ligne_entete=camp.get("entete_version_en_ligne") is not False)[0]
        versions[v] = {"subject": x["subject"], "html": h, "texte": (x["text"] or "").strip() or sweego.html_vers_texte(h)}

    # Warm-up (espaces clients) : chaque adresse expéditrice a un plafond du jour ; ce qui
    # dépasse reste « queued » et le lot repart demain matin. Une adresse sans plan est refusée.
    reste_demain = 0
    fen = fenetre(camp)
    maintenant = datetime.now(PARIS)
    if not dans_fenetre(fen, maintenant):
        # Hors de la fenêtre de la campagne : rien ne part, le lot attend la prochaine ouverture.
        ouverture = prochaine_ouverture(fen, maintenant)
        pg.ecrire("UPDATE sending_batches SET status = 'pending' WHERE id = %(s)s", {"s": sb_id})
        file.empiler(JOB_ENVOYER, campaign_id=cid, payload={"sending_batch_id": str(sb_id)},
                     idempotency_key=f"dispatch:{sb_id}:{ouverture.isoformat(timespec='hours')}",
                     priority=50 + sb["sequence_number"], run_after=ouverture)
        return {"lot": sb["sequence_number"], "hors_fenetre": True, "reprise": ouverture.isoformat()}
    part = part_de_la_journee(fen, maintenant)
    from jobs import routage
    if routage.est_routee(cid):
        part = 1.0            # la vague est déjà dimensionnée par l'agent (heure, messagerie, warm-up)
    if pg.schema_courant() != pg.SCHEMA:
        dest, reste_demain = _plafond_warmup(camp, profil, dest, part)

    reglage = pg.ligne("SELECT max_rate_per_minute FROM settings")
    piege = bool(clics.regles().get("piege_actif", True))
    rappel_actif = bool((camp.get("rappel") or {}).get("actif"))
    intervalle = 60.0 / max(1, int(reglage["max_rate_per_minute"]))
    verrou, prochain = threading.Lock(), [time.monotonic()]
    # Quota du fournisseur atteint (ex. Resend gratuit : 100/jour) : on arrête le lot proprement,
    # les destinataires restants gardent leur place pour la prochaine ouverture (pas d'« échec »).
    quota_atteint = threading.Event()
    # Pause / stop pendant le lot (16/10/2026) : le statut est relu toutes les 10 s ; dès qu'il
    # n'est plus « sending », plus rien ne part et les restants gardent leur place (queued).
    interrompu, dernier_controle = threading.Event(), [time.monotonic()]

    def campagne_arretee() -> bool:
        if interrompu.is_set():
            return True
        with verrou:
            if time.monotonic() - dernier_controle[0] < 10:
                return False
            dernier_controle[0] = time.monotonic()
        if pg.valeur("SELECT status FROM campaigns WHERE id = %(c)s", {"c": cid}) != "sending":
            interrompu.set()
        return interrompu.is_set()

    def cadence():
        with verrou:
            attente = prochain[0] - time.monotonic()
            prochain[0] = max(prochain[0], time.monotonic()) + intervalle
        if attente > 0:
            time.sleep(attente)

    def un(d):
        if quota_atteint.is_set():
            return {"ok": False, "reporte": True}
        if campagne_arretee():
            return {"ok": False, "interrompu": True}
        cadence()
        exp = expediteur(camp, profil, d["email_hash"])
        ver = versions.get(d.get("variante") or "") or {"subject": sb["subject"], "html": html, "texte": texte}
        corps_html = desinscription.pied_de_mail(ver["html"], d["id"], exp["from_name"],
                                                 raison_sociale=exp.get("raison_sociale"),
                                                 adresse=exp.get("adresse_postale"))
        if rappel_actif:
            # Page de rappel : chaque lien de contenu y passe, puis renvoie vers sa cible.
            corps_html = rappel.envelopper_liens(corps_html, cid, d["id"], (camp.get("rappel") or {}).get("redirection") or "")
        if piege:
            corps_html = clics.ajouter_piege(corps_html, d["id"])
        r = envoyeur(destinataire=d["email_normalized"], subject=ver["subject"],
                     html_str=corps_html,
                     texte=ver["texte"] + desinscription.texte_pied(d["id"]) + (clics.texte_piege(d["id"]) if piege else ""),
                     expediteur=exp,
                     campagne=f"mm-{cid}", tags=[tag],
                     url_desinscription=desinscription.url(d["id"]))
        if not r.get("ok") and (r.get("quota") or r.get("statut") == 429):
            quota_atteint.set()
            return {"ok": False, "reporte": True, "erreur": r.get("erreur")}
        # Écrit tout de suite : si le worker meurt en route, on sait qui est parti.
        if r.get("ok"):
            pg.ecrire("""UPDATE recipients SET send_status = 'submitted', submitted_at = now(),
                                sweego_message_id = %(u)s, provider_message_id = %(u)s,
                                provider = %(pv)s, from_email = %(fe)s,
                                provider_raw_metadata = %(m)s::jsonb, updated_at = now()
                          WHERE id = %(i)s AND send_status = 'queued'""",
                      {"i": d["id"], "u": r.get("swg_uid"), "pv": r.get("provider") or "sweego",
                       "fe": exp["from_email"],
                       "m": json.dumps({"transaction_id": r.get("transaction_id")})})
        else:
            pg.ecrire("""UPDATE recipients SET send_status = 'failed', updated_at = now(),
                                provider_raw_metadata = %(m)s::jsonb
                          WHERE id = %(i)s AND send_status = 'queued'""",
                      {"i": d["id"], "m": json.dumps({"erreur": r.get("erreur"),
                                                      "incertain": r.get("incertain", False)})})
        return r

    with ThreadPoolExecutor(FILS_ENVOI) as ex:
        # `meme_espace` : sans lui, les fils écriraient les statuts d'un client dans l'espace interne.
        res = list(ex.map(pg.meme_espace(un), dest))
    acceptes = sum(1 for r in res if r.get("ok"))
    reportes = sum(1 for r in res if r.get("reporte"))
    interrompus = sum(1 for r in res if r.get("interrompu"))
    rejetes = len(res) - acceptes - reportes - interrompus
    if interrompus:
        # Pause ou stop en plein lot : le lot garde ses restants pour la reprise, sans nouveau job.
        etat = pg.valeur("SELECT status FROM campaigns WHERE id = %(c)s", {"c": cid})
        with pg.connexion() as cur:
            cur.execute("""UPDATE sending_batches SET status = %(st)s, dispatched_at = now(), accepted_count = %(a)s,
                                  rejected_count = %(r)s WHERE id = %(s)s""",
                        {"s": sb_id, "a": acceptes, "r": rejetes, "st": "cancelled" if etat == "cancelled" else "pending"})
            _audit(cur, cid, "worker", None, "sending.batch_interrupted",
                   f"Lot {sb['sequence_number']} : {acceptes} mail(s) parti(s), {interrompus} gardé(s) pour la reprise "
                   f"(campagne {'stoppée' if etat == 'cancelled' else 'en pause'})")
        return {"lot": sb["sequence_number"], "acceptes": acceptes, "interrompus": interrompus}
    reste_demain += reportes
    erreurs = sorted({r.get("erreur") for r in res if not r.get("ok")} - {None})[:5]

    with pg.connexion() as cur:
        cur.execute("""UPDATE sending_batches SET status = %(st)s, dispatched_at = now(),
                              completed_at = now(), accepted_count = %(a)s, rejected_count = %(r)s,
                              error_message = %(e)s WHERE id = %(s)s""",
                    {"s": sb_id, "a": acceptes, "r": rejetes,
                     "st": "pending" if reste_demain else ("completed" if acceptes or not rejetes else "failed"),
                     "e": "; ".join(erreurs) or None})
        _audit(cur, cid, "worker", None, "sending.batch_dispatched",
               f"Lot {sb['sequence_number']} : {acceptes} mail(s) parti(s)"
               + (f", {rejetes} refusé(s)" if rejetes else ""), {"erreurs": erreurs})
        if reste_demain:
            _audit(cur, cid, "worker", None, "sending.warmup_cap",
                   f"Lot {sb['sequence_number']} : {reste_demain} destinataire(s) en attente"
                   + (" (quota du fournisseur atteint)" if reportes else
                      " (étalement sur la journée)" if part < 1 else " (plafond de warm-up du jour atteint)"))
        _terminer_si_fini(cur, cid)
    if reste_demain:
        # Étalement : l'heure suivante si la plage n'est pas finie (et pas de quota fournisseur) ;
        # sinon : la prochaine ouverture (jour autorisé suivant).
        dans_une_heure = (maintenant + timedelta(hours=1)).replace(minute=2, second=0, microsecond=0)
        if part < 1 and not reportes and dans_fenetre(fen, dans_une_heure):
            reprise = dans_une_heure
        else:
            reprise = prochaine_ouverture(fen, maintenant.replace(hour=23, minute=59))
        file.empiler(JOB_ENVOYER, campaign_id=cid, payload={"sending_batch_id": str(sb_id)},
                     idempotency_key=f"dispatch:{sb_id}:{reprise.isoformat(timespec='hours')}",
                     priority=50 + sb["sequence_number"], run_after=reprise)
    return {"lot": sb["sequence_number"], "acceptes": acceptes, "rejetes": rejetes, "reste_demain": reste_demain}


def ordre_rattrapage(dest: list[dict], partis: dict) -> list[dict]:
    """Fonction pure : ordonne les destinataires A/B pour que tout préfixe du lot ramène l'écart
    cumulé (déjà partis + pris) au plus près de 0. Les autres restent à la fin."""
    files = {v: [d for d in dest if d.get("variante") == v] for v in ("A", "B")}
    compte = {v: int(partis.get(v, 0)) for v in ("A", "B")}
    out = []
    while files["A"] or files["B"]:
        v = min((x for x in ("A", "B") if files[x]), key=lambda x: (compte[x], x))
        out.append(files[v].pop(0))
        compte[v] += 1
    return out + [d for d in dest if d.get("variante") not in ("A", "B")]


def _plafond_warmup(camp: dict, profil: dict | None, dest: list[dict], part: float = 1.0) -> tuple[list[dict], int]:
    """Garde, par adresse expéditrice, au plus (plafond du jour × part de la journée écoulée
    − déjà envoyés aujourd'hui). `part` < 1 = étalement heure par heure sur la plage."""
    par_adresse: dict[str, list[dict]] = {}
    for d in dest:
        par_adresse.setdefault(expediteur(camp, profil, d["email_hash"])["from_email"].lower(), []).append(d)
    garde, reste = [], 0
    for adresse, lot in par_adresse.items():
        exp = pg.ligne("SELECT * FROM expediteurs WHERE lower(adresse) = %(a)s AND actif", {"a": adresse})
        cap = math.ceil((clients.plafond_du_jour(exp) if exp else 0) * part)
        deja = pg.valeur("""SELECT count(*) FROM recipients WHERE lower(from_email) = %(a)s
                              AND submitted_at >= date_trunc('day', now() AT TIME ZONE 'Europe/Paris') AT TIME ZONE 'Europe/Paris'""",
                         {"a": adresse}) or 0
        n = max(0, cap - int(deja))
        garde += lot[:n]
        reste += len(lot) - min(n, len(lot))
    return garde, reste


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
    if fournisseurs.nom() != "sweego":
        # Espace client (Resend/SES) : les statuts arrivent en direct par le webhook signé,
        # il n'y a pas de journal à relire — et surtout jamais celui de Sweego.
        n = pg.valeur("SELECT count(*) FROM recipients WHERE campaign_id = %(c)s AND submitted_at IS NOT NULL",
                      {"c": campaign_id}) or 0
        return {"ok": True, "source": "webhook", "fournisseur": fournisseurs.nom(), "envoyes": int(n)}
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
