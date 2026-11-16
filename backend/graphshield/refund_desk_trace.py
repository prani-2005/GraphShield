"""Evidence-first trace: real MCP calls selected by real HydraDB traversal.

No LLM reasoning is impersonated. The orchestration policy is deterministic until
an optional external LLM is configured separately. Trace events identify their
provenance and count actual MCP calls and DB queries separately.
"""
import json, time
from .refund_desk import _order, delay, eligibility, load_policy
from .real_mcp import RealHydra
from .demo_features import execute_readonly

FIRST='refund_desk_first_request'
FOLLOW='refund_desk_followup'

def assert_order(order_id):
    if not isinstance(order_id,str) or not 1<=len(order_id)<=70 or not all(c.isalnum() or c in '-_' for c in order_id):
        raise ValueError('Invalid historical order ID')
    if _order(order_id) is None:raise ValueError('Order ID not found in the original Olist CSVs')

def stream_case(order_id, followup=False, simulate_failure=False, execute_mcp=True):
    """Generator of dict events for use in JSON or SSE; execute_mcp=False is for plan-only debugging."""
    assert_order(order_id)
    db=RealHydra(); begin=time.perf_counter();calls=0;errors=0
    entity_key='refund_desk_order:'+order_id
    try:
        entity=db.get_entity(entity_key)
        cache_hit=bool(entity)
        # Always demonstrate the lookup if no entity exists. Never claim a cache hit
        # merely because the UI previously displayed this order in its selector.
        yield {'event':'goal','message':('For which items and how long will a refund take?' if followup else 'My order arrived late; investigate eligibility and prepare an approval draft.'),
               'order_id':order_id,'source':'operator-selected historical Olist order','model':'deterministic demonstration planner; no LLM tokens claimed'}
        yield {'event':'entity_cache','hit':cache_hit,'lookup_skipped':int(followup and cache_hit),
               'source':'HydraDB Entity-RESOLVED_AS->Resolution', 'entity_key':entity_key}
        task_key=FOLLOW if followup and cache_hit else FIRST
        route=db.resolve(task_key,entity_key=entity_key if cache_hit else None)
        yield {'event':'graph_context','task_key':task_key,'selected':[{'tool_key':t['tool_key'],'name':t['name'],'server':t['server']} for t in route['tools']],
               'rejected':route['rejected'],'traversal':route['graph_edges'],
               'graph_queries':route['graph_queries'],'estimated_tool_schema_tokens':route['estimated_schema_tokens'],
               'token_method':'estimated_chars_divided_by_4','hydradb':True}
        # No hidden synthetic tool results. Only MCP protocol calls are executed.
        for i,tool in enumerate(route['tools'],1):
            yield {'event':'step_started','index':i,'name':tool['name'],'provider':tool['server'],
                   'why':'Required by directed dependency traversal in HydraDB'}
            if not execute_mcp:
                yield {'event':'step_not_executed','index':i,'reason':'plan-only mode'}
                continue
            try:
                result=execute_readonly(tool['tool_key'],{'order_id':order_id})
                calls+=1
                if result.get('is_error'):
                    raise RuntimeError('MCP tool reported isError=true')
                yield {'event':'step_result','index':i,'tool_key':tool['tool_key'],'result':result,
                       'data_provenance':'Olist historical records or labeled invented demo policy'}
            except Exception as exc:
                errors+=1
                yield {'event':'step_failed','index':i,'tool_key':tool['tool_key'],'error':str(exc)[:350]}
                if simulate_failure:
                    db.fail(tool['id'])
                    yield {'event':'failure_recorded','tool_key':tool['tool_key'],'storage':'HydraDB','type':'SIMULATED OUTAGE'}
                    new_route=db.resolve(task_key,entity_key=entity_key if cache_hit else None)
                    alternate=next((x for x in new_route['tools'] if x['name']==tool['name']),None)
                    if alternate and alternate['tool_key']!=tool['tool_key']:
                        yield {'event':'rerouted','previous':tool['tool_key'],'alternative':alternate['tool_key'],'storage':'HydraDB'}
                        try:
                            fallback_result=execute_readonly(alternate['tool_key'],{'order_id':order_id});calls+=1
                            if fallback_result.get('is_error'):raise RuntimeError('MCP fallback reported error')
                            yield {'event':'step_result','index':i,'tool_key':alternate['tool_key'],'result':fallback_result,'recovered':True}
                        except Exception as fallback_error:
                            errors+=1;yield {'event':'step_failed','index':i,'error':str(fallback_error)[:350],'fallback':True}
                # Do not silently pretend a failed dependency succeeded.
                if not simulate_failure:break
        if not cache_hit and errors==0 and execute_mcp:
            db.save_entity(entity_key,json.dumps({'order_id':order_id,'resolved':True}),'Olist read-only MCP investigation')
            yield {'event':'entity_saved','entity_key':entity_key,'source':'HydraDB'}
        # Show demonstrative eligibility only when genuine source records exist.
        derived=eligibility(order_id)
        yield {'event':'assessment','derived':derived,'policy':load_policy()['source'],
               'approval_required':True,'real_refund_issued':False}
        yield {'event':'done','tool_calls':calls,'failed_attempts':errors,'entity_cache_hit':cache_hit,
               'elapsed_ms':round((time.perf_counter()-begin)*1000,2),'model_token_usage':None,
               'note':'Historical Olist evidence + invented demo policy; no real refund or customer message sent'}
    finally:db.close()
