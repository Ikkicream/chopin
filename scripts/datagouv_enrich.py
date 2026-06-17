#!/usr/bin/env python3
"""
datagouv_enrich.py — Enrichissement des contacts du pool Genesis via l'API
publique recherche-entreprises.api.gouv.fr (data.gouv.fr).

Rattaché au pool de contacts (data/contacts.duckdb) — l'enrichissement est une
donnée d'IDENTITÉ ENTREPRISE (SIRET / NAF / taille / signaux), donc globale et
mutualisée inter-sites. Résultats stockés dans la table satellite 1:1
`contact_enrichment` (clé = contacts.id).

Principes (repris du skill cheffer-datagouv-enrichment) :
  - rate limit 6 req/s (sous la limite officielle de 7)
  - cache local SQLite (TTL 30 jours) pour ne pas re-taper l'API
  - exclusions RGPD systématiques : statut_diffusion 'P', administration /
    service public, entreprise fermée
  - AUCUNE donnée personnelle (dirigeants / mandataires) n'est stockée
  - anti-join : ne traite que les contacts pas encore enrichis (sauf --rebuild)

Le scrape ne fournit PAS de SIRET → match par dénomination (societe) + géo
(code_postal / city). Fiabilité moyenne ; les matchs ambigus sont exclus.

Usage :
    python3 scripts/datagouv_enrich.py --dry-run --limit 5
    python3 scripts/datagouv_enrich.py --limit 200
    python3 scripts/datagouv_enrich.py                 # tout le reliquat
    python3 scripts/datagouv_enrich.py --rebuild        # ré-enrichit tout
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
POOL_DB = BASE_DIR / "data" / "contacts.duckdb"
CACHE_DB = BASE_DIR / "data" / "datagouv_cache.sqlite"

API_BASE = "https://recherche-entreprises.api.gouv.fr"
USER_AGENT = "genesis-datagouv-enrichment/1.0 (+leclientroi.com)"
RATE_LIMIT_PER_SEC = 4    # l'API throttle (429) au-delà ; le backoff ajuste si besoin
CACHE_TTL_DAYS = 30
WRITE_RETRY = 5            # retries si lock DuckDB (écriture concurrente du pool)
API_RETRY = 4             # retries sur 429 / erreur réseau, avec backoff

TRANCHES_EFFECTIFS = {
    "NN": "Non employeur", "00": "0 salarié", "01": "1-2", "02": "3-5",
    "03": "6-9", "11": "10-19", "12": "20-49", "21": "50-99",
    "22": "100-199", "31": "200-249", "32": "250-499", "41": "500-999",
    "42": "1000-1999", "51": "2000-4999", "52": "5000-9999", "53": "10000+",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("datagouv_enrich")


# --------------------------------------------------------------------------- #
# Schéma DuckDB — table satellite 1:1 de contacts
# --------------------------------------------------------------------------- #
ENRICHMENT_DDL = """
CREATE TABLE IF NOT EXISTS contact_enrichment (
    contact_id               VARCHAR PRIMARY KEY,
    siret                    VARCHAR,
    siren                    VARCHAR,
    denomination             VARCHAR,
    nom_commercial           VARCHAR,
    sigle                    VARCHAR,
    code_naf                 VARCHAR,
    section_naf              VARCHAR,
    categorie_entreprise     VARCHAR,
    tranche_effectif_code    VARCHAR,
    tranche_effectif_libelle VARCHAR,
    code_postal              VARCHAR,
    commune                  VARCHAR,
    code_insee               VARCHAR,
    dept_code                VARCHAR,
    region_code              VARCHAR,
    latitude                 DOUBLE,
    longitude                DOUBLE,
    etat_administratif       VARCHAR,
    date_creation            DATE,
    date_fermeture           DATE,
    statut_diffusion         VARCHAR,
    est_rge                  BOOLEAN,
    est_qualiopi             BOOLEAN,
    est_ess                  BOOLEAN,
    est_bio                  BOOLEAN,
    est_societe_mission      BOOLEAN,
    match_quality            VARCHAR,
    excluded                 BOOLEAN,
    exclusion_reason         VARCHAR,
    enriched_at              TIMESTAMP,
    raw                      JSON
);
"""

# Ordre des colonnes pour l'INSERT (doit suivre le DDL)
COLS = [
    "contact_id", "siret", "siren", "denomination", "nom_commercial", "sigle",
    "code_naf", "section_naf", "categorie_entreprise", "tranche_effectif_code",
    "tranche_effectif_libelle", "code_postal", "commune", "code_insee",
    "dept_code", "region_code", "latitude", "longitude", "etat_administratif",
    "date_creation", "date_fermeture", "statut_diffusion", "est_rge",
    "est_qualiopi", "est_ess", "est_bio", "est_societe_mission",
    "match_quality", "excluded", "exclusion_reason", "enriched_at", "raw",
]


def ensure_enrichment_table() -> None:
    for attempt in range(WRITE_RETRY):
        try:
            c = duckdb.connect(str(POOL_DB))
            try:
                c.execute(ENRICHMENT_DDL)
            finally:
                c.close()
            return
        except Exception as e:
            if attempt == WRITE_RETRY - 1:
                raise
            log.warning("DuckDB occupé (création table), retry %d : %s", attempt + 1, e)
            time.sleep(1.5)


# --------------------------------------------------------------------------- #
# Cache SQLite (séparé de DuckDB : petits upserts fréquents, pas de contention)
# --------------------------------------------------------------------------- #
class Cache:
    def __init__(self, path: Path, ttl_days: int = CACHE_TTL_DAYS, enabled: bool = True):
        self.enabled = enabled
        self.ttl = timedelta(days=ttl_days)
        if not enabled:
            return
        self._conn = sqlite3.connect(str(path))
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, fetched_at TIMESTAMP, payload TEXT)"
        )
        self._conn.commit()

    def get(self, key: str):
        if not self.enabled:
            return None
        row = self._conn.execute("SELECT fetched_at, payload FROM cache WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        if datetime.now(timezone.utc) - datetime.fromisoformat(row[0]) > self.ttl:
            return None
        return json.loads(row[1])

    def set(self, key: str, payload: dict):
        if not self.enabled:
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (key, fetched_at, payload) VALUES (?,?,?)",
            (key, datetime.now(timezone.utc).isoformat(), json.dumps(payload)),
        )
        self._conn.commit()

    def close(self):
        if self.enabled:
            self._conn.close()


class RateLimiter:
    def __init__(self, max_per_sec: int):
        self.interval = 1.0 / max_per_sec
        self.last = 0.0

    def wait(self):
        elapsed = time.monotonic() - self.last
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self.last = time.monotonic()


# --------------------------------------------------------------------------- #
# Client API
# --------------------------------------------------------------------------- #
class DataGouvClient:
    def __init__(self, cache: Cache, rl: RateLimiter, stats: dict):
        self.cache = cache
        self.rl = rl
        self.stats = stats
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    def search(self, params: dict):
        """Retourne le JSON (dict, éventuellement {results:[]}) en cas de succès,
        ou None en cas d'échec TRANSITOIRE (429/réseau) après retries — None ne doit
        donc PAS être interprété comme 'aucun résultat' mais comme 'à réessayer'."""
        key = "search:" + json.dumps(params, sort_keys=True)
        cached = self.cache.get(key)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return cached
        for attempt in range(API_RETRY):
            self.rl.wait()
            self.stats["api_calls"] += 1
            try:
                r = self.session.get(API_BASE + "/search", params=params, timeout=30)
                if r.status_code == 429:
                    self.stats["rate_limited"] = self.stats.get("rate_limited", 0) + 1
                    wait = float(r.headers.get("Retry-After", 0) or 0) or (1.5 * (2 ** attempt))
                    log.warning("429 (req %d/%d), backoff %.1fs", attempt + 1, API_RETRY, wait)
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                data = r.json()
            except requests.RequestException as e:
                if attempt == API_RETRY - 1:
                    log.warning("Erreur API définitive %s : %s", params, e)
                    return None
                time.sleep(1.5 * (attempt + 1))
                continue
            self.cache.set(key, data)
            return data
        return None  # 429 persistant → échec transitoire

    def by_denomination(self, denom: str, code_postal: str = "", city: str = "", dept: str = ""):
        params = {"q": denom, "per_page": 5}
        cp = (code_postal or "").strip()
        if cp.isdigit() and len(cp) == 5:
            params["code_postal"] = cp
        elif city and city.strip():
            params["q"] = f"{denom} {city.strip()}"
        elif dept and dept.strip():
            params["departement"] = dept.strip()
        return self.search(params)


# --------------------------------------------------------------------------- #
# Enrichissement d'un contact → ligne contact_enrichment (ou exclusion)
# --------------------------------------------------------------------------- #
def _clean_date(v):
    v = (v or "").strip()
    return v[:10] if len(v) >= 10 else None


# Champs retirés du payload `raw` avant stockage : données personnelles (RGPD)
# + volumineux/inutiles. On ne persiste JAMAIS de dirigeants/mandataires.
_RAW_DROP = (
    "dirigeants", "mandataires_sociaux", "beneficiaires_effectifs",
    "finances", "matching_etablissements",
)


def _sanitize_raw(raw: dict) -> str:
    clean = {k: v for k, v in raw.items() if k not in _RAW_DROP}
    return json.dumps(clean, ensure_ascii=False)


_DENOM_SPLIT = re.compile(r"\s+[\-–—|/]\s+|,")     # " - ", " | ", " / ", ","
_TRAILING_DEPT = re.compile(r"\s+\d{2,3}\s*$")      # "FB Plomberie 92" → "FB Plomberie"


def _clean_denom(denom: str) -> str:
    """Variante nettoyée d'un nom scrapé bruyant : garde la tête avant le premier
    séparateur descriptif et retire un n° de département en fin."""
    head = _DENOM_SPLIT.split(denom, 1)[0].strip()
    head = _TRAILING_DEPT.sub("", head).strip()
    return head


def _denom_variants(denom: str) -> list[str]:
    """Requête brute d'abord (plus spécifique), puis variante nettoyée en fallback."""
    variants = [denom]
    cleaned = _clean_denom(denom)
    if cleaned and cleaned.upper() != denom.upper() and len(cleaned) >= 3:
        variants.append(cleaned)
    return variants


