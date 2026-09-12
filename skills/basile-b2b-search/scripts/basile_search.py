#!/usr/bin/env python3
"""
Helper pour l'API Basile (api.basile.cc) — recherche, comptage, export (petit & gros volume).

Auth : variable d'env BASILE_KEY (clé brute, sans 'Bearer').
Débit : BASILE_DELAY (s entre appels, défaut 1.5) ou --delay. On espace volontairement
        les appels pour ne PAS marteler l'API (sinon le cloud va trop vite et sature
        l'API pour rien). Un gros export prend quelques minutes : c'est normal et voulu
        (dire à l'utilisateur de revenir dans 10-20 min).

Commandes :
  count   <people|companies> '<filtres_json>'
  find    <people|companies> '<filtres_json>' [--limit 100] [--token TOKEN]
  export  <people|companies> '<filtres_json>' [--out fichier.csv] [--delay 1.5] [--batch 1000]
          → bascule AUTOMATIQUEMENT en mode bulk (par lots) si total > 2000,
            pour éviter le timeout d'un /export géant.

Exemples :
  python basile_search.py count people '{"result_role":{"include":["CEO","PDG"]},"hide_legal_entities":true}'
  python basile_search.py export companies '{"naf_code":{"include":["41.x"]},"company_ceased":false}' --out btp.csv
  python basile_search.py export people '{"siren":{"include":["552100554"]}}' --out dirigeants.csv --delay 2
"""
import os, sys, json, time, ssl, urllib.request, urllib.error

BASE = os.environ.get("BASILE_BASE", "https://api.basile.cc")
KEY = os.environ.get("BASILE_KEY", "")
DEFAULT_DELAY = float(os.environ.get("BASILE_DELAY", "1.5"))
BULK_THRESHOLD = 2000          # au-delà → export par lots (évite le timeout d'un /export géant)
DEFAULT_BATCH = 1000           # taille d'un lot d'IDs pour l'export bulk

