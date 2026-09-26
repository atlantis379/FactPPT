"""Offline deterministic checks. No clinical entailment or pixel certification."""
from __future__ import annotations
import hashlib
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

PASS = {'PASS', 'PASS_WITH_WARNINGS'}
QUALIFIED = {'QUALIFIED', 'REFERENCE_QUALIFIED', 'QUALIFIED_WITH_RESTRICTIONS'}
REQUIRED_SUBGATES = {'W02-FSC', 'W06-NR', 'W06-NP', 'W12-A', 'W12-RQ', 'W12-B'}

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')

def diff(expected, actual, location='$'):
    """Order-sensitive JSON equality; no Unicode, numeric, or scope normalization."""
    if type(expected) is not type(actual):
        return [{'path': location, 'expected': expected, 'actual': actual}]
    if isinstance(expected, dict):
        out = []
        for key in sorted(expected.keys() | actual.keys()):
            if key not in expected or key not in actual:
                out.append({'path': f'{location}.{key}', 'expected': expected.get(key), 'actual': actual.get(key), 'missing_key': True})
            else:
                out.extend(diff(expected[key], actual[key], f'{location}.{key}'))
        return out
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return [{'path': location, 'expected': expected, 'actual': actual}]
        return [item for i, (a, b) in enumerate(zip(expected, actual)) for item in diff(a, b, f'{location}[{i}]')]
    return [] if expected == actual else [{'path': location, 'expected': expected, 'actual': actual}]

def numeric_diff(expected, actual):
    """Decimal equality plus exact operator, units, provenance and context."""
    required = {'fact_id', 'value', 'operator', 'unit', 'context', 'value_origin'}
    if not required <= expected.keys() or not required <= actual.keys():
        return [{'path': '$', 'error': 'NUMERIC_FIELDS_MISSING'}]
    e, a = dict(expected), dict(actual)
    try:
        for value in (e, a):
            # Values must be decimal strings; floats cannot represent exact source decimals.
            if not isinstance(value['value'], str):
                raise ValueError('decimal string required')
            d = Decimal(value['value'])
            if not d.is_finite():
                raise ValueError('finite value required')
            value['value'] = str(d.normalize())
    except (InvalidOperation, ValueError):
        return [{'path': '$.value', 'error': 'INVALID_EXACT_DECIMAL'}]
    return diff(e, a)

def validate_state(data):
    errors = []
    if data.get('schema_version') != '0.5.0' or data.get('skill_version') != 'v0.5.0':
        errors.append('VERSION_MISMATCH')
    stages = data.get('stages', {})
    if set(stages) != {f'W{i:02}' for i in range(19)}:
        errors.append('STAGE_SET_MISMATCH')
    sub = data.get('subgates', {})
    if not REQUIRED_SUBGATES <= sub.keys():
        errors.append('SUBGATES_MISSING')
    if data.get('mode')=='DELIVERY':
        for i in range(1,18):
            if stages.get(f'W{i:02}') in PASS and any(stages.get(f'W{j:02}') not in PASS for j in range(i)):
                errors.append(f'W{i:02}:UNPASSED_UPSTREAM_STAGE')
        for stage,required in [('W05',['W02-FSC']),('W07',['W06-NR','W06-NP']),('W13',['W12-A','W12-RQ','W12-B'])]:
            if stages.get(stage) in PASS and any(sub.get(g) not in PASS for g in required): errors.append(stage+':UNPASSED_SUBGATE')
    if data.get('mode') == 'DESIGN_PROTOTYPE':
        if data.get('delivery_eligible') is not False: errors.append('PROTOTYPE_REQUIRES_NOT_FOR_DELIVERY')
        if stages.get('W14') in PASS or stages.get('W17') in PASS: errors.append('PROTOTYPE_AUTHORITATIVE_STAGE')
    if data.get('final_disposition') == 'APPROVED_REFERENCE_OUTPUT':
        if data.get('mode') != 'DELIVERY': errors.append('PROTOTYPE_CANNOT_DELIVER')
        if any(x not in PASS for x in stages.values()) or any(sub.get(x) not in PASS for x in REQUIRED_SUBGATES):
            errors.append('UNPASSED_GATE')
        if data.get('blocking_issues') or data.get('stale_object_ids'):
            errors.append('UNRESOLVED_OR_STALE')
        qa = data.get('quality', {})
        if any(qa.get(x) not in PASS for x in ('source_semantic', 'numeric_logic', 'composition', 'rendered_review')):
            errors.append('QUALITY_INCOMPLETE')
        if data.get('risk') == 'RED':
            review = data.get('human_review', {})
            if review.get('status') != 'APPROVED' or not review.get('reviewer') or not review.get('artifact_sha256'):
                errors.append('RED_REVIEW_MISSING')
            if review.get('artifact_sha256') != data.get('artifact_sha256'):
                errors.append('REVIEW_ARTIFACT_MISMATCH')
    return errors

