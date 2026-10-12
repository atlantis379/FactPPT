"""Independent, resumable prompt trials; does not change production approvals."""
from __future__ import annotations
import argparse,copy,hashlib,json,secrets,shutil,sqlite3,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from factdeck.visual_lab import STRATEGIES,block_texts,compile_prompt,digest,validate_design,validate_graph
LAB=ROOT/'output/visual_prompt_lab'

def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+secrets.token_hex(4)+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8');temp.replace(path)
def file_sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def db():
    LAB.mkdir(parents=True,exist_ok=True)
    d=sqlite3.connect(LAB/'experiment.sqlite3',timeout=30);d.row_factory=sqlite3.Row
    d.executescript('''CREATE TABLE IF NOT EXISTS trials(id TEXT PRIMARY KEY, phase TEXT,page INTEGER,strategy TEXT,repeat INTEGER,status TEXT,worker TEXT,token TEXT,expires REAL,design_path TEXT,prompt_path TEXT,prompt_sha256 TEXT,result_path TEXT);
    CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY,trial_id TEXT,status TEXT,at REAL,receipt_path TEXT);
    CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,event TEXT,at REAL,details TEXT);''')
    return d
def event(d,name,data):d.execute('INSERT INTO events(event,at,details) VALUES(?,?,?)',(name,time.time(),json.dumps(data,ensure_ascii=False)))
def init():
    with sqlite3.connect(ROOT/'data/deckflow/workflow.sqlite3') as d:
        w=json.loads(d.execute('SELECT state FROM workflows WHERE id=?',('deck_5a725e2d98854c81abd3',)).fetchone()[0])
    old=read(ROOT/'output/visual_model_ab_explanatory/common_input.json');g=w['generation']
    if g['input_sha256']!=old['generation_input_sha256']:raise ValueError('Content version changed; rebind explicitly')
    pages=[{'number':n,'id':g['pages'][n-1]['id'],'lock':copy.deepcopy(g['pages'][n-1]['lock'])} for n in (2,5,9,1,20,21)]
    snapshot={'schema_version':'visual-prompt-lab.v1','workflow_id':w['id'],'generation_input_sha256':g['input_sha256'],'template':w['visual_template'],'palette':g['palette'],'font':g['font'],'pages':pages,'strategies':STRATEGIES,
              'phases':{'screen':9,'stability':4,'extension':3,'max_quality_revisions':3,'max_transport_retries':2,'design_call_limit':19},'model':'gpt-6-luna','image_backend':'builtin image_gen','status':'EXPERIMENT_NOT_APPROVED'}
    target=LAB/'common_input.json'
    if target.exists() and read(target)!=snapshot:raise ValueError('Existing frozen input differs')
    write(target,snapshot)
    graph=read(LAB/'semantic_graph.json');selected=[p for p in pages if p['number'] in (2,5,9)]
    check=validate_graph(selected,graph);review=read(LAB/'graph_review.json')
    if review.get('graph_sha256')!=digest(graph) or review.get('status')!='SUPPORTED_WITH_NO_BLOCKERS':raise ValueError('Independent graph review is not current')
    write(LAB/'graph_validation.json',check)
    shutil.copy2(ROOT/'data/deckflow'/w['visual_template']['design_path'],LAB/'template_reference.png')
    with db() as d:
        for strategy in STRATEGIES:
            for n in (2,5,9):
                tid=f'screen_{strategy}_{n:02d}_r1'
                d.execute('INSERT OR IGNORE INTO trials(id,phase,page,strategy,repeat,status) VALUES(?,?,?,?,?,?)',(tid,'screen',n,strategy,1,'PLANNED'))
        event(d,'INIT',{'source_sha256':digest(snapshot),'graph_sha256':digest(graph)})
    return {'trials':9,'source_sha256':digest(snapshot),'graph':check}
