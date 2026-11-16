"""Tests use clearly artificial records ONLY inside isolated unit-test fixtures.
They do not contaminate the application dataset or performance evidence.
"""
from datetime import datetime,timedelta
from pathlib import Path
import pytest
from graphshield import refund_desk as d
from graphshield import commerce_mcp as commerce

@pytest.fixture
def sample(monkeypatch):
    base=datetime(2018,1,1)
    orders=[];customers=[];payments=[];items=[]
    for i in range(160):
        oid=f'fixture_order_{i:04d}'
        orders.append({'order_id':oid,'customer_id':f'fixture_customer_{i:04d}',
          'order_status':'delivered','order_purchase_timestamp':base.isoformat(),
          'order_delivered_customer_date':(base+timedelta(days=i%19+1)).isoformat(),
          'order_estimated_delivery_date':base.isoformat()})
        customers.append({'customer_id':f'fixture_customer_{i:04d}','customer_unique_id':f'fixture_unique_{i:04d}',
          'customer_city':'TEST_ONLY','customer_state':'XX'})
        payments.append({'order_id':oid,'payment_value':'100.00','payment_type':'credit_card','payment_installments':'1','payment_sequential':'1'})
        items.append({'order_id':oid,'order_item_id':'1','product_id':'test_product','seller_id':'test_seller','price':'90.00','freight_value':'10.00'})
    data={'orders':orders,'customers':customers,'payments':payments,'items':items}
    monkeypatch.setattr(d,'records',lambda name:data[name])
    monkeypatch.setattr(commerce,'records',lambda name:data[name])
    monkeypatch.setattr(d,'_order',lambda oid:next((x for x in orders if x['order_id']==oid),None))
    yield


def test_tool_manifest_counts_and_source_classifications():
    s=d.specs()
    assert len(s)==60
    assert len({x['name'] for x in s})==60
    assert {x['role'] for x in s}==set(d.GROUPS)
    assert any(x['is_write'] and x['evidence_type']=='simulated' for x in s)


def test_policy_derived_from_order_data(sample):
    a=d.eligibility('fixture_order_0008')
    assert a['delay_days']==9
    assert a['tier']=='shipping_fee'
    assert a['estimated_refund_brl']=='10.00'
    b=d.eligibility('fixture_order_0015')
    assert b['tier']=='full_order_value'
    assert b['estimated_refund_brl']=='100.00'
    assert b['requires_human_approval']


def test_refund_actions_reject_without_approval(sample,monkeypatch,tmp_path):
    monkeypatch.setattr(d,'OUTBOX',tmp_path/'outbox.jsonl')
    assert not d.create_request('fixture_order_0008',approved=False)['created']
    assert not (tmp_path/'outbox.jsonl').exists()
    result=d.create_request('fixture_order_0008',approved=True)
    assert result['created'] and not result['real_refund_issued']
    assert (tmp_path/'outbox.jsonl').exists()


def test_150_cases_are_source_linked_and_split(sample):
    a=d.generate_cases(seed=23)
    b=d.generate_cases(seed=23)
    assert a==b
    assert len(a['cases'])==150
    assert sum(x['split']=='train' for x in a['cases'])==100
    assert sum(x['split']=='held_out' for x in a['cases'])==50
    assert len({x['order_id'] for x in a['cases']})==150
    assert all(x['gold_chain'] for x in a['cases'])
