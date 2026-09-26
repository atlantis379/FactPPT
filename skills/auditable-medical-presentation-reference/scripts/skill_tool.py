"""Portable local CLI. Run with --help; paths are explicit and never inferred from a host."""
import argparse
import importlib.util
import platform
import re
from pathlib import Path
import sys
import zipfile
from integrity import read, write, digest, safe_path, validate_state, validate_qualification, validate_quality_evaluation
from medical_gates import VALIDATORS

SKILL = Path(__file__).resolve().parents[1]

def validate_beautification_plan(data, deck):
    errors=[]
    if not data.get('native_editable'): errors.append('native_editable:MUST_BE_TRUE')
    protected=set(data.get('external_asset_policy',{}).get('protected_native_roles',[]))
    if not {'CLAIM','NUMERIC_EVIDENCE','SOURCE','RELATIONSHIP'} <= protected:
        errors.append('external_asset_policy:PROTECTED_NATIVE_ROLES_INCOMPLETE')
    deck_pages=deck.get('pages',[]); plan_pages=data.get('pages',[])
    if len(deck_pages)!=len(plan_pages): errors.append('pages:COUNT_MISMATCH')
    for source, planned in zip(deck_pages,plan_pages):
        page_id=source.get('page_id','UNKNOWN')
        if planned.get('page_id')!=page_id: errors.append(page_id+':PAGE_ID_MISMATCH')
        expected_claims={str(x.get('id')) for x in source.get('claims',[])}
        if set(planned.get('claim_ids',[]))!=expected_claims: errors.append(page_id+':CLAIM_ID_MISMATCH')
        expected_relations={str(x.get('id')) for x in source.get('relationships',[])}
        if set(planned.get('relationship_ids',[]))!=expected_relations: errors.append(page_id+':RELATIONSHIP_ID_MISMATCH')
        element_names={x.get('name') for x in planned.get('elements',[])}
        if {'claim:'+x for x in expected_claims}!={x for x in element_names if str(x).startswith('claim:')}:
            errors.append(page_id+':CLAIM_OBJECT_MISMATCH')
        connector_names={x.get('name') for x in planned.get('connectors',[])}
        if {'clinical_relationship:'+x for x in expected_relations}!=connector_names:
            errors.append(page_id+':CONNECTOR_OBJECT_MISMATCH')
        for element in planned.get('elements',[]):
            p=element.get('position',{}); left=p.get('left',-1); top=p.get('top',-1); width=p.get('width',0); height=p.get('height',0)
            if left<0 or top<0 or width<=0 or height<=0 or left+width>1280 or top+height>720:
                errors.append(page_id+':OUT_OF_BOUNDS:'+str(element.get('name')))
    return errors

CORE_ROLES={'definition','claim','evidence','mechanism','classification','process','comparison',
            'problem','solution','metric','risk','recommendation','example','context','conclusion','other'}
DIFFICULTY_FLAGS={'undefined_term','multi_step','contrastive_pair','fact_dense',
                  'negation_or_exception','long_chain','cross_reference'}
WORKING_LAYER_MARKS=(
    (r'原文\s*[:：，]', 'CITATION_MARKER'),
    (r'[（(]?块\s*\d', 'BLOCK_REFERENCE'),
    (r'block[_ ]?id|node[_ ]?id|claim[_ ]?id', 'INTERNAL_ID'),
    (r'教材第\s*\d+\s*页[·\s]*块', 'AUDIT_LOCATOR'),
    (r'教学整理|待复核|需复核|待核对', 'EDITORIAL_LABEL'),
    (r'这是全章|本页是|暗线就出来|上版|本版', 'STRUCTURE_SELF_COMMENTARY'),
    (r'…', 'ELIDED_QUOTATION'),
)
FIGURE_INTENTS={'NONE','CAUSAL','PROGRESSION','COMPARISON','TAXONOMY','PROCESS','SCALE','DATA','QUOTATION'}

