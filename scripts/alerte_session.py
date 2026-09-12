#!/usr/bin/env python3
"""L'état de santé de la plateforme, affiché à l'ouverture d'une session Claude.

Demande de Camille (2026-08-27) : « je veux une alerte quand je lance claude sur ce VPS
surtout… un tableau ASCII et toutes les alertes en rouge ».

## Pourquoi ce fichier existe

Le 2026-08-27, on a découvert que la sauvegarde hors machine échouait **depuis le 17 juin**
— deux mois et demi, 127 commits qui n'existaient que sur ce disque. Le script criait bien
son échec : dans `backups/backup.log`, que personne ne lit. **Un avertissement que personne
ne voit n'est pas un avertissement.**

Ce tableau règle ce problème-là et rien d'autre : il met sous les yeux, au moment où l'on
s'assoit devant la machine, ce qui va mal. Pas de résumé flatteur, pas de métriques
d'activité — uniquement ce qui demande une décision.

## Ce qu'il surveille, et pourquoi ces choses-là

Chaque contrôle correspond à une panne RÉELLEMENT vécue, pas à une inquiétude théorique :

  · sauvegarde périmée      — le silence de deux mois et demi (2026-08-27)
  · secret dans l'arbre     — la clé Basile qui bloquait tout push depuis juin
  · fichiers appartenant à root — a arrêté un cron deux fois (20 et 21/08), 2 993 fichiers
                                  concernés le 26/08
  · cron muet               — un cron qui ne tourne plus ne dit rien, par définition
  · campagne en erreur      — le lot du jour refusé sans que personne le voie
  · services à l'arrêt      — l'API ou l'interface tombée

## Silence = tout va bien

Rien à afficher, rien ne s'affiche. Un tableau qui apparaît tous les jours avec « tout est
vert » finit par ne plus être lu, et le jour où il vire au rouge on ne le voit pas non plus.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

# Les couleurs sont désactivées si la sortie n'est pas un terminal (redirection, cron) :
# des codes d'échappement dans un fichier de log le rendent illisible.
_COULEUR = ("--hook" in sys.argv or sys.stdout.isatty()) \
    and os.environ.get("NO_COLOR") is None
ROUGE = "\033[1;31m" if _COULEUR else ""
ORANGE = "\033[1;33m" if _COULEUR else ""
GRIS = "\033[0;90m" if _COULEUR else ""
FIN = "\033[0m" if _COULEUR else ""

LARGEUR = 100


def _cmd(args, timeout=20) -> str:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


# ── Les contrôles ─────────────────────────────────────────────────────────────
# Chacun rend (gravité, sujet, détail) ou None. `gravite` : "rouge" = agir maintenant,
# "orange" = à regarder. Rien d'autre : une échelle à cinq niveaux ne se lit pas.

def _sauvegarde():
    ts = _cmd(["git", "-C", str(RACINE), "log", "-1", "--format=%ct",
               "--branches=sauvegarde/*", "--remotes=origin/sauvegarde/*"])
    try:
        age = (time.time() - float(ts)) / 86400 if ts else 999
    except ValueError:
        age = 999
    if age > 900:
        return ("rouge", "Sauvegarde", "AUCUNE sauvegarde hors machine trouvée")
    if age > 3:
        return ("rouge", "Sauvegarde", f"dernière il y a {int(age)} jours — le travail n'existe qu'ici")
    if age > 1.5:
        return ("orange", "Sauvegarde", f"dernière il y a {age:.1f} jour(s)")
    return None


def _secret_dans_larbre():
    sortie = _cmd(["git", "-C", str(RACINE), "grep", "-lE",
                   r"sk_live_[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|xoxb-[A-Za-z0-9-]{20,}",
                   "--", "."])
    if sortie:
        n = len(sortie.splitlines())
        return ("rouge", "Secret exposé",
                f"{n} fichier(s) suivi(s) contiennent une clé — le push sera refusé")
    return None


def _fichiers_root():
    n = 0
    for base in (RACINE, RACINE.parent / "genesis-ui"):
        s = _cmd(["find", str(base), "-user", "root", "-not", "-path", "*/node_modules/*",
                  "-not", "-path", "*/.git/*", "-print", "-quit"], timeout=25)
        if s:
            n += 1
    if n:
        return ("rouge", "Droits fichiers",
                "des fichiers appartiennent à root — un cron tournant en autoblog s'arrêtera")
    return None


def _services():
    """PM2 rend du JSON : on le LIT comme tel.

    Première version : recherche de `"status":"online"` dans les 400 caractères suivant le
    nom du service. Elle annonçait `genesis-dashboard` arrêté alors qu'il tournait — le
    champ ne tombe pas toujours dans cette fenêtre, et PM2 n'espace pas son JSON de la même
    façon selon les versions. Un contrôle de santé qui crie au loup est pire que pas de
    contrôle : on apprend à ignorer son tableau.
    """
    import json as _json
    brut = _cmd(["sudo", "-u", "autoblog", "pm2", "jlist"], timeout=25)
    if not brut:
        return ("orange", "Services", "PM2 ne répond pas — état des services inconnu")
    try:
        procs = {p.get("name"): (p.get("pm2_env") or {}).get("status") for p in _json.loads(brut)}
    except Exception:  # noqa: BLE001
        return ("orange", "Services", "réponse PM2 illisible")
    manquants = [f"{n} ({procs.get(n) or 'absent'})"
                 for n in ("genesis-dashboard", "genesis-ui")
                 if procs.get(n) != "online"]
    if manquants:
        return ("rouge", "Services", ", ".join(manquants))
    return None


def _campagne():
    try:
        import pool_pg
        lignes = pool_pg._q(
            "SELECT name, left(coalesce(last_error,''), 70) FROM campaigns "
            "WHERE status = 'running' AND last_error IS NOT NULL AND last_error <> ''")
        if lignes:
            nom, err = lignes[0]
            return ("orange", "Campagne", f"« {nom} » porte une erreur : {err}")
    except Exception:  # noqa: BLE001
        return ("orange", "Campagne", "état des campagnes illisible (PostgreSQL ?)")
    return None


def _alertes_plateforme():
    """Les problèmes que `alertes.py` détecte déjà — on ne les redécrit pas ici."""
    out = []
    try:
        import alertes
        for cle, texte in (alertes.diagnostic() or {}).items():
            propre = texte.replace("*", "").strip()
            out.append(("rouge", cle.split(":")[0].capitalize(), propre[:70]))
    except Exception:  # noqa: BLE001
        out.append(("orange", "Alertes", "le module d'alertes ne répond pas"))
    return out


CONTROLES = (_sauvegarde, _secret_dans_larbre, _fichiers_root, _services, _campagne)


def _tableau(lignes) -> str:
    haut = "┌" + "─" * (LARGEUR - 2) + "┐"
    bas = "└" + "─" * (LARGEUR - 2) + "┘"
    sep = "├" + "─" * (LARGEUR - 2) + "┤"
    titre = f" ⚠  {len(lignes)} POINT(S) À REGARDER — plateforme Genesis / Cheffer"
    out = [f"{ROUGE}{haut}{FIN}",
           f"{ROUGE}│{FIN}{ROUGE}{titre.ljust(LARGEUR - 2)}{FIN}{ROUGE}│{FIN}",
           f"{ROUGE}{sep}{FIN}"]
    for gravite, sujet, detail in lignes:
        c = ROUGE if gravite == "rouge" else ORANGE
        puce = "✗" if gravite == "rouge" else "!"
        corps = f" {puce} {sujet:<16} {detail}"
        if len(corps) > LARGEUR - 3:
            corps = corps[:LARGEUR - 6] + "…"
        out.append(f"{ROUGE}│{FIN}{c}{corps.ljust(LARGEUR - 2)}{FIN}{ROUGE}│{FIN}")
    out.append(f"{ROUGE}{bas}{FIN}")
    return "\n".join(out)


def _sortie_hook(lignes) -> str:
    """Le format qu'attend un hook SessionStart de Claude Code.

    `systemMessage` s'affiche à l'écran — c'est ce que Camille veut voir en s'asseyant.
    `additionalContext` entre dans le contexte du modèle : sans lui, l'assistant ouvrirait
    la session sans savoir que quelque chose ne va pas, et il faudrait le lui répéter.
    """
    import json as _json
    return _json.dumps({
        "systemMessage": _tableau(lignes),
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext":
                "État de la plateforme à l'ouverture — "
                + " ; ".join(f"[{g}] {s} : {d}" for g, s, d in lignes),
        },
    }, ensure_ascii=False)


def main() -> int:
    lignes = []
    for c in CONTROLES:
        try:
            r = c()
        except Exception as e:  # noqa: BLE001
            r = ("orange", "Contrôle", f"{c.__name__} a échoué ({type(e).__name__})")
        if r:
            lignes.append(r)
    lignes += _alertes_plateforme()

    if not lignes:
        # Silence délibéré : voir l'en-tête du fichier.
        return 0
    # Le rouge d'abord : ce qui demande une décision passe avant ce qui demande un coup d'œil.
    lignes.sort(key=lambda x: 0 if x[0] == "rouge" else 1)
    if "--hook" in sys.argv:
        print(_sortie_hook(lignes))
        return 0
    print(_tableau(lignes))
    print(f"{GRIS}  détail : python3 scripts/alerte_session.py{FIN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
