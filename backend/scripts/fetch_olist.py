"""Download seven ORIGINAL historical Olist CSVs needed by the commerce demo.

Dataset attribution: Olist Brazilian E-Commerce Public Dataset, Kaggle
https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
License: consult source; commonly listed CC BY-NC-SA 4.0. Do not rehost data.
"""
from pathlib import Path
from urllib.request import Request,urlopen
import csv,hashlib,json,os
BASE='https://raw.githubusercontent.com/anggid/Brazilian-E-Commerce-Public-Dataset-by-Olist/main/'
FILES=['olist_orders_dataset.csv','olist_customers_dataset.csv',
       'olist_order_items_dataset.csv','olist_order_payments_dataset.csv',
       'olist_products_dataset.csv','olist_sellers_dataset.csv','olist_order_reviews_dataset.csv']
ROOT=Path(__file__).resolve().parent.parent
DEST=Path(os.environ.get('GRAPHSHIELD_COMMERCE_DATA_DIR',str(ROOT/'data'/'olist')))

def main():
    DEST.mkdir(parents=True,exist_ok=True)
    records=[]
    for name in FILES:
        path=DEST/name
        if not path.is_file():
            print('Downloading original:',name,flush=True)
            request=Request(BASE+name,headers={'User-Agent':'GraphShield-Hackathon-Evaluation/1.0'})
            with urlopen(request,timeout=90) as resp, path.open('wb') as out:
                while chunk:=resp.read(1024*1024):out.write(chunk)
        with path.open(encoding='utf-8-sig',newline='') as fh:
            reader=csv.DictReader(fh)
            if not reader.fieldnames or len(reader.fieldnames)<4:raise RuntimeError('Invalid downloaded CSV: '+name)
            count=sum(1 for _ in reader)
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        records.append({'file':name,'rows':count,'sha256':digest,'bytes':path.stat().st_size,'download_url':BASE+name})
        print(name,count,'rows')
    manifest={'source':'Olist Brazilian E-Commerce Public Dataset (historical anonymized)',
              'canonical_source':'https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce',
              'mirror':'https://github.com/anggid/Brazilian-E-Commerce-Public-Dataset-by-Olist',
              'not_live_customer_data':True,'files':records}
    (DEST/'source_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Ready:',DEST)
if __name__=='__main__':main()
