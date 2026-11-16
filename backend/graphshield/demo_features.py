"""Demo-only experiments using real discovered MCP schemas and live HydraDB.

Learning measures failed dispatch attempts avoided after persistent failure evidence;
no actual MCP outage is claimed. Every experiment restores tool health.
"""
from __future__ import annotations
import asyncio
import json
import re
import time
from pathlib import Path
from .real_mcp import RealHydra, load_registry, load_tasks, ROOT

LEARNING_REPORT = ROOT / 'results' / 'real_learning.json'
COMMERCE_WITH_ORDER = {'get_order_status','get_customer_context','get_order_items','get_order_payments','assess_delivery_timing'}
REFUND_DESK_READONLY = {x['name'] for x in __import__('graphshield.refund_desk',fromlist=['specs']).specs() if not x['is_write']}
READONLY_ALLOWLIST = COMMERCE_WITH_ORDER | REFUND_DESK_READONLY | {'list_allowed_directories', 'get_current_time', 'read_graph', 'list_reporting_documents',
                      'inspect_filing_metadata', 'extract_financial_tables', 'extract_inline_xbrl_facts',
                      'audit_filing_structure', 'filing_capability_report'}
FINANCIAL_WITH_FILENAME = {'inspect_filing_metadata', 'extract_financial_tables', 'extract_inline_xbrl_facts',
                           'audit_filing_structure', 'filing_capability_report'}


def run_learning(task_key: str = 'edit_document', iterations: int = 8):
    if not 2 <= iterations <= 30:
        raise ValueError('iterations must be between 2 and 30')
    db = RealHydra()
    primary_id = None
    try:
        baseline_route = db.resolve(task_key)
        alternate = next((x for x in baseline_route['rejected'] if x['reason'] == 'standby / alternate'), None)
        if not alternate:
            raise ValueError('This task does not have a verified alternate provider')
        # Fail only a tool with an alternate implementing the same skill.
        primary = next((x for x in baseline_route['tools'] if x['name'] == alternate['name']), None)
        if not primary:
            raise ValueError('Alternate provider does not match selected tool')
        primary_id = primary['id']
        series = []
        for i in range(iterations):
            started = time.perf_counter()
            route = db.resolve(task_key)
            selected = next((x for x in route['tools'] if x['name'] == primary['name']), None)
            if not selected:
                raise ValueError('Resolver lost required capability')
            learned_failure = int(selected['id'] == primary_id)
            # Static baseline reuses its original route, thus retries the failed provider.
            # A failed dispatch is simulated, not an actual MCP execution.
            series.append({
                'iteration': i + 1,
                'static_failed_dispatches': 1,
                'graphshield_failed_dispatches': learned_failure,
                'graphshield_route': selected['tool_key'],
                'graph_queries': route['graph_queries'],
                'resolve_ms': round((time.perf_counter() - started) * 1000, 2)
            })
            if i == 0:
                db.fail(primary_id)  # Agent A reports failed provider; later agents benefit.
        report = {
            'type': 'controlled_persistent_failure_learning',
            'backend': 'hydradb', 'task': task_key, 'iterations': iterations,
            'real_mcp_tool': primary['tool_key'], 'fallback': alternate['server'] + '::' + alternate['name'],
            'series': series,
            'static_failures_total': sum(x['static_failed_dispatches'] for x in series),
            'graphshield_failures_total': sum(x['graphshield_failed_dispatches'] for x in series),
            'disclosure': ('Actual HydraDB failure records and traversal are exercised. The outage and '
                           'failed dispatches are injected/simulated. This is adaptive routing from stored '
                           'experience, not online ML training or live MCP execution. The static baseline '
                           'intentionally does not use shared failure memory.'),
        }
        LEARNING_REPORT.parent.mkdir(parents=True, exist_ok=True)
        LEARNING_REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')
        return report
    finally:
        if primary_id is not None:
            db.restore(primary_id)
        db.close()


def eligible_readonly_tools(registry=None):
    reg = registry if registry is not None else load_registry()
    return [t for t in reg['tools'] if t['name'] in READONLY_ALLOWLIST]


def validate_readonly_args(tool, arguments=None):
    import os
    from pathlib import Path
    arguments=arguments or {}
    if not isinstance(arguments,dict):raise ValueError('Tool arguments must be a JSON object')
    if tool['name'] in FINANCIAL_WITH_FILENAME:
        if tool['server']!='financial_reporting':raise ValueError('Financial tool server does not match allowlist')
        if set(arguments)!={'filename'}:raise ValueError('Financial tools accept filename only')
        filename=arguments['filename']
        if (not isinstance(filename,str) or not filename or len(filename)>180
                or filename!=Path(filename).name or '/' in filename
                or chr(92) in filename or Path(filename).suffix.lower() not in ('.xml','.html','.htm','.xhtml')):
            raise ValueError('Only a safe XHTML/XML filename is allowed')
        return {'filename':filename}
    if tool['name'] in REFUND_DESK_READONLY and tool['server'].split('_')[0] in ('orders','customers','payments','logistics','policy','actions','catalog'):
        if set(arguments)!={'order_id'}:raise ValueError('Desk tools require only order_id')
        order_id=arguments['order_id']
        if not isinstance(order_id,str) or not 1<=len(order_id)<=70 or not all(c.isalnum() or c in '-_' for c in order_id):
            raise ValueError('Invalid order ID')
        return {'order_id':order_id}
    if tool['name'] in COMMERCE_WITH_ORDER:
        if tool['server']!='commerce_evidence':raise ValueError('Commerce tool server does not match allowlist')
        if set(arguments)!={'order_id'}:raise ValueError('Commerce tool accepts order_id only')
        order_id=arguments['order_id']
        if not isinstance(order_id,str) or not 1<=len(order_id)<=70 or not all(c.isalnum() or c in '-_' for c in order_id):
            raise ValueError('Invalid order ID')
        return {'order_id':order_id}
    if arguments:raise ValueError('This read-only tool cannot accept arguments from dashboard')
    required=tool.get('schema',{}).get('required',[])
    if required:raise ValueError('This read-only tool requires arguments and is not supported')
    return {}

