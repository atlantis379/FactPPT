"""Copy a completed, current A render into a read-only human review package.

This command never records content, style or page approval in the workflow.
"""
from __future__ import annotations
import argparse
import hashlib
import html
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.deck_generation import view
from app.deckflow import render_current
from factdeck.visual_layout import text_of


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package(workflow_id,out):
    database=ROOT/'data/deckflow/workflow.sqlite3'
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
        row=db.execute('SELECT state FROM workflows WHERE id=?',(workflow_id,)).fetchone()
    if not row: raise ValueError('Workflow does not exist')
    w=json.loads(row[0]); g=w.get('generation'); r=w.get('render')
    if not g or g['render']['status']!='COMPLETE' or not render_current(w):
        raise ValueError('Current A render is not complete; an old draft must not be packaged')
    if r.get('route')!='A_NATIVE_VECTOR' or [p['id'] for p in r['pages']]!=[p['id'] for p in g['pages']]:
        raise ValueError('Render route or page scope differs from the selected generation')
    total=(g.get('scope') or {}).get('total_pages',len(w['deck']['result']['pages']))
    out=out.resolve()
    if not out.is_relative_to(ROOT/'output'): raise ValueError('Review output must stay in this project output directory')
    out.mkdir(parents=True,exist_ok=True)
    source=(ROOT/'data/deckflow'/r['path']).resolve()
    if not source.is_relative_to(ROOT/'data/deckflow'): raise ValueError('Invalid render path')
    for name,sha in r['files'].items():
        if checksum(source/name)!=sha: raise ValueError('Render file changed: '+name)
    report=json.loads((source/'render_report.json').read_text(encoding='utf8'))
    if report['hard_errors'] or report['summary']['content_mismatch']:
        raise ValueError('Render did not pass locked-content checks')
    for name in ('deck.pptx','deck.pdf','deck.html','render_report.json','native_model.json'):
        shutil.copy2(source/name,out/name)
    native=json.loads((source/'native_model.json').read_text(encoding='utf8'))
    fonts=sorted({run.get('font',g['font']) for model in native['models']
                  for obj in model['texts']+[c for table in model['tables'] for row in table['rows'] for c in row['cells']]
                  for para in obj['paras'] for run in para})
    pages=[]; panels=[]
    for i,(page,render_page,checks) in enumerate(zip(g['pages'],r['pages'],report['slides']),1):
        if checksum(source/render_page['file'])!=render_page['sha256']: raise ValueError('Page image changed')
        shutil.copy2(source/render_page['file'],out/render_page['file'])
        shutil.copy2(source/f'browser-slide{i:02d}.png',out/f'browser-slide{i:02d}.png')
        assets=out/'assets'/f'{i:02d}-{page["id"]}';assets.mkdir(parents=True,exist_ok=True)
        for kind,asset in page['assets'].items():
            original=(ROOT/'data/deckflow'/asset['path']).resolve()
            if not original.is_relative_to(ROOT/'data/deckflow') or checksum(original)!=asset['sha256']:
                raise ValueError('Visual asset changed: '+page['id']+'/'+kind)
            shutil.copy2(original,assets/(kind+('.svg' if kind=='vector' else '.png')))
            save(assets/(kind+'_receipt.json'),asset['receipt'])
        save(assets/'layout.json',page['layout'])
        save(assets/'design_notes.json',page['lock']['design'])
        (assets/'source_notes.txt').write_text(page['lock']['notes'],encoding='utf8')
        model=page['lock']['model']
        locked_text=[text_of(t) for t in model['texts']]+[text_of(c) for t in model['tables'] for row in t['rows'] for c in row['cells']]
        pages.append({'page':i,'id':page['id'],'png':render_page['file'],'png_sha256':render_page['sha256'],
                      'locked_text_sha256':hashlib.sha256(json.dumps(locked_text,ensure_ascii=False).encode()).hexdigest(),
                      'native_paths':checks['vector']['native_paths'],'human_review':'PENDING'})
        base='assets/'+assets.name
        esc=lambda v:html.escape(str(v))
        title=next((text_of(t) for t in model['texts'] if t.get('role')=='title'),page['id'])
        panels.append(f'<article id="p{i}"><h2>{i:02d} · {esc(title)}</h2><div class="cols"><figure><figcaption>完整设计参考（生成文字不作为事实）</figcaption><a href="{base}/design.png"><img loading="lazy" src="{base}/design.png"></a></figure><figure><figcaption>实际 PowerPoint · 原生矢量＋锁定文字</figcaption><a href="{render_page["file"]}"><img loading="lazy" src="{render_page["file"]}"></a></figure></div><p class="muted">原生路径 {checks["vector"]["native_paths"]}；内容回读一致；逐页人工审核待完成。</p><details><summary>设计说明与完整来源备注</summary><pre>{esc(json.dumps(page["lock"]["design"],ensure_ascii=False,indent=2))}</pre><pre>{esc(page["lock"]["notes"])}</pre></details><details><summary>浏览器与 PowerPoint 对照</summary><a href="browser-slide{i:02d}.png">浏览器逐页预览</a> · <a href="{base}/clean.png">实际去字稿</a> · <a href="{base}/vector.svg">实际描摹 SVG</a></details></article>')
    provenance=view(w)
    save(out/'generation_provenance.json',provenance)
    inspection_path=out/'visual_inspection.json'
    inspection=json.loads(inspection_path.read_text(encoding='utf8')) if inspection_path.exists() else {'status':'PENDING_EXECUTION_INSPECTION','pages':[]}
    if inspection.get('pages') and [(p['page'],p['png_sha256']) for p in inspection['pages']]!=[(p['page'],p['png_sha256']) for p in pages]:
        inspection={'status':'PENDING_EXECUTION_INSPECTION','pages':[],'reason':'Previous inspection hashes differ from this export'}
    manifest={'workflow_id':workflow_id,'generation_id':g['id'],'route':g['route'],'created_at':datetime.now(timezone.utc).isoformat(),
              'render_input_sha256':r['input_sha256'],'scope':g.get('scope'),'complete_deck':r['complete_deck'],
              'facts_sha256':w['facts']['result_sha256'],'deck_sha256':w['deck']['result_sha256'],
              'content_approval':w['content_approval'],'semantic_reviewer':w['semantic_review']['reviewer'],
              'files':r['files'],'fonts':fonts,'pages':pages,'execution_inspection':inspection,
              'style_approval':'PENDING','page_reviews':'PENDING','workflow_updated':False}
    save(out/'review_manifest.json',manifest)
    cost=provenance['cost']; summary=report['summary']
    cost_audit=json.loads((out/'cost_ledger.json').read_text(encoding='utf8')) if (out/'cost_ledger.json').exists() else {}
    sizes={name:(out/name).stat().st_size for name in ('deck.pptx','deck.pdf')}
    markdown=f'''# 前{len(pages)}页 A 原生矢量版实测报告

生成批次：`{g['id']}`。本次范围是全套{total}页中的前{len(pages)}页；其余页面未计为已完成。

## 文件与审核状态

- `deck.pptx`：{sizes['deck.pptx']:,} 字节。
- `deck.pdf`：{sizes['deck.pdf']:,} 字节，实际 Microsoft PowerPoint 输出。
- `{len(pages)}` 张逐页 PowerPoint PNG、浏览器预览、完整设计稿、去字稿、实际SVG和任务回执已存档。
- 原内容确认及人工页面语义复核保持有效；最终风格与逐页人工画面审核待完成。本工具没有写入任何审核通过或交付状态。

## 程序与实际 PowerPoint 检查

| 检查 | 结果 |
|---|---|
| 原生文字、表格单元格与来源备注回读 | 不一致 {summary['content_mismatch']} |
| 生成图形图片对象 | {summary['generated_picture_objects']} |
| 可编辑原生路径 | {summary['native_paths']:,} |
| 浏览器内容溢出 / 对象重叠 | {summary['overflow']} / {summary['overlap']} |
| 实际 PowerPoint 渲染 | {len(report['office']['editability'])}页 |
| 实际 PowerPoint 文本框字形边界 | {sum(c['text_boxes_measured'] for c in report['office'].get('text_bounds',[]))}个已检查；未处理溢出 {sum(len(c['overflow']) for c in report['office'].get('text_bounds',[]))} |
| 组移动、路径改色和顶点编辑 | 每页实际验证通过 |
| 本次导出 | {report['seconds']}秒，其中Office {report['office']['seconds']}秒 |

## 视觉与编辑边界

保留米白、炭黑和低饱和蓝灰的设计语言。正文、表格和来源由锁定内容填回；医学连接关系按来源支持重建。图形是可修改颜色和轮廓的PowerPoint原生路径，实际SVG仅作为转换输入存档。

本机实际使用字体：{', '.join(fonts)}。PPT未嵌入字体；跨设备编辑需具备这些字体并复核换行，PDF保留本次实际导出的外观。

描摹会减少纸张颗粒与细纹；部分渐变以平均色近似，颜色量化会减少色阶。复杂路径比手工绘制的简单图标更难逐点修改。组件按区域归组，重叠插画的语义拆分仍有限。设计参考与原生成品的差异应看逐页对照，不以自动分数判定审美。

Office实际字体度量引起的局部文字容量调整共{len(report['office'].get('fontmetric_adjustments',[]))}处；仅在空白内补足最多16px文本框宽度，原文、字号和位置不变。最终PPT、PDF、PNG及浏览器预览使用相同调整，明细见 `render_report.json`。独立数字或不换行文字的小幅字形外沿单独记录。

紧凑粗体标题孤字修正共{sum(len(p.get('typographic_adjustments',[])) for p in report['slides'])}处；依据真实逐字测量，在原字号10%以内微调且不低于20px，保留全部文字及原框位置。该微调独立记录，不属于医学内容修订。

## 调用量与效率

| 应用存档口径 | 数值 |
|---|---|
| 当前与修订历史去重后的已接受工具调用 | {cost['accepted_tool_calls']} |
| 执行任务领取尝试 / 重试 | {cost['task_attempts']} / {cost['retry_attempts']} |
| 已知工具等待耗时合计 | {cost['reported_tool_seconds']}秒 |
| 耗时未知的真实调用 | {cost['unknown_tool_timings']} |
| 当前视觉素材大小 | {cost['asset_bytes']:,}字节 |

费用没有供应商账单依据，人民币金额未知。工具等待合计含排队且并发时可重叠，不能作为整套实际历时。应用计数包含已接受资产和其修订存档；未接受的真实失败/返工调用须参照执行端补充账本，不能把任务尝试当成生图次数。

本地实际调用回执和执行端记录按工具调用标识去重，共记录{cost_audit.get('recorded_distinct_actual_calls','尚未汇总')}次（ImageGen {cost_audit.get('tool_counts',{}).get('image_gen','—')}、Adobe {cost_audit.get('tool_counts',{}).get('adobe_image_vectorize','—')}），其中应用接受52次。账本另标出11次本地成功返回但未提交／失败／替代记录；另有响应中断和历史元数据覆盖，因此实际调用下界仍可能漏记，不给出费用估算。执行等待合计{cost_audit.get('recorded_tool_wait_seconds','—')}秒含重叠与排队；完整时间段含等待和人工暂停，不能当作有效生产耗时。

本次采用协调agent＋3个页面agent，一端一页一个租约；程序独立续约，ImageGen并发1、Adobe并发2、浏览器并发1、PowerPoint串行。增加agent主要重叠布局、检查、下载和矢量化的等待；不据此宣称3倍加速或推算50页费用。
'''
    (out/'report.md').write_text(markdown,encoding='utf8')
    nav='　'.join(f'<a href="#p{i}">{i:02d}</a>' for i in range(1,len(pages)+1))
    css='body{max-width:1500px;margin:30px auto;padding:0 24px;font:16px/1.65 Microsoft YaHei,sans-serif;color:#151B24;background:#F6F4EF}h1{font-size:30px}h2{font-size:24px;color:#355E78}article{background:white;border:1px solid #d5dce0;padding:22px;margin:26px 0;border-radius:8px}.cols{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}figure{margin:0}figcaption{padding:8px 0;color:#355E78}img{width:100%;display:block}pre{white-space:pre-wrap;font:14px/1.6 Microsoft YaHei}.notice{padding:20px;background:#e8eef1}.muted{font-size:14px;color:#617180}a{color:#355E78}details{margin-top:14px}@media(max-width:850px){.cols{grid-template-columns:1fr}}'
    page=f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>前{len(pages)}页原生矢量成品审核</title><style>{css}</style><h1>前{len(pages)}页 · A 原生矢量版</h1><div class="notice">这是实际PowerPoint导出的画面。已确认的内容保持锁定；本次等待最终风格及逐页人工画面审核。点击图片查看全尺寸。<br>最终范围为{total}页中的前{len(pages)}页。</div><p><a href="deck.pptx">原生PPTX</a>　<a href="deck.pdf">PDF</a>　<a href="report.md">实测报告</a>　<a href="render_report.json">检查记录</a></p><nav>{nav}</nav>'+''.join(panels)+'</html>'
    (out/'index.html').write_text(page,encoding='utf8')
    return {'output':str(out),'pages':len(pages),'summary':summary,'cost':cost}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workflow_id');parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(package(args.workflow_id,args.out),ensure_ascii=False))
