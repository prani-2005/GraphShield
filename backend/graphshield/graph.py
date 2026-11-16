"""Graph repository. Live backend executes real directed HydraDB Cypher traversals.

The mock backend is isolated and only for development tests, never for HydraDB claims.
"""
from __future__ import annotations
import os
import threading
from contextvars import ContextVar

_request_queries = ContextVar("graphshield_request_queries", default=None)

def begin_query_count():
    return _request_queries.set(0)

def current_query_count():
    return _request_queries.get() or 0

def end_query_count(token):
    _request_queries.reset(token)

def count_request_query():
    value = _request_queries.get()
    if value is not None:
        _request_queries.set(value + 1)
from collections import defaultdict
from .dataset import build_dataset

# IDs are disjoint and numeric. HydraDB matches nodes by id and accepts typed directed edges.
CAP_BASE=20000
ENTITY_BASE=40000
FAIL_BASE=50000
VERSION_BASE=60000

class InMemoryGraph:
    backend='mock'
    def __init__(self):
        self.lock=threading.RLock()
        self.data=None
        self.health={}
        self.weights=defaultdict(int)
        self.history=[]
        self.entity_resolutions={}
        self.queries=0
    def seed(self, data=None):
        with self.lock:
            self.data=data or build_dataset()
            self.health={t['id']:'healthy' for t in self.data['tools']}
            self.weights.clear(); self.history.clear(); self.entity_resolutions.clear()
            return {'tools':len(self.data['tools']),'tasks':len(self.data['tasks']),
                    'backend':self.backend}
    def _ensure(self):
        if self.data is None: raise RuntimeError('Run seed before resolve')
    def task(self,key):
        self._ensure(); self.queries+=1; count_request_query()
        return next((t for t in self.data['tasks'] if t['key']==key),None)
    def requirements(self,cap):
        self.queries+=1; count_request_query()
        return list(self.data['dependencies'].get(cap,[]))
    def candidates(self,cap):
        self.queries+=1; count_request_query()
        return [dict(t, status=self.health[t['id']], learned=self.weights[t['id']])
                for t in self.data['tools'] if t['capability']==cap]
    def entity(self,key):
        self.queries+=1; count_request_query()
        return self.entity_resolutions.get(key)
    def resolve_entity(self,key,value,source='manual'):
        self.entity_resolutions[key]={'key':key,'value':value,'source':source}
    def mark_failure(self,tool_id,kind='unavailable'):
        self._ensure()
        if tool_id not in self.health: raise KeyError(tool_id)
        self.health[tool_id]='unhealthy'
        self.history.append({'tool_id':tool_id,'type':kind})
    def mark_healthy(self,tool_id):
        self._ensure()
        if tool_id not in self.health: raise KeyError(tool_id)
        self.health[tool_id]='healthy'
    def reward(self,tool_ids):
        for tid in tool_ids: self.weights[tid]+=1
    def close(self):pass

