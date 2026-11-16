"""Optional real LLM loop: exactly three meta-tools and provider-reported usage.

This uses an OpenAI-compatible Chat Completions endpoint. No token numbers are
estimated or manufactured. It never sends messages or issues real refunds.
"""
import json, os, time
from .real_mcp import RealHydra, load_registry
from .demo_features import execute_readonly
from .refund_desk import _order, load_policy

TOOLS=[
 {'type':'function','function':{'name':'graph_context','description':'Get the dependency-ordered minimal MCP tool schemas and rejected alternatives from HydraDB for an order-refund investigation.',
  'parameters':{'type':'object','properties':{'goal':{'type':'string'},'known_entities':{'type':'object','additionalProperties':{'type':'string'}}},'required':['goal']}}},
 {'type':'function','function':{'name':'call_tool','description':'Invoke a selected, read-only MCP tool with a validated Olist order ID. Never issues a refund.',
  'parameters':{'type':'object','properties':{'tool_key':{'type':'string'},'args':{'type':'object','additionalProperties':True}},'required':['tool_key','args']}}},
 {'type':'function','function':{'name':'report_outcome','description':'Report which selected tools completed or failed, to persist outcome evidence in HydraDB.',
  'parameters':{'type':'object','properties':{'success':{'type':'boolean'},'tool_keys':{'type':'array','items':{'type':'string'}}},'required':['success','tool_keys']}}}
]


def _normalize_llm_base(value: str) -> str:
    """Accept an API base URL, not a full chat-completions endpoint.

    Some copied examples contain literal escaped colon/slash characters.
    Refuse non-HTTPS origins and unexpected paths rather than silently posting
    user data to an arbitrary endpoint.
    """
    from urllib.parse import urlsplit
    value=str(value).strip().strip('\"\'').replace('\\:', ':').replace('\\/', '/')
    value=value.rstrip('/')
    if value.endswith('/chat/completions'):
        value=value[:-len('/chat/completions')]
    parts=urlsplit(value)
    if parts.scheme != 'https' or not parts.netloc or parts.username or parts.password:
        raise ValueError('Groq API URL must be https://api.groq.com/openai/v1')
    if parts.hostname == 'api.groq.com' and parts.path not in ('/openai/v1',''):
        raise ValueError('Groq API base URL must be https://api.groq.com/openai/v1')
    if parts.hostname == 'api.groq.com' and not parts.path:
        value+='/openai/v1'
    return value

