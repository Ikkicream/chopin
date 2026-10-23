#!/usr/bin/env python3
"""routine_hebdo.py — la routine du dimanche soir (demandée par Camille le 19/10/2026).

Trois temps, puis un rapport en tableaux ASCII envoyé sur Telegram :

  1. NETTOYAGE  — ce qui encombre sans servir : journaux PM2 et Genesis démesurés (on garde
                  la fin), journal système de plus de 30 jours, caches apt/npm/pip/uv,
                  fichiers de /tmp vieux de 14 jours, copies « .bak » de plus de 30 jours
                  (ARCHIVÉES dans backups/archives_bak avant suppression, jamais perdues),
                  fichiers appartenant à root dans les dossiers d'autoblog (rendus à autoblog :
                  c'est ce qui a déjà arrêté des crons).
  2. SANTÉ      — disque, mémoire, charge, services PM2, ports HTTP, PostgreSQL, sauvegardes,
                  tâches planifiées (via alertes.diagnostic), jobs Mass Email, certificats.
  3. SÉCURITÉ   — tentatives SSH, fail2ban, connexions réussies, configuration SSH, pare-feu,
                  ports ouverts sur Internet, mises à jour, redémarrage en attente, droits des
                  secrets, clé dans l'arbre git.

La routine CONSTATE la sécurité, elle ne la modifie pas : changer le pare-feu ou SSH peut
couper l'accès au serveur — c'est une décision, pas un ménage.

Tourne en root (le nettoyage touche /var/log, /root et les caches) via le minuteur systemd
`genesis-routine-hebdo.timer` (dimanche 21:00 heure de Paris). Le rapport est aussi écrit
dans logs/routine_hebdo/AAAA-MM-JJ.txt, rendu à autoblog (piège des fichiers root).

    python3 scripts/routine_hebdo.py              # tout, et envoi Telegram
    python3 scripts/routine_hebdo.py --essai      # ne supprime rien, n'envoie rien, affiche
    python3 scripts/routine_hebdo.py --essai --envoyer   # idem, mais envoie le rapport
"""
from __future__ import annotations

import html
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import textwrap
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

RACINE = Path(__file__).resolve().parent.parent          # /home/autoblog/genesis
UI = RACINE.parent / "genesis-ui"
PARIS = ZoneInfo("Europe/Paris")
DOSSIER_RAPPORTS = RACINE / "logs" / "routine_hebdo"
ARCHIVES_BAK = RACINE / "backups" / "archives_bak"
ESSAI = "--essai" in sys.argv

Mo = 1024 * 1024
JOURNAL_MAX = 50 * Mo           # au-delà, un journal est réduit…
JOURNAL_GARDE = 5 * Mo          # …à ses 5 derniers Mo
PORTS_PUBLICS_ATTENDUS = {22, 80, 443}

sys.path.insert(0, str(RACINE / "scripts"))


# ── Outils ────────────────────────────────────────────────────────────────────

def _cmd(args, timeout=60, user=None) -> str:
    if user:
        args = ["sudo", "-n", "-u", user, "-H"] + list(args)
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as e:  # noqa: BLE001
        return f"ERREUR {e}"


def _env(cle: str) -> str:
    if os.environ.get(cle):
        return os.environ[cle]
    for ligne in (RACINE / ".env").read_text().splitlines():
        if ligne.startswith(cle + "="):
            return ligne.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _taille(p: Path) -> int:
    try:
        if p.is_file():
            return p.stat().st_size
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and not f.is_symlink())
    except Exception:  # noqa: BLE001
        return 0


def _lisible(octets: float) -> str:
    for unite in ("o", "Ko", "Mo", "Go"):
        if abs(octets) < 1024 or unite == "Go":
            return f"{octets:.0f} {unite}" if unite in ("o", "Ko") else f"{octets:.1f} {unite}"
        octets /= 1024
    return ""


def _disque_libre() -> int:
    return shutil.disk_usage("/").free


# ── 1. NETTOYAGE ──────────────────────────────────────────────────────────────
# Chaque étape rend (libellé, octets libérés, détail). Les octets sont MESURÉS (avant/après),
# pas estimés.

