#!/usr/bin/env python3
"""mass_mailing/jobs/apprentissage.py — l'agent qui apprend ce qui fait un bon message.

Demande de Camille (13/10/2026) : « fais tourner un agent pendant 3 mois qui améliore
cette partie [l'étape Message et sa note sur 100] en corrigeant et en apprenant ce qui se
passe ». Pas d'API Anthropic dans Genesis : l'agent est statistique, il tourne sur le
serveur, sans IA externe.

Chaque nuit (4 h, heure de Paris), jusqu'au 13/01/2027 :

1. **Observer** : pour chaque campagne partie depuis 3 à 60 jours, dans TOUS les espaces
   (interne et clients), il relance l'analyse du message (sans tester les liens) et la
   rapproche de ce qui s'est réellement passé : livrés, ouverts, clics, rebonds définitifs,
   plaintes, désinscriptions. Une ligne par campagne, mise à jour tant qu'elle vit.
2. **Apprendre** : pour chaque problème que l'analyse sait détecter, il compare les
   campagnes qui l'avaient et celles qui ne l'avaient pas :
   - taux négatif = (rebonds définitifs + plaintes + désinscriptions) / livrés ;
   - taux d'ouverture = ouverts / livrés.
   Un problème associé à plus de réactions négatives ou à moins d'ouvertures voit son
   poids monter ; un problème sans effet mesurable voit son poids baisser.
3. **Mots** : les expressions (1 à 2 mots) présentes dans des campagnes au taux négatif
   nettement plus haut que la moyenne deviennent « à surveiller » dans l'analyse.

Garde-fous — l'agent corrige la note, il ne la casse pas :
- rien ne bouge sous MIN_CAMPAGNES campagnes observées, ni pour une règle vue moins de
  MIN_AVEC fois avec ET MIN_SANS fois sans ;
- un poids bouge d'au plus PAS_MAX points par nuit, reste entre 0 et 25, et un problème
  BLOQUANT garde toujours son plancher (il bloque l'envoi quoi qu'il arrive) ;
- les campagnes de moins de MIN_LIVRES livrés ne comptent pas (trop de bruit) ;
- tout est journalisé (`apprentissage_journal`), lisible dans l'interface superadmin.

Les tables vivent dans `mass_mailing` (plateforme) : l'agent n'y range que des chiffres
agrégés par campagne, jamais une adresse.
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import clients, controle_html, pg, stockage  # noqa: E402

FIN = date(2027, 1, 13)          # 3 mois à partir du 13/10/2026
HEURE_PARIS = 4
MIN_CAMPAGNES = 8
MIN_AVEC, MIN_SANS = 3, 3
MIN_LIVRES = 50
PAS_MAX = 2.0
POIDS_DEFAUT = {"bloquant": 25.0, "avertissement": 7.0, "info": 0.0}
PLANCHER_BLOQUANT = 15.0

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS apprentissage_observations (
    schema_pg      TEXT        NOT NULL,
    campaign_id    UUID        NOT NULL,
    caracteristiques JSONB     NOT NULL,
    resultats      JSONB       NOT NULL,
    observee_le    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (schema_pg, campaign_id)
);
CREATE TABLE IF NOT EXISTS apprentissage_regles (
    cle            TEXT PRIMARY KEY,
    niveau         TEXT        NOT NULL,
    libelle        TEXT        NOT NULL,
    poids_defaut   NUMERIC     NOT NULL,
    poids          NUMERIC     NOT NULL,
    n_avec         INT         NOT NULL DEFAULT 0,
    n_sans         INT         NOT NULL DEFAULT 0,
    negatif_avec   NUMERIC,
    negatif_sans   NUMERIC,
    ouverture_avec NUMERIC,
    ouverture_sans NUMERIC,
    maj_le         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS apprentissage_mots (
    expression     TEXT PRIMARY KEY,
    n_campagnes    INT         NOT NULL,
    negatif        NUMERIC     NOT NULL,
    reference      NUMERIC     NOT NULL,
    statut         TEXT        NOT NULL DEFAULT 'surveille',
    maj_le         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS apprentissage_journal (
    id             BIGSERIAL PRIMARY KEY,
    le             TIMESTAMPTZ NOT NULL DEFAULT now(),
    resume         TEXT        NOT NULL,
    details        JSONB
);
"""


