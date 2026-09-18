#!/usr/bin/env python3
"""
csv_import_backend.py — Import CSV intelligent vers le pool mutualisé (contacts.duckdb).

Flux en 2 phases :
  1. analyze(file_path, site, filename) :
       - détecte séparateur (`;` `,` tab `|`) + charset (utf-8 / cp1252 / latin-1)
       - mappe les colonnes du fichier vers les champs du pool (alias FR/EN)
       - compte les valeurs distinctes de la colonne secteur
       - 1 SEUL appel DeepSeek : mappe ces valeurs vers nos secteurs existants,
         crée les manquants (plafond 30 secteurs au total), bucket "autre" sinon
       - pré-analyse (dédup batchée par email) : OK / KO + raison, nouveaux / enrichis
       - persiste un fichier méta {import_id}.json, renvoie le récap
  2. commit_import(import_id, site) : générateur d'events de progression (SSE)
       - persiste les nouveaux secteurs validés (add_sector, recheck cap 30)
       - upsert batché (1 connexion) via create_in_pool + upsert_site_history
       - source="manual"

Dédup : clé primaire = email. Doublons existants → enrichissement NULL-only
(comportement create_in_pool). Doublons internes au fichier → 1ʳᵉ occurrence gardée.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent
IMPORTS_DIR = BASE_DIR / "data" / "imports"

sys.path.insert(0, str(SCRIPTS_DIR))

MAX_ROWS = 200_000
KO_SAMPLE_LIMIT = 100
SAMPLE_ROWS = 10

# ── Mapping colonnes fichier → champ pool (clés = header normalisé) ─────────────
COLUMN_ALIASES: dict[str, str] = {
    # email (PK)
    "email": "email", "mail": "email", "courriel": "email", "emailpro": "email",
    "adresseemail": "email",
    # identité
    "firstname": "prenom", "prenom": "prenom", "prnom": "prenom",
    "lastname": "nom", "nom": "nom", "nomdefamille": "nom",
    # société
    "companyname": "societe", "company": "societe", "societe": "societe",
    "socit": "societe", "entreprise": "societe", "raisonsociale": "societe",
    # téléphone
    "tel": "tel", "telephone": "tel", "tlphone": "tel", "phone": "tel",
    "mobile": "tel", "portable": "tel", "tel1": "tel",
    # localisation
    "location": "postal_code", "cp": "postal_code", "codepostal": "postal_code",
    "postal": "postal_code", "postalcode": "postal_code", "zip": "postal_code",
    "city": "city", "ville": "city", "commune": "city",
    # web (email2 = domaine société)
    "website": "website", "site": "website", "siteweb": "website", "url": "website",
    "domaine": "website", "domain": "website", "email2": "website",
    # poste
    "jobtitle": "job_title", "poste": "job_title", "intitule": "job_title",
    "intitul": "job_title", "titre": "job_title",
    "civility": "civility", "civilite": "civility", "civilit": "civility",
    "function": "job_function", "fonction": "job_function",
    # secteur
    "lookupcategorie": "sector", "lookupcatgorie": "sector", "categorie": "sector",
    "catgorie": "sector", "secteur": "sector", "sector": "sector",
    "industrie": "sector", "industry": "sector", "activite": "sector",
}

POOL_FIELD_LABELS = {
    "email": "Email (clé)", "prenom": "Prénom", "nom": "Nom", "societe": "Société",
    "tel": "Téléphone", "postal_code": "Code postal", "city": "Ville",
    "website": "Site web", "job_title": "Poste", "civility": "Civilité",
    "job_function": "Fonction", "sector": "Secteur",
}


# ── Helpers ─────────────────────────────────────────────────────────────────--
def _norm(s: str) -> str:
    """lower + retire accents + garde alphanum (pour matcher les en-têtes)."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _decode(raw: bytes) -> tuple[str, str]:
    """Décode des bytes en (texte NFC, charset retenu)."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return unicodedata.normalize("NFC", raw.decode("utf-8-sig")), "utf-8-sig"
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return unicodedata.normalize("NFC", raw.decode(enc)), enc
        except UnicodeDecodeError:
            continue
    return unicodedata.normalize("NFC", raw.decode("latin-1", errors="replace")), "latin-1"


def _detect_sep(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        return dialect.delimiter
    except Exception:
        first = next((l for l in sample.splitlines() if l.strip()), "")
        counts = {sep: first.count(sep) for sep in (";", ",", "\t", "|")}
        best = max(counts, key=counts.get)
        return best if counts[best] > 0 else ","


def _valid_email(email: str) -> bool:
    email = (email or "").strip()
    if "@" not in email or " " in email:
        return False
    local, _, domain = email.partition("@")
    return bool(local) and "." in domain and not domain.endswith(".")


def _derive_dept(postal: str) -> str:
    p = re.sub(r"\D", "", postal or "")
    if len(p) >= 3 and p[:2] in ("97", "98"):
        return p[:3]
    return p[:2] if len(p) >= 2 else ""


def _imports_dir(site: str) -> Path:
    d = IMPORTS_DIR / site
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cleanup_old(site: str, max_age_days: int = 7) -> None:
    """Supprime fichiers + méta de plus de N jours."""
    d = IMPORTS_DIR / site
    if not d.exists():
        return
    cutoff = time.time() - max_age_days * 86400
    for f in d.iterdir():
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
        except Exception:
            pass


def _parse_json_block(text: str) -> dict | None:
    """Extrait le 1er bloc {...} d'une réponse LLM."""
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