def _reduire_journal(p: Path) -> int:
    """Garde les JOURNAL_GARDE derniers octets, à partir d'un début de ligne.

    Réécriture en place (même inode) : PM2 écrit en mode ajout, il continue sans
    redémarrage. Un `rm` laisserait le fichier ouvert par PM2 et ne libérerait rien.
    """
    avant = p.stat().st_size
    if ESSAI:
        return avant - JOURNAL_GARDE
    with open(p, "r+b") as f:
        f.seek(avant - JOURNAL_GARDE)
        fin = f.read()
        coupe = fin.find(b"\n")
        fin = fin[coupe + 1:] if coupe >= 0 else fin
        f.seek(0)
        f.write(f"[routine_hebdo {datetime.now(PARIS):%d/%m/%Y %H:%M}] journal réduit "
                f"à ses {JOURNAL_GARDE // Mo} derniers Mo\n".encode())
        f.write(fin)
        f.truncate()
    return avant - p.stat().st_size


def nettoyer_journaux():
    dossiers = [Path("/root/.pm2/logs"), Path("/home/autoblog/.pm2/logs"), RACINE / "logs",
                RACINE / "memory"]
    gagne, noms = 0, []
    for d in dossiers:
        if not d.exists():
            continue
        for p in d.rglob("*.log"):
            try:
                if p.is_file() and p.stat().st_size > JOURNAL_MAX:
                    gagne += _reduire_journal(p)
                    noms.append(p.name)
            except Exception:  # noqa: BLE001
                continue
    detail = f"{len(noms)} journal(aux) > {JOURNAL_MAX // Mo} Mo réduits"
    if noms:
        detail += " : " + ", ".join(sorted(set(noms))[:4]) + ("…" if len(set(noms)) > 4 else "")
    return ("Journaux (PM2, logs)", gagne, detail)


def nettoyer_journal_systeme():
    avant = _disque_libre()
    if not ESSAI:
        _cmd(["journalctl", "--vacuum-time=30d"])
    return ("Journal système", _disque_libre() - avant, "entrées > 30 jours supprimées")


def nettoyer_caches():
    cibles = [Path("/var/cache/apt/archives"), Path("/root/.npm/_cacache"),
              Path("/home/autoblog/.npm/_cacache"), Path("/root/.cache/pip"),
              Path("/home/autoblog/.cache/pip"), Path("/root/.cache/uv"),
              Path("/home/autoblog/.cache/uv")]
    avant = sum(_taille(c) for c in cibles)
    if not ESSAI:
        _cmd(["apt-get", "clean"])
        _cmd(["npm", "cache", "clean", "--force"], timeout=300)
        _cmd(["npm", "cache", "clean", "--force"], timeout=300, user="autoblog")
        _cmd(["pip3", "cache", "purge"], timeout=120)
        _cmd(["pip3", "cache", "purge"], timeout=120, user="autoblog")
        # `prune` ne retire que ce qu'aucun environnement n'utilise : sans risque.
        _cmd(["/root/.local/bin/uv", "cache", "prune"], timeout=300)
        _cmd(["/home/autoblog/.local/bin/uv", "cache", "prune"], timeout=300, user="autoblog")
    apres = avant if ESSAI else sum(_taille(c) for c in cibles)
    return ("Caches apt/npm/pip/uv", avant - apres if not ESSAI else avant,
            "re-téléchargés au besoin, rien de perdu")


_TMP_EPARGNES = ("claude-", "systemd-private-", ".X11", ".ICE", "tmux-", "snap-private",
                 ".font-unix", "pm2", "node-compile-cache")


def nettoyer_tmp():
    gagne, n = 0, 0
    limite = time.time() - 14 * 86400
    for p in Path("/tmp").rglob("*"):
        try:
            rel = p.relative_to("/tmp").parts[0]
            if any(rel.startswith(e) for e in _TMP_EPARGNES):
                continue
            if p.is_file() and not p.is_symlink() and p.stat().st_mtime < limite:
                gagne += p.stat().st_size
                n += 1
                if not ESSAI:
                    p.unlink()
        except Exception:  # noqa: BLE001
            continue
    return ("Fichiers /tmp", gagne, f"{n} fichier(s) de plus de 14 jours")


