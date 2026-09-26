"""Independent artifact geometry and source/narrative calibration checks.

The calibration oracle must be separately reviewed. This code cannot discover
all unknown medical propositions or infer clinical entailment from free text.
"""
import math
import re
from decimal import Decimal
from pathlib import Path
import xml.etree.ElementTree as ET
from integrity import canonical, diff, digest

def validate_editorial_asset_contract(contract, asset_path):
    """Verify asset identity and the minimum declarations needed for safe visual fusion.

    Pixel-level semantic inspection remains a separately recorded human/model review; this
    function deliberately does not claim that a hash proves absence of clinical content.
    """
    errors=[]
    asset_path=Path(asset_path)
    if not asset_path.is_file(): return ['EDITORIAL_ASSET_FILE_MISSING']
    if digest(asset_path).lower()!=contract.get('asset_sha256','').lower(): errors.append('EDITORIAL_ASSET_HASH_MISMATCH')
    prohibited={str(value).casefold() for value in contract.get('prohibited_content',[])}
    required={'text','numbers','clinical_claims'} if contract.get('asset_class')=='NONSEMANTIC_EDITORIAL_BASE' else set()
    if not required<=prohibited: errors.append('EDITORIAL_ASSET_PROHIBITIONS_INCOMPLETE')
    if contract.get('asset_class')=='NONSEMANTIC_EDITORIAL_BASE' and contract.get('layer_role')!='EDITORIAL_UNDERLAY': errors.append('EDITORIAL_BASE_LAYER_ROLE_INVALID')
    if contract.get('asset_class')=='SOURCE_BOUND_MEDICAL_ASSET' and contract.get('layer_role')!='SOURCE_BOUND_EVIDENCE': errors.append('SOURCE_BOUND_ASSET_LAYER_ROLE_INVALID')
    review=contract.get('content_review',{})
    if review.get('status')=='FAIL': errors.append('EDITORIAL_ASSET_CONTENT_REVIEW_FAILED')
    return errors

def validate_client_template_contract(contract, template_path):
    """Verify a client-provided PPTX template or background before it becomes a visual base."""
    errors=[]; template_path=Path(template_path)
    if not template_path.is_file(): return ['CLIENT_TEMPLATE_FILE_MISSING']
    if digest(template_path).lower()!=contract.get('template_sha256','').lower(): errors.append('CLIENT_TEMPLATE_HASH_MISMATCH')
    canvas=contract.get('canvas',[])
    if len(canvas)!=2 or any(not isinstance(v,(int,float)) or v<=0 for v in canvas): return errors+['CLIENT_TEMPLATE_CANVAS_INVALID']
    width,height=canvas
    def box_ok(box,label):
        if len(box)!=4 or any(not isinstance(v,(int,float)) or v<0 for v in box): errors.append(label+':INVALID_BOX'); return False
        x,y,w,h=box
        if w<=0 or h<=0 or x+w>width or y+h>height: errors.append(label+':OUTSIDE_CANVAS'); return False
        return True
    brands=[]; safe=[]
    for region in contract.get('brand_regions',[]):
        if box_ok(region.get('box',[]),region.get('region_id','UNKNOWN')): brands.append(region['box'])
    for region in contract.get('semantic_safe_regions',[]):
        if box_ok(region.get('box',[]),region.get('region_id','UNKNOWN')): safe.append(region['box'])
    for b in brands:
        for s in safe:
            if min(b[0]+b[2],s[0]+s[2])>max(b[0],s[0]) and min(b[1]+b[3],s[1]+s[3])>max(b[1],s[1]): errors.append('CLIENT_TEMPLATE_BRAND_OVERLAPS_SEMANTIC_SAFE_REGION')
    if contract.get('source_type')=='PPTX_TEMPLATE' and contract.get('application_mode')!='PRESERVE_MASTERS_AND_LAYOUTS': errors.append('CLIENT_TEMPLATE_PPTX_MODE_INVALID')
    if contract.get('source_type')=='BACKGROUND_IMAGE' and contract.get('application_mode')!='BACKGROUND_UNDERLAY': errors.append('CLIENT_TEMPLATE_BACKGROUND_MODE_INVALID')
    review=contract.get('review',{})
    if review.get('status')=='FAIL': errors.append('CLIENT_TEMPLATE_REVIEW_FAILED')
    return sorted(set(errors))

