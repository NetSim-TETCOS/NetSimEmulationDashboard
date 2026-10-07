import { drawLineChart } from './chart.js?v=20260930-11';
const $ = id => document.getElementById(id);
const state = { token:'', session:null, participants:[], summaryHistory:[], series:{}, markers:[], sort:'id', asc:true, selected:null, timer:null, activeOnly:true };
const fmt = value => value == null ? '—' : `${Number(value).toFixed(value < 100 ? 1 : 0)} ms`;
async function api(path, options={}) {
  const headers = { ...(options.headers || {}), 'X-Admin-Token':state.token };
  if (options.body) headers['Content-Type']='application/json';
  const response = await fetch(path,{...options,headers,cache:'no-store'}); if (!response.ok) throw new Error((await response.json().catch(()=>({}))).detail || `HTTP ${response.status}`); return response;
}
function renderPreflight(data) {
  const checks = [
    ['FFmpeg', data.ffmpeg, 'Required for TCP / HLS video'],
    ['MediaMTX', data.mediamtx, 'Required for UDP / WebRTC video'],
    ['Video folder', {...data.video_directory, available:data.video_directory.available && data.video_directory.video_count > 0}, `${data.video_directory.video_count} supported video file(s) found`],
  ];
  const container = $('preflightChecks'); container.replaceChildren();
  checks.forEach(([label, check, note]) => { const item=document.createElement('div'); item.className=`preflight-check ${check.available?'ready':'missing'}`; const title=document.createElement('strong'); title.textContent=`${check.available?'✓':'✕'} ${label}: ${check.available?'Ready':'Missing'}`; const detail=document.createElement('span'); detail.textContent=`${note}${check.configured ? ` · ${check.configured}` : ''}`; item.append(title, detail); container.append(item); });
  const ready = data.tcp_video_ready && data.udp_video_ready && data.video_directory.video_count > 0;
  $('preflightStatus').textContent = ready ? 'TCP and UDP video streaming are ready.' : 'Video streaming needs setup. Latency and participant dashboards remain available.';
  $('preflightStatus').className = `subtle ${ready ? 'preflight-ok' : 'preflight-warning'}`;
}
async function loadPreflight() { try { renderPreflight(await fetch('/api/preflight',{cache:'no-store'}).then(r=>r.json())); } catch(error) { $('preflightStatus').textContent=`Startup check failed: ${error.message}`; } }
function cell(row, text) { const td=document.createElement('td'); td.textContent=text; row.append(td); }
function visibleParticipants() {
  const query=$('search').value.toLowerCase();
  return state.participants.filter(p => (!state.activeOnly || p.status === 'online') && `${p.id} ${p.display_name} ${p.institution}`.toLowerCase().includes(query));
}
function renderTable() {
  let list=visibleParticipants();
  list.sort((a,b) => { if (a.status !== b.status) return a.status === 'online' ? -1 : 1; const x=a[state.sort]??'', y=b[state.sort]??''; return (typeof x==='number' ? x-y : String(x).localeCompare(String(y))) * (state.asc?1:-1); });
  const tbody=$('participantRows'); tbody.replaceChildren();
  list.forEach(p => { const tr=document.createElement('tr'); tr.onclick=()=>showDetail(p.id); cell(tr,p.id); cell(tr,p.display_name||'—'); cell(tr,p.institution||'—'); cell(tr,p.ip_address||'—');
    const td=document.createElement('td'), badge=document.createElement('span'); badge.className=`pill ${p.status==='online'?'':'offline'}`; badge.textContent=p.status; td.append(badge); tr.append(td);
    [fmt(p.current_rtt),fmt(p.baseline_rtt),fmt(p.rtt_delta),fmt(p.jitter),`${Number(p.timeout_percentage||0).toFixed(1)}%`,p.message_count,new Date(p.last_seen).toLocaleTimeString()].forEach(v=>cell(tr,v)); tbody.append(tr); });
}
function renderParticipantChart() {
  drawLineChart($('aggregateChart'), visibleParticipants().map(p => state.series[p.id]).filter(series => series?.points.length), state.markers, {since:Date.now()-60000});
}
function renderSummary(s) { $('connected').textContent=s.connected_clients; $('activeProbes').textContent=s.active_probes; $('medianRtt').textContent=fmt(s.median_client_rtt); $('p95Rtt').textContent=fmt(s.p95_client_rtt); $('jitter').textContent=fmt(s.average_jitter); $('timeouts').textContent=`${Number(s.timeout_percentage).toFixed(1)}%`;
  const timestamp = Date.now();
  state.participants.forEach((participant, index) => {
    const label = [participant.display_name, participant.institution].filter(Boolean).join(' · ') || participant.id;
    const series = state.series[participant.id] ||= { label, points:[], color:`hsl(${(index * 67) % 360} 75% 62%)` };
    series.label = label;
    const known = new Set(series.points.map(point => point.x));
    (participant.rtt_history || []).forEach(sample => {
      if (sample.rtt_ms != null && sample.status !== 'timeout' && !known.has(sample.timestamp)) series.points.push({x:sample.timestamp, y:sample.rtt_ms});
    });
    series.points.sort((a,b) => a.x - b.x);
    if (series.points.length > 600) series.points.shift();
  });
  renderParticipantChart(); }
