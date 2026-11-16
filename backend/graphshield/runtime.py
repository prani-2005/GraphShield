"""Deterministic demo execution. External side-effecting tools are intentionally not run."""
from .resolver import Resolver

def execute(graph, task_key, inject_failure=None, reward=True):
    resolver=Resolver(graph)
    first=resolver.resolve(task_key)
    attempted=[]; retries=0
    if inject_failure is not None:
        chosen=next((t for t in first['tools'] if t['id']==inject_failure),None)
        if chosen:
            attempted.append({'name':chosen['name'],'outcome':'injected_failure'})
            graph.mark_failure(chosen['id'],'injected_unavailable')
            retries=1
            first=resolver.resolve(task_key)
    for tool in first['tools']:
        attempted.append({'name':tool['name'],'outcome':'simulated_success'})
    if reward:
        graph.reward([t['id'] for t in first['tools']])
    return {'status':'simulated_success','retries':retries,'attempted':attempted,
            'route':first,'notice':'Execution uses deterministic stubs, not real third-party APIs.'}
