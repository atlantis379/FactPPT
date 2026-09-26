"""Replayable local regression evidence. Each case executes its input, not a PASS assertion."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from contextlib import contextmanager
import platform
import jsonschema
from integrity import *

S=Path(__file__).resolve().parents[1]

def load_module(name, path):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def run(out, font, symbol_font):
    if out.exists(): raise FileExistsError('Use a new evidence directory')
    out.mkdir(parents=True)
    assembler=load_module('assembler',S/'runtime_executors/reference_protected_layer_assembler_v0.1.py')
    overlay=load_module('exact',S/'runtime_executors/exact_overlay.py')
    import PIL
    from PIL import Image
    sources={p.relative_to(S).as_posix():digest(p) for p in [Path(__file__),S/'scripts/integrity.py',S/'runtime_executors/reference_protected_layer_assembler_v0.1.py',S/'runtime_executors/exact_overlay.py',S/'schemas/run_state.schema.json',S/'schemas/runtime_qualification_result.v0.2.schema.json']}
    runtime={'sources':sources,'font_sha256':digest(font),'symbol_font_sha256':digest(symbol_font),'python':platform.python_version(),'pillow':PIL.__version__,'platform':platform.platform()}
    implementation=__import__('hashlib').sha256(canonical(runtime).encode()).hexdigest()
    executor={'engine_id':'offline-integrity-suite','engine_version':'0.5.0','implementation_sha256':implementation}
    write(out/'implementation.json',runtime)
    cases=[]
    current_case=''
    @contextmanager
    def evidence_dir():
        directory=out/(current_case+'.assets')
        directory.mkdir()
        yield directory
    def case(cid, polarity, payload, expected, check):
        nonlocal current_case
        current_case=cid
        ip=out/f'{cid}.input.json'; op=out/f'{cid}.output.json'
        write(ip,{'case_id':cid,'input':payload,'expected':expected})
        try:
            actual=check(copy.deepcopy(payload)); passed=actual==expected
            result={'actual':actual,'expected':expected,'status':'PASS' if passed else 'FAIL'}
        except Exception as e:
            result={'status':'FAIL','exception':type(e).__name__,'detail':str(e)}
        write(op,result)
        cases.append({'fixture_id':cid,'polarity':polarity,'executor':executor,'input_ref':ip.name,'input_sha256':digest(ip),'output_ref':op.name,'output_sha256':digest(op),
                      'status':result['status'],'verifier_results':[{'verifier_id':'python-expected-result-equality','status':result['status']}]})

    state={'schema_version':'0.5.0','skill_version':'v0.5.0','test_id':'synthetic-state-test','mode':'DELIVERY','risk':'RED',
        'workflow_version':'REFERENCE_PIPELINE_WORKFLOW_v0.1','checklist_version':'REFERENCE_PIPELINE_CHECKLIST_v0.1',
        'stages':{f'W{i:02}':'PASS' for i in range(19)},'subgates':{x:'PASS' for x in REQUIRED_SUBGATES},
        'quality':{x:'PASS' for x in ('source_semantic','numeric_logic','composition','rendered_review')},'blocking_issues':[],'stale_object_ids':[],
        'human_review':{'status':'APPROVED','reviewer':'SYNTHETIC_TEST_ONLY','artifact_sha256':'a'*64},'artifact_sha256':'a'*64,'final_disposition':'APPROVED_REFERENCE_OUTPUT'}
    def valid_state(d):
        return not list(jsonschema.Draft202012Validator(read(S/'schemas/run_state.schema.json')).iter_errors(d)) and not validate_state(d)
    case('STATE-current','positive',state,True,valid_state)
    bad=copy.deepcopy(state); bad['stages']['W03']='FAIL'
    case('STATE-failed-approved','negative',bad,False,valid_state)
    bad=copy.deepcopy(state); bad['stages']['W03']='FAIL'; bad['final_disposition']='PARTIAL_WITH_BLOCKERS'
    case('STATE-partial-downstream-pass','negative',bad,False,valid_state)
    bad=copy.deepcopy(state); bad['subgates'].pop('W12-B')
    case('STATE-missing-subgate','negative',bad,False,valid_state)
    bad=copy.deepcopy(state); bad['mode']='DESIGN_PROTOTYPE'
    case('STATE-prototype-approved','negative',bad,False,valid_state)
    bad=copy.deepcopy(state); bad.update(mode='DESIGN_PROTOTYPE',final_disposition='PARTIAL_WITH_BLOCKERS',delivery_eligible=False)
    case('STATE-prototype-stage-pass','negative',bad,False,valid_state)
    bad['stages']['W14']='PARTIAL_PASS'; bad['stages']['W17']='BLOCKED'
    case('STATE-valid-prototype','positive',bad,True,valid_state)
    bad=copy.deepcopy(state); bad['human_review']['artifact_sha256']='b'*64
    case('STATE-review-hash','negative',bad,False,valid_state)
    bad=copy.deepcopy(state); bad['stale_object_ids']=['old']
    case('STATE-stale','negative',bad,False,valid_state)
    bad=copy.deepcopy(state); bad['skill_version']='v0.1'
    case('STATE-version','negative',bad,False,valid_state)
    empty={'schema_version':'0.2','qualification_run_id':'empty','benchmark_pack_id':'audit','runtime_profile_id':'none','executed_fixture_ids':[],
        'results':[],'capability_records':[{'qualification_status':'QUALIFIED','evidence_fixture_ids':[]}],'overall_status':'PASS'}
    case('QUAL-empty','negative',empty,False,lambda d:not validate_qualification(d,out))

    fact={'fact_id':'N1','value':'2.0','operator':'<','unit':'x','context':{'population':'test','time':'t1'},'value_origin':'SOURCE_EXACT'}
    case('NUM-exact','positive',[fact,fact],True,lambda d:not numeric_diff(*d))
    for key,new in [('operator','≤'),('unit','y'),('context',{'population':'other','time':'t1'}),('value','NaN')]:
        other=copy.deepcopy(fact); other[key]=new
        case('NUM-'+key,'negative',[fact,other],False,lambda d:not numeric_diff(*d))
    case('TEXT-unicode','negative',['x ≥ 2','x > 2'],False,lambda d:not diff(*d))

    original={'logic':'AND','bundles':[{'bundle_id':b,'facts':[{'fact_id':b+'-1','text':'x > 1','scope':'same'}, {'fact_id':b+'-2','text':b,'scope':'same'}]} for b in ('A','B')]}
    scene=factor_and(original)
    case('LOGIC-reconstruction','positive',[original,scene],True,lambda d:not validate_factoring(*d))
    case('LOGIC-empty','negative',[{'logic':'AND','bundles':[]},{'logic':'AND','bundles':[]}],False,lambda d:not validate_factoring(*d))
    bad=copy.deepcopy(original); bad['bundles'][0]['facts']=[]
    case('LOGIC-empty-facts','negative',[bad,scene],False,lambda d:not validate_factoring(*d))
    for kind in ('operator','scope','duplicate','ownership','missing'):
        bad=copy.deepcopy(scene)
        if kind=='operator': bad['logic']='OR'
        if kind=='scope': bad['shared'][0]['semantic']['scope']='other'
        if kind=='duplicate': bad['bundles'][0]['specific']*=2
        if kind=='ownership': bad['shared'][0]['bindings']['A']='B-1'
        if kind=='missing': bad['bundles'][0]['specific']=[]
        case('LOGIC-'+kind,'negative',[original,bad],False,lambda d:not validate_factoring(*d))

    def assembly_test(d):
        with evidence_dir() as td:
            t=Path(td); layers=[]
            for i, item in enumerate(d['layers']):
                p=t/f'{i}.png'; Image.new('RGBA',(8,8),tuple(item['rgba'])).save(p)
                layers.append({'layer_id':str(i),'role':'test','path':str(p),'expected_sha256':digest(p),'z_order':item.get('z_order',i),'protected':item['protected']})
            p=t/'spec.json'; write(p,{'canvas':{'width':8,'height':8},'layers':layers})
            try: assembler.assemble(str(p),str(t/'output')); return True
            except ValueError: return False
    case('ASM-background','positive',{'layers':[{'rgba':[255,255,255,255],'protected':False},{'rgba':[0,0,0,255],'protected':True}]},True,assembly_test)
    case('ASM-ordinary-cover','negative',{'layers':[{'rgba':[0,0,0,255],'protected':True},{'rgba':[255,255,255,255],'protected':False}]},False,assembly_test)
    case('ASM-low-alpha-cover','negative',{'layers':[{'rgba':[0,0,0,1],'protected':True},{'rgba':[255,255,255,1],'protected':False}]},False,assembly_test)
    case('ASM-duplicate-z','negative',{'layers':[{'rgba':[0,0,0,255],'protected':True},{'rgba':[255,255,255,255],'protected':False,'z_order':0}]},False,assembly_test)

    overlay_spec={'canvas':{'width':640,'height':160},'objects':[{'object_id':'test','semantic_object_id':'N1','exact_string':'FFR > 0.8  阈值 ≥ ≤','font_size':24,'box':{'x':20,'y':20,'width':600,'height':40}},
        {'object_id':'unit','semantic_object_id':'N2','exact_string':'mmHg·cm⁻¹·s⁻¹','font_size':24,'font_file':str(symbol_font.resolve()),'box':{'x':20,'y':80,'width':600,'height':60}}]}
    def overlay_test(d):
        with evidence_dir() as td:
            p=Path(td)/'spec.json'; write(p,d)
            try: overlay.compose(p,Path(td)/'output',font); return True
            except ValueError: return False
    case('GLYPH-required-corpus','positive',overlay_spec,True,overlay_test)
    bad=copy.deepcopy(overlay_spec); bad['objects'][0]['line_height']=0
    case('GLYPH-zero-line-height','negative',bad,False,overlay_test)
    bad=copy.deepcopy(overlay_spec); bad['objects'][0]['exact_string']='\U0010ffff'
    case('GLYPH-missing','negative',bad,False,overlay_test)
    bad=copy.deepcopy(overlay_spec); bad['objects'][0]['box']['width']=5
    case('GLYPH-overflow','negative',bad,False,overlay_test)
    bad=copy.deepcopy(overlay_spec); obj=copy.deepcopy(bad['objects'][0]); obj['object_id']='other'; bad['objects'].append(obj)
    case('GLYPH-overlap','negative',bad,False,overlay_test)

    all_pass=all(c['status']=='PASS' for c in cases)
    qualification={'schema_version':'0.2','qualification_run_id':out.name,'benchmark_pack_id':'AUDIT-REGRESSION-v0.5','runtime_profile_id':'CURRENT_LOCAL_RUNTIME',
        'runtime_ref':'implementation.json','runtime_sha256':digest(out/'implementation.json'),
        'executed_fixture_ids':[c['fixture_id'] for c in cases],'results':cases,'capability_records':[{'capability_record_id':'LOCAL-INTEGRITY-SUITE-v0.5',**executor,
        'capability':'EXECUTABLE_INTEGRITY_REGRESSION','qualification_status':'REFERENCE_QUALIFIED' if all_pass else 'NOT_QUALIFIED',
        'evidence_fixture_ids':[c['fixture_id'] for c in cases],'scope':'Only the explicit synthetic checks in this run and the recorded local font/runtime.',
        'limitations':['Does not qualify clinical entailment, statistical chart geometry, full-source recall, or all PPTX rendering.'],
        'invalidation_triggers':['implementation/schema/font/runtime dependency change']}], 'overall_status':'PASS' if all_pass else 'FAIL'}
    write(out/'qualification.json',qualification)
    errors=validate_qualification(qualification,out)
    errors += [e.message for e in jsonschema.Draft202012Validator(read(S/'schemas/runtime_qualification_result.v0.2.schema.json')).iter_errors(qualification)]
    write(out/'summary.json',{'passed':sum(c['status']=='PASS' for c in cases),'total':len(cases),'failed':[c['fixture_id'] for c in cases if c['status']!='PASS'],'evidence_errors':errors})
    print(json.dumps(read(out/'summary.json'),indent=2)); return 0 if all_pass and not errors else 1

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--out',type=Path,required=True); p.add_argument('--font',type=Path,required=True); p.add_argument('--symbol-font',type=Path,required=True)
    a=p.parse_args(); sys.exit(run(a.out,a.font,a.symbol_font))