# ── Lecture fichier ────────────────────────────────────────────────────────---
def _read_rows(file_path: str, sep: str | None = None, charset: str | None = None):
    """Retourne (header:list[str], rows:list[list[str]], sep, charset)."""
    raw = Path(file_path).read_bytes()
    if charset:
        text = unicodedata.normalize("NFC", raw.decode(charset, errors="replace"))
    else:
        text, charset = _decode(raw)
    if sep is None:
        sep = _detect_sep(text[:8192])
    reader = csv.reader(io.StringIO(text), delimiter=sep)
    rows = list(reader)
    header = rows[0] if rows else []
    return header, rows[1:], sep, charset


def _build_mapping(header: list[str]) -> tuple[dict, list, list]:
    """Renvoie (mapping {idx: pool_field}, columns [{name, field}], unmapped [name])."""
    mapping: dict[int, str] = {}
    taken: set[str] = set()
    columns, unmapped = [], []
    for idx, name in enumerate(header):
        field = COLUMN_ALIASES.get(_norm(name))
        if field and field not in taken:
            mapping[idx] = field
            taken.add(field)
            columns.append({"name": name, "field": field, "field_label": POOL_FIELD_LABELS.get(field, field)})
        else:
            columns.append({"name": name, "field": None, "field_label": "—"})
            unmapped.append(name)
    return mapping, columns, unmapped


def _row_to_data(row: list[str], mapping: dict[int, str]) -> dict:
    """Transforme une ligne brute en dict de champs pool (sans le secteur)."""
    data: dict[str, str] = {}
    for idx, field in mapping.items():
        if idx >= len(row):
            continue
        val = (row[idx] or "").strip()
        if not val or field == "sector":
            continue
        if field == "website":
            if not val.startswith(("http://", "https://")):
                val = "https://" + val.lstrip("/")
        data[field] = val
    # dérivation dept depuis le code postal
    if data.get("postal_code"):
        dept = _derive_dept(data["postal_code"])
        if dept:
            data["dept_code"] = dept
    return data


