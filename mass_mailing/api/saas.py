#!/usr/bin/env python3
"""mass_mailing/api/saas.py — routes de la plateforme multi-clients (SaaS, 13/10/2026).

- `/api/mass-mailing/espace/*` : l'espace du client COURANT (schéma posé par le middleware) :
  domaines d'envoi, parcours de mise en service, expéditeurs et warm-up.
- `/api/mm-admin/*` : superadmin seulement (le middleware refuse déjà les comptes clients) :
  créer un client, inviter ses utilisateurs, suspendre.
"""
from __future__ import annotations

import asyncio
from datetime import date

from fastapi import APIRouter, HTTPException, Request

from infra import auth, clients, desinscription, fournisseurs, onboarding, pg

router = APIRouter()


def _membre(request: Request) -> dict:
    s = getattr(request.state, "session", None) or {}
    if s.get("role") not in ("superadmin", "client"):
        raise HTTPException(status_code=403, detail="accès refusé")
    return s


def _superadmin(request: Request) -> dict:
    s = getattr(request.state, "session", None) or {}
    if s.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="réservé au superadmin")
    return s


def _espace_client(request: Request) -> dict:
    s = _membre(request)
    if pg.schema_courant() == pg.SCHEMA:
        raise HTTPException(status_code=409, detail="choisissez un client (espace interne : pas de domaine client)")
    return s


# ── Espace client ────────────────────────────────────────────────────────────
@router.get("/api/mass-mailing/espace")
def espace(request: Request):
    _membre(request)
    fiche = fournisseurs.client_courant()
    if not fiche:
        return {"client": None, "fournisseur": "sweego", "domaines": []}
    doms = []
    for d in onboarding.lister():
        b = onboarding.bilan(str(d["id"]))
        doms.append({"id": str(d["id"]), **b})
    return {"client": {k: fiche[k] for k in ("slug", "nom", "statut", "fournisseur", "reply_to")},
            "fournisseur": fiche["fournisseur"], "domaines": doms}


@router.post("/api/mass-mailing/espace/domaines")
async def connecter_domaine(request: Request):
    _espace_client(request)
    b = await request.json()
    try:
        d = await asyncio.to_thread(onboarding.connecter, b.get("domaine") or "", b.get("zone"),
                                    b.get("region") or "eu-west-1")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return onboarding.bilan(str(d["id"]))


@router.post("/api/mass-mailing/espace/domaines/{domaine_id}/auditer")
async def auditer(domaine_id: str, request: Request):
    _espace_client(request)
    r = await asyncio.to_thread(onboarding.auditer, domaine_id)
    return {**r, "bilan": onboarding.bilan(domaine_id)}


@router.post("/api/mass-mailing/espace/domaines/{domaine_id}/autotests")
async def autotests(domaine_id: str, request: Request):
    _espace_client(request)
    w = await asyncio.to_thread(onboarding.autotest_webhook, domaine_id)
    u = await asyncio.to_thread(onboarding.autotest_desinscription, domaine_id)
    return {"webhook": w, "desinscription": u, "bilan": onboarding.bilan(domaine_id)}


@router.post("/api/mass-mailing/espace/domaines/{domaine_id}/confirmer")
async def confirmer(domaine_id: str, request: Request):
    s = _espace_client(request)
    b = await request.json()
    try:
        onboarding.confirmer(domaine_id, b.get("quoi") or "", s.get("username") or "?")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return onboarding.bilan(domaine_id)


@router.post("/api/mass-mailing/espace/domaines/{domaine_id}/expediteurs")
async def expediteur(domaine_id: str, request: Request):
    _espace_client(request)
    b = await request.json()
    try:
        debut = date.fromisoformat(b["debut"]) if b.get("debut") else None
        onboarding.ajouter_expediteur(domaine_id, b.get("local") or "", b.get("nom") or "",
                                      b.get("reply_to"), int(b.get("cible_jour") or 2000), debut,
                                      int(b["plafond_fournisseur"]) if b.get("plafond_fournisseur") else None)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return onboarding.bilan(domaine_id)