def validate_visual_base_selection(scene_contract):
    """Enforce the mutually exclusive visual-base choice on a final page contract."""
    base=scene_contract.get('visual_base')
    if base is None: return []
    errors=[]; mode=base.get('mode'); binding_id=base.get('binding_id'); binding_hash=str(base.get('binding_sha256','')).lower()
    assets=scene_contract.get('editorial_assets',[])
    editorial=[asset for asset in assets if asset.get('asset_class')=='NONSEMANTIC_EDITORIAL_BASE']
    if mode=='AI_EDITORIAL_BASE':
        matched=[asset for asset in editorial if asset.get('asset_id')==binding_id and str(asset.get('asset_sha256','')).lower()==binding_hash]
        if len(matched)!=1: errors.append('VISUAL_BASE_AI_ASSET_UNBOUND')
        fusion=scene_contract.get('editorial_fusion')
        if not fusion or fusion.get('asset_id')!=binding_id: errors.append('VISUAL_BASE_AI_FUSION_PLAN_MISSING')
    elif mode=='CLIENT_TEMPLATE':
        if editorial: errors.append('VISUAL_BASE_MUTUALLY_EXCLUSIVE_CONFLICT')
        if scene_contract.get('editorial_fusion'): errors.append('VISUAL_BASE_CLIENT_WITH_AI_FUSION_CONFLICT')
        template=scene_contract.get('client_template_binding')
        if not template: errors.append('VISUAL_BASE_CLIENT_TEMPLATE_BINDING_MISSING')
        elif template.get('template_id')!=binding_id or str(template.get('template_sha256','')).lower()!=binding_hash:
            errors.append('VISUAL_BASE_CLIENT_TEMPLATE_BINDING_MISMATCH')
    else: errors.append('VISUAL_BASE_MODE_INVALID')
    return errors

def validate_editorial_fusion_plan(plan, scene_contract):
    """Validate a source-bound plan for AI editorial-base fusion.

    This checker validates binding, layer ownership and declared visual-space limits. It does
    not infer whether the resulting page is aesthetically successful; that remains a
    hash-bound render review on the final artifact.
    """
    errors=[]
    canvas=scene_contract.get('canvas',[])
    if len(canvas)!=2 or any(not isinstance(v,(int,float)) or v<=0 for v in canvas):
        return ['FUSION_SCENE_CANVAS_INVALID']
    width,height=canvas
    def within(box, label):
        if len(box)!=4 or any(not isinstance(v,(int,float)) or v<0 for v in box):
            errors.append(label+':INVALID_BOX'); return
        x,y,w,h=box
        if w<=0 or h<=0 or x+w>width or y+h>height: errors.append(label+':OUTSIDE_CANVAS')
    source_ids=set(plan.get('source_identity',{}).get('semantic_object_ids',[]))
    layers=plan.get('semantic_layers',[])
    layer_ids=[layer.get('object_id') for layer in layers]
    if len(layer_ids)!=len(set(layer_ids)): errors.append('FUSION_DUPLICATE_SEMANTIC_LAYER')
    if set(layer_ids)!=source_ids: errors.append('FUSION_SEMANTIC_BINDING_GAP')
    for layer in layers:
        if layer.get('native_editable') is not True: errors.append(layer.get('object_id','UNKNOWN')+':SEMANTIC_LAYER_NOT_NATIVE_EDITABLE')
        if not layer.get('source_anchor'): errors.append(layer.get('object_id','UNKNOWN')+':SOURCE_ANCHOR_MISSING')
        if layer.get('z_order',0)<2: errors.append(layer.get('object_id','UNKNOWN')+':SEMANTIC_LAYER_Z_ORDER_INVALID')
        within(layer.get('box',[]),layer.get('object_id','UNKNOWN'))
    for zone in plan.get('editorial_zones',[]):
        if zone.get('z_order')!=0: errors.append(zone.get('zone_id','UNKNOWN')+':EDITORIAL_ZONE_Z_ORDER_INVALID')
        within(zone.get('box',[]),zone.get('zone_id','UNKNOWN'))
    for zone in plan.get('protected_zones',[]): within(zone.get('box',[]),zone.get('zone_id','UNKNOWN'))
    asset=plan.get('editorial_asset',{})
    matches=[candidate for candidate in scene_contract.get('editorial_assets',[]) if candidate.get('asset_id')==asset.get('asset_id')]
    if len(matches)!=1: errors.append('FUSION_EDITORIAL_ASSET_UNBOUND')
    else:
        bound=matches[0]
        if asset.get('asset_sha256','').lower()!=bound.get('asset_sha256','').lower(): errors.append('FUSION_EDITORIAL_ASSET_HASH_MISMATCH')
        if bound.get('asset_class')!='NONSEMANTIC_EDITORIAL_BASE' or bound.get('layer_role')!='EDITORIAL_UNDERLAY': errors.append('FUSION_EDITORIAL_ASSET_ROLE_INVALID')
    scene_fusion=scene_contract.get('editorial_fusion')
    if not scene_fusion: errors.append('FUSION_SCENE_BINDING_MISSING')
    else:
        if scene_fusion.get('fusion_plan_id')!=plan.get('fusion_plan_id'): errors.append('FUSION_PLAN_ID_MISMATCH')
        if scene_fusion.get('asset_id')!=asset.get('asset_id'): errors.append('FUSION_SCENE_ASSET_MISMATCH')
        if scene_fusion.get('integration_mode')!=plan.get('integration_mode'): errors.append('FUSION_MODE_MISMATCH')
        plan_zones={z.get('zone_id'):z for z in plan.get('protected_zones',[])}
        for scene_zone in scene_fusion.get('protected_zones',[]):
            planned=plan_zones.get(scene_zone.get('zone_id'))
            if planned is None or planned.get('box')!=scene_zone.get('box') or planned.get('minimum_uncovered_area_ratio')!=scene_zone.get('minimum_uncovered_area_ratio'):
                errors.append('FUSION_PROTECTED_ZONE_MISMATCH')
    review=plan.get('render_review',{})
    if review.get('status')=='FAIL': errors.append('FUSION_RENDER_REVIEW_FAILED')
    return sorted(set(errors))

