#!/usr/bin/env python3
"""mass_mailing/infra/onboarding.py — mettre en service le domaine d'envoi d'un client.

Le parcours suit le skill `email-domain-setup` (§ A et § 8), dans l'ordre, chaque étape étant
VÉRIFIÉE par la machine — rien n'avance sur simple déclaration :

  1. connecter   : domaine créé chez le fournisseur, région UE FIGÉE, plan DNS enregistré
  2. auditer     : lecture du DNS public (dns-audit) + vérification chez le fournisseur
  3. auto-tests  : webhook (adresses simulateurs Resend) et désinscription one-click (POST 2xx)
  4. confirmer   : Google Postmaster Tools et Yahoo Sender Hub (déclarés par une personne :
                   ne se vérifient pas par DNS)
  5. expéditeur  : adresse + plan de warm-up (300-500/j la 1re semaine, doublement hebdo)
  6. go-live     : les six conditions réunies → état `warmup` ; l'envoi applique le plafond.

Tout s'exécute dans le schéma du client COURANT (posé par le middleware ou `pg.espace`).
"""
from __future__ import annotations

import json
import subprocess
import time
from datetime import date
from pathlib import Path

import requests

from . import clients, desinscription, fournisseurs, pg

OUTILS = Path(__file__).resolve().parent.parent / "outils" / "dns"
REGIONS_UE = {"eu-west-1", "eu-west-3", "eu-central-1", "eu-north-1", "eu-south-1"}
SIMULATEURS = ("delivered@resend.dev", "bounced@resend.dev", "complained@resend.dev")


def _journal(domaine_id: str, etape: str, ok: bool, detail: str = "", donnees=None) -> None:
    pg.ecrire("""UPDATE domaines_envoi SET journal = journal || %(j)s::jsonb, updated_at = now()
                  WHERE id = %(i)s""",
              {"i": domaine_id, "j": json.dumps([{"le": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                                  "etape": etape, "ok": ok, "detail": detail[:500],
                                                  "donnees": donnees}], default=str)})


def lire(domaine_id: str) -> dict | None:
    return pg.ligne("SELECT * FROM domaines_envoi WHERE id = %(i)s", {"i": domaine_id})


def lister() -> list[dict]:
    return pg.lignes("SELECT * FROM domaines_envoi ORDER BY created_at")


# ── 1. Connecter ─────────────────────────────────────────────────────────────
def connecter(domaine: str, zone: str | None = None, region: str = "eu-west-1") -> dict:
    """Crée (ou reprend) le domaine chez le fournisseur du client et enregistre le plan DNS.
    La région est FIGÉE à la création chez Resend comme chez SES : on refuse hors UE."""
    domaine = domaine.strip().lower().rstrip(".")
    zone = (zone or ".".join(domaine.split(".")[-2:])).strip().lower()
    if region not in REGIONS_UE:
        raise ValueError(f"région {region} refusée : clientèle européenne → région UE")
    fourn = fournisseurs.nom()
    if fourn != "resend":
        raise ValueError(f"onboarding {fourn} pas encore branché")
    mod = fournisseurs.module()
    existant = next((d for d in mod.domaines(force=True) if d["domain"] == domaine), None)
    if existant:
        brut = mod.lire_domaine(existant["id"])
    else:
        brut = mod.creer_domaine(domaine, region=region, return_path="send")
    # Suivi des ouvertures : AVANT de lire le plan DNS, pour que l'enregistrement « Tracking »
    # (CNAME links.<domaine>) en fasse partie. Nos clics restent suivis par Mass Email.
    suivi = mod.regler_suivi(brut["id"], ouvertures=True, clics=False)
    brut = mod.lire_domaine(brut["id"])
    if brut.get("region") not in REGIONS_UE:
        raise ValueError(f"domaine déjà créé chez le fournisseur en région {brut.get('region')} : "
                         "à supprimer et recréer en UE avant tout DNS")
    plan = plan_dns(brut, zone)
    row = pg.ligne("""INSERT INTO domaines_envoi (domaine, zone, fournisseur, fournisseur_id, region, etat,
                                                 enregistrements, statut_fournisseur, c_region_ue)
                      VALUES (%(d)s, %(z)s, %(f)s, %(fi)s, %(r)s, 'dns_a_poser', %(e)s::jsonb, %(s)s, true)
                      ON CONFLICT (domaine) DO UPDATE SET fournisseur_id = EXCLUDED.fournisseur_id,
                             enregistrements = EXCLUDED.enregistrements, statut_fournisseur = EXCLUDED.statut_fournisseur,
                             updated_at = now()
                      RETURNING *""",
                  {"d": domaine, "z": zone, "f": fourn, "fi": brut["id"], "r": brut.get("region"),
                   "e": json.dumps(plan), "s": brut.get("status")})
    _journal(str(row["id"]), "connecter", True, f"{fourn} {brut.get('region')} — {len(plan)} enregistrements à poser")
    _journal(str(row["id"]), "suivi_ouvertures", bool(suivi.get("demande")),
             f"suivi des ouvertures {'demandé' if suivi.get('demande') else 'REFUSÉ par le fournisseur'}, "
             f"sous-domaine {suivi.get('sous_domaine') or '—'} (vérifié avec les DNS)")
    return row


