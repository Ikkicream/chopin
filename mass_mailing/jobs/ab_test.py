#!/usr/bin/env python3
"""mass_mailing/jobs/ab_test.py — A/B test d'une campagne (Camille, 15/10/2026).

« proposer au client de faire 2 versions du message, de laisser une période de test que le client
détermine en nombre de jours, puis de passer après ce nombre de jours automatiquement sur la version
avec le meilleur taux d'ouverture ou de clic — faire un scoring pour ça ».

Déroulé :
    brouillon    deux versions (A, B), tailles des échantillons, durée en jours, critère
    test         `lancer` : tirage au hasard de taille_a + taille_b destinataires encore en file
                 (`recipients.variante` = 'A' / 'B'), la campagne part avec le message A ;
                 le routage n'envoie QUE l'échantillon, les autres attendent en file
    observation  tout l'échantillon est parti : on attend `duree_jours` À PARTIR DU DERNIER
                 envoi du test (chaque email a donc au moins cette durée pour être ouvert)
    decide       `decider` : scoring, la version gagnante devient LE message de la campagne,
                 le routage reprend le reste de la file avec elle (même warm-up, même fenêtre)

Le circuit d'envoi n'est pas dupliqué : le routage et `envoi.envoyer_lot` restent les seuls à
envoyer ; ils demandent ici quel message envoyer à qui (`contenus`) et qui retenir (`retenir`).

Scoring (`scorer`) : taux du critère choisi (ouvertures ou clics / délivrés), moins une pénalité
pour les signaux négatifs (désinscription ×1, plainte ×5, rebond ×1, rapportés aux délivrés).
Égalité parfaite → l'autre critère départage, puis la version A (le message d'origine).
Seuil de confiance (Camille, 15/10/2026) : la version en tête n'est retenue que si la confiance
statistique (test z de deux proportions sur le critère) atteint SEUIL_CONFIANCE ; sinon il n'y a
« pas de gagnant net » et la campagne garde la version A (le message d'origine).
"""
from __future__ import annotations

import json
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import pg, stockage, sweego  # noqa: E402

VARIANTES = ("A", "B")
CRITERES = ("ouverture", "clic")
PHASES_RETENUE = ("test", "observation")       # pendant ces phases, seul l'échantillon part
POIDS = {"desinscrits": 1.0, "plaintes": 5.0, "rebonds": 1.0}

SCHEMA = """
CREATE TABLE IF NOT EXISTS ab_tests (
    campaign_id         UUID        PRIMARY KEY REFERENCES campaigns(id) ON DELETE CASCADE,
    statut              TEXT        NOT NULL DEFAULT 'brouillon'
                        CHECK (statut IN ('brouillon','test','observation','decide','annule')),
    taille_a            INT         NOT NULL DEFAULT 150 CHECK (taille_a > 0),
    taille_b            INT         NOT NULL DEFAULT 150 CHECK (taille_b > 0),
    duree_jours         NUMERIC     NOT NULL DEFAULT 3 CHECK (duree_jours > 0),
    critere             TEXT        NOT NULL DEFAULT 'ouverture' CHECK (critere IN ('ouverture','clic')),
    a_subject TEXT, a_preheader TEXT, a_html_key TEXT, a_html_hash TEXT, a_text TEXT,
    b_subject TEXT, b_preheader TEXT, b_html_key TEXT, b_html_hash TEXT, b_text TEXT,
    lance_le            TIMESTAMPTZ,
    envois_finis_le     TIMESTAMPTZ,
    decision_prevue_le  TIMESTAMPTZ,
    decide_le           TIMESTAMPTZ,
    gagnant             TEXT        CHECK (gagnant IN ('A','B')),
    scores              JSONB,
    motif               TEXT,
    par                 TEXT,
    cree_le             TIMESTAMPTZ NOT NULL DEFAULT now(),
    maj_le              TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE recipients ADD COLUMN IF NOT EXISTS variante TEXT;
CREATE INDEX IF NOT EXISTS recipients_variante_idx ON recipients (campaign_id, variante) WHERE variante IS NOT NULL
"""


class ErreurAB(Exception):
    pass


def appliquer_schema() -> None:
    for b in SCHEMA.split(";"):
        if b.strip():
            pg.ecrire(b)


