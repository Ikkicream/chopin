"""
campagne_commerciale.py — les campagnes d'un commercial, envoyées depuis SA boîte Gmail.

Lot 2 de la demande de Camille du 2026-10-26 (le lot 1 est `boite_commercial.py`).

Règles, toutes décidées avec Camille :
  - **Cibles = ses contacts attribués**, rien d'autre : `contact_followup.assigned_to` vaut
    son identifiant, sur ce site, non retiré, dossier encore ouvert. Contrôlé ici, côté
    serveur, au moment de créer la campagne ET au moment d'envoyer (une attribution peut
    changer entre les deux).
  - **Contact sain** : `etat = 'ok'`, pas sur liste noire, pas une fiche de test.
  - **1 destinataire = 1 email** : un appel `send_email` par personne, jamais de groupe.
  - **120 jours** : appliqués par `maildoso_backend.send_email` (identifiant de lot à six
    segments), tous canaux confondus — et nos envois comptent à leur tour pour les autres.
  - **Fenêtre lun-sam 08:01-17:59**, **4 minutes** minimum entre deux envois de la boîte :
    aussi dans `send_email`, le seul point de passage.
  - **Chauffe** : rien tant que `boite_commercial.etat()["envoi_possible"]` est faux, puis
    jamais plus que `plafond_aujourdhui` envois Gmail dans la journée.
  - **Étalement** : le reste du jour est réparti sur le reste de la fenêtre, avec un peu
    d'aléa — un envoi régulier ressemble à quelqu'un qui travaille.

Le moteur tourne par le cron (`tick`, toutes les 5 minutes) : au plus UN email par boîte
et par passage.
"""
from __future__ import annotations

import random
import sys
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, "/home/autoblog/genesis/scripts")

STATUTS_OUVERTS = ("a_faire", "en_cours", "a_relancer")
PIED_DESINSCRIPTION = ("\n\nSi vous ne souhaitez plus recevoir mes messages, répondez "
                       "simplement « stop » à cet email.")
MOTS_DESINSCRIPTION = ("stop", "désinscri", "desinscri", "unsubscribe", "ne plus recevoir")

SCHEMA = """
CREATE TABLE IF NOT EXISTS campagnes_commerciales (
    id           text PRIMARY KEY,
    utilisateur  text NOT NULL,
    site         text NOT NULL,
    nom          text NOT NULL,
    sujet        text NOT NULL,
    corps        text NOT NULL,
    statut       text NOT NULL DEFAULT 'brouillon',   -- brouillon | active | pause | terminee
    cree_le      timestamptz NOT NULL DEFAULT now(),
    lancee_le    timestamptz,
    maj_le       timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS campagne_commerciale_cibles (
    campagne_id  text NOT NULL REFERENCES campagnes_commerciales(id) ON DELETE CASCADE,
    email        text NOT NULL,
    statut       text NOT NULL DEFAULT 'en_attente',  -- en_attente | envoye | ecarte | erreur
    motif        text,
    essais       int  NOT NULL DEFAULT 0,
    envoye_le    timestamptz,
    PRIMARY KEY (campagne_id, email)
);
CREATE INDEX IF NOT EXISTS idx_ccc_attente ON campagne_commerciale_cibles (campagne_id)
    WHERE statut = 'en_attente';
"""
_PRET = False


def _pg():
    import pool_pg
    global _PRET
    if not _PRET:
        pool_pg._ecrire(SCHEMA)
        _PRET = True
    return pool_pg


# ── Les contacts autorisés ────────────────────────────────────────────────────
_ELIGIBLES_SQL = """
    SELECT lower(f.email::text), c.prenom, c.nom, c.societe, c.city, f.statut, c.sectors
      FROM contact_followup f
      JOIN contacts c ON lower(c.email::text) = lower(f.email::text)
     WHERE f.assigned_to = %(u)s AND f.site_code = %(site)s
       AND f.retire_at IS NULL AND f.statut = ANY(%(ouverts)s)
       AND c.etat = 'ok' AND NOT COALESCE(c.global_blacklisted, false)
       AND NOT COALESCE(c.est_test, false)
"""


