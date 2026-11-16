import pytest
import json
from pathlib import Path
from graphshield.enterprise import load_openapi_directory, infer_edges, merge_registries, write_inference_report
from graphshield.enterprise_runtime import _terms


def test_openapi_operations_use_exact_source(tmp_path):
    # This fixture is a parser regression test, NOT production benchmark data.
    spec = {
        "openapi":"3.0.0", "info":{"title":"Fixture API","version":"2026-11"},
        "paths":{
            "/accounts/{account_id}":{"get":{
                "operationId":"readAccount",
                "parameters":[{"name":"account_id","in":"path","required":True,"schema":{"type":"string"}}],
                "responses":{"200":{"content":{"application/json":{"schema":{
                    "type":"object","properties":{"customer_id":{"type":"string"}}
                }}}}}
            }},
            "/clients/{customer_id}":{"get":{
                "operationId":"getClient",
                "parameters":[{"name":"customer_id","in":"path","required":True,"schema":{"type":"string"}}],
                "responses":{"200":{"description":"OK"}}
            }}
        }
    }
    path=tmp_path/'fixture.json';path.write_text(json.dumps(spec),encoding='utf-8')
    r=load_openapi_directory(tmp_path)
    assert len(r['tools'])==2
    assert r['sources'][0]['sha256']
    assert r['tools'][0]['schema']['type']=='object'
    edges=infer_edges(r['tools'])
    assert any(e['field']=='customer_id' and e['verification']=='candidate_unreviewed' for e in edges)


def test_invalid_spec_fails_visibly(tmp_path):
    (tmp_path/'invalid.json').write_text('not json',encoding='utf-8')
    result=load_openapi_directory(tmp_path)
    assert result['errors'] and not result['tools']


def test_mcp_and_openapi_keep_provenance():
    mcp={'tools':[{'key':'a::one','source':'mcp tools/list'}],'servers':['a']}
    op={'tools':[{'key':'openapi_b::two','source':'converted OpenAPI'}],
        'sources':[{'file':'b.json'}],'errors':[]}
    merged=merge_registries(mcp,op)
    assert len(merged['tools'])==2
    assert merged['tools'][1]['source']=='converted OpenAPI'
    assert merged['servers']==['a','openapi:b.json']


def test_empty_field_matches_never_fabricate_edges():
    tools=[{'key':'x','name':'x','input_fields':[],'output_fields':[]},
           {'key':'y','name':'y','input_fields':[],'output_fields':[]}]
    assert infer_edges(tools)==[]


@pytest.mark.xfail(reason="Legacy pre-Refund-Desk workflow/UI contract retired in V8.2/V9",strict=True)
def test_api_openapi_and_dashboard_contract():
    from graphshield.api import app
    routes={r.path for r in app.routes}
    for path in ['/api/health','/api/registry/stats','/api/tools','/api/resolve',
                 '/api/diagnostics','/api/feedback','/api/agent/run','/api/benchmark/load',
                 '/api/ablation','/api/experiments/learning','/api/execute']:
        assert path in routes
    html=(Path(__file__).resolve().parents[1]/'static'/'index.html').read_text(encoding='utf-8')
    script=(Path(__file__).resolve().parents[1]/'static'/'control.js').read_text(encoding='utf-8')
    assert '/api/resolve' in script and 'Simulate provider outage' in html.lower().replace('simulate provider outage','Simulate provider outage')


def test_financial_adapter_uses_real_files_and_rejects_traversal(tmp_path, monkeypatch):
    # Synthetic XHTML is a unit-test fixture only; never production/benchmark data.
    import types
    import sys
    import importlib.util
    mod=types.ModuleType('mcp'); mod.__path__=[]
    srv=types.ModuleType('mcp.server');srv.__path__=[]
    fm=types.ModuleType('mcp.server.fastmcp')
    class FakeMCP:
        def __init__(self,*a,**k):pass
        def tool(self):return lambda fn:fn
    fm.FastMCP=FakeMCP
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules,'mcp',mod)
        mp.setitem(sys.modules,'mcp.server',srv)
        mp.setitem(sys.modules,'mcp.server.fastmcp',fm)
        mp.setenv('REPORTING_DOCUMENTS_DIR',str(tmp_path))
        spec=importlib.util.spec_from_file_location('financial_test',str(Path(__file__).resolve().parents[1]/'graphshield'/'financial_mcp.py'))
        financial=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(financial)
        sample=tmp_path/'real-file.xhtml'
        sample.write_text('<html><head><title>Actual file test fixture</title></head><body>'
                          '<table><tr><th>Assets</th><td>100</td></tr></table>'
                          '<ix:nonFraction name="uk:Assets" contextRef="FY26">100</ix:nonFraction>'
                          '</body></html>',encoding='utf-8')
        assert financial.list_reporting_documents()['count']==1
        assert financial.inspect_filing_metadata('real-file.xhtml')['inline_xbrl_fact_count']==1
        assert financial.extract_financial_tables('real-file.xhtml')['tables'][0]['rows'][0]==['Assets','100']
        assert financial.audit_filing_structure('real-file.xhtml')['finding_count']==0
        import pytest
        with pytest.raises(ValueError): financial.document_path('../outside.xml')


def test_financial_readonly_argument_validation():
    import pytest
    from graphshield.demo_features import validate_readonly_args
    tool={'name':'extract_inline_xbrl_facts','server':'financial_reporting',
          'schema':{'type':'object','required':['filename']}}
    assert validate_readonly_args(tool,{'filename':'Filing_2026.xhtml'})=={'filename':'Filing_2026.xhtml'}
    with pytest.raises(ValueError):validate_readonly_args(tool,{'filename':'../secret.xhtml'})
    with pytest.raises(ValueError):validate_readonly_args(tool,{'filename':'C:\\outside.xhtml'})
    with pytest.raises(ValueError):validate_readonly_args(tool,{'filename':'file.xhtml','other':'bad'})
    with pytest.raises(ValueError):validate_readonly_args({'name':'edit_file','server':'filesystem_primary'}, {'filename':'bad.xhtml'})
