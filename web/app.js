/* SMCDI UCSM 2026 — frontend sin dependencias externas.
 * Interfaz basada en los mockups del PFC y conectada a API REST + WebSocket.
 */
const app = document.getElementById('app');
const toastRoot = document.getElementById('toast-root');

const state = {
  token: localStorage.getItem('smcdi_token') || '',
  user: JSON.parse(localStorage.getItem('smcdi_user') || 'null'),
  ws: null,
  wsTimer: null,
  activeSession: null,
  livePoints: [],
  route: '',
};

const NAV = [
  ['dashboard','Dashboard','◫'],
  ['residents','Residentes','◎'],
  ['monitor','Sesiones de ducha','♨'],
  ['history','Estadísticas','▥'],
  ['ai','Inteligencia Artificial','✦'],
  ['alerts','Alertas','●'],
  ['tam','Encuesta TAM','☷'],
  ['config','Configuración','⚙','ADMINISTRADOR'],
  ['users','Usuarios','◉','ADMINISTRADOR'],
];

function esc(value='') {
  return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}
function fmtNumber(n, digits=1){ const v=Number(n||0); return new Intl.NumberFormat('es-PE',{minimumFractionDigits:digits,maximumFractionDigits:digits}).format(v); }
function fmtDate(value){ if(!value) return '—'; const d=new Date(value); return Number.isNaN(d.getTime()) ? value : d.toLocaleString('es-PE',{dateStyle:'short',timeStyle:'short'}); }
function fmtDuration(s){ s=Math.max(0,Number(s||0)); const m=Math.floor(s/60), sec=Math.floor(s%60); return `${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`; }
function titleCase(s=''){ return String(s).toLowerCase().replace(/(^|\s|_)(\p{L})/gu,(m,a,b)=>a+b.toUpperCase()).replaceAll('_',' '); }
function toast(message, type=''){ const el=document.createElement('div'); el.className=`toast ${type}`; el.textContent=message; toastRoot.appendChild(el); setTimeout(()=>el.remove(),3600); }

async function api(path, options={}){
  const headers = {'Content-Type':'application/json', ...(options.headers||{})};
  if(state.token) headers.Authorization = `Bearer ${state.token}`;
  const res = await fetch(path,{...options,headers});
  const ct = res.headers.get('content-type')||'';
  const data = ct.includes('application/json') ? await res.json() : await res.text();
  if(!res.ok){
    const msg = data?.error?.message || data?.detail || data || `Error ${res.status}`;
    if(res.status===401){ logout(false); }
    throw new Error(msg);
  }
  return data;
}

function statusPill(status){
  const s=String(status||'').toUpperCase();
  const cls = ['ACTIVA','CONECTADO','VALIDA','HABILITADO','RESUELTA'].includes(s) ? 'ok' :
              ['PENDIENTE','PAUSADA','PREPARADA','REVISADA'].includes(s) ? 'warn' :
              ['CRITICA','ERROR','DESCONECTADO','INVALIDA'].includes(s) ? 'bad' : 'info';
  return `<span class="status-pill ${cls}">${esc(titleCase(s||'—'))}</span>`;
}

function routeName(route){
  if(route.startsWith('resident/')) return ['Detalle del residente','Seguimiento individual e historial'];
  return ({
    dashboard:['Dashboard','Comparación operativa, alertas y actividad reciente'],
    residents:['Residentes','Gestión de participantes y perfiles autorizados'],
    monitor:['Monitoreo en tiempo real','Telemetría del ESP32, estado de sesión y seguridad'],
    history:['Historial y reportes','Sesiones registradas, comparación y exportación'],
    ai:['Inteligencia Artificial','Patrones, predicción y evaluación separadas en bloques claros'],
    alerts:['Alertas del sistema','Eventos críticos, atención y trazabilidad'],
    tam:['Encuesta de aceptación tecnológica – TAM','Registro Likert de 20 ítems según el instrumento aprobado'],
    config:['Configuración','Parámetros operativos, seguridad determinística y mantenimiento'],
    users:['Gestión de Usuarios','Cuentas del personal y control de acceso por roles'],
  })[route] || ['Ducha Inteligente','Sistema de gestión y monitoreo'];
}

function shell(content){
  const route=state.route.split('/')[0] || 'dashboard';
  const [title,sub]=routeName(state.route);
  const nav = NAV.filter(n=>!n[3]||n[3]===state.user?.role).map(([id,label,icon])=>
    `<a href="#/${id}" class="nav-item ${route===id?'active':''}"><span class="nav-icon">${icon}</span><span>${label}</span></a>`).join('');
  return `<div class="shell" id="shell">
    <aside class="sidebar">
      <div class="brand"><div class="brand-logo">UC<br>SM</div><div><div class="brand-title">UCSM</div><div class="brand-sub">Ducha Inteligente</div></div></div>
      <nav class="nav">${nav}</nav>
      <div class="sidebar-footer"><button class="logout" onclick="logout()"><span class="nav-icon">◉</span>Cerrar sesión</button></div>
    </aside>
    <main class="main">
      <header class="topbar">
        <button class="mobile-menu" onclick="document.getElementById('shell').classList.toggle('menu-open')">☰</button>
        <div class="top-title"><h2>${esc(title)}</h2><p>${esc(sub)}</p></div>
        <div class="userbox"><div class="bell">●<span class="dot"></span></div><div class="usertext"><strong>${esc(state.user?.full_name||state.user?.username||'Usuario')}</strong><span>${esc(titleCase(state.user?.role||''))}</span></div></div>
      </header>
      <section class="content">${content}</section>
    </main>
  </div>`;
}

function loginView(error=''){
  app.innerHTML=`<div class="login-page">
    <div class="login-card">
      <div class="login-logo">UC<br>SM</div>
      <div class="tiny muted">UCSM</div>
      <h1>Ducha Inteligente</h1>
      <p class="subtitle">Sistema de gestión y monitoreo</p>
      <form id="login-form">
        <input class="input-pill" name="username" autocomplete="username" placeholder="Usuario" value="admin.ucsm" required>
        <input class="input-pill" name="password" type="password" autocomplete="current-password" placeholder="Contraseña" value="Admin2026!" required>
        <button class="btn full" type="submit">Iniciar sesión</button>
      </form>
      ${error?`<div class="login-demo" style="border-color:#efb3b3;color:#8c1e1e">${esc(error)}</div>`:''}
      <div class="login-demo"><b>Demostración local</b><br>Administrador: <span class="mono">admin.ucsm / Admin2026!</span><br>Moderador: <span class="mono">mod.turno1 / Moderador2026!</span></div>
      <button class="login-help" type="button">¿Olvidaste tu contraseña?</button>
    </div>
    <div class="login-footer">© 2026 Universidad Católica de Santa María</div>
  </div>`;
  document.getElementById('login-form').addEventListener('submit', async e=>{
    e.preventDefault(); const fd=new FormData(e.currentTarget);
    try{
      const data=await api('/api/v1/auth/login',{method:'POST',body:JSON.stringify(Object.fromEntries(fd))});
      state.token=data.token; state.user=data.user;
      localStorage.setItem('smcdi_token',state.token); localStorage.setItem('smcdi_user',JSON.stringify(state.user));
      connectWS(); location.hash='#/dashboard'; await render();
    }catch(err){ loginView(err.message); }
  });
}