async def _execute_readonly(tool_key: str, arguments=None):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    registry = load_registry()
    matches = [t for t in eligible_readonly_tools(registry) if t['key'] == tool_key]
    if len(matches) != 1:
        raise ValueError('Only explicitly allowlisted read-only MCP tools are executable')
    tool = matches[0]
    safe_arguments=validate_readonly_args(tool,arguments)
    import os
    config = json.loads(Path(os.getenv('GRAPHSHIELD_MCP_CONFIG',str(ROOT / 'mcp_servers.json'))).read_text(encoding='utf-8'))
    server = next((s for s in config['servers'] if s['id'] == tool['server']), None)
    if not server:
        raise ValueError('Server definition not found')
    # Never accept arbitrary shell commands from UI. Only local configured MCP server.
    import os
    params = StdioServerParameters(command=__import__('sys').executable if server['command']=='{python}' else server['command'], args=server.get('args', []),
                                   env={**os.environ, **server.get('env', {})})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool['name'], arguments=safe_arguments)
            return {'tool_key': tool_key, 'executed': True, 'is_error': bool(result.isError),
                    'content': [c.model_dump(mode='json') for c in result.content]}


def execute_readonly(tool_key: str, arguments=None):
    return asyncio.run(_execute_readonly(tool_key,arguments))

# These paraphrases are manually written challenge inputs, NOT an external benchmark.
# Selection tests evaluate task-intent matching separately from graph traversal.
CHALLENGE_CASES = [
    ('Show me the latest commits and whether my repository is clean', 'inspect_repo'),
    ('Find out what changed in the working tree and look through the git history', 'inspect_changes'),
    ('Check what I staged and tell me the current repository state', 'inspect_staged'),
    ('Browse the directory and open a text document', 'read_document'),
    ('Find the filename somewhere in the permitted folder and open the text', 'find_document'),
    ('Review the folder contents, metadata, and contents of one file', 'review_documents'),
    ('Read, modify, and verify changes to a document', 'edit_document'),
    ('Explore nested folders and open a file inside them', 'inspect_tree'),
    ('Find remembered knowledge entities and retrieve their details', 'memory_lookup'),
    ('Insert a new memory record and attach fresh observations', 'memory_update'),
    ('Look up related knowledge nodes and their connections', 'memory_connections'),
    ('Tell me the time in another time zone', 'time_convert'),
    ('Work through a difficult problem one reasoning step at a time', 'think_through_problem'),
]

def match_task(text: str, workflows=None):
    import math
    if not 3 <= len(text.strip()) <= 1000:
        raise ValueError('Task description must contain 3-1000 characters')
    tasks=(workflows if workflows is not None else load_tasks())['tasks']
    if not tasks:raise ValueError('No MCP workflows discovered')
    def words(s):
        return set(re.findall(r'[a-z0-9]+',s.lower().replace('_',' '))) - {
            'a','an','the','i','me','my','to','in','on','and','then','with','of','for','from','it','some','one','its','be'}
    q=words(text)
    scored=[]
    for task in tasks:
        d=words(task['description']+' '+task['key'])
        score=len(q & d)/math.sqrt(max(len(q),1)*max(len(d),1))
        scored.append((score,task))
    scored.sort(key=lambda x:(-x[0],x[1]['key']))
    value,task=scored[0]
    return {'task_key':task['key'],'description':task['description'],
            'similarity':round(value,3),'method':'lexical-intent-match',
            'warning':'Lexical intent matching is a convenience UI, not a trained LLM planner. Confirm workflow before executing.'}


def evaluate_hard_intents():
    workflows=load_tasks()
    known={x['key'] for x in workflows['tasks']}
    rows=[]
    for prompt,expected in CHALLENGE_CASES:
        if expected not in known:continue
        result=match_task(prompt,workflows)
        rows.append({'prompt':prompt,'expected':expected,'predicted':result['task_key'],
                     'correct':result['task_key']==expected,'score':result['similarity']})
    if not rows:raise ValueError('No applicable manually authored challenge cases')
    summary={'cases':len(rows),'correct':sum(x['correct'] for x in rows),
             'accuracy':round(sum(x['correct'] for x in rows)/len(rows),3),
             'evaluation':'Manually authored, independent paraphrases of curated workflows; NOT public ground truth or full tool execution',
             'method':'lexical intent classifier followed by graph traversal; errors are expected and shown'}
    return {'summary':summary,'cases':rows}