def validate_reading_structure(data, expected_run=None):
    """Deterministic subset of W01-R v0.2. Material-agnostic: anything material-specific must be
    declared in `profile`, and this gate checks that it was. Judgement fields (thread quality,
    why_here usefulness, difficulty reasons, narrative quality) are reviewer-assessed and are NOT
    assessed here; the result says so explicitly."""
    errors=[]; unassessed=[]
    if data.get('schema_version')!='reading_structure_artifact.v0.2':
        errors.append('schema_version:SUPERSEDED_OR_UNKNOWN:'+str(data.get('schema_version')))
    # --- profile: everything material-specific must be declared
    prof=data.get('profile') or {}
    for key in ('material_kind','language','role_vocabulary','signal_lexicon','relation_lexicon'):
        if not prof.get(key): errors.append('profile:'+key.upper()+':NOT_DECLARED')
    lexicon=(prof.get('signal_lexicon') or {})
    if not lexicon.get('emphasis_markers'): errors.append('profile:SIGNAL_LEXICON:EMPHASIS_MARKERS_NOT_DECLARED')
    if not lexicon.get('fact_pattern'): errors.append('profile:SIGNAL_LEXICON:FACT_PATTERN_NOT_DECLARED')
    extensions=set((prof.get('role_vocabulary') or {}).get('extensions') or [])
    allowed=CORE_ROLES|extensions
    # --- reading completeness
    rp=data.get('reading_pass',{})
    if rp.get('blocks_read')!=rp.get('blocks_total'): errors.append('reading_pass:BLOCKS_NOT_FULLY_READ')
    total=rp.get('chars_total',0) or 1
    if rp.get('chars_read',0)/total<0.98: errors.append('reading_pass:CHARACTERS_NOT_FULLY_READ')
    if rp.get('reading_mode')!='FULL_TEXT_READ': errors.append('reading_pass:NOT_A_FULL_TEXT_READ')
    if rp.get('structure_derivation')!='LLM_SEMANTIC_SYNTHESIS': errors.append('reading_pass:MECHANICAL_STRUCTURE_DERIVATION')
    # --- reading freshness: the reading must belong to the run under validation (REG-READ-018).
    # Completeness above certifies that a reading happened; it cannot certify that it happened for
    # THIS run. A frozen authored answer file, a cache keyed by source hash and a replayed endpoint
    # response all satisfy every completeness criteria while no reader met the material.
    reused=str(rp.get('reused_from') or '').strip()
    if reused: errors.append('reading_pass:READING_REUSED_FROM_PRIOR_ARTIFACT:'+reused)
    declared_run=str(rp.get('executed_for_run') or '').strip()
    declared_sha=str(rp.get('read_from_sha256') or '').strip().lower()
    source_sha=str((data.get('source') or {}).get('sha256') or '').strip().lower()
    if declared_sha and source_sha and declared_sha!=source_sha:
        errors.append('reading_pass:READ_FROM_A_DIFFERENT_SOURCE:declared='+declared_sha[:12]+':source='+source_sha[:12])
    if expected_run:
        if declared_run!=expected_run:
            errors.append('reading_pass:NOT_READ_FOR_THIS_RUN:expected='+str(expected_run)
                          +':declared='+(declared_run or '(none declared)'))
    else:
        unassessed.append('reading_pass:FRESHNESS_NOT_VERIFIED — no --run-id supplied, so this gate '
                          'cannot exercise the REG-READ-018 failure mode. The reading may still have '
                          'been performed for this run; this gate did not establish that it was.')
    # --- blocks
    blocks=data.get('blocks',[]); nodes={n.get('node_id'):n for n in data.get('structure',{}).get('nodes',[])}
    known=set(nodes); high_signal_evidence_only=0; hard_without_page=[]; assumed=[]
    allocated=set()
    for page in (data.get('page_plan') or []):
        allocated.update(page.get('source_block_ids') or [])
    for b in blocks:
        bid=b.get('block_id'); where='block '+str(bid)
        if b.get('role') not in allowed: errors.append(where+':ROLE_NOT_IN_CORE_OR_DECLARED_EXTENSIONS:'+str(b.get('role')))
        if b.get('coverage') not in ('in_deck','evidence_only'): errors.append(where+':INVALID_COVERAGE')
        sids=b.get('structure_node_ids',[])
        for sid in sids:
            if sid not in known: errors.append(where+':UNKNOWN_STRUCTURE_NODE:'+str(sid))
        if not sids and not str(b.get('orphan_reason','')).strip(): errors.append(where+':NO_ATTRIBUTION')
        if b.get('coverage')=='evidence_only' and not str(b.get('evidence_only_reason','')).strip():
            errors.append(where+':EVIDENCE_ONLY_WITHOUT_REASON')
        if b.get('relation_status')=='EXPLICIT' and not str(b.get('relation_evidence','')).strip():
            errors.append(where+':EXPLICIT_RELATION_WITHOUT_EVIDENCE')
        for flag in (b.get('difficulty') or []):
            if flag not in DIFFICULTY_FLAGS: errors.append(where+':UNKNOWN_DIFFICULTY_FLAG:'+str(flag))
        sig=b.get('signals',{})
        if (sig.get('emphasis_terms',0)>=3 or sig.get('facts',0)>=4) and b.get('coverage')=='evidence_only':
            high_signal_evidence_only+=1
        diffs=set(b.get('difficulty') or [])
        if 'undefined_term' in diffs: assumed.append(bid)
        if len(diffs)>=2 and b.get('coverage')=='in_deck' and bid not in allocated:
            hard_without_page.append(bid)
    decl=data.get('coverage_declaration')
    if high_signal_evidence_only and not decl:
        errors.append('emphasis:HIGH_SIGNAL_EVIDENCE_ONLY_WITHOUT_DECLARATION:'+str(high_signal_evidence_only))
    if hard_without_page and not decl:
        errors.append('difficulty:HIGH_DIFFICULTY_ALLOCATED_NOWHERE:'+','.join(str(x) for x in hard_without_page[:6]))
    if assumed:
        unassessed.append('difficulty:UNDEFINED_TERMS_UNRESOLVED_REQUIRES_REVIEWER:'+','.join(str(x) for x in assumed[:6]))
    # --- structure nodes
    bad=('because the source has','source heading','材料有这一节','目录顺序','the material lists')
    for n in nodes.values():
        nid=str(n.get('node_id')); why=str(n.get('why_here','')).strip().lower()
        if any(t in why for t in bad): errors.append('node:'+nid+':WHY_HERE_NOT_ADMISSIBLE')
        if not n.get('source_block_ids'): errors.append('node:'+nid+':NO_SOURCE_BLOCKS')
        basis=n.get('emphasis_basis')
        if basis in ('EXTERNAL_AUTHORITY','BOTH'):
            if not str(n.get('emphasis_authority','')).strip():
                errors.append('node:'+nid+':EXTERNAL_AUTHORITY_WITHOUT_NAMED_AUTHORITY')
            if not decl:
                errors.append('node:'+nid+':EXTERNAL_AUTHORITY_EMPHASIS_WITHOUT_DECLARATION')
        if basis=='NONE' and not str(n.get('difficulty_basis','')).strip():
            errors.append('node:'+nid+':IMPORTANCE_WITH_NO_BASIS')
    # --- narrative (REG-READ-014)
    nar=data.get('narrative')
    if not nar:
        errors.append('narrative:NOT_DECLARED')
    else:
        if nar.get('differs_from_source_order') is False:
            if len(str(nar.get('difference_reason','')).strip())<12:
                errors.append('narrative:SOURCE_ORDER_WITHOUT_JUSTIFICATION')
        order=nar.get('narrative_order') or []
        for nid in order:
            if nid not in known: errors.append('narrative:UNKNOWN_NODE:'+str(nid))
        if not order: errors.append('narrative:EMPTY_ORDER')
    # --- page allocation (REG-READ-015)
    plan=data.get('page_plan') or []
    if not plan: errors.append('page_plan:NOT_DECLARED')
    for page in plan:
        pid=str(page.get('page_id'))
        if not page.get('source_block_ids') and len(str(page.get('synthesised_reason','')).strip())<12:
            errors.append('page:'+pid+':NO_SOURCE_BLOCKS_AND_NOT_DECLARED_AS_SYNTHESIS')
        if len(str(page.get('why_this_page','')).strip())<12: errors.append('page:'+pid+':NO_REASON')
        is_content=bool(page.get('source_block_ids'))
        if is_content:
            if len(str(page.get('action_title','')).strip())<6:
                errors.append('page:'+pid+':CONTENT_PAGE_WITHOUT_ACTION_TITLE')
        else:
            if len(str(page.get('section_label','')).strip())<2 and \
               len(str(page.get('action_title','')).strip())<6:
                errors.append('page:'+pid+':STRUCTURE_PAGE_WITHOUT_LABEL')
        if page.get('figure_intent') not in FIGURE_INTENTS: errors.append('page:'+pid+':INVALID_FIGURE_INTENT')
        if page.get('difficulty_served') and page.get('figure_intent')=='NONE':
            errors.append('page:'+pid+':CLAIMS_TO_SERVE_DIFFICULTY_ON_INTENT_NONE')
        if len(str(page.get('why_this_page','')).strip())>=12 and not str(page.get('speaker_notes','')).strip():
            errors.append('page:'+pid+':NO_SPEAKER_NOTES_FOR_WORKING_LAYER')
        if page.get('figure_intent')=='NONE':
            fb=[b for b in blocks if b.get('block_id') in (page.get('source_block_ids') or [])]
            if any(len(b.get('difficulty') or [])>=2 for b in fb):
                errors.append('page:'+pid+':HARD_BLOCK_ON_INTENT_NONE_PAGE')
    # --- surface layer (REG-READ-016): presentation text only
    sf_status=((data.get('checks') or {}).get('surface') or {}).get('status')
    for page in plan:
        pid=str(page.get('page_id'))
        surface=list(page.get('on_slide_text') or [])
        if not surface:
            surface=[str(page.get('action_title',''))]
        for text in surface:
            for pattern,mark in WORKING_LAYER_MARKS:
                if re.search(pattern, str(text)):
                    (unassessed if sf_status=='NOT_CHECKED' else errors).append(
                        'page:'+pid+':WORKING_LAYER_ON_SLIDE:'+mark)
    # --- structure rendered (REG-READ-017)
    # 若该判据自身声明 NOT_CHECKED（例如尚未生成幻灯片），只记为未评估，不报失败。
    sr_status=((data.get('checks') or {}).get('structure_rendered') or {}).get('status')
    renders={}
    for page in plan:
        kind=page.get('renders_structure') or 'NONE'
        renders.setdefault(kind, []).append(str(page.get('page_id')))
    find=unassessed.append if sr_status=='NOT_CHECKED' else errors.append
    if not renders.get('ROADMAP'):
        find('structure_rendered:NO_ROADMAP_PAGE')
    if not renders.get('SECTION_QUESTION'):
        find('structure_rendered:NO_SECTION_QUESTION_PAGE')
    if not renders.get('CONSOLIDATION'):
        find('structure_rendered:NO_CONSOLIDATION_PAGE')
    order=(data.get('narrative') or {}).get('narrative_order') or []
    exposed=set()
    for page in plan:
        exposed.update(page.get('narrative_node_ids') or [])
        for bid in (page.get('source_block_ids') or []):
            for nid, node in nodes.items():
                if bid in (node.get('source_block_ids') or []):
                    exposed.add(nid)
    missing=[n for n in order if n not in exposed]
    if missing:
        find('structure_rendered:NARRATIVE_NODES_NOT_RENDERED:'+','.join(missing[:6]))
    # page order must follow narrative order (monotone over first appearance)
    seen=[]; 
    for page in plan:
        for nid in (page.get('narrative_node_ids') or []):
            if nid in order and nid not in seen: seen.append(nid)
    seq=[n for n in order if n in seen]
    if seen!=seq:
        find('structure_rendered:PAGE_ORDER_CONTRADICTS_NARRATIVE_ORDER')
    # --- checks integrity
    for name,c in (data.get('checks') or {}).items():
        if c.get('status')=='PASS' and len(str(c.get('method','')).strip())<10:
            errors.append('check:'+name+':PASS_WITHOUT_METHOD')
        if c.get('status')=='FAIL' and not c.get('failures'):
            errors.append('check:'+name+':FAIL_WITHOUT_FAILURES')
        if c.get('status')=='NOT_CHECKED':
            unassessed.append('check:'+name+':NOT_CHECKED')
    return errors, unassessed