def nettoyer_bak():
    """Les copies « .bak » de plus de 30 jours : archivées puis supprimées.

    On ne détruit pas une copie de code : elle part dans une archive datée (on en garde 8,
    soit deux mois), d'où on peut toujours la ressortir.
    """
    limite = time.time() - 30 * 86400
    fichiers = []
    for base in (RACINE, UI):
        for p in base.rglob("*.bak*"):
            s = str(p)
            if "/node_modules/" in s or "/.git/" in s or "/archives_bak/" in s or "/.next" in s:
                continue
            try:
                if p.is_file() and p.stat().st_mtime < limite:
                    fichiers.append(p)
            except Exception:  # noqa: BLE001
                continue
    gagne = sum(p.stat().st_size for p in fichiers)
    if fichiers and not ESSAI:
        ARCHIVES_BAK.mkdir(parents=True, exist_ok=True)
        archive = ARCHIVES_BAK / f"bak-{datetime.now(PARIS):%Y%m%d-%H%M%S}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for p in fichiers:
                tar.add(p, arcname=str(p.relative_to(RACINE.parent)))
        for p in fichiers:
            p.unlink()
        for vieille in sorted(ARCHIVES_BAK.glob("bak-*.tar.gz"))[:-8]:
            vieille.unlink()
        gagne -= archive.stat().st_size
        _cmd(["chown", "-R", "autoblog:autoblog", str(ARCHIVES_BAK)])
    return ("Copies .bak > 30 jours", gagne,
            f"{len(fichiers)} archivée(s) dans backups/archives_bak" if fichiers else "aucune")


def rendre_fichiers_root():
    n = 0
    for base in (RACINE, UI):
        sortie = _cmd(["find", str(base), "-user", "root", "-not", "-path", "*/node_modules/*"],
                      timeout=120)
        lignes = [l for l in sortie.splitlines() if l.startswith("/")]
        n += len(lignes)
        if lignes and not ESSAI:
            _cmd(["find", str(base), "-user", "root", "-not", "-path", "*/node_modules/*",
                  "-exec", "chown", "-h", "autoblog:autoblog", "{}", "+"], timeout=300)
    return ("Fichiers root → autoblog", 0,
            f"{n} fichier(s) rendus à autoblog (sinon un cron s'arrête)" if n else "aucun")


NETTOYAGES = (nettoyer_journaux, nettoyer_journal_systeme, nettoyer_caches, nettoyer_tmp,
              nettoyer_bak, rendre_fichiers_root)


# ── 2. SANTÉ et 3. SÉCURITÉ ───────────────────────────────────────────────────
# Chaque contrôle rend une liste de (état, contrôle, détail, action) ; état ∈ OK / !! / KO.
# `action` = ce qu'il faut faire, en clair, quand ce n'est pas OK.

def _pg():
    import psycopg2
    return psycopg2.connect(_env("PG_DSN"), connect_timeout=10)


def sante_systeme():
    out = []
    du = shutil.disk_usage("/")
    pct = du.used * 100 / du.total
    etat = "KO" if pct > 90 else "!!" if pct > 80 else "OK"
    out.append((etat, "Disque /", f"{pct:.0f} % utilisé, {_lisible(du.free)} libres",
                "libérer de la place (le serveur s'arrête à 100 %)"))
    mem = {l.split(":")[0]: int(l.split()[1]) * 1024
           for l in Path("/proc/meminfo").read_text().splitlines()}
    dispo = mem["MemAvailable"] / mem["MemTotal"] * 100
    etat = "KO" if dispo < 10 else "!!" if dispo < 20 else "OK"
    out.append((etat, "Mémoire", f"{_lisible(mem['MemAvailable'])} dispo sur "
                f"{_lisible(mem['MemTotal'])} ({dispo:.0f} %)",
                "identifier le service qui consomme (pm2 ls, colonne mem)"))
    charge = os.getloadavg()[2]
    coeurs = os.cpu_count() or 1
    etat = "!!" if charge > coeurs else "OK"
    jours = float(Path("/proc/uptime").read_text().split()[0]) / 86400
    out.append((etat, "Charge CPU", f"{charge:.2f} sur 15 min ({coeurs} cœurs), "
                f"allumé depuis {jours:.0f} j", "regarder le process le plus gourmand (top)"))
    return out