def _plateforme():
    return pg.espace(pg.SCHEMA)


def assurer_schema() -> None:
    with _plateforme():
        pg.ecrire(SCHEMA_SQL)


def cle_probleme(p: dict) -> str:
    """Clé stable d'un problème : catégorie + message sans les nombres ni le détail."""
    msg = re.sub(r"\d+([.,]\d+)?", "N", p.get("message") or "")
    return f"{p.get('categorie', '?')}:{msg[:80]}"


def _sans_accents(x: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (x or "").lower()) if unicodedata.category(c) != "Mn")


MOTS_VIDES = set("""le la les un une des de du d l et ou a au aux en dans pour par sur avec ce cette ces
vous votre vos nous notre nos il elle ils on se sa son ses qui que quoi est sont etre avoir
pas ne y je tu me te mon ma mes ton ta tes leur leurs si mais donc car comme tout tous toute toutes""".split())


def expressions(texte: str) -> set[str]:
    mots = [m for m in re.findall(r"[a-z0-9€%!]+", _sans_accents(texte)) if len(m) > 2 and m not in MOTS_VIDES]
    return set(mots) | {f"{a} {b}" for a, b in zip(mots, mots[1:])}


# ── 1. Observer ──────────────────────────────────────────────────────────────
def _resultats(campaign_id) -> dict:
    return pg.ligne("""SELECT count(*) FILTER (WHERE submitted_at IS NOT NULL) AS envoyes,
                              count(*) FILTER (WHERE delivered_at IS NOT NULL) AS livres,
                              count(*) FILTER (WHERE opened_at IS NOT NULL) AS ouverts,
                              count(*) FILTER (WHERE clicked_at IS NOT NULL) AS clics,
                              count(*) FILTER (WHERE bounced_at IS NOT NULL AND
                                     (bounce_type ILIKE '%%hard%%' OR bounce_type ILIKE 'permanent%%')) AS rebonds_hard,
                              count(*) FILTER (WHERE complained_at IS NOT NULL) AS plaintes,
                              count(*) FILTER (WHERE unsubscribed_at IS NOT NULL) AS desinscriptions
                         FROM recipients WHERE campaign_id = %(c)s""", {"c": campaign_id}) or {}


def observer_espace(schema: str) -> int:
    n = 0
    with pg.espace(schema):
        camps = pg.lignes("""SELECT id, subject, preheader, html_storage_key FROM campaigns
                              WHERE started_at BETWEEN now() - interval '60 days' AND now() - interval '3 days'
                                AND html_storage_key IS NOT NULL""")
        for c in camps:
            try:
                html = stockage.lire(c["html_storage_key"]).decode("utf-8", "replace")
                a = controle_html.analyser(html, objet=c["subject"] or "", preheader=c["preheader"] or "",
                                           expediteur={"adresse_postale": "x"}, tester_liens=False)
            except Exception as e:  # noqa: BLE001 — une campagne illisible n'arrête pas l'agent
                print(f"[apprentissage] {schema}/{c['id']} illisible : {e}", flush=True)
                continue
            texte = re.sub(r"<[^>]+>", " ", html)
            # Les signalements de l'agent lui-même ne sont pas des caractéristiques du message.
            pbs = [p for p in a["problemes"] if p.get("categorie") != "Apprentissage"]
            carac = {"score": a["score"], "taille": a.get("taille_octets"), "nb_liens": a.get("nb_liens"),
                     "nb_images": a.get("nb_images"), "nb_caracteres": a.get("nb_caracteres_texte"),
                     "objet_long": len(c["subject"] or ""),
                     "problemes": sorted({cle_probleme(p) for p in pbs}),
                     "niveaux": {cle_probleme(p): p["niveau"] for p in pbs},
                     "libelles": {cle_probleme(p): p["message"][:160] for p in pbs},
                     "expressions": sorted(expressions(f"{c['subject'] or ''} {texte}"))[:3000]}
            res = _resultats(c["id"])
            with _plateforme():
                pg.ecrire("""INSERT INTO apprentissage_observations (schema_pg, campaign_id, caracteristiques, resultats)
                             VALUES (%(s)s, %(c)s, %(k)s::jsonb, %(r)s::jsonb)
                             ON CONFLICT (schema_pg, campaign_id) DO UPDATE SET caracteristiques = EXCLUDED.caracteristiques,
                                    resultats = EXCLUDED.resultats, observee_le = now()""",
                          {"s": schema, "c": c["id"], "k": json.dumps(carac), "r": json.dumps(res, default=int)})
            n += 1
    return n