def validate_chatgpt_image_asset(data, root):
    errors=[]
    try:
        asset=safe_path(root,data.get('path',''))
        payload=asset.read_bytes()
        if payload[:8]!=b'\x89PNG\r\n\x1a\n' or len(payload)<24 or payload[12:16]!=b'IHDR':
            errors.append('asset:INVALID_PNG_SIGNATURE')
        if digest(asset).lower()!=str(data.get('sha256','')).lower():
            errors.append('asset:HASH_MISMATCH')
    except (OSError,ValueError):
        errors.append('asset:MISSING_OR_INVALID_PATH')
    checks=data.get('content_review',{}).get('checked',{})
    for key in ('no_text','no_numbers','no_medical_claim','no_relationship_encoding','no_watermark','safe_regions_clear'):
        if checks.get(key) is not True: errors.append('content_review:'+key+':NOT_PASS')
    fusion=data.get('fusion_theme',{})
    if fusion.get('reuse_mode')!='MASTER_UNDERLAY': errors.append('fusion_theme:INVALID_REUSE_MODE')
    if fusion.get('content_zone')!={'left':64,'top':36,'width':960,'height':620}: errors.append('fusion_theme:INVALID_CONTENT_ZONE')
    if fusion.get('protected_decoration_zone')!={'left':1050,'top':0,'width':230,'height':720}: errors.append('fusion_theme:INVALID_DECORATION_ZONE')
    return errors

