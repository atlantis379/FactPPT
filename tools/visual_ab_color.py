"""Recolor existing native slide objects while preserving their exact structure.

The bundled artifact-tool import/export probe retained path vertices but removed
all 33 component groups. Patch only existing OOXML color attributes to retain the
user's required component editing and all unrelated package parts byte for byte.
"""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import re
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

from lxml import etree

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.visual_ab_test import dump,sha

BASE=ROOT/'output/visual_ab_test'
SOURCE=BASE/'A_vector'
OUT=BASE/'A_vector_muted'
A='{http://schemas.openxmlformats.org/drawingml/2006/main}'
P='{http://schemas.openxmlformats.org/presentationml/2006/main}'
NS={'a':A[1:-1],'p':P[1:-1]}
PRIMARY='355E78'
HEADER='3E6278'


def blue(value):
    r,g,b=[int(value[i:i+2],16)/255 for i in (0,2,4)]
    h,l,s=colorsys.rgb_to_hls(r,g,b)
    # Exclude the original cool charcoal text and neutral source annotations.
    return l>.20 and b-r>.065 and .50<h<.76 and s>.18


def muted(value,role):
    if not blue(value):return value
    rgb=[int(value[i:i+2],16)/255 for i in (0,2,4)]
    h,l,s=colorsys.rgb_to_hls(*rgb)
    if role=='text' and l<.77:return PRIMARY
    if role=='table' and l<.70:return HEADER
    h=.575+.18*(h-.575)
    if role=='wave':
        s=min(.27,s*.34);l=l+.12*(1-l)
    elif role=='artwork':
        s=min(.34,s*.42);l=l-.065*s*(1-l)
    else:
        if l<.63:return '607F93'
        s=min(.25,s*.37)
    return ''.join(f'{round(v*255):02X}' for v in colorsys.hls_to_rgb(h,l,s))


def color_role(element):
    ancestors=list(element.iterancestors())
    if any(x.tag in (A+'rPr',A+'defRPr',A+'endParaRPr') for x in ancestors):return 'text'
    if any(x.tag==A+'tcPr' for x in ancestors):return 'table'
    shape=next((x for x in ancestors if x.tag in (P+'sp',P+'cxnSp',P+'graphicFrame')),None)
    if shape is not None:
        name=shape.find('.//'+P+'cNvPr').get('name','')
        if name.startswith('描摹组件：'):
            return 'wave' if '波纹' in name or '底部装饰' in name else 'artwork'
    return 'decorative'


