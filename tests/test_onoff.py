#!/usr/bin/env python3
"""Connecteur Onoff Business — ce qu'il promet doit être ce qu'il fait.

Deux familles de contrôles, pour deux risques distincts.

**L'honnêteté du connecteur.** L'API Onoff est en lecture seule : elle n'expose ni la
composition d'un appel, ni l'envoi d'un SMS, ni le solde du compte (vérifié le 2026-08-24
sur la navigation complète de la documentation officielle, et sur la page produit qui
range l'envoi de SMS dans les fonctions « à venir »). Un connecteur qui prétendrait le
contraire produirait des boutons morts. Les contrôles ci-dessous figent ce que le code
annonce.

**L'invariant de la messagerie.** Onoff peut REJOUER un log déjà envoyé. Sans précaution,
chaque rejeu remettrait en « non lu » un message déjà écouté, et le répondeur redeviendrait
plein tout seul. C'est le contrôle le plus important du fichier.
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

ECHECS: list[str] = []
PREFIXE = "autotest-onoff-"


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'✓' if condition else '✗'} {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def lance() -> int:
    import onoff
    import pool_pg

    print("\nNormalisation des numéros")
    # Le pool stocke du national, Onoff renvoie de l'international : sans conversion des
    # deux côtés, aucun rapprochement n'aboutit et l'historique reste vide.
    cas = [
        ("0428384508", "+33428384508"),
        ("04 28 38 45 08", "+33428384508"),
        ("04.28.38.45.08", "+33428384508"),
        ("0033428384508", "+33428384508"),
        ("+33428384508", "+33428384508"),
        ("33428384508", "+33428384508"),
        ("", ""),
    ]
    for brut, attendu in cas:
        verifie(f"{brut or '(vide)'} → {attendu or '(vide)'}", onoff.e164(brut) == attendu,
                f"(reçu : {onoff.e164(brut)})")
    verifie("relecture humaine par paires", onoff.lisible("+33428384508") == "04 28 38 45 08",
            f"(reçu : {onoff.lisible('+33428384508')})")

    print("\nCe que le connecteur annonce ne pas savoir faire")
    src = (RACINE / "scripts" / "onoff.py").read_text()
    # Un seul POST part vers Onoff dans tout le module : la tentative d'envoi de SMS.
    # Si un jour un autre apparaît, ce contrôle le signale — c'est la porte par laquelle
    # une action non supportée s'introduirait.
    posts = [l.strip() for l in src.splitlines() if 'methode="POST"' in l]
    verifie("un seul appel POST vers Onoff, et c'est l'envoi de SMS",
            len(posts) == 1 and "/api/v1/messages" in posts[0],
            f"({len(posts)} trouvé(s))")
    verifie("l'absence de composition est documentée",
            "PASSER un appel" in src and "aucun endpoint" in src)
    verifie("l'absence de solde est documentée", "CRÉDIT / SOLDE" in src)
    verifie("l'envoi de SMS rend un refus explicite, pas une panne",
            "indisponible" in src and "annoncé « à venir »" in src)

    routes = (RACINE / "scripts" / "api.py").read_text()
    verifie("la route SMS rend 501 (non implémenté côté Onoff), pas 500",
            '"indisponible": 501' in routes)
    verifie("l'écran est prévenu des capacités réelles",
            '"appeler": False' in routes and '"envoyer_sms": False' in routes
            and '"credit": False' in routes)

    print("\nSans clé, le connecteur refuse proprement")
    r = onoff.envoyer_sms("lcr", "+33756000000", "0428384508", "")
    verifie("message vide refusé", r.get("raison") == "vide")
    r = onoff.envoyer_sms("lcr", "+33756000000", "pas-un-numero", "coucou")
    verifie("numéro invalide refusé", r.get("raison") == "numero", f"(reçu : {r.get('raison')})")

    print("\nJournal local : typage des événements reçus")
    verifie("le schéma s'applique", onoff.assurer_schema())

    charges = {
        "vm": {"id": PREFIXE + "vm", "eventName": "VM", "externalNumber": "0428384508",
               "callStarted": "2026-08-24T09:00:00Z", "callDirection": "INBOUND",
               "callStatus": "VMS", "voicemailUrl": "https://x/1.mp3", "voicemailDuration": 30},
        "sms": {"id": PREFIXE + "sms", "eventName": "SMS", "externalNumber": "0612345678",
                "callStarted": "2026-08-24T10:00:00Z", "callDirection": "INBOUND",
                "text": "Rappelez-moi"},
        "cdr": {"id": PREFIXE + "cdr", "eventName": "CDR", "externalNumber": "0428384508",
                "callStarted": "2026-08-24T11:00:00Z", "callDirection": "OUTBOUND",
                "callStatus": "ANSWERED", "callDuration": 120},
        # Une messagerie annoncée sans eventName VM : Onoff utilise les deux chemins.
        "vms": {"id": PREFIXE + "vms", "externalNumber": "0499999999",
                "callStarted": "2026-08-24T12:00:00Z", "callDirection": "INBOUND",
                "callStatus": "VMS", "voicemailUrl": "https://x/2.mp3"},
    }
    try:
        for k, c in charges.items():
            res = onoff.enregistrer_evenement("lcr", c)
            verifie(f"{k} accepté", res.get("ok"), f"→ type {res.get('type')}")
        verifie("statut VMS reconnu comme messagerie même sans eventName",
                onoff.enregistrer_evenement("lcr", charges["vms"]).get("type") == "VM")

        print("\nL'invariant : un rejeu ne réveille pas un message écouté")
        avant = onoff.compter_non_lus("lcr")
        verifie("les deux messageries sont non lues", avant >= 2, f"({avant})")
        onoff.marquer_lu("lcr", PREFIXE + "vm")
        apres = onoff.compter_non_lus("lcr")
        verifie("marquer écouté décrémente", apres == avant - 1, f"({avant} → {apres})")
        onoff.enregistrer_evenement("lcr", charges["vm"])          # Onoff rejoue le même log
        verifie("le rejeu ne remet PAS en non lu", onoff.compter_non_lus("lcr") == apres,
                f"({onoff.compter_non_lus('lcr')} attendu {apres})")

        print("\nCohérence des compteurs")
        onoff.marquer_lu("lcr", PREFIXE + "vm", lu=False)
        verifie("on peut remettre en non lu", onoff.compter_non_lus("lcr") == avant)

        print("\nIsolation entre sites")
        # Une marque posée depuis un autre site ne doit pas toucher cet événement.
        r = onoff.marquer_lu("mkd", PREFIXE + "vm")
        verifie("marquer depuis le mauvais site ne fait rien", not r.get("ok"))

        print("\nRegroupement et filtres")
        fils = onoff.fils_sms("lcr")["fils"]
        verifie("les SMS sont groupés par interlocuteur", len(fils) >= 1)
        ap = onoff.appels("lcr", numero="0428384508")["appels"]
        verifie("le filtre par numéro accepte le format national", len(ap) >= 2, f"({len(ap)})")
        verifie("un SMS n'est pas compté comme un appel",
                all(a["type"] != "SMS" for a in ap))
    finally:
        n = pool_pg._ecrire("DELETE FROM onoff_evenements WHERE id LIKE %(p)s",
                            {"p": PREFIXE + "%"})
        print(f"\n  (nettoyage : {n} ligne(s) de test supprimée(s))")

    print("\nBranchement dans la plateforme")
    import roles_backend as rbk
    cles = [p["cle"] for p in rbk.PAGES]
    verifie("la page Téléphonie est déclarée", "onoff" in cles)
    verifie("la page Répondeur est déclarée", "onoff_messagerie" in cles)
    verifie("les deux sont en bêta fermée",
            {"onoff", "onoff_messagerie"} <= rbk.pages_beta())
    verifie("un compte hors bêta est bloqué",
            bool(rbk.beta_interdite("/api/sites/lcr/onoff/etat", "un-inconnu", "lcr")))
    for r_ in ("/api/sites/{site}/onoff/etat", "/api/sites/{site}/onoff/messagerie",
               "/api/webhook/onoff/{site}", "/api/sites/{site}/onoff/appel"):
        verifie(f"route {r_}", r_ in routes)
    verifie("le webhook passe par le jeton en query (mécanisme existant)",
            '"/webhook" in path' in routes)

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:6])}")
        return 1
    print("Le connecteur Onoff dit ce qu'il fait, et le répondeur ne se remplit pas tout seul.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
