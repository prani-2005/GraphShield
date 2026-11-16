"""Additional operator CLI commands; uses existing real MCP and HydraDB backend."""
import argparse
import json
from pathlib import Path
from .enterprise import load_openapi_directory, write_inference_report
from .real_mcp import load_registry, load_tasks
from .enterprise_runtime import diagnostics, registry_stats, run_load, flat_ablation


def main():
    p=argparse.ArgumentParser(description='GraphShield Track 2 source-backed evaluation tools')
    p.add_argument('action',choices=['inspect-openapi','stats','diagnostics','infer','load','ablation'])
    p.add_argument('--directory',default='openapi_sources')
    p.add_argument('--repeats',type=int,default=10)
    a=p.parse_args()
    if a.action=='inspect-openapi':
        reg=load_openapi_directory(Path(a.directory))
        out={'real_openapi_operations':len(reg['tools']),'sources':reg['sources'],'errors':reg['errors']}
    elif a.action=='stats':out=registry_stats()
    elif a.action=='diagnostics':out=diagnostics()
    elif a.action=='infer':
        data=write_inference_report(load_registry()['tools'])
        out={k:v for k,v in data.items() if k!='edges'}
    elif a.action=='load':out=run_load((1,5,10,20),a.repeats)
    else:out=flat_ablation()
    print(json.dumps(out,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
