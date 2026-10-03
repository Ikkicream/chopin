#!/usr/bin/env python3
"""mass_mailing/jobs/routage.py — agent de routage intelligent (Camille, 27/09/2026).

Une campagne routée n'envoie pas tout d'un coup : ses lots d'origine passent EN RÉSERVE
(`sending_batches.status = 'scheduled'`) et, toutes les heures dans la fenêtre 8h-22h (heure de
Paris), l'agent prélève une VAGUE par messagerie :

    volume(messagerie) = min( débit/h appris × part , reste du jour appris , adresses restantes )
    part = 1,0 pour les messageries qui OUVRENT (priorité 1), PART_BASSE (0,3) pour les autres,
           1,0 pour tout le monde quand la priorité 1 est épuisée.

La priorité est recalculée à chaque vague : taux d'ouverture humain lissé
(ouvertures + 1) / (livrés + 20) sur toutes les campagnes du même domaine d'identité ; priorité 1
si ≥ SEUIL_PRIORITE. Capacités lues dans jobs/capacite (skill pilotage-delivrabilite) : une
messagerie en pause n'envoie rien, une messagerie freinée envoie à son débit réduit.
Avant chaque vague : réputation d'envoi HetrixTools (IP + domaine) ; listé → routage suspendu.

Chaque vague = un `sending_batch` ordinaire + un job d'envoi : même circuit que tout le reste
(1 destinataire = 1 mail, suppression relue, préférences, B2C, badge, désinscription).
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import pg  # noqa: E402
from jobs import capacite, envoi, file  # noqa: E402

PARIS = ZoneInfo("Europe/Paris")
PART_BASSE = 0.3
SEUIL_PRIORITE = 0.05
# Sous ce taux, une messagerie reste à PART_BASSE même quand la priorité 1 est épuisée (Camille, 27/09 :
# Gmail et Outlook n'ouvrent pas, on ne les inonde pas pour « finir » la campagne).
SEUIL_BAS = 0.03
# Retrait AUTOMATIQUE d'une messagerie de la campagne (Camille, 27/09 : « tu ne dois plus me demander ») :
# ≥ 5 % d'adresses mortes (rebond définitif « destinataire invalide ») sur au moins 10 envois.
# Une liste qui rebondit abîme la réputation : l'agent ne la réintègre jamais seul.
SEUIL_INVALIDES = 0.05
MIN_ENVOIS_INVALIDES = 10
INTERVALLE = timedelta(hours=1)

SCHEMA = """
CREATE TABLE IF NOT EXISTS routage_campagnes (
    campaign_id     UUID        PRIMARY KEY REFERENCES campaigns(id) ON DELETE CASCADE,
    actif           BOOLEAN     NOT NULL DEFAULT true,
    part_basse      NUMERIC     NOT NULL DEFAULT 0.3,
    prochaine_vague TIMESTAMPTZ NOT NULL DEFAULT now(),
    demarre_le      TIMESTAMPTZ NOT NULL DEFAULT now(),
    termine_le      TIMESTAMPTZ,
    suspendu_motif  TEXT,
    par             TEXT
);
ALTER TABLE routage_campagnes ADD COLUMN IF NOT EXISTS groupes_exclus JSONB NOT NULL DEFAULT '{}'::jsonb;
CREATE TABLE IF NOT EXISTS routage_vagues (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    campaign_id     UUID        NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    numero          INT         NOT NULL,
    at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    groupe          TEXT        NOT NULL,
    priorite        INT         NOT NULL,
    taux_ouverture  NUMERIC,
    volume          INT         NOT NULL,
    restant_avant   INT         NOT NULL,
    sending_batch_id UUID,
    raison          TEXT
)
"""


def appliquer_schema() -> None:
    for b in SCHEMA.split(";"):
        if b.strip():
            pg.ecrire(b)


def dans_fenetre(t: datetime | None = None) -> bool:
    t = (t or datetime.now(timezone.utc)).astimezone(PARIS)
    return capacite.FENETRE_ENVOI[0] <= t.hour < capacite.FENETRE_ENVOI[1]


# ── Démarrage ────────────────────────────────────────────────────────────────

def demarrer(campaign_id: str, acteur: str, part_basse: float = PART_BASSE) -> dict:
    """Met la campagne en routage : contrôles avant envoi au vert exigés, lots d'origine en réserve,
    campagne `sending` (sans empiler les lots : c'est l'agent qui envoie, vague par vague)."""
    appliquer_schema()
    snap = envoi.preflight(campaign_id, acteur)
    if not snap["ok"]:
        raise envoi.ErreurDefinitive("contrôles avant envoi au rouge : "
                                     + " ; ".join(x["libelle"] for x in snap["controles"] if x["bloquant"] and not x["ok"]))
    with pg.connexion() as cur:
        cur.execute("SELECT status FROM campaigns WHERE id = %(c)s FOR UPDATE", {"c": campaign_id})
        st = cur.fetchone()["status"]
        if st not in ("ready_to_schedule", "paused", "scheduled", "sending"):
            raise envoi.ErreurDefinitive(f"routage impossible depuis « {st} »")
        cur.execute("""UPDATE sending_batches SET status = 'scheduled'
                        WHERE campaign_id = %(c)s AND status = 'pending'""", {"c": campaign_id})
        cur.execute("""UPDATE campaigns SET status = 'sending', started_at = COALESCE(started_at, now()),
                              paused_at = NULL, updated_at = now() WHERE id = %(c)s""", {"c": campaign_id})
        cur.execute("""INSERT INTO routage_campagnes (campaign_id, actif, part_basse, prochaine_vague, par)
                       VALUES (%(c)s, true, %(p)s, now(), %(a)s)
                       ON CONFLICT (campaign_id) DO UPDATE SET actif = true, part_basse = EXCLUDED.part_basse,
                              prochaine_vague = now(), suspendu_motif = NULL, termine_le = NULL""",
                    {"c": campaign_id, "p": part_basse, "a": acteur})
        envoi._audit(cur, campaign_id, "user", acteur, "routage.start",
                     f"Routage intelligent démarré (vagues horaires 8h-22h, part des messageries peu ouvreuses {int(part_basse * 100)} %)")
    return {"ok": True}


# ── Priorités et plan d'une vague (fonctions pures testées) ─────────────────────

def taux_lisse(ouverts: int, livres: int) -> float:
    return (ouverts + 1) / (livres + 20)


def planifier(restants: dict[str, int], taux: dict[str, float], capacites: dict[str, dict], part_basse: float,
              exclus: dict[str, str] | None = None) -> list[dict]:
    """Plan d'une vague. restants : adresses en réserve par messagerie ; taux : ouverture lissée ;
    capacites : {groupe: {debit_heure, restant_jour, etat}} ; exclus : {groupe: motif} retirés du routage.
    Renvoie [{groupe, priorite, volume, raison}]."""
    exclus = exclus or {}
    prio1 = {g for g, n in restants.items() if n > 0 and taux.get(g, 0) >= SEUIL_PRIORITE}
    plan = []
    for g, n in sorted(restants.items(), key=lambda kv: -taux.get(kv[0], 0)):
        if n <= 0:
            continue
        cap = capacites.get(g) or {}
        if g in exclus:
            plan.append({"groupe": g, "priorite": 0, "volume": 0, "raison": f"retirée du routage : {exclus[g]}"}); continue
        if cap.get("etat") == "paused":
            plan.append({"groupe": g, "priorite": 0, "volume": 0, "raison": "messagerie en pause (capacité)"}); continue
        haute = g in prio1
        part = 1.0 if (haute or (not prio1 and taux.get(g, 0) >= SEUIL_BAS)) else part_basse
        debit = float(cap.get("debit_heure") or capacite.PROFILS.get(g, capacite.PROFILS["autres"])[0])
        reste_jour = int(cap.get("restant_jour") if cap.get("restant_jour") is not None
                         else capacite.PROFILS.get(g, capacite.PROFILS["autres"])[1])
        volume = max(0, min(int(debit * part), int(reste_jour * (1.0 if part == 1.0 else part_basse)) if reste_jour else 0, n))
        if part < 1.0 and volume == 0 and n > 0 and reste_jour > 0:
            volume = 1        # toujours un peu de présence, même en priorité basse
        raison = (f"priorité {'1' if haute else '2'} : ouverture {taux.get(g, 0):.1%}, "
                  f"part {int(part * 100)} % du débit {debit:.0f}/h, reste du jour {reste_jour}")
        plan.append({"groupe": g, "priorite": 1 if haute else 2, "volume": volume, "raison": raison})
    return plan


def exclusions_auto(stats: dict[str, tuple[int, int]], deja: dict[str, str]) -> dict[str, str]:
    """stats : {groupe: (envoyés, adresses mortes)}. Renvoie les NOUVELLES exclusions {groupe: motif}."""
    out = {}
    for g, (n, morts) in stats.items():
        if g not in deja and n >= MIN_ENVOIS_INVALIDES and morts / n >= SEUIL_INVALIDES:
            out[g] = f"retrait automatique : {morts} adresse(s) morte(s) sur {n} envois ({morts / n:.0%} ≥ {SEUIL_INVALIDES:.0%})"
    return out


def _invalides_campagne(campaign_id: str) -> dict[str, tuple[int, int]]:
    agg: dict[str, list[int]] = {}
    for x in pg.lignes("""SELECT split_part(r.email_normalized, '@', 2) AS d, count(*) AS n,
                                 count(*) FILTER (WHERE r.send_status = 'bounced' AND EXISTS (
                                     SELECT 1 FROM smtp_reponses s WHERE s.email_hash = r.email_hash
                                        AND s.categorie IN ('permanent_invalid_recipient', 'permanent_invalid_domain'))) AS morts
                            FROM recipients r WHERE r.campaign_id = %(c)s AND r.submitted_at IS NOT NULL GROUP BY 1""",
                       {"c": campaign_id}):
        a = agg.setdefault(capacite.groupe_de(x["d"]), [0, 0])
        a[0] += x["n"]; a[1] += x["morts"]
    return {g: (n, m) for g, (n, m) in agg.items()}


def _taux_par_groupe(identite: str) -> dict[str, float]:
    lignes = pg.lignes("""
        SELECT split_part(r.email_normalized, '@', 2) AS d, count(r.delivered_at) AS livres,
               count(*) FILTER (WHERE (r.opened_at IS NOT NULL AND NOT EXISTS (SELECT 1 FROM clicks k WHERE k.recipient_id = r.id AND k.verdict = 'robot'))
                                   OR EXISTS (SELECT 1 FROM clicks k WHERE k.recipient_id = r.id AND k.verdict = 'humain')) AS ouverts
          FROM recipients r JOIN campaigns c ON c.id = r.campaign_id
         WHERE r.submitted_at IS NOT NULL AND %(i)s = ANY(COALESCE(c.sending_domains, ARRAY[%(i)s]))
         GROUP BY 1""", {"i": identite})
    agg: dict[str, list[int]] = {}
    for x in lignes:
        a = agg.setdefault(capacite.groupe_de(x["d"]), [0, 0])
        a[0] += x["ouverts"]; a[1] += x["livres"]
    return {g: taux_lisse(o, l) for g, (o, l) in agg.items()}


def _partis_aujourdhui(identite: str) -> dict[str, int]:
    """Mails PARTIS aujourd'hui par messagerie (les réponses Sweego arrivent avec ~10 min de retard)."""
    out: dict[str, int] = {}
    for x in pg.lignes("""SELECT split_part(r.email_normalized, '@', 2) AS d, count(*) AS n FROM recipients r
                           JOIN campaigns c ON c.id = r.campaign_id
                          WHERE (r.submitted_at AT TIME ZONE 'Europe/Paris')::date = (now() AT TIME ZONE 'Europe/Paris')::date
                            AND %(i)s = ANY(COALESCE(c.sending_domains, ARRAY[%(i)s])) GROUP BY 1""", {"i": identite}):
        g = capacite.groupe_de(x["d"])
        out[g] = out.get(g, 0) + x["n"]
    return out


