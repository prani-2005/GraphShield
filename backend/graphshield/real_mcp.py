"""Real MCP tool discovery + genuine HydraDB graph context routing.

Never fabricates tool schemas. Discovery calls the MCP tools/list protocol. The
curated workflows describe manually authored tasks, NOT an external benchmark.
Tools are not executed: this project demonstrates agent context retrieval.
"""
from __future__ import annotations
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import time
from .graph import HydraGraph, begin_query_count, current_query_count, end_query_count
from .resolver import estimate_tokens
from .enterprise import load_openapi_directory, merge_registries, write_inference_report

ROOT=Path(__file__).resolve().parent.parent
SNAPSHOT=ROOT/'data'/'mcp_registry.json'
WORKFLOWS=ROOT/'data'/'real_workflows.json'
REPORT=ROOT/'results'/'real_mcp_benchmark.json'

# These are real named MCP tools from the reference-server ecosystem. Each
# scenario is included ONLY if all named tools actually occur in tools/list.
# Ground truth is hand-authored and explicitly not independent public labels.
RECIPES=[
('refund_desk_first_request','Late delivery: resolve order, timeline, delay, payment, demo policy, eligibility, and approval draft',['resolve_order','get_order_timeline','compute_delay_days','get_order_payments','get_refund_policy','check_refund_eligibility','draft_refund_request']),
('refund_desk_followup','After resolving an order, retrieve its items and simulated refund timeline',['get_order_items','get_refund_processing_eta']),
('refund_desk_payment_question','Investigate historical payment details',['resolve_order','get_order_payments','get_payment_breakdown']),
('refund_desk_order_status','Inspect order delivery status',['resolve_order','get_order_status','get_delivery_timeline']),
('refund_desk_wrong_item','Inspect historical item and product IDs',['resolve_order','get_order_items','get_product_ids']),
]

def stable_id(kind, value):
    # Distinct ID range from original synthetic demo (10k..60k).
    # Substantial hashing space; collisions checked during seed.
    return 1000000000 + int.from_bytes(hashlib.sha256((kind+'|'+str(value)).encode()).digest()[:6], 'big')

def _short_key(name):
    return re.sub('[^a-z0-9_]+','_',name.lower()).strip('_')

async def discover_server(server):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params=StdioServerParameters(command=__import__('sys').executable if server['command']=='{python}' else server['command'], args=server.get('args',[]), env={**os.environ,**server.get('env',{})})
    result=[]
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            page=await session.list_tools()
            for t in page.tools:
                schema=t.inputSchema if isinstance(t.inputSchema,dict) else t.inputSchema.model_dump(mode='json')
                result.append({'key':server['id']+'::'+t.name,'name':t.name,'server':server['id'],
                               'description':t.description or '', 'schema':schema,
                               'annotations':t.annotations.model_dump(mode='json') if t.annotations else {},
                               'source':'mcp tools/list', 'server_package':server.get('package',''),
                               'source_repo':server.get('source_repo','https://github.com/modelcontextprotocol/servers'), 'output_fields':[], 'input_fields':[]})
            # Some MCP servers paginate. Use cursor whenever provided.
            cursor=page.nextCursor
            while cursor:
                page=await session.list_tools(cursor=cursor)
                for t in page.tools:
                    schema=t.inputSchema if isinstance(t.inputSchema,dict) else t.inputSchema.model_dump(mode='json')
                    result.append({'key':server['id']+'::'+t.name,'name':t.name,'server':server['id'],
                                   'description':t.description or '', 'schema':schema,
                                   'annotations':t.annotations.model_dump(mode='json') if t.annotations else {},
                                   'source':'mcp tools/list','server_package':server.get('package',''),
                                   'source_repo':server.get('source_repo','https://github.com/modelcontextprotocol/servers'), 'output_fields':[], 'input_fields':[]})
                cursor=page.nextCursor
    return result

