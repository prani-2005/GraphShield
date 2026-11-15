'use strict';
(()=>{
const $=id=>document.getElementById(id);
const escapeText=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let currentCase=null, currentTrace=[], isRunning=false, allCases=[];
const INTENTS={late_delivery_refund:{label:'Late-delivery refund',goal:'My order arrived late. I want a refund.',summary:'Refund assessment (simulated policy)'},payment_question:{label:'Payment inquiry',goal:'Can you explain the payment breakdown for my order?',summary:'Payment evidence (historical data)'},wrong_item_inquiry:{label:'Wrong-item inquiry',goal:'I received the wrong item. Which product IDs were actually recorded for my order?',summary:'Items and product IDs (historical data)'},order_status:{label:'Order status',goal:'Where is my order? Show the recorded status and delivery timeline.',summary:'Historical order status'}};
const setStatus=(txt,bad=false)=>{$('deskStatus').textContent=txt;$('deskStatus').className='status'+(bad?' bad':'')};
async function jsonAPI(path,options={}){const r=await fetch(path,options);const body=await r.json();if(!r.ok)throw Error(body.detail||`HTTP ${r.status}`);return body}
function row(name,value){return `<div class="metric-row"><span class="muted">${escapeText(name)}</span><strong>${escapeText(value)}</strong></div>`}
function onEvent(evt){currentTrace.push(evt);
 const tag=escapeText(evt.event.replaceAll('_',' ').toUpperCase());
 const detail=evt.event==='graph_context'?`${evt.selected.length} tools · ${evt.graph_queries} HydraDB queries · ${evt.estimated_tool_schema_tokens} estimated schema tokens`:
 evt.event==='step_started'?`${evt.index}. ${evt.name} · ${evt.provider}`:
 evt.event==='step_result'?`${evt.tool_key} · MCP response received`:
 evt.event==='entity_cache'?`HydraDB cache ${evt.hit?'HIT':'MISS'} · avoided lookup: ${evt.lookup_skipped}`:
 evt.event==='step_failed'?`Step ${evt.index}: ${evt.error}`:
 evt.event==='rerouted'?`${evt.previous} → ${evt.alternative}`:
 evt.event==='assessment'?`Demo policy: ${evt.derived.tier} · BRL ${evt.derived.estimated_refund_brl}`:
 evt.event==='case_summary'?`${(INTENTS[evt.intent]||{}).label||evt.intent} · ${evt.tool_calls} actual MCP calls`:
 evt.event==='done'?`${evt.tool_calls} MCP calls · ${evt.failed_attempts} failed attempts · ${evt.elapsed_ms} ms`:
 evt.event==='error'?evt.message:(evt.message||evt.entity_key||'');
 const el=document.createElement('div');el.className='desk-event '+(evt.event.includes('fail')||evt.event==='error'?'bad':'');
 el.innerHTML=`<div class="tiny muted">${tag}</div><strong>${escapeText(detail)}</strong>`;
 if(evt.event==='step_result'){
  const d=document.createElement('details');d.innerHTML='<summary class="tiny muted">Inspect source-backed MCP result</summary><pre>'+escapeText(JSON.stringify(evt.result,null,2).slice(0,6000))+'</pre>';el.append(d);
 }
 $('deskTrace').append(el);
 if(evt.event==='graph_context'){
  const chosen=evt.selected||[];
  $('deskGraph').innerHTML='<div class="desk-node task">CUSTOMER REQUEST</div>'+chosen.map((t,i)=>`<div class="desk-flow">↓ REQUIRED CAPABILITY</div><div class="desk-node"><strong>${escapeText(t.name)}</strong><span>${escapeText(t.server)}</span></div>`).join('');
  $('deskRejected').textContent=(evt.rejected||[]).map(r=>`${r.name||r.tool_key} / ${r.server}: ${r.reason}`).join('\n')||'No alternatives rejected.';
  $('deskKpis').innerHTML=row('Selected tool schemas',chosen.length)+row('DB queries',evt.graph_queries)+row('Schema tokens (estimated)',evt.estimated_tool_schema_tokens)+row('Rejected alternatives',(evt.rejected||[]).length);
 }
 if(evt.event==='done')$('deskKpis').innerHTML+=row('MCP calls executed',evt.tool_calls)+row('Failed attempts',evt.failed_attempts)+row('End-to-end trace time',evt.elapsed_ms+' ms');
 if(evt.event==='assessment')$('deskAssessment').innerHTML=`<strong>${escapeText(evt.derived.tier)}</strong><p>Illustrative amount BRL ${escapeText(evt.derived.estimated_refund_brl)} · ${escapeText(evt.derived.delay_days)} days late</p><div class="disclosure">This policy was invented for the demonstration. No actual refund rights are assessed and no real refund is issued.</div>`;
 if(evt.event==='case_summary')$('deskAssessment').innerHTML=`<strong>${escapeText(INTENTS[evt.intent].summary)}</strong><p>Inspect the source-backed MCP step results for this order. These records cannot establish a real customer complaint, delivery mismatch, or live tracking.</p><div class="disclosure">${escapeText(evt.note)}</div>`;
 if(evt.event==='error')setStatus(evt.message,true);
}
async function run(followup=false,simulate_failure=false){if(isRunning)return;const order_id=currentCase?.order_id;if(!order_id){setStatus('Load original Olist cases first.',true);return}
 isRunning=true;$('deskTrace').replaceChildren();$('deskGraph').replaceChildren();currentTrace=[];setStatus('Running read-only MCP calls and HydraDB traversal…');
 try{
  const r=await fetch('/api/refund-desk/trace',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id,intent:currentCase.intent,followup,simulate_failure,execute_mcp:true})});
  if(!r.ok){let x=await r.json();throw Error(x.detail||'Request failed')}
  const rd=r.body.getReader(),decoder=new TextDecoder();let pending='';
  while(true){let {done,value}=await rd.read();if(done)break;pending+=decoder.decode(value,{stream:true});const items=pending.split('\n\n');pending=items.pop();for(const item of items){const line=item.split('\n').find(x=>x.startsWith('data: '));if(line)onEvent(JSON.parse(line.slice(6)))}}
  if(!currentTrace.some(x=>x.event==='error'))setStatus('Trace complete. All events are inspectable below.');
 }catch(e){setStatus(e.message,true)}finally{isRunning=false}}