def plan_dns(brut_fournisseur: dict, zone: str) -> list[dict]:
    """Enregistrements du fournisseur (valeurs exactes) + DMARC p=none avec rua, en noms
    relatifs à la zone. Le DMARC n'est proposé que s'il n'existe pas déjà (un seul par nom)."""
    plan = []
    for r in brut_fournisseur.get("records") or []:
        plan.append({"type": r["type"], "nom": r["name"], "valeur": r["value"], "priorite": r.get("priority"),
                     "role": r.get("record"), "requis": True})
    cfg = fournisseurs.client_courant()
    rua = (cfg or {}).get("reply_to") or f"dmarc@{zone}"
    plan.append({"type": "TXT", "nom": "_dmarc", "valeur": f"v=DMARC1; p=none; sp=none; rua=mailto:{rua}",
                 "priorite": None, "role": "DMARC", "requis": True,
                 "note": "Ne pas créer s'il existe déjà un DMARC sur la zone : le compléter."})
    return plan


# ── 2. Auditer (DNS public + fournisseur) ────────────────────────────────────
def auditer(domaine_id: str, demander_verification: bool = True) -> dict:
    d = lire(domaine_id)
    if not d:
        raise ValueError("domaine inconnu")
    try:
        sortie = subprocess.run(["node", str(OUTILS / "dns-audit.mjs"), d["domaine"], "--provider", d["fournisseur"],
                                 "--return-path", f"send.{d['domaine']}", "--json"],
                                capture_output=True, text=True, timeout=90)
        audit = json.loads(sortie.stdout or "{}")
    except Exception as e:  # noqa: BLE001
        audit = {"status": "ERROR", "findings": [{"key": "audit:erreur", "severity": "error", "title": str(e)[:200]}]}
    erreurs = [f for f in audit.get("findings", []) if f.get("severity") == "error"]
    # DMARC absent est une erreur pour l'audit, et une condition du go-live : on la garde.
    dns_ok = audit.get("status") not in ("FAILED", "ERROR") and not erreurs
    mod = fournisseurs.module()
    statut = d["statut_fournisseur"]
    # Ne JAMAIS relancer la vérification d'un domaine déjà vérifié : Resend repasse alors
    # le statut à `pending` le temps de revérifier (vécu le 13/10 : 20 min de « pending »
    # entretenues par nos propres relances).
    deja = mod.lire_domaine(d["fournisseur_id"]).get("status") if d["fournisseur_id"] else None
    if demander_verification and d["fournisseur_id"] and deja != "verified":
        mod.verifier_domaine(d["fournisseur_id"])
        time.sleep(2)
    if d["fournisseur_id"]:
        brut = mod.lire_domaine(d["fournisseur_id"])
        statut = brut.get("status")
        par_nom = {r["name"]: r.get("status") for r in brut.get("records") or []}
        suivi = mod.etat_suivi(brut)
        if not suivi["sous_domaine"] or not suivi["demande"]:
            # Domaine connecté avant le 14/10 (ou réglage perdu) : on le pose, son CNAME s'ajoute au plan.
            suivi = {**mod.etat_suivi(brut), **mod.regler_suivi(d["fournisseur_id"])}
            brut = mod.lire_domaine(d["fournisseur_id"])
        # Le plan DNS affiché suit le fournisseur : un enregistrement apparu depuis (ex. Tracking) s'y ajoute.
        connus = {(x["type"], x["nom"]) for x in d["enregistrements"] or []}
        nouveaux = [{"type": r["type"], "nom": r["name"], "valeur": r["value"], "priorite": r.get("priority"),
                     "role": r.get("record"), "requis": True}
                    for r in brut.get("records") or [] if (r["type"], r["name"]) not in connus]
        if nouveaux:
            pg.ecrire("UPDATE domaines_envoi SET enregistrements = enregistrements || %(n)s::jsonb WHERE id = %(i)s",
                      {"n": json.dumps(nouveaux), "i": domaine_id})
    else:
        par_nom, suivi = {}, {"actif": False}
    verifie = statut == "verified"
    etat = "verifie" if (verifie and dns_ok) else ("dns_publie" if dns_ok else "dns_a_poser")
    if d["etat"] in ("pret", "warmup", "en_service") and verifie and dns_ok:
        etat = d["etat"]
    pg.ecrire("""UPDATE domaines_envoi SET audit = %(a)s::jsonb, c_dns_ok = %(ok)s, statut_fournisseur = %(s)s,
                        etat = %(e)s, verifie_at = CASE WHEN %(v)s THEN COALESCE(verifie_at, now()) END,
                        c_suivi_ok = %(su)s, updated_at = now() WHERE id = %(i)s""",
              {"a": json.dumps(audit), "ok": dns_ok and verifie, "s": statut, "e": etat, "v": verifie,
               "su": bool(suivi.get("actif")), "i": domaine_id})
    if dns_ok and verifie and not d["c_dns_ok"]:
        # Routine (Camille, 13/10) : dès qu'un domaine passe vérifié, sa surveillance HetrixTools
        # est créée par l'API — pas d'étape manuelle. Le bilan horaire la complète si besoin.
        try:
            from . import hetrix
            fiche = fournisseurs.client_courant()
            if fiche:
                hetrix.assurer_surveillance_client(
                    fiche["slug"], [x["domaine"] for x in lister()], desinscription.url(0), fiche["fournisseur"],
                    f"{desinscription.BASE_PUBLIQUE}/api/public/mm/{fiche['fournisseur']}/webhook")
        except Exception as e:  # noqa: BLE001 — la surveillance ne bloque jamais la vérification
            print(f"[onboarding] surveillance HetrixTools non créée : {e}", flush=True)
    _journal(domaine_id, "auditer", dns_ok and verifie,
             f"DNS {'OK' if dns_ok else f'{len(erreurs)} erreur(s)'} · {d['fournisseur']} : {statut}",
             {"erreurs": [f["key"] for f in erreurs], "enregistrements": par_nom})
    return {"etat": etat, "dns_ok": dns_ok, "statut_fournisseur": statut, "erreurs": erreurs,
            "enregistrements": par_nom, "suivi": suivi}


