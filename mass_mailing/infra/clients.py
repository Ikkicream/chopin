#!/usr/bin/env python3
"""mass_mailing/infra/clients.py — les clients de la plateforme Mass Email (SaaS, 13/10/2026).

Décision de Camille le 13/10 : Mass Email devient une plateforme pour des clients. Chaque
client a son espace, Camille garde la vue superadmin, et les données sont **en silo** :

- un client = un schéma PostgreSQL `mmc_<slug>`, créé à partir du même `schema.sql` que
  l'espace interne. Campagnes, destinataires (une base par campagne, déjà le cas),
  suppressions, événements, file de jobs : rien n'est partagé entre deux clients ;
- la fiche du client (`mass_mailing.clients`) et ses comptes (`mass_mailing.utilisateurs`)
  sont des tables de PLATEFORME, dans `mass_mailing` ;
- un client n'envoie QUE par Resend ou SES — jamais par Sweego, qui reste l'outil interne.

Ce module ajoute dans chaque schéma client ce que l'espace interne n'a pas : les domaines
d'envoi connectés chez le fournisseur (avec leur état de mise en service) et les adresses
expéditrices avec leur plan de montée en volume (warm-up).

    python3 -m infra.clients creer zylio "Zylio" --reply-to contact@zylio.email
    python3 -m infra.clients lister
"""
from __future__ import annotations

import json
import re
import sys
from zoneinfo import ZoneInfo
from datetime import date, datetime, timedelta

from . import pg

SLUG = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

# Tables propres aux espaces clients (rejouables : IF NOT EXISTS partout).
SQL_CLIENT = """
-- Domaine d'envoi connecté chez le fournisseur. L'état avance par étapes vérifiées, jamais
-- par déclaration : c'est la machine (DNS, API du fournisseur, auto-tests) qui le fait passer.
CREATE TABLE IF NOT EXISTS domaines_envoi (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domaine          TEXT        NOT NULL UNIQUE,          -- ex. news.zylio.email
    zone             TEXT        NOT NULL,                 -- ex. zylio.email
    fournisseur      TEXT        NOT NULL CHECK (fournisseur IN ('resend','ses')),
    fournisseur_id   TEXT,                                 -- id du domaine chez le fournisseur
    region           TEXT        NOT NULL,                 -- FIGÉE à la création (UE)
    etat             TEXT        NOT NULL DEFAULT 'cree'
                     CHECK (etat IN ('cree','dns_a_poser','dns_publie','verifie',
                                     'pret','warmup','en_service','suspendu','echec')),
    enregistrements  JSONB       NOT NULL DEFAULT '[]'::jsonb,   -- plan DNS (valeurs du fournisseur)
    audit            JSONB,                                      -- dernier audit DNS (dns-audit)
    statut_fournisseur TEXT,                                     -- not_started / pending / verified…
    -- Les six conditions avant le 1er envoi marketing (skill email-domain-setup §8)
    c_region_ue      BOOLEAN     NOT NULL DEFAULT false,
    c_dns_ok         BOOLEAN     NOT NULL DEFAULT false,
    c_webhooks_ok    BOOLEAN     NOT NULL DEFAULT false,
    c_desinscription_ok BOOLEAN  NOT NULL DEFAULT false,
    c_postmaster_ok  BOOLEAN     NOT NULL DEFAULT false,   -- confirmé par une personne
    c_senderhub_ok   BOOLEAN     NOT NULL DEFAULT false,   -- confirmé par une personne
    journal          JSONB       NOT NULL DEFAULT '[]'::jsonb,   -- étapes horodatées
    verifie_at       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 7e condition (14/10/2026) : suivi des ouvertures réellement actif chez le fournisseur.
ALTER TABLE domaines_envoi ADD COLUMN IF NOT EXISTS c_suivi_ok BOOLEAN NOT NULL DEFAULT false;

-- Adresse expéditrice et son warm-up. Le plafond du jour se LIT dans le plan : l'envoi
-- ne le dépasse jamais, quel que soit le volume de la campagne.
CREATE TABLE IF NOT EXISTS expediteurs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    adresse          TEXT        NOT NULL UNIQUE,          -- ex. hello@news.zylio.email
    nom_affiche      TEXT        NOT NULL,
    reply_to         TEXT,
    domaine_id       UUID        NOT NULL REFERENCES domaines_envoi(id) ON DELETE CASCADE,
    warmup_debut     DATE,
    warmup_plan      JSONB,                                -- sortie de warmup-plan.mjs
    plafond_fournisseur INT,                               -- ex. 100/jour sur Resend gratuit
    actif            BOOLEAN     NOT NULL DEFAULT true,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Identifiant du message chez le fournisseur (Resend/SES). `sweego_message_id` reste
-- celui de l'espace interne ; un client n'en a jamais.
ALTER TABLE recipients ADD COLUMN IF NOT EXISTS provider TEXT;
ALTER TABLE recipients ADD COLUMN IF NOT EXISTS provider_message_id TEXT;
CREATE INDEX IF NOT EXISTS recipients_provider_msg_idx ON recipients (provider_message_id)
    WHERE provider_message_id IS NOT NULL;
"""


def schema_de(slug: str) -> str:
    if not SLUG.match(slug or ""):
        raise ValueError(f"identifiant client invalide : {slug!r} (minuscules, chiffres, _)")
    return f"mmc_{slug}"


def _plateforme():
    return pg.espace(pg.SCHEMA)


def lister() -> list[dict]:
    with _plateforme():
        return pg.lignes("SELECT * FROM clients ORDER BY created_at")


def par_slug(slug: str) -> dict | None:
    with _plateforme():
        return pg.ligne("SELECT * FROM clients WHERE slug = %(s)s", {"s": slug})


