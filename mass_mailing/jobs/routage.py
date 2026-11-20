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
from jobs import capacite, envoi, file, placement  # noqa: E402

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
# Jamais plus de 10 % d'une vague vers un même domaine destinataire (Camille, 21/10/2026 : 456 mails
# Gmail en un après-midi, vague après vague). gmail.com, orpi.com, foncia.fr… : chacun ≤ 10 %.
PART_MAX_DOMAINE = 0.10
# File jugée « spam probable » (jobs/placement.py) : quelques mails par vague seulement, pour voir si
# de vraies ouvertures reviennent, au lieu de remplir un dossier Spam (Gmail, 21/10/2026).
SONDE = 2
# Une vague reflète la réserve : une file ne prend pas plus de 2 × sa part (21/10/2026).
FACTEUR_EQUILIBRE = 2.0
# Domaine coupé de la campagne : une plainte, ou au moins 3 rebonds définitifs faisant ≥ 10 % de ses envois.
REBONDS_DOMAINE_MIN = 3
REBONDS_DOMAINE_TAUX = 0.10

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
ALTER TABLE routage_campagnes ADD COLUMN IF NOT EXISTS domaines_exclus JSONB NOT NULL DEFAULT '{}'::jsonb;
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


def inscrire(campaign_id: str, acteur: str) -> None:
    """Espace client (13/10/2026) : la campagne autorisée passe en ROUTAGE au lieu de partir lot par lot.
    Ses lots vont en réserve ; l'agent envoie vague par vague, par messagerie, dans la fenêtre de la
    campagne, sous le plafond de warm-up. Les contrôles ont déjà été faits par `envoi.autoriser`."""
    appliquer_schema()
    with pg.connexion() as cur:
        cur.execute("""UPDATE sending_batches SET status = 'scheduled'
                        WHERE campaign_id = %(c)s AND status = 'pending'""", {"c": campaign_id})
        cur.execute("""INSERT INTO routage_campagnes (campaign_id, actif, part_basse, prochaine_vague, par)
                       VALUES (%(c)s, true, %(p)s, now(), %(a)s)
                       ON CONFLICT (campaign_id) DO UPDATE SET actif = true, prochaine_vague = now(),
                              suspendu_motif = NULL, termine_le = NULL""",
                    {"c": campaign_id, "p": PART_BASSE, "a": acteur})
        envoi._audit(cur, campaign_id, "user", acteur, "routage.start",
                     "Routage par messagerie : vagues horaires dans la fenêtre de la campagne, sous le plafond de warm-up")


def est_routee(campaign_id: str) -> bool:
    try:
        return bool(pg.valeur("SELECT actif FROM routage_campagnes WHERE campaign_id = %(c)s", {"c": campaign_id}))
    except Exception:  # noqa: BLE001 — table absente : pas de routage
        return False


def _borner_warmup(campaign_id: str, plan: list[dict]) -> list[dict]:
    """Budget de la vague = part de warm-up de l'heure (adresse expéditrice), servie dans l'ordre du
    plan (priorité 1 d'abord). Une vague ne dépasse jamais ce que le warm-up autorise à cette heure."""
    import math
    from infra import clients
    camp = pg.ligne("SELECT * FROM campaigns WHERE id = %(c)s", {"c": campaign_id})
    profil = envoi.profil_defaut()
    exp = envoi.expediteur(camp, profil) or {}
    adresse = (exp.get("from_email") or "").lower()
    e = pg.ligne("SELECT * FROM expediteurs WHERE lower(adresse) = %(a)s AND actif", {"a": adresse})
    if not e:
        return [{**p, "volume": 0, "raison": f"aucun plan de warm-up pour {adresse or 'l’expéditeur'}"} for p in plan]
    part = envoi.part_de_la_journee(envoi.fenetre(camp), datetime.now(PARIS))
    cap = math.ceil(min(clients.plafond_du_jour(e), e.get("plafond_fournisseur") or 10**9) * part)
    deja = pg.valeur("""SELECT count(*) FROM recipients WHERE lower(from_email) = %(a)s AND submitted_at >=
                         date_trunc('day', now() AT TIME ZONE 'Europe/Paris') AT TIME ZONE 'Europe/Paris'""", {"a": adresse}) or 0
    budget = max(0, cap - int(deja))
    out = []
    # Les sondes passent d'abord : sans elles, une file en spam probable ne serait plus jamais mesurée.
    for p in sorted(plan, key=lambda x: (0 if x.get("sonde") else 1, x.get("priorite") or 9)):
        v = min(p["volume"], budget)
        budget -= v
        out.append({**p, "volume": v, "raison": p["raison"] + (f" · bornée par le warm-up ({cap} à cette heure)" if v < p["volume"] else "")})
    return out


