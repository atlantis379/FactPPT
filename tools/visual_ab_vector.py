"""Trace the actual A artwork into editable native Office geometry.

SVG inputs are actual Adobe image_vectorize outputs, not embedded SVG pictures.
Near-white paper grain is omitted. A controlled palette reduces patch count;
geometry is retained and grouped by spatial component for convenient editing.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
import time
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.visual_ab_test import OUT, dump, sha
from tools.visual_ab_native import native_vectors, verify_pptx, canon, CSS

FOLDER=OUT/'A_vector'


def paint_color(value, gradients):
    if value.startswith('url('):
        return gradients[value.removeprefix('url(#').removesuffix(')')]
    nums=list(map(int,re.findall(r'\d+',value)))
    if len(nums)==3:return nums
    if value.startswith('#'):
        h=value.lstrip('#');h=''.join(x*2 for x in h) if len(h)==3 else h
        return [int(h[i:i+2],16) for i in (0,2,4)]
    raise ValueError(value)


def region_name(sample,commands):
    pts=[a[1:] for a in commands if len(a)>1]
    xs=[v for a in pts for v in a[::2]];ys=[v for a in pts for v in a[1::2]]
    x=(min(xs)+max(xs))/2;y=(min(ys)+max(ys))/2
    if y>=635:return '装饰波纹'
    if sample==1:return '肺部插画' if x>=690 else '底部装饰'
    if sample==2:
        if 255<=y<=330:return '指南图标-左' if x<610 else '指南图标-右'
        if 345<=y<=535:return '编号与分隔-左' if x<610 else '编号与分隔-右'
    if sample==3:
        if 313<=y<=421:
            return '指标图标-'+str(1+sum(x>v for v in (341,650,944)))
        if 559<=y<=633:return '参考说明带'
    if sample==4:
        if y<253:return '页眉装饰'
        if 253<=y<=339:return '目标人群插画与容器'
        if 360<=y<=444:return '阈值图标与容器-'+str(1+sum(x>v for v in (447,837)))
        if 445<=y<=635:return '分支内容容器-'+str(1+sum(x>v for v in (447,837)))
    if sample==5:
        if 230<=y<=403 and x<120:return '研究背景图标'
        if 420<=y<=618 and x<125:return '定义编号'
    if sample==6:return '表格区域底色' if 170<=y<=653 else '装饰与分隔线'
    return '装饰与分隔线'


def trace(sample,step=4):
    from lxml import etree
    from fontTools.svgLib.path import parse_path
    from fontTools.pens.recordingPen import RecordingPen
    file=FOLDER/f'source{sample:02d}.svg'
    root=etree.parse(str(file)).getroot();ns='{http://www.w3.org/2000/svg}'
    assert not list(root.iter(ns+'image')),'An SVG containing an image is not a vector trace.'
    width,height=float(root.get('width')),float(root.get('height'))
    scale=(1280/width,720/height)
    gradients={}
    for g in root.iter(ns+'linearGradient'):
        colors=[paint_color(re.search(r'stop-color:\s*(.+?);',s.get('style')).group(1),{}) for s in g]
        gradients[g.get('id')]=[round(sum(c[i] for c in colors)/len(colors)) for i in range(3)]
    buckets={};dropped=0;commands_count=0;raw_count=0
    for element in root.iter(ns+'path'):
        raw_count+=1
        rgb=paint_color(element.get('fill'),gradients)
        if min(rgb)>=232 and max(rgb)-min(rgb)<=8:
            dropped+=1;continue
        # Remove paper grain while retaining the spatial geometry of blue artwork.
        rgb=[min(255,round(v/step)*step) for v in rgb] if step else rgb
        fill='#'+''.join(f'{v:02X}' for v in rgb)
        pen=RecordingPen();parse_path(element.get('d'),pen)
        cmds=[]
        for op,points in pen.value:
            if op=='endPath':continue
            tag={'moveTo':'M','lineTo':'L','curveTo':'C','qCurveTo':'Q','closePath':'Z'}[op]
            cmds.append([tag,*[round(v*scale[i],4) for pt in points for i,v in enumerate(pt)]])
        region=region_name(sample,cmds)
        key=(region,fill)
        if key not in buckets:buckets[key]=dict(commands=[],fill=fill,stroke=None,width=0,opacity=1,name=region,group=region)
        buckets[key]['commands'].extend(cmds)
        commands_count+=len(cmds)
    vectors=list(buckets.values())
    stats=dict(sample=sample,raw_paths=raw_count,paper_paths_omitted=dropped,native_color_paths=len(vectors),
               path_commands=commands_count,palette_step=step,gradient_paths_approximated=len(gradients),
               spatial_groups=sorted(set(v['group'] for v in vectors)),source_svg_sha256=sha(file))
    return vectors,stats


def vector_svg(vectors):
    from html import escape
    paths=[]
    for v in vectors:
        d=' '.join(c[0]+' '+','.join(str(n) for n in c[1:]) for c in v['commands'])
        paths.append(f'<path d="{d}" fill="{v["fill"]}"/>')
    return '<svg class="vectors" viewBox="0 0 1280 720" width="1280" height="720">'+''.join(paths)+'</svg>'


def group_artwork(path):
    from pptx import Presentation
    from pptx.oxml.ns import qn
    from pptx.util import Emu
    prs=Presentation(path)
    counts=[]
    for slide in prs.slides:
        groups=defaultdict(list)
        for sh in list(slide.shapes):
            if sh._element.find('.//'+qn('a:custGeom')) is not None and sh.name.startswith('描摹组件：'):
                groups[sh.name.rsplit(' ',1)[0]].append(sh)
        for label,shapes in groups.items():
            tree=slide.shapes._spTree
            first_index=min(list(tree).index(sh._element) for sh in shapes)
            group=slide.shapes.add_group_shape(shapes)
            group.name=label.removeprefix('描摹组件：')
            group.shadow.inherit=False
            tree.remove(group._element);tree.insert(first_index,group._element)
        counts.append({k:len(v) for k,v in groups.items()})
    prs.save(path)
    return counts


def native_texts(slide):
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    out=[]
    def visit(shapes):
        for s in shapes:
            if s.shape_type==MSO_SHAPE_TYPE.GROUP:visit(s.shapes)
            else:
                if s.has_text_frame and s.text.strip():out.append(canon(s.text))
                if s.has_table:out.extend(canon(c.text) for row in s.table.rows for c in row.cells)
    visit(slide.shapes)
    return sorted(out)


def build(samples):
    from playwright.sync_api import sync_playwright
    from factdeck.render import build_pptx
    from pptx import Presentation
    from lxml import html as lh
    start=time.perf_counter()
    pages=json.loads((OUT/'content_lock.json').read_text(encoding='utf8'))['pages']
    models=json.loads((OUT/'A'/'measured_layout.json').read_text(encoding='utf8'))
    overlays=json.loads((OUT/'A'/'vector_geometry.json').read_text(encoding='utf8'))
    document=lh.fromstring((OUT/'A'/'deck.html').read_text(encoding='utf8'))
    all_slides=document.xpath('//section')
    vectors=[];stats=[];selected_models=[];sections=[]
    for i in samples:
        v,s=trace(i)
        for x in v:x['name']='描摹组件：'+x['group']
        v.extend(copy.deepcopy(overlays[i-1]))
        vectors.append(v);stats.append(s)
        m=copy.deepcopy(models[i-1]);m['rasters']=[];selected_models.append(m)
        section=copy.deepcopy(all_slides[i-1]);section.set('id',f'v{i}')
        for image in section.xpath('.//img'):image.getparent().remove(image)
        for oldsvg in section.xpath('.//*[local-name()="svg" and @class="vectors"]'):oldsvg.getparent().remove(oldsvg)
        section.insert(0,lh.fromstring(vector_svg(v)))
        # The semantic connector layer and locked text remain unchanged.
        sections.append(lh.tostring(section,encoding='unicode'))
    prefix='prototype' if len(samples)!=6 else 'deck'
    out=FOLDER/f'{prefix}.pptx'
    build_pptx(selected_models,{},[pages[i-1]['notes'] for i in samples],out,title='A 原图描摹：全原生矢量')
    native_vectors(out,vectors)
    groupcounts=group_artwork(out)
    prs=Presentation(out);reference=Presentation(OUT/'A'/'deck.pptx')
    assert all(native_texts(s)==native_texts(reference.slides[i-1]) for s,i in zip(prs.slides,samples))
    assert all(s.notes_slide.notes_text_frame.text==pages[i-1]['notes'] for s,i in zip(prs.slides,samples))
    def pics(shapes):
        return sum(pics(s.shapes) if s.shape_type==6 else int(s.shape_type==13) for s in shapes)
    assert sum(pics(s.shapes) for s in prs.slides)==0
    html_file=FOLDER/f'{prefix}.html'
    html_file.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>'+CSS+'</style><body>'+''.join(sections)+'</body></html>',encoding='utf8')
    with sync_playwright() as pw:
        b=pw.chromium.launch();web=b.new_page(viewport={'width':1280,'height':720})
        web.goto(html_file.as_uri());web.evaluate('document.fonts.ready')
        for j,i in enumerate(samples,1):web.locator(f'#v{i}').screenshot(path=str(FOLDER/f'{prefix}-browser{j:02d}.png'))
        b.close()
    result=dict(samples=samples,build_seconds=round(time.perf_counter()-start,3),pptx_bytes=out.stat().st_size,
                picture_objects=0,locked_text_exact=True,source_notes_exact=True,pages=stats,groups=groupcounts,
                limitations=['近白纸张颗粒省略；颜色按4级量化。','极少量渐变用平均色近似。','空间归组不是原始设计图层的精确恢复；相交的颜色区域可能属于同一轮廓。'])
    dump(FOLDER/f'{prefix}-verification.json',result)
    dump(FOLDER/f'{prefix}-geometry.json',vectors)
    print(json.dumps(result,ensure_ascii=False,indent=2))


def office(samples):
    import win32com.client,pythoncom
    pythoncom.CoInitialize();app=win32com.client.DispatchEx('PowerPoint.Application')
    prefix='prototype' if len(samples)!=6 else 'deck'
    start=time.perf_counter();p=app.Presentations.Open(str(FOLDER/f'{prefix}.pptx'),ReadOnly=True,WithWindow=False)
    editing=[]
    try:
        for i in range(1,len(samples)+1):p.Slides(i).Export(str(FOLDER/f'{prefix}-slide{i:02d}.png'),'PNG',1280,720)
        p.SaveAs(str(FOLDER/f'{prefix}.pdf'),32)
        for i in range(1,len(samples)+1):
            slide=p.Slides(i)
            groups=[slide.Shapes(j) for j in range(1,slide.Shapes.Count+1) if slide.Shapes(j).Type==6]
            assert groups
            group=max(groups,key=lambda g:g.GroupItems.Count)
            oldleft=group.Left;group.Left=oldleft+5;assert abs(group.Left-oldleft-5)<.2;group.Left=oldleft
            leaves=[group.GroupItems(j) for j in range(1,group.GroupItems.Count+1)]
            shape=max(leaves,key=lambda s:s.Nodes.Count)
            assert shape.Nodes.Count>0
            oldcolor=shape.Fill.ForeColor.RGB;shape.Fill.ForeColor.RGB=0x228B22
            assert shape.Fill.ForeColor.RGB==0x228B22;shape.Fill.ForeColor.RGB=oldcolor
            points=shape.Nodes.Item(1).Points;xx,yy=points[0]
            shape.Nodes.SetPosition(1,xx+1,yy+1)
            changed=shape.Nodes.Item(1).Points[0]
            assert abs(changed[0]-xx-1)<.2 and abs(changed[1]-yy-1)<.2
            shape.Nodes.SetPosition(1,xx,yy)
            editing.append(dict(sample=samples[i-1],component_groups=len(groups),
                                tested_group=group.Name,group_move=True,fill_recolor=True,
                                contour_node_edit=True,tested_nodes=shape.Nodes.Count))
    finally:p.Close();app.Quit();pythoncom.CoUninitialize()
    result=dict(render_and_edit_check_seconds=round(time.perf_counter()-start,3),samples=samples,editability=editing)
    dump(FOLDER/f'{prefix}-office.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


def download(samples):
    import requests
    receipts=json.loads((FOLDER/'vector_receipts.json').read_text(encoding='utf8'))
    for i in samples:
        target=FOLDER/f'source{i:02d}.svg'
        if target.exists() and target.stat().st_size>100:continue
        r=next(x for x in receipts['calls'] if x['sample']==f'sample{i:02d}.png')
        url=r['result']['results'][0]['assets'][0]['presignedAssetUrl']
        response=requests.get(url,timeout=45);response.raise_for_status()
        assert len(response.content)<70_000_000
        target.write_bytes(response.content)
        print(f'Downloaded source{i:02d}.svg: {len(response.content)} bytes',flush=True)


def deliver(_samples=None):
    """Verify and package the six-page vector study without changing workflow state."""
    import html
    from lxml import html as lh
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    from pypdf import PdfReader
    from playwright.sync_api import sync_playwright

    lock=json.loads((OUT/'content_lock.json').read_text(encoding='utf8'))
    build_record=json.loads((FOLDER/'deck-verification.json').read_text(encoding='utf8'))
    office_record=json.loads((FOLDER/'deck-office.json').read_text(encoding='utf8'))
    receipts=json.loads((FOLDER/'vector_receipts.json').read_text(encoding='utf8'))
    assert build_record['samples']==[1,2,3,4,5,6]
    prs=Presentation(FOLDER/'deck.pptx');original=Presentation(OUT/'A'/'deck.pptx')
    assert len(prs.slides)==6 and len(PdfReader(FOLDER/'deck.pdf').pages)==6
    content_checks=verify_pptx(FOLDER/'deck.pptx',lock['pages'])

    def leaves(shapes):
        for s in shapes:
            if s.shape_type==MSO_SHAPE_TYPE.GROUP:yield from leaves(s.shapes)
            else:yield s

    slide_checks=[]
    for i,(slide,ref,p) in enumerate(zip(prs.slides,original.slides,lock['pages']),1):
        assert native_texts(slide)==native_texts(ref)
        assert slide.notes_slide.notes_text_frame.text==p['notes']
        objects=list(leaves(slide.shapes))
        assert not any(s.shape_type==MSO_SHAPE_TYPE.PICTURE for s in objects)
        assert (FOLDER/f'deck-slide{i:02d}.png').is_file()
        assert all(office_record['editability'][i-1][k] for k in ('group_move','fill_recolor','contour_node_edit'))
        slide_checks.append(dict(sample=i,original_page=p['original_page'],
                                 native_leaf_objects=len(objects),picture_objects=0,
                                 text_exact_to_A=True,source_notes_exact=True,
                                 actual_powerpoint_edit_check=True))
    with zipfile.ZipFile(FOLDER/'deck.pptx') as z:
        assert not any(n.startswith('ppt/media/') for n in z.namelist())
    paths=sum(p['native_color_paths'] for p in build_record['pages'])
    seconds=sum(r['seconds'] for r in receipts['calls'])
    cost=dict(vector_calls=len(receipts['calls']),vector_retries=0,
              vector_tool_seconds_sum=round(seconds,3),
              build_seconds=build_record['build_seconds'],
              powerpoint_render_and_edit_check_seconds=office_record['render_and_edit_check_seconds'],
              pptx_bytes=(FOLDER/'deck.pptx').stat().st_size,pdf_bytes=(FOLDER/'deck.pdf').stat().st_size,
              scope='additional to the existing A study; tool latency sums are not end-to-end wall time',
              actual_monetary_cost=None,production_server_load_test=False)
    dump(FOLDER/'cost.json',cost)
    differences=[
        '肺部轮廓、细密分支和波纹保留为原生路径；连续的水彩明暗变成多个色面，近白纸张颗粒省略。',
        '指南图标、编号与分隔线可编辑；双栏文字和来源与 A 完全相同，纸张颗粒及浅色细节减少。',
        '四项指标图标与参考说明带拆为原生路径；数字、单位、比较符号与限定条件沿用 A 原生文字。',
        '阈值图标、容器与装饰拆分；医学流程仍使用冻结原页支持的7条原生箭头，低分支没有新增后续箭头。',
        '研究背景图标、定义编号及波纹可编辑；41.6%与全部研究条件保持原生，浅色纹理简化。',
        '表体仍是可逐格修改的原生表格；底色与波纹成为原生路径，全部36个事实单元格保持一致。',
    ]
    page_rows='\n'.join(f'| {p["sample"]} / 原{lock["pages"][p["sample"]-1]["original_page"]}页 | {p["native_color_paths"]} | {len(p["spatial_groups"])} | {differences[p["sample"]-1]} |' for p in build_record['pages'])
    file_rows='\n'.join(f'| {label} | {file.stat().st_size/1048576:.2f} MiB | {pictures} |' for label,file,pictures in [('A 原版',OUT/'A/deck.pptx',6),('A 原生矢量拆分版',FOLDER/'deck.pptx',0),('B 原生重绘版',OUT/'B/deck.pptx',0)])
    report=f'''# A 原生矢量拆分版：六页实测

## 结果与使用

按用户要求“所有图形都变成原生矢量，可改轮廓和颜色；允许部分纹理细节损失”，已将六页 A 的实际底图描摹为 Office 原生自由曲线，并保留 A 的原生文字、表格、来源备注和医学连接关系。

- [六页 PPTX](deck.pptx)、[PowerPoint PDF](deck.pdf)、[A 原版 / A 矢量拆分 / B 对照](index.html)。
- 文件中图片对象为0，`ppt/media/`中无图片；SVG只作为路径转换输入，没有嵌入为图片。PPTX 为{cost['pptx_bytes']/1048576:.2f} MiB。
- 肺部、波纹、图标、编号与容器按位置归组。选中组可移动；进入组或取消组合后可选中色面，修改填充色，用“编辑顶点”改变轮廓。文字和表格按常规方式编辑。
- 已在本机 PowerPoint 对每页实际测试一个组件组的移动、一个路径的填色和顶点修改，全部成功；测试后恢复原状，交付文件未保存这些试验改动。这些是抽样编辑测试，未逐个操作全部路径。

## 保真与限制

这次是在 A 的实际去字底图上描摹轮廓，保留了比 B 手工简化图形更多的细节。六页已经逐页查看 PowerPoint 实际导出的画面，未见影响阅读的文字溢出或遮挡。浏览器与 PowerPoint 的字体边缘、换行和路径显示仍可能有差异；对照页默认显示 PowerPoint 交付画面。

近白纸张颗粒省略；颜色以4步长量化；5个 SVG 渐变定义用平均填色近似。水彩过渡变得更像色块，微粒和局部浅色边界有损失。**可编辑并不意味着无损还原原图。**

空间归组是根据画面位置建立的组件，不是恢复了生成图原有的设计图层。同一颜色的碎片在同一区域合并为复合路径；部分波纹或相交轮廓可能连在同一路径中。进入组件后仍有很多色面，精细修改的操作量较大。尚未实现通用的语义分层、一键换主题或自动判断医学图形含义。

| 样本 | 原生描摹路径 | 组件组 | 逐页差异 |
|---|---|---|---|
{page_rows}

描摹路径共{paths}个，另有原生文字、表格、遮罩和关系图形。B 六页共326个顶层对象，更适合大范围修改版式与图形。封面肺部包含634个颜色路径，移动整个肺部很方便，但改局部分支仍需进入组选择路径。

## 内容与对象检查

沿用冻结的实际 `output/deck_full` 原页1、4、17、22、30、47。逐页回读71条事实、36个表格事实单元格、作者标题、来源短注、页码和全部来源备注；A 矢量版与 A 原生文本完全一致。数字、单位、比较符号、上标、限定条件及范围保持不变，未通过删减内容提升观感。

医学流程保留冻结原页的7条支持关系；低阈值分支没有新增后续箭头。全部文字和表格为原生对象，所有图形为原生形状或连接线。本次检查是冻结输出到重建稿的保真检查，没有重新独立审查全部原始医学证据，也没有写入医学、客户或页面审批状态。

## 额外调用和执行耗时

| 阶段 | 本次新增量 / 耗时 |
|---|---|
| 矢量化工具 | {len(receipts['calls'])}次，重试0次 |
| 六次工具响应耗时之和 | {seconds:.3f}秒 |
| 六页路径转换、原生导出及浏览器预览 | {build_record['build_seconds']:.3f}秒 |
| PowerPoint PNG、PDF及编辑测试 | {office_record['render_and_edit_check_seconds']:.3f}秒 |
| 新增生图 | 0次，复用已保存的 A 底图 |

| 路线 | PPTX 大小 | 图片对象 |
|---|---|---|
{file_rows}

原 A 制作的13次生图调用仍是前置成本，完整设计稿与去字耗时合计786.907秒；此前放弃的5次底图探索另计。此次新增6次矢量化调用不能当作完整制作成本。并行调用的响应耗时之和不是实际经过时间。下载连接曾失败，重试下载了已生成文件，没有重新发起矢量化。

没有真实费用数据，只报告调用量。上述时间不含设计拆解、代码编写、模型推理和人工审阅；没有测量生产服务器的并发能力、内存峰值或编辑器交互延迟，不能据此计算 SaaS 吞吐量。

## 适用范围与后续判断

- A 矢量拆分适合保留插画轮廓和精细装饰、同时需要局部改色或形状的页面。封面和图标页能保留更多原图细节。
- 表格、流程、文字对照仍应由内容约束下的原生对象表达；描摹用于视觉元素，医学连接关系继续使用经过内容核对的独立连接线。
- 高频编辑与批量套版更适合少量清晰的原生组件。大量颜色路径可作为最终视觉素材，但它们的编辑复杂度高于 B。
- 当前证明可以把这六页 A 转为全原生矢量；进入主线前仍需验证不同图像的分层稳定性、路径压缩和重复制作成本。六页不直接推广到整套课件。

用户此前整体偏好 A，原话“方案A明显更加的精致”。用户尚未对新矢量版给出审美结论；不把对象检查或路径数换算为审美评分。

## 文件与复现

`deck.pptx/pdf`、`deck-slideNN.png`是实际交付；`deck.html`和`deck-browserNN.png`用于浏览器对照。`sourceNN.svg`是实际矢量化输出；`vector_receipts.json`保留工具回执与耗时。`deck-geometry.json`记录转换后的原生路径；`deck-verification.json`、`deck-office.json`和`release-verification.json`记录检查，`cost.json`记录新增成本，`manifest.json`记录交付文件校验值。

独立入口为 `python tools/visual_ab_vector.py build --samples 1 2 3 4 5 6` → `office --samples 1 2 3 4 5 6` → `deliver`。复现使用已保存的矢量文件和 A 的测量布局，脚本不重新调用生图或矢量化。PowerPoint 阶段需要本机 PowerPoint 与 pywin32。

本次仅增加实验输出与独立工具，没有增加生产 API、改变现有模板或更新工作流确认及交付状态。
'''
    (FOLDER/'report.md').write_text(report,encoding='utf8')
    # Reuse the existing experiment's visual shell.
    prior=(OUT/'index.html').read_text(encoding='utf8')
    css=re.search(r'<style>(.*?)</style>',prior,re.S).group(1)
    cards=[]
    for p,diff in zip(lock['pages'],differences):
        i=p['sample'];nn=f'{i:02d}'
        columns=[]
        for route,label,src,websrc in [('A','A 原版',f'../A/slide{nn}.png',f'../A/browser{nn}.png'),('V','A 原生矢量拆分',f'deck-slide{nn}.png',f'deck-browser{nn}.png'),('B','B 原生重绘',f'../B/slide{nn}.png',f'../B/browser{nn}.png')]:
            columns.append(f'<figure><figcaption>{label}</figcaption><button class="zoom" data-label="样本{i} · {label}"><img src="{src}" data-office="{src}" data-browser="{websrc}" alt="样本{i} {label}" loading="lazy"/></button></figure>')
        cards.append(f'''<section id="sample{i}" class="sample"><header><span class="number">{nn}</span><div><h2>{html.escape(p['kind'])}</h2><p>原课件第{p['original_page']}页 · 点击画面放大</p></div><button class="reference" data-src="../designs/sample{nn}.png" data-label="样本{i} · 完整生图设计参考（内容以冻结输入为准）">查看完整设计稿</button></header><div class="columns">{''.join(columns)}</div><p class="difference">{html.escape(diff)}</p><div class="feedback"><label>本页偏好 <select data-pref="{i}"><option value="">尚未评价</option><option value="A">A 原版</option><option value="V">A 原生矢量</option><option value="B">B 原生重绘</option><option value="neither">均未达标</option></select></label><input data-note="{i}" aria-label="样本{i}评价理由" placeholder="专业感、焦点、阅读顺序、密度、一致性或编辑体验"/></div></section>''')
    js='''const key='factppt-a-vector-review-v1';let state={};try{state=JSON.parse(localStorage.getItem(key)||'{}')}catch(e){}document.querySelectorAll('[data-pref],[data-note]').forEach(el=>{const i=el.dataset.pref||el.dataset.note,k=el.dataset.pref?'preference':'note';el.value=state[i]?.[k]||'';el.onchange=()=>{state[i]??={};state[i][k]=el.value;try{localStorage.setItem(key,JSON.stringify(state))}catch(e){}document.querySelector('#status').textContent='评价保存在当前浏览器，可导出留存'}});const d=document.querySelector('dialog');document.querySelectorAll('.zoom,.reference').forEach(b=>b.onclick=()=>{document.querySelector('#large').src=b.querySelector('img')?.src||b.dataset.src;document.querySelector('#caption').textContent=b.dataset.label;d.showModal()});document.querySelector('#close').onclick=()=>d.close();d.onclick=e=>{if(e.target===d)d.close()};document.querySelector('#preview').onchange=e=>document.querySelectorAll('.zoom img').forEach(im=>im.src=im.dataset[e.target.value]);document.querySelector('#export').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({experiment:'a-vector-six-page',criteria:['专业感','焦点','阅读顺序','密度','一致性','编辑体验'],pages:state},null,2)],{type:'application/json'}));a.download='a_vector_preferences.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};'''
    webpage=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>A 原版与原生矢量拆分 · 六页对照</title><style>{css}</style></head><body><main class="wrap"><div class="eyebrow">FACTPPT · VECTOR STUDY</div><h1>保留 A 的构图，将图形转成原生矢量</h1><p class="intro">六页相同内容，对照 A 原版、A 原生矢量拆分和 B 原生重绘。新版本没有图片对象，组件可移动，路径可改色及编辑顶点；纸张颗粒、连续渐变和部分浅色细节有损失。默认展示 PowerPoint 实际交付画面。请结合视觉偏好与实际编辑体验判断。</p><div class="links"><a href="deck.pptx" download>A 矢量 · PPTX</a><a href="deck.pdf">A 矢量 · PDF</a><a href="../A/deck.pptx" download>A 原版 · PPTX</a><a href="../B/deck.pptx" download>B · PPTX</a><a href="report.md">实测报告</a><a href="../visual_ab_vector_delivery.zip" download>完整交付包</a></div><div class="toolbar"><label>画面 <select id="preview"><option value="office">PowerPoint 交付画面</option><option value="browser">浏览器排版预览</option></select></label><button id="export">导出我的评价</button><span id="status">新矢量版尚未评价</span><nav>{''.join(f'<a href="#sample{i}">{i:02d}</a>' for i in range(1,7))}</nav></div>{''.join(cards)}<footer>此前整体视觉偏好：A。此次要求：所有图形原生矢量，可改轮廓与颜色，允许部分纹理损失。<br/>空间组件为近似归组；每页均已抽样验证移动、填色和顶点编辑。新版本审美结论由用户评价。</footer></main><dialog><header><span id="caption"></span><button id="close">关闭</button></header><img id="large" alt="放大预览"/></dialog><script>{js}</script></body></html>'''
    (FOLDER/'index.html').write_text(webpage,encoding='utf8')
    doc=lh.fromstring(webpage)
    links=[s for s in doc.xpath('//@src|//@href|//@data-office|//@data-browser|//@data-src') if not s.startswith('#')]
    package=OUT/'visual_ab_vector_delivery.zip'
    assert all((FOLDER/s).is_file() or (FOLDER/s).resolve()==package for s in links)
    with sync_playwright() as pw:
        browser=pw.chromium.launch();web=browser.new_page(viewport={'width':1920,'height':1080})
        errors=[];web.on('pageerror',lambda err:errors.append(str(err)))
        web.goto((FOLDER/'index.html').as_uri())
        web.evaluate("document.querySelectorAll('.zoom img').forEach(x=>x.loading='eager')")
        web.wait_for_function("[...document.querySelectorAll('.zoom img')].every(x=>x.complete&&x.naturalWidth===1280)")
        assert web.locator('.sample').count()==6 and web.locator('.zoom img').count()==18
        web.locator('.zoom').nth(1).click();assert web.locator('dialog').is_visible()
        assert 'deck-slide01.png' in web.locator('#large').get_attribute('src')
        web.locator('#close').click();web.locator('.reference').first.click()
        assert '完整生图' in web.locator('#caption').inner_text();web.locator('#close').click()
        web.locator('#preview').select_option('browser')
        web.wait_for_function("[...document.querySelectorAll('.zoom img')].every(x=>x.complete&&x.naturalWidth===1280)")
        assert web.locator('.zoom img').nth(1).get_attribute('src')=='deck-browser01.png'
        web.locator('#preview').select_option('office')
        web.locator('[data-pref="1"]').select_option('V');web.reload()
        assert web.locator('[data-pref="1"]').input_value()=='V'
        web.evaluate('localStorage.removeItem("factppt-a-vector-review-v1")');web.reload()
        web.screenshot(path=str(FOLDER/'comparison-preview.png'))
        web.set_viewport_size({'width':390,'height':844})
        assert web.evaluate('document.documentElement.scrollWidth<=390')
        assert not errors,errors
        browser.close()
    release=dict(status='passed',checked_utc=datetime.now(timezone.utc).isoformat(),
                 source_hashes=lock['source_hashes'],slides=slide_checks,content_checks=content_checks,
                 all_native_text_exact_to_A=True,all_source_notes_exact=True,
                 picture_objects=0,ppt_media_files=0,pdf_pages=6,
                 native_traced_paths=paths,comparison_pages=6,comparison_images=18,
                 comparison_zoom=True,reference_zoom=True,preview_switch=True,
                 preference_persistence=True,mobile_no_horizontal_overflow=True,
                 user_preference_for_new_variant=None,production_state_changed=False)
    dump(FOLDER/'release-verification.json',release)
    files=[p for p in FOLDER.iterdir() if p.is_file() and not p.name.startswith(('prototype','~$')) and p.name!='manifest.json']
    for folder in ('A','B','designs','clean_backgrounds','prompts','receipts'):
        files.extend(p for p in (OUT/folder).iterdir() if p.is_file() and not p.name.startswith('~$'))
    files.extend(OUT/name for name in ('content_lock.json','design_spec.json','experiment_cost.json','generation_receipts.json','build_verification.json','visual_review.json','office_render.json'))
    records=[dict(path=p.relative_to(OUT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(files)]
    dump(FOLDER/'manifest.json',dict(created_utc=datetime.now(timezone.utc).isoformat(),source_hashes=lock['source_hashes'],files=records))
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files+[FOLDER/'manifest.json']:z.write(p,p.relative_to(OUT).as_posix())
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        for r in records:
            import hashlib
            assert hashlib.sha256(z.read(r['path'])).hexdigest()==r['sha256']
    print(json.dumps(dict(status='passed',package=str(package),files=len(files)+1,
                          package_bytes=package.stat().st_size,native_traced_paths=paths,
                          picture_objects=0,cost=cost),ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['build','office','download','deliver'])
    parser.add_argument('--samples',nargs='+',type=int,default=[1,3])
    a=parser.parse_args();{'build':build,'office':office,'download':download,'deliver':deliver}[a.command](a.samples)
