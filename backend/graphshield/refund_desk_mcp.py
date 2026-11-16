"""Runnable MCP adapter, partitioned by domain role and optional provider.

MCP tool names/schemas come from functions registered here via FastMCP.
Historical evidence is sourced from original Olist files. Provider replication
is simulated: all instances use the same CSV snapshot; no independent vendor.
"""
import hashlib, os, time
from mcp.server.fastmcp import FastMCP
from .refund_desk import GROUPS, invoke

role=os.environ.get('GRAPHSHIELD_DESK_ROLE','orders')
if role not in GROUPS:raise ValueError('Invalid role')
provider=os.environ.get('GRAPHSHIELD_DESK_PROVIDER','primary')
mcp=FastMCP(f'GraphShield Refund Desk: {role}/{provider}')


def _read_handler(name):
    def tool(order_id: str) -> dict:
        _simulate_transport(name,order_id)
        return invoke(name,order_id)
    return tool


def _action_handler(name):
    def tool(order_id: str, approved: bool=False) -> dict:
        _simulate_transport(name,order_id)
        return invoke(name,order_id,approved=approved)
    return tool


def _simulate_transport(name,order_id):
    """Explicitly injected deterministic latency/outage, disabled by default."""
    ms=max(0,min(5000,int(os.getenv('GRAPHSHIELD_DESK_LATENCY_MS','0'))))
    if ms:time.sleep(ms/1000)
    probability=max(0,min(1,float(os.getenv('GRAPHSHIELD_DESK_FAILURE_RATE','0'))))
    if probability:
        sample=int.from_bytes(hashlib.sha256((role+'|'+provider+'|'+name+'|'+order_id).encode()).digest()[:8],'big')/2**64
        if sample<probability:raise RuntimeError('INJECTED simulated provider failure')

for name,description,handler in GROUPS[role]:
    tool=_action_handler(name) if handler=='write' else _read_handler(name)
    mcp.add_tool(tool,name=name,description=description+(' [SIMULATED; SANDBOX ONLY]' if handler=='write' else ''))

if __name__=='__main__':mcp.run()