def _capacites(identite: str) -> dict[str, dict]:
    partis = _partis_aujourdhui(identite)
    out = {}
    for ip in capacite.tableau()["ips"]:
        if ip["identite"] != identite:
            continue
        for f in ip["files"]:
            if f["flux"] != "market":
                continue
            deja = max(f["deja_aujourdhui"], partis.get(f["groupe"], 0))
            out[f["groupe"]] = {"debit_heure": f["debit_heure"], "restant_jour": max(0, f["max_aujourdhui"] - deja), "etat": f["etat"]}
    # Messagerie sans file encore (jamais servie) : profil de départ, moins ce qui est déjà parti.
    for g, n in partis.items():
        if g not in out:
            d, p, _ = capacite.PROFILS.get(g, capacite.PROFILS["autres"])
            out[g] = {"debit_heure": d, "restant_jour": max(0, p - n), "etat": "warming"}
    return out


# ── Une vague ────────────────────────────────────────────────────────────────

def _reserve(campaign_id: str) -> dict[str, list[int]]:
    par: dict[str, list[int]] = {}
    for x in pg.lignes("""SELECT r.id, split_part(r.email_normalized, '@', 2) AS d FROM recipients r
                           JOIN sending_batches sb ON sb.id = r.sending_batch_id
                          WHERE r.campaign_id = %(c)s AND r.send_status = 'queued' AND sb.status = 'scheduled'""",
                       {"c": campaign_id}):
        par.setdefault(capacite.groupe_de(x["d"]), []).append(x["id"])
    return par