async function refresh() { try { const [session,participants,summary]=await Promise.all([api('/api/session/current').then(r=>r.json()),api('/api/participants?active_only=false').then(r=>r.json()),api('/api/metrics/summary').then(r=>r.json())]); state.session=session; state.participants=participants; $('sessionId').textContent=session.id; $('mode').value=session.experiment_mode; $('experimentLabel').value=session.experiment_label; renderTable(); renderSummary(summary); } catch(error) { if(error.message.includes('token')||error.message.includes('401')) logout(error.message); } }
async function login() { state.token=$('adminToken').value; try { await api('/api/participants?active_only=false'); try { sessionStorage.setItem('admin_token',state.token); } catch (_) {} $('authPanel').classList.add('hidden'); $('dashboard').classList.remove('hidden'); await refresh(); await loadVideos(); clearInterval(state.timer); state.timer=setInterval(refresh,1000); } catch(error) { $('authError').textContent=error.message; } }
function logout(message) { clearInterval(state.timer); $('dashboard').classList.add('hidden'); $('authPanel').classList.remove('hidden'); $('authError').textContent=message; }
function addEvent(marker) { state.markers.push(marker); const li=document.createElement('li'), time=document.createElement('time'); time.textContent=new Date(marker.timestamp).toLocaleTimeString(); li.append(time,document.createTextNode(marker.label)); $('eventList').prepend(li); }
async function showDetail(id) { const p=await api(`/api/participants/${encodeURIComponent(id)}`).then(r=>r.json()); state.selected=p; $('detailTitle').textContent=`${p.id} · ${p.display_name||'Unnamed participant'}`; const body=$('detailBody'); body.replaceChildren();
  const grid=document.createElement('div'); grid.className='stats-grid'; const entries=[['Institution',p.institution||'—'],['IP',p.ip_address],['Browser',`${p.browser} / ${p.os}`],['Connected',new Date(p.connected_at).toLocaleString()],['Current',fmt(p.current_rtt)],['Baseline',fmt(p.baseline_rtt)],['Median',fmt(p.median_rtt)],['P95',fmt(p.p95_rtt)],['Jitter',fmt(p.jitter)],['Probes',p.probe_count],['Timeouts',p.timeout_count],['Messages',p.message_count]];
  entries.forEach(([label,value])=>{const d=document.createElement('div');d.className='stat';const s=document.createElement('span');s.className='subtle';s.textContent=label;const strong=document.createElement('strong');strong.textContent=value;d.append(s,strong);grid.append(d);}); body.append(grid); $('detailModal').classList.remove('hidden');
  requestAnimationFrame(()=>drawLineChart($('detailChart'),[{points:p.rtt_history.filter(x=>x.rtt_ms!=null).map(x=>({x:x.timestamp,y:x.rtt_ms}))}],state.markers,{since:Date.now()-600000,baseline:p.baseline_rtt})); }
