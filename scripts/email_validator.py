#!/usr/bin/env python3
"""
email_validator.py — Validation + scoring email pour cold email B2B France.

Implémente la spec EMAIL_VALIDATION_SCORING.md à la lettre.
6 étages : normalisation, regex syntax, hard rejects (TLD/role/disposable),
domain tier, MX check sur exotiques, scoring 0-100 + RGPD.

Point d'entrée unique : validate_and_score(email_raw, prospect) -> dict.

Dépendances : dnspython (`pip install dnspython`).
"""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

import dns.resolver

BASE_DIR = Path(__file__).parent.parent
DISPOSABLE_CSV = BASE_DIR / "data" / "email_jetable.csv"


# ──────────────────────────────────────────────────────────────────────────────
# Étage 1 — Normalisation
# ──────────────────────────────────────────────────────────────────────────────
def normalize_email(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip().lower()
    s = unicodedata.normalize("NFC", s)
    return s


# ──────────────────────────────────────────────────────────────────────────────
# Étage 2 — Regex syntaxique + anti-patterns
# ──────────────────────────────────────────────────────────────────────────────
EMAIL_REGEX = re.compile(
    r"^[a-z0-9._%-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,24}$"
)


def is_syntax_valid(email: str) -> bool:
    if not email or len(email) > 254:
        return False
    if ".." in email or email.startswith(".") or "@." in email:
        return False
    local, _, domain = email.partition("@")
    if not domain or len(local) > 64:
        return False
    return bool(EMAIL_REGEX.match(email))


def has_forbidden_patterns(email: str) -> tuple[bool, str]:
    if "+" in email:
        return True, "tag_alias_interdit"
    if email.count("@") != 1:
        return True, "multiple_at"
    local, _, domain = email.partition("@")
    if len(local) < 2:
        return True, "local_trop_court"
    if local.isdigit():
        return True, "local_numerique_pur"
    if re.search(r"(.)\1{4,}", local):
        return True, "repetition_anormale"
    if domain.count(".") > 4:
        return True, "trop_de_sous_domaines"
    if len(domain) < 4:
        return True, "domaine_trop_court"
    return False, ""


# ──────────────────────────────────────────────────────────────────────────────
# Étage 3.1 — TLDs / patterns INTERDITS (RGPD + secteur public)
# ──────────────────────────────────────────────────────────────────────────────
FORBIDDEN_TLD_PATTERNS = [
    # Gouvernement
    r"\.gouv\.fr$",
    r"\.gov$", r"\.gov\.[a-z]+$",
    r"\.mil$", r"\.mil\.[a-z]+$",
    # Education / recherche
    r"\.edu$", r"\.edu\.[a-z]+$",
    r"\.ac\.[a-z]+$",
    r"(?:\.|@)univ-[a-z0-9-]+\.fr$",
    r"\.scolarite\.[a-z]+$",
    r"@etudiant\.",
    r"@student\.",
    # Administrations FR
    r"@.*\.prefecture\.",
    r"@.*\.mairie-",
    r"@cnaf\.fr$", r"@caf\.fr$",
    r"@urssaf\.fr$", r"@impots\.gouv\.fr$",
    r"@pole-emploi\.fr$", r"@francetravail\.fr$",
    r"@cpam\b", r"@ameli\.fr$",
    # Santé publique
    r"\.aphp\.fr$", r"\.chu-[a-z]+\.fr$", r"@hopital-",
    # Internet infra
    r"@iana\.org$", r"@icann\.org$",
]


def is_forbidden_tld(email: str) -> tuple[bool, str]:
    for pat in FORBIDDEN_TLD_PATTERNS:
        if re.search(pat, email):
            return True, f"forbidden_tld:{pat}"
    return False, ""


# ──────────────────────────────────────────────────────────────────────────────
# Étage 3.2 — Adresses role-based
# ──────────────────────────────────────────────────────────────────────────────
FORBIDDEN_LOCAL_PARTS = {
    # Sécurité / abuse
    "abuse", "postmaster", "hostmaster", "webmaster", "admin", "administrator",
    "root", "security", "noc", "soc", "sysadmin", "sysop", "it", "informatique",
    "dns", "mx", "smtp", "imap", "pop", "ftp", "ssl", "spam", "phishing",
    # Automatique / no-reply
    "noreply", "no-reply", "donotreply", "do-not-reply", "notification",
    "notifications", "alerts", "alert", "alerte", "alertes", "system", "daemon",
    "mailer-daemon", "bounce", "bounces", "mailer", "auto", "autoreply",
    "automatique", "robot", "bot",
    # Support / SAV
    "support", "help", "helpdesk", "service", "services", "customercare",
    "customer-care", "customer-service", "sav", "client", "clients",
    "assistance", "reclamation", "reclamations", "litige", "litiges",
    # Sales / marketing / presse
    "sales", "marketing", "newsletter", "newsletters", "communications",
    "comms", "communication", "com", "media", "medias", "press", "presse",
    "rp", "publicrelations", "pub", "publicite",
    # RH / juridique
    "rh", "hr", "recruitment", "recrutement", "jobs", "career", "carriere",
    "candidature", "candidatures", "emploi", "stage", "stages",
    "legal", "juridique", "compliance", "privacy", "conformite", "cnil",
    "mentions", "mentions-legales",
    # Comptabilité / administratif — ne décident jamais, et polluent le taux de réponse
    "compta", "comptabilite", "comptable", "facture", "factures", "facturation",
    "billing", "invoice", "invoices", "finance", "finances", "tresorerie",
    "paiement", "paiements", "reglement", "adv", "achats", "fournisseurs",
    # rgpd, gdpr, dpo retirés ici -> traités comme honeypots (étage 3.4)
}

# ── Boîtes d'accueil génériques ────────────────────────────────────────────────
# Ajouté le 2026-08-21 sur décision de Camille : « toutes les adresses en contact@,
# dpo@, postmaster@ — nous n'en voulons pas. » Ces adresses arrivent dans une boîte
# partagée que personne ne s'approprie : elles gonflent le volume et écrasent le taux
# de réponse. Elles étaient jusqu'ici seulement pénalisées (-15 au score, cf.
# GENERIC_LOCALS) et partaient quand même en campagne.
GENERIC_INBOX = {
    "contact", "contacts", "info", "infos", "information", "informations",
    "hello", "hi", "bonjour", "salut", "welcome", "bienvenue",
    "accueil", "reception", "standard", "secretariat", "secretaire", "bureau",
    "mail", "email", "e-mail", "courrier", "message", "messages", "boite",
    "agence", "siege", "societe", "entreprise", "cabinet", "office",
    "direction", "gerance", "gestion", "administration", "general", "generale",
    "commercial", "commerciale", "commerciaux", "vente", "ventes", "devis",
}
FORBIDDEN_LOCAL_PARTS |= GENERIC_INBOX

# ── Adresses de gabarit ────────────────────────────────────────────────────────
# Trouvées le 2026-08-20 dans le repli « page contact » de Basile : des sites dont le
# modèle n'a jamais été rempli rendent `exemple@domaine.fr` ou `email@domaine.com`.
# Elles passaient avec un score de 75 — au-dessus d'un contact@ légitime.
PLACEHOLDER_LOCALS = {
    "exemple", "example", "votreemail", "votre-email", "votremail", "monemail",
    "mon-email", "votrenom", "votre-nom", "yourname", "your-name", "youremail",
    "your-email", "nom", "prenom", "nomprenom", "name", "firstname", "lastname",
    "utilisateur", "user", "username", "test", "tests", "essai", "sample",
    "demo", "exemple1", "xxx", "aaa", "abc", "azerty", "qwerty", "lorem",
}
PLACEHOLDER_DOMAINS = {
    "domaine.fr", "domaine.com", "domain.com", "domain.fr", "votredomaine.fr",
    "votredomaine.com", "mondomaine.fr", "mondomaine.com", "example.com",
    "example.fr", "example.org", "exemple.fr", "exemple.com", "votresite.fr",
    "votresite.com", "monsite.fr", "monsite.com", "site.com", "site.fr",
    "email.com", "mail.com", "adresse.fr", "societe.fr", "entreprise.fr",
    "nomdedomaine.fr", "test.com", "test.fr", "localhost", "domaine.tld",
}

FORBIDDEN_LOCAL_PREFIXES = ("noreply", "no-reply", "donotreply", "abuse")

# Suffixes numériques ou géographiques collés à une boîte générique : contact2@,
# contact33@, info-paris@ restent des boîtes génériques.
_SUFFIXE_NUM = re.compile(r"(\d+)$")


def is_role_based(email: str) -> tuple[bool, str]:
    local = email.split("@", 1)[0]
    canonical = local.replace(".", "").replace("-", "").replace("_", "")
    canonical_set = {p.replace("-", "").replace("_", "") for p in FORBIDDEN_LOCAL_PARTS}
    if canonical in canonical_set:
        return True, f"role_based:{canonical}"
    # contact2@, contact33@, info75@ : même boîte, un chiffre en plus. On ne coupe le
    # suffixe QUE si la racine est elle-même générique — jamais sur un nom propre
    # (marie2@, dupont33@ restent des personnes).
    racine = _SUFFIXE_NUM.sub("", canonical)
    if racine != canonical and racine in canonical_set:
        return True, f"role_based_num:{racine}"
    for prefix in FORBIDDEN_LOCAL_PREFIXES:
        if local.startswith(prefix):
            return True, f"role_based_prefix:{prefix}"
    return False, ""


def is_placeholder(email: str) -> tuple[bool, str]:
    """Adresse de gabarit non modifié (exemple@domaine.fr) : ni une personne, ni une
    société — un site web qu'on n'a jamais fini de remplir."""
    local, _, domain = email.partition("@")
    canonical = local.replace(".", "").replace("-", "").replace("_", "")
    if domain in PLACEHOLDER_DOMAINS:
        return True, f"placeholder_domain:{domain}"
    if canonical in {p.replace("-", "").replace("_", "") for p in PLACEHOLDER_LOCALS}:
        return True, f"placeholder_local:{canonical}"
    return False, ""


# ──────────────────────────────────────────────────────────────────────────────
# Étage 3.3 — Domaines jetables
# ──────────────────────────────────────────────────────────────────────────────
def load_disposable_domains(csv_path: Path = DISPOSABLE_CSV) -> set[str]:
    domains: set[str] = set()
    if not csv_path.exists():
        return domains
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) >= 2:
                d = row[1].strip().lower()
                if d and "." in d:
                    domains.add(d)
    return domains


