"""Experiment-only HTML measurement and native geometry adapter.

The generated complete designs are references, never authoritative text.
All displayed content comes from the immutable exported sample lock.
No production renderer or workflow database is changed.
"""
from __future__ import annotations

import html
import json
import math
import time
from pathlib import Path

from tools.visual_ab_test import OUT, ROOT, SAMPLES, STYLE, dump, sha

BLUE, INK, PAPER = STYLE['accent'], STYLE['ink'], STYLE['paper']


def canon(s):
    return ''.join(s.split())


class Canvas:
    def __init__(self, page, route):
        self.page, self.route = page, route
        self.parts, self.vectors, self.regions = [], [], []
        self.used = set()
        self.serial = 0

    def text(self, text, x, y, w, h, size=24, *, fact=None, authored=False,
             color=INK, bold=False, line=None, align='left', parts=None, role=''):
        self.serial += 1
        line = line or round(size * 1.3, 2)
        attr = f'data-fact="{html.escape(fact)}"' if fact else ('data-authored=""' if authored else 'data-chrome=""')
        if fact:
            assert canon(text) == canon(self.page['facts'][fact]), (fact, text)
            assert fact not in self.used, fact
            self.used.add(fact)
        if parts:
            assert canon(''.join(s for s, _ in parts)) == canon(text)
            content = ''.join(f'<span style="color:{c}">{html.escape(s)}</span>' for s, c in parts)
        else:
            content = html.escape(text)
        cls = 'text title' if role == 'title' else 'text'
        self.parts.append(f'<div class="{cls}" data-t="" data-region="t{self.serial}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;font-size:{size}px;line-height:{line}px;font-weight:{700 if bold else 400};color:{color};text-align:{align}"><span {attr}>{content}</span></div>')
        self.regions.append(dict(id=f't{self.serial}', fact=fact, text=text, x=x, y=y, w=w, h=h,
                                 size=size, line=line, role=role or 'content'))

    def f(self, fid, *geo, **kw):
        self.text(self.page['facts'][fid], *geo, fact=fid, **kw)

    def path(self, commands, *, fill=None, stroke=None, width=1, opacity=1, name='decoration'):
        self.vectors.append(dict(commands=commands, fill=fill, stroke=stroke,
                                 width=width, opacity=opacity, name=name))

    def line(self, pts, color=BLUE, width=1, opacity=1, name='rule'):
        self.path([['M', *pts[0]]] + [['L', *p] for p in pts[1:]], stroke=color, width=width, opacity=opacity, name=name)

    def dashes(self, start, end, y, color):
        commands=[]
        for x in range(start,end,8):commands.extend([['M',x,y],['L',x+3,y]])
        self.path(commands,stroke=color,width=.7,name='dashed rule')

    def rect(self, x, y, w, h, fill, radius=0, opacity=1, stroke=None):
        r = min(radius, w/2, h/2)
        self.path([['M',x+r,y],['L',x+w-r,y],['Q',x+w,y,x+w,y+r],['L',x+w,y+h-r],
                   ['Q',x+w,y+h,x+w-r,y+h],['L',x+r,y+h],['Q',x,y+h,x,y+h-r],
                   ['L',x,y+r],['Q',x,y,x+r,y],['Z']], fill=fill, stroke=stroke, opacity=opacity, name='panel')

    def ellipse(self, x, y, rx, ry, fill=None, stroke=None, width=1, opacity=1, name='icon'):
        k = .55228475
        self.path([['M',x+rx,y],['C',x+rx,y+k*ry,x+k*rx,y+ry,x,y+ry],
                   ['C',x-k*rx,y+ry,x-rx,y+k*ry,x-rx,y],
                   ['C',x-rx,y-k*ry,x-k*rx,y-ry,x,y-ry],
                   ['C',x+k*rx,y-ry,x+rx,y-k*ry,x+rx,y],['Z']],
                  fill=fill,stroke=stroke,width=width,opacity=opacity,name=name)

    def icon(self, kind, x, y, s):
        # Every icon is a native path in B; no SVG image or raster fallback.
        if kind == 'clip':
            self.rect(x+s*.12,y+s*.1,s*.68,s*.84,None,s*.03,stroke=BLUE)
            self.rect(x+s*.31,y,s*.32,s*.2,PAPER,s*.03,stroke=BLUE)
            for i,w in enumerate((.43,.43,.32)):
                self.line([(x+s*.24,y+s*(.36+.2*i)),(x+s*(.24+w),y+s*(.36+.2*i))],width=3)
        elif kind == 'globe':
            self.ellipse(x+s/2,y+s/2,s*.47,s*.47,stroke=BLUE,width=3)
            self.ellipse(x+s/2,y+s/2,s*.2,s*.47,stroke=BLUE,width=2)
            self.line([(x,y+s/2),(x+s,y+s/2)],width=2)
            for yy in (.28,.72):
                self.path([['M',x+s*.1,y+s*yy],['Q',x+s/2,y+s*(yy+.08*(1 if yy<.5 else -1)),x+s*.9,y+s*yy]],stroke=BLUE,width=2)
        elif kind in ('cells','sputum'):
            self.ellipse(x+s*.5,y+s*.51,s*.46,s*.4,fill='#DDE8FC',stroke='#A9C3F5',width=2)
            for xx,yy,rr in ((.28,.44,.16),(.68,.59,.17),(.70,.24,.1)):
                self.ellipse(x+s*xx,y+s*yy,s*rr,s*rr,fill='#86ABF2',stroke='#648FF0',width=1.3)
                self.ellipse(x+s*(xx-.025),y+s*(yy-.02),s*rr*.48,s*rr*.5,fill=BLUE)
                if kind == 'sputum':
                    self.ellipse(x+s*(xx+.05),y+s*(yy+.04),s*.027,s*.027,fill=BLUE)
        elif kind == 'lung':
            self.path([['M',x+s*.43,y+s*.17],['C',x+s*.2,y+s*.01,x+s*.06,y+s*.57,x+s*.07,y+s*.83],
                       ['Q',x+s*.1,y+s*.91,x+s*.43,y+s*.65],['Z']],fill='#DBE7FD',stroke='#7DA2EC',width=2)
            self.path([['M',x+s*.57,y+s*.17],['C',x+s*.8,y+s*.01,x+s*.94,y+s*.57,x+s*.93,y+s*.83],
                       ['Q',x+s*.9,y+s*.91,x+s*.57,y+s*.65],['Z']],fill='#DBE7FD',stroke='#7DA2EC',width=2)
            self.line([(x+s*.5,y),(x+s*.5,y+s*.35),(x+s*.26,y+s*.52)],width=4)
            self.line([(x+s*.5,y+s*.35),(x+s*.76,y+s*.52)],width=4)
            for sign in (-1,1):
                for yy in (.42,.57,.72):
                    self.line([(x+s*(.5+sign*.15),y+s*yy),(x+s*(.5+sign*.31),y+s*(yy-.11))],width=1.5)
        elif kind == 'head':
            self.path([['M',x+s*.8,y+s*.92],['L',x+s*.68,y+s*.68],['C',x+s*.94,y+s*.12,x+s*.53,y,x+s*.37,y+s*.14],
                       ['Q',x+s*.26,y+s*.3,x+s*.3,y+s*.39],['L',x+s*.18,y+s*.48],['L',x+s*.31,y+s*.51],
                       ['Q',x+s*.26,y+s*.63,x+s*.4,y+s*.65],['L',x+s*.43,y+s*.92],['Z']],fill='#BFD4FA')
            self.path([['M',x+s*.30,y+s*.43],['Q',x+s*.60,y+s*.43,x+s*.60,y+s*.91]],stroke='white',width=5)
            for xx,yy in ((.02,.30),(.06,.68),(.13,.1)):
                self.ellipse(x+s*xx,y+s*yy,s*.055,s*.055,fill='#85A9F4',stroke=BLUE)
        elif kind == 'people':
            for xx, yy, rr in ((.5,.22,.14),(.14,.35,.1),(.86,.35,.1)):
                self.ellipse(x+s*xx,y+s*yy,s*rr,s*rr,fill='#7AA0EE')
                self.rect(x+s*(xx-rr),y+s*(yy+rr+.04),s*rr*2,s*.4,'#A7C3F6',s*rr)
        elif kind == 'antibody':
            self.line([(x+s*.5,y+s*.93),(x+s*.5,y+s*.50),(x+s*.15,y+s*.12)],width=s*.1)
            self.line([(x+s*.5,y+s*.50),(x+s*.85,y+s*.12)],width=s*.1)
            self.line([(x+s*.38,y+s*.89),(x+s*.38,y+s*.55),(x+s*.08,y+s*.25)],width=s*.07)
            self.line([(x+s*.62,y+s*.89),(x+s*.62,y+s*.55),(x+s*.92,y+s*.25)],width=s*.07)
        elif kind == 'warning':
            self.path([['M',x+s*.5,y+s*.02],['L',x+s*.98,y+s*.88],['L',x+s*.02,y+s*.88],['Z']],stroke=BLUE,width=3)
            self.line([(x+s*.5,y+s*.3),(x+s*.5,y+s*.59)],width=4)
            self.ellipse(x+s*.5,y+s*.74,s*.025,s*.025,fill=BLUE)

    def svg(self):
        paths = []
        for v in self.vectors:
            d = ' '.join(c[0] + ' ' + ' '.join(f'{n:.3f}' for n in c[1:]) for c in v['commands'])
            paths.append(f'<path data-native="{html.escape(json.dumps(v),quote=True)}" d="{d}" fill="{v["fill"] or "none"}" stroke="{v["stroke"] or "none"}" stroke-width="{v["width"]}" opacity="{v["opacity"]}" stroke-linejoin="round" stroke-linecap="round"/>')
        return '<svg class="vectors" width="1280" height="720" viewBox="0 0 1280 720">'+''.join(paths)+'</svg>'


