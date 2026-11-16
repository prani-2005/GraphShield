from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel,Field
from .graph import make_graph
from .dataset import build_dataset
from .resolver import Resolver,ResolutionError
from .runtime import execute

@asynccontextmanager
async def lifespan(app):
    app.state.graph=make_graph()
    yield
    app.state.graph.close()

app=FastAPI(title='GraphShield',version='0.1.0',lifespan=lifespan)

class ResolveBody(BaseModel):
    task_key:str
    token_budget:int=Field(default=2400,ge=100,le=500000)
class FailureBody(BaseModel):
    tool_id:int
    error_kind:str='unavailable'
class SuccessBody(BaseModel):
    tool_ids:list[int]
class EntityBody(BaseModel):
    key:str
    value:str
    source:str='manual'
class ExecuteBody(BaseModel):
    task_key:str
    inject_failure:int|None=None

@app.get('/health')
def health():return {'status':'ok','backend':app.state.graph.backend}

@app.post('/seed')
def seed():
    try:return app.state.graph.seed(build_dataset())
    except Exception as e:raise HTTPException(503,detail=str(e))

@app.post('/resolve')
def resolve(body:ResolveBody):
    try:return Resolver(app.state.graph).resolve(body.task_key,body.token_budget)
    except ResolutionError as e:raise HTTPException(422,detail=str(e))
    except Exception as e:raise HTTPException(503,detail=str(e))

@app.post('/failure')
def failure(body:FailureBody):
    try:app.state.graph.mark_failure(body.tool_id,body.error_kind);return {'recorded':True,'tool_id':body.tool_id}
    except Exception as e:raise HTTPException(422,detail=str(e))

@app.post('/healthy/{tool_id}')
def healthy(tool_id:int):
    try:app.state.graph.mark_healthy(tool_id);return {'healthy':True,'tool_id':tool_id}
    except Exception as e:raise HTTPException(422,detail=str(e))

@app.post('/success')
def success(body:SuccessBody):
    try:app.state.graph.reward(body.tool_ids);return {'rewarded':body.tool_ids}
    except Exception as e:raise HTTPException(422,detail=str(e))

@app.post('/entities')
def entities(body:EntityBody):
    try:app.state.graph.resolve_entity(body.key,body.value,body.source);return {'stored':True}
    except Exception as e:raise HTTPException(422,detail=str(e))

@app.post('/execute')
def run(body:ExecuteBody):
    try:return execute(app.state.graph,body.task_key,body.inject_failure)
    except Exception as e:raise HTTPException(422,detail=str(e))

# Real MCP mode: kept separate from the legacy synthetic-only API endpoints.
# No tool invocation is exposed; all calls are context retrieval / failure simulation.
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from .real_mcp import RealHydra, load_registry, load_tasks, evaluate

class RealResolveBody(BaseModel):
    task_key: str
    entity_key: str | None = None
    token_budget: int = Field(default=12000, ge=100, le=200000)

app.mount('/static', StaticFiles(directory=Path(__file__).resolve().parent.parent / 'static'), name='static')

@app.get('/')
def dashboard():
    return FileResponse(Path(__file__).resolve().parent.parent / 'static' / 'index.html')

@app.get('/real/status')
def real_status():
    from .real_mcp import SNAPSHOT, WORKFLOWS
    if not SNAPSHOT.exists():
        return {'ready':False,'detail':'Run python -m graphshield.real_mcp discover first'}
    registry=load_registry()
    return {'ready':WORKFLOWS.exists(), 'tools':len(registry['tools']),
            'servers':registry['servers'],'discovery_errors':registry['errors'],
            'source_commit':registry['source_git_commit']}

@app.get('/real/tasks')
def real_tasks():
    try:return load_tasks()
    except FileNotFoundError:raise HTTPException(409,detail='Run MCP discovery first')

@app.post('/real/seed')
def real_seed():
    db=RealHydra()
    try:return db.seed(load_registry(),load_tasks())
    except Exception as e:raise HTTPException(503,detail=str(e))
    finally:db.close()

@app.post('/real/resolve')
def real_resolve(body:RealResolveBody):
    db=RealHydra()
    try:return db.resolve(body.task_key,body.token_budget,body.entity_key)
    except ValueError as e:raise HTTPException(422,detail=str(e))
    except Exception as e:raise HTTPException(503,detail=str(e))
    finally:db.close()