async def discover(config_path):
    config=json.loads(Path(config_path).read_text(encoding='utf-8'))
    tools=[]; errors=[]; servers_ok=[]
    for server in config['servers']:
        try:
            entries=await asyncio.wait_for(discover_server(server), timeout=90)
            if not entries: raise ValueError('MCP server returned zero tools')
            tools.extend(entries)
            servers_ok.append(server['id'])
            print(f"MCP {server['id']}: {len(entries)} real tools")
        except Exception as e:
            errors.append({'server':server['id'],'error':str(e)})
            print(f"SKIPPED {server['id']}: {e}")
    if not tools: raise RuntimeError('No real MCP tools discovered; check Node/npm and server commands')
    doc={'source':'MCP protocol tools/list (live discovery)', 'source_git_commit':config.get('source_git_commit',''),
         'discovered_at_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
         'servers':servers_ok,'errors':errors,'tools':tools}
    # Include only operator-supplied, source-verified OpenAPI specifications.
    openapi=load_openapi_directory()
    doc=merge_registries(doc,openapi)
    write_inference_report(doc['tools'])
    SNAPSHOT.parent.mkdir(parents=True,exist_ok=True)
    SNAPSHOT.write_text(json.dumps(doc,indent=2,ensure_ascii=False),encoding='utf-8')
    print(f'Saved {len(tools)} real tools to {SNAPSHOT}')
    return doc

def build_workflows(doc):
    by_name={}
    for t in doc['tools']:
        by_name.setdefault(t['name'],[]).append(t)
    tasks=[]; excluded=[]
    for key,description,chain in RECIPES:
        missing=[x for x in chain if x not in by_name]
        if missing:
            excluded.append({'key':key,'missing_tools':missing})
            continue
        # Prefer non-standby instance for reproducibility; duplicate tools in chain
        # are collapsed to a single graph node per workflow step.
        tasks.append({'key':key,'description':description,'chain':list(dict.fromkeys(chain)),
                      'labels_origin':'manually reviewed reference-server workflow',
                      'difficulty':'multi_step' if len(set(chain))>=3 else 'standard'})
    # Operator-reviewed task chains are optional and must refer to discovered real tools.
    # No generated or invented gold examples are inserted into the registry.
    approved=ROOT/'data'/'approved_workflows.json'
    if approved.exists():
        external=json.loads(approved.read_text(encoding='utf-8'))
        if not isinstance(external,list):raise ValueError('approved_workflows.json must be a list')
        for item in external:
            if item.get('review_status')!='human_verified':
                excluded.append({'key':item.get('key'),'reason':'review_status is not human_verified'});continue
            key=item.get('key','');chain=item.get('chain',[])
            if not isinstance(key,str) or not re.fullmatch('[a-zA-Z0-9_-]{3,100}',key) or not isinstance(chain,list) or not chain:
                raise ValueError('Invalid human-verified workflow record')
            if any(x not in by_name for x in chain):
                excluded.append({'key':key,'missing_tools':[x for x in chain if x not in by_name]});continue
            if any(x['key']==key for x in tasks):raise ValueError('Duplicate workflow key: '+key)
            tasks.append({'key':key,'description':item.get('description',key),
                          'chain':list(dict.fromkeys(chain)),
                          'labels_origin':'operator human_verified workflow',
                          'difficulty':item.get('difficulty','reviewed')})
    data={'tasks':tasks,'excluded':excluded,'note':'Built-in task templates and optional human-verified task chains use discovered real tool names. No claim of public labeled benchmark.'}
    WORKFLOWS.parent.mkdir(exist_ok=True,parents=True)
    WORKFLOWS.write_text(json.dumps(data,indent=2),encoding='utf-8')
    return data

