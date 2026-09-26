"""Adapt the existing P05 content contract to complete source-bound AND objects."""
import argparse
import re
from pathlib import Path
from integrity import read, write, digest, factor_and

def formatting_key(text):
    return re.sub(r'\s+','',text.replace('⁻¹','^-1'))

def adapt(content_path, w10_path):
    content=read(content_path)
    p05=next(p for p in read(w10_path)['pages'] if p['page_id']=='P05')
    if content.get('page_id')!='P05' or content.get('logic')!='AND': raise ValueError('P05 AND contract required')
    if len(content['phenotypes'])!=len(p05['phenotype_bundles']) or len(content['phenotypes'])!=3: raise ValueError('P05 bundle coverage mismatch')
    original={'logic':'AND','source_file_sha256':digest(w10_path),'page_id':'P05','bundles':[]}
    mappings=[]
    for c,b in zip(content['phenotypes'],p05['phenotype_bundles']):
        if c['name']!=b['phenotype'] or c['criteria_ref']!=b['criteria_ref'] or b['logic']!='AND': raise ValueError('bundle ownership mismatch')
        texts=c['guidewire_conditions']+c['ach_conditions']
        if len(texts)!=len(b['components']): raise ValueError('condition coverage mismatch')
        facts=[]
        for i,(text,source) in enumerate(zip(texts,b['components'])):
            raw=source.get('display',source.get('source_component'))
            if formatting_key(raw)!=formatting_key(text): raise ValueError('source/display mismatch: '+str(raw))
            fid=source.get('fact',b['criteria_ref']+f':component-{i+1}')
            m=re.search(r'([<>≥≤])\s*([0-9]+(?:\.[0-9]+)?)',text)
            numeric={'operator':m[1],'value':m[2],'unit':('%' if '%' in text else 'mmHg·cm⁻¹·s⁻¹' if 'mmHg' in text else '')} if m else None
            facts.append({'fact_id':fid,'text':text,'context':'CMVD-2023:INOCA-classification:p15','source_namespace':'W10:P05','numeric':numeric})
            mappings.append({'fact_id':fid,'source_string':raw,'display_string':text,'formatting_rule':'P05 whitespace + ^-1 to superscript -1 only'})
        original['bundles'].append({'bundle_id':b['criteria_ref'],'facts':facts})
    rec=p05['classification_approach']['recommendation_binding']
    if formatting_key(content['classification_approach'])!=formatting_key(p05['classification_approach']['label']): raise ValueError('classification mismatch')
    if content['recommendation_binding']!=f"{rec['class']} / {rec['evidence_level']}": raise ValueError('recommendation mismatch')
    locks={k:content[k] for k in ('title','primary_message','classification_approach','recommendation_binding','scope_lock','visible_source','review_requirement')}
    # Textual entailment of paraphrased title/message/scope is reviewed separately.
    return original,factor_and(original),mappings,{'content_sha256':digest(content_path),'w10_sha256':digest(w10_path),'exact_content_locks':locks,
        'semantic_review_required':['title/message entailment','scope translation','source citation identity'],
        'claim_boundary':'Conditions and recommendation binding checked against existing W10; no new clinical source approval.'}

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--content',type=Path,required=True); p.add_argument('--w10',type=Path,required=True); p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists(): raise FileExistsError('Use a new output directory')
    values=adapt(a.content,a.w10)
    for name,value in zip(('original_semantics','factored_scene','source_display_mappings','content_locks'),values): write(a.out/(name+'.json'),value)
    print('P05 adapter PASS: exact source conditions and explicit content locks emitted')