@app.post('/real/fail')
def real_fail(body:FailureBody):
    db=RealHydra()
    try:return db.fail(body.tool_id)
    except ValueError as e:raise HTTPException(422,detail=str(e))
    except Exception as e:raise HTTPException(503,detail=str(e))
    finally:db.close()

@app.post('/real/restore/{tool_id}')
def real_restore(tool_id:int):
    db=RealHydra()
    try:return db.restore(tool_id)
    except Exception as e:raise HTTPException(503,detail=str(e))
    finally:db.close()

@app.get('/real/report')
def real_report():
    from .real_mcp import REPORT
    if not REPORT.exists():raise HTTPException(404,'Run real MCP benchmark first')
    return __import__('json').loads(REPORT.read_text(encoding='utf-8'))

class RealEntityBody(BaseModel):
    key: str
    value: str
    source: str = "reviewed"

@app.post('/real/entities')
def real_entity(body:RealEntityBody):
    db=RealHydra()
    try:return db.save_entity(body.key,body.value,body.source)
    except Exception as e:raise HTTPException(422,detail=str(e))
    finally:db.close()

# Loom-friendly endpoints. Controlled learning restores changed tool status on completion.
from .demo_features import run_learning, LEARNING_REPORT, eligible_readonly_tools, execute_readonly

class LearningBody(BaseModel):
    task_key: str = 'edit_document'
    iterations: int = Field(default=8, ge=2, le=30)

class ReadonlyBody(BaseModel):
    tool_key: str

@app.post('/demo/learning')
def demo_learning(body: LearningBody):
    try: return run_learning(body.task_key, body.iterations)
    except Exception as e: raise HTTPException(422, detail=str(e))

@app.get('/demo/learning')
def learning_report():
    if not LEARNING_REPORT.exists(): raise HTTPException(404, detail='Run learning experiment first')
    import json
    return json.loads(LEARNING_REPORT.read_text(encoding='utf-8'))

@app.get('/demo/read-only-tools')
def readonly_tools():
    try:return [{'key': t['key'], 'name': t['name'], 'server': t['server']} for t in eligible_readonly_tools()]
    except Exception as e:raise HTTPException(409,detail=str(e))

@app.post('/demo/execute-readonly')
def readonly_execute(body: ReadonlyBody):
    try:return execute_readonly(body.tool_key)
    except Exception as e:raise HTTPException(422,detail=str(e))

class IntentBody(BaseModel):
    text: str

@app.post('/demo/match-task')
def match_intent(body: IntentBody):
    from .demo_features import match_task
    try:return match_task(body.text)
    except Exception as e:raise HTTPException(422,detail=str(e))

@app.get('/demo/hard-eval')
def hard_eval():
    from .demo_features import evaluate_hard_intents
    try:return evaluate_hard_intents()
    except Exception as e:raise HTTPException(422,detail=str(e))

# Track-2 public API: all results are backed by source-discovered MCP schemas.
# The old demo endpoints remain available for backwards compatibility.
from typing import Literal
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from .enterprise_runtime import (registry_stats, resolve_plan, flat_ablation,
                                 diagnostics, run_load, measured_llm_run, PLAN_CACHE)
from .enterprise import REVIEW_FILE
import json as _json
import os as _os
import time as _time
from threading import Lock as _Lock

_origins=[x.strip() for x in _os.getenv('GRAPHSHIELD_CORS_ORIGINS','http://127.0.0.1:8800,http://localhost:8800').split(',') if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=_origins,allow_methods=['GET','POST','DELETE'],allow_headers=['Content-Type'])

class EnterpriseResolveBody(BaseModel):
    task: str
    mode: Literal['preload','lexical','embedding','graphshield']='graphshield'
    agent_id: str='demo'
    entity_key: str|None=None
class EnterpriseFailBody(BaseModel):
    tool_key: str
    reason: str='demo_provider_outage'
    agent_id: str='demo'
class EnterpriseFeedbackBody(BaseModel):
    plan_id: str
    outcome: Literal['success','fail']
    failed_step: int|None=None
class EnterpriseExecuteBody(BaseModel):
    plan_id: str
    filename: str|None=None
    order_id: str|None=None
class EnterpriseLoadBody(BaseModel):
    concurrency: list[int]=[1,5,10,20]
    repeats: int=Field(default=5,ge=1,le=100)
class EnterpriseEntityBody(BaseModel):
    key: str
    value: str
    source: str='reviewed'
class EnterpriseAgentBody(BaseModel):
    task: str
    mode: Literal['preload','lexical','embedding','graphshield']='graphshield'
