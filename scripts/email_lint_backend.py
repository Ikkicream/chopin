"""
Lint / validation d'emails HTML via @emailens/cli (commandes `lint` + `analyze`).

- 100 % LOCAL sur le VPS : aucune donnée du contenu ne sort (moteur @emailens/engine + data caniemail).
  On n'utilise PAS `emailens fix` (qui enverrait le HTML à Claude/Anthropic) -> conforme RGPD.
- run_lint(html) -> résultat normalisé { ok, global_score, per_client, issues[], counts, blocking, tested_at }
- save_result / get_result / get_all_results -> table `newsletter_lint` (god_mode.duckdb).

Schéma réel des sorties emailens (v0.3.4 / engine 0.8.6) :
  lint --json    -> { files:[{file, issues:[{severity,category,rule,message}], errors, warnings}],
                      totalErrors, totalWarnings }
  analyze --json -> { overallScore:int, scores:{<client>:{score,errors,warnings,info}}, warnings:[...] }
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"

EMAILENS_BIN = os.environ.get("EMAILENS_BIN", "/home/autoblog/.npm-global/bin/emailens")
SPAM_THRESHOLD = int(os.environ.get("EMAILENS_SPAM_THRESHOLD", "5"))
TIMEOUT_S = int(os.environ.get("EMAILENS_TIMEOUT_S", "120"))

# Une ERREUR dans une de ces catégories BLOQUE l'envoi. Les autres erreurs (ex. accessibilité
# "low-contrast", souvent bruyantes sur des fonds dégradés) restent À CORRIGER mais non bloquantes.
BLOCKING_CATEGORIES = ("templatevars", "links", "html", "spam")

# Variables de fusion légitimes : non résolues au lint (remplies à l'envoi par le canal —
# Emelia OU Maildoso/cold email). On ne les compte donc PAS comme erreurs -> le check
# templateVars ne bloque que sur de VRAIES variables inconnues (faute de frappe).
ALLOWED_VARS = {
    # Emelia
    "firstname", "lastname", "unsubscribe_link", "field1", "field2", "field3", "field4", "field5",
    # Cold email maison / Maildoso (cf. maildoso_backend._apply_tokens)
    "prenom", "nom", "entreprise", "societe", "company", "ville", "city",
    "expediteur_prenom", "expediteur_nom", "unsubscribe",
}

# Les marqueurs du CONDITIONNEL ne sont pas des variables : `{{si prenom}}`, `{{sinon}}` et
# `{{/si}}` sont développés par `qualite_message.conditionnel()` avant l'envoi, et ont donc
# disparu quand le message part. Sans cette exception, le lint les prenait pour des
# variables inconnues et BLOQUAIT le lot — c'est arrivé le 2026-08-26 à la campagne
# « Agent immobilier, loi cazenave », arrêtée en cours d'envoi.
MOTS_CONDITION = {"si", "sinon", "/si"}
_CONDITION_RE = re.compile(r"\{\{\s*(?:si\s+[A-Za-z0-9_]+|sinon|/si)\s*\}\}")
_VAR_RE = re.compile(r"\{+\s*([A-Za-z0-9_]+)\s*\}+")

# Un PRÉ-EN-TÊTE est délibérément invisible : c'est le texte que la boîte de réception
# affiche à côté de l'objet, et qui ne doit PAS réapparaître dans le corps. On l'obtient
# en empilant `display:none`, `font-size:0`, `max-height:0` et `opacity:0` — d'où un
# contraste de 1.0:1 que le lint signale à chaque passage (« low contrast ratio 1.0:1 »).
# Ce bruit a fait perdre du temps le 2026-08-26 : dans le rapport d'une campagne bloquée,
# il apparaissait en tête et donnait l'impression d'être la cause du blocage — alors que
# le coupable était `{{si prenom}}`. La catégorie `accessibility` n'a jamais été bloquante
# (cf. BLOCKING_CATEGORIES), on retire donc seulement le bruit, pas une protection.
_PREHEADER_RE = re.compile(
    r"(display\s*:\s*none|font-size\s*:\s*0|max-height\s*:\s*0|opacity\s*:\s*0)",
    re.I,
)
# 1.0:1 = premier plan et fond STRICTEMENT identiques, donc texte invisible. Un vrai défaut
# de lisibilité (gris clair sur blanc) donne 2:1 ou 3:1 et reste signalé.
_CONTRASTE_NUL_RE = re.compile(r"\b1(?:[.,]0+)?\s*:\s*1\b")


def _conn():
    # `duck_ouverture.ouvrir` et non `duckdb.connect` : ce module est dans le CHEMIN DU
    # DISPATCH — résoudre le message, le contrôler, lire les modèles. Une ouverture directe
    # échoue au premier verrou tenu par un scrape, et le lot entier est refusé : c'est ce
    # qui a fait échouer la campagne du 2026-08-27 à 10h30, « Could not set lock on file
    # god_mode.duckdb ». Ces lectures ne sont pas des écritures de garantie — elles peuvent
    # attendre une seconde et demie, et se contenter d'un accès en lecture seule.
    import duck_ouverture
    return duck_ouverture.ouvrir(GOD_DB)


def _ensure_table():
    c = _conn()
    try:
        c.execute(
            """CREATE TABLE IF NOT EXISTS newsletter_lint (
                site_code    VARCHAR,
                target_type  VARCHAR,   -- 'structure' | 'version'
                target_ref   VARCHAR,   -- nom de structure (stem) ou id de version
                global_score INTEGER,
                n_errors     INTEGER,
                n_warnings   INTEGER,
                blocking     BOOLEAN,
                result_json  VARCHAR,
                tested_at    TIMESTAMP,
                tested_by    VARCHAR,
                PRIMARY KEY (site_code, target_type, target_ref)
            )"""
        )
    finally:
        c.close()


def _run(cmd: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
    return p.returncode, p.stdout, p.stderr


def _drop_preheader_contrast(issues: list[dict], html: str) -> list[dict]:
    """Retire l'alerte de contraste nul quand le message porte un pré-en-tête caché.

    `emailens` ne dit pas QUEL élément est en cause : on ne peut donc pas viser le bloc.
    Deux conditions ensemble suffisent à conclure sans risque — le HTML contient bien un
    bloc masqué, et le contraste signalé vaut exactement 1.0:1 (invisible, pas « peu
    lisible »). Si l'une manque, l'alerte est conservée.
    """
    if not _PREHEADER_RE.search(html or ""):
        return issues
    return [
        it for it in issues
        if not ((it.get("rule") or "").lower() == "low-contrast"
                and _CONTRASTE_NUL_RE.search(it.get("message") or ""))
    ]


def _drop_known_vars(issues: list[dict]) -> list[dict]:
    """Retire les alertes « variable non résolue » qui pointent une variable Emelia légitime."""
    out = []
    for it in issues:
        is_var = ("templatevar" in (it.get("category") or "").lower()
                  or "variable" in (it.get("rule") or "").lower())
        if is_var:
            msg = it.get("message", "") or ""
            # Un marqueur de conditionnel n'est pas une variable : il aura disparu du
            # message au moment de l'envoi.
            if _CONDITION_RE.search(msg):
                continue
            m = _VAR_RE.search(msg)
            if m and m.group(1).lower() in (ALLOWED_VARS | MOTS_CONDITION):
                continue  # variable de fusion attendue, ou mot-clé du conditionnel
        out.append(it)
    return out


def _is_blocking(issues: list[dict]) -> bool:
    # Bloque uniquement sur une ERREUR dans une catégorie critique : liens cassés (links), variable
    # inconnue (templatevars), html cassé, spam avéré. Les findings spam de moindre gravité
    # (caps-ratio…) restent de simples warnings. NB : le tag <link> (CSS externe ignoré par Gmail)
    # a une catégorie "client" (gmail-web,…), pas "links" -> non bloquant.
    for it in issues:
        if it.get("severity") != "error":
            continue
        cat = (it.get("category") or "").lower()
        if any(b in cat for b in BLOCKING_CATEGORIES):
            return True
    return False


def run_lint(html: str) -> dict:
    """Lance emailens lint + analyze sur le HTML fourni. Renvoie un résultat normalisé."""
    if not (html or "").strip():
        return {"ok": False, "error": "HTML vide"}
    if not Path(EMAILENS_BIN).exists():
        return {"ok": False, "error": f"emailens introuvable ({EMAILENS_BIN})"}

    tmp = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
            f.write(html)
            tmp = f.name

        # --- lint (liste d'issues + compteurs) ---
        _, out_lint, err_lint = _run([EMAILENS_BIN, "lint", tmp, "--json"])
        try:
            lint = json.loads(out_lint) if out_lint.strip() else {}
        except json.JSONDecodeError:
            return {"ok": False, "error": "parse lint JSON", "raw": (out_lint or err_lint)[:500]}

        files = lint.get("files") or [{}]
        first = files[0] if files else {}
        issues = _drop_known_vars(first.get("issues", []) or [])
        issues = _drop_preheader_contrast(issues, html)
        # compteurs recalculés sur les issues filtrées (cohérent avec ce qui s'affiche)
        n_err = sum(1 for i in issues if i.get("severity") == "error")
        n_warn = sum(1 for i in issues if i.get("severity") == "warning")

        # --- analyze (score global + par client) ---
        _, out_an, _ = _run([EMAILENS_BIN, "analyze", tmp, "--json"])
        try:
            analyze = json.loads(out_an) if out_an.strip() else {}
        except json.JSONDecodeError:
            analyze = {}
        global_score = analyze.get("overallScore")
        per_client = analyze.get("scores", {}) or {}

        return {
            "ok": True,
            "global_score": global_score,
            "per_client": per_client,
            "issues": issues,
            "counts": {
                "errors": n_err,
                "warnings": n_warn,
                "info": sum(1 for i in issues if i.get("severity") == "info"),
            },
            "blocking": _is_blocking(issues),
            "tested_at": datetime.now(timezone.utc).isoformat(),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout {TIMEOUT_S}s"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def save_result(site: str, target_type: str, target_ref: str, result: dict, by: str = "ui") -> None:
    _ensure_table()
    counts = result.get("counts", {}) or {}
    c = _conn()
    try:
        c.execute(
            "DELETE FROM newsletter_lint WHERE site_code=? AND target_type=? AND target_ref=?",
            [site, target_type, target_ref],
        )
        c.execute(
            "INSERT INTO newsletter_lint VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                site, target_type, target_ref,
                result.get("global_score"),
                counts.get("errors", 0), counts.get("warnings", 0),
                bool(result.get("blocking", False)),
                json.dumps(result), datetime.now(timezone.utc), by,
            ],
        )
    finally:
        c.close()


def get_all_results(site: str) -> dict:
    """Map { '<type>:<ref>': {global_score, n_errors, n_warnings, blocking, tested_at} } pour les badges."""
    _ensure_table()
    c = _conn()
    try:
        rows = c.execute(
            "SELECT target_type, target_ref, global_score, n_errors, n_warnings, blocking, tested_at "
            "FROM newsletter_lint WHERE site_code=?",
            [site],
        ).fetchall()
    finally:
        c.close()
    return {
        f"{r[0]}:{r[1]}": {
            "global_score": r[2], "n_errors": r[3], "n_warnings": r[4],
            "blocking": r[5], "tested_at": str(r[6]),
        }
        for r in rows
    }


if __name__ == "__main__":
    import sys
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    h = p.read_text(encoding="utf-8") if p and p.exists() else ""
    print(json.dumps(run_lint(h), ensure_ascii=False, indent=2)[:2000])