async function logout(callApi=true){
  if(callApi && state.token){ try{ await api('/api/v1/auth/logout',{method:'POST'}); }catch{} }
  if(state.ws) state.ws.close(); state.ws=null;
  state.token='';state.user=null; localStorage.removeItem('smcdi_token');localStorage.removeItem('smcdi_user');
  loginView();
}

function connectWS(){
  if(!state.token) return;
  if(state.ws && [WebSocket.OPEN,WebSocket.CONNECTING].includes(state.ws.readyState)) return;
  const proto=location.protocol==='https:'?'wss':'ws';
  const ws=new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(state.token)}`); state.ws=ws;
  ws.onmessage=(ev)=>{
    let msg; try{msg=JSON.parse(ev.data)}catch{return}
    if(msg.type==='telemetry'){
      state.activeSession={...(state.activeSession||{}),...msg.data,latest:{
        flow_lmin:msg.data.flow_lmin,volume_l:msg.data.volume_l,temp_c:msg.data.temperature_c,ts:msg.data.timestamp,state:msg.data.state
      }};
      state.livePoints.push({t:Date.now(),v:Number(msg.data.volume_l||0),f:Number(msg.data.flow_lmin||0),temp:Number(msg.data.temperature_c||0)});
      if(state.livePoints.length>90) state.livePoints.shift();
      updateRealtimeDom(msg.data);
    }
    if(msg.type==='alert'){ if(state.route==='alerts') render(); toast('Nueva alerta recibida','error'); }
    if(msg.type==='device_status'){ updateConnectionBadge(msg.data); }
  };
  ws.onclose=()=>{ clearTimeout(state.wsTimer); state.wsTimer=setTimeout(connectWS,2500); };
}

function updateConnectionBadge(data){ const el=document.querySelector('[data-live-connection]'); if(el) el.innerHTML=data?.status==='CONECTADO'?'<span class="live-dot"></span> ESP32 conectado':'ESP32 sin conexión'; }
function updateRealtimeDom(d){
  const map={
    'live-volume':`${fmtNumber(d.volume_l,2)} L`, 'live-flow':`${fmtNumber(d.flow_lmin,2)} L/min`,
    'live-temp':`${fmtNumber(d.temperature_c,1)} °C`, 'live-time':fmtDuration(d.total_duration_s||d.elapsed_s),
    'live-state':titleCase(d.state||d.status), 'live-pauses':String(d.pause_count||0),
  };
  Object.entries(map).forEach(([id,v])=>{const el=document.getElementById(id);if(el)el.textContent=v});
  const target=Number(state.activeSession?.target_l||0), vol=Number(d.volume_l||0);
  const p=target?Math.min(100,vol/target*100):0; const bar=document.getElementById('goal-progress'); if(bar)bar.style.width=`${p}%`;
  const goal=document.getElementById('goal-text'); if(goal)goal.textContent=target?`${fmtNumber(vol,1)} L / ${fmtNumber(target,1)} L`:`${fmtNumber(vol,1)} L`;
  const chart=document.getElementById('live-chart'); if(chart) chart.innerHTML=lineChart(state.livePoints.map((x,i)=>({x:i,y:x.v})),{height:220,color:'#2563eb',fill:true});
}

function lineChart(points,{height=230,color='#2563eb',fill=false}={}){
  if(!points?.length) return '<div class="chart-empty">Sin datos disponibles</div>';
  const w=700,h=height,pad=28; const vals=points.map(p=>Number(p.y||0)); let min=Math.min(...vals),max=Math.max(...vals); if(max===min){max=min+1;} const span=max-min;
  const coords=points.map((p,i)=>{const x=pad+(i/(Math.max(1,points.length-1)))*(w-pad*2);const y=h-pad-((Number(p.y)-min)/span)*(h-pad*2);return [x,y]});
  const poly=coords.map(c=>c.join(',')).join(' '); const area=`${pad},${h-pad} ${poly} ${w-pad},${h-pad}`;
  return `<svg class="svg-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    ${[0,.25,.5,.75,1].map(r=>`<line x1="${pad}" x2="${w-pad}" y1="${pad+r*(h-pad*2)}" y2="${pad+r*(h-pad*2)}" stroke="#e7edf4" stroke-width="1"/>`).join('')}
    ${fill?`<polygon points="${area}" fill="${color}" opacity=".08"/>`:''}
    <polyline points="${poly}" fill="none" stroke="${color}" stroke-width="3" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="${pad}" y="${h-5}" class="axis-label">${esc(points[0]?.label||'Inicio')}</text><text x="${w-pad-40}" y="${h-5}" class="axis-label">${esc(points.at(-1)?.label||'Actual')}</text>
  </svg>`;
}

function pageHeader(title,sub,actions=''){ return `<div class="page-header"><div><h1>${title}</h1><p>${sub}</p></div><div class="page-actions">${actions}</div></div>`; }

async function dashboardView(){
  const d=await api('/api/v1/dashboard');
  const points=(d.daily||[]).map(x=>({label:x.day?.slice(5),y:x.liters}));
  const c=d.comparison||{}; const max=Math.max(Number(c.traditional_avg_l||0),Number(c.intelligent_avg_l||0),1);
  return `${pageHeader('Dashboard','Comparación operativa, alertas y actividad reciente')}
    <div class="grid grid-4">
      <div class="card metric"><div class="metric-label">CONSUMO DE HOY</div><div class="metric-value">${fmtNumber(d.consumption_today_l,1)} L</div><div class="metric-foot blue">${esc(d.date)}</div></div>
      <div class="card metric"><div class="metric-label">SESIONES DE HOY</div><div class="metric-value">${d.sessions_today}</div><div class="metric-foot green">${d.active_sessions} activas</div></div>
      <div class="card metric"><div class="metric-label">REDUCCIÓN INTELIGENTE</div><div class="metric-value">${fmtNumber(d.reduction_pct,1)} %</div><div class="metric-foot green">Tradicional vs Inteligente</div></div>
      <div class="card metric"><div class="metric-label">ALERTAS ACTIVAS</div><div class="metric-value">${d.active_alerts}</div><div class="metric-foot red">Requieren atención</div></div>
    </div>
    <div class="grid grid-73" style="margin-top:18px">
      <div class="card pad"><div class="card-title">Consumo de agua · últimos registros diarios</div><div class="card-sub">Eje Y: litros acumulados · Eje X: fecha</div><div class="chart-box">${lineChart(points,{height:240,color:'#2563eb',fill:true})}</div></div>
      <div class="card pad"><div class="card-title">Comparación por modo</div><div class="card-sub">Promedio de litros por sesión</div><div class="bar-compare">
        <div class="bar-col"><div class="bar" style="height:${Math.max(8,Number(c.traditional_avg_l||0)/max*150)}px"></div><strong>${fmtNumber(c.traditional_avg_l,1)} L</strong><span>Tradicional · n=${c.traditional_n||0}</span></div>
        <div class="bar-col"><div class="bar greenbar" style="height:${Math.max(8,Number(c.intelligent_avg_l||0)/max*150)}px"></div><strong>${fmtNumber(c.intelligent_avg_l,1)} L</strong><span>Inteligente · n=${c.intelligent_n||0}</span></div>
      </div></div>
    </div>
    <div class="card pad" style="margin-top:18px"><div class="card-title">Actividad reciente</div><div class="card-sub">Sesiones registradas por el sistema</div><div class="table-wrap"><table class="data-table"><thead><tr><th>Sesión</th><th>Residente</th><th>Habitación</th><th>Modo</th><th>Consumo</th><th>Estado</th><th>Fecha</th></tr></thead><tbody>
      ${(d.recent||[]).map(r=>`<tr><td class="mono">${esc(r.code)}</td><td>${esc(r.display_name)}</td><td>${esc(r.room||'—')}</td><td>${esc(titleCase(r.mode))}</td><td>${fmtNumber(r.volume_total_l,1)} L</td><td>${statusPill(r.status)}</td><td>${fmtDate(r.started_at)}</td></tr>`).join('')||'<tr><td colspan="7" class="muted">Sin actividad</td></tr>'}
    </tbody></table></div></div>`;
}

async function residentsView(){
  const rows=await api('/api/v1/residentes');
  return `${pageHeader('Residentes','Perfiles codificados, consentimiento y seguimiento',`<button class="btn primary" onclick="openResidentModal()">+ Nuevo residente</button>`)}
    <div class="card filter-panel"><div class="toolbar"><div class="search"><input class="control" id="resident-search" placeholder="Buscar por código, nombre, DNI o habitación" oninput="filterResidentRows(this.value)"></div><span class="status-pill info">${rows.length} registrados</span></div></div>
    <div class="card pad"><div class="table-wrap"><table class="data-table" id="resident-table"><thead><tr><th>Código</th><th>Residente</th><th>DNI</th><th>Hab.</th><th>Sesiones</th><th>Prom. consumo</th><th>Temp. preferida</th><th>Consentimiento</th><th>Estado</th><th></th></tr></thead><tbody>
      ${rows.map(r=>`<tr data-search="${esc(`${r.code} ${r.display_name} ${r.dni||''} ${r.room||''}`.toLowerCase())}"><td class="mono">${esc(r.code)}</td><td><b>${esc(r.display_name)}</b></td><td>${esc(r.dni||'—')}</td><td>${esc(r.room||'—')}</td><td>${r.session_count}</td><td>${fmtNumber(r.avg_volume_l,1)} L</td><td>${fmtNumber(r.preferred_temp,1)} °C</td><td>${r.consent_valid?statusPill('VALIDA'):statusPill('PENDIENTE')}</td><td>${r.enabled?statusPill('HABILITADO'):statusPill('INACTIVO')}</td><td><a class="btn light sm" href="#/resident/${r.id}">Ver</a></td></tr>`).join('')}
    </tbody></table></div></div>`;
}
window.filterResidentRows=(q)=>{q=q.toLowerCase();document.querySelectorAll('#resident-table tbody tr').forEach(tr=>tr.style.display=tr.dataset.search.includes(q)?'':'none')};

async function residentDetailView(id){
  const d=await api(`/api/v1/residentes/${id}`), r=d.resident,s=d.stats;
  const pts=[...(d.sessions||[])].reverse().filter(x=>x.status==='FINALIZADA').map((x,i)=>({x:i,y:x.volume_total_l,label:(x.started_at||'').slice(5,10)}));
  return `${pageHeader('Detalle del residente','Información individual, consumo e historial',`<a class="btn ghost" href="#/residents">← Volver</a><button class="btn primary" onclick="openEditResident(${r.id})">Editar residente</button>`)}
    <div class="grid grid-3">
      <div class="card pad"><div style="display:flex;align-items:center;gap:14px"><div class="brand-logo" style="width:50px;height:50px">${esc((r.display_name||'R').split(' ').map(x=>x[0]).slice(0,2).join(''))}</div><div><div class="card-title">${esc(r.display_name)}</div><div class="card-sub mono">${esc(r.code)} · Hab. ${esc(r.room||'—')}</div></div></div><div class="info-list"><div class="info-row"><div class="k">DNI</div><div class="v">${esc(r.dni||'—')}</div></div><div class="info-row"><div class="k">Fecha de registro</div><div class="v">${fmtDate(r.created_at)}</div></div><div class="info-row"><div class="k">Estado / consentimiento</div><div class="v">${r.enabled?statusPill('HABILITADO'):statusPill('INACTIVO')} ${r.consent_valid?statusPill('VALIDA'):statusPill('PENDIENTE')}</div></div></div></div>
      <div class="card metric"><div class="metric-label">SESIONES REGISTRADAS</div><div class="metric-value">${s.n||0}</div><div class="metric-foot muted">Muestra individual</div></div>
      <div class="card metric"><div class="metric-label">CONSUMO PROMEDIO</div><div class="metric-value">${fmtNumber(s.avg_volume_l,1)} L</div><div class="metric-foot green">Objetivo actual: ${fmtNumber(d.target?.target_l||r.default_goal_l,1)} L</div></div>
    </div>
    <div class="grid grid-2" style="margin-top:18px"><div class="card pad"><div class="card-title">Consumo de las últimas sesiones</div><div class="chart-box">${lineChart(pts,{height:230,color:'#2563eb',fill:true})}</div></div>
    <div class="card pad"><div class="card-title">Resumen del perfil</div><div class="info-list"><div class="info-row"><div class="k">Duración promedio</div><div class="v">${fmtDuration(s.avg_duration_s)}</div></div><div class="info-row"><div class="k">Temperatura promedio</div><div class="v">${fmtNumber(s.avg_temp_c,1)} °C</div></div><div class="info-row"><div class="k">Temperatura preferida</div><div class="v">${fmtNumber(r.preferred_temp,1)} °C</div></div><div class="info-row"><div class="k">Secuencia experimental</div><div class="v">${esc(r.experiment_sequence)}</div></div></div></div></div>
    <div class="card pad" style="margin-top:18px"><div class="card-title">Sesiones recientes</div><div class="table-wrap"><table class="data-table"><thead><tr><th>Fecha</th><th>Sesión</th><th>Modo</th><th>Volumen</th><th>Duración</th><th>Temp.</th><th>Calidad</th></tr></thead><tbody>${(d.sessions||[]).slice(0,10).map(x=>`<tr><td>${fmtDate(x.started_at)}</td><td class="mono">${esc(x.code)}</td><td>${titleCase(x.mode)}</td><td>${fmtNumber(x.volume_total_l,1)} L</td><td>${fmtDuration(x.total_duration_s)}</td><td>${fmtNumber(x.avg_temp_c,1)} °C</td><td>${statusPill(x.quality)}</td></tr>`).join('')}</tbody></table></div></div>`;
}

async function monitorView(){
  const active=await api('/api/v1/sesiones/activa'); state.activeSession=active;
  const [residents,devices]=await Promise.all([api('/api/v1/residentes'),api('/api/v1/dispositivos')]);
  if(!active){
    return `${pageHeader('Monitoreo en tiempo real','No existe una sesión activa',`<button class="btn primary" onclick="prepareFromMonitor()">Preparar sesión</button>`)}
      <div class="grid grid-2"><div class="card pad"><div class="card-title">Preparación autorizada</div><p class="muted">Seleccione un residente, el modo de operación y el dispositivo. El sistema valida habilitación, consentimiento y disponibilidad antes de iniciar.</p><div class="form-grid" style="margin-top:16px"><div class="field"><label>Residente</label><select id="prep-resident" class="control">${residents.filter(r=>r.enabled).map(r=>`<option value="${r.id}">${esc(r.code)} · ${esc(r.display_name)}</option>`).join('')}</select></div><div class="field"><label>Dispositivo</label><select id="prep-device" class="control">${devices.map(d=>`<option value="${d.id}">${esc(d.device_code)} · ${esc(d.status)}</option>`).join('')}</select></div><div class="field"><label>Modo de operación</label><select id="prep-mode" class="control"><option>INTELIGENTE</option><option>TRADICIONAL</option></select></div><div class="field"><label>Estado</label><div style="padding-top:8px">${devices[0]?.status?statusPill(devices[0].status):statusPill('DESCONECTADO')}</div></div></div><button class="btn primary" style="margin-top:18px" onclick="prepareFromMonitor()">Preparar sesión</button></div>
      <div class="card pad"><div class="card-title">Flujo esperado</div><div class="info-list"><div class="info-row"><div class="k">1. Preparación</div><div class="v">La aplicación valida residente, consentimiento y prototipo.</div></div><div class="info-row"><div class="k">2. Inicio físico</div><div class="v">El ESP32 detecta caudal y cambia el estado a ACTIVA.</div></div><div class="info-row"><div class="k">3. Telemetría</div><div class="v">MQTT → backend → BD → WebSocket.</div></div><div class="info-row"><div class="k">4. Seguridad</div><div class="v">La temperatura y cierre de emergencia se controlan localmente en el ESP32.</div></div></div></div></div>`;
  }
  const l=active.latest||{}; const vol=Number(l.volume_l ?? active.volume_total_l ??0), target=Number(active.target_l||0); const pct=target?Math.min(100,vol/target*100):0;
  const readings=await api(`/api/v1/sesiones/${active.id}/lecturas?limit=90`); state.livePoints=readings.map((x,i)=>({x:i,t:new Date(x.ts).getTime(),v:x.volume_l,f:x.flow_lmin,temp:x.temp_c}));
  return `${pageHeader('Monitoreo en tiempo real','Actualización continua desde el prototipo IoT',`<span class="status-pill ok" data-live-connection><span class="live-dot"></span> Canal en tiempo real</span><button class="btn danger" onclick="requestStop(${active.id})">Solicitar detención</button>`)}
    <div class="card session-id-card"><div class="card-title">Identificación de sesión</div><div class="session-state">${statusPill(active.status)}</div><div class="session-meta"><div class="meta"><div class="label">SESIÓN</div><div class="value mono">${esc(active.code)}</div></div><div class="meta"><div class="label">RESIDENTE</div><div class="value">${esc(active.resident_code)} · ${esc(active.display_name)}</div></div><div class="meta"><div class="label">HABITACIÓN</div><div class="value">${esc(active.room||'—')}</div></div><div class="meta"><div class="label">MODO</div><div class="value">${titleCase(active.mode)}</div></div><div class="meta"><div class="label">DISPOSITIVO</div><div class="value mono">${esc(active.device_code||'—')}</div></div><div class="meta"><div class="label">INICIO</div><div class="value">${fmtDate(active.started_at)}</div></div></div></div>
    <div class="live-metrics" style="margin-top:18px">
      <div class="card dial"><div class="dial-ring" style="--p:${Math.min(100,vol/Math.max(target,60)*100)}%"><div class="dial-value" id="live-volume">${fmtNumber(vol,2)} L</div></div><div class="dial-label">CONSUMO ACUMULADO</div></div>
      <div class="card dial"><div class="dial-ring" style="--p:${Math.min(100,Number(l.temp_c||active.avg_temp_c||0)/41*100)}%;background:conic-gradient(var(--orange) var(--p),#eef3f8 0)"><div class="dial-value" id="live-temp">${fmtNumber(l.temp_c||active.avg_temp_c,1)} °C</div></div><div class="dial-label">TEMPERATURA</div></div>
      <div class="card dial"><div class="dial-ring" style="--p:${Math.min(100,Number(l.flow_lmin||0)/12*100)}%;background:conic-gradient(var(--green) var(--p),#eef3f8 0)"><div class="dial-value" id="live-flow">${fmtNumber(l.flow_lmin,2)} L/min</div></div><div class="dial-label">CAUDAL</div></div>
      <div class="card dial"><div class="dial-ring" style="--p:${Math.min(100,Number(active.total_duration_s||0)/600*100)}%;background:conic-gradient(var(--purple) var(--p),#eef3f8 0)"><div class="dial-value" id="live-time">${fmtDuration(active.total_duration_s)}</div></div><div class="dial-label">TIEMPO TRANSCURRIDO</div></div>
    </div>
    <div class="grid grid-73" style="margin-top:18px"><div class="card pad"><div class="card-title">Consumo en tiempo real</div><div class="card-sub">Actualización por WebSocket a partir de telemetría MQTT</div><div class="chart-box" id="live-chart">${lineChart(state.livePoints.map((x,i)=>({x:i,y:x.v})),{height:220,color:'#2563eb',fill:true})}</div></div>
      <div class="card pad"><div class="card-title">Progreso de objetivo</div><div class="card-sub">Objetivo personalizado independiente de la predicción</div><div id="goal-text" style="font-size:22px;font-weight:800;margin:16px 0 8px">${target?`${fmtNumber(vol,1)} L / ${fmtNumber(target,1)} L`:`${fmtNumber(vol,1)} L`}</div><div class="progress"><span id="goal-progress" style="width:${pct}%"></span></div><div class="info-list" style="margin-top:18px"><div class="info-row"><div class="k">ESTADO</div><div class="v" id="live-state">${titleCase(l.state||active.status)}</div></div><div class="info-row"><div class="k">PAUSAS</div><div class="v" id="live-pauses">${active.pause_count||0}</div></div></div></div>
    </div>
    <div class="grid grid-2" style="margin-top:18px"><div class="ai-tip"><b>Recomendación IA</b><br>El objetivo personalizado se obtiene del histórico del residente. La IA apoya el análisis; no gobierna las funciones críticas.</div><div class="safety-note"><b>Seguridad determinística</b><br>La temperatura máxima, el cierre de emergencia y los fallos de sensores son gestionados directamente por el ESP32, aun sin conexión al servidor.</div></div>`;
}

window.prepareFromMonitor=async()=>{
  const resident=Number(document.getElementById('prep-resident')?.value), device=Number(document.getElementById('prep-device')?.value), mode=document.getElementById('prep-mode')?.value||'INTELIGENTE';
  if(!resident) return toast('Seleccione un residente','error');
  try{await api('/api/v1/sesiones/preparar',{method:'POST',body:JSON.stringify({resident_id:resident,device_id:device||null,mode})});toast('Sesión preparada','success');await render();}catch(e){toast(e.message,'error')}
};
window.requestStop=async(id)=>{if(!confirm('¿Solicitar detención de la sesión? El ESP32 conserva la responsabilidad del cierre físico.'))return;try{const r=await api(`/api/v1/sesiones/${id}/detener`,{method:'POST',body:JSON.stringify({motivo:'Detención solicitada desde la interfaz'})});toast(r.message,'success');setTimeout(render,700)}catch(e){toast(e.message,'error')}};

async function historyView(){
  const [rows,report]=await Promise.all([api('/api/v1/historial'),api('/api/v1/reportes/comparacion')]);
  return `${pageHeader('Historial y reportes','Trazabilidad de sesiones y datos para análisis',`<button class="btn primary" onclick="downloadExport('csv')">Exportar CSV</button><button class="btn ghost" onclick="downloadExport('xlsx')">XLSX</button>`)}
    <div class="card filter-panel"><div class="toolbar"><input class="control" type="search" placeholder="Buscar residente / sesión" oninput="filterHistoryRows(this.value)"><select class="control" onchange="filterHistoryMode(this.value)"><option value="">Todos los modos</option><option>TRADICIONAL</option><option>INTELIGENTE</option></select><span class="status-pill info">Reducción: ${fmtNumber(report.reduction_pct,1)} %</span></div></div>
    <div class="card pad"><div class="table-wrap"><table class="data-table" id="history-table"><thead><tr><th>Fecha / hora</th><th>Sesión</th><th>Residente</th><th>Hab.</th><th>Modo</th><th>Duración</th><th>Consumo</th><th>Temp. prom.</th><th>Calidad</th><th>Estado</th></tr></thead><tbody>
    ${rows.map(r=>`<tr data-search="${esc(`${r.code} ${r.resident_code} ${r.display_name}`.toLowerCase())}" data-mode="${esc(r.mode)}"><td>${fmtDate(r.started_at)}</td><td class="mono">${esc(r.code)}</td><td>${esc(r.resident_code)} · ${esc(r.display_name)}</td><td>${esc(r.room||'—')}</td><td>${titleCase(r.mode)}</td><td>${fmtDuration(r.total_duration_s)}</td><td>${fmtNumber(r.volume_total_l,1)} L</td><td>${fmtNumber(r.avg_temp_c,1)} °C</td><td>${statusPill(r.quality)}</td><td>${statusPill(r.status)}</td></tr>`).join('')}</tbody></table></div></div>`;
}
window.filterHistoryRows=q=>{q=q.toLowerCase();document.querySelectorAll('#history-table tbody tr').forEach(tr=>tr.style.display=tr.dataset.search.includes(q)?'':'none')};
window.filterHistoryMode=mode=>{document.querySelectorAll('#history-table tbody tr').forEach(tr=>tr.style.display=!mode||tr.dataset.mode===mode?'':'none')};
window.downloadExport=async(format)=>{try{const res=await fetch(`/api/v1/exportaciones?format=${format}`,{headers:{Authorization:`Bearer ${state.token}`}});if(!res.ok){const j=await res.json();throw new Error(j?.error?.message||'No se pudo exportar')}const blob=await res.blob();const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`sesiones_smcdi.${format}`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}catch(e){toast(e.message,'error')}};

async function aiView(){
  const residents=await api('/api/v1/residentes'); const residentId=Number(sessionStorage.getItem('ai_resident')||residents.find(x=>x.code==='R-003')?.id||residents[0]?.id||1); const d=await api(`/api/v1/ia?resident_id=${residentId}`); const p=d.prediction;
  return `${pageHeader('Inteligencia Artificial','Patrones, predicción y evaluación separadas en bloques claros',state.user.role==='ADMINISTRADOR'?'<button class="btn primary" onclick="trainAI()">Evaluar modelos</button>':'')}
    <div class="notice"><b>Responsabilidad del módulo.</b> La inteligencia artificial se utiliza para análisis y predicción de consumo. Las funciones críticas de seguridad son gestionadas por mecanismos determinísticos independientes.</div>
    <div class="toolbar" style="margin:18px 0"><label class="small muted">Residente</label><select class="control" onchange="sessionStorage.setItem('ai_resident',this.value);render()">${residents.map(r=>`<option value="${r.id}" ${r.id===residentId?'selected':''}>${esc(r.code)} · ${esc(r.display_name)}</option>`).join('')}</select><button class="btn ghost" onclick="predictAI(${residentId})">Generar predicción</button></div>
    <div class="ai-columns">
      <div class="card pad"><div class="card-title">A. Patrones de consumo</div><div class="info-list"><div class="info-row"><div class="k">TENDENCIA HISTÓRICA</div><div class="v">${fmtNumber(d.patterns?.trend_pct,1)} %</div></div><div class="info-row"><div class="k">VENTANA DE MAYOR USO</div><div class="v">${esc(d.patterns?.peak_window||'—')}</div></div><div class="info-row"><div class="k">DÍA DE MAYOR CONSUMO</div><div class="v">${esc(titleCase(d.patterns?.top_day||'—'))}</div></div><div class="info-row"><div class="k">PATRÓN DESTACADO</div><div class="v">${esc(d.patterns?.message||'—')}</div></div></div></div>
      <div class="card pad"><div class="card-title">B. Predicción y objetivo</div><div class="info-list"><div class="info-row"><div class="k">CÓDIGO RESIDENTE</div><div class="v mono">${esc(d.resident?.code||'—')}</div></div><div class="info-row"><div class="k">CONSUMO ESPERADO IA</div><div class="v">${p?`${fmtNumber(p.predicted_l,1)} L`:'Sin predicción congelada'}</div></div><div class="info-row"><div class="k">OBJETIVO PERSONALIZADO</div><div class="v">${p?`${fmtNumber(p.target_l,1)} L`:fmtNumber(d.resident?.default_goal_l,1)+' L'}</div></div><div class="info-row"><div class="k">REDUCCIÓN OBJETIVO</div><div class="v">${p?fmtNumber(p.reduction_pct,1)+' %':'—'}</div></div><div class="info-row"><div class="k">VERSIÓN</div><div class="v mono">${esc(p?.version||p?.model_version||'—')}</div></div></div></div>
      <div class="card pad"><div class="card-title">C. Evaluación de modelos</div><div class="table-wrap"><table class="data-table model-table"><thead><tr><th>Modelo</th><th>MAE</th><th>RMSE</th><th>R²</th><th>Estado</th></tr></thead><tbody>${(d.models||[]).map(m=>`<tr><td>${esc(m.algorithm)}</td><td>${m.mae==null?'—':fmtNumber(m.mae,2)}</td><td>${m.rmse==null?'—':fmtNumber(m.rmse,2)}</td><td>${m.r2==null?'—':fmtNumber(m.r2,2)}</td><td>${m.active?statusPill('ACTIVO'):statusPill('EVALUADO')}</td></tr>`).join('')||'<tr><td colspan="5" class="muted">Ejecute la evaluación de modelos.</td></tr>'}</tbody></table></div></div>
    </div>`;
}
window.trainAI=async()=>{try{toast('Evaluando modelos…');const r=await api('/api/v1/ia/entrenar',{method:'POST'});if(!r.ok)throw new Error(r.message||'No se pudo entrenar');toast(`Modelo seleccionado: ${r.selected.algorithm}`,'success');render()}catch(e){toast(e.message,'error')}};
window.predictAI=async(resident_id)=>{try{const r=await api('/api/v1/predicciones',{method:'POST',body:JSON.stringify({resident_id})});if(!r.ok)throw new Error(r.message||r.reason||'No se pudo predecir');toast(`Predicción ${fmtNumber(r.predicted_l,1)} L · objetivo ${fmtNumber(r.target_l,1)} L`,'success');render()}catch(e){toast(e.message,'error')}};

async function alertsView(){
  const rows=await api('/api/v1/alertas'); const counts={PENDIENTE:0,REVISADA:0,RESUELTA:0,ALTA:0}; rows.forEach(r=>{counts[r.status]=(counts[r.status]||0)+1;if(['ALTA','CRITICA'].includes(r.severity))counts.ALTA++});
  return `${pageHeader('Alertas del sistema','Listado legible con datos críticos y trazabilidad')}
    <div class="grid grid-4"><div class="card metric"><div class="metric-label">PENDIENTES</div><div class="metric-value">${counts.PENDIENTE}</div><div class="metric-foot red">Requiere atención</div></div><div class="card metric"><div class="metric-label">REVISADAS</div><div class="metric-value">${counts.REVISADA}</div><div class="metric-foot blue">Eventos trazados</div></div><div class="card metric"><div class="metric-label">RESUELTAS</div><div class="metric-value">${counts.RESUELTA}</div><div class="metric-foot green">Cerradas</div></div><div class="card metric"><div class="metric-label">ALTA SEVERIDAD</div><div class="metric-value">${counts.ALTA}</div><div class="metric-foot orange">Consumo / temperatura</div></div></div>
    <div class="card pad" style="margin-top:18px"><div class="table-wrap"><table class="data-table"><thead><tr><th>ID / fecha</th><th>Tipo / severidad</th><th>Asociado</th><th>Descripción</th><th>Estado</th><th></th></tr></thead><tbody>${rows.map(r=>`<tr><td><div class="mono">${esc(r.code)}</div><div class="tiny muted">${fmtDate(r.created_at)}</div></td><td><b>${esc(r.kind)}</b><div class="tiny ${['ALTA','CRITICA'].includes(r.severity)?'red':'muted'}">${esc(titleCase(r.severity))}</div></td><td>${esc(r.display_name||'Sistema')}<div class="tiny muted">${esc(r.resident_code||'')} ${r.room?'· Hab. '+esc(r.room):''} ${r.session_code?'· '+esc(r.session_code):''}</div></td><td class="wrap">${esc(r.description)}</td><td>${statusPill(r.status)}</td><td><button class="btn light sm" onclick="openAlert(${r.id},'${esc(r.status)}')">Atender</button></td></tr>`).join('')}</tbody></table></div><div class="small muted" style="margin-top:14px">Cada alerta conserva identificador único y referencia coherente a residente, habitación y sesión.</div></div>`;
}

async function tamView(){
  const residents=await api('/api/v1/residentes');
  const items=Array.from({length:20},(_,i)=>`Ítem ${String(i+1).padStart(2,'0')} — texto pendiente del cuestionario aprobado`);
  return `${pageHeader('Encuesta de aceptación tecnológica – TAM','Escala Likert de 1 a 5 · 20 respuestas obligatorias')}
    <form id="tam-form"><div class="tam-head"><div class="field"><label>Código del residente</label><select class="control" name="resident_id" required>${residents.map(r=>`<option value="${r.id}">${esc(r.code)} · ${esc(r.display_name)}</option>`).join('')}</select></div><div class="field"><label>Momento de aplicación</label><select class="control" name="moment"><option>POST_INTERVENCION</option><option>SEGUIMIENTO</option></select></div><div class="field"><label>Fecha</label><input class="control" type="date" value="${new Date().toISOString().slice(0,10)}" disabled></div></div>
    <div class="card pad" style="margin-top:18px"><div class="card-title">Cuestionario TAM</div><div class="card-sub">El PFC y el mockup especifican 20 respuestas Likert, pero no incluyen el texto definitivo del instrumento. Por ello, el sistema conserva los 20 campos como ítems pendientes hasta incorporar el cuestionario aprobado.</div><div class="tam-scale"><span>1 = Totalmente en desacuerdo</span><span>5 = Totalmente de acuerdo</span></div><div class="tam-grid">${items.map((q,i)=>`<div class="tam-item"><span>${esc(q)}</span><div class="likert">${[1,2,3,4,5].map(v=>`<label>${v}<input type="radio" name="q${i}" value="${v}" required></label>`).join('')}</div></div>`).join('')}</div></div>
    <div class="card pad" style="margin-top:16px;display:flex;align-items:center;justify-content:space-between;gap:12px"><span id="tam-progress" class="muted small">Validación: 20 respuestas pendientes antes de guardar.</span><button class="btn primary" type="submit">Guardar encuesta</button></div></form>`;
}

async function configView(){
  if(state.user.role!=='ADMINISTRADOR') throw new Error('Permiso insuficiente'); const rows=await api('/api/v1/configuracion'); const o=Object.fromEntries(rows.map(x=>[x.key,x]));
  const field=(key,label,unit='')=>`<div class="field"><label>${label}</label><div style="display:flex;gap:6px"><input class="control" type="number" step="0.1" name="${key}" value="${esc(o[key]?.typed_value??'')}">${unit?`<span class="status-pill">${unit}</span>`:''}</div></div>`;
  return `${pageHeader('Configuración','Parámetros operativos y de seguridad',`<button class="btn danger" onclick="resetDemo()">Restablecer demo</button>`)}
    <form id="config-form"><div class="grid grid-2"><div class="card pad"><div class="card-title">Parámetros de consumo y sesión</div><div class="form-grid" style="margin-top:14px">${field('max_volume_l','Volumen máximo','L')}${field('recommended_time_min','Duración recomendada','min')}${field('pause_threshold_s','Umbral de pausa','s')}${field('end_inactivity_s','Fin por inactividad','s')}${field('ai_reduction_pct','Reducción objetivo IA','%')}${field('telemetry_interval_ms','Intervalo de telemetría','ms')}</div></div>
      <div class="card pad"><div class="card-title">Límites de seguridad determinísticos</div><div class="form-grid" style="margin-top:14px">${field('max_temp_c','Temperatura máxima','°C')}${field('critical_temp_c','Temperatura crítica','°C')}${field('default_preferred_temp_c','Temperatura preferida por defecto','°C')}</div><div class="safety-note" style="margin-top:18px">Estos valores se sincronizan con el prototipo, pero el cierre de seguridad se ejecuta localmente en el ESP32 y no depende de la IA ni de la interfaz web.</div></div></div><div style="margin-top:16px"><button class="btn primary" type="submit">Guardar configuración</button></div></form>`;
}

async function usersView(){
  if(state.user.role!=='ADMINISTRADOR') throw new Error('Permiso insuficiente');const rows=await api('/api/v1/usuarios');
  return `${pageHeader('Gestión de Usuarios','Cuentas del personal autorizado y permisos por rol',`<button class="btn primary" onclick="openUserModal()">+ Nuevo usuario</button>`)}<div class="grid grid-3" style="margin-bottom:18px"><div class="card metric"><div class="metric-label">CUENTAS</div><div class="metric-value">${rows.length}</div><div class="metric-foot blue">Registradas</div></div><div class="card metric"><div class="metric-label">ADMINISTRADORES</div><div class="metric-value">${rows.filter(x=>x.role==='ADMINISTRADOR').length}</div><div class="metric-foot muted">Gestión completa</div></div><div class="card metric"><div class="metric-label">MODERADORES ACTIVOS</div><div class="metric-value">${rows.filter(x=>x.role==='MODERADOR'&&x.is_active).length}</div><div class="metric-foot green">Operación de sesiones</div></div></div>
    <div class="card pad"><div class="table-wrap"><table class="data-table"><thead><tr><th>Usuario</th><th>Nombre</th><th>Rol</th><th>Estado</th><th>Último acceso</th><th>Creación</th><th></th></tr></thead><tbody>${rows.map(u=>`<tr><td class="mono">${esc(u.username)}</td><td>${esc(u.full_name)}</td><td>${statusPill(u.role)}</td><td>${u.is_active?statusPill('HABILITADO'):statusPill('INACTIVO')}</td><td>${fmtDate(u.last_login)}</td><td>${fmtDate(u.created_at)}</td><td><button class="btn light sm" onclick="openEditUser(${u.id},'${esc(u.full_name)}','${esc(u.role)}',${u.is_active})">Editar</button></td></tr>`).join('')}</tbody></table></div></div>`;
}

function modal(html){const wrap=document.createElement('div');wrap.className='modal-backdrop';wrap.id='modal-root';wrap.innerHTML=`<div class="modal">${html}</div>`;wrap.addEventListener('click',e=>{if(e.target===wrap)wrap.remove()});document.body.appendChild(wrap)}
window.closeModal=()=>document.getElementById('modal-root')?.remove();
window.openResidentModal=()=>modal(`<h3>Nuevo residente</h3><div class="modal-sub">Registro del perfil participante.</div><form id="resident-modal-form"><div class="form-grid"><div class="field"><label>Nombre</label><input class="control" name="display_name" required></div><div class="field"><label>DNI</label><input class="control" name="dni"></div><div class="field"><label>Habitación</label><input class="control" name="room"></div><div class="field"><label>Temperatura preferida</label><input class="control" name="preferred_temp" type="number" step="0.1" value="24"></div><div class="field"><label>Secuencia experimental</label><select class="control" name="experiment_sequence"><option>T-I</option><option>I-T</option></select></div><div class="field"><label>Consentimiento</label><select class="control" name="consent_valid"><option value="true">Vigente</option><option value="false">No vigente</option></select></div></div><div class="modal-actions"><button type="button" class="btn ghost" onclick="closeModal()">Cancelar</button><button class="btn primary">Guardar</button></div></form>`);
window.openEditResident=async id=>{const d=await api(`/api/v1/residentes/${id}`),r=d.resident;modal(`<h3>Editar residente</h3><div class="modal-sub mono">${esc(r.code)}</div><form id="resident-edit-form" data-id="${id}"><div class="form-grid"><div class="field"><label>Nombre</label><input class="control" name="display_name" value="${esc(r.display_name)}"></div><div class="field"><label>DNI</label><input class="control" name="dni" value="${esc(r.dni||'')}"></div><div class="field"><label>Habitación</label><input class="control" name="room" value="${esc(r.room||'')}"></div><div class="field"><label>Temperatura preferida</label><input class="control" name="preferred_temp" type="number" step="0.1" value="${r.preferred_temp}"></div><div class="field"><label>Consentimiento</label><select class="control" name="consent_valid"><option value="true" ${r.consent_valid?'selected':''}>Vigente</option><option value="false" ${!r.consent_valid?'selected':''}>No vigente</option></select></div><div class="field"><label>Estado</label><select class="control" name="enabled"><option value="true" ${r.enabled?'selected':''}>Habilitado</option><option value="false" ${!r.enabled?'selected':''}>Inactivo</option></select></div></div><div class="modal-actions"><button type="button" class="btn ghost" onclick="closeModal()">Cancelar</button><button class="btn primary">Guardar</button></div></form>`)};
window.openAlert=(id,status)=>modal(`<h3>Atender alerta</h3><div class="modal-sub">Cambie el estado y registre una observación de atención.</div><form id="alert-modal-form" data-id="${id}"><div class="field"><label>Estado</label><select class="control" name="status"><option ${status==='PENDIENTE'?'selected':''}>PENDIENTE</option><option ${status==='REVISADA'?'selected':''}>REVISADA</option><option ${status==='RESUELTA'?'selected':''}>RESUELTA</option></select></div><div class="field" style="margin-top:12px"><label>Observación</label><textarea class="control" name="note"></textarea></div><div class="modal-actions"><button type="button" class="btn ghost" onclick="closeModal()">Cancelar</button><button class="btn primary">Guardar</button></div></form>`);
window.openUserModal=()=>modal(`<h3>Nuevo usuario</h3><div class="modal-sub">Cuenta para personal autorizado.</div><form id="user-modal-form"><div class="form-grid"><div class="field"><label>Usuario</label><input class="control" name="username" required></div><div class="field"><label>Nombre completo</label><input class="control" name="full_name" required></div><div class="field"><label>Rol</label><select class="control" name="role"><option>MODERADOR</option><option>ADMINISTRADOR</option></select></div><div class="field"><label>Contraseña</label><input class="control" name="password" type="password" minlength="8" required></div></div><div class="modal-actions"><button type="button" class="btn ghost" onclick="closeModal()">Cancelar</button><button class="btn primary">Crear cuenta</button></div></form>`);
window.openEditUser=(id,name,role,active)=>modal(`<h3>Editar usuario</h3><form id="user-edit-form" data-id="${id}"><div class="form-grid"><div class="field"><label>Nombre</label><input class="control" name="full_name" value="${esc(name)}"></div><div class="field"><label>Rol</label><select class="control" name="role"><option ${role==='MODERADOR'?'selected':''}>MODERADOR</option><option ${role==='ADMINISTRADOR'?'selected':''}>ADMINISTRADOR</option></select></div><div class="field"><label>Estado</label><select class="control" name="is_active"><option value="true" ${active?'selected':''}>Activo</option><option value="false" ${!active?'selected':''}>Inactivo</option></select></div><div class="field"><label>Nueva contraseña (opcional)</label><input class="control" name="password" type="password" minlength="8"></div></div><div class="modal-actions"><button type="button" class="btn ghost" onclick="closeModal()">Cancelar</button><button class="btn primary">Guardar</button></div></form>`);
window.resetDemo=async()=>{if(!confirm('¿Regenerar la base de demostración? Se perderán los cambios locales actuales.'))return;try{await api('/api/v1/demo/reset',{method:'POST'});toast('Demo restablecida','success');location.hash='#/dashboard';render()}catch(e){toast(e.message,'error')}};

// Delegación de formularios dinámicos.
document.addEventListener('submit',async e=>{
  const f=e.target;
  if(f.id==='tam-form'){e.preventDefault();const fd=new FormData(f),answers=[];for(let i=0;i<20;i++)answers.push(Number(fd.get(`q${i}`)||0));if(answers.some(v=>!v)){return toast('Complete las 20 respuestas','error')}try{const r=await api('/api/v1/encuestas',{method:'POST',body:JSON.stringify({resident_id:Number(fd.get('resident_id')),moment:fd.get('moment'),answers})});toast(`Encuesta guardada · promedio ${fmtNumber(r.score_avg,2)}`,'success');render()}catch(err){toast(err.message,'error')}return;}
  if(f.id==='config-form'){e.preventDefault();const fd=new FormData(f),values={};for(const [k,v] of fd)values[k]=Number(v);try{await api('/api/v1/configuracion',{method:'PATCH',body:JSON.stringify({values})});toast('Configuración guardada','success')}catch(err){toast(err.message,'error')}return;}
  if(f.id==='resident-modal-form'){e.preventDefault();const fd=Object.fromEntries(new FormData(f));fd.preferred_temp=Number(fd.preferred_temp);fd.consent_valid=fd.consent_valid==='true';try{await api('/api/v1/residentes',{method:'POST',body:JSON.stringify(fd)});closeModal();toast('Residente registrado','success');render()}catch(err){toast(err.message,'error')}return;}
  if(f.id==='resident-edit-form'){e.preventDefault();const fd=Object.fromEntries(new FormData(f));fd.preferred_temp=Number(fd.preferred_temp);fd.consent_valid=fd.consent_valid==='true';fd.enabled=fd.enabled==='true';try{await api(`/api/v1/residentes/${f.dataset.id}`,{method:'PATCH',body:JSON.stringify(fd)});closeModal();toast('Residente actualizado','success');render()}catch(err){toast(err.message,'error')}return;}
  if(f.id==='alert-modal-form'){e.preventDefault();const fd=Object.fromEntries(new FormData(f));try{await api(`/api/v1/alertas/${f.dataset.id}`,{method:'PATCH',body:JSON.stringify(fd)});closeModal();toast('Alerta actualizada','success');render()}catch(err){toast(err.message,'error')}return;}
  if(f.id==='user-modal-form'){e.preventDefault();const fd=Object.fromEntries(new FormData(f));try{await api('/api/v1/usuarios',{method:'POST',body:JSON.stringify(fd)});closeModal();toast('Usuario creado','success');render()}catch(err){toast(err.message,'error')}return;}
  if(f.id==='user-edit-form'){e.preventDefault();const fd=Object.fromEntries(new FormData(f));fd.is_active=fd.is_active==='true';if(!fd.password)delete fd.password;try{await api(`/api/v1/usuarios/${f.dataset.id}`,{method:'PATCH',body:JSON.stringify(fd)});closeModal();toast('Usuario actualizado','success');render()}catch(err){toast(err.message,'error')}return;}
});

document.addEventListener('change',()=>{
  const f=document.getElementById('tam-form'),p=document.getElementById('tam-progress'); if(f&&p){let n=0;for(let i=0;i<20;i++)if(new FormData(f).get(`q${i}`))n++;p.textContent=n===20?'Validación completa. La encuesta puede guardarse.':`Validación: ${20-n} respuestas pendientes antes de guardar.`}
});

async function render(){
  if(!state.token){loginView();return}
  if(!state.user){try{state.user=await api('/api/v1/auth/me');localStorage.setItem('smcdi_user',JSON.stringify(state.user))}catch{return}}
  let route=(location.hash||'#/dashboard').replace(/^#\/?/,''); if(!route)route='dashboard'; state.route=route;
  const base=route.split('/')[0];
  if(['config','users'].includes(base)&&state.user.role!=='ADMINISTRADOR'){location.hash='#/dashboard';return}
  try{
    let content;
    if(base==='dashboard')content=await dashboardView();
    else if(base==='residents')content=await residentsView();
    else if(base==='resident')content=await residentDetailView(Number(route.split('/')[1]));
    else if(base==='monitor')content=await monitorView();
    else if(base==='history')content=await historyView();
    else if(base==='ai')content=await aiView();
    else if(base==='alerts')content=await alertsView();
    else if(base==='tam')content=await tamView();
    else if(base==='config')content=await configView();
    else if(base==='users')content=await usersView();
    else {location.hash='#/dashboard';return}
    app.innerHTML=shell(content);
  }catch(e){app.innerHTML=shell(`${pageHeader('No se pudo cargar la vista','Se produjo un error al consultar el sistema')}<div class="card pad"><b>${esc(e.message)}</b><p class="muted">Compruebe el backend y vuelva a intentarlo.</p><button class="btn primary" onclick="render()">Reintentar</button></div>`)}
}

window.addEventListener('hashchange',()=>{document.getElementById('shell')?.classList.remove('menu-open');render()});
window.render=render;

(async function boot(){
  if(state.token){
    try{state.user=await api('/api/v1/auth/me');localStorage.setItem('smcdi_user',JSON.stringify(state.user));connectWS();render();}
    catch{logout(false)}
  }else loginView();
})();