def _audit(campaign_id: str, acteur: str, event: str, resume: str, charge: dict | None = None) -> None:
    pg.ecrire("""INSERT INTO campaign_events (campaign_id, actor_type, actor_id, event_type, summary, payload)
                 VALUES (%(c)s, %(t)s, %(a)s, %(e)s, %(r)s, %(p)s::jsonb)""",
              {"c": campaign_id, "t": "worker" if acteur == "ab-test" else "user", "a": acteur, "e": event,
               "r": resume, "p": json.dumps(charge or {}, ensure_ascii=False, default=str)})


def lire(campaign_id: str) -> dict | None:
    try:
        return pg.ligne("SELECT * FROM ab_tests WHERE campaign_id = %(c)s", {"c": campaign_id})
    except Exception:  # noqa: BLE001 — table absente : aucun test
        return None


def phase(campaign_id: str) -> str | None:
    t = lire(campaign_id)
    return t["statut"] if t else None


def retenir(campaign_id: str) -> bool:
    """Vrai tant que seul l'échantillon du test doit partir."""
    return phase(campaign_id) in PHASES_RETENUE


# ── Configuration ────────────────────────────────────────────────────────────

def creer_ou_lire(campaign_id: str, acteur: str) -> dict:
    """Crée le test en brouillon ; la version A part du message actuel de la campagne."""
    appliquer_schema()
    t = lire(campaign_id)
    if t:
        return t
    c = pg.ligne("SELECT subject, preheader, html_storage_key, html_hash, text_content FROM campaigns WHERE id = %(c)s",
                 {"c": campaign_id})
    pg.ecrire("""INSERT INTO ab_tests (campaign_id, a_subject, a_preheader, a_html_key, a_html_hash, a_text, par)
                 VALUES (%(c)s, %(s)s, %(p)s, %(k)s, %(h)s, %(t)s, %(a)s) ON CONFLICT DO NOTHING""",
              {"c": campaign_id, "s": c["subject"], "p": c["preheader"], "k": c["html_storage_key"],
               "h": c["html_hash"], "t": c["text_content"], "a": acteur})
    return lire(campaign_id)


def regler(campaign_id: str, acteur: str, *, taille_a=None, taille_b=None, duree_jours=None, critere=None) -> dict:
    t = creer_ou_lire(campaign_id, acteur)
    if t["statut"] != "brouillon":
        raise ErreurAB("le test est lancé : ses réglages ne se modifient plus")
    ch = {}
    for cle, v in (("taille_a", taille_a), ("taille_b", taille_b)):
        if v is not None:
            if int(v) < 1:
                raise ErreurAB("chaque version doit partir à au moins 1 destinataire")
            ch[cle] = int(v)
    if duree_jours is not None:
        if not 0 < float(duree_jours) <= 60:
            raise ErreurAB("la période de test va de quelques heures à 60 jours")
        ch["duree_jours"] = float(duree_jours)
    if critere is not None:
        if critere not in CRITERES:
            raise ErreurAB("critère : « ouverture » ou « clic »")
        ch["critere"] = critere
    if ch:
        pg.ecrire("UPDATE ab_tests SET " + ", ".join(f"{k} = %({k})s" for k in ch) + ", maj_le = now() WHERE campaign_id = %(c)s",
                  {**ch, "c": campaign_id})
        _audit(campaign_id, acteur, "ab.reglages", "A/B test : réglages " + ", ".join(f"{k} = {v}" for k, v in ch.items()), ch)
    return lire(campaign_id)


def enregistrer_version(campaign_id: str, acteur: str, variante: str, *, subject: str, preheader: str, html: str) -> dict:
    """Enregistre une version (HTML hébergé et réparé comme le message d'une campagne)."""
    if variante not in VARIANTES:
        raise ErreurAB("version A ou B")
    t = creer_ou_lire(campaign_id, acteur)
    if t["statut"] != "brouillon":
        raise ErreurAB("le test est lancé : les versions ne se modifient plus")
    if not (subject or "").strip() or not (html or "").strip():
        raise ErreurAB("objet et message HTML requis")
    from infra import images
    html, _ = images.heberger(html)
    html, _ = images.reparer_corps(html)
    d = stockage.deposer(html.encode("utf-8"), "html", taille_max=5 * 1024 * 1024)
    v = variante.lower()
    pg.ecrire(f"""UPDATE ab_tests SET {v}_subject = %(s)s, {v}_preheader = %(p)s, {v}_html_key = %(k)s,
                         {v}_html_hash = %(h)s, {v}_text = %(t)s, maj_le = now() WHERE campaign_id = %(c)s""",
              {"s": subject.strip(), "p": (preheader or "").strip(), "k": d["storage_key"], "h": d["sha256"],
               "t": sweego.html_vers_texte(html), "c": campaign_id})
    _audit(campaign_id, acteur, "ab.version", f"A/B test : version {variante} enregistrée (« {subject.strip()} »)",
           {"html_hash": d["sha256"]})
    return lire(campaign_id)


