#!/usr/bin/env python3
"""mass_mailing/jobs/pilote.py — pilote de chauffe des campagnes routées (Camille, 26/11/2026).

« Je ne peux pas surveiller chaque campagne à la main. La croissance doit être exponentielle tant
que c'est sain, et c'est le système qui décide où envoyer. » Hall U Need A (23-26/11) : 10 mails
par vague pendant deux jours, parce que :
  1. les ouvertures Sweego n'étaient jamais classées (ni IP ni logiciel lus) : chaque grosse
     messagerie finissait en SONDE dès 50 livrés et n'en sortait jamais (corrigé dans placement) ;
  2. l'équilibre bornait les messageries saines sur une réserve gonflée par celles en sonde
     (corrigé dans routage.vague) ;
  3. rien ne faisait monter le volume d'une vague à l'autre : seul le débit appris bougeait, une
     fois par jour.

Deux rôles, appelés par routage.vague AVANT chaque vague, pour chaque messagerie :

  CONTRÔLEUR  juger()          fonction PURE — ce qui s'est passé depuis la dernière décision :
              VERT   sain                         → on accélère
              ORANGE alerte faible (freinage du fournisseur, rebonds 2-3 %) → on tient
              ROUGE  plainte nouvelle, rebonds > 3 % → on recule
              SONDE  spam probable (jobs/placement) → au moins SONDE_JOUR (20) mails par jour,
                     répartis sur les vagues restantes, pour continuer à mesurer. Une messagerie
                     n'est JAMAIS arrêtée par le pilote (Camille, 27/11/2026 : « minimum 20 emails
                     par jour, puis l'agent se débrouille seul »).
              REPRISE la sonde récente montre de vrais lecteurs (SORTIE_SIGNAUX signaux et
                     SORTIE_TAUX des livrés en sonde sur 7 j) → la messagerie sort de la sonde
                     d'elle-même et repart à DEPART, même si la mesure sur 7 j dit encore spam.
  PRODUCTEUR  palier_suivant() fonction PURE — mails par vague pour cette messagerie :
              VERT ×CROISSANCE (à partir de ce qui est vraiment parti), ORANGE =, ROUGE ×RECUL,
              SONDE : le reste du quota du jour divisé par les vagues restantes. Tant que la boîte de réception n'est pas PROUVÉE (placement
              « boîte probable »), le palier ne dépasse pas PALIER_SANS_PREUVE : on n'accélère
              franchement que quand de vraies personnes lisent.

Le volume final reste borné par la capacité (débit/h et plafond du jour de jobs/capacite, qui
montent d'un jour à l'autre) et par la part max par domaine (routage.plafond_domaine).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import pg  # noqa: E402
from jobs import capacite, placement  # noqa: E402

DEPART = 5                  # mails par messagerie à la première vague (ou en sortie de sonde)
CROISSANCE = 1.5            # ×1,5 par vague saine : 5, 8, 12, 18, 27, 41, 62, 93…
RECUL = 0.5
SONDE = 2                   # sonde minimale d'une vague (sans pilote : routage.SONDE)
SONDE_JOUR = 20             # mails par jour, au minimum, vers une messagerie en sonde (Camille, 27/11)
PALIER_SANS_PREUVE = 25     # plafond du palier tant que la boîte de réception n'est pas prouvée
SORTIE_SIGNAUX = 2          # sortie de sonde : au moins 2 vrais signaux…
SORTIE_TAUX = 0.03          # … et 3 % des livrés en sonde sur 7 jours
SONDE_MAX = 60              # au-delà, une sonde sans un seul signal est « persistante » (motif seulement)
REBONDS_ROUGE = 0.03
REBONDS_ORANGE = 0.02
MIN_POUR_TAUX = 20          # sous 20 envois, un taux de rebond ne veut rien dire
VERT, ORANGE, ROUGE, EN_SONDE, STOP = "vert", "orange", "rouge", "sonde", "stop"
# STOP n'est plus jamais rendu (27/11) ; la constante reste pour lire les décisions anciennes.

SCHEMA = """
CREATE TABLE IF NOT EXISTS routage_paliers (
    campaign_id   UUID        NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    groupe        TEXT        NOT NULL,
    palier        INT         NOT NULL,
    verdict       TEXT        NOT NULL,
    motif         TEXT,
    plaintes_vues INT         NOT NULL DEFAULT 0,
    maj           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (campaign_id, groupe)
)
"""


# ── Contrôleur ───────────────────────────────────────────────────────────────

def juger(placement_etat: str | None, envoyes: int, rebonds: int, nouvelles_plaintes: int, frein: bool,
          sonde_livres: int = 0, sonde_signaux: int = 0) -> tuple[str, str]:
    """Fonction PURE. envoyes / rebonds : messagerie, campagne, 48 dernières heures (rebonds DÉFINITIFS).
    nouvelles_plaintes : plaintes jamais encore jugées. frein : le fournisseur a freiné (4xx, report)
    depuis la dernière décision. sonde_* : livrés et signaux (ouverture humaine, Apple, clic) depuis
    l'entrée en spam probable."""
    taux = rebonds / envoyes if envoyes else 0.0
    if nouvelles_plaintes:
        return ROUGE, f"{nouvelles_plaintes} nouvelle(s) plainte(s)"
    if envoyes >= MIN_POUR_TAUX and taux > REBONDS_ROUGE:
        return ROUGE, f"rebonds définitifs {taux:.1%} sur {envoyes} envois (48 h)"
    if placement_etat == placement.SPAM:
        if sonde_signaux >= SORTIE_SIGNAUX and sonde_livres and sonde_signaux / sonde_livres >= SORTIE_TAUX:
            return VERT, (f"reprise : {sonde_signaux} vrais signaux sur {sonde_livres} livrés en sonde "
                          f"({sonde_signaux / sonde_livres:.1%}) — on sort de la sonde et on repart petit")
        if sonde_livres >= SONDE_MAX and sonde_signaux == 0:
            return EN_SONDE, (f"spam persistant : 0 signal sur {sonde_livres} livrés en sonde — on garde "
                              f"{SONDE_JOUR} mails/jour pour voir quand ça revient")
        return EN_SONDE, f"spam probable — sonde : {sonde_signaux} signal(aux) sur {sonde_livres} livrés"
    if frein:
        return ORANGE, "le fournisseur a freiné (réponses 4xx ou reports)"
    if envoyes >= MIN_POUR_TAUX and taux > REBONDS_ORANGE:
        return ORANGE, f"rebonds définitifs {taux:.1%} sur {envoyes} envois (48 h)"
    return VERT, f"sain : rebonds {taux:.1%} sur {envoyes} envois (48 h), aucune plainte, aucun freinage"