class ExperimentBody(BaseModel):
    iterations: int=Field(default=5,ge=2,le=10)
    task_key: str='edit_document'

@app.get('/api/health')
def enterprise_health():
    try:
        db=RealHydra()
        try:db.run('MATCH (t:Tool)-[:HAS_VERSION]->(v:ToolVersion) RETURN t.name AS name LIMIT 1')
        finally:db.close()
        connected=True;error=None
    except Exception as exc:connected=False;error=str(exc)[:200]
    try:stats=registry_stats()
    except Exception:stats={}
    return {'status':'ok' if connected else 'degraded','hydradb_connected':connected,
            'registry':stats,'version':'4.0-spec-extension','error':error}

@app.get('/api/registry/stats')
def enterprise_stats():
    try:return registry_stats()
    except Exception as e:raise HTTPException(409,detail=str(e))

@app.get('/api/tools')
def enterprise_tools(q: str='',server: str='',limit:int=100):
    try:
        tools=load_registry()['tools']
        filtered=[{'key':t['key'],'name':t['name'],'server':t['server'],
                   'description':t['description'],'source':t.get('source',''),
                   'version':t.get('version',t.get('server_package',''))} for t in tools
                   if (not q or q.lower() in (t['name']+' '+t['description']).lower())
                   and (not server or t['server']==server)]
        return {'total':len(filtered),'tools':filtered[:max(1,min(500,limit))]}
    except Exception as e:raise HTTPException(409,detail=str(e))

@app.post('/api/resolve')
def enterprise_resolve(body:EnterpriseResolveBody):
    try:return resolve_plan(body.task,body.mode,body.agent_id,body.entity_key)
    except ValueError as e:raise HTTPException(422,detail=str(e))
    except Exception as e:raise HTTPException(503,detail=str(e))

@app.get('/api/diagnostics')
def enterprise_diagnostics():
    try:
        report=diagnostics() # all query shapes executed on running HydraDB
        checks=[{'name':x['name'],'ok':x['ok'],'ms':None,
                 'query_shape':x['name'].replace('_',' '),'error':x.get('error')}
                for x in report.get('checks',[])]
        return {**report,'passed':sum(bool(c['ok']) for c in checks),'total':len(checks),'checks':checks}
    except Exception as e:raise HTTPException(503,detail=str(e))

@app.get('/api/graph/inference')
def enterprise_inference():
    if not REVIEW_FILE.exists():return {'candidate_edges':0,'warning':'Run discovery first'}
    data=_json.loads(REVIEW_FILE.read_text(encoding='utf-8'))
    return {k:v for k,v in data.items() if k!='edges'}|{'sample':data['edges'][:25]}

@app.get('/api/ablation')
def enterprise_ablation():
    try:return flat_ablation()
    except Exception as e:raise HTTPException(503,detail=str(e))

@app.post('/api/failures')
def enterprise_failure(body:EnterpriseFailBody):
    registry=load_registry(); found=[t for t in registry['tools'] if t['key']==body.tool_key]
    if len(found)!=1:raise HTTPException(404,'Unknown tool key')
    db=RealHydra()
    try:return db.fail(__import__('graphshield.real_mcp',fromlist=['stable_id']).stable_id('tool',body.tool_key))
    except Exception as e:raise HTTPException(503,detail=str(e))
    finally:db.close()

@app.delete('/api/failures/{tool_key:path}')
def enterprise_clear_failure(tool_key:str):
    from .real_mcp import stable_id
    db=RealHydra()
    try:return db.restore(stable_id('tool',tool_key))
    finally:db.close()

@app.post('/api/feedback')
def enterprise_feedback(body:EnterpriseFeedbackBody):
    plan=PLAN_CACHE.get(body.plan_id)
    if not plan:raise HTTPException(404,'Plan expired or unknown')
    keys=[s['tool_key'] for s in plan['steps']]
    if body.failed_step:
        if body.failed_step>len(keys) or body.failed_step<1:raise HTTPException(422,'Invalid step')
        keys=[keys[body.failed_step-1]]
    db=RealHydra()
    try:return db.feedback(keys,body.outcome=='success')
    except Exception as e:raise HTTPException(503,detail=str(e))
    finally:db.close()

@app.get('/api/entities')
def enterprise_entities(key:str):
    db=RealHydra()
    try:return {'entity':db.get_entity(key)}
    finally:db.close()

@app.post('/api/entities')
def enterprise_save_entity(body:EnterpriseEntityBody):
    db=RealHydra()
    try:return db.save_entity(body.key,body.value,body.source)
    finally:db.close()