def vague(campaign_id: str) -> dict:
    rc = pg.ligne("SELECT * FROM routage_campagnes WHERE campaign_id = %(c)s", {"c": campaign_id})
    c = pg.ligne("SELECT sending_domains, status FROM campaigns WHERE id = %(c)s", {"c": campaign_id})
    identite = (c.get("sending_domains") or ["news.leclientroi.email"])[0]
    # Contrôle avant CHAQUE vague : réputation d'envoi (IP + domaine).
    from infra import hetrix
    rep = hetrix.reputation_envoi([identite])
    if any(e["etat"] == "listee" for e in rep["elements"]):
        motif = "IP ou domaine d'envoi listé : " + ", ".join(e["cible"] for e in rep["elements"] if e["etat"] == "listee")
        pg.ecrire("UPDATE routage_campagnes SET actif = false, suspendu_motif = %(m)s WHERE campaign_id = %(c)s",
                  {"m": motif, "c": campaign_id})
        return {"suspendu": motif}
    reserve = _reserve(campaign_id)
    restants = {g: len(v) for g, v in reserve.items()}
    if not any(restants.values()):
        pg.ecrire("""UPDATE sending_batches SET status = 'skipped' WHERE campaign_id = %(c)s AND status = 'scheduled'
                      AND NOT EXISTS (SELECT 1 FROM recipients r WHERE r.sending_batch_id = sending_batches.id AND r.send_status = 'queued')""",
                  {"c": campaign_id})
        pg.ecrire("UPDATE routage_campagnes SET actif = false, termine_le = now() WHERE campaign_id = %(c)s", {"c": campaign_id})
        with pg.connexion() as cur:
            envoi._terminer_si_fini(cur, campaign_id)
        return {"termine": True}
    exclus = dict(rc.get("groupes_exclus") or {})
    nouvelles = exclusions_auto(_invalides_campagne(campaign_id), exclus)
    if nouvelles:
        exclus.update(nouvelles)
        pg.ecrire("UPDATE routage_campagnes SET groupes_exclus = %(e)s::jsonb WHERE campaign_id = %(c)s",
                  {"e": json.dumps(exclus, ensure_ascii=False), "c": campaign_id})
        with pg.connexion() as cur:
            envoi._audit(cur, campaign_id, "worker", "routage", "routage.exclusion",
                         " ; ".join(f"{capacite.NOMS.get(g, g)} : {m}" for g, m in nouvelles.items()))
    plan = planifier(restants, _taux_par_groupe(identite), _capacites(identite), float(rc["part_basse"]), exclus)
    choisis: list[int] = []
    numero = (pg.valeur("SELECT COALESCE(max(numero), 0) FROM routage_vagues WHERE campaign_id = %(c)s", {"c": campaign_id}) or 0) + 1
    lignes_plan = []
    for p in plan:
        ids = reserve.get(p["groupe"], [])
        random.shuffle(ids)
        pris = ids[:p["volume"]]
        choisis += pris
        lignes_plan.append({**p, "restant_avant": len(ids), "pris": len(pris)})
    sb_id = None
    if choisis:
        seq = (pg.valeur("SELECT COALESCE(max(sequence_number), 0) FROM sending_batches WHERE campaign_id = %(c)s",
                         {"c": campaign_id}) or 0) + 1
        sb_id = pg.valeur("""INSERT INTO sending_batches (campaign_id, sequence_number, recipients_count, status, scheduled_for)
                             VALUES (%(c)s, %(s)s, %(n)s, 'pending', now()) RETURNING id""",
                          {"c": campaign_id, "s": seq, "n": len(choisis)})
        pg.ecrire("UPDATE recipients SET sending_batch_id = %(b)s, updated_at = now() WHERE id = ANY(%(i)s) AND send_status = 'queued'",
                  {"b": sb_id, "i": choisis})
        file.empiler(envoi.JOB_ENVOYER, campaign_id=campaign_id, payload={"sending_batch_id": str(sb_id)},
                     idempotency_key=f"dispatch:{sb_id}", priority=40)
    for p in lignes_plan:
        pg.ecrire("""INSERT INTO routage_vagues (campaign_id, numero, groupe, priorite, taux_ouverture, volume, restant_avant, sending_batch_id, raison)
                     VALUES (%(c)s, %(n)s, %(g)s, %(p)s, %(t)s, %(v)s, %(r)s, %(b)s, %(ra)s)""",
                  {"c": campaign_id, "n": numero, "g": p["groupe"], "p": p["priorite"], "t": None, "v": p["pris"],
                   "r": p["restant_avant"], "b": sb_id, "ra": p["raison"]})
    pg.ecrire("UPDATE routage_campagnes SET prochaine_vague = now() + %(i)s WHERE campaign_id = %(c)s",
              {"i": INTERVALLE, "c": campaign_id})
    with pg.connexion() as cur:
        envoi._audit(cur, campaign_id, "worker", "routage", "routage.vague",
                     f"Vague {numero} : {len(choisis)} mail(s) — " + ", ".join(f"{capacite.NOMS.get(p['groupe'], p['groupe'])} {p['pris']}" for p in lignes_plan if p["pris"]),
                     {"plan": lignes_plan})
    return {"numero": numero, "envoyes": len(choisis), "plan": lignes_plan}