function selectIntent(){
 const intent=$('deskIntent').value;
 const eligible=allCases.filter(x=>x.intent===intent);
 $('deskCase').replaceChildren();
 for(const c of eligible){const opt=document.createElement('option');opt.value=c.case_id;opt.textContent=`${c.case_id} · ${c.order_id.slice(0,12)}… · ${c.observed_delay_days} days late`; $('deskCase').append(opt)}
 currentCase=(intent==='late_delivery_refund'?eligible.find(x=>x.observed_delay_days===9):null)||eligible[0]||null;
 if(currentCase)$('deskCase').value=currentCase.case_id;
 $('deskCase').onchange=()=>{currentCase=eligible.find(x=>x.case_id===$('deskCase').value)||null;showCase()};
 showCase();
 setStatus(`Loaded ${eligible.length} ${INTENTS[intent].label.toLowerCase()} cases from the historical Olist evaluation set.`);
}
async function load(){try{const r = await jsonAPI('/api/refund-desk/cases');
const reg = await jsonAPI('/api/refund-desk/registry').catch(e => ({
  unique_domain_definitions: 'Unavailable',
  actual_discovered_entries: 'Unavailable',
  providers: [],
  error: e.message
}));
 allCases=r.cases||[];selectIntent();
 $('deskRegistry').innerHTML=row('Domain capability definitions',reg.unique_domain_definitions)+row('MCP discovered entries',reg.actual_discovered_entries)+row('Provider instances',reg.providers.length)+row('Train / held-out cases',`${r.train_count} / ${r.held_out_count}`)+row('Evaluation intents',new Set(allCases.map(x=>x.intent)).size);
 }catch(e){setStatus('Setup required: '+e.message,true)}}
function showCase(){
 const intent=currentCase?.intent||$('deskIntent').value;
 const meta=INTENTS[intent];
 $('deskRequest').value=meta.goal;
 $('deskCaseBanner').textContent=meta.goal;
 $('deskAssessmentTitle').textContent=meta.summary;
 $('deskAssessment').textContent='Run an investigation to inspect historical tool evidence.';
 $('deskCaseNote').textContent=currentCase?`Case ${currentCase.case_id} · ${currentCase.split} set · order ${currentCase.order_id} · observed ${currentCase.observed_delay_days}-day delay (all 150 selected historical orders were late). Curated scenario; not an actual complaint.`:'No cases for this intent.';
 const refund=intent==='late_delivery_refund';
 $('deskRunFollow').disabled=!refund;
 $('deskSimOutage').disabled=!refund;
 $('deskRestore').disabled=!refund;
 $('deskRunFirst').textContent=refund?'1 · Investigate refund':'1 · Inspect '+meta.label.toLowerCase();
 $('deskTrace').replaceChildren();$('deskGraph').replaceChildren();$('deskKpis').textContent='Run an investigation to see actual counts.';
}
$('deskIntent').onchange=selectIntent;
$('deskLoadCases').onclick=load;
$('deskLoadExperiment').onclick=async()=>{try{let d=await jsonAPI('/api/refund-desk/experiment');let rows=d.summary.filter(x=>x.system==='graphshield_learned');$('deskExperiment').innerHTML=rows.map(x=>`<div class="metric-row"><span>Iteration ${x.iteration}</span><strong>${(100*x.first_try_success.mean).toFixed(1)}% first-try success (injected faults)</strong></div>`).join('')+`<div class="disclosure">${escapeText(d.limitations.join(' · '))}</div>`}catch(e){$('deskExperiment').textContent='No results available: '+e.message+'. Run python -m graphshield.refund_experiment first.'}};

