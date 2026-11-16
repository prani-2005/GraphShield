"""Source-grounded registry expansion and graph dependency analysis.

All imported operations must originate from genuine OpenAPI documents supplied by
an operator. Nothing in this module generates fictitious tools or gold labels.
"""
from __future__ import annotations
import json
import re
import hashlib
from pathlib import Path
from urllib.parse import urlparse
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
OPENAPI_DIR = ROOT / 'openapi_sources'
REVIEW_FILE = ROOT / 'results' / 'inferred_edges.json'


def _read_spec(path: Path):
    raw=path.read_text(encoding='utf-8')
    if path.suffix.lower() in ('.yaml','.yml'):
        try: import yaml
        except ImportError as e: raise RuntimeError('Install PyYAML to import YAML OpenAPI specs') from e
        return yaml.safe_load(raw)
    return json.loads(raw)


def _ref_schema(spec, item):
    """Resolve internal component-schema refs only; stop recursion/cycles."""
    seen=set()
    for _ in range(8):
        if not isinstance(item,dict) or '$ref' not in item: break
        ref=item['$ref']
        if not ref.startswith('#/') or ref in seen: return {}
        seen.add(ref)
        value=spec
        for token in ref[2:].split('/'):
            token=token.replace('~1','/').replace('~0','~')
            value=value.get(token,{}) if isinstance(value,dict) else {}
        item=value
    return item if isinstance(item,dict) else {}


def _field_types(spec, node, prefix='', depth=0):
    node=_ref_schema(spec,node)
    if depth>3 or not isinstance(node,dict):return []
    fields=[]
    for name,child in node.get('properties',{}).items():
        child=_ref_schema(spec,child)
        key=(prefix+'.'+name).strip('.')
        typ=child.get('type','object')
        fields.append({'name':key,'type':typ if isinstance(typ,str) else str(typ)})
        if typ=='object': fields.extend(_field_types(spec,child,key,depth+1))
    return fields


def load_openapi_directory(directory=OPENAPI_DIR):
    directory=Path(directory)
    tools=[]; errors=[]; provenance=[]; seen=set()
    if not directory.exists():return {'tools':[], 'errors':[], 'sources':[]}
    for path in sorted(directory.glob('*')):
        if path.suffix.lower() not in ('.json','.yml','.yaml'):continue
        try:
            spec=_read_spec(path)
            if not isinstance(spec,dict) or not (spec.get('openapi') or spec.get('swagger')):
                raise ValueError('Not an OpenAPI/Swagger document')
            title=spec.get('info',{}).get('title',path.stem)
            version=str(spec.get('info',{}).get('version','unknown'))
            source_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
            source={'file':path.name,'sha256':source_sha256,'title':title,'version':version,
                    'license':spec.get('info',{}).get('license',{}),
                    'source_url':spec.get('externalDocs',{}).get('url','')}
            provenance.append(source)
            server='openapi_'+re.sub(r'[^a-z0-9]+','_',path.stem.lower()).strip('_')[:42]
            for route,methods in spec.get('paths',{}).items():
                if not isinstance(methods,dict):continue
                for method,op in methods.items():
                    if method.lower() not in ('get','post','put','patch','delete','head') or not isinstance(op,dict):continue
                    operation_id=str(op.get('operationId') or f'{method}_{route}')
                    name=re.sub(r'[^a-zA-Z0-9_]+','_',operation_id).strip('_')[:100]
                    tool_key=f'{server}::{name}'
                    if tool_key in seen:
                        tool_key += '_'+hashlib.sha256((method+route).encode()).hexdigest()[:8]
                    seen.add(tool_key)
                    properties={}; required=[]
                    parameters=list(methods.get('parameters',[]))+list(op.get('parameters',[]))
                    for param in parameters:
                        param=_ref_schema(spec,param)
                        if not param.get('name'):continue
                        field=param.get('schema',{'type':param.get('type','string')})
                        properties[param['name']]=_ref_schema(spec,field)
                        if param.get('required'):required.append(param['name'])
                    body=_ref_schema(spec,op.get('requestBody',{}))
                    content=body.get('content',{})
                    request_schema=(content.get('application/json') or next(iter(content.values()),{})).get('schema',{}) if content else {}
                    request_schema=_ref_schema(spec,request_schema)
                    for k,v in request_schema.get('properties',{}).items():properties[k]=_ref_schema(spec,v)
                    required+=request_schema.get('required',[])
                    schema={'type':'object','properties':properties,'required':list(dict.fromkeys(required))}
                    responses=op.get('responses',{})
                    success=next((v for k,v in responses.items() if str(k).startswith('2')),{})
                    success=_ref_schema(spec,success)
                    output_content=success.get('content',{})
                    response_schema=(output_content.get('application/json') or next(iter(output_content.values()),{})).get('schema',{}) if output_content else {}
                    response_schema=_ref_schema(spec,response_schema)
                    tools.append({'key':tool_key,'name':name,'server':server,
                                  'description':op.get('description') or op.get('summary') or f'{method.upper()} {route}',
                                  'schema':schema,'output_schema':response_schema,
                                  'annotations':{'readOnlyHint':method.lower() in ('get','head')},
                                  'source':'converted OpenAPI','source_file':path.name,
                                  'source_sha256':source_sha256, 'version':version,
                                  'http_method':method.upper(),'http_path':route,
                                  'input_fields':_field_types(spec,schema),
                                  'output_fields':_field_types(spec,response_schema)})
        except Exception as exc:errors.append({'file':path.name,'error':str(exc)})
    return {'tools':tools,'errors':errors,'sources':provenance}


