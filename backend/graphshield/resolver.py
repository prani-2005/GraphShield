"""Resolve relevant tool schemas through bounded directed graph relationships."""
from __future__ import annotations
import json
from dataclasses import dataclass
from .graph import begin_query_count, current_query_count, end_query_count

class ResolutionError(Exception): pass

@dataclass
class Resolver:
    graph: object
    max_depth: int = 5
    max_tools: int = 12

    def resolve(self,task_key,token_budget=2400):
        token = begin_query_count()
        try:
            return self._resolve(task_key, token_budget)
        finally:
            end_query_count(token)

    def _resolve(self,task_key,token_budget):
        task=self.graph.task(task_key)
        if not task: raise ResolutionError(f'Unknown task key: {task_key}. Seed first.')
        ordered=[]; visited=set(); active=set(); traversed=[]
        def walk(cap, depth):
            if depth>self.max_depth: raise ResolutionError('Graph dependency depth exceeded')
            if cap in active: raise ResolutionError('Cycle in skill dependencies')
            if cap in visited:return
            active.add(cap)
            for dependency in self.graph.requirements(cap):
                traversed.append({'from':cap,'type':'DEPENDS_ON','to':dependency})
                walk(dependency,depth+1)
            active.remove(cap);visited.add(cap);ordered.append(cap)
        walk(task['target'],0)
        if len(ordered)>self.max_tools:raise ResolutionError('Too many required skills')
        selected=[]; rejected=[]
        for cap in ordered:
            candidates=self.graph.candidates(cap)
            if not candidates: raise ResolutionError(f'No tool for {cap}')
            # Query actual version health and learned weights from graph, not local cache.
            candidates.sort(key=lambda t:(t.get('status')=='healthy',int(t.get('priority') or 0)+2*int(t.get('learned') or 0),-int(t['id'])),reverse=True)
            healthy=[t for t in candidates if t.get('status')=='healthy']
            if not healthy:raise ResolutionError(f'No healthy version for {cap}')
            chosen=healthy[0]
            selected.append(chosen)
            traversed.append({'from':cap,'type':'IMPLEMENTED_BY','to':chosen['name']})
            rejected.extend([{'name':c['name'],'reason':'unhealthy version' if c.get('status')!='healthy' else 'lower routing priority'} for c in candidates if c['id']!=chosen['id']][:3])
        # Never silently omit required tools to hit a budget: return a clear error.
        schema_tokens=estimate_tokens([{'name':t['name'],'schema':t['schema']} for t in selected])
        if schema_tokens>token_budget:raise ResolutionError(f'Required schemas need ~{schema_tokens} estimated tokens; budget {token_budget}')
        entity=self.graph.entity(task['entity_key'])
        return {'task':task_key,'backend':self.graph.backend,'tools':selected,
                'selected_names':[t['name'] for t in selected],
                'resolved_entity':entity,'skill_path':ordered,'graph_edges':traversed,
                'rejected':rejected,'estimated_schema_tokens':schema_tokens,
                'graph_queries':current_query_count()}

def estimate_tokens(value):
    # Character-length proxy, NOT provider-billed or tokenizer-measured tokens.
    return (len(json.dumps(value,sort_keys=True,ensure_ascii=False))+3)//4