$('deskRunFirst').onclick=()=>run(false,false);
$('deskRunFollow').onclick=()=>run(true,false);
$('deskSimOutage').onclick=async()=>{if(currentCase?.intent!=='late_delivery_refund'){setStatus('Outage replay is enabled for refunds only.',true);return}try{let r=await jsonAPI('/api/refund-desk/provider-health',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider:'orders_primary',tool_name:'resolve_order'})});setStatus('SIMULATED provider outage recorded in HydraDB. Running Session B…');await run(false,false)}catch(e){setStatus(e.message,true)}};
$('deskRestore').onclick=async()=>{try{await jsonAPI('/api/refund-desk/provider-health',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider:'orders_primary',tool_name:'resolve_order',restore:true})});setStatus('Primary restored in HydraDB. Resolve again to check routing.')}catch(e){setStatus(e.message,true)}};
async function showLlmStatus(){
 try {let c=await jsonAPI('/api/refund-desk/llm-status');
  $('deskLlmStatus').textContent=c.configured?('Groq ready to test · model: '+c.model+' · key loaded by this FastAPI process'):'Groq NOT configured in this FastAPI process. Set key + model in the Uvicorn PowerShell window, then restart the server.';
  $('deskLlmStatus').className='status'+(c.configured?'':' bad');
  $('deskRunModel').disabled=!c.configured;
 }catch(e){$('deskLlmStatus').textContent='Unable to check LLM configuration: '+e.message; $('deskRunModel').disabled=true;}
}
function renderAgentEvents(events){
 const container=$('deskModelTrace');container.replaceChildren();
 for(const evt of (events||[])){
  const el=document.createElement('div');el.className='desk-event';
  const label=document.createElement('strong');label.textContent=({llm_response:'MODEL DECISION',graph_context:'HYDRADB CONTEXT',mcp_call:'ACTUAL MCP CALL',outcome_written:'FEEDBACK TO GRAPH',limit_reached:'MODEL TURN LIMIT'})[evt.event]||evt.event;
  const description=document.createElement('div');description.className='small muted';
  description.textContent=evt.event==='llm_response'?('Turn '+evt.turn+' · requested: '+((evt.tool_calls||[]).join(', ')||'final answer')+' · provider-reported usage: '+JSON.stringify(evt.provider_reported_usage||{})):
    evt.event==='graph_context'?('Task: '+(evt.task_key||'preload-all')+' · inspect graph choices and alternatives below'):
    evt.event==='mcp_call'?('Tool: '+evt.tool_key):evt.event==='outcome_written'?'Outcome feedback recorded if validated':'Inspect details';
  const details=document.createElement('details');const sum=document.createElement('summary');sum.textContent='Inspect actual event';details.append(sum);
  const pre=document.createElement('pre');pre.textContent=JSON.stringify(evt,null,2);details.append(pre);
  el.append(label,description,details);container.append(el);
 }
}
$('deskRunModel').onclick=async()=>{if(currentCase?.intent!=='late_delivery_refund'){setStatus('Live LLM agent currently supports only the refund workflow; use the deterministic MCP investigation for other intents.',true);return}
 const order_id=currentCase?.order_id;if(!order_id){setStatus('Select a historical Olist order before running the model.',true);return}
 try{setStatus('Calling real model — API usage is measured from provider responses…');$('deskModelTrace').textContent='Calling model…';
  const mode=$('deskModelMode').value;
  const x=await jsonAPI('/api/refund-desk/agent',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id,mode,goal:$('deskRequest').value})});
  renderAgentEvents(x.events);
  $('deskModelResult').textContent=JSON.stringify({model:x.model,usage:x.usage,model_round_trips:x.model_round_trips,tool_calls:x.tool_calls,failed_attempts:x.failed_attempts,final_message:x.final_message,disclosure:x.disclosure},null,2);
  setStatus('Real model returned provider usage. Inspect its individual decisions above.');
 }catch(e){$('deskModelTrace').textContent='No successful LLM trace.';setStatus(e.message,true)}
};
showLlmStatus();
load();

