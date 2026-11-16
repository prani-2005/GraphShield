"""Interactive enterprise evaluation against the existing HydraDB resolver.

Preload/lexical/embedding are honest retrieval baselines. Tools are not
executed unless the user invokes the explicit read-only MCP endpoint.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from .real_mcp import RealHydra, load_registry, load_tasks
from .resolver import estimate_tokens

ROOT=Path(__file__).resolve().parent.parent
REPORT_DIR=ROOT/'results'
PLAN_CACHE={}


def _terms(text):return set(re.findall('[a-z0-9]+',text.lower().replace('_',' ')))


def _meta(tool):
    return {'name':tool['name'],'description':tool['description'],'schema':tool['schema']}


def _graph_route(task_key, budget=200000, entity_key=None):
    db=RealHydra()
    try:return db.resolve(task_key, budget, entity_key)
    finally:db.close()


def _embedding_rank(task,tools,limit):
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError as e:
        raise RuntimeError('Embedding baseline unavailable. Install sentence-transformers; no lexical substitution is made.') from e
    model=SentenceTransformer(os.getenv('GRAPHSHIELD_EMBEDDING_MODEL','sentence-transformers/all-MiniLM-L6-v2'))
    texts=[task['description']]+[t['name']+' '+t['description'] for t in tools]
    embeddings=model.encode(texts,normalize_embeddings=True)
    values=embeddings[1:] @ embeddings[0]
    return [tools[i] for i in sorted(range(len(tools)),key=lambda i:-float(values[i]))[:limit]]


def resolve_plan(task_key,mode='graphshield',agent_id='demo',entity_key=None):
    if mode not in ('graphshield','preload','lexical','embedding'):
        raise ValueError('mode must be graphshield, preload, lexical or embedding')
    registry=load_registry(); workflows=load_tasks(); tasks={x['key']:x for x in workflows['tasks']}
    original_input=task_key
    matching='direct_workflow_key'
    if task_key not in tasks:
        from .demo_features import match_task
        prediction=match_task(task_key,workflows)
        task_key=prediction['task_key']
        matching='lexical_intent_match_unverified'
    task=tasks[task_key]; t0=time.perf_counter()
    query_text=original_input if matching!='direct_workflow_key' else task['description']
    tools=registry['tools']
    graph_route=None
    if mode=='graphshield':
        graph_route=_graph_route(task_key,entity_key=entity_key)
        chosen=graph_route['tools']; rejected=graph_route['rejected'];edges=graph_route['graph_edges']
    elif mode=='preload':
        chosen=tools; rejected=[];edges=[]
    else:
        n=len(task['chain'])
        if mode=='lexical':
            q=_terms(query_text)
            ranked=sorted(tools,key=lambda t:-len(q&_terms(t['name']+' '+t['description'])))
            chosen=ranked[:n]
        else: chosen=_embedding_rank({'description':query_text},tools,n)
        rejected=[];edges=[]
    context=[_meta(x) for x in chosen]
    plan_id=str(uuid.uuid4())
    result={
        'plan_id':plan_id,'task_key':task_key,'goal':query_text,'mode':mode,'intent_method':matching,
        'agent_id':agent_id,'steps':[{'step':i+1,'capability':t['name'],
           'tool_key':t['key'] if 'key' in t else t['tool_key'],'server':t['server'],
           'reason':'HydraDB traversal' if mode=='graphshield' else 'retrieval baseline',
           'inputs_needed':list(t.get('schema',{}).get('required',[])),
           'produces':list(t.get('output_schema',{}).get('properties',{})),
           'read_only':bool(t.get('annotations',{}).get('readOnlyHint',False))} for i,t in enumerate(chosen)],
        'traversal':edges,'rejected':rejected,
        'entities_reused':[graph_route['resolved_entity']] if graph_route and graph_route.get('resolved_entity') else [],
        'tokens':{'loaded':estimate_tokens(context),'registry_total':estimate_tokens([_meta(t) for t in tools]),
                  'method':'estimated_chars_divided_by_4','measured':False},
        'graph_queries':graph_route['graph_queries'] if graph_route else 0,
        'latency_ms':round((time.perf_counter()-t0)*1000,3),
        'limitations':['Tool selection and schemas only; not an executed agent workflow.',
                       'Input task is mapped to a curated workflow. No arbitrary-goal LLM planning.',
                       'Token estimate is JSON character count divided by four.'],
    }
    PLAN_CACHE[plan_id]=result
    if len(PLAN_CACHE)>1000:PLAN_CACHE.pop(next(iter(PLAN_CACHE)))
    return result


def diagnostics():
    """Verify bounded, anchored Cypher query shapes on the running HydraDB."""
    from .real_mcp import stable_id
    checks=[]
    registry=load_registry();workflows=load_tasks()
    if not registry['tools'] or not workflows['tasks']:
        raise ValueError('Discover and seed real tools before checking Cypher')
    t=registry['tools'][0]
    tid=stable_id('tool',t['key'])
    sid=stable_id('server',t['server'])
    task=workflows['tasks'][0]
    taskid=stable_id('task',task['key'])
    queries=[
      ('task_requires','MATCH (t:Task {id: $id})-[:REQUIRES]->(s:Skill) RETURN s.id AS id',{'id':taskid}),
      ('tool_versions','MATCH (t:Tool {id: $id})-[:HAS_VERSION]->(v:ToolVersion) RETURN v.status AS status',{'id':tid}),
      ('server_exposes','MATCH (s:MCPServer {id: $id})-[:EXPOSES]->(t:Tool) RETURN t.name AS name',{'id':sid}),
      ('failure','MATCH (t:Tool {id: $id})-[:FAILED_ON]->(f:Failure) RETURN f.id AS id',{'id':tid}),
      ('producer_datatype','MATCH (t:Tool {id: $id})-[:PRODUCES]->(d:DataType) RETURN d.name AS name',{'id':tid}),
      ('consumer_datatype','MATCH (t:Tool {id: $id})-[:CONSUMES]->(d:DataType) RETURN d.name AS name',{'id':tid}),
    ]
    db=RealHydra()
    try:
        for name,q,params in queries:
            try:checks.append({'name':name,'ok':True,'count':len(db.run(q,**params))})
            except Exception as ex:checks.append({'name':name,'ok':False,'error':str(ex)[:240]})
    finally:db.close()
    return {'backend':'hydradb','checks':checks,'all_queries_supported':all(x['ok'] for x in checks)}


def registry_stats():
    reg=load_registry();tasks=load_tasks()['tasks']
    return {'tools':len(reg['tools']),'unique_tool_names':len({t['name'] for t in reg['tools']}),
            'server_instances':len(reg['servers']),'curated_workflows':len(tasks),
            'sources':{'mcp_tools_list':sum(t.get('source')=='mcp tools/list' for t in reg['tools']),
                       'converted_openapi':sum(t.get('source')=='converted OpenAPI' for t in reg['tools'])},
            'estimated_registry_schema_tokens':estimate_tokens([_meta(t) for t in reg['tools']]),
            'token_method':'estimated_chars_divided_by_4',
            'openapi_sources':reg.get('openapi_sources',[]),'errors':reg.get('errors',[])+reg.get('openapi_errors',[])}


def flat_ablation():
    """Compare context selection without graph traversal against curated graph chains.

    Flat lexical is not asserted to be the strongest possible relational solution.
    """
    registry=load_registry();tasks=load_tasks()['tasks'];tools=registry['tools'];rows=[]
    for task in tasks:
        n=len(task['chain']);q=_terms(task['description'])
        ranked=sorted(tools,key=lambda t:-len(q&_terms(t['name']+' '+t['description'])))[:n]
        matched={x['name'] for x in ranked};target=set(task['chain'])
        graph_names={x['name'] for x in _graph_route(task['key'])['tools']}
        rows.append({'task':task['key'],'dependencies':len(target),'flat_recall':round(len(matched&target)/max(1,len(target)),3),
                     'graph_recall':round(len(graph_names&target)/max(1,len(target)),3)})
    return {'rows':rows,'flat_mean_recall':round(statistics.mean(x['flat_recall'] for x in rows),3) if rows else None,
            'graph_mean_recall':round(statistics.mean(x['graph_recall'] for x in rows),3) if rows else None,
            'disclosure':'Flat baseline is simple lexical matching with no joins or traversal. Not a proof that SQL cannot implement dependency traversal. Gold chains are curated.'}


def run_load(workers=(1,5,10,20), repeats=5):
    if not 1<=repeats<=100:raise ValueError('repeats out of allowed range')
    tasks=load_tasks()['tasks'];summary=[]
    for n in workers:
        if n not in (1,5,10,20,50):raise ValueError('Unsupported worker setting')
        requests=[t['key'] for _ in range(repeats) for t in tasks]
        started=time.perf_counter()
        def one(key):
            t0=time.perf_counter()
            try:
                route=_graph_route(key)
                return {'ms':(time.perf_counter()-t0)*1000,'queries':route['graph_queries'],'error':None}
            except Exception as ex:
                return {'ms':(time.perf_counter()-t0)*1000,'queries':0,'error':str(ex)}
        with ThreadPoolExecutor(max_workers=n) as pool:rows=list(pool.map(one,requests))
        wall=time.perf_counter()-started
        good=sorted(x['ms'] for x in rows if not x['error'])
        def pct(q):return round(good[min(len(good)-1,int((len(good)-1)*q))],2) if good else None
        summary.append({'workers':n,'requests':len(rows),'p50_ms':pct(.50),'p95_ms':pct(.95),'p99_ms':pct(.99),
                        'throughput_tasks_sec':round(len(rows)/wall,2) if wall else None,
                        'errors':sum(bool(x['error']) for x in rows),
                        'graph_queries_per_task_mean':round(statistics.mean(x['queries'] for x in rows),2),
                        'system_graph_queries_total':sum(x['queries'] for x in rows),
                        'wall_seconds':round(wall,3)})
    result={'backend':'hydradb','rows':summary,
            'disclosure':'Real routing calls to HydraDB, no LLM execution. Repeated curated task keys; no external concurrent users.'}
    REPORT_DIR.mkdir(exist_ok=True,parents=True)
    (REPORT_DIR/'enterprise_load.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def measured_llm_run(task_key,mode='graphshield',prompt=None):
    """Optional actual model API call. Never synthesizes token usage."""
    import httpx
    api_key=os.getenv('GRAPHSHIELD_LLM_API_KEY')
    base=os.getenv('GRAPHSHIELD_LLM_BASE_URL','https://api.groq.com/openai/v1').rstrip('/')
    model=os.getenv('GRAPHSHIELD_LLM_MODEL')
    if not api_key or not model:
        raise RuntimeError('Configure GRAPHSHIELD_LLM_API_KEY and GRAPHSHIELD_LLM_MODEL for measured LLM runs')
    if not base.startswith('https://'):
        raise ValueError('LLM API endpoint must use HTTPS')
    plan=resolve_plan(task_key,mode)
    if prompt:plan['goal']=prompt
    registry=load_registry();lookup={t['key']:t for t in registry['tools']}
    schemas=[{'key':x['tool_key'],**_meta(lookup[x['tool_key']])} for x in plan['steps']]
    messages=[{'role':'system','content':'You are an enterprise workflow planner. Return ONLY a JSON object with a tool_keys array containing the available tool identifiers required for the task. Never invent a tool key. Never execute or request writes.'},
              {'role':'user','content':f"Task: {plan['goal']}\nAvailable tool definitions: {json.dumps(schemas,ensure_ascii=False)}"}]
    tick=time.perf_counter()
    with httpx.Client(timeout=60) as client:
        response=client.post(base+'/chat/completions',headers={'Authorization':'Bearer '+api_key},
                             json={'model':model,'messages':messages,'temperature':0})
        response.raise_for_status();data=response.json()
    usage=data.get('usage')
    if not usage:raise RuntimeError('LLM response had no usage information; no measured token claim possible')
    content=data['choices'][0]['message'].get('content','') or ''
    try:
        parsed=json.loads(content.strip())
        predicted=parsed.get('tool_keys') if isinstance(parsed,dict) else None
        if not isinstance(predicted,list) or any(not isinstance(x,str) for x in predicted):predicted=None
    except Exception:predicted=None
    gold_names=set(next(t['chain'] for t in load_tasks()['tasks'] if t['key']==task_key))
    found_names={lookup[x]['name'] for x in predicted if x in lookup} if predicted is not None else set()
    checked=predicted is not None
    return {'plan':plan,'model':model,'provider_url':base,'usage':usage,
            'predicted_tool_keys':predicted,'gold_capability_match':int(found_names==gold_names) if checked else None,
            'gold_source':'curated workflow chain, not independent external ground truth',
            'latency_ms':round((time.perf_counter()-tick)*1000,2),
            'model_text':content,
            'success_checked':checked,
            'disclosure':'Actual provider-reported token usage; matching compares model output to curated workflow capabilities, NOT real task completion. No MCP tools executed.'}