# ── 3. Auto-tests ────────────────────────────────────────────────────────────
def autotest_webhook(domaine_id: str, attente_s: int = 45) -> dict:
    """Envoie aux simulateurs Resend (livré, rebond, plainte) DEPUIS le domaine, puis attend
    que les trois événements soient revenus signés dans l'espace du client."""
    d = lire(domaine_id)
    if not d or d["statut_fournisseur"] != "verified":
        return {"ok": False, "raison": "domaine pas encore vérifié chez le fournisseur"}
    mod = fournisseurs.module()
    tenant = pg.schema_courant()[4:]
    ids = {}
    for adr in SIMULATEURS:
        r = mod.envoyer_un(destinataire=adr, subject="Auto-test webhook Mass Email", html_str="<p>Auto-test</p>",
                           texte="Auto-test", campagne="mm-autotest", tags=["autotest"],
                           expediteur={"from_name": "Auto-test", "from_email": f"autotest@{d['domaine']}",
                                       "tenant": tenant, "campaign_type": "transac",
                                       "idempotence": f"autotest:{adr}:{int(time.time())}"})
        ids[adr] = r.get("transaction_id") if r.get("ok") else f"ÉCHEC {r.get('erreur')}"
    attendus = {"email.delivered", "email.bounced", "email.complained"}
    vus: set = set()
    fin = time.time() + attente_s
    while time.time() < fin and not attendus <= vus:
        time.sleep(5)
        vus = {r["event_type"] for r in pg.lignes(
            """SELECT DISTINCT event_type FROM webhook_events WHERE provider = 'resend'
                AND raw_payload->'data'->>'email_id' = ANY(%(i)s)""",
            {"i": [v for v in ids.values() if v and not str(v).startswith("ÉCHEC")]})}
    ok = attendus <= vus
    pg.ecrire("UPDATE domaines_envoi SET c_webhooks_ok = %(o)s, updated_at = now() WHERE id = %(i)s",
              {"o": ok, "i": domaine_id})
    # Les simulateurs ont produit un rebond et une plainte : on les retire de la liste de
    # suppression du client, ce ne sont pas de vraies personnes.
    pg.ecrire("DELETE FROM suppressions WHERE email_normalized LIKE '%%@resend.dev'")
    _journal(domaine_id, "autotest_webhook", ok, f"reçus : {sorted(vus)}", ids)
    return {"ok": ok, "recus": sorted(vus), "envois": ids}


