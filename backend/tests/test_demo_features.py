import pytest
from pathlib import Path
from graphshield.demo_features import eligible_readonly_tools, READONLY_ALLOWLIST
from graphshield import demo_features


def test_readonly_allowlist_cannot_enable_writes():
    registry={'tools': [
        {'key': 'x::list_allowed_directories','name': 'list_allowed_directories'},
        {'key': 'x::edit_file','name': 'edit_file'},
        {'key': 'x::read_graph','name': 'read_graph'},
        {'key': 'x::write_file','name': 'write_file'},
    ]}
    selected=eligible_readonly_tools(registry)
    assert [t['name'] for t in selected] == ['list_allowed_directories','read_graph']
    assert 'edit_file' not in READONLY_ALLOWLIST


def test_learning_experiment_uses_database_and_restores(monkeypatch, tmp_path):
    recorded=[]
    class FakeHydra:
        def __init__(self): self.failed=False
        def resolve(self,key):
            return {'tools':[{'id':2 if self.failed else 1,'name':'edit_file',
                              'tool_key':'fs_standby::edit_file' if self.failed else 'fs_primary::edit_file'}],
                    'rejected':[{'name':'edit_file','server':'fs_standby','reason':'standby / alternate'}],
                    'graph_queries':5}
        def fail(self,tid): recorded.append(('fail',tid));self.failed=True
        def restore(self,tid): recorded.append(('restore',tid));self.failed=False
        def close(self): recorded.append(('close',0))
    monkeypatch.setattr(demo_features,'RealHydra',FakeHydra)
    monkeypatch.setattr(demo_features,'LEARNING_REPORT',tmp_path/'learning.json')
    result=demo_features.run_learning('edit_document',5)
    assert [x['graphshield_failed_dispatches'] for x in result['series']]==[1,0,0,0,0]
    assert result['static_failures_total']==5
    assert result['graphshield_failures_total']==1
    assert recorded==[('fail',1),('restore',1),('close',0)]
    assert (tmp_path/'learning.json').exists()


@pytest.mark.xfail(reason="Legacy pre-Refund-Desk workflow/UI contract retired in V8.2/V9",strict=True)
def test_dashboard_has_functional_sections():
    content=(Path(__file__).resolve().parents[1]/'static'/'index.html').read_text(encoding='utf-8')
    for name in ('playground','graph','benchmark','learning','about'):
        assert 'id="'+name+'"' in content
    script=(Path(__file__).resolve().parents[1]/'static'/'control.js').read_text(encoding='utf-8')
    assert '/api/experiments/learning' in script and '/api/resolve' in script


def test_independent_paraphrases_are_not_fabricated_tool_records():
    from graphshield.demo_features import match_task
    data={'tasks':[
        {'key':'edit_document','description':'Read a file and edit its contents'},
        {'key':'inspect_repo','description':'Check Git repository status and history'},
    ]}
    prediction=match_task('Check git repository history',data)
    assert prediction['task_key']=='inspect_repo'
    assert prediction['method']=='lexical-intent-match'