# ── Producteur ───────────────────────────────────────────────────────────────

def sonde_par_vague(deja_aujourdhui: int, vagues_restantes: int) -> int:
    """Fonction PURE : ce qu'une messagerie en sonde reçoit à cette vague pour atteindre SONDE_JOUR
    dans la journée (reste du quota ÷ vagues restantes, arrondi au-dessus)."""
    reste = max(0, SONDE_JOUR - deja_aujourdhui)
    return math.ceil(reste / max(1, vagues_restantes)) if reste else 0


def palier_suivant(palier: int | None, parti: int | None, verdict: str, avant: str | None,
                   boite_prouvee: bool, deja_aujourdhui: int = 0, vagues_restantes: int = 14) -> int:
    """Fonction PURE. palier : décision précédente (None = première vague) ; parti : mails vraiment
    partis à la dernière vague de cette messagerie ; avant : verdict précédent ; deja_aujourdhui :
    mails partis aujourd'hui vers cette messagerie (campagne) ; vagues_restantes : y compris celle-ci."""
    if verdict in (EN_SONDE, STOP):
        return sonde_par_vague(deja_aujourdhui, vagues_restantes)
    if verdict == ROUGE:
        return max(SONDE, int((palier or DEPART) * RECUL))
    if palier is None or avant in (EN_SONDE, STOP):
        return DEPART                      # première vague, ou sortie de sonde : on repart petit
    if verdict == ORANGE:
        return palier
    # VERT : on accélère à partir de ce qui est réellement parti (une vague bornée par la capacité ou
    # par la réserve ne doit pas faire grimper un palier fictif).
    base = palier if parti is None else max(min(palier, parti), DEPART)
    nouveau = max(base + 1, math.ceil(base * CROISSANCE))
    return nouveau if boite_prouvee else min(nouveau, max(PALIER_SANS_PREUVE, palier))


# ── Mesures (base) ───────────────────────────────────────────────────────────

