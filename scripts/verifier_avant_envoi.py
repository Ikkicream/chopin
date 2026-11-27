#!/usr/bin/env python3
"""Le message est-il TOUJOURS le bon ? À lancer avant de relancer un dispatch.

Écrit le 2026-08-26, après une journée où le message d'une campagne en cours a changé
quatre fois sous ses pieds : lien LinkedIn ajouté, marque posée dans le nom d'expéditeur,
règle des liens relevée, fenêtre d'envoi alignée. Chacune de ces modifications était
voulue ; leur cumul, non vérifié, ne l'était pas.

Ce script rejoue **exactement les contrôles du dispatch**, sur le message **emballé**
— celui qui part réellement, pied de page légal compris — et non sur le corps stocké. La
différence n'est pas cosmétique : le corps stocké porte trois liens, l'emballé en porte
quatre, et c'est le quatrième qui aurait bloqué le lot.

Il vérifie en plus ce que le dispatch ne regarde pas :
  - chaque lien répond vraiment (un lien mort dans un cold email, c'est un signalement) ;
  - la signature n'a pas été abîmée par la marque accolée au nom d'expéditeur ;
  - les deux cas de personnalisation rendent un texte propre, sans marqueur résiduel ;
  - la désinscription est présente.

Usage :
    python3 scripts/verifier_avant_envoi.py                     # la campagne en cours
    python3 scripts/verifier_avant_envoi.py --modele cold:retail:first
    python3 scripts/verifier_avant_envoi.py --sans-reseau       # saute le test des liens
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

PROBLEMES: list[str] = []
ALERTES: list[str] = []


def ok(nom: str, condition: bool, detail: str = "") -> bool:
    print(f"  {'✓' if condition else '✗'}  {nom} {detail}")
    if not condition:
        PROBLEMES.append(nom)
    return condition


def alerte(nom: str, detail: str = "") -> None:
    print(f"  !  {nom} {detail}")
    ALERTES.append(nom)


def _dsn() -> str:
    for ligne in (RACINE / ".env").read_text().splitlines():
        if ligne.startswith("PG_DSN="):
            return ligne.split("=", 1)[1].strip()
    raise SystemExit("PG_DSN introuvable")


def campagne_en_cours() -> dict | None:
    import psycopg2  # type: ignore
    cx = psycopg2.connect(_dsn())
    try:
        with cx, cx.cursor() as cur:
            cur.execute("SELECT legacy_id, name, message_id, subject, sent_count, "
                        "target_size FROM campaigns WHERE status = 'running' "
                        "ORDER BY created_at DESC LIMIT 1")
            r = cur.fetchone()
    finally:
        cx.close()
    if not r:
        return None
    return {"legacy_id": r[0], "nom": r[1], "message_id": r[2], "subject": r[3],
            "envoyes": r[4], "cible": r[5]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", default="lcr")
    ap.add_argument("--modele", default="")
    ap.add_argument("--objet", default="")
    ap.add_argument("--sans-reseau", action="store_true")
    args = ap.parse_args()

    import html_templates_backend as htb
    import qualite_message as qm
    import maildoso_backend as md
    import expediteur as ex
    import email_lint_backend as lint
    import garde_variables as gvar
    import fenetre_envoi as fen

    modele, objet, camp = args.modele, args.objet, None
    if not modele:
        camp = campagne_en_cours()
        if not camp:
            print("Aucune campagne en cours et aucun --modele : rien à vérifier.")
            return 1
        modele, objet = camp["message_id"], camp["subject"]
        print(f"Campagne « {camp['nom']} » — {camp['envoyes']}/{camp['cible']} envoyés")
    print(f"Modèle : {modele}\nObjet   : {objet}\n")

    resolu = htb.resolve_campaign_message(args.site, modele)
    html = (resolu or {}).get("html") or ""
    if not ok("le message se résout", bool(html)):
        return 1

    print("\n— Les contrôles que le dispatch applique —")
    premier = modele.startswith("cold:") and modele.endswith(":first")
    verdict = lint.run_lint(html)
    ok("contrôle anti-spam (lint) non bloquant", not verdict.get("blocking"),
       f"({[i.get('rule') for i in (verdict.get('issues') or []) if i.get('severity') == 'error'][:3]})")
    qual = qm.controler(objet or "", html, premier_contact=premier)
    ok(f"vocabulaire et forme (premier_contact={premier})", qual["ok"], f"({qual['bloquants']})")
    inconnues = gvar.variables_inconnues(html) | gvar.variables_inconnues(objet or "")
    ok("aucune variable qu'aucun moteur ne sait remplir", not inconnues, f"({inconnues})")

    print("\n— Ce qui part vraiment —")
    boites = ex.boites(args.site)
    boite = next((b for b in boites if b.get("usage") == "adhoc"), boites[0] if boites else {})
    entete = f"{boite.get('sender_name', '')} <{boite.get('email', '')}>"
    ok("l'expéditeur porte la marque", "·" in entete or "LeClientROI" in entete, f"« {entete} »")
    prenom_exp, nom_exp = md._split_name(boite.get("sender_name", ""))
    ok("la signature reste le nom de la personne, sans la marque",
       "LeClientROI" not in f"{prenom_exp} {nom_exp}", f"« {prenom_exp} {nom_exp} »")

    cas = [("avec prénom", {"email": "m.dupont@exemple.fr", "prenom": "Marc", "nom": "Dupont",
                            "societe": "Agence Dupont", "city": "Nantes"}),
           ("sans prénom", {"email": "contact@exemple.fr", "prenom": "", "nom": "",
                            "societe": "Agence Dupont", "city": "Nantes"})]
    rendus = []
    for libelle, ct in cas:
        rendu = md._apply_tokens(qm.conditionnel(qm.spintax(html, ct["email"]), ct), ct, boite)
        obj = md._apply_tokens(qm.conditionnel(qm.spintax(objet or "", ct["email"]), ct), ct, boite)
        rendus.append((libelle, obj, rendu))
        texte = qm._texte(rendu)
        residus = re.findall(r"\{\{[^}]*\}\}", rendu) + re.findall(r"\{\{[^}]*\}\}", obj)
        ok(f"[{libelle}] aucun marqueur résiduel", not residus, f"({residus[:3]})")
        ok(f"[{libelle}] pas de salutation vide", "Bonjour ," not in texte and "Bonjour  " not in texte)
        ok(f"[{libelle}] la désinscription est présente",
           "unsubscribe" in rendu.lower() or "désinscri" in texte.lower()
           or "desinscri" in texte.lower())
        ok(f"[{libelle}] la signature est là", (nom_exp or prenom_exp) in texte,
           f"(cherché « {nom_exp or prenom_exp} »)")

    print("\n— Les liens —")
    urls = qm.liens(html)
    print(f"  {len(urls)} lien(s), maximum {qm.LIENS_MAX_PREMIER} au premier contact")
    if args.sans_reseau:
        for u in urls:
            print(f"     · {u}")
    else:
        import urllib.request
        import urllib.error
        for u in urls:
            propre = re.sub(r"\{\{[^}]*\}\}", "", u)
            try:
                req = urllib.request.Request(propre, method="HEAD",
                                             headers={"User-Agent": "Mozilla/5.0 (verif-cheffer)"})
                with urllib.request.urlopen(req, timeout=12) as r:
                    code = r.status
                ok(f"{propre[:66]}", 200 <= code < 400, f"(HTTP {code})")
            except urllib.error.HTTPError as e:
                # Trois codes ne disent RIEN sur la validité du lien :
                #   405 — HEAD refusé, la page répond très bien en GET ;
                #   403 — pare-feu applicatif devant un client non-navigateur ;
                #   999 — code maison de LinkedIn, renvoyé à tout ce qui n'est pas un
                #         navigateur, que la page existe ou non.
                # Les compter comme des échecs rendrait ce contrôle impossible à passer —
                # et un contrôle qu'on ne peut jamais satisfaire finit débranché. On les
                # signale pour vérification humaine.
                if e.code in (403, 405, 999):
                    alerte(f"{propre[:66]}", f"(HTTP {e.code} — à ouvrir à la main)")
                else:
                    ok(f"{propre[:66]}", False, f"(HTTP {e.code})")
            except Exception as e:  # noqa: BLE001
                ok(f"{propre[:66]}", False, f"({type(e).__name__})")

    print("\n— L'heure et la capacité —")
    profil = fen.profil_pour(f"{args.site}-x-2026-01-01-x-x", None)
    ouverte, motif = fen.ouverte(profil)
    print(f"  fenêtre {profil} : {'OUVERTE' if ouverte else 'FERMÉE'} {motif}")
    reste = md.remaining_quota_today(args.site)
    print(f"  envois encore disponibles aujourd'hui : {reste}")

    print("\n" + "=" * 64)
    if PROBLEMES:
        print(f"{len(PROBLEMES)} PROBLÈME(S) — ne pas envoyer :")
        for p in PROBLEMES:
            print(f"   ✗ {p}")
        return 1
    if ALERTES:
        print(f"Aucun problème bloquant. {len(ALERTES)} point(s) à regarder à la main :")
        for a in ALERTES:
            print(f"   ! {a}")
    else:
        print("Le message est bon. Rien ne s'oppose à l'envoi.")
    if not ouverte:
        print(f"\nMais la fenêtre est fermée : {motif}")
    elif reste <= 0:
        print("\nMais il ne reste aucun envoi disponible aujourd'hui.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