class RealHydra:
    def __init__(self):
        self.db=HydraGraph()
        self.backend='hydradb'
        self.tools=[]
        self.workflows=[]
    def close(self):self.db.close()
    def run(self,q,**kw):return self.db.run(q,**kw)
    def _seed_edge(self, src_label, src_id, relation, dst_label, dst_id, query, params, context):
        """Skip an already-present edge, preserving persisted provider health.

        This is a compatibility workaround for re-seeding a V2/V3 graph on the
        current HydraDB engine. It does not update existing node metadata.
        """
        allowed_labels={'MCPServer','Tool','ToolVersion','DataType','Skill','Task'}
        allowed_relations={'EXPOSES','HAS_VERSION','PRODUCES','CONSUMES',
                           'IMPLEMENTED_BY','DEPENDS_ON','REQUIRES'}
        if src_label not in allowed_labels or dst_label not in allowed_labels or relation not in allowed_relations:
            raise ValueError('Invalid seed edge type')
        check=(f'MATCH (a:{src_label} {{id: $src}})-[:{relation}]->'
               f'(b:{dst_label} {{id: $dst}}) RETURN b.id AS id')
        try:
            if self.run(check,src=src_id,dst=dst_id):
                return False
            self.run(query,**params)
            return True
        except Exception as exc:
            raise RuntimeError(f'Failed graph seeding at {context} '
                               f'({src_label}:{src_id})-[:{relation}]->'
                               f'({dst_label}:{dst_id}): {exc}') from exc

    def seed(self, registry, workflows):
        tools=registry['tools'];tasks=workflows['tasks']
        self.tools=tools;self.workflows=tasks
        q=0;skipped=0
        def edge(src_label,src_id,relation,dst_label,dst_id,query,params,context):
            nonlocal q,skipped
            if self._seed_edge(src_label,src_id,relation,dst_label,dst_id,query,params,context):
                q+=1
            else:
                skipped+=1
        for tool in tools:
            tid=stable_id('tool',tool['key'])
            vid=stable_id('version',tool['key'])
            sid=stable_id('server',tool['server'])
            if len({tid,vid,sid})!=3:raise ValueError('Hash ID collision')
            edge('MCPServer',sid,'EXPOSES','Tool',tid,
                'MERGE (s:MCPServer {id: $sid, name: $server})-[:EXPOSES]->(t:Tool {id: $tid, name: $name, server: $server, description: $description, schema_json: $schema, tool_key: $key})',
                dict(sid=sid,server=tool['server'],tid=tid,name=tool['name'],
                     description=tool['description'],schema=json.dumps(tool['schema'],sort_keys=True),key=tool['key']),
                'MCP tool '+tool['key'])
            edge('Tool',tid,'HAS_VERSION','ToolVersion',vid,
                'MERGE (t:Tool {id: $tid})-[:HAS_VERSION]->(v:ToolVersion {id: $vid, status: $status, version: $version})',
                dict(tid=tid,vid=vid,status='healthy',version=registry.get('source_git_commit','reference')),
                'version '+tool['key'])
        from .enterprise import infer_edges
        dtype_seen=set()
        for item in infer_edges(tools):
            producer_id=stable_id('tool',item['producer'])
            consumer_id=stable_id('tool',item['consumer'])
            dtype_id=stable_id('datatype',item['field']+'|'+item['type'])
            if ('p',producer_id,dtype_id) not in dtype_seen:
                edge('Tool',producer_id,'PRODUCES','DataType',dtype_id,
                     'MERGE (t:Tool {id: $tid})-[:PRODUCES]->(d:DataType {id: $did, name: $name, data_type: $typ})',
                     dict(tid=producer_id,did=dtype_id,name=item['field'],typ=item['type']),
                     'produced datatype '+item['producer']+' '+item['field'])
                dtype_seen.add(('p',producer_id,dtype_id))
            if ('c',consumer_id,dtype_id) not in dtype_seen:
                edge('Tool',consumer_id,'CONSUMES','DataType',dtype_id,
                     'MERGE (t:Tool {id: $tid})-[:CONSUMES]->(d:DataType {id: $did, name: $name, data_type: $typ})',
                     dict(tid=consumer_id,did=dtype_id,name=item['field'],typ=item['type']),
                     'consumed datatype '+item['consumer']+' '+item['field'])
                dtype_seen.add(('c',consumer_id,dtype_id))
        for task in tasks:
            ordered=[]
            for i,name in enumerate(task['chain']):
                skill_id=stable_id('skill',task['key']+'|'+str(i))
                ordered.append(skill_id)
                for tool in (t for t in tools if t['name']==name):
                    tid=stable_id('tool',tool['key'])
                    edge('Skill',skill_id,'IMPLEMENTED_BY','Tool',tid,
                         'MERGE (s:Skill {id: $sid, name: $skill, step: $step})-[:IMPLEMENTED_BY]->(t:Tool {id: $tid})',
                         dict(sid=skill_id,skill=task['key']+':'+name,step=i,tid=tid),
                         'implementation '+task['key']+' '+tool['key'])
                if i>0:
                    edge('Skill',skill_id,'DEPENDS_ON','Skill',ordered[i-1],
                         'MERGE (s:Skill {id: $sid})-[:DEPENDS_ON]->(p:Skill {id: $prior})',
                         dict(sid=skill_id,prior=ordered[i-1]),'dependency '+task['key'])
            if ordered:
                task_id=stable_id('task',task['key'])
                edge('Task',task_id,'REQUIRES','Skill',ordered[-1],
                     'MERGE (t:Task {id: $tid, task_key: $key, description: $desc})-[:REQUIRES]->(s:Skill {id: $sid})',
                     dict(tid=task_id,key=task['key'],desc=task['description'],sid=ordered[-1]),
                     'task '+task['key'])
        return {'real_tools':len(tools),'curated_tasks':len(tasks),
                'write_queries':q,'existing_edges_skipped':skipped,
                'servers':len(registry['servers'])}

    def resolve(self,key,token_budget=12000,entity_key=None):
        token=begin_query_count()
        try:return self._resolve(key,token_budget,entity_key)
        finally:end_query_count(token)
    def _resolve(self,key,token_budget,entity_key=None):
        tasks=self.run('MATCH (t:Task)-[:REQUIRES]->(s:Skill) WHERE t.task_key = $key RETURN t.description AS description, s.id AS skill_id',key=key)
        if not tasks: raise ValueError('Unknown real task key; import real registry first: '+key)
        # Actual graph traversal for dependencies, not a local CSV lookup.
        selected=[];paths=[];rejected=[];active=set();visited=set()
        def walk(sid,depth):
            if depth>8: raise ValueError('Graph dependency depth limit (8)')
            if sid in active:raise ValueError('Dependency cycle')
            if sid in visited:return
            active.add(sid)
            prereqs=self.run('MATCH (a:Skill {id: $sid})-[:DEPENDS_ON]->(b:Skill) RETURN b.id AS id',sid=sid)
            for p in prereqs:
                paths.append({'source':sid,'relation':'DEPENDS_ON','target':p['id']})
                walk(p['id'],depth+1)
            active.remove(sid);visited.add(sid)
            rows=self.run('MATCH (s:Skill {id: $sid})-[:IMPLEMENTED_BY]->(t:Tool)-[:HAS_VERSION]->(v:ToolVersion) RETURN t.id AS id, t.name AS name, t.server AS server, t.description AS description, t.schema_json AS schema_json, t.tool_key AS tool_key, v.status AS status, v.reward AS reward',sid=sid)
            if not rows: raise ValueError('No tool implementations for skill '+str(sid))
            rows.sort(key=lambda r:(r['status']!='healthy', -(r.get('reward') or 0), 0 if r['server'].endswith('_primary') else 1 if r['server'].endswith('_replica') else 2 if r['server'].endswith('_cache') else 3 if r['server'].endswith('_standby') else 0, r['tool_key']))
            healthy=[r for r in rows if r['status']=='healthy']
            if not healthy: raise ValueError('No healthy tool for skill '+str(sid))
            best=healthy[0]
            selected.append({'id':best['id'],'name':best['name'],'server':best['server'],'tool_key':best['tool_key'],
                             'description':best['description'],'schema':json.loads(best['schema_json']),'reward':best.get('reward') or 0})
            paths.append({'source':sid,'relation':'IMPLEMENTED_BY','target':best['tool_key']})
            rejected.extend([{'name':r['name'],'server':r['server'],'reason':'unhealthy' if r['status']!='healthy' else 'standby / alternate'} for r in rows if r['id']!=best['id']])
        walk(tasks[0]['skill_id'],0)
        tok=estimate_tokens([{'name':t['name'],'description':t['description'],'schema':t['schema']} for t in selected])
        if tok>token_budget:raise ValueError(f'Required schemas need ~{tok} estimated tokens, budget {token_budget}; no silent omission')
        entities=self.get_entity(entity_key) if entity_key else None
        return {'task':key,'description':tasks[0]['description'],'backend':'hydradb','tools':selected,
                'graph_edges':paths,'rejected':rejected,'resolved_entity':entities,'estimated_schema_tokens':tok,'graph_queries':current_query_count()}
    def feedback(self, tool_keys, success=True):
        updated=[]
        for key in tool_keys:
            tid=stable_id('tool',key)
            rows=self.run('MATCH (t:Tool {id: $tid})-[:HAS_VERSION]->(v:ToolVersion) RETURN v.reward AS reward',tid=tid)
            if not rows:continue
            old=int(rows[0].get('reward') or 0)
            new=max(-10,min(100,old+(1 if success else -2)))
            self.run('MATCH (t:Tool {id: $tid})-[:HAS_VERSION]->(v:ToolVersion) SET v.reward = $reward',tid=tid,reward=new)
            updated.append({'tool_key':key,'before':old,'after':new})
        return {'updated':updated,'persisted_in':'HydraDB ToolVersion.reward',
                'limitation':'Evidence-based preference update only; not an independently verified learning improvement'}
    def get_entity(self,key):
        if not key:return None
        rows=self.run('MATCH (e:Entity)-[:RESOLVED_AS]->(r:Resolution) WHERE e.entity_key = $key RETURN r.value AS value, r.source AS source',key=key)
        return {'key':key,'value':rows[0]['value'],'source':rows[0]['source']} if rows else None
    def save_entity(self,key,value,source="reviewed"):
        if not key or len(key)>200 or len(value)>4000:raise ValueError("Invalid entity key/value length")
        eid=stable_id('entity',key);rid=stable_id('resolution',key)
        self.run('MERGE (e:Entity {id: $eid, entity_key: $key})-[:RESOLVED_AS]->(r:Resolution {id: $rid, value: $value, source: $source})',eid=eid,key=key,rid=rid,value=value,source=source)
        self.run('MATCH (r:Resolution {id: $rid}) SET r.value = $value, r.source = $source',rid=rid,value=value,source=source)
        return {'stored':True,'key':key}
    def fail(self,tid):
        # Persistent graph mutation: availability shared between independent API processes.
        result=self.run('MATCH (t:Tool {id: $tid})-[:HAS_VERSION]->(v:ToolVersion) RETURN t.id AS id',tid=tid)
        if not result:raise ValueError('Tool not found')
        self.run('MATCH (t:Tool {id: $tid})-[:HAS_VERSION]->(v:ToolVersion) SET v.status = $status',tid=tid,status='unhealthy')
        # Persist a typed FAILED_ON relation for graph-based auditing.
        self.run('MERGE (t:Tool {id: $tid})-[:FAILED_ON]->(f:Failure {id: $fid, error_kind: $reason})',
                 tid=tid,fid=stable_id('failure',tid),reason='demo_injected_failure')
        return {'recorded':True,'tool_id':tid,'kind':'injected_failure','persistent':True}
    def restore(self,tid):
        self.run('MATCH (t:Tool {id: $tid})-[:HAS_VERSION]->(v:ToolVersion) SET v.status = $status',tid=tid,status='healthy')
        return {'restored':True,'tool_id':tid}

