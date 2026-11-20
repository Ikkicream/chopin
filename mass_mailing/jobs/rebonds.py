#!/usr/bin/env python3
"""mass_mailing/jobs/rebonds.py — rebonds (soft / hard) et liste noire globale (Camille, 30/09/2026).

Sweego a signalé « beaucoup trop de hard bounces ». Ce que l'analyse du 30/09 a montré :
- son compteur « hardbounce » mélange de VRAIES adresses mortes (550 5.1.1…) et des refus
  TEMPORAIRES dus à notre IP (Free « 451 too many errors from your ip », Microsoft « 451 4.7.652 ») ;
- l'essentiel du volume vient d'un AUTRE émetteur qui partage le compte Sweego et le domaine
  news.leclientroi.email : la plateforme LeClientRoi (serveur 188.245.184.71, lcr@news.leclientroi.email),
  dont les listes ne passent pas par Mailnjoy.

On relit donc les logs Sweego de TOUT le compte, on classe chaque échec, et on range l'adresse dans
la liste noire globale de Mass Email (`suppressions`, scope global) quand c'est l'ADRESSE qui est en cause :

    hard       adresse morte : inconnue, désactivée, bloquée pour inactivité, domaine invalide,
               déjà dans la liste de suppression de Sweego           → reason 'hard_bounce'
    soft       problème du destinataire, temporaire : boîte pleine, boîte inactive (4.2.1)
                                                                      → reason 'soft_bounce'
    expediteur refus lié à NOTRE réputation ou à notre débit (421/451 « too many », 4.7.x,
               spam, politique) : l'adresse est bonne               → JAMAIS en liste noire
    technique  erreur de notre côté (étiquette vide, réseau)          → ignoré

Une adresse déjà en liste pour une raison plus forte (plainte, désinscription, hard) n'est jamais
rétrogradée ; une adresse en « soft » passe en « hard » si un rebond définitif arrive ensuite.
"""
from __future__ import annotations

import hashlib
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import pg, sweego  # noqa: E402
from infra.adresses import normaliser  # noqa: E402

NOTRE_IP_CONNEXION = "204.168.186.159"      # serveur de Mass Email (appels API Sweego)
IP_PLATEFORME_LCR = "188.245.184.71"        # plateforme LeClientRoi (même compte Sweego)
DOMAINES_ENVOI = ("news.leclientroi.email", "leclientroi.com", "swg-srv.net")

SCHEMA = """
CREATE TABLE IF NOT EXISTS rebonds (
    swg_uid       TEXT        PRIMARY KEY,
    email_hash    TEXT        NOT NULL,
    email         TEXT        NOT NULL,
    domaine       TEXT        NOT NULL,
    famille       TEXT        NOT NULL,     -- hard | soft | expediteur | technique
    cause         TEXT        NOT NULL,
    code          TEXT,
    texte         TEXT,
    type_sweego   TEXT,                     -- l'étiquette de Sweego (hard/soft), pour comparaison
    origine       TEXT        NOT NULL,     -- mass_email | plateforme_lcr | autre
    campagne      TEXT,
    at            TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS rebonds_hash_idx ON rebonds (email_hash);
CREATE INDEX IF NOT EXISTS rebonds_campagne_idx ON rebonds (campagne)
"""
# Contrainte des motifs de suppression élargie à 'soft_bounce'. Faite UNE fois (revue du 30/09 : la
# refaire à chaque appel verrouillait `suppressions` en exclusif, et un GET de l'accueil la déclenchait).
CONTRAINTE = """
ALTER TABLE suppressions DROP CONSTRAINT IF EXISTS suppressions_reason_check;
ALTER TABLE suppressions ADD CONSTRAINT suppressions_reason_check CHECK (reason = ANY (ARRAY[
    'unsubscribe', 'hard_bounce', 'soft_bounce', 'complaint', 'manual', 'import', 'provider']))
"""
_schema_fait = False

# Du plus fort au plus faible : une raison n'est jamais remplacée par une plus faible.
FORCE = {"complaint": 5, "unsubscribe": 4, "manual": 4, "hard_bounce": 3, "provider": 2, "import": 2, "soft_bounce": 1}


def appliquer_schema() -> None:
    """Idempotent et léger : tables et index en IF NOT EXISTS ; la contrainte n'est touchée que si
    elle ne connaît pas encore 'soft_bounce'. À appeler depuis le worker, jamais depuis un GET."""
    global _schema_fait
    if _schema_fait:
        return
    for b in SCHEMA.split(";"):
        if b.strip():
            pg.ecrire(b)
    defn = pg.valeur("""SELECT pg_get_constraintdef(oid) FROM pg_constraint
                         WHERE conrelid = 'suppressions'::regclass AND conname = 'suppressions_reason_check'""") or ""
    if "soft_bounce" not in defn:
        with pg.connexion() as cur:          # une seule transaction : jamais de fenêtre sans contrainte
            cur.execute(CONTRAINTE)
    _schema_fait = True


# ── Classement (fonction pure, testée) ─────────────────────────────────────────