def _ssl_context():
    """Certifi si dispo, sinon certifs système. Vérification JAMAIS désactivée
    (la clé API transite dessus). Erreur 'CERTIFICATE_VERIFY_FAILED' → pip install certifi."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()

SSL_CTX = _ssl_context()

def _req(path, body=None, method="POST", raw=False, with_headers=False, timeout=150, _tries=0):
    if not KEY:
        sys.exit("ERREUR: variable d'env BASILE_KEY manquante (clé API brute).")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
        headers={"Authorization": KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
            payload = r.read()
            if with_headers:
                return payload, dict(r.headers)
            return payload if raw else json.loads(payload)
    except urllib.error.HTTPError as e:
        if e.code == 429 and _tries < 5:                       # rate limit : respecter Retry-After
            ra = e.headers.get("Retry-After")
            wait = int(ra) if (ra and str(ra).isdigit()) else 10
            print(f"  ⏳ 429 rate limit — pause {wait}s puis reprise…", file=sys.stderr)
            time.sleep(wait)
            return _req(path, body, method, raw, with_headers, timeout, _tries + 1)
        sys.exit(f"HTTP {e.code} sur {path}: {e.read().decode(errors='replace')}")
    except (urllib.error.URLError, TimeoutError) as e:
        if _tries < 3:
            print(f"  ⏳ réseau/timeout ({e}) — nouvelle tentative dans 5s…", file=sys.stderr)
            time.sleep(5)
            return _req(path, body, method, raw, with_headers, timeout, _tries + 1)
        sys.exit(f"Échec réseau sur {path}: {e}")

def count(kind, filters):
    """Total sans extraire (gratuit en quota)."""
    return _req(f"/{kind}/find", {"filters": filters, "limit": 1}).get("total", 0)

def find(kind, filters, limit=100, token=None):
    body = {"filters": filters, "limit": min(int(limit), 100)}
    if token:
        body["paginationToken"] = token
    return _req(f"/{kind}/find", body)

def collect_ids(kind, filters, delay):
    """Pagine /find (pages de 100) pour récupérer TOUS les IDs, avec délai entre pages."""
    ids, token, page = [], None, 0
    while True:
        res = find(kind, filters, 100, token)
        leads = res.get("leads", [])
        ids += [l["_id"] for l in leads if l.get("_id")]
        page += 1
        print(f"  page {page} — {len(ids):,} IDs collectés", file=sys.stderr)
        token = (res.get("pagination") or {}).get("nextToken")
        if not token or not leads:
            break
        time.sleep(delay)
    return ids

def _export_single(kind, filters, out):
    """Petit volume : un seul /export (serveur plafonné au max du plan)."""
    csv, headers = _req(f"/{kind}/export", {"filters": filters}, with_headers=True)
    with open(out, "wb") as f:
        f.write(csv)
    rows = max(0, csv.count(b"\n"))
    cap = headers.get("X-Export-Max-Rows")
    print(f"✅ Export écrit: {out} — ~{rows:,} lignes (limite/export du plan: {cap or 'n/a'})",
          file=sys.stderr)

def _export_bulk(kind, filters, out, batch, delay):
    """Gros volume : collecte des IDs puis export par lots, avec délai entre appels."""
    print(f"Phase 1/2 — collecte des IDs (pages de 100, délai {delay}s)…", file=sys.stderr)
    ids = collect_ids(kind, filters, delay)
    if not ids:
        sys.exit("Aucun ID collecté.")
    nb = len(ids)
    nlots = (nb + batch - 1) // batch
    print(f"Phase 2/2 — {nb:,} IDs → export par {nlots} lot(s) de {batch} (délai {delay}s)…",
          file=sys.stderr)
    first = True
    with open(out, "wb") as f:
        for k in range(nlots):
            chunk = ids[k*batch:(k+1)*batch]
            blob = _req(f"/{kind}/export", {"ids": chunk}, raw=True, timeout=240)
            if first:
                f.write(blob); first = False
            else:                                              # retirer l'en-tête des lots suivants
                nl = blob.find(b"\n")
                if nl >= 0 and blob[nl+1:]:
                    f.write(blob[nl+1:])
            if not blob.endswith(b"\n"):
                f.write(b"\n")
            print(f"  lot {k+1}/{nlots} ✓ (~{min((k+1)*batch, nb):,}/{nb:,})", file=sys.stderr)
            if k < nlots - 1:
                time.sleep(delay)
    print(f"✅ Export bulk terminé: {out} — {nb:,} contacts", file=sys.stderr)

def export(kind, filters, out, batch=DEFAULT_BATCH, delay=DEFAULT_DELAY):
    """Compte, puis choisit la bonne stratégie selon le volume."""
    total = count(kind, filters)
    if total == 0:
        sys.exit("Aucun résultat — rien à exporter.")
    if total <= BULK_THRESHOLD:
        print(f"Total {total:,} — export direct…", file=sys.stderr)
        _export_single(kind, filters, out)
    else:
        print(f"Total {total:,} (> {BULK_THRESHOLD:,}) — mode bulk pour éviter le timeout.",
              file=sys.stderr)
        _export_bulk(kind, filters, out, int(batch), float(delay))

def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    cmd, kind, filt = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
    if kind not in ("people", "companies"):
        sys.exit("kind doit être 'people' ou 'companies'")
    args = sys.argv[4:]
    def opt(name, default=None):
        return args[args.index(name)+1] if name in args else default

    if cmd == "count":
        print(json.dumps({"total": count(kind, filt)}))
    elif cmd == "find":
        print(json.dumps(find(kind, filt, opt("--limit", 100), opt("--token")), ensure_ascii=False, indent=1))
    elif cmd == "export":
        export(kind, filt, opt("--out", "export.csv"),
               int(opt("--batch", DEFAULT_BATCH)), float(opt("--delay", DEFAULT_DELAY)))
    else:
        sys.exit("commande inconnue: count | find | export")

if __name__ == "__main__":
    main()