DISPOSABLE_DOMAINS: set[str] = load_disposable_domains()

DISPOSABLE_PATTERNS = (
    "tempmail", "10minute", "throwaway", "trashmail", "guerrilla",
    "yopmail", "mailinator", "fakeinbox", "dispostable", "spambog",
)


def is_disposable(email: str) -> tuple[bool, str]:
    domain = email.split("@", 1)[1]
    if domain in DISPOSABLE_DOMAINS:
        return True, f"disposable:{domain}"
    for s in DISPOSABLE_PATTERNS:
        if s in domain:
            return True, f"disposable_pattern:{s}"
    return False, ""


# ──────────────────────────────────────────────────────────────────────────────
# Étage 4 — Tiers de domaines (whitelist FR + B2B + trash)
# ──────────────────────────────────────────────────────────────────────────────
TOP_FR_PERSONAL = {
    "gmail.com", "yahoo.fr", "yahoo.com", "hotmail.fr", "hotmail.com",
    "outlook.fr", "outlook.com", "orange.fr", "wanadoo.fr", "free.fr",
    "sfr.fr", "laposte.net", "live.fr", "live.com", "msn.com",
    "gmx.fr", "gmx.com", "icloud.com", "me.com", "mac.com",
    "bbox.fr", "neuf.fr", "club-internet.fr", "numericable.fr",
    "aliceadsl.fr", "voila.fr", "noos.fr",
    "proton.me", "protonmail.com", "tutanota.com",
    "fastmail.com", "zoho.com",
}