def verify_package(root):
    lock=read(root/'PACKAGE_LOCK.json'); errors=[]
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='PACKAGE_LOCK.json'}
    for extra in sorted(actual-set(lock['files'])): errors.append(extra+':UNLOCKED_FILE')
    for ref, expected in lock['files'].items():
        try:
            if digest(safe_path(root,ref))!=expected: errors.append(ref+':HASH_MISMATCH')
        except (OSError,ValueError): errors.append(ref+':MISSING_OR_INVALID')
    return errors

def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='command',required=True)
    for kind in ('state','qualification','quality-evaluation'):
        p=sub.add_parser(kind); p.add_argument('input',type=Path); p.add_argument('--root',type=Path,default=Path.cwd())
    gate_schemas={
        'source-intake':'source_intake_record.v0.1.schema.json',
        'fact-oracle':'fact_oracle_review.v0.1.schema.json',
        'source-chain':'source_version_chain.v0.1.schema.json',
        'case-boundary':'case_boundary_review.v0.1.schema.json',
        'document-structure':'document_structure_audit.v0.1.schema.json',
        'privacy-gate':'privacy_surface_audit.v0.1.schema.json',
        'beautification-plan':'native_beautification_plan.v0.1.schema.json',
        'chatgpt-image-asset':'chatgpt_image_editorial_asset.v0.1.schema.json',
        'reading-structure':'reading_structure_artifact.v0.2.schema.json',
    }
    for kind in gate_schemas:
        p=sub.add_parser(kind); p.add_argument('input',type=Path); p.add_argument('--root',type=Path,default=Path.cwd())
        if kind=='beautification-plan': p.add_argument('--deck',type=Path,required=True)
        if kind=='reading-structure':
            p.add_argument('--run-id',dest='run_id',default=None,
                           help='the run this reading must have been performed for (REG-READ-018). '
                                'Omitted, the freshness check reports NOT_CHECKED rather than PASS.')
    p=sub.add_parser('preflight'); p.add_argument('--font',type=Path)
    p=sub.add_parser('package'); p.add_argument('out',type=Path)
    p=sub.add_parser('verify-package'); p.add_argument('root',type=Path)
    a=parser.parse_args()
    if a.command in ('state','qualification','quality-evaluation'):
        data=read(a.input)
        import jsonschema
        name={'state':'run_state.schema.json','qualification':'runtime_qualification_result.v0.2.schema.json','quality-evaluation':'quality_evaluation.schema.json'}[a.command]
        errors=[e.message for e in jsonschema.Draft202012Validator(read(SKILL/'schemas'/name)).iter_errors(data)]
        errors += validate_state(data) if a.command=='state' else validate_qualification(data,a.root) if a.command=='qualification' else validate_quality_evaluation(data,a.root)
        print(__import__('json').dumps({'status':'FAIL' if errors else 'PASS','errors':errors},ensure_ascii=False,indent=2))
        return bool(errors)
    if a.command in gate_schemas:
        data=read(a.input)
        import jsonschema
        errors=[e.message for e in jsonschema.Draft202012Validator(read(SKILL/'schemas'/gate_schemas[a.command])).iter_errors(data)]
        unassessed=[]
        if a.command=='beautification-plan':
            errors += validate_beautification_plan(data,read(a.deck))
        elif a.command=='chatgpt-image-asset':
            errors += validate_chatgpt_image_asset(data,a.root)
        elif a.command=='reading-structure':
            det,unassessed=validate_reading_structure(data,getattr(a,'run_id',None))
            errors += det
        else:
            validator=VALIDATORS[a.command]
            errors += validator(data,a.root) if a.command=='source-intake' else validator(data)
        result={
            'status':'FAIL' if errors else 'PASS',
            'gate':a.command,
            'delivery_eligible':not errors,
            'errors':sorted(set(errors)),
        }
        if a.command=='reading-structure':
            result['gate_scope']=('Deterministic subset only. Thread quality, why_here usefulness and '
                                  'difficulty reasons require human or model review and were not assessed here.')
            result['not_assessed_by_this_gate']=unassessed or ['(none flagged)']
        print(__import__('json').dumps(result,ensure_ascii=False,indent=2))
        return bool(errors)
    if a.command=='preflight':
        modules={m:importlib.util.find_spec(m) is not None for m in ('jsonschema','PIL','fontTools')}
        result={'python':platform.python_version(),'platform':platform.platform(),'dependencies':modules,
                'semantic_validation_ready':modules['jsonschema'],
                'protected_assembly_ready':modules['PIL'],
                'exact_overlay_ready':all(modules.values()) and bool(a.font and a.font.is_file()),
                'qualified_capabilities':[],
                'qualification_required':'Readiness never carries qualifications from another runtime.',
                'statistical_chart_geometry':'SIMPLE_SVG_CHECKER_AVAILABLE_REQUIRES_LOCAL_QUALIFICATION'}
        print(__import__('json').dumps(result,indent=2)); return 0
    if a.command=='verify-package':
        errors=verify_package(a.root)
        print(__import__('json').dumps({'status':'FAIL' if errors else 'PASS','errors':errors},indent=2)); return bool(errors)
    if a.command=='package':
        if a.out.exists(): raise FileExistsError(a.out)
        a.out.parent.mkdir(parents=True,exist_ok=True)
        files=[p for p in SKILL.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='PACKAGE_LOCK.json' and p.suffix not in ('.pyc',)]
        lock={'skill_version':read(SKILL/'SKILL_MANIFEST.json')['skill_version'],'files':{p.relative_to(SKILL).as_posix():digest(p) for p in sorted(files)}}
        write(SKILL/'PACKAGE_LOCK.json',lock)
        with zipfile.ZipFile(a.out,'w',zipfile.ZIP_DEFLATED) as z:
            for p in files: z.write(p,p.relative_to(SKILL))
            z.writestr('PACKAGE_LOCK.json',__import__('json').dumps(lock,indent=2))
        print(__import__('json').dumps({'package':str(a.out),'sha256':digest(a.out),'files':len(files)},indent=2)); return 0

if __name__=='__main__': sys.exit(main())