def prepare(trial_id,design_path):
    common=read(LAB/'common_input.json');design=read(design_path)
    with db() as d:
        row=d.execute('SELECT * FROM trials WHERE id=?',(trial_id,)).fetchone()
        if not row or row['status'] not in ('PLANNED','PREPARED'):raise ValueError('Trial is not preparable')
        extension=row['phase']=='extension'
        graph=read(LAB/('extension_graph.json' if extension else 'semantic_graph.json'))
        accepted=read(LAB/('extension_graph_validation.json' if extension else 'graph_validation.json'))
        review=read(LAB/('extension_graph_review.json' if extension else 'graph_review.json'))
        if accepted['graph_sha256']!=digest(graph) or review.get('graph_sha256')!=digest(graph) or review.get('status')!='SUPPORTED_WITH_NO_BLOCKERS':raise ValueError('Graph or independent review changed; revalidate before generation')
        numbers={p['page']['number'] for p in graph['pages']}
        validate_graph([p for p in common['pages'] if p['number'] in numbers],graph)
        p=next(p for p in graph['pages'] if p['page']['number']==row['page'])
        if design['strategy']!=row['strategy']:raise ValueError('Strategy differs')
        validate_design(p,design);prompt=compile_prompt(p,design,common['palette'])
        folder=LAB/'trials'/trial_id;folder.mkdir(parents=True,exist_ok=True)
        saved=folder/'design.json';write(saved,design)
        write(folder/'source_binding.json',{'common_sha256':file_sha(LAB/'common_input.json'),'graph_sha256':digest(graph),'review_sha256':digest(review),'graph_file':'extension_graph.json' if extension else 'semantic_graph.json'})
        prompt_path=folder/'prompt.txt';prompt_path.write_text(prompt,encoding='utf8')
        d.execute('UPDATE trials SET status=?,design_path=?,prompt_path=?,prompt_sha256=? WHERE id=?',('PREPARED',str(saved.relative_to(ROOT)),str(prompt_path.relative_to(ROOT)),file_sha(prompt_path),trial_id))
        event(d,'PREPARE',{'trial':trial_id,'design_sha256':digest(design)})
    return {'trial':trial_id,'status':'PREPARED','prompt_path':str(prompt_path),'prompt_sha256':file_sha(prompt_path)}
def prepare_repeat(trial_id):
    with db() as d:
        row=d.execute('SELECT * FROM trials WHERE id=?',(trial_id,)).fetchone()
        if not row or row['phase']!='stability':raise ValueError('Only a stability trial can repeat a screen input')
        baseline=f"screen_{row['strategy']}_{row['page']:02d}_r1"
        old=d.execute('SELECT * FROM trials WHERE id=?',(baseline,)).fetchone()
        if not old or old['status']!='GENERATED_INSPECTED':raise ValueError('Actual baseline is missing')
    result=prepare(trial_id,ROOT/old['design_path'])
    if result['prompt_sha256']!=old['prompt_sha256']:raise ValueError('Compiled repeat input differs from baseline')
    write(LAB/'trials'/trial_id/'repeat_binding.json',{'baseline_trial':baseline,'baseline_prompt_sha256':old['prompt_sha256'],'repeat_prompt_sha256':result['prompt_sha256'],
        'template_sha256':file_sha(LAB/'template_reference.png'),'reference_clarification_sha256':file_sha(LAB/(row['strategy']+'_reference_clarification.json')),'purpose':'same declared content, prompt and reference; no approval'})
    return result
def claim(trial_id,worker,out):
    with db() as d:
        d.execute('BEGIN IMMEDIATE');row=d.execute('SELECT * FROM trials WHERE id=?',(trial_id,)).fetchone()
        if not row or row['status']!='PREPARED':raise ValueError('Trial not ready or already claimed; recover existing call, do not restart')
        token=secrets.token_hex(24)
        d.execute('UPDATE trials SET status=?,worker=?,token=?,expires=? WHERE id=?',('CLAIMED',worker,token,time.time()+1800,trial_id))
        task={**dict(row),'worker':worker,'lease_token':token,'id':trial_id,'experiment':'visual_prompt_lab'}
        write(out,task);event(d,'CLAIM',{'trial':trial_id,'worker':worker})
    return {'claimed':True,'trial':trial_id,'task_path':str(Path(out).resolve())}
