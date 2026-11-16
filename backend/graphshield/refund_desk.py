"""Late-Delivery Refund Desk: Olist-backed evidence + explicitly simulated policy/actions.

No fabricated customer/order data. Historical 2016-2018 Olist observations are NOT
proof of a contractual entitlement or a live payment/refund state.
"""
from __future__ import annotations
import csv, hashlib, json, os, random, statistics, threading
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
from .commerce_mcp import _order, records, _date, data_dir

ROOT = Path(__file__).resolve().parent.parent
POLICY_FILE = ROOT / 'config' / 'demo_refund_policy.json'
OUTBOX = ROOT / 'data' / 'sandbox_outbox.jsonl'
_LOCK = threading.Lock()
EXTRA_FILES = {'products': 'olist_products_dataset.csv', 'sellers':'olist_sellers_dataset.csv', 'reviews':'olist_order_reviews_dataset.csv'}

@lru_cache(maxsize=3)
def extra_rows(folder, name):
    path=Path(folder)/EXTRA_FILES[name]
    if not path.is_file():
        raise FileNotFoundError(f'{path.name} not downloaded; run scripts/fetch_olist.py')
    with path.open(encoding='utf-8-sig', newline='') as fh:
        return tuple(csv.DictReader(fh))

def load_policy():
    return json.loads(POLICY_FILE.read_text(encoding='utf-8'))

def amount(v):
    try:return Decimal(str(v or 0))
    except Exception:return Decimal('0')

