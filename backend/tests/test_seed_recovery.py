from graphshield.real_mcp import RealHydra


def test_seed_edge_skips_existing_relationship():
    obj=object.__new__(RealHydra)
    calls=[]
    def run(query,**kwargs):
        calls.append((query,kwargs))
        return [{'id':2}] if query.startswith('MATCH ') else []
    obj.run=run
    wrote=obj._seed_edge('MCPServer',1,'EXPOSES','Tool',2,'MERGE dummy',{},'unit tool')
    assert not wrote
    assert len(calls)==1


def test_seed_edge_has_context_on_failure():
    obj=object.__new__(RealHydra)
    def run(query,**kwargs):
        if query.startswith('MATCH '):return []
        raise RuntimeError('database write refused')
    obj.run=run
    try:
        obj._seed_edge('MCPServer',1,'EXPOSES','Tool',2,'MERGE dummy',{},'example-server::read')
    except RuntimeError as exc:
        assert 'example-server::read' in str(exc)
        assert 'database write refused' in str(exc)
    else:
        raise AssertionError('expected diagnostic failure')
