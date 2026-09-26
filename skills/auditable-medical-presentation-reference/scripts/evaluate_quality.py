"""Execute a general quality checker against explicit inputs, with hashed output."""
import argparse
from pathlib import Path
import jsonschema
from integrity import read,write,digest
from quality_checks import validate_chart_svg,validate_coverage,validate_narrative,validate_editorial_asset_contract,validate_editorial_fusion_plan,validate_client_template_contract,validate_visual_base_selection
from pptx_quality import inspect

S=Path(__file__).resolve().parents[1]

if __name__=='__main__':
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='kind',required=True)
    c=sub.add_parser('chart'); c.add_argument('--contract',type=Path,required=True); c.add_argument('--artifact',type=Path,required=True)
    c=sub.add_parser('coverage'); c.add_argument('--source',type=Path,required=True); c.add_argument('--reference',type=Path,required=True); c.add_argument('--candidate',type=Path,required=True)
    c=sub.add_parser('narrative'); c.add_argument('--reference',type=Path,required=True); c.add_argument('--candidate',type=Path,required=True)
    c=sub.add_parser('editorial-asset'); c.add_argument('--contract',type=Path,required=True); c.add_argument('--artifact',type=Path,required=True)
    c=sub.add_parser('client-template'); c.add_argument('--contract',type=Path,required=True); c.add_argument('--artifact',type=Path,required=True)
    c=sub.add_parser('editorial-fusion'); c.add_argument('--plan',type=Path,required=True); c.add_argument('--scene',type=Path,required=True)
    c=sub.add_parser('pptx'); c.add_argument('--contract',type=Path,required=True); c.add_argument('--artifact',type=Path,required=True); c.add_argument('--fonts',type=Path,required=True); c.add_argument('--slide',type=int,default=1); c.add_argument('--render-evidence',type=Path)
    for c in sub.choices.values(): c.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists(): raise FileExistsError('Preserve evidence; choose a new output file')
    result={}
    if a.kind=='chart': errors=validate_chart_svg(read(a.contract),a.artifact)
    elif a.kind=='coverage': errors=validate_coverage(read(a.source),read(a.reference),read(a.candidate))
    elif a.kind=='narrative': errors=validate_narrative(read(a.reference),read(a.candidate))
    elif a.kind=='editorial-asset':
        contract=read(a.contract)
        jsonschema.Draft202012Validator(read(S/'schemas/scene_quality_contract.schema.json')).validate({
            'contract_version':'asset-validation', 'basis':'asset-validation', 'canvas':[1,1], 'background_color':'FFFFFF',
            'minimum_contrast_ratio':4.5, 'minimum_font_px':1, 'constraint_rationale':'schema harness',
            'content_safe_regions':[], 'mandatory_texts':[], 'editorial_assets':[contract]})
        errors=validate_editorial_asset_contract(contract,a.artifact)
    elif a.kind=='editorial-fusion':
        plan,scene=read(a.plan),read(a.scene)
        jsonschema.Draft202012Validator(read(S/'schemas/editorial_fusion_plan.v0.1.schema.json')).validate(plan)
        jsonschema.Draft202012Validator(read(S/'schemas/scene_quality_contract.schema.json')).validate(scene)
        errors=validate_editorial_fusion_plan(plan,scene)
        result={'fusion_plan_id':plan['fusion_plan_id'],'source_sha256':plan['source_identity']['source_sha256'],'integration_mode':plan['integration_mode']}
    elif a.kind=='client-template':
        contract=read(a.contract)
        jsonschema.Draft202012Validator(read(S/'schemas/client_template_contract.v0.1.schema.json')).validate(contract)
        errors=validate_client_template_contract(contract,a.artifact)
    else:
        contract=read(a.contract)
        jsonschema.Draft202012Validator(read(S/'schemas/scene_quality_contract.schema.json')).validate(contract)
        result=inspect(a.artifact,read(a.fonts),contract,a.slide,a.render_evidence)
        errors=validate_visual_base_selection(contract)+(result['glyph_errors']+result['composition_errors']+result['render_errors'] if result['render_status']=='FAIL' else result['glyph_errors']+result['composition_errors'])
    needs_review=(a.kind=='pptx' and result.get('render_status')!='PASS') or (a.kind=='editorial-asset' and read(a.contract).get('content_review',{}).get('status')!='PASS') or (a.kind=='editorial-fusion' and (read(a.plan).get('render_review',{}).get('status')!='PASS' or read(a.plan).get('render_review',{}).get('reviewer_role')!='independent')) or (a.kind=='client-template' and (read(a.contract).get('review',{}).get('status')!='PASS' or read(a.contract).get('review',{}).get('reviewer_role')!='independent'))
    status='FAIL' if errors else ('NEEDS_REVIEW' if needs_review else 'PASS')
    result.update(status=status,errors=errors,input_hashes={k:digest(v) for k,v in vars(a).items() if isinstance(v,Path) and k!='out'},kind=a.kind)
    write(a.out,result); print(result['status']); raise SystemExit(result['status']!='PASS')