def validate_chart_svg(contract, path):
    """Read actual SVG primitives, then recompute geometry from raw decimal data.

    Supported: simple linear bars, linear/log point/interval charts, polylines.
    No transforms, clipping, CSS or hidden styling in this qualified subset.
    """
    errors=[]
    root=ET.parse(path).getroot(); nodes={}
    for node in root.iter():
        if node.tag.split('}')[-1] in ('rect','circle','line','polyline','path','polygon') and not node.get('id'): errors.append('UNIDENTIFIED_GEOMETRY')
        if any(k in node.attrib for k in ('transform','clip-path','mask','style','display','visibility','opacity','fill-opacity','stroke-opacity','filter')):
            errors.append('UNQUALIFIED_SVG_TRANSFORM_OR_STYLE')
        if node.tag.split('}')[-1] in ('style','script','use'): errors.append('UNQUALIFIED_SVG_ELEMENT')
        if 'id' in node.attrib:
            if node.attrib['id'] in nodes: errors.append('DUPLICATE_SVG_ID')
            nodes[node.attrib['id']]=node
    if contract.get('comparable') is not True: errors.append('COMPARABILITY_NOT_APPROVED')
    axis=contract['axis']
    if axis.get('dimension') not in ('x','y'): return ['INVALID_AXIS_DIMENSION']
    try:
        lo,hi=map(Decimal,axis['domain']); start,end=map(float,axis['pixel_range'])
        if not lo.is_finite() or not hi.is_finite() or lo>=hi or not all(math.isfinite(v) for v in (start,end)) or start==end: raise ValueError()
        if axis['scale'] not in ('linear','log10'): raise ValueError()
        if axis['scale']=='log10' and lo<=0: raise ValueError()
    except (ValueError,TypeError,ArithmeticError): return ['INVALID_AXIS']
    def mapped(value):
        v=Decimal(value)
        if not v.is_finite() or v<lo or v>hi: raise ValueError('data clipped/outside domain')
        fraction=float((v-lo)/(hi-lo)) if axis['scale']=='linear' else (math.log10(float(v))-math.log10(float(lo)))/(math.log10(float(hi))-math.log10(float(lo)))
        return start+fraction*(end-start)
    def attrs(oid,tag,values):
        node=nodes.get(oid)
        if node is None: errors.append(oid+':MISSING'); return
        if node.tag.split('}')[-1]!=tag: errors.append(oid+':WRONG_PRIMITIVE'); return
        if tag in ('rect','circle','line','polyline'):
            fill=node.get('fill','black'); stroke=node.get('stroke','none')
            # Closed paint grammar: reject rgba()/currentColor/inheritance/paint servers.
            if any(not re.fullmatch(r'(?:#[0-9a-fA-F]{6}|black|white|navy|blue|red|green|gray|grey|none|transparent)',p) for p in (fill,stroke)):
                errors.append(oid+':UNQUALIFIED_PAINT_SYNTAX')
            forbidden={'none','transparent','white','#ffffff','#fff'}
            painted_fill=tag in ('rect','circle') and fill.lower() not in forbidden
            try: painted_stroke=stroke.lower() not in forbidden and float(node.get('stroke-width','1'))>0
            except ValueError: painted_stroke=False
            if not painted_fill and not painted_stroke: errors.append(oid+':INVISIBLE_MARK')
            if any('url(' in c.lower() for c in (fill,stroke)): errors.append(oid+':UNQUALIFIED_PAINT')
            if tag=='circle':
                try:
                    radius=float(node.get('r','0'))
                    if not math.isfinite(radius) or radius<=0: errors.append(oid+':INVISIBLE_POINT')
                except ValueError: errors.append(oid+':INVALID_RADIUS')
        for k,v in values.items():
            try:
                n=float(node.attrib[k])
                if not math.isfinite(n) or abs(n-v)>0.1: errors.append(oid+':GEOMETRY_'+k)
            except (KeyError,ValueError): errors.append(oid+':INVALID_'+k)
    def text(oid,expected):
        n=nodes.get(oid)
        if n is None or ''.join(n.itertext())!=expected: errors.append(oid+':LABEL_MISMATCH')
    text('axis-unit',contract['unit_label'])
    text('context',contract['context_label'])
    for tick in axis['ticks']:
        text(tick['id'],tick['label'])
        try: attrs(tick['id'],'text',{axis['dimension']:mapped(tick['value'])})
        except ValueError: errors.append('TICK_OUT_OF_DOMAIN')
    seen=set()
    for series in contract['series']:
        text('legend-'+series['id'],series['label'])
        point_positions=[]
        for datum in series['data']:
            oid=datum['id']
            if oid in seen: errors.append('DUPLICATE_DATA_ID')
            seen.add(oid)
            if datum.get('value') is None:
                if oid in nodes: errors.append(oid+':MISSING_RENDERED_AS_VALUE')
                continue
            if not isinstance(datum['value'],str): errors.append(oid+':DECIMAL_STRING_REQUIRED'); continue
            try: value=mapped(datum['value'])
            except (ValueError,ArithmeticError): errors.append(oid+':DATA_CLIPPED'); continue
            text('label-'+oid,datum['display'])
            slot=float(datum['slot'])
            if series['kind']=='bar':
                if axis['scale']!='linear' or axis.get('zero_policy')!='REQUIRED' or not lo<=0<=hi:
                    errors.append('BAR_ZERO_BASELINE_REQUIRED'); continue
                base=mapped('0'); dim=axis['dimension']; cross='x' if dim=='y' else 'y'
                attrs(oid,'rect',{dim:min(value,base),cross:slot,'height' if dim=='y' else 'width':abs(base-value),'width' if dim=='y' else 'height':float(datum['thickness'])})
            elif series['kind'] in ('point','line','interval'):
                x,y=(value,slot) if axis['dimension']=='x' else (slot,value)
                attrs(oid,'circle',{'cx':x,'cy':y}); point_positions.append((x,y))
                if series['kind']=='interval':
                    try:
                        if not Decimal(datum['lower'])<=Decimal(datum['value'])<=Decimal(datum['upper']): raise ValueError()
                        low,high=mapped(datum['lower']),mapped(datum['upper'])
                        positions={'x1':low,'x2':high,'y1':slot,'y2':slot} if axis['dimension']=='x' else {'x1':slot,'x2':slot,'y1':low,'y2':high}
                        attrs('interval-'+oid,'line',positions)
                    except (KeyError,ValueError,ArithmeticError): errors.append(oid+':INVALID_INTERVAL')
            else: errors.append('UNQUALIFIED_CHART_KIND')
        if series['kind']=='line':
            n=nodes.get('series-'+series['id'])
            attrs('series-'+series['id'],'polyline',{})
            try:
                actual=[tuple(map(float,p.split(','))) for p in n.attrib['points'].split()]
                if len(actual)!=len(point_positions) or any(abs(a-b)>0.1 for p,q in zip(actual,point_positions) for a,b in zip(p,q)): errors.append('LINE_POINT_ORDER_OR_GEOMETRY')
            except (AttributeError,KeyError,ValueError): errors.append('LINE_MISSING')
    # Reject unexpected geometry that could introduce extra/misleading data marks.
    allowed=seen|{'interval-'+x for x in seen}|{'series-'+s['id'] for s in contract['series']}|set(contract.get('allowed_nondata_ids',[]))
    for oid,n in nodes.items():
        if n.tag.split('}')[-1] in ('rect','circle','line','polyline','path','polygon') and oid not in allowed: errors.append(oid+':UNREGISTERED_GEOMETRY')
    return sorted(set(errors))

