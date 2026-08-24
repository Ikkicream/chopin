#!/usr/bin/env python3
"""Mozart : le moteur des scénarios. Il envoie de vrais emails, donc il se teste.

Deux familles de garanties, et les deux comptent autant :

  - **ce qui protège** : un scénario n'a AUCUN privilège. Tout email qu'il envoie passe
    par le chemin des campagnes — fenêtre de 120 jours, garde-fou des variables, affinité
    d'expéditeur, plafond par boîte. Un scénario capable d'écrire à quelqu'un qu'une
    campagne s'interdit d'écrire serait une porte dérobée dans la règle la plus coûteuse
    de la plateforme.
  - **ce qui exécute** : un contact n'entre qu'une fois, un délai fait attendre, une
    condition choisit la bonne branche, et un graphe cassé s'arrête au lieu de partir
    au hasard.

Aucun email n'est envoyé par ces tests : l'envoi est remplacé par un faux.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'ÉCHEC'}  {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def _graphe(**kw):
    g = {
        "nodes": [
            {"id": "d1", "type": "declencheur", "data": {"nom": "Entrée", "depuis_jours": 3}},
            {"id": "w1", "type": "delai", "data": {"nom": "Attendre", "duree": 1, "unite": "jours"}},
            {"id": "e1", "type": "email", "data": {"nom": "Message", "message_id": "cold:immobilier:first"}},
            {"id": "c1", "type": "condition", "data": {"nom": "Ouvert ?", "sur": "ouvert"}},
            {"id": "e2", "type": "email", "data": {"nom": "Relance", "message_id": "cold:immobilier:first"}},
            {"id": "f1", "type": "fin", "data": {"nom": "Fin"}},
        ],
        "edges": [
            {"id": "a", "source": "d1", "target": "w1"},
            {"id": "b", "source": "w1", "target": "e1"},
            {"id": "c", "source": "e1", "target": "c1"},
            {"id": "d", "source": "c1", "target": "f1", "sourceHandle": "oui"},
            {"id": "e", "source": "c1", "target": "e2", "sourceHandle": "non"},
            {"id": "f", "source": "e2", "target": "f1"},
        ],
    }
    g.update(kw)
    return g


def lance() -> int:
    import mozart

    print("Contrôle d'un graphe — ce qui doit empêcher l'activation")
    verifie("un graphe complet passe", mozart.verifier(_graphe()) == [],
            f"({mozart.verifier(_graphe())})")

    sans_decl = _graphe()
    sans_decl["nodes"] = [n for n in sans_decl["nodes"] if n["id"] != "d1"]
    verifie("sans déclencheur, on refuse",
            any("déclencheur" in p for p in mozart.verifier(sans_decl)))

    sans_msg = _graphe()
    sans_msg["nodes"] = [{**n, "data": {**n["data"], "message_id": None}}
                         if n["id"] == "e1" else n for n in sans_msg["nodes"]]
    verifie("un email sans message, on refuse",
            any("message" in p for p in mozart.verifier(sans_msg)))

    delai_zero = _graphe()
    delai_zero["nodes"] = [{**n, "data": {**n["data"], "duree": 0}}
                           if n["id"] == "w1" else n for n in delai_zero["nodes"]]
    verifie("un délai à zéro, on refuse",
            any("zéro" in p for p in mozart.verifier(delai_zero)))

    branches = _graphe()
    branches["edges"] = [e for e in branches["edges"] if e["source"] != "c1"]
    verifie("une condition sans branche reliée, on refuse",
            any("branche" in p for p in mozart.verifier(branches)))

    print("\nCheminement dans le graphe")
    liens = _graphe()["edges"]
    verifie("le pas suivant est le bon", mozart._suivant(liens, "w1") == "e1")
    verifie("la branche « oui » mène à la fin",
            mozart._suivant(liens, "c1", "oui") == "f1")
    verifie("la branche « non » mène à la relance",
            mozart._suivant(liens, "c1", "non") == "e2")
    verifie("un nœud terminal ne mène nulle part",
            mozart._suivant(liens, "f1") is None)
    verifie("une branche absente ne part pas au hasard",
            mozart._suivant([{"source": "c1", "target": "x", "sourceHandle": "oui"}],
                            "c1", "non") is None)

    print("\nLes protections d'envoi — un scénario n'a aucun privilège")
    vrai_recents = None
    import journal_pg
    vrai_recents = journal_pg.recemment_servis
    sc = {"id": str(uuid.uuid4()), "site_code": "lcr", "graphe": _graphe()}
    noeud = {"id": "e1", "type": "email", "data": {"message_id": "cold:immobilier:first"}}
    insc = {"email": "quelquun@exemple-test.fr"}

    journal_pg.recemment_servis = lambda emails, jours: {"quelquun@exemple-test.fr"}
    res, detail = mozart._envoyer(sc, noeud, insc, dry_run=False)
    verifie("un contact servi trop récemment est REFUSÉ par le scénario",
            res == "refuse" and "récemment" in detail, f"({res} — {detail})")

    # La garantie n'est plus dans Mozart : elle est au POINT DE PASSAGE de tous les
    # envois. Le contrôle de Mozart n'est plus qu'une économie — éviter de résoudre un
    # message pour quelqu'un qui sera refusé. On vérifie donc les DEUX niveaux.
    import maildoso_backend as md
    import inspect
    src_send = inspect.getsource(md.send_email)
    verifie("la fenêtre est appliquée dans `send_email` lui-même",
            "recemment_servis" in src_send and "SUPPRESSION_JOURS" in src_send,
            "(sinon un nouveau chemin d'envoi la contournerait)")
    verifie("elle exempte les BAT et les tests",
            'len((campaign_id or "").split("-")) >= 6' in src_send,
            "(un BAT part vers nos propres adresses, à notre demande)")
    verifie("la constante n'est écrite qu'une fois",
            md.SUPPRESSION_JOURS == mozart.md_suppression_jours() == 120,
            f"({md.SUPPRESSION_JOURS})")

    journal_pg.recemment_servis = lambda emails, jours: set()
    res, detail = mozart._envoyer(sc, {"id": "e1", "type": "email", "data": {}},
                                  insc, dry_run=False)
    verifie("un nœud sans message est refusé", res == "refuse", f"({res} — {detail})")

    res, detail = mozart._envoyer(sc, noeud, insc, dry_run=True)
    verifie("à sec, on simule sans envoyer", res == "simule", f"({res} — {detail})")
    journal_pg.recemment_servis = vrai_recents

    print("\nCanal et expéditeur — ce que l'écran propose doit exister vraiment")
    canaux = {c["canal"]: c for c in mozart.expediteurs("lcr")}
    verifie("seuls Maildoso et Sweego sont proposés",
            set(canaux) == set(mozart.CANAUX_AUTORISES) == {"maildoso", "sweego"},
            f"({sorted(canaux)})")
    verifie("Maildoso propose de vraies boîtes",
            canaux["maildoso"]["choix_possible"] and len(canaux["maildoso"]["expediteurs"]) >= 1,
            f"({len(canaux['maildoso']['expediteurs'])} boîtes)")
    verifie("Maildoso est le seul à porter l'affinité",
            canaux["maildoso"]["porte_affinite"]
            and not canaux["sweego"]["porte_affinite"])
    verifie("Sweego a une adresse unique, non choisie",
            not canaux["sweego"]["choix_possible"]
            and len(canaux["sweego"]["expediteurs"]) == 1,
            f"({canaux['sweego']['expediteurs']})")
    verifie("Emelia n'est plus proposé", "emelia" not in canaux)

    print("\nUn graphe ancien réglé sur un canal interdit reste bloqué")
    # L'écran ne propose plus Emelia, mais un scénario enregistré AVANT la décision — ou
    # modifié à la main — ne doit pas passer au travers pour autant.
    for canal_interdit in ("emelia", "postal", ""):
        g_i = _graphe()
        g_i["nodes"] = [{**n, "data": {**n["data"], "canal": canal_interdit}}
                        if n["id"] == "e1" else n for n in g_i["nodes"]]
        pbs = mozart.verifier(g_i)
        attendu = canal_interdit not in ("",)   # canal vide = Maildoso par défaut
        verifie(f"canal « {canal_interdit or '(vide)'} »",
                (any("canal" in p for p in pbs)) == attendu, f"({pbs})")

    print("\nL'envoi refuse aussi le canal interdit, pas seulement l'activation")
    journal_pg.recemment_servis = lambda emails, jours: set()
    res, detail = mozart._envoyer(
        {"id": str(uuid.uuid4()), "site_code": "lcr", "graphe": _graphe()},
        {"id": "e1", "type": "email",
         "data": {"message_id": "cold:immobilier:first", "canal": "emelia"}},
        {"email": "quelquun@exemple-test.fr"}, dry_run=False)
    verifie("un nœud Emelia ne part pas", res == "refuse" and "canal" in detail,
            f"({res} — {detail})")
    journal_pg.recemment_servis = vrai_recents

    print("\nL'affinité confirmée l'emporte sur le canal choisi")
    import routage
    vrai_verrous = routage.contacts_verrouilles
    routage.contacts_verrouilles = lambda emails: {e.lower() for e in emails}
    journal_pg.recemment_servis = lambda emails, jours: set()
    res, detail = mozart._envoyer(
        {"id": str(uuid.uuid4()), "site_code": "lcr", "graphe": _graphe()},
        {"id": "e1", "type": "email",
         "data": {"message_id": "cold:immobilier:first", "canal": "sweego"}},
        {"email": "quelquun@exemple-test.fr"}, dry_run=False)
    verifie("un contact verrouillé ne part PAS par un autre canal",
            res == "refuse" and "affinité" in detail, f"({res} — {detail})")
    routage.contacts_verrouilles = vrai_verrous
    journal_pg.recemment_servis = vrai_recents

    print("\nLa fenêtre d'envoi — heure de Paris, jamais heure serveur")
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo
    P = ZoneInfo("Europe/Paris")
    cas = [
        ((2026, 8, 24, 9, 0),  False, "lundi 09:00 — une minute trop tôt"),
        ((2026, 8, 24, 9, 1),  True,  "lundi 09:01 — ouverture"),
        ((2026, 8, 24, 13, 0), True,  "lundi 13:00"),
        ((2026, 8, 24, 18, 30), True, "lundi 18:30 — dernière minute"),
        ((2026, 8, 24, 18, 31), False, "lundi 18:31 — fermé"),
        ((2026, 8, 24, 3, 0),  False, "lundi 03:00 — la nuit"),
        ((2026, 8, 29, 12, 0), True,  "samedi midi — jour ouvré"),
        ((2026, 8, 23, 12, 0), False, "DIMANCHE midi"),
        ((2026, 8, 23, 10, 0), False, "dimanche matin, dans les horaires"),
    ]
    for (a_, mo, j, h, mi), attendu, libelle in cas:
        ok, _ = mozart.fenetre_ouverte(_dt(a_, mo, j, h, mi, tzinfo=P))
        verifie(libelle, ok == attendu, f"({'ouvert' if ok else 'fermé'})")

    print("\nUn refus horaire vise la RÉOUVERTURE, pas « dans deux heures »")
    for (a_, mo, j, h, mi), attendu_j, libelle in [
        ((2026, 8, 24, 18, 31), 25, "lundi soir → mardi"),
        ((2026, 8, 23, 12, 0),  24, "dimanche → lundi"),
        ((2026, 8, 29, 19, 0),  31, "samedi soir → lundi"),
    ]:
        p_ = mozart.prochaine_ouverture(_dt(a_, mo, j, h, mi, tzinfo=P))
        verifie(libelle, p_.day == attendu_j and p_.strftime("%H:%M") == mozart.FENETRE_DEBUT,
                f"({p_})")
    verifie("la réouverture tombe toujours un jour ouvré",
            all(mozart.prochaine_ouverture(_dt(2026, 8, d, 20, 0, tzinfo=P)).weekday()
                in mozart.FENETRE_JOURS for d in range(17, 31)))

    print("\nLe résumé chiffré d'un scénario")
    r = mozart.resume(str(uuid.uuid4()), "lcr")
    verifie("un scénario vierge rend des zéros, pas des None",
            r["envoyes_total"] == 0 and r["envoyes_aujourdhui"] == 0
            and r["destinataires"] == 0, f"({r})")
    verifie("les taux valent None quand il n'y a personne à rapporter",
            r["taux_ouverture"] is None and r["taux_clic"] is None)

    print("\nLes modèles : trois formes, verrouillées, duplicables")
    import mozart_modeles as mm
    verifie("trois modèles, pas trente", len(mm.MODELES) == 3,
            f"({[m['relances'] for m in mm.MODELES]} relance(s))")
    for m in mm.MODELES:
        g = mm._graphe(m["relances"])
        emails = [n for n in g["nodes"] if n["type"] == "email"]
        conds = [n for n in g["nodes"] if n["type"] == "condition"]
        verifie(f"« {m['nom'][9:]} » : {m['relances'] + 1} email(s)",
                len(emails) == m["relances"] + 1, f"({len(emails)})")
        verifie(f"   … et {m['relances']} condition(s)",
                len(conds) == m["relances"], f"({len(conds)})")
        # Un modèle est incomplet À DESSEIN — le message se choisit après duplication —
        # mais sa STRUCTURE doit être irréprochable : tout doit mener quelque part.
        pbs = [x for x in mozart.verifier(g) if "message" not in x]
        verifie("   … structure sans faute", not pbs, f"({pbs})")

    print("\n   Chaque relance vise les NON-ouvreurs")
    g2 = mm._graphe(2)
    for lien in [e for e in g2["edges"] if e.get("sourceHandle") == "non"]:
        cible = next(n for n in g2["nodes"] if n["id"] == lien["target"])
        verifie(f"   « non » → {cible['data']['nom']}", cible["type"] == "email")
    for lien in [e for e in g2["edges"] if e.get("sourceHandle") == "oui"]:
        cible = next(n for n in g2["nodes"] if n["id"] == lien["target"])
        verifie(f"   « oui » → {cible['data']['nom']}", cible["type"] == "fin",
                "(relancer qui a ouvert, c'est le punir d'avoir lu)")

    print("\n   Les délais montent : J+1, J+4, J+7")
    delais = [n["data"]["duree"] for n in mm._graphe(2)["nodes"] if n["type"] == "delai"]
    verifie("l'écart s'allonge à chaque relance", delais == sorted(delais) and delais == [1, 4, 7],
            f"({delais})")

    print("\n   Les modèles en base sont bien verrouillés")
    en_base = [s_ for s_ in mozart.scenarios("lcr") if s_.get("est_modele")]
    verifie("les trois sont là", len(en_base) >= 3, f"({len(en_base)})")
    verifie("tous verrouillés", all(s_["verrouille"] for s_ in en_base))
    verifie("aucun n'est actif", all(s_["statut"] != "actif" for s_ in en_base),
            "(un modèle n'envoie rien : il attend qu'on le copie)")

    print("\n   La duplication rend une copie libre")
    if en_base:
        copie = mozart.dupliquer(en_base[0]["id"], par="test")
        verifie("la copie existe", bool(copie))
        if copie:
            verifie("elle n'est ni modèle ni verrouillée",
                    not copie["verrouille"] and not copie["est_modele"])
            verifie("elle est en brouillon", copie["statut"] == "brouillon")
            verifie("le graphe est complet",
                    len(copie["graphe"]["nodes"]) == len(en_base[0]["graphe"]["nodes"]))
            mozart._ecrire("DELETE FROM mozart_scenarios WHERE id = %(i)s", {"i": copie["id"]})

    print("\n   La création des modèles est idempotente")
    avant = len([s_ for s_ in mozart.scenarios("lcr") if s_.get("est_modele")])
    mm.creer("lcr")
    apres = len([s_ for s_ in mozart.scenarios("lcr") if s_.get("est_modele")])
    verifie("un second passage ne double rien", avant == apres, f"({avant} → {apres})")

    print("\nLe garde-fou de boucle")
    verifie("un plafond de pas existe", mozart.MAX_PAS_PAR_PASSAGE > 0
            and mozart.MAX_PAS_PAR_PASSAGE <= 50, f"({mozart.MAX_PAS_PAR_PASSAGE} pas)")

    print("\nUnicité d'inscription — garantie par la base, pas par le code")
    r = mozart._q("""SELECT count(*) FROM pg_constraint
                     WHERE conname = 'mozart_une_inscription'""")
    verifie("la contrainte d'unicité existe en base", r and int(r[0][0]) == 1)

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:6])}")
        return 1
    print("Mozart exécute ce qui est dessiné, et rien de plus.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
