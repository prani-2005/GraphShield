"""Explicitly opt-in actual LLM benchmark on independently reviewed local tasks.

Makes billable external requests. Never silently runs by default.
"""
import argparse
import json
import statistics
from pathlib import Path
from .reviewed_evaluation import read_reviewed
from .enterprise_runtime import measured_llm_run, REPORT_DIR

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--execute-costly',action='store_true',help='Acknowledges real model API requests')
    p.add_argument('--limit',type=int,default=20)
    p.add_argument('--modes',nargs='+',default=['preload','graphshield'])
    a=p.parse_args()
    if not a.execute_costly:raise SystemExit('This makes billable requests. Pass --execute-costly only after configuring provider credentials.')
    reviewed=[t for t in read_reviewed() if t['split']=='heldout'][:a.limit]
    if not 20<=len(reviewed)<=30:raise SystemExit('Need at least 20 held-out reviewed tasks for an honest 20–30-task LLM benchmark')
    rows=[]
    for row in reviewed:
        for mode in a.modes:
            try:
                r=measured_llm_run(row['task_key'],mode,prompt=row['prompt'])
                rows.append({'task_id':row['id'],'mode':mode,'actual_usage':r['usage'],
                             'gold_capability_match_curated':r['gold_capability_match'],
                             'latency_ms':r['latency_ms'],'error':None})
            except Exception as e:
                rows.append({'task_id':row['id'],'mode':mode,'error':str(e)})
    summaries={}
    for mode in a.modes:
        subset=[x for x in rows if x['mode']==mode]
        good=[x for x in subset if not x['error']]
        summaries[mode]={'requests':len(subset),'errors':len(subset)-len(good),
                         'actual_prompt_tokens_mean':round(statistics.mean(x['actual_usage']['prompt_tokens'] for x in good),2) if good else None,
                         'actual_total_tokens_mean':round(statistics.mean(x['actual_usage']['total_tokens'] for x in good),2) if good else None,
                         'curated_capability_match_mean':round(statistics.mean(x['gold_capability_match_curated'] for x in good if x['gold_capability_match_curated'] is not None),3) if any(x['gold_capability_match_curated'] is not None for x in good) else None}
    result={'summary':summaries,'rows':rows,
            'disclosure':'Actual provider usage, but gold comparison is to curated workflow chains; no real MCP plan execution. Preload may exceed the model context window.'}
    REPORT_DIR.mkdir(exist_ok=True,parents=True)
    path=REPORT_DIR/'measured_agent_benchmark.json'
    path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'saved':str(path),'summary':summaries},indent=2))

if __name__=='__main__':main()
