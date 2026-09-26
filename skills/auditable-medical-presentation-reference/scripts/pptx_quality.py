"""Independent final-PPTX glyph and composition checks, no builder manifest needed."""
import zipfile
import xml.etree.ElementTree as ET
import json
import posixpath
from pathlib import Path
from fontTools.ttLib import TTFont
from PIL import Image
from integrity import digest

NS={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
EMU=9525

def text(node): return '\n'.join(''.join(t.text or '' for t in p.findall('.//a:t',NS)) for p in node.findall('.//a:p',NS))

def rect(node):
    transform=node.find('./p:xfrm',NS)
    if transform is None: transform=node.find('./p:spPr/a:xfrm',NS)
    if transform is None: return None
    o,e=transform.find('a:off',NS),transform.find('a:ext',NS)
    if o is None or e is None: return None
    return [int(o.get('x'))/EMU,int(o.get('y'))/EMU,int(e.get('cx'))/EMU,int(e.get('cy'))/EMU]

def intersects(a,b): return min(a[0]+a[2],b[0]+b[2])>max(a[0],b[0])+0.1 and min(a[1]+a[3],b[1]+b[3])>max(a[1],b[1])+0.1

def intersection_area(a,b):
    width=max(0,min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0]))
    height=max(0,min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1]))
    return width*height

def contrast(a,b):
    def lum(c):
        rgb=[int(c[i:i+2],16)/255 for i in (0,2,4)]
        v=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in rgb]
        return sum(x*y for x,y in zip(v,(.2126,.7152,.0722)))
    x,y=sorted((lum(a),lum(b))); return (y+.05)/(x+.05)

def picture_metadata(node):
    """Return the user-visible asset identifier and embedded relationship id for a picture."""
    props=node.find('./p:nvPicPr/p:cNvPr',NS)
    blip=node.find('./p:blipFill/a:blip',NS)
    return {
        'name': props.get('name','') if props is not None else '',
        'descr': props.get('descr','') if props is not None else '',
        'embed': blip.get('{%s}embed'%NS['r']) if blip is not None else None,
    }

def asset_for_element(element, assets, media_hashes=None):
    if element['kind']!='pic': return None
    values={element.get('name',''),element.get('descr','')}
    media_hash=(media_hashes or {}).get(element.get('embed'))
    return next((asset for asset in assets if asset['asset_id'] in values or asset.get('asset_sha256','').lower()==str(media_hash).lower()),None)

def embedded_media_hashes(archive, slide_number):
    """Resolve image relationship targets to hashes without trusting a builder manifest."""
    rel_path=f'ppt/slides/_rels/slide{slide_number}.xml.rels'
    if rel_path not in archive.namelist(): return {}
    rels=ET.fromstring(archive.read(rel_path)); out={}
    for rel in rels:
        if not rel.get('Type','').endswith('/image'): continue
        target=posixpath.normpath(posixpath.join('ppt/slides',rel.get('Target',''))).lstrip('/')
        if target in archive.namelist(): out[rel.get('Id')]=digest_bytes(archive.read(target))
    return out