def waves(c, *, left=False, cover=False):
    # References' grain and microvasculature are intentionally not rasterized in B.
    for i in range(16 if cover else 10):
        off=i*3.4
        if left:
            commands=[['M',0,605+off],['C',210,704+off*.2,315,606+off,740,720]]
        else:
            commands=[['M',420+off*2,720],['C',740,592+off,965,698-off,1280,570+off]]
        c.path(commands,stroke='#638FE7',width=.8,opacity=.15+(.05 if i%3==0 else 0),name='editorial wave')


def large_lung(c, x=702, y=65, scale=1):
    # Stylized reconstruction of the actual design reference, not a clinical diagram.
    def path(cmd, **kw):
        transformed=[[a[0], *[(x+n*scale if i%2==0 else y+n*scale) for i,n in enumerate(a[1:])]] for a in cmd]
        c.path(transformed,**kw)
    for cmd in ([['M',215,50],['C',149,-10,48,152,17,338],['C',-8,505,88,500,207,430],['C',254,330,231,213,215,50],['Z']],
                [['M',340,60],['C',403,0,546,182,558,360],['C',573,529,475,465,376,437],['C',327,300,330,205,340,60],['Z']]):
        path(cmd,fill='#AEC8F7',opacity=.5,stroke='#719DEE',width=.8)
    path([['M',285,-60],['C',266,50,299,136,269,185],['L',197,257],['L',208,276],['L',286,209],['L',360,290],['L',378,279],['L',306,185],['C',285,139,289,70,307,-60],['Z']],fill=BLUE,opacity=.9)
    branches=[[(218,257),(154,271),(85,250)],[(203,277),(160,340),(101,393)],[(177,310),(117,302),(51,327)],
              [(156,344),(131,411),(77,465)],[(375,283),(425,306),(507,306)],[(396,315),(438,367),(508,414)],
              [(431,353),(511,352),(544,372)],[(422,351),(447,426),(486,453)]]
    for b in branches:
        path([['M',*b[0]],['Q',*b[1],*b[2]]],stroke=BLUE,width=4*scale,opacity=.9)
        mid=b[1]
        for j in (-1,1):
            end=(mid[0]+j*25,mid[1]-40)
            path([['M',*mid],['Q',mid[0]+j*8,mid[1]-22,*end]],stroke=BLUE,width=1.2*scale,opacity=.7)


def footer(c, y=674, size=12):
    p=c.page
    if p['sample']==1:
        c.text(p['chrome'][0],54,y,760,30,size=size,color=STYLE['muted'])
    else:
        c.text(p['chrome'][0],54,y,1135,32,size=size,color=STYLE['muted'],line=17)
        c.text(p['chrome'][1],1195,y-1,40,32,size=20,bold=True,color=BLUE,align='right')


def common(c, title_size=54):
    p=c.page
    if c.route=='B':
        waves(c,left=p['sample']==4)
        c.line([(54,655),(1224,655)],color='#91AFEA',width=1,opacity=.8)
        c.line([(54,87),(88,87)],width=3)
    c.text(p['authored'][0],54,49,900,34,size=22,bold=True,authored=True)
    if p['sample']!=3:
        fid='def.title' if p['sample']==2 else None
        title=p['facts'][fid] if fid else p['authored'][1]
        cut={2:7,4:5,5:4}.get(p['sample'],len(title))
        c.text(title,54,109 if p['sample']!=4 else 88,1170,83,size=title_size,bold=True,
               fact=fid,authored=not fid,role='title',parts=[(title[:cut],INK),(title[cut:],BLUE)])


