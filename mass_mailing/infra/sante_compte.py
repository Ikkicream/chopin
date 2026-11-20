#!/usr/bin/env python3
"""mass_mailing/infra/sante_compte.py — bilan de santé d'un compte client (SaaS, 13/10/2026).

Demande de Camille : « sur HetrixTools tu devais utiliser l'API et faire le nécessaire, créer
toutes les routines et les check-up de bonne santé d'un compte ». Toutes les heures (worker),
pour chaque client actif, et à la demande depuis l'interface :

  1. Domaine d'envoi toujours VÉRIFIÉ chez le fournisseur (Resend peut le repasser en échec).
  2. DNS toujours en place : DKIM, Return-Path (MX + SPF), DMARC (audit dns-audit, sans relance).
  3. Surveillance HetrixTools présente (créée par l'API si elle manque — routine, pas de clic).
  4. Listes noires : domaines d'envoi et organisationnels propres.
  5. Disponibilité : page de désinscription du client et webhook du fournisseur « up ».
  6. Rebonds définitifs < 2 % (seuil du skill ; Resend suspend vers 4 %) sur 7 jours.
  7. Plaintes < 0,1 % (Resend : 0,08 %) sur 7 jours.
  8. Webhook vivant : si des mails sont partis ces 48 h, des événements sont revenus.
  9. Warm-up respecté : aucune adresse au-delà de son plafond du jour.

Verdict : `ok` / `attention` / `critique`. Rangé dans `mass_mailing.sante_comptes` (historique),
lisible par le superadmin (mise en service, page Clients) et par le client (son espace).
Aucune action destructive : le bilan constate et, pour la surveillance, complète.
"""
from __future__ import annotations

import json
import time