# ── Priorités et plan d'une vague (fonctions pures testées) ─────────────────────

def taux_lisse(ouverts: int, livres: int) -> float:
    return (ouverts + 1) / (livres + 20)


def planifier(restants: dict[str, int], taux: dict[str, float], capacites: dict[str, dict], part_basse: float,
              exclus: dict[str, str] | None = None, placements: dict[str, dict] | None = None) -> list[dict]:
    """Plan d'une vague. restants : adresses en réserve par messagerie ; taux : ouverture lissée ;
    capacites : {groupe: {debit_heure, restant_jour, etat}} ; exclus : {groupe: motif} retirés du routage ;
    placements : {groupe: {etat, motif}} (jobs/placement.py). Renvoie [{groupe, priorite, volume, raison}]."""
    exclus = exclus or {}
    placements = placements or {}
    en_spam = {g for g, p in placements.items() if p.get("etat") == placement.SPAM}
    prio1 = {g for g, n in restants.items() if n > 0 and taux.get(g, 0) >= SEUIL_PRIORITE and g not in en_spam}
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
        raison = (f"priorité {'1' if haute else '2'} : ouverture humaine {taux.get(g, 0):.1%}, "
                  f"part {int(part * 100)} % du débit {debit:.0f}/h, reste du jour {reste_jour}")
        if g in en_spam:
            volume = min(volume, SONDE)
            raison = f"SONDE {SONDE}/vague — spam probable : {placements[g].get('motif', '')}"
        plan.append({"groupe": g, "priorite": 1 if haute else 2, "volume": volume, "raison": raison, "sonde": g in en_spam})
    return plan


def plafond_domaine(total: int) -> int:
    """Fonction PURE : nombre maximum de mails d'une vague vers un même domaine destinataire."""
    return max(1, int(total * PART_MAX_DOMAINE))


def plafonds_equilibre(restants: dict[str, int], total: int) -> dict[str, int]:
    """Fonction PURE : aucune file ne prend plus de FACTEUR_EQUILIBRE × sa part de la réserve
    (guide § 3 « répartition égale entre fournisseurs, ne pas envoyer tout le volume vers Gmail »)."""
    import math
    n = sum(restants.values())
    return {g: max(1, math.ceil(total * FACTEUR_EQUILIBRE * k / n)) for g, k in restants.items()} if n else {}


def domaines_a_bloquer(stats: dict[str, dict], deja: dict[str, str]) -> dict[str, str]:
    """Fonction PURE. stats : {domaine: {envoyes, rebonds, plaintes}} sur la campagne.
    Une plainte, ou ≥ 3 rebonds définitifs faisant ≥ 10 % des envois : le domaine ne reçoit plus rien."""
    out = {}
    for d, x in stats.items():
        if d in deja:
            continue
        if x.get("plaintes", 0) >= 1:
            out[d] = f"{x['plaintes']} plainte(s)"
        elif x.get("rebonds", 0) >= REBONDS_DOMAINE_MIN and x["rebonds"] / max(1, x.get("envoyes", 0)) >= REBONDS_DOMAINE_TAUX:
            out[d] = f"{x['rebonds']} rebonds définitifs sur {x['envoyes']} envois"
    return out


def choisir(candidats: dict[str, list[tuple[int, str]]], volumes: dict[str, int], maxima: dict[str, int],
            ordre: list[str], plafonds: dict[str, int] | None = None, bloques: set[str] | None = None) -> dict[str, list[int]]:
    """Le plafond de 10 % se calcule sur la vague RÉELLE (22/10/2026 : vague 40 prévue à ~125,
    partie à 75 → wanadoo.fr à 16 %). On resserre jusqu'à ce que la vague tienne la règle."""
    total = sum(volumes.values())
    for _ in range(4):
        pris = _choisir(candidats, volumes, maxima, ordre, plafonds, bloques, total)
        n = sum(len(v) for v in pris.values())
        if n >= total or plafond_domaine(n) >= plafond_domaine(total):
            return pris
        total = n
    return pris