def enrich_contact(contact: dict, client: DataGouvClient) -> dict:
    """Retourne un dict prêt pour l'INSERT (toutes les clés de COLS)."""
    cid = contact["id"]
    now = datetime.now(timezone.utc)
    base = {k: None for k in COLS}
    base["contact_id"] = cid
    base["enriched_at"] = now
    base["excluded"] = False

    # Sémantique du flag `excluded` :
    #   TRUE  = exclusion DURE (ne jamais contacter) : fermée / administration / statut P
    #   FALSE = contactable. Soit enrichi (siret renseigné), soit simplement non-vérifié
    #           (non_trouve / ambigu) — match_quality le précise, exclusion_reason reste NULL.
    denom = (contact.get("societe") or "").strip()
    if not denom:
        base["match_quality"] = "non_trouve"  # excluded reste FALSE : contactable, non vérifié
        return base

    results = []
    used_cleaned = False
    got_response = False     # au moins une réponse HTTP 200 reçue
    transient = False        # au moins un échec 429/réseau
    for vi, variant in enumerate(_denom_variants(denom)):
        payload = client.by_denomination(
            variant,
            code_postal=contact.get("postal_code") or "",
            city=contact.get("city") or "",
            dept=contact.get("dept_code") or "",
        )
        if payload is None:
            transient = True
            continue
        got_response = True
        results = payload.get("results") or []
        if results:
            used_cleaned = vi > 0
            break

    # Échec transitoire (429) sans aucune réponse 200 → ne rien écrire, repassera au prochain run
    if not got_response and transient:
        base["_transient"] = True
        return base

    raw = None
    quality = "non_trouve"
    match_name = (_clean_denom(denom) if used_cleaned else denom).upper()
    geo = bool(contact.get("postal_code") or contact.get("city"))
    if len(results) == 1:
        raw = results[0]
        quality = "match_denomination_clean" if used_cleaned else \
                  ("match_denomination_ville" if geo else "match_denomination_exact")
    elif len(results) >= 2:
        top = results[0]
        top_name = (top.get("nom_complet") or "").upper()
        if match_name in top_name or top_name in match_name:
            raw = top
            quality = "match_fuzzy_top1"
        else:
            quality = "match_ambigu"

    base["match_quality"] = quality

    if not raw:
        # non_trouve / ambigu = non vérifié, PAS une exclusion dure → reste contactable
        return base

    # ----- Exclusions RGPD / qualité -----
    statut = raw.get("statut_diffusion", "O")
    complements = raw.get("complements") or {}
    if statut == "P":
        base.update(excluded=True, exclusion_reason="statut_diffusion_partielle",
                    statut_diffusion=statut, siren=raw.get("siren"))
        return base
    if complements.get("est_administration") or complements.get("est_service_public"):
        base.update(excluded=True, exclusion_reason="administration_service_public",
                    siren=raw.get("siren"))
        return base
    if raw.get("etat_administratif") != "A":
        base.update(excluded=True, exclusion_reason="entreprise_fermee",
                    etat_administratif=raw.get("etat_administratif"), siren=raw.get("siren"))
        return base

    # ----- Mapping schéma plat (champs utiles uniquement) -----
    siege = raw.get("siege") or {}
    tcode = raw.get("tranche_effectif_salarie") or ""
    base.update(
        siret=siege.get("siret"),
        siren=raw.get("siren"),
        denomination=raw.get("nom_raison_sociale"),
        nom_commercial=siege.get("nom_commercial"),
        sigle=raw.get("sigle"),
        code_naf=raw.get("activite_principale"),
        section_naf=raw.get("section_activite_principale"),
        categorie_entreprise=raw.get("categorie_entreprise"),
        tranche_effectif_code=tcode,
        tranche_effectif_libelle=TRANCHES_EFFECTIFS.get(tcode, ""),
        code_postal=siege.get("code_postal"),
        commune=siege.get("libelle_commune"),
        code_insee=siege.get("commune"),
        dept_code=siege.get("departement"),
        region_code=siege.get("region"),
        latitude=float(siege["latitude"]) if siege.get("latitude") else None,
        longitude=float(siege["longitude"]) if siege.get("longitude") else None,
        etat_administratif=raw.get("etat_administratif"),
        date_creation=_clean_date(raw.get("date_creation")),
        date_fermeture=_clean_date(raw.get("date_fermeture")),
        statut_diffusion=statut,
        est_rge=bool(complements.get("est_rge", False)),
        est_qualiopi=bool(complements.get("est_qualiopi", False)),
        est_ess=bool(complements.get("est_ess", False)),
        est_bio=bool(complements.get("est_bio", False)),
        est_societe_mission=bool(complements.get("est_societe_mission", False)),
        raw=_sanitize_raw(raw),
    )
    return base


