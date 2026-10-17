"""mass_mailing/infra/domaines.py — le domaine d'une adresse dit-il « particulier » ou « organisation » ?

Consigne de Camille (2026-09-26, après un envoi B2C parti chez bnpparibas.com et
ville-valenciennes.fr) : « je ne veux pas voir d'email envoyé à des sociétés si B2C ».

    classer(domaine)            'grand_public' | 'entreprise' | 'administration'
    hors_cible(email, public)   raison d'exclusion, ou None si l'adresse est dans la cible

Règle : un domaine est GRAND PUBLIC s'il appartient à une messagerie ou à un fournisseur
d'accès ouvert aux particuliers (liste ci-dessous) ; tout autre domaine est celui d'une
organisation. Les règles de Camille (`settings.domain_rules`, écran « Règles de domaines »)
passent avant : {"grand_public": [...], "entreprise": [...]}.

- Campagne **B2C** : toute adresse d'organisation est écartée (`hors_cible_b2c`).
- Campagne **B2B** : rien n'est écarté ; les adresses grand public sont seulement comptées
  (un artisan écrit souvent depuis Gmail).
"""
from __future__ import annotations

import re

from infra import pg

# Messageries et fournisseurs d'accès grand public (France d'abord, puis international).
GRAND_PUBLIC = frozenset("""
gmail.com googlemail.com
hotmail.fr hotmail.com hotmail.be hotmail.ch hotmail.co.uk hotmail.it hotmail.es hotmail.de
live.fr live.com live.be live.ca live.co.uk live.it msn.com windowslive.com passport.com
outlook.fr outlook.com outlook.be outlook.es outlook.it outlook.de
yahoo.fr yahoo.com yahoo.co.uk yahoo.es yahoo.it yahoo.de yahoo.be yahoo.ca ymail.com rocketmail.com
aol.com aol.fr icloud.com me.com mac.com privaterelay.appleid.com
orange.fr wanadoo.fr voila.fr free.fr aliceadsl.fr libertysurf.fr online.fr
sfr.fr neuf.fr cegetel.net club-internet.fr noos.fr numericable.fr numericable.com bbox.fr
laposte.net tiscali.fr 9online.fr nordnet.fr calixo.net estvideo.fr akeonet.com
gmx.fr gmx.com gmx.net gmx.de web.de t-online.de
netcourrier.com dbmail.com mailo.com caramail.com
protonmail.com protonmail.ch proton.me pm.me tutanota.com tuta.io mail.com yandex.com yandex.ru
skynet.be telenet.be scarlet.be bluewin.ch sunrise.ch videotron.ca sympatico.ca
libero.it tiscali.it virgilio.it
""".split())

# Organisations publiques reconnaissables au nom de domaine.
# (Affichage seulement : en B2C, administration et entreprise sont écartées pareil.)
_ADMINISTRATION = re.compile(
    r"(\.gouv\.fr$|\.gouv$|\.asso\.fr$|^(ville|mairie|commune|agglo|departement|region|cc|ca|cu|cd|ac|chu|ch)[-.]"
    r"|^(mairie|ville)|^univ-|^uphf\.|^u-|agglo|metropole|departement|region|lez|les-bains)")


def regles() -> dict:
    try:
        r = pg.valeur("SELECT domain_rules FROM settings") or {}
    except Exception:  # noqa: BLE001 — colonne absente sur une base pas encore migrée
        r = {}
    return {"grand_public": sorted({d.strip().lower() for d in r.get("grand_public") or [] if d.strip()}),
            "entreprise": sorted({d.strip().lower() for d in r.get("entreprise") or [] if d.strip()})}


def classer(domaine: str, r: dict | None = None) -> str:
    d = (domaine or "").strip().lower()
    r = r if r is not None else regles()
    if d in r["entreprise"]:
        return "entreprise"
    if d in r["grand_public"] or d in GRAND_PUBLIC:
        return "grand_public"
    return "administration" if _ADMINISTRATION.search(d) else "entreprise"


def hors_cible(email: str, public: str | None, r: dict | None = None) -> str | None:
    """Raison d'exclusion (`hors_cible_b2c`) si l'adresse n'a rien à faire dans la cible."""
    if public != "b2c":
        return None
    return None if classer(email.rsplit("@", 1)[-1], r) == "grand_public" else "hors_cible_b2c"