def contacts_eligibles(utilisateur: str, site: str) -> list[dict]:
    """Ses contacts attribués, sains, et qui n'ont rien reçu depuis 120 jours."""
    import journal_pg
    from contacts_pool_backend import SUPPRESSION_DAYS
    lignes = _pg()._q(_ELIGIBLES_SQL + " ORDER BY c.societe NULLS LAST, 1",
                      {"u": utilisateur, "site": site, "ouverts": list(STATUTS_OUVERTS)})
    servis = journal_pg.recemment_servis([l[0] for l in lignes], SUPPRESSION_DAYS)
    vus, out = set(), []
    for email, prenom, nom, societe, ville, statut, secteurs in lignes:
        if email in vus or email in servis:
            continue
        vus.add(email)
        out.append({"email": email, "prenom": prenom or "", "nom": nom or "",
                    "societe": societe or "", "city": ville or "", "statut": statut,
                    "secteur": (secteurs or [""])[0] or ""})
    return out


def _contact_autorise(utilisateur: str, site: str, email: str) -> dict | None:
    r = _pg()._q(_ELIGIBLES_SQL + " AND lower(f.email::text) = %(e)s LIMIT 1",
                 {"u": utilisateur, "site": site, "ouverts": list(STATUTS_OUVERTS),
                  "e": email.lower()})
    if not r:
        return None
    email, prenom, nom, societe, ville, _, _ = r[0]
    return {"email": email, "prenom": prenom or "", "nom": nom or "",
            "societe": societe or "", "city": ville or ""}


# ── Le message ────────────────────────────────────────────────────────────────
def _avec_desinscription(corps: str) -> str:
    bas = corps.lower()
    if any(m in bas for m in MOTS_DESINSCRIPTION):
        return corps
    return corps.rstrip() + PIED_DESINSCRIPTION


def apercu(utilisateur: str, site: str, sujet: str, corps: str, email: str | None = None) -> dict:
    """Le message tel que CE contact le recevrait, avec le verdict du garde-fou."""
    import maildoso_backend as md
    import qualite_message as qm
    import garde_variables as gvar
    contacts = contacts_eligibles(utilisateur, site)
    contact = next((c for c in contacts if c["email"] == (email or "").lower()), None) \
        or (contacts[0] if contacts else {"email": "exemple@exemple.fr", "prenom": "Marie",
                                           "societe": "Exemple SARL", "city": "Lyon"})
    corps = _avec_desinscription(corps or "")
    mb = {"email": "vous@leclientroi.com", "sender_name": _nom_expediteur(utilisateur)}
    s = qm.conditionnel(qm.spintax(sujet or "", contact["email"]), contact)
    t = qm.conditionnel(qm.spintax(corps, contact["email"]), contact)
    gabarits = [x for x in (s, t) if x]
    s, t = md._apply_tokens(s, contact, mb), md._apply_tokens(t, contact, mb)
    s, t = gvar.nettoyer_ponctuation(s), gvar.nettoyer_ponctuation(t)
    verdict = gvar.verifier_avant_envoi(s, t, None, contact, gabarits)
    return {"contact": contact, "sujet": s, "corps": t, "ok": verdict["ok"],
            "motifs": verdict.get("motifs", [])}


def _nom_expediteur(utilisateur: str) -> str:
    import boite_commercial as bc
    l = bc._ligne(utilisateur) or {}
    return l.get("nom_affiche") or utilisateur


def _texte_vers_html(texte: str) -> str:
    """Le même message en HTML minimal : il porte le pixel d'ouverture et les liens suivis.

    Volontairement nu (pas de gabarit, pas d'image) : il doit ressembler à un email écrit
    à la main, comme la version texte qui l'accompagne.
    """
    import html as _h
    import re as _re
    t = _h.escape(texte or "")
    t = _re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', t)
    paragraphes = [p.replace("\n", "<br>") for p in t.split("\n\n")]
    return ('<html><body style="font-family:Arial,sans-serif;font-size:14px;color:#222">'
            + "".join(f"<p>{p}</p>" for p in paragraphes) + "</body></html>")