def safe_path(root, ref):
    root = Path(root).resolve()
    p = (root / ref).resolve()
    if Path(ref).is_absolute() or not p.is_relative_to(root):
        raise ValueError('reference must be bundle relative')
    return p

def validate_qualification(data, root):
    """Validate evidence closure, not the truth of a medical reviewer assertion."""
    errors = []
    try:
        runtime_path=safe_path(root,data['runtime_ref'])
        if digest(runtime_path)!=data['runtime_sha256']: errors.append('RUNTIME_HASH_MISMATCH')
    except (KeyError,OSError,ValueError): errors.append('RUNTIME_EVIDENCE_MISSING')
    results = data.get('results', [])
    ids = [x.get('fixture_id') for x in results]
    if len(ids) != len(set(ids)): errors.append('DUPLICATE_FIXTURE')
    executed = data.get('executed_fixture_ids', [])
    if len(executed) != len(set(executed)): errors.append('DUPLICATE_EXECUTED_FIXTURE')
    if set(executed) != {x.get('fixture_id') for x in results if x.get('status') != 'NOT_EXECUTED'}:
        errors.append('EXECUTED_RESULT_MISMATCH')
    byid = {x.get('fixture_id'): x for x in results}
    for row in results:
        if row.get('status') not in PASS: continue
        for kind in ('input', 'output'):
            try:
                if digest(safe_path(root, row[f'{kind}_ref'])) != row[f'{kind}_sha256']:
                    errors.append(f"{row['fixture_id']}:{kind}:HASH_MISMATCH")
                if kind=='output' and read(safe_path(root,row['output_ref'])).get('status')!='PASS':
                    errors.append(f"{row['fixture_id']}:OUTPUT_RESULT_NOT_PASS")
            except (KeyError, ValueError, OSError):
                errors.append(f"{row.get('fixture_id')}:{kind}:EVIDENCE_MISSING")
        if not row.get('verifier_results') or not row.get('executor', {}).get('implementation_sha256'):
            errors.append(f"{row.get('fixture_id')}:EXECUTION_EVIDENCE_MISSING")
        if any(v.get('status') != 'PASS' for v in row.get('verifier_results', [])):
            errors.append(f"{row.get('fixture_id')}:VERIFIER_FAILED")
    for cap in data.get('capability_records', []):
        if cap.get('qualification_status') not in QUALIFIED: continue
        refs = cap.get('evidence_fixture_ids', [])
        if not refs or len(refs) != len(set(refs)):
            errors.append('EMPTY_OR_DUPLICATE_CAPABILITY_EVIDENCE')
        linked = [byid.get(x, {}) for x in refs]
        if any(x.get('status') != 'PASS' for x in linked): errors.append('UNPASSED_CAPABILITY_FIXTURE')
        if not any(x.get('polarity') == 'positive' for x in linked) or not any(x.get('polarity') == 'negative' for x in linked):
            errors.append('POSITIVE_AND_NEGATIVE_REQUIRED')
        for x in linked:
            executor = x.get('executor', {})
            if any(executor.get(k) != cap.get(k) for k in ('engine_id', 'engine_version', 'implementation_sha256')):
                errors.append('CAPABILITY_EXECUTOR_MISMATCH')
        if not cap.get('limitations') or not cap.get('scope') or not cap.get('invalidation_triggers'):
            errors.append('CAPABILITY_BOUNDARY_MISSING')
    if data.get('overall_status') in PASS:
        if not results or not data.get('capability_records'): errors.append('EMPTY_PASS')
        if any(x.get('status') != 'PASS' for x in results): errors.append('OVERALL_PASS_WITH_FAILED_FIXTURE')
    return sorted(set(errors))