def _choisir(candidats, volumes, maxima, ordre, plafonds, bloques, total) -> dict[str, list[int]]:
    """Fonction PURE : destinataires d'une vague, aucun domaine au-delà de PART_MAX_DOMAINE.
    candidats : {groupe: [(id, domaine)]} dans l'ordre de préférence ; volumes : ce que le plan donne
    à chaque messagerie ; maxima : ce que sa capacité permet (avant warm-up) ; ordre : priorité.
    Ce qu'une messagerie ne peut pas prendre (Gmail = un seul domaine) passe aux suivantes, sans
    jamais dépasser leur capacité ni le total de la vague. plafonds : maximum par file (équilibre) ;
    bloques : domaines qui ne reçoivent plus rien (plainte, rebonds)."""
    plafonds = plafonds or {}
    bloques = bloques or set()
    cap = plafond_domaine(total)
    par_dom: dict[str, int] = {}
    pris: dict[str, list[int]] = {g: [] for g in ordre}
    vus: set[int] = set()

    def servir(g: str, jusqua: int) -> None:
        jusqua = min(jusqua, plafonds.get(g, jusqua))
        for i, d in candidats.get(g, []):
            if d in bloques:
                continue
            if len(pris[g]) >= jusqua or sum(len(v) for v in pris.values()) >= total:
                return
            if i in vus or par_dom.get(d, 0) >= cap:
                continue
            pris[g].append(i); vus.add(i); par_dom[d] = par_dom.get(d, 0) + 1

    for g in ordre:
        servir(g, volumes.get(g, 0))
    for g in ordre:
        servir(g, maxima.get(g, 0))
    return pris


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
    """Taux d'ouverture HUMAIN par messagerie (21/10/2026). Avant : ouverture brute — le scanner de
    Gmail ouvre chaque mail 3 s après la livraison ; Gmail paraissait ouvrir à 18 % (1 vraie
    ouverture sur 456) et le routage l'a servi à plein débit tout l'après-midi."""
    lignes = pg.lignes("""
        SELECT r.id, split_part(r.email_normalized, '@', 2) AS d, r.delivered_at IS NOT NULL AS livre,
               (r.opened_at IS NOT NULL AND NOT EXISTS (SELECT 1 FROM clicks k WHERE k.recipient_id = r.id AND k.verdict = 'robot')) AS ouvert_brut,
               EXISTS (SELECT 1 FROM clicks k WHERE k.recipient_id = r.id AND k.verdict = 'humain' AND k.type_lien = 'contenu') AS clic_humain
          FROM recipients r JOIN campaigns c ON c.id = r.campaign_id
         WHERE r.submitted_at IS NOT NULL AND %(i)s = ANY(COALESCE(c.sending_domains, ARRAY[%(i)s]))""", {"i": identite})
    verdicts = placement.verdicts_ouverture(identite)
    agg: dict[str, list[int]] = {}
    for x in lignes:
        a = agg.setdefault(capacite.groupe_de(x["d"]), [0, 0])
        if x["id"] in verdicts:
            ouvert = verdicts[x["id"]] == "humain"
        else:   # ouverture sans IP (Sweego) ou pas d'ouverture : règle d'avant
            ouvert = x["ouvert_brut"]
        a[0] += int(ouvert or x["clic_humain"]); a[1] += int(x["livre"])
    return {g: taux_lisse(o, l) for g, (o, l) in agg.items()}


