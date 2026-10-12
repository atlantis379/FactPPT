"""Verified local academic samples; incomplete assets remain preview-only."""
import json
from app.fact57098 import ROOT, require, sha

LIBRARY=ROOT/'output'/'academic_templates'
STYLES=[('journal','医学期刊风','355E78','F6F4EF','151B24'),('defense','科研答辩风','173653','FFFFFF','152A42'),('teaching','本科教学风','355A42','F8F6EE','183A29'),('mono','黑白论文风','262626','FFFFFF','151515'),('burgundy','人文社科风','713B40','F8F4EC','44252A'),('teal','循证研究风','386F70','FFFFFF','17373C'),('indigo','工程技术风','475A82','FFFFFF','223455'),('sand','自然科学风','63704A','F8F6EC','333B26'),('plum','跨学科风','6B485F','FFFFFF','392B39'),('steel','临床会议风','466D88','FFFFFF','1E3444')]
STYLE_GUIDANCE={
 'journal':('资料密集、重视来源与限定条件的医学课程。','克制、清晰、低饱和蓝灰',['教学课件','临床汇报']),
 'defense':('研究背景、方法、结果及结论的答辩或汇报。','深蓝、正式、层级鲜明',['论文答辩','学术研讨']),
 'teaching':('本科课堂、概念讲解及分步骤学习。','暖白与深绿，阅读节奏舒缓',['教学课件']),
 'mono':('偏文字、公式与严谨论述的学术内容。','黑白、中性、便于打印',['论文答辩','学术研讨']),
 'burgundy':('人文社科论述、历史脉络及案例分析。','暖白与酒红，沉稳',['教学课件','学术研讨']),
 'teal':('证据综述、研究比较及结果汇报。','青灰、简洁、强调对照',['临床汇报','学术研讨']),
 'indigo':('技术方案、系统结构及工程研究。','靛蓝、清晰网格',['论文答辩','学术研讨']),
 'sand':('自然科学教学、分类及过程讲解。','沙色与橄榄绿，柔和',['教学课件','学术研讨']),
 'plum':('跨学科研究、多个视角或主题的组织。','灰紫、平衡、简洁',['论文答辩','学术研讨']),
 'steel':('临床会议、病例讨论及专业交流。','钢蓝、紧凑、正式',['临床汇报'])}

def entry(tid):
    for i,s in enumerate(STYLES,1):
        if tid==f'{i:02d}_{s[0]}':return s,LIBRARY/tid
    require(False,'模板不存在',404)

def list_templates():
    result=[]
    for i,s in enumerate(STYLES,1):
        tid=f'{i:02d}_{s[0]}';folder=LIBRARY/tid;ready=False
        try:
            n=json.loads((folder/'native_report.json').read_text(encoding='utf8'))
            o=json.loads((folder/'office_report.json').read_text(encoding='utf8'))
            q=json.loads((folder/'qa.json').read_text(encoding='utf8'))
            ready=n['image_objects']==0 and n['pages']==6 and q['text_free'] and q.get('final_inspected',False) and len(o['editability'])==6 and all((c['contour_edit'] and c['fill_recolor'] and c['group_move']) or (c.get('artwork_absent') and c.get('native_table_edit')) for c in o['editability']) and all((folder/f).is_file() for f in ('deck.pptx','deck.pdf','template.potx'))
        except (OSError,KeyError,ValueError,TypeError):pass
        suitable,tone,uses=STYLE_GUIDANCE[s[0]]
        result.append(dict(id=tid,name=s[1],ready=ready,suitable_for=suitable,tone=tone,uses=uses,
            palette=dict(accent='#'+s[2],background='#'+s[3],ink='#'+s[4]),
            status='原生样例已核对' if ready else '设计稿已生成，重建检查中' if (folder/'design.png').exists() else '待制作',
            design_url=f'/api/deck/templates/{tid}/design.png' if (folder/'design.png').exists() else None,
            preview_url=f'/api/deck/templates/{tid}/native_preview.png' if (folder/'native_preview.png').exists() else None,
            download_url=f'/api/deck/templates/{tid}/deck.pptx' if ready else None))
    return result

def asset(tid,filename):
    _,folder=entry(tid)
    require(filename in {'design.png','native_preview.png','deck.pptx','deck.pdf','template.potx',*[f'slide{i:02d}.png' for i in range(1,7)]},'不支持的模板文件',404)
    if filename in ('deck.pptx','deck.pdf','template.potx'):
        require(next(t for t in list_templates() if t['id']==tid)['ready'],'模板尚未完成核对',409)
    path=folder/filename;require(path.is_file(),'模板文件尚未生成',404)
    return path

def snapshot(store,w,tid):
    if tid is None:return None
    s,folder=entry(tid)
    require(next(t for t in list_templates() if t['id']==tid)['ready'],'模板尚未完成原生重建与画面检查',409)
    content=(folder/'design.png').read_bytes();native=(folder/'deck.pptx').read_bytes()
    return dict(id=tid,name=s[1],palette=dict(accent=s[2],background=s[3],ink=s[4]),
                design_sha256=sha(content),design_path=store.immutable(w['id'],'templates',content,'.png'),
                native_sha256=sha(native),native_path=store.immutable(w['id'],'templates',native,'.pptx'),
                usage='按六页设计参考和原生样例编排重建，不直接继承母版。')