def provisionner(slug: str) -> dict:
    """Crée ou met à niveau le schéma du client. Idempotent : rejouable à chaque déploiement."""
    schema = schema_de(slug)
    r = pg.appliquer_schema(schema=schema)
    with pg.espace(schema):
        pg.ecrire(SQL_CLIENT)
        # Tables créées paresseusement par certains agents de l'espace interne : posées
        # d'emblée, pour qu'aucun module ne découvre un schéma client incomplet.
        for module in ("routage", "rebonds"):
            try:
                mod = __import__(f"jobs.{module}", fromlist=["SCHEMA"])
                pg.ecrire(mod.SCHEMA)
            except Exception as e:  # noqa: BLE001
                print(f"[clients] schéma {module} non posé dans {schema} : {e}", flush=True)
        n = pg.valeur("SELECT count(*) FROM information_schema.tables WHERE table_schema = %(s)s",
                      {"s": schema})
    return {"schema": schema, "tables": int(n or 0), "base": len(r["tables"])}


def creer(slug: str, nom: str, reply_to: str | None = None, fournisseur: str = "resend",
          raison_sociale: str | None = None, adresse_postale: str | None = None) -> dict:
    schema = schema_de(slug)
    with _plateforme():
        pg.ecrire("""INSERT INTO clients (slug, nom, schema_pg, fournisseur, reply_to, raison_sociale, adresse_postale)
                     VALUES (%(s)s, %(n)s, %(sc)s, %(f)s, %(r)s, %(rs)s, %(ap)s)
                     ON CONFLICT (slug) DO UPDATE SET nom = EXCLUDED.nom,
                          reply_to = COALESCE(EXCLUDED.reply_to, clients.reply_to),
                          raison_sociale = COALESCE(EXCLUDED.raison_sociale, clients.raison_sociale),
                          adresse_postale = COALESCE(EXCLUDED.adresse_postale, clients.adresse_postale)""",
                  {"s": slug, "n": nom, "sc": schema, "f": fournisseur, "r": reply_to,
                   "rs": raison_sociale, "ap": adresse_postale})
    p = provisionner(slug)
    return {**(par_slug(slug) or {}), "provision": p}


# ── Warm-up ──────────────────────────────────────────────────────────────────

# 1re semaine jour par jour (Camille, 13/10/2026 : « 400 le 1er jour, beaucoup trop fort ;
# j'aurais fait 10 emails/heure ») : 90 le 1er jour d'envoi = 10/heure sur la plage client
# 9h-18h, puis ×1,5 par jour ouvré jusqu'au palier de la semaine. Jours ouvrés seulement :
# les clients n'envoient pas le week-end, la rampe n'avance donc pas ces jours-là.
RAMPE_SEMAINE_1 = (90, 135, 200, 300, 400)


def plan_warmup(cible_jour: int, debut: date, premier_palier: int = 400) -> dict:
    """1re semaine : rampe quotidienne RAMPE_SEMAINE_1 (jours ouvrés) jusqu'à `premier_palier` ;
    ensuite doublement hebdomadaire tant que bounces < 2 % et plaintes < 0,1 %."""
    semaines, cap, k = [], max(50, min(premier_palier, cible_jour)), 0
    while True:
        k += 1
        d = debut + timedelta(days=7 * (k - 1))
        semaines.append({"semaine": k, "du": d.isoformat(), "au": (d + timedelta(days=6)).isoformat(),
                         "plafond_jour": min(cap, cible_jour)})
        if cap >= cible_jour or k >= 20:
            break
        cap *= 2
    ouvres = [debut + timedelta(days=i) for i in range(7) if (debut + timedelta(days=i)).weekday() < 5]
    semaines[0]["jours"] = [{"du": j.isoformat(), "plafond_jour": min(v, semaines[0]["plafond_jour"])}
                            for j, v in zip(ouvres, RAMPE_SEMAINE_1)]
    return {"cible_jour": cible_jour, "debut": debut.isoformat(), "semaines": semaines,
            "conditions": {"bounces_max_pct": 2.0, "plaintes_max_pct": 0.1}}


def plafond_du_jour(expediteur: dict, jour: date | None = None) -> int:
    """Combien cette adresse peut envoyer aujourd'hui. 0 avant le début du warm-up."""
    jour = jour or datetime.now(ZoneInfo("Europe/Paris")).date()   # le jour À PARIS (serveur en UTC)
    plan = expediteur.get("warmup_plan") or {}
    if isinstance(plan, str):
        plan = json.loads(plan)
    cap = 0
    for s in plan.get("semaines") or []:
        if date.fromisoformat(s["du"]) <= jour:
            cap = int(s["plafond_jour"])
            jours = s.get("jours") or []
            if jours and jour <= date.fromisoformat(s["au"]):
                passes = [x for x in jours if date.fromisoformat(x["du"]) <= jour]
                cap = int((passes[-1] if passes else jours[0])["plafond_jour"])
    if plan.get("semaines") and jour > date.fromisoformat(plan["semaines"][-1]["au"]):
        cap = int(plan["cible_jour"])
    pf = expediteur.get("plafond_fournisseur")
    return min(cap, int(pf)) if pf else cap


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("creer")
    c.add_argument("slug"); c.add_argument("nom")
    c.add_argument("--reply-to"); c.add_argument("--fournisseur", default="resend")
    sp.add_parser("lister")
    p = sp.add_parser("provisionner"); p.add_argument("slug")
    a = ap.parse_args()
    if a.cmd == "creer":
        out = creer(a.slug, a.nom, a.reply_to, a.fournisseur)
    elif a.cmd == "provisionner":
        out = provisionner(a.slug)
    else:
        out = lister()
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    sys.exit(0)