_R = [
    ("technique", "erreur_technique", r"wrong tag value|httpsconnection|network is unreachable|network error|"
                                      r"connection timed out|connection refused|rejected\[network\]"),
    ("hard", "deja_supprimee", r"drop\[suppressed\]|found from suppression list"),
    # Refus liés à l'expéditeur AVANT les motifs « adresse » : « too many errors » n'est pas une adresse morte.
    ("expediteur", "trop_d_erreurs_ip", r"too many errors"),
    ("expediteur", "service_refuse", r"service refuse|ofr\d+_\d+|socket is already destroyed"),
    ("expediteur", "limite_debit", r"4\.7\.65\d|exceeded the maximum number of connections|too many (connections|messages)|rate limit|throttl|try again later|\bts0\d"),
    ("hard", "bloquee_inactivite", r"blocked due to inactivity|5\.2\.1"),
    ("hard", "desactivee", r"mailbox is disabled|554\.30|account (is )?disabled|deactivated|suspended"),
    ("soft", "boite_inactive", r"4\.2\.1|mailbox is inactive"),
    ("soft", "boite_pleine", r"over quota|out of storage|mailbox (is )?full|quota exceeded|4\.2\.2|5\.2\.2"),
    ("hard", "domaine_invalide", r"failed to resolve|dns error|5\.1\.2|domain (not found|does not exist)|no mx|host not found|unrouteable|nxdomain"),
    ("hard", "inconnue", r"5\.1\.1|user unknown|does not exist|no such user|mailbox not found|mailbox unavailable|"
                         r"unknown (user|recipient)|5\.1\.0|no such person|address rejected: (user unknown|address does not exist)|invalid recipient|5\.5\.0|5\.4\.1"),
    ("expediteur", "politique_spam", r"spam|blocked|blacklist|reputation|policy|5\.7\.\d|denied"),
]


def classer(texte: str | None, code: str | None = None, type_sweego: str | None = None) -> tuple[str, str]:
    """(famille, cause) d'un échec Sweego à partir de sa réponse SMTP."""
    # Les adresses IP du journal (mx=…[1.2.3.4], src=…) ne doivent pas passer pour des codes « 5.1.1 »
    # (revue du 30/09).
    t = _IP.sub(" ", f"{texte or ''} {code or ''}".lower())
    base = _code_base(texte, code)
    for famille, cause, motif in _R:
        if re.search(motif, t):
            # Garde générale : une réponse 4xx n'est JAMAIS une adresse morte.
            if famille == "hard" and base.startswith("4") and cause != "deja_supprimee":
                return "expediteur" if cause not in ("bloquee_inactivite",) else "soft", "temporaire_" + cause
            return famille, cause
    c = (code or "").strip()
    if c.startswith("5"):
        return "hard", "definitif_autre"
    if c.startswith("4"):
        return "expediteur", "temporaire_autre"
    return ("hard", "definitif_autre") if type_sweego == "hard" else ("soft", "temporaire_autre")


_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def _code_base(texte: str | None, code: str | None) -> str:
    """Code SMTP de base (« 550 », « 451 »…) : d'abord `code`, sinon la dernière réponse entre parenthèses."""
    m = re.match(r"\s*([245]\d\d)", code or "")
    if m:
        return m.group(1)
    m = re.findall(r"\(([245]\d\d)[ -]", texte or "")
    return m[-1] if m else ""


def origine_de(connection_ip: str | None, campaign_id: str | None) -> str:
    if str(campaign_id or "").startswith("mm-") or connection_ip == NOTRE_IP_CONNEXION:
        return "mass_email"
    if connection_ip == IP_PLATEFORME_LCR:
        return "plateforme_lcr"
    return "autre"


def _texte(x: dict) -> str:
    return (x.get("rejected") or x.get("deferred") or "")[-600:]


# ── Import des logs Sweego ────────────────────────────────────────────────────

def _logs(debut: str, fin: str) -> list[dict]:
    out = []
    for dom in DOMAINES_ENVOI:
        off = 0
        while True:
            r = requests.post(sweego.SWEEGO_URL + "/logs", headers=sweego._headers(), timeout=180, json={
                "channel": "email", "domains": [dom], "status": ["undelivered"],
                "start_date": debut, "end_date": fin, "size": 500, "offset": off})
            if r.status_code == 422:      # domaine sans aucun log sur la période : Sweego répond 422
                break
            r.raise_for_status()
            res = r.json().get("result") or []
            out += res
            if len(res) < 500:
                break
            off += 500
    return out


