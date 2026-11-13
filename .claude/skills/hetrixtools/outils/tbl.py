import sys
from bs4 import BeautifulSoup
src,url,title=sys.argv[1],sys.argv[2],sys.argv[3]
s=BeautifulSoup(open(src).read(),'html.parser')
out=[f"# {title}\n\n> Source : {url}  \n> Aspiré le 2026-09-26 (page publique, tarifs mensuels ; ✓ = inclus, ✗ = non inclus). Colonnes dans l'ordre de la page.\n"]
for tb in s.find_all('table'):
    rows=[]
    for tr in tb.find_all('tr'):
        cells=[]
        for td in tr.find_all(['td','th']):
            txt=td.get_text(' ',strip=True)
            tip=td.find(attrs={'title':True})
            if not txt:
                if td.find(class_='ti-check'): txt='✓'
                elif td.find(class_='ti-close'): txt='✗'
            if tip and tip.get('title') and len(cells)==0: txt+=f" _(info-bulle : {BeautifulSoup(tip['title'],'html.parser').get_text(' ')})_"
            cells.append(txt.replace('|','/'))
        if any(cells): rows.append(cells)
    if not rows: continue
    n=max(len(r) for r in rows)
    out.append('| '+' | '.join(['Ligne']+[f'c{i}' for i in range(1,n)])+' |'); out.append('|'+'---|'*n)
    for r in rows: out.append('| '+' | '.join(r+['']*(n-len(r)))+' |')
    out.append('')
print('\n'.join(out))
