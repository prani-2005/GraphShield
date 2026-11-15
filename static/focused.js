"use strict";
const panels=[...document.querySelectorAll('[data-jump]')];
for(const button of panels){button.addEventListener('click',()=>{panels.forEach(x=>x.classList.toggle('active',x===button));document.getElementById(button.dataset.jump)?.scrollIntoView({behavior:'smooth',block:'start'});});}
fetch('/api/health').then(r=>r.json()).then(v=>{const el=document.getElementById('health');el.textContent=v.hydradb_connected?'● HydraDB connected':'● HydraDB offline';el.className='badge'+(v.hydradb_connected?'':' bad')}).catch(()=>{document.getElementById('health').textContent='● Database unavailable'});