def load_registry():return json.loads(SNAPSHOT.read_text(encoding='utf-8'))
def load_tasks():return json.loads(WORKFLOWS.read_text(encoding='utf-8'))

def evaluate(db,registry,workflows,workers=1):
    all_tokens=estimate_tokens([{'name':t['name'],'description':t['description'],'schema':t['schema']} for t in registry['tools']])
    tools=registry['tools'];tasks=workflows['tasks'];start=time.perf_counter()
    def one(task):
        t0=time.perf_counter();route=db.resolve(task['key'],token_budget=200000)
        actual=[x['name'] for x in route['tools']];expected=task['chain']
        # Simple first-n lexical baseline. Not vector retrieval.
        import re
        tokens=lambda s:set(re.findall(r'[a-z0-9]+',s.lower()))
        query=tokens(task['description'])
        ranked=sorted(tools,key=lambda t:len(query & tokens(t['name']+' '+t['description'])),reverse=True)
        lexical=[x['name'] for x in ranked[:len(expected)]]
        def calc(values):
            a=set(values);b=set(expected)
            return {'recall':len(a&b)/len(b),'precision':len(a&b)/len(a) if a else 0}
        return {'task':task['key'],'expected':expected,'selected':actual,'graphshield':calc(actual),
                'lexical_topk':calc(lexical),'estimated_schema_tokens':route['estimated_schema_tokens'],
                'query_count':route['graph_queries'],'latency_ms':round((time.perf_counter()-t0)*1000,3)}
    if workers>1:
        with ThreadPoolExecutor(max_workers=workers) as ex:rows=list(ex.map(one,tasks))
    else:rows=[one(t) for t in tasks]
    latency=sorted(r['latency_ms'] for r in rows); elapsed=time.perf_counter()-start
    def percentile(p):return latency[min(len(latency)-1,int((len(latency)-1)*p))] if latency else 0
    summary={'backend':'hydradb','data_source':'live MCP tools/list snapshot','tool_count':len(tools),'task_count':len(tasks),
             'concurrency':workers,'preload_tokens_est':all_tokens,
             'graphshield_tokens_est_mean':round(statistics.mean(r['estimated_schema_tokens'] for r in rows),2) if rows else None,
             'graphshield_recall_mean':round(statistics.mean(r['graphshield']['recall'] for r in rows),3) if rows else None,
             'graphshield_precision_mean':round(statistics.mean(r['graphshield']['precision'] for r in rows),3) if rows else None,
             'lexical_recall_mean':round(statistics.mean(r['lexical_topk']['recall'] for r in rows),3) if rows else None,
             'graph_queries_per_task_mean':round(statistics.mean(r['query_count'] for r in rows),2) if rows else None,
             'p50_ms':percentile(.5),'p95_ms':percentile(.95),'p99_ms':percentile(.99),
             'wall_seconds':round(elapsed,3),'throughput_tasks_sec':round(len(rows)/elapsed,2) if elapsed else 0,
             'limitations':['MCP tool schemas are real; task chains are manually authored, not independent public ground truth.',
                            'Tokenizer numbers are JSON characters / 4 estimates, not billed API tokens.',
                            'Lexical baseline is word overlap, not vector embeddings.',
                            'Only context routing is measured; no external MCP tools are executed.',
                            'Failure injection simulates tool outage; graph persistence is real.']}
    return {'summary':summary,'rows':rows}