def run_llm_refund_agent(order_id:str, goal:str, mode='graphshield', max_turns=8):
    import httpx
    if mode not in ('graphshield','preload'):raise ValueError('Only graphshield and preload available for this measured agent loop')
    if not _order(order_id):raise ValueError('Unknown historical Olist order ID')
    key=os.getenv('GRAPHSHIELD_LLM_API_KEY');model=os.getenv('GRAPHSHIELD_LLM_MODEL')
    base=_normalize_llm_base(os.getenv('GRAPHSHIELD_LLM_BASE_URL','https://api.groq.com/openai/v1'))
    if not key or not model:raise RuntimeError('Set GRAPHSHIELD_LLM_API_KEY and GRAPHSHIELD_LLM_MODEL to run real agent')
    if not base.startswith('https://'):raise ValueError('Real model API must use HTTPS')
    reg=load_registry();lookup={t['key']:t for t in reg['tools']}
    registry_context=[{'key':x['key'],'name':x['name'],'description':x['description'],'schema':x['schema']} for x in reg['tools']]
    prompt=('You are an enterprise order-investigation assistant. Data is historical Olist, not live. '
            'Refund rules are invented for a safe demo and refunds/messages must NOT be sent. '
            'You have only three meta-tools: graph_context, call_tool and report_outcome. '
            'Use graph_context to obtain only the tools you need, then call read-only tools in dependency order. '
            'Do not invent a tool response. Cite the evidence from tool results and distinguish simulated policy. '
            'Finish with an explanation requiring human approval. ')
    if mode=='preload':prompt+=' PRELOAD BASELINE: Here are all registered tools: '+json.dumps(registry_context,ensure_ascii=False)
    messages=[{'role':'system','content':prompt},{'role':'user','content':f'Historical order ID: {order_id}. Request: {goal}'}]
    events=[];final_answer=None;allowed_keys=set();executed_status={};usage={'prompt_tokens':0,'completion_tokens':0,'total_tokens':0};start=time.perf_counter();failures=0;calls=0
    db=RealHydra()
    try:
        with httpx.Client(timeout=90) as http:
            for turn in range(max_turns):
                response=http.post(base+'/chat/completions',headers={'Authorization':'Bearer '+key},
                   json={'model':model,'messages':messages,'tools':TOOLS,'tool_choice':'auto','temperature':0})
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as err:
                    code=err.response.status_code
                    if code==404:
                        raise RuntimeError('Groq API returned 404. Check GRAPHSHIELD_LLM_BASE_URL=https://api.groq.com/openai/v1 and confirm the model ID is supported.') from err
                    if code==401:
                        raise RuntimeError('Groq API rejected the key (401). Configure a valid Groq API key in the same terminal used to start FastAPI.') from err
                    if code==429:
                        raise RuntimeError('Groq rate limit reached (429). Check provider quota or retry later.') from err
                    raise RuntimeError(f'LLM provider HTTP {code}: {err.response.text[:180]}') from err
                payload=response.json()
                observed=payload.get('usage') or {}
                if not {'prompt_tokens','completion_tokens'}.issubset(observed):
                    raise RuntimeError('LLM returned no official token usage; no estimated usage is substituted')
                for k in ('prompt_tokens','completion_tokens','total_tokens'):
                    usage[k]+=int(observed.get(k,0))
                assistant=payload['choices'][0]['message'];calls_for_turn=assistant.get('tool_calls') or []
                messages.append({'role':'assistant','content':assistant.get('content'),'tool_calls':calls_for_turn} if calls_for_turn else {'role':'assistant','content':assistant.get('content') or ''})
                events.append({'event':'llm_response','turn':turn+1,'tool_calls':[x['function']['name'] for x in calls_for_turn],
                               'provider_reported_usage':observed})
                if not calls_for_turn:
                    final_answer=assistant.get('content') or ''
                    break
                for call in calls_for_turn:
                    name=call['function']['name'];arg=json.loads(call['function'].get('arguments') or '{}')
                    if name=='graph_context':
                        if mode=='graphshield':
                            task='refund_desk_followup' if 'how long' in goal.lower() and 'item' in goal.lower() else 'refund_desk_first_request'
                            route=db.resolve(task,entity_key='refund_desk_order:'+order_id)
                            chosen=route['tools'];allowed_keys={x['tool_key'] for x in chosen}
                            result={'tool_schemas':[{'tool_key':x['tool_key'],'name':x['name'],'input_schema':x['schema']} for x in chosen],
                                'ordered_steps':[x['tool_key'] for x in chosen],'rejected':route['rejected'],
                                'traversal':route['graph_edges'],'graph_queries':route['graph_queries'],
                                'entity_reused':bool(route.get('resolved_entity'))}
                            events.append({'event':'graph_context','task_key':task,'result':result})
                        else:
                            allowed_keys=set(lookup)
                            result={'tool_schemas':registry_context,'ordered_steps':None,
                                    'note':'Preload-all baseline; no graph dependency ordering'}
                            events.append({'event':'graph_context','task_key':None,'result':{'tool_schema_count':len(registry_context),'ordered_steps':None,'note':'Preload-all baseline; no graph traversal'}})
                    elif name=='call_tool':
                        tool_key=arg.get('tool_key');given=arg.get('args') or {}
                        if tool_key not in allowed_keys or tool_key not in lookup:
                            result={'error':'Tool key was not available in the resolved context. Call graph_context first.'};failures+=1
                        elif given.get('order_id')!=order_id or set(given)!={'order_id'}:
                            result={'error':'Only the selected historical order_id may be used.'};failures+=1
                        else:
                            try:
                                result=execute_readonly(tool_key,{'order_id':order_id});calls+=1
                                executed_status[tool_key]=not result.get('is_error',False)
                                if result.get('is_error'):failures+=1
                            except Exception as ex:result={'error':str(ex)[:250]};executed_status[tool_key]=False;failures+=1
                        events.append({'event':'mcp_call','tool_key':tool_key,'result':result})
                    elif name=='report_outcome':
                        keys=[x for x in arg.get('tool_keys',[]) if x in allowed_keys and x in executed_status]
                        claimed_success=bool(arg.get('success'))
                        if not keys:result={'warning':'No executed, validated tool keys; no learning update'}
                        else:
                            verified_success=all(executed_status[k] for k in keys)
                            result=db.feedback(keys,verified_success)
                            result['agent_claimed_success']=claimed_success
                            result['verified_from_mcp_results']=verified_success
                        events.append({'event':'outcome_written','result':result})
                    else:result={'error':'Unknown meta-tool'};failures+=1
                    messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result,default=str,ensure_ascii=False)[:15000]})
            else:
                events.append({'event':'limit_reached','max_turns':max_turns})
        return {'mode':mode,'model':model,'order_id':order_id,'events':events,'usage':usage,
                'tool_calls':calls,'failed_attempts':failures,'model_round_trips':len([x for x in events if x['event']=='llm_response']),
                'latency_ms':round((time.perf_counter()-start)*1000,2),
                'final_message':final_answer,
                'disclosure':'Real model API usage if this request succeeded. All refund rules, provider faults, and actions are simulated. No real refund issued.'}
    finally:db.close()