# ── Matching secteur (1 appel DeepSeek) ────────────────────────────────────---
def _match_sectors(distinct_counts: dict[str, int], site: str) -> tuple[dict, list]:
    """Renvoie (sector_mapping {valeur_fichier: code}, new_sectors [{code,label,emoji,kind}]).

    Réutilise les secteurs existants quand pertinent, crée les manquants, plafond 30.
    """
    from god_mode_backend import list_sectors, MAX_SECTORS

    existing = list_sectors()
    existing_codes = {s["code"] for s in existing}
    if not distinct_counts:
        return {}, []

    values = sorted(distinct_counts.items(), key=lambda kv: -kv[1])
    cat_lines = "\n".join(f'- "{v}" ({n} contacts)' for v, n in values)
    sect_lines = "\n".join(f'- {s["code"]} : {s["label"]} ({s["kind"]})' for s in existing)
    available = MAX_SECTORS - len(existing_codes)

    prompt = f"""Tu organises des secteurs d'activité pour une base de prospection B2B/B2C.

SECTEURS EXISTANTS ({len(existing_codes)}) :
{sect_lines}

CATÉGORIES DU FICHIER À MAPPER ({len(values)}) :
{cat_lines}

Règles :
1. Mappe CHAQUE catégorie du fichier vers un code secteur.
2. Réutilise un secteur existant quand le rapprochement est pertinent.
3. Sinon crée un nouveau code (kebab-case court, sans accent), avec un label FR, un emoji, un kind (b2b|b2c|mixed).
4. CONTRAINTE ABSOLUE : le nombre TOTAL de secteurs (existants + nouveaux) ne doit JAMAIS dépasser {MAX_SECTORS}. Tu peux donc créer au maximum {max(available, 0)} nouveaux secteurs. Fusionne les catégories proches.
5. Utilise le code "autre" pour les catégories non catégorisables (ex "Autre / Non catégorisé").

Réponds UNIQUEMENT en JSON strict, sans texte autour :
{{"mapping": {{"<catégorie fichier>": "<code secteur>", ...}},
  "new_sectors": [{{"code": "...", "label": "...", "emoji": "...", "kind": "b2b|b2c|mixed"}}]}}"""

    raw = ""
    try:
        from llm_call import call_llm
        raw = call_llm(prompt, max_tokens=2000, temperature=0.0,
                       module="acquisition", action="csv-sector-match", site=site,
                       note=f"{len(values)} catégories")
    except Exception as e:
        print(f"[csv_import] DeepSeek sector-match KO: {e}")

    parsed = _parse_json_block(raw) or {}
    raw_map = parsed.get("mapping") or {}
    raw_new = parsed.get("new_sectors") or []

    # Index des nouveaux secteurs proposés
    new_by_code = {}
    for ns in raw_new:
        code = _slug(ns.get("code", ""))
        if code and code not in existing_codes:
            new_by_code[code] = {
                "code": code,
                "label": ns.get("label") or code.replace("-", " ").title(),
                "emoji": ns.get("emoji") or "🏷️",
                "kind": ns.get("kind") if ns.get("kind") in ("b2b", "b2c", "mixed") else "mixed",
            }

    # Mapping résolu : chaque valeur fichier → code (existant, nouveau, ou autre)
    sector_mapping: dict[str, str] = {}
    new_volume: dict[str, int] = {}
    for value, count in values:
        code = _slug(raw_map.get(value, ""))
        if code in existing_codes:
            sector_mapping[value] = code
        elif code in new_by_code:
            sector_mapping[value] = code
            new_volume[code] = new_volume.get(code, 0) + count
        else:
            sector_mapping[value] = "autre"

    # Plafond : on garde les nouveaux secteurs au plus gros volume
    kept = sorted(new_volume.keys(), key=lambda c: -new_volume[c])[:max(available, 0)]
    kept_set = set(kept)
    for value, code in list(sector_mapping.items()):
        if code in new_by_code and code not in kept_set:
            sector_mapping[value] = "autre"

    new_sectors = [new_by_code[c] for c in kept]
    return sector_mapping, new_sectors


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s


