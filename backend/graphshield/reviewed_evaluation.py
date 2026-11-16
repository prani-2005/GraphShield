"""Four-arm, five-iteration evaluation on explicitly human-reviewed tasks only.

This module refuses to invent a train/held-out dataset. Users must supply
real reviewed labels in data/evaluation_tasks.json. It records actual metrics
when execution is possible, including missing optional embedding dependencies.
"""
from __future__ import annotations
import json
import random
import statistics
import time
from pathlib import Path
from .real_mcp import RealHydra, load_registry, load_tasks, stable_id
from .enterprise_runtime import _embedding_rank, _terms
from .resolver import estimate_tokens

ROOT=Path(__file__).resolve().parent.parent
EVAL=ROOT/'data'/'evaluation_tasks.json'
REPORT=ROOT/'results'/'four_system_learning.json'


def read_reviewed():
    if not EVAL.exists():
        raise FileNotFoundError('Create data/evaluation_tasks.json using REVIEWED_EVALUATION.md; no generated ground truth is allowed')
    doc=json.loads(EVAL.read_text(encoding='utf-8'))
    if not isinstance(doc,list):raise ValueError('Evaluation file must contain a list')
    tasks={t['key'] for t in load_tasks()['tasks']}
    tools={t['key'] for t in load_registry()['tools']}
    seen=set()
    for row in doc:
        if row.get('review_status')!='human_verified':raise ValueError('Unverified task: '+str(row.get('id')))
        if row.get('split') not in ('train','heldout'):raise ValueError('Task must be train or heldout')
        if row.get('task_key') not in tasks:raise ValueError('Unknown reviewed workflow: '+str(row.get('task_key')))
        if not row.get('gold_tool_keys') or any(k not in tools for k in row['gold_tool_keys']):
            raise ValueError('Gold chain contains absent tools: '+str(row.get('id')))
        if row.get('id') in seen:raise ValueError('Duplicate evaluated task ID')
        seen.add(row['id'])
    if not any(x['split']=='train' for x in doc) or not any(x['split']=='heldout' for x in doc):
        raise ValueError('Both train and heldout data are required')
    return doc


def _score(selected,gold):
    a=set(selected);b=set(gold)
    return {'first_try_success':int(a==b),
            'dependency_recall':len(a&b)/len(b) if b else 1,
            'precision':len(a&b)/len(a) if a else 0}