const ONLINE_STYLE={static_primary_first:['#7c8fa6','Static: primary first'],static_tuned_at_launch:['#e4b56b','Static: tuned at launch'],graphshield_learned:['#40d1be','GraphShield (learned)']};
function drawOnline(d){
 const W=640,H=270,L=60,R=14,T=14,B=50;const windows=[...new Set(d.summary.map(x=>x.window))];
 const vals=d.summary.map(x=>x.failed_attempts_per_case.mean);const ymax=Math.max(0.5,Math.ceil(Math.max(...vals)*10)/10);
 const X=w=>L+(w-1)*(W-L-R)/Math.max(1,windows.length-1),Y=v=>T+(1-v/ymax)*(H-T-B);
 let g='';for(let i=0;i<=4;i++){const v=ymax*i/4;g+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="#26394c"/><text x="${L-6}" y="${Y(v)+4}" text-anchor="end" fill="#93a8bb">${v.toFixed(2)}</text>`}
 d.phases.slice(1).forEach(p=>{const w=p.start/d.window_size+0.5;const x=X(w);g+=`<line x1="${x}" x2="${x}" y1="${T}" y2="${H-B}" stroke="#ff9b9e" stroke-dasharray="4 3"/><text x="${x+4}" y="${T+12}" fill="#ff9b9e">drift</text>`});
 windows.forEach(w=>{g+=`<text x="${X(w)}" y="${H-B+16}" text-anchor="middle" fill="#93a8bb">${w}</text>`});
 g+=`<text x="${(L+W-R)/2}" y="${H-8}" text-anchor="middle" fill="#93a8bb">window of ${d.window_size} cases (mean of ${d.seeds.length} seeds)</text>`;
 g+=`<text transform="translate(12 ${(T+H-B)/2}) rotate(-90)" text-anchor="middle" fill="#93a8bb">failed attempts per case</text>`;
 d.systems.forEach(sys=>{const pts=d.summary.filter(x=>x.system===sys).map(x=>`${X(x.window)},${Y(x.failed_attempts_per_case.mean)}`).join(' ');g+=`<polyline fill="none" stroke="${ONLINE_STYLE[sys][0]}" stroke-width="${sys==='graphshield_learned'?3:2}" points="${pts}"/>`});
 return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Failed attempts per case over time for three routing systems">${g}</svg>`}
function renderOnline(d){
 const legend='<div class="legend">'+d.systems.map(s=>`<span><i style="background:${ONLINE_STYLE[s][0]}"></i>${escapeText(ONLINE_STYLE[s][1])}</span>`).join('')+'</div>';
 const rows=d.systems.map(s=>{const t=d.totals[s];return `<tr><td>${escapeText(ONLINE_STYLE[s][1])}</td><td>${t.failed_attempts_total.mean.toFixed(1)} <span class="muted">(${t.failed_attempts_total.min}-${t.failed_attempts_total.max})</span></td><td>${(100*t.first_try_success_overall.mean).toFixed(1)}%</td><td>${t.unresolved_cases.mean.toFixed(1)}</td></tr>`}).join('');
 const h=d.headline,a=h.failed_attempts_reduction_vs_static_primary_first_pct,b=h.failed_attempts_reduction_vs_static_tuned_at_launch_pct;
 const banner=d.citable_as_hydradb_evidence?'':'<div class="status bad">DRY RUN on an in-memory store. Not HydraDB evidence. Run without --backend memory against HydraDB.</div>';
 const sign=x=>x==null?'n/a':(x>=0?`${x}% fewer`:`${-x}% more`);
 $('deskOnline').innerHTML=banner+legend+drawOnline(d)+`<div class="table-wrap"><table><thead><tr><th>System</th><th>Failed attempts (mean, min-max over seeds)</th><th>First-try success</th><th>Unresolved cases</th></tr></thead><tbody>${rows}</tbody></table></div>`
  +`<div class="metric-row"><span>GraphShield vs static primary-first</span><strong>${sign(a)} failed attempts</strong></div><div class="metric-row"><span>GraphShield vs static tuned-at-launch</span><strong>${sign(b)} failed attempts</strong></div>`
  +`<div class="disclosure">Backend: ${escapeText(d.backend)} · scenario: ${escapeText(d.scenario)} · retry budget ${d.retry_budget_per_case} per case · probe every ${d.learner.probe_every_n_cases} cases. ${escapeText(d.limitations.join(' · '))}</div>`}
$('deskLoadOnline').onclick=async()=>{const sc=$('deskOnlineScenario').value;try{renderOnline(await jsonAPI('/api/refund-desk/online-learning?scenario='+sc))}catch(e){try{renderOnline(await jsonAPI('/api/refund-desk/online-learning?dryrun=true&scenario='+sc))}catch(e2){$('deskOnline').textContent='No results available: '+e.message}}};
})();
