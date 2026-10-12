"""Build the user-selected textbook candidate from actual cleaned, reviewed art."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.visual_prompt_lab import LAB,read,write,status

SELECTED={1:'extension_textbook_01_r1',2:'screen_textbook_02_r1',5:'quality_textbook_05_r2',9:'screen_textbook_09_r1',20:'extension_textbook_20_r1',21:'extension_textbook_21_r1'}

def package():
    rows={r['id']:r for r in status()['trials']}
    trials={}
    for n,tid in SELECTED.items():
        row=rows[tid]
        if not row['result_path']:raise ValueError('Actual design missing: '+tid)
        folder=LAB/'native_assets'/tid
        trials[tid]={'page_number':n,'svg_path':str(folder/'artwork.svg'),'components_path':str(folder/'components.json'),
            'layout_path':str(folder/'layout.json'),'design_png_path':str(ROOT/row['result_path']),
            'clean_png_path':str(folder/'clean.png'),'semantic_review_path':str(folder/'semantic_review.json')}
    target=LAB/'native_textbook_manifest.json'
    write(target,{'font':read(LAB/'common_input.json')['font'],'selected_trial_ids':list(SELECTED.values()),'trials':trials,
        'style_selected_by_user':True,'final_native_visual_approval':False})
    return target

if __name__=='__main__':print(package())
