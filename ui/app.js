let API_BASE = localStorage.getItem('vexa_base') || 'http://localhost:18056';
let API_TOKEN = localStorage.getItem('vexa_token') || '';

const els = {
  platform: document.getElementById('platform'),
  meetingId: document.getElementById('meetingId'),
  sendBot: document.getElementById('sendBot'),
  stopBot: document.getElementById('stopBot'),
  downloadJson: document.getElementById('downloadJson'),
  summarize: document.getElementById('summarize'),
  transcript: document.getElementById('transcript'),
  topicCloud: document.getElementById('topic-cloud'),
  pollDot: document.getElementById('poll-dot'),
  recording: document.getElementById('recording-status'),
  participants: document.getElementById('participants'),
  participantCount: document.getElementById('participant-count'),
  speaking: document.getElementById('speaking'),
  summary: document.getElementById('summary'),
  decisions: document.getElementById('decisions'),
  viewTabs: [...document.querySelectorAll('.tab')],
  views: {
    home: document.getElementById('home'),
    meetings: document.getElementById('meetings'),
    settings: document.getElementById('settings'),
  },
  meetingsList: document.getElementById('meetingsList'),
  refreshMeetings: document.getElementById('refreshMeetings'),
  baseUrl: document.getElementById('baseUrl'),
  tokenInput: document.getElementById('tokenInput'),
  defaultMeeting: document.getElementById('defaultMeeting'),
  saveSettings: document.getElementById('saveSettings'),
  clearSettings: document.getElementById('clearSettings'),
  kwFrequent: document.getElementById('kw-frequent'),
  kwRare: document.getElementById('kw-rare'),
  downloadSummary: document.getElementById('downloadSummary'),
  // Emotion elements
  emotionEnabled: document.getElementById('emotion-enabled'),
  dominantMood: document.getElementById('dominant-mood'),
  moodConfidence: document.getElementById('mood-confidence'),
  emotionTimeline: document.getElementById('emotion-timeline'),
  emotionRefresh: document.getElementById('emotion-refresh'),
  // Analytics elements
  sentimentDistribution: document.getElementById('sentiment-distribution'),
  topEmotions: document.getElementById('top-emotions'),
  speakerInsights: document.getElementById('speaker-insights'),
};

let pollTimer = null;
let transcriptCache = [];
let lastMeetingId = '';
let recordingStartedAt = null;
let timerInterval = null;
let botInMeeting = false;

// Emotion analysis data
let emotionCache = {};
let emotionLabels = {};
let emotionTimeline = [];
let lastEmotionUpdate = 0;

function headers() {
  const token = API_TOKEN.trim();
  if (!token) throw new Error('Set API Token in Settings');
  return {
    'Content-Type': 'application/json',
    'X-API-Key': token,
  };
}

function addLine({ time, speaker, text }) {
  const tpl = document.getElementById('line-template');
  const node = tpl.content.firstElementChild.cloneNode(true);
  node.querySelector('.time').textContent = time || '';
  node.querySelector('.speaker-name').textContent = speaker || 'Unknown';
  node.querySelector('.text').textContent = text || '';
  
  // Add emotion indicator if emotion analysis is enabled
  const emotionEl = node.querySelector('.speaker-emotion');
  if (els.emotionEnabled?.checked && emotionCache[speaker]) {
    const emotion = emotionCache[speaker];
    emotionEl.textContent = emotion.emoji || '😐';
    emotionEl.title = `${emotion.emotion} (${Math.round(emotion.confidence * 100)}%)`;
    emotionEl.style.color = emotion.color || '#9CA3AF';
  }
  
  els.transcript.appendChild(node);
}

function toast(message, type='success'){
  const box = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  box.appendChild(el);
  setTimeout(()=>{ el.remove(); }, 3500);
}

