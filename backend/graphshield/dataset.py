"""Deterministic synthetic task/tool registry; not a claim about public MCP coverage."""
from __future__ import annotations
import json
from pathlib import Path

CAPABILITIES = [
    ('pdf_parse', 'Extract text and structure from financial PDFs'),
    ('table_extract', 'Recognize accounting tables from parsed text'),
    ('company_resolve', 'Resolve company identifier and record'),
    ('taxonomy_lookup', 'Find relevant taxonomy version and concept'),
    ('tag_recommend', 'Recommend financial concept tags'),
    ('tag_validate', 'Validate financial tags against taxonomy'),
    ('xhtml_export', 'Export structured tagged XHTML'),
    ('invoice_parse', 'Extract invoice line items'),
    ('currency_convert', 'Convert currencies for transactions'),
    ('expense_classify', 'Classify spend categories'),
    ('emissions_factor', 'Look up greenhouse-gas emission factors'),
    ('carbon_calculate', 'Compute transaction emissions'),
    ('contract_parse', 'Extract legal contract clauses'),
    ('clause_check', 'Check policy compliance for clauses'),
    ('risk_score', 'Compute policy or financial risk score'),
    ('report_write', 'Draft final report from verified results'),
]
DEPENDENCIES = {
 'table_extract': ['pdf_parse'],
 'tag_recommend': ['table_extract', 'taxonomy_lookup', 'company_resolve'],
 'tag_validate': ['tag_recommend'],
 'xhtml_export': ['tag_validate'],
 'expense_classify': ['invoice_parse'],
 'carbon_calculate': ['expense_classify', 'emissions_factor'],
 'clause_check': ['contract_parse'],
 'risk_score': ['clause_check'],
 'report_write': ['risk_score'],
}
TASK_TYPES = [('accounts', 'xhtml_export'), ('tagging','tag_validate'),
              ('emissions','carbon_calculate'), ('legal','report_write'),
              ('invoice','expense_classify'), ('extraction','table_extract')]

def build_dataset(tool_count=160, task_count=48):
    if tool_count < len(CAPABILITIES) * 2 or task_count < 6:
        raise ValueError('at least 32 tools and 6 tasks required')
    tools = []
    for i in range(tool_count):
        cap, _ = CAPABILITIES[i % len(CAPABILITIES)]
        variant = i // len(CAPABILITIES)
        tools.append({
            'id': 10000+i, 'name': f'{cap}_{variant}_tool', 'capability': cap,
            'description': f'{cap.replace("_", " ")} integration provider {variant}. ' +
                           'Use for verified workflow capabilities and structured outputs.',
            'schema': {'name': f'{cap}_{variant}_tool', 'description': f'Provides {cap} version {variant}.',
                       'parameters': {'type':'object','properties': {'input':{'type':'string'},
                          'entity_id':{'type':'string'}}, 'required':['input']}},
            'version': f'1.{variant}.0', 'status': 'healthy',
            'priority': max(1, 100-variant*5),
        })
    tasks = []
    for i in range(task_count):
        family, target = TASK_TYPES[i % len(TASK_TYPES)]
        tasks.append({'id': 30000+i, 'key': f'{family}_{i:03}', 'description':
          f'Execute {family} processing for synthetic company {i%12} and produce verified results',
          'target':target, 'entity_key': f'company_{i%12}'})
    entities = [{'key': f'company_{i}', 'value': f'Demo Corp {i} Ltd',
                 'source': 'synthetic benchmark registry'} for i in range(12)]
    return {'tools':tools,'tasks':tasks,'capabilities':CAPABILITIES,
            'dependencies':DEPENDENCIES,'entities':entities}

def export_dataset(folder='data', tool_count=160, task_count=48):
    d=build_dataset(tool_count,task_count)
    p=Path(folder); p.mkdir(parents=True,exist_ok=True)
    for name in ('tools','tasks','entities','dependencies'):
        (p/f'{name}.json').write_text(json.dumps(d[name],indent=2),encoding='utf-8')
    return d