@app.post('/api/execute')
def enterprise_execute(body:EnterpriseExecuteBody):
    plan=PLAN_CACHE.get(body.plan_id)
    if not plan:raise HTTPException(404,'Plan expired or unknown')
    from .demo_features import eligible_readonly_tools, execute_readonly, FINANCIAL_WITH_FILENAME, COMMERCE_WITH_ORDER
    allowed={t['key'] for t in eligible_readonly_tools()}
    def events():
        for step in plan['steps']:
            yield 'data: '+_json.dumps({'event':'step_started','step':step['step'],'tool_key':step['tool_key']})+'\n\n'
            if step['tool_key'] not in allowed:
                yield 'data: '+_json.dumps({'event':'step_skipped','step':step['step'],'reason':'Not a zero-argument allowlisted read-only MCP tool'})+'\n\n'
                continue
            try:
                arguments={'filename':body.filename} if step['capability'] in FINANCIAL_WITH_FILENAME and body.filename else ({'order_id':body.order_id} if step['capability'] in COMMERCE_WITH_ORDER and body.order_id else {})
                if step['capability'] in FINANCIAL_WITH_FILENAME and not body.filename:
                    yield 'data: '+_json.dumps({'event':'step_skipped','step':step['step'],'reason':'Select a real XHTML/iXBRL filename to run this step'})+'\n\n'
                    continue
                if step['capability'] in COMMERCE_WITH_ORDER and not body.order_id:
                    yield 'data: '+_json.dumps({'event':'step_skipped','step':step['step'],'reason':'Choose a historical order ID before executing commerce tools'})+'\n\n'
                    continue
                result=execute_readonly(step['tool_key'],arguments)
                yield 'data: '+_json.dumps({'event':'step_result','step':step['step'],'result':result})+'\n\n'
            except Exception as exc:
                yield 'data: '+_json.dumps({'event':'step_failed','step':step['step'],'error':str(exc)[:300]})+'\n\n'
        yield 'data: '+_json.dumps({'event':'done','note':'Only allowlisted read-only tools may have executed; remaining steps were skipped'})+'\n\n'
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-cache'})

@app.post('/api/experiments/learning')
def enterprise_learning(body:ExperimentBody):
    from .demo_features import run_learning
    try:return run_learning(body.task_key,body.iterations)
    except Exception as e:raise HTTPException(422,detail=str(e))

@app.get('/api/benchmark/results')
def enterprise_bench_results():
    from .real_mcp import REPORT
    items={}
    for name,p in [('real_mcp',REPORT),('load',Path(__file__).resolve().parent.parent/'results'/'enterprise_load.json'),
                   ('learning',Path(__file__).resolve().parent.parent/'results'/'real_learning.json')]:
        if p.exists():items[name]=_json.loads(p.read_text(encoding='utf-8'))
    return items

@app.post('/api/benchmark/load')
def enterprise_load(body:EnterpriseLoadBody):
    try:return run_load(body.concurrency,body.repeats)
    except ValueError as e:raise HTTPException(422,detail=str(e))
    except Exception as e:raise HTTPException(503,detail=str(e))

@app.post('/api/agent/run')
def enterprise_model_run(body:EnterpriseAgentBody):
    try:return measured_llm_run(body.task,body.mode)
    except Exception as e:raise HTTPException(503,detail=str(e))

# A simple in-process demo guard. For public production deployment, use an API
# gateway/shared rate limiter; this guard is intentionally not claimed as robust
# distributed security.
from fastapi import Request
from fastapi.responses import JSONResponse
from collections import defaultdict as _defaultdict
_rate_guard=_Lock()
_rate_windows=_defaultdict(list)
_mutation_paths=('/api/failures','/api/feedback','/api/entities','/api/execute',
                 '/api/benchmark/load','/api/experiments/learning','/api/experiments/reviewed','/api/agent/run',
                 '/real/fail','/real/restore','/real/seed','/demo/learning')

@app.middleware('http')
async def guard_public_demo(request:Request,call_next):
    if request.url.path.startswith('/api/') and request.method!='GET':
        ip=request.client.host if request.client else 'unknown'
        now=_time.monotonic()
        with _rate_guard:
            recent=[x for x in _rate_windows[ip] if now-x<60]
            if len(recent)>=int(_os.getenv('GRAPHSHIELD_RATE_LIMIT_PER_MIN','60')):
                return JSONResponse(status_code=429,content={'detail':'Demo rate limit reached'})
            recent.append(now);_rate_windows[ip]=recent
    key=_os.getenv('GRAPHSHIELD_ADMIN_TOKEN','')
    if key and request.method in ('POST','DELETE') and request.url.path.startswith(_mutation_paths):
        import hmac
        received=request.headers.get('x-graphshield-admin','')
        if not hmac.compare_digest(key,received):
            return JSONResponse(status_code=403,content={'detail':'Administrative demo token required'})
    return await call_next(request)