def validate_factoring(original, scene):
    """Only lossless AND factoring. Every source identity is retained per bundle."""
    errors = []
    if original.get('logic') != 'AND' or scene.get('logic') != 'AND': return ['ONLY_AND_SUPPORTED']
    bundles = original.get('bundles', [])
    outputs = scene.get('bundles', [])
    if not bundles or not outputs: return ['EMPTY_BUNDLES']
    for b in bundles:
        if not b.get('bundle_id') or not b.get('facts'): return ['EMPTY_OR_UNIDENTIFIED_BUNDLE']
        if any(not f.get('fact_id') or not (set(f)-{'fact_id'}) for f in b['facts']): return ['FACT_ID_OR_SEMANTICS_MISSING']
    if Counter(b.get('bundle_id') for b in bundles) != Counter(b.get('bundle_id') for b in outputs):
        return ['BUNDLE_ID_MISMATCH']
    if len({b['bundle_id'] for b in bundles}) != len(bundles): return ['DUPLICATE_BUNDLE_ID']
    shared = scene.get('shared', [])
    shared_ids = [x.get('slot_id') for x in shared]
    if len(shared_ids) != len(set(shared_ids)): errors.append('DUPLICATE_SHARED_SLOT')
    for source, rendered in zip(bundles, outputs):
        # Deliberately keep bundle order and ownership, not just a set of strings.
        if source.get('bundle_id') != rendered.get('bundle_id'): errors.append('BUNDLE_ORDER_MISMATCH')
        source_facts = source.get('facts', [])
        if len({f.get('fact_id') for f in source_facts}) != len(source_facts): errors.append('DUPLICATE_SOURCE_FACT')
        reconstructed = list(rendered.get('specific', []))
        for slot in shared:
            bindings = slot.get('bindings', {})
            fact_id = bindings.get(source.get('bundle_id'))
            reconstructed.append({'fact_id': fact_id, **slot.get('semantic', {})})
        if len({f.get('fact_id') for f in reconstructed}) != len(reconstructed): errors.append('DUPLICATE_RENDERED_FACT')
        if Counter(canonical(x) for x in source_facts) != Counter(canonical(x) for x in reconstructed):
            errors.append(f"{source.get('bundle_id')}:FACT_CONTENT_OR_SCOPE_MISMATCH")
    return sorted(set(errors))

def factor_and(original):
    if original.get('logic') != 'AND': raise ValueError('ONLY_AND_SUPPORTED')
    bundles = original['bundles']
    if not bundles: raise ValueError('EMPTY_BUNDLES')
    semantics = lambda f: {k: v for k, v in f.items() if k != 'fact_id'}
    common = []
    for f in bundles[0]['facts']:
        s = semantics(f)
        matches = [[x for x in b['facts'] if semantics(x) == s] for b in bundles]
        if all(len(x) == 1 for x in matches):
            common.append({'slot_id': f'shared-{len(common)+1}', 'semantic': s,
                           'bindings': {b['bundle_id']: m[0]['fact_id'] for b, m in zip(bundles, matches)}})
    scene = {'logic': 'AND', 'shared': common, 'bundles': []}
    for b in bundles:
        ids = {s['bindings'][b['bundle_id']] for s in common}
        scene['bundles'].append({'bundle_id': b['bundle_id'], 'specific': [f for f in b['facts'] if f['fact_id'] not in ids]})
    failures = validate_factoring(original, scene)
    if failures: raise ValueError(failures)
    return scene

def validate_quality_evaluation(data, root):
    errors=[]
    if data.get('mode')=='DESIGN_PROTOTYPE' and data.get('delivery_eligible') is not False:
        errors.append('PROTOTYPE_CANNOT_DELIVER')
    for dimension,result in data.get('dimensions',{}).items():
        if result.get('status')=='NOT_APPLICABLE' and not result.get('reason'):
            errors.append(dimension+':APPLICABILITY_REASON_REQUIRED')
        if result.get('status') in ('PASS','FAIL') and not result.get('evidence'):
            errors.append(dimension+':EVIDENCE_REQUIRED')
        for item in result.get('evidence',[]):
            try:
                if digest(safe_path(root,item['ref']))!=item['sha256']: errors.append(dimension+':EVIDENCE_HASH_MISMATCH')
            except (KeyError,ValueError,OSError): errors.append(dimension+':EVIDENCE_MISSING')
    if data.get('delivery_eligible'):
        # This record never grants delivery by itself; formal run-state/human gate remains required.
        if not data.get('dimensions') or any(v.get('status') not in ('PASS','NOT_APPLICABLE') for v in data['dimensions'].values()):
            errors.append('QUALITY_NOT_READY_FOR_DELIVERY')
    return errors
