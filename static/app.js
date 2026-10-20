const $=id=>document.getElementById(id);
let iface='',history=[],lastHistory=0,lastSample=null;
const num=n=>(Number(n)||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const safe=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function load(){
 try{
  const response=await fetch('/api/state',{cache:'no-store'});if(!response.ok)throw Error('HTTP '+response.status);
  const s=await response.json();lastSample=s;
  $('status').textContent=s.error?'● Collector error':'● Live';$('status').style.color=s.error?'#ffd17d':'#70efbb';
  const names=Object.keys(s.interfaces).sort();
  if(!names.includes(iface))iface=names.includes('enp5s0f0np0')?'enp5s0f0np0':(names[0]||'');
  if([...$('interface').options].map(o=>o.value).join('|')!==names.join('|')){
    $('interface').replaceChildren(...names.map(n=>new Option(n,n)));$('interface').value=iface;
  }
  const n=s.interfaces[iface]||{rx:0,tx:0};
  $('rx').textContent=num(s.totals.rx);$('tx').textContent=num(s.totals.tx);
  $('throughput').textContent=num(n.rx+n.tx);
  $('count').textContent=new Set(s.clients.map(c=>c.ip)).size;
  $('breakdown').textContent=s.clients.filter(c=>c.protocol==='SMB').length+' SMB · '+s.clients.filter(c=>c.protocol==='iSCSI').length+' iSCSI sessions';
  const types=[...new Set(s.clients.map(c=>c.protocol))].sort(),select=$('protocol'),old=select.value;
  if([...select.options].slice(1).map(o=>o.value).join('|')!==types.join('|')){
    select.replaceChildren(new Option('All protocols','All'),...types.map(t=>new Option(t,t)));select.value=types.includes(old)?old:'All';
  }
  renderClients(s.clients);$('foot').textContent=s.error?'Collector: '+s.error:'Last sampled '+new Date(s.timestamp*1000).toLocaleTimeString()+' · TCP rates are estimates; interface counters include all protocols';
  if(Date.now()-lastHistory>5000){lastHistory=Date.now();await fetchHistory()}
 }catch(e){$('status').textContent='● Offline';$('foot').textContent=String(e)}
}
function renderClients(data){
 const filter=$('protocol').value,sort=$('sort').value;
 const rows=data.filter(c=>filter==='All'||c.protocol===filter);
 rows.sort((a,b)=>sort==='ip'?a.ip.localeCompare(b.ip):(b[sort]||((b.rx+b.tx)))-(a[sort]||((a.rx+a.tx))));
 $('clients').innerHTML=rows.length?rows.map(c=>'<tr><td>'+safe(c.ip)+'</td><td><span class="tag '+(c.protocol==='iSCSI'?'iscsi':c.protocol==='Other TCP'?'other':'')+'">'+safe(c.protocol)+'</span></td><td>'+c.connections+'</td><td>'+num(c.rx)+' MB/s</td><td>'+num(c.tx)+' MB/s</td></tr>').join(''):'<tr><td colspan="5" class="empty">No active connections match this filter.</td></tr>';
}
async function fetchHistory(){
 if(!iface)return;
 try{const r=await fetch('/api/history?interface='+encodeURIComponent(iface)+'&seconds='+$('range').value);history=await r.json();draw()}catch(e){}
}
function draw(){
 const canvas=$('chart'),ctx=canvas.getContext('2d'),rect=canvas.getBoundingClientRect(),dpr=devicePixelRatio||1;
 canvas.width=Math.round(rect.width*dpr);canvas.height=Math.round(rect.height*dpr);ctx.scale(dpr,dpr);
 const w=rect.width,h=rect.height,left=50,right=12,top=12,bottom=25,cw=w-left-right,ch=h-top-bottom;
 ctx.clearRect(0,0,w,h);const max=Math.max(1,...history.flatMap(p=>[p.rx,p.tx]))*1.15;
 ctx.font='11px system-ui';ctx.textAlign='right';ctx.fillStyle='#91a6b9';
 for(let i=0;i<5;i++){let y=top+ch*i/4;ctx.strokeStyle='#314759';ctx.setLineDash([3,5]);ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();ctx.fillText(num(max*(4-i)/4),left-8,y+4)}ctx.setLineDash([]);
 if(history.length<2){ctx.textAlign='center';ctx.fillText('Collecting history…',w/2,h/2);return}
 const first=history[0].ts,last=history[history.length-1].ts,span=Math.max(1,last-first);
 for(const [field,color] of [['tx','#4fe0aa'],['rx','#66baff']]){
  ctx.beginPath();history.forEach((p,i)=>{const x=left+(p.ts-first)/span*cw,y=top+ch-(p[field]/max)*ch;i?ctx.lineTo(x,y):ctx.moveTo(x,y)});
  ctx.strokeStyle=color;ctx.lineWidth=2.5;ctx.lineJoin='round';ctx.stroke();
 }
 ctx.fillStyle='#91a6b9';ctx.textAlign='left';ctx.fillText(new Date(first*1000).toLocaleTimeString(),left,h-4);ctx.textAlign='right';ctx.fillText(new Date(last*1000).toLocaleTimeString(),w-right,h-4);
}
$('interface').addEventListener('change',e=>{iface=e.target.value;lastHistory=0;load()});
$('range').addEventListener('change',()=>{lastHistory=0;load()});
$('protocol').addEventListener('change',()=>lastSample&&renderClients(lastSample.clients));
$('sort').addEventListener('change',()=>lastSample&&renderClients(lastSample.clients));
window.addEventListener('resize',draw);
load();setInterval(load,1000);
