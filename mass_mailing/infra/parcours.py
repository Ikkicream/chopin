"""mass_mailing/infra/parcours.py — le parcours d'une liste, de la première ligne au clic humain.

Trois temps, dans l'esprit du guide délivrabilité 2026 et du cahier anti-bot de Camille
(.claude/skills/delivrabilite, .claude/skills/anti-bot-clics) :

    1. Préparation : lignes du fichier → adresses uniques → hors cible / désinscrits →
       vérifiées Mailnjoy → éligibles.
    2. Remise : envoyées → livrées (acceptées par la messagerie, ce qui ne prouve PAS la
       boîte de réception) ; rebonds, refus.
    3. Engagement : clics bruts → robots écartés → clics humains → visites de la page de
       rappel → réponses « oui ». Les ouvertures restent un indicateur secondaire (Apple
       préchargement, scanners) et celles des destinataires classés robots sont retirées.

Lecture seule. Chaque étape porte ses pertes, avec leur raison, pour que l'écran les dise en
toutes lettres au lieu de pourcentages à décoder.
"""
from __future__ import annotations

from infra import pg


def _n(v) -> int:
    return int(v or 0)


def calculer(campaign_id: str) -> dict:
    c = pg.ligne("SELECT target_version_id, audience FROM campaigns WHERE id = %(c)s", {"c": campaign_id})
    if not c or not c["target_version_id"]:
        return {"disponible": False}
    tv = pg.ligne("SELECT * FROM campaign_target_versions WHERE id = %(t)s", {"t": c["target_version_id"]})
    r = pg.ligne("""
        SELECT count(*) AS total,
               count(*) FILTER (WHERE eligibility_reason = 'hors_cible_b2c') AS hors_cible,
               count(*) FILTER (WHERE eligibility_reason = 'suppressed') AS desinscrits,
               count(*) FILTER (WHERE eligibility_reason = 'envoye_en_test') AS paliers,
               count(*) FILTER (WHERE validation_status NOT IN ('pending') AND import_status = 'imported') AS verifiees,
               count(*) FILTER (WHERE eligibility_status = 'eligible'
                                   OR eligibility_reason IN ('envoye_en_test')) AS eligibles,
               count(*) FILTER (WHERE eligibility_status = 'excluded' AND validation_status <> 'pending'
                                   AND COALESCE(eligibility_reason, '') NOT IN
                                       ('hors_cible_b2c', 'suppressed', 'envoye_en_test', 'report_fournisseur')) AS refus_mailnjoy,
               count(*) FILTER (WHERE send_status IN ('submitted', 'delivered', 'bounced')) AS envoyes,
               count(*) FILTER (WHERE delivered_at IS NOT NULL) AS livres,
               count(*) FILTER (WHERE bounced_at IS NOT NULL) AS rebonds,
               count(*) FILTER (WHERE send_status = 'failed') AS refus,
               count(*) FILTER (WHERE unsubscribed_at IS NOT NULL) AS desinscriptions
          FROM recipients WHERE target_version_id = %(t)s
    """, {"t": c["target_version_id"]})
    k = pg.ligne("""
        SELECT count(DISTINCT recipient_id) AS bruts,
               count(DISTINCT recipient_id) FILTER (WHERE verdict = 'humain') AS humains,
               count(DISTINCT recipient_id) FILTER (WHERE verdict = 'suspect') AS suspects,
               count(*) AS evenements
          FROM clicks WHERE campaign_id = %(c)s
    """, {"c": campaign_id})
    robots = pg.valeur("""SELECT count(*) FROM (SELECT recipient_id FROM clicks WHERE campaign_id = %(c)s
                           GROUP BY 1 HAVING bool_and(verdict = 'robot')) x""", {"c": campaign_id})
    o = pg.ligne("""
        SELECT count(*) FILTER (WHERE r.opened_at IS NOT NULL) AS brutes,
               count(*) FILTER (WHERE r.opened_at IS NOT NULL AND NOT EXISTS
                                (SELECT 1 FROM clicks k WHERE k.recipient_id = r.id AND k.verdict = 'robot')) AS probables
          FROM recipients r WHERE r.campaign_id = %(c)s
    """, {"c": campaign_id})
    rap = pg.ligne("""
        SELECT count(DISTINCT recipient_id) FILTER (WHERE action = 'visite') AS visites,
               count(DISTINCT recipient_id) FILTER (WHERE action = 'accepte') AS oui
          FROM rappels WHERE campaign_id = %(c)s AND NOT test AND recipient_id IS NOT NULL
    """, {"c": campaign_id})
    # Une visite de la page de rappel par un destinataire dont TOUS les clics sont robots
    # n'est pas une visite : c'est le scanner qui a suivi le lien.
    visites_robots = pg.valeur("""
        SELECT count(DISTINCT v.recipient_id) FROM rappels v
         WHERE v.campaign_id = %(c)s AND NOT v.test AND v.action = 'visite'
           AND v.recipient_id IN (SELECT recipient_id FROM clicks WHERE campaign_id = %(c)s
                                   GROUP BY 1 HAVING bool_and(verdict = 'robot'))""", {"c": campaign_id})
    # Fin du parcours (Camille, 27/09) : Livrés → Ouverts / Non ouverts / Désabonnés → Clics.
    # Partition exacte des livrés : désabonné d'abord ; sinon « ouvert » s'il a ouvert (hors
    # destinataires robots) OU cliqué pour de vrai ; sinon « non ouvert ». Clics = ouverts humains
    # qui ont cliqué.
    fin = pg.ligne("""
        WITH d AS (
            SELECT r.unsubscribed_at IS NOT NULL AS desabonne,
                   EXISTS (SELECT 1 FROM clicks k WHERE k.recipient_id = r.id AND k.verdict = 'humain') AS clic_humain,
                   (r.opened_at IS NOT NULL AND NOT EXISTS
                       (SELECT 1 FROM clicks k WHERE k.recipient_id = r.id AND k.verdict = 'robot')) AS ouverture
              FROM recipients r WHERE r.target_version_id = %(t)s AND r.delivered_at IS NOT NULL)
        SELECT count(*) FILTER (WHERE desabonne) AS desabonnes,
               count(*) FILTER (WHERE NOT desabonne AND (ouverture OR clic_humain)) AS ouverts,
               count(*) FILTER (WHERE NOT desabonne AND NOT ouverture AND NOT clic_humain) AS non_ouverts,
               count(*) FILTER (WHERE NOT desabonne AND clic_humain) AS clics
          FROM d""", {"t": c["target_version_id"]})
    rappel_actif = bool(pg.valeur("SELECT (rappel->>'actif')::boolean FROM campaigns WHERE id = %(c)s",
                                  {"c": campaign_id}))

    lignes, uniques = _n(tv["extracted_rows"]), _n(tv["unique_emails"])
    envoyes, livres = _n(r["envoyes"]), _n(r["livres"])
    return {
        "disponible": True,
        "public": c["audience"],
        "preparation": {
            "lignes": lignes, "doublons": _n(tv["duplicate_count"]), "invalides": _n(tv["invalid_syntax_count"]),
            "uniques": uniques, "hors_cible": _n(r["hors_cible"]), "desinscrits": _n(r["desinscrits"]),
            "verifiees": _n(r["verifiees"]), "eligibles": _n(r["eligibles"]),
            "refus_mailnjoy": _n(r["refus_mailnjoy"]),
            "paliers": _n(r["paliers"]),
        },
        "remise": {
            "envoyes": envoyes, "livres": livres, "rebonds": _n(r["rebonds"]), "refus": _n(r["refus"]),
            "en_attente": max(0, envoyes - livres - _n(r["rebonds"])),
        },
        "engagement": {
            "clics_bruts": _n(k["bruts"]), "robots": _n(robots), "suspects": _n(k["suspects"]),
            "humains": _n(k["humains"]), "evenements": _n(k["evenements"]),
            "ouvertures_brutes": _n(o["brutes"]), "ouvertures_probables": _n(o["probables"]),
            "rappel_actif": rappel_actif,
            "visites": max(0, _n(rap["visites"]) - _n(visites_robots)), "visites_robots": _n(visites_robots),
            "oui": _n(rap["oui"]), "desinscriptions": _n(r["desinscriptions"]),
            "fin": {"ouverts": _n(fin["ouverts"]), "non_ouverts": _n(fin["non_ouverts"]),
                    "desabonnes": _n(fin["desabonnes"]), "clics": _n(fin["clics"])},
        },
    }