def version(t: dict, variante: str) -> dict:
    v = variante.lower()
    return {"subject": t.get(f"{v}_subject"), "preheader": t.get(f"{v}_preheader"),
            "html_key": t.get(f"{v}_html_key"), "html_hash": t.get(f"{v}_html_hash"), "text": t.get(f"{v}_text")}


def contenus(campaign_id: str) -> dict:
    """{variante: {subject, preheader, html, text}} pour l'envoi — vide s'il n'y a pas de test."""
    t = lire(campaign_id)
    if not t or t["statut"] in ("brouillon", "annule"):
        return {}
    out = {}
    for x in VARIANTES:
        v = version(t, x)
        if v["html_key"]:
            out[x] = {"subject": v["subject"], "preheader": v["preheader"] or "",
                      "html": stockage.lire(v["html_key"]).decode("utf-8", "replace"), "text": v["text"] or ""}
    return out


# ── Contrôles et lancement ───────────────────────────────────────────────────

def disponibles(campaign_id: str) -> int:
    """Destinataires encore en file, pas encore partis : le vivier du tirage."""
    return int(pg.valeur("""SELECT count(*) FROM recipients WHERE campaign_id = %(c)s AND send_status = 'queued'
                              AND submitted_at IS NULL AND eligibility_status = 'eligible'""", {"c": campaign_id}) or 0)


def controler(campaign_id: str) -> list[dict]:
    """Ce qui empêche le lancement. Chaque version passe le contrôle complet du message."""
    from infra import controle_html, desinscription
    t = lire(campaign_id)
    ctrl = []

    def ajoute(cle, ok, libelle, bloquant=True):
        ctrl.append({"cle": cle, "ok": bool(ok), "libelle": libelle, "bloquant": bloquant})

    if not t:
        ajoute("test", False, "Aucun A/B test configuré")
        return ctrl
    c = pg.ligne("SELECT status FROM campaigns WHERE id = %(c)s", {"c": campaign_id})
    ajoute("campagne", c["status"] in ("ready_to_schedule", "paused", "scheduled"),
           f"Campagne en pause ou prête à envoyer (actuellement : {c['status']})")
    for x in VARIANTES:
        v = version(t, x)
        if not (v["subject"] and v["html_key"]):
            ajoute(f"version_{x}", False, f"Version {x} : objet et message à renseigner")
            continue
        html = stockage.lire(v["html_key"]).decode("utf-8", "replace")
        an = controle_html.analyser(html, objet=v["subject"], preheader=v["preheader"] or "", expediteur={},
                                    url_miroir=desinscription.url_miroir(campaign_id))
        bloq = [p["message"] for p in an["problemes"] if p["niveau"] == "bloquant"]
        ajoute(f"version_{x}", not bloq, f"Version {x} : note {an['score']}/100"
               + (f" — {'; '.join(bloq)}" if bloq else ", aucun problème bloquant"))
        ajoute(f"jetons_{x}", "{{" not in html, f"Version {x} : aucune variable {{{{…}}}} oubliée")
    dispo = disponibles(campaign_id)
    besoin = int(t["taille_a"]) + int(t["taille_b"])
    ajoute("echantillon", dispo >= besoin, f"Échantillon : {besoin} destinataires à tirer parmi {dispo} encore en file")
    if t["critere"] == "clic":
        sans_lien = [x for x in VARIANTES if version(t, x)["html_key"] and not [
            l for l in sweego.liens_du_html(stockage.lire(version(t, x)["html_key"]).decode("utf-8", "replace"))
            if l.lower().startswith("http")]]
        ajoute("liens", not sans_lien, "Critère « clic » : chaque version contient au moins un lien"
               + (f" (aucun lien dans la version {', '.join(sans_lien)})" if sans_lien else ""), bloquant=False)
    return ctrl


