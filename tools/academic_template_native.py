"""Rebuild reviewed Adobe contact-sheet paths as editable six-page PPT samples.

Requires actual design.png, reviewed clean.png and Adobe artwork.svg. No raster
or SVG is embedded in slides. Generic sample text is not medical content.
"""
from pathlib import Path
import argparse, copy, json, sys, zipfile
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from factdeck.native_vectors import trace_svg, add_native_vectors
from factdeck.visual_render import office_render
from pptx import Presentation
from pptx.util import Emu, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN

def px(n): return Emu(round(n * 9525))
def rgb(s): return RGBColor.from_string(s.lstrip('#'))

def build(folder, accent, background, ink, row_body=False):
    receipt=json.loads((folder/'qa.json').read_text(encoding='utf8'))
    if not receipt.get('clean_inspected') or not receipt.get('text_free'):
        raise ValueError('Actual clean artwork must be viewed and text-free first')
    # Contact sheet panels are measured from the actual source, not invented.
    boxes=receipt['panels']
    data=(folder/'artwork.svg').read_bytes();root=etree.fromstring(data)
    vw=float(root.get('width').removesuffix('px'));vh=float(root.get('height').removesuffix('px'))
    components=[dict(name=f'panel{i+1}',x=b[0]*vw,y=b[1]*vh,w=b[2]*vw,h=b[3]*vh) for i,b in enumerate(boxes)]
    vectors,report=trace_svg(data,(),preserve_order=True,target_size=(vw,vh))
    # Adobe may put disconnected artwork from several panels in one SVG path.
    # Partition its subpaths without replacing their geometry or painting order.
    distributed=[[] for _ in boxes]
    for original in vectors:
        subpaths=[]
        for command in original['commands']:
            if command[0]=='M':subpaths.append([])
            if subpaths:subpaths[-1].append(command)
        grouped={}
        for commands in subpaths:
            coords=[c[1:] for c in commands if len(c)>1]
            if not coords:continue
            xs=[n for c in coords for n in c[::2]];ys=[n for c in coords for n in c[1::2]]
            for i,b in enumerate(boxes):
                x,y,w,h=b[0]*vw,b[1]*vh,b[2]*vw,b[3]*vh
                if min(xs)>=x-3 and max(xs)<=x+w+3 and min(ys)>=y-3 and max(ys)<=y+h+3:
                    if max(xs)-min(xs)>w*.96 and max(ys)-min(ys)>h*.96:break
                    if i==5 and min(ys)>y+h*.15 and max(ys)<y+h*.94:break
                    # Explicitly remove the three residual generated arrows from
                    # reviewed cleanup; native connectors carry the sample relation.
                    lanes={'02_defense':(848,1206,850,884,1152),'06_teal':(848,1205,570,594,770),'07_indigo':(708,1345,703,725,1152)}
                    if i==4 and folder.name in lanes:
                        lx,rx,ty,by,hh=lanes[folder.name]
                        if min(xs)>=lx/2048*vw and max(xs)<=rx/2048*vw and min(ys)>=ty/hh*vh and max(ys)<=by/hh*vh:break
                    cx=((min(xs)+max(xs))/2-x)/w;cy=((min(ys)+max(ys))/2-y)/h
                    component='整页装饰'
                    if i==2 and cy>.15:component=f'正文区域{min(2,int(cy*3 if row_body else cx*3))+1}'
                    elif i==3 and cy>.15:component=f'对照区域{1 if cx<.5 else 2}'
                    elif i==4 and cy>.15:component=f'流程区域{min(3,int(cx*4))+1}'
                    grouped.setdefault((i,component),[]).extend(commands);break
        for (i,component),commands in grouped.items():
            v=copy.deepcopy(original);v['commands']=commands;v['group']=component;distributed[i].append(v)
    pages=[]
    for i,b in enumerate(boxes):
        x,y,w,h=b[0]*vw,b[1]*vh,b[2]*vw,b[3]*vh
        scale=min(1280/w,720/h); dx=(1280-w*scale)/2;dy=(720-h*scale)/2
        page=[]
        for v in distributed[i]:
            v=copy.deepcopy(v)
            coords=[c[1:] for c in v['commands'] if len(c)>1]
            xs=[n for c in coords for n in c[::2]];ys=[n for c in coords for n in c[1::2]]
            # Reject paths crossing a panel boundary (contact-sheet gutters/frame).
            if min(xs)<x-2 or max(xs)>x+w+2 or min(ys)<y-2 or max(ys)>y+h+2: continue
            if max(xs)-min(xs)>w*.96 and max(ys)-min(ys)>h*.96: continue
            if i==5 and min(ys)>y+h*.15 and max(ys)<y+h*.94: continue
            for c in v['commands']:
                for k in range(1,len(c),2):c[k]=(c[k]-x)*scale+dx;c[k+1]=(c[k+1]-y)*scale+dy
            v['width']*=scale;v['name']='可编辑描摹路径'
            page.append(v)
        if not page and i!=5: raise ValueError(f'Page {i+1} has no usable native artwork')
        pages.append(page)
    prs=Presentation();prs.slide_width=px(1280);prs.slide_height=px(720)
    font='Microsoft YaHei'
    locked=[]
    def text(sl,t,x,y,w,h,size=26,color=ink,bold=False,align=None):
        sh=sl.shapes.add_textbox(px(x),px(y),px(w),px(h));sh.name='占位文字：'+t[:20]
        tf=sh.text_frame;tf.word_wrap=True
        tf.margin_left=tf.margin_right=0;tf.margin_top=tf.margin_bottom=0
        for n,line in enumerate(t.split('\n')):
            p=tf.paragraphs[0] if n==0 else tf.add_paragraph();p.text=line
            p.font.name=font;p.font.size=Pt(size*.75);p.font.bold=bold;p.font.color.rgb=rgb(color)
            p.space_after=Pt(4)
            if align is not None:p.alignment=align
        locked.append(t);return sh
    titles=['学术研究汇报','研究背景','研究问题','方案对照','研究流程','结果与局限']
    for i,title in enumerate(titles):
        sl=prs.slides.add_slide(prs.slide_layouts[6]);sl.background.fill.solid();sl.background.fill.fore_color.rgb=rgb(background)
        sl.notes_slide.notes_text_frame.text='学术模板占位样页。请以已核对资料替换文字、数据与关系；模板不提供医学事实。'+title
        if i==0:
            text(sl,title,205,170,750,100,58,bold=True)
            text(sl,'研究主题与报告信息',208,284,650,60,32)
            text(sl,'汇报人：请填写姓名\n所在单位：请填写单位\n报告日期：请填写日期',210,466,600,130,23)
        elif i==1:
            text(sl,'01',205,170,220,150,100,accent)
            text(sl,title,435,204,600,80,54,bold=True)
            text(sl,'问题的提出与研究意义',438,305,590,65,28)
        else:
            text(sl,title,245 if folder.name=='07_indigo' else 205,48,650,70,40,bold=True)
            if i==2:
                labels=['核心问题','研究方法','主要观察']
                for j,label in enumerate(labels):
                    if row_body:
                        text(sl,label,395,175+j*175,600,50,28,bold=True)
                        text(sl,'请填写核对后的内容，保留必要的范围和限定。',395,228+j*175,600,82,24)
                    else:
                        x=90+j*420 if folder.name=='06_teal' else 220+j*290
                        text(sl,label,x,340,260,48,28,bold=True,align=PP_ALIGN.CENTER)
                        text(sl,'请填写核对后的内容。\n保留研究范围与限定。\n此处为学术占位文字。',x,470 if folder.name=='06_teal' else 425,250,175,24)
            elif i==3:
                for j in range(2):
                    x=215+j*450
                    text(sl,f'方案{"一" if j==0 else "二"}',90+j*640 if folder.name=='06_teal' else x+20,174,460 if folder.name=='06_teal' else 375,50,30,ink if folder.name=='04_mono' else 'FFFFFF',True,PP_ALIGN.CENTER)
                    compact=folder.name=='05_burgundy'
                    value='主要思路\n请填写研究思路。\n实施要点\n请填写实施条件。\n解释边界\n请填写局限与不确定性。' if compact else '主要思路\n请填写研究思路。\n\n实施要点\n请填写实施条件。\n\n解释边界\n请填写局限与不确定性。'
                    if folder.name=='07_indigo':
                        for yy,label,body in [(310,'主要思路','请填写研究思路。'),(430,'实施要点','请填写实施条件。'),(570,'解释边界','请填写局限与不确定性。')]:
                            text(sl,label,330+j*450,yy,280,36,21,bold=True)
                            text(sl,body,330+j*450,yy+36,280,50,21)
                    else:
                        text(sl,value,230+j*640 if folder.name=='06_teal' else 330+j*450,300 if compact else 365,350 if folder.name=='06_teal' else 280,225 if compact else 280,21)
            elif i==4:
                for j,label in enumerate(['问题提出','研究设计','资料分析','结果讨论']):
                    x=90+j*305 if folder.name=='06_teal' else 205+j*230
                    text(sl,label,x,350,205,52,27,bold=True,align=PP_ALIGN.CENTER)
                    text(sl,'填写步骤内容。\n关系须有依据。',x+10,570 if folder.name=='02_defense' else 440,190,120,22)
                    if j<3:
                        line=sl.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,px(x+195),px(310),px(x+(305 if folder.name=='06_teal' else 230)),px(310))
                        line.line.color.rgb=rgb(accent);line.line.width=Pt(1.5)
                        from pptx.oxml.xmlchemy import OxmlElement
                        end=OxmlElement('a:tailEnd');end.set('type','triangle');line._element.spPr.find('{http://schemas.openxmlformats.org/drawingml/2006/main}ln').append(end)
            else:
                table=sl.shapes.add_table(5,3,px(205),px(176),px(880),px(410)).table
                for col,width in zip(table.columns,[195,350,335]):col.width=px(width)
                rows=[['观察项目','结果摘要','解释边界']]+[[f'项目{n}','请填写经核对的结果。','请填写适用范围与局限。'] for n in '一二三四']
                for r,row in enumerate(rows):
                    for c,value in enumerate(row):
                        cell=table.cell(r,c);cell.text=value;locked.append(value)
                        cell.fill.solid();cell.fill.fore_color.rgb=rgb(accent if r==0 else background)
                        cell.margin_left=px(15);cell.margin_right=px(12);cell.margin_top=px(12)
                        for p in cell.text_frame.paragraphs:
                            p.font.name=font;p.font.size=Pt(17);p.font.bold=r==0;p.font.color.rgb=rgb('FFFFFF' if r==0 else ink)
                text(sl,'来源与备注：请填写核对后的资料。',205,635,880,48,21)
    prs.save(folder/'deck.pptx');add_native_vectors(folder/'deck.pptx',pages)
    check=Presentation(folder/'deck.pptx')
    def leaves(shapes):
        for s in shapes:
            if s.shape_type==6:yield from leaves(s.shapes)
            else:yield s
    pics=sum(s.shape_type==13 for sl in check.slides for s in leaves(sl.shapes))
    if pics:raise ValueError('Generated template cannot contain image objects')
    actual=[]
    for sl in check.slides:
        for s in leaves(sl.shapes):
            if s.has_text_frame and s.text:actual.append(s.text)
            if s.has_table:actual.extend(c.text for row in s.table.rows for c in row.cells)
    if actual!=locked: raise ValueError('Native sample text round-trip mismatch')
    ratio_note='联系稿部分子页面接近4:3；描摹轮廓等比适配16:9画布并增加必要留白。' if any(abs(b[2]*vw/(b[3]*vh)/(16/9)-1)>.02 for b in boxes) else '联系稿子页面接近16:9；实际轮廓等比适配至最终画布。'
    report.update(image_objects=pics,pages=6,native_paths_per_page=[len(p) for p in pages],
                  differences=report['differences']+[ratio_note,'占位文字与原生表格按可读容量重排，不保留生成文字笔画。'])
    (folder/'native_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    office=office_render(folder,6,template_export=True)
    (folder/'office_report.json').write_text(json.dumps(office,ensure_ascii=False,indent=2),encoding='utf8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--accent',default='355E78');p.add_argument('--background',default='F6F4EF');p.add_argument('--ink',default='151B24');p.add_argument('--row-body',action='store_true');a=p.parse_args()
    print(json.dumps(build(a.folder,a.accent,a.background,a.ink,a.row_body),ensure_ascii=False))
