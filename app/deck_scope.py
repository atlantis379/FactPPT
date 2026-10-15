"""Explicit prefix runs retain the whole spec and validate only requested pages.

Source/fact/semantic gates still apply to every displayed object. Coverage outside
the prefix is recorded as outside this run, never as unsupported or completed.
"""
from __future__ import annotations
import copy
from app.fact57098 import require
from factdeck.deck import check


def scope_of(deck):
    value=deck.get('generation_scope')
    if value is None: return None
    require(isinstance(value,dict) and set(value)=={'kind','page_count','total_pages','base_page_ids'},'生成范围字段无效',422)
    require(value['kind']=='PREFIX','只支持显式前N页生成',422)
    n=value['page_count']; pages=deck['pages']
    require(isinstance(n,int) and not isinstance(n,bool) and 0<n<len(pages),'前N页范围须小于全套页数',422)
    require(value['total_pages']==len(pages) and value['base_page_ids']==[p['id'] for p in pages],'生成范围须保留全套页面编号和数量',422)
    return value


def selected_spec(deck):
    scope=scope_of(deck)
    if not scope: return deck
    view=copy.deepcopy(deck);view['pages']=view['pages'][:scope['page_count']]
    return view


def context(deck,outline,sections,requirements,parts):
    scope=scope_of(deck)
    if not scope: return deck,outline,sections,requirements,parts,None
    view=selected_spec(deck)
    ids={x for p in view['pages'] for x in p.get('point_ids') or []}
    known={p['id'] for o in outline for p in o.get('points') or []}
    require(bool(ids) and ids<=known,'范围内页面须标明有效的教学要点',422)
    oids={o['id'] for o in outline if ids & {p['id'] for p in o.get('points') or []}}
    explicit={x for p in view['pages'] for x in p.get('section_ids') or []}
    require(explicit<={s['id'] for s in sections},'范围内页面引用了不存在的总结章节',422)
    rows=[]
    for o in outline:
        if o['id'] in oids:
            item=copy.deepcopy(o);item['points']=[p for p in item.get('points') or [] if p['id'] in ids];rows.append(item)
    secs=[]
    for s in sections:
        if s['id'] not in explicit and s.get('outline_id') not in oids: continue
        item=copy.deepcopy(s)
        if item.get('outline_id'):
            msg=item.get('message')
            if msg:
                # Preserve the approved core and whole relations as context; do
                # not turn a partial relation into a new singleton/sub-branch.
                # Only enforce display of limits included in this prefix.
                msg['roles']={k:v for k,v in msg['roles'].items() if v!='limit' or k in ids}
        secs.append(item)
    req=copy.deepcopy(requirements);req['target_pages']=len(view['pages'])
    selected_sections={s['id'] for s in secs}
    view['omissions']=[o for o in view.get('omissions') or [] if o.get('section_id') in selected_sections]
    descriptor={**copy.deepcopy(scope),'page_ids':[p['id'] for p in view['pages']],
                'outside_scope_points':[p['id'] for o in outline for p in o.get('points') or [] if p['id'] not in ids],
                'outside_scope_sections':[s['id'] for s in sections if s['id'] not in selected_sections],
                'complete_deck':False,'part_page_budget_checked':False}
    # Whole-chapter page budgets cannot be judged from a prefix run.
    return view,rows,secs,req,[],descriptor


def check_spec(deck,facts,terms,outline,sections,requirements,parts,key_points=None):
    view,rows,secs,req,parts,scope=context(deck,outline,sections,requirements,parts)
    if scope and key_points is not None:
        # a first-N-pages scope is partial by design: check the key points it names, not completeness
        named={x for p in view['pages'] for x in p.get('key_point_ids') or []}
        key_points={k:v for k,v in key_points.items() if k in named}
    result=check(view,facts,terms,rows,secs,req,parts,key_points=key_points)
    if scope: result['scope']=scope;result['coverage']['scope']=scope
    return result