ACCEPTED_TLDS_B2B = {
    ".fr", ".com", ".eu", ".net", ".org",
    ".io", ".co", ".tech", ".biz",
    ".be", ".ch", ".lu", ".mc",
}

TRASH_TLDS = {
    ".xyz", ".top", ".club", ".online", ".site", ".shop", ".win", ".click",
    ".work", ".party", ".review", ".science", ".gq", ".tk", ".ml", ".cf",
    ".ga", ".loan", ".date", ".racing", ".accountant", ".cricket", ".faith",
    ".download", ".stream", ".trade", ".webcam",
}



def is_honeypot(email: str) -> tuple[bool, str]:
    """Étage 3.4 — détection honeypot/spam-trap/DPO/RGPD (drop immédiat).
    Substrings interdits dans l'email entier : voir HONEYPOT_TERMS.
    """
    for t in HONEYPOT_TERMS:
        if t in email:
            return True, f"honeypot:{t}"
    return False, ""


# ── Étage 3.5 — Concurrents nommés ────────────────────────────────────────────────
# Camille, 2026-08-29 : les agences marketing et web ne vendent PAS le même service que
# LeClientRoi. Les classer « concurrent » dans le catalogue des secteurs était une erreur
# de conception — elle interdisait deux secteurs entiers pour protéger contre DEUX
# sociétés. Les vrais concurrents sont deux plateformes de SMS marketing local :
#   · wellpack.fr  — « acquisition locale par SMS marketing », 37 M de profils adressables ;
#   · spot-hit.fr  — plateforme SMS / RCS / email / vocal multicanal.
# L'exclusion est donc NOMINATIVE, pas sectorielle. Elle vit ici, au seul point que les
# trois chemins de collecte traversent (Serper, Basile, acquisition manuelle) : une liste
# posée dans un seul collecteur laisserait les deux autres la contourner.
CONCURRENTS_DOMAINES = ("wellpack.fr", "spot-hit.fr")
# Le nom couvre ce que le domaine rate : une filiale, un domaine de campagne, ou le
# commercial de chez eux qui laisse une adresse Gmail. Écrit sans tiret ni espace pour
# attraper « Spot-Hit », « Spot Hit » et « spothit » d'une seule entrée.
# Frontières de mot obligatoires : « wellpack » est le début de « Wellpackaging », un
# fabricant d'emballages qui n'a rien à voir. Aplatir la chaîne sans frontière excluait
# cette société-là par ricochet. On normalise donc les séparateurs en ESPACES (et non en
# rien), ce qui garde les frontières, et on laisse la regex absorber « Spot-Hit », « Spot
# Hit » et « spothit » d'une seule alternative.
CONCURRENTS_NOMS = re.compile(r"\b(wellpack|spot ?hit)\b")


