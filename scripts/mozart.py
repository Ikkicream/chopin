#!/usr/bin/env python3
"""mozart.py — le moteur des scénarios d'automatisation d'emails.

Un scénario est un GRAPHE, celui que l'éditeur visuel manipule : des nœuds reliés par des
liens. Il est stocké tel quel — le même objet des deux côtés, donc rien à traduire et rien
à désynchroniser.

Quatre types de nœuds, volontairement quatre et pas douze : un éditeur qui propose trente
briques produit des scénarios que personne ne relit.

  ┌─ déclencheur ─┐   qui entre, et à quelle condition
  ├─ délai ───────┤   on attend
  ├─ email ───────┤   on écrit
  └─ condition ───┘   a-t-il ouvert ? cliqué ? rien ? → deux sorties

**Ce moteur n'a AUCUN privilège.** Tout email qu'il envoie passe par le même chemin que
les campagnes : affinité d'expéditeur, plafond journalier par boîte, boîtes au repos,
garde-fou des variables, et surtout la fenêtre de 120 jours. Un scénario qui pourrait
écrire à quelqu'un qu'une campagne s'interdit d'écrire serait une porte dérobée dans la
règle la plus coûteuse de la plateforme.

Deux garanties d'exécution, contre les deux façons de se tromper en boucle :
  - **un contact n'entre qu'une fois** dans un scénario donné (contrainte d'unicité en
    base) — sinon un déclencheur réévalué toutes les heures le réinscrit à chaque passage ;
  - **chaque pas est journalisé** dans `mozart_passages`, en ajout seul. Les statistiques
    se relisent, elles ne s'incrémentent pas : un compteur se perd, un journal se relit.

Usage :
    python3 scripts/mozart.py etat            # ce qui est en cours
    python3 scripts/mozart.py tick --dry-run  # ce que le prochain passage ferait
    python3 scripts/mozart.py tick
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

TYPES_NOEUDS = ("declencheur", "delai", "email", "condition", "fin")

# Un scénario ne joue jamais plus de pas que ça en un passage pour un même contact. Un
# graphe mal fait — un délai de zéro qui boucle sur lui-même — tournerait sinon à l'infini
# en envoyant un email à chaque tour.
MAX_PAS_PAR_PASSAGE = 20

# ── La fenêtre d'envoi des scénarios ─────────────────────────────────────────
# Demande de Camille (2026-08-24) : aucun email le dimanche, et rien entre 18h30 et 9h01,
# heure de Paris. Elle est PLUS ÉTROITE que celle des campagnes (08:01–17:59, cf.
# `deliverability_agent`) et c'est délibéré : un scénario part tout seul, à l'heure où un
# contact atteint son nœud. Personne ne le regarde partir. Mieux vaut donc qu'il vise le
# cœur de la journée de bureau plutôt que ses bords.
#
# L'heure est TOUJOURS calculée en Europe/Paris, jamais en heure serveur : le serveur vit
# en UTC, et en été un envoi « à 18h00 » y serait déclenché à 20h00 chez le destinataire.
FENETRE_JOURS = (0, 1, 2, 3, 4, 5)     # lundi → samedi
FENETRE_DEBUT = "09:01"
FENETRE_FIN = "18:30"
FUSEAU = "Europe/Paris"


def maintenant_paris():
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        return _dt.now(ZoneInfo(FUSEAU))
    except Exception:  # noqa: BLE001
        return _dt.now(timezone.utc)


def fenetre_ouverte(quand=None) -> tuple[bool, str]:
    """Peut-on envoyer maintenant ? → (oui/non, motif lisible du refus).

    Le motif est rendu pour être affiché tel quel : « reporté — dimanche » se comprend,
    « False » ne se comprend pas.
    """
    q = quand or maintenant_paris()
    if q.weekday() not in FENETRE_JOURS:
        return False, "dimanche — aucun envoi ce jour"
    hhmm = q.strftime("%H:%M")
    if hhmm < FENETRE_DEBUT:
        return False, f"trop tôt — les envois reprennent à {FENETRE_DEBUT} (il est {hhmm} à Paris)"
    if hhmm > FENETRE_FIN:
        return False, f"trop tard — plus d'envoi après {FENETRE_FIN} (il est {hhmm} à Paris)"
    return True, ""


def prochaine_ouverture(quand=None):
    """Le prochain instant où la fenêtre sera ouverte. Sert à REPORTER proprement.

    Sans lui, un contact bloqué à 18h31 serait réessayé toutes les heures toute la nuit :
    onze passages pour rien, onze lignes de journal, et la vraie tentative noyée dedans.
    """
    from datetime import time as _time
    q = quand or maintenant_paris()
    h, m = (int(x) for x in FENETRE_DEBUT.split(":"))
    candidat = q.replace(hour=h, minute=m, second=0, microsecond=0)
    if q.strftime("%H:%M") >= FENETRE_DEBUT:
        candidat = candidat + timedelta(days=1)
    while candidat.weekday() not in FENETRE_JOURS:
        candidat = candidat + timedelta(days=1)
    return candidat


SCHEMA = BASE_DIR / "scripts" / "mozart_schema.sql"


def assurer_schema() -> bool:
    """Applique le schéma s'il manque. Idempotent — tout est en `IF NOT EXISTS`.

    Les trois tables et la contrainte d'unicité dont dépend `ON CONFLICT` n'existaient que
    dans la base vivante, créées à la main : une restauration ou une base reconstruite —
    et la migration PostgreSQL est en cours — aurait fait échouer chaque route Mozart avec
    « no unique or exclusion constraint matching the ON CONFLICT specification ».
    Le schéma vit désormais dans le dépôt, et s'applique tout seul.
    """
    import pool_pg
    c = pool_pg._conn()
    try:
        with c.cursor() as cur:
            cur.execute(SCHEMA.read_text())
        c.commit()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[mozart] schéma non appliqué ({type(e).__name__}: {e})", flush=True)
        return False
    finally:
        pool_pg._rendre(c)


def _q(sql: str, params=None) -> list[tuple]:
    import pool_pg
    return pool_pg._q(sql, params or {})


def _ecrire(sql: str, params=None) -> int:
    import pool_pg
    return pool_pg._ecrire(sql, params)


# ── Lecture du graphe ─────────────────────────────────────────────────────────
def _graphe(scenario: dict) -> tuple[dict, list]:
    g = scenario.get("graphe") or {}
    noeuds = {n["id"]: n for n in (g.get("nodes") or [])}
    liens = g.get("edges") or []
    return noeuds, liens


def _suivant(liens: list, noeud_id: str, sortie: str | None = None) -> str | None:
    """Le nœud d'après. `sortie` distingue les deux branches d'une condition.

    React Flow nomme la poignée de sortie `sourceHandle` ; une condition en a deux, « oui »
    et « non ». Un lien sans poignée sert de branche par défaut, ce qui rend un graphe
    incomplet inoffensif : on s'arrête au lieu de partir au hasard.
    """
    candidats = [l for l in liens if l.get("source") == noeud_id]
    if sortie is not None:
        exact = [l for l in candidats if (l.get("sourceHandle") or "") == sortie]
        if exact:
            return exact[0].get("target")
        return None
    return candidats[0].get("target") if candidats else None


_COLONNES = """id, site_code, nom, description, statut, graphe, cree_le, modifie_le,
               est_modele, verrouille, suivi_ouverture"""


def _ligne(x) -> dict:
    return {"id": str(x[0]), "site_code": x[1], "nom": x[2], "description": x[3],
            "statut": x[4], "graphe": x[5], "cree_le": str(x[6]), "modifie_le": str(x[7]),
            "est_modele": bool(x[8]), "verrouille": bool(x[9]),
            # Ajouter une colonne à `_COLONNES` sans l'ajouter ICI la rend invisible :
            # elle est bien lue, mais jamais rendue. Les deux listes vont ensemble.
            "suivi_ouverture": bool(x[10])}


def scenarios(site: str, statut: str | None = None) -> list[dict]:
    cond = " AND statut = %(st)s" if statut else ""
    # Les modèles d'abord : ce sont eux qu'on cherche quand on arrive sur une liste vide.
    return [_ligne(r) for r in _q(
        f"""SELECT {_COLONNES} FROM mozart_scenarios
            WHERE site_code = %(site)s{cond}
            ORDER BY est_modele DESC, modifie_le DESC""",
        {"site": site, "st": statut})]


def scenario(sid: str) -> dict | None:
    r = _q(f"SELECT {_COLONNES} FROM mozart_scenarios WHERE id = %(id)s", {"id": sid})
    return _ligne(r[0]) if r else None


def dupliquer(sid: str, nom: str | None = None, par: str = "") -> dict | None:
    """Copie un scénario dans un nouveau brouillon, déverrouillé.

    C'est la seule façon de partir d'un modèle : on ne « déverrouille » pas un modèle pour
    le modifier, on en fait une copie. Le modèle reste ce qu'il était pour la fois
    suivante — et pour tous les autres.

    Le graphe est copié tel quel : mêmes nœuds, mêmes liens, mêmes identifiants internes.
    Ils n'ont besoin d'être uniques qu'à l'intérieur d'un scénario.
    """
    src = scenario(sid)
    if not src:
        return None
    import pool_pg
    c = pool_pg._conn()
    try:
        with c.cursor() as cur:
            cur.execute("""
                INSERT INTO mozart_scenarios (site_code, nom, description, statut, graphe,
                                              cree_par, est_modele, verrouille)
                VALUES (%s, %s, %s, 'brouillon', %s::jsonb, %s, false, false)
                RETURNING id""",
                (src["site_code"], (nom or f"{src['nom']} (copie)")[:120],
                 src.get("description"), json.dumps(src.get("graphe") or {}), par))
            neuf = str(cur.fetchone()[0])
        c.commit()
    finally:
        pool_pg._rendre(c)
    return scenario(neuf)


# ── Contrôle d'un graphe avant activation ─────────────────────────────────────
def verifier(graphe: dict) -> list[str]:
    """Ce qui empêche un scénario de partir. Vide = il peut être activé.

    Contrôlé à l'ACTIVATION et pas seulement à l'exécution : un scénario qui s'arrête au
    premier contact parce qu'il lui manque un message est découvert trop tard, quand les
    gens sont déjà dedans.
    """
    noeuds = {n["id"]: n for n in (graphe.get("nodes") or [])}
    liens = graphe.get("edges") or []
    pbs: list[str] = []

    declencheurs = [n for n in noeuds.values() if n.get("type") == "declencheur"]
    if not declencheurs:
        pbs.append("aucun déclencheur : personne n'entrerait dans le scénario")
    elif len(declencheurs) > 1:
        pbs.append(f"{len(declencheurs)} déclencheurs — il en faut exactement un")

    for n in noeuds.values():
        t = n.get("type")
        d = n.get("data") or {}
        etiquette = d.get("nom") or n.get("id")
        if t == "email" and not d.get("message_id"):
            pbs.append(f"l'email « {etiquette} » n'a pas de message choisi")
        if t == "email" and (d.get("canal") or "maildoso") not in CANAUX_AUTORISES:
            pbs.append(f"l'email « {etiquette} » utilise le canal "
                       f"« {d.get('canal')} », qu'un scénario ne sait pas jouer — "
                       f"seuls {' et '.join(CANAUX_AUTORISES)} fonctionnent contact "
                       f"par contact")
        if t == "delai":
            try:
                if float(d.get("duree") or 0) <= 0:
                    pbs.append(f"le délai « {etiquette} » vaut zéro — le scénario "
                               f"tournerait sans jamais attendre")
            except (TypeError, ValueError):
                pbs.append(f"le délai « {etiquette} » n'est pas un nombre")
        if t == "condition":
            sorties = {(l.get("sourceHandle") or "") for l in liens
                       if l.get("source") == n["id"]}
            if not ({"oui", "non"} & sorties):
                pbs.append(f"la condition « {etiquette} » n'a aucune branche reliée")
        # Un déclencheur ou un délai qui ne mène nulle part est une faute : le parcours
        # s'arrête sans avoir rien fait. Un EMAIL terminal, lui, est une fin légitime —
        # le message part, le scénario se termine. La condition d'origine
        # (`if t != "email" or True`) était toujours vraie et bloquait donc l'activation
        # de tout scénario finissant par un envoi.
        if t in ("declencheur", "delai") and not _suivant(liens, n["id"]):
            pbs.append(f"« {etiquette} » ne mène nulle part")
    return pbs


# ── Inscription : qui entre dans le scénario ──────────────────────────────────
def _candidats(site: str, declencheur: dict, limite: int = 500) -> list[tuple]:
    """Les contacts que le déclencheur fait entrer.

    Un seul événement pour l'instant — « nouveau contact » — et c'est volontaire : le
    reste (a ouvert, a cliqué, a changé d'état) se construit sur la même mécanique, mais
    un premier scénario doit pouvoir se lire en entier avant qu'on en ajoute.
    """
    d = declencheur.get("data") or {}
    jours = int(d.get("depuis_jours") or 7)
    secteurs = [s for s in (d.get("secteurs") or []) if s]

    cond_secteur = " AND ct.sectors && %(secteurs)s" if secteurs else ""
    return _q(f"""
        SELECT ct.id, lower(ct.email::text), ct.prenom, ct.nom, ct.societe, ct.city
        FROM contacts ct
        JOIN contact_sites cs ON cs.contact_id = ct.id AND cs.site_code = %(site)s
        WHERE ct.etat = 'ok' AND cs.state = 'cold_email'
          AND ct.created_at >= now() - make_interval(days => %(j)s){cond_secteur}
        ORDER BY ct.created_at DESC
        LIMIT %(lim)s""",
        {"site": site, "j": jours, "secteurs": secteurs, "lim": int(limite)})


# ── Ce que les boîtes peuvent RÉELLEMENT absorber ────────────────────────────
# Un scénario n'envoie pas ce qu'il veut : il envoie ce que les adresses Maildoso
# autorisent. Au 2026-08-25 les quatre boîtes réservées à Mozart sont en chauffe — elles
# rendent ZÉRO jusqu'au 8 septembre — puis montent de 15 à 35 par jour et par boîte.
#
# Sans garde-fou, `inscrire()` prenait 500 contacts par passage et le cron tourne toutes
# les heures : de quoi mettre douze mille personnes en file pour une capacité de soixante
# par jour. Ces contacts attendraient des mois, recevraient un message périmé, et la
# fenêtre de non-recontact de 120 jours les bloquerait entre-temps. On n'inscrit donc pas
# plus que ce qui peut partir dans un horizon raisonnable.
HORIZON_FILE_JOURS = 7


def capacite_jour(site: str) -> dict:
    """Ce que les adresses de Mozart peuvent envoyer aujourd'hui, et pourquoi.

    Rend aussi le détail par boîte : « 0 parce qu'en chauffe » n'est pas la même chose que
    « 0 parce que le plafond du jour est atteint », et l'écran doit pouvoir le dire.
    """
    try:
        import expediteur as ex
        boites = ex.boites(site, usage="mozart")
    except Exception as e:  # noqa: BLE001
        return {"capacite": 0, "boites": [], "erreur": str(e)[:200]}

    detail = []
    for b in boites:
        motif = ("en chauffe jusqu'au " + str(b.get("chauffe_fin") or "")
                 if b.get("en_chauffe") else
                 "au repos" if b.get("au_repos_jusqu_a") else
                 "inactive" if not b.get("active") else "")
        detail.append({"email": b["email"], "reste": b["reste"],
                       "plafond": b.get("plafond_chauffe"), "motif": motif})
    return {"capacite": sum(b["reste"] for b in boites),
            "boites": detail,
            "en_chauffe": sum(1 for b in boites if b.get("en_chauffe")),
            "horizon_jours": HORIZON_FILE_JOURS}


def file_en_attente(scenario_id: str) -> int:
    """Combien de contacts attendent déjà leur tour dans ce scénario."""
    r = _q("""SELECT count(*) FROM mozart_inscriptions
               WHERE scenario_id = %(s)s AND statut = 'en_cours'""", {"s": scenario_id})
    return int(r[0][0]) if r else 0


def inscrire(sc: dict, dry_run: bool = False, limite: int = 500) -> dict:
    noeuds, liens = _graphe(sc)
    decl = next((n for n in noeuds.values() if n.get("type") == "declencheur"), None)
    if not decl:
        return {"inscrits": 0, "note": "aucun déclencheur"}

    premier = _suivant(liens, decl["id"])
    if not premier:
        return {"inscrits": 0, "note": "le déclencheur ne mène nulle part"}

    # La file ne doit jamais dépasser ce que les boîtes peuvent envoyer sur l'horizon.
    # On calcule la place restante AVANT de piocher : inutile de lire cinq cents contacts
    # pour en jeter quatre cent quatre-vingts.
    cap = capacite_jour(sc["site_code"])
    plafond_file = max(0, cap["capacite"] * HORIZON_FILE_JOURS)
    deja = file_en_attente(sc["id"])
    place = max(0, plafond_file - deja)
    if place <= 0:
        return {"inscrits": 0, "candidats": 0, "bride": True,
                "note": (f"file pleine : {deja} contact(s) en attente pour une capacité de "
                         f"{cap['capacite']}/jour"
                         + (" (boîtes en chauffe)" if cap.get("en_chauffe") else "")),
                "capacite_jour": cap["capacite"], "file": deja}

    cands = _candidats(sc["site_code"], decl, min(limite, place))
    if dry_run:
        return {"inscrits": 0, "candidats": len(cands), "dry_run": True,
                "exemples": [c[1] for c in cands[:5]]}

    # Un seul INSERT pour tout le monde : 500 candidats faisaient 500 transactions, donc
    # 500 emprunts de connexion, pour insérer des lignes triviales.
    # `ON CONFLICT DO NOTHING` porte la garantie « une seule fois » : deux passages
    # rapprochés du cron ne peuvent pas inscrire deux fois la même personne.
    n = _ecrire("""
        INSERT INTO mozart_inscriptions (scenario_id, email, contact_id,
                                         noeud_courant, agir_a)
        SELECT %(s)s, x.email, x.cid::uuid, %(n)s, now()
        FROM unnest(%(emails)s::text[], %(cids)s::text[]) AS x(email, cid)
        ON CONFLICT (scenario_id, email) DO NOTHING""",
        {"s": sc["id"], "n": premier,
         "emails": [c[1] for c in cands], "cids": [str(c[0]) for c in cands]})
    return {"inscrits": n, "candidats": len(cands),
            "capacite_jour": cap["capacite"], "file": deja + n,
            "plafond_file": plafond_file}


# ── Exécution d'un pas ────────────────────────────────────────────────────────
def _journaliser(sid: str, noeud_id: str, email: str, type_noeud: str,
                 resultat: str, detail: str = "") -> None:
    _ecrire("""INSERT INTO mozart_passages (scenario_id, noeud_id, email, type_noeud,
                                            resultat, detail)
               VALUES (%(s)s, %(n)s, %(e)s, %(t)s, %(r)s, %(d)s)""",
            {"s": sid, "n": noeud_id, "e": email, "t": type_noeud,
             "r": resultat, "d": (detail or "")[:400]})


def _a_reagi(email: str, site: str, depuis, quoi: str) -> bool:
    """Le contact a-t-il ouvert ou cliqué DEPUIS le dernier email du scénario ?

    On interroge `email_events`, le même journal que les campagnes : une ouverture y est
    la même qu'elle vienne d'un scénario ou d'un envoi de masse.
    """
    types = ["click"] if quoi == "clique" else ["open", "click"]
    r = _q("""SELECT 1 FROM email_events
              WHERE lower(email::text) = %(e)s AND site_code = %(site)s
                AND event_type = ANY(%(t)s) AND occurred_at > %(d)s
                AND COALESCE((meta->>'proxy')::boolean, false) = false
              LIMIT 1""",
           {"e": email, "site": site, "t": types, "d": depuis})
    return bool(r)


# Les canaux qu'un scénario a le droit d'utiliser. **Décision de Camille du 2026-08-24 :
# Maildoso et Sweego, pas Emelia.** La raison n'est pas un goût : Emelia fonctionne par
# CAMPAGNE ENTIÈRE — on lui remet une liste de contacts et il l'étale lui-même sur les
# jours suivants. Un scénario, lui, décide contact par contact, à l'instant où celui-ci
# atteint le nœud. Les deux modèles ne se rejoignent pas, et le proposer quand même aurait
# produit des scénarios qui échouent au premier contact.
CANAUX_AUTORISES = ("maildoso", "sweego")


def expediteurs(site: str) -> list[dict]:
    """Les canaux d'envoi et, pour chacun, les expéditeurs réellement disponibles.

    Les deux canaux n'ont pas la même réalité, et l'écran doit le dire plutôt que
    présenter deux listes identiques :

      - **Maildoso** a de vraies boîtes nommées, une par expéditrice. C'est le seul canal
        où « choisir l'expéditeur » veut dire quelque chose — et le seul qui porte
        l'affinité par contact.
      - **Sweego** envoie depuis une adresse unique dérivée du domaine configuré. Il n'y a
        rien à choisir ; on l'affiche pour qu'on sache ce qui partira.
    """
    import expediteur as ex

    out = [{
        "canal": "maildoso",
        "libelle": "Maildoso (SMTP, une boîte nommée par envoi)",
        "choix_possible": True,
        "porte_affinite": True,
        "expediteurs": [{"email": b["email"], "nom": b["sender_name"],
                         "statut": b["status"], "disponible": b["active"]}
                        for b in ex.boites(site, usage="mozart")],
    }]
    try:
        import sweego_backend as sw
        f = sw._from()
        out.append({"canal": "sweego", "libelle": "Sweego (envoi de masse)",
                    "choix_possible": False, "porte_affinite": False,
                    "expediteurs": [{"email": f.get("email"), "nom": f.get("name"),
                                     "statut": "unique", "disponible": True}]})
    except Exception:  # noqa: BLE001
        pass
    return out


def md_suppression_jours() -> int:
    """La fenêtre de non-recontact, lue là où elle est définie — jamais recopiée."""
    import maildoso_backend as md
    return md.SUPPRESSION_JOURS


def _envoyer(sc: dict, noeud: dict, insc: dict, dry_run: bool = False) -> tuple[str, str]:
    """Envoie l'email d'un nœud. Rend (résultat, détail).

    Emprunte EXACTEMENT le chemin des campagnes : résolution du message, fenêtre de 120
    jours, garde-fou des variables, affinité d'expéditeur, plafond par boîte. Un scénario
    n'a aucun privilège — sinon il devient la porte dérobée de toutes les règles.

    **Le canal et l'expéditeur du nœud sont respectés, sauf contre l'affinité.** Un
    contact qui a ouvert ou cliqué depuis une adresse précise garde CETTE adresse : c'est
    la décision du 2026-08-23, et un réglage de nœud ne peut pas la défaire sans détruire
    le capital de réputation acquis auprès de ce destinataire. Le choix du nœud s'applique
    donc à tous les autres — et le refus est dit, jamais silencieux.
    """
    import html_templates_backend as htb
    import journal_pg
    import maildoso_backend as md
    from contacts_pool_backend import mark_pushed_to_emelia

    site = sc["site_code"]
    d = noeud.get("data") or {}
    mid = d.get("message_id")
    if not mid:
        return "refuse", "aucun message choisi sur ce nœud"

    canal = (d.get("canal") or "maildoso").strip()
    # Le garde-fou reste, même si l'écran ne propose plus qu'un canal autorisé : un graphe
    # enregistré avant la décision, ou modifié à la main, ne doit pas passer au travers.
    if canal not in CANAUX_AUTORISES:
        return "refuse", (f"canal « {canal} » non utilisable par un scénario — "
                          f"choisir {' ou '.join(CANAUX_AUTORISES)}")

    msg = htb.resolve_campaign_message(site, mid)
    if not msg or not msg.get("html"):
        return "refuse", f"message « {mid} » introuvable"

    # La fenêtre de non-recontact est appliquée par `maildoso_backend.send_email`, au point
    # de passage de TOUS les envois. On la contrôle quand même ici — mais seulement pour
    # éviter de résoudre un message et de lire une fiche pour quelqu'un qui sera refusé.
    # Ce n'est plus la garantie, c'est une économie.
    if journal_pg.recemment_servis([insc["email"]], md_suppression_jours()):
        return "refuse", "contacté trop récemment"

    # Un canal autre que Maildoso change forcément d'adresse expéditrice : Sweego part
    # d'une adresse unique. On écarte donc les contacts dont l'affinité est CONFIRMÉE,
    # comme le fait déjà le dispatch des campagnes (`routage.filtrer_pour_canal`).
    # Contrôlé AVANT de lire le contact : ce refus ne dépend d'aucune donnée de fiche, et
    # le placer après faisait échouer la vérification pour la mauvaise raison.
    if canal != "maildoso":
        try:
            import routage
            if (insc["email"] or "").lower() in routage.contacts_verrouilles([insc["email"]]):
                return "refuse", (f"affinité expéditeur confirmée — ce contact reste sur "
                                  f"Maildoso, il ne part pas par {canal}")
        except Exception as e:  # noqa: BLE001
            print(f"[mozart] filtre de routage indisponible ({type(e).__name__}: {e})",
                  flush=True)

    if dry_run:
        return "simule", f"enverrait « {msg.get('subject') or d.get('objet') or mid} »"

    contact = _q("""SELECT id::text, email::text, prenom, nom, societe, city
                    FROM contacts WHERE email = %(e)s""", {"e": insc["email"]})
    if not contact:
        return "refuse", "contact absent du référentiel"
    cid, email, prenom, nom, societe, ville = contact[0]
    ct = {"id": cid, "email": email, "prenom": prenom, "nom": nom,
          "societe": societe, "city": ville}

    campaign_id = f"{site}-mozart-{sc['id'][:8]}-{datetime.now(timezone.utc):%Y-%m-%d}"

    if canal != "maildoso":
        import sweego_backend as sw
        r = sw.send_email(email, d.get("objet") or msg.get("subject") or "",
                          html_str=msg["html"], site=site)
        if not (r or {}).get("ok"):
            return "refuse", (r or {}).get("error") or "envoi Sweego refusé"
        try:
            mark_pushed_to_emelia(cid, site, campaign_id, "", email=email)
        except Exception as e:  # noqa: BLE001
            print(f"[mozart] marquage de {email} échoué : {type(e).__name__}: {e}", flush=True)
        return "envoye", "via Sweego"

    # Maildoso. Une boîte explicitement choisie sur le nœud ne l'emporte QUE si le contact
    # n'a pas d'affinité confirmée — sinon c'est la sienne qui gagne, silencieusement pour
    # le scénario mais délibérément pour la réputation.
    boite = None
    voulue = (d.get("expediteur") or "").strip()
    if voulue:
        import expediteur as ex
        aff = ex.affinite(email)
        if aff and aff.get("confirmee"):
            boite = None          # sa boîte, choisie par `send_email` via l'affinité
        else:
            boite = next((b for b in ex.boites(site, usage="mozart")
                          if b["email"] == voulue and b["active"] and b["reste"] > 0), None)
            if not boite:
                return "reporte", f"la boîte {voulue} n'est pas disponible aujourd'hui"

    # L'écart minimum par boîte est appliqué par `send_email` lui-même, qui est le seul à
    # savoir quelle boîte servira réellement. Le refaire ici obligeait à DEVINER cette
    # boîte via l'affinité — et à ne rien contrôler du tout pour un contact qui n'en a pas
    # encore. Le refus revient sous la forme `reporte`, traitée juste en dessous.
    # Le pixel d'ouverture est optionnel PAR SCÉNARIO. Le guide Maildoso le déconseille
    # (Gmail le note), mais le couper partout priverait les commerciaux de la liste des
    # ouvreurs et éteindrait l'alerte sur la pente du taux d'ouverture. Un scénario
    # automatique, lui, tourne sans personne derrière : c'est là qu'on peut s'en passer.
    # Défaut : suivi actif — on ne retire pas une mesure sans que ce soit demandé.
    suivi = sc.get("suivi_ouverture")
    res = md.send_email(email, d.get("objet") or msg.get("subject") or "",
                        html=msg["html"], site=site, campaign_id=campaign_id, contact=ct,
                        mailbox=boite, usage="mozart",
                        suivi_ouverture=True if suivi is None else bool(suivi))
    if not res.get("ok"):
        # Un report (boîte pleine, contact en attente de SA boîte) n'est pas un échec :
        # on le rejouera au prochain passage sans avancer dans le graphe.
        if res.get("reporte"):
            return "reporte", res.get("error") or "boîte attitrée pleine"
        return "refuse", res.get("error") or "envoi refusé"

    try:
        mark_pushed_to_emelia(cid, site, campaign_id, "", email=email,
                              mailbox=res.get("mailbox"))
    except Exception as e:  # noqa: BLE001
        print(f"[mozart] marquage de {email} échoué : {type(e).__name__}: {e}", flush=True)
    return "envoye", f"via {res.get('mailbox')}"


def _jouer_un_pas(sc: dict, insc: dict, dry_run: bool, graphe=None) -> dict:
    """Exécute le nœud courant et dit où aller ensuite, et quand.

    `graphe` est passé par `avancer` : le reconstruire depuis le JSON à chaque pas, pour
    chaque contact, refaisait le même travail des milliers de fois par tick.
    """
    noeuds, liens = graphe if graphe else _graphe(sc)
    noeud = noeuds.get(insc["noeud_courant"])
    if not noeud:
        return {"fin": True, "motif": f"nœud « {insc['noeud_courant']} » disparu du graphe"}

    t = noeud.get("type")
    d = noeud.get("data") or {}

    if t in ("fin", None):
        return {"fin": True, "motif": "fin du scénario"}

    if t == "delai":
        unite = d.get("unite") or "jours"
        duree = float(d.get("duree") or 1)
        delta = timedelta(hours=duree) if unite == "heures" else timedelta(days=duree)
        if not dry_run:
            _journaliser(sc["id"], noeud["id"], insc["email"], t, "attend",
                         f"{duree} {unite}")
        return {"suivant": _suivant(liens, noeud["id"]),
                "agir_a": datetime.now(timezone.utc) + delta,
                "resultat": f"attend {duree} {unite}"}

    if t == "email":
        # La fenêtre d'envoi est contrôlée ICI, au moment de jouer le pas, et pas à
        # l'inscription : entre les deux il peut s'écouler des jours.
        ouverte, pourquoi = fenetre_ouverte()
        if ouverte or dry_run:
            resultat, detail = _envoyer(sc, noeud, insc, dry_run)
        else:
            resultat, detail = "hors_fenetre", pourquoi
            if not dry_run:
                _journaliser(sc["id"], noeud["id"], insc["email"], t, resultat, detail)
            # On reste sur le même nœud et on vise la RÉOUVERTURE, pas « dans deux
            # heures » : un contact bloqué à 18h31 serait sinon réessayé onze fois
            # pendant la nuit, pour rien.
            return {"suivant": noeud["id"], "resultat": resultat, "detail": detail,
                    "agir_a": prochaine_ouverture().astimezone(timezone.utc)}
        if not dry_run:
            _journaliser(sc["id"], noeud["id"], insc["email"], t, resultat, detail)
        if resultat == "reporte":
            # On reste sur le même nœud : le prochain passage réessaiera.
            return {"suivant": noeud["id"], "resultat": resultat, "detail": detail,
                    "agir_a": datetime.now(timezone.utc) + timedelta(hours=2)}
        return {"suivant": _suivant(liens, noeud["id"]),
                "agir_a": datetime.now(timezone.utc),
                "resultat": resultat, "detail": detail}

    if t == "condition":
        quoi = d.get("sur") or "ouvert"
        depuis = insc.get("inscrit_le") or (datetime.now(timezone.utc) - timedelta(days=30))
        # On regarde depuis le DERNIER email envoyé par ce scénario à ce contact : la
        # question « a-t-il ouvert ? » n'a de sens que rapportée à un message précis.
        dernier = _q("""SELECT max(quand) FROM mozart_passages
                        WHERE scenario_id = %(s)s AND email = %(e)s
                          AND type_noeud = 'email' AND resultat = 'envoye'""",
                     {"s": sc["id"], "e": insc["email"]})
        if dernier and dernier[0][0]:
            depuis = dernier[0][0]
        reagi = _a_reagi(insc["email"], sc["site_code"], depuis,
                         "clique" if quoi == "clique" else "ouvert")
        branche = "oui" if reagi else "non"
        if not dry_run:
            _journaliser(sc["id"], noeud["id"], insc["email"], t,
                         "clique" if (reagi and quoi == "clique") else
                         ("ouvert" if reagi else "rien"), f"branche {branche}")
        return {"suivant": _suivant(liens, noeud["id"], branche),
                "agir_a": datetime.now(timezone.utc),
                "resultat": branche}

    return {"fin": True, "motif": f"type de nœud inconnu : {t}"}


def avancer(sc: dict, dry_run: bool = False, limite: int = 200) -> dict:
    """Fait avancer tous les inscrits dont l'heure est venue."""
    dus = _q("""SELECT id, email, noeud_courant, inscrit_le
                FROM mozart_inscriptions
                WHERE scenario_id = %(s)s AND statut = 'en_cours'
                  AND agir_a IS NOT NULL AND agir_a <= now()
                ORDER BY agir_a LIMIT %(lim)s""",
             {"s": sc["id"], "lim": int(limite)})

    graphe = _graphe(sc)      # une fois pour tout le lot, pas une fois par pas
    bilan = {"traites": 0, "envoyes": 0, "reportes": 0, "refuses": 0, "termines": 0,
             "hors_fenetre": 0, "details": []}
    for iid, email, noeud, inscrit_le in dus:
        insc = {"id": str(iid), "email": email, "noeud_courant": noeud,
                "inscrit_le": inscrit_le}
        bilan["traites"] += 1
        pas = 0
        while pas < MAX_PAS_PAR_PASSAGE:
            pas += 1
            r = _jouer_un_pas(sc, insc, dry_run, graphe)
            if r.get("resultat") == "envoye":
                bilan["envoyes"] += 1
            elif r.get("resultat") == "reporte":
                bilan["reportes"] += 1
            elif r.get("resultat") == "refuse":
                bilan["refuses"] += 1
            elif r.get("resultat") == "hors_fenetre":
                bilan["hors_fenetre"] += 1
            if len(bilan["details"]) < 12:
                bilan["details"].append({"email": email, "noeud": insc["noeud_courant"],
                                         "resultat": r.get("resultat") or r.get("motif"),
                                         "detail": r.get("detail")})
            if r.get("fin") or not r.get("suivant"):
                bilan["termines"] += 1
                if not dry_run:
                    _ecrire("""UPDATE mozart_inscriptions
                               SET statut = 'termine', termine_le = now(),
                                   agir_a = NULL, motif_sortie = %(m)s
                               WHERE id = %(id)s""",
                            {"id": insc["id"], "m": (r.get("motif") or "parcours terminé")[:200]})
                break

            insc["noeud_courant"] = r["suivant"]
            if not dry_run:
                _ecrire("""UPDATE mozart_inscriptions
                           SET noeud_courant = %(n)s, agir_a = %(a)s
                           WHERE id = %(id)s""",
                        {"id": insc["id"], "n": r["suivant"], "a": r["agir_a"]})
            # On ne joue en chaîne que ce qui est immédiat. Dès qu'un pas repousse
            # l'échéance, on s'arrête : c'est le prochain passage qui reprendra.
            if r["agir_a"] > datetime.now(timezone.utc) + timedelta(seconds=5):
                break
    return bilan


def sites_actifs() -> list[str]:
    """Les sites qui ont au moins un scénario actif.

    Le cron appelait `tick` sans argument, donc sur `lcr` seul : un scénario créé pour une
    autre marque s'affichait, s'activait, et n'avançait jamais — sans que rien ne le dise.
    On demande à la base plutôt qu'à une constante.
    """
    return [r[0] for r in _q("""SELECT DISTINCT site_code FROM mozart_scenarios
                               WHERE statut = 'actif' ORDER BY 1""")]


def tick(site: str | None = None, dry_run: bool = False) -> dict:
    """Un passage complet : on inscrit les nouveaux, puis on fait avancer tout le monde.

    Sans `site`, on traite TOUS les sites qui ont un scénario actif.
    """
    if site is None:
        resultats = [tick(s, dry_run=dry_run) for s in sites_actifs()]
        return {"sites": [r["site"] for r in resultats], "dry_run": dry_run,
                "scenarios": [x for r in resultats for x in r["scenarios"]]}
    out = {"site": site, "dry_run": dry_run, "scenarios": []}
    for sc in scenarios(site, statut="actif"):
        ins = inscrire(sc, dry_run=dry_run)
        av = avancer(sc, dry_run=dry_run)
        out["scenarios"].append({"id": sc["id"], "nom": sc["nom"],
                                 "inscription": ins, "avancement": av})
    return out


# ── Statistiques ──────────────────────────────────────────────────────────────
def resume(sid: str, site: str) -> dict:
    """Le chiffre d'un scénario : ce qui est parti, et ce que les gens en ont fait.

    Les envois se comptent dans `mozart_passages` — le journal du scénario. Les réactions
    se lisent dans `email_events`, le journal COMMUN à toute la plateforme : une ouverture
    est la même qu'elle vienne d'un scénario ou d'une campagne, et la compter deux fois de
    deux façons produirait deux chiffres pour un seul fait.

    Les taux sont rapportés aux destinataires DISTINCTS servis par ce scénario. Rapportés
    aux envois, un contact relancé deux fois qui ouvre une fois donnerait 50 % — ce qui ne
    dit rien de personne.
    """
    envois = _q("""
        SELECT count(*) FILTER (WHERE type_noeud = 'email' AND resultat = 'envoye'),
               count(*) FILTER (WHERE type_noeud = 'email' AND resultat = 'envoye'
                                  AND timezone('Europe/Paris', quand)::date
                                      = timezone('Europe/Paris', now())::date),
               count(DISTINCT email) FILTER (WHERE type_noeud = 'email' AND resultat = 'envoye'),
               min(quand) FILTER (WHERE type_noeud = 'email' AND resultat = 'envoye')
        FROM mozart_passages WHERE scenario_id = %(s)s""", {"s": sid})
    total, aujourdhui, destinataires, premier = (envois[0] if envois else (0, 0, 0, None))

    # Chaque réaction doit être POSTÉRIEURE à l'envoi que CE scénario a fait à CETTE
    # personne. Sans cette borne, toute ouverture qu'un contact a produite un jour sur le
    # site comptait — y compris une campagne d'il y a trois mois. Sur une liste déjà
    # travaillée, un scénario que personne n'a ouvert affichait près de 100 %.
    reactions = _q("""
        WITH servis AS (
            SELECT email, min(quand) AS premier_envoi FROM mozart_passages
            WHERE scenario_id = %(s)s AND type_noeud = 'email' AND resultat = 'envoye'
            GROUP BY email)
        SELECT count(DISTINCT ev.email) FILTER (WHERE ev.event_type = 'open'
                   AND COALESCE((ev.meta->>'proxy')::boolean, false) = false),
               count(DISTINCT ev.email) FILTER (WHERE ev.event_type = 'click')
        FROM email_events ev
        JOIN servis s ON s.email = ev.email AND ev.occurred_at >= s.premier_envoi
        WHERE ev.site_code = %(site)s""", {"s": sid, "site": site})
    ouvreurs, cliqueurs = (reactions[0] if reactions else (0, 0))

    d = int(destinataires or 0)

    def pc(n):
        return round(100.0 * int(n or 0) / d, 1) if d else None

    # La date de début : le premier envoi s'il y en a eu un, sinon la première inscription.
    # C'est la question qu'on se pose devant un scénario — « depuis quand tourne-t-il ? » —
    # et elle n'a de sens qu'à partir du moment où il a fait quelque chose.
    if not premier:
        r = _q("""SELECT min(inscrit_le) FROM mozart_inscriptions
                  WHERE scenario_id = %(s)s""", {"s": sid})
        premier = r[0][0] if r else None

    return {"envoyes_total": int(total or 0), "envoyes_aujourdhui": int(aujourdhui or 0),
            "destinataires": d, "ouvreurs": int(ouvreurs or 0),
            "cliqueurs": int(cliqueurs or 0),
            "taux_ouverture": pc(ouvreurs), "taux_clic": pc(cliqueurs),
            "debut": str(premier) if premier else None}


def stats(sid: str) -> dict:
    """Par nœud : combien sont passés, et avec quel résultat. Pour l'affichage sur le graphe."""
    par_noeud: dict[str, dict] = {}
    for noeud_id, resultat, n in _q("""
            SELECT noeud_id, COALESCE(resultat, '?'), count(*)
            FROM mozart_passages WHERE scenario_id = %(s)s GROUP BY 1, 2""", {"s": sid}):
        e = par_noeud.setdefault(noeud_id, {"total": 0})
        e[resultat] = int(n)
        e["total"] += int(n)

    etats = {r[0]: int(r[1]) for r in _q("""
        SELECT statut, count(*) FROM mozart_inscriptions
        WHERE scenario_id = %(s)s GROUP BY 1""", {"s": sid})}

    encours = {r[0]: int(r[1]) for r in _q("""
        SELECT noeud_courant, count(*) FROM mozart_inscriptions
        WHERE scenario_id = %(s)s AND statut = 'en_cours' AND noeud_courant IS NOT NULL
        GROUP BY 1""", {"s": sid})}
    for noeud_id, n in encours.items():
        par_noeud.setdefault(noeud_id, {"total": 0})["en_attente"] = n

    return {"scenario_id": sid, "par_noeud": par_noeud, "inscriptions": etats,
            "total_inscrits": sum(etats.values())}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("commande", choices=["etat", "tick"], nargs="?", default="etat")
    ap.add_argument("--site", default=None, help="par défaut : tous les sites actifs")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    assurer_schema()
    if a.commande == "tick":
        print(json.dumps(tick(a.site, dry_run=a.dry_run), indent=1,
                         ensure_ascii=False, default=str))
    else:
        for sc in scenarios(a.site or "lcr"):
            s = stats(sc["id"])
            print(f"  [{sc['statut']:9s}] {sc['nom']}  —  {s['total_inscrits']} inscrit(s) "
                  f"{s['inscriptions']}")