def lancer(campaign_id: str, acteur: str) -> dict:
    """Tire l'échantillon, met le message A sur la campagne, puis donne le feu vert d'envoi
    par le circuit normal (contrôles avant envoi + routage)."""
    from jobs import envoi
    t = lire(campaign_id)
    if not t or t["statut"] != "brouillon":
        raise ErreurAB("aucun A/B test en brouillon pour cette campagne")
    bloq = [x["libelle"] for x in controler(campaign_id) if x["bloquant"] and not x["ok"]]
    if bloq:
        raise ErreurAB("lancement impossible : " + " ; ".join(bloq))
    ids = [x["id"] for x in pg.lignes("""SELECT id FROM recipients WHERE campaign_id = %(c)s AND send_status = 'queued'
                                           AND submitted_at IS NULL AND eligibility_status = 'eligible'""", {"c": campaign_id})]
    random.SystemRandom().shuffle(ids)
    a, b = ids[:int(t["taille_a"])], ids[int(t["taille_a"]):int(t["taille_a"]) + int(t["taille_b"])]
    va = version(t, "A")
    with pg.connexion() as cur:
        cur.execute("UPDATE recipients SET variante = NULL WHERE campaign_id = %(c)s AND submitted_at IS NULL", {"c": campaign_id})
        cur.execute("UPDATE recipients SET variante = 'A', updated_at = now() WHERE id = ANY(%(i)s)", {"i": a})
        cur.execute("UPDATE recipients SET variante = 'B', updated_at = now() WHERE id = ANY(%(i)s)", {"i": b})
        # Le message de la campagne = version A pendant le test (fiche, BAT, contrôles avant envoi).
        cur.execute("""UPDATE campaigns SET subject = %(s)s, preheader = %(p)s, html_storage_key = %(k)s, html_hash = %(h)s,
                              text_content = %(t)s, message_version = message_version + 1, preflight_snapshot = NULL,
                              updated_at = now() WHERE id = %(c)s""",
                    {"s": va["subject"], "p": va["preheader"], "k": va["html_key"], "h": va["html_hash"], "t": va["text"],
                     "c": campaign_id})
        cur.execute("UPDATE ab_tests SET statut = 'test', lance_le = now(), maj_le = now() WHERE campaign_id = %(c)s",
                    {"c": campaign_id})
    # Les lots déjà formés retournent en réserve : seule la réserve est filtrée par le test.
    pg.ecrire("""UPDATE sending_batches SET status = 'scheduled' WHERE campaign_id = %(c)s AND status = 'pending'""",
              {"c": campaign_id})
    _audit(campaign_id, acteur, "ab.lance",
           f"A/B test lancé : {len(a)} destinataires version A, {len(b)} version B, décision {float(t['duree_jours']):g} jour(s) "
           f"après le dernier envoi du test, critère {t['critere']}")
    try:
        snap = envoi.preflight(campaign_id, acteur)
        if not snap.get("ok"):
            raise ErreurAB("contrôles avant envoi au rouge : "
                           + " ; ".join(x["libelle"] for x in snap["controles"] if x["bloquant"] and not x["ok"]))
        envoi.autoriser(campaign_id, acteur)
    except Exception:
        # Rien n'est parti : on revient au brouillon pour pouvoir corriger et relancer.
        pg.ecrire("UPDATE ab_tests SET statut = 'brouillon', lance_le = NULL WHERE campaign_id = %(c)s", {"c": campaign_id})
        pg.ecrire("UPDATE recipients SET variante = NULL WHERE campaign_id = %(c)s AND submitted_at IS NULL", {"c": campaign_id})
        raise
    return {"ok": True, "A": len(a), "B": len(b)}


# ── Résultats et décision ────────────────────────────────────────────────────