def validate_coverage(source, reference, extracted):
    """Independent, anchored inventory comparison; UNKNOWN denominator cannot be 100%."""
    errors=[]
    source_hash=__import__('hashlib').sha256(canonical(source).encode()).hexdigest()
    if reference.get('source_sha256')!=source_hash or extracted.get('source_sha256')!=source_hash: errors.append('SOURCE_HASH_MISMATCH')
    if reference.get('review_run_id')==extracted.get('extraction_run_id') or reference.get('origin') not in ('INDEPENDENT_SOURCE_REVIEW','SYNTHETIC_GOLD_ORACLE'):
        errors.append('NONINDEPENDENT_INVENTORY')
    if reference.get('denominator_status')!='REVIEWED_COMPLETE': errors.append('UNKNOWN_DENOMINATOR')
    if set(extracted.get('page_ids',[]))!=set(source['pages']): errors.append('PAGE_COVERAGE_GAP')
    if set(extracted.get('section_ids',[]))!=set(reference['section_ids']): errors.append('SECTION_COVERAGE_GAP')
    expected=reference['objects']; candidates=extracted.get('objects',[])
    if len({x['id'] for x in expected})!=len(expected) or len({x['id'] for x in candidates})!=len(candidates): errors.append('DUPLICATE_COVERAGE_ID')
    for obj in expected:
        anchor=obj['anchor']; body=source['pages'].get(anchor['page'],'')
        if body[anchor['start']:anchor['end']]!=anchor['quote']: errors.append(obj['id']+':INVALID_SOURCE_ANCHOR')
    byid={x['id']:x for x in candidates}
    for obj in expected:
        if obj['id'] not in byid: errors.append(obj['id']+':OMITTED')
        elif diff(obj,byid[obj['id']]): errors.append(obj['id']+':SEMANTIC_OR_ANCHOR_MISMATCH')
    if set(byid)-{x['id'] for x in expected}: errors.append('UNREVIEWED_EXTRA_OBJECT')
    return errors

