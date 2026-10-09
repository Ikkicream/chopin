#!/usr/bin/env python3
"""La maintenance doit fermer la plateforme, pas seulement sa porte d'entrée.

Jusqu'au 2026-08-25, `login_allowed()` ne gardait que le login : une session déjà ouverte
continuait de naviguer pendant une correction. Les menus répondaient 500, les appels
partaient pour rien, et les gens finissaient par téléphoner. Demande de Camille : « au lieu
de faire galérer tout le monde, déconnecte les comptes et mets une page de maintenance,
demande de retenter dans 15 minutes ».

Trois exigences, et la troisième est celle qu'on oublie :
  1. tout appel d'un compte non-administrateur est refusé — pas seulement le login ;
  2. les administrateurs traversent, sinon plus personne ne peut lever la maintenance ;
  3. l'écran envoie vers une page de MAINTENANCE et non vers le login : un login affiché
     pendant une coupure fait ressaisir des identifiants qui échoueront.
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
    import maintenance_backend as m

    etat_initial = m.get_status()["enabled"]
    print("\nLa porte se ferme pour tout le monde, sauf ceux qui doivent la rouvrir")
    try:
        m.set_status(True, "Contrôle automatique.", by="tests")
        verifie("un commercial est refusé", not m.acces_autorise("commercial"))
        verifie("un utilisateur est refusé", not m.acces_autorise("user"))
        verifie("un admin passe", m.acces_autorise("admin"))
        verifie("un superadmin passe", m.acces_autorise("superadmin"))
        verifie("un rôle vide est refusé", not m.acces_autorise(""))

        print("\nLe refus dit quoi faire, et pour combien de temps")
        r = m.refus("commercial")
        verifie("il se reconnaît comme une maintenance", r.get("maintenance") is True)
        verifie("il annonce un délai", int(r.get("retry_minutes") or 0) >= 1,
                f"({r.get('retry_minutes')} min)")
        verifie("il porte le message affiché", "Contrôle automatique." in (r.get("message") or ""))
    finally:
        m.set_status(bool(etat_initial), by="tests")
    verifie("l'état initial est restauré", m.get_status()["enabled"] == etat_initial)

    print("\nHors maintenance, rien ne change")
    if not etat_initial:
        verifie("un commercial passe", m.acces_autorise("commercial"))

    print("\nLe contrôle s'applique à CHAQUE appel, pas au seul login")
    api = (RACINE / "scripts" / "api.py").read_text()
    verifie("le middleware appelle acces_autorise", "_maint.acces_autorise(" in api)
    verifie("il répond 503 et non 401", "status_code=503" in api and "_maint.refus(" in api)
    verifie("il annonce Retry-After", '"Retry-After"' in api)
    # Le contrôle doit venir APRÈS l'authentification (il a besoin du rôle) mais AVANT
    # l'exécution de la route : sinon on ferme la plateforme après l'avoir fait travailler.
    verifie("posé après l'authentification",
            api.index("_maint.acces_autorise(") > api.index("sess = auth_verify(token)"))

    print("\nL'écran envoie vers la maintenance, pas vers le login")
    lib = RACINE.parent / "genesis-ui" / "src" / "lib" / "api.ts"
    if lib.exists():
        t = lib.read_text()
        verifie("le 503 est intercepté", "res.status === 503" in t)
        verifie("la session est fermée", "localStorage.removeItem('genesis_token')" in t)
        verifie("la redirection va vers /maintenance", "'/maintenance?'" in t)
        verifie("on ne boucle pas sur la page elle-même",
                "window.location.pathname !== '/maintenance'" in t)
    page = RACINE.parent / "genesis-ui" / "src" / "app" / "maintenance" / "page.tsx"
    verifie("la page de maintenance existe", page.exists())
    if page.exists():
        p = page.read_text()
        verifie("elle ne dépend d'aucun appel API",
                "apiFetch" not in p and "useSearchParams" in p,
                "(l'API est précisément ce qui refuse de répondre)")
        verifie("elle affiche un compte à rebours", "setReste" in p)

    print("\nUn onglet resté ouvert doit savoir qu'il est périmé")
    # L'autre moitié du problème, et elle n'a rien à voir avec la maintenance : reconstruire
    # l'interface pendant qu'un onglet est ouvert le tue — le navigateur garde l'ancien
    # JavaScript, dont les identifiants d'action n'existent plus. Next répond « Failed to
    # find Server Action » et la page meurt. Vécu le 2026-08-25 sur `/view`.
    api = (RACINE / "scripts" / "api.py").read_text()
    verifie("l'identifiant de build de l'interface est exposé", '"/api/ui-build"' in api)
    verifie("il est lisible SANS session",
            '"/api/ui-build",' in api.split("_AUTH_OPEN_PATHS")[1][:600],
            "(un écran déconnecté doit pouvoir détecter le décalage)")
    banniere = RACINE.parent / "genesis-ui" / "src" / "components" / "nouvelle-version.tsx"
    verifie("le bandeau existe", banniere.exists())
    if banniere.exists():
        b = banniere.read_text()
        verifie("il compare au build du premier chargement", "initial.current" in b)
        verifie("il NE recharge PAS d'autorité", "location.reload()" in b and "setPerime(true)" in b,
                "(quelqu'un peut être en train d'écrire — on propose, on n'impose pas)")
    mise_en_page = RACINE.parent / "genesis-ui" / "src" / "app" / "layout.tsx"
    verifie("il est monté sur toutes les pages",
            mise_en_page.exists() and "NouvelleVersion" in mise_en_page.read_text())

    print("\nLe navigateur ne doit jamais garder un HTML périmé")
    # La cause profonde de la page morte du 2026-08-25 : Next sert ses pages prérendues
    # avec `s-maxage=31536000`. Le navigateur gardait donc un document qui référence des
    # fichiers JavaScript disparus au build suivant. Symptôme révélateur : la navigation
    # privée fonctionnait, le profil normal non — le cache, et rien d'autre.
    conf = Path("/etc/nginx/sites-available/genesis-api")
    if not conf.exists():
        conf = Path("/etc/nginx/sites-enabled/genesis-api")
    if not conf.exists():
        print("  … configuration nginx introuvable, contrôle ignoré")
    else:
        c = conf.read_text()
        verifie("le document HTML est en no-store",
                'add_header Cache-Control "no-store' in c)
        verifie("l'ancien Cache-Control de Next est masqué",
                "proxy_hide_header Cache-Control" in c)
        # Sans cette exception, on perdrait le cache d'un an sur tout le JavaScript —
        # or ces fichiers portent un condensé dans leur nom, ils sont immuables.
        verifie("les fichiers immuables gardent leur cache",
                "location /_next/static/" in c)
        verifie("les logos restent servis par l'API", "location /assets/" in c)

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:6])}")
        return 1
    print("Une correction ferme la plateforme proprement, et dit quand revenir.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
