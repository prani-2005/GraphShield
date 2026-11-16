"""Reproducible routing benchmark. Schema tokens are estimates, not LLM usage.

No claim about LLM rounds: graph query count and selection calls are separate.
"""
import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .dataset import build_dataset
from .graph import make_graph
from .resolver import Resolver,estimate_tokens


def closure(target, deps):
    output=set()
    def visit(s):
        if s in output:return
        output.add(s)
        for p in deps.get(s,[]):visit(p)
    visit(target)
    return output

def score(selected,ground_truth):
    selected=set(selected);truth=set(ground_truth)
    return {'recall':len(selected&truth)/len(truth) if truth else 1,
            'precision':len(selected&truth)/len(selected) if selected else 0}

def bench(graph, data, concurrency=1):
    resolver=Resolver(graph)
    bench_start=time.perf_counter()
    tools=data['tools']; rows=[]
    # Preload-all and TF-IDF-like lexical retrieval use exactly the same registry.
    # Lexical baseline is intentionally not misrepresented as embedding-vector top-k.
    all_tokens=estimate_tokens([{'name':t['name'],'schema':t['schema']} for t in tools])
    def one(task):
        tick=time.perf_counter()
        route=resolver.resolve(task['key'],token_budget=99999)
        latency_ms=round((time.perf_counter()-tick)*1000,3)
        truth=closure(task['target'],data['dependencies'])
        chosen_caps=[t['capability'] for t in route['tools']]
        # Lexical top-k: query compared with schema names, cannot infer deps by graph.
        words=set(task['description'].lower().replace('_',' ').split())
        scored=sorted(tools,key=lambda t:len(words&set((t['name']+' '+t['description']).lower().replace('_',' ').split())),reverse=True)
        lexical=scored[:len(truth)]
        return {'task':task['key'],'backend':graph.backend,'graphshield':{
             **score(chosen_caps,truth),'schema_tokens_est':route['estimated_schema_tokens'],
             'graph_queries':route['graph_queries'],'latency_ms':latency_ms,
             'tool_count':len(route['tools'])},
             'preload_all':{**score([t['capability'] for t in tools],truth),
                           'schema_tokens_est':all_tokens,'tool_count':len(tools)},
             'lexical_topk':{**score([t['capability'] for t in lexical],truth),
                             'schema_tokens_est':estimate_tokens([{'name':t['name'],'schema':t['schema']} for t in lexical]),
                             'tool_count':len(lexical)}}
    if concurrency>1:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            rows=list(pool.map(one,data['tasks']))
    else:rows=[one(t) for t in data['tasks']]
    def avg(key,metric):return round(statistics.mean(r[key][metric] for r in rows),3)
    total_seconds=time.perf_counter()-bench_start
    summary={'total_wall_seconds':round(total_seconds,3),'throughput_tasks_per_second':round(len(rows)/total_seconds,3) if total_seconds>0 else 0,'backend':graph.backend,'task_count':len(rows),'tools_in_registry':len(tools),
             'concurrency':concurrency,'preload_tokens_est_mean':avg('preload_all','schema_tokens_est'),
             'graphshield_tokens_est_mean':avg('graphshield','schema_tokens_est'),
             'graphshield_recall_mean':avg('graphshield','recall'),
             'graphshield_precision_mean':avg('graphshield','precision'),
             'lexical_recall_mean':avg('lexical_topk','recall'),
             'graph_query_count_mean':avg('graphshield','graph_queries'),
             'graphshield_p50_latency_ms':round(statistics.median(r['graphshield']['latency_ms'] for r in rows),3),
             'graphshield_p95_latency_ms':round(sorted(r['graphshield']['latency_ms'] for r in rows)[int(.95*(len(rows)-1))],3),
             'graphshield_p99_latency_ms':round(sorted(r['graphshield']['latency_ms'] for r in rows)[int(.99*(len(rows)-1))],3),
             'notes':['Token estimates use JSON length/4; not actual LLM tokenizer results.',
                      'Latency measures routing only; preload and lexical latency not measured.',
                      'Lexical baseline is token-overlap top-k, not vector embeddings.',
                      'Mock backend does not constitute HydraDB performance evidence.']}
    return {'summary':summary,'tasks':rows}

def run_cli():
    p=argparse.ArgumentParser();p.add_argument('--seed',action='store_true');p.add_argument('--concurrency',type=int,default=1);p.add_argument('--output',default='results/benchmark.json');p.add_argument('--tools',type=int,default=160);p.add_argument('--tasks',type=int,default=48)
    a=p.parse_args(); data=build_dataset(a.tools,a.tasks);graph=make_graph()
    try:
        if a.seed:print('Seed:',graph.seed(data))
        result=bench(graph,data,a.concurrency)
        path=Path(a.output);path.parent.mkdir(exist_ok=True,parents=True)
        path.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result['summary'],indent=2))
        print('Saved:',path)
    finally:graph.close()
if __name__=='__main__':run_cli()