def validate_narrative(reference, narrative):
    """Check against independently annotated wording; unseen wording needs review."""
    errors=[]
    if reference.get('review_run_id')==narrative.get('generation_run_id'): errors.append('SELF_REVIEW_NOT_CALIBRATED')
    if not reference.get('review_run_id'): errors.append('REVIEW_ID_MISSING')
    expected=reference['approved_assertions']; seen=set(); covered=set(); seconds=0; present=set()
    question_bindings=reference.get('question_assertions',{})
    if any(not question_bindings.get(q) for q in reference['required_questions']): errors.append('INDEPENDENT_QUESTION_BINDINGS_MISSING')
    dependencies=reference.get('section_dependencies')
    if dependencies is None: errors.append('INDEPENDENT_DEPENDENCIES_MISSING'); dependencies={}
    for section in narrative['sections']:
        sid=section['id']
        if sid in seen: errors.append('DUPLICATE_NARRATIVE_SECTION')
        for dep in section.get('depends_on',[]):
            if dep not in seen: errors.append(sid+':DEPENDENCY_ORDER')
        if not set(dependencies.get(sid,[]))<=set(section.get('depends_on',[])): errors.append(sid+':REQUIRED_DEPENDENCY_MISSING')
        seen.add(sid)
        duration=section['seconds']
        if not isinstance(duration,(int,float)) or not math.isfinite(duration) or duration<=0: errors.append(sid+':INVALID_DURATION')
        else: seconds+=duration
        valid_section=set()
        for assertion in section['assertions']:
            approved=expected.get(assertion['id'])
            if approved is None or diff(approved,assertion): errors.append(assertion['id']+':UNREVIEWED_OR_CHANGED_ASSERTION')
            else: valid_section.add(assertion['id']); present.add(assertion['id'])
        for question in section.get('answers',[]):
            required=set(question_bindings.get(question,[]))
            if required and required<=valid_section: covered.add(question)
            else: errors.append(question+':ANSWER_WITHOUT_REVIEWED_ASSERTIONS')
    if not set(reference['required_questions'])<=covered: errors.append('QUESTION_COVERAGE_GAP')
    if not set(reference['required_questions'])<=set(narrative.get('closure_questions',[])): errors.append('CLOSURE_GAP')
    closing=set(narrative.get('closure_assertion_ids',[]))
    if not closing<=present: errors.append('UNSUPPORTED_CLOSURE_ASSERTION')
    for q in reference['required_questions']:
        if not set(question_bindings.get(q,[]))<=closing: errors.append(q+':CLOSURE_WITHOUT_ASSERTIONS')
    if seconds>reference['duration_seconds']: errors.append('DURATION_OVERFLOW')
    if narrative.get('scope')!=reference['scope']: errors.append('SCOPE_EXPANSION')
    return errors