# ── Les campagnes ─────────────────────────────────────────────────────────────
_COLS = ("id", "utilisateur", "site", "nom", "sujet", "corps", "statut", "cree_le",
         "lancee_le", "maj_le")


def _campagne(cid: str, utilisateur: str) -> dict | None:
    r = _pg()._q(f"SELECT {', '.join(_COLS)} FROM campagnes_commerciales "
                 "WHERE id = %s AND utilisateur = %s", (cid, utilisateur))
    return dict(zip(_COLS, r[0])) if r else None


def lister(utilisateur: str, site: str) -> list[dict]:
    lignes = _pg()._q(f"""
        SELECT {', '.join('c.' + x for x in _COLS)},
               count(t.email) AS total,
               count(t.email) FILTER (WHERE t.statut = 'envoye')     AS envoyes,
               count(t.email) FILTER (WHERE t.statut = 'en_attente') AS en_attente,
               count(t.email) FILTER (WHERE t.statut = 'ecarte')     AS ecartes,
               count(t.email) FILTER (WHERE t.statut = 'erreur')     AS erreurs
          FROM campagnes_commerciales c
          LEFT JOIN campagne_commerciale_cibles t ON t.campagne_id = c.id
         WHERE c.utilisateur = %s AND c.site = %s
         GROUP BY c.id ORDER BY c.cree_le DESC""", (utilisateur, site))
    out = []
    for r in lignes:
        d = dict(zip(_COLS + ("total", "envoyes", "en_attente", "ecartes", "erreurs"), r))
        for k in ("cree_le", "lancee_le", "maj_le"):
            d[k] = d[k].isoformat() if d[k] else None
        out.append(d)
    return out


def detail(utilisateur: str, cid: str) -> dict | None:
    c = _campagne(cid, utilisateur)
    if not c:
        return None
    for k in ("cree_le", "lancee_le", "maj_le"):
        c[k] = c[k].isoformat() if c[k] else None
    c["cibles"] = [{"email": e, "statut": s, "motif": m,
                    "envoye_le": d.isoformat() if d else None}
                   for e, s, m, d in _pg()._q(
                       "SELECT email, statut, motif, envoye_le FROM campagne_commerciale_cibles "
                       "WHERE campagne_id = %s ORDER BY envoye_le DESC NULLS LAST, email", (cid,))]
    return c


def creer(utilisateur: str, site: str, nom: str, sujet: str, corps: str,
          emails: list[str]) -> dict:
    nom, sujet, corps = (nom or "").strip(), (sujet or "").strip(), (corps or "").strip()
    if not nom or not sujet or not corps:
        return {"error": "Nom, objet et message sont obligatoires."}
    autorises = {c["email"] for c in contacts_eligibles(utilisateur, site)}
    choisis = sorted({(e or "").strip().lower() for e in emails} & autorises)
    if not choisis:
        return {"error": "Aucun des contacts choisis n'est l'un de tes contacts éligibles."}
    cid = uuid.uuid4().hex[:10]
    pg = _pg()
    pg._ecrire("INSERT INTO campagnes_commerciales (id, utilisateur, site, nom, sujet, corps) "
               "VALUES (%s, %s, %s, %s, %s, %s)", (cid, utilisateur, site, nom, sujet, corps))
    for e in choisis:
        pg._ecrire("INSERT INTO campagne_commerciale_cibles (campagne_id, email) VALUES (%s, %s) "
                   "ON CONFLICT DO NOTHING", (cid, e))
    return {"ok": True, "id": cid, "cibles": len(choisis),
            "ignores": len({(e or "").strip().lower() for e in emails}) - len(choisis)}


def modifier(utilisateur: str, cid: str, nom: str, sujet: str, corps: str) -> dict:
    c = _campagne(cid, utilisateur)
    if not c:
        return {"error": "Campagne introuvable."}
    if c["statut"] not in ("brouillon", "pause"):
        return {"error": "Mets la campagne en pause avant de modifier le message."}
    _pg()._ecrire("UPDATE campagnes_commerciales SET nom = %s, sujet = %s, corps = %s, "
                  "maj_le = now() WHERE id = %s", (nom.strip(), sujet.strip(), corps.strip(), cid))
    return {"ok": True}


