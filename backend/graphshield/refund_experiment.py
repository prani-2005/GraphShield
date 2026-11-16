"""Five-iteration, three-seed held-out experiment using Olist-derived cases.

Provider outcomes are DETERMINISTIC INJECTED FAULTS, not observed production
incidents; LLM token counts are NOT invented. Routing and reward state are
resolved and updated through the real HydraDB engine.
"""
from __future__ import annotations
import hashlib,json,math,statistics,time
from pathlib import Path
from .refund_desk import ROOT,save_cases
from .real_mcp import RealHydra,stable_id,load_registry
from .resolver import estimate_tokens

OUTPUT=ROOT/'results'/'refund_desk_heldout_injected_faults.json'
PROVIDERS={'orders_primary':0.43,'orders_replica':0.07,'orders_cache':0.14}
TASKS={'late_delivery_refund':'refund_desk_first_request',
       'payment_question':'refund_desk_payment_question',
       'wrong_item_inquiry':'refund_desk_wrong_item',
       'order_status':'refund_desk_order_status'}

def fails(case_id,provider,seed,iteration):
    """Stable Bernoulli trial; probability is a declared experimental assumption."""
    rate=PROVIDERS.get(provider,0.02)
    key=f'{seed}|{iteration}|{case_id}|{provider}'
    sample=int.from_bytes(hashlib.sha256(key.encode()).digest()[:8],'big')/2**64
    return sample<rate

def _confidence_bounds(values):
    return {'mean':round(statistics.mean(values),4),'min':round(min(values),4),'max':round(max(values),4)}

def _read_cases():
    p=ROOT/'data'/'refund_desk_cases.json'
    if not p.exists():save_cases()
    doc=json.loads(p.read_text(encoding='utf-8'))
    train=[x for x in doc['cases'] if x['split']=='train']
    held=[x for x in doc['cases'] if x['split']=='held_out']
    if len(train)!=100 or len(held)!=50:raise ValueError('Require 100 train and 50 held-out cases')
    if {x['order_id'] for x in train}&{x['order_id'] for x in held}:
        raise ValueError('Train / test order IDs overlap')
    return train,held

def _score(route,truth):
    selected={t['name'] for t in route['tools']}
    return len(selected&set(truth))/max(1,len(set(truth)))

def _first_order_provider(route):
    return next((t['server'] for t in route['tools'] if t['name']=='resolve_order'),'orders_primary')

def _set_reward(db,key,value):
    # Supported HydraDB anchored update; results persist between API processes.
    tid=stable_id('tool',key)
    db.run('MATCH (t:Tool {id: $tid})-[:HAS_VERSION]->(v:ToolVersion) SET v.reward = $reward',tid=tid,reward=max(-10,min(100,int(value))))