@router.get("/api/mass-mailing/espace/domaines/{domaine_id}")
def bilan(domaine_id: str, request: Request):
    _espace_client(request)
    try:
        return onboarding.bilan(domaine_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ── Superadmin : agent d'apprentissage du message ───────────────────────────
@router.get("/api/mm-admin/apprentissage")
def apprentissage_etat(request: Request):
    _superadmin(request)
    from jobs import apprentissage
    apprentissage.assurer_schema()
    with pg.espace(pg.SCHEMA):
        return {
            "fin": apprentissage.FIN.isoformat(), "heure_paris": apprentissage.HEURE_PARIS,
            "seuils": {"campagnes": apprentissage.MIN_CAMPAGNES, "livres_min": apprentissage.MIN_LIVRES,
                       "pas_max": apprentissage.PAS_MAX},
            "observations": pg.valeur("SELECT count(*) FROM apprentissage_observations"),
            "exploitables": pg.valeur("SELECT count(*) FROM apprentissage_observations WHERE (resultats->>'livres')::int >= %(m)s",
                                      {"m": apprentissage.MIN_LIVRES}),
            "regles": pg.lignes("""SELECT cle, niveau, libelle, poids_defaut, poids, n_avec, n_sans, negatif_avec, negatif_sans,
                                          ouverture_avec, ouverture_sans, maj_le FROM apprentissage_regles
                                    ORDER BY abs(poids - poids_defaut) DESC, n_avec DESC LIMIT 50"""),
            "mots": pg.lignes("""SELECT expression, n_campagnes, negatif, reference FROM apprentissage_mots
                                  WHERE statut = 'a_surveiller' ORDER BY negatif DESC LIMIT 50"""),
            "journal": pg.lignes("SELECT le, resume FROM apprentissage_journal ORDER BY le DESC LIMIT 30"),
        }


# ── Superadmin : mise en service d'un client (13/10/2026) ───────────────────
# Demande de Camille : « à chaque nouveau compte il faut le faire […] crée un onboarding
# pour le superadmin ». Chaque étape est lue dans l'état réel (base, fournisseur,
# HetrixTools), jamais cochée à la main, sauf les deux inscriptions humaines.
def _etapes_client(c: dict) -> list[dict]:
    from infra import hetrix
    with pg.espace(c["schema_pg"]):
        doms = pg.lignes("SELECT * FROM domaines_envoi ORDER BY created_at")
        exps = pg.valeur("SELECT count(*) FROM expediteurs WHERE actif") or 0
        prof = pg.ligne("SELECT raison_sociale, adresse_postale FROM sender_profiles WHERE is_default")
        url_desinscr = desinscription.url(0)
    with pg.espace(pg.SCHEMA):
        membres = pg.lignes("SELECT actif FROM utilisateurs WHERE client_id = %(c)s", {"c": c["id"]})
    d = doms[0] if doms else None
    try:
        surv = hetrix.etat_surveillance_client(c["slug"], [x["domaine"] for x in doms], c["fournisseur"]) if doms else {"complet": False}
    except Exception as e:  # noqa: BLE001
        surv = {"complet": False, "erreur": str(e)[:120]}
    adresse = (prof or {}).get("adresse_postale") or c.get("adresse_postale")
    E = lambda cle, titre, ok, detail="", action=None: {"cle": cle, "titre": titre, "ok": bool(ok), "detail": detail, "action": action}  # noqa: E731
    return [
        E("espace", "Espace isolé créé", True, c["schema_pg"]),
        E("domaine", f"Domaine d'envoi connecté chez {c['fournisseur'].capitalize()} (région UE)", d and d["c_region_ue"],
          d["domaine"] if d else "aucun domaine", "ouvrir_domaine"),
        E("dns", "DNS publié et domaine vérifié", d and d["c_dns_ok"], (d or {}).get("statut_fournisseur") or "", "ouvrir_domaine"),
        E("suivi", "Suivi des ouvertures actif (sous-domaine links.… vérifié)", d and d.get("c_suivi_ok"),
          "" if d and d.get("c_suivi_ok") else "CNAME links.<domaine> à publier, puis « Vérifier »", "ouvrir_domaine"),
        E("tests", "Webhook et désinscription en un clic testés", d and d["c_webhooks_ok"] and d["c_desinscription_ok"], "", "ouvrir_domaine"),
        E("surveillance", "Surveillance HetrixTools (listes noires + disponibilité)", surv.get("complet"),
          ("manque : " + ", ".join(surv.get("manque") or [])) if surv.get("manque") else surv.get("erreur", ""), "surveillance"),
        E("inscriptions", "Google Postmaster + Yahoo Sender Hub", d and d["c_postmaster_ok"] and d["c_senderhub_ok"], "", "ouvrir_domaine"),
        E("expediteur", "Adresse expéditrice + plan de montée en volume", exps > 0, f"{exps} adresse(s)", "ouvrir_domaine"),
        E("pied", "Raison sociale et adresse postale (pied de mail)", adresse, adresse or "absente"),
        E("utilisateur", "Utilisateur client invité et activé", any(m["actif"] for m in membres),
          f"{len(membres)} compte(s), {sum(1 for m in membres if m['actif'])} actif(s)", "inviter"),
    ]


@router.get("/api/mass-mailing/espace/sante")
def sante_espace(request: Request):
    _espace_client(request)
    from infra import sante_compte
    return sante_compte.dernier(fournisseurs.client_courant()["slug"]) or {"verdict": None, "controles": []}


@router.post("/api/mass-mailing/espace/sante")
async def sante_espace_maintenant(request: Request):
    _espace_client(request)
    from infra import sante_compte
    return await asyncio.to_thread(sante_compte.bilan, fournisseurs.client_courant()["slug"])


@router.get("/api/mass-mailing/espace/resume")
def resume_espace(request: Request):
    """La phrase de l'accueil (Camille, 13/10) : santé, capacité d'envoi du jour et de la semaine,
    prochain palier de montée en volume, problème principal. Chiffres calculés, jamais inventés."""
    prenom = (_membre(request).get("prenom") or "").strip()
    from datetime import date, timedelta
    from infra import sante_compte
    fiche = fournisseurs.client_courant()
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo
    aujourd_hui = _dt.now(ZoneInfo("Europe/Paris")).date()
    envoyes_jour = pg.valeur("""SELECT count(*) FROM recipients WHERE submitted_at >=
                                 date_trunc('day', now() AT TIME ZONE 'Europe/Paris') AT TIME ZONE 'Europe/Paris'""") or 0
    envoyes_semaine = pg.valeur("SELECT count(*) FROM recipients WHERE submitted_at > now() - interval '7 days'") or 0
    # Performances sur 30 jours (13/10) : taux rapportés aux mails DÉLIVRÉS.
    perf = pg.ligne("""SELECT count(*) FILTER (WHERE delivered_at IS NOT NULL) AS livres,
                              count(*) FILTER (WHERE opened_at IS NOT NULL) AS ouverts,
                              count(*) FILTER (WHERE clicked_at IS NOT NULL) AS cliques
                         FROM recipients WHERE submitted_at > now() - interval '30 days'""") or {}
    perf = {k: int(v or 0) for k, v in perf.items()}
    if not fiche:
        # Espace interne (Sweego) : pas de warm-up par adresse ; débit réglé dans settings.
        reg = pg.ligne("SELECT max_rate_per_minute FROM settings") or {}
        return {"espace": "interne", "prenom": prenom, "fournisseur": "sweego", "envoyes_jour": int(envoyes_jour), "perf": perf,
                "envoyes_semaine": int(envoyes_semaine), "debit_minute": reg.get("max_rate_per_minute"),
                "sante": None, "expediteurs": []}
    exps = []
    for e in pg.lignes("SELECT * FROM expediteurs WHERE actif ORDER BY created_at"):
        plan = e["warmup_plan"] or {}
        semaines = plan.get("semaines") or []
        jour = clients.plafond_du_jour(e, aujourd_hui)
        semaine = sum(clients.plafond_du_jour(e, aujourd_hui + timedelta(days=i)) for i in range(7))
        courante = next((s for s in semaines if date.fromisoformat(s["du"]) <= aujourd_hui <= date.fromisoformat(s["au"])), None)
        # Prochain palier = prochain jour où le plafond monte (rampe quotidienne de la 1re semaine comprise).
        prochaine = next(({"du": (aujourd_hui + timedelta(days=i)).isoformat(), "plafond_jour": clients.plafond_du_jour(e, aujourd_hui + timedelta(days=i))}
                          for i in range(1, 60) if clients.plafond_du_jour(e, aujourd_hui + timedelta(days=i)) > jour), None)
        exps.append({"adresse": e["adresse"], "jour": jour, "semaine": semaine,
                     "semaine_warmup": courante["semaine"] if courante else None, "nb_semaines": len(semaines),
                     "cible_jour": plan.get("cible_jour"), "plafond_fournisseur": e.get("plafond_fournisseur"),
                     "prochain_palier": {"le": prochaine["du"], "jour": prochaine["plafond_jour"]} if prochaine else None,
                     "debut": plan.get("debut")})
    b = sante_compte.dernier(fiche["slug"]) or {}
    controles = b.get("controles") or []
    problemes = [c for c in controles if c["etat"] in ("critique", "attention")]
    capacite_jour = sum(x["jour"] for x in exps)
    return {"espace": fiche["slug"], "prenom": prenom, "nom": fiche["nom"], "fournisseur": fiche["fournisseur"],
            "sante": b.get("verdict"), "sante_le": b.get("le"), "problemes": problemes,
            "controles_ok": sum(1 for c in controles if c["etat"] == "ok"), "controles_total": len(controles),
            "capacite_jour": capacite_jour, "capacite_semaine": sum(x["semaine"] for x in exps),
            "restant_jour": max(0, capacite_jour - int(envoyes_jour)),
            "envoyes_jour": int(envoyes_jour), "envoyes_semaine": int(envoyes_semaine), "expediteurs": exps, "perf": perf,
            "domaines": [{"domaine": d["domaine"], "etat": d["etat"]} for d in onboarding.lister()]}


@router.get("/api/mm-admin/clients/{slug}/mise-en-service")
def mise_en_service(slug: str, request: Request):
    _superadmin(request)
    c = clients.par_slug(slug)
    if not c:
        raise HTTPException(status_code=404, detail="client inconnu")
    etapes = _etapes_client(c)
    from infra import sante_compte
    return {"client": slug, "etapes": etapes, "faites": sum(e["ok"] for e in etapes), "total": len(etapes),
            "sante": sante_compte.dernier(slug)}


@router.post("/api/mm-admin/clients/{slug}/surveillance")
async def surveiller_client(slug: str, request: Request):
    _superadmin(request)
    from infra import hetrix
    c = clients.par_slug(slug)
    if not c:
        raise HTTPException(status_code=404, detail="client inconnu")
    with pg.espace(c["schema_pg"]):
        doms = [r["domaine"] for r in pg.lignes("SELECT domaine FROM domaines_envoi ORDER BY created_at")]
        url = desinscription.url(0)
    if not doms:
        raise HTTPException(status_code=409, detail="connectez d'abord un domaine d'envoi")
    try:
        r = await asyncio.to_thread(hetrix.assurer_surveillance_client, slug, doms, url, c["fournisseur"],
                                    f"{desinscription.BASE_PUBLIQUE}/api/public/mm/{c['fournisseur']}/webhook")
    except hetrix.ErreurHetrix as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {**r, "etapes": _etapes_client(c)}


# ── Superadmin : clients ─────────────────────────────────────────────────────
@router.get("/api/mm-admin/clients")
def lister_clients(request: Request):
    _superadmin(request)
    out = []
    for c in clients.lister():
        with pg.espace(c["schema_pg"]):
            stats = pg.ligne("""SELECT (SELECT count(*) FROM campaigns) AS campagnes,
                                       (SELECT count(*) FROM recipients WHERE submitted_at IS NOT NULL) AS envoyes,
                                       (SELECT count(*) FROM domaines_envoi) AS domaines,
                                       (SELECT count(*) FROM domaines_envoi WHERE etat IN ('warmup','en_service')) AS domaines_actifs""")
        with pg.espace(pg.SCHEMA):
            membres = pg.lignes("""SELECT id, identifiant, email, prenom, actif, derniere_connexion_at FROM utilisateurs
                                    WHERE client_id = %(c)s ORDER BY identifiant""", {"c": c["id"]})
        out.append({**{k: c[k] for k in ("slug", "nom", "statut", "fournisseur", "reply_to", "created_at")},
                    **(stats or {}), "membres": membres})
    return {"clients": out}


@router.post("/api/mm-admin/clients")
async def creer_client(request: Request):
    _superadmin(request)
    b = await request.json()
    try:
        c = await asyncio.to_thread(clients.creer, (b.get("slug") or "").strip().lower(), (b.get("nom") or "").strip(),
                                    b.get("reply_to"), b.get("fournisseur") or "resend",
                                    b.get("raison_sociale"), b.get("adresse_postale"))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"ok": True, "client": {k: c.get(k) for k in ("slug", "nom", "schema_pg", "fournisseur")}}