function updateTopics() {
  const words = transcriptCache
    .flatMap(s => (s.text || '').toLowerCase().match(/\b[a-z]{3,}\b/g) || [])
    .filter(w => !['the','and','for','with','that','this','from','have','will','your','ours','you','are','was','but','not','our'].includes(w));
  const freq = new Map();
  for (const w of words) freq.set(w, (freq.get(w) || 0) + 1);
  const items = [...freq.entries()].sort((a,b)=>b[1]-a[1]);
  const frequent = items.slice(0,10).map(([w])=>w);
  const rareOnes = items.filter(([,c])=>c===1).map(([w])=>w).slice(-10);
  const rare = rareOnes.length ? rareOnes : items.slice(-10).map(([w])=>w);
  if (els.kwFrequent) els.kwFrequent.innerHTML = frequent.map(w=>`<span class="chip">${w}</span>`).join('');
  if (els.kwRare) els.kwRare.innerHTML = rare.map(w=>`<span class="chip">${w}</span>`).join('');
}

async function sendBot() {
  const platform = els.platform.value;
  const id = els.meetingId.value.trim();
  if (!API_BASE) return toast('Set API Base URL in Settings.', 'warn');
  if (!API_TOKEN) return toast('Set API Token in Settings.', 'warn');
  if (!id) return toast('Enter a meeting id.', 'warn');

  lastMeetingId = id; // track current meeting
  els.sendBot.disabled = true;
  els.sendBot.textContent = 'Sending...';
  try {
    const resp = await fetch(`${API_BASE}/bots`, {
      method: 'POST',
      mode: 'cors',
      headers: headers(),
      body: JSON.stringify({ platform, native_meeting_id: id, bot_name: 'VexaTestBot' }),
    });
    let data = {};
    try { data = await resp.json(); } catch {}
    if (!resp.ok) {
      console.error('Bot request failed', resp.status, data);
      toast('Bot request failed: ' + (data.detail || data.message || resp.status), 'error');
      return;
    }
    toast('Bot requested. Please admit the bot in your meeting.', 'success');
    startPolling();
  } catch (err) {
    console.error(err);
    toast('Network error while sending bot. Check API URL and token.', 'error');
  } finally {
    els.sendBot.disabled = false;
    els.sendBot.textContent = 'Send Bot';
  }
}

