"""Translate existing independent evidence into an isolated six-page manifest."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.visual_prompt_lab import LAB,read,write,file_sha,status
from factdeck.visual_lab import digest

SELECTED={1:'extension_editorial_01_r1',2:'stability_editorial_02_r2',5:'quality_editorial_05_r2',9:'stability_editorial_09_r2',20:'extension_editorial_20_r1',21:'extension_editorial_21_r1'}

def package():
    common=read(LAB/'common_input.json');source_sha=file_sha(LAB/'common_input.json')
    rows={r['id']:r for r in status()['trials']};trials={}
    for page,tid in SELECTED.items():
        row=rows[tid];asset=ROOT/row['result_path'];folder=LAB/'native_assets'/tid
        graph_path=LAB/('extension_graph.json' if row['phase']=='extension' else 'semantic_graph.json')
        report_path=LAB/('extension_review.json' if row['phase']=='extension' else 'quality_review.json' if row['phase']=='quality' else 'stability_review.json')
        report=read(report_path)
        if report.get('source_sha256')!=source_sha:raise ValueError('Independent image review source is stale')
        recorded_graph=report.get('graph_sha256',report.get('semantic_graph_sha256',report.get('graph_sha256_digest')))
        if recorded_graph not in (digest(read(graph_path)),file_sha(graph_path)):raise ValueError('Independent image review graph is stale')
        check=next(t for t in report['trials'] if t.get('id',t.get('trial_id'))==tid)
        if check.get('viewed') is not True or check.get('asset_sha256',check.get('image_sha256'))!=file_sha(asset):raise ValueError('Image review binding differs')
        if 'hard_error_ids' in check:errors=check['hard_error_ids']
        elif 'hard_failures' in check:errors=check['hard_failures']
        else:raise ValueError('Explicit hard-error disposition required')
        if errors:raise ValueError('Selected image still has blockers')
        worker=report.get('worker',report.get('reviewer'))
        if not worker or worker==row['worker']:raise ValueError('Independent reviewer identity required')
        write(folder/'native_semantic_binding.json',{'status':'CLEAR','reviewer':worker,'derived_from':str(report_path.relative_to(ROOT)),
            'review_file_sha256':file_sha(report_path),'reviewed_asset_sha256':file_sha(asset),'source_sha256':source_sha,
            'graph_sha256':digest(read(graph_path)),'medical_approval':False,'customer_approval':False,
            'scope':'Mechanical translation of existing viewed-image findings; no new review or clinical approval'})
        trials[tid]={'page_number':page,'svg_path':str(folder/'artwork.svg'),'components_path':str(folder/'components.json'),
            'layout_path':str(folder/'layout.json'),'design_png_path':str(asset),'semantic_review_path':str(folder/'native_semantic_binding.json')}
    target=LAB/'native_manifest.json';write(target,{'font':common['font'],'selected_trial_ids':list(SELECTED.values()),'trials':trials,'approved':False})
    return target

if __name__=='__main__':print(package())
