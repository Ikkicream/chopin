#!/usr/bin/env python3
"""Le garde-fou de crédits Emelia : « quand il n'y a plus de crédit, on s'arrête ».

La boucle des dirigeants appelait Emelia pour CHAQUE nom, sans jamais regarder le solde.
À court de crédits, elle continuait d'appeler — autant d'échecs, et aucune trace de la
raison. Ces tests vérifient les trois arrêts, sans dépenser un seul crédit : l'appel
payant est remplacé par un faux.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'ÉCHEC'}  {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def lance() -> int:
    import basile_backend as bb

    vrais = (bb.count, bb.find, bb.fetch_dirigeants_by_siren,
             bb._emelia_find_email, bb._solde_emelia)
    appels = {"emelia": 0}

    # 40 sociétés, 1 dirigeant chacune : de quoi dépasser tous les plafonds testés.
    societes = [{"data": {"siren": f"{700000000+i}", "legal_name": f"SOCIETE {i}",
                          "website": f"societe{i}.fr", "headquarters_city": "NANTES",
                          "headquarters_postal_code": "44000", "phone": None}}
                for i in range(40)]

    def faux_emelia(fullname, company, website):
        appels["emelia"] += 1
        return {"status": "completed", "value": f"contact{appels['emelia']}@exemple-test.fr"}

    def faux_emelia_bredouille(fullname, company, website):
        """Emelia qui ne trouve jamais rien : aucune facturation, donc aucun crédit."""
        appels["emelia"] += 1
        return {"status": "completed", "value": None}

    bb.count = lambda kind, filters: len(societes)
    bb.find = lambda kind, filters, limit, token=None: {"leads": societes, "pagination": {}}
    bb.fetch_dirigeants_by_siren = lambda sirens, delay=0: {
        s: [{"prenom": "Jean", "nom": f"Dupont{i}", "role": "Gérant"}]
        for i, s in enumerate(sirens)}
    bb._emelia_find_email = faux_emelia

    def passe(**kw):
        appels["emelia"] = 0
        return bb.run_dirigeant_segment("lcr", {"naf_code": {"include": ["68.31Z"]}},
                                        sector="immobilier", dept_code="44",
                                        max_companies=40, delay=0, use_emelia=True,
                                        dry_run=False, **kw)

    print("Le budget de la passe s'impose")
    bb._solde_emelia = lambda: 850
    r = passe(budget_credits=5)
    verifie("5 crédits demandés → 5 appels au plus", appels["emelia"] <= 5,
            f"({appels['emelia']} appels)")
    verifie("l'arrêt est nommé", r.get("status") == "credits_epuises", f"({r.get('status')})")
    verifie("le nombre de non-traités est dit", "non traité" in (r.get("note") or ""),
            f"({r.get('note')})")

    print("\nLe solde réel borne le budget, même si on en demande plus")
    bb._solde_emelia = lambda: 3
    r = passe(budget_credits=100)
    verifie("solde 3 → 3 appels au plus", appels["emelia"] <= 3, f"({appels['emelia']})")
    verifie("le plafond retenu est le solde", r.get("plafond_credits") == 3,
            f"({r.get('plafond_credits')})")

    print("\nLe plancher de réserve est respecté")
    bb._solde_emelia = lambda: 10
    r = passe(plancher_credits=8)
    verifie("solde 10, plancher 8 → 2 appels au plus", appels["emelia"] <= 2,
            f"({appels['emelia']})")

    print("\nSolde à zéro : on ne part même pas")
    bb._solde_emelia = lambda: 0
    r = passe()
    verifie("aucun appel", appels["emelia"] == 0)
    verifie("arrêt annoncé", r.get("status") == "credits_epuises", f"({r.get('status')})")

    print("\nSolde illisible : on refuse de dépenser à l'aveugle")
    bb._solde_emelia = lambda: None
    r = passe()
    verifie("aucun appel", appels["emelia"] == 0)
    verifie("la passe est annulée", r.get("status") == "solde_emelia_illisible",
            f"({r.get('status')})")

    print("\nLe solde qui s'effondre en cours de passe arrête la boucle")
    etat = {"solde": 850, "vus": 0}

    def solde_qui_tombe():
        etat["vus"] += 1
        return 850 if etat["vus"] <= 1 else 0     # le contrôle périodique voit 0

    bb._solde_emelia = solde_qui_tombe
    r = passe(budget_credits=100)
    verifie("la boucle s'arrête au contrôle périodique",
            appels["emelia"] <= bb.CONTROLE_SOLDE_TOUS_LES,
            f"({appels['emelia']} appels, contrôle tous les {bb.CONTROLE_SOLDE_TOUS_LES})")
    verifie("l'arrêt est nommé", r.get("status") == "credits_epuises", f"({r.get('status')})")

    print("\nOn compte ce qui est FACTURÉ, pas ce qui est cherché")
    bb._solde_emelia = lambda: 850
    bb._emelia_find_email = faux_emelia_bredouille
    # Budget 1 → borne de rendement à 20 recherches, franchie par les 40 paires du jeu.
    # Avec un budget de 3 la borne valait 60 : la boucle finissait avant de l'atteindre et
    # le test passait sans rien vérifier.
    r = passe(budget_credits=1)
    verifie("une recherche infructueuse ne consomme pas le budget",
            appels["emelia"] > 1, f"({appels['emelia']} recherches pour 0 crédit)")
    verifie("le rendement anormal finit par arrêter la passe",
            r.get("status") == "rendement_trop_faible", f"({r.get('status')})")
    bb._emelia_find_email = faux_emelia

    print("\nÀ sec, rien n'est jamais appelé")
    bb._solde_emelia = lambda: 850
    appels["emelia"] = 0
    r = bb.run_dirigeant_segment("lcr", {"naf_code": {"include": ["68.31Z"]}},
                                 sector="immobilier", dept_code="44", max_companies=40,
                                 delay=0, use_emelia=True, dry_run=True)
    verifie("aucun appel payant en mode à sec", appels["emelia"] == 0)
    verifie("le coût est estimé", (r.get("cost_estimate") or {}).get("emelia_calls") == 40,
            f"({r.get('cost_estimate')})")

    (bb.count, bb.find, bb.fetch_dirigeants_by_siren,
     bb._emelia_find_email, bb._solde_emelia) = vrais

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:6])}")
        return 1
    print("Le garde-fou tient : aucun crédit ne peut être dépensé au-delà du solde.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
