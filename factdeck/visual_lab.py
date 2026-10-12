"""Deterministic contracts for source-bound visual experiments.

This module neither generates images nor approves clinical or aesthetic content.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
from collections import Counter

STRATEGIES = {
    'textbook': {'name':'教材式结构图','direction':'Precise educational diagrams with explicitly labelled nodes, clean grouping braces and visible condition boundaries. Clear hierarchy and generous whitespace. The main explanation is the diagram itself, not icons added to paragraphs.'},
    'editorial': {'name':'期刊式信息图','direction':'Refined journal editorial information design: strong grid, restrained forest-green emphasis, elegant typography, and diagrams integrated with their exact labels. Use visual alignment and hierarchy to expose the source structure.'},
    'scenario': {'name':'场景式教学插画','direction':'Sophisticated educational scene illustration integrated with a labelled explanation. Scenes must explain the source concept, never replace its explicit conditions with a vague metaphor. Avoid decorative landscapes, buildings, books and botanical filler.'},
}

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def block_texts(page):
    from factdeck.visual_layout import text_of
    model=page['lock']['model']
    texts=[text_of(t).replace('\x01','') for t in model['texts']]
    texts.extend(text_of(cell).replace('\x01','') for table in model.get('tables',[]) for row in table['rows'] for cell in row['cells'])
    return texts

def block_bindings(page):
    model=page['lock']['model'];bindings=[{'kind':'text','index':i} for i in range(len(model['texts']))]
    bindings.extend({'kind':'table_cell','table':i,'row':j,'column':k} for i,t in enumerate(model.get('tables',[])) for j,row in enumerate(t['rows']) for k,_ in enumerate(row['cells']))
    return bindings

def validate_graph(source_pages, graph):
    known={p['number']:p for p in source_pages}
    if len(graph['pages'])!=len(known):raise ValueError('Graph must cover each selected page')
    if {p['page']['number'] for p in graph['pages']}!=set(known):raise ValueError('Graph page set differs')
    for p in graph['pages']:
        source=known[p['page']['number']]
        if p['page']['id']!=source['id']:raise ValueError('Page identity differs')
        blocks=block_texts(source)
        if p['block_texts']!=[{'block_index':i,'text':text} for i,text in enumerate(blocks)]:raise ValueError('Source text changed')
        alias_ids=set()
        for alias in p.get('render_aliases',[]):
            i=alias['block_index'];targets=alias['covered_by_block_indices']
            if i in alias_ids or i not in range(len(blocks)) or not targets or i in targets or any(t not in range(len(blocks)) for t in targets):raise ValueError('Invalid duplicate alias')
            normalized=lambda value:re.sub(r'\s+','',value)
            if normalized(blocks[i])!=normalized(''.join(blocks[t] for t in targets)):raise ValueError('Alias would remove unique source content')
            alias_ids.add(i)
        if any(alias_ids.intersection(a['covered_by_block_indices']) for a in p.get('render_aliases',[])):raise ValueError('Duplicate aliases cannot form chains')
        fs=p['text_fragments'];ids=[f['id'] for f in fs]
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate fragment IDs')
        by_id={f['id']:f for f in fs}
        for i,text in enumerate(blocks):
            fragments=sorted([f for f in fs if f['block_index']==i],key=lambda f:f['start'])
            cursor=0
            for f in fragments:
                if not (f['start']==cursor and cursor<f['end']<=len(text)):raise ValueError('Gap, overlap or invalid fragment')
                if f['quote']!=text[f['start']:f['end']]:raise ValueError('Fragment is not verbatim')
                cursor=f['end']
            if cursor!=len(text):raise ValueError('Incomplete text block')
        if any(f['block_index'] not in range(len(blocks)) for f in fs):raise ValueError('Unknown source block')
        rs=p['regions'];region_ids=[r['id'] for r in rs]
        if len(set(region_ids))!=len(region_ids):raise ValueError('Duplicate regions')
        used=[]
        for r in rs:
            assigned=r['label_fragment_ids']+r['body_fragment_ids'];used+=assigned
            if any(i not in by_id for i in assigned):raise ValueError('Unknown fragment reference')
            if any(by_id[i]['block_index'] not in r['source_block_indices'] for i in assigned):raise ValueError('Region source binding differs')
            if r.get('parent_region_id') and r['parent_region_id'] not in region_ids:raise ValueError('Unknown parent region')
        parents={r['id']:r.get('parent_region_id') for r in rs}
        for rid in parents:
            seen=set();current=rid
            while current:
                if current in seen:raise ValueError('Cyclic scope regions')
                seen.add(current);current=parents[current]
        if Counter(used)!=Counter(ids):raise ValueError('Each fragment must belong to exactly one region')
        for f in fs:
            if any(i not in by_id for i in f.get('qualifier_for',[])):raise ValueError('Unknown qualifier target')
        for r in p['relations']:
            if r['type'] not in {'classification','contrast','condition','context','in_order'}:raise ValueError('Unsupported relation type')
            if any(i not in region_ids for i in r['from']+r['to']):raise ValueError('Unknown relation endpoint')
            mappings=r['source_mappings']
            quoted='\n'.join(''.join(by_id[i]['quote'] for i in m['fragment_ids']) for m in mappings)
            if quoted!=r['support_quote']:raise ValueError('Relation support does not match mapped spans')
            for m in mappings:
                if m['block_index'] not in r['source_block_indices'] or any(by_id[i]['block_index']!=m['block_index'] for i in m['fragment_ids']):raise ValueError('Relation source binding differs')
    return {'structural_valid':True,'pages':len(known),'graph_sha256':digest(graph),'medical_approval':False}

def validate_design(graph_page, design):
    if design.get('page')!=graph_page['page']['number']:raise ValueError('Design page differs')
    if design.get('strategy') not in STRATEGIES:raise ValueError('Unknown strategy')
    known={r['id']:r for r in graph_page['regions']}
    rows=design['regions']
    if len(rows)!=len(known) or {r['id'] for r in rows}!=set(known):raise ValueError('Design must place every region exactly once')
    placed={r['id']:r for r in rows}
    for row in rows:
        if set(row)-{'id','x','y','w','h','render_instruction'}:raise ValueError('Design may not replace text or source binding')
        x,y,w,h=(row[k] for k in ('x','y','w','h'))
        if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in (x,y,w,h)) or w<=0 or h<=0 or x<0 or y<0 or x+w>1280 or y+h>720:raise ValueError('Region out of bounds')
        parent=known[row['id']].get('parent_region_id')
        if parent:
            p=placed[parent]
            if x<p['x'] or y<p['y'] or x+w>p['x']+p['w'] or y+h>p['y']+p['h']:raise ValueError('Scope must contain its child region')
    if {r['id'] for r in design['relations']}!={r['id'] for r in graph_page['relations']}:raise ValueError('Every bound relation needs a visual treatment')
    if any(set(r)-{'id','render_instruction'} for r in design['relations']):raise ValueError('Design may not replace relationship type')
    return {'structural_valid':True,'design_sha256':digest(design),'medical_approval':False}

def compile_prompt(graph_page, design, palette):
    validate_design(graph_page,design)
    fragments={f['id']:f for f in graph_page['text_fragments']}
    # The exact render strings occur in one section only, with a unique owner.
    render=[]
    alias_indices={a['block_index'] for a in graph_page.get('render_aliases',[])}
    for region in graph_page['regions']:
        ids=region['label_fragment_ids']+region['body_fragment_ids']
        ids=[i for i in ids if fragments[i]['block_index'] not in alias_indices]
        ids=sorted(ids,key=lambda i:(fragments[i]['block_index'],fragments[i]['start']))
        text=''.join(fragments[i]['quote'] for i in ids).replace('\n','')
        render.append({'region':region['id'],'text':text})
    forbidden=list(graph_page['forbidden_implications'])
    # Referring to an exact locked sentence in a prohibition can make the image
    # model print it twice. Preserve the constraint through its unique region ID.
    for row in sorted(render,key=lambda row:len(row['text']),reverse=True):
        if len(row['text'])>=8:
            forbidden=[value.replace(row['text'],'[region '+row['region']+']') for value in forbidden]
    directions={'regions':design['regions'],'relations':[{'id':r['id'],'type':r['type'],'from':r['from'],'to':r['to']} for r in graph_page['relations']],
                'relationship_treatment':design['relations'],'scope':[{'region':r['id'],'parent':r.get('parent_region_id')} for r in graph_page['regions']],
                'forbidden_implications':forbidden}
    if alias_indices:
        directions['nonrendering_alias_regions']=[r['id'] for r in graph_page['regions'] if (r['label_fragment_ids']+r['body_fragment_ids']) and all(fragments[i]['block_index'] in alias_indices for i in r['label_fragment_ids']+r['body_fragment_ids'])]
    render_rule='\nSOLE TEXT TO RENDER: each region string exactly ONCE. Natural wrapping permitted. Never also render its original whole paragraph or repeat it in a caption. Never write prose from the geometry instructions. Do not add headings or summary labels.\n'
    if alias_indices:
        render_rule='\nSOLE TEXT TO RENDER: each nonempty region string exactly ONCE. Empty alias regions have no text or visible container; their source obligations are already covered verbatim by other nodes. Natural wrapping permitted. Never also render its original whole paragraph or repeat it in a caption. Never write prose from the geometry instructions. Do not add headings or summary labels.\n'
    prompt=('Create ONE complete 16:9 academic undergraduate teaching slide, 1280x720. '+STRATEGIES[design['strategy']]['direction']+
            '\nThe attached common template image supplies palette and typography only. No copied template wording. '+json.dumps(palette,ensure_ascii=False)+
            '\nExplain the source through substantial diagram geometry and directly attached labels. Page title dominates navigation and page number. Peers have equal visual treatment. Keep conditions and qualifiers visibly attached to their governed nodes. All text must fit and remain legible. No new medical entities, mechanisms, numerical data, statistical uncertainty, implication of causality or inevitable progression. Do not draw pathogens, sealed barriers or invented anatomical details. No error bars, distribution curves or data axes unless source data explicitly requires them.'+
            '\nGEOMETRY AND DIRECTIONS (instructions only, never print IDs or prose from this section):\n'+json.dumps(directions,ensure_ascii=False)+
            render_rule+json.dumps(render,ensure_ascii=False)+
            '\nFor conceptual scenes without measured data, the only optional added nature marker is: 概念示意，非研究数据. This reference image is not content authority; do not add conclusions.')
    # A direction cannot repeat a substantial locked render string.
    direction_text=json.dumps(directions,ensure_ascii=False)
    for row in render:
        if len(row['text'])>=8 and row['text'] in direction_text:raise ValueError('Direction repeats locked text; use region IDs')
    return prompt
