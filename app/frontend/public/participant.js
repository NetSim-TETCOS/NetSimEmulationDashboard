import { drawLineChart } from './chart.js?v=20261001-14';

const $ = id => document.getElementById(id);
const state = { socket: null, attempts: 0, probeTimer: null, heartbeatTimer: null, videoSyncTimer: null, hls: null, webrtc: null, sequence: 0, pending: new Map(), points: [], markers: [], metrics: {}, messages: 0, probeTimeoutMs: 5000, probeRun: null };
let bandwidthAbort = null;
const bandwidthState = { points: [], current: 0, average: 0, peak: 0 };
const fmt = value => value == null ? '—' : `${Number(value).toFixed(value < 100 ? 1 : 0)} ms`;

function drawBandwidthChart() {
  const canvas = $('bandwidthChart'); if (!canvas) return;
  const dpr = window.devicePixelRatio || 1, width = canvas.clientWidth, height = canvas.clientHeight;
  if (!width || !height) return;
  canvas.width = width * dpr; canvas.height = height * dpr;
  const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr);
  const pad = {left: 46, right: 14, top: 14, bottom: 26};
  const plotW = width - pad.left - pad.right, plotH = height - pad.top - pad.bottom;
  const points = bandwidthState.points, max = Math.max(1, ...points.map(point => point.y)) * 1.2;
  ctx.clearRect(0, 0, width, height); ctx.font = '11px system-ui'; ctx.strokeStyle = '#243b55'; ctx.fillStyle = '#91a7bd'; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) { const y = pad.top + plotH * i / 4; ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke(); ctx.fillText(`${(max * (1 - i / 4)).toFixed(1)}`, 2, y + 4); }
  if (points.length) { ctx.strokeStyle = '#37d6c0'; ctx.lineWidth = 2; ctx.beginPath(); points.forEach((point, index) => { const x = pad.left + (point.x - points[0].x) / Math.max(1, points.at(-1).x - points[0].x) * plotW; const y = pad.top + plotH * (1 - point.y / max); if (index) ctx.lineTo(x, y); else ctx.moveTo(x, y); }); ctx.stroke(); }
  ctx.fillStyle = '#91a7bd'; ctx.fillText('Mbps', 2, 11); ctx.fillText('0 s', pad.left, height - 7); const end = points.length ? `${((points.at(-1).x - points[0].x) / 1000).toFixed(1)} s` : '0 s'; ctx.fillText(end, width - pad.right - ctx.measureText(end).width, height - 7);
}

function updateBandwidthView(received, elapsed, speed, duration) {
  bandwidthState.current = speed; bandwidthState.peak = Math.max(bandwidthState.peak, speed);
  const total = bandwidthState.points.reduce((sum, point) => sum + point.y, 0) + speed; bandwidthState.average = total / (bandwidthState.points.length + 1);
  bandwidthState.points.push({x: performance.now(), y: speed}); if (bandwidthState.points.length > 120) bandwidthState.points.shift();
  $('bandwidthCurrent').textContent = speed.toFixed(2); $('bandwidthAverage').textContent = `${bandwidthState.average.toFixed(2)} Mbps`; $('bandwidthPeak').textContent = `${bandwidthState.peak.toFixed(2)} Mbps`; $('bandwidthReceived').textContent = `${(received / 1048576).toFixed(2)} MB`; $('bandwidthElapsed').textContent = `${elapsed.toFixed(1)} s`; $('bandwidthProgress').value = Math.min(100, elapsed / duration * 100); $('bandwidthGauge').style.setProperty('--speed-angle', `${Math.min(360, speed / Math.max(1, bandwidthState.peak) * 360)}deg`); drawBandwidthChart();
}