def sante_pm2():
    out = []
    for user in ("root", "autoblog"):
        brut = _cmd(["pm2", "jlist"], user=None if user == "root" else user, timeout=30)
        try:
            debut = brut.index("[")
            procs = json.loads(brut[debut:])
        except Exception:  # noqa: BLE001
            out.append(("!!", f"PM2 ({user})", "PM2 ne répond pas", "vérifier PM2 à la main"))
            continue
        en_ligne = [p for p in procs if (p.get("pm2_env") or {}).get("status") == "online"]
        arretes = [p["name"] for p in procs
                   if (p.get("pm2_env") or {}).get("status") not in ("online", "stopped")]
        stoppes = [p["name"] for p in procs if (p.get("pm2_env") or {}).get("status") == "stopped"]
        instables = [f"{p['name']} ({p['pm2_env'].get('restart_time', 0)}×)"
                     for p in en_ligne if (p.get("pm2_env") or {}).get("unstable_restarts", 0) > 0]
        detail = f"{len(en_ligne)}/{len(procs)} en ligne"
        if stoppes:
            detail += f" ; {len(stoppes)} arrêté(s) volontairement"
        if arretes:
            out.append(("KO", f"Services PM2 ({user})",
                        detail + f" ; EN ERREUR : {', '.join(arretes)}",
                        f"relancer le service en erreur et lire son journal d'erreur"))
        elif instables:
            out.append(("!!", f"Services PM2 ({user})", detail + f" ; instables : "
                        + ", ".join(instables), "lire le journal d'erreur du service"))
        else:
            out.append(("OK", f"Services PM2 ({user})", detail, ""))
    return out


_HTTP = {"API Mass Email (8090)": "http://127.0.0.1:8090/api/mass-mailing/health",
         "Interface (3100)": "http://127.0.0.1:3100/",
         "API Genesis (8080)": "http://127.0.0.1:8080/api/health"}


def sante_http():
    out = []
    for nom, url in _HTTP.items():
        try:
            urllib.request.urlopen(url, timeout=15)
            code = 200
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception:  # noqa: BLE001
            code = 0
        # 401/404/307 = le service répond (il exige une connexion) ; 0 ou 5xx = il est tombé.
        ok = 0 < code < 500
        out.append(("OK" if ok else "KO", nom, f"répond (HTTP {code})" if ok else
                    f"ne répond pas (HTTP {code or 'aucune réponse'})",
                    "relancer : bash scripts/deployer_mass_email.sh (ui|api) ou pm2 restart"))
    return out


def sante_postgres():
    try:
        with _pg() as c, c.cursor() as cur:
            cur.execute("SELECT pg_size_pretty(pg_database_size(current_database())), "
                        "(SELECT count(*) FROM pg_stat_activity)")
            taille, connexions = cur.fetchone()
        return [("OK", "PostgreSQL", f"répond, base {taille}, {connexions} connexion(s)", "")]
    except Exception as e:  # noqa: BLE001
        return [("KO", "PostgreSQL", f"injoignable : {str(e)[:60]}",
                 "systemctl status postgresql")]


def sante_sauvegardes():
    out = []
    ts = _cmd(["git", "-C", str(RACINE), "log", "-1", "--format=%ct",
               "--branches=sauvegarde/*", "--remotes=origin/sauvegarde/*"], user="autoblog")
    try:
        age = (time.time() - float(ts.splitlines()[-1])) / 86400
    except Exception:  # noqa: BLE001
        age = 999
    etat = "KO" if age > 3 else "!!" if age > 1.5 else "OK"
    out.append((etat, "Sauvegarde GitHub", f"dernière il y a {age:.1f} j" if age < 900
                else "aucune trouvée", "lire logs/sauvegarde-hors-machine.log"))
    log = RACINE / "backups" / "backup.log"
    try:
        fin = log.read_text(errors="replace")[-3000:]
        age_log = (time.time() - log.stat().st_mtime) / 86400
        ok = "[OK] Backup terminé" in fin.splitlines()[-1] if fin.strip() else False
        etat = "OK" if ok and age_log < 1.5 else "KO"
        out.append((etat, "Sauvegarde locale", f"dernier passage il y a {age_log:.1f} j, "
                    + ("terminé OK" if ok else "N'A PAS TERMINÉ"),
                    "lire la fin de backups/backup.log"))
    except Exception:  # noqa: BLE001
        out.append(("KO", "Sauvegarde locale", "backup.log illisible", "lire backups/backup.log"))
    return out


