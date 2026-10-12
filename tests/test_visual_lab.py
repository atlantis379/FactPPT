import copy
import pytest
from factdeck.visual_lab import compile_prompt,validate_graph,validate_design

def fixture():
    text='Under C, not B; value < 7.';cut=9
    source={'number':2,'id':'p2','lock':{'model':{'texts':[{'paras':[[{'text':text}]]}]}}}
    graph={'pages':[{'page':{'number':2,'id':'p2'},'block_texts':[{'block_index':0,'text':text}],
        'text_fragments':[{'id':'context','block_index':0,'start':0,'end':cut,'quote':text[:cut],'qualifier_for':['value']},
                          {'id':'value','block_index':0,'start':cut,'end':len(text),'quote':text[cut:]}],
        'regions':[{'id':'scope','label_fragment_ids':['context'],'body_fragment_ids':[],'source_block_indices':[0]},
                   {'id':'condition','label_fragment_ids':[],'body_fragment_ids':['value'],'source_block_indices':[0],'parent_region_id':'scope'}],
        'relations':[{'id':'relation','type':'context','from':['scope'],'to':['condition'],'source_block_indices':[0],
                      'source_mappings':[{'block_index':0,'fragment_ids':['context','value']}],'support_quote':text}],
        'forbidden_implications':['Do not remove the contextual requirement']} ]}
    design={'page':2,'strategy':'textbook','regions':[{'id':'scope','x':0,'y':0,'w':1280,'h':720,'render_instruction':'Top condition boundary'},
        {'id':'condition','x':100,'y':100,'w':500,'h':300,'render_instruction':'Internal condition node'}],
        'relations':[{'id':'relation','render_instruction':'Enclosure, no causal arrow'}]}
    return source,graph,design

def test_complete_source_bindings_and_single_render_occurrence():
    source,graph,design=fixture()
    assert validate_graph([source],graph)['medical_approval'] is False
    prompt=compile_prompt(graph['pages'][0],design,{'paper':'#F8F6EE'})
    assert prompt.count('not B; value < 7.')==1

@pytest.mark.parametrize('mutation',['operator','gap','duplicate','source','scope_cycle'])
def test_source_and_scope_corruption_rejected(mutation):
    source,graph,_=fixture();p=graph['pages'][0]
    if mutation=='operator':p['text_fragments'][1]['quote']=p['text_fragments'][1]['quote'].replace('<','>=')
    elif mutation=='gap':p['text_fragments'][1]['start']+=1
    elif mutation=='duplicate':p['regions'][0]['body_fragment_ids']=['value']
    elif mutation=='source':p['relations'][0]['support_quote']='Unsupported statement'
    else:p['regions'][0]['parent_region_id']='condition'
    with pytest.raises(ValueError):validate_graph([source],graph)

@pytest.mark.parametrize('mutation',['outside_scope','nonfinite','replacement_text','missing_relation'])
def test_design_cannot_escape_scope_or_replace_content(mutation):
    _,graph,design=fixture()
    if mutation=='outside_scope':design['regions'][0].update(x=200,w=1080)
    elif mutation=='nonfinite':design['regions'][1]['x']=float('nan')
    elif mutation=='replacement_text':design['regions'][1]['text']='rewritten content'
    else:design['relations']=[]
    with pytest.raises(ValueError):validate_design(graph['pages'][0],design)

def test_prompt_instructions_cannot_repeat_exact_render_content():
    _,graph,design=fixture();design['regions'][1]['render_instruction']='Render not B; value < 7. again'
    with pytest.raises(ValueError,match='repeats'):compile_prompt(graph['pages'][0],design,{})


def test_source_prohibition_uses_region_reference_without_duplicate_render_text():
    _,graph,design=fixture()
    graph['pages'][0]['forbidden_implications']=['Never detach not B; value < 7. from its scope']
    prompt=compile_prompt(graph['pages'][0],design,{})
    assert prompt.count('not B; value < 7.')==1
    assert 'Never detach [region condition] from its scope' in prompt


def test_locked_table_cells_cannot_be_omitted_or_changed():
    from factdeck.visual_lab import block_texts,block_bindings
    source,graph,_=fixture()
    source['lock']['model']['tables']=[{'rows':[{'cells':[{'paras':[[{'text':'< 7 mg'}]]},{'paras':[[{'text':'not eligible'}]]}]}]}]
    assert block_texts(source)[1:]==['< 7 mg','not eligible']
    assert block_bindings(source)[-1]=={'kind':'table_cell','table':0,'row':0,'column':1}
    with pytest.raises(ValueError,match='Source text changed'):validate_graph([source],graph)


def test_alias_preserves_source_and_rejects_unique_content_loss():
    source,graph,design=fixture();p=graph['pages'][0];text=p['block_texts'][0]['text']
    duplicate=text.replace(' ', '\n')
    source['lock']['model']['texts'].append({'paras':[[{'text':duplicate}]]})
    p['block_texts'].append({'block_index':1,'text':duplicate})
    p['text_fragments'].append({'id':'duplicate','block_index':1,'start':0,'end':len(duplicate),'quote':duplicate})
    p['regions'].append({'id':'alias','label_fragment_ids':[],'body_fragment_ids':['duplicate'],'source_block_indices':[1]})
    design['regions'].append({'id':'alias','x':0,'y':0,'w':10,'h':10,'render_instruction':'Nonrendering source alias'})
    p['render_aliases']=[{'block_index':1,'covered_by_block_indices':[0]}]
    assert validate_graph([source],graph)['structural_valid']
    assert 'nonrendering_alias_regions' in compile_prompt(p,design,{})
    p['render_aliases'][0]['covered_by_block_indices']=[1]
    with pytest.raises(ValueError,match='Invalid duplicate alias'):validate_graph([source],graph)
    p['render_aliases'][0]['covered_by_block_indices']=[0]
    p['block_texts'][1]['text']+=' extra'
    source['lock']['model']['texts'][1]['paras'][0][0]['text']+=' extra'
    with pytest.raises(ValueError,match='unique source content'):validate_graph([source],graph)