def analyser_vague_precedente(campaign_id: str, identite: str) -> str | None:
    """Avant chaque vague : bilan de la vague d'avant (21/10/2026, Camille : « tu n'as même pas analysé
    la vague d'avant »). Écrit dans le journal de la campagne ; le taux humain qui en sort pilote déjà
    la priorité de la vague suivante."""
    prec = pg.ligne("""SELECT numero, min(at) AS at, array_agg(DISTINCT sending_batch_id::text) FILTER (WHERE sending_batch_id IS NOT NULL) AS lots
                         FROM routage_vagues WHERE campaign_id = %(c)s GROUP BY numero ORDER BY numero DESC LIMIT 1""",
                    {"c": campaign_id})
    if not prec or not prec["lots"]:
        return None
    rs = pg.lignes("""SELECT id, split_part(email_normalized, '@', 2) AS d, delivered_at IS NOT NULL AS livre,
                             send_status = 'bounced' AS rebond, complained_at IS NOT NULL AS plainte
                        FROM recipients WHERE sending_batch_id = ANY(%(l)s::uuid[])""", {"l": [str(x) for x in prec["lots"]]})
    if not rs:
        return None
    verdicts = placement.verdicts_ouverture(identite, prec["at"] - timedelta(minutes=5))
    doms: dict[str, int] = {}
    for x in rs:
        doms[x["d"]] = doms.get(x["d"], 0) + 1
    top_d, top_n = max(doms.items(), key=lambda kv: kv[1])
    v = [verdicts.get(x["id"]) for x in rs]
    texte = (f"Analyse vague {prec['numero']} : {len(rs)} envoyé(s), {sum(x['livre'] for x in rs)} livré(s), "
             f"{sum(x['rebond'] for x in rs)} rebond(s), {sum(x['plainte'] for x in rs)} plainte(s) · ouvertures : "
             f"{v.count('humain')} humaine(s), {v.count('apple')} Apple, {v.count('machine')} machine(s) · "
             f"domaine le plus servi : {top_d} {top_n} ({top_n / len(rs):.0%})")
    with pg.connexion() as cur:
        envoi._audit(cur, campaign_id, "worker", "routage", "routage.analyse", texte)
    return texte


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

def _stats_domaines(campaign_id: str) -> dict[str, dict]:
    """Par domaine destinataire : envoyés, rebonds DÉFINITIFS (pas les boîtes pleines), plaintes."""
    return {x["d"]: x for x in pg.lignes("""
        SELECT split_part(email_normalized, '@', 2) AS d, count(*) AS envoyes,
               count(*) FILTER (WHERE send_status = 'bounced' AND COALESCE(bounce_type, '') !~* '^(transient|undetermined)') AS rebonds,
               count(*) FILTER (WHERE complained_at IS NOT NULL) AS plaintes
          FROM recipients WHERE campaign_id = %(c)s AND submitted_at IS NOT NULL GROUP BY 1""", {"c": campaign_id})}


def _ordre_de_passage(campaign_id: str, identite: str, ids: list[int]) -> dict[int, tuple]:
    """Qui part en premier (guide § 3 : « les plus engagés d'abord ») : clé de tri par destinataire.
    1. domaine où de vraies personnes ont déjà ouvert nos mails ; 2. risque de rebond le plus bas
    (modèle appris chaque nuit, jobs/risque_adresses) ; le hasard départage (liste déjà mélangée)."""
    if not ids:
        return {}
    from jobs import risque_adresses
    lignes = pg.lignes("SELECT id, email_normalized e, validation_provider_status v FROM recipients WHERE id = ANY(%(i)s)", {"i": ids})
    humains = placement.verdicts_ouverture(identite)
    doms_lus = {x["d"] for x in pg.lignes("""SELECT DISTINCT split_part(email_normalized, '@', 2) AS d FROM recipients
                                             WHERE id = ANY(%(i)s)""", {"i": [i for i, v in humains.items() if v == "humain"]})}
    with pg.espace(pg.SCHEMA):        # le modèle est appris une fois pour toutes, dans l'espace plateforme
        m = risque_adresses.modele_courant()
    out = {}
    for x in lignes:
        p = risque_adresses.probabilite(m, risque_adresses.facteurs(x["e"], x["v"]))[0] if m else 0.0
        out[x["id"]] = (0 if x["e"].rsplit("@", 1)[-1] in doms_lus else 1, round(p, 2))
    return out


def _reserve(campaign_id: str, avec_domaine: bool = False) -> dict[str, list]:
    # A/B test : toute la file est servie, échantillon compris (21/10/2026 — il ne retient plus rien).
    par: dict[str, list] = {}
    for x in pg.lignes("""SELECT r.id, split_part(r.email_normalized, '@', 2) AS d FROM recipients r
                           JOIN sending_batches sb ON sb.id = r.sending_batch_id
                          WHERE r.campaign_id = %(c)s AND r.send_status = 'queued' AND sb.status = 'scheduled'""",
                       {"c": campaign_id}):
        par.setdefault(capacite.groupe_de(x["d"]), []).append((x["id"], x["d"]) if avec_domaine else x["id"])
    return par


