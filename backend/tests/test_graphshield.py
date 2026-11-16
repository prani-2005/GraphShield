from graphshield.graph import InMemoryGraph
from graphshield.resolver import Resolver,ResolutionError
from graphshield.runtime import execute
from graphshield.benchmark import bench
from graphshield.dataset import build_dataset

def test_deps_and_budget():
    g=InMemoryGraph();g.seed();r=Resolver(g).resolve('accounts_000')
    assert r['skill_path'].index('pdf_parse') < r['skill_path'].index('xhtml_export')
    assert len(r['tools'])==7
    assert r['graph_queries']>0
    try:Resolver(g).resolve('accounts_000',token_budget=100)
    except ResolutionError:pass
    else:assert False

def test_recover_and_share():
    g=InMemoryGraph();g.seed();first=Resolver(g).resolve('tagging_001')
    dead=first['tools'][-1]['id']
    run=execute(g,'tagging_001',inject_failure=dead)
    assert run['retries']==1
    agent_b=Resolver(g).resolve('tagging_001')
    assert dead not in [t['id'] for t in agent_b['tools']]

def test_learning_reweight():
    g=InMemoryGraph();g.seed()
    a=Resolver(g).resolve('invoice_004')
    chosen=a['tools'][-1]
    secondary=next(t for t in g.data['tools'] if t['capability']==chosen['capability'] and t['id']!=chosen['id'])
    # Learned weights are observable in graph, not proof of improved task success.
    g.reward([secondary['id']]*10)
    b=Resolver(g).resolve('invoice_004')
    assert b['tools'][-1]['id']==secondary['id']

def test_benchmark():
    d=build_dataset(48,12);g=InMemoryGraph();g.seed(d)
    result=bench(g,d)
    assert result['summary']['graphshield_recall_mean']==1
    assert result['summary']['graphshield_tokens_est_mean']<result['summary']['preload_tokens_est_mean']