def changer_statut(utilisateur: str, cid: str, action: str) -> dict:
    c = _campagne(cid, utilisateur)
    if not c:
        return {"error": "Campagne introuvable."}
    cible = {"lancer": "active", "pause": "pause", "reprendre": "active",
             "terminer": "terminee"}.get(action)
    if not cible:
        return {"error": "Action inconnue."}
    if c["statut"] == "terminee":
        return {"error": "Cette campagne est terminée."}
    if cible == "active":
        # Le message doit passer le garde-fou pour au moins un contact avant de lancer.
        a = apercu(utilisateur, c["site"], c["sujet"], c["corps"])
        if not a["ok"]:
            return {"error": "Le message ne passe pas le contrôle : " + "; ".join(a["motifs"][:2])}
    _pg()._ecrire("UPDATE campagnes_commerciales SET statut = %s, maj_le = now(), "
                  "lancee_le = COALESCE(lancee_le, CASE WHEN %s = 'active' THEN now() END) "
                  "WHERE id = %s", (cible, cible, cid))
    return {"ok": True, "statut": cible}


def supprimer(utilisateur: str, cid: str) -> dict:
    c = _campagne(cid, utilisateur)
    if not c:
        return {"error": "Campagne introuvable."}
    if c["statut"] != "brouillon":
        return {"error": "Seul un brouillon se supprime ; termine plutôt la campagne."}
    _pg()._ecrire("DELETE FROM campagnes_commerciales WHERE id = %s", (cid,))
    return {"ok": True}


# ── Le moteur ─────────────────────────────────────────────────────────────────
def envoyes_aujourdhui(mailbox: str) -> int:
    r = _pg()._q("""
        SELECT count(*) FROM email_events
         WHERE event_type = 'sent' AND channel = 'gmail' AND mailbox = %s
           AND timezone('Europe/Paris', occurred_at)::date = timezone('Europe/Paris', now())::date
    """, (mailbox,))
    return int(r[0][0]) if r else 0


def _secondes_restantes_fenetre() -> int:
    import fenetre_envoi as fe
    p = fe.profil("campagne")
    q = fe.maintenant()
    h, m = (int(x) for x in p["fin"].split(":"))
    fin = q.replace(hour=h, minute=m, second=0, microsecond=0)
    return max(0, int((fin - q).total_seconds()))