def sante_taches():
    """Les tâches planifiées en retard ou mortes : `alertes.diagnostic` les connaît déjà."""
    try:
        import alertes
        problemes = alertes.diagnostic() or {}
    except Exception as e:  # noqa: BLE001
        return [("!!", "Tâches planifiées", f"diagnostic impossible ({type(e).__name__})",
                 "python3 scripts/alertes.py")]
    if not problemes:
        return [("OK", "Tâches planifiées", "toutes passées à l'heure, sans erreur", "")]
    out = []
    for cle, texte in problemes.items():
        propre = re.sub(r"[*_`]", "", texte).replace("\n", " ")
        propre = re.sub(r"[^\w\s.,:;()/%'’«»<>=+-]", "", propre).strip()
        out.append(("!!", "Tâche planifiée", propre[:140],
                    "lire le journal de la tâche dans logs/ et la relancer"))
    return out


def sante_mass_email():
    try:
        with _pg() as c, c.cursor() as cur:
            cur.execute("SELECT schema_name FROM information_schema.schemata "
                        "WHERE schema_name = 'mass_mailing' OR schema_name LIKE 'mmc\\_%'")
            espaces = [r[0] for r in cur.fetchall()]
            morts, bloques, envois = [], [], 0
            for e in espaces:
                cur.execute(f"SELECT count(*) FROM {e}.jobs WHERE status = 'dead' "
                            "AND created_at > now() - interval '7 days'")
                n = cur.fetchone()[0]
                if n:
                    morts.append(f"{e.replace('mmc_', '')} {n}")
                cur.execute(f"SELECT count(*) FROM {e}.jobs WHERE status = 'running' "
                            "AND started_at < now() - interval '2 hours'")
                n = cur.fetchone()[0]
                if n:
                    bloques.append(f"{e.replace('mmc_', '')} {n}")
                cur.execute(f"SELECT count(*) FROM {e}.recipients "
                            "WHERE submitted_at > now() - interval '7 days'")
                envois += cur.fetchone()[0]
    except Exception as e:  # noqa: BLE001
        return [("!!", "Mass Email", f"lecture impossible : {str(e)[:60]}", "")]
    out = [("OK", "Mass Email : envois", f"{envois} email(s) partis en 7 j, "
            f"{len(espaces)} espace(s)", "")]
    out.append(("!!" if morts else "OK", "Mass Email : jobs morts",
                "7 j : " + ", ".join(morts) if morts else "aucun sur 7 jours",
                "ouvrir la fiche campagne (bandeau rouge) et lire l'erreur"))
    out.append(("KO" if bloques else "OK", "Mass Email : bloqués",
                "en cours depuis > 2 h : " + ", ".join(bloques) if bloques else "aucun job coincé",
                "redémarrer le worker : pm2 restart mass-mailing-worker"))
    return out


def sante_certificats():
    sortie = _cmd(["certbot", "certificates"], timeout=60)
    out = []
    for nom, jours in re.findall(r"Certificate Name: (\S+).*?VALID: (\d+ \w+)", sortie, re.S):
        n, unite = jours.split()
        j = int(n) if unite.startswith("day") else 0
        delai = f"{n} j" if unite.startswith("day") else f"{n} h"
        if j < 14:
            out.append(("KO" if j < 7 else "!!", "Certificat SSL", f"{nom} expire dans {delai}",
                        "certbot renew --cert-name " + nom + " (et lire l'erreur s'il échoue)"))
    if not out:
        out.append(("OK", "Certificats SSL", "aucun n'expire dans les 14 jours", ""))
    return out