def money(x):
    return str(x.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

def resolve_order(order_id):
    row=_order(order_id)
    if row is None:return {'found':False,'order_id':order_id,'source':'Olist orders CSV'}
    return {'found':True,'source':'Olist historical orders','record':row,'order_id':order_id,'customer_id':row['customer_id']}

def timeline(order_id):
    row=_order(order_id)
    if not row:return {'found':False,'order_id':order_id}
    keys=('order_purchase_timestamp','order_approved_at','order_delivered_carrier_date','order_delivered_customer_date','order_estimated_delivery_date','order_status')
    return {'found':True,'order_id':order_id,'fields':{k:row.get(k,'') for k in keys},'source':'Olist historical orders'}

def delay(order_id):
    row=_order(order_id)
    if not row:return {'found':False,'order_id':order_id}
    a=_date(row.get('order_delivered_customer_date'));b=_date(row.get('order_estimated_delivery_date'))
    # Difference in completed calendar days, rather than a rounded timedelta.
    days=(a.date()-b.date()).days if a and b else None
    return {'found':True,'order_id':order_id,'delay_days':days,'delivered':bool(a),
            'delivery_date':a.isoformat() if a else None,'promised_proxy':b.isoformat() if b else None,
            'source':'Olist delivery timestamps','warning':'estimated date is a proxy for promise; not contractual SLA'}

def customer(order_id):
    row=_order(order_id)
    if not row:return {'found':False,'order_id':order_id}
    c=next((r for r in records('customers') if r['customer_id']==row['customer_id']),None)
    if not c:return {'found':False,'order_id':order_id}
    return {'found':True,'order_id':order_id,'customer_id':c['customer_id'],'customer_unique_id':c.get('customer_unique_id'),
            'region':{'city':c.get('customer_city'),'state':c.get('customer_state')},'source':'Olist customers CSV'}

def items(order_id):
    if not _order(order_id):return {'found':False,'order_id':order_id}
    found=[r for r in records('items') if r['order_id']==order_id]
    return {'found':True,'order_id':order_id,'items':[{k:r.get(k) for k in ('order_item_id','product_id','seller_id','price','freight_value')} for r in found[:40]],
            'total_items':len(found),'source':'Olist items CSV','currency':'BRL'}

def payments(order_id):
    if not _order(order_id):return {'found':False,'order_id':order_id}
    rows=[r for r in records('payments') if r['order_id']==order_id]
    return {'found':True,'order_id':order_id,'payments':[{k:r.get(k) for k in ('payment_type','payment_installments','payment_value','payment_sequential')} for r in rows[:20]],
            'total_paid_brl':money(sum((amount(r.get('payment_value')) for r in rows),Decimal('0'))),
            'source':'Olist payments CSV','warning':'not proof of remaining refundable balance'}

def freight(order_id):
    res=items(order_id)
    if not res['found']:return res
    return {'found':True,'order_id':order_id,'total_freight_brl':money(sum((amount(r['freight_value']) for r in res['items']),Decimal('0'))),
            'source':'Olist item freight values','truncated':res['total_items']>40}

def eligibility(order_id):
    d=delay(order_id)
    if not d['found']:return d
    days=d['delay_days'];policy=load_policy();thresholds=policy['thresholds']
    if days is None: tier='manual_review'
    elif days>=thresholds['full_refund_days']:tier='full_order_value'
    elif days>=thresholds['shipping_refund_days']:tier='shipping_fee'
    else:tier='not_eligible_under_demo_rule'
    pay=payments(order_id);ship=freight(order_id)
    refundable=Decimal('0')
    if tier=='shipping_fee':refundable=amount(ship['total_freight_brl'])
    if tier=='full_order_value':refundable=amount(pay['total_paid_brl'])
    return {'found':True,'order_id':order_id,'delay_days':days,'tier':tier,'estimated_refund_brl':money(refundable),
            'refund_policy':'SIMULATED / INVENTED DEMO POLICY','policy_version':policy['version'],
            'source':'derived from Olist + invented rule','requires_human_approval':True,
            'not_real_refund_eligibility':True,'warning':'No merchant refund rights asserted; decision is demo-only'}

def refund_eta(order_id):
    e=eligibility(order_id)
    if not e.get('found'):return e
    return {'order_id':order_id,'estimate_business_days':load_policy()['demo_processing_business_days'],
            'label':'SIMULATED POLICY ETA — not observed in Olist data','tier':e['tier']}

def draft_reply(order_id):
    e=eligibility(order_id);d=delay(order_id)
    if not e.get('found'):return e
    return {'order_id':order_id,'status':'draft_only','message':f"Our historical records show an estimated delivery delay of {d['delay_days']} days. Under the illustrative demo policy, the review category is {e['tier']} and estimated amount is BRL {e['estimated_refund_brl']}. No refund was issued; staff approval would be required.",
            'simulation':True,'sent':False}

def create_request(order_id, approved=False):
    if not approved:return {'created':False,'reason':'human approval flag required','simulation':True}
    e=eligibility(order_id)
    if not e.get('found'):return {'created':False,'reason':'unknown order','simulation':True}
    record={'event':'SIMULATED_REFUND_APPROVAL_REQUEST','order_id':order_id,'policy_result':e,'sent_to_provider':False}
    OUTBOX.parent.mkdir(parents=True,exist_ok=True)
    with _LOCK, OUTBOX.open('a',encoding='utf-8') as fh:fh.write(json.dumps(record,ensure_ascii=False)+'\n')
    return {'created':True,'sandbox_outbox':str(OUTBOX),'simulation':True,'real_refund_issued':False}

def seller_info(order_id):
    it=items(order_id)
    if not it.get('found'):return it
    sellers={x['seller_id'] for x in it['items']}
    return {'order_id':order_id,'sellers':[r for r in extra_rows(str(data_dir()),'sellers') if r['seller_id'] in sellers][:20], 'source':'Olist sellers CSV'}

def product_info(order_id):
    it=items(order_id)
    if not it.get('found'):return it
    ids={x['product_id'] for x in it['items']}
    return {'order_id':order_id,'products':[r for r in extra_rows(str(data_dir()),'products') if r['product_id'] in ids][:20], 'source':'Olist products CSV'}

def order_reviews(order_id):
    return {'order_id':order_id,'reviews':[r for r in extra_rows(str(data_dir()),'reviews') if r['order_id']==order_id][:20],'source':'Olist reviews CSV'}

# Tool definitions intentionally declare their evidence class, and all names are
# discoverable through MCP tools/list; they are not fictitious external services.
# A few narrowly scoped read-only projections share an underlying Olist data join.
GROUPS={
 'orders':[
  ('resolve_order','Resolve an Olist historical order ID to an order and customer reference','resolve_order'),
  ('get_order_status','Read historical order status and ID','resolve_order'),
  ('get_order_timeline','Read historical order and delivery timestamps','timeline'),
  ('get_purchase_timestamp','Read original purchase date for an order','timeline'),
  ('get_order_approval','Read order approval timestamp','timeline'),
  ('get_order_customer_ref','Resolve the customer ID from an order ID','resolve_order'),
  ('get_order_delivery_estimate','Read Olist estimated delivery timestamp','timeline'),
  ('get_order_delivery_actual','Read Olist observed customer delivery timestamp','timeline'),
  ('verify_delivered_order','Check whether the historical record has a delivered date','delay'),
  ('get_order_summary','Retrieve historical order metadata','resolve_order')],
 'customers':[
  ('resolve_customer','Resolve anonymized Olist customer reference for an order','customer'),
  ('get_customer_region','Read customer city and state using an order ID','customer'),
  ('get_customer_unique_id','Read anonymized customer unique reference','customer'),
  ('get_customer_order_reference','Read Olist customer-order join','customer'),
  ('get_customer_delivery_region','Read the historical delivery region','customer'),
  ('get_customer_location','Read historical customer location','customer')],
 'payments':[
  ('get_order_payments','Read original payment rows associated with an order','payments'),
  ('get_payment_total','Sum observed payment values in BRL','payments'),
  ('get_payment_methods','List methods from original Olist payment records','payments'),
  ('get_payment_installments','Read installment counts from original payment rows','payments'),
  ('get_payment_sequences','Inspect Olist payment sequence identifiers','payments'),
  ('get_payment_breakdown','Read breakdown of observed payment amounts','payments'),
  ('get_order_freight','Sum Olist item freight charges in BRL','freight'),
  ('get_refund_source_amount','Read historical amount only; not actual refundable balance','payments')],
 'logistics':[
  ('get_delivery_timeline','Read Olist carrier handoff and delivery timestamps','timeline'),
  ('compute_delay_days','Compute calendar-days late from Olist estimated and actual delivery dates','delay'),
  ('check_delivery_lateness','Classify whether delivery was later than estimate','delay'),
  ('get_carrier_handoff','Read historical carrier handoff time','timeline'),
  ('get_delivery_timestamp','Read final historical delivery timestamp','timeline'),
  ('get_estimated_delivery','Read historical estimated delivery timestamp','timeline'),
  ('get_delivery_exception','Summarize actual lateness, not live carrier status','delay'),
  ('get_carrier_status_simulated','SIMULATED carrier status from Olist records, not a live carrier API','delay')],
 'policy':[
  ('get_refund_policy','Read INVENTED demonstration policy and thresholds','policy'),
  ('check_refund_eligibility','Evaluate invented refund policy using observed delay and payments','eligibility'),
  ('calculate_refund_estimate','Calculate illustrative refund amount in BRL','eligibility'),
  ('get_refund_processing_eta','Return SIMULATED business-day processing estimate','eta'),
  ('check_shipping_refund','Evaluate invented shipping refund threshold','eligibility'),
  ('check_full_refund','Evaluate invented full refund threshold','eligibility'),
  ('explain_policy_decision','Explain demo eligibility and evidence categories','eligibility')],
 'actions':[
  ('draft_refund_request','Create non-sending draft for staff review','draft'),
  ('draft_customer_message','Compose an unsent support message','draft'),
  ('preview_refund_amount','Preview simulated amount requiring approval','eligibility'),
  ('get_refund_status_simulated','Return draft status only, no payment provider contacted','draft'),
  ('get_customer_message_preview','Read unsent customer message preview','draft'),
  ('create_refund_request','SIMULATED sandbox outbox request; requires approved=true','write')],
 'catalog':[
  ('get_order_items','Read original Olist line items','items'),
  ('get_item_prices','Read real historical item prices','items'),
  ('get_product_ids','Read real product IDs within an order','items'),
  ('get_seller_ids','Read real seller IDs within an order','items'),
  ('get_product_descriptions','Read original Olist product attributes','products'),
  ('get_seller_profiles','Read original Olist seller records','sellers'),
  ('get_customer_reviews','Read original Olist review records','reviews'),
  ('get_order_reviews','Read historic reviews; not proof of refund rights','reviews'),
  ('get_item_freight','Read individual freight charges','items'),
  ('get_item_detail','Read original Olist item rows','items'),
  ('get_seller_geography','Read seller geographic fields from Olist','sellers'),
  ('get_product_attributes','Read product catalog attributes from Olist','products'),
  ('get_product_category','Read product category metadata from Olist','products'),
  ('get_review_scores','Read historical review scores','reviews'),
  ('get_review_comments','Read historical review comments','reviews')]
}
HANDLERS={'resolve_order':resolve_order,'timeline':timeline,'delay':delay,'customer':customer,
          'payments':payments,'freight':freight,'eligibility':eligibility,'eta':refund_eta,
          'draft':draft_reply,'items':items,'sellers':seller_info,'products':product_info,
          'reviews':order_reviews,'policy':lambda order_id:{'policy':load_policy(),'simulation':True,'order_id':order_id}}

def invoke(name,order_id,approved=False):
    for entries in GROUPS.values():
        for n,_,handler in entries:
            if name==n:
                if handler=='write':return create_request(order_id,approved)
                return HANDLERS[handler](order_id)
    raise ValueError('Unknown registered tool')

def specs():
    return [{'name':n,'description':desc,'role':role,'handler':handler,
             'evidence_type':'simulated' if handler in ('policy','eligibility','eta','draft','write') or n.endswith('_simulated') else 'historical_olist',
             'is_write':handler=='write'} for role,entries in GROUPS.items() for n,desc,handler in entries]

def generate_cases(count=150,seed=17):
    """Deterministic, source-linked case labels; no synthetic order records."""
    if count!=150:raise ValueError('Submission case count is fixed to 150 for reproducibility')
    policy=load_policy();candidates=[]
    for r in records('orders'):
        a=_date(r.get('order_delivered_customer_date'));b=_date(r.get('order_estimated_delivery_date'))
        if a and b and (a.date()-b.date()).days>=1:
            candidates.append((r['order_id'],(a.date()-b.date()).days))
    rng=random.Random(seed);rng.shuffle(candidates)
    if len(candidates)<count:raise ValueError('Not enough late-delivery records')
    intents=['late_delivery_refund','payment_question','wrong_item_inquiry','order_status']
    out=[]
    for i,(oid,days) in enumerate(candidates[:count]):
        intent=intents[i%len(intents)]
        result=eligibility(oid)
        chain=['resolve_order','get_order_timeline','compute_delay_days','get_order_payments','get_refund_policy','check_refund_eligibility','draft_refund_request'] if intent=='late_delivery_refund' else (
          ['resolve_order','get_order_payments','get_payment_breakdown'] if intent=='payment_question' else (
          ['resolve_order','get_order_items','get_product_ids'] if intent=='wrong_item_inquiry' else ['resolve_order','get_order_status','get_delivery_timeline']))
        out.append({'case_id':f'olist_case_{i:03d}','order_id':oid,'intent':intent,'observed_delay_days':days,
                    'gold_tier_under_invented_policy':result['tier'],'gold_refund_amount_brl':result['estimated_refund_brl'],
                    'gold_chain':chain,'followup':'How long will the refund take and for which items?',
                    'source':'historical Olist records + clearly invented policy',
                    'split':'train' if i<100 else 'held_out'})
    return {'seed':seed,'policy_version':policy['version'],'train_count':100,'held_out_count':50,
            'cases':out,'note':'Historical orders; generated intents and ground-truth chains are curated design, not real support tickets'}

def save_cases(path=None,seed=17):
    dest=Path(path) if path else ROOT/'data'/'refund_desk_cases.json'
    dest.parent.mkdir(parents=True,exist_ok=True)
    data=generate_cases(seed=seed)
    dest.write_text(json.dumps(data,indent=2),encoding='utf-8')
    return {'path':str(dest),'cases':len(data['cases']),'train':100,'held_out':50}
