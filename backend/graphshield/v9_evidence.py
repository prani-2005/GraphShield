"""V9 dashboard evidence endpoints: render actual saved data; never synthesize runs.

The older held-out study uses a narrower set of measured/estimated metrics.
Missing metrics are intentionally null, not inferred or estimated.
"""
from __future__ import annotations
import json
from pathlib import Path
from .real_mcp import SNAPSHOT,WORKFLOWS
from .enterprise import REVIEW_FILE
from .refund_experiment import OUTPUT as HELD_OUT
from .review_edges import summarize as review_summary


def _load_json(path:Path):
    if not path.is_file():return None
    return json.loads(path.read_text(encoding='utf-8'))


def learning_evidence():
    """Actual five-iteration, three-seed HydraDB-backed refund study, if run."""
    doc=_load_json(HELD_OUT)
    if not doc:return None
    remap={'first_try_success':'task_success','injected_failures':'failed_attempts_per_task','estimated_tokens':'tokens_per_task'}
    rows=[]
    for row in doc.get('summary',[]):
        out={'system':row['system'],'iteration':row['iteration'],
             'round_trips_per_task':None,'p95_latency_ms':None}
        for src,dst in remap.items():out[dst]=row.get(src)
        rows.append(out)
    return {'backend':'hydradb','experiment':doc.get('experiment'), 'seeds':doc.get('seeds',[]),
            'split':{'train':doc.get('train_cases'),'held_out':doc.get('held_out_cases')},
            'tokens_basis':'estimated',
            'providers':[{'name':k,'failure_rate':v,'latency_ms':None} for k,v in doc.get('provider_failure_assumptions',{}).items()],
            'systems':list(dict.fromkeys(r['system'] for r in rows)),'summary':rows,
            'limitations':doc.get('limitations',[])+['Model round-trips and p95 latency were not collected by this evaluation.',
            'The first-try success and injected failure rate are outcomes from simulated provider failure draws, not LLM end-to-end success.']}


def benchmark_evidence():
    reg=_load_json(SNAPSHOT)
    if not reg:return None
    from .resolver import estimate_tokens
    tools=reg.get('tools',[])
    estimate=estimate_tokens([{'name':t.get('name'),'description':t.get('description'),'schema':t.get('schema',{})} for t in tools])
    candidates=_load_json(REVIEW_FILE) or {}
    edges=candidates.get('edges',[])
    review=None
    try:review=review_summary()
    except FileNotFoundError:pass
    checked=review.get('reviewed',0) if review else 0
    # Count *candidate* relations; not confirmed persisted Cypher edges.
    # The schema candidate records use producer/consumer/field, not a graph DB edge type.
    from .enterprise_runtime import flat_ablation
    ablation_error=None
    try:
        ab=flat_ablation()  # live HydraDB graph traversal
        rows=ab.get('rows',[])
        systems=[{'system':'graphshield','label':'HydraDB curated graph traversal',
                  'dependency_recall':ab.get('graph_mean_recall'),'plan_correctness':None,'queries_per_case':None},
                 {'system':'flat_lexical','label':'Flat lexical matching',
                  'dependency_recall':ab.get('flat_mean_recall'),'plan_correctness':None,'queries_per_case':None}]
        sample_plan=[]
        if rows:
            task=rows[0]['task']
            workflows=_load_json(WORKFLOWS) or {}
            match=next((x for x in workflows.get('tasks',[]) if x['key']==task),None)
            sample_plan=[{'tool':name,'consumes':[],'produces':[]} for name in match.get('chain',[])] if match else []
    except Exception as exc:
        rows=[];systems=[];sample_plan=[];ablation_error=str(exc)[:250]
    sample=[{'tool':e.get('producer'),'relation':'candidate output to input','datatype':e.get('field'),
             'confidence':e.get('confidence'), 'hand_check':None} for e in edges[:25]]
    return {'registry':{'real_tools':len(tools), 'distractor_tools':None,'total_tools':len(tools),
                        'preload_all_tokens':estimate,'tokens_basis':'estimated','distractor_sources':[]},
            'dataflow_edges':{'produces':len(edges), 'consumes':len(edges),
                              'mean_confidence':round(sum(e.get('confidence',0) for e in edges)/len(edges),3) if edges else None,
                              'hand_check':{'sampled':checked,'correct':None,'precision':review.get('precision') if review else None}},
            'multi_hop':{'cases':len(rows),'systems':systems},
            'example_plan':sample_plan,'sample_edges':sample,
            'limitations':['Dataflow counts describe unreviewed candidate output/input compatibility records, NOT confirmed edges stored in HydraDB.',
                           'Plan sequence comes from a human-curated workflow; not derived by backward dataflow traversal.',
                           'Preload schema-token estimate uses chars/4, not API usage.',
                           'Plan correctness and query counts were not collected in this comparison.'] +
                           ([f'Live ablation unavailable: {ablation_error}'] if ablation_error else [])}