def securite_ssh():
    out = []
    journal = _cmd(["journalctl", "-u", "ssh", "-u", "sshd", "--since", "-7d",
                    "--no-pager", "-o", "cat"], timeout=120)
    echecs = len(re.findall(r"Failed password|Invalid user|authentication failure", journal))
    ips_echec = set(re.findall(r"(?:Failed password|Invalid user).*? from (\S+)", journal))
    acceptes = re.findall(r"Accepted (\w+) for (\S+) from (\S+)", journal)
    out.append(("OK", "SSH : attaques", f"{echecs} tentative(s) ratée(s) en 7 j "
                f"depuis {len(ips_echec)} IP (bruit d'Internet)", ""))
    f2b = _cmd(["fail2ban-client", "status", "sshd"])
    m = re.search(r"Currently banned:\s*(\d+).*?Total banned:\s*(\d+)", f2b, re.S)
    if m:
        out.append(("OK", "fail2ban", f"actif : {m.group(1)} IP bannie(s), "
                    f"{m.group(2)} au total", ""))
    else:
        out.append(("KO", "fail2ban", "inactif ou illisible", "systemctl start fail2ban"))
    connexions = {}
    for methode, qui, ip in acceptes:
        connexions.setdefault((qui, ip), methode)
    par_mdp = [f"{q}@{ip}" for (q, ip), m_ in connexions.items() if m_ == "password"]
    detail = f"{len(acceptes)} connexion(s) réussie(s), {len(connexions)} couple(s) compte/IP"
    if connexions:
        detail += " : " + ", ".join(f"{q}@{ip}" for q, ip in list(connexions)[:4])
    out.append(("!!" if par_mdp else "OK", "SSH : connexions", detail,
                "vérifier que ces IP sont bien les tiennes"))
    conf = _cmd(["sshd", "-T"])
    racine = re.search(r"^permitrootlogin (\S+)", conf, re.M)
    mdp = re.search(r"^passwordauthentication (\S+)", conf, re.M)
    if racine and mdp and racine.group(1) == "yes" and mdp.group(1) == "yes":
        out.append(("!!", "SSH : configuration", "root peut se connecter AVEC mot de passe",
                    "passer à la connexion par clé seule (décision à prendre, pas automatique)"))
    else:
        out.append(("OK", "SSH : configuration", f"root={racine and racine.group(1)}, "
                    f"mot de passe={mdp and mdp.group(1)}", ""))
    return out


def _publique(adresse: str) -> bool:
    hote = adresse.rsplit(":", 1)[0].strip("[]").split("%")[0]
    if hote in ("*", "0.0.0.0", "::"):
        return True
    try:
        return not ipaddress.ip_address(hote).is_loopback
    except ValueError:
        return False


def securite_reseau():
    out = []
    ufw = _cmd(["ufw", "status"])
    actif = "Status: active" in ufw
    ports = {}
    for ligne in _cmd(["ss", "-tlnpH"]).splitlines():
        champs = ligne.split()
        if len(champs) < 4 or not _publique(champs[3]):
            continue
        port = int(champs[3].rsplit(":", 1)[1])
        proc = re.search(r'\(\("([^"]+)"', ligne)
        ports[port] = proc.group(1) if proc else "?"
    inattendus = {p: n for p, n in sorted(ports.items()) if p not in PORTS_PUBLICS_ATTENDUS}
    out.append(("OK" if actif else "!!", "Pare-feu (UFW)", "actif" if actif else
                "INACTIF : tout port ouvert est joignable depuis Internet",
                "activer UFW en autorisant 22, 80, 443 (décision à prendre ensemble)"))
    if inattendus and not actif:
        out.append(("!!", "Ports exposés", "ouverts sur Internet en plus de 22/80/443 : "
                    + ", ".join(f"{p} ({n})" for p, n in inattendus.items()),
                    "les fermer au pare-feu ou les lier à 127.0.0.1"))
    else:
        out.append(("OK", "Ports exposés", "seulement " + ", ".join(map(str, sorted(ports)))
                    + (" (filtrés par le pare-feu)" if inattendus else ""), ""))
    return out


def securite_systeme():
    out = []
    _cmd(["apt-get", "update", "-qq"], timeout=300)
    maj = [l for l in _cmd(["apt", "list", "--upgradable"], timeout=120).splitlines()
           if "/" in l]
    secu = [l for l in maj if "-security" in l]
    out.append(("!!" if secu else "OK", "Mises à jour", f"{len(secu)} de sécurité, "
                f"{len(maj)} au total en attente",
                "apt-get upgrade (unattended-upgrades devrait les passer seul)"))
    if Path("/var/run/reboot-required").exists():
        paquets = Path("/var/run/reboot-required.pkgs")
        quoi = ", ".join(sorted(set(paquets.read_text().split()))[:3]) if paquets.exists() else ""
        out.append(("!!", "Redémarrage", f"le système attend un redémarrage ({quoi})",
                    "redémarrer le serveur à un creux (dimanche soir, aucun envoi en cours)"))
    else:
        out.append(("OK", "Redémarrage", "aucun en attente", ""))
    return out