def page_canvas(p, route):
    c=Canvas(p,route)
    i=p['sample']
    if route=='A':
        c.parts.append(f'<img class="background" data-raster="bg{i}" src="../clean_backgrounds/sample{i:02d}.png" alt=""/>')
    if i==1:
        if route=='B':
            large_lung(c)
            waves(c,cover=True)
        c.line([(54,132),(89,132)],width=3)
        c.text(p['authored'][0],54,89,420,44,size=27,bold=True,authored=True)
        title=p['authored'][1]
        c.text(title,54,176,692,224,size=84,bold=True,line=108,authored=True,role='title',
               parts=[('哮喘与慢阻肺\n',INK),('生物制剂治疗应用',BLUE)])
        c.text(p['authored'][2],54,435,680,100,size=32,authored=True,line=43)
        footer(c,y=668,size=15)
    elif i==2:
        common(c,title_size=55)
        if route=='A':c.rect(50,215,112,43,'#FBFAF7')
        c.text(p['authored'][1],54,222,120,38,size=25,bold=True,authored=True)
        if route=='B':
            c.line([(161,234),(1224,234)],color='#A7BFEE',opacity=.8)
            c.line([(614,270),(614,560)],color='#B2C7EA',opacity=.8)
            c.icon('clip',55,271,42); c.icon('globe',650,267,51)
            for x in (80,677):
                for y in (376,511): c.ellipse(x,y,23,23,fill='#DEE8FB')
            for xx in (54,650):
                c.dashes(xx,xx+540,471,'#B8C8E6')
        for fid,x,w,cut in [('def.cn.h',116,452,4),('def.gina.h',721,493,9)]:
            s=p['facts'][fid]
            c.text(s,x,276,w,77,size=25,bold=True,fact=fid,line=34,parts=[(s[:cut],BLUE),(s[cut:],INK)])
        for k,fid,x,y,w in [(1,'def.cn.a',128,357,436),(2,'def.cn.b',128,494,436),
                             (1,'def.gina.a',726,357,478),(2,'def.gina.b',726,494,478)]:
            c.text(str(k),63 if x==128 else 660,y+5,34,38,size=27,bold=True,color=BLUE,align='center')
            s=p['facts'][fid]
            highlighted={'def.cn.a':'仍未控制','def.cn.b':'出现加重','def.gina.a':'仍未得到控制的哮喘；','def.gina.b':'发生急性发作的哮喘'}[fid]
            cut=s.index(highlighted)
            c.text(s,x,y,w,110 if k==1 else 83,size=22,line=31,fact=fid,
                   parts=[(s[:cut],INK),(s[cut:],BLUE)])
        c.f('def.gloss',54,621,930,29,size=14,line=19)
        c.f('def.ref1',54,651,1162,23,size=11.5,line=17)
        c.f('def.ref2',54,672,1162,23,size=11.5,line=17)
        # All three long references survive; move the export source to the margin above them.
        c.text(p['chrome'][0],650,596,526,23,size=11.5,line=17,color=STYLE['muted'])
        c.text(p['chrome'][1],1195,595,40,28,size=20,bold=True,color=BLUE,align='right')
    elif i==3:
        common(c)
        lead=p['facts']['o.f025']; cut=lead.index('应考虑')
        c.text(lead,54,103,1160,152,size=45,bold=True,line=63,fact='o.f025',role='title',
               parts=[(lead[:cut]+'\n',INK),(lead[cut:],BLUE)])
        c.text(p['authored'][1],54,272,820,39,size=23,bold=True,authored=True)
        if route=='B':
            for x in (341,650,944): c.line([(x,315),(x,529)],color='#AAC1E6',opacity=.85)
            for kind,x,w in [('cells',117,98),('lung',430,111),('sputum',741,104),('head',1062,100)]:
                c.icon(kind,x,320,w)
            c.rect(54,565,603,66,'#E4ECFA',5)
            c.icon('clip',84,579,41)
            c.line([(160,577),(160,617)],color='#A6BFEC')
            c.dashes(54,1224,544,'#A7BFEB')
        for label,value,x,w,vs in [('o.d.p.eos.l','o.d.p.eos',54,278,54),('o.d.p.feno.l','o.d.p.feno',365,265,51),
                                  ('o.d.p.sp.l','o.d.p.sp',678,250,59),('o.d.p.al.l','o.d.p.al',963,271,36)]:
            c.f(label,x,427,w,40,size=22,bold=True,align='center',line=29)
            c.f(value,x,470,w,76,size=vs,bold=True,color=BLUE,align='center',line=68)
        c.text(p['authored'][2],194,569,427,27,size=18,bold=True,authored=True)
        c.text(p['facts']['o.d5.ph.sp'].replace('\n',' '),194,596,427,32,size=21,line=28,
               fact='o.d5.ph.sp',bold=True,color=BLUE)
        footer(c,size=11.5)
    elif i==4:
        common(c,title_size=48)
        if route=='B':
            c.icon('clip',54,171,45)
            c.line([(54,239),(1224,239)],color='#A8BFF0')
            c.rect(490,255,300,77,'#DEE8FC',39)
            c.ellipse(544,293,49,44,fill='#C9DCFB'); c.icon('lung',514,269,55)
            for x,w in ((87,337),(470,346),(862,336)):
                c.rect(x,366,w,67,'#DFE9FA',34)
                c.ellipse(x+59,399,32,32,fill='#CCDDFB'); c.icon('cells',x+32,372,54)
            c.rect(850,453,352,84,'#E9EDF2',12); c.rect(850,549,352,82,'#E9EDF2',12)
            c.ellipse(905,494,36,36,fill='#D4E2FC');c.icon('warning',883,473,43)
            c.ellipse(905,589,36,36,fill='#D4E2FC');c.icon('antibody',884,569,42)
        # The reference invents a low→clinical-selection edge. The frozen export
        # has middle→clinical-selection→targets, and no outgoing low edge.
        c.rect(75,447,737,190,'#FBFAF7' if route=='A' else PAPER)
        c.rect(477,450,326,179,'#E9EDF2',12)
        c.ellipse(553,559,40,40,fill='#D4E2FC');c.icon('antibody',529,535,48)
        c.line([(495,504),(782,504)],color='#B6C8E7',width=.8)
        c.f('o.d.nejm',123,170,1090,69,size=25,line=35)
        c.f('o.d.t.nocs',588,268,187,62,size=23,bold=True,line=30,align='center')
        c.f('o.d.t.eos1',202,376,207,54,size=22,bold=True,line=27,align='center')
        # Rewrap between threshold and unit without changing any character.
        s=p['facts']['o.d.t.eos2'].replace('个细胞','\n个细胞')
        c.text(s,571,376,231,54,size=21,bold=True,line=27,align='center',fact='o.d.t.eos2')
        c.f('o.d.t.eos3',976,376,211,54,size=22,bold=True,line=27,align='center')
        c.f('o.d.t.by',496,457,285,49,size=19,bold=True,line=25)
        c.f('o.d.t.o.mid',625,516,156,117,size=21,bold=True,line=23)
        c.f('o.f054',958,461,232,68,size=19,line=25)
        c.f('o.d.t.o.hi',980,564,200,58,size=23,bold=True,line=28)
        # Same seven supported edges as the frozen HTML, in a new orientation.
        edges=[('o.d.ar.s20:a20',[(640,332),(640,347),(256,347),(256,365)]),
               ('o.d.ar.s20:a10',[(640,332),(640,365)]),
               ('o.d.ar.s20:a11',[(640,332),(640,347),(1030,347),(1030,365)]),
               ('o.d.ar.s20:a3',[(642,433),(642,450)]),
               ('o.d.ar.s20:a2',[(705,507),(705,517)]),
               ('o.d.ar.s20:a16',[(1030,433),(1030,452)]),
               ('o.d.ar.s20:a1',[(1030,537),(1030,548)])]
        lines=[]
        for fid,pts in edges:
            points=' '.join(f'{x},{y}' for x,y in pts)
            lines.append(f'<polyline data-edge="{fid}" points="{points}" stroke="{BLUE}" stroke-width="2" fill="none" marker-end="url(#arr{route})"/>')
        c.parts.insert(0,f'<svg class="edge-layer" data-edges="" viewBox="0 0 1280 720" width="1280" height="720"><defs><marker id="arr{route}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="{BLUE}"/></marker></defs>{"".join(lines)}</svg>')
        footer(c,size=12)
    elif i==5:
        common(c,title_size=55)
        if route=='B':
            c.line([(54,213),(1224,213)],width=1.2,opacity=.85)
            c.icon('clip',54,240,47); c.icon('people',54,334,47)
            c.line([(700,245),(700,618)],color='#B2C5E4')
            for y in (454,572): c.ellipse(80,y,23,23,fill='#DFE9FC')
            for y in (411,532):
                c.dashes(54,674,y,'#B0C5E9')
            c.line([(732,465),(1226,465)],width=2)
        c.f('o.f190',124,243,540,77,size=23,bold=True,line=32)
        c.f('o.f073',128,330,542,78,size=21,line=30)
        for k,fid,y,h in [(1,'o.f071',437,95),(2,'o.f072',556,80)]:
            c.text(str(k),63,y+1,34,39,size=27,bold=True,color=BLUE,align='center')
            c.f(fid,128,y,542,h,size=21,line=30)
        c.f('o.f199',733,270,493,180,size=137,bold=True,color=BLUE,line=178)
        c.f('o.f200',732,490,493,90,size=43,bold=True,line=57)
        footer(c,size=12)
    elif i==6:
        if route=='A':c.rect(50,132,211,42,'#FBFAF7')
        if route=='B':
            waves(c)
            c.line([(54,40),(97,40)],width=4)
            c.line([(261,154),(1226,154)],width=1,color='#91ADE4')
            c.line([(54,668),(1226,668)],width=1,color='#91ADE4')
        c.text(p['authored'][0],54,57,1162,82,size=62,bold=True,authored=True,role='title',
               parts=[('价格、医保',INK),('与用法',BLUE)])
        c.text(p['authored'][1],54,138,315,40,size=25,bold=True,authored=True)
        widths=[176,218,400,140,108,180]
        heights=[49,57,67,70,119,53,53]
        rows=[]
        for ri,row in enumerate(p['table']):
            cells=[]
            for ci,cell in enumerate(row):
                fid=cell['facts'][0] if cell['facts'] else None
                text=cell['text']
                if fid:
                    self_text=p['facts'][fid]
                    assert canon(text)==canon(self_text)
                    c.used.add(fid)
                    text=self_text
                attr=f'data-fact="{fid}"' if fid else 'data-authored=""'
                # Keep exact digits and units, but use line breaks for the dual price.
                if fid=='o.f161': text=text.replace(' 200mg','\n200mg')
                size=19 if not ri else (22 if ci==0 else (24 if ci==5 and fid!='o.f161' else (17.5 if ci==2 or fid=='o.f161' else 18.5)))
                color='white' if not ri else (BLUE if ci==5 else INK)
                fill=BLUE if not ri else (PAPER if ri%2 else '#EFEEE8')
                align='center' if ci in (3,4,5) or not ri else 'left'
                cells.append(f'<{"th" if not ri else "td"} style="width:{widths[ci]}px;height:{heights[ri]}px;background:{fill};color:{color};font-size:{size}px;line-height:{25 if ri else 30}px;font-weight:{700 if not ri or ci in (0,5) else 400};text-align:{align};"><span {attr}>{html.escape(text)}</span></{"th" if not ri else "td"}>')
            rows.append('<tr>'+''.join(cells)+'</tr>')
        c.parts.append('<table data-table="" style="left:32px;top:178px;width:1222px"><colgroup>'+''.join(f'<col style="width:{w}px"/>' for w in widths)+'</colgroup>'+''.join(rows)+'</table>')
        footer(c,y=680,size=11.5)
    assert c.used==set(p['facts']), (i, set(p['facts'])-c.used)
    return c