def is_concurrent(email: str, prospect: dict | None = None) -> tuple[bool, str]:
    """Étage 3.5 — concurrent direct de LeClientRoi : ne jamais démarcher.

    Contrôle le domaine, sous-domaines compris (`web-reseau.wellpack.fr` compte), puis —
    si la fiche est fournie — le nom de société et le site.
    """
    domaine = email.split("@", 1)[-1]
    for d in CONCURRENTS_DOMAINES:
        if domaine == d or domaine.endswith("." + d):
            return True, f"concurrent:{d}"
    if prospect:
        blob = " ".join(str(prospect.get(k) or "") for k in ("company_name", "website"))
        # Tout ce qui n'est ni lettre ni chiffre devient un espace : « Spot-Hit »,
        # « spot_hit » et « https://wellpack.fr/contact » se ramènent au même mot.
        aplati = re.sub(r"[^a-z0-9]+", " ", blob.lower()).strip()
        trouve = CONCURRENTS_NOMS.search(aplati)
        if trouve:
            return True, f"concurrent:{trouve.group(1).replace(' ', '')}"
    return False, ""


def domain_tier(email: str) -> str:
    """Retourne 'personal', 'b2b_clean', 'b2b_exotic'."""
    domain = email.split("@", 1)[1]
    if domain in TOP_FR_PERSONAL:
        return "personal"
    for tld in ACCEPTED_TLDS_B2B:
        if domain.endswith(tld):
            return "b2b_clean"
    return "b2b_exotic"


def is_trash_tld(email: str) -> bool:
    domain = email.split("@", 1)[1]
    return any(domain.endswith(t) for t in TRASH_TLDS)


# ──────────────────────────────────────────────────────────────────────────────
# Étage 5 — MX check (DNS only)
# ──────────────────────────────────────────────────────────────────────────────
_mx_cache: dict[str, bool] = {}


def has_mx_record(domain: str, timeout: float = 3.0) -> bool:
    if domain in _mx_cache:
        return _mx_cache[domain]
    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = timeout
        resolver.lifetime = timeout
        answers = resolver.resolve(domain, "MX")
        ok = len(answers) > 0
    except Exception:
        ok = False
    _mx_cache[domain] = ok
    return ok


# ──────────────────────────────────────────────────────────────────────────────
# RGPD blocker (avant scoring)
# ──────────────────────────────────────────────────────────────────────────────
# "basile" ajouté 2026-06-17 : les emails Basile proviennent du registre légal public
# (INSEE/RNCS) + Google My Business — sources publiques au sens RGPD, comme annuaire_public.
LICIT_SOURCES = {"serper_places", "annuaire_public", "site_web_pro", "basile"}


