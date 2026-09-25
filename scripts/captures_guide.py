#!/usr/bin/env python3
"""Refaire toutes les captures d'écran du guide, par rôle. Une commande, une repasse.

Demande de Camille (2026-08-26) : « il faudra faire une repasse chaque fois qu'il y a une
mise à jour des pages ». Les captures prises à la main vieillissent en silence — sur les
onze que le guide réclamait, une seule existait, datée du 9 juillet, et trois visaient des
écrans que la fusion cold email / newsletters venait de faire disparaître.

Le plan n'est écrit nulle part : il est DÉDUIT de `roles_backend.PAGES` et de la matrice
des droits. Ajouter une page au catalogue suffit donc à la faire photographier au passage
suivant, pour chacun des rôles qui la voit — et une page retirée cesse d'être prise.

## Les sessions

Photographier une page demande d'y être connecté. Le script crée une session
**temporaire** par rôle, directement dans `auth.duckdb`, et **la supprime à la fin, même
en cas d'erreur**. Elles durent 30 minutes au lieu des 7 jours d'une session normale, et
portent un préfixe reconnaissable pour qu'un jeton oublié se voie tout de suite.

Aucun mot de passe n'est demandé ni stocké. Les jetons ne sont jamais affichés.

## Usage

    python3 scripts/captures_guide.py --lister        # ce qui SERAIT pris, sans rien faire
    python3 scripts/captures_guide.py                 # la repasse complète
    python3 scripts/captures_guide.py --role admin    # un seul rôle
    python3 scripts/captures_guide.py --nettoyer      # supprime les sessions oubliées
"""
from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

AUTH_DB = RACINE / "data" / "auth.duckdb"
SORTIE = RACINE.parent / "genesis-ui" / "public" / "guide"
OUTIL = Path("/home/autoblog/outils-captures/captures.mjs")
# L'URL PUBLIQUE, et non `127.0.0.1:3100`. `NEXT_PUBLIC_API_URL` est vide : l'interface
# appelle son API en chemin relatif, et c'est nginx qui route `/api/…` vers le port 8080.
# Attaquer le serveur Next directement donne donc des écrans vides — « Liste indisponible »
# sur les cinq premières captures — parce que rien ne répond aux appels de données.
# Passer par le nom public fait voir exactement ce qu'un utilisateur voit.
BASE = "https://api.cheffer.email"
SITE = "lcr"

# Une session de capture vit 30 minutes, pas 7 jours. Le préfixe rend un jeton oublié
# visible d'un coup d'œil dans la table — et `--nettoyer` sait alors quoi supprimer.
PREFIXE = "capture-"
DUREE = timedelta(minutes=30)

# Un compte par rôle à photographier. Le rôle vient de la table `users` : on ne crée aucun
# compte, on emprunte ceux qui existent.
COMPTES_PAR_ROLE = {
    "superadmin": "camille",
    "admin": "Gilles",
    "user": "Romeo",
    "commercial": "test",
}


def _conn(lecture_seule: bool = False):
    import duckdb
    return duckdb.connect(str(AUTH_DB), read_only=lecture_seule)


def _comptes() -> dict[str, str]:
    """{role: user_id} pour les comptes existants, non désactivés."""
    c = _conn(lecture_seule=True)
    try:
        lignes = c.execute("SELECT id, username, role, disabled FROM users").fetchall()
    finally:
        c.close()
    par_nom = {u.lower(): (uid, role) for uid, u, role, d in lignes if not d}
    out = {}
    for role, nom in COMPTES_PAR_ROLE.items():
        trouve = par_nom.get(nom.lower())
        if trouve and trouve[1] == role:
            out[role] = trouve[0]
        elif trouve:
            print(f"  ! le compte « {nom} » n'a pas le rôle {role} mais {trouve[1]} — ignoré")
        else:
            print(f"  ! aucun compte « {nom} » pour le rôle {role} — ignoré")
    return out


