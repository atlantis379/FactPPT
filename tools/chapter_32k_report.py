"""Report only recorded local timings and accepted independent review results."""
from pathlib import Path
from collections import Counter
from datetime import datetime
import chapter_draft_benchmark as b

OUT=b.ROOT/'output/chapter_32k_full'

def main():
    run=b.read(OUT/'run.json');manifest=b.read(OUT/'manifest.json')
    review=b.read(OUT/'review/candidate_u8/validation_report.json')
    receipts=[b.read(p) for p in sorted((OUT/'local').glob('*.receipt.json'))]
    usage={'prompt_tokens':0,'completion_tokens':0,'total_tokens':0}
    for r in receipts:
        for k in usage:usage[k]+=(r.get('usage') or {}).get(k,0)
    pages=[b.unpack(b.read(OUT/c['file'])) for c in manifest['cases']]
    expected_units={u['id'] for p in pages for u in p['units']}
    expected_claims={c['id'] for p in pages for c in p['claims']}
    actual_units={x for g in run['groups'] for x in g['provided_unit_ids']}
    actual_claims={x for g in run['groups'] for x in g['provided_claim_ids']}
    actual_pages=[x for g in run['groups'] for x in g['primary_page_ids']]
    coverage={'primary_page_count':len(actual_pages),'primary_pages_unique':len(set(actual_pages)),
              'provided_unit_count':len(actual_units),'provided_claim_count':len(actual_claims),
              'all_expected_units_provided':actual_units==expected_units,'all_expected_claims_provided':actual_claims==expected_claims,
              'meaning':'Input provision only. Independent review determines content fidelity; ledger does not certify reading.'}
    resource=b.read(OUT/'resources_valid.json')['samples']
    gpu=[float(x['gpu'].split(',')[0]) for x in resource if x.get('gpu')]
    memory=[x['host_available_mib'] for x in resource if x.get('memory_query_ok')]
    audit=b.read(OUT/'review/candidate_u8/result.json')
    verdicts=Counter(p['verdict'] for s in audit['sections'] for p in s['key_points'])
    summary_verdicts=Counter(s['summary_verdict'] for s in audit['sections'])
    candidate=b.read(OUT/'local/chapter.result.json')
    unique_pending=len({b.canonical(x) for x in candidate.get('pending_issues',[])})
    preparation=b.read(OUT/'review/source_preparation/preparation_record.json')
    reviewer_run=b.read(OUT/'review/candidate_u8/reviewer_run.json')
    archive_elapsed=(datetime.fromisoformat(reviewer_run['finished_at_utc'])-datetime.fromisoformat(run['started_at'])).total_seconds()
    result={'source_sha256':manifest['source_sha256'],'snapshot_sha256':manifest['snapshot_sha256'],
            'run_started_at':run['started_at'],'draft_finished_at':run['finished_at'],
            'draft_wall_seconds':run['elapsed_seconds'],'local_requests':len(receipts),
            'local_request_wall_seconds':sum(r['elapsed_seconds'] for r in receipts),
            'structural_retry_requests':sum('structural_retry' in p.name for p in (OUT/'local').glob('*.receipt.json')),
            'max_actual_prompt_tokens':max((r.get('usage') or {}).get('prompt_tokens',0) for r in receipts),
            'local_usage':usage,'local_inference_fee':None,'cloud_review_usage_and_fee':None,
            'coverage':coverage,'review':review,'key_point_verdicts':dict(verdicts),
            'pending_issue_unique_count':unique_pending,'source_preparation':preparation,
            'section_summary_verdicts':dict(summary_verdicts),
            'generation_start_to_review_archive_seconds':archive_elapsed,
            'review_timing':reviewer_run,
            'status':'CONTENT_REVISION_REQUIRED' if review['blockers'] else 'INDEPENDENT_AUDIT_COMPLETE_HUMAN_GATE_PENDING',
            'gpu_max_sampled_mib':max(gpu) if gpu else None,'host_min_available_sampled_mib':min(memory) if memory else None,
            'resource_sampling_limitations':'Supplementary samples start after inference begins; initial integrated sampler failed memory fields; values are observed samples, not guaranteed peaks.',
            'protocol_changes_vs_16k':run['protocol_changes_vs_16k'],'production_submitted':False,'human_confirmed':False}
    b.save(OUT/'report.json',result)
    def display_ref(issue):
        ref=issue.get('ref',issue.get('id',''))
        return ref.split(':',1)[1] if ':' in ref and len(ref.split(':',1)[0])==64 else ref
    issues='\n'.join(f"- **{i['severity']}**（{display_ref(i)}）：{i.get('problem','')}" for i in review['issues'])
    text=f'''# S03 整章 32K 重跑与独立审核

## 审核结果

29 页新候选；逐条审核 {review['key_points_reviewed']} 个要点。发现 **{review['blockers']} 个阻断、{review['notes']} 个提示**；候选留下 {review['pending_issue_count']} 条待处理记录，按完整字符串去重为 {unique_pending} 条，包含冻结来源遗留的图表待二读标记，不等于新增医学错误数量。要点判定分布：{dict(verdicts)}。

候选结构验收：{review['candidate_contract_accepted']}。独立审核合同验收：{review['review_contract_accepted']}。未作人工确认，未提交现网。独立审核判断来源忠实度，不代表医学批准。

逐页摘要判定分布：{dict(summary_verdicts)}。章节总述、跨页续句及遗漏检查见独立审核说明 `review/candidate_u8/audit_notes.md`。

## 输入与运行

- 来源：S03《02_第2章_诊断评估和监测》，同一冻结资料。
- 独立审核端重新读取29页、376条论断、419个单元；实际查看原PDF的14页图表/箭头，页码 {preparation['visual_pages_actually_viewed']}。原图全部渲染不等于全部实际查看。
- 全部 {len(actual_pages)} 页、{len(actual_units)} 个来源单元、{len(actual_claims)} 条论断已实际提供给模型；代码登记提供情况，不声称登记等于阅读完整或内容正确。
- 本地生成总历时 {run['elapsed_seconds']/60:.2f} 分钟；模型请求累计 {result['local_request_wall_seconds']/60:.2f} 分钟。
- 从开始本地生成到独立审核归档 {archive_elapsed/60:.2f} 分钟，包含并行审核及等待，未包括更早的样本准备/程序编写。这是到审核结果的时间，尚未达到可确认版本。审核端未在收到任务时记录起始，完整独立审核耗时未知；不把尾段计时当作完整审核时间。
- 请求 {len(receipts)} 次，其中结构重试 {result['structural_retry_requests']} 次；输入 {usage['prompt_tokens']:,}、输出 {usage['completion_tokens']:,} token。
- 最大实际单次输入 {result['max_actual_prompt_tokens']:,} token；32K 单槽运行，保留输出空间。
- 显存最高采样值 {result['gpu_max_sampled_mib']} MiB；系统可用内存最低采样值 {result['host_min_available_sampled_mib']:.1f} MiB。补充采样晚于生成开始，不是完整峰值；首次集成采样字段错误保留在原记录中。
- 本地推理没有云端推理账单；当前会话与独立云端审核仍有消耗，未取得真实用量/费用，不估算收费。

## 与 16K 的比较限制

本轮同时改为连续多页加邻页原文、取消人为要点上限、由代码维护输入账本，且完全重新生成。结果可以检验新流程质量，不能把变化单独归因于 32K。旧候选和旧审核均保留，未覆盖。

## 独立审核发现

{issues}

## 文件

本目录保存冻结输入、每次完整请求与原响应、实际 token/耗时、输入账本、章节候选、匿名独立审核与验收报告。来源原图检查范围及审核历时以 review 中实际记录为准。
'''
    (OUT/'report.md').write_text(text,encoding='utf-8')
    print({k:result[k] for k in ('local_requests','draft_wall_seconds','key_point_verdicts','coverage')})

if __name__=='__main__':main()