def run(iterations=5,seeds=(7,17,29)):
    if iterations!=5 or len(seeds)<3:raise ValueError('Use exactly 5 iterations and >=3 seeds')
    train,held=_read_cases();registry=load_registry();start=time.perf_counter()
    keys=['orders_primary::resolve_order','orders_replica::resolve_order','orders_cache::resolve_order']
    exists={t['key'] for t in registry['tools']}
    if not set(keys).issubset(exists):raise ValueError('Discover and seed 3 orders providers first')
    all_context=estimate_tokens([{'name':t['name'],'description':t['description'],'schema':t['schema']} for t in registry['tools']])
    db=RealHydra();records=[]
    original_rewards={}
    try:
        for key in keys:
            tid=stable_id('tool',key)
            row=db.run('MATCH (t:Tool {id: $tid})-[:HAS_VERSION]->(v:ToolVersion) RETURN v.reward AS reward',tid=tid)
            if not row:raise ValueError('Missing seeded HydraDB ToolVersion for '+key)
            original_rewards[key]=row[0].get('reward') or 0
        for seed in seeds:
            for key in keys:_set_reward(db,key,0)
            cold={k:db.resolve(k) for k in sorted(set(TASKS.values()))}
            for iteration in range(iterations):
                # Train on 100 case IDs without inspecting held-out outcomes.
                training_failures=0;training_successes=0
                chosen_provider=_first_order_provider(db.resolve('refund_desk_first_request'))
                for c in train:
                    failed=fails(c['case_id'],chosen_provider,seed,iteration)
                    training_failures+=int(failed);training_successes+=int(not failed)
                tool_key=chosen_provider+'::resolve_order'
                # Reward is derived from observed injected outcomes, not an arbitrary iteration index.
                # On 100 cases, a provider with high failure probability should lose priority.
                new_reward=max(-10,min(100,training_successes-2*training_failures))
                _set_reward(db,tool_key,new_reward)
                learned={k:db.resolve(k) for k in cold}
                for mode in ('preload_all_oracle','lexical_topk','graphshield_cold','graphshield_learned'):
                    success=[];recall=[];tokens=[];repeat_fail=[]
                    for c in held:
                        task=TASKS[c['intent']]
                        graph_route=learned[task] if mode=='graphshield_learned' else cold[task]
                        if mode=='lexical_topk':
                            q=set((c['intent']+' '+task.replace('_',' ')).lower().split())
                            ranked=sorted(registry['tools'],key=lambda x:-len(q & set((x['name']+' '+x['description']).lower().replace('_',' ').split())))
                            top=ranked[:len(c['gold_chain'])]
                            dependency_recall=len({x['name'] for x in top}&set(c['gold_chain']))/len(set(c['gold_chain']))
                            tok=estimate_tokens([{'name':x['name'],'schema':x['schema']} for x in top])
                        elif mode=='preload_all_oracle':
                            dependency_recall=1.0  # An ORACLE plan; not an LLM success claim.
                            tok=all_context
                        else:
                            dependency_recall=_score(graph_route,c['gold_chain']);tok=graph_route['estimated_schema_tokens']
                        provider=_first_order_provider(graph_route) if mode=='graphshield_learned' else 'orders_primary'
                        failed=fails(c['case_id'],provider,seed,iteration)
                        ok=dependency_recall==1.0 and not failed
                        success.append(float(ok));recall.append(dependency_recall);tokens.append(tok);repeat_fail.append(float(failed))
                    records.append({'seed':seed,'iteration':iteration+1,'system':mode,
                        'first_try_success':round(statistics.mean(success),4),
                        'dependency_recall':round(statistics.mean(recall),4),
                        'estimated_schema_tokens':round(statistics.mean(tokens),2),
                        'injected_provider_failures_per_case':round(statistics.mean(repeat_fail),4),
                        'train_provider':chosen_provider,'train_failures':training_failures,'learned_provider':_first_order_provider(learned['refund_desk_first_request']),
                        'learned_reward':new_reward})
        agg=[]
        for iteration in range(1,iterations+1):
            for mode in ('preload_all_oracle','lexical_topk','graphshield_cold','graphshield_learned'):
                sample=[x for x in records if x['system']==mode and x['iteration']==iteration]
                agg.append({'iteration':iteration,'system':mode,'first_try_success':_confidence_bounds([x['first_try_success'] for x in sample]),
                            'dependency_recall':_confidence_bounds([x['dependency_recall'] for x in sample]),
                            'injected_failures':_confidence_bounds([x['injected_provider_failures_per_case'] for x in sample]),
                            'estimated_tokens':_confidence_bounds([x['estimated_schema_tokens'] for x in sample])})
        result={'experiment':'Controlled Olist-source-linked provider fault evaluation',
                'train_cases':100,'held_out_cases':50,'iterations':iterations,'seeds':list(seeds),
                'observed_from':'HydraDB route traversal with persistent reward updates + deterministic injected provider faults',
                'provider_failure_assumptions':PROVIDERS,'records':records,'summary':agg,
                'duration_seconds':round(time.perf_counter()-start,2),
                'limitations':['Provider failure probabilities are invented and simulated; not production outages.',
                  'Preload-all uses an oracle gold chain and is NOT a measured LLM baseline.',
                  'Lexical top-k is not an embedding baseline.',
                  'No real LLM token, model round-trip or task-success results are claimed.',
                  'Gold task chains and scenario intents are hand-authored over real historical order IDs.',
                  'Failure-reward updates are written to real HydraDB ToolVersion nodes.'],
                'note':'Original provider rewards are restored after evaluation; any interrupted run should be reviewed before reusing graph state.'}
        OUTPUT.parent.mkdir(parents=True,exist_ok=True)
        OUTPUT.write_text(json.dumps(result,indent=2),encoding='utf-8')
        return result
    finally:
        try:
            for key,reward in original_rewards.items():_set_reward(db,key,reward)
        finally:db.close()

if __name__=='__main__':
    result=run()
    print('Saved',OUTPUT)
    for x in result['summary']:
        if x['system']=='graphshield_learned':print('Iteration',x['iteration'],'first-try success',x['first_try_success'])