def without_color(root):
    root=etree.fromstring(etree.tostring(root))
    for e in root.iter(A+'srgbClr'):e.set('val','COLOR')
    return etree.tostring(root,method='c14n')


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter();changed=[];changes=Counter()
    with zipfile.ZipFile(SOURCE/'deck.pptx') as src,zipfile.ZipFile(OUT/'deck.pptx','w',zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data=src.read(info.filename)
            if re.fullmatch(r'ppt/slides/slide\d+\.xml',info.filename) or info.filename.startswith('ppt/theme/') and info.filename.endswith('.xml'):
                root=etree.fromstring(data);before=without_color(root);n=0
                for e in root.iter(A+'srgbClr'):
                    old=e.get('val').upper();role=color_role(e)
                    new=muted(old,role)
                    if old!=new:
                        e.set('val',new);n+=1;changes[(role,old,new)]+=1
                assert without_color(root)==before,'Only color values may change.'
                if n:
                    data=etree.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
                    changed.append(dict(part=info.filename,color_values_changed=n))
            dst.writestr(info,data)
    with zipfile.ZipFile(SOURCE/'deck.pptx') as src,zipfile.ZipFile(OUT/'deck.pptx') as dst:
        assert src.namelist()==dst.namelist()
        for name in src.namelist():
            if name not in {x['part'] for x in changed}:assert src.read(name)==dst.read(name)
            else:assert without_color(etree.fromstring(src.read(name)))==without_color(etree.fromstring(dst.read(name)))
        slides=[n for n in src.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)]
        assert len(slides)==6
        assert not any(n.startswith('ppt/media/') for n in dst.namelist())
        counts=[]
        for name in slides:
            root=etree.fromstring(dst.read(name))
            counts.append(dict(slide=name,custom_geometry=len(list(root.iter(A+'custGeom'))),
                               groups=len(list(root.iter(P+'grpSp'))),pictures=len(list(root.iter(P+'pic')))))
    # Color is applied to the saved browser preview as well, without raster editing.
    from lxml import html
    document=html.fromstring((SOURCE/'deck.html').read_text(encoding='utf8'))
    for e in document.iter():
        if 'style' in e.attrib:
            tag=e.tag.rsplit('}',1)[-1]
            role='text' if tag in ('div','span','p','b','strong','td','th') else 'decorative'
            if tag in ('td','th'):
                def css_color(m):
                    property_name=m.group(1);value=m.group(2)
                    return property_name+':#'+muted(value,'table' if property_name=='background' else 'text')
                e.set('style',re.sub(r'(color|background):#([\da-fA-F]{6})',css_color,e.get('style')))
            else:e.set('style',re.sub(r'#([\da-fA-F]{6})',lambda m:'#'+muted(m.group(1),role),e.get('style')))
        for attr in ('fill','stroke'):
            if re.fullmatch(r'#[\da-fA-F]{6}',e.get(attr,'')):
                value=e.get(attr)[1:]
                # Visual-only browser SVG does not preserve PPT grouping metadata.
                e.set(attr,'#'+muted(value,'artwork'))
    (OUT/'deck.html').write_text(html.tostring(document,encoding='unicode'),encoding='utf8')
    result=dict(source_sha256=sha(SOURCE/'deck.pptx'),new_sha256=sha(OUT/'deck.pptx'),
                build_seconds=round(time.perf_counter()-start,3),source_pages=6,
                content_and_geometry_exact=True,source_notes_bytes_exact=True,picture_objects=0,
                changed_parts=changed,objects=counts,
                color_changes=[dict(role=r,old=old,new=new,count=n) for (r,old,new),n in changes.items()],
                palette=dict(primary='#'+PRIMARY,table_header='#'+HEADER,body='#151B24',paper='#F6F4EF'),
                additional_image_calls=0,additional_vector_calls=0)
    dump(OUT/'verification.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('color_changes','changed_parts')},ensure_ascii=False,indent=2))


def office():
    import win32com.client,pythoncom
    pythoncom.CoInitialize();start=time.perf_counter()
    app=win32com.client.DispatchEx('PowerPoint.Application')
    p=app.Presentations.Open(str(OUT/'deck.pptx'),ReadOnly=True,WithWindow=False)
    try:
        assert p.Slides.Count==6
        for i in range(1,7):p.Slides(i).Export(str(OUT/f'slide{i:02d}.png'),'PNG',1280,720)
        p.SaveAs(str(OUT/'deck.pdf'),32)
    finally:p.Close();app.Quit();pythoncom.CoUninitialize()
    dump(OUT/'office.json',dict(pages=6,render_seconds=round(time.perf_counter()-start,3),renderer='Installed Microsoft PowerPoint'))
    print('Rendered six PowerPoint pages and PDF.')


def deliver():
    from playwright.sync_api import sync_playwright
    from pypdf import PdfReader
    assert len(PdfReader(OUT/'deck.pdf').pages)==6
    titles=['封面','国内外指南定义','炎症表型指标','生物制剂选择路径','研究中的缓解定义与结果','规格、用法与价格']
    css=re.search(r'<style>(.*?)</style>',(SOURCE/'index.html').read_text(encoding='utf8'),re.S).group(1)
    css+=' .columns{grid-template-columns:repeat(2,minmax(0,1fr))}@media(max-width:1000px){.columns{grid-template-columns:1fr}}'
    sections=[]
    for i,title in enumerate(titles,1):
        figures=''.join(f'<figure><figcaption>{label}</figcaption><button class="zoom" data-label="{title} · {label}"><img src="{src}" alt="{title} {label}"/></button></figure>' for label,src in [('原配色',f'../A_vector/deck-slide{i:02d}.png'),('墨蓝与蓝灰',f'slide{i:02d}.png')])
        sections.append(f'<section class="sample" id="sample{i}"><header><span class="number">{i:02d}</span><h2>{title}</h2></header><div class="columns">{figures}</div></section>')
    doc=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>六页配色调整对照</title><style>{css}</style></head><body><main class="wrap"><div class="eyebrow">FACTPPT · COLOR STUDY</div><h1>降低蓝色饱和度，拉开强调与装饰层级</h1><p class="intro">标题和关键数字使用墨蓝，插画改为灰蓝，底部波纹进一步减弱。正文保留炭黑，背景保留米白。六页均为 PowerPoint 实际导出画面，点击放大。</p><div class="links"><a href="deck.pptx" download>调整版 PPTX</a><a href="deck.pdf">PDF</a><a href="color_notes.md">配色说明</a><a href="color_delivery.zip" download>交付包</a></div><div class="toolbar"><nav>{''.join(f'<a href="#sample{i}">{i:02d}</a>' for i in range(1,7))}</nav></div>{''.join(sections)}</main><dialog><header><span id="caption"></span><button id="close">关闭</button></header><img id="large" alt="放大预览"/></dialog><script>const d=document.querySelector('dialog');document.querySelectorAll('.zoom').forEach(b=>b.onclick=()=>{{document.querySelector('#large').src=b.querySelector('img').src;document.querySelector('#caption').textContent=b.dataset.label;d.showModal()}});document.querySelector('#close').onclick=()=>d.close();d.onclick=e=>{{if(e.target===d)d.close()}};</script></body></html>'''
    (OUT/'index.html').write_text(doc,encoding='utf8')
    notes='''# 六页原生矢量 PPT：配色调整

根据“蓝色有点过曝”的反馈，降低蓝色饱和度并拉开颜色层级。

| 区域 | 调整 |
|---|---|
| 标题、关键数字、正文强调 | 原钴蓝 #2458D3 改为墨蓝 #355E78 |
| 表格表头 | #3E6278，保留白色文字 |
| 肺部和正文图标 | 按原明暗连续映射为灰蓝，保留各色面关系 |
| 波纹、底部装饰 | 进一步降低饱和度与对比，减少背景干扰 |
| 正文、纸张背景 | 炭黑 #151B24、米白 #F6F4EF |

颜色是原生对象属性，没有重新生成或矢量化图片。六页中所有文字、表格、来源备注、箭头、分组、路径顶点和位置均保留；检查确认文件仅有颜色属性发生变化，图片对象仍为0。

用本机 PowerPoint 导出六页 PNG 和 PDF，并逐页查看实际画面。此版本针对已有六页样本，没有生成50页课件，也没有修改生产模板或工作流确认状态。原版保留于 A_vector 目录。
'''
    (OUT/'color_notes.md').write_text(notes,encoding='utf8')
    with sync_playwright() as pw:
        browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1720,'height':1040})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto((OUT/'index.html').as_uri())
        page.wait_for_function("[...document.querySelectorAll('.zoom img')].every(x=>x.complete&&x.naturalWidth===1280)")
        assert page.locator('.sample').count()==6 and page.locator('.zoom img').count()==12
        page.locator('.zoom').nth(1).click();assert page.locator('dialog').is_visible();page.locator('#close').click()
        page.screenshot(path=str(OUT/'comparison-preview.png'))
        page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=390')
        assert not errors,errors
        browser.close()
    files=[p for p in OUT.iterdir() if p.is_file() and p.name not in ('color_delivery.zip','manifest.json')]
    files.extend(SOURCE/f'deck-slide{i:02d}.png' for i in range(1,7))
    dump(OUT/'manifest.json',dict(files=[dict(path=p.relative_to(BASE).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in files]))
    with zipfile.ZipFile(OUT/'color_delivery.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in files+[OUT/'manifest.json']:z.write(p,p.relative_to(BASE).as_posix())
    print(json.dumps(dict(delivery=str(OUT),slides=6,picture_objects=0,files=len(files)+1,
                          pptx_bytes=(OUT/'deck.pptx').stat().st_size,zip_bytes=(OUT/'color_delivery.zip').stat().st_size),ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['build','office','deliver'])
    a=p.parse_args();{'build':build,'office':office,'deliver':deliver}[a.command]()