$('loginForm').onsubmit=e=>{e.preventDefault();login();}; $('search').oninput=()=>{renderTable();renderParticipantChart();}; $('closeDetail').onclick=()=> $('detailModal').classList.add('hidden');
document.querySelectorAll('th[data-sort]').forEach(th=>th.onclick=()=>{ if(state.sort===th.dataset.sort)state.asc=!state.asc;else{state.sort=th.dataset.sort;state.asc=true;}renderTable(); });
$('applyExperiment').onclick=async()=>{ await api('/api/experiment',{method:'POST',body:JSON.stringify({mode:$('mode').value,label:$('experimentLabel').value})}); addEvent({timestamp:new Date().toISOString(),label:$('experimentLabel').value||$('mode').value}); await refresh(); };
$('markerForm').onsubmit=async e=>{e.preventDefault();const marker=await api('/api/experiment/marker',{method:'POST',body:JSON.stringify({label:$('markerLabel').value,event_type:'MARKER',notes:''})}).then(r=>r.json());addEvent(marker);$('markerLabel').value='';};
$('disconnect').onclick=async()=>{if(!state.selected)return;await api(`/api/participants/${encodeURIComponent(state.selected.id)}`,{method:'DELETE'});$('detailModal').classList.add('hidden');await refresh();};
$('refreshVideos').onclick=loadVideos;
$('refreshPreflight').onclick=loadPreflight;
$('refreshParticipants').onclick=refresh;
$('activeOnly').onchange=()=>{state.activeOnly=$('activeOnly').checked;renderTable();renderParticipantChart();};
let instructorVideoSyncTimer=null;
let suppressVideoControls=false;
function videoPosition(video) {
  const position = Number(video.position || 0);
  if (!video.playing) return Math.max(0, position);
  const updated = Number(video.position_updated_at || video.started_at || Date.now());
  return Math.max(0, position + (Date.now() - updated) / 1000);
}
function showInstructorVideo(video, onReady) {
  const player=$('instructorVideo'); clearInterval(instructorVideoSyncTimer);
  if(!video){player.pause();player.removeAttribute('src');player.classList.add('hidden');return;}
  player.classList.remove('hidden'); const source=new URL(video.url,location.href).href;
  player.onloadedmetadata=()=>{
    if (Number.isFinite(player.duration) && player.duration > 0) player.currentTime=Math.min(videoPosition(video), Math.max(0, player.duration - 0.05));
    if (video.playing) player.play().catch(()=>{}); else player.pause();
    if(onReady) Promise.resolve(onReady()).finally(()=>{setTimeout(()=>{suppressVideoControls=false;},250);});
    else setTimeout(()=>{suppressVideoControls=false;},250);
  };
  suppressVideoControls=true;
  player.src=source; player.load();
}
let videoControlDebounce = null;
async function sendVideoControl(action) { if (!state.session || suppressVideoControls) return; clearTimeout(videoControlDebounce); const player=$('instructorVideo'); videoControlDebounce=setTimeout(async()=>{ try { await api('/api/video/control',{method:'POST',body:JSON.stringify({action,position:player.currentTime||0,playing:!player.paused})}); } catch (_) {} }, action === 'seek' ? 150 : 0); }
$('videoForm').onsubmit=async e=>{e.preventDefault(); const filename=$('videoSelect').value; if(!filename) return; const transport=$('videoTransport').value; try { const video=await api('/api/video/start',{method:'POST',body:JSON.stringify({filename,transport})}).then(r=>r.json()); $('videoStatus').textContent=`Preparing ${video.name} over ${transport.toUpperCase()}…`; showInstructorVideo(video,async()=>{await api('/api/video/ready',{method:'POST'});$('videoStatus').textContent=`Streaming ${video.name} over ${transport.toUpperCase()} to participants.`;}); } catch(error) { $('videoStatus').textContent=error.message; } };
$('instructorVideo').onplay=()=>sendVideoControl('play'); $('instructorVideo').onpause=()=>sendVideoControl('pause'); $('instructorVideo').onseeked=()=>sendVideoControl('seek');
$('stopVideo').onclick=async()=>{await api('/api/video/stop',{method:'POST'});$('videoStatus').textContent='Video stream stopped.';showInstructorVideo(null);};
$('export').onclick=async()=>{const response=await api(`/api/export/session/${encodeURIComponent(state.session.id)}.json`);const blob=await response.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`${state.session.id}.json`;a.click();URL.revokeObjectURL(url);};
async function loadVideos() { try { const response=await api('/api/videos').then(r=>r.json()); const select=$('videoSelect'); select.replaceChildren(); response.videos.forEach(video=>{const option=document.createElement('option');option.value=video.name;option.textContent=video.name;select.append(option);}); if(response.active) { $('videoTransport').value=response.active.transport || 'tcp'; $('videoStatus').textContent=`Streaming ${response.active.name} over ${(response.active.transport || 'tcp').toUpperCase()} to participants.`; showInstructorVideo(response.active); } } catch(error) { $('videoStatus').textContent=error.message; } }
window.addEventListener('resize',renderParticipantChart);
let saved=''; try { saved=sessionStorage.getItem('admin_token') || ''; } catch (_) {} if(saved){$('adminToken').value=saved;login();}
loadPreflight();
window.instructorReady = true;
