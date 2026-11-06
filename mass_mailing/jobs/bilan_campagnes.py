#!/usr/bin/env python3
"""mass_mailing/jobs/bilan_campagnes.py — bilan de chaque campagne pour le carnet de chauffe (20/10/2026).

Camille : « sur le serveur, pour que tu apprennes de chaque campagne ». Chaque nuit (worker, 5 h Paris),
pour chaque espace (interne + clients) et chaque campagne qui a envoyé :
- mesure les chiffres qui comptent pour la chauffe et l'hygiène (rebonds, plaintes, désinscriptions,
  ouvertures BRUTES et HUMAINES — au moins 60 s après la livraison —, par webmail, pro / perso) ;
- garde la photo du jour dans `bilans_campagne` (une ligne par campagne et par jour) ;
- réécrit `.claude/skills/chauffe-hygiene/references/journal-campagnes.md`, que Claude relit à chaque
  session avec la méthode (SKILL.md). Les LEÇONS ne s'écrivent pas seules : Claude les valide à la main.

Lecture seule sur les campagnes ; seules `bilans_campagne` et le fichier du journal sont écrits.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from infra import clients, ouvertures, pg  # noqa: E402
from jobs import capacite  # noqa: E402

HEURE_PARIS = 5
PARIS = ZoneInfo("Europe/Paris")
JOURNAL = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "chauffe-hygiene" / "references" / "journal-campagnes.md"
DELAI_HUMAIN_S = 60
WEBMAILS = {"gmail", "microsoft", "yahoo", "orange", "laposte", "free", "sfr", "icloud", "bouygues", "gmx"}

# Seuils d'alerte du carnet (SKILL.md § 3) — mêmes ordres de grandeur que jobs/capacite.py.
SEUILS = {"hard": 0.02, "plaintes": 0.003, "desinscrits": 0.01, "rapides": 0.40}


def appliquer_schema() -> None:
    with pg.espace(pg.SCHEMA):
        pg.ecrire("""
            CREATE TABLE IF NOT EXISTS bilans_campagne (
                espace       TEXT        NOT NULL,
                campaign_id  UUID        NOT NULL,
                jour         DATE        NOT NULL,
                donnees      JSONB       NOT NULL,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (espace, campaign_id, jour)
            )""")


def _pct(n: int, d: int) -> float | None:
    return round(100 * n / d, 1) if d else None


def alertes(b: dict) -> list[str]:
    """Fonction PURE : ce qui dépasse les seuils du carnet."""
    out = []
    if b["envoyes"] and b["hard"] / b["envoyes"] > SEUILS["hard"]:
        out.append(f"rebonds durs {_pct(b['hard'], b['envoyes'])} % > {SEUILS['hard']:.0%}")
    if b["livres"] and b["plaintes"] / b["livres"] > SEUILS["plaintes"]:
        out.append(f"plaintes {_pct(b['plaintes'], b['livres'])} % > 0,3 %")
    if b["livres"] and b["desinscrits"] / b["livres"] > SEUILS["desinscrits"]:
        out.append(f"désinscriptions {_pct(b['desinscrits'], b['livres'])} % > 1 %")
    if b["ouverts_brut"] >= 20 and b["ouverts_rapides"] / b["ouverts_brut"] > SEUILS["rapides"]:
        out.append(f"{_pct(b['ouverts_rapides'], b['ouverts_brut'])} % des ouvertures en moins de 60 s (antivirus) : "
                   "le taux brut ment")
    return out


def mesurer(campaign_id: str) -> dict:
    """Chiffres d'une campagne dans l'espace COURANT (pg.espace posé par l'appelant)."""
    c = pg.ligne("""SELECT internal_name, subject, status, started_at, from_local, sending_domains
                      FROM campaigns WHERE id = %(c)s""", {"c": campaign_id})
    lignes = pg.lignes("""
        SELECT split_part(r.email_normalized, '@', 2) AS d,
               count(*) FILTER (WHERE r.submitted_at IS NOT NULL) AS envoyes,
               count(*) FILTER (WHERE r.delivered_at IS NOT NULL) AS livres,
               count(*) FILTER (WHERE r.bounce_type ILIKE 'hard%%') AS hard,
               count(*) FILTER (WHERE r.bounced_at IS NOT NULL AND r.bounce_type NOT ILIKE 'hard%%') AS soft,
               count(*) FILTER (WHERE r.complained_at IS NOT NULL) AS plaintes,
               count(*) FILTER (WHERE r.unsubscribed_at IS NOT NULL) AS desinscrits,
               count(*) FILTER (WHERE r.opened_at IS NOT NULL) AS ouverts_brut,
               count(*) FILTER (WHERE r.opened_at IS NOT NULL AND r.delivered_at IS NOT NULL
                                  AND r.opened_at < r.delivered_at + make_interval(secs => %(s)s)) AS ouverts_rapides,
               count(*) FILTER (WHERE r.opened_at IS NOT NULL AND r.delivered_at IS NOT NULL
                                  AND r.opened_at >= r.delivered_at + make_interval(secs => %(s)s)
                                  AND NOT EXISTS (SELECT 1 FROM clicks k WHERE k.recipient_id = r.id AND k.verdict = 'robot')) AS ouverts_humains,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM clicks k WHERE k.recipient_id = r.id AND k.verdict = 'humain')) AS clics_humains
          FROM recipients r WHERE r.campaign_id = %(c)s GROUP BY 1""", {"c": campaign_id, "s": DELAI_HUMAIN_S})
    cles = ("envoyes", "livres", "hard", "soft", "plaintes", "desinscrits", "ouverts_brut", "ouverts_rapides",
            "ouverts_humains", "clics_humains")
    tot = {k: 0 for k in cles}
    groupes: dict[str, dict] = {}
    for x in lignes:
        g = capacite.groupe_de(x["d"])
        a = groupes.setdefault(g, {"envoyes": 0, "livres": 0, "ouverts_humains": 0})
        for k in cles:
            tot[k] += int(x[k] or 0)
        for k in a:
            a[k] += int(x[k] or 0)
    pro = {"envoyes": 0, "livres": 0, "ouverts_humains": 0}
    perso = dict(pro)
    for g, a in groupes.items():
        cible = perso if g in WEBMAILS else pro
        for k in cible:
            cible[k] += a[k]
    b = {**tot, "nom": c["internal_name"], "objet": c["subject"], "statut": c["status"],
         "debut": c["started_at"].astimezone(PARIS).date().isoformat() if c["started_at"] else None,
         # Adresse réellement utilisée (recipients.from_email), sinon local@domaine déclaré.
         "expediteur": pg.valeur("SELECT max(from_email) FROM recipients WHERE campaign_id = %(c)s AND from_email IS NOT NULL",
                                 {"c": campaign_id}) or (f"{c['from_local']}@{(c['sending_domains'] or ['?'])[0]}" if c.get("from_local") else None),
         "par_webmail": {g: {**a, "taux_humain": _pct(a["ouverts_humains"], a["livres"])}
                         for g, a in sorted(groupes.items(), key=lambda kv: -kv[1]["envoyes"]) if a["envoyes"]},
         "pro": {**pro, "taux_humain": _pct(pro["ouverts_humains"], pro["livres"])},
         "perso": {**perso, "taux_humain": _pct(perso["ouverts_humains"], perso["livres"])}}
    b.update(qui_ouvre(campaign_id))
    b["alertes"] = alertes(b)
    return b


def qui_ouvre(campaign_id: str) -> dict:
    """Ouvertures classées par IP et logiciel (infra/ouvertures.py) quand le fournisseur les donne
    (Resend). Sinon {} : le journal garde la règle des 60 s."""
    evs = pg.lignes("""
        SELECT r.id, split_part(r.email_normalized, '@', 2) AS d,
               w.raw_payload::jsonb #>> '{data,open,ipAddress}' AS ip, w.raw_payload::jsonb #>> '{data,open,userAgent}' AS ua,
               EXTRACT(EPOCH FROM (w.received_at - r.delivered_at)) AS secondes
          FROM recipients r
          JOIN webhook_events w ON w.provider = 'resend' AND w.event_type ILIKE '%%open%%'
                               AND w.raw_payload::jsonb #>> '{data,email_id}' = r.provider_message_id
         WHERE r.campaign_id = %(c)s AND r.provider_message_id IS NOT NULL""", {"c": campaign_id})
    if not evs:
        return {}
    par: dict = {}
    sources: dict[str, int] = {}
    for e in evs:
        v, src = ouvertures.classer(ouvertures.organisation(e["ip"] or ""), e["ua"] or "", e["secondes"])
        par.setdefault(e["id"], {"d": e["d"], "v": []})["v"].append(v)
        sources[f"{v} · {src}"] = sources.get(f"{v} · {src}", 0) + 1
    tot = {ouvertures.HUMAIN: 0, ouvertures.APPLE: 0, ouvertures.MACHINE: 0}
    groupes: dict[str, int] = {}
    for x in par.values():
        v = ouvertures.verdict_destinataire(x["v"])
        tot[v] += 1
        if v == ouvertures.HUMAIN:
            g = capacite.groupe_de(x["d"])
            groupes[g] = groupes.get(g, 0) + 1
    return {"ouverts_surs": tot[ouvertures.HUMAIN], "ouverts_apple": tot[ouvertures.APPLE], "ouverts_machines": tot[ouvertures.MACHINE],
            "surs_par_webmail": groupes, "sources_ouvertures": dict(sorted(sources.items(), key=lambda kv: -kv[1]))}


def _espaces() -> list[tuple[str, str]]:
    return [("interne", pg.SCHEMA)] + [(c["slug"], c["schema_pg"]) for c in clients.lister()]


def tourner(jour: date | None = None) -> dict:
    appliquer_schema()
    ouvertures.appliquer_schema()
    jour = jour or datetime.now(PARIS).date()
    n = 0
    for nom, schema in _espaces():
        with pg.espace(schema):
            ids = [str(x["id"]) for x in pg.lignes("""SELECT DISTINCT campaign_id AS id FROM recipients
                                                       WHERE submitted_at IS NOT NULL""")]
            bilans = [(i, mesurer(i)) for i in ids]
        with pg.espace(pg.SCHEMA):
            for i, b in bilans:
                pg.ecrire("""INSERT INTO bilans_campagne (espace, campaign_id, jour, donnees) VALUES (%(e)s, %(c)s, %(j)s, %(d)s)
                             ON CONFLICT (espace, campaign_id, jour) DO UPDATE SET donnees = EXCLUDED.donnees, created_at = now()""",
                          {"e": nom, "c": i, "j": jour, "d": json.dumps(b, default=str)})
                n += 1
    ecrire_journal()
    return {"campagnes": n, "journal": str(JOURNAL)}


def _ligne_webmails(pw: dict) -> str:
    return " · ".join(f"{capacite.NOMS.get(g, g)} {a['envoyes']} → {a['taux_humain'] if a['taux_humain'] is not None else '—'} %"
                      for g, a in list(pw.items())[:8])


def rendre(lignes: list[dict]) -> str:
    """Fonction PURE : le journal Markdown (dernière photo de chaque campagne, la plus récente en haut)."""
    out = ["# Journal des campagnes — généré chaque nuit par `mass_mailing/jobs/bilan_campagnes.py`",
           "",
           "> Ne pas modifier à la main : le fichier est réécrit à 5 h (Paris). Les leçons validées vont dans",
           "> `../SKILL.md` § 5. « Humaines » = ouverture au moins 60 s après la livraison (règle grossière) ;",
           "> « Qui ouvre » = classement par IP + logiciel (infra/ouvertures.py), à préférer quand il existe.",
           ""]
    for x in lignes:
        b = x["donnees"]
        out += [f"## {b['nom']} — espace {x['espace']} — photo du {x['jour']}",
                f"- Statut **{b['statut']}** · début {b['debut'] or '—'} · expéditeur `{b.get('expediteur') or '—'}` · objet « {b.get('objet') or '—'} »",
                f"- Envoyés **{b['envoyes']}** · livrés {b['livres']} ({_pct(b['livres'], b['envoyes'])} %) · "
                f"rebonds durs {b['hard']} ({_pct(b['hard'], b['envoyes'])} %) · doux {b['soft']} · "
                f"plaintes {b['plaintes']} · désinscrits {b['desinscrits']}",
                f"- Ouvertures : brutes {b['ouverts_brut']} ({_pct(b['ouverts_brut'], b['livres'])} %) · "
                f"**humaines {b['ouverts_humains']} ({_pct(b['ouverts_humains'], b['livres'])} %)** · "
                f"en moins de 60 s {b['ouverts_rapides']} · clics humains {b['clics_humains']}",
                *([f"- **Qui ouvre (IP + logiciel)** : humains sûrs **{b['ouverts_surs']} ({_pct(b['ouverts_surs'], b['livres'])} %)** · "
                   f"Apple Mail {b['ouverts_apple']} (lu ou non : inconnu) · machines {b['ouverts_machines']} · "
                   f"sources : {', '.join(f'{k} {n}' for k, n in sorted(b['sources_ouvertures'].items(), key=lambda kv: -kv[1])[:6])}",
                   f"- Humains sûrs par webmail : "
                   + (" · ".join(f"{capacite.NOMS.get(g, g)} {n}/{b['par_webmail'].get(g, {}).get('livres', 0)}"
                                 for g, n in sorted(b['surs_par_webmail'].items(), key=lambda kv: -kv[1])) or "aucun")]
                  if "ouverts_surs" in b else []),
                f"- Pro {b['pro']['envoyes']} → {b['pro']['taux_humain']} % · perso {b['perso']['envoyes']} → {b['perso']['taux_humain']} %",
                f"- Webmails : {_ligne_webmails(b['par_webmail'])}",
                f"- Alertes : {' ; '.join(b['alertes']) if b['alertes'] else 'aucune'}",
                ""]
    return "\n".join(out)


def ecrire_journal() -> None:
    with pg.espace(pg.SCHEMA):
        lignes = pg.lignes("""SELECT DISTINCT ON (espace, campaign_id) espace, campaign_id, jour, donnees
                                FROM bilans_campagne ORDER BY espace, campaign_id, jour DESC""")
    lignes.sort(key=lambda x: (x["donnees"].get("debut") or "", str(x["jour"])), reverse=True)
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=JOURNAL.parent, prefix=".journal-")
    with os.fdopen(fd, "w") as f:
        f.write(rendre(lignes))
    os.chmod(tmp, 0o644)
    os.replace(tmp, JOURNAL)


if __name__ == "__main__":
    print(tourner())
