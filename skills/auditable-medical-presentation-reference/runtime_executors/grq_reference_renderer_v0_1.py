from __future__ import annotations
import json, hashlib, html, os
from pathlib import Path
from PIL import Image
import cairosvg

OUT=None  # set by run(); importing never creates directories
FONT='AR PL UMing CN'

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for ch in iter(lambda:f.read(1<<20), b''): h.update(ch)
    return h.hexdigest()

def esc(s): return html.escape(str(s), quote=True)

def svg_wrap(body,w=1200,h=700):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<rect width="100%" height="100%" fill="white"/>
<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#222"/></marker></defs>
{body}
</svg>'''

def write_svg(name, svg, manifest):
    svg_p=OUT/f'{name}.svg'; json_p=OUT/f'{name}.manifest.json'; png_p=OUT/f'{name}.png'
    svg_p.write_text(svg, encoding='utf-8')
    json_p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    cairosvg.svg2png(bytestring=svg.encode('utf-8'), write_to=str(png_p), output_width=1200)
    return {'svg':str(svg_p),'png':str(png_p),'manifest':str(json_p),'svg_sha256':sha256_file(svg_p),'png_sha256':sha256_file(png_p),'manifest_sha256':sha256_file(json_p)}

def render_diagram(fid, nodes, edges, logic_bindings=None):
    pos={n['id']:(n['x'],n['y']) for n in nodes}
    body=[]
    for e in edges:
        x1,y1=pos[e['from']]; x2,y2=pos[e['to']]
        body.append(f'<line x1="{x1}" y1="{y1+25}" x2="{x2}" y2="{y2-25}" stroke="#222" stroke-width="2" marker-end="url(#arrow)"/>')
        if e.get('label'):
            mx=(x1+x2)/2; my=(y1+y2)/2
            body.append(f'<rect x="{mx-45}" y="{my-15}" width="90" height="24" fill="white"/>')
            body.append(f'<text x="{mx}" y="{my+3}" text-anchor="middle" font-family="{FONT}" font-size="18">{esc(e["label"])}</text>')
    for n in nodes:
        body.append(f'<rect x="{n["x"]-110}" y="{n["y"]-25}" rx="8" width="220" height="50" fill="#f4f4f4" stroke="#222"/>')
        body.append(f'<text x="{n["x"]}" y="{n["y"]+6}" text-anchor="middle" font-family="{FONT}" font-size="20">{esc(n["label"])}</text>')
    manifest={'fixture_id':fid,'engine':'reference_svg_renderer','engine_version':'v0.1','semantic_graph':{'nodes':nodes,'edges':edges},'logic_bindings':logic_bindings or [],'text_items':[{'id':n['id'],'text':n['label']} for n in nodes]+[{'id':e['id']+'-label','text':e.get('label','')} for e in edges if e.get('label')]}
    return write_svg(fid, svg_wrap('\n'.join(body)), manifest)

def render_matrix(fid, columns, rows, cells, logic_bindings=None, groups=None):
    w=1200; left=240; top=120; cw=(w-left-40)/max(1,len(columns)); rh=60; h=top+rh*(len(rows)+1)+80
    body=[]
    for ci,c in enumerate(columns):
        x=left+ci*cw
        body.append(f'<rect x="{x}" y="{top-rh}" width="{cw}" height="{rh}" fill="#f0f0f0" stroke="#444"/>')
        body.append(f'<text x="{x+cw/2}" y="{top-rh/2+7}" text-anchor="middle" font-family="{FONT}" font-size="19">{esc(c["label"])}</text>')
    for ri,r in enumerate(rows):
        y=top+ri*rh
        body.append(f'<rect x="20" y="{y}" width="{left-20}" height="{rh}" fill="#f7f7f7" stroke="#444"/>')
        body.append(f'<text x="{left-10}" y="{y+rh/2+7}" text-anchor="end" font-family="{FONT}" font-size="18">{esc(r["label"])}</text>')
        for ci,c in enumerate(columns):
            x=left+ci*cw
            body.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{rh}" fill="white" stroke="#444"/>')
            val=cells.get((r['id'],c['id']),'')
            body.append(f'<text x="{x+cw/2}" y="{y+rh/2+7}" text-anchor="middle" font-family="{FONT}" font-size="18">{esc(val)}</text>')
    manifest={'fixture_id':fid,'engine':'reference_svg_renderer','engine_version':'v0.1','matrix':{'columns':columns,'rows':rows,'cells':[{'row_id':r,'column_id':c,'text':v} for (r,c),v in cells.items()],'groups':groups or []},'logic_bindings':logic_bindings or [],'text_items':[{'id':c['id'],'text':c['label']} for c in columns]+[{'id':r['id'],'text':r['label']} for r in rows]+[{'id':f'{r}:{c}','text':v} for (r,c),v in cells.items()]}
    return write_svg(fid, svg_wrap('\n'.join(body),w=w,h=h), manifest)

def render_exact(fid, strings):
    body=[]
    y=80
    for i,s in enumerate(strings):
        body.append(f'<text x="80" y="{y}" font-family="{FONT}" font-size="34">{esc(s)}</text>')
        y+=85
    manifest={'fixture_id':fid,'engine':'reference_svg_renderer','engine_version':'v0.1','text_items':[{'id':f't{i+1}','text':s} for i,s in enumerate(strings)]}
    return write_svg(fid, svg_wrap('\n'.join(body),w=1200,h=max(400,y+40)), manifest)

def asset_scale(fid, src, scale):
    im=Image.open(src)
    out=OUT/f'{fid}.png'
    size=(round(im.width*scale), round(im.height*scale))
    im.resize(size, Image.Resampling.LANCZOS).save(out)
    manifest={'fixture_id':fid,'engine':'reference_pillow_asset_renderer','engine_version':'Pillow-12.3.0+policy-v0.1','operation':'uniform_scale','parent_sha256':sha256_file(src),'scale':scale,'output_size':size,'output_sha256':sha256_file(out),'ai_redraw':False}
    mp=OUT/f'{fid}.manifest.json'; mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'png':str(out),'manifest':str(mp),'png_sha256':sha256_file(out),'manifest_sha256':sha256_file(mp)}

def asset_crop_margin(fid, src, crop):
    im=Image.open(src)
    l,t,r,b=crop
    if l>im.width*0.03 or (im.width-r)>im.width*0.03 or t>im.height*0.03 or (im.height-b)>im.height*0.03:
        raise ValueError('crop exceeds safe-margin policy')
    out=OUT/f'{fid}.png'; im.crop(crop).save(out)
    manifest={'fixture_id':fid,'engine':'reference_pillow_asset_renderer','engine_version':'Pillow-12.3.0+policy-v0.1','operation':'verified_margin_crop','parent_sha256':sha256_file(src),'crop':crop,'output_size':Image.open(out).size,'output_sha256':sha256_file(out),'ai_redraw':False,'derivative_label':'VERIFIED_DERIVATIVE'}
    mp=OUT/f'{fid}.manifest.json'; mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'png':str(out),'manifest':str(mp),'png_sha256':sha256_file(out),'manifest_sha256':sha256_file(mp)}

def run(out_dir, source_asset):
    global OUT
    OUT=Path(out_dir); OUT.mkdir(parents=True, exist_ok=True)
    outputs={}
    outputs['GRQ-DIA-001']=render_diagram('GRQ-DIA-001',[
        {'id':'A','label':'A','x':300,'y':100},{'id':'B','label':'B?','x':300,'y':230},{'id':'C','label':'C','x':150,'y':400},{'id':'D','label':'D','x':450,'y':400}],
        [{'id':'E1','from':'A','to':'B','label':''},{'id':'E2','from':'B','to':'C','label':'YES'},{'id':'E3','from':'B','to':'D','label':'NO'}])
    outputs['GRQ-DIA-002']=render_diagram('GRQ-DIA-002',[
        {'id':'B','label':'x阈值？','x':300,'y':150},{'id':'D','label':'D','x':150,'y':350},{'id':'E','label':'E','x':450,'y':350}],
        [{'id':'E1','from':'B','to':'D','label':'x≥50%'},{'id':'E2','from':'B','to':'E','label':'x<50%'}])
    outputs['GRQ-DIA-003']=render_diagram('GRQ-DIA-003',[
        {'id':'BUNDLE','label':'A AND B AND C','x':300,'y':170},{'id':'P','label':'Phenotype','x':300,'y':380}],
        [{'id':'E1','from':'BUNDLE','to':'P','label':'AND bundle'}],logic_bindings=[{'bundle_id':'L1','operator':'AND','members':['A','B','C']}])
    outputs['GRQ-DIA-004']=render_diagram('GRQ-DIA-004',[
        {'id':'IOCA','label':'IOCA','x':120,'y':180},{'id':'ANCHOR','label':'INOCA Anchor','x':480,'y':280},{'id':'MINOCA','label':'MINOCA','x':120,'y':420}],
        [{'id':'R1','from':'IOCA','to':'ANCHOR','label':'可参照'},{'id':'R2','from':'MINOCA','to':'ANCHOR','label':'推荐同'}])
    cols=[{'id':f'G{i+1}','label':f'Group {i+1}'} for i in range(4)]
    rows=[{'id':f'R{i+1}','label':f'Item {i+1}'} for i in range(3)]
    cells={('R1','G1'):'A1',('R2','G1'):'A2',('R1','G2'):'B1',('R2','G2'):'B2',('R1','G3'):'C1',('R2','G3'):'C2',('R3','G3'):'C3',('R1','G4'):'D1',('R2','G4'):'D2'}
    outputs['GRQ-MAT-001']=render_matrix('GRQ-MAT-001',cols,rows,cells,groups=[{'group_id':c['id'],'members':[v for (r,g),v in cells.items() if g==c['id']]} for c in cols])
    cols=[{'id':'M1','label':'Method 1'},{'id':'M2','label':'Method 2'},{'id':'M3','label':'Method 3'}]
    rows=[{'id':'Q1','label':'Need A'},{'id':'Q2','label':'Need B'},{'id':'Q3','label':'Need C'}]
    cells={('Q1','M1'):'✓',('Q1','M2'):'✓',('Q2','M2'):'✓',('Q3','M1'):'✓',('Q3','M3'):'✓'}
    outputs['GRQ-MAT-002']=render_matrix('GRQ-MAT-002',cols,rows,cells)
    cols=[{'id':'PA','label':'Phenotype A'},{'id':'PB','label':'Phenotype B'},{'id':'PC','label':'Phenotype C'}]
    rows=[{'id':'FFR','label':'FFR'},{'id':'CFR','label':'CFR'},{'id':'IMR','label':'IMR'},{'id':'HMR','label':'HMR'},{'id':'ACH','label':'ACh症状'},{'id':'ST','label':'ST改变'},{'id':'DIA','label':'Diameter'}]
    vals={'PA':['>0.8','<2.0','≥25','≥1.9','YES','YES','<90%'],'PB':['>0.8','≥2.0','<25','<1.9','YES','YES','≥90%'],'PC':['>0.8','<2.0','≥25','≥1.9','YES','YES','≥90%']}
    cells={(r['id'],c['id']):vals[c['id']][ri] for ri,r in enumerate(rows) for c in cols}
    outputs['GRQ-MAT-003']=render_matrix('GRQ-MAT-003',cols,rows,cells,logic_bindings=[{'bundle_id':c['id'],'operator':'AND','members':[r['id'] for r in rows]} for c in cols])
    cols=[{'id':'C1','label':'MIOCA'},{'id':'C2','label':'Post-STEMI PCI'},{'id':'C3','label':'Non-athero + hypertrophy'},{'id':'C4','label':'Non-athero no hypertrophy'}]
    rows=[{'id':'OWN','label':'Owned treatment set'}]
    cells={('OWN','C1'):'Table9',('OWN','C2'):'Table10',('OWN','C3'):'Table11-A',('OWN','C4'):'Table11-B'}
    outputs['GRQ-MAT-004']=render_matrix('GRQ-MAT-004',cols,rows,cells)
    exact_sets={
      'GRQ-TXT-001':['CFR <2.0','IMR ≥25','HMR ≥1.9','HMR >1.7','HMR >3'],
      'GRQ-TXT-002':['冠脉狭窄≥50%','冠脉狭窄<50%','CFR<2.0'],
      'GRQ-TXT-003':['推荐类别：IIa','证据级别：B','可参照INOCA相关CMVD治疗','推荐同INOCA相关CMVD'],
      'GRQ-TXT-004':['0.4 mg/5 ml','2.25 ml·g⁻¹·min⁻¹','≤2.0~2.5','<1.5~2'],
      'GRQ-TXT-005':['主讲语义子图｜完整条件与全部分支见原共识图1','AI生成模拟病例｜非原文病例｜仅用于教学演示']
    }
    for fid,ss in exact_sets.items(): outputs[fid]=render_exact(fid,ss)
    src=str(Path(source_asset).resolve(strict=True))
    outputs['GRQ-AST-001']=asset_scale('GRQ-AST-001',src,0.5)
    im=Image.open(src); crop=(20,20,im.width-20,im.height-20)
    outputs['GRQ-AST-002']=asset_crop_margin('GRQ-AST-002',src,crop)
    neg={}
    try:
      bad=(0,0,im.width,int(im.height*0.7))
      asset_crop_margin('GRQ-AST-003',src,bad)
      neg['GRQ-AST-003']={'rejected':False}
    except Exception as e: neg['GRQ-AST-003']={'rejected':True,'reason':str(e)}
    neg['GRQ-AST-004']={'status':'POLICY_UNSUPPORTED','executed':False,'reason':'AI redraw as source authority is not an operation supported by reference_pillow_asset_renderer policy-v0.1'}
    outputs.update(neg)
    summary={'renderer_script_sha256':sha256_file(__file__),'python_version':__import__('sys').version,'pillow_version':__import__('PIL').__version__,'cairosvg_version':cairosvg.__version__,'outputs':outputs}
    (OUT/'run_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('--out',required=True); p.add_argument('--source-asset',required=True)
    a=p.parse_args(); print(json.dumps(run(a.out,a.source_asset),ensure_ascii=False,indent=2))