def observer() -> int:
    total = observer_espace(pg.SCHEMA)
    for c in clients.lister():
        total += observer_espace(c["schema_pg"])
    return total


# ── 2. Apprendre ─────────────────────────────────────────────────────────────
def _taux(obs: list[dict]) -> tuple[float | None, float | None]:
    livres = sum(o["r"]["livres"] for o in obs)
    if not livres:
        return None, None
    neg = sum(o["r"]["rebonds_hard"] + o["r"]["plaintes"] + o["r"]["desinscriptions"] for o in obs)
    return neg / livres, sum(o["r"]["ouverts"] for o in obs) / livres


def apprendre() -> dict:
    with _plateforme():
        lignes = pg.lignes("SELECT caracteristiques AS k, resultats AS r FROM apprentissage_observations")
    obs = [o for o in lignes if int(o["r"].get("livres") or 0) >= MIN_LIVRES]
    if len(obs) < MIN_CAMPAGNES:
        return {"ajuste": False, "raison": f"{len(obs)} campagne(s) exploitable(s) sur {MIN_CAMPAGNES} nécessaires",
                "campagnes": len(obs)}
    neg_ref, ouv_ref = _taux(obs)
    niveaux, libelles = {}, {}
    for o in obs:
        niveaux.update(o["k"].get("niveaux") or {})
        libelles.update(o["k"].get("libelles") or {})
    changements = []
    for cle, niveau in niveaux.items():
        avec = [o for o in obs if cle in (o["k"].get("problemes") or [])]
        sans = [o for o in obs if cle not in (o["k"].get("problemes") or [])]
        with _plateforme():
            regle = pg.ligne("SELECT * FROM apprentissage_regles WHERE cle = %(c)s", {"c": cle})
        defaut = POIDS_DEFAUT.get(niveau, 0.0)
        poids = float(regle["poids"]) if regle else defaut
        neg_a, ouv_a = _taux(avec)
        neg_s, ouv_s = _taux(sans)
        nouveau = poids
        if len(avec) >= MIN_AVEC and len(sans) >= MIN_SANS and neg_a is not None and neg_s is not None:
            # Effet relatif : +100 % de réactions négatives ou −50 % d'ouvertures ≈ +1 sur l'échelle.
            effet_neg = (neg_a - neg_s) / max(neg_s, 0.002)
            effet_ouv = (ouv_s - ouv_a) / max(ouv_s, 0.01)
            effet = max(-1.0, min(2.0, 0.6 * effet_neg + 0.4 * 2 * effet_ouv))
            cible = max(0.0, min(25.0, (defaut if defaut else 3.0) * (1 + effet)))
            nouveau = poids + max(-PAS_MAX, min(PAS_MAX, cible - poids))
            if niveau == "bloquant":
                nouveau = max(PLANCHER_BLOQUANT, nouveau)
            nouveau = round(nouveau, 2)
            if abs(nouveau - poids) >= 0.01:
                changements.append({"cle": cle, "avant": poids, "apres": nouveau, "avec": len(avec), "sans": len(sans),
                                    "negatif_avec": round(neg_a, 4), "negatif_sans": round(neg_s, 4)})
        with _plateforme():
            pg.ecrire("""INSERT INTO apprentissage_regles (cle, niveau, libelle, poids_defaut, poids, n_avec, n_sans,
                                                          negatif_avec, negatif_sans, ouverture_avec, ouverture_sans, maj_le)
                         VALUES (%(c)s, %(n)s, %(l)s, %(d)s, %(p)s, %(na)s, %(ns)s, %(ga)s, %(gs)s, %(oa)s, %(os)s, now())
                         ON CONFLICT (cle) DO UPDATE SET poids = EXCLUDED.poids, n_avec = EXCLUDED.n_avec,
                              n_sans = EXCLUDED.n_sans, negatif_avec = EXCLUDED.negatif_avec,
                              negatif_sans = EXCLUDED.negatif_sans, ouverture_avec = EXCLUDED.ouverture_avec,
                              ouverture_sans = EXCLUDED.ouverture_sans, libelle = EXCLUDED.libelle, maj_le = now()""",
                      {"c": cle, "n": niveau, "l": libelles.get(cle, cle)[:200], "d": defaut, "p": nouveau,
                       "na": len(avec), "ns": len(sans), "ga": neg_a, "gs": neg_s, "oa": ouv_a, "os": ouv_s})
    mots = _apprendre_mots(obs, neg_ref)
    controle_html.oublier_apprentissage()
    return {"ajuste": True, "campagnes": len(obs), "negatif_ref": round(neg_ref or 0, 4),
            "ouverture_ref": round(ouv_ref or 0, 4), "changements": changements, "mots": mots}