def securite_secrets():
    out = []
    mauvais = []
    for p in [RACINE / ".env", *RACINE.glob(".secret*"), *RACINE.glob("data/.master_key"),
              *(RACINE / "mass_mailing").glob(".env*")]:
        try:
            if p.is_file() and p.stat().st_mode & 0o077:
                mauvais.append(f"{p.name} ({oct(p.stat().st_mode & 0o777)[2:]})")
        except Exception:  # noqa: BLE001
            continue
    out.append(("KO" if mauvais else "OK", "Droits des secrets",
                "lisibles par d'autres comptes : " + ", ".join(mauvais) if mauvais
                else ".env et clés en 600 (lisibles par leur seul propriétaire)",
                "chmod 600 sur ces fichiers"))
    sortie = _cmd(["git", "-C", str(RACINE), "grep", "-lE",
                   r"sk_live_[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|xoxb-[A-Za-z0-9-]{20,}|"
                   r"re_[A-Za-z0-9]{8}_[A-Za-z0-9]{16,}", "--", "."], user="autoblog")
    fichiers = [l for l in sortie.splitlines() if l and not l.startswith(("fatal", "ERREUR"))]
    out.append(("KO" if fichiers else "OK", "Clés dans le code",
                f"{len(fichiers)} fichier(s) suivi(s) contiennent une clé : "
                + ", ".join(fichiers[:3]) if fichiers else "aucune clé dans les fichiers suivis",
                "sortir la clé du fichier (vers .env) et la changer chez le fournisseur"))
    return out


SANTE = (sante_systeme, sante_pm2, sante_http, sante_postgres, sante_sauvegardes,
         sante_taches, sante_mass_email, sante_certificats)
SECURITE = (securite_ssh, securite_reseau, securite_systeme, securite_secrets)


# ── Rapport ───────────────────────────────────────────────────────────────────

def _table(entetes, largeurs, lignes) -> list[str]:
    """Tableau ASCII pur ; la dernière colonne se replie sur plusieurs lignes."""
    sep = "+" + "+".join("-" * (l + 2) for l in largeurs) + "+"
    out = [sep, "| " + " | ".join(e.ljust(l) for e, l in zip(entetes, largeurs)) + " |", sep]
    for ligne in lignes:
        cellules = [textwrap.wrap(str(c), l) or [""] for c, l in zip(ligne, largeurs)]
        for i in range(max(len(c) for c in cellules)):
            out.append("| " + " | ".join((c[i] if i < len(c) else "").ljust(l)
                                         for c, l in zip(cellules, largeurs)) + " |")
    out.append(sep)
    return out


def _executer(controles):
    lignes = []
    for c in controles:
        try:
            lignes += c()
        except Exception as e:  # noqa: BLE001
            lignes.append(("!!", c.__name__, f"contrôle en échec ({type(e).__name__}: "
                           f"{str(e)[:50]})", "relancer la routine en --essai pour voir"))
    return lignes