def mesures(campaign_id: str) -> dict:
    out = {}
    for x in pg.lignes("""SELECT variante,
               count(*) AS echantillon,
               count(*) FILTER (WHERE submitted_at IS NOT NULL) AS envoyes,
               count(*) FILTER (WHERE send_status = 'queued') AS en_file,
               count(*) FILTER (WHERE delivered_at IS NOT NULL) AS livres,
               count(*) FILTER (WHERE opened_at IS NOT NULL) AS ouverts,
               count(*) FILTER (WHERE clicked_at IS NOT NULL) AS cliques,
               count(*) FILTER (WHERE unsubscribed_at IS NOT NULL) AS desinscrits,
               count(*) FILTER (WHERE complained_at IS NOT NULL) AS plaintes,
               count(*) FILTER (WHERE bounced_at IS NOT NULL) AS rebonds,
               max(submitted_at) AS dernier_envoi
          FROM recipients WHERE campaign_id = %(c)s AND variante IS NOT NULL GROUP BY variante""", {"c": campaign_id}):
        out[x["variante"]] = dict(x)
    for v in VARIANTES:
        out.setdefault(v, {"echantillon": 0, "envoyes": 0, "en_file": 0, "livres": 0, "ouverts": 0, "cliques": 0,
                           "desinscrits": 0, "plaintes": 0, "rebonds": 0, "dernier_envoi": None})
    # Ouvertures : seules les HUMAINES comptent (15/10/2026). Les scanners de sécurité
    # (Microsoft 365, Google, passerelles) ouvrent presque tout en quelques secondes et
    # noieraient l'écart entre les deux versions. Classement : jobs/engagement.py.
    from jobs import engagement
    verdicts = engagement.ouvertures_humaines(campaign_id)
    var = {r["id"]: r["variante"] for r in pg.lignes(
        "SELECT id, variante FROM recipients WHERE campaign_id = %(c)s AND variante IS NOT NULL AND opened_at IS NOT NULL",
        {"c": campaign_id})}
    for v in VARIANTES:
        brut = out[v]["ouverts"] or 0
        les_miens = [verdicts.get(r, "?") for r, x in var.items() if x == v]
        out[v]["ouverts_bruts"] = brut
        out[v]["ouverts"] = sum(1 for x in les_miens if x == "humain")
        out[v]["ouverts_robots"] = sum(1 for x in les_miens if x == "robot")
        out[v]["ouverts_incertains"] = sum(1 for x in les_miens if x == "?")
    return out


