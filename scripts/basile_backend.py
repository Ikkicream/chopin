#!/usr/bin/env python3
"""basile_backend.py — Connecteur Basile (api.basile.cc) pour Genesis.

2e outil d'acquisition de contacts, à côté de Serper (`god_mode_agents.serper_places`).
Les deux alimentent le MÊME pool mutualisé `contacts.duckdb` (dédup par email) + la file
`scrappe_pending` (god_mode.duckdb) drainée par Mailnjoy. Différence : Serper scrape des
commerces Google par ville ; Basile interroge le registre légal + LinkedIn + GMB et ramène
des SOCIÉTÉS et des DIRIGEANTS NOMMÉS (prenom/nom/job_title), enrichissables via Emelia.

⚠️ STATUT : écrit d'après la doc du skill `skills/basile-b2b-search` pendant que app.basile.cc
était DOWN. La partie HTTP (count/find/export) n'a PAS été testée en live. Les blocs marqués
« FIELD MAP — à confirmer au retour du site » doivent être vérifiés contre une vraie réponse
`/people/find` (champs de `lead["data"]`). Voir docs/basile-api.md §Go-live.

Règles de volume (demande user, alignées sur les limites du plan API Basile) :
  - JAMAIS d'export > 20 000 d'un coup (limite plan ; au-delà → segmenter par dept/NAF).
  - Collecte par PASSES de 1 000 contacts (PASS_SIZE), avec throttle entre appels.
  - Toujours COMPTER (limit:1 → total) avant d'extraire (gratuit en quota).

Auth : env BASILE_KEY (clé brute, SANS 'Bearer'). Chargée depuis .env si présente.
"""
from __future__ import annotations

import json
import os
import sys
import time
import ssl
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

# --- chargement .env (même pattern que les autres agents) ---------------------
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k, _v.strip("'\""))

BASILE_BASE = os.environ.get("BASILE_BASE", "https://api.basile.cc")
BASILE_KEY = os.environ.get("BASILE_KEY", "")
DEFAULT_DELAY = float(os.environ.get("BASILE_DELAY", "1.5"))   # throttle anti-429

# Règles de volume
EXPORT_HARD_CAP = 20_000      # jamais au-delà sur un même segment (limite plan API)
PASS_SIZE = 1_000             # 1 passe = 1 000 contacts (pages /find de 100 → 10 pages)
PAGE_SIZE = 100               # max /find par page

# Flag de blocage live (même esprit que SERPER_BLOCKED_STATUS) : posé sur 402/429/403.
BASILE_BLOCKED_STATUS: int | None = None

# ── Mapping secteur Genesis → codes NAF (confirmés live 2026-06-17) ─────────────
# Format NAF strict avec point+lettre ("56.10A"). Géo via headquarters_city (MAJUSCULES).
SECTOR_NAF: dict[str, list[str]] = {
    "restaurant":       ["56.10A", "56.10C", "56.30Z"],
    "boulanger":        ["10.71C", "47.24Z"],
    "coiffeur":         ["96.02A", "96.02B"],
    "garagiste":        ["45.20A", "45.20B"],
    "immobilier":       ["68.31Z"],
    "artisan":          ["41.20A", "43.11Z", "43.12A", "43.13Z", "43.21A", "43.21B",
                         "43.22A", "43.22B", "43.31Z", "43.32A", "43.32B", "43.32C",
                         "43.33Z", "43.34Z", "43.39Z", "43.91A", "43.91B",
                         "43.99A", "43.99B"],
    "retail":           ["47.11A", "47.11B", "47.11C", "47.11D", "47.11E", "47.11F",
                         "47.19A", "47.19B", "47.21Z", "47.22Z", "47.23Z", "47.29Z"],
    "fleuriste":        ["47.76Z"],
    "plombier":         ["43.22A", "43.22B"],
    "electricien":      ["43.21A", "43.21B"],
    "menuisier":        ["43.32A", "43.32B", "43.32C"],
    "avocat":           ["69.10Z"],
    "comptable":        ["69.20Z"],
    "agence-marketing": ["73.11Z"],
    "agence-web":       ["62.01Z", "73.11Z"],
    "consultant":       ["70.22Z"],
}


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


