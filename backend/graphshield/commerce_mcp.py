"""Read-only commerce operations MCP backed by operator-downloaded Olist CSVs.

Historical, anonymized 2016-2018 dataset. No checkout, shipment API, refunds or
live customer service integrations. No generated order or customer records.
"""
from __future__ import annotations
import csv
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    # Allows deterministic data/validation tests without MCP installed.
    # Actual server startup still requires the MCP dependency.
    class FastMCP:
        def __init__(self, *args, **kwargs): pass
        def tool(self): return lambda fn:fn
        def run(self): raise RuntimeError('Install project requirements to run MCP server')

mcp=FastMCP('GraphShield Commerce Evidence')
FILES={'orders':'olist_orders_dataset.csv','customers':'olist_customers_dataset.csv',
       'items':'olist_order_items_dataset.csv','payments':'olist_order_payments_dataset.csv'}

def data_dir():
    return Path(os.environ.get('GRAPHSHIELD_COMMERCE_DATA_DIR', str(Path(__file__).resolve().parent.parent/'data'/'olist'))).resolve()

@lru_cache(maxsize=4)
def _rows(folder: str, name: str):
    file=Path(folder)/FILES[name]
    if not file.is_file():
        raise FileNotFoundError(f'Missing {file.name}. Download the original Olist CSVs using scripts/fetch_olist.py; records are never invented.')
    with file.open(encoding='utf-8-sig',newline='') as fh:
        return tuple(csv.DictReader(fh))

def records(name): return _rows(str(data_dir()),name)

def _order(order_id):
    if not isinstance(order_id,str) or not (1<=len(order_id)<=70) or not all(c.isalnum() or c in '-_' for c in order_id):
        raise ValueError('order_id must contain 1-70 alphanumeric/hyphen/underscore characters')
    return next((row for row in records('orders') if row.get('order_id')==order_id), None)

def _date(v):
    if not v:return None
    try:return datetime.fromisoformat(v.strip())
    except ValueError:return None

@mcp.tool()
def find_delayed_orders(limit: int=8)->dict:
    """Find historical orders delivered after their estimated dates, for a real-case investigation. Read only."""
    limit=max(1,min(20,limit))
    out=[]
    for row in records('orders'):
        delivered=_date(row.get('order_delivered_customer_date'))
        estimated=_date(row.get('order_estimated_delivery_date'))
        if delivered and estimated and delivered>estimated:
            out.append({'order_id':row['order_id'],'status':row.get('order_status'),
                        'estimated_delivery':row['order_estimated_delivery_date'],
                        'actual_delivery':row['order_delivered_customer_date'],
                        'late_days':(delivered-estimated).days})
            if len(out)==limit:break
    return {'source':'Olist anonymized historical e-commerce dataset','historical_not_live':True,'cases':out}

@mcp.tool()
def get_order_status(order_id: str)->dict:
    """Fetch a real historical order status and its estimated/actual delivery dates by order_id. Read only."""
    row=_order(order_id)
    if row is None:return {'found':False,'order_id':order_id}
    keys=('order_id','customer_id','order_status','order_purchase_timestamp','order_approved_at',
          'order_delivered_carrier_date','order_delivered_customer_date','order_estimated_delivery_date')
    return {'found':True,'source':'olist_orders_dataset.csv','historical_not_live':True,
            'record':{k:row.get(k,'') for k in keys}}

@mcp.tool()
def get_customer_context(order_id: str)->dict:
    """Resolve the anonymized customer of an order and its region, using the orders-to-customers join. Read only."""
    row=_order(order_id)
    if row is None:return {'found':False,'order_id':order_id}
    customer=next((r for r in records('customers') if r.get('customer_id')==row['customer_id']),None)
    if not customer:return {'found':False,'order_id':order_id,'customer_id':row['customer_id']}
    return {'found':True,'source':'olist_customers_dataset.csv','order_id':order_id,
            'customer_id':customer.get('customer_id'),
            'customer_unique_id':customer.get('customer_unique_id'),
            'city':customer.get('customer_city'),'state':customer.get('customer_state'),
            'historical_not_live':True}

@mcp.tool()
def get_order_items(order_id: str)->dict:
    """Retrieve product identifiers, seller identifiers, and line-item price/freight amounts for an order. Read only."""
    if _order(order_id) is None:return {'found':False,'order_id':order_id}
    items=[{k:row.get(k) for k in ('order_item_id','product_id','seller_id','price','freight_value')}
           for row in records('items') if row.get('order_id')==order_id]
    return {'found':True,'source':'olist_order_items_dataset.csv','order_id':order_id,
            'item_count':len(items),'items':items[:30],'truncated':len(items)>30,'currency':'BRL'}

@mcp.tool()
def get_order_payments(order_id: str)->dict:
    """Retrieve recorded payment methods and values associated with an order; does not authorize refunds. Read only."""
    if _order(order_id) is None:return {'found':False,'order_id':order_id}
    payments=[{k:row.get(k) for k in ('payment_type','payment_installments','payment_value')}
              for row in records('payments') if row.get('order_id')==order_id]
    return {'found':True,'source':'olist_order_payments_dataset.csv','order_id':order_id,
            'payments':payments[:20],'currency':'BRL','refund_eligibility':'unknown; not present in source'}

@mcp.tool()
def assess_delivery_timing(order_id: str)->dict:
    """Compare observed historical delivery with the estimated date; return evidence, not refund eligibility."""
    row=_order(order_id)
    if row is None:return {'found':False,'order_id':order_id}
    actual=_date(row.get('order_delivered_customer_date'))
    expected=_date(row.get('order_estimated_delivery_date'))
    delta=(actual-expected).days if actual and expected else None
    return {'found':True,'order_id':order_id,'delivered_after_estimate':actual>expected if actual and expected else None,
            'days_after_estimate':delta,'actual_delivery':row.get('order_delivered_customer_date'),
            'estimated_delivery':row.get('order_estimated_delivery_date'),
            'conclusion':'Historical delivery-date comparison only; no current tracking, SLA adjudication or refund eligibility',
            'source':'olist_orders_dataset.csv'}

if __name__=='__main__':mcp.run()