@app.get('/api/experiments/reviewed')
def reviewed_experiment_report():
    from .reviewed_evaluation import REPORT
    if not REPORT.exists():
        raise HTTPException(404,'No human-reviewed evaluation results. See REVIEWED_EVALUATION.md')
    return _json.loads(REPORT.read_text(encoding='utf-8'))

@app.post('/api/experiments/reviewed')
def reviewed_experiment_run():
    from .reviewed_evaluation import run
    try:return run()
    except (ValueError,FileNotFoundError) as e:raise HTTPException(422,detail=str(e))
    except Exception as e:raise HTTPException(503,detail=str(e))


@app.get('/api/commerce/cases')
def commerce_case_list():
    """Local case picker reads original Olist CSVs; routing/execution remains MCP+HydraDB."""
    try:
        from .commerce_mcp import find_delayed_orders, data_dir
        found=find_delayed_orders(12)
        found['source_directory']=str(data_dir())
        return found
    except FileNotFoundError:
        raise HTTPException(409,detail='No Olist data installed. Run py -3.12 scripts\\fetch_olist.py and restart.')
    except Exception as exc:
        raise HTTPException(422,detail=str(exc)[:300])

# ===== Late-Delivery Refund Desk: dedicated enterprise workflow =====
class RefundDeskBody(BaseModel):
    order_id: str
    followup: bool=False
    simulate_failure: bool=False
    execute_mcp: bool=True

class RefundDeskAgentBody(BaseModel):
    order_id:str
    goal:str='My order arrived late. Please investigate a refund request.'
    mode:str='graphshield'

@app.get('/api/refund-desk/cases')
def refund_desk_cases():
    from .refund_desk import ROOT, save_cases
    path=ROOT/'data'/'refund_desk_cases.json'
    try:
        if not path.exists():save_cases()
        doc=_json.loads(path.read_text(encoding='utf-8'))
        return {'seed':doc['seed'],'train_count':doc['train_count'],'held_out_count':doc['held_out_count'],
                'cases':doc['cases'][:150],
                'disclosure':'All order IDs are historical Olist records. Intents/gold chains and demo policy are authored; not live customer tickets.'}
    except FileNotFoundError as ex:raise HTTPException(409,detail='Original Olist CSV missing: '+str(ex))

@app.get('/api/refund-desk/llm-status')
def refund_desk_llm_status():
    """Safe configuration probe: never exposes credentials or their contents."""
    import os
    configured=bool(os.getenv('GRAPHSHIELD_LLM_API_KEY')) and bool(os.getenv('GRAPHSHIELD_LLM_MODEL'))
    return {'configured':configured,
            'model':os.getenv('GRAPHSHIELD_LLM_MODEL') if configured else None,
            'api_key_present':bool(os.getenv('GRAPHSHIELD_LLM_API_KEY')),
            'model_present':bool(os.getenv('GRAPHSHIELD_LLM_MODEL')),
            'hint':('Ready to attempt a real model call; credentials/model availability are verified only on request.' if configured
                    else 'Set GRAPHSHIELD_LLM_API_KEY and GRAPHSHIELD_LLM_MODEL in the same PowerShell session BEFORE starting Uvicorn; restart Uvicorn afterward.')}

@app.get('/api/refund-desk/registry')
def refund_desk_registry():
    from .refund_desk import GROUPS, specs,load_policy
    from .real_mcp import SNAPSHOT
    discovered=[]
    if SNAPSHOT.exists():
        doc=load_registry()
        discovered=[t for t in doc['tools'] if t['server'].split('_')[0] in GROUPS]
    return {'unique_domain_definitions':len(specs()),'domain_roles':len(GROUPS),
            'actual_discovered_entries':len(discovered),
            'providers':sorted(set(t['server'] for t in discovered)),
            'policy':load_policy(), 'source':'Actual tool records must be discovered via MCP tools/list'}

