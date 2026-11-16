import json
from .reviewed_evaluation import run

if __name__=='__main__':
    report=run()
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows',)},indent=2))
