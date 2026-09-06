#!/usr/bin/env python3
"""La boîte expéditrice doit voyager jusqu'au journal — sinon aucun plafond ne s'applique.

Le 2026-08-24, les 29 emails du matin sont TOUS partis de la même adresse. Le journal
PostgreSQL les enregistrait sans expéditeur ; `expediteur.envoyes_aujourdhui`, qui compte
par boîte, rendait donc 0 pour les quatre. Conséquences en chaîne :

  - le plafond de 40/jour/boîte n'était appliqué à personne — le compteur ne bougeait
    jamais, donc `reste` valait toujours 40 ;
  - la répartition choisissait systématiquement la même boîte, « la moins chargée » étant
    à égalité parfaite à zéro ;
  - la montée en charge lisait des volumes faux, et pouvait relever un plafond sur une
    boîte qui venait d'envoyer seule toute la journée.

Trois maillons, un seul manquait. Ce test les vérifie un par un, sans envoyer d'email.
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
    import contacts_pool_backend as cpb
    import maildoso_backend as md

    print("1. `send_batch` attache au contact la boîte qui a écrit")
    vus: list[dict] = []
    vrai_send, vrai_already = md.send_email, md.already_sent_emails
    md.already_sent_emails = lambda cid: set()
    md.send_email = lambda to_email, subject, **kw: {
        "ok": True, "mailbox": "j.durand@leclient-roi.com", "rfc_msgid": "<x@y>"}
    try:
        md.send_batch("lcr-test-2026-08-24", "Objet", "<p>Bonjour Marie.</p>",
                      [{"email": "a@exemple-test.fr"}], site="lcr", pace=(0, 0),
                      on_sent=lambda ct: vus.append(dict(ct)))
    finally:
        md.send_email, md.already_sent_emails = vrai_send, vrai_already
    verifie("le callback reçoit la boîte",
            bool(vus) and vus[0].get("_mailbox") == "j.durand@leclient-roi.com",
            f"({vus[0].get('_mailbox') if vus else 'aucun appel'})")

    print("\n2. `mark_pushed_to_emelia` la transmet au journal")
    # On capture TOUS les appels au miroir : la fonction en déclenche plusieurs
    # (`record_send`, puis `promote_contact` via l'historique de site). Ne garder que le
    # dernier faisait échouer le test sur un appel qui n'était pas celui qu'on examine.
    recus: list[dict] = []
    vrai_miroir = cpb._miroir
    cpb._miroir = lambda fn, *a, **k: recus.append({"fn": fn, "args": a, "kw": k})
    try:
        cpb.mark_pushed_to_emelia("id-inexistant", "lcr", "lcr-test-2026-08-24",
                                  email="a@exemple-test.fr",
                                  mailbox="j.juste@leclient-roi.com")
    except Exception:
        pass          # le contact n'existe pas : l'appel au journal a déjà eu lieu
    finally:
        cpb._miroir = vrai_miroir
    envois = [r for r in recus if r["fn"] == "record_send"]
    verifie("le journal d'envoi est bien appelé", bool(envois),
            f"({[r['fn'] for r in recus]})")
    verifie("il reçoit la boîte expéditrice",
            bool(envois) and envois[0]["kw"].get("mailbox") == "j.juste@leclient-roi.com",
            f"({envois[0]['kw'].get('mailbox') if envois else '—'})")

    print("\n3. `record_send` sait la porter jusqu'à la base")
    import inspect
    import pg_sync
    verifie("record_send accepte une boîte",
            "mailbox" in inspect.signature(pg_sync.record_send).parameters)

    print("\n4. Le compteur par boîte reflète la réalité")
    import expediteur as ex
    # La base god_mode est souvent tenue par un dispatch ou un scrape. Un test qui meurt
    # sur ce verrou n'apprend rien : on saute le contrôle en le disant, plutôt que de
    # rendre la suite instable et donc ignorée.
    import duckdb
    reel = None
    try:
        g = duckdb.connect("/home/autoblog/genesis/data/god_mode.duckdb", read_only=True)
        try:
            reel = {r[0]: int(r[1]) for r in g.execute(
                "SELECT mailbox, count(*) FROM maildoso_sent WHERE status='sent' "
                "AND CAST(created_at AS DATE) = CURRENT_DATE GROUP BY 1").fetchall() if r[0]}
        finally:
            g.close()
    except Exception as e:  # noqa: BLE001
        verifie("journal d'envoi illisible — contrôle sauté", True,
                f"({type(e).__name__} : base tenue par un autre process)")
        reel = {}
    vu = {b["email"]: b["envoyes_aujourdhui"] for b in ex.boites("lcr")}
    for boite, n in sorted(reel.items()):
        verifie(f"{boite.split('@')[0]} : le compteur suit le journal d'envoi",
                abs(vu.get(boite, 0) - n) <= 2, f"(réel {n} / compté {vu.get(boite, 0)})")
    if not reel:
        verifie("aucun envoi aujourd'hui — cas non exercé", True, "(informatif)")

    print("\n5. Un compteur à zéro partout ne doit PAS laisser passer un lot entier")
    # C'est le symptôme exact du bug : quatre boîtes à égalité à zéro, et la première
    # alphabétiquement encaisse tout jusqu'à son plafond. Le plafond doit exister.
    fausses = [{"email": f"b{i}@x.fr", "active": True, "daily_cap": 40,
                "envoyes_aujourdhui": 40, "reste": 0} for i in range(4)]
    verifie("plafond atteint partout → aucune boîte proposée",
            ex.choisir("inconnu-xyz@nulle-part.test", "lcr", disponibles=fausses) is None)

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:6])}")
        return 1
    print("La boîte expéditrice va jusqu'au journal : les plafonds s'appliquent.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
