"""mass_mailing/api/ab.py — routes de l'A/B test d'une campagne (Camille, 15/10/2026).

Accessibles au superadmin ET au compte client : c'est le client qui écrit ses deux versions,
choisit la taille des échantillons, la durée du test et le critère. Le schéma PostgreSQL posé
par le middleware enferme chaque compte dans son espace. Le moteur est dans jobs/ab_test.py.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.routes import _campagne, _superadmin
from infra import desinscription, harmonisation, stockage, sweego
from jobs import ab_test
from jobs.file import ErreurDefinitive

router = APIRouter(prefix="/api/mass-mailing", tags=["mass-mailing-ab"])


def _erreur(e: Exception) -> HTTPException:
    return HTTPException(status_code=409, detail=str(e))


@router.get("/campaigns/{campaign_id}/ab")
def lire(campaign_id: str, request: Request):
    _superadmin(request)
    c = _campagne(campaign_id)
    ab_test.appliquer_schema()
    return {**ab_test.etat(campaign_id), "campagne": {"id": str(c["id"]), "nom": c["internal_name"], "statut": c["status"]}}


@router.put("/campaigns/{campaign_id}/ab")
def regler(campaign_id: str, request: Request, corps: dict):
    acteur = _superadmin(request)
    _campagne(campaign_id)
    try:
        ab_test.regler(campaign_id, acteur, taille_a=corps.get("taille_a"), taille_b=corps.get("taille_b"),
                       duree_jours=corps.get("duree_jours"), critere=corps.get("critere"))
    except (ab_test.ErreurAB, ValueError, TypeError) as e:
        raise _erreur(e) from e
    return ab_test.etat(campaign_id)


@router.get("/campaigns/{campaign_id}/ab/version/{variante}")
def lire_version(campaign_id: str, variante: str, request: Request):
    acteur = _superadmin(request)
    _campagne(campaign_id)
    if variante not in ab_test.VARIANTES:
        raise HTTPException(status_code=404, detail="version A ou B")
    t = ab_test.creer_ou_lire(campaign_id, acteur)
    v = ab_test.version(t, variante)
    html = stockage.lire(v["html_key"]).decode("utf-8", "replace") if v["html_key"] else ""
    return {"variante": variante, "subject": v["subject"] or "", "preheader": v["preheader"] or "", "html": html}


@router.get("/campaigns/{campaign_id}/ab/apercu/{variante}")
def apercu(campaign_id: str, variante: str, request: Request):
    """Le HTML tel qu'il partira (en-tête harmonisé, pied de désinscription d'un BAT)."""
    _superadmin(request)
    c = _campagne(campaign_id)
    t = ab_test.lire(campaign_id)
    v = ab_test.version(t, variante) if t and variante in ab_test.VARIANTES else {}
    if not v.get("html_key"):
        return {"html": ""}
    html = harmonisation.harmoniser(sweego.nettoyer_html(stockage.lire(v["html_key"]).decode("utf-8", "replace")),
                                    preheader=v["preheader"] or "", url_miroir=desinscription.url_miroir(campaign_id),
                                    ligne_entete=c.get("entete_version_en_ligne") is not False)[0]
    return {"html": desinscription.pied_de_mail(html, 0, c.get("from_name") or "")}


@router.put("/campaigns/{campaign_id}/ab/version/{variante}")
def enregistrer_version(campaign_id: str, variante: str, request: Request, corps: dict):
    acteur = _superadmin(request)
    _campagne(campaign_id)
    try:
        ab_test.enregistrer_version(campaign_id, acteur, variante, subject=corps.get("subject") or "",
                                    preheader=corps.get("preheader") or "", html=corps.get("html") or "")
    except (ab_test.ErreurAB, stockage.StockageErreur) as e:
        raise _erreur(e) from e
    return ab_test.etat(campaign_id)


@router.get("/campaigns/{campaign_id}/ab/controles")
def controles(campaign_id: str, request: Request):
    _superadmin(request)
    _campagne(campaign_id)
    return {"controles": ab_test.controler(campaign_id)}


@router.post("/campaigns/{campaign_id}/ab/lancer")
def lancer(campaign_id: str, request: Request, corps: dict):
    acteur = _superadmin(request)
    _campagne(campaign_id)
    if corps.get("confirmation") is not True:
        raise HTTPException(status_code=422, detail="confirmation explicite requise")
    try:
        return {**ab_test.lancer(campaign_id, acteur), **ab_test.etat(campaign_id)}
    except (ab_test.ErreurAB, ErreurDefinitive) as e:
        raise _erreur(e) from e