def _apprendre_mots(obs: list[dict], neg_ref: float | None) -> list[str]:
    if not neg_ref:
        return []
    presence: dict[str, list[dict]] = defaultdict(list)
    for o in obs:
        for e in o["k"].get("expressions") or []:
            presence[e].append(o)
    frequents = Counter({e: len(v) for e, v in presence.items()})
    nouveaux = []
    for e, n in frequents.items():
        if n < 3 or n > 0.6 * len(obs):        # trop rare pour conclure, ou trop banal pour être un signal
            continue
        neg, _ = _taux(presence[e])
        if neg is None:
            continue
        statut = "a_surveiller" if neg >= 2 * neg_ref and neg - neg_ref >= 0.003 else "neutre"
        with _plateforme():
            avant = pg.valeur("SELECT statut FROM apprentissage_mots WHERE expression = %(e)s", {"e": e})
            pg.ecrire("""INSERT INTO apprentissage_mots (expression, n_campagnes, negatif, reference, statut, maj_le)
                         VALUES (%(e)s, %(n)s, %(g)s, %(r)s, %(s)s, now())
                         ON CONFLICT (expression) DO UPDATE SET n_campagnes = EXCLUDED.n_campagnes, negatif = EXCLUDED.negatif,
                              reference = EXCLUDED.reference, statut = EXCLUDED.statut, maj_le = now()""",
                      {"e": e, "n": n, "g": neg, "r": neg_ref, "s": statut})
        if statut == "a_surveiller" and avant != "a_surveiller":
            nouveaux.append(e)
    return nouveaux[:50]


# ── 3. Tour de nuit ──────────────────────────────────────────────────────────
def tourner(force: bool = False) -> dict:
    if date.today() > FIN and not force:
        return {"ok": False, "raison": f"période d'apprentissage terminée le {FIN.isoformat()}"}
    assurer_schema()
    debut = time.time()
    n = observer()
    r = apprendre()
    resume = (f"{n} campagne(s) observée(s) · "
              + (f"{len(r['changements'])} poids ajusté(s), {len(r['mots'])} expression(s) à surveiller"
                 if r.get("ajuste") else f"pas d'ajustement ({r['raison']})"))
    with _plateforme():
        pg.ecrire("INSERT INTO apprentissage_journal (resume, details) VALUES (%(r)s, %(d)s::jsonb)",
                  {"r": resume, "d": json.dumps({**r, "observees": n, "duree_s": round(time.time() - debut, 1)}, default=str)})
    return {"ok": True, "resume": resume, **r}


if __name__ == "__main__":
    print(json.dumps(tourner(force="--force" in sys.argv), ensure_ascii=False, indent=1, default=str))