class HydraGraph:
    """Bolt adapter. All graph traversals are real MATCH relationships, not JSON registry scans."""
    backend='hydradb'
    def __init__(self):
        from neo4j import GraphDatabase
        self.driver=GraphDatabase.driver(os.getenv('HYDRADB_BOLT','bolt://127.0.0.1:7687'),
              auth=('neo4j',os.getenv('HYDRADB_TOKEN','local-development-token-32-bytes')))
        self.database=os.getenv('HYDRADB_GRAPH','default')
        self.queries=0
        self.data=None
        self.lock=threading.RLock()
    def run(self,query, **params):
        with self.driver.session(database=self.database) as session:
            result=session.run(query,**params)
            if query.lstrip().upper().startswith(('MERGE','CREATE','UNWIND','MATCH')) and ' RETURN ' not in query.upper():
                result.consume(); rows=[]
            else:
                rows=[dict(rec) for rec in result]
        with self.lock: self.queries+=1
        count_request_query()
        return rows
    def seed(self,data=None):
        """Idempotent seed; 160 tools and explicit relationships.
        Does not delete arbitrary existing graph data: IDs are project-owned range.
        """
        d=data or build_dataset();self.data=d
        caps={name:CAP_BASE+i for i,(name,_) in enumerate(d['capabilities'])}
        # HydraDB requires every creation to involve an edge, so MERGE edge endpoints.
        for t in d['tools']:
            cid=caps[t['capability']]; vid=VERSION_BASE+(t['id']-10000)
            self.run('MERGE (c:Skill {id: $c, name: $cn})-[:IMPLEMENTED_BY]->(t:Tool {id: $t, name: $tn, description: $desc, priority: $priority})',
                     c=cid,cn=t['capability'],t=t['id'],tn=t['name'],desc=t['description'],priority=t['priority'])
            self.run('MERGE (t:Tool {id: $t})-[:HAS_VERSION]->(v:ToolVersion {id: $v, status: $status, version: $version, reward: 0})',
                     t=t['id'],v=vid,status='healthy',version=t['version'])
        for task in d['tasks']:
            self.run('MERGE (t:Task {id: $t, task_key: $key, description: $description, entity_key: $entity})-[:REQUIRES]->(s:Skill {id: $s, name: $name})',
                t=task['id'],key=task['key'],description=task['description'],entity=task['entity_key'],
                s=caps[task['target']],name=task['target'])
        for skill, prereqs in d['dependencies'].items():
            for prereq in prereqs:
                self.run('MERGE (a:Skill {id: $a, name: $an})-[:DEPENDS_ON]->(b:Skill {id: $b, name: $bn})',
                         a=caps[skill],an=skill,b=caps[prereq],bn=prereq)
        return {'tools':len(d['tools']),'tasks':len(d['tasks']),'backend':self.backend,
                'queries':self.queries}
    def task(self,key):
        rows=self.run('MATCH (t:Task)-[:REQUIRES]->(s:Skill) WHERE t.task_key = $key RETURN t.id AS id, t.task_key AS task_key, t.entity_key AS entity_key, s.name AS target',key=key)
        return {'id':rows[0]['id'],'key':rows[0]['task_key'],'target':rows[0]['target'],
                'entity_key':rows[0]['entity_key']} if rows else None
    def requirements(self,cap):
        rows=self.run('MATCH (s:Skill)-[:DEPENDS_ON]->(p:Skill) WHERE s.name = $cap RETURN p.name AS name',cap=cap)
        return [r['name'] for r in rows]
    def candidates(self,cap):
        rows=self.run('MATCH (s:Skill)-[:IMPLEMENTED_BY]->(t:Tool)-[:HAS_VERSION]->(v:ToolVersion) WHERE s.name = $cap RETURN t.id AS id, t.name AS name, t.description AS description, t.priority AS priority, v.status AS status, v.reward AS learned, v.version AS version',cap=cap)
        if self.data is None:
            # Schema can be generated without needing the local data after re-start.
            from .dataset import build_dataset
            self.data=build_dataset()
        schema_by_id={t['id']:t['schema'] for t in self.data['tools']}
        return [dict(r, capability=cap, schema=schema_by_id.get(int(r['id']),{})) for r in rows]
    def entity(self,key):
        rows=self.run('MATCH (e:Entity)-[:RESOLVED_AS]->(r:Resolution) WHERE e.entity_key = $key RETURN r.value AS value, r.source AS source',key=key)
        return {'key':key,'value':rows[0]['value'],'source':rows[0]['source']} if rows else None
    def resolve_entity(self,key,value,source='manual'):
        # Explicitly project-owned deterministic IDs: entity_0...company_11 only.
        if not key.startswith('company_') or not key[8:].isdigit() or int(key[8:])>=1000:
            raise ValueError('Demo entities must be company_<0..999>')
        k=int(key[8:]); eid=ENTITY_BASE+k; rid=ENTITY_BASE+2000+k
        self.run('MERGE (e:Entity {id: $eid, entity_key: $key})-[:RESOLVED_AS]->(r:Resolution {id: $rid, value: $value, source: $source})',eid=eid,rid=rid,key=key,value=value,source=source)
        self.run('MATCH (r:Resolution {id: $rid}) SET r.value = $value, r.source = $source',rid=rid,value=value,source=source)
    def mark_failure(self,tool_id,kind='unavailable'):
        vid=VERSION_BASE+(tool_id-10000)
        self.run('MATCH (t:Tool {id: $tid})-[:HAS_VERSION]->(v:ToolVersion {id: $vid}) SET v.status = $status',tid=tool_id,vid=vid,status='unhealthy')
        fid=FAIL_BASE+(tool_id-10000)
        self.run('MERGE (t:Tool {id: $tid})-[:FAILED_ON]->(f:Failure {id: $fid, error_kind: $kind})',tid=tool_id,fid=fid,kind=kind)
    def mark_healthy(self,tool_id):
        self.run('MATCH (t:Tool {id: $tid})-[:HAS_VERSION]->(v:ToolVersion) SET v.status = $status',tid=tool_id,status='healthy')
    def reward(self,tool_ids):
        # SET values from locally fetched actual graph reward; safe demo sequential loop.
        for tid in tool_ids:
            rows=self.run('MATCH (t:Tool {id: $tid})-[:HAS_VERSION]->(v:ToolVersion) RETURN v.reward AS reward',tid=tid)
            if rows:
                value=int(rows[0]['reward'] or 0)+1
                self.run('MATCH (t:Tool {id: $tid})-[:HAS_VERSION]->(v:ToolVersion) SET v.reward = $reward',tid=tid,reward=value)
    def close(self):self.driver.close()

def make_graph():
    if os.getenv('GRAPH_BACKEND','mock').lower()=='hydradb': return HydraGraph()
    return InMemoryGraph()