def capacite(utilisateur: str, site: str) -> dict:
    """Combien ce commercial peut envoyer AUJOURD'HUI, et pourquoi — pour l'écran.

    Les mêmes règles que le moteur : boîte prête, plafond de chauffe du jour moins ce qui
    est déjà parti, et au plus un email toutes les 4 minutes dans ce qui reste de la
    fenêtre lun-sam 08:01-17:59.
    """
    import boite_commercial as bc
    import fenetre_envoi as fe
    import maildoso_backend as md
    et = bc.etat(utilisateur)
    ch = et.get("chauffe") or {}
    boite = bc._ligne(utilisateur) or {}
    deja = envoyes_aujourdhui(boite["email"]) if boite.get("email") else 0
    plafond = int(ch.get("plafond_aujourdhui") or 0)
    ouverte, motif = fe.ouverte("campagne")
    par_rythme = (_secondes_restantes_fenetre() // md.ECART_MIN_BOITE + 1) if ouverte else 0
    reste = max(0, plafond - deja) if et.get("envoi_possible") else 0
    en_attente = _pg()._q("""
        SELECT count(*) FROM campagne_commerciale_cibles t
          JOIN campagnes_commerciales c ON c.id = t.campagne_id
         WHERE c.utilisateur = %s AND c.site = %s AND c.statut = 'active'
           AND t.statut = 'en_attente'""", (utilisateur, site))[0][0]
    return {
        "aujourdhui": min(reste, par_rythme), "plafond": plafond, "deja_envoyes": deja,
        "fenetre_ouverte": ouverte, "fenetre_motif": motif,
        "envoi_possible": bool(et.get("envoi_possible")), "raisons": et.get("raisons", []),
        "connectee": bool(et.get("connectee")), "email": et.get("email"),
        "jour_chauffe": ch.get("jour"), "phase": ch.get("phase"),
        "jours_avant_premier_cold": ch.get("jours_avant_premier_cold"),
        "plafond_max": ch.get("plafond_max") or 35,
        # Les 7 prochains jours où la boîte AURA le droit d'envoyer (pendant la chauffe,
        # les jours à zéro n'apprennent rien).
        "prochains_jours": [c for c in (ch.get("courbe") or [])
                            if c["date"] > fe.maintenant().date().isoformat() and c["plafond"] > 0][:7],
        "en_attente": int(en_attente),
    }


def _assez_espace(mailbox: str, reste_jour: int) -> tuple[bool, str]:
    """L'étalement : attendre (fenêtre restante / envois restants), à 70-100 %."""
    import maildoso_backend as md
    ecoule = md._secondes_depuis_dernier_envoi(mailbox)
    if ecoule is None:
        return True, ""
    ecart = max(md.ECART_MIN_BOITE,
                _secondes_restantes_fenetre() / max(1, reste_jour) * random.uniform(0.7, 1.0))
    if ecoule < ecart:
        return False, f"étalement : prochain envoi dans {int(ecart - ecoule)} s"
    return True, ""


def _marquer(cid: str, email: str, statut: str, motif: str | None = None) -> None:
    _pg()._ecrire("""UPDATE campagne_commerciale_cibles
                        SET statut = %s, motif = %s, essais = essais + 1,
                            envoye_le = CASE WHEN %s = 'envoye' THEN now() ELSE envoye_le END
                      WHERE campagne_id = %s AND email = %s""",
                  (statut, (motif or "")[:300] or None, statut, cid, email))


def tick_utilisateur(utilisateur: str) -> dict:
    """Au plus UN email pour ce commercial. Rend ce qui s'est passé, pour le journal."""
    import boite_commercial as bc
    import fenetre_envoi as fe
    import maildoso_backend as md
    import site_credentials_backend as scb

    ok, motif = fe.ouverte("campagne")
    if not ok:
        return {"utilisateur": utilisateur, "action": "attente", "motif": motif}
    et = bc.etat(utilisateur, controler=True)
    if not et.get("envoi_possible"):
        return {"utilisateur": utilisateur, "action": "bloque", "motif": "; ".join(et["raisons"])}
    boite = bc._ligne(utilisateur)
    plafond = int(et["chauffe"]["plafond_aujourdhui"])
    deja = envoyes_aujourdhui(boite["email"])
    if deja >= plafond:
        return {"utilisateur": utilisateur, "action": "plafond", "motif": f"{deja}/{plafond}"}
    ok, motif = _assez_espace(boite["email"], plafond - deja)
    if not ok:
        return {"utilisateur": utilisateur, "action": "attente", "motif": motif}

    # La cible la plus ancienne des campagnes actives de ce commercial.
    r = _pg()._q("""
        SELECT c.id, c.site, c.sujet, c.corps, t.email
          FROM campagnes_commerciales c
          JOIN campagne_commerciale_cibles t ON t.campagne_id = c.id
         WHERE c.utilisateur = %s AND c.statut = 'active' AND t.statut = 'en_attente'
         ORDER BY c.lancee_le, t.email LIMIT 1""", (utilisateur,))
    if not r:
        return {"utilisateur": utilisateur, "action": "rien"}
    cid, site, sujet, corps, email = r[0]

    contact = _contact_autorise(utilisateur, site, email)
    if not contact:
        _marquer(cid, email, "ecarte", "plus attribué, ou contact devenu invalide")
        return {"utilisateur": utilisateur, "action": "ecarte", "email": email}

    mb = {"email": boite["email"], "username": boite["email"],
          "sender_name": boite.get("nom_affiche") or utilisateur,
          "smtp_host": bc.SMTP_HOTE, "smtp_port": bc.SMTP_PORT,
          "password": scb.decrypt_value(boite["mdp_chiffre"]),
          "canal": "gmail", "utilisateur": utilisateur}
    jour = fe.maintenant().strftime("%Y-%m-%d")
    lot = f"{site}-com-{cid}-{jour}"          # six segments : fenêtre + 120 jours appliqués
    texte = _avec_desinscription(corps)
    res = md.send_email(email, sujet, text=texte, html=_texte_vers_html(texte), site=site,
                        campaign_id=lot, to_name=None, mailbox=mb, contact=contact)
    if res.get("ok"):
        _marquer(cid, email, "envoye")
        _terminer_si_vide(cid)
        return {"utilisateur": utilisateur, "action": "envoye", "email": email}
    if res.get("refuse"):
        _marquer(cid, email, "ecarte", res.get("error"))
        _terminer_si_vide(cid)
        return {"utilisateur": utilisateur, "action": "ecarte", "email": email,
                "motif": res.get("error")}
    if res.get("reporte"):
        return {"utilisateur": utilisateur, "action": "reporte", "motif": res.get("error")}
    # Erreur SMTP : on réessaie au passage suivant, trois fois au plus.
    essais = _pg()._q("SELECT essais FROM campagne_commerciale_cibles "
                      "WHERE campagne_id = %s AND email = %s", (cid, email))
    if essais and essais[0][0] >= 2:
        _marquer(cid, email, "erreur", res.get("error"))
    else:
        _pg()._ecrire("UPDATE campagne_commerciale_cibles SET essais = essais + 1, motif = %s "
                      "WHERE campagne_id = %s AND email = %s", ((res.get("error") or "")[:300], cid, email))
    return {"utilisateur": utilisateur, "action": "erreur", "email": email,
            "motif": res.get("error")}


def _terminer_si_vide(cid: str) -> None:
    _pg()._ecrire("""UPDATE campagnes_commerciales SET statut = 'terminee', maj_le = now()
                      WHERE id = %s AND statut = 'active' AND NOT EXISTS (
                        SELECT 1 FROM campagne_commerciale_cibles
                         WHERE campagne_id = %s AND statut = 'en_attente')""", (cid, cid))


# ── Les rebonds ───────────────────────────────────────────────────────────────
# Gmail ne prévient personne d'un rebond : il dépose un avis « Mail Delivery Subsystem »
# dans la boîte de l'expéditeur. On les relit par IMAP (le même mot de passe d'application).
def _adresses_en_echec(msg) -> set[str]:
    import re as _re
    out = set()
    for h in msg.get_all("X-Failed-Recipients") or []:
        out |= {a.strip().lower() for a in h.split(",") if "@" in a}
    for part in msg.walk():
        ct = part.get_content_type()
        if ct == "message/delivery-status":
            # Le corps est une suite de blocs d'en-têtes, que `email` range en sous-messages.
            for bloc in part.get_payload() if isinstance(part.get_payload(), list) else []:
                for champ in ("Final-Recipient", "Original-Recipient"):
                    v = bloc.get(champ) or ""
                    if "@" in v:
                        out.add(v.split(";")[-1].strip(" <>").lower())
            continue
        if ct == "text/plain":
            try:
                corps = part.get_payload(decode=True)
                corps = corps.decode("utf-8", "replace") if corps else str(part.get_payload())
            except Exception:  # noqa: BLE001
                continue
            out |= {m.lower() for m in _re.findall(
                r"(?:Final|Original)-Recipient:\s*rfc822;\s*<?([^\s>]+@[^\s>]+)", corps, _re.I)}
    return out


def relever_rebonds(utilisateur: str, jours: int = 4) -> dict:
    import email as _email
    import imaplib
    from datetime import date
    import boite_commercial as bc
    import site_credentials_backend as scb
    import pg_sync
    boite = bc._ligne(utilisateur)
    if not boite or not boite.get("mdp_chiffre"):
        return {"utilisateur": utilisateur, "rebonds": 0, "motif": "pas de boîte"}
    envoyes = {e: (cid, d, site) for e, cid, d, site in _pg()._q("""
        SELECT t.email, t.campagne_id, t.envoye_le, c.site FROM campagne_commerciale_cibles t
          JOIN campagnes_commerciales c ON c.id = t.campagne_id
         WHERE c.utilisateur = %s AND t.statut = 'envoye'
           AND t.envoye_le > now() - interval '30 days'""", (utilisateur,))}
    if not envoyes:
        return {"utilisateur": utilisateur, "rebonds": 0}
    depuis = date.fromordinal(date.today().toordinal() - jours).strftime("%d-%b-%Y")
    trouves = set()
    m = imaplib.IMAP4_SSL(bc.IMAP_HOTE, timeout=bc.TIMEOUT_S)
    try:
        m.login(boite["email"], scb.decrypt_value(boite["mdp_chiffre"]))
        m.select("INBOX", readonly=True)
        _, ids = m.search(None, f'(SINCE {depuis} FROM "mailer-daemon")')
        for i in (ids[0].split() if ids and ids[0] else []):
            _, data = m.fetch(i, "(BODY.PEEK[])")
            if data and data[0]:
                trouves |= _adresses_en_echec(_email.message_from_bytes(data[0][1]))
    finally:
        try:
            m.logout()
        except Exception:  # noqa: BLE001
            pass
    nouveaux = 0
    for adr in trouves & set(envoyes):
        cid, envoye_le, site = envoyes[adr]
        deja = _pg()._q("SELECT 1 FROM email_events WHERE lower(email::text) = %s AND channel = 'gmail' "
                        "AND event_type = 'bounce' AND occurred_at >= %s LIMIT 1", (adr, envoye_le))
        if deja:
            continue
        pg_sync.record_event(adr, "bounce", site, "gmail", mailbox=boite["email"],
                             meta={"source": "gmail_commercial", "campagne": cid, "type": "hard"})
        _pg()._ecrire("UPDATE campagne_commerciale_cibles SET motif = 'rebond : adresse refusée' "
                      "WHERE campagne_id = %s AND email = %s", (cid, adr))
        try:
            import contacts_pool_backend as cpb
            cpb.set_global_blacklist(adr, reason=f"HARD BOUNCE via Gmail de {utilisateur}")
        except Exception as e:  # noqa: BLE001
            print(f"[campagne_commerciale] liste noire impossible pour {adr} : {e}", flush=True)
        nouveaux += 1
    return {"utilisateur": utilisateur, "rebonds": nouveaux}


def relever_tous_rebonds() -> list[dict]:
    out = []
    for (u,) in _pg()._q("SELECT DISTINCT c.utilisateur FROM campagnes_commerciales c "
                         "JOIN campagne_commerciale_cibles t ON t.campagne_id = c.id "
                         "WHERE t.statut = 'envoye' AND t.envoye_le > now() - interval '30 days'"):
        try:
            out.append(relever_rebonds(u))
        except Exception as e:  # noqa: BLE001
            out.append({"utilisateur": u, "erreur": f"{type(e).__name__}: {e}"})
    return out


# ── Les statistiques ──────────────────────────────────────────────────────────
# Une ouverture n'est pas une personne : un scanner Gmail ou un antivirus « ouvre » et
# « clique » dans la minute. Chaque événement porte le verdict de `robots_suivi`
# (humain / apple / robot / incertain) ; les taux affichés ne comptent que les personnes.
_RANG = {"humain": 3, "incertain": 2, "apple": 1, "robot": 0}


def _engagement(utilisateur: str, cid: str | None = None) -> dict[tuple[str, str], dict]:
    """Par (campagne, email) envoyé : la meilleure ouverture, le meilleur clic, le rebond."""
    filtre, params = "c.utilisateur = %s", [utilisateur]
    if cid:
        filtre += " AND c.id = %s"
        params.append(cid)
    lignes = _pg()._q(f"""
        SELECT t.campagne_id, t.email, ev.event_type, ev.meta, ev.occurred_at
          FROM campagne_commerciale_cibles t
          JOIN campagnes_commerciales c ON c.id = t.campagne_id
          JOIN email_events ev ON lower(ev.email::text) = t.email AND ev.channel = 'gmail'
               AND ev.event_type IN ('open', 'click', 'bounce') AND ev.occurred_at >= t.envoye_le
         WHERE {filtre} AND t.statut = 'envoye'
         ORDER BY ev.occurred_at""", tuple(params))
    out: dict = {}
    for camp, email, typ, meta, quand in lignes:
        e = out.setdefault((camp, email), {"ouverture": None, "clic": None, "rebond": False,
                                           "ouvert_le": None, "clique_le": None, "raison": None})
        meta = meta or {}
        verdict = meta.get("verdict") or "incertain"
        if typ == "bounce":
            e["rebond"] = True
            continue
        cle, quand_cle = ("clic", "clique_le") if typ == "click" else ("ouverture", "ouvert_le")
        if e[cle] is None or _RANG[verdict] > _RANG.get(e[cle], 0):
            e[cle], e[quand_cle] = verdict, quand.isoformat()
            if typ == "click" or e["clic"] is None:
                e["raison"] = meta.get("raison")
    # Un clic humain prouve une ouverture humaine, même si le pixel n'a pas été chargé.
    for e in out.values():
        if e["clic"] == "humain" and e["ouverture"] != "humain":
            e["ouverture"] = "humain"
    return out


def _taux(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def statistiques(utilisateur: str, site: str) -> list[dict]:
    eng = _engagement(utilisateur)
    out = []
    for c in lister(utilisateur, site):
        envoyes = c["envoyes"]
        lignes = [v for (camp, _), v in eng.items() if camp == c["id"]]
        o_h = sum(1 for v in lignes if v["ouverture"] == "humain")
        o_a = sum(1 for v in lignes if v["ouverture"] == "apple")
        o_r = sum(1 for v in lignes if v["ouverture"] == "robot" and v["clic"] != "humain")
        c_h = sum(1 for v in lignes if v["clic"] == "humain")
        c_r = sum(1 for v in lignes if v["clic"] in ("robot", "incertain"))
        reb = sum(1 for v in lignes if v["rebond"])
        out.append({"id": c["id"], "nom": c["nom"], "statut": c["statut"], "lancee_le": c["lancee_le"],
                    "envoyes": envoyes, "total": c["total"],
                    "ouvertures": o_h, "ouvertures_apple": o_a, "ouvertures_robot": o_r,
                    "clics": c_h, "clics_robot": c_r, "rebonds": reb,
                    "taux_ouverture": _taux(o_h, envoyes - reb), "taux_clic": _taux(c_h, envoyes - reb),
                    "taux_rebond": _taux(reb, envoyes)})
    return out


def engages(utilisateur: str, cid: str) -> list[dict] | None:
    """Les contacts d'une campagne qui ont ouvert, cliqué ou rebondi — personnes d'abord."""
    if not _campagne(cid, utilisateur):
        return None
    eng = _engagement(utilisateur, cid)
    if not eng:
        return []
    infos = {r[0]: r[1:] for r in _pg()._q(
        "SELECT lower(email::text), prenom, nom, societe, tel FROM contacts "
        "WHERE lower(email::text) = ANY(%s)", ([e for (_, e) in eng],))}
    out = []
    for (_, email), v in eng.items():
        prenom, nom, societe, tel = infos.get(email, ("", "", "", ""))
        out.append({"email": email, "prenom": prenom or "", "nom": nom or "",
                    "societe": societe or "", "tel": tel or "", **v})
    out.sort(key=lambda x: (-(_RANG.get(x["clic"] or "", -1) + 1) * 10
                            - (_RANG.get(x["ouverture"] or "", -1) + 1), x["email"]))
    return out


def tick() -> list[dict]:
    users = [r[0] for r in _pg()._q(
        "SELECT DISTINCT utilisateur FROM campagnes_commerciales WHERE statut = 'active'")]
    out = []
    for u in users:
        try:
            out.append(tick_utilisateur(u))
        except Exception as e:  # noqa: BLE001 — un commercial en panne ne bloque pas les autres
            out.append({"utilisateur": u, "action": "exception", "motif": f"{type(e).__name__}: {e}"})
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "rebonds":
        for ligne in relever_tous_rebonds():
            print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ligne, flush=True)
    if len(sys.argv) > 1 and sys.argv[1] == "tick":
        for ligne in tick():
            if ligne.get("action") not in ("rien",):
                print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ligne, flush=True)