def run(iterations=5,seeds=(7,11,23),embeddings=True):
    if iterations!=5:raise ValueError('Spec requires exactly five iterations')
    data=read_reviewed(); registry=load_registry();tools=registry['tools'];tool_by_key={x['key']:x for x in tools}
    held=[x for x in data if x['split']=='heldout'];train=[x for x in data if x['split']=='train']
    workflows={x['key']:x for x in load_tasks()['tasks']}
    result=[];missing_embedding=False
    db=RealHydra(); prior={}
    try:
        # Back up only the route weights we're permitted to change.
        affected={key for row in train for key in row['gold_tool_keys']}
        for key in affected:
            tid=stable_id('tool',key)
            rows=db.run('MATCH (t:Tool {id: $tid})-[:HAS_VERSION]->(v:ToolVersion) RETURN v.reward AS reward',tid=tid)
            if rows:prior[key]=int(rows[0].get('reward') or 0)
        for seed in seeds:
            rng=random.Random(seed)
            # Reset before each seed to avoid cross-seed contamination.
            for key,value in prior.items():
                db.run('MATCH (t:Tool {id: $tid})-[:HAS_VERSION]->(v:ToolVersion) SET v.reward = $reward',
                       tid=stable_id('tool',key),reward=value)
            for iteration in range(iterations+1):
                for row in held:
                    gold=row['gold_tool_keys'];work=workflows[row['task_key']]
                    expected_n=len(gold)
                    task_terms=_terms(row['prompt'])
                    candidate=sorted(tools,key=lambda t:-len(task_terms & _terms(t['name']+' '+t['description'])))[:expected_n]
                    vector=[]
                    if embeddings and not missing_embedding:
                        try:
                            vector=_embedding_rank({'description':row['prompt']},tools,expected_n)
                        except (ImportError,RuntimeError):missing_embedding=True
                    # The cold graph route is evaluated without feedback from this seed.
                    # We capture its initial route at iteration zero, then reuse it.
                    if iteration==0:
                        pass
                    graph=db.resolve(row['task_key'])
                    selected=[t['tool_key'] for t in graph['tools']]
                    for system,keys in [
                        ('preload_all',[t['key'] for t in tools]),
                        ('embedding_top_k',[t['key'] for t in vector] if not missing_embedding else None),
                        ('graphshield_learned',selected)]:
                        if keys is None:continue
                        metrics=_score(keys,gold)
                        result.append({'seed':seed,'iteration':iteration,'task_id':row['id'],
                                       'system':system,**metrics,
                                       'tool_count':len(keys),'schema_tokens_est':estimate_tokens([
                                           {'name':tool_by_key[k]['name'],'description':tool_by_key[k]['description'],
                                            'schema':tool_by_key[k]['schema']} for k in keys]),
                                       'graph_queries':graph['graph_queries'] if system=='graphshield_learned' else 0})
                    # A frozen graph baseline: initial provider preferences saved at iteration 0.
                    if iteration==0:
                        row.setdefault('_cold_keys_by_seed',{})[str(seed)]=list(selected)
                    cold=row['_cold_keys_by_seed'][str(seed)]
                    result.append({'seed':seed,'iteration':iteration,'task_id':row['id'],
                                   'system':'graphshield_cold',**_score(cold,gold),
                                   'tool_count':len(cold),'schema_tokens_est':estimate_tokens([
                                       {'name':tool_by_key[k]['name'],'description':tool_by_key[k]['description'],
                                        'schema':tool_by_key[k]['schema']} for k in cold]),
                                   'graph_queries':0,
                                   'caveat':'Frozen first-resolved plan; no repeated graph lookup in baseline'})
                if iteration < iterations:
                    # Only training records can update learned reward edges.
                    train_batch=train[:];rng.shuffle(train_batch)
                    for task in train_batch:
                        db.feedback(task['gold_tool_keys'],True)
        series=[]
        for system in sorted({r['system'] for r in result}):
            for iteration in range(iterations+1):
                vals=[r for r in result if r['system']==system and r['iteration']==iteration]
                if not vals:continue
                series.append({'system':system,'iteration':iteration,
                               'first_try_plan_success_mean':round(statistics.mean(x['first_try_success'] for x in vals),4),
                               'dependency_recall_mean':round(statistics.mean(x['dependency_recall'] for x in vals),4),
                               'schema_tokens_est_mean':round(statistics.mean(x['schema_tokens_est'] for x in vals),2),
                               'samples':len(vals)})
        report={'benchmark':'human-reviewed source-defined tasks','train_count':len(train),'heldout_count':len(held),
                'iterations':iterations,'seeds':list(seeds),'series':series,'rows':result,
                'missing_embedding':missing_embedding,
                'limitations':['Existing task-to-skill edges are curated.',
                  'Successful gold-route rewards are supervision, not observed execution success.',
                  'Measured first-try plan equality is not actual downstream task completion.',
                  'Token values are estimated, not LLM API usage.',
                  'No automatic improvement is claimed if the curve is flat.']}
        REPORT.parent.mkdir(parents=True,exist_ok=True)
        REPORT.write_text(json.dumps(report,indent=2),encoding='utf-8')
        return report
    finally:
        for key,value in prior.items():
            try:db.run('MATCH (t:Tool {id: $tid})-[:HAS_VERSION]->(v:ToolVersion) SET v.reward = $reward',
                       tid=stable_id('tool',key),reward=value)
            except Exception:pass
        db.close()