_SSL = _ssl_context()


# ── HTTP ──────────────────────────────────────────────────────────────────────
def _req(path: str, body=None, method="POST", raw=False, with_headers=False,
         timeout=150, _tries=0):
    """Appel HTTP Basile. Auth header brut. Reprise sur 429 (Retry-After) et réseau.
    Pose BASILE_BLOCKED_STATUS sur 402/403/429 (quota/abo/limite) au lieu d'avaler."""
    global BASILE_BLOCKED_STATUS
    if not BASILE_KEY:
        raise RuntimeError("BASILE_KEY manquante (clé API brute, sans 'Bearer').")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASILE_BASE + path, data=data, method=method,
        headers={"Authorization": BASILE_KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
            payload = r.read()
            if with_headers:
                return payload, dict(r.headers)
            return payload if raw else json.loads(payload)
    except urllib.error.HTTPError as e:
        if e.code == 429 and _tries < 5:
            ra = e.headers.get("Retry-After")
            wait = int(ra) if (ra and str(ra).isdigit()) else 10
            print(f"  ⏳ 429 rate limit — pause {wait}s puis reprise…", file=sys.stderr)
            time.sleep(wait)
            return _req(path, body, method, raw, with_headers, timeout, _tries + 1)
        if e.code in (402, 403):
            # abonnement requis / plan API requis : blocage métier, pas une erreur passagère
            BASILE_BLOCKED_STATUS = e.code
            raise RuntimeError(f"BASILE_BLOCKED ({e.code}) sur {path}: "
                               f"{e.read().decode(errors='replace')[:200]}")
        raise RuntimeError(f"HTTP {e.code} sur {path}: {e.read().decode(errors='replace')[:300]}")
    except (urllib.error.URLError, TimeoutError) as e:
        if _tries < 3:
            print(f"  ⏳ réseau/timeout ({e}) — nouvelle tentative dans 5s…", file=sys.stderr)
            time.sleep(5)
            return _req(path, body, method, raw, with_headers, timeout, _tries + 1)
        raise RuntimeError(f"Échec réseau sur {path}: {e}")


def count(kind: str, filters: dict) -> int:
    """Total sans extraire (gratuit en quota). kind = 'people' | 'companies'."""
    return _req(f"/{kind}/find", {"filters": filters, "limit": 1}).get("total", 0)


def find(kind: str, filters: dict, limit: int = PAGE_SIZE, token: str | None = None) -> dict:
    body = {"filters": filters, "limit": min(int(limit), PAGE_SIZE)}
    if token:
        body["paginationToken"] = token
    return _req(f"/{kind}/find", body)


# ── Normalisation Basile → schéma `prospect` Genesis ────────────────────────────
def _first(d: dict, *keys, default=None):
    """Renvoie la 1re valeur non vide parmi plusieurs noms de champs possibles."""
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return default


def lead_to_prospect(lead: dict, *, sector: str | None = None,
                     dept_code: str | None = None, region_code: str | None = None,
                     search_query: str = "basile") -> dict | None:
    """Convertit un lead Basile (`/find`) en `prospect` Genesis (même schéma que Serper).

    FIELD MAP — CONFIRMÉ en live le 2026-06-17 (champs réels de lead["data"]) :
      SOCIÉTÉS (porteuses de l'email) : company_name, legal_name, siren, email (générique),
        phone (+33…), headquarters_city (MAJ), headquarters_postal_code, naf_code,
        naf_code_label, activity_domain, headcount_min/max, capital, legal_form, x_gmb{…}.
        → PAS de champ website à plat (parfois dans x_gmb).
      PERSONNES (dirigeants Legal via SIREN) : result_first_name, result_last_name,
        result_city, result_country_code, result_age, siren, current_company_name.
        ⚠️ PAS d'email ni de phone → un lead 'people' Legal seul ne produit pas de prospect
        (email requis) ; il sert à ENRICHIR une société (nom du dirigeant) ou à alimenter
        Emelia (email nominatif). Les alias d'autres sources (LKI) restent lus défensivement.
    """
    d = lead.get("data") or {}
    src = lead.get("source")  # "Legal" | "LKI" | "GMB"
    xg = d.get("x_gmb") or {}

    email = _first(d, "email", "generic_email", "contact_email")
    if isinstance(email, list):
        email = email[0] if email else None
    if not email:
        return None  # sans email, rien à valider/insérer (people Legal, ou société sans email)

    # alias Legal (result_*) ET LinkedIn/LKI (people_*, current_*, location_*)
    first = _first(d, "result_first_name", "people_first_name", "first_name", "prenom")
    last = _first(d, "result_last_name", "people_last_name", "last_name", "nom")
    full = _first(d, "result_full_name", "full_name")
    if not full and (first or last):
        full = " ".join(x for x in (first, last) if x)

    societe = _first(d, "legal_name", "company_name", "current_company_name", "employer", "name")
    website = (_first(d, "website", "domain")
               or _first(xg, "domain_principal_url", "domain_url", "open_website",
                         "website", "site", "url"))
    phone = _first(d, "phone", "phone_number", "tel")
    city = _first(d, "headquarters_city", "result_city", "location_city", "city")
    postal = _first(d, "headquarters_postal_code", "result_postal_code", "postal_code")
    role = _first(d, "result_role", "current_job_title", "mandate_role", "job_title")
    profile_url = _first(d, "profile_url", "current_company_profile_url", "linkedin_url")
    siren = _first(d, "siren")

    return {
        # champs scrappe_pending / prospect (alignés sur god_mode_agents.serper_places)
        "company_name":  societe or full or "",
        "contact_name":  full or "",
        "email":         email,
        "phone":         phone,
        "sector":        sector,
        "city":          city,
        "postal_code":   postal,
        "website":       website,
        "source":        "basile",
        "search_query":  search_query,
        "region_code":   region_code,
        "dept_code":     dept_code,
        "raw_data": {
            "basile_id":   lead.get("_id"),
            "basile_src":  src,
            "siren":       siren,
            "role":        role,
            "profile_url": profile_url,
            "first_name":  first,
            "last_name":   last,
        },
        # champs additionnels pour le pool (Serper ne les a pas : Basile nomme le décideur)
        "_pool_extra": {
            "prenom":      first,
            "nom":         last,
            "job_title":   role,
        },
    }


# ── Garde-fous de volume ────────────────────────────────────────────────────────
def enforce_volume_rules(total: int) -> dict:
    """Décide quoi faire d'un `total` avant extraction. Pur (testable sans clé)."""
    if total <= 0:
        return {"action": "skip", "reason": "aucun résultat", "passes": 0}
    if total > EXPORT_HARD_CAP:
        return {"action": "segment", "reason":
                f"{total:,} > cap {EXPORT_HARD_CAP:,} — segmenter (dept/NAF/taille) "
                f"avant extraction", "passes": 0}
    passes = (total + PASS_SIZE - 1) // PASS_SIZE
    return {"action": "extract", "reason":
            f"{total:,} ≤ cap — extraction en {passes} passe(s) de {PASS_SIZE}",
            "passes": passes}


# ── Orchestrateur d'un segment (collecte + validation + double écriture) ─────────
def run_segment(site: str, kind: str, filters: dict, *, sector: str | None = None,
                dept_code: str | None = None, region_code: str | None = None,
                max_contacts: int = PASS_SIZE, delay: float = DEFAULT_DELAY,
                dry_run: bool = True, progress_cb=None) -> dict:
    """Collecte UN segment Basile en passes de 1 000 et l'insère dans le pool.

    - COMPTE d'abord (gratuit). Refuse si > 20 000 (à segmenter en amont).
    - Pagine /find par pages de 100, throttle `delay`, jusqu'à `max_contacts`.
    - Pour chaque lead : normalise → valide l'email → double-écrit (scrappe_pending + pool).
    - Fallback email : si Basile n'a pas d'email direct mais a un website (x_gmb), on scrape
      la page contact du site exactement comme Serper fait — c'est ainsi qu'on trouve
      agence.colombes@cabinetvincent.fr à partir de la fiche Basile de Cabinet Vincent.
    - dry_run=True : ne fait QUE compter + normaliser (aucune écriture DB) — sûr sans quota.

    Retourne un récap. Ne lève pas sur erreur lead (skip + compteur).
    """
    from email_validator import validate_and_score
    from god_mode_agents import fetch_email_from_site

    total = count(kind, filters)
    rule = enforce_volume_rules(total)
    out = {"site": site, "kind": kind, "sector": sector, "dept_code": dept_code,
           "total": total, "rule": rule, "valid": 0, "rejected": 0,
           "duplicates": 0, "errors": 0, "dry_run": dry_run, "collected": 0,
           "website_scraped": 0}
    if rule["action"] != "extract":
        out["status"] = rule["action"]      # skip | segment
        return out

    target = min(total, max_contacts, EXPORT_HARD_CAP)
    gm = None
    cpb = None
    if not dry_run:
        import god_mode_backend as gm           # noqa: F811
        import contacts_pool_backend as cpb     # noqa: F811

    token, page = None, 0
    samples = []
    while out["collected"] < target:
        res = find(kind, filters, PAGE_SIZE, token)
        leads = res.get("leads", [])
        if not leads:
            break
        for lead in leads:
            if out["collected"] >= target:
                break
            out["collected"] += 1
            try:
                prospect = lead_to_prospect(
                    lead, sector=sector, dept_code=dept_code,
                    region_code=region_code, search_query=f"basile:{sector or kind}")
                if not prospect:
                    # Fallback : le lead n'a pas d'email direct chez Basile.
                    # On essaie de scraper le site web de la fiche (x_gmb ou website) —
                    # même technique que Serper pour trouver contact@, agence@, etc.
                    d = lead.get("data") or {}
                    xg = d.get("x_gmb") or {}
                    website = (_first(d, "website", "domain")
                               or _first(xg, "domain_principal_url", "domain_url",
                                         "open_website", "website", "site", "url"))
                    if website and not dry_run:
                        scraped_email = fetch_email_from_site(website)
                        if scraped_email:
                            out["website_scraped"] += 1
                            # On ré-injecte l'email dans le lead et on re-tente
                            lead_patched = dict(lead)
                            lead_patched["data"] = dict(d)
                            lead_patched["data"]["email"] = scraped_email
                            prospect = lead_to_prospect(
                                lead_patched, sector=sector, dept_code=dept_code,
                                region_code=region_code,
                                search_query=f"basile-web:{sector or kind}")
                    if not prospect:
                        out["rejected"] += 1
                        continue
                vres = validate_and_score(prospect["email"], prospect)
                if vres["decision"] == "drop":
                    out["rejected"] += 1
                    continue
                prospect["email"] = vres["email"]
                prospect["email_score"] = vres["score"]
                prospect["email_validation_reasons"] = vres["reasons"]
                prospect["status"] = ("manual_review" if vres["decision"] == "queue"
                                      else "mailnjoy_pending")
                if dry_run:
                    out["valid"] += 1
                    if len(samples) < 3:
                        samples.append({k: prospect[k] for k in
                                        ("company_name", "contact_name", "email",
                                         "sector", "city")})
                    continue
                # dédup léger avant insert (comme Serper) + tombstone des rejetés
                if gm.email_recently_validated(prospect["email"], days=30) or \
                   gm.email_in_pending(prospect["email"]) or \
                   gm.email_rejected(prospect["email"]):
                    out["duplicates"] += 1
                    continue
                gm.add_prospect_pending(site, prospect)
                pool_extra = prospect.pop("_pool_extra", {})
                cid = cpb.create_in_pool({
                    "email":   prospect["email"],
                    "societe": prospect["company_name"],
                    "prenom":  pool_extra.get("prenom"),
                    "nom":     pool_extra.get("nom"),
                    "job_title": pool_extra.get("job_title"),
                    "tel":     prospect["phone"],
                    "website": prospect["website"],
                    "city":    prospect["city"],
                    "postal_code": prospect["postal_code"],
                    "dept_code":   dept_code,
                    "region_code": region_code,
                    "sectors": [sector] if sector else None,
                    "email_score": vres["score"],
                    "email_validation_reasons": vres["reasons"],
                }, primary_source="basile")
                if cid:
                    cpb.upsert_site_history(cid, site, state="cold_email",
                                            source="basile", by="basile_segment")
                out["valid"] += 1
            except Exception as e:  # noqa: BLE001
                out["errors"] += 1
                print(f"  [basile] lead error (skip): {e}", file=sys.stderr)
        page += 1
        if progress_cb:
            progress_cb({"page": page, "collected": out["collected"], "valid": out["valid"]})
        token = (res.get("pagination") or {}).get("nextToken")
        if not token:
            break
        time.sleep(delay)

    if dry_run and samples:
        out["samples"] = samples
    out["status"] = "done"
    return out


# ── Flux DIRIGEANTS (sociétés → dirigeants nommés → Emelia email nominatif) ──────
# Stratégie retenue pour LCR (2026-06-17) : Basile donne société + dirigeant + SIREN
# (les dirigeants n'ont PAS d'email chez Basile), Emelia trouve l'email nominatif.
def _chunk(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def fetch_dirigeants_by_siren(sirens: list[str], delay: float = DEFAULT_DELAY) -> dict:
    """Map siren -> [{prenom, nom, role, city}] via /people/find (batch de SIREN)."""
    out: dict[str, list] = {}
    for batch in _chunk([s for s in sirens if s], 100):
        token = None
        while True:
            res = find("people", {"siren": {"include": batch},
                                   "result_is_current": True,
                                   "hide_legal_entities": True}, PAGE_SIZE, token)
            for l in res.get("leads", []):
                d = l.get("data") or {}
                sir = d.get("siren")
                if not sir:
                    continue
                out.setdefault(sir, []).append({
                    "prenom": d.get("result_first_name"),
                    "nom":    d.get("result_last_name"),
                    "role":   d.get("result_role") or d.get("mandate_role"),
                    "city":   d.get("result_city"),
                })
            token = (res.get("pagination") or {}).get("nextToken")
            if not token:
                break
            time.sleep(delay)
        time.sleep(delay)
    return out


def _emelia_module():
    """Charge le helper Emelia du skill en mappant EMELIA_API_KEY → EMELIA_KEY."""
    import importlib
    sys.path.insert(0, str(BASE_DIR / "skills" / "basile-b2b-search" / "scripts"))
    ee = importlib.import_module("emelia_enrich")
    ee.KEY = os.environ.get("EMELIA_API_KEY") or os.environ.get("EMELIA_KEY", "")
    if not ee.KEY:
        raise RuntimeError("EMELIA_API_KEY manquante")
    return ee


def _emelia_find_email(fullname: str, company: str, website: str | None):
    """Finder email Emelia (PAYANT, 1 crédit si trouvé). Décrémente le compteur local."""
    res = _emelia_module().find_email(fullname, company, website=website, country="France")
    try:
        import emelia_credits
        emelia_credits.record("find_email", found=bool(res.get("value")),
                              note=f"{fullname} @ {company}")
    except Exception:  # noqa: BLE001
        pass
    return res


def emelia_find_phone(linkedin_url: str):
    """Finder téléphone Emelia (PAYANT, 1 crédit si trouvé) via URL LinkedIn. Décrémente le compteur."""
    res = _emelia_module().find_phone(linkedin_url)
    try:
        import emelia_credits
        emelia_credits.record("find_phone", found=bool(res.get("value")), note=linkedin_url)
    except Exception:  # noqa: BLE001
        pass
    return res


def run_dirigeant_segment(site: str, companies_filter: dict, *, sector: str | None = None,
                          dept_code: str | None = None, region_code: str | None = None,
                          max_companies: int = PASS_SIZE, delay: float = DEFAULT_DELAY,
                          use_emelia: bool = False, dry_run: bool = True,
                          progress_cb=None) -> dict:
    """Sociétés (NAF/activity+géo) → dirigeants nommés → (opt) Emelia email nominatif → pool.

    - dry_run=True (défaut) : compte + jointure dirigeants + ESTIME le coût Emelia. AUCUN appel
      payant, AUCUNE écriture DB. C'est le mode sûr pour chiffrer avant de lancer.
    - use_emelia=True + dry_run=False : appelle Emelia (1 crédit/dirigeant) pour l'email nominatif,
      valide, et double-écrit (scrappe_pending + pool, prenom/nom/job_title remplis, source=basile).
    """
    from email_validator import validate_and_score

    total = count("companies", companies_filter)
    rule = enforce_volume_rules(total)
    out = {"site": site, "sector": sector, "dept_code": dept_code, "flow": "dirigeants",
           "companies_total": total, "rule": rule, "companies_scanned": 0,
           "dirigeants_found": 0, "emelia_needed": 0, "emelia_calls": 0,
           "valid": 0, "rejected": 0, "errors": 0, "dry_run": dry_run, "use_emelia": use_emelia}
    if rule["action"] != "extract":
        out["status"] = rule["action"]
        return out

    target = min(total, max_companies, EXPORT_HARD_CAP)

    # 1) collecte sociétés (siren + méta)
    companies, token = [], None
    while len(companies) < target:
        res = find("companies", companies_filter, PAGE_SIZE, token)
        leads = res.get("leads", [])
        if not leads:
            break
        for l in leads:
            if len(companies) >= target:
                break
            d = l.get("data") or {}
            xg = d.get("x_gmb") or {}
            companies.append({
                "siren":   d.get("siren"),
                "societe": d.get("legal_name") or d.get("company_name"),
                "website": (_first(d, "website", "domain")
                            or _first(xg, "domain_principal_url", "domain_url",
                                      "open_website", "website", "site", "url")),
                "city":    d.get("headquarters_city"),
                "postal":  d.get("headquarters_postal_code"),
                "phone":   d.get("phone"),
            })
        token = (res.get("pagination") or {}).get("nextToken")
        if not token:
            break
        time.sleep(delay)
    out["companies_scanned"] = len(companies)

    # 2) dirigeants par SIREN
    sirens = [c["siren"] for c in companies if c["siren"]]
    dmap = fetch_dirigeants_by_siren(sirens, delay) if sirens else {}
    pairs = []  # (company, dirigeant)
    for c in companies:
        for dg in dmap.get(c["siren"], []):
            if dg.get("prenom") or dg.get("nom"):
                pairs.append((c, dg))
    out["dirigeants_found"] = len(pairs)
    out["emelia_needed"] = len(pairs)   # 1 crédit Emelia par dirigeant

    if dry_run:
        out["cost_estimate"] = {"emelia_calls": len(pairs),
                                "note": "1 crédit Emelia / dirigeant si use_emelia"}
        out["samples"] = [{"societe": c["societe"], "dirigeant": f'{dg.get("prenom")} {dg.get("nom")}',
                           "city": c["city"], "website": c["website"]}
                          for c, dg in pairs[:5]]
        out["status"] = "dry_run"
        return out

    # 3) live : Emelia + validation + double écriture
    import god_mode_backend as gm
    import contacts_pool_backend as cpb
    for c, dg in pairs:
        try:
            fullname = " ".join(x for x in (dg.get("prenom"), dg.get("nom")) if x)
            email = None
            if use_emelia:
                er = _emelia_find_email(fullname, c["societe"], c["website"])
                out["emelia_calls"] += 1
                email = er.get("value") if er.get("status") == "completed" else None
            if not email:
                out["rejected"] += 1
                continue
            prospect = {
                "company_name": c["societe"], "contact_name": fullname, "email": email,
                "phone": c["phone"], "sector": sector, "city": c["city"],
                "postal_code": c["postal"], "website": c["website"], "source": "basile",
                "search_query": f"basile-dirigeant:{sector or ''}",
                "region_code": region_code, "dept_code": dept_code,
                "raw_data": {"siren": c["siren"], "role": dg.get("role"),
                             "first_name": dg.get("prenom"), "last_name": dg.get("nom"),
                             "email_source": "emelia"},
            }
            vres = validate_and_score(email, prospect)
            if vres["decision"] == "drop":
                out["rejected"] += 1
                continue
            prospect.update(email=vres["email"], email_score=vres["score"],
                            email_validation_reasons=vres["reasons"],
                            status=("manual_review" if vres["decision"] == "queue"
                                    else "mailnjoy_pending"))
            if gm.email_recently_validated(vres["email"], days=30) or \
               gm.email_in_pending(vres["email"]) or gm.email_rejected(vres["email"]):
                continue
            gm.add_prospect_pending(site, prospect)
            cid = cpb.create_in_pool({
                "email": vres["email"], "societe": c["societe"],
                "prenom": dg.get("prenom"), "nom": dg.get("nom"), "job_title": dg.get("role"),
                "tel": c["phone"], "website": c["website"], "city": c["city"],
                "postal_code": c["postal"], "dept_code": dept_code, "region_code": region_code,
                "sectors": [sector] if sector else None, "email_score": vres["score"],
                "email_validation_reasons": vres["reasons"],
            }, primary_source="basile")
            if cid:
                cpb.upsert_site_history(cid, site, state="cold_email",
                                        source="basile", by="basile_dirigeant")
            out["valid"] += 1
        except Exception as e:  # noqa: BLE001
            out["errors"] += 1
            print(f"  [basile-dirigeant] {e}", file=sys.stderr)
        if progress_cb:
            progress_cb({"valid": out["valid"], "emelia_calls": out["emelia_calls"]})
    out["status"] = "done"
    return out


# ── Intégration autoscrape (Serper + Basile en parallèle de sources) ────────────
def _city_to_basile_city(city_name: str) -> str:
    """Normalise un nom de ville (workflow_geo) → majuscules Basile.
    Arrondissements (Paris 1er, Lyon 2e, Marseille 16e) → ville parente."""
    base = city_name.split()[0].upper()
    if base in ("PARIS", "LYON", "MARSEILLE"):
        return base
    return city_name.upper()


def run_sector_for_city(site: str, sector: str, city_name: str,
                        dept_code: str | None = None, region_code: str | None = None,
                        target: int = 50, delay: float = DEFAULT_DELAY,
                        dry_run: bool = False) -> dict:
    """Collecte Basile pour un secteur × une ville. Complète Serper sans remplacer.

    Utilise SECTOR_NAF pour mapper le code secteur → codes NAF. Si pas de mapping,
    retourne status='no_naf'. Filtre géo = headquarters_city (MAJUSCULES Basile).
    Les résultats sont insérés dans le même pool que Serper (dédup par email).

    Retourne {"valid", "rejected", "duplicates", "errors", "status", ...}
    """
    global BASILE_BLOCKED_STATUS
    nafs = SECTOR_NAF.get(sector)
    if not nafs:
        return {"valid": 0, "rejected": 0, "duplicates": 0, "errors": 0, "status": "no_naf",
                "sector": sector, "city": city_name}

    if not BASILE_KEY:
        return {"valid": 0, "rejected": 0, "duplicates": 0, "errors": 0,
                "status": "no_key", "sector": sector, "city": city_name}

    basile_city = _city_to_basile_city(city_name)
    filters = {
        "naf_code":        {"include": nafs},
        "company_ceased":  False,
        "headquarters_city": {"include": [basile_city]},  # format obligatoire {include:[...]}
    }

    try:
        BASILE_BLOCKED_STATUS = None  # reset avant l'appel
        res = run_segment(
            site, "companies", filters,
            sector=sector, dept_code=dept_code, region_code=region_code,
            max_contacts=target, delay=delay, dry_run=dry_run,
        )
        res["city"] = city_name
        return res
    except RuntimeError as e:
        msg = str(e)
        if "BASILE_BLOCKED" in msg:
            return {"valid": 0, "rejected": 0, "duplicates": 0, "errors": 1,
                    "status": "blocked", "city": city_name, "error": msg}
        return {"valid": 0, "rejected": 0, "duplicates": 0, "errors": 1,
                "status": "error", "city": city_name, "error": msg}
    except Exception as e:  # noqa: BLE001
        return {"valid": 0, "rejected": 0, "duplicates": 0, "errors": 1,
                "status": "error", "city": city_name, "error": str(e)}


# ── CLI ─────────────────────────────────────────────────────────────────────────
def main():
    import argparse
    ap = argparse.ArgumentParser(description="Connecteur Basile pour Genesis")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_count = sub.add_parser("count", help="compter (gratuit)")
    p_count.add_argument("kind", choices=["people", "companies"])
    p_count.add_argument("filters", help="JSON des filtres")

    p_seg = sub.add_parser("segment", help="collecter un segment (1 passe)")
    p_seg.add_argument("kind", choices=["people", "companies"])
    p_seg.add_argument("filters", help="JSON des filtres")
    p_seg.add_argument("--site", required=True)
    p_seg.add_argument("--sector", default=None)
    p_seg.add_argument("--dept", default=None)
    p_seg.add_argument("--region", default=None)
    p_seg.add_argument("--max", type=int, default=PASS_SIZE)
    p_seg.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    p_seg.add_argument("--live", action="store_true", help="écrit en DB (sinon dry-run)")

    p_dir = sub.add_parser("dirigeants", help="sociétés → dirigeants nommés → (opt) Emelia")
    p_dir.add_argument("filters", help="JSON des filtres ENTREPRISES (naf_code/activity + géo)")
    p_dir.add_argument("--site", required=True)
    p_dir.add_argument("--sector", default=None)
    p_dir.add_argument("--dept", default=None)
    p_dir.add_argument("--region", default=None)
    p_dir.add_argument("--max", type=int, default=PASS_SIZE)
    p_dir.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    p_dir.add_argument("--emelia", action="store_true", help="appelle Emelia (PAYANT, 1 crédit/dirigeant)")
    p_dir.add_argument("--live", action="store_true", help="écrit en DB (implique le coût Emelia si --emelia)")

    args = ap.parse_args()
    if args.cmd == "count":
        print(json.dumps({"total": count(args.kind, json.loads(args.filters))}))
    elif args.cmd == "segment":
        res = run_segment(args.site, args.kind, json.loads(args.filters),
                          sector=args.sector, dept_code=args.dept, region_code=args.region,
                          max_contacts=args.max, delay=args.delay, dry_run=not args.live)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.cmd == "dirigeants":
        res = run_dirigeant_segment(args.site, json.loads(args.filters),
                                    sector=args.sector, dept_code=args.dept, region_code=args.region,
                                    max_companies=args.max, delay=args.delay,
                                    use_emelia=args.emelia, dry_run=not args.live)
        print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
