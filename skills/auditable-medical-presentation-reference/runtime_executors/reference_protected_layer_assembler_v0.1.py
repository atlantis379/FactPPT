from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
from PIL import Image

ENGINE_ID='reference_protected_layer_assembler'
ENGINE_VERSION='v0.2'

def sha256_file(p:Path):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for ch in iter(lambda:f.read(1<<20),b''): h.update(ch)
    return h.hexdigest()

def alpha_mask(im:Image.Image): return im.convert('RGBA').getchannel('A')
def placed_mask(im:Image.Image,W,H,x,y):
    m=Image.new('L',(W,H),0); m.paste(alpha_mask(im),(x,y)); return m

def intersection_pixels(a:Image.Image,b:Image.Image):
    import PIL.ImageChops as IC
    # Binarize first: multiplying low alpha values can round an overlap to zero.
    return sum(1 for v in IC.logical_and(a.point(lambda v:255 if v else 0).convert('1'),b.point(lambda v:255 if v else 0).convert('1')).getdata() if v)

def assemble(spec_path:str,out_dir:str):
    sp=Path(spec_path); spec=json.loads(sp.read_text(encoding='utf-8')); out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    W=int(spec['canvas']['width']); H=int(spec['canvas']['height'])
    layers=sorted(spec['layers'],key=lambda x:x['z_order'])
    if W<=0 or H<=0: raise ValueError('invalid canvas')
    if len({x['z_order'] for x in layers})!=len(layers): raise ValueError('duplicate z_order')
    ids=[x['layer_id'] for x in layers]
    if len(ids)!=len(set(ids)): raise ValueError('duplicate layer_id')
    loaded=[]
    for L in layers:
        p=Path(L['path']); actual=sha256_file(p)
        if actual!=L['expected_sha256']: raise ValueError(f"{L['layer_id']}: source hash mismatch")
        if float(L.get('scale',1.0))!=1.0 or float(L.get('rotation_deg',0.0))!=0.0: raise ValueError(f"{L['layer_id']}: assembler forbids scale/rotation")
        im=Image.open(p).convert('RGBA'); x=int(L.get('x',0)); y=int(L.get('y',0))
        if x!=L.get('x',0) or y!=L.get('y',0): raise ValueError('integer translation required')
        if x<0 or y<0 or x+im.width>W or y+im.height>H: raise ValueError(f"{L['layer_id']}: bounds outside canvas")
        loaded.append((L,im,placed_mask(im,W,H,x,y)))
    if spec.get('allowed_overlap_pairs'): raise ValueError('legacy whole-layer overlap approval is unsupported; use region-bound allowed_overlaps')
    allowed=spec.get('allowed_overlaps',[])
    for grant in allowed:
        if not grant.get('contract_id') or not grant.get('reason') or len(grant.get('pair',[]))!=2:
            raise ValueError('overlap approval requires pair, contract_id and reason')
        x,y,w,h=grant['region']
        if min(x,y)<0 or min(w,h)<=0 or x+w>W or y+h>H: raise ValueError('invalid overlap region')
    overlaps=[]
    for i in range(len(loaded)):
        Li,imi,mi=loaded[i]
        for j in range(i+1,len(loaded)):
            Lj,imj,mj=loaded[j]
            # Any later layer can obscure a protected lower layer, including editorial art.
            if not Li.get('protected',False): continue
            n=intersection_pixels(mi,mj)
            if n:
                pair=tuple(sorted((Li['layer_id'],Lj['layer_id'])))
                import PIL.ImageChops as IC
                from PIL import ImageDraw
                intersection=IC.logical_and(mi.point(lambda v:255 if v else 0).convert('1'),mj.point(lambda v:255 if v else 0).convert('1'))
                approved=Image.new('1',(W,H),0)
                for grant in allowed:
                    if tuple(sorted(grant['pair']))==pair:
                        x,y,w,h=grant['region']; ImageDraw.Draw(approved).rectangle((x,y,x+w-1,y+h-1),fill=1)
                residual=IC.logical_and(intersection,IC.invert(approved))
                permitted=residual.getbbox() is None
                overlaps.append({'pair':list(pair),'pixels':n,'allowed':permitted})
                if not permitted: raise ValueError(f'undeclared protected overlap: {pair} pixels={n}')
    final=Image.new('RGBA',(W,H),(255,255,255,255))
    rec=[]
    for L,im,m in loaded:
        x=int(L.get('x',0)); y=int(L.get('y',0))
        final.alpha_composite(im,(x,y))
        rec.append({'layer_id':L['layer_id'],'role':L['role'],'protected':bool(L.get('protected',False)),'z_order':L['z_order'],'source_sha256':L['expected_sha256'],'x':x,'y':y,'width':im.width,'height':im.height,'scale':1.0,'rotation_deg':0.0})
    op=out/'final_page.png'; final.convert('RGB').save(op)
    manifest={'engine_id':ENGINE_ID,'engine_version':ENGINE_VERSION,'implementation_sha256':sha256_file(Path(__file__)),'input_spec_sha256':sha256_file(sp),'canvas':{'width':W,'height':H},'layers':rec,'protected_overlap_audit':overlaps,'transform_policy':'TRANSLATION_ONLY_SCALE_1_ROTATION_0','final_output_sha256':sha256_file(op)}
    (out/'assembly_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest

if __name__=='__main__': assemble(sys.argv[1],sys.argv[2])
