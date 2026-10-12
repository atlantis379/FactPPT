"""Report actual experimental outputs and calls without estimating vendor fees."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.visual_prompt_lab import LAB,read,write,file_sha,status
from tools.visual_lab_package import SELECTED

def report():
    state=status();native=LAB/'native';render=read(native/'render_report.json') if (native/'render_report.json').is_file() else None
    qa=read(native/'final_visual_review.json') if (native/'final_visual_review.json').is_file() else {}
    design=sum(c['status']=='RETURNED_INSPECTED' for c in state['calls'])
    failures=sum(c['status']=='FAILED_TRANSPORT' for c in state['calls'])
    clean=[read(p) for p in (LAB/'native_assets').glob('*/clean_receipt.json')]
    vectors=[read(p) for p in (LAB/'native_assets').glob('*/vector_receipt.json')]
    info={'status':'AWAITING_HUMAN_VISUAL_CONFIRMATION' if render and qa.get('ready_for_human_style_review') is True else 'LOCAL_VISUAL_QA_PENDING' if render else 'NATIVE_VALIDATION_PENDING',
        'model':'gpt-6-luna','image_backend':'builtin ImageGen','vector_backend':'Adobe',
        'source_sha256':file_sha(LAB/'common_input.json'),'selected_trials':SELECTED,
        'calls':{'design_returned':design,'design_transport_failures':failures,'quality_revisions':sum(t['phase']=='quality' and t['result_path'] is not None for t in state['trials']),
                 'clean_returned':len(clean),'adobe_vector_returned':len(vectors)},
        'timing':{'native_render_seconds':render.get('seconds') if render else None,
                  'clean_outer_elapsed_seconds':[r.get('elapsed_seconds') for r in clean],
                  'vector_outer_elapsed_seconds':[(r['ended']-r['started'])/1000 if 'started' in r else (r['ended_ms']-r['started_ms'])/1000 for r in vectors],
                  'note':'Outer elapsed times include execution and transport; parallel stages must not be summed as total project duration.'},
        'fees':None,'model_tokens':None,'fee_note':'Actual vendor invoices and token usage were not returned; report calls only.',
        'native_verification':render,'files':{},'medical_approval':False,'customer_style_approval':False,'frozen':False,
        'limitations':['Only six representative pages qualified; not a 59-page delivery.',
            'Generated serif-like lettering differs from native Microsoft YaHei; inspect actual PowerPoint output.',
            'Vector tracing loses paper texture and some gradient/detail; differences remain in render_report.',
            'Textbook repeats added unsupported text/relations; rejected from candidate.',
            'One redundant editorial page9 repair occurred after a false-positive review; correction history retained.']}
    for name in ('deck.pptx','deck.pdf'):
        p=native/name
        if p.is_file():info['files'][name]={'path':str(p),'bytes':p.stat().st_size,'sha256':file_sha(p)}
    write(LAB/'experiment_report.json',info)
    recipe={'version':'visual-editorial.v0-candidate','status':'AWAITING_HUMAN_STYLE_CONFIRMATION','frozen':False,
        'model':'gpt-6-luna','template_reference_sha256':file_sha(LAB/'template_reference.png'),
        'palette':read(LAB/'common_input.json')['palette'],'native_font':read(LAB/'common_input.json')['font'],
        'principles':['Source graph precedes design; exact fragments and scope bind every region.',
            'One sole-text section; directions refer to region IDs, not repeated prose.',
            'Use parallel regions for classification/contrast, scoped forward edges for conditions, native cells for tables.',
            'Never infer medical claims, measured curves or statistical intervals from a conceptual source.',
            'Generated letters and connectors are removed; locked text and supported geometry are reconstructed natively.',
            'Check the actual PowerPoint output; geometry metrics alone miss strokes through text and paragraph fusion.',
            'Reuse unchanged-image reviews by SHA; review only changed pages and keep correction history.'],
        'actual_examples':{str(n):{'trial_id':tid,'prompt_sha256':file_sha(LAB/'trials'/tid/'prompt.txt'),
            'layout_sha256':file_sha(LAB/'native_assets'/tid/'layout.json')} for n,tid in SELECTED.items()},
        'budget_policy':{'baseline_design_calls':16,'max_quality_revisions':3,'max_transport_retries':2,
                         'clean_and_vector_calls_counted_separately':True,'unknown_fees_not_estimated':True},
        'actual_output_files':info['files'],'medical_approval':False,'customer_style_approval':False}
    recipe['actual_page_images']=[{'source_page':n,'sha256':file_sha(native/f'slide{i:02d}.png')} for i,n in enumerate(SELECTED,1) if (native/f'slide{i:02d}.png').is_file()]
    write(LAB/'candidate_recipe.json',recipe)
    text=f'''# Luna 图解方案实测报告

状态：{info['status']}。设计模型固定 Luna，生图使用内置工具，矢量化使用 Adobe。

## 实际调用

设计返回 {design} 次，其中针对性质量修订 {info['calls']['quality_revisions']} 次；去字 {len(clean)} 次；Adobe矢量化 {len(vectors)} 次。设计连接失败 {failures} 次。厂商费用和模型token未取得，不估算金额。

## 结果与适用范围

期刊式为本次样本的临时候选。并列目标、方法学对照、条件判定、表格和条件评估使用各自的源绑定结构；封面保持标题主焦点。教材式重复稿新增非来源要点及跨范围双向关系，未入选。场景式的原方法学画面出现虚构统计图形，未进入稳定性阶段。

生成图只提供设计与插画；最终文字、表格、条件与关系由原生对象表达。插画不是来源医学图或研究数据。19张实际稿的prompt、图片、回执及局部复核均留存。

原生导出：{render['summary']['native_paths'] if render else '未完成'} 条路径，生成图片对象 {render['summary']['generated_picture_objects'] if render else '未完成'}；最终一次导出和核对耗时 {render.get('seconds') if render else '未完成'} 秒。首次局部排版及可见问题修订的耗时未合并为这个数，不能把它作为整个实验总历时。PowerPoint实际画面另经独立查看，最终审美留待用户确认。

## 局限与下一步

本机原生字体为 Microsoft YaHei；图稿的衬线字体观感无法原样复制，需看实际PowerPoint结果。纸张纹理、渐变与部分细节损失按矢量解析报告记录。样本只覆盖六种页面，不直接推广到59页。

独立复核曾误把教材页9的问题记入期刊页9，重新逐图定位后已更正，保留CORRECTED历史；误判导致一次冗余修订调用，未隐藏成本。

最终视觉标准尚未固定。请根据实际六页原生画面判断专业感、焦点、阅读顺序、密度和一致性；代码通过不替代审美结论。人工视觉确认后才能归档正式提示词方案和进入主线。
'''
    (LAB/'experiment_report.md').write_text(text,encoding='utf8')
    return info['status']

if __name__=='__main__':print(report())