def merge_registries(mcp, openapi):
    tools=list(mcp.get('tools',[])) + list(openapi.get('tools',[]))
    keys=[x['key'] for x in tools]
    if len(keys)!=len(set(keys)):raise ValueError('Duplicate tool identifiers across registry sources')
    return {**mcp,'tools':tools,'openapi_sources':openapi.get('sources',[]),
            'openapi_errors':openapi.get('errors',[]),'servers':list(mcp.get('servers',[]))+[
                'openapi:'+s['file'] for s in openapi.get('sources',[])]}


def _normalize(field):
    x=field.split('.')[-1].lower()
    x=re.sub(r'([a-z])([A-Z])',r'\1_\2',x)
    x=re.sub(r'[^a-z0-9]+','_',x).strip('_')
    return x


def infer_edges(tools, limit=10000):
    """Conservative candidate schema compatibility; not a verified dependency."""
    producers=defaultdict(list); consumers=defaultdict(list)
    for t in tools:
        for fld in t.get('output_fields',[]):
            n=_normalize(fld['name'])
            if n and n not in {'id','name','status','type','value','result','data','message'}:
                producers[n].append((t,fld))
        for fld in t.get('input_fields',[]):
            n=_normalize(fld['name'])
            if n and n not in {'id','name','status','type','value','result','data','message'}:
                consumers[n].append((t,fld))
    edges=[];seen=set()
    for name in producers.keys() & consumers.keys():
        for a,output in producers[name]:
            for b,required in consumers[name]:
                if a['key']==b['key']:continue
                if output['type']!=required['type']:continue
                key=(a['key'],b['key'],name)
                if key in seen:continue
                seen.add(key)
                edges.append({'producer':a['key'],'consumer':b['key'],'field':name,
                              'type':output['type'],'confidence':0.65,
                              'verification':'candidate_unreviewed',
                              'reason':'Normalized output/input field name and type match; not proof of a runnable dependency'})
                if len(edges)>=limit:return edges
    return edges


def write_inference_report(tools, path=REVIEW_FILE):
    edges=infer_edges(tools)
    out={'source_tool_count':len(tools),'candidate_edges':len(edges),
         'reviewed_edges':0,'precision':None,
         'warning':'Candidate inferred edges are NOT trusted execution edges until reviewed. Precision unavailable.',
         'edges':edges}
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,indent=2),encoding='utf-8')
    return out