def importer(jours: int = 3, debut: str | None = None) -> dict:
    """Relit les échecs Sweego (tout le compte), les classe, remplit `rebonds` et la liste noire globale."""
    appliquer_schema()
    debut = debut or (date.today() - timedelta(days=jours)).isoformat()
    fin = (date.today() + timedelta(days=1)).isoformat()
    compte = {"echecs": 0, "hard": 0, "soft": 0, "expediteur": 0, "technique": 0}
    for x in _logs(debut, fin):
        email = normaliser(x.get("email_to"))
        if not email or not x.get("swg_uid"):
            continue
        texte = _texte(x)
        code = str(x.get("email_state") or "")
        famille, cause = classer(texte, code, x.get("bounce_type"))
        compte["echecs"] += 1
        compte[famille] += 1
        pg.ecrire("""INSERT INTO rebonds (swg_uid, email_hash, email, domaine, famille, cause, code, texte, type_sweego, origine, campagne, at)
                     VALUES (%(u)s, %(h)s, %(e)s, %(d)s, %(f)s, %(c)s, %(k)s, %(t)s, %(ts)s, %(o)s, %(cp)s, %(at)s)
                     ON CONFLICT (swg_uid) DO UPDATE SET famille = EXCLUDED.famille, cause = EXCLUDED.cause,
                            code = EXCLUDED.code, texte = EXCLUDED.texte""",
                  {"u": x["swg_uid"], "h": hashlib.sha256(email.encode()).hexdigest(), "e": email,
                   "d": email.split("@")[1], "f": famille, "c": cause, "k": code[:20], "t": texte,
                   "ts": x.get("bounce_type"), "o": origine_de(x.get("connection_ip"), x.get("campaign_id")),
                   "cp": str(x.get("campaign_id") or "")[:60], "at": x.get("email_last_update") or x.get("email_creation")})
    compte["liste_noire"] = alimenter_liste_noire()
    return compte


def alimenter_liste_noire() -> dict:
    """hard → 'hard_bounce', soft → 'soft_bounce', dans `suppressions` (scope global).
    Ne rétrograde jamais une raison plus forte ; un soft devient hard si un hard arrive."""
    n_hard = pg.ecrire("""
        INSERT INTO suppressions (email_hash, email_normalized, reason, source, scope, metadata, occurred_at)
        SELECT DISTINCT ON (email_hash) email_hash, email, 'hard_bounce', 'sweego_logs', 'global',
               jsonb_build_object('cause', cause, 'code', code, 'origine', origine, 'swg_uid', swg_uid), COALESCE(at, now())
          FROM rebonds WHERE famille = 'hard' ORDER BY email_hash, at DESC NULLS LAST
        ON CONFLICT (email_hash, scope, COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid))
        DO UPDATE SET reason = 'hard_bounce', metadata = EXCLUDED.metadata, occurred_at = EXCLUDED.occurred_at
              WHERE suppressions.reason = 'soft_bounce'""")
    n_soft = pg.ecrire("""
        INSERT INTO suppressions (email_hash, email_normalized, reason, source, scope, metadata, occurred_at)
        SELECT DISTINCT ON (email_hash) email_hash, email, 'soft_bounce', 'sweego_logs', 'global',
               jsonb_build_object('cause', cause, 'code', code, 'origine', origine, 'swg_uid', swg_uid), COALESCE(at, now())
          FROM rebonds WHERE famille = 'soft' ORDER BY email_hash, at DESC NULLS LAST
        ON CONFLICT (email_hash, scope, COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid))
        DO NOTHING""")
    # Retrait de ce que nous avions posé à tort : une ligne « sweego_logs » que plus aucun rebond ne
    # justifie (classifieur corrigé, revue du 30/09). Ne touche jamais une plainte ni une désinscription.
    n_retires = pg.ecrire("""
        DELETE FROM suppressions s WHERE s.source = 'sweego_logs' AND s.scope = 'global'
           AND ((s.reason = 'hard_bounce' AND NOT EXISTS (SELECT 1 FROM rebonds b WHERE b.email_hash = s.email_hash AND b.famille = 'hard'))
             OR (s.reason = 'soft_bounce' AND NOT EXISTS (SELECT 1 FROM rebonds b WHERE b.email_hash = s.email_hash AND b.famille IN ('soft', 'hard'))))""")
    return {"hard": n_hard, "soft": n_soft, "retires": n_retires}


def reclasser() -> int:
    """Repasse le classifieur actuel sur tous les rebonds déjà stockés (après une correction des règles)."""
    n = 0
    for x in pg.lignes("SELECT swg_uid, texte, code, type_sweego, famille, cause FROM rebonds"):
        f, c = classer(x["texte"], x["code"], x["type_sweego"])
        if (f, c) != (x["famille"], x["cause"]):
            n += pg.ecrire("UPDATE rebonds SET famille = %(f)s, cause = %(c)s WHERE swg_uid = %(u)s",
                           {"f": f, "c": c, "u": x["swg_uid"]})
    return n


# ── Statistiques par campagne (écran) ──────────────────────────────────────────

def stats_campagne(campaign_id: str) -> dict:
    lignes = pg.lignes("""SELECT famille, cause, count(DISTINCT email_hash) AS n FROM rebonds
                           WHERE campagne = %(c)s GROUP BY 1, 2""", {"c": f"mm-{campaign_id}"})
    out = {"hard": 0, "soft": 0, "expediteur": 0, "causes": {}}
    for x in lignes:
        if x["famille"] in out:
            out[x["famille"]] += x["n"]
        out["causes"][x["cause"]] = out["causes"].get(x["cause"], 0) + x["n"]
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(importer(debut=sys.argv[1] if len(sys.argv) > 1 else "2026-06-01"), ensure_ascii=False))