async function stopBot() {
  const platform = els.platform.value;
  const id = els.meetingId.value.trim();
  if (!id) return alert('Enter a meeting id');
  const resp = await fetch(`${API_BASE}/bots/${platform}/${id}`, {
    method: 'DELETE',
    headers: headers(),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(()=>({}));
    toast('Remove bot failed: ' + (data.detail || resp.status), 'error');
    return;
  }
  toast('Bot removed for this meeting.', 'success');
  botInMeeting = false;
  stopPolling();
}

async function getTranscript() {
  const platform = els.platform.value;
  const id = els.meetingId.value.trim();
  if (!id) return [];
  const resp = await fetch(`${API_BASE}/transcripts/${platform}/${id}`, {
    method: 'GET',
    headers: headers(),
  });
  if (!resp.ok) return [];
  const body = await resp.json().catch(()=>({}));
  const segments = body.segments || (body.data && body.data.transcripts) || [];
  updateParticipants(segments);
  return segments.map(s => ({
    time: s.time || s.start_time || '',
    speaker: s.speaker || s.speaker_name || 'Speaker',
    text: s.text || s.content || '',
  }));
}

function isAtBottom(el){
  return el.scrollTop + el.clientHeight >= el.scrollHeight - 8;
}

async function pollOnce() {
  try {
    els.pollDot.classList.add('active');
    const segments = await getTranscript();
    if (segments.length > transcriptCache.length) {
      const shouldStick = isAtBottom(els.transcript);
      const newSegs = segments.slice(transcriptCache.length);
      newSegs.forEach(addLine);
      transcriptCache = segments;
      updateTopics();
      if (shouldStick) els.transcript.scrollTop = els.transcript.scrollHeight;
      if (transcriptCache.length === newSegs.length) {
        toast('Bot admitted. Live transcription started.', 'success');
        botInMeeting = true;
        startTimer();
      }
    } else if (segments.length === 0 && transcriptCache.length > 0) {
      botInMeeting = false;
    }
  } catch (e) {
    console.warn(e);
    if (botInMeeting) botInMeeting = false;
  } finally {
    setTimeout(()=>els.pollDot.classList.remove('active'), 250);
  }
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(pollOnce, 3000);
  pollOnce();
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
  botInMeeting = false;
  stopTimer();
}

function downloadJSON() {
  const payload = transcriptCache.length ? { segments: transcriptCache } : { segments: [], note: 'No segments captured yet.' };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `transcript-${els.meetingId.value || 'meeting'}.json`;
  a.click();
}

async function summarize() {
  if (transcriptCache.length === 0) return alert('No transcript yet.');
  // Try llama (Ollama) summary first
  try {
    const platform = els.platform.value;
    const id = els.meetingId.value.trim();
    const resp = await fetch(`${API_BASE}/analysis/summarize_llama/${platform}/${id}`, { headers: headers() });
    if (resp.ok) {
      const data = await resp.json();
      const md = data.text || '';
      // Basic Markdown to HTML (headings and bullets)
      const html = md
        .replace(/^### (.*)$/gm, '<h3>$1</h3>')
        .replace(/^## (.*)$/gm, '<h3>$1</h3>')
        .replace(/^# (.*)$/gm, '<h3>$1</h3>')
        .replace(/^\- (.*)$/gm, '<li>$1</li>')
        .replace(/\n\n/g, '<br/>');
      els.summary.innerHTML = `<div>${html}</div>`;
      // Prepare downloadable
      if (els.downloadSummary) {
        els.downloadSummary.onclick = function(){
          const blob = new Blob([md], { type: 'text/markdown' });
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = `summary-${els.meetingId.value || 'meeting'}.md`;
          a.click();
        };
      }
      return;
    }
  } catch (e) { console.warn('llama summary failed, trying server TF', e); }
  // Fallback to server TF or client TF
  try {
    const platform = els.platform.value;
    const id = els.meetingId.value.trim();
    const resp = await fetch(`${API_BASE}/analysis/summarize/${platform}/${id}`, { headers: headers() });
    if (resp.ok) {
      const data = await resp.json();
      els.summary.innerHTML = `<ul class="bullets">${(data.bullets||[]).map(t=>`<li>${t}</li>`).join('')}</ul>`;
      return;
    }
  } catch (e) { console.warn('server TF summary failed, using client fallback', e); }
  // Client fallback
  const stop = new Set(['the','and','for','with','that','this','from','have','will','your','ours','you','are','was','but','not','our','their','them','they','she','his','her','him','who','what','when','where','why','how']);
  const allText = transcriptCache.map(s=>s.text||'').join(' ').toLowerCase();
  const tf = new Map();
  (allText.match(/\b[a-z]{3,}\b/g)||[]).forEach(w=>{ if(!stop.has(w)) tf.set(w,(tf.get(w)||0)+1); });
  const scored = [];
  for (const seg of transcriptCache){
    const sent = (seg.text||'').trim(); if(!sent) continue;
    const words = sent.toLowerCase().match(/\b[a-z]{3,}\b/g)||[];
    let score = 0; words.forEach(w=>{ if(!stop.has(w)) score += (tf.get(w)||0); });
    scored.push({score, sent: `(${seg.time||''}) ${seg.speaker||'Speaker'}: ${sent}`});
  }
  scored.sort((a,b)=>b.score-a.score);
  els.summary.innerHTML = `<ul class="bullets">${scored.slice(0,8).map(x=>`<li>${x.sent}</li>`).join('')}</ul>`;
}

function downloadSummaryTxt(){
  const txt = (els.summary.textContent || '').trim() || 'No summary available yet.';
  const blob = new Blob([txt], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `summary-${els.meetingId.value || 'meeting'}.txt`;
  a.click();
}

function updateParticipants(segments){
  const bySpeaker = new Map();
  for (const s of segments){
    const name = (s.speaker || 'Speaker').trim();
    bySpeaker.set(name, (bySpeaker.get(name)||0) + (s.text? s.text.split(/\s+/).length:0));
  }
  const entries = [...bySpeaker.entries()].sort((a,b)=>b[1]-a[1]);
  els.participants.innerHTML = entries.map(([name, score])=>{
    const emotion = emotionCache[name] || {};
    const emotionBadge = els.emotionEnabled?.checked && emotion.emoji ? 
      `<span class="emotion-badge" title="${emotion.emotion || 'neutral'} (${Math.round((emotion.confidence || 0) * 100)}%)"> ${emotion.emoji}</span>` : '';
    return `<div class="participant"><div class="avatar">${name.charAt(0)}</div><div><div>${name} <span class="muted" id="mood-${CSS.escape(name)}"></span>${emotionBadge}</div><div class="muted">${Math.max(1, Math.round(score))} words</div></div></div>`;
  }).join('');
  els.participantCount.textContent = `(${entries.length})`;

  // speaking bars
  const total = entries.reduce((a,[_n,v])=>a+v,0) || 1;
  els.speaking.innerHTML = entries.map(([name,v])=>{
    const pct = Math.round((v/total)*100);
    return `<div class="row"><div class="muted" style="width:70px">${name}</div><div class="bar"><span style="width:${pct}%"></span></div><div class="muted" style="width:34px;text-align:right">${pct}%</div></div>`;
  }).join('');

  // Fetch moods server-side and inject next to names (backward compatibility)
  updateMoods().catch(()=>{});
  
  // Update emotions if enabled
  if (els.emotionEnabled?.checked) {
    updateEmotions().catch(()=>{});
  }
}

async function updateMoods(){
  try {
    const platform = els.platform.value;
    const id = els.meetingId.value.trim();
    const resp = await fetch(`${API_BASE}/analysis/mood/${platform}/${id}`, { headers: headers() });
    if (!resp.ok) return;
    const data = await resp.json();
    const moods = data.moods || {};
    Object.entries(moods).forEach(([name, info])=>{
      const el = document.querySelector(`#mood-${CSS.escape(name)}`);
      if (el) el.textContent = info.dominant ? `(${info.dominant})` : '';
    });
  } catch (e) { console.warn('updateMoods failed', e); }
}

// Emotion Analysis Functions
async function initializeEmotionLabels() {
  try {
    const resp = await fetch(`${API_BASE}/analysis/emotions/labels`);
    if (resp.ok) {
      emotionLabels = await resp.json();
      console.log('Emotion labels loaded:', emotionLabels);
    }
  } catch (e) {
    console.warn('Failed to load emotion labels:', e);
  }
}

async function updateEmotions() {
  if (!els.emotionEnabled?.checked) return;
  
  try {
    const platform = els.platform.value;
    const id = els.meetingId.value.trim();
    if (!id) return;
    
    const resp = await fetch(`${API_BASE}/analysis/emotions/${platform}/${id}`, { 
      headers: headers() 
    });
    
    if (!resp.ok) {
      console.warn('Emotion analysis failed:', resp.status);
      return;
    }
    
    const data = await resp.json();
    
    // Update speaker emotion cache
    if (data.speakers) {
      data.speakers.forEach(speakerData => {
        const speaker = speakerData.speaker;
        if (speakerData.emotions && speakerData.emotions.length > 0) {
          // Get latest emotion
          const latestEmotion = speakerData.emotions[speakerData.emotions.length - 1];
          emotionCache[speaker] = latestEmotion;
        }
      });
    }
    
    // Update overall mood
    if (data.overall_mood) {
      updateOverallMood(data.overall_mood);
    }
    
    // Update emotion timeline
    if (data.emotion_timeline) {
      updateEmotionTimeline(data.emotion_timeline);
    }
    
    // Update analytics
    updateEmotionAnalytics(data);
    
  } catch (e) {
    console.warn('updateEmotions failed', e);
  }
}

function updateOverallMood(overallMood) {
  if (!els.dominantMood || !els.moodConfidence) return;
  
  // Find dominant emotion
  let dominantEmotion = 'neutral';
  let maxScore = 0;
  
  Object.entries(overallMood).forEach(([emotion, score]) => {
    if (score > maxScore) {
      maxScore = score;
      dominantEmotion = emotion;
    }
  });
  
  const emoji = (emotionLabels.labels && emotionLabels.labels[dominantEmotion]) || '😐';
  const confidence = Math.round(maxScore * 100);
  
  els.dominantMood.textContent = `${emoji} ${dominantEmotion.charAt(0).toUpperCase() + dominantEmotion.slice(1)}`;
  els.moodConfidence.textContent = `${confidence}%`;
}

function updateEmotionTimeline(timelineData) {
  if (!els.emotionTimeline) return;
  
  // Only show new emotions since last update
  const newEmotions = timelineData.filter(item => {
    const timestamp = new Date(item.timestamp).getTime();
    return timestamp > lastEmotionUpdate;
  });
  
  if (newEmotions.length === 0) return;
  
  // Update last emotion update timestamp
  if (timelineData.length > 0) {
    const latestTimestamp = new Date(timelineData[timelineData.length - 1].timestamp).getTime();
    lastEmotionUpdate = Math.max(lastEmotionUpdate, latestTimestamp);
  }
  
  // Add new emotion items
  newEmotions.forEach(addEmotionTimelineItem);
  
  // Keep only last 20 items
  const items = els.emotionTimeline.querySelectorAll('.emotion-item');
  if (items.length > 20) {
    for (let i = 0; i < items.length - 20; i++) {
      items[i].remove();
    }
  }
  
  // Scroll to bottom
  els.emotionTimeline.scrollTop = els.emotionTimeline.scrollHeight;
}

function addEmotionTimelineItem(emotionData) {
  const tpl = document.getElementById('emotion-timeline-item');
  if (!tpl) return;
  
  const node = tpl.content.firstElementChild.cloneNode(true);
  
  // Format timestamp
  const time = new Date(emotionData.timestamp);
  const timeStr = time.toLocaleTimeString('en-US', { 
    hour12: false, 
    hour: '2-digit', 
    minute: '2-digit' 
  });
  
  node.querySelector('.emotion-timestamp').textContent = timeStr;
  node.querySelector('.emotion-speaker').textContent = emotionData.speaker || 'Unknown';
  node.querySelector('.emotion-emoji').textContent = (emotionLabels.labels && emotionLabels.labels[emotionData.emotion]) || '😐';
  node.querySelector('.emotion-label').textContent = emotionData.emotion || 'neutral';
  node.querySelector('.emotion-confidence').textContent = `${Math.round((emotionData.confidence || 0) * 100)}%`;
  node.querySelector('.emotion-text-preview').textContent = emotionData.text_preview || '';
  
  // Set color
  const color = (emotionLabels.colors && emotionLabels.colors[emotionData.emotion]) || '#9CA3AF';
  node.querySelector('.emotion-label').style.color = color;
  
  // Add new item animation
  node.classList.add('new');
  setTimeout(() => node.classList.remove('new'), 800);
  
  // Insert at the top for newest first, or append for chronological order
  els.emotionTimeline.appendChild(node);
}

function updateEmotionAnalytics(data) {
  if (!els.emotionEnabled?.checked) return;
  
  // Update sentiment distribution
  if (data.overall_mood && els.sentimentDistribution) {
    updateSentimentBars(data.overall_mood);
  }
  
  // Update top emotions
  if (data.overall_mood && els.topEmotions) {
    updateTopEmotions(data.overall_mood);
  }
  
  // Update speaker insights
  if (data.speakers && els.speakerInsights) {
    updateSpeakerInsights(data.speakers);
  }
}

function updateSentimentBars(overallMood) {
  if (!els.sentimentDistribution) return;
  
  // Get top 5 emotions
  const sortedEmotions = Object.entries(overallMood)
    .sort(([,a], [,b]) => b - a)
    .slice(0, 5);
  
  if (sortedEmotions.length === 0) {
    els.sentimentDistribution.innerHTML = '<div class="muted">No emotion data yet</div>';
    return;
  }
  
  const maxValue = sortedEmotions[0][1];
  
  els.sentimentDistribution.innerHTML = sortedEmotions.map(([emotion, score]) => {
    const percentage = maxValue > 0 ? (score / maxValue) * 100 : 0;
    const color = (emotionLabels.colors && emotionLabels.colors[emotion]) || '#9CA3AF';
    
    return `
      <div class="sentiment-bar">
        <div class="sentiment-label">${emotion}</div>
        <div class="sentiment-progress">
          <div class="sentiment-fill" style="width: ${percentage}%; background-color: ${color};"></div>
        </div>
        <div class="sentiment-value">${Math.round(score * 100)}%</div>
      </div>
    `;
  }).join('');
}

function updateTopEmotions(overallMood) {
  if (!els.topEmotions) return;
  
  // Get top 8 emotions with counts
  const sortedEmotions = Object.entries(overallMood)
    .sort(([,a], [,b]) => b - a)
    .slice(0, 8);
  
  if (sortedEmotions.length === 0) {
    els.topEmotions.innerHTML = '<div class="muted">No emotions detected yet</div>';
    return;
  }
  
  els.topEmotions.innerHTML = sortedEmotions.map(([emotion, score]) => {
    const emoji = (emotionLabels.labels && emotionLabels.labels[emotion]) || '😐';
    const count = Math.round(score * 100);
    
    return `
      <div class="emotion-chip">
        <span class="emoji">${emoji}</span>
        <span>${emotion}</span>
        <span class="count">${count}</span>
      </div>
    `;
  }).join('');
}

function updateSpeakerInsights(speakers) {
  if (!els.speakerInsights) return;
  
  if (speakers.length === 0) {
    els.speakerInsights.innerHTML = '<div class="muted">No speaker data yet</div>';
    return;
  }
  
  els.speakerInsights.innerHTML = speakers.map(speaker => {
    const dominantEmotion = speaker.dominant_emotion || 'neutral';
    const emoji = (emotionLabels.labels && emotionLabels.labels[dominantEmotion]) || '😐';
    const emotionCount = speaker.emotions ? speaker.emotions.length : 0;
    
    return `
      <div class="speaker-insight">
        <div class="insight-speaker">${speaker.speaker}</div>
        <div class="insight-emotion">
          <span class="emoji">${emoji}</span>
          <span>${dominantEmotion}</span>
        </div>
        <div class="insight-count">${emotionCount}</div>
      </div>
    `;
  }).join('');
}

function toggleEmotionAnalysis() {
  const enabled = els.emotionEnabled?.checked;
  if (enabled) {
    // Initialize emotion labels if not already loaded
    if (!emotionLabels.labels) {
      initializeEmotionLabels();
    }
    // Update emotions immediately
    updateEmotions();
    toast('Emotion analysis enabled', 'success');
  } else {
    // Clear emotion cache and UI
    emotionCache = {};
    if (els.emotionTimeline) {
      els.emotionTimeline.innerHTML = '<div class="muted">Emotion analysis disabled.</div>';
    }
    if (els.dominantMood) {
      els.dominantMood.textContent = '😐 Neutral';
    }
    if (els.moodConfidence) {
      els.moodConfidence.textContent = '--';
    }
    // Clear analytics
    if (els.sentimentDistribution) {
      els.sentimentDistribution.innerHTML = '<div class="muted">Emotion analysis disabled</div>';
    }
    if (els.topEmotions) {
      els.topEmotions.innerHTML = '<div class="muted">Emotion analysis disabled</div>';
    }
    if (els.speakerInsights) {
      els.speakerInsights.innerHTML = '<div class="muted">Emotion analysis disabled</div>';
    }
    toast('Emotion analysis disabled', 'info');
  }
}

function computeKeywords(){
  const words = transcriptCache.flatMap(s => (s.text || '').toLowerCase().match(/\b[a-z]{3,}\b/g) || []);
  const stop = new Set(['the','and','for','with','that','this','from','have','will','your','ours','you','are','was','but','not','our','their','them','they','she','his','her','him','who','what','when','where','why','how']);
  const freq = new Map();
  for (const w of words){ if(!stop.has(w)) freq.set(w,(freq.get(w)||0)+1); }
  const items = [...freq.entries()].sort((a,b)=>b[1]-a[1]);
  const frequent = items.slice(0,10).map(([w])=>w);
  const rareOnes = items.filter(([,c])=>c===1).map(([w])=>w).slice(-10);
  const rare = rareOnes.length ? rareOnes : items.slice(-10).map(([w])=>w);
  if (els.kwFrequent) els.kwFrequent.innerHTML = frequent.map(w=>`<span class="chip">${w}</span>`).join('');
  if (els.kwRare) els.kwRare.innerHTML = rare.map(w=>`<span class="chip">${w}</span>`).join('');
}

// Navigation
function switchView(id){
  for (const [key,el] of Object.entries(els.views)){
    el.classList.toggle('hidden', `#${key}` !== id);
  }
  els.viewTabs.forEach(btn=>btn.classList.toggle('active', btn.dataset.view === id));
}

async function loadMeetings(){
  try{
    const resp = await fetch(`${API_BASE}/meetings`, { headers: headers() });
    if(!resp.ok) return;
    const data = await resp.json().catch(()=>({}));
    const list = (data.meetings)||[];
    els.meetingsList.innerHTML = list.map(m=>{
      const id = `${m.platform}/${m.native_meeting_id}`;
      return `<div class="participant" style="justify-content:space-between">
        <div><div style="font-weight:600">${m.platform}</div><div class="muted">${m.native_meeting_id}</div></div>
        <div class="buttons"><button class="ghost" data-open="${id}">Open</button></div>
      </div>`;
    }).join('');
    els.meetingsList.querySelectorAll('[data-open]').forEach(btn=>{
      btn.addEventListener('click',()=>{
        const [platform, native] = btn.dataset.open.split('/');
        els.platform.value = platform;
        els.meetingId.value = native;
        switchView('#home');
        startPolling();
      });
    });
  }catch(e){ console.warn(e); }
}

// Timer
function startTimer(){
  if (!botInMeeting) return;
  recordingStartedAt = new Date();
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = setInterval(()=>{
    if (!botInMeeting) { stopTimer(); return; }
    const diffMs = Date.now() - recordingStartedAt.getTime();
    const totalSec = Math.floor(diffMs/1000);
    const m = String(Math.floor(totalSec/60)).padStart(2,'0');
    const s = String(totalSec%60).padStart(2,'0');
    els.recording.textContent = `Recording • ${m}:${s}`;
  }, 1000);
}
function stopTimer(){ if (timerInterval) clearInterval(timerInterval); timerInterval = null; els.recording.textContent = 'Recording • 00:00'; }

// Settings
function loadSettings(){
  els.baseUrl.value = API_BASE;
  els.tokenInput.value = API_TOKEN ? '••••••••' : '';
  els.defaultMeeting.value = localStorage.getItem('vexa_meeting') || (window.__defaults && window.__defaults.MEETING_ID) || '';
  if (!els.meetingId.value && els.defaultMeeting.value) els.meetingId.value = els.defaultMeeting.value;
}

function saveSettings(){
  API_BASE = els.baseUrl.value.trim() || API_BASE;
  localStorage.setItem('vexa_base', API_BASE);
  if (els.tokenInput.value && els.tokenInput.value !== '••••••••'){
    API_TOKEN = els.tokenInput.value.trim();
    localStorage.setItem('vexa_token', API_TOKEN);
  }
  localStorage.setItem('vexa_meeting', els.defaultMeeting.value.trim());
  alert('Saved');
}

function clearSettings(){
  localStorage.removeItem('vexa_base');
  localStorage.removeItem('vexa_token');
  localStorage.removeItem('vexa_meeting');
  API_TOKEN = '';
  loadSettings();
}

// Prefill meeting id from defaults
if (window.__defaults && window.__defaults.MEETING_ID) {
  // do not force a specific default; let user type any id
}

els.sendBot.addEventListener('click', sendBot);
els.stopBot.addEventListener('click', stopBot);
els.downloadJson.addEventListener('click', ()=>{ computeKeywords(); downloadJSON(); });
els.summarize.addEventListener('click', ()=>{ summarize(); });
if (els.downloadSummary) els.downloadSummary.addEventListener('click', downloadSummaryTxt);
els.viewTabs.forEach(btn=>btn.addEventListener('click', ()=> switchView(btn.dataset.view)));
els.refreshMeetings.addEventListener('click', loadMeetings);
els.saveSettings.addEventListener('click', saveSettings);
els.clearSettings.addEventListener('click', clearSettings);

// Emotion analysis event listeners
if (els.emotionEnabled) {
  els.emotionEnabled.addEventListener('change', toggleEmotionAnalysis);
}
if (els.emotionRefresh) {
  els.emotionRefresh.addEventListener('click', () => {
    if (els.emotionEnabled?.checked) {
      updateEmotions();
      toast('Emotions refreshed', 'success');
    }
  });
}

loadSettings();
switchView('#home');

// Initialize emotion analysis
if (els.emotionEnabled?.checked) {
  initializeEmotionLabels();
}