def rgpd_check(email: str, prospect: dict) -> tuple[bool, str]:
    tier = domain_tier(email)
    if tier == "personal" and not prospect.get("website"):
        return False, "rgpd_personal_no_pro_link"
    forbidden, reason = is_forbidden_tld(email)
    if forbidden:
        return False, "rgpd_secteur_public"
    source = prospect.get("source") or ""
    if source and source not in LICIT_SOURCES:
        return False, "rgpd_source_non_publique"
    return True, "ok"


# ──────────────────────────────────────────────────────────────────────────────
# Étage 6 — Scoring final
# ──────────────────────────────────────────────────────────────────────────────
# Substrings qui doivent IMMÉDIATEMENT drop l'email (honeypots + DPO/RGPD = ne JAMAIS contacter).
# Détection par substring dans l'email entier (pas juste le local).
HONEYPOT_TERMS = (
    # Spam traps / sécurité
    "spamtrap", "honeypot", "trap@", "abuse@", "spam@",
    "postmaster", "hostmaster", "mailer-daemon",
    # RGPD / DPO / vie privée : contacter ces adresses en cold email = plainte CNIL.
    "rgpd@", "dpo@", "gdpr@", "@rgpd.", "@dpo.",
    "donneespersonnelles", "donnees-personnelles", "donneeperso", "donnees-perso",
    "privacy@", "privacy.", "@privacy.",
    "vie-privee", "vieprivee",
    # Mentions légales / juridique / compliance
    "mentionslegales", "mentions-legales", "mention-legale",
    "juridique@", "@juridique.", "legal@", "@legal.", "compliance@", "compliance.",
    "conformite@", "@conformite.",
    # Autorités françaises / RGPD officiel
    "cnil@", "@cnil.", "cnil-",
    # Anonymisation / droits utilisateurs
    "anonymisation", "droits-rgpd", "droits-personnels", "exercice-droits",
)
GENERIC_LOCALS = {"contact", "info", "hello", "bonjour", "accueil"}


def score_email(email: str, prospect: dict) -> tuple[int, list[str]]:
    score = 50
    reasons: list[str] = []
    local, _, domain = email.partition("@")

    # Local part
    if "." in local and len(local.split(".")) == 2:
        score += 25
        reasons.append("+25 pattern prenom.nom")
    elif local in GENERIC_LOCALS:
        # generic local part : on saute le bonus 'simple' et on applique le malus
        score -= 15
        reasons.append(f"-15 generic_local:{local}")
    elif re.match(r"^[a-z]+$", local) and 3 <= len(local) <= 12:
        score += 10
        reasons.append("+10 local simple")
    elif re.search(r"\d{3,}", local):
        score -= 10
        reasons.append("-10 chiffres dans local")

    # Domain tier
    tier = domain_tier(email)
    if tier == "personal":
        score -= 10
        reasons.append("-10 perso (gmail/orange/etc)")
    elif tier == "b2b_clean":
        score += 15
        reasons.append("+15 domaine b2b standard")
    elif tier == "b2b_exotic":
        score -= 5
        reasons.append("-5 TLD exotique")

    # Cohérence email/website
    website = (prospect.get("website") or "").lower()
    if website:
        website_domain = re.sub(r"^(https?://)?(www\.)?", "", website).split("/")[0]
        if website_domain and website_domain == domain:
            score += 20
            reasons.append("+20 email domain match website")

    # Honeypot detection est désormais à l'étage 3.4 (hard reject), pas ici.
    return max(0, min(100, score)), reasons


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline complet
# ──────────────────────────────────────────────────────────────────────────────
def validate_and_score(email_raw: str, prospect: dict) -> dict:
    """
    Pipeline unique — appeler AVANT add_prospect() ou push_emelia().

    Returns:
        {
          "email":    str (normalisé),
          "valid":    bool,
          "score":    int 0-100,
          "decision": "push" | "queue" | "drop",
          "reasons":  list[str],
        }
    """
    email = normalize_email(email_raw)
    reasons: list[str] = []

    # Étage 2 — Syntax
    if not is_syntax_valid(email):
        return {"email": email, "valid": False, "score": 0,
                "decision": "drop", "reasons": ["syntax_invalid"]}
    rejected, reason = has_forbidden_patterns(email)
    if rejected:
        return {"email": email, "valid": False, "score": 0,
                "decision": "drop", "reasons": [reason]}

    # Étage 3 — Hard rejects (dans l'ordre du moins cher au plus cher)
    for check in (is_honeypot, is_forbidden_tld, is_role_based, is_placeholder,
                  is_disposable):
        rejected, reason = check(email)
        if rejected:
            return {"email": email, "valid": False, "score": 0,
                    "decision": "drop", "reasons": [reason]}
    rejected, reason = is_concurrent(email, prospect)
    if rejected:
        return {"email": email, "valid": False, "score": 0,
                "decision": "drop", "reasons": [reason]}
    if is_trash_tld(email):
        return {"email": email, "valid": False, "score": 0,
                "decision": "drop", "reasons": ["trash_tld"]}

    # Étage 5 — MX check sur tout sauf personal (FAIs grand public toujours valides).
    # Spec §12 demande MX check sur .com (b2b_clean) aussi, donc on ne saute aucun étage.
    if domain_tier(email) != "personal":
        if not has_mx_record(email.split("@", 1)[1]):
            return {"email": email, "valid": False, "score": 0,
                    "decision": "drop", "reasons": ["no_mx"]}

    # RGPD blocker
    ok, reason = rgpd_check(email, prospect)
    if not ok:
        return {"email": email, "valid": False, "score": 0,
                "decision": "drop", "reasons": [reason]}

    # Étage 6 — Scoring
    score, score_reasons = score_email(email, prospect)
    reasons.extend(score_reasons)

    # Tout ce qui passe les hard rejects va à Mailnjoy — y compris contact@ sur domaine B2B.
    # Mailnjoy est la vraie barrière qualité. On ne droppe plus par score soft.
    decision = "push"

    return {"email": email, "valid": True, "score": score,
            "decision": decision, "reasons": reasons}


