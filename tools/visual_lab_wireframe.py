"""Source-exact structural reference from an accepted Luna layout (not final art)."""
from __future__ import annotations
import argparse,html,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from factdeck.visual_lab import validate_design

def render(graph_page,design,out):
    validate_design(graph_page,design)
    fs={f['id']:f for f in graph_page['text_fragments']};regions={r['id']:r for r in graph_page['regions']}
    boxes={r['id']:r for r in design['regions']};parts=[]
    for row in design['regions']:
        region=regions[row['id']];ids=region['label_fragment_ids']+region['body_fragment_ids']
        ids=sorted(ids,key=lambda i:(fs[i]['block_index'],fs[i]['start']))
        text=''.join(fs[i]['quote'] for i in ids).replace('\n','')
        descendants=[r for r in design['regions'] if regions[r['id']].get('parent_region_id')==row['id']]
        text_h=max(24,min([r['y']-row['y']-12 for r in descendants])) if descendants else row['h']
        role=fs[ids[0]].get('role','content') if ids else 'content'
        size=34 if role=='title' else 13 if role in ('navigation','source','page') else 20
        border='1px solid #8FA994' if role=='content' or descendants else 'none'
        parts.append(f'<div style="position:absolute;left:{row["x"]}px;top:{row["y"]}px;width:{row["w"]}px;height:{row["h"]}px;border:{border};border-radius:12px;box-sizing:border-box;background:rgba(230,237,223,.15)"></div>')
        parts.append(f'<div data-region="{html.escape(row["id"])}" style="position:absolute;left:{row["x"]+8}px;top:{row["y"]+6}px;width:{row["w"]-16}px;height:{max(18,text_h-12)}px;font-size:{size}px;line-height:1.35;overflow:visible;box-sizing:border-box">{html.escape(text)}</div>')
    for relation in graph_page['relations']:
        if relation['type'] in ('context','contrast'):continue
        for src in relation['from']:
            for dst in relation['to']:
                a,b=boxes[src],boxes[dst];x1=a['x']+a['w']/2;y1=a['y']+a['h'];x2=b['x']+b['w']/2;y2=b['y']
                # Structural guide only: a connector without an invented label.
                parts.append(f'<svg style="position:absolute;left:0;top:0;width:1280px;height:720px;pointer-events:none"><path d="M{x1},{y1} L{x2},{y2}" fill="none" stroke="#355A42" stroke-width="1.5"/></svg>')
    content='<!doctype html><meta charset="utf-8"><body style="margin:0;background:#F8F6EE;color:#183A29;font-family:Microsoft YaHei,sans-serif"><main style="position:relative;width:1280px;height:720px">'+''.join(parts)+'</main>'
    out.parent.mkdir(parents=True,exist_ok=True);out.with_suffix('.html').write_text(content,encoding='utf8')
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1280,'height':720},device_scale_factor=1)
        page.goto(out.with_suffix('.html').resolve().as_uri());page.evaluate('document.fonts.ready')
        metrics=page.locator('[data-region]').evaluate_all('els=>els.map(n=>({id:n.dataset.region,scroll:n.scrollHeight,client:n.clientHeight}))')
        if any(m['scroll']>m['client']+2 for m in metrics):raise ValueError('Wireframe text overflows; fix layout before using reference: '+str([m['id'] for m in metrics if m['scroll']>m['client']+2]))
        page.screenshot(path=str(out));browser.close()
    return {'reference':str(out),'source_text_exact':True,'medical_approval':False,'purpose':'structural reference, not final slide'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--design',required=True,type=Path);parser.add_argument('--out',required=True,type=Path);a=parser.parse_args()
    design=json.loads(a.design.read_text(encoding='utf8'));graph=json.loads((ROOT/'output/visual_prompt_lab/semantic_graph.json').read_text(encoding='utf8'))
    p=next(p for p in graph['pages'] if p['page']['number']==design['page'])
    print(json.dumps(render(p,design,a.out),ensure_ascii=False))
