"""Portable same-font measurement/drawing, explicit glyph coverage, no font fallback."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, __version__ as pillow_version
from fontTools.ttLib import TTFont

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def compose(spec_path, out_dir, font_path):
    spec = json.loads(Path(spec_path).read_text(encoding='utf-8'))
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    font_path = Path(font_path).resolve(strict=True)
    face = int(spec.get('font_index', 0))
    width, height = (spec['canvas'][x] for x in ('width','height'))
    if any(type(n) is not int or n <= 0 for n in (width,height)): raise ValueError('positive integer canvas required')
    image = Image.new('RGBA',(width,height),(0,0,0,0)); draw = ImageDraw.Draw(image)
    seen=set(); occupied=[]; records=[]
    for obj in spec['objects']:
        oid=obj['object_id']; text=obj['exact_string']; b=obj['box']
        object_font=Path(obj.get('font_file',font_path)).resolve(strict=True)
        with TTFont(str(object_font),fontNumber=face) as ttf:
            cmap=ttf.getBestCmap() or {}
        if oid in seen: raise ValueError('duplicate object_id')
        seen.add(oid)
        if not obj.get('semantic_object_id'): raise ValueError('semantic binding required')
        if any(ord(c) not in cmap for c in text if c not in '\n'): raise ValueError(f'{oid}: unsupported glyph/control character')
        x,y,w,h=(b[k] for k in ('x','y','width','height'))
        size=obj.get('font_size',24); line_height=obj.get('line_height',math.ceil(size*1.5))
        if not all(isinstance(n,(int,float)) and math.isfinite(n) for n in (x,y,w,h,size,line_height)): raise ValueError('finite geometry required')
        if min(w,h,size)<=0 or min(x,y)<0 or x+w>width or y+h>height: raise ValueError('invalid box')
        font=ImageFont.truetype(str(object_font),int(size),index=face)
        ascent,descent=font.getmetrics()
        if line_height<ascent+descent: raise ValueError('line height below font metrics')
        # Explicit newlines are retained as offsets; no silent normalization.
        lines=[]; cur=''; start=0; offset=0
        for c in text:
            if c=='\n':
                lines.append((cur,start,offset)); cur=''; start=offset+1
            elif cur and draw.textlength(cur+c,font=font)>w:
                lines.append((cur,start,offset)); cur=c; start=offset
            else: cur+=c
            offset+=1
        lines.append((cur,start,offset))
        if len(lines)*line_height>h: raise ValueError('text height overflow')
        ink=[]
        for i,(line,s,e) in enumerate(lines):
            baseline=y+ascent+i*line_height
            bounds=draw.textbbox((x,baseline),line,font=font,anchor='ls')
            if bounds[0]<x or bounds[1]<y or bounds[2]>x+w or bounds[3]>y+h: raise ValueError('ink outside box')
            for other in occupied:
                if max(bounds[0],other[0])<min(bounds[2],other[2]) and max(bounds[1],other[1])<min(bounds[3],other[3]): raise ValueError('text ink overlap')
            draw.text((x,baseline),line,font=font,anchor='ls',fill=obj.get('color','#102A43'))
            ink.append({'text':line,'start':s,'end':e,'ink_bounds':bounds}); occupied.append(bounds)
        records.append({'object_id':oid,'semantic_object_id':obj['semantic_object_id'],'exact_string':text,'font_sha256':sha(object_font),'lines':ink})
    target=out/'exact_overlay.png'; image.save(target)
    manifest={'engine_id':'portable_exact_overlay','engine_version':'0.5.0','implementation_sha256':sha(__file__),
              'font_sha256':sha(font_path),'font_index':face,'pillow_version':pillow_version,'input_sha256':sha(spec_path),
              'output_sha256':sha(target),'glyph_check':'PASS','objects':records}
    (out/'generation_output_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('spec'); p.add_argument('out'); p.add_argument('--font',required=True)
    a=p.parse_args(); compose(a.spec,a.out,a.font)