def autotest_desinscription(domaine_id: str) -> dict:
    """POST one-click (RFC 8058) sur un lien de test : doit répondre 2xx, sans redirection."""
    url = desinscription.url(0)
    try:
        r = requests.post(url, data={"List-Unsubscribe": "One-Click"}, allow_redirects=False, timeout=20)
        ok = 200 <= r.status_code < 300
        detail = f"HTTP {r.status_code}"
    except requests.RequestException as e:
        ok, detail = False, str(e)[:200]
    pg.ecrire("UPDATE domaines_envoi SET c_desinscription_ok = %(o)s, updated_at = now() WHERE id = %(i)s",
              {"o": ok, "i": domaine_id})
    _journal(domaine_id, "autotest_desinscription", ok, detail)
    return {"ok": ok, "detail": detail, "url": url}


# ── 4. Confirmations humaines ────────────────────────────────────────────────
def confirmer(domaine_id: str, quoi: str, par: str) -> dict:
    col = {"postmaster": "c_postmaster_ok", "senderhub": "c_senderhub_ok"}.get(quoi)
    if not col:
        raise ValueError("postmaster ou senderhub")
    pg.ecrire(f"UPDATE domaines_envoi SET {col} = true, updated_at = now() WHERE id = %(i)s", {"i": domaine_id})
    _journal(domaine_id, f"confirmer_{quoi}", True, f"confirmé par {par}")
    return {"ok": True}