def _plan(roles: dict[str, str], seulement: str = "") -> list[dict]:
    """Ce qu'il faut photographier : déduit du catalogue, jamais écrit à la main."""
    import roles_backend as rbk
    par_cle = {p["cle"]: p for p in rbk.PAGES}
    beta = rbk.pages_beta()
    plan = []
    for role in roles:
        if seulement and role != seulement:
            continue
        pages = []
        for cle in rbk.pages_autorisees(role):
            p = par_cle.get(cle)
            if not p:
                continue
            # Une page en bêta fermée s'ouvrirait sur un refus : la photographier
            # donnerait une capture du message d'interdiction, pas de l'écran.
            if cle in beta and role != "superadmin":
                continue
            pages.append({"cle": cle, "label": p["label"],
                          "url": p["url"].replace("{site}", SITE)})
        if pages:
            # `compte` voyage jusqu'au navigateur : la clé de la fenêtre « Voici ta
            # journée » porte le nom d'utilisateur, il faut le même pour la marquer vue.
            plan.append({"role": role, "compte": COMPTES_PAR_ROLE[role],
                         "pages": sorted(pages, key=lambda x: x["cle"])})
    return plan


def _creer_sessions(roles: dict[str, str], plan: list[dict]) -> dict[str, str]:
    jetons = {}
    expire = (datetime.now(timezone.utc) + DUREE).isoformat()
    c = _conn()
    try:
        for entree in plan:
            role = entree["role"]
            jeton = PREFIXE + secrets.token_urlsafe(32)
            c.execute("INSERT INTO sessions (token, user_id, created_at, expires_at) "
                      "VALUES (?, ?, ?, ?)",
                      [jeton, roles[role], datetime.now(timezone.utc).isoformat(), expire])
            jetons[role] = jeton
    finally:
        c.close()
    return jetons


def _supprimer_sessions() -> int:
    """Supprime TOUTES les sessions de capture, y compris celles d'un passage interrompu."""
    c = _conn()
    try:
        avant = c.execute("SELECT count(*) FROM sessions WHERE token LIKE ?",
                          [PREFIXE + "%"]).fetchone()[0]
        c.execute("DELETE FROM sessions WHERE token LIKE ?", [PREFIXE + "%"])
    finally:
        c.close()
    return int(avant or 0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--role", default="", help="ne traiter qu'un rôle")
    ap.add_argument("--lister", action="store_true", help="afficher le plan sans rien faire")
    ap.add_argument("--nettoyer", action="store_true",
                    help="supprimer les sessions de capture oubliées, puis sortir")
    ap.add_argument("--attente-ms", type=int, default=2500)
    args = ap.parse_args()

    if args.nettoyer:
        print(f"{_supprimer_sessions()} session(s) de capture supprimée(s).")
        return 0

    roles = _comptes()
    if not roles:
        print("Aucun compte utilisable — rien à photographier.")
        return 1
    plan = _plan(roles, args.role)
    total = sum(len(e["pages"]) for e in plan)
    print(f"{total} capture(s) à prendre, sur {len(plan)} rôle(s) :")
    for e in plan:
        print(f"  {e['role']:<12} {len(e['pages']):>2} pages — "
              + ", ".join(p["cle"] for p in e["pages"][:6])
              + (" …" if len(e["pages"]) > 6 else ""))
    if args.lister:
        return 0
    if not OUTIL.exists():
        print(f"\nOutil de capture introuvable : {OUTIL}")
        return 1

    # Les sessions oubliées d'un passage précédent partent d'abord : deux jetons valides
    # pour le même compte, c'est un de trop.
    oubliees = _supprimer_sessions()
    if oubliees:
        print(f"\n({oubliees} session(s) de capture d'un passage précédent supprimée(s))")

    jetons = _creer_sessions(roles, plan)
    fichier = None
    try:
        charge = {"base": BASE, "sortie": str(SORTIE), "attente_ms": args.attente_ms,
                  "roles": [{**e, "token": jetons[e["role"]]} for e in plan]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as f:
            json.dump(charge, f)
            fichier = f.name
        print(f"\nCaptures vers {SORTIE}\n")
        r = subprocess.run(["node", str(OUTIL), fichier], cwd=str(OUTIL.parent))
        code = r.returncode
    finally:
        # Le `finally` est le cœur de ce script : une session de capture qui survit à une
        # interruption est un jeton d'accès en liberté.
        n = _supprimer_sessions()
        print(f"\n{n} session(s) temporaire(s) supprimée(s).")
        if fichier:
            try:
                Path(fichier).unlink()
            except OSError:
                pass
    return code


if __name__ == "__main__":
    raise SystemExit(main())