# --------------------------------------------------------------------------- #
# I/O DuckDB
# --------------------------------------------------------------------------- #
def fetch_worklist(limit: int | None, rebuild: bool) -> list[dict]:
    """Anti-join : contacts avec societe pas encore enrichis (ou tous si rebuild)."""
    where_extra = "" if rebuild else \
        "AND NOT EXISTS (SELECT 1 FROM contact_enrichment e WHERE e.contact_id = c.id)"
    q = f"""
        SELECT c.id, c.societe, c.city, c.postal_code, c.dept_code
        FROM contacts c
        WHERE c.societe IS NOT NULL AND c.societe <> ''
          {where_extra}
        ORDER BY c.updated_at DESC
        {f'LIMIT {int(limit)}' if limit else ''}
    """
    c = duckdb.connect(str(POOL_DB), read_only=True)
    try:
        rows = c.execute(q).fetchall()
    finally:
        c.close()
    return [dict(zip(["id", "societe", "city", "postal_code", "dept_code"], r)) for r in rows]


def flush_batch(batch: list[dict]) -> None:
    """INSERT OR REPLACE d'un lot. Retry si lock (écriture concurrente du pool)."""
    if not batch:
        return
    placeholders = ",".join(["?"] * len(COLS))
    sql = f"INSERT OR REPLACE INTO contact_enrichment ({','.join(COLS)}) VALUES ({placeholders})"
    params = [[row.get(k) for k in COLS] for row in batch]
    for attempt in range(WRITE_RETRY):
        try:
            c = duckdb.connect(str(POOL_DB))
            try:
                c.executemany(sql, params)
            finally:
                c.close()
            return
        except Exception as e:
            if attempt == WRITE_RETRY - 1:
                raise
            log.warning("DuckDB occupé (flush), retry %d : %s", attempt + 1, e)
            time.sleep(1.5)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="Limiter à N contacts")
    ap.add_argument("--rebuild", action="store_true", help="Ré-enrichir même les contacts déjà enrichis")
    ap.add_argument("--no-cache", action="store_true", help="Désactive le cache SQLite")
    ap.add_argument("--rate-limit", type=int, default=RATE_LIMIT_PER_SEC, help="Req/s max (≤7)")
    ap.add_argument("--dry-run", action="store_true", help="N'écrit rien en base, montre le résultat")
    ap.add_argument("--batch", type=int, default=50, help="Taille des lots d'écriture DuckDB")
    args = ap.parse_args()

    rate = min(args.rate_limit, 7)
    ensure_enrichment_table()

    worklist = fetch_worklist(args.limit, args.rebuild)
    log.info("%d contact(s) à enrichir (rebuild=%s, dry_run=%s)", len(worklist), args.rebuild, args.dry_run)
    if not worklist:
        log.info("Rien à faire.")
        return 0

    est = len(worklist) / rate
    log.info("Durée estimée minimale : ~%.0fs (%d × %d req/s)", est, len(worklist), rate)

    cache = Cache(CACHE_DB, enabled=not args.no_cache)
    rl = RateLimiter(rate)
    stats = {"api_calls": 0, "cache_hits": 0}
    client = DataGouvClient(cache, rl, stats)

    enriched = unmatched = excluded = skipped = 0
    reasons: dict[str, int] = {}
    unmatched_reasons: dict[str, int] = {}
    batch: list[dict] = []
    samples: list[dict] = []
    t0 = time.monotonic()

    for i, contact in enumerate(worklist, 1):
        row = enrich_contact(contact, client)
        if row.get("_transient"):
            skipped += 1
            if i % 50 == 0:
                log.info("  ...%d/%d (transitoires ignorés: %d)", i, len(worklist), skipped)
            continue
        if row["excluded"]:
            excluded += 1
            reasons[row["exclusion_reason"]] = reasons.get(row["exclusion_reason"], 0) + 1
        elif not row.get("siret"):
            unmatched += 1
            mq = row.get("match_quality") or "non_trouve"
            unmatched_reasons[mq] = unmatched_reasons.get(mq, 0) + 1
        else:
            enriched += 1
            if len(samples) < 5:
                samples.append({"societe_scrape": contact["societe"], **{k: row[k] for k in
                               ("denomination", "siret", "code_naf", "categorie_entreprise",
                                "tranche_effectif_libelle", "commune", "est_rge", "est_qualiopi", "match_quality")}})
        if not args.dry_run:
            batch.append(row)
            if len(batch) >= args.batch:
                flush_batch(batch)
                batch = []
        if i % 50 == 0:
            log.info("  ...%d/%d (%d enrichis, %d exclus, API=%d cache=%d)",
                     i, len(worklist), enriched, excluded, stats["api_calls"], stats["cache_hits"])

    if not args.dry_run:
        flush_batch(batch)
    cache.close()

    dur = time.monotonic() - t0
    log.info("=" * 60)
    log.info("Total: %d | Enrichis: %d | Non-vérifiés(contactables): %d | Exclus durs: %d | Transitoires(non écrits): %d | API: %d | Cache: %d | 429: %d | %.1fs",
             len(worklist), enriched, unmatched, excluded, skipped, stats["api_calls"], stats["cache_hits"],
             stats.get("rate_limited", 0), dur)
    log.info("Exclusions DURES par motif (filtrées au push): %s", json.dumps(reasons, ensure_ascii=False))
    log.info("Non-vérifiés par motif (restent contactables): %s", json.dumps(unmatched_reasons, ensure_ascii=False))
    log.info("Échantillon enrichis:")
    for s in samples:
        log.info("  %s", json.dumps(s, ensure_ascii=False))
    if args.dry_run:
        log.info("(--dry-run : aucune écriture en base)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