# ── 5. Expéditeur et warm-up ─────────────────────────────────────────────────
def ajouter_expediteur(domaine_id: str, local: str, nom_affiche: str, reply_to: str | None,
                       cible_jour: int, debut: date | None = None, plafond_fournisseur: int | None = None) -> dict:
    d = lire(domaine_id)
    if not d:
        raise ValueError("domaine inconnu")
    adresse = f"{local.strip().lower()}@{d['domaine']}"
    plan = clients.plan_warmup(cible_jour, debut or date.today())
    row = pg.ligne("""INSERT INTO expediteurs (adresse, nom_affiche, reply_to, domaine_id, warmup_debut, warmup_plan,
                                              plafond_fournisseur)
                      VALUES (%(a)s, %(n)s, %(r)s, %(d)s, %(w)s, %(p)s::jsonb, %(pf)s)
                      ON CONFLICT (adresse) DO UPDATE SET nom_affiche = EXCLUDED.nom_affiche, reply_to = EXCLUDED.reply_to,
                             warmup_debut = EXCLUDED.warmup_debut, warmup_plan = EXCLUDED.warmup_plan,
                             plafond_fournisseur = EXCLUDED.plafond_fournisseur
                      RETURNING *""",
                   {"a": adresse, "n": nom_affiche, "r": reply_to, "d": domaine_id, "w": plan["debut"],
                    "p": json.dumps(plan), "pf": plafond_fournisseur})
    # Profil expéditeur par défaut de l'espace : ce que l'étape « Message » proposera.
    if not pg.valeur("SELECT count(*) FROM sender_profiles WHERE is_default"):
        fiche = fournisseurs.client_courant() or {}
        pg.ecrire("""INSERT INTO sender_profiles (name, from_name, from_email, reply_to, sending_domain,
                                                  is_default, raison_sociale, adresse_postale)
                     VALUES (%(n)s, %(fn)s, %(fe)s, %(r)s, %(d)s, true, %(rs)s, %(ap)s)""",
                  {"n": nom_affiche, "fn": nom_affiche, "fe": adresse, "r": reply_to, "d": d["domaine"],
                   "rs": fiche.get("raison_sociale"), "ap": fiche.get("adresse_postale")})
    _journal(domaine_id, "expediteur", True, f"{adresse} — warm-up {plan['semaines'][0]['plafond_jour']}/j "
                                             f"→ {cible_jour}/j en {len(plan['semaines'])} semaines")
    return {**row, "plafond_aujourdhui": clients.plafond_du_jour(row)}


# ── 6. Go-live ───────────────────────────────────────────────────────────────
CONDITIONS = [
    ("c_region_ue", "Domaine créé en région UE (figée)"),
    ("c_dns_ok", "DNS publié et domaine vérifié chez le fournisseur (DKIM, Return-Path, DMARC p=none + rua)"),
    ("c_webhooks_ok", "Webhooks rebonds/plaintes signés et reçus (auto-test simulateurs)"),
    ("c_desinscription_ok", "Désinscription one-click (RFC 8058) : POST 2xx sans redirection"),
    ("c_postmaster_ok", "Google Postmaster Tools inscrit (confirmé par une personne)"),
    ("c_senderhub_ok", "Yahoo Sender Hub inscrit (confirmé par une personne)"),
    ("c_suivi_ok", "Suivi des ouvertures actif (sous-domaine de suivi links.… vérifié chez le fournisseur)"),
]


def bilan(domaine_id: str) -> dict:
    d = lire(domaine_id)
    if not d:
        raise ValueError("domaine inconnu")
    conds = [{"cle": k, "libelle": l, "ok": bool(d[k])} for k, l in CONDITIONS]
    exps = pg.lignes("SELECT * FROM expediteurs WHERE domaine_id = %(d)s AND actif", {"d": domaine_id})
    warmup = bool(exps)
    pret = all(c["ok"] for c in conds) and warmup
    if pret and d["etat"] in ("verifie", "pret"):
        pg.ecrire("UPDATE domaines_envoi SET etat = 'warmup', updated_at = now() WHERE id = %(i)s", {"i": domaine_id})
        _journal(domaine_id, "go_live", True, "toutes les conditions réunies : envoi ouvert, plafonné par le warm-up")
        d = lire(domaine_id)
    return {"domaine": d["domaine"], "etat": d["etat"], "conditions": conds,
            "warmup": [{"adresse": e["adresse"], "plafond_aujourdhui": clients.plafond_du_jour(e),
                        "plan": e["warmup_plan"]} for e in exps],
            "go": pret, "enregistrements": d["enregistrements"], "journal": d["journal"][-15:]}