CSS='''*{box-sizing:border-box}html,body{margin:0;padding:0;background:#e6e8ed}body{font-family:"Microsoft YaHei",sans-serif;color:#151B24}.slide{position:relative;width:1280px;height:720px;overflow:hidden;background:#F6F4EF;break-after:page;margin:0 auto 24px}.text{position:absolute;z-index:3;white-space:pre-line;overflow:visible}.text span{white-space:inherit}.background{position:absolute;inset:0;width:1280px;height:720px;z-index:0}.vectors{position:absolute;inset:0;z-index:1;pointer-events:none}.edge-layer{position:absolute;inset:0;z-index:2}table{position:absolute;z-index:3;border-collapse:collapse;table-layout:fixed}th,td{padding:10px 12px;vertical-align:middle;border-bottom:1px solid #D6D9DE;white-space:pre-line;overflow-wrap:normal}td:nth-child(3){padding-top:9px;padding-bottom:9px}@media print{html,body{background:none}.slide{margin:0;break-after:page}@page{size:1280px 720px;margin:0}}'''


def native_vectors(pptx_path, vector_models):
    """Export code-authored SVG paths as editable Office custom geometry."""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.oxml.xmlchemy import OxmlElement
    from pptx.oxml.ns import qn
    from pptx.util import Emu
    PX=9525
    E=lambda x:Emu(round(x*PX))
    prs=Presentation(pptx_path)
    for slide,vectors in zip(prs.slides,vector_models):
        # Restore title layering: the stock renderer's title placeholder is first.
        title=slide.shapes.title
        if title is not None:
            slide.shapes._spTree.remove(title._element)
            slide.shapes._spTree.insert_element_before(title._element,'p:extLst')
        insert=2+sum(1 for s in slide.shapes if s.shape_type==13)
        for j,v in enumerate(vectors):
            coords=[c[1:] for c in v['commands'] if len(c)>1]
            xs=[a for row in coords for a in row[::2]]; ys=[a for row in coords for a in row[1::2]]
            x0,y0=min(xs),min(ys); w,h=max(max(xs)-x0,.1),max(max(ys)-y0,.1)
            sh=slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,E(x0),E(y0),E(w),E(h))
            sh.name=f'{v["name"]} {j+1}'
            sp=sh._element.spPr
            old=sp.find(qn('a:prstGeom')); sp.remove(old)
            geom=OxmlElement('a:custGeom')
            for n in ('avLst','gdLst','ahLst','cxnLst'):geom.append(OxmlElement('a:'+n))
            rect=OxmlElement('a:rect')
            for k,a in dict(l='0',t='0',r='r',b='b').items():rect.set(k,a)
            geom.append(rect)
            paths=OxmlElement('a:pathLst'); path=OxmlElement('a:path')
            path.set('w',str(max(1,round(w*1000))));path.set('h',str(max(1,round(h*1000))))
            path.set('fill','norm' if v['fill'] else 'none');path.set('stroke','1' if v['stroke'] else '0')
            for cmd in v['commands']:
                tag={'M':'moveTo','L':'lnTo','C':'cubicBezTo','Q':'quadBezTo','Z':'close'}[cmd[0]]
                el=OxmlElement('a:'+tag)
                for k in range(1,len(cmd),2):
                    pt=OxmlElement('a:pt');pt.set('x',str(round((cmd[k]-x0)*1000)));pt.set('y',str(round((cmd[k+1]-y0)*1000)));el.append(pt)
                path.append(el)
            paths.append(path);geom.append(paths);sp.insert(1,geom)
            for oldfill in list(sp):
                if oldfill.tag in (qn('a:solidFill'),qn('a:noFill'),qn('a:gradFill'),qn('a:ln')):sp.remove(oldfill)
            def fill(parent,color):
                f=OxmlElement('a:solidFill' if color else 'a:noFill')
                if color:
                    rgb=OxmlElement('a:srgbClr');rgb.set('val',color.lstrip('#').upper() if color!='white' else 'FFFFFF')
                    if v['opacity']<1:
                        a=OxmlElement('a:alpha');a.set('val',str(round(v['opacity']*100000)));rgb.append(a)
                    f.append(rgb)
                parent.append(f)
            fill(sp,v['fill'])
            ln=OxmlElement('a:ln');ln.set('w',str(round(v['width']*PX)));ln.set('cap','rnd')
            fill(ln,v['stroke']);ln.append(OxmlElement('a:round'));sp.append(ln)
            sh.shadow.inherit=False
            sh.text_frame.text=''
            # Insert all artwork in DOM order behind native connectors and text.
            tree=slide.shapes._spTree;tree.remove(sh._element);tree.insert(insert,sh._element);insert+=1
        for sh in slide.shapes:
            if sh.has_table:
                from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
                for ri,row in enumerate(sh.table.rows):
                    for ci,cell in enumerate(row.cells):
                        cell.vertical_anchor=MSO_ANCHOR.MIDDLE
                        for para in cell.text_frame.paragraphs:
                            para.alignment=PP_ALIGN.CENTER if ci in (3,4,5) or not ri else PP_ALIGN.LEFT
                        # The legacy exporter appends borders after the table style's
                        # defaults. Remove duplicate sides in this isolated adapter.
                        props=cell._tc.get_or_add_tcPr()
                        for node in list(props):
                            if node.tag in [qn('a:ln'+a) for a in ('L','R','T','B')]:props.remove(node)
                        for border_index,side in enumerate(('L','R','T','B')):
                            border=OxmlElement('a:ln'+side);border.set('w','6350')
                            f=OxmlElement('a:solidFill');co=OxmlElement('a:srgbClr');co.set('val','D6D9DE');f.append(co);border.append(f)
                            props.insert(border_index,border)
    prs.save(pptx_path)