@app.post('/api/refund-desk/trace')
def refund_desk_trace(body:RefundDeskBody):
    from .refund_desk_trace import stream_case,assert_order
    try:assert_order(body.order_id)
    except FileNotFoundError as ex:raise HTTPException(409,detail=str(ex))
    except ValueError as ex:raise HTTPException(422,detail=str(ex))
    def gen():
        try:
            for event in stream_case(body.order_id,body.followup,body.simulate_failure,body.execute_mcp):
                yield 'data: '+_json.dumps(event,default=str,ensure_ascii=False)+'\n\n'
        except Exception as ex:
            yield 'data: '+_json.dumps({'event':'error','message':str(ex)[:400]})+'\n\n'
    return StreamingResponse(gen(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})

@app.post('/api/refund-desk/agent')
def refund_desk_llm(body:RefundDeskAgentBody):
    from .refund_agent import run_llm_refund_agent
    try:return run_llm_refund_agent(body.order_id,body.goal,body.mode)
    except ValueError as ex:raise HTTPException(422,detail=str(ex))
    except Exception as ex:raise HTTPException(503,detail=str(ex)[:300])

class RefundOutageBody(BaseModel):
    tool_name: str='resolve_order'
    provider: str='orders_primary'
    restore: bool=False

@app.post('/api/refund-desk/provider-health')
def refund_desk_provider_health(body:RefundOutageBody):
    """Controlled health injection for exact discoverable order/payment provider tools."""
    from .real_mcp import stable_id
    if body.provider not in ('orders_primary','orders_replica','orders_cache','payments_primary','payments_replica','payments_cache'):
        raise HTTPException(422,'Provider not in demo allowlist')
    from .refund_desk import GROUPS
    role=body.provider.split('_')[0]
    if body.tool_name not in {x[0] for x in GROUPS[role]}:
        raise HTTPException(422,'Tool is not a configured provider capability')
    tool_key=f'{body.provider}::{body.tool_name}'
    if tool_key not in {x['key'] for x in load_registry()['tools']}:
        raise HTTPException(404,'Provider tool not discovered; run discovery and seed')
    db=RealHydra()
    try:
        out=db.restore(stable_id('tool',tool_key)) if body.restore else db.fail(stable_id('tool',tool_key))
        return {'tool_key':tool_key,'simulation':True,'health_change':out,
                'note':'Persistent HydraDB provider-health injection, not a real API outage'}
    except Exception as ex:raise HTTPException(503,detail=str(ex)[:300])
    finally:db.close()

@app.get('/api/refund-desk/experiment')
def refund_desk_experiment_result():
    from .refund_experiment import OUTPUT
    if not OUTPUT.exists():raise HTTPException(404,'Run python -m graphshield.refund_experiment first')
    return _json.loads(OUTPUT.read_text(encoding='utf-8'))


@app.get('/api/refund-desk/online-learning')
def refund_desk_online_learning(scenario:str='drift',dryrun:bool=False):
    """Saved online-learning results. Dry-run (in-memory) files are served only on request and are flagged non-citable."""
    from .refund_online import OUTPUT,OUTPUT_DRYRUN,SCENARIOS
    if scenario not in SCENARIOS:raise HTTPException(422,'scenario must be drift or stationary')
    path=OUTPUT_DRYRUN if dryrun else OUTPUT
    if scenario!='drift':path=path.with_name(path.stem+'_'+scenario+path.suffix)
    if not path.exists():raise HTTPException(404,'Run python -m graphshield.refund_online'+('' if scenario=='drift' else ' --scenario '+scenario)+(' --backend memory' if dryrun else '')+' first')
    return _json.loads(path.read_text(encoding='utf-8'))


# V9 evidence endpoints, all sourced from real saved reports or live HydraDB queries.
# Missing reports produce clear 404s, rather than fabricated demo numbers.
@app.get('/api/experiments/learning')
def v9_learning_report():
    from .v9_evidence import learning_evidence
    result=learning_evidence()
    if result is None:
        raise HTTPException(404,'Run python -m graphshield.refund_experiment to generate the real 5-iteration study first')
    return result

@app.get('/api/benchmarks/dataflow')
def v9_dataflow_report():
    from .v9_evidence import benchmark_evidence
    result=benchmark_evidence()
    if result is None:
        raise HTTPException(404,'MCP discovery required: python -m graphshield.real_mcp discover')
    return result

@app.post('/api/demo/reset')
def v9_demo_reset():
    # Deliberately refuse to mutate a shared graph: a safe transactional reset
    # needs operator-approved isolation and must not erase a real HydraDB store.
    raise HTTPException(501,'Safe full reset is not implemented; reset is disabled to protect HydraDB data')