def reevaluer(campaign_id: str) -> dict:
    """Applique le public de la campagne à sa cible actuelle, adresses pas encore parties.

    - hors cible et encore « pending » ou « eligible » → exclue (`hors_cible_b2c`) ;
    - exclue pour `hors_cible_b2c` mais de nouveau dans la cible (public ou règle changés)
      → remise en « pending » SI la liste n'est pas encore partie au nettoyage Mailnjoy
      (sinon elle n'aurait pas de verdict : elle reste exclue, il faut réimporter).
    """
    c = pg.ligne("SELECT audience, target_version_id FROM campaigns WHERE id = %(c)s", {"c": campaign_id})
    if not c or not c["target_version_id"]:
        return {"exclues": 0, "reintegrees": 0}
    r = regles()
    lignes = pg.lignes("""SELECT id, email_normalized, eligibility_status, eligibility_reason, validation_status
                            FROM recipients WHERE target_version_id = %(t)s AND submitted_at IS NULL
                             AND send_status IN ('pending', 'queued')""", {"t": c["target_version_id"]})
    exclure = [x["id"] for x in lignes if x["eligibility_status"] in ("pending", "eligible")
               and hors_cible(x["email_normalized"], c["audience"], r)]
    reintegrer = [x["id"] for x in lignes if x["eligibility_reason"] == "hors_cible_b2c"
                  and x["validation_status"] == "pending"
                  and not hors_cible(x["email_normalized"], c["audience"], r)]
    if exclure:
        pg.ecrire("""UPDATE recipients SET eligibility_status = 'excluded', eligibility_reason = 'hors_cible_b2c',
                            send_status = CASE WHEN send_status = 'queued' THEN 'skipped' ELSE send_status END,
                            updated_at = now() WHERE id = ANY(%(i)s)""", {"i": exclure})
    if reintegrer:
        pg.ecrire("""UPDATE recipients SET eligibility_status = 'pending', eligibility_reason = NULL, updated_at = now()
                      WHERE id = ANY(%(i)s)""", {"i": reintegrer})
    # Le compteur « à valider » de la cible suit (il décide du statut ready_for_validation).
    pg.ecrire("""UPDATE campaign_target_versions tv SET validation_eligible_count =
                        (SELECT count(*) FROM recipients r WHERE r.target_version_id = tv.id
                            AND r.eligibility_status = 'pending' AND r.import_status = 'imported')
                  WHERE tv.id = %(t)s""", {"t": c["target_version_id"]})
    return {"exclues": len(exclure), "reintegrees": len(reintegrer)}


def repartition(campaign_id: str) -> dict:
    """Domaines de la cible actuelle, classés, avec le nombre d'adresses (écran de contrôle)."""
    c = pg.ligne("SELECT audience, target_version_id FROM campaigns WHERE id = %(c)s", {"c": campaign_id})
    if not c or not c["target_version_id"]:
        return {"public": c and c["audience"], "domaines": [], "totaux": {}}
    r = regles()
    lignes = pg.lignes("""SELECT split_part(email_normalized, '@', 2) AS domaine, count(*) AS n,
                                 count(*) FILTER (WHERE eligibility_reason = 'hors_cible_b2c') AS ecartees,
                                 count(*) FILTER (WHERE submitted_at IS NOT NULL) AS parties
                            FROM recipients r
                           WHERE target_version_id = %(t)s

                           GROUP BY 1 ORDER BY 2 DESC, 1""", {"t": c["target_version_id"]})
    # Adresses parties dans une AUTRE campagne (paliers de test dupliqués) : même personne.
    ailleurs = {x["domaine"]: x["n"] for x in pg.lignes(
        """SELECT split_part(r.email_normalized, '@', 2) AS domaine, count(DISTINCT r.email_normalized) AS n
             FROM recipients r JOIN recipients x ON x.email_normalized = r.email_normalized
                                                AND x.campaign_id <> r.campaign_id AND x.submitted_at IS NOT NULL
            WHERE r.target_version_id = %(t)s GROUP BY 1""", {"t": c["target_version_id"]})}
    domaines, totaux = [], {"grand_public": 0, "entreprise": 0, "administration": 0}
    for x in lignes:
        k = classer(x["domaine"], r)
        totaux[k] += x["n"]
        domaines.append({"domaine": x["domaine"], "n": x["n"], "classe": k, "ecartees": x["ecartees"],
                         "parties": x["parties"] + ailleurs.get(x["domaine"], 0),
                         "regle": "grand_public" if x["domaine"] in r["grand_public"]
                                  else "entreprise" if x["domaine"] in r["entreprise"] else None})
    return {"public": c["audience"], "domaines": domaines, "totaux": totaux,
            "ecartees": sum(x["ecartees"] for x in domaines),
            # Adresses d'organisation qui ont DÉJÀ reçu le mail (avant ce contrôle, ou en B2B).
            "orgas_parties": sum(x["parties"] for x in domaines if x["classe"] != "grand_public")}