def verify_pptx(path, pages):
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    prs=Presentation(path); assert len(prs.slides)==6
    checks=[]
    for slide,p in zip(prs.slides,pages):
        texts=[]; pics=0; tables=0; native=0
        for sh in slide.shapes:
            pics+=int(sh.shape_type==MSO_SHAPE_TYPE.PICTURE)
            native+=int(sh.shape_type!=MSO_SHAPE_TYPE.PICTURE)
            if sh.has_text_frame:texts.append(sh.text)
            if sh.has_table:
                tables+=1;texts.extend(cell.text for row in sh.table.rows for cell in row.cells)
                got=[[canon(cell.text) for cell in row.cells] for row in sh.table.rows]
                assert got==[[canon(cell['text']) for cell in row] for row in p['table']]
        blob=canon('\n'.join(texts))
        missing=[fid for fid,s in p['facts'].items() if canon(s) not in blob]
        missing_authored=[s for s in p['authored'] if canon(s) not in blob]
        missing_chrome=[s for s in p['chrome'] if canon(s) not in blob]
        assert not missing and not missing_authored and not missing_chrome,(p['sample'],missing,missing_authored,missing_chrome)
        assert slide.notes_slide.notes_text_frame.text==p['notes']
        checks.append(dict(sample=p['sample'],facts=len(p['facts']),missing=missing,missing_authored=missing_authored,
                           pictures=pics,native_objects=native,tables=tables,source_notes_exact=True))
    return checks


def build():
    from playwright.sync_api import sync_playwright
    from factdeck.render import build_pptx
    lock=json.loads((OUT/'content_lock.json').read_text(encoding='utf8'))
    for name,digest in lock['source_hashes'].items():assert sha(OUT/'frozen'/name)==digest
    expected={fid:s for p in lock['pages'] for fid,s in p['facts'].items()}
    extract=(ROOT/'factdeck'/'extract.js').read_text(encoding='utf8')
    design=[]; results={}; start=time.perf_counter()
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        web=browser.new_page(viewport={'width':1280,'height':720},device_scale_factor=1)
        for route in ('A','B'):
            started=time.perf_counter(); folder=OUT/route; folder.mkdir(exist_ok=True)
            canvases=[page_canvas(p,route) for p in lock['pages']]
            doc='<html lang="zh-CN"><head><meta charset="utf-8"><title>视觉实测 '+route+'</title><style>'+CSS+'</style></head><body>'
            doc+=''.join(f'<section class="slide" id="ab{i+1}">{c.svg()}{"".join(c.parts)}</section>' for i,c in enumerate(canvases))+'</body></html>'
            (folder/'deck.html').write_text(doc,encoding='utf8')
            web.goto((folder/'deck.html').as_uri());web.evaluate('document.fonts.ready')
            models=[]; checks=[]
            for i,c in enumerate(canvases):
                web.locator(f'#ab{i+1}').screenshot(path=str(folder/f'browser{i+1:02d}.png'))
                m=web.evaluate(extract,{'slideId':f'ab{i+1}','expected':expected})
                for t,r in zip(m['texts'],c.regions):t['role']='title' if r['role']=='title' else ''
                extra=web.evaluate('''(id)=>{const s=document.getElementById(id),out=[];for(const a of s.querySelectorAll('table')){const A=a.getBoundingClientRect();for(const b of s.querySelectorAll('[data-t]')){const B=b.getBoundingClientRect();if(Math.min(A.right,B.right)-Math.max(A.left,B.left)>2&&Math.min(A.bottom,B.bottom)-Math.max(A.top,B.top)>2)out.push(b.textContent)}}return out}''',f'ab{i+1}')
                m['checks']['overlap'].extend(extra)
                assert not any(m['checks'][k] for k in ('untracked','mismatch','overflow','bounds','overlap')),m['checks']
                checks.append(m['checks']);models.append(m)
                if route=='B':
                    design.append(dict(sample=i+1,original_page=SAMPLES[i],reference=f'designs/sample{i+1:02d}.png',
                                       prompt=f'prompts/sample{i+1:02d}-full-design.txt',regions=c.regions,
                                       vector_count=len(c.vectors),fact_ids=sorted(c.used),
                                       direction=json.loads((OUT/'design_inputs.json').read_text(encoding='utf8'))['records'][i]['art_direction']))
            dump(folder/'measured_layout.json',models)
            dump(folder/'vector_geometry.json',[c.vectors for c in canvases])
            raster={f'bg{i}':OUT/'clean_backgrounds'/f'sample{i:02d}.png' for i in range(1,7)} if route=='A' else {}
            build_pptx(models,raster,[p['notes'] for p in lock['pages']],folder/'deck.pptx',title=f'六页视觉实测 {route}',font='Microsoft YaHei')
            native_vectors(folder/'deck.pptx',[c.vectors for c in canvases])
            rb=verify_pptx(folder/'deck.pptx',lock['pages'])
            assert all(r['pictures']==(1 if route=='A' else 0) for r in rb)
            web.emulate_media(media='print');web.pdf(path=str(folder/'browser.pdf'),width='1280px',height='720px',print_background=True)
            web.emulate_media(media='screen')
            results[route]=dict(build_seconds=round(time.perf_counter()-started,3),browser_checks=checks,native_checks=rb)
        browser.close()
    dump(OUT/'design_spec.json',dict(style=STYLE,pages=design,flow_correction='保留冻结输出的七条支持箭头；低分支无后续箭头；中分支连接临床特征选择再连接靶点列表。'))
    dump(OUT/'build_verification.json',dict(routes=results,total_build_seconds=round(time.perf_counter()-start,3)))
    print(json.dumps(results,ensure_ascii=False,indent=2))


def office():
    import win32com.client
    import pythoncom
    from PIL import Image, ImageChops, ImageStat
    pythoncom.CoInitialize()
    app=win32com.client.DispatchEx('PowerPoint.Application')
    timings={}
    try:
        for route in ('A','B','existing'):
            start=time.perf_counter()
            folder=OUT/route if route!='existing' else OUT/'frozen'/'powerpoint'
            folder.mkdir(parents=True,exist_ok=True)
            source=folder/'deck.pptx' if route!='existing' else OUT/'frozen'/'deck.pptx'
            pres=app.Presentations.Open(str(source),ReadOnly=True,WithWindow=False)
            try:
                for i,n in enumerate(SAMPLES if route=='existing' else range(1,7),1):
                    pres.Slides(n).Export(str(folder/f'slide{i:02d}.png'),'PNG',1280,720)
                if route!='existing':pres.SaveAs(str(folder/'deck.pdf'),32)
            finally:pres.Close()
            timings[route]=dict(render_seconds=round(time.perf_counter()-start,3))
            if route!='existing':
                drift=[]
                for i in range(1,7):
                    a=Image.open(folder/f'slide{i:02d}.png').convert('RGB')
                    b=Image.open(folder/f'browser{i:02d}.png').convert('RGB')
                    mean=sum(ImageStat.Stat(ImageChops.difference(a,b)).mean)/3/255
                    drift.append(dict(sample=i,pixel_difference=round(mean,4)))
                timings[route]['browser_office_difference']=drift
    finally:
        app.Quit();pythoncom.CoUninitialize()
    dump(OUT/'office_render.json',timings)
    print(json.dumps(timings,ensure_ascii=False,indent=2))


