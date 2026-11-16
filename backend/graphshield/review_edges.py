"""Human review of schema-derived dataflow candidate edges.

Never auto-approves candidate links. Review 50 or fewer actual inferred edges.
"""
import argparse
import csv
import json
import random
from pathlib import Path
from .enterprise import REVIEW_FILE
ROOT=Path(__file__).resolve().parent.parent
CSV=ROOT/'results'/'edge_review_sample.csv'


def export_sample(count=50,seed=42):
    if not REVIEW_FILE.exists():raise FileNotFoundError('Run real_mcp discover first')
    data=json.loads(REVIEW_FILE.read_text(encoding='utf-8'))
    edges=data['edges'];randomizer=random.Random(seed)
    chosen=randomizer.sample(edges,min(count,len(edges)))
    CSV.parent.mkdir(parents=True,exist_ok=True)
    with CSV.open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=['producer','consumer','field','type','confidence','accepted','reviewer_note'])
        writer.writeheader()
        for x in chosen:writer.writerow({k:x.get(k,'') for k in writer.fieldnames})
    return {'candidates':len(edges),'sample_size':len(chosen),'file':str(CSV),
            'instructions':'Manually set accepted to yes or no on every sampled row; blank rows do not count.'}


def summarize():
    if not CSV.exists():raise FileNotFoundError('Export an edge review sample first')
    with CSV.open(encoding='utf-8-sig',newline='') as handle:rows=list(csv.DictReader(handle))
    marked=[x for x in rows if x.get('accepted','').strip().lower() in ('yes','no')]
    accepted=sum(x['accepted'].strip().lower()=='yes' for x in marked)
    result={'reviewed':len(marked),'sample_size':len(rows),
            'precision':round(accepted/len(marked),4) if marked else None,
            'status':'complete' if rows and len(marked)==len(rows) else 'incomplete',
            'disclosure':'Human-reviewed precision on a random sample of schema-compatibility candidates; not automated workflow execution precision.'}
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['export','summary']);args=p.parse_args()
    print(json.dumps(export_sample() if args.action=='export' else summarize(),indent=2))
