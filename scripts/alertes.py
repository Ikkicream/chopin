#!/usr/bin/env python3
"""alertes.py — La sonnerie qui manquait au relevé technique.

Le relevé (`etat_technique`) sait dire ce qui n'a pas tourné ; encore faut-il que quelqu'un
le regarde. Ce script le lit toutes les heures et n'ouvre la bouche que quand il y a un
problème — puis une seconde fois, pour dire qu'il est réglé.

Trois familles de contrôles :
  1. **Tâches planifiées** : chacune a un âge maximal. Passé ce délai, elle n'a pas tourné.
  2. **Services** : les trois process qui doivent être en ligne.
  3. **Collecte** : un scrape bloqué (Serper/Basile refusés) ne se voit pas dans les logs.

Anti-spam, la partie qui fait qu'on continue à lire les alertes : on ne notifie qu'au
CHANGEMENT d'état. Un problème qui dure ne sonne qu'une fois — puis un rappel par jour,
pas plus. Un problème qui se règle envoie un message de rétablissement : sans lui, on
n'ose plus faire confiance au silence.

État : memory/alertes.json
CLI  :
    python3 scripts/alertes.py            # contrôle + notifie si l'état a changé
    python3 scripts/alertes.py --etat     # affiche le diagnostic sans rien envoyer
    python3 scripts/alertes.py --test     # envoie un message de test (vérifie le câblage)
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))
ETAT_PATH = BASE_DIR / "memory" / "alertes.json"

_envf = BASE_DIR / ".env"
if _envf.exists():
    for _l in _envf.read_text().splitlines():
        _l = _l.strip()
        if _l and not _l.startswith("#") and "=" in _l:
            _k, _v = _l.split("=", 1)
            os.environ.setdefault(_k, _v.strip("'\""))

# Âge maximal admis pour chaque tâche, en heures. Une tâche quotidienne a droit à 26 h :
# deux heures de marge sur son créneau, pour qu'un décalage de cron ne sonne pas.
AGE_MAX_H = {
    "enrichissement data.gouv": 26,
    "réconciliation PostgreSQL": 26,
    "dispatch campagnes": 26,
    "sauvegarde": 26,
}

# Un rappel par jour pour un problème qui dure, et pas davantage.
RAPPEL_H = 24


def _envoyer(texte: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        print("[alertes] TELEGRAM_BOT_TOKEN/CHAT_ID absents — rien n'est envoyé")
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": texte,
                                       "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
            return r.status == 200
    except Exception as e:  # noqa: BLE001
        print(f"[alertes] envoi Telegram impossible : {e}")
        return False


def _charger_etat() -> dict:
    try:
        return json.loads(ETAT_PATH.read_text())
    except Exception:  # noqa: BLE001
        return {"problemes": {}}


def _sauver_etat(e: dict) -> None:
    ETAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    e["verifie_a"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ETAT_PATH.write_text(json.dumps(e, ensure_ascii=False, indent=2))


def diagnostic() -> dict:
    """Les problèmes en cours, chacun sous une clé stable (c'est elle qui porte l'anti-spam)."""
    import etat_technique as et
    problemes: dict[str, str] = {}

    try:
        taches = et._taches()
    except Exception as e:  # noqa: BLE001
        taches = {}
        problemes["releve"] = f"🩺 Le relevé technique lui-même est en panne : {e}"

    # Lecture massive de la base de contacts, sur l'HEURE écoulée — même fenêtre que le
    # quota, même seuil (1 000 fiches). L'alerte part donc à l'instant où le compte touche
    # le plafond : le quota bloque, l'alerte prévient, dans le même mouvement.
    #
    # Le calcul, à partir du terrain (Camille, 2026-08-21) : un commercial passe AU PLUS
    # 30 appels dans l'heure. Trente fiches ouvertes, plus la liste pour les trouver — huit
    # pages de 25 si la recherche est laborieuse, soit 200 lignes. Un usage intense tient
    # donc dans ~230 fiches/heure. Le plafond de 1 000 laisse un facteur QUATRE : personne
    # ne peut l'atteindre en travaillant. Qui le touche ne travaille pas, il aspire.
    #
    # Clé par utilisateur : deux comptes différents = deux alertes distinctes.
    try:
        import garde_lecture as gl
        for lecteur in gl.gros_lecteurs(heures=1, seuil=1000):
            # L'espace des milliers se fabrique sur le NOMBRE seul : un `.replace(",", " ")`
            # sur toute la phrase mangeait aussi les virgules du texte.
            fiches = f"{lecteur['lignes']:,}".replace(",", " ")
            problemes[f"aspiration:{lecteur['utilisateur']}"] = (
                f"🔥 *ASPIRATION DE LA BASE — compte « {lecteur['utilisateur']} »* "
                f"({lecteur['role'] or 'rôle inconnu'})\n"
                f"   {fiches} fiches lues en {lecteur['requetes']} requêtes dans l'heure. "
                f"Plafond atteint, lecture bloquée.\n"
                f"   Usage normal d'un commercial : ~230 fiches/h pour 30 appels.")
    except Exception as e:  # noqa: BLE001
        problemes["garde_lecture"] = f"🔥 Le garde-fou de lecture est illisible : {e}"

    for nom, limite in AGE_MAX_H.items():
        info = taches.get(nom) or {}
        if not info.get("present"):
            problemes[f"tache:{nom}"] = f"⏰ *{nom}* : aucune trace d'exécution."
        elif float(info.get("heures") or 0) > limite:
            problemes[f"tache:{nom}"] = (
                f"⏰ *{nom}* : dernier passage il y a {info['heures']} h "
                f"(limite {limite} h).")

    try:
        for nom, en_ligne in (et._services() or {}).items():
            if not en_ligne:
                problemes[f"service:{nom}"] = f"🛑 *{nom}* : service arrêté."
    except Exception as e:  # noqa: BLE001
        problemes["services"] = f"🛑 État des services illisible : {e}"

    # Délivrabilité : la configuration du domaine, les listes noires et les taux
    # d'ouverture, de rebond et de plainte. Rien de tout cela n'apparaît dans les logs de
    # tâche — une campagne qui n'arrive plus s'affiche « envoyée » jusqu'au bout.
    try:
        import sante_envoi
        problemes.update(sante_envoi.problemes("lcr"))
    except Exception as e:  # noqa: BLE001
        problemes["sante_envoi"] = f"📉 La surveillance de délivrabilité est illisible : {e}"

    # Collecte : un blocage fournisseur n'écrit rien dans les logs de tâche, il faut le
    # demander au scrapper lui-même.
    try:
        import autoscrape_backend as asb
        live = asb.read_status("lcr") or {}
        if live.get("blocked"):
            problemes["scrape:bloque"] = (
                f"🕷 *Collecte bloquée* : {live.get('message') or 'fournisseur en refus'}.")
    except Exception:  # noqa: BLE001 — pas de statut = pas d'alerte, ce n'est pas un problème
        pass

    return problemes


def controler(forcer: bool = False) -> dict:
    """Compare avec le dernier passage et notifie ce qui a changé."""
    maintenant = datetime.now(timezone.utc)
    etat = _charger_etat()
    connus: dict = etat.get("problemes") or {}
    actuels = diagnostic()

    nouveaux = [k for k in actuels if k not in connus]
    regles = [k for k in connus if k not in actuels]
    a_rappeler = []
    for k in actuels:
        if k in connus:
            try:
                depuis = datetime.fromisoformat(connus[k]["depuis"])
                dernier = datetime.fromisoformat(connus[k].get("notifie_a") or connus[k]["depuis"])
            except Exception:  # noqa: BLE001
                continue
            if (maintenant - dernier).total_seconds() / 3600 >= RAPPEL_H:
                a_rappeler.append((k, depuis))

    lignes = []
    if nouveaux or forcer:
        # Une aspiration de la base et une sauvegarde en retard ne se lisent pas de la même
        # façon : le titre doit trancher avant même qu'on lise le détail. Sinon l'alerte
        # grave se noie dans le train-train des tâches en retard.
        a_traiter = nouveaux or list(actuels)
        securite = [k for k in a_traiter if k.startswith("aspiration:")]
        if securite:
            noms = ", ".join(k.split(":", 1)[1] for k in securite)
            lignes.append(f"🔥🚨 *SÉCURITÉ — {noms}* 🚨🔥")
        else:
            lignes.append("🔴 *Genesis — anomalie détectée*")
        # Le sujet grave d'abord, le reste ensuite.
        for k in sorted(a_traiter, key=lambda x: not x.startswith("aspiration:")):
            lignes.append(f"• {actuels[k]}")
    for k, depuis in a_rappeler:
        heures = round((maintenant - depuis).total_seconds() / 3600)
        lignes.append(f"🔁 Toujours en panne depuis {heures} h : {actuels[k]}")
    if regles:
        lignes.append("🟢 *Rétabli* : " + " · ".join(
            k.split(":", 1)[-1] for k in regles))

    envoye = False
    if lignes:
        envoye = _envoyer("\n".join(lignes))

    suivant = {}
    for k in actuels:
        ancien = connus.get(k) or {}
        notifie = maintenant.isoformat(timespec="seconds") if (
            k in nouveaux or any(k == r[0] for r in a_rappeler) or forcer
        ) else ancien.get("notifie_a")
        suivant[k] = {"depuis": ancien.get("depuis") or maintenant.isoformat(timespec="seconds"),
                      "notifie_a": notifie, "texte": actuels[k]}
    etat["problemes"] = suivant
    _sauver_etat(etat)

    return {"ok": True, "problemes": len(actuels), "nouveaux": nouveaux,
            "regles": regles, "rappels": [k for k, _ in a_rappeler],
            "notifie": envoye, "detail": actuels}


if __name__ == "__main__":
    if "--test" in sys.argv:
        # Le test ne se contente pas de dire « ça marche » : il montre à quoi ressemblera
        # chaque famille d'alerte. On ne découvre pas la mise en forme d'un message grave
        # le jour où il arrive. L'en-tête dit clairement qu'il s'agit d'un essai — un
        # message de test qu'on prend pour une vraie alerte est pire qu'un silence.
        ok = _envoyer("\n".join([
            "🔔 *Genesis — TEST de la sonnerie* (aucune anomalie réelle)",
            "",
            "Voici la forme de chaque alerte :",
            "",
            "🔥 *ASPIRATION DE LA BASE — compte « exemple »* (commercial)",
            "   1 200 fiches lues en 12 requêtes dans l'heure. Plafond atteint, lecture bloquée.",
            "   Usage normal d'un commercial : ~230 fiches/h pour 30 appels.",
            "⏰ *sauvegarde* : dernier passage il y a 31 h (limite 26 h).",
            "🛑 *genesis-ui* : service arrêté.",
            "🕷 *Collecte bloquée* : fournisseur en refus.",
            "🔁 Toujours en panne depuis 24 h : …",
            "🟢 *Rétabli* : …",
            "",
            "Une aspiration change le TITRE du message et passe en tête de liste.",
        ]))
        print(json.dumps({"envoye": ok}, ensure_ascii=False))
    elif "--etat" in sys.argv:
        print(json.dumps({"problemes": diagnostic()}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(controler(forcer="--force" in sys.argv),
                         ensure_ascii=False, indent=2))