from . import clients, desinscription, hetrix, onboarding, pg

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sante_comptes (
    id         BIGSERIAL PRIMARY KEY,
    slug       TEXT        NOT NULL,
    le         TIMESTAMPTZ NOT NULL DEFAULT now(),
    verdict    TEXT        NOT NULL CHECK (verdict IN ('ok','attention','critique')),
    controles  JSONB       NOT NULL
);
CREATE INDEX IF NOT EXISTS sante_comptes_slug_le ON sante_comptes (slug, le DESC);
"""

SEUIL_HARD, SEUIL_PLAINTES = 0.02, 0.001


def assurer_schema() -> None:
    with pg.espace(pg.SCHEMA):
        pg.ecrire(SCHEMA_SQL)


def _c(cle, titre, etat, detail=""):
    return {"cle": cle, "titre": titre, "etat": etat, "detail": detail}   # etat : ok | attention | critique | na


def bilan(slug: str, completer_surveillance: bool = True) -> dict:
    fiche = clients.par_slug(slug)
    if not fiche:
        raise ValueError("client inconnu")
    out: list[dict] = []
    with pg.espace(fiche["schema_pg"]):
        doms = onboarding.lister()
        url_desinscr = desinscription.url(0)
        # 1-2. Domaine et DNS
        if not doms:
            out.append(_c("domaine", "Domaine d'envoi", "critique", "aucun domaine connecté"))
        for d in doms:
            try:
                a = onboarding.auditer(str(d["id"]), demander_verification=False)
                out.append(_c(f"domaine:{d['domaine']}", f"{d['domaine']} vérifié chez {fiche['fournisseur'].capitalize()}",
                              "ok" if a["statut_fournisseur"] == "verified" else "critique", a["statut_fournisseur"] or ""))
                out.append(_c(f"dns:{d['domaine']}", f"DNS de {d['domaine']} (DKIM, Return-Path, DMARC)",
                              "ok" if a["dns_ok"] else "critique",
                              ", ".join(e.get("title", e.get("key", "")) for e in a["erreurs"])[:300]))
                su = a.get("suivi") or {}
                out.append(_c(f"suivi:{d['domaine']}", f"Suivi des ouvertures de {d['domaine']}",
                              "ok" if su.get("actif") else "attention",
                              "" if su.get("actif") else
                              ("réglage désactivé chez le fournisseur" if not su.get("demande") else
                               f"CNAME {su.get('sous_domaine') or 'links'}.{d['domaine']} à publier ou en vérification")))
            except Exception as e:  # noqa: BLE001
                out.append(_c(f"domaine:{d['domaine']}", f"{d['domaine']}", "attention", f"contrôle impossible : {str(e)[:120]}"))
        # 6-7. Rebonds et plaintes (7 jours)
        r = pg.ligne("""SELECT count(*) FILTER (WHERE submitted_at > now() - interval '7 days') AS envoyes,
                               count(*) FILTER (WHERE bounced_at > now() - interval '7 days'
                                                 AND (bounce_type ILIKE 'permanent%%' OR bounce_type ILIKE '%%hard%%'
                                                      OR bounce_type ILIKE 'email.suppressed%%')) AS hard,
                               count(*) FILTER (WHERE complained_at > now() - interval '7 days') AS plaintes,
                               count(*) FILTER (WHERE submitted_at > now() - interval '48 hours') AS envoyes_48h
                          FROM recipients""") or {}
        envoyes = int(r.get("envoyes") or 0)
        if envoyes >= 50:
            th, tp = r["hard"] / envoyes, r["plaintes"] / envoyes
            out.append(_c("rebonds", "Rebonds définitifs (7 j) < 2 %", "ok" if th < SEUIL_HARD else ("critique" if th >= 0.04 else "attention"),
                          f"{th:.2%} sur {envoyes} envois"))
            out.append(_c("plaintes", "Plaintes (7 j) < 0,1 %", "ok" if tp < SEUIL_PLAINTES else ("critique" if tp >= 0.0008 * 2 else "attention"),
                          f"{tp:.3%} sur {envoyes} envois"))
        else:
            out.append(_c("rebonds", "Rebonds et plaintes (7 j)", "na", f"{envoyes} envoi(s) : pas encore assez pour un taux"))
        # 8. Webhook vivant
        if int(r.get("envoyes_48h") or 0) > 0:
            ev = pg.valeur("SELECT count(*) FROM webhook_events WHERE received_at > now() - interval '48 hours'") or 0
            out.append(_c("webhook", "Événements du fournisseur reçus (48 h)", "ok" if ev else "critique",
                          f"{ev} événement(s) pour {r['envoyes_48h']} envoi(s)"))
        # 9. Warm-up
        from . import clients as _cl
        depasse = []
        for e in pg.lignes("SELECT * FROM expediteurs WHERE actif"):
            cap = _cl.plafond_du_jour(e)
            n = pg.valeur("""SELECT count(*) FROM recipients WHERE lower(from_email) = lower(%(a)s)
                               AND submitted_at >= date_trunc('day', now() AT TIME ZONE 'Europe/Paris') AT TIME ZONE 'Europe/Paris'""",
                          {"a": e["adresse"]}) or 0
            if n > cap:
                depasse.append(f"{e['adresse']} {n}/{cap}")
        out.append(_c("warmup", "Montée en volume respectée", "critique" if depasse else "ok", ", ".join(depasse)))
    # 3-5. HetrixTools (hors espace : lecture du compte HetrixTools)
    noms_doms = [d["domaine"] for d in doms]
    if noms_doms:
        try:
            etat = hetrix.etat_surveillance_client(slug, noms_doms, fiche["fournisseur"])
            if not etat.get("complet") and completer_surveillance and etat.get("configure"):
                hetrix.assurer_surveillance_client(slug, noms_doms, url_desinscr, fiche["fournisseur"],
                                                   f"{desinscription.BASE_PUBLIQUE}/api/public/mm/{fiche['fournisseur']}/webhook")
                etat = hetrix.etat_surveillance_client(slug, noms_doms, fiche["fournisseur"])
            out.append(_c("surveillance", "Surveillance HetrixTools en place", "ok" if etat.get("complet") else "attention",
                          ("manque : " + ", ".join(etat.get("manque") or [])) if etat.get("manque") else ""))
            res = hetrix.resume_espace(slug, fiche["fournisseur"])
            listees = [m for m in res.get("blacklist") or [] if hetrix.etat_moniteur(m) == "listee"]
            out.append(_c("listes_noires", "Listes noires (domaines)", "critique" if listees else "ok",
                          ", ".join(f"{m['cible']} sur {', '.join(x['rbl'] for x in m['listes'])}" for m in listees)))
            bas = [m for m in res.get("uptime") or [] if m.get("etat") == "down"]
            out.append(_c("disponibilite", "Disponibilité (désinscription, webhook)", "critique" if bas else "ok",
                          ", ".join(m["nom"] for m in bas)))
        except Exception as e:  # noqa: BLE001
            out.append(_c("surveillance", "Surveillance HetrixTools", "attention", f"HetrixTools injoignable : {str(e)[:120]}"))
    etats = [x["etat"] for x in out]
    verdict = "critique" if "critique" in etats else ("attention" if "attention" in etats else "ok")
    assurer_schema()
    with pg.espace(pg.SCHEMA):
        pg.ecrire("INSERT INTO sante_comptes (slug, verdict, controles) VALUES (%(s)s, %(v)s, %(c)s::jsonb)",
                  {"s": slug, "v": verdict, "c": json.dumps(out)})
        pg.ecrire("DELETE FROM sante_comptes WHERE slug = %(s)s AND le < now() - interval '90 days'", {"s": slug})
    return {"client": slug, "verdict": verdict, "controles": out, "le": int(time.time())}


def dernier(slug: str) -> dict | None:
    assurer_schema()
    with pg.espace(pg.SCHEMA):
        return pg.ligne("SELECT slug, le, verdict, controles FROM sante_comptes WHERE slug = %(s)s ORDER BY le DESC LIMIT 1",
                        {"s": slug})


def tourner() -> list[dict]:
    """Toutes les heures (worker) : un bilan par client actif."""
    res = []
    for c in clients.lister():
        if c["statut"] != "actif":
            continue
        try:
            b = bilan(c["slug"])
            res.append({"client": c["slug"], "verdict": b["verdict"]})
        except Exception as e:  # noqa: BLE001 — un client en erreur n'empêche pas les autres
            res.append({"client": c["slug"], "erreur": str(e)[:150]})
    return res