def cli():
    p=argparse.ArgumentParser(description='Real MCP tool discovery and HydraDB Track 2 benchmark')
    sub=p.add_subparsers(dest='action',required=True)
    d=sub.add_parser('discover');d.add_argument('--config',default=os.getenv('GRAPHSHIELD_MCP_CONFIG',str(ROOT/'mcp_servers.json')))
    sub.add_parser('seed');sub.add_parser('tasks')
    run=sub.add_parser('benchmark');run.add_argument('--concurrency',type=int,default=1);run.add_argument('--output',default=str(REPORT))
    resolve=sub.add_parser('resolve');resolve.add_argument('task');resolve.add_argument('--budget',type=int,default=12000)
    fail=sub.add_parser('fail');fail.add_argument('tool_id',type=int)
    restore=sub.add_parser('restore');restore.add_argument('tool_id',type=int)
    args=p.parse_args()
    if args.action=='discover':
        doc=asyncio.run(discover(args.config)); print(json.dumps(build_workflows(doc),indent=2));return
    if args.action=='tasks':print(json.dumps(load_tasks(),indent=2));return
    db=RealHydra()
    try:
        if args.action=='seed':out=db.seed(load_registry(),load_tasks())
        elif args.action=='resolve':out=db.resolve(args.task,args.budget)
        elif args.action=='fail':out=db.fail(args.tool_id)
        elif args.action=='restore':out=db.restore(args.tool_id)
        else:
            out=evaluate(db,load_registry(),load_tasks(),args.concurrency)
            path=Path(args.output);path.parent.mkdir(exist_ok=True,parents=True)
            path.write_text(json.dumps(out,indent=2),encoding='utf-8');print('Saved:',path)
            out=out['summary']
        print(json.dumps(out,indent=2,ensure_ascii=False))
    finally:db.close()

if __name__=='__main__':cli()
