#!/usr/bin/env python3
"""Réécrit les blocs JSON de composants (schémas OpenAPI, en-têtes UI) en Markdown lisible."""
import json
import re
import sys
from pathlib import Path

RACINE = Path(sys.argv[1])
BLOC = re.compile(r"<!-- (M?\w+) -->\n```json\n(.*?)\n```\n", re.S)
BRUIT = {"as", "className", "id", "context", "level"}


def type_de(s: dict) -> str:
    if not isinstance(s, dict):
        return ""
    for k in ("anyOf", "oneOf", "allOf"):
        if k in s:
            t = [type_de(x) for x in s[k] if type_de(x)]
            t = [x for x in t if x != "null"]
            return " \\| ".join(dict.fromkeys(t)) or s.get("title", "")
    t = s.get("type", "")
    if t == "array":
        return f"array<{type_de(s.get('items', {})) or 'any'}>"
    if t == "object" and s.get("title"):
        return f"object ({s['title']})"
    if s.get("format"):
        return f"{t} ({s['format']})"
    return t or s.get("title", "")


def fusion(s: dict) -> dict:
    """Aplati allOf à un seul schéma."""
    if isinstance(s, dict) and "allOf" in s and len(s["allOf"]) == 1:
        return {**s["allOf"][0], **{k: v for k, v in s.items() if k != "allOf"}}
    return s


def champs(schema: dict, prefixe: str = "", requis=(), prof=0) -> list[str]:
    schema = fusion(schema)
    lignes = []
    props = schema.get("properties") or {}
    req = set(schema.get("required") or requis)
    for nom, s in props.items():
        s = fusion(s)
        desc = (s.get("description") or "").replace("\n", " ").replace("|", "\\|")
        extra = []
        if "enum" in s:
            extra.append("valeurs : " + ", ".join(f"`{v}`" for v in s["enum"]))
        if "default" in s:
            extra.append(f"défaut : `{json.dumps(s['default'], ensure_ascii=False)}`")
        for k in ("minItems", "maxItems", "minLength", "maxLength", "pattern", "minimum", "maximum"):
            if k in s:
                extra.append(f"{k} : `{s[k]}`")
        if "items" in s and isinstance(s["items"], dict) and "pattern" in s["items"]:
            extra.append(f"motif : `{s['items']['pattern']}`")
        texte = " — ".join(x for x in [desc, "; ".join(extra)] if x)
        lignes.append(f"| `{prefixe}{nom}` | {type_de(s)} | {'oui' if nom in req else ''} | {texte} |")
        if prof < 3:
            sous = s
            if s.get("type") == "array" and isinstance(s.get("items"), dict):
                sous = fusion(s["items"])
                pre = f"{prefixe}{nom}[]."
            else:
                pre = f"{prefixe}{nom}."
            if isinstance(sous, dict) and sous.get("properties"):
                lignes += champs(sous, pre, (), prof + 1)
    return lignes


def table(schema: dict) -> str:
    variantes = [fusion(v) for v in (schema.get("anyOf") or schema.get("oneOf") or [])
                 if isinstance(v, dict)]
    if not schema.get("properties") and any(v.get("properties") for v in variantes):
        return "".join(f"\n**Variante : {v.get('title', '?')}**\n\n" + table(v) for v in variantes)
    l = champs(schema)
    if not l:
        return f"Type : {type_de(schema) or json.dumps(schema)[:300]}\n"
    return "| Champ | Type | Requis | Description |\n| --- | --- | --- | --- |\n" + "\n".join(l) + "\n"


def exemples(contenu: dict) -> str:
    out = ""
    for nom, ex in (contenu.get("examples") or {}).items():
        v = ex.get("value", ex) if isinstance(ex, dict) else ex
        out += f"\nExemple « {ex.get('summary', nom) if isinstance(ex, dict) else nom} » :\n```json\n{json.dumps(v, indent=1, ensure_ascii=False)[:4000]}\n```\n"
    if "example" in contenu:
        out += f"\nExemple :\n```json\n{json.dumps(contenu['example'], indent=1, ensure_ascii=False)[:4000]}\n```\n"
    return out


def rendre_bloc(d: dict) -> str:
    if set(d) <= BRUIT:
        return ""
    if "method" in d and "path" in d:
        return f"\n**{d['method'].upper()}** `https://api.sweego.io{d['path']}`\n\n"
    if "parameters" in d and isinstance(d["parameters"], list):
        if not d["parameters"]:
            return ""
        t = f"\n### Paramètres ({d.get('title', '')})\n\n| Nom | Type | Requis | Description |\n| --- | --- | --- | --- |\n"
        for p in d["parameters"]:
            t += (f"| `{p.get('name')}` | {type_de(p.get('schema', {}))} | {'oui' if p.get('required') else ''} | "
                  f"{(p.get('description') or '').replace(chr(10), ' ')} |\n")
        return t
    if "body" in d:
        b = d["body"] or {}
        t = f"\n### Corps de la requête{' (requis)' if b.get('required') else ''}\n\n"
        for ctype, c in (b.get("content") or {}).items():
            t += f"Content-Type : `{ctype}`\n\n" + table(c.get("schema", {})) + exemples(c)
        return t
    if "responses" in d:
        t = "\n### Réponses\n"
        for code, r in (d["responses"] or {}).items():
            t += f"\n#### {code} — {r.get('description', '')}\n\n"
            for ctype, c in (r.get("content") or {}).items():
                t += table(c.get("schema", {})) + exemples(c)
        return t
    if list(d) == ["type"]:
        return f"\n> **{str(d['type']).upper()}**\n"
    if list(d) == ["title"] or list(d) == ["label"]:
        return f"\n**{list(d.values())[0]}**\n"
    s = json.dumps(d, ensure_ascii=False)
    return f"\n`{s[:500]}`\n" if len(s) < 500 else f"\n```json\n{json.dumps(d, indent=1, ensure_ascii=False)[:6000]}\n```\n"


n = 0
for f in RACINE.rglob("*.md"):
    s = f.read_text()
    def repl(m):
        try:
            return rendre_bloc(json.loads(m.group(2)))
        except Exception:
            return m.group(0)
    s2 = BLOC.sub(repl, s)
    # textes de libellés UI parasites laissés par les composants OpenAPI
    s2 = re.sub(r"\n(Request|Responses|Schema|Body|required)\n", "\n", s2)
    s2 = re.sub(r"\n{3,}", "\n\n", s2)
    if s2 != s:
        f.write_text(s2)
        n += 1
print(n, "fichiers réécrits")