def tour() -> list[dict]:
    """Appelé par le worker : lance les vagues dues des campagnes routées, dans la fenêtre 8h-22h."""
    appliquer_schema()
    if not dans_fenetre():
        return []
    out = []
    for rc in pg.lignes("""SELECT r.campaign_id FROM routage_campagnes r JOIN campaigns c ON c.id = r.campaign_id
                            WHERE r.actif AND r.prochaine_vague <= now() AND c.status = 'sending'"""):
        try:
            out.append({"campaign_id": str(rc["campaign_id"]), **vague(str(rc["campaign_id"]))})
        except Exception as e:  # noqa: BLE001
            out.append({"campaign_id": str(rc["campaign_id"]), "erreur": str(e)[:200]})
    return out


def etat(campaign_id: str) -> dict:
    appliquer_schema()
    rc = pg.ligne("SELECT * FROM routage_campagnes WHERE campaign_id = %(c)s", {"c": campaign_id})
    if not rc:
        return {"actif": False, "existe": False}
    reserve = {g: len(v) for g, v in _reserve(campaign_id).items()}
    vagues = pg.lignes("""SELECT numero, min(at) AS at, sum(volume) AS volume,
                                 json_agg(json_build_object('groupe', groupe, 'priorite', priorite, 'volume', volume, 'raison', raison) ORDER BY priorite, groupe) AS detail
                            FROM routage_vagues WHERE campaign_id = %(c)s GROUP BY numero ORDER BY numero DESC LIMIT 30""",
                       {"c": campaign_id})
    return {"existe": True, "actif": rc["actif"], "prochaine_vague": rc["prochaine_vague"], "suspendu_motif": rc["suspendu_motif"],
            "termine_le": rc["termine_le"], "groupes_exclus": rc.get("groupes_exclus") or {}, "part_basse": float(rc["part_basse"]), "reserve": reserve,
            "reserve_total": sum(reserve.values()), "vagues": vagues}