def digest_bytes(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()

def validate_render_evidence(pptx, evidence_path, contract, slide_number):
    """Bind an actual review raster and independent visual-review record to one final PPTX.

    This validates provenance and reviewer declarations; it cannot authenticate the reviewer
    or infer medical meaning from pixels.
    """
    if evidence_path is None:
        return 'NEEDS_REVIEW',[{'issue':'RENDER_EVIDENCE_MISSING'}],None
    try:
        evidence_path=Path(evidence_path)
        data=json.loads(evidence_path.read_text(encoding='utf-8'))
    except (OSError,json.JSONDecodeError):
        return 'FAIL',[{'issue':'RENDER_EVIDENCE_UNREADABLE'}],None
    errors=[]
    if data.get('artifact_sha256')!=digest(pptx): errors.append({'issue':'RENDER_ARTIFACT_HASH_MISMATCH'})
    if data.get('slide_number')!=slide_number: errors.append({'issue':'RENDER_SLIDE_MISMATCH'})
    renderer=data.get('renderer',{})
    if not isinstance(renderer.get('id'),str) or not renderer['id'] or not isinstance(renderer.get('version'),str) or not renderer['version']:
        errors.append({'issue':'RENDERER_IDENTITY_MISSING'})
    render=data.get('render',{})
    ref=render.get('path')
    render_path=(evidence_path.parent/ref).resolve() if isinstance(ref,str) and not Path(ref).is_absolute() else Path(ref) if isinstance(ref,str) else None
    if render_path is None or not render_path.is_file(): errors.append({'issue':'RENDER_FILE_MISSING'})
    else:
        if render.get('sha256')!=digest(render_path): errors.append({'issue':'RENDER_HASH_MISMATCH'})
        try:
            with Image.open(render_path) as image:
                if image.size!=tuple(contract['canvas']): errors.append({'issue':'RENDER_CANVAS_MISMATCH','observed':list(image.size),'expected':contract['canvas']})
        except (OSError,ValueError): errors.append({'issue':'RENDER_IMAGE_UNREADABLE'})
    if errors: return 'FAIL',errors,data
    review=data.get('visual_review')
    if not isinstance(review,dict): return 'NEEDS_REVIEW',[{'issue':'INDEPENDENT_VISUAL_REVIEW_MISSING'}],data
    required={'reviewer_id','reviewer_role','status','checked'}
    if not required<=set(review) or not review.get('reviewer_id') or review.get('reviewer_role')!='independent':
        return 'NEEDS_REVIEW',[{'issue':'INDEPENDENT_VISUAL_REVIEW_INCOMPLETE'}],data
    if not all(review.get('checked',{}).get(k) is True for k in ('glyphs','clipping','meaning_critical_text')):
        return 'NEEDS_REVIEW',[{'issue':'VISUAL_REVIEW_CHECKLIST_INCOMPLETE'}],data
    if review.get('status')=='FAIL': return 'FAIL',[{'issue':'INDEPENDENT_VISUAL_REVIEW_FAILED'}],data
    if review.get('status')!='PASS': return 'NEEDS_REVIEW',[{'issue':'INDEPENDENT_VISUAL_REVIEW_UNRESOLVED'}],data
    return 'PASS',[],data

def inspect(pptx,font_files,contract,slide_number=1,render_evidence=None):
    glyph_errors=[]; composition_errors=[]; fonts={}; cmap={}
    for family,path in font_files.items():
        with TTFont(str(path),fontNumber=0) as f: cmap[family]=f.getBestCmap() or {}
        fonts[family]=digest(path)
    with zipfile.ZipFile(pptx) as z:
        root=ET.fromstring(z.read(f'ppt/slides/slide{slide_number}.xml'))
        media_hashes=embedded_media_hashes(z,slide_number)
    glyph_records=[]
    for run in root.findall('.//a:r',NS):
        t=run.find('a:t',NS); props=run.find('a:rPr',NS)
        if t is None or not t.text: continue
        family_node=props.find('a:latin',NS) if props is not None else None
        family=family_node.get('typeface') if family_node is not None else None
        missing=[f'U+{ord(c):04X}' for c in t.text if not c.isspace() and ord(c) not in cmap.get(family,{})]
        if missing: glyph_errors.append({'text':t.text,'font':family,'missing':sorted(set(missing))})
        glyph_records.append({'text':t.text,'font':family,'font_sha256':fonts.get(family),'missing':missing})
    elements=[]
    for order,node in enumerate(root.find('p:cSld/p:spTree',NS)):
        bounds=rect(node)
        if bounds is None: continue
        kind=node.tag.split('}')[-1]; string=text(node)
        fillnode=node.find('./p:spPr/a:solidFill/a:srgbClr',NS)
        fill=fillnode.get('val') if fillnode is not None else None
        metadata=picture_metadata(node) if kind=='pic' else {}
        elements.append({'node':node,'order':order,'kind':kind,'bounds':bounds,'text':string,'fill':fill,**metadata})
    assets=contract.get('editorial_assets',[])
    for asset in assets:
        matched=[e for e in elements if asset_for_element(e,[asset],media_hashes)]
        if asset['policy']=='REQUIRED' and len(matched)!=1:
            composition_errors.append({'issue':'REQUIRED_EDITORIAL_ASSET_MISSING_OR_DUPLICATED','asset_id':asset['asset_id'],'count':len(matched)})
            continue
        if asset['policy']=='FORBIDDEN' and matched:
            composition_errors.append({'issue':'FORBIDDEN_EDITORIAL_ASSET_PRESENT','asset_id':asset['asset_id']})
        for e in matched:
            tolerance=asset.get('placement_tolerance_px',0.5)
            if any(abs(actual-expected)>tolerance for actual,expected in zip(e['bounds'],asset['placement'])):
                composition_errors.append({'issue':'EDITORIAL_ASSET_PLACEMENT_MISMATCH','asset_id':asset['asset_id']})
            if media_hashes.get(e.get('embed'))!=asset['asset_sha256']:
                composition_errors.append({'issue':'EDITORIAL_ASSET_HASH_MISMATCH','asset_id':asset['asset_id']})
            if asset['layer_role']=='EDITORIAL_UNDERLAY' and any(other['text'] and other['order']<e['order'] for other in elements):
                composition_errors.append({'issue':'EDITORIAL_UNDERLAY_NOT_BELOW_TEXT','asset_id':asset['asset_id']})
    fusion=contract.get('editorial_fusion')
    if fusion:
        fusion_assets=[asset for asset in assets if asset.get('asset_id')==fusion.get('asset_id')]
        underlay_elements=[e for e in elements if fusion_assets and asset_for_element(e,fusion_assets,media_hashes)]
        if len(underlay_elements)!=1:
            composition_errors.append({'issue':'FUSION_EDITORIAL_UNDERLAY_UNRESOLVED','asset_id':fusion.get('asset_id')})
        else:
            underlay_order=underlay_elements[0]['order']
            for zone in fusion.get('protected_zones',[]):
                box=zone['box']; area=box[2]*box[3]
                covered=0.0
                for element in elements:
                    if element['order']<=underlay_order or element['text']:
                        continue
                    is_base=asset_for_element(element,fusion_assets,media_hashes) is not None
                    opaque_shape=element['kind']=='sp' and bool(element['fill'])
                    opaque_picture=element['kind']=='pic' and not is_base
                    if opaque_shape or opaque_picture:
                        covered+=intersection_area(box,element['bounds'])
                uncovered=max(0.0,1.0-min(1.0,covered/max(area,1.0)))
                if uncovered+1e-6<zone['minimum_uncovered_area_ratio']:
                    composition_errors.append({'issue':'FUSION_EDITORIAL_BASE_OCCLUDED','zone':zone['zone_id'],'uncovered_area_ratio':round(uncovered,3),'minimum':zone['minimum_uncovered_area_ratio']})
    template_binding=contract.get('client_template_binding')
    if template_binding:
        for region in template_binding.get('brand_regions',[]):
            for element in elements:
                if element['text'] and intersects(region['box'],element['bounds']):
                    composition_errors.append({'issue':'CLIENT_TEMPLATE_BRAND_REGION_OCCLUDED','region':region['region_id'],'text':element['text']})
    width,height=contract['canvas']
    for e in elements:
        x,y,w,h=e['bounds']
        if min(x,y)<0 or x+w>width+.1 or y+h>height+.1: composition_errors.append({'issue':'OUTSIDE_CANVAS','order':e['order']})
        if not e['text']: continue
        # Native table bounds are protected even when table strings are split into cells.
        for later in elements:
            if later['order']<=e['order'] or later['text'] or not (later['fill'] or later['kind']=='pic'): continue
            if intersects(e['bounds'],later['bounds']): composition_errors.append({'issue':'LATER_LAYER_OBSCURES_TEXT_OR_TABLE','protected_order':e['order'],'overlay_order':later['order']})
        for previous in elements:
            if previous['order']>=e['order'] or not previous['text']: continue
            if intersects(e['bounds'],previous['bounds']): composition_errors.append({'issue':'TEXT_REGION_OVERLAP','orders':[previous['order'],e['order']]})
        # Shape-text contrast, taking nearest earlier flat background into account.
        if e['kind']=='sp':
            bg=contract['background_color']
            for earlier in elements:
                if earlier['order']>=e['order']: break
                if earlier['fill'] and intersects(e['bounds'],earlier['bounds']): bg=earlier['fill']
            for r in e['node'].findall('.//a:rPr',NS):
                color=r.find('a:solidFill/a:srgbClr',NS)
                if color is not None and contrast(color.get('val'),bg)<contract['minimum_contrast_ratio']:
                    composition_errors.append({'issue':'LOW_TEXT_CONTRAST','text':e['text'],'ratio':round(contrast(color.get('val'),bg),2)})
                if float(r.get('sz','0'))/100*96/72<contract['minimum_font_px']:
                    composition_errors.append({'issue':'FONT_TOO_SMALL','text':e['text']})
    for zone in contract['content_safe_regions']:
        for e in elements:
            asset=asset_for_element(e,assets,media_hashes)
            allowed_underlay=asset and asset['layer_role']=='EDITORIAL_UNDERLAY' and asset.get('allow_content_safe_underlay') is True
            if e['kind']=='pic' and intersects(zone['box'],e['bounds']) and not allowed_underlay:
                composition_errors.append({'issue':'ART_IN_CONTENT_SAFE_REGION','zone':zone['id']})
    for required in contract['mandatory_texts']:
        if sum(e['text']==required for e in elements)!=1: composition_errors.append({'issue':'MANDATORY_TEXT_MISSING_OR_DUPLICATED','text':required})
    render_status,render_errors,render_record=validate_render_evidence(pptx,render_evidence,contract,slide_number)
    glyph_status='FAIL' if glyph_errors else ('NEEDS_REVIEW' if render_status!='PASS' else 'PASS')
    return {'pptx_sha256':digest(pptx),'glyph_status':glyph_status,'glyph_errors':glyph_errors,'glyph_records':glyph_records,
        'composition_geometry_status':'FAIL' if composition_errors else 'PASS','composition_errors':composition_errors,
        'render_status':render_status,'render_errors':render_errors,'render_evidence':render_record,
        'independent_of_builder_manifest':True,
        'limitations':['Font cmap and XML cannot alone prove final visible glyphs. A hash-bound render plus independent visual-review record is required.','No native PowerPoint edit/save claim.']}
