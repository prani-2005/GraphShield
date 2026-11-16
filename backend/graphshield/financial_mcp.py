"""Real, read-only financial reporting MCP adapter for operator-provided XHTML/iXBRL.

This server never manufactures reports, XBRL facts or taxonomy validations.
Reads only actual files in REPORTING_DOCUMENTS_DIR, never writes or runs commands.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
from collections import Counter
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

server=FastMCP('GraphShield Financial Reporting Operations')
MAX_BYTES=10_000_000
EXTENSIONS={'.html','.htm','.xhtml','.xml'}


def root_dir():
    return Path(os.getenv('REPORTING_DOCUMENTS_DIR', str(Path.home()/'GraphShieldReports'))).expanduser().resolve()


def document_path(filename:str):
    if not filename or Path(filename).name!=filename or '/' in filename or '\\' in filename:
        raise ValueError('Only a filename within the permitted reporting directory is allowed')
    root=root_dir();path=(root/filename).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in EXTENSIONS or not path.is_file():
        raise FileNotFoundError('Report not found in the configured directory')
    if path.stat().st_size>MAX_BYTES:raise ValueError('Document exceeds 10 MB demo limit')
    return path


def _doc(filename):
    path=document_path(filename)
    raw=path.read_bytes()
    return path, BeautifulSoup(raw,'html.parser'),hashlib.sha256(raw).hexdigest()


@server.tool()
def list_reporting_documents() -> dict:
    """List real XHTML/iXBRL financial reports in the authorized reporting directory."""
    root=root_dir()
    if not root.exists():
        return {'configured_directory':str(root),'documents':[],
                'warning':'Directory does not exist. Copy actual financial XHTML/iXBRL files here; no sample data generated.'}
    files=[]
    for p in sorted(root.iterdir()):
        if p.is_file() and p.suffix.lower() in EXTENSIONS and p.stat().st_size<=MAX_BYTES:
            files.append({'filename':p.name,'bytes':p.stat().st_size})
    return {'configured_directory':str(root),'documents':files,'count':len(files)}


@server.tool()
def inspect_filing_metadata(filename:str) -> dict:
    """Inspect report title, table count, inline XBRL fact count and source hash."""
    path,dom,digest=_doc(filename)
    title=dom.title.get_text(' ',strip=True) if dom.title else ''
    facts=dom.find_all(lambda tag:tag.name and tag.name.lower().split(':')[-1] in ('nonfraction','nonnumeric'))
    return {'filename':path.name,'sha256':digest,'title':title,
            'tables':len(dom.find_all('table')),'inline_xbrl_fact_count':len(facts),
            'source':'actual local XHTML/iXBRL file','limitation':'Metadata inspection is not official taxonomy validation'}


@server.tool()
def extract_financial_tables(filename:str, max_tables:int=15, max_rows:int=30) -> dict:
    """Read actual financial HTML tables, headings and cells without changing the report."""
    _,dom,digest=_doc(filename)
    if not 1<=max_tables<=30 or not 1<=max_rows<=100:raise ValueError('Requested extraction exceeds demo limits')
    tables=[]
    for idx,table in enumerate(dom.find_all('table')[:max_tables]):
        rows=[]
        for tr in table.find_all('tr')[:max_rows]:
            cells=[c.get_text(' ',strip=True)[:250] for c in tr.find_all(['td','th'],recursive=False)]
            if cells:rows.append(cells)
        tables.append({'table_index':idx,'rows':rows,'row_count_returned':len(rows)})
    return {'filename':filename,'source_sha256':digest,'table_count_total':len(dom.find_all('table')),
            'tables':tables,'note':'Actual HTML table cells; no OCR or interpretation of financial meaning'}


@server.tool()
def extract_inline_xbrl_facts(filename:str, max_facts:int=150) -> dict:
    """Extract actual ix:nonFraction and ix:nonNumeric facts with source attributes."""
    _,dom,digest=_doc(filename)
    if not 1<=max_facts<=500:raise ValueError('max_facts must be between 1 and 500')
    nodes=dom.find_all(lambda tag:tag.name and tag.name.lower().split(':')[-1] in ('nonfraction','nonnumeric'))
    result=[]
    for node in nodes[:max_facts]:
        result.append({'concept':node.get('name'),'contextRef':node.get('contextref'),
                       'unitRef':node.get('unitref'),'decimals':node.get('decimals'),
                       'value':node.get_text(' ',strip=True)[:300],
                       'kind':node.name.split(':')[-1]})
    return {'filename':filename,'source_sha256':digest,'fact_count_total':len(nodes),
            'facts':result,'truncated':len(nodes)>max_facts,
            'note':'Extracted source values only; no arithmetic or taxonomy validation'}


@server.tool()
def audit_filing_structure(filename:str) -> dict:
    """Check document structure and obvious missing iXBRL attributes; not regulatory compliance."""
    _,dom,digest=_doc(filename)
    findings=[]
    if not dom.title:findings.append({'severity':'info','code':'NO_TITLE','detail':'HTML title element not present'})
    for idx,t in enumerate(dom.find_all('table')):
        if not t.find('tr'):findings.append({'severity':'warning','code':'EMPTY_TABLE','table_index':idx})
    facts=dom.find_all(lambda tag:tag.name and tag.name.lower().split(':')[-1] in ('nonfraction','nonnumeric'))
    for i,node in enumerate(facts):
        if not node.get('name'):findings.append({'severity':'warning','code':'FACT_NO_CONCEPT','fact_index':i})
        if not node.get('contextref'):findings.append({'severity':'warning','code':'FACT_NO_CONTEXT_REF','fact_index':i})
    return {'filename':filename,'source_sha256':digest,'fact_count':len(facts),
            'finding_count':len(findings),'findings':findings[:100],
            'validation_level':'STRUCTURAL_ONLY',
            'disclosure':'Not XBRL formula validation, not filing acceptance, not UK FRC/Companies House compliance validation'}


@server.tool()
def filing_capability_report(filename:str) -> dict:
    """Produce a factual capability summary from a real financial report, without edits."""
    meta=inspect_filing_metadata(filename)
    audit=audit_filing_structure(filename)
    return {'metadata':meta,'structure_audit':audit,
            'next_review':'Human review or independent official taxonomy validator required'}


if __name__=='__main__':
    server.run(transport='stdio')
