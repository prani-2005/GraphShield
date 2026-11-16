"""V9 evidence adapter: no fabricated results and strict fidelity to experiment metrics."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from graphshield.api import app
from graphshield import v9_evidence


def test_v9_static_assets_and_real_routes():
    root=Path(__file__).resolve().parents[1]
    html=(root/'static/index.html').read_text()
    assert 'Benchmarks' in html and 'Diagnostics' in html
    assert 'labs.js' in html and 'V9 · HYDRADB HACKATHON' in html
    assert 'read_document' not in html and 'edit_document' not in html
    routes={r.path for r in app.routes}
    assert {'/api/experiments/learning','/api/benchmarks/dataflow','/api/demo/reset','/api/diagnostics'}.issubset(routes)


def test_missing_report_is_explicit(monkeypatch,tmp_path):
    monkeypatch.setattr(v9_evidence,'HELD_OUT',tmp_path/'does-not-exist.json')
    assert v9_evidence.learning_evidence() is None
    with TestClient(app) as client:
        r=client.get('/api/experiments/learning')
    assert r.status_code==404
    assert 'refund_experiment' in str(r.json())


def test_saved_report_uses_only_observed_fields(monkeypatch,tmp_path):
    report=tmp_path/'held.json'
    report.write_text(json.dumps({'experiment':'controlled test','seeds':[7,17,29],
        'train_cases':100,'held_out_cases':50,'provider_failure_assumptions':{'orders_primary':.43},
        'summary':[{'iteration':1,'system':'graphshield_learned',
                    'first_try_success':{'mean':.52,'min':.5,'max':.55},
                    'injected_failures':{'mean':.1,'min':.08,'max':.12},
                    'estimated_tokens':{'mean':250,'min':245,'max':255}}],
        'limitations':['simulated']}))
    monkeypatch.setattr(v9_evidence,'HELD_OUT',report)
    r=v9_evidence.learning_evidence(); row=r['summary'][0]
    assert row['task_success']['mean']==.52
    assert row['tokens_per_task']['mean']==250
    assert row['round_trips_per_task'] is None
    assert row['p95_latency_ms'] is None
    assert r['tokens_basis']=='estimated'


def test_reset_refuses_mutation():
    with TestClient(app) as client:
        r=client.post('/api/demo/reset',json={})
    assert r.status_code==501
