import json,glob,html,sys,os
from markdownify import markdownify as md
D='/home/autoblog/genesis/.claude/skills/hetrixtools/doc'
def write(p,sub):
    title=html.unescape(p['title']['rendered'])
    body=md(p['content']['rendered'],heading_style='ATX',code_language='')
    body=body.replace('\n\n\n','\n\n')
    out=f"# {title}\n\n> Source : {p['link']}  \n> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié {p['date'][:10]}, modifié {p['modified'][:10]}\n\n{body.strip()}\n"
    fn=f"{D}/{sub}/{p['slug']}.md"; open(fn,'w').write(out); return fn
seen=set()
for f,sub in [('posts_17.json','api'),('posts_477.json','mcp'),('posts_480.json','mcp')]:
    for p in json.load(open(f)):
        if p['slug'] in seen: continue
        seen.add(p['slug']); print(write(p,sub))
for f in glob.glob('extra_*.json'):
    p=json.load(open(f))[0]
    sub='api' if p['slug'] in ('api-key-scope','what-is-the-difference-between-api-calls-and-api-checks','moscow-relocation-api-webhook-changes','linux-server-monitoring-agent-v2-api-endpoint-documentation') else 'related'
    print(write(p,sub))
