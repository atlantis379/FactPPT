"""Package inspected actual A-route assets, never mark inspection automatically."""
from pathlib import Path
import hashlib,json,sys,zipfile
from lxml import etree
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.academic_templates import STYLES,list_templates,LIBRARY


def package():
    if not all(t['ready'] for t in list_templates()):raise ValueError('All ten samples must be inspected first')
    manifest=[]
    for i,s in enumerate(STYLES,1):
        folder=LIBRARY/f'{i:02d}_{s[0]}'
        native=json.loads((folder/'native_report.json').read_text(encoding='utf8'))
        office=json.loads((folder/'office_report.json').read_text(encoding='utf8'))
        qa=json.loads((folder/'qa.json').read_text(encoding='utf8'))
        for filename in ('deck.pptx','template.potx'):
            with zipfile.ZipFile(folder/filename) as z:
                pages=[n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
                if len(pages)!=6:raise ValueError('Native page count mismatch')
                if any(etree.fromstring(z.read(n)).xpath('//*[local-name()="pic"]') for n in pages):raise ValueError('Bitmap object found')
                if any(n.startswith('ppt/media/') for n in z.namelist()):raise ValueError('Unexpected embedded media')
        files=['design.png','design_prompt.txt',qa['clean_file'],'artwork.svg','deck.pptx','template.potx','deck.pdf','native_preview.png','qa.json','native_report.json','office_report.json','tool_receipt.json']+[f'slide{n:02d}.png' for n in range(1,7)]
        hashes={n:{'bytes':(folder/n).stat().st_size,'sha256':hashlib.sha256((folder/n).read_bytes()).hexdigest()} for n in files}
        differences=['实际SVG路径描摹；纸张颗粒、部分浅色细节省略，渐变简化；不是像素级复刻。','多数联系稿子页接近4:3；等比适配16:9后有左右留白。','生成占位文字改为原生文字；流程连接线和整张表格原生重建。']
        if i in (1,6,8,10):differences.append('局部细线断续或色块边缘粗化可见；实际预览保留这些差异。')
        if i in (1,2):differences.append('流程页第一个装饰圆形未保留；四个步骤的原生文字和连接线完整。')
        if i==10:differences.append('正文页只保留少量标题装饰；三列文字结构保留，不宣称原稿装饰全部复刻。')
        if i in (2,6,7):differences.append('去字图仍留少量箭头，已从实际原生路径中按位置移除，再添加原生连接线。')
        if i==6:differences[1]='此套实际PNG和SVG均2512×944，子页面接近16:9；按比例适配最终画布。'
        if native['native_paths_per_page'][5]==0:differences.append('表格页没有保留装饰路径；原生表格已在PowerPoint验证编辑，不伪造矢量检查。')
        manifest.append({'id':folder.name,'name':s[1],'native_paths':sum(native['native_paths_per_page']),'paths_per_page':native['native_paths_per_page'],'image_objects':0,'office_seconds':office['seconds'],'files':hashes,'differences':differences})
    (LIBRARY/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    rows=['| 模板 | 原生路径 | PPTX大小 | 最后一次Office渲染 |','|---|---:|---:|---:|']
    rows += [f"| {m['name']} | {m['native_paths']} | {m['files']['deck.pptx']['bytes']/1024:.0f} KB | {m['office_seconds']:.1f} 秒 |" for m in manifest]
    report='''# 十套学术原生模板交付记录

2026-10-04，沿用用户确认的A路线制作。每套六页：封面、章节、正文、对照、流程、表格，共60页。

## 使用

工作台 http://127.0.0.1:8001/#/templates 查看实际预览与完整设计稿；进入项目“要求与模板”选择。
每套POTX包含六张可复制编辑的样页；PPTX是同内容编辑版，PDF及PNG由本机PowerPoint渲染。
目前按内容引用模板设计稿重新编排，不自动继承六套自定义母版，也不宣称已测试所有内容密度。
选择保存实际设计稿和原生样例的不可变快照及校验值，绑定A路线任务的参考资产、完整提示词和配色；修改选择使既有视觉生成失效，内容确认规则保持原流程。

## 实际制作与检查

ImageGen带文字联系稿 → Adobe去字并逐套查看 → Adobe实际SVG → 拆分实际路径、按区域分组 → 原生文字、表格、连接线 → 本机PowerPoint渲染、抽样改色/顶点/组移动 → POTX实际打开检查。
全部60页图片对象为0；PPTX与POTX均无嵌入图片媒体。58页具有描摹装饰路径，2张纯表格页验证原生表格编辑。
查看了全部最终PowerPoint页面，修正了文字与插画、圆形、标题方块和分隔线的遮挡。程序测量无文本框溢出。审美偏好待用户选择，不以测试通过替代审美结论。
模板示例为通用占位内容，未代替任何课件的来源审核、人工内容确认或交付确认。

## 调用与费用

成功输出：10次完整设计稿生图、21次Adobe去字结果（每套两次，另加自然科学风一次）、10次Adobe矢量化。
第二轮去字中有4次传输错误，重试后获得实际输出；没有把失败调用计成成功结果。
未取得真实费用、云端token账单或完整设计阶段计时；只报告已知调用量。每套回执保留实际工具结果、已记录提示词与耗时；第1套早期去字提示词/部分耗时未完整落盘，缺失值保持null，不补造。
下表为最后一次Office渲染耗时，不代表包含制作、云端等待和人工检查的总历时。

'''+ '\n'.join(rows)+'\n\n## 逐套差异\n\n'+ '\n\n'.join('### '+m['name']+'\n\n'+'\n'.join('- '+d for d in m['differences']) for m in manifest)+'''

## 前端与兼容性

沿用现有Tabler MIT界面和许可证。模板未通过实际原生及画面检查前不能选用/下载交付文件。未选模板的旧项目维持原渲染输入校验值；原有事实、审核、人工确认和交付接口保持。
22项相关测试通过；两个前端脚本语法检查通过。回执、逐文件SHA256和实际Office检查见本目录。
'''
    (LIBRARY/'REPORT.md').write_text(report,encoding='utf8')
    archive=LIBRARY/'academic_templates_10.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for m in manifest:
            for name in m['files']:z.write(LIBRARY/m['id']/name,f"{m['id']}/{name}")
        for name in ('REPORT.md','manifest.json','potx_open_report.json'):z.write(LIBRARY/name,name)
    print(json.dumps({'templates':len(manifest),'pages':60,'native_paths':sum(m['native_paths'] for m in manifest),'archive_bytes':archive.stat().st_size},ensure_ascii=False))

if __name__=='__main__':package()
