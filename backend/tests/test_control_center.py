import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from graphshield.api import app

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.xfail(reason="Legacy pre-Refund-Desk workflow/UI contract retired in V8.2/V9",strict=True)
def test_control_center_v5_ui_and_assets():
    html=(ROOT/'static'/'index.html').read_text(encoding='utf-8')
    js=(ROOT/'static'/'control.js').read_text(encoding='utf-8')
    for target in ('playground','learning','benchmark','graph','about'):
        assert f'id="{target}"' in html
    for feature in ('data-mode="preload"','data-mode="embedding"','data-mode="graphshield"',
                    'executionLog','learningChart','loadResults','graphCanvas','modeComparison'):
        assert feature in html
    for endpoint in ('/api/resolve','/api/execute','/api/experiments/learning',
                     '/api/benchmark/load','/api/ablation','/api/diagnostics'):
        assert endpoint in js
    assert 'estimated schema' in html.lower()
    with TestClient(app) as client:
        assert client.get('/').status_code == 200
        response=client.get('/static/control.js')
        assert response.status_code == 200
        assert 'function renderPlan' in response.text

def test_ablation_uses_each_task_description_not_unknown_variable(monkeypatch):
    import graphshield.enterprise_runtime as ent
    fake_tools=[{'name':'alpha','description':'read document'}, {'name':'beta','description':'send message'}]
    monkeypatch.setattr(ent,'load_registry',lambda:{'tools':fake_tools})
    monkeypatch.setattr(ent,'load_tasks',lambda:{'tasks':[{'key':'read','description':'read document','chain':['alpha']}]})
    monkeypatch.setattr(ent,'_graph_route',lambda key:{'tools':[{'name':'alpha'}]})
    report=ent.flat_ablation()
    assert report['graph_mean_recall']==1.0
    assert report['flat_mean_recall']==1.0
