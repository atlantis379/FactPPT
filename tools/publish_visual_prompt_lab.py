"""Publish lightweight progress and real assets using the existing Tabler shell."""
from __future__ import annotations
import json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.visual_prompt_lab import LAB,read,status,file_sha,write
from factdeck.visual_lab import STRATEGIES

def current_native_review(native, review):
    """A previous render's visual review cannot approve replacement images."""
    if not review.get('ready_for_human_style_review') or review.get('defects'):
        return False
    slides=review.get('slides',[])
    if len(slides)!=6 or {s.get('slide_number') for s in slides}!=set(range(1,7)):
        return False
    if review.get('source_common_input_sha256')!=file_sha(LAB/'common_input.json'):
        return False
    return all(s.get('viewed_native') is True and
               s.get('native_image_sha256')==file_sha(native/f"slide{s['slide_number']:02d}.png")
               for s in slides)

def current_style_confirmation():
    path=LAB/'textbook_style_confirmation.json'
    if not path.is_file():return None
    confirmation=read(path)
    if confirmation.get('actor')!='human_user' or confirmation.get('approved_style') is not True or not confirmation.get('binds'):return None
    for relative,expected in confirmation['binds'].items():
        asset=(LAB/relative).resolve()
        if not asset.is_relative_to(LAB.resolve()) or not asset.is_file() or file_sha(asset)!=expected:return None
    return confirmation