def _alterner(ids: list[int], variantes: dict, premier: str | None = None) -> list[int]:
    """Fonction pure : entrelace les destinataires A et B. `premier` = la version en retard sur
    l'ensemble de la campagne (sinon la plus fournie dans cette liste)."""
    a = [i for i in ids if variantes.get(i) == "A"]
    b = [i for i in ids if variantes.get(i) == "B"]
    autres = [i for i in ids if variantes.get(i) not in ("A", "B")]
    if premier in ("A", "B") and (a if premier == "A" else b):
        p, q = (a, b) if premier == "A" else (b, a)
    else:
        p, q = (a, b) if len(a) >= len(b) else (b, a)
    out = []
    for k in range(max(len(p), len(q))):
        if k < len(p):
            out.append(p[k])
        if k < len(q):
            out.append(q[k])
    return out + autres


def _relancer_echantillon(campaign_id: str) -> dict:
    """A/B test en attente (20/10/2026) : la réserve est vide mais des destinataires de l'échantillon
    peuvent dormir dans un lot reporté (job repoussé au lendemain). Sans eux, le test ne passe jamais
    en observation et le routage attend sans fin (Zylio : 0 vague du 16 au 20/10). On avance leur
    job à maintenant, et on dit dans le journal pourquoi aucune vague ne part (une fois par état)."""
    attente = pg.valeur("""SELECT count(*) FROM recipients WHERE campaign_id = %(c)s AND variante IS NOT NULL
                             AND send_status = 'queued'""", {"c": campaign_id}) or 0
    avances = pg.ecrire("""UPDATE jobs SET run_after = now() WHERE campaign_id = %(c)s AND job_type = %(t)s
                             AND status = 'pending' AND run_after > now() + interval '15 minutes'
                             AND (payload->>'sending_batch_id')::uuid IN (
                                 SELECT DISTINCT r.sending_batch_id FROM recipients r WHERE r.campaign_id = %(c)s
                                    AND r.variante IS NOT NULL AND r.send_status = 'queued')""",
                        {"c": campaign_id, "t": envoi.JOB_ENVOYER}) if attente else 0
    resume = (f"Pas de vague : A/B test en cours, {attente} destinataire(s) de l'échantillon encore en file"
              + (f" (lot reporté relancé)" if avances else "")
              if attente else "Pas de vague : échantillon A/B parti, le reste attend la décision du test")
    dernier = pg.valeur("""SELECT summary FROM campaign_events WHERE campaign_id = %(c)s
                            AND event_type LIKE 'routage.%%' ORDER BY created_at DESC LIMIT 1""", {"c": campaign_id})
    if avances or not (dernier or "").startswith(resume.split(",")[0]):
        with pg.connexion() as cur:
            envoi._audit(cur, campaign_id, "worker", "routage", "routage.attente_ab", resume)
    return {"echantillon_en_file": attente, "lots_relances": avances}


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
    # Vrai serveur de chaque domaine pro de la réserve (21/10/2026) : résolu une fois, puis en cache.
    capacite.charger_mx()
    try:
        from infra import mx
        mx.resoudre({x["d"] for x in pg.lignes("""SELECT DISTINCT split_part(email_normalized, '@', 2) AS d FROM recipients
                                                   WHERE campaign_id = %(c)s AND send_status = 'queued'""", {"c": campaign_id})})
    except Exception:  # noqa: BLE001 — DNS en panne : les domaines non résolus restent « autres »
        pass
    reserve_dom = _reserve(campaign_id, avec_domaine=True)
    domaine_de = {i: d for v in reserve_dom.values() for i, d in v}
    reserve = {g: [i for i, _ in v] for g, v in reserve_dom.items()}
    restants = {g: len(v) for g, v in reserve.items()}
    from jobs import ab_test
    if not any(restants.values()) and ab_test.en_cours(campaign_id):
        # Réserve vide pendant un test : des destinataires de l'échantillon dorment peut-être dans un lot reporté.
        pg.ecrire("UPDATE routage_campagnes SET prochaine_vague = now() + %(i)s WHERE campaign_id = %(c)s",
                  {"i": INTERVALLE, "c": campaign_id})
        return {"ab_attente": ab_test.phase(campaign_id), **_relancer_echantillon(campaign_id)}
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
    dom_exclus = dict(rc.get("domaines_exclus") or {})
    nouveaux = domaines_a_bloquer(_stats_domaines(campaign_id), dom_exclus)
    if nouveaux:
        dom_exclus.update(nouveaux)
        pg.ecrire("UPDATE routage_campagnes SET domaines_exclus = %(e)s::jsonb WHERE campaign_id = %(c)s",
                  {"e": json.dumps(dom_exclus, ensure_ascii=False), "c": campaign_id})
        with pg.connexion() as cur:
            envoi._audit(cur, campaign_id, "worker", "routage", "routage.exclusion",
                         "Domaine(s) coupé(s) de la campagne : " + " ; ".join(f"{d} ({m})" for d, m in nouveaux.items()))
    try:
        analyser_vague_precedente(campaign_id, identite)
    except Exception:  # noqa: BLE001 — l'analyse ne bloque jamais une vague
        pass
    try:
        placements = placement.suivre(campaign_id, identite)
    except Exception:  # noqa: BLE001 — sans mesure, la vague part sur les autres règles
        placements = {}
    plan = planifier(restants, _taux_par_groupe(identite), _capacites(identite), float(rc["part_basse"]), exclus, placements)
    # Fiche de décision (skill pilotage § 15) : chaque file dit ce qui a été mesuré et ce qui en découle.
    caps = _capacites(identite)
    for p in plan:
        pl, cp = placements.get(p["groupe"]) or {}, caps.get(p["groupe"]) or {}
        if pl and not p["raison"].startswith("SONDE"):
            p["raison"] += f" · placement : {pl['etat'].replace('_', ' ')} ({pl['motif']})"
        if cp.get("etat") and cp["etat"] != "warming":
            p["raison"] += f" · file {cp['etat']}"
    maxima = {p["groupe"]: p["volume"] for p in plan}
    if pg.schema_courant() != pg.SCHEMA:
        plan = _borner_warmup(campaign_id, plan)
    choisis: list[int] = []
    numero = (pg.valeur("SELECT COALESCE(max(numero), 0) FROM routage_vagues WHERE campaign_id = %(c)s", {"c": campaign_id}) or 0) + 1
    lignes_plan = []
    # A/B test (15/10/2026) : pendant le test, chaque vague sert A et B à parts égales
    # (alternance A, B, A, B… en commençant par la version qui a le plus de retard). L'échantillon
    # passe d'abord ; le reste de la file reçoit sa version au départ de la vague (21/10/2026).
    variantes = {}
    en_ab = ab_test.en_cours(campaign_id)
    if en_ab:
        variantes = {x["id"]: x["variante"] for x in pg.lignes(
            "SELECT id, variante FROM recipients WHERE campaign_id = %(c)s AND send_status = 'queued' AND variante IS NOT NULL",
            {"c": campaign_id})}
    reste_ab = {"A": sum(1 for v in variantes.values() if v == "A"), "B": sum(1 for v in variantes.values() if v == "B")}
    candidats = {}
    try:
        ordre = _ordre_de_passage(campaign_id, identite, [i for p in plan if p["volume"] for i in reserve.get(p["groupe"], [])])
    except Exception:  # noqa: BLE001 — sans score, ordre au hasard comme avant
        ordre = {}
    for p in plan:
        ids = reserve.get(p["groupe"], [])
        random.shuffle(ids)
        ids.sort(key=lambda i: ordre.get(i, (1, 1.0)))
        if variantes:
            # La version qui a le plus de destinataires en file sur TOUTE la campagne passe
            # d'abord : l'écart cumulé A/B reste ≤ 1, pas seulement l'écart d'un groupe.
            ids = _alterner(ids, variantes, "A" if reste_ab["A"] >= reste_ab["B"] else "B")
        candidats[p["groupe"]] = [(i, domaine_de.get(i, "")) for i in ids]
    # Aucun domaine destinataire au-delà de 10 % de la vague (21/10/2026).
    total = sum(p["volume"] for p in plan)
    plafonds = plafonds_equilibre({g: n for g, n in restants.items() if g not in exclus}, total)
    selection = choisir(candidats, {p["groupe"]: p["volume"] for p in plan}, maxima, [p["groupe"] for p in plan],
                        plafonds, set(dom_exclus))
    cap_dom = plafond_domaine(total)
    for p in plan:
        pris = selection.get(p["groupe"], [])
        for i in pris:
            if variantes.get(i) in reste_ab:
                reste_ab[variantes[i]] -= 1
        choisis += pris
        raison = p["raison"] + (f" · bornée à {min(p['volume'], plafonds.get(p['groupe'], p['volume']))} (équilibre) et {cap_dom} max par domaine"
                                if len(pris) != p["volume"] else "")
        lignes_plan.append({**p, "raison": raison, "restant_avant": len(candidats[p["groupe"]]), "pris": len(pris)})
    sans_version = [i for i in choisis if i not in variantes] if en_ab else []
    if sans_version:
        compte = {x["variante"]: x["n"] for x in pg.lignes(
            """SELECT variante, count(*) AS n FROM recipients WHERE campaign_id = %(c)s AND variante IS NOT NULL
                GROUP BY variante""", {"c": campaign_id})}
        versions = ab_test.repartir(len(sans_version), compte)
        for v in ab_test.VARIANTES:
            ids_v = [i for i, x in zip(sans_version, versions) if x == v]
            if ids_v:
                pg.ecrire("""UPDATE recipients SET variante = %(v)s, ab_suite = true, updated_at = now()
                              WHERE id = ANY(%(i)s) AND variante IS NULL""", {"v": v, "i": ids_v})
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
                     {"plan": lignes_plan, "placements": placements, "domaines_exclus": dom_exclus,
                      "plafond_domaine": cap_dom, "plafonds_equilibre": plafonds})
    return {"numero": numero, "envoyes": len(choisis), "plan": lignes_plan}


