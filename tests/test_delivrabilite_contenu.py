#!/usr/bin/env python3
"""Le contenu des emails, mesuré contre le guide de délivrabilité de Maildoso.

Analysé le 2026-08-25. Le guide tient en onze recommandations ; ce fichier fige les quatre
qui ont été retenues, plus l'option de suivi.

Ce que le guide dit, et pourquoi c'est ici :
  - **mots à risque** : « zéro tolérance ». Aucun contrôle n'existait — le lint en place
    (`email_generator.BANNED`) traque des clichés de style, pas le vocabulaire que les
    filtres notent. Deux sujets différents, deux listes différentes ;
  - **spintax** : deux destinataires ne doivent jamais recevoir le même texte exact, un
    message identique mille fois se reconnaissant par empreinte ;
  - **liens et images au premier contact** : à éviter. Mesuré avant correction : 2,4 liens
    en moyenne sur les huit premiers messages de LCR, et une signature en image ;
  - **signature** : sans photo, sans lien, sans domaine.

Le suivi d'ouverture, lui, n'est PAS retiré : c'est lui qui alimente les commerciaux en
ouvreurs et qui déclenche l'alerte sur la pente. Il devient une option, par scénario.
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'✓' if condition else '✗'} {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def lance() -> int:
    import qualite_message as q

    print("\nLe spintax varie, mais reste le même pour une même personne")
    g = "Bonjour {{prenom}}, {je me demandais|je voulais savoir} si {{entreprise}} est concernée."
    a1, a2 = q.spintax(g, "a@x.fr"), q.spintax(g, "a@x.fr")
    b1 = q.spintax(g, "b@x.fr")
    verifie("un même destinataire obtient toujours le même texte", a1 == a2)
    verifie("la variation existe entre destinataires",
            len({q.spintax(g, f"{i}@x.fr") for i in range(30)}) > 1)
    # Le tirage doit survivre au redémarrage : `hash()` est salé par processus, donc une
    # relance aurait été rédigée autrement que le premier message reçu par la personne.
    import subprocess
    autre = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(RACINE / 'scripts')!r});"
         f"import qualite_message as q; print(q.spintax({g!r}, 'a@x.fr'))"],
        capture_output=True, text=True).stdout.strip()
    verifie("le tirage survit à un autre processus (hachage stable)", autre == a1,
            "(sinon une relance ne ressemblerait pas au message déjà reçu)")

    print("\nLe spintax ne dévore pas la personnalisation")
    verifie("{{prenom}} traverse intact", "{{prenom}}" in a1)
    verifie("{prenom} sans pipe n'est pas un choix",
            q.spintax("Bonjour {prenom}", "x") == "Bonjour {prenom}")
    verifie("un texte sans spintax est rendu tel quel",
            q.spintax("Bonjour, comment allez-vous ?", "x") == "Bonjour, comment allez-vous ?")

    print("\nLes mots qui pèsent sur la note de spam")
    v = q.controler("Offre exceptionnelle", "<p>Cliquez ici pour un service 100% gratuit</p>")
    verifie("les termes notoires sont bloquants", not v["ok"], f"({len(v['bloquants'])} motif(s))")
    v2 = q.controler("Votre prospection", "<p>Bonjour, un point rapide sur vos mandats ?</p>")
    verifie("un message sobre passe", v2["ok"], f"({v2['bloquants']})")
    v3 = q.controler("URGENT PROMO", "<p>Bonjour !!</p>")
    verifie("capitales et exclamations sont signalées", len(v3["avertissements"]) >= 2,
            f"({v3['avertissements']})")

    print("\nLe premier message reste sobre")
    deux = ('<p>Bonjour</p><p><a href="https://leclientroi.com">nous</a> — '
            '<a href="https://api.cheffer.email/api/book/lcr">un rendez-vous</a></p>')
    # Deux liens sont ACCEPTÉS depuis le 2026-08-25 : le lint impose le CTA de rendez-vous,
    # et Camille a demandé que le lien vers leclientroi.com soit toujours présent. Le seuil
    # reste bas pour que le troisième, lui, soit refusé — c'est lui qui ferait un tract.
    verifie("les deux liens attendus passent",
            q.controler("x", deux, premier_contact=True)["ok"])
    # Seuil passé de 2 à 4 le 2026-08-26, sur décision de Camille. Le message EMBALLÉ en
    # porte quatre : page du secteur, prise de rendez-vous, LinkedIn (demandé le 26/08) et
    # lien de marque ajouté par `wrap_cold_email`. Le corps stocké n'en montre que trois —
    # c'est ce décalage qui aurait bloqué le dispatch si on avait plafonné à trois.
    quatre = deux[:-4] + ('<a href="https://exemple.fr/a">a</a>'
                          '<a href="https://exemple.fr/b">b</a></p>')
    verifie("les quatre liens réellement envoyés passent",
            q.controler("x", quatre, premier_contact=True)["ok"],
            f"({q.controler('x', quatre, premier_contact=True)['bloquants']})")
    cinq = quatre[:-4] + '<a href="https://exemple.fr/c">et encore</a></p>'
    verifie("un CINQUIÈME lien au premier contact est refusé",
            not q.controler("x", cinq, premier_contact=True)["ok"])
    verifie("les mêmes deux liens passent en relance",
            q.controler("x", deux, premier_contact=False)["ok"])
    verifie("une image au premier contact est refusée",
            not q.controler("x", '<p><img src="https://x/y.png"></p>', premier_contact=True)["ok"])
    verifie("le lien de désinscription n'est jamais compté",
            q.controler("x", '<p><a href="https://x/unsubscribe">stop</a></p>',
                        premier_contact=True)["liens"] == 0)

    print("\nLes modèles réellement enregistrés")
    import duckdb, time
    con = None
    for _ in range(10):
        try:
            con = duckdb.connect(str(RACINE / "data" / "god_mode.duckdb"), read_only=True)
            break
        except Exception:  # noqa: BLE001
            time.sleep(3)
    if con is None:
        print("  … base occupée, contrôle des modèles ignoré")
    else:
        try:
            lignes = con.execute(
                "SELECT site_code, sector, kind, subject, body_html FROM email_templates"
            ).fetchall()
        finally:
            con.close()
        fautifs = []
        for site, sec, kind, subj, html in lignes:
            r = q.controler(subj or "", html or "", premier_contact=(kind == "first"))
            if not r["ok"]:
                fautifs.append(f"{site}/{sec}/{kind}: {r['bloquants'][0]}")
        verifie(f"aucun des {len(lignes)} modèles n'est bloquant", not fautifs,
                f"({fautifs[:2]})")
        images = [f"{s}/{sec}/{k}" for s, sec, k, _, h in lignes if "<img" in (h or "")]
        verifie("plus aucune image dans les modèles", not images, f"({images[:3]})")

    print("\nLa signature est en texte, plus en image")
    for fichier in ("god_mode_templates.py", "api.py"):
        src = (RACINE / "scripts" / fichier).read_text()
        verifie(f"{fichier} n'appose plus l'image de signature",
                "1778073002600-signature.png" not in src)

    print("\nLe suivi d'ouverture est une OPTION, pas une suppression")
    md = (RACINE / "scripts" / "maildoso_backend.py").read_text()
    verifie("send_email accepte l'option", "suivi_ouverture: bool = True" in md)
    verifie("le pixel n'est posé que si elle est vraie", "if not suivi_ouverture:" in md)
    verifie("les CLICS restent mesurés quoi qu'il arrive",
            md.index("if not suivi_ouverture:") > md.index("_re.sub(r'(href=)"),
            "(la réécriture des liens précède la sortie anticipée)")
    verifie("le défaut reste le suivi actif", "suivi_ouverture: bool = True" in md)
    mz = (RACINE / "scripts" / "mozart.py").read_text()
    verifie("Mozart lit l'option de son scénario", 'sc.get("suivi_ouverture")' in mz)
    sch = (RACINE / "scripts" / "mozart_schema.sql").read_text()
    verifie("la colonne existe et vaut vrai par défaut",
            "suivi_ouverture boolean NOT NULL DEFAULT true" in sch)

    print("\nLe premier email ne reçoit plus le lien secteur à la génération")
    eg = (RACINE / "scripts" / "email_generator.py").read_text()
    verifie("le lien secteur est réservé aux relances",
            "if i > 0:" in eg and "_ensure_sector_link" in eg)

    print("\nLa garde avant lot refuse un message à risque")
    ce = (RACINE / "scripts" / "campaign_engine.py").read_text()
    verifie("le contrôle de vocabulaire est appelé", "qualite_message as qmsg" in ce)
    verifie("un terme notoire arrête le lot", 'qual["bloquants"]' in ce)
    verifie("l'absence de spintax est signalée sans bloquer",
            'qual["variantes"] == 1' in ce and "message sans spintax" in ce)

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:6])}")
        return 1
    print("Le contenu suit le guide Maildoso, sans perdre la mesure des ouvertures.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