def rapport() -> tuple[str, dict]:
    debut = time.time()
    libre_avant = _disque_libre()
    nettoyage = []
    for n in NETTOYAGES:
        try:
            nettoyage.append(n())
        except Exception as e:  # noqa: BLE001
            nettoyage.append((n.__name__, 0, f"échec : {type(e).__name__} {str(e)[:40]}"))
    libere = _disque_libre() - libre_avant
    sante = _executer(SANTE)
    securite = _executer(SECURITE)

    tout = sante + securite
    ko = sum(1 for l in tout if l[0] == "KO")
    av = sum(1 for l in tout if l[0] == "!!")
    ok = sum(1 for l in tout if l[0] == "OK")
    maintenant = datetime.now(PARIS)
    verdict = ("TOUT VA BIEN" if not ko and not av else
               f"{ko} PROBLÈME(S)" if ko else f"{av} POINT(S) À REGARDER")

    L = [f"ROUTINE HEBDO — serveur Genesis — {maintenant:%d/%m/%Y %H:%M}"
         + (" — ESSAI, rien supprimé" if ESSAI else ""),
         f"Verdict : {verdict}   (KO {ko} | à voir {av} | OK {ok})",
         f"Légende : OK = bon, !! = à regarder, KO = à traiter", ""]
    L.append("1. NETTOYAGE" + (" (ce qui SERAIT libéré)" if ESSAI else ""))
    L += _table(["Élément", "Libéré", "Détail"], [22, 9, 26],
                [(n, _lisible(max(o, 0)) if o else "-", d) for n, o, d in nettoyage])
    if not ESSAI:
        L.append(f"Total mesuré sur le disque : {_lisible(max(libere, 0))} libérés")
    L.append("")
    L.append("2. SANTÉ")
    L += _table(["Contrôle", "État", "Détail"], [21, 4, 34], [(l[1], l[0], l[2]) for l in sante])
    L.append("")
    L.append("3. SÉCURITÉ")
    L += _table(["Contrôle", "État", "Détail"], [21, 4, 34], [(l[1], l[0], l[2]) for l in securite])
    actions = [(l[0], l[1], l[3]) for l in tout if l[0] != "OK" and l[3]]
    if actions:
        L.append("")
        L.append("4. À FAIRE (rien n'a été modifié pour ces points)")
        actions.sort(key=lambda a: 0 if a[0] == "KO" else 1)
        L += _table(["#", "Contrôle", "Action"], [2, 21, 36],
                    [(str(i), f"{c} ({e})", a) for i, (e, c, a) in enumerate(actions, 1)])
    L.append("")
    L.append(f"Durée {time.time() - debut:.0f} s — rapport complet : "
             f"logs/routine_hebdo/{maintenant:%Y-%m-%d}.txt")
    return "\n".join(L), {"ko": ko, "a_voir": av, "ok": ok, "libere": libere}


def envoyer_telegram(texte: str) -> bool:
    token, chat = _env("TELEGRAM_BOT_TOKEN"), _env("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[routine_hebdo] TELEGRAM_BOT_TOKEN/CHAT_ID absents — rien envoyé")
        return False
    # Telegram plafonne à 4 096 caractères : on coupe entre deux lignes, et chaque morceau
    # reste dans un bloc <pre> pour garder les colonnes alignées (police à chasse fixe).
    morceaux, courant = [], ""
    for ligne in texte.splitlines():
        if len(courant) + len(ligne) + 1 > 3500:
            morceaux.append(courant)
            courant = ""
        courant += ligne + "\n"
    morceaux.append(courant)
    ok = True
    for m in morceaux:
        data = urllib.parse.urlencode({"chat_id": chat, "parse_mode": "HTML",
                                       "text": f"<pre>{html.escape(m)}</pre>"}).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    f"https://api.telegram.org/bot{token}/sendMessage", data=data),
                    timeout=30) as r:
                ok = ok and r.status == 200
        except Exception as e:  # noqa: BLE001
            print(f"[routine_hebdo] envoi Telegram impossible : {e}")
            ok = False
    return ok


def main() -> int:
    if os.geteuid() != 0:
        print("routine_hebdo doit tourner en root (nettoyage de /var/log, /root, caches)")
        return 1
    texte, chiffres = rapport()
    print(texte)
    if ESSAI:
        if "--envoyer" in sys.argv:          # essai complet du canal, sans rien supprimer
            print(f"[routine_hebdo] Telegram : {'envoyé' if envoyer_telegram(texte) else 'ÉCHEC'}")
        return 0
    DOSSIER_RAPPORTS.mkdir(parents=True, exist_ok=True)
    fichier = DOSSIER_RAPPORTS / f"{datetime.now(PARIS):%Y-%m-%d}.txt"
    fichier.write_text(texte + "\n")
    for vieux in sorted(DOSSIER_RAPPORTS.glob("*.txt"))[:-26]:   # six mois de rapports
        vieux.unlink()
    _cmd(["chown", "-R", "autoblog:autoblog", str(DOSSIER_RAPPORTS)])
    envoye = envoyer_telegram(texte)
    print(f"[routine_hebdo] rapport écrit dans {fichier} ; Telegram : "
          f"{'envoyé' if envoye else 'ÉCHEC'} ; {json.dumps(chiffres)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
