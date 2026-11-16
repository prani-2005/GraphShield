import pytest
from graphshield.real_mcp import stable_id, build_workflows, RECIPES
from graphshield.graph import InMemoryGraph
from graphshield.resolver import Resolver
from graphshield.dataset import build_dataset
from concurrent.futures import ThreadPoolExecutor


def test_hashed_ids_stable_and_separate():
    assert stable_id('tool','a::x')==stable_id('tool','a::x')
    assert stable_id('tool','a::x') != stable_id('tool','b::x')
    assert stable_id('tool','a::x') > 1_000_000_000


@pytest.mark.xfail(reason="Legacy pre-Refund-Desk workflow/UI contract retired in V8.2/V9",strict=True)
def test_workflows_require_real_discovery(tmp_path,monkeypatch):
    from graphshield import real_mcp
    monkeypatch.setattr(real_mcp,'WORKFLOWS',tmp_path/'real_workflows.json')
    # No invented record for unavailable tools.
    task_names={name for _,_,chain in RECIPES for name in chain}
    records=[{'name':name,'server':'test_instance','schema':{'type':'object'},'description':'source'} for name in task_names if name in {'git_status','git_log'}]
    result=build_workflows({'tools':records})
    assert any(t['key']=='inspect_repo' for t in result['tasks'])
    assert all(set(t['chain'])<= {'git_status','git_log'} for t in result['tasks'])
    assert result['excluded']


def test_per_request_queries_remain_constant_under_load():
    g=InMemoryGraph();g.seed(build_dataset(48,12))
    resolver=Resolver(g)
    task='accounts_000'
    serial=resolver.resolve(task)['graph_queries']
    with ThreadPoolExecutor(max_workers=12) as pool:
        counts=list(pool.map(lambda _:resolver.resolve(task)['graph_queries'],range(60)))
    assert serial>0
    assert all(q==serial for q in counts)