@router.post("/api/mm-admin/clients/{slug}/invitation")
async def inviter(slug: str, request: Request):
    _superadmin(request)
    c = clients.par_slug(slug)
    if not c:
        raise HTTPException(status_code=404, detail="client inconnu")
    b = await request.json()
    ident = (b.get("identifiant") or "").strip().lower()
    if not ident:
        raise HTTPException(status_code=422, detail="identifiant requis")
    with pg.espace(pg.SCHEMA):
        autre = pg.ligne("SELECT role, client_id FROM utilisateurs WHERE identifiant = %(i)s", {"i": ident})
    if autre and (autre["role"] != "client" or autre["client_id"] != c["id"]):
        raise HTTPException(status_code=409, detail="cet identifiant appartient déjà à un autre compte")
    jeton = auth.creer_invitation(ident, b.get("email"), client_id=c["id"], prenom=b.get("prenom"))
    return {"ok": True, "lien": f"{desinscription.BASE_PUBLIQUE}/mass-email/connexion?activation={jeton}",
            "valable_heures": auth.DUREE_ACTIVATION_H}


@router.post("/api/mm-admin/clients/{slug}/utilisateurs/{uid}/transfert")
async def transferer(slug: str, uid: int, request: Request):
    """Change prénom/identifiant/email d'un utilisateur du client et renvoie un lien d'activation :
    l'ancien mot de passe et l'ancienne double authentification ne marchent plus."""
    _superadmin(request)
    c = clients.par_slug(slug)
    if not c:
        raise HTTPException(status_code=404, detail="client inconnu")
    b = await request.json()
    ident = (b.get("identifiant") or "").strip().lower()
    if not ident:
        raise HTTPException(status_code=422, detail="identifiant requis")
    with pg.espace(pg.SCHEMA):
        u = pg.ligne("SELECT id FROM utilisateurs WHERE id = %(u)s AND client_id = %(c)s AND role = 'client'",
                     {"u": uid, "c": c["id"]})
        autre = pg.ligne("SELECT id FROM utilisateurs WHERE identifiant = %(i)s AND id <> %(u)s", {"i": ident, "u": uid})
    if not u:
        raise HTTPException(status_code=404, detail="utilisateur inconnu pour ce client")
    if autre:
        raise HTTPException(status_code=409, detail="cet identifiant appartient déjà à un autre compte")
    jeton = auth.transferer_compte(uid, ident, b.get("email"), b.get("prenom"))
    return {"ok": True, "lien": f"{desinscription.BASE_PUBLIQUE}/mass-email/connexion?activation={jeton}",
            "valable_heures": auth.DUREE_ACTIVATION_H}


@router.patch("/api/mm-admin/clients/{slug}")
async def modifier_client(slug: str, request: Request):
    _superadmin(request)
    b = await request.json()
    champs = {k: b[k] for k in ("nom", "statut", "reply_to", "raison_sociale", "adresse_postale") if k in b}
    if not champs:
        raise HTTPException(status_code=422, detail="rien à modifier")
    if champs.get("statut") not in (None, "actif", "suspendu"):
        raise HTTPException(status_code=422, detail="statut : actif ou suspendu")
    sets = ", ".join(f"{k} = %({k})s" for k in champs)
    with pg.espace(pg.SCHEMA):
        n = pg.ecrire(f"UPDATE clients SET {sets} WHERE slug = %(slug)s", {**champs, "slug": slug})
    if not n:
        raise HTTPException(status_code=404, detail="client inconnu")
    return {"ok": True}
