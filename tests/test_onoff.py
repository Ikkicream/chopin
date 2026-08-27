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

    print("\nLe numéro de ligne, tel qu'on l'annonce")
    verifie("format international avec l'indicatif détaché",
            onoff.international("+33744306603") == "+33 7 44 30 66 03",
            f"(reçu : {onoff.international('+33744306603')})")
    verifie("le national reste distinct", onoff.lisible("+33744306603") == "07 44 30 66 03")
    verifie("drapeau français sur un +33", onoff.drapeau("+33612345678") == "🇫🇷")
    verifie("drapeau neutre hors France", onoff.drapeau("+14155552671") == "🌍")
    verifie("le numéro vient de la configuration, pas du code",
            "ONOFF_NUMERO_" in (RACINE / "scripts" / "onoff.py").read_text())

    print("\nCe que l'API attend vraiment (constaté le 2026-08-25, non documenté)")
    src_o = (RACINE / "scripts" / "onoff.py").read_text()
    # La doc écrit USED/AVAILABLE en majuscules ; l'API les refuse avec `invalid.status`.
    verifie("le statut des numéros part en minuscules", '(statut or "used").lower()' in src_o)
    # Sans dates, l'API rend `startDate.invalid` — ce qui ressemble à un paramètre erroné
    # alors que c'est une absence.
    verifie("les statistiques envoient toujours une période",
            '"startDate": depuis or' in src_o)
    # Les enveloppes réelles ne sont nommées nulle part dans la documentation.
    verifie("les enveloppes callLogs/messagesLogs sont reconnues",
            '"callLogs"' in src_o and '"messagesLogs"' in src_o)

    print("\nLes dates d'Onoff, telles qu'elles arrivent vraiment")
    # Constaté le 2026-08-25 sur la charge de validation : `"2026-08-25 14:01:43 CEST"`.
    # Ni ISO, ni UTC, fuseau en toutes lettres. PostgreSQL sait le lire, `strptime` NON.
    verifie("le format réel d'Onoff est accepté",
            onoff._horodatage("2026-08-25 14:01:43 CEST") == "2026-08-25 14:01:43 CEST")
    for v in ("2026-08-25T14:01:43Z", "2026-08-25T14:01:43+02:00", "2026-08-25"):
        verifie(f"format {v} accepté", onoff._horodatage(v) == v)
    # Le point qui compte : une date illisible ne doit coûter QUE la date. Si elle faisait
    # échouer l'INSERT, l'appel entier serait perdu sans que personne le sache.
    for v in ("n'importe quoi", "2026-13-45 99:99:99", ""):
        verifie(f"date rejetée sans exception : {v!r}", onoff._horodatage(v) is None)

    print("\nLa pastille du répondeur ne doit RIEN coûter à Onoff")
    api = (RACINE / "scripts" / "api.py").read_text()
    i = api.index("def api_onoff_pastille")
    corps = api[i:i + 1200]
    verifie("elle ne fait pas de sonde vivante", "verifier(" not in corps)
    verifie("elle lit le journal local", "o.resume(site)" in corps)
    verifie("elle porte la ligne à afficher", '"affichage"' in corps)

    print("\nLe bouton d'appel ne saute plus vers `tel:` tout seul")
    ui = RACINE.parent / "genesis-ui" / "src" / "components" / "actions-appel.tsx"
    if ui.exists():
        t = ui.read_text()
        # Un saut automatique ouvrait FaceTime sur macOS : ni ce qu'on veut, ni ce qu'on
        # avait annoncé, et l'appel ne partait pas de la ligne Onoff.
        verifie("aucune redirection automatique vers tel:",
                "window.location.href = r.tel" not in t)
        verifie("le numéro est proposé à la copie", "copierNumero" in t)
        verifie("l'extension Click2Call est proposée", "Click2Call" in t)
        verifie("le lien tel: reste disponible, mais explicite",
                "Ouvrir dans l" in t and "FaceTime" in t)
    else:
        print("  … composant introuvable, contrôle ignoré")

    print("\nÀ qui appartient chaque ligne")
    # L'attribution ne se lit PAS sur le numéro : `GET /numbers` ne rend que
    # {id, phoneNumber, countryCode}, et `GET /numbers/{id}` répond `invalid.id`. Elle vit
    # côté MEMBRE, dans `numberIdRefs` — il faut croiser les deux listes.
    verifie("le croisement numéros ↔ membres existe", hasattr(onoff, "lignes"))
    verifie("l'attribution est cherchée chez les membres",
            "numberIdRefs" in src and "par_numero" in src)
    api_src = (RACINE / "scripts" / "api.py").read_text()
    verifie("l'état de la page porte les lignes", 'out["lignes"] = o.lignes(site)' in api_src)
    ecran = RACINE.parent / "genesis-ui" / "src" / "app" / "site" / "[code]" / "onoff" / "page.tsx"
    if ecran.exists():
        t = ecran.read_text()
        verifie("le badge dit la DISPONIBILITÉ, pas seulement « bêta »",
                "indisponible — attribuée" in t and "ligne libre" in t)
        verifie("le titulaire est nommé", "utilisée par" in t and "titulaire" in t)
        verifie("les membres sans ligne sont listés", "membres_sans_ligne" in t)
        print("\nLa marche à suivre pour appeler")
        verifie("le guide Click2Call est en bas de page", "installer Click2Call" in t)
        verifie("il donne le lien du Chrome Web Store", "chromewebstore.google.com" in t)
        verifie("il prévient du piège FaceTime", "FaceTime sur Mac" in t)
        verifie("il dit pourquoi l'API ne compose pas", "404" in t)
    else:
        print("  … écran introuvable, contrôles ignorés")

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