# ──────────────────────────────────────────────────────────────────────────────
# CLI / tests rapides
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        e = sys.argv[1]
        prospect = {
            "source":  "serper_places",
            "website": sys.argv[2] if len(sys.argv) > 2 else "",
        }
        print(json.dumps(validate_and_score(e, prospect), indent=2, ensure_ascii=False))
    else:
        # Cas de test §12 du spec
        TESTS = [
            ("jean.dupont@restaurant-pickles.fr",   {"source": "serper_places", "website": "restaurant-pickles.fr"}, "push"),
            ("m.bernard@cabinet-bernard.com",       {"source": "serper_places"}, "push"),
            ("contact@boulangerie-martin.fr",       {"source": "serper_places"}, "queue"),
            ("test@10minutemail.com",               {"source": "serper_places"}, "drop"),
            ("admin@orange.fr",                     {"source": "serper_places", "website": "x.fr"}, "drop"),
            ("jean.dupont+spam@gmail.com",          {"source": "serper_places", "website": "x.fr"}, "drop"),
            ("contact@cnaf.fr",                     {"source": "serper_places"}, "drop"),
            ("contact@univ-paris1.fr",              {"source": "serper_places"}, "drop"),
            ("support@nant-artisans.com",           {"source": "serper_places"}, "drop"),
            ("something@whatever.xyz",              {"source": "serper_places"}, "drop"),
            ("fake@yaho-fake-domain-xyz1234.com",   {"source": "serper_places"}, "drop"),
            ("abc@@gmail.com",                      {"source": "serper_places"}, "drop"),
            ("jeandupont1985@gmail.com",            {"source": "serper_places", "website": "x.fr"}, "queue"),
            ("info@some-domain.fr",                 {"source": "serper_places"}, "queue"),
        ]
        print(f"{'EMAIL':<40s} | {'EXP':<6s} | {'GOT':<6s} | {'SCORE':<5s} | REASONS")
        print("-" * 120)
        ok_count = 0
        for email, prospect, expected in TESTS:
            res = validate_and_score(email, prospect)
            mark = "✓" if res["decision"] == expected else "✗"
            if res["decision"] == expected:
                ok_count += 1
            print(f"{email:<40s} | {expected:<6s} | {res['decision']:<6s} | {res['score']:<5d} | {mark} {','.join(res['reasons'])[:60]}")
        print(f"\n{ok_count}/{len(TESTS)} tests passed")
