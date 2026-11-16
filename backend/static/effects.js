'use strict';
/* Hero proof numbers come from real result files via the API; nothing here is hard-coded evidence. */
(()=>{
const $=id=>document.getElementById(id);
const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
function countUp(el,to,{dec=0,suffix=''}={}){
 if(reduce||!isFinite(to)){el.textContent=to.toFixed(dec)+suffix;return}
 const t0=performance.now(),dur=900;
 (function f(t){const k=Math.min(1,(t-t0)/dur),e=1-Math.pow(1-k,3);el.textContent=(to*e).toFixed(dec)+suffix;if(k<1)requestAnimationFrame(f)})(t0)}
async function get(url){const r=await fetch(url);if(!r.ok)throw Error(r.status);return r.json()}
function setProof(id,value,label,opts,warn){const n=$(id);if(!n)return;countUp(n.querySelector('.n'),value,opts);n.querySelector('.l').textContent=label;n.querySelector('.n').classList.toggle('warn',!!warn)}
async function loadProof(){
 try{const reg=await get('/api/refund-desk/registry');const count=reg.actual_discovered_entries||reg.unique_domain_definitions;
  if(count)setProof('proofTools',count,'tools the agent could be handed',{}) }catch(e){}
 let d=null,dry=false;
 try{d=await get('/api/refund-desk/online-learning')}catch(e){try{d=await get('/api/refund-desk/online-learning?dryrun=true');dry=true}catch(e2){}}
 if(d){const a=d.headline.failed_attempts_reduction_vs_static_primary_first_pct;
  if(a!=null)setProof('proofFail',Math.abs(a),(a>=0?'fewer':'more')+' failed attempts than a static router'+(dry?' (DRY RUN, not HydraDB)':''),{suffix:'%'},dry)}}
window.addEventListener('gs:trace-selected',e=>{const n=e.detail;setProof('proofLoaded',n.loaded,`tools loaded for this task (of ${n.total||'all'})`,{})});
/* stagger children of the graph + trace so the path "draws itself" */
function stagger(node){[...node.children].forEach((c,i)=>c.style.setProperty('--i',i))}
function tagEvents(node){node.querySelectorAll('.desk-event').forEach(el=>{const t=el.textContent.toUpperCase();
 if(t.includes('REROUTED'))el.classList.add('reroute')})}
function watch(id,fn){const n=$(id);if(n)new MutationObserver(()=>fn(n)).observe(n,{childList:true})}
document.addEventListener('DOMContentLoaded',()=>{
 loadProof();watch('deskGraph',stagger);watch('deskTrace',tagEvents);
 watch('deskGraph',n=>{const loaded=n.querySelectorAll('.desk-node:not(.task)').length;
  if(loaded)window.dispatchEvent(new CustomEvent('gs:trace-selected',{detail:{loaded,total:parseInt(($('proofTools')?.querySelector('.n')||{}).textContent)||0}}))})});
})();
