#!/usr/bin/env python3
"""La marque dans le nom d'expéditeur (Lot D, 2026-08-26).

Le constat de Camille : « la marque n'est identifiée nulle part ». Un inconnu recevait un
email d'une personne inconnue, d'une société qu'il ne voyait qu'en signature — donc APRÈS
avoir ouvert. Les quatre boîtes s'appelaient « Juliette Bernard », « Juliette Durand »…

Deux pistes existaient. La marque dans l'OBJET a été écartée : les données la
déconseillent (nom d'entreprise en objet, 38 % d'ouverture, la pire catégorie utile). Le
nom d'EXPÉDITEUR, lui, est visible dans toute boîte de réception avant même l'ouverture,
et ne coûte pas un caractère d'objet. C'est la piste retenue.

Le piège, traité AVANT ce script : `maildoso_backend._split_name` alimente
`{{expediteur_nom}}`, qui SIGNE le message. Sans découpe de la marque, le nom de famille
serait devenu « Durand · LeClientROI » et aurait signé chaque email. `_sans_marque` coupe
donc sur « · », « | », « — », « – » et « - » avant de séparer prénom et nom.

Les deux stockages sont mis à jour. PostgreSQL fait foi (`expediteur.choisir`), DuckDB est
le repli de `maildoso_backend._pick_mailbox` : n'en renommer qu'un, c'est garantir qu'un
jour de panne les emails repartiront sous l'ancien nom.

Usage :
    python3 scripts/marque_expediteur.py               # simulation
    python3 scripts/marque_expediteur.py --apply
    python3 scripts/marque_expediteur.py --retirer     # revient en arrière
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

MARQUE = "LeClientROI"
SEPARATEUR = " · "


def _dsn() -> str:
    for ligne in (RACINE / ".env").read_text().splitlines():
        if ligne.startswith("PG_DSN="):
            return ligne.split("=", 1)[1].strip()
    raise SystemExit("PG_DSN introuvable")


def _sans_marque(nom: str) -> str:
    import maildoso_backend as md
    return md._sans_marque(nom)


def _avec_marque(nom: str) -> str:
    base = _sans_marque(nom)
    return f"{base}{SEPARATEUR}{MARQUE}" if base else base


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--retirer", action="store_true",
                    help="enlève la marque et remet le nom seul")
    args = ap.parse_args()
    transformer = _sans_marque if args.retirer else _avec_marque

    import psycopg2  # type: ignore
    import duckdb

    print(f"Marque dans le nom d'expéditeur — "
          f"{'RETRAIT' if args.retirer else 'POSE'}, "
          f"{'APPLIQUÉ' if args.apply else 'SIMULATION'}\n")

    changements: list[tuple[str, str, str]] = []
    cx = psycopg2.connect(_dsn())
    try:
        with cx, cx.cursor() as cur:
            cur.execute("SELECT email, sender_name FROM mailboxes ORDER BY email")
            for email, nom in cur.fetchall():
                voulu = transformer(nom or "")
                if voulu and voulu != (nom or ""):
                    changements.append((email, nom or "", voulu))
                    if args.apply:
                        cur.execute("UPDATE mailboxes SET sender_name = %s WHERE email = %s",
                                    (voulu, email))
            if not args.apply:
                cx.rollback()
    finally:
        cx.close()

    print(f"  PostgreSQL : {len(changements)} boîte(s)")
    for email, avant, apres in changements:
        print(f"    {email:<32} « {avant} »  →  « {apres} »")

    # DuckDB : le repli. Il ne porte que les boîtes ad hoc, c'est normal.
    n_duck = 0
    try:
        c = duckdb.connect(str(RACINE / "data" / "god_mode.duckdb"))
        try:
            for email, nom in c.execute(
                    "SELECT email, sender_name FROM mailboxes ORDER BY email").fetchall():
                voulu = transformer(nom or "")
                if voulu and voulu != (nom or ""):
                    n_duck += 1
                    if args.apply:
                        c.execute("UPDATE mailboxes SET sender_name=? WHERE email=?",
                                  [voulu, email])
        finally:
            c.close()
        print(f"\n  DuckDB (repli) : {n_duck} boîte(s)")
    except Exception as e:  # noqa: BLE001
        print(f"\n  DuckDB indisponible ({type(e).__name__}: {e}) — "
              f"le repli garderait l'ancien nom, à relancer.")
        return 1

    if not args.apply:
        print("\n  → SIMULATION : rien n'a été écrit.")
    else:
        print("\n  → écrit dans les deux stockages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
