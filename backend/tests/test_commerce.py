"""Read-only commerce contract tests; no fake orders shipped in product bundle."""
from pathlib import Path
import pytest
from graphshield import commerce_mcp as c
from graphshield.demo_features import validate_readonly_args
from graphshield.real_mcp import RECIPES

@pytest.mark.xfail(reason="Legacy pre-Refund-Desk workflow/UI contract retired in V8.2/V9",strict=True)
def test_commerce_recipes_use_real_mcp_names():
    tasks={r[0]:r[2] for r in RECIPES}
    assert tasks['commerce_order_investigation']==[
        'get_order_status','get_customer_context','get_order_items',
        'get_order_payments','assess_delivery_timing']

def test_rejects_unsafe_order_ids():
    tool={'name':'get_order_status','server':'commerce_evidence'}
    assert validate_readonly_args(tool,{'order_id':'abc123'})=={'order_id':'abc123'}
    with pytest.raises(ValueError):validate_readonly_args(tool,{'order_id':'../../secrets'})
    with pytest.raises(ValueError):validate_readonly_args(tool,{'order_id':'abc','filename':'x'})

def test_missing_data_is_not_fabricated(tmp_path,monkeypatch):
    monkeypatch.setenv('GRAPHSHIELD_COMMERCE_DATA_DIR',str(tmp_path))
    c._rows.cache_clear()
    with pytest.raises(FileNotFoundError):c.get_order_status('abc123')

def test_delayed_order_status_from_fixture(tmp_path,monkeypatch):
    # In-memory test rows check behavior; NOT distributed as business records.
    import csv
    order={'order_id':'real_format_id','customer_id':'cust','order_status':'delivered',
           'order_estimated_delivery_date':'2018-01-01 00:00:00',
           'order_delivered_customer_date':'2018-01-04 00:00:00'}
    with (tmp_path/'olist_orders_dataset.csv').open('w',newline='') as h:
        writer=csv.DictWriter(h,fieldnames=order.keys());writer.writeheader();writer.writerow(order)
    monkeypatch.setenv('GRAPHSHIELD_COMMERCE_DATA_DIR',str(tmp_path))
    c._rows.cache_clear()
    assert c.assess_delivery_timing('real_format_id')['days_after_estimate']==3
    assert c.find_delayed_orders()['cases'][0]['order_id']=='real_format_id'