# ── analyze ────────────────────────────────────────────────────────────────---
def analyze(file_path: str, site: str, filename: str = "") -> dict:
    _cleanup_old(site)
    header, rows, sep, charset = _read_rows(file_path)
    if not header:
        return {"error": "empty_file"}
    if len(rows) > MAX_ROWS:
        return {"error": "too_many_rows", "total": len(rows), "max": MAX_ROWS}

    mapping, columns, unmapped = _build_mapping(header)
    field_to_idx = {f: i for i, f in mapping.items()}
    email_idx = field_to_idx.get("email")
    if email_idx is None:
        return {"error": "no_email_column", "columns": [c["name"] for c in columns]}
    sector_idx = field_to_idx.get("sector")

    # Valeurs distinctes du secteur (en mémoire, pas en DB)
    distinct_counts: dict[str, int] = {}
    if sector_idx is not None:
        for r in rows:
            if sector_idx < len(r):
                v = (r[sector_idx] or "").strip()
                if v:
                    distinct_counts[v] = distinct_counts.get(v, 0) + 1

    sector_mapping, new_sectors = _match_sectors(distinct_counts, site)

    # Pré-analyse dédup (1 requête pour tous les emails existants)
    existing_emails = _load_existing_emails()
    seen: set[str] = set()
    ok = new = update = ko = 0
    ko_samples: list[dict] = []
    for line_no, r in enumerate(rows, start=2):
        email = (r[email_idx].strip().lower() if email_idx < len(r) else "")
        if not _valid_email(email):
            ko += 1
            if len(ko_samples) < KO_SAMPLE_LIMIT:
                ko_samples.append({"line": line_no, "email": email or "(vide)", "reason": "email invalide"})
            continue
        if email in seen:
            ko += 1
            if len(ko_samples) < KO_SAMPLE_LIMIT:
                ko_samples.append({"line": line_no, "email": email, "reason": "doublon dans le fichier"})
            continue
        seen.add(email)
        ok += 1
        if email in existing_emails:
            update += 1
        else:
            new += 1

    # Échantillon de lignes mappées (pour aperçu UI)
    sample = []
    for r in rows[:SAMPLE_ROWS]:
        d = _row_to_data(r, mapping)
        if sector_idx is not None and sector_idx < len(r):
            raw_sec = (r[sector_idx] or "").strip()
            d["sector"] = sector_mapping.get(raw_sec, "autre")
        sample.append(d)

    # Récap secteurs pour la popup
    sector_summary = [
        {"value": v, "count": n, "code": sector_mapping.get(v, "autre")}
        for v, n in sorted(distinct_counts.items(), key=lambda kv: -kv[1])
    ]
    new_codes = {s["code"] for s in new_sectors}

    import_id = uuid.uuid4().hex[:12]
    meta = {
        "import_id": import_id,
        "site": site,
        "filename": filename or Path(file_path).name,
        "file_path": file_path,
        "separator": sep,
        "charset": charset,
        "total": len(rows),
        "mapping_by_idx": {str(k): v for k, v in mapping.items()},
        "sector_idx": sector_idx,
        "sector_mapping": sector_mapping,
        "new_sectors": new_sectors,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path = _imports_dir(site) / f"{import_id}.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    try:
        meta_path.chmod(0o600)
        Path(file_path).chmod(0o600)
    except Exception:
        pass

    return {
        "import_id": import_id,
        "filename": meta["filename"],
        "separator": sep,
        "charset": charset,
        "total": len(rows),
        "columns": columns,
        "unmapped_columns": unmapped,
        "ok_count": ok,
        "ko_count": ko,
        "new_count": new,
        "update_count": update,
        "ko_samples": ko_samples,
        "sector_summary": sector_summary,
        "new_sectors": new_sectors,
        "new_sector_codes": sorted(new_codes),
        "sectors_total_after": _sectors_total() + len(new_sectors),
        "max_sectors": _max_sectors(),
    }


def _load_existing_emails() -> set[str]:
    import contacts_pool_backend as pool
    c = pool._conn(read_only=True)
    try:
        rows = c.execute("SELECT email FROM contacts").fetchall()
    finally:
        c.close()
    return {(r[0] or "").strip().lower() for r in rows if r[0]}


def _sectors_total() -> int:
    from god_mode_backend import list_sectors
    return len(list_sectors())


def _max_sectors() -> int:
    from god_mode_backend import MAX_SECTORS
    return MAX_SECTORS


# ── commit (générateur SSE) ──────────────────────────────────────────────────-
def commit_import(import_id: str, site: str):
    """Générateur : yield des dicts d'events {step, pct, message, ...}."""
    meta_path = _imports_dir(site) / f"{import_id}.json"
    if not meta_path.exists():
        yield {"step": "error", "message": "import introuvable (expiré ?)"}
        return
    meta = json.loads(meta_path.read_text())

    yield {"step": "sectors", "pct": 0, "message": "Création des secteurs…"}
    from god_mode_backend import add_sector
    created_sectors = []
    for ns in meta.get("new_sectors", []):
        res = add_sector(ns["code"], ns.get("label", ""), ns.get("emoji", "🏷️"), ns.get("kind", "mixed"))
        if res.get("created"):
            created_sectors.append(ns["code"])
        elif res.get("rejected"):
            # Plafond atteint : on bascule les valeurs concernées vers "autre"
            for val, code in list(meta["sector_mapping"].items()):
                if code == ns["code"]:
                    meta["sector_mapping"][val] = "autre"

    mapping = {int(k): v for k, v in meta["mapping_by_idx"].items()}
    sector_idx = meta.get("sector_idx")
    sector_mapping = meta.get("sector_mapping", {})
    email_idx = next((i for i, f in mapping.items() if f == "email"), None)

    header, rows, _, _ = _read_rows(meta["file_path"], meta["separator"], meta["charset"])
    total = len(rows)

    import contacts_pool_backend as pool
    existing_emails = _load_existing_emails()
    seen: set[str] = set()
    added = updated = skipped = errors = 0

    c = pool._conn()
    try:
        for i, r in enumerate(rows, start=1):
            email = (r[email_idx].strip().lower() if email_idx is not None and email_idx < len(r) else "")
            if not _valid_email(email) or email in seen:
                skipped += 1
            else:
                seen.add(email)
                was_existing = email in existing_emails
                try:
                    data = _row_to_data(r, mapping)
                    data["email"] = email
                    if sector_idx is not None and sector_idx < len(r):
                        raw_sec = (r[sector_idx] or "").strip()
                        data["sectors"] = [sector_mapping.get(raw_sec, "autre")]
                    cid = pool.create_in_pool(data, primary_source="manual", conn=c)
                    if cid:
                        pool.upsert_site_history(cid, site, state="cold_email",
                                                 source="manual", by="csv_import", conn=c)
                        if was_existing:
                            updated += 1
                        else:
                            added += 1
                            existing_emails.add(email)
                    else:
                        errors += 1
                except Exception as e:
                    errors += 1
                    print(f"[csv_import commit] err ligne {i}: {e}")
            if i % 200 == 0 or i == total:
                yield {"step": "import", "pct": int(i / total * 100) if total else 100,
                       "message": f"Insertion {i} / {total}…",
                       "done": i, "total": total}
    finally:
        c.close()

    yield {"step": "done", "pct": 100, "added": added, "updated": updated,
           "skipped": skipped, "errors": errors, "total": total,
           "created_sectors": created_sectors}


# ── CLI smoke-test ─────────────────────────────────────────────────────────---
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: csv_import_backend.py <file.csv> <site> [--commit]")
        sys.exit(1)
    fp, st = sys.argv[1], sys.argv[2]
    res = analyze(fp, st, Path(fp).name)
    print(json.dumps({k: v for k, v in res.items() if k not in ("ko_samples",)},
                     ensure_ascii=False, indent=2)[:4000])
    if "--commit" in sys.argv:
        for ev in commit_import(res["import_id"], st):
            print(ev)