def tour() -> list[dict]:
    """Appelé par le worker : lance les vagues dues des campagnes routées, dans la fenêtre 8h-22h."""
    appliquer_schema()
    client = pg.schema_courant() != pg.SCHEMA
    if not client and not dans_fenetre():
        return []
    out = []
    for rc in pg.lignes("""SELECT r.campaign_id, c.* FROM routage_campagnes r JOIN campaigns c ON c.id = r.campaign_id
                            WHERE r.actif AND r.prochaine_vague <= now() AND c.status = 'sending'"""):
        # Espace client : la fenêtre de LA campagne (jours + plage) — 13/10/2026.
        if client and not envoi.dans_fenetre(envoi.fenetre(rc), datetime.now(PARIS)):
            continue
        try:
            out.append({"campaign_id": str(rc["campaign_id"]), **vague(str(rc["campaign_id"]))})
        except Exception as e:  # noqa: BLE001
            out.append({"campaign_id": str(rc["campaign_id"]), "erreur": str(e)[:200]})
    return out


def etat(campaign_id: str) -> dict:
    appliquer_schema()
    capacite.charger_mx()
    rc = pg.ligne("SELECT * FROM routage_campagnes WHERE campaign_id = %(c)s", {"c": campaign_id})
    if not rc:
        return {"actif": False, "existe": False}
    reserve = {g: len(v) for g, v in _reserve(campaign_id).items()}
    vagues = pg.lignes("""SELECT numero, min(at) AS at, sum(volume) AS volume,
                                 json_agg(json_build_object('groupe', groupe, 'priorite', priorite, 'volume', volume, 'raison', raison) ORDER BY priorite, groupe) AS detail
                            FROM routage_vagues WHERE campaign_id = %(c)s GROUP BY numero ORDER BY numero DESC LIMIT 2000""",
                       {"c": campaign_id})
    # Journal (21/10/2026) : sans ces lignes, du 16 au 21/10 la page n'a montré que la vague du 16/10
    # alors que l'échantillon A/B partait et que le routage notait pourquoi il n'envoyait rien.
    evenements = pg.lignes("""SELECT created_at AS at, event_type AS type, summary FROM campaign_events
                               WHERE campaign_id = %(c)s AND event_type <> 'routage.vague'
                                 AND (event_type LIKE 'routage.%%' OR event_type LIKE 'ab.%%'
                                      OR event_type IN ('sending.batch_dispatched', 'sending.warmup_cap',
                                                        'sending.paused', 'sending.authorized', 'sending.stopped'))
                               ORDER BY created_at DESC LIMIT 2000""", {"c": campaign_id})
    return {"existe": True, "actif": rc["actif"], "prochaine_vague": rc["prochaine_vague"], "suspendu_motif": rc["suspendu_motif"],
            "termine_le": rc["termine_le"], "groupes_exclus": rc.get("groupes_exclus") or {}, "part_basse": float(rc["part_basse"]), "reserve": reserve,
            "reserve_total": sum(reserve.values()), "vagues": vagues, "evenements": evenements}