def begin(task_path,call_id):
    task=read(task_path)
    with db() as d:
        d.execute('BEGIN IMMEDIATE');row=d.execute('SELECT * FROM trials WHERE id=?',(task['id'],)).fetchone()
        if not row or row['token']!=task['lease_token'] or row['status']!='CLAIMED':raise ValueError('Invalid claim or call already started')
        n=d.execute("SELECT COUNT(*) FROM calls WHERE status!='FAILED_TRANSPORT'").fetchone()[0]
        limit=19
        selection_path=LAB/'textbook_selection.json'
        if selection_path.is_file():
            selection=read(selection_path)
            if selection.get('source_sha256')==file_sha(LAB/'common_input.json') and selection.get('extra_design_calls')==3 and task['id'] in selection.get('authorized_trial_ids',[]):
                limit+=3
        if n>=limit:raise ValueError('Experiment design call budget exhausted')
        if file_sha(ROOT/row['prompt_path'])!=row['prompt_sha256']:raise ValueError('Prompt changed after preparation')
        d.execute('INSERT INTO calls VALUES(?,?,?,?,?)',(call_id,task['id'],'ISSUED',time.time(),None));d.execute('UPDATE trials SET status=? WHERE id=?',('CALL_ISSUED',task['id']))
        event(d,'CALL_ISSUED',{'trial':task['id'],'call_id':call_id})
    return {'issued_recorded':True,'call_id':call_id}
def release(task_path,reason):
    """Release only a claim whose provider call has not been issued."""
    task=read(task_path)
    with db() as d:
        d.execute('BEGIN IMMEDIATE');row=d.execute('SELECT * FROM trials WHERE id=?',(task['id'],)).fetchone()
        if not row or row['token']!=task['lease_token'] or row['status']!='CLAIMED':raise ValueError('Only a pre-call claim may be released')
        if d.execute("SELECT 1 FROM calls WHERE trial_id=? AND status='ISSUED'",(task['id'],)).fetchone():raise ValueError('Outstanding call must be recovered first')
        d.execute('UPDATE trials SET status=?,worker=NULL,token=NULL,expires=NULL WHERE id=?',('PREPARED',task['id']))
        event(d,'RELEASE_PRE_CALL',{'trial':task['id'],'reason':reason})
    return {'released':True,'trial':task['id'],'status':'PREPARED'}
def fail(task_path,call_id,error):
    """Record a returned terminal transport error; never infer it from a wait timeout."""
    task=read(task_path)
    with db() as d:
        d.execute('BEGIN IMMEDIATE');row=d.execute('SELECT * FROM trials WHERE id=?',(task['id'],)).fetchone()
        call=d.execute('SELECT * FROM calls WHERE id=?',(call_id,)).fetchone()
        if not row or row['token']!=task['lease_token'] or row['status']!='CALL_ISSUED' or not call or call['trial_id']!=task['id']:raise ValueError('Claim/call binding differs')
        saved=LAB/'trials'/task['id']/(call_id+'.failure.json')
        if saved.exists():raise ValueError('Failure record already exists')
        write(saved,{'call_id':call_id,'trial_id':task['id'],'error':error,'output':None,'timing_status':'UNKNOWN','at':time.time()})
        d.execute('UPDATE calls SET status=?,receipt_path=? WHERE id=?',('FAILED_TRANSPORT',str(saved.relative_to(ROOT)),call_id))
        failures=d.execute("SELECT COUNT(*) FROM calls WHERE status='FAILED_TRANSPORT'").fetchone()[0]
        state='PREPARED' if failures<=2 else 'TRANSPORT_BLOCKED'
        d.execute('UPDATE trials SET status=?,token=NULL,expires=NULL WHERE id=?',(state,task['id']))
        event(d,'FAIL_TRANSPORT',{'trial':task['id'],'call_id':call_id,'retry_available':failures<=2})
    return {'recorded':True,'trial':task['id'],'status':state}