function appendProbeLine(line = '') {
  const consoleArea = $('probeConsole');
  const lines = consoleArea.textContent.split('\n');
  lines.push(line);
  consoleArea.textContent = lines.slice(-250).join('\n');
  consoleArea.scrollTop = consoleArea.scrollHeight;
}
function startProbeConsole() {
  state.probeRun = { sent:0, received:0, timeouts:0, rtts:[] };
  $('probeConsole').textContent = `Application-probing ${location.hostname} over WebSocket/TCP:\n` +
    `RTT is measured in the browser. TTL is not exposed by browser networking APIs.\n`;
}
function printProbeSummary() {
  const run = state.probeRun;
  if (!run || !run.sent) return;
  const lost = Math.max(0, run.sent - run.received);
  const loss = run.sent ? lost / run.sent * 100 : 0;
  appendProbeLine(`\nApplication probe statistics for ${location.hostname}:`);
  appendProbeLine(`    Probes: Sent = ${run.sent}, Received = ${run.received}, Timed out = ${run.timeouts}, Lost = ${lost} (${loss.toFixed(0)}% loss)`);
  if (run.rtts.length) {
    const minimum = Math.min(...run.rtts), maximum = Math.max(...run.rtts);
    const average = run.rtts.reduce((sum, value) => sum + value, 0) / run.rtts.length;
    appendProbeLine('Approximate application round trip times:');
    appendProbeLine(`    Minimum = ${minimum.toFixed(1)} ms, Maximum = ${maximum.toFixed(1)} ms, Average = ${average.toFixed(1)} ms`);
  }
}

