#!/usr/bin/env python3
"""Aucun horaire ne doit être aménagé pour éviter un verrou DuckDB (2026-08-27).

## Ce que ce fichier empêche de refaire

Le 2026-08-27, en remontant le départ du dispatch à 9h, j'ai ÉLARGI le créneau pendant
lequel le scraping ne démarre pas — pour éviter qu'un scrape tienne le verrou DuckDB au
moment du premier lot. Camille : « on fait toute une migration sur postgresql pour ne plus
être dépendant de duckdb et ce verrou il y a 1 semaine et là tu me dis exactement le
contraire ».

Elle avait raison. Ce créneau était un vestige d'AVANT la migration, et le maintenir
revenait à protéger un verrou dont la plateforme s'était affranchie — pire, à décaler le
routage pour l'éviter.

La cause de l'erreur n'était pas le code : c'était la fiche de mémoire projet, écrite avant
la migration, qui prescrivait ce créneau noir sur blanc. Un commentaire et une fiche
corrigée ne suffisent pas — il faut quelque chose qui ÉCHOUE si quelqu'un le réintroduit.

## L'invariant

Dans le chemin d'envoi, un verrou DuckDB dégrade un miroir ; il ne met plus rien en danger.
Si un verrou gêne encore un chemin, c'est que ce chemin n'a pas fini sa migration — la
réponse est de le migrer, pas de lui aménager une plage horaire.
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'ÉCHEC'}  {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


print("\nAucun créneau n'est réservé au routage")
import autoscrape_daily as asd

verifie("le créneau « dispatch » n'existe plus",
        not hasattr(asd, "DISPATCH_RESERVE_UTC"),
        f"({getattr(asd, 'DISPATCH_RESERVE_UTC', None)})")
verifie("un seul créneau reste, celui de l'entretien",
        len(asd.CRENEAUX_RESERVES) == 1, f"({asd.CRENEAUX_RESERVES})")
verifie("et il protège pg_reconcile, une opération PostgreSQL",
        asd.CRENEAUX_RESERVES[0] == asd.ENTRETIEN_RESERVE_UTC,
        f"({asd.CRENEAUX_RESERVES[0]})")

src = (RACINE / "scripts" / "autoscrape_daily.py").read_text()
verifie("le module explique POURQUOI il a été retiré",
        "migration PostgreSQL" in src and "vestige" in src.lower()
        or "SUPPRIMÉ le 2026-08-27" in src)

print("\nLe chemin d'envoi ne dépend plus de DuckDB pour ses garanties")
ce = (RACINE / "scripts" / "campaign_engine.py").read_text()
i = ce.index("def _conn(")
verifie("campaign_engine parle à PostgreSQL", "psycopg2" in ce[i:i + 400])
verifie("il n'ouvre plus DuckDB du tout", "duckdb.connect" not in ce)

cpb = (RACINE / "scripts" / "contacts_pool_backend.py").read_text()
j = cpb.index("def mark_pushed_to_emelia")
corps = cpb[j:j + 3000]
i_pg = corps.find('_miroir("record_send"')
i_duck = corps.find("c = _conn()")
verifie("le journal PostgreSQL est écrit AVANT d'ouvrir DuckDB",
        0 <= i_pg < i_duck, f"(pg@{i_pg}, duckdb@{i_duck})")

md = (RACINE / "scripts" / "maildoso_backend.py").read_text()
verifie("un échec du journal DuckDB n'interrompt pas l'envoi",
        "journal DuckDB indisponible" in md and "le journal PostgreSQL fait foi" in md)
verifie("le quota du jour se lit dans le journal, pas dans DuckDB",
        "expediteur.boites(site)" in md or "import expediteur" in md)
verifie("la cadence par boîte aussi",
        "_secondes_depuis_dernier_envoi" in md and "FROM email_events" in md)

print("\nLe routage part quand la fenêtre est ouverte, pas plus tard")
import subprocess

r = subprocess.run(["crontab", "-u", "autoblog", "-l"], capture_output=True, text=True)
if r.returncode:
    print("  …  crontab illisible depuis ce compte, contrôle ignoré")
else:
    lignes = [l for l in r.stdout.splitlines()
              if "campaign_engine" in l and "dispatch" in l and not l.strip().startswith("#")]
    verifie("un cron déclenche le dispatch", bool(lignes), f"({len(lignes)})")
    if lignes:
        heures = lignes[0].split()[1]
        # La fenêtre ouvre à 08:01 Paris = 06:01 UTC en été. Un départ à 08:30 UTC
        # (10:30 Paris) laissait deux heures et demie de fenêtre ouverte sans rien envoyer.
        premiere = int(heures.split("-")[0].split(",")[0])
        verifie("il démarre au plus tard à 07:00 UTC (09:00 Paris)",
                premiere <= 7, f"({heures} UTC)")
        verifie("il repasse plusieurs fois — un lot bloqué ne perd plus la journée",
                "," in lignes[0].split()[0] or "/" in lignes[0].split()[0],
                f"(minutes : {lignes[0].split()[0]})")

print("\n" + "=" * 62)
if ECHECS:
    print(f"{len(ECHECS)} ÉCHEC(S) : " + ", ".join(ECHECS))
    raise SystemExit(1)
print("Tout est vert.")