def publish():
    target=ROOT/'web/deck/reviews/visual_prompt_lab';target.mkdir(parents=True,exist_ok=True)
    common=read(LAB/'common_input.json');state=status();output=[]
    for row in state['trials']:
        trial={k:row[k] for k in ('id','phase','page','strategy','repeat','status')}
        trial['name']=STRATEGIES[row['strategy']]['name'];trial['preview']=None
        calls=[c for c in state['calls'] if c['trial_id']==row['id']]
        trial['calls']=len([c for c in calls if c['status'] in ('RETURNED_INSPECTED','FAILED_TRANSPORT')])
        if row['result_path']:
            asset=ROOT/row['result_path'];dest=target/'assets'/asset.name;dest.parent.mkdir(exist_ok=True)
            shutil.copy2(asset,dest);trial['preview']='assets/'+asset.name;trial['asset_sha256']=file_sha(asset)
            accepted=next((c for c in reversed(calls) if c['status']=='RETURNED_INSPECTED'),None)
            if accepted:
                receipt=read(ROOT/accepted['receipt_path']);trial['inspection']=receipt['inspection'];trial['issues']=receipt.get('quality_issues',[])
                trial['outer_wait_seconds']=receipt.get('outer_wait_seconds');trial['provider_elapsed_seconds']=receipt.get('provider_elapsed_seconds')
        if row['prompt_path']:
            p=ROOT/row['prompt_path'];shutil.copy2(p,target/(row['id']+'.prompt.txt'));trial['prompt_url']=row['id']+'.prompt.txt'
        output.append(trial)
    review=read(LAB/'screen_review.json') if (LAB/'screen_review.json').exists() else None
    reviews={phase:read(LAB/f'{phase}_review.json') for phase in ('screen','quality','stability') if (LAB/f'{phase}_review.json').exists()}
    for trial in output:
        checked=next((t for t in reviews.get(trial['phase'],{}).get('trials',[]) if t.get('id',t.get('trial_id'))==trial['id']),None)
        if checked and checked.get('asset_sha256',checked.get('image_sha256'))==trial.get('asset_sha256'):
            trial['independent_hard_errors']=checked.get('hard_error_ids',[])
    current_phase=next((phase for phase in ('extension','stability','quality','screen') if any(t['phase']==phase for t in output)),'screen')
    manifest={'source_sha256':file_sha(LAB/'common_input.json'),'phase':current_phase,'trials':output,'review':review,'reviews':reviews,
              'actual_calls':sum(t['calls'] for t in output),'approved':False,'native_preview':None,
              'clean_images':sum(1 for p in (LAB/'native_assets').glob('*/clean_receipt.json') if read(p).get('inspected') is True and (p.parent/'clean.png').is_file() and read(p).get('clean_asset_sha256')==file_sha(p.parent/'clean.png')),
              'vector_assets':len(list((LAB/'native_assets').glob('*/artwork.svg')))}
    native=LAB/'native'
    selection=read(LAB/'textbook_selection.json') if (LAB/'textbook_selection.json').is_file() else None
    manifest['selection']=selection
    manifest['style_confirmation']=current_style_confirmation() if selection else None
    if selection:
        from tools.visual_lab_textbook_package import SELECTED as textbook_selected
        folders=[LAB/'native_assets'/tid for tid in textbook_selected.values()]
        manifest['clean_images']=sum((p/'clean_receipt.json').is_file() and read(p/'clean_receipt.json').get('inspected') is True for p in folders)
        manifest['vector_assets']=sum((p/'artwork.svg').is_file() for p in folders)
        if (LAB/'native_textbook/render_report.json').is_file():native=LAB/'native_textbook'
    if (native/'render_report.json').is_file():
        from tools.visual_lab_package import SELECTED
        if native.name=='native_textbook':SELECTED=textbook_selected
        prefix=native.name
        dest=target/prefix;dest.mkdir(exist_ok=True)
        for p in native.glob('*.png'):shutil.copy2(p,dest/p.name)
        for name in ('deck.pptx','deck.pdf','render_report.json','final_visual_review.json'):
            if (native/name).is_file():shutil.copy2(native/name,dest/name)
        for name in ('experiment_report.md','experiment_report.json'):
            if (LAB/name).is_file():shutil.copy2(LAB/name,target/name)
        visual=read(native/'final_visual_review.json') if (native/'final_visual_review.json').is_file() else {}
        native_designs={}
        native_manifest=LAB/'native_textbook_manifest.json'
        if prefix=='native_textbook' and native_manifest.is_file():
            inputs=read(native_manifest)['trials']
            for i,tid in enumerate(SELECTED.values(),1):
                asset=Path(inputs[tid]['design_png_path'])
                filename=f'input-slide{i:02d}.png'
                shutil.copy2(asset,dest/filename)
                native_designs[tid]=f'{prefix}/{filename}?v='+file_sha(asset)[:12]
        manifest['native_preview']={'ready_for_human_style_review':current_native_review(native,visual) if prefix=='native_textbook' else visual.get('ready_for_human_style_review',False),
            'style_confirmed':bool(manifest['style_confirmation']) if prefix=='native_textbook' else False,
            'label':'教材式原生样稿' if prefix=='native_textbook' else '期刊式原生样稿（上一版）' if selection else '六页原生PPT实际画面',
            'pptx':prefix+'/deck.pptx?v='+file_sha(native/'deck.pptx')[:12],'pdf':prefix+'/deck.pdf?v='+file_sha(native/'deck.pdf')[:12],'report':'textbook_report.md' if prefix=='native_textbook' else 'experiment_report.md',
            'verification':read(native/'render_report.json')['summary'],
            'pages':[{'page':n,'design':native_designs.get(tid,next(t['preview'] for t in output if t['id']==tid)),'browser':f'{prefix}/browser-slide{i:02d}.png?v='+file_sha(native/f'browser-slide{i:02d}.png')[:12],'powerpoint':f'{prefix}/slide{i:02d}.png?v='+file_sha(native/f'slide{i:02d}.png')[:12]} for i,(n,tid) in enumerate(SELECTED.items(),1)]}
        if (LAB/'textbook_report.md').is_file():shutil.copy2(LAB/'textbook_report.md',target/'textbook_report.md')
    write(target/'manifest.json',manifest)
    shutil.copy2(ROOT/'web/deck/visual_lab.html',target/'index.html')
    return {'images':sum(bool(t['preview']) for t in output),'actual_calls':manifest['actual_calls'],'url':'http://127.0.0.1:8001/web/deck/reviews/visual_prompt_lab/index.html'}
if __name__=='__main__':print(json.dumps(publish(),ensure_ascii=False))