def finish(task_path,call_id,image_path,receipt_path):
    task=read(task_path);receipt=read(receipt_path)
    with db() as d:
        d.execute('BEGIN IMMEDIATE');row=d.execute('SELECT * FROM trials WHERE id=?',(task['id'],)).fetchone()
        call=d.execute('SELECT * FROM calls WHERE id=?',(call_id,)).fetchone()
        if not row or row['token']!=task['lease_token'] or row['status']!='CALL_ISSUED' or not call or call['trial_id']!=task['id']:raise ValueError('Claim/call binding differs')
        if receipt.get('prompt_sha256')!=row['prompt_sha256'] or receipt.get('prompt')!=(ROOT/row['prompt_path']).read_text(encoding='utf8'):raise ValueError('Receipt must preserve exact actual prompt')
        if receipt.get('tool')!='builtin image_gen' or not receipt.get('output_identifier'):raise ValueError('Actual tool output provenance missing')
        if receipt.get('inspected') is not True or not receipt.get('inspection'):raise ValueError('Actual output inspection missing')
        if receipt.get('asset_sha256')!=file_sha(image_path):raise ValueError('Actual image hash differs')
        from PIL import Image
        with Image.open(image_path) as im:
            if im.format!='PNG' or abs(im.width/im.height-16/9)>0.03:raise ValueError('Expected actual 16:9 PNG')
        folder=LAB/'trials'/task['id'];target=folder/(call_id+'.png');saved=folder/(call_id+'.receipt.json')
        if target.exists() or saved.exists():raise ValueError('Immutable output already exists')
        shutil.copy2(image_path,target);write(saved,receipt)
        d.execute('UPDATE trials SET status=?,result_path=?,expires=NULL WHERE id=?',('GENERATED_INSPECTED',str(target.relative_to(ROOT)),task['id']))
        d.execute('UPDATE calls SET status=?,receipt_path=? WHERE id=?',('RETURNED_INSPECTED',str(saved.relative_to(ROOT)),call_id));event(d,'COMPLETE',{'trial':task['id'],'asset_sha256':file_sha(target)})
    return {'accepted':True,'trial':task['id'],'asset_sha256':file_sha(target),'approved':False}
def status():
    with db() as d:
        rows=[dict(r) for r in d.execute('SELECT * FROM trials ORDER BY phase,strategy,page,repeat')]
        calls=[dict(r) for r in d.execute('SELECT * FROM calls ORDER BY at')]
    for r in rows:r.pop('token',None)
    return {'trials':rows,'calls':calls,'human_confirmation':False}