function logEvent(label, timestamp = Date.now()) {
  const li = document.createElement('li');
  const time = document.createElement('time'); time.textContent = new Date(timestamp).toLocaleTimeString();
  li.append(time, document.createTextNode(label)); $('eventList').prepend(li);
}
function setConnected(connected) {
  $('connection').className = `status ${connected ? 'connected' : 'disconnected'}`;
  $('connection').lastElementChild.textContent = connected ? 'Connected' : 'Disconnected';
}
function send(payload) { if (state.socket?.readyState === WebSocket.OPEN) state.socket.send(JSON.stringify(payload)); }
function draw() { drawLineChart($('rttChart'), [{ points: state.points }], state.markers, { since: Date.now() - Number($('window').value), baseline: state.metrics.baseline_rtt }); }
function updateMetrics(metrics) {
  state.metrics = metrics || {}; const map = { currentRtt:'current_rtt', baselineRtt:'baseline_rtt', rttDelta:'rtt_delta', jitter:'jitter', minRtt:'min_rtt', avgRtt:'mean_rtt', medianRtt:'median_rtt', maxRtt:'max_rtt', p95Rtt:'p95_rtt' };
  Object.entries(map).forEach(([id,key]) => $(id).textContent = fmt(metrics[key]));
  $('timeoutRate').textContent = `${Number(metrics.timeout_percentage || 0).toFixed(1)}%`;
  $('successCount').textContent = metrics.success_count || 0; $('timeoutCount').textContent = metrics.timeout_count || 0;
  $('baselineProgress').textContent = metrics.baseline_complete ? 'Baseline complete' : `${metrics.baseline_sample_count || 0}/10 samples`;
  draw();
}
function addLocalRttPoint(rtt) {
  state.points.push({ x: Date.now(), y: rtt });
  if (state.points.length > 600) state.points.shift();
  draw();
}
function identify() { send({ type:'client_hello', name:$('name').value, institution:$('institution').value }); }
function setIdentityApplied(applied) {
  $('name').disabled = applied;
  $('institution').disabled = applied;
  $('saveIdentity').textContent = applied ? 'Edit details' : 'Apply details';
  $('saveIdentity').classList.toggle('secondary', applied);
}
async function attachWebRTC(player, url, shouldPlay) {
  const pc = new RTCPeerConnection(); state.webrtc = pc;
  pc.addTransceiver('video', {direction:'recvonly'});
  pc.addTransceiver('audio', {direction:'recvonly'});
  pc.ontrack = event => { if (event.streams[0]) player.srcObject = event.streams[0]; };
  const offer = await pc.createOffer(); await pc.setLocalDescription(offer);
  if (pc.iceGatheringState !== 'complete') await new Promise(resolve => {
    const done = () => { if (pc.iceGatheringState === 'complete') { pc.removeEventListener('icegatheringstatechange', done); resolve(); } };
    pc.addEventListener('icegatheringstatechange', done);
  });
  const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/sdp'}, body:pc.localDescription.sdp});
  if (!response.ok) throw new Error(`WebRTC gateway returned HTTP ${response.status}`);
  await pc.setRemoteDescription({type:'answer', sdp:await response.text()});
  if (shouldPlay) await player.play().catch(() => {});
}
function showVideo(video, joinExistingStream = false) {
  const panel = $('videoPanel');
  if (!video) { clearInterval(state.videoSyncTimer); state.hls?.destroy(); state.hls=null; state.webrtc?.close(); state.webrtc=null; $('liveVideo').pause(); $('liveVideo').removeAttribute('src'); $('liveVideo').srcObject=null; panel.classList.add('hidden'); return; }
  panel.classList.remove('hidden'); $('videoStatus').textContent = `Receiving ${video.name} as a live FFmpeg stream.`;
  const player = $('liveVideo');
  player.controls = false;
  player.muted = true;
  player.autoplay = true;
  player.setAttribute('playsinline', '');
  const source = new URL(video.stream_url || video.url, location.href).href;
  state.hls?.destroy(); state.hls=null; state.webrtc?.close(); state.webrtc=null; player.srcObject=null;
  const playLive = () => { player.controls = false; player.play().catch(() => {}); };
  const streamPosition = () => {
    const position = Number(video.position || 0);
    if (video.playing === false) return Math.max(0, position);
    const updated = Number(video.position_updated_at || video.started_at || Date.now());
    return Math.max(0, position + (Date.now() - updated) / 1000);
  };
  const seekToStreamPosition = () => {
    if (Number.isFinite(player.duration) && player.duration > 0) player.currentTime = Math.min(streamPosition(), Math.max(0, player.duration - 0.15));
    if (video.playing !== false) playLive(); else player.pause();
  };
  player.onloadedmetadata = seekToStreamPosition;
  player.onloadeddata = () => { if (video.playing !== false) playLive(); };
  player.oncanplay = () => { if (video.playing !== false) playLive(); };
  if (video.transport === 'udp') {
    player.removeAttribute('src'); player.load();
    attachWebRTC(player, source, video.playing !== false).catch(error => { $('videoStatus').textContent=error.message; });
  } else if (video.stream_url && window.Hls?.isSupported()) {
    state.hls = new window.Hls({ lowLatencyMode: true, liveSyncDurationCount: 2 });
    state.hls.loadSource(source); state.hls.attachMedia(player);
    state.hls.on(window.Hls.Events.MANIFEST_PARSED, () => { if (video.playing !== false) playLive(); });
  } else if (player.canPlayType('application/vnd.apple.mpegurl') || !video.stream_url) {
    player.src = source; player.load();
  } else {
    $('videoStatus').textContent = 'This browser needs hls.js to play the FFmpeg stream.';
  }
  clearInterval(state.videoSyncTimer);
}
function connect() {
  const id = localStorage.getItem('participant_id') || '';
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${location.host}/ws?participant_id=${encodeURIComponent(id)}`); state.socket = ws;
  ws.onopen = () => { state.attempts = 0; setConnected(true); logEvent('Connected'); identify(); clearInterval(state.heartbeatTimer); state.heartbeatTimer = setInterval(() => send({type:'heartbeat'}), 15000); };
  ws.onmessage = event => {
    const data = JSON.parse(event.data);
    if (data.type === 'welcome') {
      localStorage.setItem('participant_id', data.client_id); localStorage.setItem('last_session_id', data.session_id);
      $('participantId').textContent = data.client_id; $('sessionId').textContent = data.session_id;
      state.probeTimeoutMs = data.probe_timeout_ms || 5000;
      if ([...$('probeInterval').options].some(option => Number(option.value) === data.probe_interval_ms)) $('probeInterval').value = String(data.probe_interval_ms);
      $('experiment').textContent = `${data.experiment.mode}${data.experiment.label ? ` · ${data.experiment.label}` : ''}`;
      state.markers = data.markers || []; draw();
      showVideo(data.video, true);
      startProbes();
    } else if (data.type === 'pong') {
      const pending = state.pending.get(data.sequence); if (!pending) return;
      clearTimeout(pending.timeout); clearTimeout(pending.expiry); const rtt = performance.now() - pending.started; const late = pending.timedOut;
      state.pending.delete(data.sequence); $('lastResponse').textContent = `Last response ${rtt.toFixed(1)} ms RTT`;
      if (state.probeRun) { state.probeRun.received += 1; state.probeRun.rtts.push(rtt); }
      appendProbeLine(`Reply from ${location.hostname}: bytes=${pending.bytes} time=${rtt < 1 ? '<1' : rtt.toFixed(1)}ms TTL=N/A seq=${data.sequence}${late ? ' (late)' : ''}`);
      addLocalRttPoint(rtt);
      send({type:'probe_result', sequence:data.sequence, sent_at:pending.wall, rtt_ms:rtt, late});
    } else if (data.type === 'metrics') updateMetrics(data.metrics);
    else if (data.type === 'message_echo') {
      const sent = Number(data.message_id.split('-').pop()); const rtt = performance.now() - sent; state.messages += 1; $('messageCount').textContent = state.messages;
      const li = document.createElement('li'); li.textContent = `“${data.text}” — ${rtt.toFixed(1)} ms`; $('messageList').prepend(li);
    } else if (data.type === 'experiment_state') { $('experiment').textContent = `${data.mode}${data.label ? ` · ${data.label}` : ''}`; logEvent(`Network condition changed: ${data.label || data.mode}`, data.timestamp); }
    else if (data.type === 'event_marker') { state.markers.push(data); logEvent(data.label, data.timestamp); draw(); }
    else if (data.type === 'video_stream') { showVideo(data.status === 'started' ? data : null, false); logEvent(data.status === 'started' ? `Video stream started: ${data.name}` : 'Video stream stopped'); }
    else if (data.type === 'video_control') {
      const player = $('liveVideo');
      if (data.action === 'seek') { player.currentTime = Number(data.position || 0); if (data.playing === false) player.pause(); else player.play().catch(() => {}); }
      if (data.action === 'pause') { player.currentTime = Number(data.position || 0); player.pause(); }
      if (data.action === 'play') { player.currentTime = Number(data.position || 0); player.play().catch(() => {}); }
    }
    else if (data.type === 'error') logEvent(`Server notice: ${data.message}`);
  };
  ws.onclose = () => { setConnected(false); clearInterval(state.heartbeatTimer); stopProbes(); logEvent('Connection interrupted; retrying'); const delay = Math.min(10000, 500 * 2 ** state.attempts++); setTimeout(connect, delay); };
  ws.onerror = () => ws.close();
}
function sendProbe() {
  const sequence = ++state.sequence; const wall = Date.now();
  const payload = {type:'ping', sequence, client_timestamp:wall};
  const pending = { started:performance.now(), wall, timedOut:false, bytes:new TextEncoder().encode(JSON.stringify(payload)).length };
  pending.timeout = setTimeout(() => { pending.timedOut = true; if (state.probeRun) state.probeRun.timeouts += 1; appendProbeLine(`Request timed out: seq=${sequence}`); send({type:'probe_timeout', sequence, sent_at:pending.wall}); logEvent(`Probe ${sequence} timed out`); pending.expiry=setTimeout(()=>state.pending.delete(sequence),30000); }, state.probeTimeoutMs);
  state.pending.set(sequence, pending); if (state.probeRun) state.probeRun.sent += 1; send(payload);
}
function startProbes() { if (state.probeTimer) return; startProbeConsole(); sendProbe(); state.probeTimer = setInterval(sendProbe, Number($('probeInterval').value)); $('startProbe').disabled=true; $('stopProbe').disabled=false; }
function stopProbes() { if (state.probeTimer) printProbeSummary(); clearInterval(state.probeTimer); state.probeTimer=null; $('startProbe').disabled=false; $('stopProbe').disabled=true; }
$('startProbe').onclick = startProbes; $('stopProbe').onclick = stopProbes;
$('fullscreenVideo').onclick = async () => {
  const panel = $('videoPanel');
  if (document.fullscreenElement) await document.exitFullscreen();
  else if (panel.requestFullscreen) await panel.requestFullscreen();
  else if (panel.webkitRequestFullscreen) panel.webkitRequestFullscreen();
};
document.addEventListener('fullscreenchange', () => { $('fullscreenVideo').textContent = document.fullscreenElement ? 'Exit fullscreen' : 'Fullscreen'; });
async function runBandwidthTest() {
  if (bandwidthAbort) return;
  const seconds = Number($('bandwidthDuration').value); const controller = new AbortController(); bandwidthAbort = controller;
  bandwidthState.points = []; bandwidthState.current = 0; bandwidthState.average = 0; bandwidthState.peak = 0; updateBandwidthView(0, 0, 0, seconds);
  $('startBandwidth').disabled=true; $('stopBandwidth').disabled=false; $('bandwidthProgress').value=0; $('bandwidthStatus').textContent='Testing…';
  const started = performance.now(); let received = 0; let lastUpdate = started;
  try {
    const response = await fetch(`/api/bandwidth/download?seconds=${encodeURIComponent(seconds)}&t=${Date.now()}`, {cache:'no-store', headers:{'Cache-Control':'no-cache'}, signal:controller.signal});
    if (!response.ok || !response.body) throw new Error(`Bandwidth test failed (HTTP ${response.status})`);
    const reader = response.body.getReader();
    while (true) {
      const result = await reader.read(); if (result.done) break; received += result.value.byteLength;
      const now = performance.now(); if (now - lastUpdate >= 200) { const elapsed=(now-started)/1000; const speed=received*8/elapsed/1000000; updateBandwidthView(received, elapsed, speed, seconds); $('bandwidthStatus').textContent=`Testing · ${speed.toFixed(2)} Mbps`; lastUpdate=now; }
    }
    const elapsed=Math.max(0.001,(performance.now()-started)/1000); const speed=received*8/elapsed/1000000; updateBandwidthView(received, elapsed, speed, seconds); $('bandwidthProgress').value=100; $('bandwidthStatus').textContent=`Result: ${(received/1048576).toFixed(2)} MB in ${elapsed.toFixed(2)} s · ${speed.toFixed(2)} Mbps`;
  } catch (error) { if (error.name === 'AbortError') $('bandwidthStatus').textContent='Bandwidth test stopped.'; else $('bandwidthStatus').textContent=error.message; }
  finally { bandwidthAbort=null; $('startBandwidth').disabled=false; $('stopBandwidth').disabled=true; }
}
$('startBandwidth').onclick = runBandwidthTest;
$('stopBandwidth').onclick = () => bandwidthAbort?.abort();
$('resetProbe').onclick = () => { state.points=[]; state.metrics={}; state.probeRun=null; $('probeConsole').textContent='Ready. Select START LATENCY TEST to begin.'; ['currentRtt','baselineRtt','rttDelta','jitter','minRtt','avgRtt','medianRtt','maxRtt','p95Rtt'].forEach(id => $(id).textContent='—'); draw(); };
$('probeInterval').onchange = () => { if (state.probeTimer) { stopProbes(); startProbes(); } };
window.addEventListener('resize', () => { draw(); drawBandwidthChart(); });
$('saveIdentity').onclick = () => {
  if ($('saveIdentity').textContent === 'Edit details') { setIdentityApplied(false); $('name').focus(); return; }
  const name = $('name').value.trim(), institution = $('institution').value.trim();
  localStorage.setItem('participant_name', name); localStorage.setItem('institution', institution); identify(); setIdentityApplied(true); logEvent('Participant details applied');
};
$('messageForm').onsubmit = event => { event.preventDefault(); const text=$('messageText').value.trim(); if (!text) return; const stamp=performance.now(); send({type:'message_send',message_id:`m-${state.sequence}-${stamp}`,text,client_timestamp:Date.now()}); $('messageText').value=''; };
$('name').value = localStorage.getItem('participant_name') || ''; $('institution').value = localStorage.getItem('institution') || '';
if ($('name').value || $('institution').value) setIdentityApplied(true);
connect(); draw(); drawBandwidthChart();
