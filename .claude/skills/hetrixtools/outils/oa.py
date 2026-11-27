import yaml,json,re
d=yaml.safe_load(open('api.yaml'))
D='/home/autoblog/genesis/.claude/skills/hetrixtools/doc/api/v3'
SRC='https://docs.hetrixtools.com/api/v3/ (spec : https://docs.hetrixtools.com/api/v3/api.yaml?v=170)'
def res(o,depth=0):
    if isinstance(o,dict):
        if '$ref' in o and depth<20:
            parts=o['$ref'].lstrip('#/').split('/'); x=d
            for p in parts: x=x[p]
            return res(x,depth+1)
        return {k:res(v,depth) for k,v in o.items()}
    if isinstance(o,list): return [res(v,depth) for v in o]
    return o
def fields(s,prefix='',rows=None,req=()):
    if rows is None: rows=[]
    if not isinstance(s,dict): return rows
    for comb in ('allOf','oneOf','anyOf'):
        if comb in s:
            for sub in s[comb]: fields(sub,prefix,rows,req)
    t=s.get('type')
    if t=='object' or 'properties' in s:
        r=s.get('required',[])
        for k,v in (s.get('properties') or {}).items():
            name=prefix+k
            vt=v.get('type','')
            if 'enum' in v: vt+=' enum '+str(v['enum'])
            if v.get('nullable'): vt+=' | null'
            if v.get('format'): vt+=f" ({v['format']})"
            desc=(v.get('description') or '').strip().replace('\n',' ').replace('|','/')
            rows.append(f"| `{name}` | {vt} | {'oui' if k in r else ''} | {desc} |")
            if v.get('type')=='object' or 'properties' in v: fields(v,name+'.',rows)
            if v.get('type')=='array' and isinstance(v.get('items'),dict): fields(v['items'],name+'[].',rows)
            if isinstance(v.get('additionalProperties'),dict): fields(v['additionalProperties'],name+'.<clé>.',rows)
    elif t=='array' and isinstance(s.get('items'),dict): fields(s['items'],prefix+'[].',rows)
    return rows
def table(rows):
    return "| Champ | Type | Requis | Description |\n|---|---|---|---|\n"+"\n".join(rows) if rows else "_(pas de schéma détaillé)_"
def ex(x): return "```json\n"+json.dumps(x,indent=2,ensure_ascii=False)+"\n```"
index=["# HetrixTools API v3 — index des endpoints\n",f"> Source : {SRC}  \n> Généré le 2026-09-26 depuis la spec OpenAPI officielle (fichier brut : `api.yaml`).\n","Base URL : `https://api.hetrixtools.com/v3/` — Auth : `Authorization: Bearer <API_KEY>`\n","| Méthode | Chemin | Titre | Fichier |","|---|---|---|---|"]
# intro
intro=f"# HetrixTools API v3 — introduction (Redoc)\n\n> Source : {SRC}\n\n"+d['info']['description']+"\n\n## Authentification (securitySchemes.bearerAuth)\n\n"+d['components']['securitySchemes']['bearerAuth']['description']+"\n\n## Réponses d'erreur communes (components.responses)\n\n"
for k,v in d['components']['responses'].items():
    v=res(v); intro+=f"### {k}\n\n{v.get('description','')}\n\n"
    for ct,c in (v.get('content') or {}).items():
        if 'example' in c: intro+=ex(c['example'])+"\n\n"
        for en,e in (c.get('examples') or {}).items(): intro+=f"_{en}_\n\n"+ex(e.get('value'))+"\n\n"
open(D+'/_intro.md','w').write(intro)
for p,v in d['paths'].items():
    common=v.get('parameters',[])
    for m,o in v.items():
        if m not in ('get','post','put','delete','patch'): continue
        o=res(o); slug=(m+'_'+re.sub(r'[{}]','',p).strip('/').replace('/','_')).replace('-','-')
        s=[f"# {m.upper()} {p} — {o.get('summary','')}\n",f"> Source : https://docs.hetrixtools.com/api/v3/ (opération `{m.upper()} {p}`) — spec api.yaml?v=170, aspirée le 2026-09-26\n",
           f"`{m.upper()} https://api.hetrixtools.com/v3{p}`\n","## Description\n",(o.get('description') or '').strip()+"\n"]
        params=res(common)+(o.get('parameters') or [])
        if params:
            s.append("## Paramètres\n\n| Nom | Où | Type | Requis | Description |\n|---|---|---|---|---|")
            for pa in params:
                sc=pa.get('schema',{}); ty=sc.get('type','')
                for k in ('enum','default','minimum','maximum'):
                    if k in sc: ty+=f" {k}={sc[k]}"
                s.append(f"| `{pa['name']}` | {pa.get('in')} | {ty} | {'oui' if pa.get('required') else ''} | {(pa.get('description') or '').strip().replace(chr(10),' ').replace('|','/')} |")
            s.append("")
        rb=o.get('requestBody')
        if rb:
            s.append("## Corps de la requête\n")
            if rb.get('description'): s.append(rb['description'].strip()+"\n")
            for ct,c in (rb.get('content') or {}).items():
                s.append(f"Content-Type : `{ct}`\n"); s.append(table(fields(c.get('schema',{})))+"\n")
                if 'example' in c: s.append("Exemple :\n\n"+ex(c['example'])+"\n")
                for en,e in (c.get('examples') or {}).items(): s.append(f"Exemple « {en} » :\n\n"+ex(e.get('value'))+"\n")
        s.append("## Réponses\n")
        for code,r in (o.get('responses') or {}).items():
            s.append(f"### {code} — {(r.get('description') or '').strip()}\n")
            for h,hv in (r.get('headers') or {}).items(): s.append(f"- en-tête `{h}` : {hv.get('description','')}")
            for ct,c in (r.get('content') or {}).items():
                sc=c.get('schema',{})
                if str(code).startswith('2'): s.append(table(fields(sc))+"\n")
                if 'example' in c: s.append(ex(c['example'])+"\n")
                for en,e in (c.get('examples') or {}).items(): s.append(f"_{en}_ :\n\n"+ex(e.get('value'))+"\n")
        if o.get('security') is not None: s.append(f"\nSécurité : `{o['security']}`\n")
        open(f"{D}/{slug}.md",'w').write("\n".join(s))
        index.append(f"| {m.upper()} | `{p}` | {o.get('summary','')} | `{slug}.md` |")
open(D+'/INDEX.md','w').write("\n".join(index)+"\n\nVoir aussi `_intro.md` (codes HTTP, limites de débit, auth).\n")