def add_phase(kind,strategies,basis,pages=None):
    if kind not in ('stability','extension','quality'):raise ValueError('Invalid phase')
    if len(strategies)!=len(set(strategies)) or any(s not in STRATEGIES for s in strategies):raise ValueError('Invalid strategies')
    if not Path(basis).is_file():raise ValueError('Actual selection/review basis required')
    review=read(basis)
    if review.get('source_sha256')!=file_sha(LAB/'common_input.json'):raise ValueError('Review is not bound to current frozen input')
    with db() as d:
        d.execute('BEGIN IMMEDIATE')
        reviewed=review.get('trials',[])
        if not reviewed:raise ValueError('Actual image review evidence required')
        for t in reviewed:
            row=d.execute('SELECT result_path FROM trials WHERE id=?',(t.get('id',t.get('trial_id')),)).fetchone()
            if not row or not row['result_path'] or t.get('asset_sha256',t.get('image_sha256'))!=file_sha(ROOT/row['result_path']) or t.get('viewed') is not True:raise ValueError('Review image binding/view evidence differs')
        if kind=='stability' and len(strategies)!=2:raise ValueError('Stability requires two candidates')
        if kind=='extension' and len(strategies)!=1:raise ValueError('Extension requires one provisional candidate')
        if kind=='extension':
            if review.get('provisional_winner')!=strategies[0]:raise ValueError('Extension requires an independently qualified provisional winner')
            candidate=[t for t in reviewed if t.get('strategy')==strategies[0]]
            if not candidate or any(t.get('hard_error_ids') for t in candidate):raise ValueError('Candidate still has accuracy blockers')
        if pages is not None and kind!='quality':raise ValueError('Custom pages are only allowed for targeted quality revisions')
        if kind=='quality':
            if len(strategies)>3:raise ValueError('Quality revision budget exhausted')
            numbers=tuple(pages or (5,));repeat=2
            if len(numbers)!=len(set(numbers)) or any(n not in (2,5,9) for n in numbers):raise ValueError('Quality pages must be unique frozen screen samples')
        else:numbers=(2,9) if kind=='stability' else (1,20,21);repeat=2 if kind=='stability' else 1
        for strategy in strategies:
            for n in numbers:
                tid=f'{kind}_{strategy}_{n:02d}_r{repeat}'
                d.execute('INSERT OR IGNORE INTO trials(id,phase,page,strategy,repeat,status) VALUES(?,?,?,?,?,?)',(tid,kind,n,strategy,repeat,'PLANNED'))
        if d.execute("SELECT COUNT(*) FROM trials WHERE phase='quality'").fetchone()[0]>3:raise ValueError('Quality revision budget exhausted')
        event(d,'ADD_PHASE',{'phase':kind,'strategies':strategies,'basis_sha256':file_sha(basis),'provisional':True,'approved':False})
    return {'phase':kind,'trials':len(numbers)*len(strategies),'approved':False}
def main():
    parser=argparse.ArgumentParser();subs=parser.add_subparsers(dest='cmd',required=True)
    subs.add_parser('init');subs.add_parser('status')
    p=subs.add_parser('prepare');p.add_argument('trial');p.add_argument('--design',required=True,type=Path)
    p=subs.add_parser('repeat');p.add_argument('trial')
    p=subs.add_parser('claim');p.add_argument('trial');p.add_argument('--worker',required=True);p.add_argument('--out',required=True,type=Path)
    p=subs.add_parser('phase');p.add_argument('kind',choices=('stability','extension','quality'));p.add_argument('--strategies',required=True,nargs='+');p.add_argument('--basis',required=True,type=Path);p.add_argument('--pages',type=int,nargs='+')
    p=subs.add_parser('release');p.add_argument('--task',required=True,type=Path);p.add_argument('--reason',required=True)
    for cmd in ('begin','finish','fail'):
        p=subs.add_parser(cmd);p.add_argument('--task',required=True,type=Path);p.add_argument('--call-id',required=True)
        if cmd=='finish':p.add_argument('--image',required=True,type=Path);p.add_argument('--receipt',required=True,type=Path)
        if cmd=='fail':p.add_argument('--error',required=True)
    a=parser.parse_args()
    if a.cmd=='init':result=init()
    elif a.cmd=='status':result=status()
    elif a.cmd=='prepare':result=prepare(a.trial,a.design)
    elif a.cmd=='repeat':result=prepare_repeat(a.trial)
    elif a.cmd=='claim':result=claim(a.trial,a.worker,a.out)
    elif a.cmd=='phase':result=add_phase(a.kind,a.strategies,a.basis,a.pages)
    elif a.cmd=='begin':result=begin(a.task,a.call_id)
    elif a.cmd=='release':result=release(a.task,a.reason)
    elif a.cmd=='fail':result=fail(a.task,a.call_id,a.error)
    else:result=finish(a.task,a.call_id,a.image,a.receipt)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
