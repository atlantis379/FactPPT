"""General-rule gold/corruption tests, independent of P05 composition."""
import argparse
import copy
import hashlib
import platform
from pathlib import Path
from PIL import Image
from integrity import *
from quality_checks import validate_chart_svg,validate_coverage,validate_narrative,validate_editorial_asset_contract,validate_editorial_fusion_plan,validate_client_template_contract,validate_visual_base_selection
from pptx_quality import validate_render_evidence

S=Path(__file__).resolve().parents[1]

def run(out):
    if out.exists(): raise FileExistsError('Use a new evidence directory')
    out.mkdir(parents=True)
    runtime={'python':platform.python_version(),'platform':platform.platform(),'source_hashes':{p.name:digest(p) for p in [Path(__file__),S/'scripts/quality_checks.py',S/'scripts/integrity.py']}}
    write(out/'runtime.json',runtime)
    engine={'engine_id':'general-quality-calibration','engine_version':'0.5.0','implementation_sha256':hashlib.sha256(canonical(runtime).encode()).hexdigest()}
    records=[]
    def case(name,payload,expected,fn):
        ip=out/(name+'.input.json'); op=out/(name+'.output.json')
        write(ip,{'input':payload,'expected_accept':expected,'fixture_kind':'SYNTHETIC_GOLD_CALIBRATION_NOT_MEDICAL_EVIDENCE'})
        try:
            errors=fn(copy.deepcopy(payload),name); actual=not errors; status='PASS' if actual==expected else 'FAIL'
            output={'accepted':actual,'expected_accept':expected,'errors':errors,'status':status}
        except Exception as e: output={'status':'FAIL','exception':repr(e)}
        write(op,output)
        records.append({'fixture_id':name,'polarity':'positive' if expected else 'negative','executor':engine,'input_ref':ip.name,'input_sha256':digest(ip),
                        'output_ref':op.name,'output_sha256':digest(op),'status':output['status'],'verifier_results':[{'verifier_id':'python-expected-result-equality','status':output['status']}]})
    bars={'comparable':True,'unit_label':'events / 100','context_label':'SYNTHETIC population A, t1','axis':{'dimension':'y','domain':['0','100'],'pixel_range':[180,20],'scale':'linear','zero_policy':'REQUIRED',
        'ticks':[{'id':'tick0','value':'0','label':'0'},{'id':'tick100','value':'100','label':'100'}]},
        'series':[{'id':'a','kind':'bar','label':'Synthetic series','data':[{'id':'a1','value':'25','display':'25','slot':40,'thickness':20},{'id':'a2','value':'75','display':'75','slot':100,'thickness':20},{'id':'a3','value':None,'display':'not reported','slot':160,'thickness':20}]}]}
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="240" height="220"><text id="axis-unit">events / 100</text><text id="context">SYNTHETIC population A, t1</text><text id="legend-a">Synthetic series</text><text id="tick0" y="180">0</text><text id="tick100" y="20">100</text><text id="label-a1">25</text><text id="label-a2">75</text><rect id="a1" x="40" y="140" width="20" height="40"/><rect id="a2" x="100" y="60" width="20" height="120"/></svg>'
    def chart(payload,name):
        path=out/(name+'.svg'); path.write_text(payload['svg'],encoding='utf-8'); return validate_chart_svg(payload['contract'],path)
    case('CHART-linear-bar',{'contract':bars,'svg':svg},True,chart)
    case('CHART-invisible-fill-stroke',{'contract':bars,'svg':svg.replace('id="a1"','id="a1" fill="none" stroke="none"')},False,chart)
    case('CHART-transparent-paint',{'contract':bars,'svg':svg.replace('id="a1"','id="a1" fill="rgba(0,0,0,0)"')},False,chart)
    for name,changed in [('height',svg.replace('height="40"','height="80"')),('series-slot',svg.replace('x="40"','x="100"')),('missing-zero',svg.replace('</svg>','<rect id="a3" x="160" y="180" width="20" height="0"/></svg>')),('unit',svg.replace('events / 100','events / 10')),('context',svg.replace('population A','population B')),('hidden',svg.replace('id="a1"','id="a1" opacity="0"')),('extra',svg.replace('</svg>','<rect x="0" y="0" width="40" height="40"/></svg>'))]:
        case('CHART-'+name,{'contract':bars,'svg':changed},False,chart)
    changed=copy.deepcopy(bars); changed['axis']['domain']=['20','100']
    case('CHART-nonzero-baseline',{'contract':changed,'svg':svg},False,chart)
    changed=copy.deepcopy(bars); changed['axis']['domain']=['0','50']
    case('CHART-axis-clipping',{'contract':changed,'svg':svg},False,chart)
    interval={'comparable':True,'unit_label':'ratio','context_label':'SYNTHETIC same population/time','axis':{'dimension':'x','domain':['0','10'],'pixel_range':[20,220],'scale':'linear','ticks':[]},
        'series':[{'id':'f','label':'Estimate and interval','kind':'interval','data':[{'id':'f1','value':'5','lower':'3','upper':'7','display':'5 [3,7]','slot':60}]}]}
    forest='<svg xmlns="http://www.w3.org/2000/svg"><text id="axis-unit">ratio</text><text id="context">SYNTHETIC same population/time</text><text id="legend-f">Estimate and interval</text><text id="label-f1">5 [3,7]</text><circle id="f1" cx="120" cy="60" r="3"/><line id="interval-f1" x1="80" x2="160" y1="60" y2="60" stroke="black"/></svg>'
    case('CHART-interval',{'contract':interval,'svg':forest},True,chart)
    case('CHART-interval-displaced',{'contract':interval,'svg':forest.replace('x2="160"','x2="180"')},False,chart)
    log={'comparable':True,'unit_label':'ratio','context_label':'SYNTHETIC log data','axis':{'dimension':'y','domain':['1','1000'],'pixel_range':[300,0],'scale':'log10','ticks':[]},
        'series':[{'id':'l','label':'Log series','kind':'line','data':[{'id':'l1','value':'10','display':'10','slot':30},{'id':'l2','value':'100','display':'100','slot':80}]}]}
    line='<svg xmlns="http://www.w3.org/2000/svg"><text id="axis-unit">ratio</text><text id="context">SYNTHETIC log data</text><text id="legend-l">Log series</text><text id="label-l1">10</text><text id="label-l2">100</text><circle id="l1" cx="30" cy="200" r="3"/><circle id="l2" cx="80" cy="100" r="3"/><polyline id="series-l" points="30,200 80,100" stroke="black"/></svg>'
    case('CHART-log-line',{'contract':log,'svg':line},True,chart)
    case('CHART-log-linearized',{'contract':log,'svg':line.replace('cy="200"','cy="297"')},False,chart)
    case('CHART-line-reversed',{'contract':log,'svg':line.replace('30,200 80,100','80,100 30,200')},False,chart)

    source={'pages':{'p1':'Synthetic report. At t1, cohort A has 25 of 100 observations. Exclude subgroup X.','p2':'Table continuation: cohort B has 75 of 100 observations. Footnote: association only; no causal conclusion.'}}
    anchors=[('A','p1','At t1, cohort A has 25 of 100 observations.',{'value':'25','denominator':'100','population':'A','time':'t1'}),
             ('X','p1','Exclude subgroup X.',{'negation':True,'subgroup':'X'}),
             ('B','p2','Table continuation: cohort B has 75 of 100 observations.',{'value':'75','denominator':'100','population':'B','time':'t1'}),
             ('F','p2','Footnote: association only; no causal conclusion.',{'strength':'association','causality':False})]
    objects=[]
    for oid,page,quote,semantics in anchors:
        start=source['pages'][page].index(quote)
        objects.append({'id':oid,'anchor':{'page':page,'start':start,'end':start+len(quote),'quote':quote},'semantics':semantics})
    source_hash=hashlib.sha256(canonical(source).encode()).hexdigest()
    oracle={'source_sha256':source_hash,'origin':'SYNTHETIC_GOLD_ORACLE','review_run_id':'fixed-gold-v1','denominator_status':'REVIEWED_COMPLETE','section_ids':['body','continued_table','footnote'],'objects':objects}
    extracted={'source_sha256':source_hash,'extraction_run_id':'candidate-run','page_ids':['p1','p2'],'section_ids':oracle['section_ids'],'objects':copy.deepcopy(objects)}
    def coverage(d,n): return validate_coverage(d['source'],d['reference'],d['extracted'])
    payload={'source':source,'reference':oracle,'extracted':extracted}
    case('COVERAGE-full-inventory',payload,True,coverage)
    for kind in ('footnote','continuation','negation','unknown-denominator','self-review','page','denominator'):
        d=copy.deepcopy(payload)
        if kind=='footnote': d['extracted']['objects']=d['extracted']['objects'][:-1]
        elif kind=='continuation': d['extracted']['objects'].pop(2)
        elif kind=='negation': d['extracted']['objects'][1]['semantics']['negation']=False
        elif kind=='unknown-denominator': d['reference']['denominator_status']='UNKNOWN'
        elif kind=='self-review': d['extracted']['extraction_run_id']='fixed-gold-v1'
        elif kind=='page': d['extracted']['page_ids']=['p1']
        elif kind=='denominator': d['extracted']['objects'][0]['semantics']['denominator']='10'
        case('COVERAGE-'+kind,d,False,coverage)

    assertions={'a':{'id':'a','text':'Observed association in cohort A at t1.','support':['A','F'],'scope':'cohort A at t1','strength':'association'},
        'x':{'id':'x','text':'Subgroup X was excluded.','support':['X'],'scope':'study','strength':'source'},
        'b':{'id':'b','text':'No causal conclusion is licensed.','support':['F'],'scope':'study','strength':'source'}}
    nref={'review_run_id':'independent-annotator-v1','approved_assertions':assertions,'required_questions':['finding','limitation'],'duration_seconds':120,'scope':'study',
        'question_assertions':{'finding':['a'],'limitation':['x','b']},'section_dependencies':{'S2':['S1']}}
    narrative={'generation_run_id':'author-v1','scope':'study','sections':[{'id':'S1','depends_on':[],'seconds':50,'answers':['finding'],'assertions':[assertions['a']]},
        {'id':'S2','depends_on':['S1'],'seconds':40,'answers':['limitation'],'assertions':[assertions['x'],assertions['b']]}],'closure_questions':['finding','limitation'],'closure_assertion_ids':['a','x','b']}
    def narr(d,n): return validate_narrative(d['reference'],d['narrative'])
    payload={'reference':nref,'narrative':copy.deepcopy(narrative)}
    case('NARRATIVE-reviewed',payload,True,narr)
    no_assertions=copy.deepcopy(payload)
    for s in no_assertions['narrative']['sections']: s['assertions']=[]
    case('NARRATIVE-empty-assertions',no_assertions,False,narr)
    missing_dep=copy.deepcopy(payload); missing_dep['narrative']['sections'][1]['depends_on']=[]
    case('NARRATIVE-omitted-required-dependency',missing_dep,False,narr)
    for kind in ('causal-upgrade','universalized','dependency','closure','missing-answer','duration','changed-text-id'):
        d=copy.deepcopy(payload); n=d['narrative']
        if kind=='causal-upgrade': n['sections'][0]['assertions'][0]['strength']='causal'
        elif kind=='universalized': n['scope']='all populations'
        elif kind=='dependency': n['sections'].reverse()
        elif kind=='closure': n['closure_questions']=[]
        elif kind=='missing-answer': n['sections'][1]['answers']=[]
        elif kind=='duration': n['sections'][1]['seconds']=100
        elif kind=='changed-text-id': n['sections'][0]['assertions'][0]['text']='This causes the outcome in everyone.'
        case('NARRATIVE-'+kind,d,False,narr)

    # Final-render provenance is a separate quality capability, not a P05 layout rule.
    def render_evidence_case(payload,name):
        artifact=out/(name+'.artifact.bin'); artifact.write_bytes(b'SYNTHETIC_FINAL_ARTIFACT')
        render=out/(name+'.png'); Image.new('RGB',(320,180),'white').save(render)
        evidence={'artifact_sha256':digest(artifact),'slide_number':1,'renderer':{'id':'synthetic-renderer','version':'1'},
                  'render':{'path':render.name,'sha256':digest(render)},'visual_review':{'reviewer_id':'synthetic-independent-reviewer','reviewer_role':'independent','status':'PASS','checked':{'glyphs':True,'clipping':True,'meaning_critical_text':True}}}
        evidence.update(payload)
        evidence_path=out/(name+'.render-evidence.json'); write(evidence_path,evidence)
        status,errors,_=validate_render_evidence(artifact,evidence_path,{'canvas':[320,180]},1)
        return [] if status=='PASS' else errors or [{'issue':status}]
    case('RENDER-EVIDENCE-bound-review',{},True,render_evidence_case)
    case('RENDER-EVIDENCE-artifact-hash-mismatch',{'artifact_sha256':'0'*64},False,render_evidence_case)
    case('RENDER-EVIDENCE-renderer-missing',{'renderer':{}},False,render_evidence_case)
    case('RENDER-EVIDENCE-review-missing',{'visual_review':{}},False,render_evidence_case)

    # Editorial assets are independently bound to the actual local bytes. These fixtures
    # cover the general visual-fusion contract, not any page-specific composition.
    def editorial_asset_case(payload,name):
        asset=out/(name+'.png'); asset.write_bytes(payload['bytes_text'].encode('ascii'))
        return validate_editorial_asset_contract(payload['contract'],asset)
    asset_bytes=b'SYNTHETIC_EDITORIAL_ASSET_V1'
    asset_contract={'asset_id':'SYNTHETIC_BASE','asset_class':'NONSEMANTIC_EDITORIAL_BASE','policy':'REQUIRED','layer_role':'EDITORIAL_UNDERLAY',
        'asset_sha256':hashlib.sha256(asset_bytes).hexdigest(),'relative_path':'SYNTHETIC.png','placement':[0,0,320,180],
        'prohibited_content':['text','numbers','clinical_claims'],'content_review':{'status':'NEEDS_REVIEW','reviewer_role':'author','checked':{}}}
    case('EDITORIAL-ASSET-bound-nonsemantic-base',{'bytes_text':asset_bytes.decode('ascii'),'contract':asset_contract},True,editorial_asset_case)
    changed=copy.deepcopy(asset_contract); changed['asset_sha256']='0'*64
    case('EDITORIAL-ASSET-hash-mismatch',{'bytes_text':asset_bytes.decode('ascii'),'contract':changed},False,editorial_asset_case)
    changed=copy.deepcopy(asset_contract); changed['prohibited_content']=['text']
    case('EDITORIAL-ASSET-prohibitions-incomplete',{'bytes_text':asset_bytes.decode('ascii'),'contract':changed},False,editorial_asset_case)

    # Fusion is deliberately bound to source-owned native semantic layers and an asset
    # identity. The negative cases prove that a visually plausible plan cannot pass when
    # it loses source bindings or turns an editable evidence layer into generated art.
    fusion_plan={'fusion_plan_id':'FUSION-SYNTHETIC-1','fusion_plan_version':'0.1','source_identity':{'source_sha256':'a'*64,'semantic_object_ids':['S1','S2']},'page_id':'P1',
        'editorial_asset':{'asset_id':'SYNTHETIC_BASE','asset_sha256':'b'*64,'asset_class':'NONSEMANTIC_EDITORIAL_BASE','prompt_provenance_ref':'prompt.json'},'integration_mode':'FIELD_INTEGRATED',
        'semantic_layers':[{'object_id':'S1','source_anchor':'p1:0-10','native_editable':True,'box':[40,40,110,80],'z_order':2,'visual_relation':'READING_ORDER'},
                           {'object_id':'S2','source_anchor':'p1:11-20','native_editable':True,'box':[180,40,110,80],'z_order':2,'visual_relation':'GROUPING_ONLY'}],
        'editorial_zones':[{'zone_id':'lower-rhythm','box':[0,130,320,50],'role':'LOWER_RHYTHM','z_order':0}],
        'protected_zones':[{'zone_id':'body-gap','box':[40,130,240,30],'minimum_uncovered_area_ratio':0.75}],
        'render_review':{'reviewer_role':'author','status':'NEEDS_REVIEW','checked':{'background_visible':True,'semantic_text_legible':True,'visual_hierarchy_aligned':True,'no_semantic_replacement':True}}}
    fusion_scene={'canvas':[320,180],'editorial_assets':[{'asset_id':'SYNTHETIC_BASE','asset_class':'NONSEMANTIC_EDITORIAL_BASE','layer_role':'EDITORIAL_UNDERLAY','asset_sha256':'b'*64}],
        'editorial_fusion':{'fusion_plan_id':'FUSION-SYNTHETIC-1','asset_id':'SYNTHETIC_BASE','integration_mode':'FIELD_INTEGRATED','protected_zones':copy.deepcopy(fusion_plan['protected_zones'])}}
    def fusion_case(payload,name): return validate_editorial_fusion_plan(payload['plan'],payload['scene'])
    case('EDITORIAL-FUSION-bound-native-semantic-layers',{'plan':fusion_plan,'scene':fusion_scene},True,fusion_case)
    changed=copy.deepcopy(fusion_plan); changed['semantic_layers'][1]['native_editable']=False
    case('EDITORIAL-FUSION-nonnative-semantic-layer',{'plan':changed,'scene':fusion_scene},False,fusion_case)
    changed=copy.deepcopy(fusion_plan); changed['editorial_asset']['asset_sha256']='c'*64
    case('EDITORIAL-FUSION-asset-hash-mismatch',{'plan':changed,'scene':fusion_scene},False,fusion_case)
    changed=copy.deepcopy(fusion_plan); changed['semantic_layers']=changed['semantic_layers'][:1]
    case('EDITORIAL-FUSION-semantic-binding-gap',{'plan':changed,'scene':fusion_scene},False,fusion_case)

    # A client template is an alternate visual base, never an implicit AI-background
    # enhancement. These fixtures bind its exact bytes and protected brand/safe regions.
    client_bytes=b'SYNTHETIC_CLIENT_TEMPLATE_V1'
    client_contract={'template_id':'CLIENT-HOSPITAL-1','template_version':'1','client_supplied':True,'source_type':'PPTX_TEMPLATE',
        'template_sha256':hashlib.sha256(client_bytes).hexdigest(),'application_mode':'PRESERVE_MASTERS_AND_LAYOUTS','embedded_text_policy':'BRAND_ONLY_CONFIRMED','canvas':[320,180],
        'brand_regions':[{'region_id':'logo','role':'LOGO','box':[10,10,50,20],'preserve':True}],
        'semantic_safe_regions':[{'region_id':'body','box':[70,40,220,100]}],
        'review':{'reviewer_role':'author','status':'NEEDS_REVIEW','checked':{'client_asset_identity':True,'brand_regions':True,'embedded_text':True,'semantic_safe_regions':True}}}
    def client_template_case(payload,name):
        asset=out/(name+'.pptx'); asset.write_bytes(payload['bytes_text'].encode('ascii'))
        return validate_client_template_contract(payload['contract'],asset)
    case('CLIENT-TEMPLATE-bound-pptx',{'bytes_text':client_bytes.decode('ascii'),'contract':client_contract},True,client_template_case)
    changed=copy.deepcopy(client_contract); changed['template_sha256']='0'*64
    case('CLIENT-TEMPLATE-hash-mismatch',{'bytes_text':client_bytes.decode('ascii'),'contract':changed},False,client_template_case)
    changed=copy.deepcopy(client_contract); changed['semantic_safe_regions'][0]['box']=[20,10,120,60]
    case('CLIENT-TEMPLATE-brand-safe-overlap',{'bytes_text':client_bytes.decode('ascii'),'contract':changed},False,client_template_case)

    ai_scene=copy.deepcopy(fusion_scene)
    ai_scene['visual_base']={'mode':'AI_EDITORIAL_BASE','binding_id':'SYNTHETIC_BASE','binding_sha256':'b'*64}
    case('VISUAL-BASE-ai-exclusive',{'scene':ai_scene},True,lambda p,n: validate_visual_base_selection(p['scene']))
    client_scene={'visual_base':{'mode':'CLIENT_TEMPLATE','binding_id':'CLIENT-HOSPITAL-1','binding_sha256':hashlib.sha256(client_bytes).hexdigest()},
        'client_template_binding':{'template_id':'CLIENT-HOSPITAL-1','template_sha256':hashlib.sha256(client_bytes).hexdigest(),'brand_regions':[{'region_id':'logo','box':[10,10,50,20]}]},'editorial_assets':[]}
    case('VISUAL-BASE-client-exclusive',{'scene':client_scene},True,lambda p,n: validate_visual_base_selection(p['scene']))
    changed=copy.deepcopy(client_scene); changed['editorial_assets']=[asset_contract]
    case('VISUAL-BASE-client-ai-conflict',{'scene':changed},False,lambda p,n: validate_visual_base_selection(p['scene']))
    changed=copy.deepcopy(client_scene); changed.pop('client_template_binding')
    case('VISUAL-BASE-client-binding-missing',{'scene':changed},False,lambda p,n: validate_visual_base_selection(p['scene']))

    passed=all(r['status']=='PASS' for r in records)
    q={'schema_version':'0.2','qualification_run_id':out.name,'benchmark_pack_id':'GENERAL-QUALITY-v0.5','runtime_profile_id':'LOCAL','runtime_ref':'runtime.json','runtime_sha256':digest(out/'runtime.json'),
        'executed_fixture_ids':[r['fixture_id'] for r in records],'results':records,'capability_records':[{'capability_record_id':'GENERAL-QUALITY-CALIBRATION',**engine,
            'capability':'SIMPLE_SVG_GEOMETRY_ANNOTATED_CALIBRATION_AND_EDITORIAL_ASSET_IDENTITY','qualification_status':'REFERENCE_QUALIFIED' if passed else 'NOT_QUALIFIED','evidence_fixture_ids':[r['fixture_id'] for r in records],
            'scope':'Only the simple SVG primitives, independently annotated synthetic oracle checks and editorial asset identity checks executed here.',
            'limitations':['No arbitrary SVG/CSS/PPTX chart qualification; no automated clinical entailment or proof of real full-source recall.'],
            'invalidation_triggers':['code/schema/runtime/format/annotation protocol change']}], 'overall_status':'PASS' if passed else 'FAIL'}
    write(out/'qualification.json',q)
    errors=validate_qualification(q,out)
    write(out/'summary.json',{'passed':sum(r['status']=='PASS' for r in records),'total':len(records),'failed':[r['fixture_id'] for r in records if r['status']!='PASS'],'evidence_errors':errors})
    print(canonical(read(out/'summary.json')))
    return 0 if passed and not errors else 1

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--out',type=Path,required=True); a=p.parse_args(); raise SystemExit(run(a.out))