def deliver():
    import zipfile
    from collections import Counter
    from datetime import datetime, timezone
    from pptx import Presentation
    from pypdf import PdfReader
    lock=json.loads((OUT/'content_lock.json').read_text(encoding='utf8'))
    builds=json.loads((OUT/'build_verification.json').read_text(encoding='utf8'))
    office_result=json.loads((OUT/'office_render.json').read_text(encoding='utf8'))
    for name,digest in lock['source_hashes'].items():assert sha(OUT/'frozen'/name)==digest
    all_texts={}
    for route in ('A','B'):
        rb=verify_pptx(OUT/route/'deck.pptx',lock['pages'])
        assert all(p['pictures']==(1 if route=='A' else 0) for p in rb)
        assert len(PdfReader(OUT/route/'deck.pdf').pages)==6
        slides=Presentation(OUT/route/'deck.pptx').slides
        all_texts[route]=[]
        for slide in slides:
            texts=[]
            for sh in slide.shapes:
                if sh.has_text_frame and sh.text.strip():texts.append(canon(sh.text))
                if sh.has_table:texts.extend(canon(c.text) for row in sh.table.rows for c in row.cells)
            all_texts[route].append(Counter(texts))
    assert all_texts['A']==all_texts['B']
    receipts=[json.loads(p.read_text(encoding='utf8')) for p in sorted((OUT/'receipts').glob('*.json'))]
    full=[r for r in receipts if r['stage']=='full-design']
    clean=[r for r in receipts if r['stage']=='text-removal']
    old=json.loads((OUT/'generation_receipts.json').read_text(encoding='utf8'))['calls']
    assert len(full)==6 and len(clean)==7 and len(old)==5
    sizes={r:{name:dict(bytes=(OUT/r/name).stat().st_size,sha256=sha(OUT/r/name))
              for name in ('deck.pptx','deck.pdf','deck.html')} for r in ('A','B')}
    cost=dict(shared_design=dict(image_calls=6,tool_seconds=round(sum(r['seconds'] for r in full),3)),
              A_additional=dict(text_removal_calls=7,retries=1,tool_seconds=round(sum(r['seconds'] for r in clean),3)),
              B_additional=dict(image_calls=0,visual_revision_rounds=1),
              current_total=dict(image_calls=13,tool_seconds=round(sum(r['seconds'] for r in receipts),3)),
              abandoned_exploration=dict(image_calls=5,tool_seconds=round(sum(r['seconds'] for r in old),3)),
              billed_currency=None,manual_and_model_authoring_seconds=None,
              final_exports={r:dict(build_seconds=builds['routes'][r]['build_seconds'],**office_result[r],files=sizes[r]) for r in ('A','B')},
              export_passes=[dict(stage='first export',A_seconds=16.784,B_seconds=4.683),
                             dict(stage='one visual revision',A_seconds=15.317,B_seconds=3.829),
                             dict(stage='native border and background rule repair',
                                  A_seconds=builds['routes']['A']['build_seconds'],B_seconds=builds['routes']['B']['build_seconds'])],
              timing_scope='工具响应和脚本执行耗时；不是端到端制作时间、服务器容量或真实计费。')
    dump(OUT/'experiment_cost.json',cost)
    differences=[
        '封面保留左侧两行大标题与右侧肺部构图。A 保留细密分支、粒子与纸张纹理；B 重建轮廓和主要枝干，微血管与颗粒不复刻。',
        '指南页保留对等双栏、两层条款及引文。重建字体、年份比例和换行与生图稿不同；A 去字底图的短分隔线由原生遮罩修正。',
        '指标页恢复完整“任何一项”“可能性”限定，四项保持并列；2.5% 与“中国指南口径”同处独立说明带。B 图标为扁平路径，透明层次简化。',
        '选择路径页按冻结原页修正生图稿的错误关系：低分支无后续箭头；中分支经过临床特征选择再到靶点列表；高分支经过排除条件再到靶点列表。A 使用原生遮罩及容器修正背景，遮罩区域有轻微纹理差异。',
        '结果页恢复研究设计、人群、52周、ACQ-5、FEV₁、≥0 mL 等完整条件。原生 41.6% 使用安装字体，字重、宽度及蓝色纹理与生图稿不同。',
        '表格逐格恢复全部36条事实，包括剂量上标⁵与每行“中国”范围。两路线表体使用相同原生表格，字号和行高以完整内容为准。A 底图表格被原生表体覆盖；B 没有图片。'
    ]
    previous_review=OUT/'visual_review.json'
    preference=json.loads(previous_review.read_text(encoding='utf8')).get('customer_preference') if previous_review.exists() else None
    preference_note=(f'用户整体视觉偏好为{preference["preferred_route"]}，原话：“{preference["verbatim_feedback"]}”。该反馈按整套观感记录，不换算为逐页评分。'
                     if preference else '尚未记录用户审美偏好。')
    visual=dict(status='manual_visual_inspection_completed',renderer='Installed Microsoft PowerPoint',
                inspected=[dict(route=r,samples=list(range(1,7))) for r in ('A','B')],
                content_scope='冻结输出的保真检查；不代替来源医学审查或客户审美确认。',
                same_native_text_on_both_routes=True,facts_per_route=71,table_cells_checked=36,
                generated_design_text_is_authoritative=False,differences=differences,
                customer_preference=preference,workflow_confirmation_updated=False)
    dump(OUT/'visual_review.json',visual)
    spec=json.loads((OUT/'design_spec.json').read_text(encoding='utf8'))
    reads=[
        ('主标题','临床应用副标题','来源说明','右侧肺部构图与大标题形成视觉平衡'),
        ('同等指南名称','两条定义的横向对照','缩写与文献出处','双栏对等结构与蓝色限定词'),
        ('完整限定句','四项并列指标','独立的中国指南阈值与来源','蓝色阈值与等宽分栏'),
        ('目标人群','阈值分支与已支持路径','原页来源备注','只有有来源的连接关系'),
        ('结果及4组分标签','研究背景与定义','人群限定与来源','原生大数字41.6%'),
        ('表头与药物行名','按列读取规格、用法、获批和医保','价格、上标及来源','无删减的可编辑表格')]
    for p,read,diff in zip(spec['pages'],reads,differences):
        p['reading_order']=dict(first=read[0],next=read[1],reference=read[2],strong=read[3])
        p['reconstruction_difference']=diff
    dump(OUT/'design_spec.json',spec)
    rows='\n'.join(f'| {p["sample"]} / 原{p["original_page"]}页 | {p["kind"]} | {differences[p["sample"]-1]} |' for p in lock['pages'])
    cost_rows='\n'.join(f'| {r} | {builds["routes"][r]["build_seconds"]:.3f} 秒 | {office_result[r]["render_seconds"]:.3f} 秒 | {sizes[r]["deck.pptx"]["bytes"]/1024/1024:.2f} MiB | {sizes[r]["deck.pdf"]["bytes"]/1024/1024:.2f} MiB |' for r in ('A','B'))
    call_rows=[]
    for i in range(1,7):
        f=next(r for r in full if r['sample']==i);rs=[r for r in clean if r['sample']==i]
        call_rows.append(f'| {i} | 1 / {f["seconds"]:.3f} 秒 | {len(rs)} / {sum(r["seconds"] for r in rs):.3f} 秒 | {1 if len(rs)>1 else 0} |')
    report=f'''# 完整设计稿 → 原生 PPT：六页视觉实测

## 本次结果

已完成同一内容的两套6页PPTX、PowerPoint导出的PDF与逐页PNG，以及三栏对照页。**先由模型生成带文字完整设计稿，再根据冻结内容重建原生文字、表格和关系图**。

- A：完整设计稿 → 生图工具去字 → 原生文字与表格覆盖，保留位图插画和纹理。
- B：参考同一完整设计稿、底图与提示词 → HTML/CSS/SVG重建 → 全原生PPT，无图片对象。
- A和B使用相同文字区域、全部内容及相同原生表格；B图元由实验适配层转换为Office可编辑路径。
- 本次证明这条制作方法可以产出可编辑交付文件。**没有实现任意图片的一键自动拆解**：本次布局和图形结构由Codex逐页编写重建。六页也不足以证明无人审核的SaaS稳定性。

入口：[三栏对照网页](index.html)；[A PPTX](A/deck.pptx)、[A PDF](A/deck.pdf)；[B PPTX](B/deck.pptx)、[B PDF](B/deck.pdf)。网页还可查看完整生图设计稿和浏览器排版。

## 输入与内容保真

冻结实际`output/deck_full`的HTML、52页PPTX、渲染报告及来源备注，采用原页1、4、17、22、30、47。数据库版本未用于本次内容输入。

- 每条事实逐字核对，忽略仅用于排版的空白变化：每路线71条事实均通过。
- 表格36个事实单元格逐格回读一致；数字、比较符号、单位、上标和“中国”范围均保留。
- 原生文字内容在A与B完全一致，原页作者标题、来源短注、页码均保留。
- 来源备注逐页原样保存；原页待确认标记为0。没有修改医学审核、客户确认、页面审核或交付状态。
- 本次核对范围是冻结输出到重建稿的保真，未重新独立审查全部来源医学证据。
- 生图设计稿有错字、重复标题、符号及连接关系偏差，最终文字由冻结输入恢复。选择路径页修正了低阈值分支的错误箭头，保留原页7条支持关系。没有补充低分支的后续处理，也没有擅自补齐原页阈值边界。

## 各页差异

| 样本 | 内容 | 重建结果与差异 |
|---|---|---|
{rows}

## 原生对象与实际画面

| 项目 | A | B |
|---|---|---|
| 页面 | 6 | 6 |
| 图片对象 | 每页1张底图，共6张 | 0 |
| 文字 | 全部原生 | 全部原生 |
| 表格 | 原生7行×6列 | 原生7行×6列 |
| 医学连接线 | 原生，7条支持关系 | 原生，7条支持关系 |
| 装饰图形 | 底图中的图形不可分别编辑 | 路径、填色、轮廓均为原生对象 |

两套HTML均经浏览器测量，未发现文字溢出、越界、文字间重叠或表格与来源区重叠。安装的PowerPoint成功打开两套文件并导出各6页PDF、PNG；已逐页看过实际画面。修复了首轮密集表格的行高/换行问题与表格边框导出顺序问题。

浏览器与PowerPoint仍有字形边缘、行距、换行和表格边线差异，逐页像素差记录在`office_render.json`。该记录仅用于发现渲染差异，不作为审美评分。实际交付预览以`A/slideNN.png`与`B/slideNN.png`为准。

## 成本与耗时

| 成本阶段 | 实际调用 | 工具响应耗时 |
|---|---|---|
| 两路线共享的完整设计稿 | 6次生图 | {cost['shared_design']['tool_seconds']:.3f} 秒 |
| A额外去字 | 6次初次去字 + 1次修正 | {cost['A_additional']['tool_seconds']:.3f} 秒 |
| B额外生图 | 0次，复用6张设计参考 | 0秒 |
| 当前方向总计 | 13次 | {cost['current_total']['tool_seconds']:.3f} 秒 |
| 先前已放弃的无文字底图探索 | 5次，另计 | {cost['abandoned_exploration']['tool_seconds']:.3f} 秒 |

研究结果页第一次去字残留百分号，做了1次局部修正；保留首版与修正调用记录。完整设计稿每页生成1次，没有重生成。B完成1轮视觉修改，另修复原生导出边框与背景分隔线问题。

| 样本 | 完整稿调用/耗时 | 去字调用/耗时 | 去字重试 |
|---|---|---|---|
{chr(10).join(call_rows)}

最终一次脚本导出与实机渲染：

| 路线 | 浏览器测量＋原生导出 | PowerPoint PNG＋PDF | PPTX大小 | PDF大小 |
|---|---|---|---|---|
{cost_rows}

这些时间仅包括工具响应和脚本执行，**不包括完整的设计拆解、代码编写、模型推理和人工审阅时间**；不能直接当作端到端制作成本或服务器吞吐量。没有真实计费数据，因此不报告货币费用。图片生成由内置工具完成；本次没有对生产服务器的并发、内存峰值或队列延迟做压测。小文件的B路线仍有前置设计成本。

## 哪条路线值得继续

- **A适合封面、章节引导和需要细腻插画/纹理的页面。**当前实验中更接近生图参考的图像细节。其代价是额外去字调用、残留文字检查、较大文件，且底图中的图形不能分别编辑。
- **B适合长文本对照、指标、流程、结果和表格。**文字准确、关系可审查、全部可编辑、导出文件较小；目前能重建网格、字号层级、色块、线条和常规图形，复杂绘画质感保真度有限。
- **B的当前天花板在复杂图像细节与自动化拆解。**纯原生对象能表达大量矢量效果，但本次并未逐粒子、逐微血管复刻，也未实现通用图像分割/OCR到矢量结构的自动映射。直接把生图稿当准确文本或流程依据会带入错误。
- 值得保留“完整设计稿先确定审美 → 内容锁定 → 原生重建”的实验入口。根据本次用户偏好，后续样本优先优化{preference['preferred_route'] if preference else '待选路线'}，再验证不同内容密度下的重复稳定性。优化重点是文字重建、去字残留、图表准确性及调用成本。适合复用的构图可以沉淀为原生版式。
- **审美反馈：**{preference_note}

## 文件与复现

- `designs/`：6张带文字完整设计参考。
- `clean_backgrounds/`：6张最终去字底图；`sample05-v1.png`为残留百分号的首版。
- `prompts/`及`receipts/`：完整提示词、实际工具输出路径、耗时、重试记录。
- `content_lock.json`、`frozen/`：冻结输入、来源备注与校验值。
- `design_spec.json`：共同阅读顺序、区域、字号、重点和重建差异。
- `A/`与`B/`：PPTX、PowerPoint PDF和PNG、HTML、浏览器预览、测量布局及原生矢量几何。
- `build_verification.json`、`visual_review.json`、`office_render.json`、`experiment_cost.json`：检查与成本记录。
- `manifest.json`：文件大小与SHA-256。交付包不含被放弃的早期无文字底图。

独立入口：`python tools/visual_ab_test.py build` → `office` → `deliver`。使用已保存的设计和底图重建，不调用生图。首次取输入与准备提示词使用`prepare`、`prompts`；冻结文件变化时会拒绝覆盖。PowerPoint阶段需安装本机PowerPoint与pywin32。

仅新增实验工具与实验输出，复用现有浏览器测量和原生导出；未增加生产API、未改变现有模板/渲染行为、未更新工作流状态。这6页不直接推广到整套课件。
'''
    (OUT/'report.md').write_text(report,encoding='utf8')
    page_cards=[]
    for p,diff in zip(lock['pages'],differences):
        i=p['sample']
        columns=''.join(f'<figure><figcaption>{label}</figcaption><button class="zoom" data-src="{src}" data-label="样本{i} · {label}"><img src="{src}" alt="样本{i} {label}" data-route="{route}" data-sample="{i}" loading="lazy"/></button></figure>'
                        for route,label,src in [('existing','现有版本',f'frozen/powerpoint/slide{i:02d}.png'),('A','A · 保留生成图形',f'A/slide{i:02d}.png'),('B','B · 全部原生重建',f'B/slide{i:02d}.png')])
        page_cards.append(f'''<section id="sample{i}" class="sample"><header><span class="number">{i:02d}</span><div><h2>{html.escape(p['kind'])}</h2><p>原课件第{p['original_page']}页 · 点击画面放大</p></div><button class="reference" data-src="designs/sample{i:02d}.png" data-label="样本{i} · 完整生图设计参考（非准确内容依据）">查看完整设计稿</button></header><div class="columns">{columns}</div><p class="difference">{html.escape(diff)}</p><div class="feedback"><label>本页偏好 <select data-pref="{i}"><option value="">尚未评价</option><option value="A">更喜欢 A</option><option value="B">更喜欢 B</option><option value="existing">更喜欢现有版本</option><option value="tie">A / B 接近</option><option value="neither">A / B 均未达标</option></select></label><input data-note="{i}" aria-label="样本{i}评价理由" placeholder="评价理由：专业感、焦点、阅读顺序、密度或一致性"/></div></section>''')
    webcss='''*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f5f3ed;color:#151b24;font-family:"Microsoft YaHei",sans-serif}.wrap{max-width:1840px;margin:auto;padding:48px 40px}.eyebrow{font-size:14px;color:#2458d3;font-weight:700;letter-spacing:2px}h1{font-size:42px;line-height:1.25;margin:14px 0}h2{font-size:23px;margin:0 0 6px}.intro{max-width:900px;color:#57616f;line-height:1.85}.links,.toolbar{display:flex;flex-wrap:wrap;gap:12px;margin:22px 0}a,button,select{font:inherit}a{color:#2458d3;text-decoration:none}.links a{border:1px solid #bdc9df;padding:10px 16px;border-radius:4px;background:#fff}.toolbar{align-items:center;border-top:1px solid #d5d9e0;border-bottom:1px solid #d5d9e0;padding:17px 0;position:sticky;top:0;z-index:4;background:#f5f3edf2;backdrop-filter:blur(12px)}.toolbar nav{display:flex;gap:15px;margin-left:auto}.sample{margin:45px 0 70px;scroll-margin-top:90px}.sample header{display:flex;align-items:center;gap:16px;margin-bottom:20px}.number{font-size:28px;color:#2458d3;align-self:flex-start}.sample header p{margin:0;color:#7b8490;font-size:13px}.reference{margin-left:auto}.columns{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}figure{margin:0}figcaption{font-size:14px;font-weight:700;margin-bottom:10px}.zoom{border:0;padding:0;display:block;background:none;width:100%;cursor:zoom-in}.zoom img{display:block;width:100%;aspect-ratio:16/9;box-shadow:0 5px 18px #18233c12;border:1px solid #d8dce3}button:not(.zoom){padding:9px 13px;background:#fff;border:1px solid #c2ccde;border-radius:4px;cursor:pointer;color:#2458d3}.difference{font-size:13px;line-height:1.8;color:#647082;margin:16px 0}.feedback{display:flex;gap:20px;align-items:center;padding-top:12px;border-top:1px solid #d7dce4;font-size:13px}.feedback select{padding:8px;border:1px solid #ccd3df;background:white;margin-left:8px;border-radius:4px}.feedback input{flex:1;min-width:120px;padding:10px 12px;background:#fff;border:1px solid #d3d9e4;border-radius:4px;font:inherit}footer{font-size:13px;line-height:1.8;color:#647082;padding:20px 0}dialog{border:0;padding:0;background:#f5f3ed;width:min(96vw,1600px);max-width:1600px;max-height:95vh;box-shadow:0 12px 60px #0007}dialog::backdrop{background:#151b24bf}dialog header{display:flex;justify-content:space-between;align-items:center;padding:12px 20px}dialog img{display:block;width:100%;height:auto}#status{font-size:13px;color:#637388}@media(max-width:1000px){.columns{grid-template-columns:1fr}.wrap{padding:26px 18px}h1{font-size:31px}.toolbar{position:static}.feedback{flex-wrap:wrap}.feedback input{flex-basis:100%}.sample header{flex-wrap:wrap}.toolbar nav{margin:0}.reference{margin-left:0}}'''
    js='''const key='factppt-visual-ab-v1';let state={};try{state=JSON.parse(localStorage.getItem(key)||'{}')}catch(e){}const save=()=>{try{localStorage.setItem(key,JSON.stringify(state))}catch(e){}document.querySelector('#status').textContent='评价保存在当前浏览器，可导出留存'};document.querySelectorAll('[data-pref],[data-note]').forEach(el=>{const i=el.dataset.pref||el.dataset.note,k=el.dataset.pref?'preference':'note';el.value=state[i]?.[k]||'';el.addEventListener('change',()=>{state[i]??={};state[i][k]=el.value;save()})});const dialog=document.querySelector('dialog');const show=(src,label)=>{document.querySelector('#large').src=src;document.querySelector('#caption').textContent=label;dialog.showModal()};document.querySelectorAll('[data-src]').forEach(b=>b.addEventListener('click',()=>show(b.querySelector('img')?.src||b.dataset.src,b.dataset.label)));document.querySelector('#close').onclick=()=>dialog.close();dialog.onclick=e=>{if(e.target===dialog)dialog.close()};document.querySelector('#preview').onchange=e=>{document.querySelectorAll('.zoom img').forEach(img=>{const i=String(img.dataset.sample).padStart(2,'0'),r=img.dataset.route;img.src=e.target.value==='office'?(r==='existing'?`frozen/powerpoint/slide${i}.png`:`${r}/slide${i}.png`):(r==='existing'?`frozen/sample${i}.png`:`${r}/browser${i}.png`)})};document.querySelector('#export').onclick=()=>{const blob=new Blob([JSON.stringify({experiment:'visual-ab-test.v1',criteria:['专业感','第一眼焦点','阅读顺序','密度','整套一致性'],pages:state},null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='visual_ab_preferences.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};'''
    webpage=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>完整设计稿 → 原生 PPT · 六页视觉实测</title><style>{webcss}</style></head><body><main class="wrap"><div class="eyebrow">FACTPPT · VISUAL STUDY</div><h1>先确定设计，再重建原生 PPT</h1><p class="intro">同一组6页内容，比较现有版本、保留生成图形的 A、全部原生重建的 B。默认展示 PowerPoint 实际交付画面。完整生图设计稿单独查看，最终文字与医学连接关系以冻结内容为准。请按专业感、第一眼焦点、阅读顺序、密度和整套一致性给出偏好。</p><div class="links"><a href="A/deck.pptx" download>A · PPTX</a><a href="A/deck.pdf">A · PDF</a><a href="B/deck.pptx" download>B · PPTX</a><a href="B/deck.pdf">B · PDF</a><a href="report.md">实测报告</a><a href="visual_ab_delivery.zip" download>全部交付文件</a></div><div class="toolbar"><label>画面 <select id="preview"><option value="office">PowerPoint 交付画面</option><option value="browser">浏览器排版预览</option></select></label><button id="export">导出我的评价</button><span id="status">尚未选择偏好</span><nav>{''.join(f'<a href="#sample{i}">{i:02d}</a>' for i in range(1,7))}</nav></div>{''.join(page_cards)}<footer>A：文字、表格、连接线可编辑，底图保留位图。B：文字、表格、插画与装饰均为原生对象，无图片。<br/>六页样本用于选择方向，不直接推广到整套课件；尚未记录用户审美结论。</footer></main><dialog><header><span id="caption"></span><button id="close">关闭</button></header><img id="large" alt="放大预览"/></dialog><script>{js}</script></body></html>'''
    webpage=webpage.replace('尚未记录用户审美结论',html.escape(preference_note))
    (OUT/'index.html').write_text(webpage,encoding='utf8')
    files=[]
    for folder in ('A','B','designs','clean_backgrounds','prompts','receipts'):
        files.extend(p for p in (OUT/folder).glob('*') if p.is_file() and not p.name.startswith('~$'))
    files.extend(p for p in (OUT/'frozen'/'powerpoint').glob('*.png'))
    files.extend(p for p in (OUT/'frozen').glob('sample*.png'))
    files.extend(OUT/'frozen'/name for name in ('deck.html','deck.pptx','render_report.json'))
    files.extend(OUT/name for name in ('index.html','report.md','content_lock.json','design_inputs.json','design_spec.json','build_verification.json','visual_review.json','office_render.json','experiment_cost.json'))
    dump(OUT/'manifest.json',dict(created_utc=datetime.now(timezone.utc).isoformat(),source_hashes=lock['source_hashes'],
                                 files=[dict(path=str(p.relative_to(OUT)).replace('\\','/'),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(files)]))
    with zipfile.ZipFile(OUT/'visual_ab_delivery.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in files+[OUT/'manifest.json']:z.write(p,str(p.relative_to(OUT)))
    print(json.dumps(dict(delivery=str(OUT),files=len(files),facts_per_route=71,zip_bytes=(OUT/'visual_ab_delivery.zip').stat().st_size,cost=cost),ensure_ascii=False,indent=2))