def _z(p1: float, n1: int, p2: float, n2: int) -> float | None:
    if not n1 or not n2:
        return None
    p = (p1 * n1 + p2 * n2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return None if se == 0 else (p1 - p2) / se


SEUIL_CONFIANCE = 90.0


def scorer(m: dict, critere: str) -> dict:
    """Fonction pure : mesures par variante → scores, gagnant, confiance."""
    res = {}
    for v in VARIANTES:
        x = m[v]
        base = max(1, int(x["livres"] or x["envoyes"] or 0))
        t_ouv, t_clic = (x["ouverts"] or 0) / base, (x["cliques"] or 0) / base
        penalite = sum(POIDS[k] * (x[k] or 0) for k in POIDS) / base
        principal = t_ouv if critere == "ouverture" else t_clic
        res[v] = {"base": base, "taux_ouverture": round(100 * t_ouv, 2), "taux_clic": round(100 * t_clic, 2),
                  "penalite": round(100 * penalite, 2), "score": round(100 * (principal - penalite), 2)}
    a, b = res["A"], res["B"]
    if a["score"] != b["score"]:
        gagnant, depart = ("A" if a["score"] > b["score"] else "B"), "score"
    else:
        autre = "taux_clic" if critere == "ouverture" else "taux_ouverture"
        gagnant, depart = (("A" if a[autre] >= b[autre] else "B"), f"égalité : départagé par {autre.replace('_', ' ')}") \
            if a[autre] != b[autre] else ("A", "égalité parfaite : on garde la version A (message d'origine)")
    cle = "taux_ouverture" if critere == "ouverture" else "taux_clic"
    z = _z(a[cle] / 100, a["base"], b[cle] / 100, b["base"])
    confiance = None if z is None else round(100 * math.erf(abs(z) / math.sqrt(2)), 1)
    net = bool(confiance is not None and confiance >= SEUIL_CONFIANCE and a[cle] != b[cle])
    en_tete = gagnant
    if not net:
        depart = (f"pas de gagnant net : confiance {confiance if confiance is not None else 0} % < {SEUIL_CONFIANCE:g} %, "
                  "on garde la version A (message d'origine)")
        gagnant = "A"
    return {"critere": critere, "variantes": res, "gagnant": gagnant, "en_tete": en_tete, "net": net,
            "departage": depart, "confiance": confiance, "seuil": SEUIL_CONFIANCE, "significatif": net}


def decider(campaign_id: str, acteur: str = "ab-test") -> dict:
    """Bascule la campagne sur la version gagnante ; le routage reprend le reste de la file."""
    t = lire(campaign_id)
    if not t or t["statut"] not in PHASES_RETENUE:
        raise ErreurAB("aucun test en cours")
    s = scorer(mesures(campaign_id), t["critere"])
    g = version(t, s["gagnant"])
    with pg.connexion() as cur:
        cur.execute("""UPDATE campaigns SET subject = %(s)s, preheader = %(p)s, html_storage_key = %(k)s, html_hash = %(h)s,
                              text_content = %(t)s, message_version = message_version + 1, updated_at = now()
                        WHERE id = %(c)s""",
                    {"s": g["subject"], "p": g["preheader"], "k": g["html_key"], "h": g["html_hash"], "t": g["text"],
                     "c": campaign_id})
        cur.execute("""UPDATE ab_tests SET statut = 'decide', decide_le = now(), gagnant = %(g)s, scores = %(sc)s::jsonb,
                              maj_le = now() WHERE campaign_id = %(c)s""",
                    {"g": s["gagnant"], "sc": json.dumps(s), "c": campaign_id})
    va, vb = s["variantes"]["A"], s["variantes"]["B"]
    _audit(campaign_id, acteur, "ab.decision",
           f"A/B test : version {s['gagnant']} retenue" + ("" if s["net"] else " (pas de gagnant net)")
           + f" (score A {va['score']} / B {vb['score']}, critère {t['critere']}"
           + (f", confiance {s['confiance']} %" if s["confiance"] is not None else "") + ") — le reste de la campagne part avec elle", s)
    return s


def tour() -> list[dict]:
    """Appelé par le worker dans chaque espace : fin des envois du test → observation ;
    fin de la période → décision automatique."""
    try:
        tests = pg.lignes("SELECT * FROM ab_tests WHERE statut IN ('test','observation')")
    except Exception:  # noqa: BLE001 — table absente dans cet espace
        return []
    out = []
    for t in tests:
        cid = str(t["campaign_id"])
        try:
            if t["statut"] == "test":
                reste = pg.valeur("""SELECT count(*) FROM recipients WHERE campaign_id = %(c)s AND variante IS NOT NULL
                                       AND send_status = 'queued'""", {"c": cid}) or 0
                if reste == 0:
                    fin = pg.valeur("SELECT max(submitted_at) FROM recipients WHERE campaign_id = %(c)s AND variante IS NOT NULL",
                                    {"c": cid}) or datetime.now(timezone.utc)
                    prevue = fin + timedelta(days=float(t["duree_jours"]))
                    pg.ecrire("""UPDATE ab_tests SET statut = 'observation', envois_finis_le = %(f)s, decision_prevue_le = %(p)s,
                                        maj_le = now() WHERE campaign_id = %(c)s AND statut = 'test'""", {"f": fin, "p": prevue, "c": cid})
                    _audit(cid, "ab-test", "ab.observation",
                           f"A/B test : échantillon entièrement parti, décision automatique le {prevue:%d/%m/%Y à %H:%M} UTC")
                    out.append({"campaign_id": cid, "observation": prevue.isoformat()})
            elif t["decision_prevue_le"] and t["decision_prevue_le"] <= datetime.now(timezone.utc):
                s = decider(cid)
                out.append({"campaign_id": cid, "gagnant": s["gagnant"]})
        except Exception as e:  # noqa: BLE001
            out.append({"campaign_id": cid, "erreur": str(e)[:200]})
    return out


def etat(campaign_id: str) -> dict:
    t = lire(campaign_id)
    if not t:
        return {"existe": False, "disponibles": disponibles(campaign_id)}
    m = mesures(campaign_id)
    return {"existe": True, "test": {k: v for k, v in t.items() if not k.endswith(("_html_key", "_text"))},
            "versions": {x: {k: version(t, x)[k] for k in ("subject", "preheader", "html_hash")} for x in VARIANTES},
            "mesures": m, "projection": scorer(m, t["critere"]) if t["statut"] != "brouillon" else None,
            "disponibles": disponibles(campaign_id)}