def _mesures(campaign_id: str, identite: str) -> dict[str, dict]:
    """Par messagerie, pour CETTE campagne : envois et rebonds définitifs sur 48 h, plaintes au total,
    derniers partis, livrés et signaux depuis l'entrée en spam probable."""
    entree = {x["groupe"]: x["at"] for x in pg.lignes(
        "SELECT groupe, at FROM placement_etats WHERE identite = %(i)s AND etat = %(e)s", {"i": identite, "e": placement.SPAM})}
    signaux = placement.verdicts_ouverture(identite, min(entree.values()) if entree else None)
    depuis_7j = pg.valeur("SELECT now() - interval '7 days'")
    out: dict[str, dict] = {}
    for x in pg.lignes("""
        SELECT r.id, split_part(r.email_normalized, '@', 2) AS d, r.submitted_at, r.delivered_at,
               r.submitted_at > now() - interval '48 hours' AS recent,
               (r.submitted_at AT TIME ZONE 'Europe/Paris')::date = (now() AT TIME ZONE 'Europe/Paris')::date AS aujourdhui,
               r.send_status = 'bounced' AND COALESCE(r.bounce_type, '') !~* '^(transient|undetermined)' AS rebond,
               r.complained_at IS NOT NULL AS plainte,
               EXISTS (SELECT 1 FROM clicks k WHERE k.recipient_id = r.id AND k.verdict = 'humain' AND k.type_lien = 'contenu') AS clic
          FROM recipients r WHERE r.campaign_id = %(c)s AND r.submitted_at IS NOT NULL""", {"c": campaign_id}):
        g = capacite.groupe_de(x["d"])
        s = out.setdefault(g, {"envoyes": 0, "rebonds": 0, "plaintes": 0, "sonde_livres": 0, "sonde_signaux": 0, "aujourdhui": 0})
        s["aujourdhui"] += int(x["aujourdhui"])
        s["envoyes"] += int(x["recent"])
        s["rebonds"] += int(x["recent"] and x["rebond"])
        s["plaintes"] += int(x["plainte"])
        if g in entree and x["delivered_at"] and x["delivered_at"] >= max(entree[g], depuis_7j):
            s["sonde_livres"] += 1
            s["sonde_signaux"] += int(x["clic"] or signaux.get(x["id"]) in ("humain", "apple"))
    for x in pg.lignes("""SELECT DISTINCT ON (groupe) groupe, volume FROM routage_vagues
                           WHERE campaign_id = %(c)s ORDER BY groupe, numero DESC""", {"c": campaign_id}):
        out.setdefault(x["groupe"], {"envoyes": 0, "rebonds": 0, "plaintes": 0, "sonde_livres": 0, "sonde_signaux": 0, "aujourdhui": 0})
        out[x["groupe"]]["parti"] = x["volume"]
    return out


def _freins(identite: str, depuis: dict[str, object]) -> set[str]:
    """Messageries que le fournisseur a freinées (jobs/capacite : réduire / suspendre) depuis la
    dernière décision du pilote (6 h si aucune)."""
    out = set()
    for x in pg.lignes("""SELECT cle, max(at) AS at FROM capacite_decisions
                           WHERE cle LIKE %(p)s AND decision IN ('reduire', 'suspendre') AND at > now() - interval '6 hours'
                           GROUP BY cle""", {"p": "%|" + identite + "|market|%"}):
        g = x["cle"].rsplit("|", 1)[-1]
        if depuis.get(g) is None or x["at"] > depuis[g]:
            out.add(g)
    return out


def piloter(campaign_id: str, identite: str, placements: dict[str, dict], groupes: list[str]) -> dict[str, dict]:
    """Contrôle puis production, pour chaque messagerie de la réserve. Écrit la décision, journalise
    chaque changement de verdict. Renvoie {groupe: {palier, verdict, motif}}."""
    from jobs import envoi
    pg.ecrire(SCHEMA)
    avant = {x["groupe"]: x for x in pg.lignes("SELECT * FROM routage_paliers WHERE campaign_id = %(c)s", {"c": campaign_id})}
    mes = _mesures(campaign_id, identite)
    freins = _freins(identite, {g: x["maj"] for g, x in avant.items()})
    from datetime import datetime
    from zoneinfo import ZoneInfo
    heure = datetime.now(ZoneInfo("Europe/Paris")).hour
    vagues_restantes = max(1, capacite.FENETRE_ENVOI[1] - heure)
    out = {}
    for g in groupes:
        m = mes.get(g) or {"envoyes": 0, "rebonds": 0, "plaintes": 0, "sonde_livres": 0, "sonde_signaux": 0, "aujourdhui": 0}
        a = avant.get(g) or {}
        etat_pl = (placements.get(g) or {}).get("etat")
        nouvelles = max(0, m["plaintes"] - int(a.get("plaintes_vues") or 0))
        verdict, motif = juger(etat_pl, m["envoyes"], m["rebonds"], nouvelles, g in freins, m["sonde_livres"], m["sonde_signaux"])
        palier = palier_suivant(a.get("palier"), m.get("parti"), verdict, a.get("verdict"), etat_pl == placement.BOITE,
                                m.get("aujourdhui", 0), vagues_restantes)
        pg.ecrire("""INSERT INTO routage_paliers (campaign_id, groupe, palier, verdict, motif, plaintes_vues, maj)
                     VALUES (%(c)s, %(g)s, %(p)s, %(v)s, %(m)s, %(pl)s, now())
                     ON CONFLICT (campaign_id, groupe) DO UPDATE SET palier = EXCLUDED.palier, verdict = EXCLUDED.verdict,
                            motif = EXCLUDED.motif, plaintes_vues = EXCLUDED.plaintes_vues, maj = now()""",
                  {"c": campaign_id, "g": g, "p": palier, "v": verdict, "m": motif, "pl": m["plaintes"]})
        if verdict != a.get("verdict") or (verdict == VERT and motif.startswith("reprise") and not (a.get("motif") or "").startswith("reprise")):
            with pg.connexion() as cur:
                envoi._audit(cur, campaign_id, "worker", "routage", "routage.pilote",
                             f"{capacite.NOMS.get(g, g)} : {verdict.upper()} — {motif} → {palier} mail(s) par vague")
        out[g] = {"palier": palier, "verdict": verdict, "motif": motif}
    return out
