#!/usr/bin/env python3
"""
Helper d'enrichissement via l'API Emelia (api.emelia.io).
- find-email : email nominatif d'une personne (payant, 1 crédit)
- find-phone : téléphone portable via URL LinkedIn (payant, 1 crédit)
- verify     : tester un email (peu coûteux)
- guess      : deviner l'email générique d'une entreprise (contact@/bonjour@/hello@, max 3)

Auth : variable d'env EMELIA_KEY (clé brute, sans 'Bearer').

⚠️ find-email et find-phone consomment des crédits Emelia. Le batch doit être
validé par l'utilisateur AVANT (voir SKILL.md), sauf opt-out explicite.

Réponses Emelia : enveloppe { success, data: { _id, status, email/phone, ... } }.
Statut "en cours" = "running". On poll data._id jusqu'à completed/failed.

Exemples :
  python emelia_enrich.py find-email "Jean Dupont" "ACME" --website acme.fr --country France
  python emelia_enrich.py find-phone "https://www.linkedin.com/in/jean-dupont"
  python emelia_enrich.py verify "contact@acme.fr"
  python emelia_enrich.py guess acme.fr
"""
import os, sys, json, time, ssl, urllib.request, urllib.error

BASE = os.environ.get("EMELIA_BASE", "https://api.emelia.io").rstrip("/")
KEY = os.environ.get("EMELIA_KEY", "")

IN_PROGRESS = {"running","pending","in_progress","processing","queued","created","started","waiting","scheduled"}
GENERIC_PREFIXES = ["contact", "bonjour", "hello"]  # max 3, dans cet ordre

def _ssl_context():
    """Certifi si dispo, sinon certifs système. Vérification jamais désactivée
    (la clé API transite dessus). Erreur 'CERTIFICATE_VERIFY_FAILED' → pip install certifi."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()

SSL_CTX = _ssl_context()

def _req(path, body=None, method="POST", _tries=0):
    if not KEY:
        sys.exit("ERREUR: variable d'env EMELIA_KEY manquante (clé API Emelia brute).")
    req = urllib.request.Request(BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 429 and _tries < 5:
            ra = e.headers.get("Retry-After")
            wait = int(ra) if (ra and str(ra).isdigit()) else 10
            print(f"  ⏳ 429 rate limit Emelia — pause {wait}s…", file=sys.stderr)
            time.sleep(wait)
            return _req(path, body, method, _tries + 1)
        sys.exit(f"HTTP {e.code} sur {path}: {e.read().decode(errors='replace')}")

def _unwrap(raw):
    """Enlève l'enveloppe { data: {...} }."""
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
        return raw["data"]
    return raw if isinstance(raw, dict) else {}

def _job_id(raw):
    d = _unwrap(raw)
    jid = d.get("_id") or d.get("jobId") or d.get("id")
    if not jid:
        sys.exit("Réponse Emelia sans job id: " + json.dumps(raw)[:200])
    return jid

def _poll(result_path, value_keys, timeout=90, interval=3):
    """Poll un job jusqu'à trouver une valeur ou un statut terminal."""
    waited = 0
    while waited < timeout:
        d = _unwrap(_req(result_path, method="GET"))
        val = next((d[k] for k in value_keys if isinstance(d.get(k), str) and d[k].strip()), None)
        status = str(d.get("status", "")).lower().strip()
        if val:
            return {"status": "completed", "value": val, "confidence": d.get("confidence"), "raw": d}
        if status and status not in IN_PROGRESS:
            return {"status": "failed", "value": None, "raw": d}
        time.sleep(interval); waited += interval
    return {"status": "timeout", "value": None}

def find_email(fullname, company, website=None, country=None):
    body = {"fullname": fullname, "companyName": company}
    if website: body["companyWebsite"] = website
    if country: body["country"] = country
    jid = _job_id(_req("/tools/find/email", body))
    return _poll(f"/tools/find/email/{jid}", ["email"])

def find_phone(linkedin_url):
    jid = _job_id(_req("/tools/find/phone", {"linkedinUrl": linkedin_url}))
    return _poll(f"/tools/find/phone/{jid}", ["phone", "phoneNumber"])

def verify(email):
    jid = _job_id(_req("/tools/verify/email", {"email": email}))
    # verify renvoie une qualification (valid/risky/invalid...) plutôt qu'une valeur trouvée
    waited = 0
    while waited < 60:
        d = _unwrap(_req(f"/tools/verify/email/{jid}", method="GET"))
        q = d.get("qualification") or d.get("result") or d.get("status_detail")
        status = str(d.get("status", "")).lower().strip()
        if q:
            return {"email": email, "qualification": str(q).lower(), "raw": d}
        if status and status not in IN_PROGRESS:
            return {"email": email, "qualification": str(d.get("status","unknown")).lower(), "raw": d}
        time.sleep(3); waited += 3
    return {"email": email, "qualification": "timeout"}

def guess_generic(domain):
    """Teste contact@/bonjour@/hello@ (max 3), renvoie le 1er valide."""
    domain = domain.lower().replace("https://","").replace("http://","").strip("/").split("/")[0]
    tried = []
    for prefix in GENERIC_PREFIXES:
        email = f"{prefix}@{domain}"
        res = verify(email)
        tried.append({"email": email, "qualification": res["qualification"]})
        if res["qualification"] in ("valid", "deliverable", "ok"):
            return {"found": email, "qualification": res["qualification"], "tried": tried}
    return {"found": None, "tried": tried}

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    a = sys.argv[2:]
    def opt(name):
        return a[a.index(name)+1] if name in a else None

    if cmd == "find-email":
        if len(a) < 2: sys.exit('Usage: find-email "Nom Complet" "Société" [--website d] [--country c]')
        print(json.dumps(find_email(a[0], a[1], opt("--website"), opt("--country")), ensure_ascii=False, indent=1))
    elif cmd == "find-phone":
        if len(a) < 1: sys.exit("Usage: find-phone <url_linkedin>")
        print(json.dumps(find_phone(a[0]), ensure_ascii=False, indent=1))
    elif cmd == "verify":
        if len(a) < 1: sys.exit("Usage: verify <email>")
        print(json.dumps(verify(a[0]), ensure_ascii=False, indent=1))
    elif cmd == "guess":
        if len(a) < 1: sys.exit("Usage: guess <domaine>")
        print(json.dumps(guess_generic(a[0]), ensure_ascii=False, indent=1))
    else:
        sys.exit("commande inconnue: find-email | find-phone | verify | guess")

if __name__ == "__main__":
    main()
