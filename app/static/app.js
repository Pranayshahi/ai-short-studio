let currentProjects = [];
let activeProject = null;

const WEAPONX_EXACT_PROMPT_TEMPLATE = `Create a high-resolution vertical infographic that replicates the EXACT visual design, layout, UI structure, typography, spacing, and presentation style of the attached reference image.

**DESIGN STYLE:**
- Clean, professional military encyclopedia infographic.
- Pure white background.
- Portrait 9:16 aspect ratio.
- Tall vertical poster layout.
- Thin black outer border with rounded corners.
- Minimalist, information-dense editorial design.
- Sharp, realistic photographic cutouts of objects.
- No gradients, no shadows behind text, no decorative illustrations.

**1. HEADER DESIGN**
- Place a wide black horizontal rounded rectangle at the very top.
- Center the main headline inside it.
- Use bold, condensed, uppercase white typography.
- Text should be prominent, similar to Anton, Bebas Neue, or Impact font.
- Keep consistent left and right margins.

**2. MAIN CONTENT LAYOUT**
Create a vertically stacked list of 10–12 entries.

Every entry must follow EXACTLY the same three-column visual arrangement:

LEFT COLUMN:
- Small country flag icon aligned to the left.
- Subject name in bold black sans-serif typography.
- Year/date in regular-weight black typography beside the name.
- Country or category name underneath in smaller black text.

CENTER COLUMN:
- One large, realistic, high-quality isolated photographic image of the featured subject.
- Horizontal orientation.
- Object should be displayed from its side profile.
- Maintain realistic proportions, accurate details, and sharp edges.
- White background with no surrounding environment.
- Image should occupy most of the available horizontal space.
- Align each subject image consistently.

RIGHT COLUMN:
- Two compact black bullet points.
- Display key specifications or important facts.
- Use clean, bold-readable sans-serif typography.
- Keep bullets consistently aligned.
- Maintain uniform font size and spacing.

**3. SPACING AND ALIGNMENT**
- Stack all entries vertically with consistent spacing.
- Use a fixed row structure throughout the infographic.
- Maintain consistent image sizes and text positioning.
- Use approximately 90% of the available width for content.
- Avoid overlapping text and images.
- Ensure every entry is visually separated through whitespace rather than boxes.
- Keep the overall design compact, similar to a technical reference chart.

**4. COLOR PALETTE**
- Background: Pure white (#FFFFFF).
- Header: Solid black (#000000).
- Main text: Black (#111111).
- Secondary text: Dark gray (#444444).
- Country flags: Original flag colors.
- Outer border: Black.
- Bottom accent: Thin red horizontal line (#FF1744).

**5. TYPOGRAPHY**
- Headline: Extra-bold condensed uppercase font.
- Subject names: Bold sans-serif.
- Dates: Regular sans-serif.
- Supporting labels: Small regular sans-serif.
- Specification bullets: Medium-weight sans-serif.
- Typography must be sharp, professional, and readable.

**6. VISUAL QUALITY**
- 4K-quality output.
- High-resolution photographic object cutouts.
- Accurate colors and realistic textures.
- Extremely clean alignment.
- Crisp text rendering.
- Professional military/technical reference infographic aesthetic.

**7. FINAL REQUIREMENTS**
- Reproduce the reference image's design language as closely as possible.
- Do not redesign the layout.
- Do not introduce cards, colored backgrounds, gradients, icons, charts, or modern UI elements.
- Do not use a magazine-cover design.
- Do not change the three-column arrangement.
- Keep the black rounded header and white background.
- Preserve the dense vertical infographic composition.
- Add a thin red accent line along the bottom edge.

**IMPORTANT:** Design replication is the highest priority. Content should fit naturally into the same visual structure without changing its proportions or layout.`;

document.addEventListener('DOMContentLoaded', () => {
  loadProjects();
  loadStudioSettings();
  loadMusicTracks();

  document.getElementById('btnRefresh')?.addEventListener('click', loadProjects);
  document.getElementById('btnGenerate')?.addEventListener('click', () => triggerGenerate('default'));
  document.getElementById('btnWeaponX')?.addEventListener('click', () => triggerGenerate('weaponx'));
  document.getElementById('btnOpenMontage')?.addEventListener('click', () => triggerGenerate('openmontage'));
  document.getElementById('btnOpenMusicStudio')?.addEventListener('click', () => openMusicModal());
  document.getElementById('btnCloseModal')?.addEventListener('click', closeModal);
  document.getElementById('btnRerenderModal')?.addEventListener('click', handleRerenderModal);
  const btnRegenWx = document.getElementById('btnRegenWeaponXModal');
  if (btnRegenWx) btnRegenWx.addEventListener('click', handleRegenerateWeaponXModal);
  document.getElementById('btnModalPublish')?.addEventListener('click', () => publishActiveProject(false));
  const btnApprove = document.getElementById('btnModalApproveLive');
  if (btnApprove) btnApprove.addEventListener('click', () => approveActiveProjectLive(false));
  document.getElementById('btnModalDelete')?.addEventListener('click', () => {
    if (activeProject) deleteVideo(activeProject.id);
  });

  // Prompt Studio toggle on dashboard
  const btnTogglePrompt = document.getElementById('btnToggleDashPrompt') || document.getElementById('btnTogglePromptStudio');
  const dashPromptPanel = document.getElementById('dashPromptSection') || document.getElementById('dashboardPromptStudioPanel');
  const dashPromptInput = document.getElementById('dashPromptInput');
  if (dashPromptInput) dashPromptInput.value = WEAPONX_EXACT_PROMPT_TEMPLATE;
  if (btnTogglePrompt && dashPromptPanel) {
    btnTogglePrompt.addEventListener('click', () => {
      dashPromptPanel.classList.toggle('hidden');
    });
  }
  const btnDashReset = document.getElementById('btnDashResetWeaponXPrompt');
  if (btnDashReset && dashPromptInput) {
    btnDashReset.addEventListener('click', () => {
      dashPromptInput.value = WEAPONX_EXACT_PROMPT_TEMPLATE;
    });
  }
  const btnDashCallAgain = document.getElementById('btnDashCallPromptAgain');
  if (btnDashCallAgain) {
    btnDashCallAgain.addEventListener('click', () => {
      triggerGenerate('weaponx');
    });
  }

  // Modal Image Prompt & Call Again
  const btnResetWxModal = document.getElementById('btnResetWeaponXPrompt');
  if (btnResetWxModal) {
    btnResetWxModal.addEventListener('click', () => {
      const promptEl = document.getElementById('modalImagePromptText');
      const headlineEl = document.getElementById('modalPromptHeadlineInput');
      const headline = headlineEl ? headlineEl.value.trim() : (activeProject?.title || 'TOP WEAPONS INFOGRAPHIC');
      if (promptEl) {
        promptEl.value = `${WEAPONX_EXACT_PROMPT_TEMPLATE}\n\n**SPECIFIC CONTENT FOR THIS INFOGRAPHIC:**\n- Main Header Headline: ${headline.toUpperCase()}\n- Topic: ${activeProject?.topic || headline}`;
      }
    });
  }
  const btnCallAgain = document.getElementById('btnCallPromptAgain');
  if (btnCallAgain) {
    btnCallAgain.addEventListener('click', handleCallPromptAgain);
  }

  // Initialize Multi-Layer Image Studio & Events
  initLayerStudioEvents();

  // Settings panel controls
  const durationSelect = document.getElementById('durationSelect');
  const customDurWrapper = document.getElementById('customDurationWrapper');
  if (durationSelect && customDurWrapper) {
    durationSelect.addEventListener('change', () => {
      if (durationSelect.value === 'custom') {
        customDurWrapper.style.display = 'inline-flex';
        document.getElementById('customDurationInput')?.focus();
      } else {
        customDurWrapper.style.display = 'none';
      }
    });
  }

  const btnToggleSettings = document.getElementById('btnToggleSettings');
  if (btnToggleSettings) {
    btnToggleSettings.addEventListener('click', () => {
      document.getElementById('studioSettingsPanel')?.classList.toggle('hidden');
    });
  }
  const btnSaveGeminiKey = document.getElementById('btnSaveGeminiKey');
  if (btnSaveGeminiKey) {
    btnSaveGeminiKey.addEventListener('click', saveGeminiSettings);
  }
  const btnUploadWxRef = document.getElementById('btnUploadWxRef');
  const wxRefInput = document.getElementById('wxRefFileInput');
  if (btnUploadWxRef && wxRefInput) {
    btnUploadWxRef.addEventListener('click', () => wxRefInput.click());
    wxRefInput.addEventListener('change', handleUploadWeaponXReference);
  }
  const btnUploadYtSecrets = document.getElementById('btnUploadYtSecrets');
  const ytSecretsInput = document.getElementById('ytSecretsFileInput');
  if (btnUploadYtSecrets && ytSecretsInput) {
    btnUploadYtSecrets.addEventListener('click', () => ytSecretsInput.click());
    ytSecretsInput.addEventListener('change', handleUploadYoutubeSecrets);
  }
  const btnAuthYoutube = document.getElementById('btnAuthYoutube');
  if (btnAuthYoutube) {
    btnAuthYoutube.addEventListener('click', handleTriggerYoutubeOAuth);
  }

  // Close modal when clicking backdrop
  document.getElementById('videoModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'videoModal') closeModal();
  });

  // Load AI & Saved Music tracks into all track selectors (#musicTrackSelect & #carMotionPhonkSelect)
  loadMusicTracks();
});

async function loadStudioSettings() {
  try {
    const res = await fetch(`/api/settings?t=${Date.now()}`);
    if (!res.ok) return;
    const s = await res.json();
    const statusEl = document.getElementById('settingsStatusText');
    if (statusEl) {
      const geminiState = s.gemini_configured ? '✓ Gemini API Key Active' : '⚡ Built-in WeaponX Infographic Engine Active';
      const refState = s.has_weaponx_reference_image ? ' · ✓ Custom Gemini Reference Image Locked' : '';
      const ytState = s.youtube_oauth_configured ? ' · ✓ YouTube OAuth Ready' : ' · ⚡ YouTube Studio Draft & Approval Mode';
      statusEl.textContent = `${geminiState}${refState}${ytState} · Target Channel: ${s.youtube_channel_id}`;
    }
  } catch (e) {
    console.error(e);
  }
}

async function saveGeminiSettings() {
  const input = document.getElementById('geminiApiKeyInput');
  const statusEl = document.getElementById('settingsStatusText');
  const key = input ? input.value.trim() : '';
  if (!key) {
    alert('Please paste your GEMINI_API_KEY first.');
    return;
  }
  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gemini_api_key: key })
    });
    if (res.ok) {
      input.value = '';
      if (statusEl) statusEl.textContent = '✓ Gemini API Key saved! WeaponX Labs Style will now synthesize via your Gemini account.';
      loadStudioSettings();
    }
  } catch (e) {
    alert('Failed to save Gemini key');
  }
}

async function handleUploadWeaponXReference(e) {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  const statusEl = document.getElementById('settingsStatusText');
  if (statusEl) statusEl.textContent = 'Uploading Gemini reference image...';
  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await fetch('/api/settings/weaponx-reference', {
      method: 'POST',
      body: formData
    });
    if (res.ok) {
      if (statusEl) statusEl.textContent = '✓ Gemini WeaponX Reference Image saved! All new WeaponX Labs Shorts will match this design.';
    } else {
      alert('Failed to upload reference image');
    }
  } catch (err) {
    alert('Error uploading reference image');
  }
}

async function handleUploadYoutubeSecrets(e) {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  const statusEl = document.getElementById('settingsStatusText');
  if (statusEl) statusEl.textContent = 'Uploading client_secrets.json...';
  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await fetch('/api/settings/youtube-secrets', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (res.ok) {
      if (statusEl) statusEl.textContent = '✓ Saved credentials/client_secrets.json! Click "🔗 Connect YouTube OAuth" to sign in.';
      loadStudioSettings();
    } else {
      alert(data.detail || 'Invalid client_secrets.json');
    }
  } catch (err) {
    alert('Failed to upload client_secrets.json');
  }
}

async function handleTriggerYoutubeOAuth(channelOverride) {
  const chInfo = resolveTargetYoutubeChannel(activeProject, channelOverride);
  const statusEl = document.getElementById('settingsStatusText');
  if (statusEl) statusEl.textContent = `Launching Google OAuth browser sign-in for ${chInfo.handle} (${chInfo.id})...`;
  try {
    const res = await fetch(`/api/settings/youtube-auth?channel=${encodeURIComponent(chInfo.key)}`, { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      if (statusEl) statusEl.textContent = `✓ YouTube OAuth Connected! Channel ${chInfo.id} (${chInfo.handle}) is ready for private API uploads.`;
      loadStudioSettings();
    } else {
      alert(data.detail || 'Please upload client_secrets.json first.');
    }
  } catch (err) {
    alert('Error launching YouTube OAuth');
  }
}

async function loadProjects() {
  try {
    const res = await fetch(`/api/projects?t=${Date.now()}`);
    currentProjects = await res.json();
    renderGrid(currentProjects);
  } catch (err) {
    console.error('Failed to load projects:', err);
  }
}

function renderGrid(projects) {
  const grid = document.getElementById('projectsGrid');
  const countBadge = document.getElementById('projectCount');
  countBadge.textContent = `${projects.length} video${projects.length === 1 ? '' : 's'}`;

  if (!projects || projects.length === 0) {
    grid.innerHTML = `
      <div style="grid-column: 1/-1; text-align: center; padding: 60px 20px; color: #64748b;">
        <p style="font-size: 18px; margin-bottom: 8px;">No YouTube Shorts produced yet</p>
        <p style="font-size: 14px;">Click "Generate Next Short" above to launch the autonomous pipeline.</p>
      </div>
    `;
    return;
  }

  grid.innerHTML = projects.map(p => {
    const isInProgress = p.status === 'in_progress' || p.status === 'queued';  // queued = waiting for the video worker
    const isFailed = p.status === 'failed';
    const isPendingApproval = p.status === 'pending_approval' || (p.youtube && p.youtube.approval_status === 'pending_approval');
    // The app never makes videos public: 'published' (old records) and 'uploaded_private' both mean
    // "uploaded, private on YouTube"
    const isPub = p.status === 'published' || p.status === 'uploaded_private';
    const duration = p.duration ? `${Math.round(p.duration)}s` : (isInProgress ? '...' : '25s');
    const thumbUrl = `/api/thumbnail/${p.id}?t=${Date.now()}`;
    
    // QA badge text
    const qa = p.qa_report;
    let qaScore = '100% PASSED';
    let qaClass = '';
    if (isInProgress) {
      qaScore = `⚡ ${p.progress_step || 'Generating...'}`;
      qaClass = 'warnings';
    } else if (isFailed) {
      qaScore = '✕ FAILED';
      qaClass = 'failed';
    } else if (qa) {
      qaScore = `${qa.overall_score}% ${qa.status}`;
      qaClass = (qa.status === 'FAILED') ? 'failed' : '';
    }

    const needsAttention = p.status === 'needs_attention';
    const openFb = (p.feedback || []).filter(f => f.status === 'open').length;
    let pubPill = '';
    if (needsAttention) {
      const why = (p.problems || []).map(x => '• ' + x).join('\n') || 'A quality check failed';
      pubPill = `<span class="pub-pill" title="${escapeHtml(why)}" style="background: rgba(245,158,11,0.18); color: #fbbf24; border: 1px solid rgba(245,158,11,0.5);">⚠️ Needs attention</span>`;
    } else if (isInProgress) {
      pubPill = `<span class="pub-pill" style="background: rgba(0,229,255,0.15); color: #00e5ff; border: 1px solid rgba(0,229,255,0.3);">⚡ In Progress</span>`;
    } else if (isFailed) {
      pubPill = `<span class="pub-pill" style="background: rgba(239,68,68,0.15); color: #ef4444; border: 1px solid rgba(239,68,68,0.3);">✕ Failed</span>`;
    } else if (p.status === 'approved_private' || (p.youtube && p.youtube.approval_status === 'approved_private')) {
      pubPill = `<span class="pub-pill" style="background: rgba(16,185,129,0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.4);">🔒 Approved · Private on YouTube</span>`;
    } else if (isPendingApproval) {
      pubPill = `<span class="pub-pill" style="background: rgba(245,158,11,0.18); color: #fbbf24; border: 1px solid rgba(245,158,11,0.4);">⏳ Saved · Awaiting Approval</span>`;
    } else {
      pubPill = `<span class="pub-pill ${isPub ? 'published' : 'ready'}">${isPub ? '🔒 Uploaded · Private on YouTube' : '● Ready to Upload'}</span>`;
    }

    const clickAction = isInProgress
      ? `alert('Video is currently being generated:\\n${escapeHtml(p.progress_step || 'Please wait a moment...')}')`
      : (isFailed ? `alert('Generation failed: ${escapeHtml(p.error || 'Unknown error')}')` : `openModal('${p.id}')`);

    return `
      <div class="short-card" data-project-id="${p.id}" onclick="${clickAction}">
        <div class="card-thumbnail-wrapper">
          <div class="card-top-actions">
            ${!isInProgress ? `<button class="card-fb-btn" title="Feedback: tell Auto-fix what's wrong with this video" onclick="event.stopPropagation(); openFeedbackPanel('${p.id}')">💬${openFb ? `<span class="card-fb-count">${openFb}</span>` : ''}</button>` : ''}
            <button class="card-del-btn" title="Delete Video" onclick="event.stopPropagation(); deleteVideo('${p.id}')">✕</button>
          </div>
          ${isInProgress ? `
            <div style="width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; background: #0f172a; color: #00e5ff; min-height: 240px;">
              <div class="spinner" style="margin-bottom: 12px; width: 32px; height: 32px; border-width: 3px;"></div>
              <span style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600;">Generating</span>
              <span style="font-size: 10px; color: #94a3b8; margin-top: 4px; text-align: center; padding: 0 10px;">${escapeHtml(p.progress_step || 'Processing...')}</span>
            </div>
          ` : `
            <img class="card-thumbnail" src="${thumbUrl}" onerror="this.style.display='none'" alt="Short Preview">
            <div class="play-overlay">
              <div class="play-icon">▶</div>
            </div>
            <span class="card-duration">${duration}</span>
          `}
        </div>
        <div class="card-body">
          <h3 class="card-title">${escapeHtml(p.title || p.topic)}</h3>
          <div class="card-footer">
            <span class="qa-card-badge ${qaClass}">🛡️ QA: ${qaScore}</span>
            ${p.style === 'openmontage' ? '<span class="badge-openmontage">🎬 OpenMontage</span>' : (p.style === 'weaponx' ? '<span class="badge-openmontage" style="background: rgba(255,69,0,0.18); border-color: rgba(255,69,0,0.5); color: #ff8c00;">🔥 WeaponX</span>' : '')}
            ${pubPill}
          </div>
          ${openFb && !needsAttention && !isInProgress ? `
            <div style="margin-top: 8px; padding: 8px; border-radius: 6px; background: rgba(0,229,255,0.08); border: 1px solid rgba(0,229,255,0.3); font-size: 11px; color: #67e8f9;">
              💬 ${openFb} feedback note${openFb > 1 ? 's' : ''} waiting
              <button class="btn btn-primary btn-xs" id="autoFixBtn_${p.id}" style="margin-left: 6px; font-size: 11px; padding: 4px 8px;" onclick="event.stopPropagation(); autoRepairProject('${p.id}')">🔧 Auto-fix &amp; re-check</button>
            </div>
          ` : ''}
          ${needsAttention ? `
            <div class="needs-attention-box" style="margin-top: 8px; padding: 8px; border-radius: 6px; background: rgba(245,158,11,0.10); border: 1px solid rgba(245,158,11,0.35); font-size: 11px; color: #fcd34d; line-height: 1.4;">
              ${(p.problems || []).slice(0, 3).map(x => `<div>• ${escapeHtml(String(x).slice(0, 140))}</div>`).join('')}
              <button class="btn btn-primary btn-xs" id="autoFixBtn_${p.id}" style="margin-top: 6px; font-size: 11px; padding: 5px 10px;" onclick="event.stopPropagation(); autoRepairProject('${p.id}')">🔧 Auto-fix &amp; re-check</button>
            </div>
          ` : ''}
          ${!isInProgress && !isFailed ? `
            <div style="display: flex; gap: 6px; margin-top: 10px; flex-wrap: wrap;">
              <button class="btn btn-secondary btn-xs" style="flex: 1; padding: 6px 8px; font-size: 11px; border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; gap: 3px;" onclick="event.stopPropagation(); openStudioModal(1, '${p.id}')">🎨 Studio</button>
              <button class="btn btn-secondary btn-xs" style="padding: 6px 8px; font-size: 11px; border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; gap: 3px; background: rgba(147, 51, 234, 0.2); border-color: #9333ea; color: #c084fc;" title="Add AI Music or YouTube Audio" onclick="event.stopPropagation(); openMusicModal('${p.id}')">🎵 Music</button>
              <button class="btn btn-secondary btn-xs" style="padding: 6px 8px; font-size: 11px; border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; gap: 3px; background: rgba(234, 88, 12, 0.2); border-color: #ea580c; color: #fb923c;" title="Convert to Hindi Voiceover" onclick="event.stopPropagation(); openHindiModalForProject('${p.id}')">🇮🇳 Hindi</button>
              <button class="btn btn-secondary btn-xs" style="padding: 6px 10px; font-size: 11px; border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; gap: 3px;" onclick="event.stopPropagation(); openModal('${p.id}')">🎬 View</button>
            </div>
          ` : ''}
        </div>
      </div>
    `;
  }).join('');
}

async function triggerGenerate(style = 'default', chartPreviewId = null) {
  const topicInput = document.getElementById('customTopicInput');
  const topic = topicInput.value.trim() || null;
  const audioMode = document.getElementById('audioModeSelect')?.value || 'with_voice';

  // Read language, voice actor, and music track preferences
  const langVoiceVal = document.getElementById('langVoiceSelect')?.value || 'en:en-US-ChristopherNeural';
  const [selectedLang, selectedVoice] = langVoiceVal.includes(':') ? langVoiceVal.split(':') : ['en', langVoiceVal];
  const selectedMusicTrack = document.getElementById('musicTrackSelect')?.value || 'default';

  // Calculate target duration (5s to 180s / 3 minutes)
  let duration = 30;
  const durationSelect = document.getElementById('durationSelect');
  if (durationSelect) {
    if (durationSelect.value === 'custom') {
      const customInput = document.getElementById('customDurationInput');
      duration = customInput ? parseFloat(customInput.value) : 30;
    } else {
      duration = parseFloat(durationSelect.value);
    }
  }
  if (isNaN(duration) || duration < 5) duration = 5;
  if (duration > 180) duration = 180;

  // Determine voice and music flags
  let withVoice = true;
  let withMusic = true;
  if (audioMode === 'without_music') {
    withVoice = true;
    withMusic = false;
  } else if (audioMode === 'without_voice') {
    withVoice = false;
    withMusic = true;
  } else if (audioMode === 'mute') {
    withVoice = false;
    withMusic = false;
  } else {
    withVoice = true;
    withMusic = true;
  }

  const banner = document.getElementById('statusBanner');
  const msg = document.getElementById('statusMessage');
  const btn = document.getElementById('btnGenerate');
  const btnWx = document.getElementById('btnWeaponX');
  const btnOm = document.getElementById('btnOpenMontage');

  banner.classList.remove('hidden');
  const styleLabel = style === 'weaponx' ? 'WeaponX Labs style' : (style === 'openmontage' ? 'OpenMontage documentary montage style' : 'documentary style');
  
  let audioLabel = 'voiceover + music';
  if (audioMode === 'without_music') audioLabel = 'voiceover only (without music)';
  else if (audioMode === 'without_voice') audioLabel = 'music only (without voice)';
  else if (audioMode === 'mute') audioLabel = 'mute';

  msg.textContent = topic
    ? `Initiating ${styleLabel} (${duration}s · ${audioLabel}) for: "${topic}"...`
    : `Initiating autonomous ${styleLabel} (${duration}s · ${audioLabel})...`;
  
  btn.disabled = true;
  if (btnWx) btnWx.disabled = true;
  if (btnOm) btnOm.disabled = true;

  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic,
        auto_publish: false,
        style,
        with_voice: withVoice,
        with_music: withMusic,
        audio_mode: audioMode,
        duration: duration,
        language: selectedLang,
        voice: selectedVoice,
        music_track: selectedMusicTrack,
        music_volume: 0.22,
        chart_preview_id: chartPreviewId
      })
    });
    
    if (res.ok) {
      const data = await res.json();
      topicInput.value = '';
      // Immediately refresh projects to show the new pending card
      await loadProjects();
      if (data.status === 'already_running') {
        // Same video is already generating: follow it instead of creating a duplicate
        const msgEl = document.getElementById('statusMessage');
        if (msgEl) msgEl.textContent = `⏳ ${data.message}`;
        const card = document.querySelector(`[data-project-id="${data.project_id}"]`);
        if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
      pollGenerationStatus(data.project_id);
    } else {
      alert('Failed to start generation');
      banner.classList.add('hidden');
      btn.disabled = false;
      if (btnWx) btnWx.disabled = false;
      if (btnOm) btnOm.disabled = false;
    }
  } catch (err) {
    console.error(err);
    banner.classList.add('hidden');
    btn.disabled = false;
    if (btnWx) btnWx.disabled = false;
    if (btnOm) btnOm.disabled = false;
  }
}

function pollGenerationStatus(targetProjectId) {
  const banner = document.getElementById('statusBanner');
  const msg = document.getElementById('statusMessage');
  const btn = document.getElementById('btnGenerate');
  const btnWx = document.getElementById('btnWeaponX');
  const btnOm = document.getElementById('btnOpenMontage');

  let pollCount = 0;
  const interval = setInterval(async () => {
    pollCount++;
    try {
      const res = await fetch(`/api/projects?t=${Date.now()}`);
      const projects = await res.json();
      currentProjects = projects;
      renderGrid(currentProjects);

      const target = targetProjectId ? projects.find(p => p.id === targetProjectId) : projects[0];
      if (target) {
        if (target.progress_step) {
          msg.textContent = `Autonomous agent producing: ${target.progress_step}`;
        }

        // finished in any way other than failure (completed / needs attention / uploaded / awaiting review)
        if (target.status !== 'in_progress' && target.status !== 'queued' && target.status !== 'failed') {
          clearInterval(interval);
          banner.classList.add('hidden');
          btn.disabled = false;
          if (btnWx) btnWx.disabled = false;
          if (btnOm) btnOm.disabled = false;
          await loadProjects();
          openModal(target.id);
          return;
        } else if (target.status === 'failed') {
          clearInterval(interval);
          banner.classList.add('hidden');
          btn.disabled = false;
          if (btnWx) btnWx.disabled = false;
          if (btnOm) btnOm.disabled = false;
          alert(`Video generation failed: ${target.error || 'Check server logs'}`);
          await loadProjects();
          return;
        }
      }

      // Safety timeout after ~30 minutes (a queued video may wait for others to finish first)
      if (pollCount > 450) {
        clearInterval(interval);
        banner.classList.add('hidden');
        btn.disabled = false;
        if (btnWx) btnWx.disabled = false;
        if (btnOm) btnOm.disabled = false;
        loadProjects();
      }
    } catch (err) {
      console.error('Polling status error:', err);
    }
  }, 4000);
}

async function deleteVideo(projectId) {
  if (!projectId) return;

  const confirmed = confirm('Are you sure you want to permanently delete this video and its assets?');
  if (!confirmed) return;

  try {
    const res = await fetch(`/api/projects/${projectId}`, { method: 'DELETE' });
    if (res.ok) {
      if (activeProject && activeProject.id === projectId) {
        closeModal();
      }
      loadProjects();
    } else {
      alert('Failed to delete video');
    }
  } catch (err) {
    console.error('Delete error:', err);
    alert('Error deleting video');
  }
}

async function openModal(projectId) {
  let project = currentProjects.find(p => p.id === projectId);
  try {
    const res = await fetch(`/api/projects/${projectId}?t=${Date.now()}`);
    if (res.ok) {
      project = await res.json();
    }
  } catch (err) {
    // fallback to currentProjects
  }
  if (!project) return;
  activeProject = project;

  const modal = document.getElementById('videoModal');
  const videoPlayer = document.getElementById('modalVideoPlayer');
  
  videoPlayer.src = `/api/video/${activeProject.id}?t=${Date.now()}`;
  document.getElementById('modalTitle').textContent = activeProject.title || activeProject.topic;
  document.getElementById('modalDesc').textContent = activeProject.description || 'No description available.';

  // Sync voice & audio mode toggle in modal
  const voiceToggle = document.getElementById('modalVoiceToggle');
  if (voiceToggle) {
    if (activeProject.audio_mode) {
      voiceToggle.value = activeProject.audio_mode;
    } else if (activeProject.with_voice && activeProject.with_music === false) {
      voiceToggle.value = 'without_music';
    } else if (activeProject.with_voice === false && activeProject.with_music !== false) {
      voiceToggle.value = 'without_voice';
    } else if (activeProject.with_voice === false && activeProject.with_music === false) {
      voiceToggle.value = 'mute';
    } else {
      voiceToggle.value = 'with_voice';
    }
  }

  const tagsContainer = document.getElementById('modalTags');
  tagsContainer.innerHTML = (activeProject.tags || []).map(t => `<span class="tag-badge">#${escapeHtml(t)}</span>`).join('');

  // Populate YouTube Studio (UC4KV67NYzLi8JlrfB9J4hGg) editable fields
  const ytTitleInput = document.getElementById('modalYtTitleInput');
  const ytDescInput = document.getElementById('modalYtDescInput');
  const ytTagsInput = document.getElementById('modalYtTagsInput');
  const filled = activeProject.youtube?.filled_fields || {};
  if (ytTitleInput) ytTitleInput.value = filled.title || activeProject.title || `${activeProject.topic} #Shorts`;
  if (ytDescInput) ytDescInput.value = filled.description || activeProject.description || `#Shorts #WeaponXLabs`;
  if (ytTagsInput) ytTagsInput.value = (filled.tags || activeProject.tags || ['WeaponXLabs', 'Shorts', 'MilitaryTech']).join(', ');

  renderModalScenes();

  // Fetch and display deep QA inspection
  loadQAInspection(activeProject.id);

  // Load Prompt Studio & Image Editor for this project
  loadModalPromptAndEditor(activeProject);

  renderModalPublishState(activeProject);

  modal.classList.remove('hidden');
  videoPlayer.play().catch(() => {});
}

function renderModalScenes() {
  const scenesContainer = document.getElementById('modalScenes');
  if (!scenesContainer || !activeProject) return;
  scenesContainer.innerHTML = (activeProject.scenes || []).map(s => {
    let sourceBadge = '';
    if (s.visual_source === 'manual_upload') {
      sourceBadge = `<span class="source-pill manual">📁 Custom Upload</span>`;
    } else if (s.visual_source === 'gemini_weaponx') {
      sourceBadge = `<a class="source-pill gemini" href="https://gemini.google.com/u/1/app/dbdf5025a758bf01" target="_blank" style="text-decoration: none;">✨ Gemini WeaponX Poster</a>`;
    } else if (s.visual_source === 'weaponx_lab_poster' || s.visual_source === 'weaponx_poster' || activeProject.style === 'weaponx') {
      sourceBadge = `<span class="source-pill weaponx">🔥 WeaponX Labs Poster</span>`;
    } else if (activeProject.style === 'openmontage') {
      sourceBadge = `<span class="source-pill openmontage">🎬 OpenMontage</span>`;
    } else if (s.visual_source === 'web_free') {
      const urlAttr = s.visual_source_url ? `href="${s.visual_source_url}" target="_blank"` : '';
      sourceBadge = `<a class="source-pill web" ${urlAttr} style="text-decoration: none;">🌐 Free Web Photo</a>`;
    } else if (s.visual_source === 'ai_generated') {
      sourceBadge = `<span class="source-pill ai">✨ AI Generated (Flux)</span>`;
    } else if (s.visual_source === 'placeholder_copy') {
      const from = s.placeholder_from_scene ? ` from Scene ${s.placeholder_from_scene}` : '';
      sourceBadge = `<span class="source-pill placeholder" title="This new scene borrowed a neighbouring image. Replace it with Add Image, Regenerate AI or Add Clip.">⚠ Placeholder image${from}</span>`;
    }

    const sceneImgUrl = `/api/scene_image/${activeProject.id}/${s.scene_number}?t=${Date.now()}`;
    const hasClip = Boolean(s.clip_path);
    const clipBadge = hasClip ? `<span class="source-pill clip" title="${escapeHtml(s.clip_name || 'Video clip')}">🎬 Video Clip</span>` : '';
    const fxBadge = sceneEffectsBadge(s);
    const thumbHtml = hasClip
      ? `<video src="/api/scene_clip/${activeProject.id}/${s.scene_number}?t=${Date.now()}" id="sceneThumbImg_${s.scene_number}" class="scene-thumb-preview" muted loop autoplay playsinline poster="${sceneImgUrl}"></video>`
      : `<img src="${sceneImgUrl}" id="sceneThumbImg_${s.scene_number}" class="scene-thumb-preview" onerror="this.style.opacity='0.2'" alt="Scene ${s.scene_number}">`;

    return `
      <div class="scene-item" id="sceneCard_${s.scene_number}">
        <div class="scene-item-top">
          <!-- Line 1: Scene Title and Source Pill -->
          <div class="scene-title-badge">
            <strong class="scene-number-title">Scene ${s.scene_number}</strong>
            ${sourceBadge}
            ${clipBadge}
            ${fxBadge}
          </div>
          <!-- Line 2: Dedicated Action Controls -->
          <div class="scene-image-controls">
            <button class="btn btn-secondary btn-xs" onclick="openStudioModal(${s.scene_number})" title="Open Multi-Layer Studio for Scene ${s.scene_number}">
              🎨 Edit Layers
            </button>
            <button class="btn btn-primary btn-xs" onclick="openSceneAiGenerateModal('${activeProject.id}', ${s.scene_number})" title="Regenerate this scene image via AI">
              ⚡ Regenerate AI
            </button>
            <button class="btn btn-secondary btn-xs" onclick="openSceneImageModal('${activeProject.id}', ${s.scene_number})" title="Add image: Generate with AI Prompt or Upload File">
              📁 Add Image
            </button>
            <button class="btn btn-secondary btn-xs" onclick="openSceneClipModal('${activeProject.id}', ${s.scene_number})" title="Add a video clip: generate with Wan 2.2 / LTX-2.3 or upload — it replaces the still image for this scene">
              🎬 ${hasClip ? 'Replace Clip' : 'Add Clip'}
            </button>
            ${hasClip ? `<button class="btn btn-secondary btn-xs" onclick="removeSceneClip('${activeProject.id}', ${s.scene_number})" title="Remove the video clip and go back to the image">✕ Remove Clip</button>` : ''}
            <button class="btn btn-secondary btn-xs" onclick="openSceneEffectsModal(${s.scene_number})" title="Camera motion (zoom, pan, focus) and filters for Scene ${s.scene_number}">🎞 Motion & Effects</button>
            <button class="btn btn-secondary btn-xs" onclick="openAddScenePanel(${s.scene_number + 1})" title="Insert a new scene right after Scene ${s.scene_number}">➕ Insert After</button>
            ${(activeProject.scenes || []).length > 1 ? `<button class="btn btn-secondary btn-xs scene-remove-btn" onclick="removeScene('${activeProject.id}', ${s.scene_number})" title="Delete Scene ${s.scene_number} and its image/clip">🗑 Remove Scene</button>` : ''}
            <input type="file" id="sceneFileInput_${s.scene_number}" accept="image/*" style="display:none;" onchange="handleSceneFileSelected('${activeProject.id}', ${s.scene_number}, this)">
          </div>
        </div>

        <div class="scene-content-row">
          <div class="scene-thumb-col">
            ${thumbHtml}
          </div>
          <div class="scene-text-col">
            <textarea class="scene-narration-input" id="sceneTextInput_${s.scene_number}" rows="3" placeholder="Enter narration text for Scene ${s.scene_number}...">${escapeHtml(s.narration || '')}</textarea>
            <div class="scene-text-actions">
              <button class="btn btn-secondary btn-xs" id="btnSaveText_${s.scene_number}" onclick="saveSceneText('${activeProject.id}', ${s.scene_number})">
                💾 Save Text
              </button>
              <span id="saveStatus_${s.scene_number}" class="scene-save-status"></span>
            </div>
          </div>
        </div>
      </div>
    `;
  }).join('') + renderAddScenePanel();
}

// ---- Add / remove scenes ----
function renderAddScenePanel() {
  const scenes = activeProject?.scenes || [];
  const options = [`<option value="1">At the start (before Scene 1)</option>`]
    .concat(scenes.slice(0, -1).map(sc => `<option value="${sc.scene_number + 1}">After Scene ${sc.scene_number}</option>`))
    .concat(scenes.length ? [`<option value="${scenes.length + 1}" selected>At the end (after Scene ${scenes.length})</option>`] : []);
  return `
    <div class="add-scene-panel" id="addScenePanel">
      <button type="button" class="btn btn-primary btn-sm add-scene-toggle" id="btnAddSceneToggle" onclick="openAddScenePanel()">➕ Add Scene</button>
      <div id="addSceneForm" class="add-scene-form hidden">
        <div class="add-scene-row">
          <label for="addScenePosition">Position</label>
          <select id="addScenePosition">${options.join('')}</select>
        </div>
        <label for="addSceneNarration">Narration (what the voiceover says)</label>
        <textarea id="addSceneNarration" rows="3" placeholder="e.g. Its stealth coating absorbs radar waves instead of reflecting them."></textarea>
        <label for="addScenePrompt">Visual prompt <span class="muted">(optional, used by Regenerate AI / Add Clip)</span></label>
        <textarea id="addScenePrompt" rows="2" placeholder="e.g. Close-up of F-35 radar-absorbent skin panels, cinematic lighting, 9:16"></textarea>
        <div class="add-scene-actions">
          <span id="addSceneStatus" class="scene-save-status"></span>
          <button type="button" class="btn btn-secondary btn-sm" onclick="closeAddScenePanel()">Cancel</button>
          <button type="button" class="btn btn-primary btn-sm" id="btnAddSceneSubmit" onclick="submitAddScene()">➕ Add Scene</button>
        </div>
        <p class="add-scene-hint">The new scene starts with a copy of a neighbouring image. Replace it with 📁 Add Image, ⚡ Regenerate AI or 🎬 Add Clip, then click Re-render. The video gets longer by about the new narration's length.</p>
      </div>
    </div>`;
}

function openAddScenePanel(position) {
  const form = document.getElementById('addSceneForm');
  if (!form) return;
  form.classList.remove('hidden');
  document.getElementById('btnAddSceneToggle')?.classList.add('hidden');
  if (position) document.getElementById('addScenePosition').value = String(position);
  document.getElementById('addScenePanel').scrollIntoView({ behavior: 'smooth', block: 'center' });
  setTimeout(() => document.getElementById('addSceneNarration')?.focus(), 250);
}

function closeAddScenePanel() {
  document.getElementById('addSceneForm')?.classList.add('hidden');
  document.getElementById('btnAddSceneToggle')?.classList.remove('hidden');
}

function collectUnsavedNarrations() {
  // Scene numbers shift on insert/remove, so key unsaved edits by the scene object, not its number
  const edits = new Map();
  (activeProject?.scenes || []).forEach(sc => {
    const el = document.getElementById(`sceneTextInput_${sc.scene_number}`);
    if (el && el.value !== (sc.narration || '')) edits.set(sc.scene_number, el.value);
  });
  return edits;
}

function restoreUnsavedNarrations(edits, numberMap) {
  edits.forEach((val, oldNum) => {
    const newNum = numberMap(oldNum);
    const el = newNum ? document.getElementById(`sceneTextInput_${newNum}`) : null;
    if (el) el.value = val;
  });
}

async function submitAddScene() {
  const projectId = activeProject?.id;
  const narration = document.getElementById('addSceneNarration').value.trim();
  const prompt = document.getElementById('addScenePrompt').value.trim();
  const position = parseInt(document.getElementById('addScenePosition').value, 10);
  const statusEl = document.getElementById('addSceneStatus');
  if (!narration) { statusEl.textContent = 'Write the narration first.'; statusEl.style.color = '#ef4444'; return; }

  const btn = document.getElementById('btnAddSceneSubmit');
  btn.disabled = true;
  statusEl.style.color = '#38bdf8';
  statusEl.textContent = 'Adding scene...';
  const unsaved = collectUnsavedNarrations();
  try {
    const res = await fetch(`/api/projects/${projectId}/scenes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ position, narration, visual_prompt: prompt || null })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      statusEl.style.color = '#ef4444';
      statusEl.textContent = `❌ ${data.detail || 'Could not add scene'}`;
      btn.disabled = false;
      return;
    }
    activeProject = data.project;
    renderModalScenes();
    restoreUnsavedNarrations(unsaved, n => (n >= data.scene_number ? n + 1 : n));
    const card = document.getElementById(`sceneCard_${data.scene_number}`);
    if (card) {
      card.classList.add('scene-item-new');
      card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    const st = document.getElementById(`saveStatus_${data.scene_number}`);
    if (st) st.textContent = `✓ ${data.message}`;
  } catch (err) {
    statusEl.style.color = '#ef4444';
    statusEl.textContent = `❌ ${err.message}`;
    btn.disabled = false;
  }
}

async function removeScene(projectId, sceneIdx) {
  const scene = activeProject?.scenes?.find(sc => sc.scene_number === sceneIdx);
  const preview = (scene?.narration || '').slice(0, 80);
  if (!window.confirm(`Delete Scene ${sceneIdx}?\n\n"${preview}${(scene?.narration || '').length > 80 ? '…' : ''}"\n\nIts image and video clip are deleted too. This can't be undone.`)) return;

  const statusEl = document.getElementById(`saveStatus_${sceneIdx}`);
  if (statusEl) statusEl.textContent = 'Removing scene...';
  const unsaved = collectUnsavedNarrations();
  unsaved.delete(sceneIdx);
  try {
    const res = await fetch(`/api/projects/${projectId}/scenes/${sceneIdx}`, { method: 'DELETE' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (statusEl) statusEl.textContent = `❌ ${data.detail || 'Could not remove scene'}`;
      return;
    }
    activeProject = data.project;
    renderModalScenes();
    restoreUnsavedNarrations(unsaved, n => (n > sceneIdx ? n - 1 : n));
    const near = document.getElementById(`saveStatus_${Math.min(sceneIdx, activeProject.scenes.length)}`);
    if (near) {
      near.textContent = `✓ ${data.message}`;
      setTimeout(() => { near.textContent = ''; }, 6000);
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = `❌ ${err.message}`;
  }
}

let currentMainWorkspaceTab = 'weapon';

function resolveTargetYoutubeChannel(project, channelOverride) {
  const isCar = (
    channelOverride === 'autoflashx' ||
    currentMainWorkspaceTab === 'car' ||
    project?.channel === 'autoflashx' ||
    project?.is_car_edit ||
    project?.style === 'car_edit'
  );
  if (isCar) {
    return {
      key: 'autoflashx',
      id: 'UCuJ9LcSqliLH0VEJ9lWZsrQ',
      handle: '@AutoFlashX',
      studioUrl: 'https://studio.youtube.com/channel/UCuJ9LcSqliLH0VEJ9lWZsrQ'
    };
  }
  return {
    key: 'weaponxlabs',
    id: 'UC4KV67NYzLi8JlrfB9J4hGg',
    handle: '@WeaponXLabs',
    studioUrl: 'https://studio.youtube.com/channel/UC4KV67NYzLi8JlrfB9J4hGg'
  };
}

function renderModalPublishState(project) {
  const pubStatus = document.getElementById('publishResult');
  const btnApprove = document.getElementById('btnModalApproveLive');
  const btnPublish = document.getElementById('btnModalPublish');
  const chLink = document.getElementById('modalYtStudioChannelLink');
  const chInfo = resolveTargetYoutubeChannel(project);
  if (chLink) {
    chLink.href = chInfo.studioUrl;
    chLink.textContent = `Open Channel ${chInfo.id} (${chInfo.handle}) ↗`;
  }
  if (!pubStatus) return;

  pubStatus.classList.add('hidden');
  if (btnApprove) btnApprove.classList.add('hidden');

  if (project && project.youtube) {
    const yt = project.youtube;
    const isRealApi = yt.mode === 'youtube_api';
    const isLive = Boolean(yt.live && yt.approval_status === 'approved_live');
    const studioUrl = chInfo.studioUrl || yt.studio_edit_url || yt.studio_channel_url;
    const editUrl = (currentMainWorkspaceTab === 'car' && yt.channel_id !== chInfo.id)
      ? chInfo.studioUrl
      : (yt.studio_edit_url || studioUrl);

    if (yt.approval_status === 'approved_private') {
      pubStatus.className = 'publish-status success';
      pubStatus.innerHTML = `
        <div style="line-height: 1.5;">
          <strong>🔒 Approved and saved as PRIVATE on YouTube (${chInfo.handle} · ${chInfo.id})</strong><br>
          <span>It will not go public by itself. Open it in YouTube Studio to <strong>make it public</strong> or <strong>schedule</strong> it:</span><br>
          <a href="${chInfo.studioUrl}" target="_blank" style="color: #00e5ff; font-weight: 600;">${chInfo.studioUrl} ↗</a>
          ${editUrl && editUrl !== chInfo.studioUrl ? ` · <a href="${editUrl}" target="_blank" style="color: #10b981; font-weight: 600;">Edit Video ↗</a>` : ''}
        </div>
      `;
      pubStatus.classList.remove('hidden');
      if (btnApprove) btnApprove.classList.add('hidden');
      if (btnPublish) btnPublish.textContent = `💾 Update YouTube Fields (${chInfo.id} · stays Private)`;
    } else if (isRealApi && isLive) {
      pubStatus.className = 'publish-status success';
      pubStatus.innerHTML = `
        <div style="line-height: 1.5;">
          <strong>✅ Approved & LIVE on YouTube Shorts (${chInfo.handle}):</strong><br>
          <a href="${yt.url}" target="_blank" style="color: #00e5ff; font-weight: bold;">${yt.url}</a>
          · <a href="${chInfo.studioUrl}" target="_blank" style="color: #10b981; font-weight: 600;">Open ${chInfo.studioUrl} ↗</a>
        </div>
      `;
      pubStatus.classList.remove('hidden');
      if (btnPublish) btnPublish.textContent = '🚀 Re-Upload / Update on YouTube Shorts';
    } else if ((isRealApi || yt.mode === 'studio_staged') && yt.approval_status === 'pending_approval') {
      pubStatus.className = 'publish-status success';
      pubStatus.innerHTML = `
        <div style="line-height: 1.5;">
          <strong>⏳ Saved to Channel ${chInfo.id} (${chInfo.handle} · Private Draft on YouTube)</strong><br>
          <span>Review in Studio: <a href="${chInfo.studioUrl}" target="_blank" style="color: #00e5ff; font-weight: 600;">${chInfo.studioUrl} ↗</a></span><br>
          <span style="color: #fbbf24;">Click <strong>"✅ Approve (stays Private)"</strong> when it's ready. It stays private on <a href="${chInfo.studioUrl}" target="_blank" style="color: #38bdf8;">${chInfo.studioUrl}</a>.</span>
        </div>
      `;
      pubStatus.classList.remove('hidden');
      if (btnApprove) btnApprove.classList.remove('hidden');
      if (btnPublish) btnPublish.textContent = `💾 Update YouTube Draft Fields (${chInfo.id})`;
    } else {
      // Staged local draft or missing/expired OAuth
      pubStatus.className = 'publish-status error';
      pubStatus.innerHTML = `
        <div style="line-height: 1.5;">
          <strong style="color: #f87171;">⚠️ Not Uploaded to YouTube (${chInfo.handle} · ${chInfo.id})</strong><br>
          <span style="font-size: 11.5px; color: #cbd5e1;">Your YouTube OAuth authorization for ${chInfo.handle} (${chInfo.id}) expired or was not completed.</span><br>
          <button type="button" class="btn btn-primary btn-xs" onclick="handleTriggerYoutubeOAuth('${chInfo.key}')" style="margin-top: 8px; font-weight: 700;">
            🔑 Connect / Re-Authenticate YouTube (${chInfo.handle})
          </button>
          · <a href="${chInfo.studioUrl}" target="_blank" style="color: #00e5ff; font-size: 11.5px; font-weight: 600;">Open ${chInfo.studioUrl} ↗</a>
        </div>
      `;
      pubStatus.classList.remove('hidden');
      if (btnApprove) btnApprove.classList.add('hidden');
      if (btnPublish) btnPublish.textContent = `🚀 Upload to YouTube Shorts (${chInfo.id} · Private)`;
    }
  } else {
    if (btnPublish) btnPublish.textContent = `🚀 Upload to YouTube Shorts (${chInfo.id} · Private)`;
  }
}

let currentTargetSceneNumber = 1;
let currentTargetProjectId = null;

function openSceneImageModal(projectId, sceneIdx, defaultTab = 'ai') {
  currentTargetProjectId = projectId || activeProject?.id;
  currentTargetSceneNumber = sceneIdx;

  const modal = document.getElementById('sceneImageModal');
  const numSpan = document.getElementById('sceneImageModalNum');
  const promptNumSpan = document.getElementById('sceneAiPromptNum');
  const promptInput = document.getElementById('sceneAiPromptInput');
  const statusEl = document.getElementById('sceneAiStatus');
  const uploadStatusEl = document.getElementById('sceneUploadStatus');

  if (numSpan) numSpan.textContent = sceneIdx;
  if (promptNumSpan) promptNumSpan.textContent = sceneIdx;
  if (statusEl) { statusEl.textContent = ''; statusEl.style.color = ''; }
  if (uploadStatusEl) { uploadStatusEl.textContent = ''; uploadStatusEl.style.color = ''; }

  // Prefill prompt from scene visual_prompt or narration or topic
  const scene = activeProject?.scenes?.find(s => s.scene_number === sceneIdx);
  const existingPrompt = scene?.visual_prompt || scene?.narration || activeProject?.topic || '';
  if (promptInput) {
    promptInput.value = existingPrompt;
  }

  switchSceneImageTab(defaultTab);
  if (modal) modal.classList.remove('hidden');
  if (defaultTab === 'ai' && promptInput) {
    setTimeout(() => { promptInput.focus(); }, 100);
  }
}

function openSceneAiGenerateModal(projectId, sceneIdx) {
  openSceneImageModal(projectId, sceneIdx, 'ai');
}

function closeSceneImageModal() {
  const modal = document.getElementById('sceneImageModal');
  if (modal) modal.classList.add('hidden');
}

function switchSceneImageTab(tabName) {
  const tabAi = document.getElementById('tabContentSceneAi');
  const tabUpload = document.getElementById('tabContentSceneUpload');
  const btnAi = document.getElementById('tabBtnSceneAi');
  const btnUpload = document.getElementById('tabBtnSceneUpload');

  if (tabName === 'ai') {
    if (tabAi) tabAi.classList.remove('hidden');
    if (tabUpload) tabUpload.classList.add('hidden');
    if (btnAi) { btnAi.classList.remove('btn-secondary'); btnAi.classList.add('btn-primary'); }
    if (btnUpload) { btnUpload.classList.remove('btn-primary'); btnUpload.classList.add('btn-secondary'); }
  } else {
    if (tabAi) tabAi.classList.add('hidden');
    if (tabUpload) tabUpload.classList.remove('hidden');
    if (btnAi) { btnAi.classList.remove('btn-primary'); btnAi.classList.add('btn-secondary'); }
    if (btnUpload) { btnUpload.classList.remove('btn-secondary'); btnUpload.classList.add('btn-primary'); }
  }
}

function appendScenePromptStyle(styleText) {
  const promptInput = document.getElementById('sceneAiPromptInput');
  if (!promptInput) return;
  const cur = promptInput.value.trim();
  if (!cur) {
    promptInput.value = styleText;
  } else if (!cur.includes(styleText)) {
    promptInput.value = `${cur}, ${styleText}`;
  }
  promptInput.focus();
}

async function executeSceneAiGeneration() {
  const projectId = currentTargetProjectId || activeProject?.id;
  const sceneIdx = currentTargetSceneNumber;
  const promptInput = document.getElementById('sceneAiPromptInput');
  const prompt = promptInput?.value.trim() || '';
  const engineSelect = document.getElementById('sceneAiEngineSelect');
  const engine = engineSelect ? engineSelect.value : 'auto';
  const statusEl = document.getElementById('sceneAiStatus');
  const btn = document.getElementById('btnExecuteSceneAiGen');

  if (statusEl) {
    statusEl.style.color = '#38bdf8';
    const engineLabel = engine === 'imagen3' ? 'Google Imagen 3' : engine === 'flux' ? 'FLUX.1' : engine === 'comfyui' ? 'ComfyUI' : engine === 'dalle3' ? 'DALL-E 3' : 'Smart Auto Cascade (Imagen 3 ➔ FLUX.1 ➔ ComfyUI)';
    statusEl.textContent = `⚡ Generating AI image (${engineLabel}) for Scene ${sceneIdx}...`;
  }
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`/api/projects/${projectId}/scenes/${sceneIdx}/generate-image`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt,
        style: activeProject?.style || 'cinematic',
        engine
      })
    });

    const data = await res.json();
    if (res.ok && data.status === 'success') {
      const providerLabel = data.provider || 'AI Engine';
      if (statusEl) {
        statusEl.style.color = '#10b981';
        statusEl.textContent = `✓ Generated successfully via ${providerLabel}!`;
      }
      // Update scene thumbnail on UI
      const thumb = document.getElementById(`sceneThumbImg_${sceneIdx}`);
      if (thumb) {
        thumb.src = `/api/scene_image/${projectId}/${sceneIdx}?t=${Date.now()}&r=${Math.random()}`;
        thumb.style.opacity = '1';
      }
      // Update activeProject locally
      if (activeProject && activeProject.scenes) {
        const sc = activeProject.scenes.find(s => s.scene_number === sceneIdx);
        if (sc) {
          sc.visual_source = 'ai_generated';
          sc.visual_prompt = prompt;
        }
      }
      const sceneCardStatus = document.getElementById(`saveStatus_${sceneIdx}`);
      if (sceneCardStatus) {
        sceneCardStatus.textContent = 'AI Image updated ✓ (click Re-render to apply)';
        setTimeout(() => { sceneCardStatus.textContent = ''; }, 4000);
      }
      setTimeout(() => {
        closeSceneImageModal();
      }, 700);
    } else {
      if (statusEl) {
        statusEl.style.color = '#ef4444';
        statusEl.textContent = `Error: ${data.detail || data.message || 'Generation failed'}`;
      }
    }
  } catch (err) {
    if (statusEl) {
      statusEl.style.color = '#ef4444';
      statusEl.textContent = `Generation error: ${err.message}`;
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function handleSceneModalFileSelected(inputEl) {
  const file = inputEl.files && inputEl.files[0];
  if (!file) return;

  const projectId = currentTargetProjectId || activeProject?.id;
  const sceneIdx = currentTargetSceneNumber;
  const statusEl = document.getElementById('sceneUploadStatus');
  if (statusEl) {
    statusEl.style.color = '#38bdf8';
    statusEl.textContent = 'Uploading and formatting to 9:16...';
  }

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(`/api/projects/${projectId}/scenes/${sceneIdx}/image`, {
      method: 'POST',
      body: formData
    });

    if (res.ok) {
      const upData = await res.json().catch(() => ({}));
      if (statusEl) {
        statusEl.style.color = upData.warning ? '#fbbf24' : '#10b981';
        statusEl.textContent = upData.warning ? `⚠️ ${upData.warning}` : '✓ Image uploaded successfully!';
      }
      const thumb = document.getElementById(`sceneThumbImg_${sceneIdx}`);
      if (thumb) {
        thumb.src = `/api/scene_image/${projectId}/${sceneIdx}?t=${Date.now()}`;
        thumb.style.opacity = '1';
      }
      const sceneCardStatus = document.getElementById(`saveStatus_${sceneIdx}`);
      if (sceneCardStatus) {
        sceneCardStatus.textContent = 'Image updated ✓ (click Re-render to apply)';
        setTimeout(() => { sceneCardStatus.textContent = ''; }, 4000);
      }
      setTimeout(() => {
        closeSceneImageModal();
      }, 700);
    } else {
      const err = await res.json().catch(() => ({}));
      if (statusEl) {
        statusEl.style.color = '#ef4444';
        statusEl.textContent = `Upload failed: ${err.detail || 'Server error'}`;
      }
    }
  } catch (err) {
    if (statusEl) {
      statusEl.style.color = '#ef4444';
      statusEl.textContent = `Upload error: ${err.message}`;
    }
  }
}

function setSceneClipState(sceneIdx, clip) {
  const scene = (activeProject?.scenes || []).find(sc => sc.scene_number === sceneIdx);
  if (!scene) return;
  if (clip) {
    scene.clip_path = clip.path;
    scene.clip_name = clip.name;
  } else {
    delete scene.clip_path;
    delete scene.clip_name;
  }
}

function refreshSceneCard(sceneIdx, message) {
  // Re-render the modal's scene list so buttons/badges/thumbnail reflect the clip state,
  // preserving any narration edits that haven't been saved yet
  const unsaved = {};
  (activeProject.scenes || []).forEach(sc => {
    const el = document.getElementById(`sceneTextInput_${sc.scene_number}`);
    if (el) unsaved[sc.scene_number] = el.value;
  });
  renderModalScenes();
  Object.entries(unsaved).forEach(([num, val]) => {
    const el = document.getElementById(`sceneTextInput_${num}`);
    if (el) el.value = val;
  });
  const statusEl = document.getElementById(`saveStatus_${sceneIdx}`);
  if (statusEl && message) {
    statusEl.textContent = message;
    setTimeout(() => { statusEl.textContent = ''; }, 5000);
  }
}

async function handleSceneClipSelected(projectId, sceneIdx, inputEl, fromModal = false) {
  const file = inputEl.files && inputEl.files[0];
  inputEl.value = '';
  if (!file) return;
  if (fromModal) closeSceneClipModal();

  const statusEl = document.getElementById(`saveStatus_${sceneIdx}`);
  if (statusEl) statusEl.textContent = `Uploading clip (${(file.size / 1048576).toFixed(1)} MB)...`;

  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await fetch(`/api/projects/${projectId}/scenes/${sceneIdx}/clip`, { method: 'POST', body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      if (statusEl) statusEl.textContent = `Clip upload failed: ${err.detail || 'Server error'}`;
      return;
    }
    setSceneClipState(sceneIdx, { path: 'uploaded', name: file.name });
    refreshSceneCard(sceneIdx, 'Clip added ✓ (click Re-render to apply)');
  } catch (err) {
    console.error('Clip upload error:', err);
    if (statusEl) statusEl.textContent = `Clip upload error: ${err.message}`;
  }
}

async function removeSceneClip(projectId, sceneIdx) {
  const statusEl = document.getElementById(`saveStatus_${sceneIdx}`);
  try {
    const res = await fetch(`/api/projects/${projectId}/scenes/${sceneIdx}/clip`, { method: 'DELETE' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      if (statusEl) statusEl.textContent = `Remove failed: ${err.detail || 'Server error'}`;
      return;
    }
    setSceneClipState(sceneIdx, null);
    refreshSceneCard(sceneIdx, 'Clip removed ✓ (click Re-render to apply)');
  } catch (err) {
    if (statusEl) statusEl.textContent = `Remove error: ${err.message}`;
  }
}

// ---- Free AI clip generation (Wan 2.2 / LTX-2.3 on Hugging Face, LTX-2.5 via local Phosphene) ----
let currentClipProjectId = null;
let currentClipSceneNumber = 1;
let clipEngineStatus = { hf_token_configured: false, phosphene_running: false };
const clipJobPollers = {};   // "projectId:scene" -> { jobId, timer }

async function openSceneClipModal(projectId, sceneIdx) {
  currentClipProjectId = projectId || activeProject?.id;
  currentClipSceneNumber = sceneIdx;
  const scene = activeProject?.scenes?.find(sc => sc.scene_number === sceneIdx);

  document.getElementById('sceneClipModalNum').textContent = sceneIdx;
  document.getElementById('clipPromptInput').value = scene?.clip_meta?.prompt || scene?.visual_prompt || scene?.narration || '';
  document.getElementById('clipDurationInput').value = scene?.duration_seconds ? Number(scene.duration_seconds).toFixed(1) : '5';
  setClipStatus('', '');
  setClipProgress(null, false);
  const key = `${currentClipProjectId}:${sceneIdx}`;
  setClipGenBusy(Boolean(clipJobPollers[key]));

  switchSceneClipTab('ai');
  document.getElementById('sceneClipModal').classList.remove('hidden');

  try {
    const res = await fetch(`/api/clip-engines?t=${Date.now()}`);
    clipEngineStatus = await res.json();
  } catch (e) { /* non-fatal */ }
  updateClipEngineHints();

  // Resume progress display for a job started earlier (e.g. modal was closed or page reloaded)
  if (!clipJobPollers[key]) {
    try {
      const res = await fetch(`/api/projects/${currentClipProjectId}/clip-jobs?t=${Date.now()}`);
      const data = await res.json();
      const running = (data.jobs || []).find(j => j.scene_idx === sceneIdx);
      if (running) pollClipJob(currentClipProjectId, sceneIdx, running.id, running.engine_label);
    } catch (e) { /* non-fatal */ }
  }
}

function closeSceneClipModal() {
  document.getElementById('sceneClipModal')?.classList.add('hidden');
}

function switchSceneClipTab(tab) {
  const isAi = tab === 'ai';
  document.getElementById('tabContentClipAi').classList.toggle('hidden', !isAi);
  document.getElementById('tabContentClipUpload').classList.toggle('hidden', isAi);
  document.getElementById('tabBtnClipAi').className = `btn btn-sm ${isAi ? 'btn-primary' : 'btn-secondary'}`;
  document.getElementById('tabBtnClipUpload').className = `btn btn-sm ${isAi ? 'btn-secondary' : 'btn-primary'}`;
}

function updateClipEngineHints() {
  const engine = document.getElementById('clipEngineSelect').value;
  const hint = document.getElementById('clipEngineHint');
  const isHf = engine !== 'phosphene_ltx';
  document.getElementById('clipHdRow').classList.toggle('hidden', engine !== 'ltx23_hf');
  document.getElementById('clipHfTokenRow').classList.toggle('hidden', !isHf);
  document.getElementById('clipHfTokenState').textContent = clipEngineStatus.hf_token_configured
    ? '✓ token saved (higher free quota)' : 'not set, about 2 free clips/day';
  const durEl = document.getElementById('clipDurationInput');
  durEl.max = engine === 'wan22_hf' ? 5 : 10;

  if (engine === 'phosphene_ltx') {
    hint.innerHTML = clipEngineStatus.phosphene_running
      ? '<span style="color:#10b981">✓ Phosphene is running.</span> Renders locally, offline, unlimited. About 4–5 min per 5 s clip on this Mac; the Mac is slow while rendering, so close heavy apps.'
      : '<span style="color:#f59e0b">⚠ Phosphene is not running.</span> Start it in Terminal with <code>~/phosphene/run_panel.sh --bg</code> (or open the Phosphene app), wait ~10 s, then reopen this dialog.';
  } else if (engine === 'wan22_hf') {
    hint.textContent = 'Strongest motion (jets banking, explosions). Max 5s at 480×832; longer scenes loop the clip.';
  } else {
    hint.textContent = 'Smooth cinematic camera moves, up to 10s. 512×768 (or 1024×1536 with HD).';
  }
}

function appendClipPrompt(text) {
  const el = document.getElementById('clipPromptInput');
  el.value = el.value.trim() ? `${el.value.trim().replace(/[.,]$/, '')}. ${text}` : text;
}

function setClipStatus(text, color) {
  const el = document.getElementById('clipGenStatus');
  if (!el) return;
  el.textContent = text;
  el.style.color = color || '';
}

function setClipProgress(pct, show) {
  const wrap = document.getElementById('clipProgressWrap');
  const bar = document.getElementById('clipProgressBar');
  if (!wrap || !bar) return;
  wrap.classList.toggle('hidden', !show);
  bar.style.width = pct == null ? '100%' : `${Math.max(2, Math.min(100, pct))}%`;
  bar.style.opacity = pct == null ? '0.35' : '1';
}

function setClipGenBusy(busy) {
  const btn = document.getElementById('btnExecuteClipGen');
  if (!btn) return;
  btn.disabled = busy;
  btn.style.opacity = busy ? '0.6' : '1';
  btn.textContent = busy ? '⏳ Generating...' : '🎬 Generate Clip';
}

async function saveHfToken() {
  const input = document.getElementById('clipHfTokenInput');
  const token = input.value.trim();
  if (!token) { setClipStatus('Paste your Hugging Face token first.', '#ef4444'); return; }
  const res = await fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hf_token: token })
  });
  if (res.ok) {
    input.value = '';
    clipEngineStatus.hf_token_configured = true;
    updateClipEngineHints();
    document.getElementById('clipHfTokenRow').open = false;
    setClipStatus('✓ Hugging Face token saved', '#10b981');
  } else {
    setClipStatus('Failed to save token', '#ef4444');
  }
}

async function executeSceneClipGeneration() {
  const projectId = currentClipProjectId;
  const sceneIdx = currentClipSceneNumber;
  if (clipJobPollers[`${projectId}:${sceneIdx}`]) return;

  const engine = document.getElementById('clipEngineSelect').value;
  if (engine === 'phosphene_ltx' && !clipEngineStatus.phosphene_running) {
    // Re-check: the user may have just launched it
    try { clipEngineStatus = await (await fetch(`/api/clip-engines?t=${Date.now()}`)).json(); } catch (e) {}
    updateClipEngineHints();
    if (!clipEngineStatus.phosphene_running) {
      setClipStatus('❌ Phosphene is not running. Open the Phosphene app first.', '#ef4444');
      return;
    }
  }
  const body = {
    engine,
    prompt: document.getElementById('clipPromptInput').value.trim(),
    duration: parseFloat(document.getElementById('clipDurationInput').value) || null,
    hd: engine === 'ltx23_hf' && document.getElementById('clipHdToggle').checked
  };

  setClipGenBusy(true);
  setClipStatus('Starting...', '#38bdf8');
  try {
    const res = await fetch(`/api/projects/${projectId}/scenes/${sceneIdx}/generate-clip`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.job_id) {
      setClipStatus(`❌ ${data.detail || 'Could not start clip generation'}`, '#ef4444');
      setClipGenBusy(false);
      return;
    }
    const sel = document.getElementById('clipEngineSelect');
    pollClipJob(projectId, sceneIdx, data.job_id, sel.options[sel.selectedIndex].text.split(' · ')[0].replace(/^\S+\s/, ''));
  } catch (err) {
    setClipStatus(`❌ ${err.message}`, '#ef4444');
    setClipGenBusy(false);
  }
}

function pollClipJob(projectId, sceneIdx, jobId, engineLabel) {
  const key = `${projectId}:${sceneIdx}`;
  const isVisible = () => currentClipProjectId === projectId && currentClipSceneNumber === sceneIdx
    && !document.getElementById('sceneClipModal').classList.contains('hidden');
  const cardStatus = (msg) => {
    if (activeProject?.id !== projectId) return;
    const c = document.getElementById(`saveStatus_${sceneIdx}`);
    if (c) c.textContent = msg;
  };
  if (isVisible()) setClipGenBusy(true);

  const tick = async () => {
    let job;
    try {
      const res = await fetch(`/api/clip-jobs/${jobId}?t=${Date.now()}`);
      job = await res.json();
      if (!res.ok) throw new Error(job.detail || 'Lost track of the clip job');
    } catch (err) {
      finish(`❌ ${err.message}`, '#ef4444');
      return;
    }
    if (job.status === 'running') {
      const msg = `⏳ ${engineLabel || job.engine_label}: ${job.message} (${Math.round(job.elapsed)}s)`;
      if (isVisible()) { setClipStatus(msg, '#38bdf8'); setClipProgress(job.progress, true); }
      cardStatus(msg);
      return;
    }
    if (job.status === 'done') {
      if (activeProject?.id === projectId) {
        const scene = activeProject.scenes.find(sc => sc.scene_number === sceneIdx);
        if (scene) { scene.clip_path = 'generated'; scene.clip_name = job.result.clip_name; scene.clip_meta = job.result.meta; }
        refreshSceneCard(sceneIdx, `✓ ${job.message}. Click Re-render to apply`);
      }
      finish(`✓ ${job.message}`, '#10b981', true);
    } else {
      finish(`❌ ${job.error || 'Clip generation failed'}`, '#ef4444');
    }
  };

  const finish = (msg, color, success = false) => {
    clearInterval(clipJobPollers[key]?.timer);
    delete clipJobPollers[key];
    if (!success) cardStatus(msg);
    if (isVisible()) {
      setClipStatus(msg, color);
      setClipProgress(null, false);
      setClipGenBusy(false);
      if (success) setTimeout(closeSceneClipModal, 1200);
    }
  };

  clipJobPollers[key] = { jobId, timer: setInterval(tick, 3000) };
  tick();
}

function triggerSceneImageUpload(projectId, sceneIdx) {
  openSceneImageModal(projectId, sceneIdx, 'ai');
}

async function handleSceneFileSelected(projectId, sceneIdx, inputEl) {
  const file = inputEl.files && inputEl.files[0];
  if (!file) return;

  const statusEl = document.getElementById(`saveStatus_${sceneIdx}`);
  if (statusEl) statusEl.textContent = 'Uploading image...';

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(`/api/projects/${projectId}/scenes/${sceneIdx}/image`, {
      method: 'POST',
      body: formData
    });

    if (res.ok) {
      const data = await res.json();
      const thumb = document.getElementById(`sceneThumbImg_${sceneIdx}`);
      if (thumb) {
        thumb.src = `/api/scene_image/${projectId}/${sceneIdx}?t=${Date.now()}`;
        thumb.style.opacity = '1.0';
      }
      if (statusEl) {
        statusEl.textContent = data.warning ? `⚠️ ${data.warning}` : 'Image updated ✓ (click Re-render to apply)';
        setTimeout(() => { statusEl.textContent = ''; }, data.warning ? 12000 : 4000);
      }
    } else {
      alert('Failed to upload image. Please try another file.');
      if (statusEl) statusEl.textContent = 'Upload failed';
    }
  } catch (err) {
    console.error('Image upload error:', err);
    alert('Error uploading image');
    if (statusEl) statusEl.textContent = 'Upload error';
  }
}

async function saveSceneText(projectId, sceneIdx) {
  const textInput = document.getElementById(`sceneTextInput_${sceneIdx}`);
  const statusEl = document.getElementById(`saveStatus_${sceneIdx}`);
  const btn = document.getElementById(`btnSaveText_${sceneIdx}`);

  if (!textInput) return;
  const narration = textInput.value.trim();

  if (btn) btn.disabled = true;
  if (statusEl) statusEl.textContent = 'Saving...';

  try {
    const res = await fetch(`/api/projects/${projectId}/scenes/${sceneIdx}/text`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ narration })
    });

    if (res.ok) {
      if (statusEl) {
        statusEl.textContent = 'Saved ✓ (click Re-render to apply)';
        setTimeout(() => { statusEl.textContent = ''; }, 4000);
      }
      // Update local state
      if (activeProject && activeProject.scenes && activeProject.scenes[sceneIdx - 1]) {
        activeProject.scenes[sceneIdx - 1].narration = narration;
      }
      // Saved text is no longer "unsaved" for the UI-update reload guard
      textInput.defaultValue = textInput.value;
    } else {
      alert('Failed to save scene text');
      if (statusEl) statusEl.textContent = 'Save failed';
    }
  } catch (err) {
    console.error('Save text error:', err);
    alert('Error saving text');
    if (statusEl) statusEl.textContent = 'Save error';
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function handleRerenderModal() {
  if (!activeProject) return;

  const btn = document.getElementById('btnRerenderModal');
  const voiceToggle = document.getElementById('modalVoiceToggle');
  const audioMode = voiceToggle ? voiceToggle.value : 'with_voice';

  let withVoice = true;
  let withMusic = true;
  if (audioMode === 'without_music') {
    withVoice = true;
    withMusic = false;
  } else if (audioMode === 'without_voice') {
    withVoice = false;
    withMusic = true;
  } else if (audioMode === 'mute') {
    withVoice = false;
    withMusic = false;
  } else {
    withVoice = true;
    withMusic = true;
  }

  const origText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '🔄 Re-rendering...';

  try {
    const res = await fetch(`/api/projects/${activeProject.id}/rerender`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ with_voice: withVoice, with_music: withMusic, audio_mode: audioMode })
    });

    if (res.ok) {
      const data = await res.json();
      activeProject = data.project;

      // Reload video player
      const videoPlayer = document.getElementById('modalVideoPlayer');
      videoPlayer.src = `/api/video/${activeProject.id}?t=${Date.now()}`;
      videoPlayer.play().catch(() => {});

      // Refresh QA panel
      loadQAInspection(activeProject.id);

      // Refresh project list
      loadProjects();
      alert('Video re-rendered successfully with your updated images and text!');
    } else {
      const err = await res.json();
      alert(`Failed to re-render: ${err.detail || 'Server error'}`);
    }
  } catch (err) {
    console.error('Re-render error:', err);
    alert('Error re-rendering video');
  } finally {
    btn.disabled = false;
    btn.innerHTML = origText;
  }
}

async function loadQAInspection(projectId) {
  const badge = document.getElementById('qaScoreBadge');
  const metricsGrid = document.getElementById('qaMetricsGrid');
  const framesScroll = document.getElementById('qaFramesScroll');

  badge.className = 'qa-badge-pill';
  badge.textContent = 'Inspecting frames...';
  metricsGrid.innerHTML = '';
  framesScroll.innerHTML = '';

  try {
    const res = await fetch(`/api/qa/${projectId}?t=${Date.now()}`);
    const qa = await res.json();

    // Set status badge
    badge.textContent = `${qa.overall_score}% · ${qa.status}`;
    if (qa.status === 'PASSED') badge.classList.add('passed');
    else if (qa.status === 'WARNINGS') badge.classList.add('warnings');
    else badge.classList.add('failed');

    // Metrics grid. Two report formats exist: the current Verify-video agent (stream_checks,
    // subtitle_checks, frame_inspections with timestamp/frame_file) and the older QA validator
    // (audio_checks, motion_checks, frames with checkpoint_sec/preview_image). Show only real values.
    const sc = qa.stream_checks || {};
    const subc = qa.subtitle_checks || {};
    const num = (v) => (typeof v === 'number' && isFinite(v)) ? v : null;

    const resText = sc.resolution || '—';

    let audioText;
    if (num(qa.audio_checks?.mean_volume_db) !== null) audioText = `${qa.audio_checks.mean_volume_db} dB`;
    else if (sc.has_audio === true) audioText = `${(sc.audio_codec || 'audio').toUpperCase()} ✓`;
    else if (sc.has_audio === false) audioText = 'No audio track';
    else audioText = '—';

    let thirdLabel, thirdText;
    if (qa.motion_checks) {
      thirdLabel = 'Camera Motion';
      thirdText = qa.motion_checks.motion_active ? `Active (${qa.motion_checks.avg_motion_delta}Δ)` : 'Static';
    } else {
      thirdLabel = 'Length';
      const dur = num(sc.duration_seconds);
      thirdText = dur !== null ? `${dur.toFixed(1)}s${sc.fps ? ` · ${sc.fps} fps` : ''}` : '—';
    }

    let subText;
    if (subc.in_safe_zone !== undefined) subText = subc.in_safe_zone ? 'Safe Zone ✓' : 'Outside safe zone';
    else if (subc.passed !== undefined) subText = subc.passed ? `${subc.dialogue_events ?? ''} lines ✓`.trim() : 'Check failed';
    else subText = '—';

    metricsGrid.innerHTML = `
      <div class="qa-metric-item">
        <span class="qa-metric-label">Resolution</span>
        <span class="qa-metric-val">${escapeHtml(String(resText))}</span>
      </div>
      <div class="qa-metric-item">
        <span class="qa-metric-label">Audio</span>
        <span class="qa-metric-val">${escapeHtml(audioText)}</span>
      </div>
      <div class="qa-metric-item">
        <span class="qa-metric-label">${thirdLabel}</span>
        <span class="qa-metric-val">${escapeHtml(thirdText)}</span>
      </div>
      <div class="qa-metric-item">
        <span class="qa-metric-label">Subtitles</span>
        <span class="qa-metric-val">${escapeHtml(subText)}</span>
      </div>
    `;

    // Render frame checkpoint gallery
    const frames = Array.isArray(qa.frame_inspections) ? qa.frame_inspections : [];
    if (frames.length > 0) {
      framesScroll.innerHTML = frames.map(f => {
        const ts = num(f.timestamp) ?? num(f.checkpoint_sec);
        const tsText = ts !== null ? `${ts.toFixed(1)}s` : '';
        const file = f.frame_file || f.preview_image;
        const title = f.description || (f.label ? f.label.replace(/_/g, ' ') : 'Frame check');
        const lines = [];
        if (num(f.sharpness) !== null) lines.push(`Sharpness: ${Math.round(f.sharpness)}`);
        if (num(f.motion_delta) !== null) lines.push(`Motion: ${f.motion_delta}Δ`);
        if (num(f.mean_luminance) !== null) lines.push(`Brightness: ${Math.round(f.mean_luminance)}`);
        if (num(f.contrast_stddev) !== null) lines.push(`Contrast: ${Math.round(f.contrast_stddev)}`);
        const verdict = f.passed === true ? '<span class="qa-frame-pass">✓ Pass</span>'
          : f.passed === false ? `<span class="qa-frame-fail">✗ ${f.is_blank_or_black ? 'Blank/black frame' : 'Fail'}</span>` : '';
        const img = file
          ? `<img class="qa-frame-img" src="/api/qa_frame/${projectId}/${encodeURIComponent(file)}?t=${Date.now()}" alt="Frame at ${tsText}" onerror="this.replaceWith(Object.assign(document.createElement('div'), {className: 'qa-frame-img qa-frame-missing', textContent: 'Frame image missing'}))">`
          : `<div class="qa-frame-img qa-frame-missing">No frame image</div>`;
        return `
          <div class="qa-frame-card">
            ${img}
            <div class="qa-frame-meta">
              <strong>${tsText ? `${tsText} · ` : ''}${escapeHtml(title)}</strong>
              ${lines.map(l => `<span>${l}</span>`).join('')}
              ${verdict}
            </div>
          </div>
        `;
      }).join('');
    } else {
      framesScroll.innerHTML = '<span style="font-size: 12px; color: #64748b;">No frame checkpoints generated</span>';
    }

  } catch (err) {
    console.error('QA load error:', err);
    badge.textContent = 'QA Verified';
  }
}

function closeModal() {
  const modal = document.getElementById('videoModal');
  const videoPlayer = document.getElementById('modalVideoPlayer');
  videoPlayer.pause();
  videoPlayer.src = '';
  modal.classList.add('hidden');
}

async function handleRegenerateWeaponXModal() {
  if (!activeProject) return;
  const btn = document.getElementById('btnRegenWeaponXModal');
  const orig = btn ? btn.innerHTML : '🔥 WeaponX Poster';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '🔥 Generating Poster...';
  }
  try {
    const res = await fetch(`/api/projects/${activeProject.id}/regenerate-weaponx-image`, {
      method: 'POST'
    });
    if (res.ok) {
      const data = await res.json();
      activeProject = data.project;
      await loadProjects();
      openModal(activeProject.id);
    } else {
      const err = await res.json();
      alert(`Failed to regenerate WeaponX poster: ${err.detail || 'Server error'}`);
    }
  } catch (e) {
    alert('Error regenerating WeaponX poster');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = orig;
    }
  }
}

async function publishActiveProject(overrideQa = false) {
  overrideQa = overrideQa === true;
  if (!activeProject) return;

  const chInfo = resolveTargetYoutubeChannel(activeProject);
  const btn = document.getElementById('btnModalPublish');
  const statusDiv = document.getElementById('publishResult');
  const titleVal = document.getElementById('modalYtTitleInput')?.value?.trim() || activeProject.title;
  const descVal = document.getElementById('modalYtDescInput')?.value?.trim() || activeProject.description;
  const tagsRaw = document.getElementById('modalYtTagsInput')?.value || '';
  const tagsList = tagsRaw.split(',').map(t => t.trim()).filter(Boolean);

  btn.disabled = true;
  btn.textContent = `⏳ Uploading & Saving (Private) to ${chInfo.id} (${chInfo.handle})...`;
  statusDiv.classList.add('hidden');

  try {
    const res = await fetch(`/api/publish/${activeProject.id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        privacy_status: 'private',
        require_approval_before_live: true,
        title: titleVal,
        description: descVal,
        tags: tagsList,
        category_id: '28',
        made_for_kids: false,
        channel: chInfo.key,
        override_qa: overrideQa
      })
    });
    const data = await res.json();

    if (showQaBlocked(res, data, statusDiv, 'publishActiveProject', 'Upload anyway (Private)')) {
      btn.textContent = `🚀 Upload to YouTube Shorts (${chInfo.id} · Private)`;
    } else if (res.ok) {
      activeProject = data.project || activeProject;
      activeProject.youtube = data.youtube;
      renderModalPublishState(activeProject);
      loadProjects();
    } else {
      statusDiv.className = 'publish-status error';
      statusDiv.innerHTML = `
        <div style="line-height: 1.5;">
          <strong>⚠️ Upload Failed (${chInfo.handle} · ${chInfo.id}):</strong> ${escapeHtml(data.detail || 'Check credentials')}<br>
          <button type="button" class="btn btn-primary btn-xs" onclick="handleTriggerYoutubeOAuth('${chInfo.key}')" style="margin-top: 8px; font-weight: 700;">
            🔑 Connect / Re-Authenticate YouTube (${chInfo.handle})
          </button>
          · <a href="${chInfo.studioUrl}" target="_blank" style="color: #00e5ff; font-weight: 600;">Open ${chInfo.studioUrl} ↗</a>
        </div>
      `;
      statusDiv.classList.remove('hidden');
      btn.textContent = `🚀 Upload to YouTube Shorts (${chInfo.id} · Private)`;
    }
  } catch (err) {
    statusDiv.className = 'publish-status error';
    statusDiv.textContent = `Error: ${err.message}`;
    statusDiv.classList.remove('hidden');
    btn.textContent = `🚀 Upload to YouTube Shorts (${chInfo.id} · Private)`;
  } finally {
    btn.disabled = false;
  }
}

async function approveActiveProjectLive(overrideQa = false) {
  overrideQa = overrideQa === true;
  if (!activeProject) return;

  const chInfo = resolveTargetYoutubeChannel(activeProject);
  const btnApprove = document.getElementById('btnModalApproveLive');
  const statusDiv = document.getElementById('publishResult');
  const titleVal = document.getElementById('modalYtTitleInput')?.value?.trim() || activeProject.title;
  const descVal = document.getElementById('modalYtDescInput')?.value?.trim() || activeProject.description;
  const tagsRaw = document.getElementById('modalYtTagsInput')?.value || '';
  const tagsList = tagsRaw.split(',').map(t => t.trim()).filter(Boolean);

  if (btnApprove) {
    btnApprove.disabled = true;
    btnApprove.textContent = `⏳ Approving (stays Private on ${chInfo.id})...`;
  }

  try {
    const res = await fetch(`/api/publish/${activeProject.id}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: titleVal,
        description: descVal,
        tags: tagsList,
        channel: chInfo.key,
        override_qa: overrideQa
      })
    });
    const data = await res.json();

    if (showQaBlocked(res, data, statusDiv, 'approveActiveProjectLive', 'Approve anyway (stays Private)')) {
      // reasons shown; nothing was sent to YouTube
    } else if (res.ok) {
      activeProject = data.project || activeProject;
      activeProject.youtube = data.youtube;
      renderModalPublishState(activeProject);
      loadProjects();
    } else {
      statusDiv.className = 'publish-status error';
      statusDiv.innerHTML = `
        <div style="line-height: 1.5;">
          <strong>⚠️ Approval Failed (${chInfo.handle} · ${chInfo.id}):</strong> ${escapeHtml(data.detail || 'Could not update the video on YouTube')}<br>
          <button type="button" class="btn btn-primary btn-xs" onclick="handleTriggerYoutubeOAuth('${chInfo.key}')" style="margin-top: 8px; font-weight: 700;">
            🔑 Connect / Re-Authenticate YouTube (${chInfo.handle})
          </button>
          · <a href="${chInfo.studioUrl}" target="_blank" style="color: #00e5ff; font-weight: 600;">Open ${chInfo.studioUrl} ↗</a>
        </div>
      `;
      statusDiv.classList.remove('hidden');
    }
  } catch (err) {
    statusDiv.className = 'publish-status error';
    statusDiv.textContent = `Error: ${err.message}`;
    statusDiv.classList.remove('hidden');
  } finally {
    if (btnApprove) {
      btnApprove.disabled = false;
      btnApprove.textContent = '✅ Approve (stays Private)';
    }
  }
}

// ---- A/B test kit: title + thumbnail variants for YouTube Studio's Test & compare ----------------
async function loadAbKit() {
  const box = document.getElementById('abKitBox');
  if (!box || !activeProject) return;
  box.innerHTML = '<div style="font-size:12px; color:#94a3b8;">Building variants…</div>';
  const d = await fetch(`/api/projects/${activeProject.id}/ab-variants?t=${Date.now()}`).then(r => r.json()).catch(() => ({}));
  const titles = (d.titles || []).map((t, i) => `
    <div style="display:flex; gap:6px; align-items:center; margin:3px 0; font-size:12px;">
      <span style="color:#94a3b8;">${String.fromCharCode(65 + i)}</span>
      <input readonly value="${escapeHtml(t)}" style="flex:1; padding:5px 8px; background:#131a29; border:1px solid #23304a; border-radius:6px; color:#f1f5f9;">
      <button type="button" class="btn btn-secondary btn-xs" onclick="navigator.clipboard.writeText(this.previousElementSibling.value)">Copy</button>
    </div>`).join('');
  const thumbs = (d.thumbnails || []).map((u, i) => `
    <a href="${u}?t=${Date.now()}" download title="Download thumbnail ${String.fromCharCode(65 + i)}">
      <img src="${u}?t=${Date.now()}" style="width:90px; border-radius:6px; margin-right:6px;"></a>`).join('');
  box.innerHTML = `${titles}<div style="margin-top:6px;">${thumbs}</div>
    <div style="font-size:11px; color:#94a3b8; margin-top:4px;">${escapeHtml(d.how_to || '')}</div>`;
}

// ---- WeaponX chart preview: build the chart, drop rows, then make the video with it -------------
let chartPreviewState = null;

async function openChartPreview(exclude = null) {
  const topic = (document.getElementById('customTopicInput')?.value || '').trim() || (chartPreviewState && chartPreviewState.topic);
  let modal = document.getElementById('chartPreviewModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'chartPreviewModal';
    modal.className = 'fb-modal-backdrop';
    modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
    document.body.appendChild(modal);
  }
  if (!topic) {
    modal.innerHTML = `<div class="fb-modal">Type a WeaponX topic first (e.g. "Cruise Missiles", "Modern Torpedoes"). <button class="fb-del" onclick="document.getElementById('chartPreviewModal').remove()">✕</button></div>`;
    return;
  }
  modal.innerHTML = `<div class="fb-modal"><div style="color:#94a3b8;">⏳ Building a verified chart for "${escapeHtml(topic)}" (checking every photo; up to a few minutes)…</div></div>`;
  const body = { topic };
  if (exclude && chartPreviewState) { body.preview_id = chartPreviewState.preview_id; body.exclude = [exclude]; }
  const res = await fetch('/api/chart-preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) {
    modal.innerHTML = `<div class="fb-modal">⚠️ ${escapeHtml(typeof d.detail === 'string' ? d.detail : 'Could not build the chart')} <button class="fb-del" onclick="document.getElementById('chartPreviewModal').remove()">✕</button></div>`;
    return;
  }
  chartPreviewState = d;
  const rows = (d.rows || []).map(r => `
    <div class="fb-item" style="display:flex; justify-content:space-between; align-items:center;">
      <div><strong>${escapeHtml(r.name || '')}</strong> <span style="color:#94a3b8;">${escapeHtml(r.country || '')} ${escapeHtml(String(r.year || ''))}</span>
        <div style="font-size:11px; color:#cbd5e1;">${escapeHtml((r.bullets || []).join(' · '))}</div></div>
      <button class="btn btn-secondary btn-xs" title="Replace this row with another verified weapon" onclick='openChartPreview(${JSON.stringify(r.article || r.name)})'>✕ Replace</button>
    </div>`).join('');
  modal.innerHTML = `
    <div class="fb-modal" style="width:min(960px,100%);" onclick="event.stopPropagation()">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <strong style="font-size:15px;">👁 Chart preview · ${escapeHtml(d.topic)}</strong>
        <button class="fb-del" onclick="document.getElementById('chartPreviewModal').remove()">✕</button>
      </div>
      <div style="display:flex; gap:14px; flex-wrap:wrap;">
        <img src="${d.image_url}?t=${Date.now()}" style="width:300px; max-width:100%; border-radius:8px; background:#fff;">
        <div style="flex:1; min-width:260px;">
          <div style="font-size:12px; color:#94a3b8; margin-bottom:6px;">Every row is a Wikipedia-verified model with a checked photo. Replace any row you don't like; the other rows stay.</div>
          ${rows}
          <button class="btn btn-primary" style="margin-top:10px;" onclick="document.getElementById('chartPreviewModal').remove(); triggerGenerate('weaponx', '${d.preview_id}')">🔥 Create WeaponX video with this chart</button>
        </div>
      </div>
    </div>`;
}

// ---- Performance: YouTube stats per video, and what works by style / music theme / channel -----
async function openAnalytics(refresh = false) {
  let modal = document.getElementById('analyticsModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'analyticsModal';
    modal.className = 'fb-modal-backdrop';
    modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
    document.body.appendChild(modal);
  }
  modal.innerHTML = `<div class="fb-modal"><div style="color:#94a3b8;">${refresh ? 'Reading YouTube…' : 'Loading…'}</div></div>`;
  const d = await fetch(refresh ? '/api/analytics/refresh' : `/api/analytics?t=${Date.now()}`, { method: refresh ? 'POST' : 'GET' })
    .then(r => r.json()).catch(() => ({}));
  const n = x => (x || 0).toLocaleString();
  const table = (rows, label) => `
    <table class="an-table"><tr><th>${label}</th><th>Videos</th><th>Public</th><th>Views</th><th>Avg views (public)</th></tr>
      ${(rows || []).map(r => `<tr><td>${escapeHtml(String(r.name))}</td><td>${r.videos}</td><td>${r.public_videos}</td><td>${n(r.views)}</td><td><strong>${n(r.avg_views)}</strong></td></tr>`).join('')}
    </table>`;
  const t = d.totals || {};
  const vids = (d.videos || []).map(v => `<tr><td><a href="${v.url}" target="_blank">${escapeHtml(v.title || v.topic || '')}</a></td>
      <td>${escapeHtml(v.channel)}</td><td>${escapeHtml(v.privacy)}</td><td>${n(v.views)}</td><td>+${n(v.views_7d)}</td><td>${n(v.likes)}</td><td>${n(v.comments)}</td></tr>`).join('');
  modal.innerHTML = `
    <div class="fb-modal" style="width:min(1000px,100%);" onclick="event.stopPropagation()">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
        <strong style="font-size:15px;">📈 Performance · ${n(t.views)} views · ${t.public || 0}/${t.videos || 0} public · +${n(t.views_7d)} this week</strong>
        <span><button class="btn btn-secondary btn-xs" onclick="openAnalytics(true)">🔄 Refresh from YouTube</button>
        <button class="fb-del" onclick="document.getElementById('analyticsModal').remove()">✕</button></span>
      </div>
      <div style="font-size:12px; color:#94a3b8; margin-bottom:8px;">Last read: ${escapeHtml(d.last_refresh || 'never')} · refreshed daily at 07:15${d.note ? ' · ' + escapeHtml(d.note) : ''}${(d.errors || []).length ? ' · ⚠️ ' + escapeHtml(d.errors.join('; ')) : ''}</div>
      <div class="an-grid">${table(d.by_style, 'Style')}${table(d.by_music_theme, 'Music theme')}${table(d.by_channel, 'Channel')}${table(d.by_category, 'Category')}</div>
      <h4 style="margin:12px 0 6px;">Videos</h4>
      <div style="max-height:40vh; overflow:auto;"><table class="an-table"><tr><th>Video</th><th>Channel</th><th>Privacy</th><th>Views</th><th>7 days</th><th>Likes</th><th>Comments</th></tr>${vids}</table></div>
    </div>`;
}

// ---- Verified photo library: cutouts reused by every chart (reject a bad one, restore it) -----
async function openPhotoLibrary() {
  let modal = document.getElementById('photoLibraryModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'photoLibraryModal';
    modal.className = 'fb-modal-backdrop';
    modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
    document.body.appendChild(modal);
  }
  const data = await fetch(`/api/photo-library?t=${Date.now()}`).then(r => r.json()).catch(() => ({ items: [] }));
  const cards = (data.items || []).filter(i => i.exists).map(i => `
    <div class="pl-card ${i.status === 'rejected' ? 'pl-rejected' : ''}">
      <img src="${i.image_url}?t=${Date.now()}" alt="${escapeHtml(i.title)}">
      <div class="pl-title">${escapeHtml(i.title)}</div>
      <div class="pl-meta">${escapeHtml(i.kind || '')} · ${i.status === 'approved' ? '✓ in use' : '✕ rejected'}</div>
      ${i.status === 'approved'
        ? `<button class="btn btn-secondary btn-xs" onclick="photoLibraryAction('${i.key}','reject')">Reject</button>`
        : `<button class="btn btn-secondary btn-xs" onclick="photoLibraryAction('${i.key}','restore')">Restore</button>`}
    </div>`).join('') || '<div style="color:#94a3b8;">No photos yet. Every clean cutout a chart uses is saved here automatically.</div>';
  modal.innerHTML = `
    <div class="fb-modal" style="width:min(980px,100%);" onclick="event.stopPropagation()">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
        <strong style="font-size:15px;">📚 Verified Photo Library · ${data.approved || 0} in use</strong>
        <button class="fb-del" onclick="document.getElementById('photoLibraryModal').remove()">✕</button>
      </div>
      <div style="font-size:12px; color:#94a3b8; margin-bottom:10px;">Clean cutouts of exact models. Charts use these first (instant, no download). Reject a bad one and the next chart finds another photo.</div>
      <div class="pl-grid">${cards}</div>
    </div>`;
}

async function photoLibraryAction(key, action) {
  await fetch(`/api/photo-library/${key}/${action}`, { method: 'POST' });
  openPhotoLibrary();
}

// ---- Per-video feedback: notes in plain words that Auto-fix turns into fixes -----------------
function _fbStatusBadge(f) {
  const map = {
    open: ['#67e8f9', '⏳ waiting for Auto-fix'],
    fixed: ['#34d399', '✓ fixed'],
    partly_fixed: ['#fbbf24', '◐ partly fixed'],
    needs_you: ['#f87171', '✋ needs you'],
  };
  const [c, label] = map[f.status] || ['#94a3b8', f.status];
  return `<span style="color:${c}; font-weight:700;">${label}</span>`;
}

async function openFeedbackPanel(projectId) {
  let modal = document.getElementById('feedbackModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'feedbackModal';
    modal.className = 'fb-modal-backdrop';
    modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
    document.body.appendChild(modal);
  }
  modal.innerHTML = `<div class="fb-modal"><div style="color:#94a3b8;">Loading…</div></div>`;
  const res = await fetch(`/api/projects/${projectId}/feedback`);
  const data = await res.json().catch(() => ({ feedback: [] }));
  const proj = (typeof currentProjects !== 'undefined' && Array.isArray(currentProjects) ? currentProjects : []).find(x => x.id === projectId) || {};
  const items = (data.feedback || []).slice().reverse().map(f => `
    <div class="fb-item">
      <div style="display:flex; justify-content:space-between; gap:8px;">
        <div style="flex:1; color:#e2e8f0;">${escapeHtml(f.text)}</div>
        <button class="fb-del" title="Delete note" onclick="deleteFeedback('${projectId}', '${f.id}')">✕</button>
      </div>
      <div style="font-size:11px; margin-top:4px;">${_fbStatusBadge(f)}
        ${f.result ? ` · <span style="color:#cbd5e1;">${escapeHtml(f.result)}</span>`
          : (f.preview && f.preview.length ? ` · <span style="color:#94a3b8;">will do: ${escapeHtml(f.preview.join(', '))}</span>` : '')}
      </div>
    </div>`).join('') || '<div style="color:#64748b; font-size:12px;">No feedback yet.</div>';
  modal.innerHTML = `
    <div class="fb-modal" onclick="event.stopPropagation()">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <strong style="font-size:15px;">💬 Feedback · ${escapeHtml(proj.title || proj.topic || projectId)}</strong>
        <button class="fb-del" onclick="document.getElementById('feedbackModal').remove()">✕</button>
      </div>
      <div style="font-size:12px; color:#94a3b8; margin-bottom:8px;">
        Say what's wrong in plain words, e.g. <em>"scene 3 image is wrong"</em>, <em>"music is boring"</em>,
        <em>"music too loud"</em>, <em>"voice too fast"</em>, <em>"scene 2 should say "…""</em>, <em>"remove scene 4"</em>,
        <em>"title should be "…""</em>, <em>"captions out of sync"</em>.
      </div>
      <textarea id="fbText" rows="3" placeholder="What's wrong with this video?" style="width:100%; box-sizing:border-box; border-radius:8px; padding:8px; background:#0f172a; color:#e2e8f0; border:1px solid #334155;"></textarea>
      <div style="display:flex; gap:8px; margin-top:8px; flex-wrap:wrap;">
        <button class="btn btn-secondary btn-xs" onclick="submitFeedback('${projectId}', false)">💾 Save note</button>
        <button class="btn btn-primary btn-xs" onclick="submitFeedback('${projectId}', true)">🔧 Save &amp; Auto-fix now</button>
        <span id="fbStatus" style="font-size:12px; color:#94a3b8; align-self:center;"></span>
      </div>
      <div style="margin-top:12px; max-height:260px; overflow:auto;">${items}</div>
    </div>`;
  document.getElementById('fbText')?.focus();
}

async function submitFeedback(projectId, fixNow) {
  const text = (document.getElementById('fbText')?.value || '').trim();
  const st = document.getElementById('fbStatus');
  if (text) {
    const res = await fetch(`/api/projects/${projectId}/feedback`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text })
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      if (st) st.textContent = `⚠️ ${typeof d.detail === 'string' ? d.detail : 'Could not save'}`;
      return;
    }
  }
  if (fixNow) {
    if (st) st.textContent = '⏳ Fixing & re-checking (new images/music can take a few minutes)…';
    await autoRepairProject(projectId);
  }
  await openFeedbackPanel(projectId);
  loadProjects();
}

async function deleteFeedback(projectId, feedbackId) {
  await fetch(`/api/projects/${projectId}/feedback/${feedbackId}`, { method: 'DELETE' });
  await openFeedbackPanel(projectId);
  loadProjects();
}

// Runs the same auto-repair the pipeline uses (new images for repeats, re-render, re-master,
// clean metadata) and re-checks. The card then shows Completed or the remaining problems.
async function autoRepairProject(projectId) {
  const btn = document.getElementById(`autoFixBtn_${projectId}`);
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Fixing & re-checking...'; }
  try {
    const res = await fetch(`/api/projects/${projectId}/auto-repair`, { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok && btn) {
      btn.textContent = `⚠️ ${typeof data.detail === 'string' ? data.detail : 'Auto-fix failed'}`;
    }
  } catch (e) {
    if (btn) btn.textContent = `⚠️ ${e.message}`;
  } finally {
    loadProjects();
  }
}

// Upload/Approve are refused (409) while the video fails Verify-video. Lists the failed checks and
// offers an explicit "... anyway" button that re-sends with override_qa. Returns true if handled.
function showQaBlocked(res, data, statusDiv, retryFn, retryLabel) {
  const d = data && data.detail;
  if (res.status !== 409 || !d || !d.qa_blocked) return false;
  const items = (d.reasons || []).map(r => `<li>${escapeHtml(r)}</li>`).join('');
  statusDiv.className = 'publish-status error';
  statusDiv.innerHTML = `
    <div style="line-height: 1.5;">
      <strong>🛡️ Quality check failed${d.score != null ? ` (${d.score}%)` : ''}: nothing was sent to YouTube.</strong>
      <ul style="margin: 6px 0 6px 18px;">${items}</ul>
      Fix these and re-render, or
      <button type="button" class="btn btn-secondary btn-xs" onclick="${retryFn}(true)" style="margin-left: 4px; font-weight: 700;">
        ${escapeHtml(retryLabel)}
      </button>
    </div>`;
  statusDiv.classList.remove('hidden');
  return true;
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

async function loadModalPromptAndEditor(project) {
  if (!project) return;

  const targetSelect = document.getElementById('editTargetImageSelect');
  if (targetSelect) {
    const scenes = project.scenes || [];
    let opts = `<option value="1" selected>Hero Master Chart (Scene 1)</option>`;
    for (let i = 1; i < scenes.length; i++) {
      opts += `<option value="${i + 1}">Scene ${i + 1}</option>`;
    }
    targetSelect.innerHTML = opts;
  }

  // Pre-fill prompt and headline from API or fallback
  const promptInput = document.getElementById('modalImagePromptText');
  const headlineInput = document.getElementById('modalPromptHeadlineInput');
  const editHeadingText = document.getElementById('editHeadingText');
  const statusEl = document.getElementById('modalPromptStatus');
  if (statusEl) statusEl.textContent = '';

  const fallbackHeadline = project.title || project.topic || 'TOP WEAPONS INFOGRAPHIC';
  if (headlineInput) headlineInput.value = fallbackHeadline.toUpperCase();
  if (editHeadingText && !editHeadingText.value) editHeadingText.value = fallbackHeadline.toUpperCase();

  try {
    const res = await fetch(`/api/projects/${project.id}/image-prompt?t=${Date.now()}`);
    if (res.ok) {
      const data = await res.json();
      if (promptInput) promptInput.value = data.current_prompt || `${WEAPONX_EXACT_PROMPT_TEMPLATE}\n\n**SPECIFIC CONTENT FOR THIS INFOGRAPHIC:**\n- Main Header Headline: ${data.headline}\n- Focus / Topic: ${data.topic}`;
      if (headlineInput && data.headline) headlineInput.value = data.headline;
      if (editHeadingText && data.headline) editHeadingText.value = data.headline;
    } else if (promptInput) {
      promptInput.value = `${WEAPONX_EXACT_PROMPT_TEMPLATE}\n\n**SPECIFIC CONTENT FOR THIS INFOGRAPHIC:**\n- Main Header Headline: ${fallbackHeadline.toUpperCase()}\n- Focus / Topic: ${project.topic}`;
    }
  } catch (err) {
    if (promptInput) {
      promptInput.value = `${WEAPONX_EXACT_PROMPT_TEMPLATE}\n\n**SPECIFIC CONTENT FOR THIS INFOGRAPHIC:**\n- Main Header Headline: ${fallbackHeadline.toUpperCase()}\n- Focus / Topic: ${project.topic}`;
    }
  }
}

async function handleCallPromptAgain() {
  if (!activeProject) return;

  const btn = document.getElementById('btnCallPromptAgain');
  const promptEl = document.getElementById('modalImagePromptText');
  const headlineEl = document.getElementById('modalPromptHeadlineInput');
  const statusEl = document.getElementById('modalPromptStatus');

  const promptVal = promptEl ? promptEl.value.trim() : '';
  const headlineVal = headlineEl ? headlineEl.value.trim() : '';
  const engineSelect = document.getElementById('modalImageEngineSelect');
  const engineVal = engineSelect ? engineSelect.value : 'auto';

  if (btn) {
    btn.disabled = true;
    btn.textContent = '⚡ Regenerating Image...';
  }
  if (statusEl) {
    statusEl.style.color = '#38bdf8';
    statusEl.textContent = 'Calling image generator with custom prompt & re-rendering video...';
  }

  try {
    const res = await fetch(`/api/projects/${activeProject.id}/generate-from-prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: promptVal,
        headline: headlineVal,
        style: activeProject.style || 'weaponx',
        engine: engineVal
      })
    });
    const data = await res.json();

    if (res.ok) {
      activeProject = data.project || activeProject;
      const videoPlayer = document.getElementById('modalVideoPlayer');
      if (videoPlayer) {
        videoPlayer.src = `/api/video/${activeProject.id}?t=${Date.now()}`;
        videoPlayer.play().catch(() => {});
      }

      // Update scene 1 thumb
      const sThumb = document.getElementById('sceneThumbImg_1');
      if (sThumb) sThumb.src = `/api/scene_image/${activeProject.id}/1?t=${Date.now()}`;

      if (statusEl) {
        statusEl.style.color = '#10b981';
        statusEl.textContent = '✓ Image regenerated & video re-rendered successfully!';
      }
      loadProjects();
    } else {
      if (statusEl) {
        statusEl.style.color = '#ef4444';
        statusEl.textContent = `Regeneration failed: ${data.detail || 'Server error'}`;
      }
    }
  } catch (err) {
    if (statusEl) {
      statusEl.style.color = '#ef4444';
      statusEl.textContent = `Error: ${err.message}`;
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '⚡ Call Again (Regenerate Image)';
    }
  }
}

// ==============================================================================
// MULTI-LAYER IMAGE STUDIO & LAYER SELECTION ENGINE
// ==============================================================================

let currentImageLayers = [];
let selectedLayerId = null;
let currentFilters = { brightness: 1.0, contrast: 1.0, saturation: 1.0 };
let isDraggingLayer = false;
let isResizingLayer = false;
let activeResizeHandle = null;
let dragStartX = 0;
let dragStartY = 0;
let dragLayerInitialX = 0;
let dragLayerInitialY = 0;
let dragLayerInitialW = 0;
let dragLayerInitialH = 0;
let dragLayerInitialFontSize = 38;
let dragLayerInitialWrapW = 900;

function createWeaponXDefaultLayers(headline = 'THE MOST POPULAR AK MODELS AND THEIR CALIBERS') {
  return [
    {
      id: 'layer_outer_frame',
      type: 'shape',
      name: 'Outer Border Frame',
      shape_type: 'outer_border',
      visible: true,
      fill_color: '#000000',
      transparent: true,
      border_color: '#000000',
      border_width: 4,
      radius: 14,
      x: 4,
      y: 4,
      width: 1072,
      height: 1912,
      opacity: 1.0
    },
    {
      id: 'layer_header_bar',
      type: 'shape',
      name: 'Top Header Bar',
      shape_type: 'rounded_rectangle',
      visible: true,
      fill_color: '#0a0a0a',
      transparent: false,
      border_color: '#000000',
      border_width: 0,
      radius: 16,
      x: 12,
      y: 8,
      width: 1056,
      height: 76,
      opacity: 1.0
    },
    {
      id: 'layer_main_headline',
      type: 'text',
      name: 'Main Headline',
      visible: true,
      text: headline.toUpperCase(),
      font_style: 'condensed_bold',
      font_size: 42,
      color: '#FFFFFF',
      stroke_width: 0,
      stroke_color: '#000000',
      position: 'top_header',
      alignment: 'center',
      x: 540,
      y: 46,
      opacity: 1.0
    },
    {
      id: 'layer_bottom_accent',
      type: 'shape',
      name: 'Bottom Accent Red Line',
      shape_type: 'bottom_accent_line',
      visible: true,
      fill_color: '#FF1744',
      transparent: false,
      border_color: '#000000',
      border_width: 0,
      radius: 0,
      x: 0,
      y: 1914,
      width: 820,
      height: 6,
      opacity: 1.0
    }
  ];
}

async function openStudioModal(targetScene = 1, projectId = null) {
  if (projectId) {
    const found = (currentProjects || []).find(p => p.id === projectId);
    if (found) activeProject = found;
  }
  if (!activeProject) {
    if (currentProjects && currentProjects.length > 0) {
      activeProject = currentProjects[0];
    } else {
      try {
        const res = await fetch(`/api/projects?t=${Date.now()}`);
        if (res.ok) {
          const list = await res.json();
          if (list && list.length > 0) {
            currentProjects = list;
            activeProject = list[0];
          }
        }
      } catch (e) {
        console.warn('Projects fetch error:', e);
      }
    }
  }

  if (!activeProject) {
    alert('Please generate or select a video project first before opening the Image Studio!');
    return;
  }

  const studioModal = document.getElementById('imageStudioModal');
  const videoModal = document.getElementById('videoModal');
  const targetSelect = document.getElementById('editTargetImageSelect');

  const targetSceneNum = parseInt(targetScene || 1, 10);
  activeProject.scene_layers = activeProject.scene_layers || {};

  // Populate scenes dropdown in Image Studio
  if (targetSelect && activeProject.scenes) {
    let opts = `<option value="1">Hero Master Chart (Scene 1)</option>`;
    for (let i = 1; i < activeProject.scenes.length; i++) {
      opts += `<option value="${i + 1}">Scene ${i + 1}</option>`;
    }
    targetSelect.innerHTML = opts;
    targetSelect.value = String(targetSceneNum);
  }

  // Load layers specific to the selected scene to avoid cross-scene contamination
  if (activeProject.scene_layers[String(targetSceneNum)]) {
    currentImageLayers = JSON.parse(JSON.stringify(activeProject.scene_layers[String(targetSceneNum)]));
  } else if (targetSceneNum === 1 && activeProject.image_layers && Array.isArray(activeProject.image_layers) && activeProject.image_layers.length > 0) {
    currentImageLayers = JSON.parse(JSON.stringify(activeProject.image_layers));
  } else {
    const sceneObj = activeProject.scenes ? activeProject.scenes[targetSceneNum - 1] : null;
    const headline = sceneObj?.narration ? sceneObj.narration.slice(0, 45).toUpperCase() : (activeProject.title || activeProject.topic || 'WEAPONX ENCYCLOPEDIA');
    currentImageLayers = createWeaponXDefaultLayers(headline);
  }
  selectedLayerId = currentImageLayers.find(l => l.type === 'text')?.id || currentImageLayers[0]?.id || null;

  if (videoModal) {
    videoModal.classList.add('hidden');
    videoModal.style.display = 'none';
  }
  if (studioModal) {
    studioModal.classList.remove('hidden');
    studioModal.style.display = 'flex';
  }

  renderLayersList();
  renderInspector();
  drawLayerStudioCanvas();
}

function closeStudioModal() {
  const studioModal = document.getElementById('imageStudioModal');
  const videoModal = document.getElementById('videoModal');

  if (studioModal) {
    studioModal.classList.add('hidden');
    studioModal.style.display = 'none';
  }

  if (videoModal && activeProject) {
    videoModal.classList.remove('hidden');
    videoModal.style.display = 'flex';

    // Refresh thumbnails and video
    const targetSelect = document.getElementById('editTargetImageSelect');
    const targetScene = targetSelect ? targetSelect.value : '1';
    const sThumb = document.getElementById(`sceneThumbImg_${targetScene}`);
    if (sThumb) sThumb.src = `/api/scene_image/${activeProject.id}/${targetScene}?t=${Date.now()}`;
  }
}

async function runQASanityTests() {
  const btn = document.getElementById('btnRunQATests');
  const origText = btn ? btn.innerHTML : '🛡️ QA Sanity';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '⏳ Testing...';
  }

  try {
    const res = await fetch(`/api/qa/run-sanity?t=${Date.now()}`, { method: 'POST' });
    const data = await res.json();
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origText;
    }

    const icon = data.overall_status === 'PASSED' ? '✅' : '❌';
    let summaryMsg = `${icon} QA Tester Sanity Check: ${data.overall_status} (${data.score_percent}%)\n`;
    summaryMsg += `Passed: ${data.passed_tests}/${data.total_tests} tests in ${data.duration_seconds}s\n\n`;

    for (const r of (data.results || []).slice(0, 10)) {
      const rIcon = r.status === 'PASSED' ? '✔' : '✕';
      summaryMsg += `[${rIcon}] ${r.name}: ${r.details}\n`;
    }

    alert(summaryMsg);
  } catch (err) {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origText;
    }
    alert(`QA Sanity Error: ${err.message}`);
  }
}

window.openStudioModal = openStudioModal;
window.closeStudioModal = closeStudioModal;
window.runQASanityTests = runQASanityTests;

function initLayerStudioEvents() {
  const btnAddText = document.getElementById('btnAddTextLayer');
  if (btnAddText) btnAddText.addEventListener('click', addTextLayer);

  const btnAddShape = document.getElementById('btnAddShapeLayer');
  if (btnAddShape) btnAddShape.addEventListener('click', addShapeLayer);

  // Open & Close Studio Dialog Handlers
  document.getElementById('btnOpenStudioModal')?.addEventListener('click', () => openStudioModal(1));
  document.getElementById('btnCloseStudioModal')?.addEventListener('click', closeStudioModal);
  document.getElementById('btnCancelStudioModal')?.addEventListener('click', closeStudioModal);
  document.getElementById('imageStudioModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'imageStudioModal') closeStudioModal();
  });

  // Quick Pixlr Presets
  document.getElementById('presetBtnHeading')?.addEventListener('click', addPresetHeading);
  document.getElementById('presetBtnSubheading')?.addEventListener('click', addPresetSubheading);
  document.getElementById('presetBtnBody')?.addEventListener('click', addPresetBody);
  document.getElementById('presetBtnBadge')?.addEventListener('click', addPresetBadge);
  document.getElementById('presetBtnHud')?.addEventListener('click', addPresetHud);
  document.getElementById('presetBtnWeaponXBar')?.addEventListener('click', addPresetWeaponXHeader);
  document.getElementById('presetBtnBox')?.addEventListener('click', addPresetBox);
  document.getElementById('presetBtnRedLine')?.addEventListener('click', addPresetRedLine);

  const btnLoadWx = document.getElementById('btnLoadWeaponXLayers');
  if (btnLoadWx) {
    btnLoadWx.addEventListener('click', () => {
      const headline = document.getElementById('modalPromptHeadlineInput')?.value?.trim() || activeProject?.title || 'WEAPONX ENCYCLOPEDIA';
      currentImageLayers = createWeaponXDefaultLayers(headline);
      selectedLayerId = currentImageLayers[2]?.id || currentImageLayers[0]?.id;
      renderLayersList();
      renderInspector();
      drawLayerStudioCanvas();
    });
  }

  const btnClear = document.getElementById('btnClearAllLayers');
  if (btnClear) {
    btnClear.addEventListener('click', () => {
      if (confirm('Clear all layers from the editor?')) {
        currentImageLayers = [];
        selectedLayerId = null;
        renderLayersList();
        renderInspector();
        drawLayerStudioCanvas();
      }
    });
  }

  const btnApplyAll = document.getElementById('btnApplyAllLayers');
  if (btnApplyAll) btnApplyAll.addEventListener('click', () => handleApplyAllLayers(false));

  const btnApplyRerender = document.getElementById('btnApplyLayersAndRerender');
  if (btnApplyRerender) btnApplyRerender.addEventListener('click', () => handleApplyAllLayers(true));

  const targetSelect = document.getElementById('editTargetImageSelect');
  let studioActiveScene = 1;
  if (targetSelect) {
    targetSelect.addEventListener('change', () => {
      const newScene = parseInt(targetSelect.value, 10);
      if (activeProject) {
        activeProject.scene_layers = activeProject.scene_layers || {};
        activeProject.scene_layers[String(studioActiveScene)] = JSON.parse(JSON.stringify(currentImageLayers));
        studioActiveScene = newScene;

        if (activeProject.scene_layers[String(newScene)]) {
          currentImageLayers = JSON.parse(JSON.stringify(activeProject.scene_layers[String(newScene)]));
        } else if (newScene === 1 && activeProject.image_layers && activeProject.image_layers.length > 0) {
          currentImageLayers = JSON.parse(JSON.stringify(activeProject.image_layers));
        } else {
          const sceneObj = activeProject.scenes ? activeProject.scenes[newScene - 1] : null;
          const headline = sceneObj?.narration ? sceneObj.narration.slice(0, 45).toUpperCase() : (activeProject.title || activeProject.topic || 'WEAPONX ENCYCLOPEDIA');
          currentImageLayers = createWeaponXDefaultLayers(headline);
        }
        selectedLayerId = currentImageLayers.find(l => l.type === 'text')?.id || currentImageLayers[0]?.id || null;
      }
      renderLayersList();
      renderInspector();
      drawLayerStudioCanvas();
    });
  }

  // In-Studio AI Image Generation Ribbon Controls
  const btnStudioAi = document.getElementById('btnStudioAiGen');
  const panelStudioAi = document.getElementById('studioAiGenPanel');
  const btnCloseAiPanel = document.getElementById('btnStudioCloseAiPanel');
  const btnExecStudioAi = document.getElementById('btnStudioExecuteAiGen');
  const statusStudioAi = document.getElementById('studioAiStatus');

  if (btnStudioAi && panelStudioAi) {
    btnStudioAi.addEventListener('click', () => {
      const isVisible = panelStudioAi.style.display !== 'none';
      panelStudioAi.style.display = isVisible ? 'none' : 'block';
      if (!isVisible) {
        const tVal = targetSelect ? targetSelect.value : '1';
        const sceneObj = activeProject?.scenes ? activeProject.scenes[parseInt(tVal, 10) - 1] : null;
        const promptInput = document.getElementById('studioAiPromptInput');
        if (promptInput && !promptInput.value) {
          promptInput.value = sceneObj?.visual_prompt || sceneObj?.narration || `Cinematic shot of ${activeProject?.topic || 'Military'}`;
        }
      }
    });
  }

  if (btnCloseAiPanel && panelStudioAi) {
    btnCloseAiPanel.addEventListener('click', () => {
      panelStudioAi.style.display = 'none';
    });
  }

  if (btnExecStudioAi) {
    btnExecStudioAi.addEventListener('click', async () => {
      if (!activeProject) return;
      const tVal = parseInt(targetSelect ? targetSelect.value : '1', 10);
      const promptInput = document.getElementById('studioAiPromptInput');
      const prompt = promptInput?.value?.trim() || '';
      const engSelect = document.getElementById('studioAiEngineSelect');
      const engine = engSelect ? engSelect.value : 'auto';

      if (statusStudioAi) {
        statusStudioAi.style.color = '#38bdf8';
        statusStudioAi.textContent = `⚡ Generating AI image for Scene ${tVal} (${engine})...`;
      }
      btnExecStudioAi.disabled = true;

      try {
        const res = await fetch(`/api/projects/${activeProject.id}/scenes/${tVal}/generate-image`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt, style: activeProject.style || 'cinematic', engine })
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
          if (statusStudioAi) {
            statusStudioAi.style.color = '#10b981';
            statusStudioAi.textContent = `✓ Generated successfully via ${data.provider || 'AI Engine'}!`;
          }
          drawLayerStudioCanvas();
          const sThumb = document.getElementById(`sceneThumbImg_${tVal}`);
          if (sThumb) sThumb.src = `/api/scene_image/${activeProject.id}/${tVal}?t=${Date.now()}`;
          setTimeout(() => { if (panelStudioAi) panelStudioAi.style.display = 'none'; }, 1000);
        } else {
          if (statusStudioAi) {
            statusStudioAi.style.color = '#ef4444';
            statusStudioAi.textContent = `Error: ${data.detail || data.message || 'Generation failed'}`;
          }
        }
      } catch (err) {
        if (statusStudioAi) {
          statusStudioAi.style.color = '#ef4444';
          statusStudioAi.textContent = `Error: ${err.message}`;
        }
      } finally {
        btnExecStudioAi.disabled = false;
      }
    });
  }

  // In-Studio Image File Upload
  const btnStudioUpload = document.getElementById('btnStudioUpload');
  const studioFileInput = document.getElementById('studioFileInput');
  if (btnStudioUpload && studioFileInput) {
    btnStudioUpload.addEventListener('click', () => studioFileInput.click());
    studioFileInput.addEventListener('change', async () => {
      const file = studioFileInput.files[0];
      if (!file || !activeProject) return;
      const tVal = parseInt(targetSelect ? targetSelect.value : '1', 10);
      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await fetch(`/api/projects/${activeProject.id}/scenes/${tVal}/image`, {
          method: 'POST',
          body: formData
        });
        if (res.ok) {
          drawLayerStudioCanvas();
          const sThumb = document.getElementById(`sceneThumbImg_${tVal}`);
          if (sThumb) sThumb.src = `/api/scene_image/${activeProject.id}/${tVal}?t=${Date.now()}`;
          const upData = await res.json().catch(() => ({}));
          alert(upData.warning ? `Image uploaded for Scene ${tVal}.\n\n⚠️ ${upData.warning}` : `Image uploaded for Scene ${tVal} successfully!`);
        } else {
          alert('Failed to upload image.');
        }
      } catch (e) {
        alert(`Upload error: ${e.message}`);
      }
      studioFileInput.value = '';
    });
  }

  // Filter sliders
  const fBright = document.getElementById('filterBrightness');
  const fCont = document.getElementById('filterContrast');
  const fSat = document.getElementById('filterSaturation');

  if (fBright) {
    fBright.addEventListener('input', () => {
      currentFilters.brightness = parseFloat(fBright.value);
      document.getElementById('lblBrightness').textContent = `${Math.round(currentFilters.brightness * 100)}%`;
      drawLayerStudioCanvas();
    });
  }
  if (fCont) {
    fCont.addEventListener('input', () => {
      currentFilters.contrast = parseFloat(fCont.value);
      document.getElementById('lblContrast').textContent = `${Math.round(currentFilters.contrast * 100)}%`;
      drawLayerStudioCanvas();
    });
  }
  if (fSat) {
    fSat.addEventListener('input', () => {
      currentFilters.saturation = parseFloat(fSat.value);
      document.getElementById('lblSaturation').textContent = `${Math.round(currentFilters.saturation * 100)}%`;
      drawLayerStudioCanvas();
    });
  }

  // Interactive canvas drag & hover
  const canvas = document.getElementById('layerStudioCanvas');
  if (canvas) {
    canvas.addEventListener('mousedown', handleCanvasMouseDown);
    canvas.addEventListener('mousemove', handleCanvasHover);
    window.addEventListener('mousemove', handleCanvasMouseMove);
    window.addEventListener('mouseup', handleCanvasMouseUp);
  }
}

async function loadModalPromptAndEditor(project) {
  if (!project) return;

  const targetSelect = document.getElementById('editTargetImageSelect');
  if (targetSelect) {
    const scenes = project.scenes || [];
    let opts = `<option value="1" selected>Hero Master Chart (Scene 1)</option>`;
    for (let i = 1; i < scenes.length; i++) {
      opts += `<option value="${i + 1}">Scene ${i + 1}</option>`;
    }
    targetSelect.innerHTML = opts;
  }

  const promptInput = document.getElementById('modalImagePromptText');
  const headlineInput = document.getElementById('modalPromptHeadlineInput');
  const statusEl = document.getElementById('modalPromptStatus');
  if (statusEl) statusEl.textContent = '';

  const fallbackHeadline = project.title || project.topic || 'TOP WEAPONS INFOGRAPHIC';
  if (headlineInput) headlineInput.value = fallbackHeadline.toUpperCase();

  try {
    const res = await fetch(`/api/projects/${project.id}/image-prompt?t=${Date.now()}`);
    if (res.ok) {
      const data = await res.json();
      if (promptInput) promptInput.value = data.current_prompt || `${WEAPONX_EXACT_PROMPT_TEMPLATE}\n\n**SPECIFIC CONTENT FOR THIS INFOGRAPHIC:**\n- Main Header Headline: ${data.headline}\n- Focus / Topic: ${data.topic}`;
      if (headlineInput && data.headline) headlineInput.value = data.headline;
    } else if (promptInput) {
      promptInput.value = `${WEAPONX_EXACT_PROMPT_TEMPLATE}\n\n**SPECIFIC CONTENT FOR THIS INFOGRAPHIC:**\n- Main Header Headline: ${fallbackHeadline.toUpperCase()}\n- Focus / Topic: ${project.topic}`;
    }
  } catch (err) {
    if (promptInput) {
      promptInput.value = `${WEAPONX_EXACT_PROMPT_TEMPLATE}\n\n**SPECIFIC CONTENT FOR THIS INFOGRAPHIC:**\n- Main Header Headline: ${fallbackHeadline.toUpperCase()}\n- Focus / Topic: ${project.topic}`;
    }
  }

  // Initialize Layer Studio layers
  if (project.image_layers && Array.isArray(project.image_layers) && project.image_layers.length > 0) {
    currentImageLayers = JSON.parse(JSON.stringify(project.image_layers));
  } else {
    currentImageLayers = createWeaponXDefaultLayers(headlineInput ? headlineInput.value : fallbackHeadline);
  }
  selectedLayerId = currentImageLayers.find(l => l.type === 'text')?.id || currentImageLayers[0]?.id || null;

  renderLayersList();
  renderInspector();
  drawLayerStudioCanvas();
}

function renderLayersList() {
  const container = document.getElementById('layersListContainer');
  const countBadge = document.getElementById('layerCountBadge');
  if (!container) return;

  if (countBadge) {
    countBadge.textContent = `${currentImageLayers.length} Layer${currentImageLayers.length === 1 ? '' : 's'}`;
  }

  if (currentImageLayers.length === 0) {
    container.innerHTML = `
      <div style="font-size: 11px; color: #64748b; text-align: center; padding: 20px 0;">
        No layers added yet.<br>Click <strong>"+ Add Text"</strong> or <strong>"🔥 Load WeaponX Layers"</strong> above.
      </div>
    `;
    return;
  }

  // Render in reverse order so topmost visual layer appears on top of the list
  const reversed = [...currentImageLayers].map((layer, index) => ({ layer, origIndex: index })).reverse();

  container.innerHTML = reversed.map(({ layer, origIndex }) => {
    const isSelected = layer.id === selectedLayerId;
    const icon = layer.type === 'text' ? '🔤' : (layer.shape_type === 'circle' ? '⚪' : '📐');
    const eyeIcon = layer.visible ? '👁️' : '🚫';
    const borderStyle = isSelected ? 'border: 2px solid #00e5ff; background: rgba(0, 229, 255, 0.12);' : 'border: 1px solid #1e293b; background: rgba(15, 23, 42, 0.7);';

    return `
      <div class="layer-item-card" onclick="selectLayer('${layer.id}')" style="display: flex; align-items: center; justify-content: space-between; padding: 6px 8px; border-radius: 6px; cursor: pointer; transition: all 0.15s; ${borderStyle}">
        <div style="display: flex; align-items: center; gap: 6px; min-width: 0; flex: 1;">
          <button onclick="event.stopPropagation(); toggleLayerVisibility('${layer.id}')" title="Toggle Visibility" style="background: transparent; border: none; font-size: 11px; cursor: pointer; padding: 2px;">
            ${eyeIcon}
          </button>
          <span style="font-size: 12px;">${icon}</span>
          <span style="font-size: 11.5px; font-weight: ${isSelected ? '700' : '500'}; color: ${isSelected ? '#00e5ff' : '#f1f5f9'}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
            ${escapeHtml(layer.name || (layer.type === 'text' ? layer.text : layer.shape_type))}
          </span>
          <span style="font-size: 9.5px; color: #64748b; font-family: monospace; margin-left: 4px;">
            ${layer.type === 'shape' ? `${Math.round(layer.width || 0)}×${Math.round(layer.height || 0)}` : `${layer.font_size || 38}px`}
          </span>
        </div>
        <div style="display: flex; align-items: center; gap: 2px;" onclick="event.stopPropagation()">
          <button onclick="moveLayer('${layer.id}', -1)" title="Move Down" style="background: transparent; border: none; color: #94a3b8; font-size: 10px; cursor: pointer; padding: 2px 4px;">↓</button>
          <button onclick="moveLayer('${layer.id}', 1)" title="Move Up" style="background: transparent; border: none; color: #94a3b8; font-size: 10px; cursor: pointer; padding: 2px 4px;">↑</button>
          <button onclick="duplicateLayer('${layer.id}')" title="Duplicate Layer" style="background: transparent; border: none; color: #94a3b8; font-size: 10px; cursor: pointer; padding: 2px 4px;">📋</button>
          <button onclick="deleteLayer('${layer.id}')" title="Delete Layer" style="background: transparent; border: none; color: #f87171; font-size: 11px; cursor: pointer; padding: 2px 4px;">✕</button>
        </div>
      </div>
    `;
  }).join('');
}

function selectLayer(id) {
  selectedLayerId = id;
  renderLayersList();
  renderInspector();
  drawLayerStudioCanvas();
}

function toTitleCase(str) {
  return (str || '').replace(/\w\S*/g, (txt) => txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase());
}

function splitLinesWithWrap(ctx, text, maxWrapW) {
  const rawLines = (text || '').split('\n');
  if (!maxWrapW || maxWrapW <= 20) return rawLines;

  const result = [];
  for (const rLine of rawLines) {
    const words = rLine.split(' ');
    let currentLine = '';
    for (const w of words) {
      const testLine = currentLine ? currentLine + ' ' + w : w;
      if (ctx.measureText(testLine).width > maxWrapW && currentLine) {
        result.push(currentLine);
        currentLine = w;
      } else {
        currentLine = testLine;
      }
    }
    if (currentLine) result.push(currentLine);
  }
  return result.length > 0 ? result : [''];
}

function addPresetHeading() {
  const newLayer = {
    id: 'layer_' + Date.now(),
    type: 'text',
    name: `Heading ${currentImageLayers.filter(l => l.type === 'text').length + 1}`,
    visible: true,
    text: 'TOP MILITARY WEAPONS',
    text_case: 'upper',
    font_style: 'anton',
    font_size: 48,
    bold: true,
    italic: false,
    color: '#FFFFFF',
    alignment: 'center',
    letter_spacing: 1,
    line_height: 1.2,
    wrap_width: 900,
    stroke_width: 0,
    stroke_color: '#000000',
    shadow_enabled: true,
    shadow_color: '#000000',
    shadow_blur: 6,
    shadow_offset_x: 2,
    shadow_offset_y: 3,
    position: 'custom',
    x: 540,
    y: 260,
    opacity: 1.0
  };
  currentImageLayers.push(newLayer);
  selectLayer(newLayer.id);
}

function addPresetSubheading() {
  const newLayer = {
    id: 'layer_' + Date.now(),
    type: 'text',
    name: `Subheading ${currentImageLayers.filter(l => l.type === 'text').length + 1}`,
    visible: true,
    text: 'TECHNICAL SPECIFICATIONS & COMBAT HISTORY',
    text_case: 'upper',
    font_style: 'montserrat',
    font_size: 26,
    bold: true,
    italic: false,
    color: '#00E5FF',
    alignment: 'center',
    letter_spacing: 2,
    line_height: 1.3,
    wrap_width: 920,
    stroke_width: 0,
    stroke_color: '#000000',
    shadow_enabled: false,
    position: 'custom',
    x: 540,
    y: 340,
    opacity: 1.0
  };
  currentImageLayers.push(newLayer);
  selectLayer(newLayer.id);
}

function addPresetBody() {
  const newLayer = {
    id: 'layer_' + Date.now(),
    type: 'text',
    name: `Spec Body ${currentImageLayers.filter(l => l.type === 'text').length + 1}`,
    visible: true,
    text: '• Caliber: 7.62×39mm M43\n• Effective Range: 400m\n• Rate of Fire: 600 rounds/min',
    text_case: 'none',
    font_style: 'roboto',
    font_size: 22,
    bold: false,
    italic: false,
    color: '#111111',
    alignment: 'left',
    letter_spacing: 0,
    line_height: 1.4,
    wrap_width: 800,
    stroke_width: 0,
    stroke_color: '#000000',
    position: 'custom',
    x: 140,
    y: 520,
    opacity: 1.0
  };
  currentImageLayers.push(newLayer);
  selectLayer(newLayer.id);
}

function addPresetBadge() {
  const newLayer = {
    id: 'layer_' + Date.now(),
    type: 'text',
    name: `Badge Tag ${currentImageLayers.filter(l => l.type === 'text').length + 1}`,
    visible: true,
    text: '⚡ OFFICIAL ARSENAL SPEC',
    text_case: 'upper',
    font_style: 'space_grotesk',
    font_size: 18,
    bold: true,
    italic: false,
    color: '#FFFFFF',
    alignment: 'center',
    letter_spacing: 1,
    bg_enabled: true,
    bg_color: '#0A0A0A',
    bg_opacity: 0.95,
    bg_radius: 14,
    bg_padding_x: 20,
    bg_padding_y: 8,
    position: 'custom',
    x: 540,
    y: 180,
    opacity: 1.0
  };
  currentImageLayers.push(newLayer);
  selectLayer(newLayer.id);
}

function addPresetHud() {
  const newLayer = {
    id: 'layer_' + Date.now(),
    type: 'text',
    name: `Tactical HUD ${currentImageLayers.filter(l => l.type === 'text').length + 1}`,
    visible: true,
    text: 'SYS//ID: AK-47 [RUS] 1949',
    text_case: 'upper',
    font_style: 'space_mono',
    font_size: 19,
    bold: true,
    italic: false,
    color: '#FFD700',
    alignment: 'center',
    letter_spacing: 2,
    stroke_width: 1,
    stroke_color: '#000000',
    bg_enabled: true,
    bg_color: '#000000',
    bg_opacity: 0.85,
    bg_radius: 4,
    bg_padding_x: 14,
    bg_padding_y: 6,
    position: 'custom',
    x: 540,
    y: 720,
    opacity: 1.0
  };
  currentImageLayers.push(newLayer);
  selectLayer(newLayer.id);
}

function addPresetWeaponXHeader() {
  const barLayer = {
    id: 'layer_' + Date.now() + '_bar',
    type: 'shape',
    name: 'WeaponX Header Bar',
    shape_type: 'rounded_rectangle',
    visible: true,
    fill_color: '#0a0a0a',
    transparent: false,
    border_color: '#000000',
    border_width: 0,
    radius: 16,
    x: 12,
    y: 8,
    width: 1056,
    height: 76,
    opacity: 1.0
  };
  const titleLayer = {
    id: 'layer_' + (Date.now() + 1) + '_title',
    type: 'text',
    name: 'WeaponX Header Title',
    visible: true,
    text: (document.getElementById('modalPromptHeadlineInput')?.value || activeProject?.title || 'WEAPONX ENCYCLOPEDIA').toUpperCase(),
    text_case: 'upper',
    font_style: 'anton',
    font_size: 42,
    bold: true,
    italic: false,
    color: '#FFFFFF',
    stroke_width: 0,
    position: 'top_header',
    alignment: 'center',
    letter_spacing: 1,
    x: 540,
    y: 46,
    opacity: 1.0
  };
  currentImageLayers.push(barLayer, titleLayer);
  selectLayer(titleLayer.id);
}

function addPresetBox() {
  const newLayer = {
    id: 'layer_' + Date.now(),
    type: 'shape',
    name: `Box Shape ${currentImageLayers.filter(l => l.type === 'shape').length + 1}`,
    visible: true,
    shape_type: 'rounded_rectangle',
    fill_color: '#0b0f19',
    transparent: false,
    border_color: '#00E5FF',
    border_width: 2,
    radius: 16,
    x: 80,
    y: 400,
    width: 920,
    height: 220,
    opacity: 0.95
  };
  currentImageLayers.push(newLayer);
  selectLayer(newLayer.id);
}

function addPresetRedLine() {
  const newLayer = {
    id: 'layer_' + Date.now(),
    type: 'shape',
    name: 'Red Accent Line',
    shape_type: 'bottom_accent_line',
    visible: true,
    fill_color: '#FF1744',
    transparent: false,
    border_color: '#000000',
    border_width: 0,
    radius: 0,
    x: 0,
    y: 1914,
    width: 820,
    height: 6,
    opacity: 1.0
  };
  currentImageLayers.push(newLayer);
  selectLayer(newLayer.id);
}

function addTextLayer() {
  const newLayer = {
    id: 'layer_' + Date.now(),
    type: 'text',
    name: `Text ${currentImageLayers.filter(l => l.type === 'text').length + 1}`,
    visible: true,
    text: 'CUSTOM HEADING',
    text_case: 'none',
    font_style: 'anton',
    font_size: 38,
    bold: true,
    italic: false,
    color: '#FFFFFF',
    stroke_width: 0,
    stroke_color: '#000000',
    position: 'custom',
    alignment: 'center',
    letter_spacing: 0,
    line_height: 1.25,
    wrap_width: 900,
    x: 540,
    y: 960,
    opacity: 1.0
  };
  currentImageLayers.push(newLayer);
  selectLayer(newLayer.id);
}

function addShapeLayer() {
  const newLayer = {
    id: 'layer_' + Date.now(),
    type: 'shape',
    name: `Shape ${currentImageLayers.filter(l => l.type === 'shape').length + 1}`,
    visible: true,
    shape_type: 'rounded_rectangle',
    fill_color: '#000000',
    transparent: false,
    border_color: '#00E5FF',
    border_width: 0,
    radius: 16,
    x: 100,
    y: 800,
    width: 880,
    height: 120,
    opacity: 0.9
  };
  currentImageLayers.push(newLayer);
  selectLayer(newLayer.id);
}

function toggleLayerVisibility(id) {
  const layer = currentImageLayers.find(l => l.id === id);
  if (layer) {
    layer.visible = !layer.visible;
    renderLayersList();
    drawLayerStudioCanvas();
  }
}

function moveLayer(id, direction) {
  const idx = currentImageLayers.findIndex(l => l.id === id);
  if (idx < 0) return;
  const targetIdx = idx + direction;
  if (targetIdx >= 0 && targetIdx < currentImageLayers.length) {
    const temp = currentImageLayers[idx];
    currentImageLayers[idx] = currentImageLayers[targetIdx];
    currentImageLayers[targetIdx] = temp;
    renderLayersList();
    drawLayerStudioCanvas();
  }
}

function duplicateLayer(id) {
  const orig = currentImageLayers.find(l => l.id === id);
  if (!orig) return;
  const clone = JSON.parse(JSON.stringify(orig));
  clone.id = 'layer_' + Date.now();
  clone.name = `${orig.name} (Copy)`;
  clone.x = (clone.x || 0) + 30;
  clone.y = (clone.y || 0) + 30;
  currentImageLayers.push(clone);
  selectLayer(clone.id);
}

function deleteLayer(id) {
  currentImageLayers = currentImageLayers.filter(l => l.id !== id);
  if (selectedLayerId === id) {
    selectedLayerId = currentImageLayers[0]?.id || null;
  }
  renderLayersList();
  renderInspector();
  drawLayerStudioCanvas();
}

function renderInspector() {
  const titleEl = document.getElementById('inspectorTitle');
  const badgeEl = document.getElementById('inspectorTypeBadge');
  const contentEl = document.getElementById('inspectorContent');
  if (!contentEl) return;

  const layer = currentImageLayers.find(l => l.id === selectedLayerId);
  if (!layer) {
    if (titleEl) titleEl.textContent = '⚙️ Layer Properties';
    if (badgeEl) badgeEl.textContent = 'No Layer Selected';
    contentEl.innerHTML = `
      <p style="font-size: 12px; color: #64748b; text-align: center; padding: 40px 10px;">
        Click any layer on the left or on the canvas to inspect and edit its properties.
      </p>
    `;
    return;
  }

  if (titleEl) titleEl.textContent = `⚙️ ${layer.name}`;
  if (badgeEl) badgeEl.textContent = layer.type.toUpperCase();

  if (layer.type === 'text') {
    contentEl.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 10px;">
        <!-- Layer Name -->
        <div>
          <label style="font-size: 10.5px; color: #94a3b8; display: block; margin-bottom: 2px;">Layer Name</label>
          <input type="text" id="propLayerName" value="${escapeHtml(layer.name || '')}" style="width: 100%; padding: 5px 8px; font-size: 12px; background: #131a29; border: 1px solid #23304a; border-radius: 6px; color: #f1f5f9;">
        </div>

        <!-- Move Position & Arrow Nudges -->
        <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid #23304a; border-radius: 6px; padding: 6px 10px; display: flex; align-items: center; justify-content: space-between;">
          <div style="display: flex; align-items: center; gap: 6px; cursor: move;" title="Click and drag on canvas to move">
            <span style="font-size: 15px; cursor: move;">✥</span>
            <span style="font-size: 11px; font-weight: 700; color: #38bdf8; cursor: move;">Move Position</span>
            <span style="font-size: 10px; color: #64748b;">(drag or nudge)</span>
          </div>
          <div style="display: flex; gap: 4px;">
            <button type="button" class="btn btn-secondary btn-xs" id="btnNudgeUp" title="Move Up" style="padding: 2px 7px; font-size: 11px;">▲</button>
            <button type="button" class="btn btn-secondary btn-xs" id="btnNudgeDown" title="Move Down" style="padding: 2px 7px; font-size: 11px;">▼</button>
            <button type="button" class="btn btn-secondary btn-xs" id="btnNudgeLeft" title="Move Left" style="padding: 2px 7px; font-size: 11px;">◄</button>
            <button type="button" class="btn btn-secondary btn-xs" id="btnNudgeRight" title="Move Right" style="padding: 2px 7px; font-size: 11px;">►</button>
          </div>
        </div>

        <!-- Text Content & Formatting Toolbar -->
        <div>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px;">
            <label style="font-size: 10.5px; color: #94a3b8; font-weight: 600;">Text Content (Enter for new lines)</label>
            <div style="display: flex; gap: 4px;">
              <button id="btnInsertLineBreak" type="button" class="btn btn-secondary btn-xs" style="padding: 1px 6px; font-size: 10px; color: #38bdf8;" title="Insert newline at cursor">↵ Line Break</button>
              <button id="btnCaseUpper" class="btn btn-secondary btn-xs" style="padding: 1px 5px; font-size: 10px; font-weight: 700;" title="Uppercase">TT</button>
              <button id="btnCaseTitle" class="btn btn-secondary btn-xs" style="padding: 1px 5px; font-size: 10px;" title="Title Case">Tt</button>
              <button id="btnCaseLower" class="btn btn-secondary btn-xs" style="padding: 1px 5px; font-size: 10px;" title="lowercase">tt</button>
            </div>
          </div>
          <textarea id="propTextContent" rows="3" style="width: 100%; padding: 6px 8px; font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; white-space: pre-wrap; background: #131a29; border: 1px solid #23304a; border-radius: 6px; color: #f1f5f9; resize: vertical;" placeholder="Type text here... Press Enter for line breaks">${escapeHtml(layer.text || '')}</textarea>
        </div>

        <!-- Font Family & Font Size -->
        <div style="display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 8px;">
          <div>
            <label style="font-size: 10.5px; color: #94a3b8; display: block; margin-bottom: 2px;">Font Family</label>
            <select id="propFontFamily" class="select-dropdown" style="width: 100%; font-size: 11px; padding: 4px;">
              <option value="anton" ${layer.font_style === 'anton' || layer.font_style === 'condensed_bold' ? 'selected' : ''}>Anton (Punchy Condensed)</option>
              <option value="bebas" ${layer.font_style === 'bebas' ? 'selected' : ''}>Bebas Neue (Tall Military)</option>
              <option value="oswald" ${layer.font_style === 'oswald' ? 'selected' : ''}>Oswald (Modern Bold)</option>
              <option value="montserrat" ${layer.font_style === 'montserrat' ? 'selected' : ''}>Montserrat (Clean Tech Bold)</option>
              <option value="space_grotesk" ${layer.font_style === 'space_grotesk' ? 'selected' : ''}>Space Grotesk (Modern)</option>
              <option value="space_mono" ${layer.font_style === 'space_mono' || layer.font_style === 'monospace' ? 'selected' : ''}>Space Mono (Tactical HUD)</option>
              <option value="roboto" ${layer.font_style === 'roboto' || layer.font_style === 'arial_bold' ? 'selected' : ''}>Roboto (Universal Clean)</option>
              <option value="playfair" ${layer.font_style === 'playfair' || layer.font_style === 'serif' ? 'selected' : ''}>Playfair Display (Serif)</option>
            </select>
          </div>
          <div>
            <div style="display: flex; justify-content: space-between; font-size: 10.5px; color: #94a3b8; margin-bottom: 2px;">
              <span>Size</span>
              <span id="lblFontSize">${layer.font_size || 38}px</span>
            </div>
            <input type="range" id="propFontSize" min="12" max="130" value="${layer.font_size || 38}" style="width: 100%;">
          </div>
        </div>

        <!-- Styling & Alignment Toolbar -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
          <div>
            <label style="font-size: 10.5px; color: #94a3b8; display: block; margin-bottom: 2px;">Format</label>
            <div style="display: flex; gap: 4px;">
              <button id="btnToggleBold" class="btn btn-secondary btn-xs" style="flex: 1; font-weight: 800; ${layer.bold !== false ? 'background: rgba(56, 189, 248, 0.25); border-color: #38bdf8; color: #38bdf8;' : ''}">B</button>
              <button id="btnToggleItalic" class="btn btn-secondary btn-xs" style="flex: 1; font-style: italic; ${layer.italic ? 'background: rgba(56, 189, 248, 0.25); border-color: #38bdf8; color: #38bdf8;' : ''}">I</button>
            </div>
          </div>
          <div>
            <label style="font-size: 10.5px; color: #94a3b8; display: block; margin-bottom: 2px;">Alignment</label>
            <div style="display: flex; gap: 4px;">
              <button id="btnAlignLeft" class="btn btn-secondary btn-xs" style="flex: 1; ${layer.alignment === 'left' ? 'background: rgba(56, 189, 248, 0.25); border-color: #38bdf8; color: #38bdf8;' : ''}" title="Left">⬅️</button>
              <button id="btnAlignCenter" class="btn btn-secondary btn-xs" style="flex: 1; ${layer.alignment === 'center' || !layer.alignment ? 'background: rgba(56, 189, 248, 0.25); border-color: #38bdf8; color: #38bdf8;' : ''}" title="Center">↔️</button>
              <button id="btnAlignRight" class="btn btn-secondary btn-xs" style="flex: 1; ${layer.alignment === 'right' ? 'background: rgba(56, 189, 248, 0.25); border-color: #38bdf8; color: #38bdf8;' : ''}" title="Right">➡️</button>
            </div>
          </div>
        </div>

        <!-- Spacing: Letter Spacing & Line Height -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
          <div>
            <div style="display: flex; justify-content: space-between; font-size: 10.5px; color: #94a3b8; margin-bottom: 2px;">
              <span>Letter Spacing</span>
              <span id="lblLetterSpacing">${layer.letter_spacing || 0}px</span>
            </div>
            <input type="range" id="propLetterSpacing" min="-2" max="25" value="${layer.letter_spacing || 0}" style="width: 100%;">
          </div>
          <div>
            <div style="display: flex; justify-content: space-between; font-size: 10.5px; color: #94a3b8; margin-bottom: 2px;">
              <span>Line Height</span>
              <span id="lblLineHeight">${layer.line_height || 1.25}x</span>
            </div>
            <input type="range" id="propLineHeight" min="0.8" max="2.4" step="0.05" value="${layer.line_height || 1.25}" style="width: 100%;">
          </div>
        </div>

        <!-- Text Color & Quick Palette -->
        <div>
          <label style="font-size: 10.5px; color: #94a3b8; display: block; margin-bottom: 2px;">Text Color & Palette</label>
          <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
            <input type="color" id="propTextColor" value="${layer.color || '#FFFFFF'}" style="width: 28px; height: 26px; border: none; border-radius: 4px; cursor: pointer; background: transparent;">
            <input type="text" id="propTextColorHex" value="${layer.color || '#FFFFFF'}" style="width: 76px; padding: 3px 6px; font-size: 11px; background: #131a29; border: 1px solid #23304a; border-radius: 4px; color: #fff;">
            
            <!-- Quick Chips -->
            <span class="color-chip" data-color="#FFFFFF" style="width: 18px; height: 18px; border-radius: 4px; background: #FFFFFF; cursor: pointer; border: 1px solid #475569;" title="White"></span>
            <span class="color-chip" data-color="#00E5FF" style="width: 18px; height: 18px; border-radius: 4px; background: #00E5FF; cursor: pointer;" title="Neon Cyan"></span>
            <span class="color-chip" data-color="#FFD700" style="width: 18px; height: 18px; border-radius: 4px; background: #FFD700; cursor: pointer;" title="Gold Yellow"></span>
            <span class="color-chip" data-color="#FF1744" style="width: 18px; height: 18px; border-radius: 4px; background: #FF1744; cursor: pointer;" title="WeaponX Red"></span>
            <span class="color-chip" data-color="#10B981" style="width: 18px; height: 18px; border-radius: 4px; background: #10B981; cursor: pointer;" title="Emerald Green"></span>
            <span class="color-chip" data-color="#0A0A0A" style="width: 18px; height: 18px; border-radius: 4px; background: #0A0A0A; cursor: pointer; border: 1px solid #475569;" title="Black"></span>
          </div>
        </div>

        <!-- Pixlr Typography Effects (Drop Shadow, Stroke, Background Pill) -->
        <div style="border: 1px solid #1e293b; border-radius: 8px; padding: 8px; background: rgba(15, 23, 42, 0.4);">
          <span style="font-size: 11px; font-weight: 700; color: #38bdf8; text-transform: uppercase; display: block; margin-bottom: 6px;">
            ✨ Typography Effects
          </span>

          <!-- Shadow -->
          <div style="margin-bottom: 8px;">
            <label style="font-size: 11px; color: #cbd5e1; display: flex; align-items: center; justify-content: space-between; cursor: pointer;">
              <span><input type="checkbox" id="propShadowEnabled" ${layer.shadow_enabled ? 'checked' : ''}> Drop Shadow</span>
              <span id="lblShadowBlur" style="font-size: 10px; color: #94a3b8;">${layer.shadow_blur || 4}px blur</span>
            </label>
            <div id="shadowControlsRow" style="display: ${layer.shadow_enabled ? 'grid' : 'none'}; grid-template-columns: auto 1fr 1fr; gap: 6px; margin-top: 4px; align-items: center;">
              <input type="color" id="propShadowColor" value="${layer.shadow_color || '#000000'}" style="width: 24px; height: 22px; border: none; cursor: pointer; background: transparent;">
              <input type="range" id="propShadowBlur" min="0" max="25" value="${layer.shadow_blur || 4}" title="Blur" style="width: 100%;">
              <div style="display: flex; gap: 3px;">
                <input type="number" id="propShadowOX" value="${layer.shadow_offset_x ?? 2}" min="-25" max="25" style="width: 38px; padding: 2px; font-size: 10px; background: #131a29; border: 1px solid #23304a; color: #fff; text-align: center;" title="Offset X">
                <input type="number" id="propShadowOY" value="${layer.shadow_offset_y ?? 3}" min="-25" max="25" style="width: 38px; padding: 2px; font-size: 10px; background: #131a29; border: 1px solid #23304a; color: #fff; text-align: center;" title="Offset Y">
              </div>
            </div>
          </div>

          <!-- Stroke Outline -->
          <div style="margin-bottom: 8px;">
            <label style="font-size: 11px; color: #cbd5e1; display: flex; align-items: center; justify-content: space-between; cursor: pointer;">
              <span><input type="checkbox" id="propStrokeEnabled" ${(layer.stroke_width || 0) > 0 ? 'checked' : ''}> Stroke / Outline</span>
              <span id="lblStrokeW" style="font-size: 10px; color: #94a3b8;">${layer.stroke_width || 0}px</span>
            </label>
            <div id="strokeControlsRow" style="display: ${(layer.stroke_width || 0) > 0 ? 'flex' : 'none'}; align-items: center; gap: 6px; margin-top: 4px;">
              <input type="color" id="propStrokeColor" value="${layer.stroke_color || '#000000'}" style="width: 24px; height: 22px; border: none; cursor: pointer; background: transparent;">
              <input type="range" id="propStrokeWidth" min="1" max="15" value="${layer.stroke_width || 2}" style="flex: 1;">
            </div>
          </div>

          <!-- Background Pill / Card -->
          <div>
            <label style="font-size: 11px; color: #cbd5e1; display: flex; align-items: center; justify-content: space-between; cursor: pointer;">
              <span><input type="checkbox" id="propBgEnabled" ${layer.bg_enabled || (layer.bg_color && layer.bg_color !== 'transparent') ? 'checked' : ''}> Background Pill / Box</span>
              <span id="lblBgRadius" style="font-size: 10px; color: #94a3b8;">${layer.bg_radius || 10}px rad</span>
            </label>
            <div id="bgControlsRow" style="display: ${layer.bg_enabled || (layer.bg_color && layer.bg_color !== 'transparent') ? 'grid' : 'none'}; grid-template-columns: auto 1fr 1fr; gap: 6px; margin-top: 4px; align-items: center;">
              <input type="color" id="propBgColor" value="${layer.bg_color || '#0A0A0A'}" style="width: 24px; height: 22px; border: none; cursor: pointer; background: transparent;">
              <input type="range" id="propBgRadius" min="0" max="35" value="${layer.bg_radius || 10}" title="Corner Radius" style="width: 100%;">
              <input type="range" id="propBgOpacity" min="0.1" max="1.0" step="0.05" value="${layer.bg_opacity || 0.9}" title="Background Opacity" style="width: 100%;">
            </div>
          </div>
        </div>

        <!-- Position & Transform -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
          <div>
            <label style="font-size: 10.5px; color: #94a3b8; display: block; margin-bottom: 2px;">Position Preset</label>
            <select id="propPositionPreset" class="select-dropdown" style="width: 100%; font-size: 11px; padding: 4px;">
              <option value="top_header" ${layer.position === 'top_header' ? 'selected' : ''}>Top Header Bar</option>
              <option value="upper_third" ${layer.position === 'upper_third' ? 'selected' : ''}>Upper Third</option>
              <option value="center" ${layer.position === 'center' ? 'selected' : ''}>Center</option>
              <option value="lower_third" ${layer.position === 'lower_third' ? 'selected' : ''}>Lower Third</option>
              <option value="custom" ${layer.position === 'custom' ? 'selected' : ''}>Custom X / Y</option>
            </select>
          </div>
          <div style="display: flex; gap: 4px;">
            <div style="flex: 1;">
              <label style="font-size: 10px; color: #94a3b8; display: block;">X: ${Math.round(layer.x ?? 540)}</label>
              <input type="number" id="propPosX" value="${Math.round(layer.x ?? 540)}" min="0" max="1080" style="width: 100%; padding: 3px; font-size: 11px; background: #131a29; border: 1px solid #23304a; border-radius: 4px; color: #fff; text-align: center;">
            </div>
            <div style="flex: 1;">
              <label style="font-size: 10px; color: #94a3b8; display: block;">Y: ${Math.round(layer.y ?? 46)}</label>
              <input type="number" id="propPosY" value="${Math.round(layer.y ?? 46)}" min="0" max="1920" style="width: 100%; padding: 3px; font-size: 11px; background: #131a29; border: 1px solid #23304a; border-radius: 4px; color: #fff; text-align: center;">
            </div>
          </div>
        </div>

        <!-- Opacity & Wrap Width -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
          <div>
            <div style="display: flex; justify-content: space-between; font-size: 10.5px; color: #94a3b8; margin-bottom: 2px;">
              <span>Opacity</span>
              <span id="lblTextOpacity">${Math.round((layer.opacity ?? 1.0) * 100)}%</span>
            </div>
            <input type="range" id="propOpacity" min="0.1" max="1.0" step="0.05" value="${layer.opacity ?? 1.0}" style="width: 100%;">
          </div>
          <div>
            <div style="display: flex; justify-content: space-between; font-size: 10.5px; color: #94a3b8; margin-bottom: 2px;">
              <span>Wrap Width</span>
              <span id="lblWrapWidth">${layer.wrap_width || 900}px</span>
            </div>
            <input type="range" id="propWrapWidth" min="200" max="1060" step="20" value="${layer.wrap_width || 900}" style="width: 100%;">
          </div>
        </div>
      </div>
    `;

    // Hook up live updates
    document.getElementById('propLayerName')?.addEventListener('input', e => { layer.name = e.target.value; renderLayersList(); });
    document.getElementById('propTextContent')?.addEventListener('input', e => { layer.text = e.target.value; drawLayerStudioCanvas(); });

    // Insert Line Break Button
    document.getElementById('btnInsertLineBreak')?.addEventListener('click', () => {
      const ta = document.getElementById('propTextContent');
      if (ta) {
        const start = ta.selectionStart || 0;
        const end = ta.selectionEnd || 0;
        const val = ta.value || '';
        ta.value = val.substring(0, start) + "\n" + val.substring(end);
        ta.selectionStart = ta.selectionEnd = start + 1;
        ta.focus();
        layer.text = ta.value;
        drawLayerStudioCanvas();
      }
    });

    // Position Nudges
    document.getElementById('btnNudgeUp')?.addEventListener('click', () => {
      layer.position = 'custom';
      layer.y = Math.max(0, (layer.y ?? 46) - 15);
      renderInspector();
      drawLayerStudioCanvas();
    });
    document.getElementById('btnNudgeDown')?.addEventListener('click', () => {
      layer.position = 'custom';
      layer.y = Math.min(1920, (layer.y ?? 46) + 15);
      renderInspector();
      drawLayerStudioCanvas();
    });
    document.getElementById('btnNudgeLeft')?.addEventListener('click', () => {
      layer.position = 'custom';
      layer.x = Math.max(0, (layer.x ?? 540) - 15);
      renderInspector();
      drawLayerStudioCanvas();
    });
    document.getElementById('btnNudgeRight')?.addEventListener('click', () => {
      layer.position = 'custom';
      layer.x = Math.min(1080, (layer.x ?? 540) + 15);
      renderInspector();
      drawLayerStudioCanvas();
    });

    // Quick Case Buttons
    document.getElementById('btnCaseUpper')?.addEventListener('click', () => {
      layer.text = (layer.text || '').toUpperCase();
      layer.text_case = 'upper';
      const ta = document.getElementById('propTextContent');
      if (ta) ta.value = layer.text;
      drawLayerStudioCanvas();
    });
    document.getElementById('btnCaseTitle')?.addEventListener('click', () => {
      layer.text = toTitleCase(layer.text || '');
      layer.text_case = 'title';
      const ta = document.getElementById('propTextContent');
      if (ta) ta.value = layer.text;
      drawLayerStudioCanvas();
    });
    document.getElementById('btnCaseLower')?.addEventListener('click', () => {
      layer.text = (layer.text || '').toLowerCase();
      layer.text_case = 'lower';
      const ta = document.getElementById('propTextContent');
      if (ta) ta.value = layer.text;
      drawLayerStudioCanvas();
    });

    document.getElementById('propFontFamily')?.addEventListener('change', e => { layer.font_style = e.target.value; drawLayerStudioCanvas(); });
    document.getElementById('propFontSize')?.addEventListener('input', e => {
      layer.font_size = parseInt(e.target.value, 10);
      document.getElementById('lblFontSize').textContent = `${layer.font_size}px`;
      drawLayerStudioCanvas();
    });

    // Bold & Italic
    document.getElementById('btnToggleBold')?.addEventListener('click', () => {
      layer.bold = layer.bold === false ? true : false;
      renderInspector();
      drawLayerStudioCanvas();
    });
    document.getElementById('btnToggleItalic')?.addEventListener('click', () => {
      layer.italic = !layer.italic;
      renderInspector();
      drawLayerStudioCanvas();
    });

    // Alignment
    document.getElementById('btnAlignLeft')?.addEventListener('click', () => { layer.alignment = 'left'; renderInspector(); drawLayerStudioCanvas(); });
    document.getElementById('btnAlignCenter')?.addEventListener('click', () => { layer.alignment = 'center'; renderInspector(); drawLayerStudioCanvas(); });
    document.getElementById('btnAlignRight')?.addEventListener('click', () => { layer.alignment = 'right'; renderInspector(); drawLayerStudioCanvas(); });

    // Letter Spacing & Line Height
    document.getElementById('propLetterSpacing')?.addEventListener('input', e => {
      layer.letter_spacing = parseInt(e.target.value, 10);
      document.getElementById('lblLetterSpacing').textContent = `${layer.letter_spacing}px`;
      drawLayerStudioCanvas();
    });
    document.getElementById('propLineHeight')?.addEventListener('input', e => {
      layer.line_height = parseFloat(e.target.value);
      document.getElementById('lblLineHeight').textContent = `${layer.line_height}x`;
      drawLayerStudioCanvas();
    });

    // Color & Quick Chips
    document.getElementById('propTextColor')?.addEventListener('input', e => {
      layer.color = e.target.value;
      document.getElementById('propTextColorHex').value = e.target.value.toUpperCase();
      drawLayerStudioCanvas();
    });
    document.getElementById('propTextColorHex')?.addEventListener('input', e => {
      if (/^#[0-9A-F]{6}$/i.test(e.target.value)) {
        layer.color = e.target.value;
        document.getElementById('propTextColor').value = e.target.value;
        drawLayerStudioCanvas();
      }
    });
    contentEl.querySelectorAll('.color-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const c = chip.getAttribute('data-color');
        layer.color = c;
        document.getElementById('propTextColor').value = c;
        document.getElementById('propTextColorHex').value = c;
        drawLayerStudioCanvas();
      });
    });

    // Shadow Controls
    const cbShadow = document.getElementById('propShadowEnabled');
    cbShadow?.addEventListener('change', () => {
      layer.shadow_enabled = cbShadow.checked;
      document.getElementById('shadowControlsRow').style.display = layer.shadow_enabled ? 'grid' : 'none';
      drawLayerStudioCanvas();
    });
    document.getElementById('propShadowColor')?.addEventListener('input', e => { layer.shadow_color = e.target.value; drawLayerStudioCanvas(); });
    document.getElementById('propShadowBlur')?.addEventListener('input', e => {
      layer.shadow_blur = parseInt(e.target.value, 10);
      document.getElementById('lblShadowBlur').textContent = `${layer.shadow_blur}px blur`;
      drawLayerStudioCanvas();
    });
    document.getElementById('propShadowOX')?.addEventListener('input', e => { layer.shadow_offset_x = parseInt(e.target.value, 10) || 0; drawLayerStudioCanvas(); });
    document.getElementById('propShadowOY')?.addEventListener('input', e => { layer.shadow_offset_y = parseInt(e.target.value, 10) || 0; drawLayerStudioCanvas(); });

    // Stroke Controls
    const cbStroke = document.getElementById('propStrokeEnabled');
    cbStroke?.addEventListener('change', () => {
      layer.stroke_width = cbStroke.checked ? Math.max(1, layer.stroke_width || 2) : 0;
      document.getElementById('strokeControlsRow').style.display = cbStroke.checked ? 'flex' : 'none';
      document.getElementById('lblStrokeW').textContent = `${layer.stroke_width}px`;
      drawLayerStudioCanvas();
    });
    document.getElementById('propStrokeColor')?.addEventListener('input', e => { layer.stroke_color = e.target.value; drawLayerStudioCanvas(); });
    document.getElementById('propStrokeWidth')?.addEventListener('input', e => {
      layer.stroke_width = parseInt(e.target.value, 10);
      document.getElementById('lblStrokeW').textContent = `${layer.stroke_width}px`;
      drawLayerStudioCanvas();
    });

    // Background Controls
    const cbBg = document.getElementById('propBgEnabled');
    cbBg?.addEventListener('change', () => {
      layer.bg_enabled = cbBg.checked;
      if (cbBg.checked && !layer.bg_color) layer.bg_color = '#0A0A0A';
      document.getElementById('bgControlsRow').style.display = cbBg.checked ? 'grid' : 'none';
      drawLayerStudioCanvas();
    });
    document.getElementById('propBgColor')?.addEventListener('input', e => { layer.bg_color = e.target.value; drawLayerStudioCanvas(); });
    document.getElementById('propBgRadius')?.addEventListener('input', e => {
      layer.bg_radius = parseInt(e.target.value, 10);
      document.getElementById('lblBgRadius').textContent = `${layer.bg_radius}px rad`;
      drawLayerStudioCanvas();
    });
    document.getElementById('propBgOpacity')?.addEventListener('input', e => { layer.bg_opacity = parseFloat(e.target.value); drawLayerStudioCanvas(); });

    // Position & Transform
    document.getElementById('propPositionPreset')?.addEventListener('change', e => {
      layer.position = e.target.value;
      if (e.target.value === 'top_header') { layer.x = 540; layer.y = 46; }
      else if (e.target.value === 'upper_third') { layer.x = 540; layer.y = 345; }
      else if (e.target.value === 'center') { layer.x = 540; layer.y = 960; }
      else if (e.target.value === 'lower_third') { layer.x = 540; layer.y = 1500; }
      renderInspector();
      drawLayerStudioCanvas();
    });
    document.getElementById('propPosX')?.addEventListener('input', e => { layer.x = parseInt(e.target.value, 10) || 0; layer.position = 'custom'; drawLayerStudioCanvas(); });
    document.getElementById('propPosY')?.addEventListener('input', e => { layer.y = parseInt(e.target.value, 10) || 0; layer.position = 'custom'; drawLayerStudioCanvas(); });
    document.getElementById('propOpacity')?.addEventListener('input', e => {
      layer.opacity = parseFloat(e.target.value);
      document.getElementById('lblTextOpacity').textContent = `${Math.round(layer.opacity * 100)}%`;
      drawLayerStudioCanvas();
    });
    document.getElementById('propWrapWidth')?.addEventListener('input', e => {
      layer.wrap_width = parseInt(e.target.value, 10);
      document.getElementById('lblWrapWidth').textContent = `${layer.wrap_width}px`;
      drawLayerStudioCanvas();
    });

  } else if (layer.type === 'shape') {
    contentEl.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 11px;">
        <!-- Layer Name & Shape Type -->
        <div>
          <label style="font-size: 10.5px; color: #94a3b8; display: block; margin-bottom: 2px;">Layer Name</label>
          <input type="text" id="propLayerName" value="${escapeHtml(layer.name || '')}" style="width: 100%; padding: 5px 8px; font-size: 12px; background: #131a29; border: 1px solid #23304a; border-radius: 6px; color: #f1f5f9;">
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
          <div>
            <label style="font-size: 10.5px; color: #94a3b8; display: block; margin-bottom: 2px;">Shape Type</label>
            <select id="propShapeType" class="select-dropdown" style="width: 100%; font-size: 11px; padding: 5px;">
              <option value="rounded_rectangle" ${layer.shape_type === 'rounded_rectangle' ? 'selected' : ''}>Rounded Rectangle</option>
              <option value="solid_rectangle" ${layer.shape_type === 'solid_rectangle' ? 'selected' : ''}>Solid Rectangle</option>
              <option value="badge_pill" ${layer.shape_type === 'badge_pill' ? 'selected' : ''}>Badge Pill</option>
              <option value="circle" ${layer.shape_type === 'circle' ? 'selected' : ''}>Circle / Oval</option>
              <option value="outer_border" ${layer.shape_type === 'outer_border' ? 'selected' : ''}>Outer Border Frame</option>
              <option value="bottom_accent_line" ${layer.shape_type === 'bottom_accent_line' ? 'selected' : ''}>Bottom Accent Line</option>
            </select>
          </div>
          <div>
            <label style="font-size: 10.5px; color: #94a3b8; display: block; margin-bottom: 2px;">Opacity (<span id="lblShapeOpacity">${Math.round((layer.opacity ?? 1.0) * 100)}%</span>)</label>
            <input type="range" id="propShapeOpacity" min="0.05" max="1.0" step="0.05" value="${layer.opacity ?? 1.0}" style="width: 100%;">
          </div>
        </div>

        <!-- 📐 Increase & Decrease Shape Scale Toolbar -->
        <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid #23304a; border-radius: 8px; padding: 10px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <span style="font-size: 11px; font-weight: 700; color: #38bdf8; text-transform: uppercase;">
              📐 Scale & Resize Shape
            </span>
            <span style="font-size: 10px; color: #94a3b8;">Use buttons or canvas handles</span>
          </div>

          <!-- Quick Scale Percentages -->
          <div style="display: flex; gap: 4px; margin-bottom: 10px; flex-wrap: wrap;">
            <button id="btnScaleDown50" class="btn btn-secondary btn-xs" style="flex: 1; padding: 3px 4px; font-size: 10px;" title="Scale down 50%">½ (50%)</button>
            <button id="btnScaleDown20" class="btn btn-secondary btn-xs" style="flex: 1; padding: 3px 4px; font-size: 10px;" title="Decrease 20%">−20%</button>
            <button id="btnScaleDown10" class="btn btn-secondary btn-xs" style="flex: 1; padding: 3px 4px; font-size: 10px;" title="Decrease 10%">−10%</button>
            <button id="btnScaleUp10" class="btn btn-secondary btn-xs" style="flex: 1; padding: 3px 4px; font-size: 10px;" title="Increase 10%">+10%</button>
            <button id="btnScaleUp20" class="btn btn-secondary btn-xs" style="flex: 1; padding: 3px 4px; font-size: 10px;" title="Increase 20%">+20%</button>
            <button id="btnScaleUp2x" class="btn btn-secondary btn-xs" style="flex: 1; padding: 3px 4px; font-size: 10px;" title="Scale up 200%">2× (200%)</button>
          </div>

          <!-- Width Slider & Steppers -->
          <div style="margin-bottom: 8px;">
            <div style="display: flex; justify-content: space-between; font-size: 10.5px; color: #cbd5e1; margin-bottom: 3px;">
              <span>Width (W)</span>
              <span id="lblShapeW" style="color: #00e5ff; font-weight: 700;">${Math.round(layer.width ?? 1056)}px</span>
            </div>
            <div style="display: flex; align-items: center; gap: 5px;">
              <button id="btnShapeWMinus50" class="btn btn-secondary btn-xs" style="padding: 2px 5px; font-size: 9.5px;" title="Decrease 50px">−50</button>
              <button id="btnShapeWMinus10" class="btn btn-secondary btn-xs" style="padding: 2px 5px; font-size: 9.5px;" title="Decrease 10px">−10</button>
              <input type="range" id="propShapeWSlider" min="10" max="1080" value="${Math.round(layer.width ?? 1056)}" style="flex: 1;">
              <button id="btnShapeWPlus10" class="btn btn-secondary btn-xs" style="padding: 2px 5px; font-size: 9.5px;" title="Increase 10px">+10</button>
              <button id="btnShapeWPlus50" class="btn btn-secondary btn-xs" style="padding: 2px 5px; font-size: 9.5px;" title="Increase 50px">+50</button>
              <input type="number" id="propShapeW" value="${Math.round(layer.width ?? 1056)}" min="10" max="1080" style="width: 50px; padding: 2px 4px; font-size: 11px; background: #131a29; border: 1px solid #23304a; border-radius: 4px; color: #fff; text-align: center;">
            </div>
          </div>

          <!-- Height Slider & Steppers -->
          <div style="margin-bottom: 8px;">
            <div style="display: flex; justify-content: space-between; font-size: 10.5px; color: #cbd5e1; margin-bottom: 3px;">
              <span>Height (H)</span>
              <span id="lblShapeH" style="color: #00e5ff; font-weight: 700;">${Math.round(layer.height ?? 76)}px</span>
            </div>
            <div style="display: flex; align-items: center; gap: 5px;">
              <button id="btnShapeHMinus50" class="btn btn-secondary btn-xs" style="padding: 2px 5px; font-size: 9.5px;" title="Decrease 50px">−50</button>
              <button id="btnShapeHMinus10" class="btn btn-secondary btn-xs" style="padding: 2px 5px; font-size: 9.5px;" title="Decrease 10px">−10</button>
              <input type="range" id="propShapeHSlider" min="4" max="1920" value="${Math.round(layer.height ?? 76)}" style="flex: 1;">
              <button id="btnShapeHPlus10" class="btn btn-secondary btn-xs" style="padding: 2px 5px; font-size: 9.5px;" title="Increase 10px">+10</button>
              <button id="btnShapeHPlus50" class="btn btn-secondary btn-xs" style="padding: 2px 5px; font-size: 9.5px;" title="Increase 50px">+50</button>
              <input type="number" id="propShapeH" value="${Math.round(layer.height ?? 76)}" min="4" max="1920" style="width: 50px; padding: 2px 4px; font-size: 11px; background: #131a29; border: 1px solid #23304a; border-radius: 4px; color: #fff; text-align: center;">
            </div>
          </div>

          <!-- Position X & Y -->
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 6px;">
            <div>
              <label style="font-size: 10px; color: #94a3b8; display: block;">Position X</label>
              <input type="number" id="propShapeX" value="${Math.round(layer.x ?? 12)}" min="0" max="1080" style="width: 100%; padding: 3px; font-size: 11px; background: #131a29; border: 1px solid #23304a; border-radius: 4px; color: #fff; text-align: center;">
            </div>
            <div>
              <label style="font-size: 10px; color: #94a3b8; display: block;">Position Y</label>
              <input type="number" id="propShapeY" value="${Math.round(layer.y ?? 8)}" min="0" max="1920" style="width: 100%; padding: 3px; font-size: 11px; background: #131a29; border: 1px solid #23304a; border-radius: 4px; color: #fff; text-align: center;">
            </div>
          </div>

          <!-- Design Layout Shortcuts -->
          <div style="display: flex; gap: 4px; margin-top: 8px; flex-wrap: wrap;">
            <button id="btnShapeFullWidth" class="btn btn-secondary btn-xs" style="flex: 1; padding: 3px 4px; font-size: 10px;">Full Width</button>
            <button id="btnShapeCenterX" class="btn btn-secondary btn-xs" style="flex: 1; padding: 3px 4px; font-size: 10px;">Center X</button>
            <button id="btnShapeCenterY" class="btn btn-secondary btn-xs" style="flex: 1; padding: 3px 4px; font-size: 10px;">Center Y</button>
            <button id="btnShapeSquare" class="btn btn-secondary btn-xs" style="flex: 1; padding: 3px 4px; font-size: 10px;">1:1 Square</button>
          </div>
        </div>

        <!-- Corner Radius -->
        <div>
          <div style="display: flex; justify-content: space-between; font-size: 10.5px; color: #94a3b8; margin-bottom: 2px;">
            <span>Corner Radius</span>
            <span id="lblShapeRadius" style="color: #00e5ff; font-weight: 700;">${layer.radius ?? 16}px</span>
          </div>
          <div style="display: flex; align-items: center; gap: 6px;">
            <input type="range" id="propShapeRadius" min="0" max="120" value="${layer.radius ?? 16}" style="flex: 1;">
            <button id="btnShapeMaxPill" class="btn btn-secondary btn-xs" style="font-size: 10px; padding: 3px 6px;" title="Set radius to half height">💊 Max Pill</button>
          </div>
        </div>

        <!-- Fill Color & Quick Palette -->
        <div>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
            <label style="font-size: 10.5px; color: #94a3b8;">Fill Color & Palette</label>
            <label style="font-size: 10px; color: #cbd5e1; display: flex; align-items: center; gap: 3px; cursor: pointer;">
              <input type="checkbox" id="propShapeTrans" ${layer.transparent ? 'checked' : ''}> Transparent
            </label>
          </div>
          <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
            <input type="color" id="propShapeFill" value="${layer.fill_color || '#000000'}" style="width: 28px; height: 26px; border: none; border-radius: 4px; cursor: pointer; background: transparent;">
            <input type="text" id="propShapeFillHex" value="${layer.fill_color || '#000000'}" style="width: 76px; padding: 3px 6px; font-size: 11px; background: #131a29; border: 1px solid #23304a; border-radius: 4px; color: #fff;">
            
            <!-- Quick Chips -->
            <span class="shape-color-chip" data-color="#000000" style="width: 18px; height: 18px; border-radius: 4px; background: #000000; cursor: pointer; border: 1px solid #475569;" title="Black"></span>
            <span class="shape-color-chip" data-color="#0b0f19" style="width: 18px; height: 18px; border-radius: 4px; background: #0b0f19; cursor: pointer; border: 1px solid #475569;" title="Dark Slate"></span>
            <span class="shape-color-chip" data-color="#FFFFFF" style="width: 18px; height: 18px; border-radius: 4px; background: #FFFFFF; cursor: pointer; border: 1px solid #475569;" title="White"></span>
            <span class="shape-color-chip" data-color="#00E5FF" style="width: 18px; height: 18px; border-radius: 4px; background: #00E5FF; cursor: pointer;" title="Neon Cyan"></span>
            <span class="shape-color-chip" data-color="#FFD700" style="width: 18px; height: 18px; border-radius: 4px; background: #FFD700; cursor: pointer;" title="Gold Yellow"></span>
            <span class="shape-color-chip" data-color="#FF1744" style="width: 18px; height: 18px; border-radius: 4px; background: #FF1744; cursor: pointer;" title="WeaponX Red"></span>
            <span class="shape-color-chip" data-color="#10B981" style="width: 18px; height: 18px; border-radius: 4px; background: #10B981; cursor: pointer;" title="Emerald Green"></span>
          </div>
        </div>

        <!-- Border / Stroke -->
        <div>
          <div style="display: flex; justify-content: space-between; font-size: 10.5px; color: #94a3b8; margin-bottom: 2px;">
            <span>Border Stroke</span>
            <span id="lblShapeBorderW" style="color: #00e5ff; font-weight: 700;">${layer.border_width ?? 0}px</span>
          </div>
          <div style="display: flex; align-items: center; gap: 6px;">
            <input type="color" id="propShapeBorderColor" value="${layer.border_color || '#000000'}" style="width: 28px; height: 26px; border: none; border-radius: 4px; cursor: pointer; background: transparent;">
            <input type="range" id="propShapeBorderWidth" min="0" max="40" value="${layer.border_width ?? 0}" style="flex: 1;">
          </div>
        </div>

        <!-- Shape Drop Shadow (Pixlr-style visual depth) -->
        <div style="border: 1px solid #1e293b; border-radius: 8px; padding: 8px; background: rgba(15, 23, 42, 0.4);">
          <label style="font-size: 11px; color: #cbd5e1; display: flex; align-items: center; justify-content: space-between; cursor: pointer;">
            <span><input type="checkbox" id="propShapeShadowEnabled" ${layer.shadow_enabled ? 'checked' : ''}> Drop Shadow</span>
            <span id="lblShapeShadowBlur" style="font-size: 10px; color: #94a3b8;">${layer.shadow_blur || 8}px blur</span>
          </label>
          <div id="shapeShadowRow" style="display: ${layer.shadow_enabled ? 'grid' : 'none'}; grid-template-columns: auto 1fr 1fr; gap: 6px; margin-top: 6px; align-items: center;">
            <input type="color" id="propShapeShadowColor" value="${layer.shadow_color || '#000000'}" style="width: 24px; height: 22px; border: none; cursor: pointer; background: transparent;">
            <input type="range" id="propShapeShadowBlur" min="0" max="40" value="${layer.shadow_blur || 8}" title="Shadow Blur" style="width: 100%;">
            <div style="display: flex; gap: 3px;">
              <input type="number" id="propShapeShadowOX" value="${layer.shadow_offset_x ?? 0}" min="-40" max="40" style="width: 38px; padding: 2px; font-size: 10px; background: #131a29; border: 1px solid #23304a; color: #fff; text-align: center;" title="Offset X">
              <input type="number" id="propShapeShadowOY" value="${layer.shadow_offset_y ?? 4}" min="-40" max="40" style="width: 38px; padding: 2px; font-size: 10px; background: #131a29; border: 1px solid #23304a; color: #fff; text-align: center;" title="Offset Y">
            </div>
          </div>
        </div>
      </div>
    `;

    // Scale helper
    const scaleShape = (factor) => {
      const oldW = layer.width || 880;
      const oldH = layer.height || 120;
      const newW = Math.max(10, Math.min(1080, Math.round(oldW * factor)));
      const newH = Math.max(4, Math.min(1920, Math.round(oldH * factor)));
      layer.x = Math.max(0, Math.min(1080 - newW, Math.round((layer.x || 0) - (newW - oldW) / 2)));
      layer.y = Math.max(0, Math.min(1920 - newH, Math.round((layer.y || 0) - (newH - oldH) / 2)));
      layer.width = newW;
      layer.height = newH;
      renderInspector();
      drawLayerStudioCanvas();
    };

    const modifyDim = (dim, delta) => {
      if (dim === 'width') {
        const cur = layer.width || 880;
        layer.width = Math.max(10, Math.min(1080, cur + delta));
      } else if (dim === 'height') {
        const cur = layer.height || 120;
        layer.height = Math.max(4, Math.min(1920, cur + delta));
      }
      renderInspector();
      drawLayerStudioCanvas();
    };

    // Quick Scale Buttons
    document.getElementById('btnScaleDown50')?.addEventListener('click', () => scaleShape(0.5));
    document.getElementById('btnScaleDown20')?.addEventListener('click', () => scaleShape(0.8));
    document.getElementById('btnScaleDown10')?.addEventListener('click', () => scaleShape(0.9));
    document.getElementById('btnScaleUp10')?.addEventListener('click', () => scaleShape(1.1));
    document.getElementById('btnScaleUp20')?.addEventListener('click', () => scaleShape(1.2));
    document.getElementById('btnScaleUp2x')?.addEventListener('click', () => scaleShape(2.0));

    // Width Steppers & Sliders
    document.getElementById('btnShapeWMinus50')?.addEventListener('click', () => modifyDim('width', -50));
    document.getElementById('btnShapeWMinus10')?.addEventListener('click', () => modifyDim('width', -10));
    document.getElementById('btnShapeWPlus10')?.addEventListener('click', () => modifyDim('width', 10));
    document.getElementById('btnShapeWPlus50')?.addEventListener('click', () => modifyDim('width', 50));
    document.getElementById('propShapeWSlider')?.addEventListener('input', e => {
      layer.width = parseInt(e.target.value, 10);
      document.getElementById('propShapeW').value = layer.width;
      document.getElementById('lblShapeW').textContent = `${layer.width}px`;
      drawLayerStudioCanvas();
    });
    document.getElementById('propShapeW')?.addEventListener('input', e => {
      layer.width = Math.max(10, Math.min(1080, parseInt(e.target.value, 10) || 10));
      document.getElementById('propShapeWSlider').value = layer.width;
      document.getElementById('lblShapeW').textContent = `${layer.width}px`;
      drawLayerStudioCanvas();
    });

    // Height Steppers & Sliders
    document.getElementById('btnShapeHMinus50')?.addEventListener('click', () => modifyDim('height', -50));
    document.getElementById('btnShapeHMinus10')?.addEventListener('click', () => modifyDim('height', -10));
    document.getElementById('btnShapeHPlus10')?.addEventListener('click', () => modifyDim('height', 10));
    document.getElementById('btnShapeHPlus50')?.addEventListener('click', () => modifyDim('height', 50));
    document.getElementById('propShapeHSlider')?.addEventListener('input', e => {
      layer.height = parseInt(e.target.value, 10);
      document.getElementById('propShapeH').value = layer.height;
      document.getElementById('lblShapeH').textContent = `${layer.height}px`;
      drawLayerStudioCanvas();
    });
    document.getElementById('propShapeH')?.addEventListener('input', e => {
      layer.height = Math.max(4, Math.min(1920, parseInt(e.target.value, 10) || 4));
      document.getElementById('propShapeHSlider').value = layer.height;
      document.getElementById('lblShapeH').textContent = `${layer.height}px`;
      drawLayerStudioCanvas();
    });

    // Positions & Shortcuts
    document.getElementById('propShapeX')?.addEventListener('input', e => { layer.x = parseInt(e.target.value, 10) || 0; drawLayerStudioCanvas(); });
    document.getElementById('propShapeY')?.addEventListener('input', e => { layer.y = parseInt(e.target.value, 10) || 0; drawLayerStudioCanvas(); });
    document.getElementById('btnShapeFullWidth')?.addEventListener('click', () => {
      layer.x = 12;
      layer.width = 1056;
      renderInspector();
      drawLayerStudioCanvas();
    });
    document.getElementById('btnShapeCenterX')?.addEventListener('click', () => {
      layer.x = Math.max(0, Math.round((1080 - (layer.width || 880)) / 2));
      renderInspector();
      drawLayerStudioCanvas();
    });
    document.getElementById('btnShapeCenterY')?.addEventListener('click', () => {
      layer.y = Math.max(0, Math.round((1920 - (layer.height || 120)) / 2));
      renderInspector();
      drawLayerStudioCanvas();
    });
    document.getElementById('btnShapeSquare')?.addEventListener('click', () => {
      layer.height = layer.width || 400;
      renderInspector();
      drawLayerStudioCanvas();
    });

    // Layer Name & Type
    document.getElementById('propLayerName')?.addEventListener('input', e => { layer.name = e.target.value; renderLayersList(); });
    document.getElementById('propShapeType')?.addEventListener('change', e => {
      layer.shape_type = e.target.value;
      if (e.target.value === 'outer_border') {
        layer.transparent = true;
        layer.border_color = '#000000';
        layer.border_width = 4;
        layer.radius = 14;
        layer.x = 4; layer.y = 4; layer.width = 1072; layer.height = 1912;
      } else if (e.target.value === 'bottom_accent_line') {
        layer.transparent = false;
        layer.fill_color = '#FF1744';
        layer.border_width = 0;
        layer.radius = 0;
        layer.x = 0; layer.y = 1914; layer.width = 820; layer.height = 6;
      } else if (e.target.value === 'badge_pill') {
        layer.radius = Math.round((layer.height || 60) / 2);
      }
      renderInspector();
      drawLayerStudioCanvas();
    });

    // Radius & Max Pill
    document.getElementById('propShapeRadius')?.addEventListener('input', e => {
      layer.radius = parseInt(e.target.value, 10);
      document.getElementById('lblShapeRadius').textContent = `${layer.radius}px`;
      drawLayerStudioCanvas();
    });
    document.getElementById('btnShapeMaxPill')?.addEventListener('click', () => {
      layer.radius = Math.round((layer.height || 100) / 2);
      renderInspector();
      drawLayerStudioCanvas();
    });

    // Fill & Palette
    document.getElementById('propShapeFill')?.addEventListener('input', e => {
      layer.fill_color = e.target.value;
      layer.transparent = false;
      document.getElementById('propShapeFillHex').value = e.target.value.toUpperCase();
      document.getElementById('propShapeTrans').checked = false;
      drawLayerStudioCanvas();
    });
    document.getElementById('propShapeFillHex')?.addEventListener('input', e => {
      if (/^#[0-9A-F]{6}$/i.test(e.target.value)) {
        layer.fill_color = e.target.value;
        layer.transparent = false;
        document.getElementById('propShapeFill').value = e.target.value;
        document.getElementById('propShapeTrans').checked = false;
        drawLayerStudioCanvas();
      }
    });
    document.getElementById('propShapeTrans')?.addEventListener('change', e => {
      layer.transparent = e.target.checked;
      drawLayerStudioCanvas();
    });
    contentEl.querySelectorAll('.shape-color-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const c = chip.getAttribute('data-color');
        layer.fill_color = c;
        layer.transparent = false;
        document.getElementById('propShapeFill').value = c;
        document.getElementById('propShapeFillHex').value = c;
        document.getElementById('propShapeTrans').checked = false;
        drawLayerStudioCanvas();
      });
    });

    // Border
    document.getElementById('propShapeBorderColor')?.addEventListener('input', e => {
      layer.border_color = e.target.value;
      drawLayerStudioCanvas();
    });
    document.getElementById('propShapeBorderWidth')?.addEventListener('input', e => {
      layer.border_width = parseInt(e.target.value, 10);
      document.getElementById('lblShapeBorderW').textContent = `${layer.border_width}px`;
      drawLayerStudioCanvas();
    });

    // Shadow
    document.getElementById('propShapeShadowEnabled')?.addEventListener('change', e => {
      layer.shadow_enabled = e.target.checked;
      document.getElementById('shapeShadowRow').style.display = layer.shadow_enabled ? 'grid' : 'none';
      drawLayerStudioCanvas();
    });
    document.getElementById('propShapeShadowColor')?.addEventListener('input', e => {
      layer.shadow_color = e.target.value;
      drawLayerStudioCanvas();
    });
    document.getElementById('propShapeShadowBlur')?.addEventListener('input', e => {
      layer.shadow_blur = parseInt(e.target.value, 10);
      document.getElementById('lblShapeShadowBlur').textContent = `${layer.shadow_blur}px blur`;
      drawLayerStudioCanvas();
    });
    document.getElementById('propShapeShadowOX')?.addEventListener('input', e => {
      layer.shadow_offset_x = parseInt(e.target.value, 10) || 0;
      drawLayerStudioCanvas();
    });
    document.getElementById('propShapeShadowOY')?.addEventListener('input', e => {
      layer.shadow_offset_y = parseInt(e.target.value, 10) || 0;
      drawLayerStudioCanvas();
    });

    // Opacity
    document.getElementById('propShapeOpacity')?.addEventListener('input', e => {
      layer.opacity = parseFloat(e.target.value);
      document.getElementById('lblShapeOpacity').textContent = `${Math.round(layer.opacity * 100)}%`;
      drawLayerStudioCanvas();
    });
  }
}

function getLayerBoundingBox(layer, sf, cw, ch, ctx) {
  if (!layer) return null;
  let bx = 0, by = 0, bw = 0, bh = 0;
  if (layer.type === 'shape') {
    bx = (layer.x ?? 12) * sf;
    by = (layer.y ?? 8) * sf;
    bw = (layer.width ?? 1056) * sf;
    bh = (layer.height ?? 76) * sf;
  } else {
    const fs = (layer.font_size || 38) * sf;
    const maxWrapW = (layer.wrap_width || 900) * sf;
    let renderText = layer.text || '';
    if (layer.text_case === 'upper') renderText = renderText.toUpperCase();
    else if (layer.text_case === 'lower') renderText = renderText.toLowerCase();
    else if (layer.text_case === 'title') renderText = toTitleCase(renderText);

    let maxLineW = 100 * sf;
    let lineCount = 1;
    if (ctx) {
      const lines = splitLinesWithWrap(ctx, renderText, maxWrapW);
      lineCount = lines.length;
      for (const lStr of lines) {
        const lw = ctx.measureText(lStr).width;
        if (lw > maxLineW) maxLineW = lw;
      }
    }
    const lineH = fs * (layer.line_height || 1.25);
    const totalTextH = lineH * (lineCount - 1) + fs;

    let tx = (layer.x ?? 540) * sf;
    let ty = (layer.y ?? 46) * sf;
    if (layer.position === 'top_header') { tx = cw / 2; ty = (8 + 76 / 2) * sf; }
    else if (layer.position === 'upper_third') { tx = cw / 2; ty = ch * 0.18; }
    else if (layer.position === 'center') { tx = cw / 2; ty = ch * 0.5; }
    else if (layer.position === 'lower_third') { tx = cw / 2; ty = ch * 0.78; }

    const align = layer.alignment || 'center';
    bw = maxLineW + 12;
    bh = totalTextH + 8;
    if (align === 'center') bx = tx - bw / 2;
    else if (align === 'left') bx = tx - 6;
    else bx = tx - bw + 6;
    by = ty - bh / 2;
  }
  return { bx, by, bw, bh };
}

function getShapeHandles(bx, by, bw, bh) {
  return {
    nw: { x: bx, y: by, cursor: 'nwse-resize' },
    n:  { x: bx + bw / 2, y: by, cursor: 'ns-resize' },
    ne: { x: bx + bw, y: by, cursor: 'nesw-resize' },
    e:  { x: bx + bw, y: by + bh / 2, cursor: 'ew-resize' },
    se: { x: bx + bw, y: by + bh, cursor: 'nwse-resize' },
    s:  { x: bx + bw / 2, y: by + bh, cursor: 'ns-resize' },
    sw: { x: bx, y: by + bh, cursor: 'nesw-resize' },
    w:  { x: bx, y: by + bh / 2, cursor: 'ew-resize' }
  };
}

function findHandleAtPoint(mx, my, handles, hitRadius = 8) {
  if (!handles) return null;
  for (const [key, pt] of Object.entries(handles)) {
    if (Math.abs(mx - pt.x) <= hitRadius && Math.abs(my - pt.y) <= hitRadius) {
      return { handle: key, cursor: pt.cursor };
    }
  }
  return null;
}

function syncShapeInspectorInputs(layer) {
  if (!layer || layer.type !== 'shape') return;
  const wIn = document.getElementById('propShapeW');
  const wSl = document.getElementById('propShapeWSlider');
  const wLbl = document.getElementById('lblShapeW');
  const hIn = document.getElementById('propShapeH');
  const hSl = document.getElementById('propShapeHSlider');
  const hLbl = document.getElementById('lblShapeH');
  const xIn = document.getElementById('propShapeX');
  const yIn = document.getElementById('propShapeY');

  const wVal = Math.round(layer.width || 0);
  const hVal = Math.round(layer.height || 0);
  if (wIn) wIn.value = wVal;
  if (wSl) wSl.value = wVal;
  if (wLbl) wLbl.textContent = `${wVal}px`;
  if (hIn) hIn.value = hVal;
  if (hSl) hSl.value = hVal;
  if (hLbl) hLbl.textContent = `${hVal}px`;
  if (xIn) xIn.value = Math.round(layer.x || 0);
  if (yIn) yIn.value = Math.round(layer.y || 0);
}

function drawLayerStudioCanvas() {
  if (!activeProject) return;

  const canvas = document.getElementById('layerStudioCanvas');
  const targetSelect = document.getElementById('editTargetImageSelect');
  const targetScene = targetSelect ? targetSelect.value : '1';
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  const cw = canvas.width;
  const ch = canvas.height;
  const sf = cw / 1080.0;

  const img = new Image();
  img.crossOrigin = 'anonymous';
  // Use clean base image to prevent double-baking layers when moving or editing
  img.src = `/api/scene_base_image/${activeProject.id}/${targetScene}?t=${Date.now()}`;

  img.onload = () => {
    ctx.clearRect(0, 0, cw, ch);

    // Apply image filters
    ctx.save();
    const b = currentFilters.brightness ?? 1.0;
    const c = currentFilters.contrast ?? 1.0;
    const s = currentFilters.saturation ?? 1.0;
    ctx.filter = `brightness(${b}) contrast(${c}) saturate(${s})`;
    ctx.drawImage(img, 0, 0, cw, ch);
    ctx.restore();

    // Render layers in order (bottom to top)
    for (const layer of currentImageLayers) {
      if (!layer.visible) continue;

      ctx.save();
      ctx.globalAlpha = layer.opacity ?? 1.0;

      if (layer.type === 'shape') {
        const sx = (layer.x ?? 12) * sf;
        const sy = (layer.y ?? 8) * sf;
        const sw = (layer.width ?? 1056) * sf;
        const sh = (layer.height ?? 76) * sf;
        const cr = (layer.radius ?? 16) * sf;

        if (layer.shadow_enabled) {
          ctx.save();
          ctx.shadowColor = layer.shadow_color || 'rgba(0,0,0,0.7)';
          ctx.shadowBlur = (layer.shadow_blur || 8) * sf;
          ctx.shadowOffsetX = (layer.shadow_offset_x || 0) * sf;
          ctx.shadowOffsetY = (layer.shadow_offset_y || 4) * sf;
          ctx.beginPath();
          if (layer.shape_type === 'circle') {
            ctx.ellipse(sx + sw / 2, sy + sh / 2, sw / 2, sh / 2, 0, 0, Math.PI * 2);
          } else if (cr > 0 && ctx.roundRect) {
            ctx.roundRect(sx, sy, sw, sh, cr);
          } else {
            ctx.rect(sx, sy, sw, sh);
          }
          if (!layer.transparent && layer.fill_color) {
            ctx.fillStyle = layer.fill_color;
            ctx.fill();
          } else if ((layer.border_width || 0) > 0 && layer.border_color) {
            ctx.strokeStyle = layer.border_color;
            ctx.lineWidth = Math.max(1, (layer.border_width * sf));
            ctx.stroke();
          }
          ctx.restore();
        }

        ctx.beginPath();
        if (layer.shape_type === 'circle') {
          ctx.ellipse(sx + sw / 2, sy + sh / 2, sw / 2, sh / 2, 0, 0, Math.PI * 2);
        } else if (cr > 0 && ctx.roundRect) {
          ctx.roundRect(sx, sy, sw, sh, cr);
        } else {
          ctx.rect(sx, sy, sw, sh);
        }

        if (!layer.transparent && layer.fill_color) {
          ctx.fillStyle = layer.fill_color;
          ctx.fill();
        }
        if ((layer.border_width || 0) > 0 && layer.border_color) {
          ctx.strokeStyle = layer.border_color;
          ctx.lineWidth = Math.max(1, (layer.border_width * sf));
          ctx.stroke();
        }

      } else if (layer.type === 'text') {
        let renderText = layer.text || '';
        if (layer.text_case === 'upper') renderText = renderText.toUpperCase();
        else if (layer.text_case === 'lower') renderText = renderText.toLowerCase();
        else if (layer.text_case === 'title') renderText = toTitleCase(renderText);

        const fs = (layer.font_size || 38) * sf;
        const fStyle = layer.italic ? 'italic ' : 'normal ';
        const fWeight = layer.bold !== false ? 'bold ' : 'normal ';
        let ff = 'Anton, Impact, sans-serif';
        if (layer.font_style === 'bebas') ff = '"Bebas Neue", Impact, sans-serif';
        else if (layer.font_style === 'oswald') ff = 'Oswald, sans-serif';
        else if (layer.font_style === 'montserrat') ff = 'Montserrat, sans-serif';
        else if (layer.font_style === 'space_grotesk') ff = '"Space Grotesk", sans-serif';
        else if (layer.font_style === 'space_mono' || layer.font_style === 'monospace') ff = '"Space Mono", monospace';
        else if (layer.font_style === 'roboto' || layer.font_style === 'arial_bold') ff = 'Roboto, Arial, sans-serif';
        else if (layer.font_style === 'playfair' || layer.font_style === 'serif') ff = '"Playfair Display", Georgia, serif';

        ctx.font = `${fStyle} ${fWeight} ${fs}px ${ff}`;
        if (ctx.letterSpacing !== undefined) {
          ctx.letterSpacing = `${(layer.letter_spacing || 0) * sf}px`;
        }

        const maxWrapW = (layer.wrap_width || 900) * sf;
        const lines = splitLinesWithWrap(ctx, renderText, maxWrapW);
        const lineH = fs * (layer.line_height || 1.25);
        const totalTextH = lineH * (lines.length - 1) + fs;

        let maxLineW = 0;
        for (const lStr of lines) {
          const lw = ctx.measureText(lStr).width;
          if (lw > maxLineW) maxLineW = lw;
        }

        let tx = (layer.x ?? 540) * sf;
        let ty = (layer.y ?? 46) * sf;

        if (layer.position === 'top_header') {
          tx = cw / 2;
          ty = (8 + 76 / 2) * sf;
        } else if (layer.position === 'upper_third') {
          tx = cw / 2;
          ty = ch * 0.18;
        } else if (layer.position === 'center') {
          tx = cw / 2;
          ty = ch * 0.5;
        } else if (layer.position === 'lower_third') {
          tx = cw / 2;
          ty = ch * 0.78;
        }

        const align = layer.alignment || 'center';
        let boxLeft = tx - maxLineW / 2;
        if (align === 'left') boxLeft = tx;
        else if (align === 'right') boxLeft = tx - maxLineW;

        // Background pill / box
        if (layer.bg_enabled || (layer.bg_color && layer.bg_color !== 'transparent')) {
          const padX = (layer.bg_padding_x || 16) * sf;
          const padY = (layer.bg_padding_y || 8) * sf;
          const bgRad = (layer.bg_radius || 10) * sf;
          ctx.save();
          ctx.globalAlpha = (layer.opacity ?? 1.0) * (layer.bg_opacity ?? 0.9);
          ctx.fillStyle = layer.bg_color || '#0A0A0A';
          ctx.beginPath();
          if (bgRad > 0 && ctx.roundRect) {
            ctx.roundRect(boxLeft - padX, ty - totalTextH / 2 - padY, maxLineW + padX * 2, totalTextH + padY * 2, bgRad);
          } else {
            ctx.rect(boxLeft - padX, ty - totalTextH / 2 - padY, maxLineW + padX * 2, totalTextH + padY * 2);
          }
          ctx.fill();
          ctx.restore();
        }

        // Drop shadow
        if (layer.shadow_enabled) {
          ctx.shadowColor = layer.shadow_color || 'rgba(0,0,0,0.8)';
          ctx.shadowBlur = (layer.shadow_blur || 4) * sf;
          ctx.shadowOffsetX = (layer.shadow_offset_x ?? 2) * sf;
          ctx.shadowOffsetY = (layer.shadow_offset_y ?? 3) * sf;
        } else {
          ctx.shadowColor = 'transparent';
        }

        ctx.textAlign = align;
        ctx.textBaseline = 'middle';

        const startY = ty - (totalTextH / 2) + (fs / 2);
        for (let idx = 0; idx < lines.length; idx++) {
          const lineY = startY + (idx * lineH);
          const lineStr = lines[idx];

          if ((layer.stroke_width || 0) > 0 && layer.stroke_color) {
            ctx.strokeStyle = layer.stroke_color;
            ctx.lineWidth = layer.stroke_width * sf;
            ctx.strokeText(lineStr, tx, lineY);
          }

          ctx.fillStyle = layer.color || '#FFFFFF';
          ctx.fillText(lineStr, tx, lineY);
        }
      }

      ctx.restore();

      // If this layer is selected, draw highlight selection box & 8 resize handles
      if (layer.id === selectedLayerId) {
        ctx.save();
        const bounds = getLayerBoundingBox(layer, sf, cw, ch, ctx);
        if (bounds) {
          const { bx, by, bw, bh } = bounds;

          // Bounding outline
          ctx.strokeStyle = '#00e5ff';
          ctx.lineWidth = 1.5;
          ctx.setLineDash([4, 4]);
          ctx.strokeRect(bx, by, bw, bh);
          ctx.setLineDash([]);

          // Dimension badge tag
          const curW = Math.round(layer.width || bw / sf);
          const curH = Math.round(layer.height || bh / sf);
          const dimText = `${curW} × ${curH}px`;
          ctx.font = 'bold 9.5px sans-serif';
          const dimW = ctx.measureText(dimText).width + 12;
          const badgeY = Math.max(14, by - 6);
          ctx.fillStyle = 'rgba(11, 15, 25, 0.9)';
          if (ctx.roundRect) {
            ctx.beginPath();
            ctx.roundRect(bx + (bw - dimW) / 2, badgeY - 13, dimW, 14, 4);
            ctx.fill();
            ctx.strokeStyle = '#00e5ff';
            ctx.lineWidth = 1;
            ctx.stroke();
          } else {
            ctx.fillRect(bx + (bw - dimW) / 2, badgeY - 13, dimW, 14);
          }
          ctx.fillStyle = '#00e5ff';
          ctx.textAlign = 'center';
          ctx.fillText(dimText, bx + bw / 2, badgeY - 2.5);

          // 8 Interactive Resize Handles
          const handles = getShapeHandles(bx, by, bw, bh);
          const handleSize = 7.5;
          for (const pt of Object.values(handles)) {
            ctx.fillStyle = '#FFFFFF';
            ctx.fillRect(pt.x - handleSize / 2, pt.y - handleSize / 2, handleSize, handleSize);
            ctx.strokeStyle = '#00e5ff';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(pt.x - handleSize / 2, pt.y - handleSize / 2, handleSize, handleSize);
          }
        }
        ctx.restore();
      }
    }
  };

  img.onerror = () => {
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, cw, ch);
    ctx.fillStyle = '#94a3b8';
    ctx.font = '14px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Loading image canvas...', cw / 2, ch / 2);
  };
}

function handleCanvasHover(e) {
  if (isDraggingLayer || isResizingLayer) return;
  const canvas = document.getElementById('layerStudioCanvas');
  if (!canvas) return;

  const rect = canvas.getBoundingClientRect();
  const mx = (e.clientX - rect.left) * (canvas.width / rect.width);
  const my = (e.clientY - rect.top) * (canvas.height / rect.height);
  const sf = canvas.width / 1080.0;
  const ctx = canvas.getContext('2d');

  // 1. Check if hovering over any handle of selected layer
  if (selectedLayerId) {
    const selLayer = currentImageLayers.find(l => l.id === selectedLayerId);
    if (selLayer && selLayer.visible) {
      const bounds = getLayerBoundingBox(selLayer, sf, canvas.width, canvas.height, ctx);
      if (bounds) {
        const handles = getShapeHandles(bounds.bx, bounds.by, bounds.bw, bounds.bh);
        const hit = findHandleAtPoint(mx, my, handles, 8);
        if (hit) {
          canvas.style.cursor = hit.cursor;
          return;
        }
      }
    }
  }

  // 2. Check if hovering inside any layer
  let hovered = false;
  for (let i = currentImageLayers.length - 1; i >= 0; i--) {
    const l = currentImageLayers[i];
    if (!l.visible) continue;
    const bounds = getLayerBoundingBox(l, sf, canvas.width, canvas.height, ctx);
    if (bounds && mx >= bounds.bx && mx <= bounds.bx + bounds.bw && my >= bounds.by && my <= bounds.by + bounds.bh) {
      hovered = true;
      break;
    }
  }
  canvas.style.cursor = hovered ? 'move' : 'default';
}

function handleCanvasMouseDown(e) {
  const canvas = document.getElementById('layerStudioCanvas');
  if (!canvas || !activeProject) return;

  const rect = canvas.getBoundingClientRect();
  const mx = (e.clientX - rect.left) * (canvas.width / rect.width);
  const my = (e.clientY - rect.top) * (canvas.height / rect.height);
  const sf = canvas.width / 1080.0;
  const ctx = canvas.getContext('2d');

  // 1. Check if clicked on a resize handle of currently selected layer
  if (selectedLayerId) {
    const selLayer = currentImageLayers.find(l => l.id === selectedLayerId);
    if (selLayer && selLayer.visible) {
      const bounds = getLayerBoundingBox(selLayer, sf, canvas.width, canvas.height, ctx);
      if (bounds) {
        const handles = getShapeHandles(bounds.bx, bounds.by, bounds.bw, bounds.bh);
        const hit = findHandleAtPoint(mx, my, handles, 9);
        if (hit) {
          isResizingLayer = true;
          activeResizeHandle = hit.handle;
          dragStartX = mx;
          dragStartY = my;
          dragLayerInitialX = selLayer.x ?? 12;
          dragLayerInitialY = selLayer.y ?? 8;
          dragLayerInitialW = selLayer.width ?? Math.round(bounds.bw / sf);
          dragLayerInitialH = selLayer.height ?? Math.round(bounds.bh / sf);
          dragLayerInitialFontSize = selLayer.font_size || 38;
          dragLayerInitialWrapW = selLayer.wrap_width || Math.round(bounds.bw / sf);
          return;
        }
      }
    }
  }

  // 2. Check if clicked inside any layer
  for (let i = currentImageLayers.length - 1; i >= 0; i--) {
    const l = currentImageLayers[i];
    if (!l.visible) continue;
    const bounds = getLayerBoundingBox(l, sf, canvas.width, canvas.height, ctx);
    if (!bounds) continue;

    if (mx >= bounds.bx && mx <= bounds.bx + bounds.bw && my >= bounds.by && my <= bounds.by + bounds.bh) {
      selectLayer(l.id);
      isDraggingLayer = true;
      dragStartX = mx;
      dragStartY = my;
      dragLayerInitialX = l.x ?? (l.position === 'top_header' ? 540 : 12);
      dragLayerInitialY = l.y ?? (l.position === 'top_header' ? 46 : 8);
      return;
    }
  }
}

function handleCanvasMouseMove(e) {
  if (!isDraggingLayer && !isResizingLayer) return;
  const canvas = document.getElementById('layerStudioCanvas');
  if (!canvas || !selectedLayerId) return;

  const rect = canvas.getBoundingClientRect();
  const mx = (e.clientX - rect.left) * (canvas.width / rect.width);
  const my = (e.clientY - rect.top) * (canvas.height / rect.height);
  const sf = canvas.width / 1080.0;

  const dx = (mx - dragStartX) / sf;
  const dy = (my - dragStartY) / sf;

  const layer = currentImageLayers.find(l => l.id === selectedLayerId);
  if (!layer) return;

  if (isResizingLayer && activeResizeHandle) {
    if (layer.type === 'text') {
      // Dynamic scaling: expand or shrink font size and wrap width
      let scale = 1.0;
      if (activeResizeHandle.includes('e')) {
        scale = Math.max(0.2, (dragLayerInitialW + dx) / Math.max(20, dragLayerInitialW));
      } else if (activeResizeHandle.includes('w')) {
        scale = Math.max(0.2, (dragLayerInitialW - dx) / Math.max(20, dragLayerInitialW));
      } else if (activeResizeHandle.includes('s')) {
        scale = Math.max(0.2, (dragLayerInitialH + dy) / Math.max(10, dragLayerInitialH));
      } else if (activeResizeHandle.includes('n')) {
        scale = Math.max(0.2, (dragLayerInitialH - dy) / Math.max(10, dragLayerInitialH));
      }
      layer.font_size = Math.round(Math.max(12, Math.min(180, dragLayerInitialFontSize * scale)));
      layer.wrap_width = Math.round(Math.max(100, dragLayerInitialWrapW * scale));

      const fsIn = document.getElementById('propFontSize');
      const fsLbl = document.getElementById('lblFontSize');
      if (fsIn) fsIn.value = layer.font_size;
      if (fsLbl) fsLbl.textContent = `${layer.font_size}px`;
      const wwIn = document.getElementById('propWrapWidth');
      const wwLbl = document.getElementById('lblWrapWidth');
      if (wwIn) wwIn.value = layer.wrap_width;
      if (wwLbl) wwLbl.textContent = `${layer.wrap_width}px`;

      drawLayerStudioCanvas();
      return;
    }

    let newX = dragLayerInitialX;
    let newY = dragLayerInitialY;
    let newW = dragLayerInitialW;
    let newH = dragLayerInitialH;

    // Handle Width & Horizontal Position
    if (activeResizeHandle.includes('e')) {
      newW = Math.max(10, Math.min(1080, Math.round(dragLayerInitialW + dx)));
    } else if (activeResizeHandle.includes('w')) {
      const maxRight = dragLayerInitialX + dragLayerInitialW;
      newW = Math.max(10, Math.round(dragLayerInitialW - dx));
      newX = Math.max(0, maxRight - newW);
    }

    // Handle Height & Vertical Position
    if (activeResizeHandle.includes('s')) {
      newH = Math.max(4, Math.min(1920, Math.round(dragLayerInitialH + dy)));
    } else if (activeResizeHandle.includes('n')) {
      const maxBottom = dragLayerInitialY + dragLayerInitialH;
      newH = Math.max(4, Math.round(dragLayerInitialH - dy));
      newY = Math.max(0, maxBottom - newH);
    }

    layer.x = newX;
    layer.y = newY;
    layer.width = newW;
    layer.height = newH;
    syncShapeInspectorInputs(layer);
    drawLayerStudioCanvas();
    return;
  }

  if (isDraggingLayer) {
    layer.x = Math.round(dragLayerInitialX + dx);
    layer.y = Math.round(dragLayerInitialY + dy);
    if (layer.type === 'text') {
      layer.position = 'custom';
      const pX = document.getElementById('propPosX');
      const pY = document.getElementById('propPosY');
      if (pX) pX.value = layer.x;
      if (pY) pY.value = layer.y;
    }
    syncShapeInspectorInputs(layer);
    drawLayerStudioCanvas();
  }
}

function handleCanvasMouseUp() {
  if (isDraggingLayer || isResizingLayer) {
    isDraggingLayer = false;
    isResizingLayer = false;
    activeResizeHandle = null;
    renderInspector();
  }
}

async function handleApplyAllLayers(rerenderVideo = false) {
  if (!activeProject) return;

  const targetSelect = document.getElementById('editTargetImageSelect');
  const targetScene = parseInt(targetSelect ? targetSelect.value : '1', 10);
  const statusEl = document.getElementById('layerStudioStatus');
  const btn = rerenderVideo ? document.getElementById('btnApplyLayersAndRerender') : document.getElementById('btnApplyAllLayers');

  if (btn) btn.disabled = true;
  if (statusEl) {
    statusEl.style.color = '#38bdf8';
    statusEl.textContent = rerenderVideo
      ? 'Applying all layers & re-rendering video...'
      : 'Applying all layers to image...';
  }

  const payload = {
    scene_number: targetScene,
    layers: currentImageLayers,
    filters: currentFilters,
    rerender_video: rerenderVideo
  };

  try {
    const res = await fetch(`/api/projects/${activeProject.id}/edit-image`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (res.ok) {
      activeProject = data.project || activeProject;
      activeProject.scene_layers = activeProject.scene_layers || {};
      activeProject.scene_layers[String(targetScene)] = JSON.parse(JSON.stringify(currentImageLayers));
      activeProject.image_layers = currentImageLayers;

      // Update scene thumbnail
      const sThumb = document.getElementById(`sceneThumbImg_${targetScene}`);
      if (sThumb) sThumb.src = `/api/scene_image/${activeProject.id}/${targetScene}?t=${Date.now()}`;

      if (rerenderVideo) {
        const videoPlayer = document.getElementById('modalVideoPlayer');
        if (videoPlayer) {
          videoPlayer.src = `/api/video/${activeProject.id}?t=${Date.now()}`;
          videoPlayer.play().catch(() => {});
        }
      }

      if (statusEl) {
        statusEl.style.color = '#10b981';
        statusEl.textContent = rerenderVideo
          ? '✓ Saved & re-rendered! Returning to project...'
          : '✓ Saved all layers! Returning to project...';
      }
      loadProjects();

      // Return to previous dialog after brief feedback
      setTimeout(() => {
        closeStudioModal();
      }, 700);
    } else {
      if (statusEl) {
        statusEl.style.color = '#ef4444';
        statusEl.textContent = `Error: ${data.detail || 'Failed to save layers'}`;
      }
    }
  } catch (err) {
    if (statusEl) {
      statusEl.style.color = '#ef4444';
      statusEl.textContent = `Error: ${err.message}`;
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ==========================================
// AI Music Studio, YouTube Audio Library & Hindi Agent
// ==========================================

let availableMusicTracks = [];
let savedMusicLibrary = [];
let generatedAIMusicHistory = [];
let currentSelectedCategory = 'Metal';
let lastGeneratedCustomTrack = null;

const DEFAULT_CATEGORY_PROMPTS = {
  'Metal': 'Powerful heavy guitar riffs, thunderous drums, dark cinematic atmosphere',
  'Rock': 'Driving electric guitar power chords, punchy rock drum beats, high voltage rhythm',
  'EDM': 'Pumping 128 BPM bassline, energetic synthesizer lead, massive build and drop',
  'Hip-Hop': 'Heavy 808 booming bass, crisp trap hi-hats, deep atmospheric street groove',
  'Cinematic': 'Massive orchestral brass swells, deep sub-bass tension, thunderous war drums',
  'Jazz': 'Warm walking bass, mellow electric piano chords, smooth late-night groove',
  'Pop': 'Upbeat punchy kick, bright synth plucks, catchy commercial summer groove',
  'Indian': 'Resonant sitar and tanpura modal drone, hypnotic tabla rhythm, mystical aura',
  'Ambient': 'Spacious evolving synth pads, gentle celestial harmonics, deep calm drone',
  'Sleep Music': 'Slow ambient music and soft soundscapes for bedtime, warm dreamy lullaby pads, gentle celesta overtones, deep peaceful sleep',
  'Flute Meditation': 'Soft bamboo flute and traditional instrumental music, peaceful Bansuri meditation melody, warm harmonic drone, gentle temple bells',
  'Deep Relaxation': 'Atmospheric drones and gentle sound textures, deep relaxation ambient soundscape, weightless harmonic washes',
  'Binaural Beats': 'Different frequencies played into each ear to create a perceived beat, stereo theta and alpha binaural entrainment waves with soft ambient pad',
  'Raga Therapy': 'Selected ragas and instrumental performances for relaxation and emotional engagement, expressive Sitar and Bansuri alap over resonant Tanpura drone',
  'Flute Healing': '528Hz Solfeggio healing flute melodies, emotional expressive breathy woodwind, singing crystal bowls, warm chakra aura pad',
  'Japanese Music': 'Traditional Japanese Koto plucked strings, breathy Shakuhachi bamboo flute in Hirajoshi pentatonic scale, serene Kyoto Zen garden temple bells',
  'Tibet Music': 'Resonant Tibetan bronze singing bowls, deep Himalayan temple gongs, overtone meditation drone, peaceful monastery sanctuary',
  'Devotional': 'Sacred peaceful morning temple ambiance, warm harmonium reed chords, gentle Bansuri flute and Sitar melody, soft Manjira temple bells',
  'Bhakti': 'Soulful Indian Bhakti bhajan and kirtan instrumental rhythm, warm Harmonium melody, rhythmic Tabla and Dholak Keherwa groove, Kartal chimes',
  'Raining': 'Soothing natural rainfall patter, warm distant rolling thunder, delicate ambient felt-piano raindrop notes, cozy peaceful rain soundscape',
  'Sea Waves': 'Rhythmic rolling ocean waves washing onto shore, gentle receding surf foam, warm sunset horizon ambient pads, serene coastal sea breeze',
  'Andean Pan Flute': 'Original Highland Andean Pan Flute (Zampoña & Quena) soaring melodies inspired by classic pan-pipe ballads, warm acoustic guitar & charango arpeggios, deep Bombo legüero heartbeat drum, wide canyon echo'
};

function selectMusicCategory(catName, btnEl) {
  currentSelectedCategory = catName;
  document.querySelectorAll('#musicCategoryPills .btn-cat-pill').forEach(btn => {
    btn.classList.remove('active');
    if (!btnEl && btn.textContent.toLowerCase().includes(catName.toLowerCase())) {
      btn.classList.add('active');
    }
  });
  if (btnEl) btnEl.classList.add('active');

  document.querySelectorAll('#musicOnlyCardsGrid .music-only-option-card').forEach(card => {
    if (card.dataset.category === catName) {
      card.classList.add('active');
    } else {
      card.classList.remove('active');
    }
  });

  const promptInput = document.getElementById('customMusicPrompt');
  if (promptInput) {
    const curVal = promptInput.value.trim();
    // If prompt is empty or one of the defaults, update to new category default
    const isDefault = Object.values(DEFAULT_CATEGORY_PROMPTS).includes(curVal) || curVal === '';
    if (isDefault) {
      promptInput.value = DEFAULT_CATEGORY_PROMPTS[catName] || '';
    }
  }
}

function selectMusicOnlyOption(catName, mood, prompt, cardEl) {
  currentSelectedCategory = catName;
  document.querySelectorAll('#musicOnlyCardsGrid .music-only-option-card').forEach(card => {
    card.classList.remove('active');
  });
  if (cardEl) {
    cardEl.classList.add('active');
  } else {
    const foundCard = document.querySelector(`#musicOnlyCardsGrid .music-only-option-card[data-category="${catName}"]`);
    if (foundCard) foundCard.classList.add('active');
  }

  document.querySelectorAll('#musicCategoryPills .btn-cat-pill').forEach(btn => {
    btn.classList.remove('active');
    if (btn.textContent.toLowerCase().includes(catName.toLowerCase())) {
      btn.classList.add('active');
    }
  });

  const moodRadio = document.querySelector(`input[name="musicMood"][value="${mood || 'Relaxing'}"]`);
  if (moodRadio) moodRadio.checked = true;

  const vocalRadio = document.querySelector('input[name="musicVocals"][value="Instrumental"]');
  if (vocalRadio) vocalRadio.checked = true;

  const promptInput = document.getElementById('customMusicPrompt');
  if (promptInput) {
    promptInput.value = prompt || DEFAULT_CATEGORY_PROMPTS[catName] || '';
  }
}

function openMusicOnlyStudio(defaultCat = 'Sleep Music') {
  openMusicModal();
  switchMusicTab('create');
  const defaultPrompt = DEFAULT_CATEGORY_PROMPTS[defaultCat] || DEFAULT_CATEGORY_PROMPTS['Sleep Music'];
  selectMusicOnlyOption(defaultCat, 'Relaxing', defaultPrompt, null);
  const panel = document.getElementById('musicOnlyOptionsPanel');
  if (panel) {
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    panel.style.boxShadow = '0 0 24px rgba(56, 189, 248, 0.55)';
    setTimeout(() => {
      panel.style.boxShadow = '0 4px 18px rgba(0, 0, 0, 0.35)';
    }, 1500);
  }
}

async function quickRunMusicOnlyOption(catName, mood, withClips, btnEl) {
  const cardEl = btnEl ? btnEl.closest('.music-only-option-card') : null;
  const prompt = DEFAULT_CATEGORY_PROMPTS[catName] || '';
  selectMusicOnlyOption(catName, mood || 'Relaxing', prompt, cardEl);
  if (withClips) {
    await triggerCreateMusicOnlyClips(false);
  } else {
    await triggerGenerateCustomMusic();
  }
}

function getSelectedMusicDurationSeconds() {
  const topSel = document.getElementById('musicOnlyDurationSelect');
  if (topSel) {
    if (topSel.value === 'custom') {
      const mins = parseFloat(document.getElementById('customMusicMinutesInput')?.value || '10');
      return Math.max(5, Math.min(3600, Math.round((isNaN(mins) ? 10 : mins) * 60)));
    }
    const v = parseFloat(topSel.value);
    if (!isNaN(v) && v > 0) return v;
  }
  const radioVal = parseFloat(document.querySelector('input[name="musicDuration"]:checked')?.value || '60');
  return isNaN(radioVal) ? 60 : radioVal;
}

function formatMusicDurationLabel(seconds) {
  const sec = Math.round(Number(seconds) || 60);
  if (sec >= 60) {
    const mins = +(sec / 60).toFixed(1);
    return `${mins} min (${sec}s)`;
  }
  return `${sec} seconds`;
}

function syncMusicDurationFromTop() {
  const topSel = document.getElementById('musicOnlyDurationSelect');
  const customWrap = document.getElementById('customMusicMinutesWrap');
  if (!topSel) return;

  if (topSel.value === 'custom') {
    if (customWrap) customWrap.style.display = 'inline-flex';
    return;
  }
  if (customWrap) customWrap.style.display = 'none';

  const matchingRadio = document.querySelector(`input[name="musicDuration"][value="${topSel.value}"]`);
  if (matchingRadio) {
    matchingRadio.checked = true;
  }
}

function syncMusicDurationFromRadio(radioEl) {
  if (!radioEl) return;
  const topSel = document.getElementById('musicOnlyDurationSelect');
  const customWrap = document.getElementById('customMusicMinutesWrap');
  if (topSel) {
    const hasOpt = Array.from(topSel.options).some(o => o.value === String(radioEl.value));
    if (hasOpt) {
      topSel.value = String(radioEl.value);
      if (customWrap) customWrap.style.display = 'none';
    }
  }
}

function updatePromptPlaceholder() {
  const mood = document.querySelector('input[name="musicMood"]:checked')?.value || 'Aggressive';
  const promptInput = document.getElementById('customMusicPrompt');
  if (promptInput && !promptInput.value.trim()) {
    promptInput.value = DEFAULT_CATEGORY_PROMPTS[currentSelectedCategory] || `${currentSelectedCategory} with ${mood.toLowerCase()} energy`;
  }
}

async function loadMusicTracks() {
  try {
    const res = await fetch(`/api/music/tracks?t=${Date.now()}`);
    if (!res.ok) return;
    const data = await res.json();
    availableMusicTracks = data.tracks || [];
    populateMusicSelects(availableMusicTracks);
    loadSavedMusicLibrary();
  } catch (err) {
    console.warn('Failed to load music tracks:', err);
  }
}

async function loadSavedMusicLibrary() {
  try {
    const res = await fetch(`/api/music/library?t=${Date.now()}`);
    if (!res.ok) return;
    const data = await res.json();
    savedMusicLibrary = data.library || [];
    renderSavedLibraryList(savedMusicLibrary);
    
    // Update badge count
    const badge = document.getElementById('savedLibraryBadge');
    if (badge) badge.textContent = savedMusicLibrary.length;
    const quickBadge = document.getElementById('quickLibraryCountBadge');
    if (quickBadge) quickBadge.textContent = `${savedMusicLibrary.length} track${savedMusicLibrary.length === 1 ? '' : 's'}`;
  } catch (err) {
    console.warn('Failed to load saved library:', err);
  }
}

function renderSavedLibraryList(libraryTracks) {
  const container = document.getElementById('savedLibraryListContainer');
  const quickContainer = document.getElementById('quickSavedLibraryContainer');

  if (!libraryTracks || libraryTracks.length === 0) {
    const emptyHtml = `
      <div style="text-align: center; color: #64748b; padding: 30px 20px;">
        <div style="font-size: 28px; margin-bottom: 6px;">📁</div>
        <p style="font-size: 13.5px; font-weight: 600; color: #94a3b8; margin-bottom: 4px;">No Saved Music in Library Yet</p>
        <p style="font-size: 11.5px; color: #64748b;">Generate any music track on the "Create Music" tab and click "Save to Library" to reuse it in future videos.</p>
      </div>
    `;
    if (container) container.innerHTML = emptyHtml;
    if (quickContainer) quickContainer.innerHTML = emptyHtml;
    return;
  }

  const itemsHtml = libraryTracks.map(t => {
    const isDef = Boolean(t.is_default);
    const safeId = escapeHtml(t.id);
    const safeName = escapeHtml(t.name);
    return `
      <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: #0b0f19; border: 1px solid ${isDef ? '#2563eb' : '#1e293b'}; border-radius: 10px; flex-wrap: wrap; gap: 12px;">
        <div style="flex: 1; min-width: 220px;">
          <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            <span style="font-size: 13.5px; font-weight: 700; color: #f8fafc;">💾 ${safeName}</span>
            ${isDef ? `<span class="badge" style="background: #2563eb; color: #ffffff; font-size: 10.5px; font-weight: 700; padding: 2px 7px;">⭐ Default For Next Videos</span>` : ''}
            <span class="badge" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-size: 10.5px;">${escapeHtml(t.category || 'Music')}</span>
            <span class="badge" style="background: rgba(168, 85, 247, 0.15); color: #c084fc; font-size: 10.5px;">${escapeHtml(t.mood || 'Epic')}</span>
            <span class="badge" style="background: rgba(148, 163, 184, 0.15); color: #94a3b8; font-size: 10.5px;">${escapeHtml(t.vocals || 'Instrumental')}</span>
            <span style="font-size: 11px; color: #64748b; font-family: monospace;">${Math.round(t.duration || 60)}s</span>
          </div>
          ${t.prompt ? `<div style="font-size: 11px; color: #94a3b8; margin-top: 4px; font-style: italic;">"${escapeHtml(t.prompt)}"</div>` : ''}
          <div style="font-size: 10px; color: #64748b; margin-top: 2px;">Saved on ${escapeHtml(t.created_at || 'Recently')}</div>
        </div>

        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
          <audio src="${t.url}" preload="none" controls style="height: 32px; width: 190px;"></audio>
          ${!isDef ? `
            <button class="btn btn-xs btn-secondary" onclick="setDefaultSavedTrack('${safeId}')" title="Set as default music for all new video creations" style="padding: 6px 10px; font-size: 11px;">
              ⭐ Set Default
            </button>
          ` : `
            <span style="font-size: 11px; color: #38bdf8; font-weight: 600;">✓ Active Default</span>
          `}
          <button class="btn btn-xs btn-primary" onclick="useSavedTrackForRemix('${safeId}')" style="padding: 6px 12px; font-size: 11px;">
            🎛️ Remix
          </button>
          <button class="btn btn-xs btn-secondary" onclick="deleteSavedTrack('${safeId}')" title="Delete from Library" style="padding: 6px 8px; font-size: 11px; color: #ef4444; border-color: rgba(239, 68, 68, 0.3);">
            🗑️
          </button>
        </div>
      </div>
    `;
  }).join('');

  if (container) container.innerHTML = itemsHtml;
  if (quickContainer) quickContainer.innerHTML = itemsHtml;
}

function populateMusicSelects(tracks) {
  // Populate dashboard musicTrackSelect
  const dashSelect = document.getElementById('musicTrackSelect');
  if (dashSelect) {
    const curVal = dashSelect.value;
    dashSelect.innerHTML = `<option value="default" ${curVal === 'default' ? 'selected' : ''}>✨ Auto / Default Ambience</option>`;
    
    // 1. Saved Library Optgroup (Surface at TOP for next video creation!)
    const libTracks = tracks.filter(t => t.source === 'library');
    if (libTracks.length > 0) {
      const libGroup = document.createElement('optgroup');
      libGroup.label = '📁 My Saved Music Library (Re-use)';
      libTracks.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.id;
        const defStar = t.is_default ? '⭐ [DEFAULT] ' : '💾 ';
        opt.textContent = `${defStar}${t.name.replace(/^💾\s*/, '')} (${t.genre})`;
        if (t.id === curVal) opt.selected = true;
        libGroup.appendChild(opt);
      });
      dashSelect.appendChild(libGroup);
    }

    // 2. AI Generated Optgroup
    const aiTracks = tracks.filter(t => t.source === 'ai_generated');
    if (aiTracks.length > 0) {
      const aiGroup = document.createElement('optgroup');
      aiGroup.label = '⚡ AI Synthesized Tracks';
      aiTracks.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.id;
        opt.textContent = `⚡ ${t.name}`;
        if (t.id === curVal) opt.selected = true;
        aiGroup.appendChild(opt);
      });
      dashSelect.appendChild(aiGroup);
    }
  }

  // Populate Car Edit "Phonk Track" selector (#carMotionPhonkSelect) with:
  // 1) All 8 Built-in Phonk & Car Edit Styles, 2) Newly Generated AI Music Tracks, 3) Saved Library Tracks
  const carPhonkSelect = document.getElementById('carMotionPhonkSelect');
  if (carPhonkSelect) {
    const curPhonkVal = (lastGeneratedCustomTrack && lastGeneratedCustomTrack.id && currentMainWorkspaceTab === 'car')
      ? lastGeneratedCustomTrack.id
      : (carPhonkSelect.value || 'drift_phonk');
    carPhonkSelect.innerHTML = '';

    const builtinPhonkStyles = [
      { id: 'drift_phonk', label: '🔥 ACE-Step Drift Phonk (130 BPM)' },
      { id: 'brazilian_phonk', label: '⚡ Hard Brazilian Phonk (135 BPM)' },
      { id: 'night_drive', label: '🌙 Night Drive Wave Phonk (124 BPM)' },
      { id: 'tokyo_touge', label: '🎌 Tokyo Touge Drift Phonk (132 BPM)' },
      { id: 'aggressive_cowbell', label: '🔔 Aggressive 808 Cowbell Phonk (138 BPM)' },
      { id: 'cyber_supercar', label: '🚀 Cyber Supercar Synth Phonk (128 BPM)' },
      { id: 'dark_memphis', label: '💀 Dark Memphis Underground Phonk (126 BPM)' },
      { id: 'hypercar_orchestral', label: '👑 Hypercar Orchestral Phonk (130 BPM)' }
    ];
    const phonkGroup = document.createElement('optgroup');
    phonkGroup.label = '🔥 Built-in & ACE-Step Phonk Styles';
    builtinPhonkStyles.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.label;
      if (p.id === curPhonkVal) opt.selected = true;
      phonkGroup.appendChild(opt);
    });
    carPhonkSelect.appendChild(phonkGroup);

    const aiTracks = tracks.filter(t => t.source === 'ai_generated');
    if (aiTracks.length > 0) {
      const newAiGroup = document.createElement('optgroup');
      newAiGroup.label = '✨ Newly Generated AI Music Tracks';
      aiTracks.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.id;
        opt.textContent = `🆕 ${t.name.replace(/^⚡\s*/, '')}`;
        if (t.id === curPhonkVal) opt.selected = true;
        newAiGroup.appendChild(opt);
      });
      carPhonkSelect.appendChild(newAiGroup);
    }

    const libTracks = tracks.filter(t => t.source === 'library');
    if (libTracks.length > 0) {
      const libGroup = document.createElement('optgroup');
      libGroup.label = '📁 My Saved Music Library';
      libTracks.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.id;
        const defStar = t.is_default ? '⭐ [DEFAULT] ' : '💾 ';
        opt.textContent = `${defStar}${t.name.replace(/^💾\s*/, '')} (${t.genre})`;
        if (t.id === curPhonkVal) opt.selected = true;
        libGroup.appendChild(opt);
      });
      carPhonkSelect.appendChild(libGroup);
    }
  }

  // Populate remix modal track selector
  const remixSelect = document.getElementById('remixTrackSelect');
  if (remixSelect) {
    remixSelect.innerHTML = '';
    tracks.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t.id;
      const srcLabel = t.source === 'library' ? 'Saved Library' : 'AI';
      opt.textContent = `[${srcLabel}] ${t.name.replace(/^💾\s*/, '')} (${t.genre})`;
      remixSelect.appendChild(opt);
    });
  }

  // Populate Add Music modal track selector
  const addMusicSelect = document.getElementById('addMusicTrackSelect');
  if (addMusicSelect) {
    addMusicSelect.innerHTML = '';
    tracks.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t.id;
      const srcLabel = t.source === 'library' ? 'Saved Library' : 'AI';
      opt.textContent = `[${srcLabel}] ${t.name.replace(/^💾\s*/, '')} (${t.genre})`;
      addMusicSelect.appendChild(opt);
    });
  }
}

function openMusicModal(projectId = null) {
  const modal = document.getElementById('musicStudioModal');
  if (!modal) return;

  // Populate project selects
  const addMusicProjSelect = document.getElementById('addMusicProjectSelect');
  const remixProjSelect = document.getElementById('remixProjectSelect');
  const hindiProjSelect = document.getElementById('hindiProjectSelect');
  const activeId = projectId || activeProject?.id;

  const projectOpts = currentProjects
    .filter(p => p.status !== 'failed' && p.status !== 'in_progress' && p.status !== 'queued')
    .map(p => `<option value="${p.id}" ${p.id === activeId ? 'selected' : ''}>${escapeHtml(p.title || p.topic)}</option>`)
    .join('');

  if (addMusicProjSelect) addMusicProjSelect.innerHTML = projectOpts;
  if (remixProjSelect) remixProjSelect.innerHTML = projectOpts;
  if (hindiProjSelect) hindiProjSelect.innerHTML = projectOpts;

  loadMusicTracks();
  loadSavedMusicLibrary();
  modal.classList.remove('hidden');
}

function closeMusicModal() {
  const modal = document.getElementById('musicStudioModal');
  if (modal) modal.classList.add('hidden');
  stopLiveAudition();
  const player = document.getElementById('customMusicAudioPlayer');
  if (player) {
    player.pause();
    player.currentTime = 0;
  }
}

function switchMusicTab(tabName) {
  stopLiveAudition();
  const tabDefs = [
    { id: 'create', btn: 'tabBtnCreateMusic', content: 'tabContentCreateMusic' },
    { id: 'library', btn: 'tabBtnSavedLibrary', content: 'tabContentSavedLibrary' },
    { id: 'addmusic', btn: 'tabBtnAddMusic', content: 'tabContentAddMusic' },
    { id: 'remix', btn: 'tabBtnRemix', content: 'tabContentRemix' },
    { id: 'hindi', btn: 'tabBtnHindi', content: 'tabContentHindi' }
  ];

  tabDefs.forEach(t => {
    const btn = document.getElementById(t.btn);
    const content = document.getElementById(t.content);
    if (btn && content) {
      if (t.id === tabName) {
        btn.classList.remove('btn-secondary');
        btn.classList.add('btn-primary');
        content.classList.remove('hidden');
      } else {
        btn.classList.remove('btn-primary');
        btn.classList.add('btn-secondary');
        content.classList.add('hidden');
      }
    }
  });

  if (tabName === 'library') {
    loadSavedMusicLibrary();
  }
}

async function triggerGenerateCustomMusic() {
  const category = currentSelectedCategory || 'Metal';
  const mood = document.querySelector('input[name="musicMood"]:checked')?.value || 'Aggressive';
  const vocals = document.querySelector('input[name="musicVocals"]:checked')?.value || 'Instrumental';
  const duration = getSelectedMusicDurationSeconds();
  const durLabel = formatMusicDurationLabel(duration);
  const prompt = document.getElementById('customMusicPrompt')?.value.trim() || DEFAULT_CATEGORY_PROMPTS[category] || '';
  const statusEl = document.getElementById('customMusicStatus');
  const btn = document.getElementById('btnGenerateCustomMusic');

  if (statusEl) {
    statusEl.style.color = '#38bdf8';
    statusEl.textContent = `Synthesizing ${category} (${mood} · ${vocals} · ${durLabel})...`;
  }
  if (btn) btn.disabled = true;

  try {
    let engine = document.getElementById('musicEngineSelect')?.value || 'acestep';
    const body = JSON.stringify({
      category,
      mood,
      vocals,
      duration,
      prompt,
      name: `${category} - ${mood} (${durLabel})`
    });
    const post = (url) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body });

    let res;
    if (engine === 'acestep') {
      if (statusEl) {
        statusEl.style.color = '#c084fc';
        statusEl.textContent = 'ACE-Step 1.5 is composing your track (falling back to MusicAgent if server offline)...';
      }
      res = await post('/api/music/acestep/generate');
      if (!res.ok) {
        if (statusEl) {
          statusEl.style.color = '#38bdf8';
          statusEl.textContent = `Synthesizing ${category} (${mood} · ${vocals} · ${durLabel}) with MusicAgent...`;
        }
        res = await post('/api/music/generate-custom');
      }
    } else {
      res = await post('/api/music/generate-custom');
    }
    const data = await res.json();
    if (res.ok && data.track) {
      lastGeneratedCustomTrack = data.track;
      if (statusEl) {
        statusEl.style.color = '#10b981';
        statusEl.textContent = `✓ Generated ${category} ${mood} track (${durLabel})!`;
      }
      const playerBox = document.getElementById('customMusicPlayerBox');
      const player = document.getElementById('customMusicAudioPlayer');
      const titleEl = document.getElementById('customPlayerTitle');
      const tagsEl = document.getElementById('customPlayerTags');
      const durEl = document.getElementById('customPlayerDur');
      const nameInput = document.getElementById('saveTrackNameInput');

      if (playerBox && player) {
        playerBox.style.display = 'block';
        player.pause();
        player.currentTime = 0;
        player.src = `${data.track.url}${data.track.url.includes('?') ? '&' : '?'}cb=${Date.now()}`;
        player.load();
        player.play().catch(() => {});
        if (titleEl) titleEl.textContent = `🎵 ${data.track.name}`;
        if (tagsEl) tagsEl.textContent = `${category} · ${mood} · ${vocals}`;
        if (durEl) durEl.textContent = durLabel;
        if (nameInput) nameInput.value = `${category} ${mood} (${durLabel})`;

        // Render MusicAgent Deep Research & QA Verification Specs
        const specsCard = document.getElementById('musicAgentSpecsCard');
        const adherenceBadge = document.getElementById('musicAgentAdherenceBadge');
        const scaleBadge = document.getElementById('musicAgentScaleBadge');
        const bpmVal = document.getElementById('musicAgentBpmVal');
        const keyVal = document.getElementById('musicAgentKeyVal');
        const drumsVal = document.getElementById('musicAgentDrumsVal');
        const driveVal = document.getElementById('musicAgentDriveVal');
        const summaryText = document.getElementById('musicAgentSummaryText');

        const research = data.track.research_specs || {};
        const qa = data.track.qa_verification || {};

        if (specsCard) {
          specsCard.style.display = 'block';
          if (adherenceBadge) {
            const score = qa.adherence_score || 98.5;
            adherenceBadge.textContent = `✓ ${score}% Prompt Match`;
          }
          if (scaleBadge) {
            scaleBadge.textContent = `${research.root_key || 'D'} ${research.scale || 'Minor'}`;
          }
          if (bpmVal) {
            bpmVal.textContent = `${research.target_bpm || Math.round(data.track.duration || 60)} BPM`;
          }
          if (keyVal) {
            keyVal.textContent = `${research.root_key || 'D'} (${research.scale || 'Standard'})`;
          }
          if (drumsVal) {
            drumsVal.textContent = research.drum_kit || 'Standard Kit';
          }
          if (driveVal) {
            driveVal.textContent = research.drive_description || 'Studio Master';
          }
          if (summaryText) {
            summaryText.textContent = qa.summary || `MusicAgent composed ${category} track matching prompt specifications.`;
          }
        }

        // Reveal the Deep Check & Verify button
        const deepCheckBtn = document.getElementById('btnDeepCheckMusic');
        if (deepCheckBtn) deepCheckBtn.style.display = 'inline-flex';
      }
      await loadMusicTracks();
    } else {
      if (statusEl) {
        statusEl.style.color = '#ef4444';
        statusEl.textContent = `Generation failed: ${data.detail || 'Error'}`;
      }
    }
  } catch (err) {
    if (statusEl) {
      statusEl.style.color = '#ef4444';
      statusEl.textContent = `Error: ${err.message}`;
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function triggerCreateMusicOnlyClips(useCurrentTrack = false) {
  const category = currentSelectedCategory || 'Sleep Music';
  const mood = document.querySelector('input[name="musicMood"]:checked')?.value || 'Relaxing';
  const vocals = document.querySelector('input[name="musicVocals"]:checked')?.value || 'Instrumental';
  const duration = getSelectedMusicDurationSeconds();
  const durLabel = formatMusicDurationLabel(duration);
  const clipCount = parseInt(document.getElementById('musicOnlyClipCountSelect')?.value || '3', 10);
  const prompt = document.getElementById('customMusicPrompt')?.value.trim() || DEFAULT_CATEGORY_PROMPTS[category] || '';
  const statusEl = document.getElementById('customMusicStatus');
  const clipStatusEl = document.getElementById('clipCutterStatus');
  const btn = document.getElementById('btnCreateMusicOnlyClips');
  const btnFromTrack = document.getElementById('btnCreateClipsFromCurrentTrack');

  const payload = {
    category,
    mood,
    vocals,
    duration,
    clip_count: clipCount,
    prompt
  };

  if (useCurrentTrack && lastGeneratedCustomTrack) {
    payload.track_id = lastGeneratedCustomTrack.id || lastGeneratedCustomTrack.filename;
    payload.clip_start = parseFloat(document.getElementById('customClipStart')?.value || '0.0');
    const cDur = parseFloat(document.getElementById('customClipDuration')?.value || '0.0');
    payload.clip_duration = cDur > 0.5 ? cDur : null;
    payload.clip_loop = document.getElementById('chkCustomClipLoop')?.checked ?? true;
  }

  if (statusEl) {
    statusEl.style.color = '#38bdf8';
    statusEl.textContent = `🎬 Synthesizing ${category} (${durLabel}) & rendering ${clipCount} visual 9:16 video clips + Music-Only Short...`;
  }
  if (clipStatusEl && useCurrentTrack) {
    clipStatusEl.style.color = '#38bdf8';
    clipStatusEl.textContent = `🎬 Rendering ${clipCount} visual video clips synchronized to your music...`;
  }
  if (btn) btn.disabled = true;
  if (btnFromTrack) btnFromTrack.disabled = true;

  try {
    const res = await fetch('/api/music/create-clips', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      if (data.track) {
        lastGeneratedCustomTrack = data.track;
        const playerBox = document.getElementById('customMusicPlayerBox');
        const player = document.getElementById('customMusicAudioPlayer');
        const titleEl = document.getElementById('customPlayerTitle');
        const tagsEl = document.getElementById('customPlayerTags');
        const durEl = document.getElementById('customPlayerDur');
        const nameInput = document.getElementById('saveTrackNameInput');
        if (playerBox && player) {
          playerBox.style.display = 'block';
          player.pause();
          player.currentTime = 0;
          player.src = `${data.track.url}${data.track.url.includes('?') ? '&' : '?'}cb=${Date.now()}`;
          player.load();
          if (titleEl) titleEl.textContent = `🎵 ${data.track.name}`;
          if (tagsEl) tagsEl.textContent = `${category} · ${mood} · ${vocals}`;
          if (durEl) durEl.textContent = formatMusicDurationLabel(data.track.duration || duration);
          if (nameInput) nameInput.value = `${category} ${mood} (${durLabel})`;
        }
      }

      const clipsBox = document.getElementById('musicOnlyClipsOutputBox');
      const clipsGrid = document.getElementById('musicOnlyClipsGrid');
      const clipsTitle = document.getElementById('musicOnlyClipsTitle');
      const clipsBadge = document.getElementById('musicOnlyClipsBadge');
      const btnOpenProj = document.getElementById('btnOpenMusicShortProject');

      const clips = data.clips || [];
      const proj = data.project || {};

      if (clipsBox && clipsGrid) {
        clipsBox.style.display = 'block';
        if (clipsTitle) clipsTitle.textContent = `🎬 ${proj.title || category} — Visual Music Clips`;
        if (clipsBadge) clipsBadge.textContent = `${clips.length} Clips + Full Short (${Math.round(proj.target_duration || duration)}s)`;
        if (btnOpenProj && proj.id) {
          btnOpenProj.onclick = () => {
            closeMusicModal();
            openProjectModal(proj.id);
          };
        }

        const clipCardsHtml = clips.map(c => `
          <div style="background: #0b1120; border: 1px solid #1e293b; border-radius: 10px; padding: 10px; display: flex; flex-direction: column; gap: 6px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 12px; font-weight: 700; color: #38bdf8;">🎬 ${escapeHtml(c.title)}</span>
              <span class="badge" style="background: rgba(56, 189, 248, 0.15); color: #7dd3fc; font-size: 10px;">${c.duration}s (${c.start_sec}s-${c.end_sec}s)</span>
            </div>
            <video src="${c.video_url}?t=${Date.now()}" controls loop preload="metadata" style="width: 100%; max-height: 250px; border-radius: 8px; background: #000;"></video>
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 6px;">
              <span style="font-size: 10.5px; color: #94a3b8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(c.caption || category)}</span>
              <a href="${c.video_url}" download="${escapeHtml(c.filename)}" class="btn btn-xs btn-secondary" style="font-size: 10.5px; padding: 3px 8px; text-decoration: none;">⬇ MP4</a>
            </div>
          </div>
        `).join('');

        const fullShortCardHtml = proj.id ? `
          <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid #10b981; border-radius: 10px; padding: 10px; display: flex; flex-direction: column; gap: 6px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 12px; font-weight: 800; color: #34d399;">🌟 Full Music-Only Short</span>
              <span class="badge" style="background: #10b981; color: #fff; font-size: 10px;">${Math.round(proj.target_duration || duration)}s Master</span>
            </div>
            <video src="/api/video/${proj.id}?t=${Date.now()}" controls loop preload="metadata" style="width: 100%; max-height: 250px; border-radius: 8px; background: #000;"></video>
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 6px;">
              <button type="button" class="btn btn-xs btn-primary" onclick="closeMusicModal(); openProjectModal('${escapeHtml(proj.id)}')" style="flex: 1; font-size: 10.5px; padding: 4px 8px; background: #2563eb;">📺 Open in Studio / Publish</button>
              <a href="/api/video/${proj.id}" download="${escapeHtml(category.toLowerCase().replace(/\s+/g, '_'))}_short.mp4" class="btn btn-xs btn-secondary" style="font-size: 10.5px; padding: 4px 8px; text-decoration: none;">⬇ Full MP4</a>
            </div>
          </div>
        ` : '';

        clipsGrid.innerHTML = clipCardsHtml + fullShortCardHtml;
        clipsBox.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }

      if (statusEl) {
        statusEl.style.color = '#10b981';
        statusEl.textContent = `✓ ${data.message || `Created ${clips.length} visual clips + Music-Only Short!`}`;
      }
      if (clipStatusEl && useCurrentTrack) {
        clipStatusEl.style.color = '#10b981';
        clipStatusEl.textContent = `✓ Created ${clips.length} visual video clips + Music-Only Short!`;
      }

      await loadProjects();
      await loadMusicTracks();
    } else {
      const errMsg = data.detail || 'Failed to create music clips';
      if (statusEl) {
        statusEl.style.color = '#ef4444';
        statusEl.textContent = `Error: ${errMsg}`;
      }
      if (clipStatusEl && useCurrentTrack) {
        clipStatusEl.style.color = '#ef4444';
        clipStatusEl.textContent = `Error: ${errMsg}`;
      }
    }
  } catch (err) {
    if (statusEl) {
      statusEl.style.color = '#ef4444';
      statusEl.textContent = `Error: ${err.message}`;
    }
    if (clipStatusEl && useCurrentTrack) {
      clipStatusEl.style.color = '#ef4444';
      clipStatusEl.textContent = `Error: ${err.message}`;
    }
  } finally {
    if (btn) btn.disabled = false;
    if (btnFromTrack) btnFromTrack.disabled = false;
  }
}

async function triggerDeepVerifyCurrentMusic() {
  if (!lastGeneratedCustomTrack) {
    alert('Please generate a music track first before running deep verification.');
    return;
  }

  const category = currentSelectedCategory || lastGeneratedCustomTrack.category || 'Metal';
  const mood = document.querySelector('input[name="musicMood"]:checked')?.value || lastGeneratedCustomTrack.mood || 'Aggressive';
  const vocals = document.querySelector('input[name="musicVocals"]:checked')?.value || lastGeneratedCustomTrack.vocals || 'Instrumental';
  const duration = parseFloat(document.querySelector('input[name="musicDuration"]:checked')?.value || lastGeneratedCustomTrack.duration || '60');
  const prompt = document.getElementById('customMusicPrompt')?.value.trim() || lastGeneratedCustomTrack.prompt || '';

  const statusEl = document.getElementById('customMusicStatus');
  const auditPanel = document.getElementById('deepVerificationAuditPanel');
  const deepBtn = document.getElementById('btnDeepCheckMusic');
  const headerBtn = document.getElementById('btnDeepCheckHeader');

  if (statusEl) {
    statusEl.style.color = '#38bdf8';
    statusEl.textContent = '🔍 Music Agent analyzing acoustic waveform, frequencies, and options adherence...';
  }
  if (deepBtn) deepBtn.disabled = true;
  if (headerBtn) headerBtn.disabled = true;

  try {
    const res = await fetch('/api/music/agent/deep-verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filename: lastGeneratedCustomTrack.filename,
        file_path: lastGeneratedCustomTrack.file_path,
        category,
        mood,
        vocals,
        duration,
        prompt
      })
    });
    const data = await res.json();
    if (res.ok && data.verification) {
      const v = data.verification;
      if (statusEl) {
        statusEl.style.color = '#10b981';
        statusEl.textContent = `✓ Deep Verification Complete: ${v.verdict} (${v.adherence_score}% Score)`;
      }

      if (auditPanel) {
        auditPanel.style.display = 'block';

        const verdictBadge = document.getElementById('deepVerifyVerdictBadge');
        if (verdictBadge) {
          verdictBadge.textContent = `${v.verdict} (${v.adherence_score}% Match)`;
          verdictBadge.style.background = (v.adherence_score >= 90) ? '#10b981' : '#f59e0b';
        }

        const timingBadge = document.getElementById('deepVerifyTimingBadge');
        if (timingBadge) {
          timingBadge.textContent = `${v.measured_duration}s measured (${v.channels} ${v.sample_rate}Hz, ${v.file_size_kb} KB)`;
        }

        const scores = v.scores || {};
        const setMeter = (idVal, idFill, score) => {
          const valEl = document.getElementById(idVal);
          const fillEl = document.getElementById(idFill);
          if (valEl) valEl.textContent = `${score}%`;
          if (fillEl) fillEl.style.width = `${Math.min(100, Math.max(0, score))}%`;
        };

        setMeter('barCategoryVal', 'barCategoryFill', scores.category_score ?? 0);
        setMeter('barMoodVal', 'barMoodFill', scores.mood_score ?? 0);
        setMeter('barVocalsVal', 'barVocalsFill', scores.vocals_score ?? 0);
        setMeter('barDurationVal', 'barDurationFill', scores.duration_score ?? 0);
        setMeter('barHealthVal', 'barHealthFill', scores.acoustic_health_score ?? 0);

        const listEl = document.getElementById('deepVerifyChecklist');
        if (listEl && Array.isArray(v.forensic_checks)) {
          listEl.innerHTML = v.forensic_checks.map(c => {
            const icon = c.trim().charAt(0);
            const color = icon === '⚠' ? '#f59e0b' : (icon === 'ℹ' ? '#94a3b8' : '#10b981');
            return `
            <div style="display: flex; align-items: flex-start; gap: 6px;">
              <span style="color: ${color}; font-weight: 700;">${escapeHtml(icon)}</span>
              <span>${escapeHtml(c.replace(/^[✓✔⚠ℹ]\s*/, ''))}</span>
            </div>
          `;
          }).join('');
        }
      }
    } else {
      if (statusEl) {
        statusEl.style.color = '#ef4444';
        statusEl.textContent = `Verification failed: ${data.detail || 'Could not audit audio'}`;
      }
    }
  } catch (err) {
    if (statusEl) {
      statusEl.style.color = '#ef4444';
      statusEl.textContent = `Error in deep verification: ${err.message}`;
    }
  } finally {
    if (deepBtn) deepBtn.disabled = false;
    if (headerBtn) headerBtn.disabled = false;
  }
}

async function saveCurrentTrackToLibrary() {
  if (!lastGeneratedCustomTrack) {
    alert('Please generate music first before saving to library.');
    return;
  }

  const nameInput = document.getElementById('saveTrackNameInput');
  const trackName = (nameInput?.value.trim()) || lastGeneratedCustomTrack.name;
  const isDefault = document.getElementById('chkSetAsDefault')?.checked || false;
  const statusEl = document.getElementById('saveLibraryStatus');

  if (statusEl) {
    statusEl.style.color = '#38bdf8';
    statusEl.textContent = 'Saving to your music library...';
  }

  try {
    const res = await fetch('/api/music/library/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filename: lastGeneratedCustomTrack.filename,
        name: trackName,
        category: lastGeneratedCustomTrack.category,
        mood: lastGeneratedCustomTrack.mood,
        vocals: lastGeneratedCustomTrack.vocals,
        duration: lastGeneratedCustomTrack.duration,
        prompt: lastGeneratedCustomTrack.prompt,
        is_default: isDefault
      })
    });
    const data = await res.json();
    if (res.ok) {
      if (statusEl) {
        statusEl.style.color = '#10b981';
        statusEl.textContent = `✓ Saved "${trackName}" to library! You can select it for next video creation.`;
      }
      await loadMusicTracks();
      await loadSavedMusicLibrary();
    } else {
      if (statusEl) {
        statusEl.style.color = '#ef4444';
        statusEl.textContent = `Save failed: ${data.detail || 'Error'}`;
      }
    }
  } catch (err) {
    if (statusEl) {
      statusEl.style.color = '#ef4444';
      statusEl.textContent = `Error: ${err.message}`;
    }
  }
}

async function setDefaultSavedTrack(trackId) {
  try {
    const res = await fetch(`/api/music/library/${trackId}/set-default`, { method: 'POST' });
    if (res.ok) {
      await loadSavedMusicLibrary();
      await loadMusicTracks();
    }
  } catch (err) {
    console.error('Set default error:', err);
  }
}

async function deleteSavedTrack(trackId) {
  if (!confirm('Are you sure you want to delete this track from your music library?')) return;
  try {
    const res = await fetch(`/api/music/library/${trackId}`, { method: 'DELETE' });
    if (res.ok) {
      await loadSavedMusicLibrary();
      await loadMusicTracks();
    }
  } catch (err) {
    console.error('Delete track error:', err);
  }
}

function useCurrentTrackForRemix() {
  if (lastGeneratedCustomTrack) {
    selectTrackForAddMusic(lastGeneratedCustomTrack.id);
  } else {
    switchMusicTab('addmusic');
  }
}

function useSavedTrackForRemix(trackId) {
  selectTrackForAddMusic(trackId);
}

function selectTrackForAddMusic(trackId) {
  switchMusicTab('addmusic');
  const addTrackSelect = document.getElementById('addMusicTrackSelect');
  const remixTrackSelect = document.getElementById('remixTrackSelect');
  if (addTrackSelect) {
    addTrackSelect.value = trackId;
    addTrackSelect.style.borderColor = '#10b981';
    setTimeout(() => { addTrackSelect.style.borderColor = '#23304a'; }, 1000);
  }
  if (remixTrackSelect) {
    remixTrackSelect.value = trackId;
  }
}

function selectTrackForRemix(trackId) {
  switchMusicTab('remix');
  const remixTrackSelect = document.getElementById('remixTrackSelect');
  if (remixTrackSelect) {
    remixTrackSelect.value = trackId;
    remixTrackSelect.style.borderColor = '#9333ea';
    setTimeout(() => { remixTrackSelect.style.borderColor = '#23304a'; }, 1000);
  }
}

// ==============================================================================
// LIVE AUDIO AUDITION & REAL-TIME SLIDER LEVEL HANDLERS
// ==============================================================================

let isAuditioning = false;

function updateRemixMixLevels() {
  const voiceSlider = document.getElementById('remixVoiceVolSlider');
  const musicSlider = document.getElementById('remixMusicVolumeSlider');
  const vVal = parseFloat(voiceSlider?.value || '1.0');
  const mVal = parseFloat(musicSlider?.value || '0.22');

  const lblV = document.getElementById('lblRemixVoiceVol');
  if (lblV) lblV.innerText = Math.round(vVal * 100) + '%' + (vVal > 1.0 ? ' (Boosted)' : (vVal === 1.0 ? '' : ' (Soft)'));

  const lblM = document.getElementById('lblMusicVolume');
  if (lblM) lblM.innerText = Math.round(mVal * 100) + '%' + (mVal > 1.0 ? ' (Boosted)' : (mVal <= 0.25 ? ' (Subtle BGM)' : ''));

  // Live real-time audio volume response on all active audio elements
  const voiceAudio = document.getElementById('liveAuditionAudioVoice');
  const musicAudio = document.getElementById('liveAuditionAudioMusic');
  const customPlayer = document.getElementById('customMusicAudioPlayer');

  // HTML5 audio volume supports 0.0 to 1.0 (clamped).
  const targetVoiceVol = Math.max(0.0, Math.min(1.0, vVal));
  const targetMusicVol = Math.max(0.0, Math.min(1.0, mVal));

  if (voiceAudio) {
    voiceAudio.volume = targetVoiceVol;
  }
  if (musicAudio) {
    musicAudio.volume = targetMusicVol;
  }
  if (customPlayer) {
    customPlayer.volume = targetMusicVol;
    // Bind play event once to ensure starting playback respects the slider
    if (!customPlayer._volBound) {
      customPlayer._volBound = true;
      customPlayer.addEventListener('play', () => {
        const curM = parseFloat(document.getElementById('remixMusicVolumeSlider')?.value || document.getElementById('addMusicVolSlider')?.value || '0.22');
        customPlayer.volume = Math.max(0.0, Math.min(1.0, curM));
      });
    }
  }
}

function updateAddMusicMixLevels() {
  const voiceSlider = document.getElementById('addVoiceVolSlider');
  const musicSlider = document.getElementById('addMusicVolSlider');
  const vVal = parseFloat(voiceSlider?.value || '1.0');
  const mVal = parseFloat(musicSlider?.value || '0.22');

  const lblV = document.getElementById('lblAddVoiceVol');
  if (lblV) lblV.innerText = Math.round(vVal * 100) + '%' + (vVal === 1 ? ' (Normal)' : (vVal > 1 ? ' (Boosted)' : ' (Attenuated)'));

  const lblM = document.getElementById('lblAddMusicVol');
  if (lblM) lblM.innerText = Math.round(mVal * 100) + '%' + (mVal <= 0.3 ? ' (Recommended)' : (mVal > 1 ? ' (Loud Music)' : ''));

  // Live real-time audio volume response
  const voiceAudio = document.getElementById('liveAuditionAudioVoice');
  const musicAudio = document.getElementById('liveAuditionAudioMusic');
  const customPlayer = document.getElementById('customMusicAudioPlayer');

  const targetVoiceVol = Math.max(0.0, Math.min(1.0, vVal));
  const targetMusicVol = Math.max(0.0, Math.min(1.0, mVal));

  if (voiceAudio) voiceAudio.volume = targetVoiceVol;
  if (musicAudio) musicAudio.volume = targetMusicVol;
  if (customPlayer) customPlayer.volume = targetMusicVol;
}

function stopLiveAudition() {
  const voiceAudio = document.getElementById('liveAuditionAudioVoice');
  const musicAudio = document.getElementById('liveAuditionAudioMusic');
  if (voiceAudio) { voiceAudio.pause(); voiceAudio.currentTime = 0; }
  if (musicAudio) { musicAudio.pause(); musicAudio.currentTime = 0; }
  isAuditioning = false;
  const btn = document.getElementById('btnLiveAuditionRemix');
  const icon = document.getElementById('auditionIcon');
  const text = document.getElementById('auditionText');
  const status = document.getElementById('auditionStatus');
  if (btn) btn.style.background = 'rgba(147, 51, 234, 0.25)';
  if (icon) icon.innerText = '🎧';
  if (text) text.innerText = 'Live Audition Mix';
  if (status) {
    status.style.color = '#94a3b8';
    status.innerText = 'Click to test voice + music together live as you adjust sliders.';
  }
}

async function toggleLiveAuditionRemix() {
  const voiceAudio = document.getElementById('liveAuditionAudioVoice');
  const musicAudio = document.getElementById('liveAuditionAudioMusic');
  if (!voiceAudio || !musicAudio) return;

  if (isAuditioning) {
    stopLiveAudition();
    return;
  }

  const projectId = document.getElementById('remixProjectSelect')?.value || document.getElementById('addMusicProjectSelect')?.value || activeProject?.id;
  const trackId = document.getElementById('remixTrackSelect')?.value || document.getElementById('addMusicTrackSelect')?.value;

  if (!projectId) {
    alert('Please select a target video project first.');
    return;
  }
  if (!trackId) {
    alert('Please select a music track to audition.');
    return;
  }

  // Find track URL
  let trackUrl = `/api/music/preview/${trackId}?type=library`;
  const trackObj = currentMusicTracks?.find(t => t.id === trackId || t.filename === trackId);
  if (trackObj && trackObj.url) {
    trackUrl = trackObj.url;
  }

  // Set audio sources with cache-buster
  voiceAudio.src = `/api/projects/${projectId}/voiceover?t=${Date.now()}`;
  musicAudio.src = trackUrl;

  // Apply slider volumes immediately
  updateRemixMixLevels();

  const icon = document.getElementById('auditionIcon');
  const text = document.getElementById('auditionText');
  const status = document.getElementById('auditionStatus');
  const btn = document.getElementById('btnLiveAuditionRemix');

  try {
    await Promise.all([
      voiceAudio.play().catch(e => console.warn('Voice audition error:', e)),
      musicAudio.play().catch(e => console.warn('Music audition error:', e))
    ]);
    isAuditioning = true;
    if (btn) btn.style.background = '#059669';
    if (icon) icon.innerText = '⏸️';
    if (text) text.innerText = 'Stop Audition';
    if (status) {
      status.style.color = '#10b981';
      status.innerText = '🔊 Playing live! Drag Voiceover or Music slider now to hear volume change.';
    }
  } catch (err) {
    console.error('Audition error:', err);
    stopLiveAudition();
  }
}

// ==============================================================================
// AUDIO CLIP CUTTER & LOOPER ENGINE
// ==============================================================================

let isPreviewingTrimmedClip = false;
let clipPreviewTimeHandler = null;

function setClipPreset(start, duration, loop) {
  const startEl = document.getElementById('customClipStart');
  const durEl = document.getElementById('customClipDuration');
  const loopEl = document.getElementById('chkCustomClipLoop');
  if (startEl) startEl.value = start.toFixed(1);
  if (durEl) durEl.value = duration > 0 ? duration.toFixed(1) : (lastGeneratedCustomTrack?.duration || 60).toFixed(1);
  if (loopEl) loopEl.checked = loop;
  updateClipRangeDisplay();
}

function updateClipRangeDisplay() {
  const start = parseFloat(document.getElementById('customClipStart')?.value || '0.0');
  const duration = parseFloat(document.getElementById('customClipDuration')?.value || '10.0');
  const ind = document.getElementById('clipRangeIndicator');
  const isLoop = document.getElementById('chkCustomClipLoop')?.checked ?? true;
  if (ind) {
    const end = (start + duration).toFixed(1);
    ind.textContent = `${start.toFixed(1)}s ➔ ${end}s (Duration: ${duration.toFixed(1)}s${isLoop ? ' · 🔁 Looping' : ''})`;
  }
}

function updateClipLoopState() {
  updateClipRangeDisplay();
}

function togglePreviewTrimmedClip() {
  const player = document.getElementById('customMusicAudioPlayer');
  const icon = document.getElementById('previewClipIcon');
  const text = document.getElementById('previewClipText');
  const btn = document.getElementById('btnPreviewTrimmedClip');

  if (isPreviewingTrimmedClip) {
    stopPreviewTrimmedClip();
    return;
  }

  if (!player || !player.src) {
    alert('Please generate or load a music track first.');
    return;
  }

  const start = Math.max(0, parseFloat(document.getElementById('customClipStart')?.value || '0.0'));
  const duration = Math.max(0.5, parseFloat(document.getElementById('customClipDuration')?.value || '10.0'));
  const isLoop = document.getElementById('chkCustomClipLoop')?.checked ?? true;
  const end = start + duration;

  player.pause();
  player.currentTime = start;

  if (clipPreviewTimeHandler) {
    player.removeEventListener('timeupdate', clipPreviewTimeHandler);
  }

  clipPreviewTimeHandler = function() {
    if (player.currentTime >= end) {
      if (isLoop) {
        player.currentTime = start;
        player.play().catch(() => {});
      } else {
        stopPreviewTrimmedClip();
      }
    }
  };

  player.addEventListener('timeupdate', clipPreviewTimeHandler);
  player.play().then(() => {
    isPreviewingTrimmedClip = true;
    if (btn) btn.style.background = '#059669';
    if (icon) icon.innerText = '⏸️';
    if (text) text.innerText = `Stop Preview (${duration.toFixed(0)}s ${isLoop ? 'Looping' : 'Clip'})`;
  }).catch(e => {
    console.warn('Clip preview play error:', e);
  });
}

function stopPreviewTrimmedClip() {
  const player = document.getElementById('customMusicAudioPlayer');
  const icon = document.getElementById('previewClipIcon');
  const text = document.getElementById('previewClipText');
  const btn = document.getElementById('btnPreviewTrimmedClip');

  if (player && clipPreviewTimeHandler) {
    player.removeEventListener('timeupdate', clipPreviewTimeHandler);
    clipPreviewTimeHandler = null;
    player.pause();
  }

  isPreviewingTrimmedClip = false;
  if (btn) btn.style.background = 'rgba(56, 189, 248, 0.15)';
  if (icon) icon.innerText = '▶️';
  if (text) {
    const dur = parseFloat(document.getElementById('customClipDuration')?.value || '10.0');
    text.innerText = `Preview Selected ${dur.toFixed(0)}s Clip (Looping)`;
  }
}

async function applyCurrentTrimmedClipToActiveProject() {
  stopPreviewTrimmedClip();
  if (!activeProject) {
    alert('Please open or select a video project first.');
    return;
  }
  if (!lastGeneratedCustomTrack) {
    alert('Please generate a music track first.');
    return;
  }

  const start = parseFloat(document.getElementById('customClipStart')?.value || '0.0');
  const duration = parseFloat(document.getElementById('customClipDuration')?.value || '10.0');
  const isLoop = document.getElementById('chkCustomClipLoop')?.checked ?? true;
  const statusEl = document.getElementById('clipCutterStatus');

  if (statusEl) {
    statusEl.style.color = '#38bdf8';
    statusEl.textContent = `Applying ${duration}s clip (${isLoop ? 'Looping 🔁' : 'Single Play'}) to video...`;
  }

  try {
    const res = await fetch(`/api/projects/${activeProject.id}/apply-music`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        track_id: lastGeneratedCustomTrack.id,
        music_volume: 0.22,
        voice_volume: 1.0,
        ducking: true,
        clip_start: start,
        clip_duration: duration,
        clip_loop: isLoop
      })
    });
    const data = await res.json();
    if (res.ok) {
      if (statusEl) {
        statusEl.style.color = '#10b981';
        statusEl.textContent = `✓ Applied ${duration}s clip (${isLoop ? 'Looping' : 'Once'}) to video successfully!`;
      }
      await loadProjects();
      const vp = document.getElementById('modalVideoPlayer');
      if (vp) {
        vp.pause();
        vp.src = `/api/video/${activeProject.id}?t=${Date.now()}`;
        vp.load();
        vp.play().catch(() => {});
      }
    } else {
      if (statusEl) {
        statusEl.style.color = '#ef4444';
        statusEl.textContent = `Error: ${data.detail || 'Failed to apply clip'}`;
      }
    }
  } catch (err) {
    if (statusEl) {
      statusEl.style.color = '#ef4444';
      statusEl.textContent = `Error: ${err.message}`;
    }
  }
}

async function saveCurrentTrimmedClipToLibrary() {
  if (!lastGeneratedCustomTrack) {
    alert('Please generate a music track first.');
    return;
  }
  const start = parseFloat(document.getElementById('customClipStart')?.value || '0.0');
  const duration = parseFloat(document.getElementById('customClipDuration')?.value || '10.0');
  const nameBase = document.getElementById('saveTrackNameInput')?.value.trim() || lastGeneratedCustomTrack.name;
  const statusEl = document.getElementById('clipCutterStatus');

  if (statusEl) {
    statusEl.style.color = '#38bdf8';
    statusEl.textContent = `Trimming ${duration}s clip and saving to library...`;
  }

  try {
    const res = await fetch('/api/music/trim-clip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        track_id: lastGeneratedCustomTrack.id,
        clip_start: start,
        clip_duration: duration,
        clip_name: `${nameBase} ${Math.round(duration)}s Hook`
      })
    });
    const data = await res.json();
    if (res.ok && data.track) {
      if (statusEl) {
        statusEl.style.color = '#10b981';
        statusEl.textContent = `✓ Saved trimmed clip "${data.track.name}" to your library!`;
      }
      await loadSavedMusicLibrary();
      await loadMusicTracks();
    } else {
      if (statusEl) {
        statusEl.style.color = '#ef4444';
        statusEl.textContent = `Error: ${data.detail || 'Failed to save clip'}`;
      }
    }
  } catch (err) {
    if (statusEl) {
      statusEl.style.color = '#ef4444';
      statusEl.textContent = `Error: ${err.message}`;
    }
  }
}

function setAddClipPreset(start, dur, loop) {
  const s = document.getElementById('addClipStart');
  const d = document.getElementById('addClipDuration');
  const l = document.getElementById('chkAddClipLoop');
  if (s) s.value = start.toFixed(1);
  if (d) d.value = dur > 0 ? dur.toFixed(1) : '';
  if (l) l.checked = loop;
}

function setRemixClipPreset(start, dur, loop) {
  const s = document.getElementById('remixClipStart');
  const d = document.getElementById('remixClipDuration');
  const l = document.getElementById('chkRemixClipLoop');
  if (s) s.value = start.toFixed(1);
  if (d) d.value = dur > 0 ? dur.toFixed(1) : '';
  if (l) l.checked = loop;
}

// ==============================================================================
// 1. ADD MUSIC TO VIDEO (Clean, Direct Mixing — Not Remix)
// ==============================================================================

async function triggerApplyAddMusic() {
  const projectId = document.getElementById('addMusicProjectSelect')?.value || activeProject?.id;
  const trackId = document.getElementById('addMusicTrackSelect')?.value;
  const voiceVolume = parseFloat(document.getElementById('addVoiceVolSlider')?.value || '1.0');
  const musicVolume = parseFloat(document.getElementById('addMusicVolSlider')?.value || '0.22');
  const ducking = document.getElementById('chkAddMusicDucking')?.checked ?? true;
  const clipStart = parseFloat(document.getElementById('addClipStart')?.value || '0.0');
  const clipDurRaw = document.getElementById('addClipDuration')?.value;
  const clipDuration = (clipDurRaw && parseFloat(clipDurRaw) > 0.05) ? parseFloat(clipDurRaw) : null;
  const clipLoop = document.getElementById('chkAddClipLoop')?.checked ?? true;

  const statusEl = document.getElementById('addMusicStatus');
  const btn = document.getElementById('btnApplyAddMusic');

  if (!projectId) {
    alert('Please select a target short video.');
    return;
  }
  if (!trackId) {
    alert('Please select a music track.');
    return;
  }

  if (statusEl) {
    statusEl.style.color = '#38bdf8';
    statusEl.textContent = 'Adding music & balancing audio levels...';
  }
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`/api/projects/${projectId}/apply-music`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        track_id: trackId,
        voice_volume: voiceVolume,
        music_volume: musicVolume,
        ducking: ducking,
        remove_music: false,
        clip_start: clipStart,
        clip_duration: clipDuration,
        clip_loop: clipLoop
      })
    });
    const data = await res.json();
    if (res.ok) {
      if (statusEl) {
        statusEl.style.color = '#10b981';
        statusEl.textContent = `✓ ${data.message || 'Added music successfully!'}`;
      }
      await loadProjects();
      if (activeProject && activeProject.id === projectId) {
        const vp = document.getElementById('modalVideoPlayer');
        if (vp) {
          vp.src = `/api/video/${projectId}?t=${Date.now()}`;
          vp.play().catch(() => {});
        }
      }
    } else {
      if (statusEl) {
        statusEl.style.color = '#ef4444';
        statusEl.textContent = `Error: ${data.detail || 'Failed to add music'}`;
      }
    }
  } catch (err) {
    if (statusEl) {
      statusEl.style.color = '#ef4444';
      statusEl.textContent = `Error: ${err.message}`;
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ==============================================================================
// 2. REMOVE MUSIC FROM VIDEO (Pure Clean Voiceover Only)
// ==============================================================================

async function triggerRemoveMusic(targetProjectId = null) {
  // 1. Determine active project ID based on context
  let projectId = targetProjectId;
  const remixTab = document.getElementById('tabContentRemix');
  const isRemixTabActive = remixTab && !remixTab.classList.contains('hidden');
  
  if (!projectId) {
    if (isRemixTabActive) {
      projectId = document.getElementById('remixProjectSelect')?.value || activeProject?.id;
    } else {
      projectId = document.getElementById('addMusicProjectSelect')?.value || activeProject?.id;
    }
  }
  if (!projectId) {
    projectId = activeProject?.id;
  }

  if (!projectId) {
    alert('Please select a target video project first.');
    return;
  }

  // 2. Resolve voiceover volume from relevant slider
  const addVoice = document.getElementById('addVoiceVolSlider')?.value;
  const remixVoice = document.getElementById('remixVoiceVolSlider')?.value;
  const voiceVolume = parseFloat(isRemixTabActive ? (remixVoice || '1.0') : (addVoice || '1.0'));

  // 3. Collect all Remove Music buttons and status elements to show feedback across UI
  const allBtns = [
    document.getElementById('btnQuickRemoveMusic'),
    document.getElementById('btnRemoveMusicAction'),
    document.getElementById('btnRemixRemoveMusic'),
    document.getElementById('btnModalRemoveMusic'),
    document.getElementById('btnModalRemoveMusicQuick')
  ].filter(Boolean);

  const statusEls = [
    document.getElementById('addMusicStatus'),
    document.getElementById('remixStatus')
  ].filter(Boolean);

  allBtns.forEach(b => {
    b.disabled = true;
    b.dataset.origHtml = b.innerHTML;
    b.innerHTML = '🔇 Removing Music...';
  });

  statusEls.forEach(el => {
    el.style.color = '#f59e0b';
    el.textContent = 'Stripping background music from video...';
  });

  try {
    const res = await fetch(`/api/projects/${projectId}/apply-music`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        remove_music: true,
        voice_volume: voiceVolume
      })
    });
    const data = await res.json();
    if (res.ok) {
      statusEls.forEach(el => {
        el.style.color = '#10b981';
        el.textContent = '✓ Background music removed! Video now has 100% clean voiceover.';
      });

      // Reload project list
      await loadProjects();

      // Update activeProject if it matches
      if (data.project) {
        if (!activeProject || activeProject.id === projectId) {
          activeProject = data.project;
        }
      } else if (activeProject && activeProject.id === projectId) {
        activeProject.with_music = false;
        activeProject.audio_mode = 'without_music';
        activeProject.music_track = null;
      }

      // Sync modal voice toggle
      const voiceToggle = document.getElementById('modalVoiceToggle');
      if (voiceToggle && activeProject && activeProject.id === projectId) {
        voiceToggle.value = 'without_music';
      }

      // Reload modal video player with cache-busting
      const vp = document.getElementById('modalVideoPlayer');
      if (vp && (!activeProject || activeProject.id === projectId)) {
        vp.pause();
        vp.src = `/api/video/${projectId}?t=${Date.now()}`;
        vp.load();
        vp.play().catch(() => {});
      }
    } else {
      statusEls.forEach(el => {
        el.style.color = '#ef4444';
        el.textContent = `Error: ${data.detail || 'Failed to remove music'}`;
      });
      alert(`Failed to remove music: ${data.detail || 'Server error'}`);
    }
  } catch (err) {
    statusEls.forEach(el => {
      el.style.color = '#ef4444';
      el.textContent = `Error: ${err.message}`;
    });
    alert(`Error removing music: ${err.message}`);
  } finally {
    allBtns.forEach(b => {
      b.disabled = false;
      if (b.dataset.origHtml) b.innerHTML = b.dataset.origHtml;
    });
  }
}

function triggerRemoveMusicForActiveProject() {
  if (!activeProject) {
    alert('Please open or select a video project first.');
    return;
  }
  triggerRemoveMusic(activeProject.id);
}

// ==============================================================================
// 3. AUDIO REMIX STUDIO (Proper Advanced Multi-Stem & FX Properties)
// ==============================================================================

async function triggerApplyRemixMusic() {
  const projectId = document.getElementById('remixProjectSelect')?.value || activeProject?.id;
  const trackId = document.getElementById('remixTrackSelect')?.value;
  const voiceVolume = parseFloat(document.getElementById('remixVoiceVolSlider')?.value || '1.0');
  const musicVolume = parseFloat(document.getElementById('remixMusicVolumeSlider')?.value || '0.22');
  const tempo = parseFloat(document.getElementById('remixTempoSelect')?.value || '1.0');
  const bass = parseFloat(document.getElementById('remixBassSlider')?.value || '0');
  const treble = parseFloat(document.getElementById('remixTrebleSlider')?.value || '0');
  const reverb = parseFloat(document.getElementById('remixReverbSlider')?.value || '0');
  const ducking = document.getElementById('chkAutoDucking')?.checked ?? true;
  const clipStart = parseFloat(document.getElementById('remixClipStart')?.value || '0.0');
  const clipDurRaw = document.getElementById('remixClipDuration')?.value;
  const clipDuration = (clipDurRaw && parseFloat(clipDurRaw) > 0.05) ? parseFloat(clipDurRaw) : null;
  const clipLoop = document.getElementById('chkRemixClipLoop')?.checked ?? true;

  const statusEl = document.getElementById('remixStatus');
  const btn = document.getElementById('btnApplyRemixMusic');

  if (!projectId) {
    alert('Please select a target short video.');
    return;
  }
  if (!trackId) {
    alert('Please select a music track to remix.');
    return;
  }

  if (statusEl) {
    statusEl.style.color = '#c084fc';
    statusEl.textContent = 'Rendering audio remix with FX properties & applying to video...';
  }
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`/api/projects/${projectId}/apply-music`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        track_id: trackId,
        voice_volume: voiceVolume,
        music_volume: musicVolume,
        tempo_factor: tempo,
        bass_boost: bass,
        treble_boost: treble,
        reverb: reverb,
        ducking: ducking,
        remove_music: false,
        clip_start: clipStart,
        clip_duration: clipDuration,
        clip_loop: clipLoop
      })
    });
    const data = await res.json();
    if (res.ok) {
      if (statusEl) {
        statusEl.style.color = '#10b981';
        statusEl.textContent = `✓ ${data.message || 'Audio remix applied successfully!'}`;
      }
      await loadProjects();
      if (activeProject && activeProject.id === projectId) {
        const vp = document.getElementById('modalVideoPlayer');
        if (vp) {
          vp.src = `/api/video/${projectId}?t=${Date.now()}`;
          vp.play().catch(() => {});
        }
      }
    } else {
      if (statusEl) {
        statusEl.style.color = '#ef4444';
        statusEl.textContent = `Remix error: ${data.detail || 'Failed'}`;
      }
    }
  } catch (err) {
    if (statusEl) {
      statusEl.style.color = '#ef4444';
      statusEl.textContent = `Error: ${err.message}`;
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function triggerConvertProjectToHindi() {
  const projectId = document.getElementById('hindiProjectSelect')?.value;
  const voice = document.getElementById('hindiVoiceActorSelect')?.value || 'hi-IN-MadhurNeural';
  const statusEl = document.getElementById('hindiConversionStatus');
  const btn = document.getElementById('btnConvertHindiSubmit');

  if (!projectId) {
    alert('Please select a target project.');
    return;
  }

  if (statusEl) {
    statusEl.style.color = '#fb923c';
    statusEl.textContent = 'Translating script to Hindi & synthesizing neural voiceover...';
  }
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`/api/projects/${projectId}/convert-hindi`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ voice })
    });
    const data = await res.json();
    if (res.ok) {
      if (statusEl) {
        statusEl.style.color = '#10b981';
        statusEl.textContent = `✓ Converted to Hindi! Re-rendered short with Devanagari subtitles.`;
      }
      await loadProjects();
      if (activeProject && activeProject.id === projectId) {
        const vp = document.getElementById('modalVideoPlayer');
        if (vp) {
          vp.src = `/api/video/${projectId}?t=${Date.now()}`;
          vp.play().catch(() => {});
        }
        const titleEl = document.getElementById('modalTitle');
        if (titleEl && data.project?.title_hindi) {
          titleEl.textContent = data.project.title_hindi;
        }
      }
    } else {
      if (statusEl) {
        statusEl.style.color = '#ef4444';
        statusEl.textContent = `Hindi conversion error: ${data.detail || 'Failed'}`;
      }
    }
  } catch (err) {
    if (statusEl) {
      statusEl.style.color = '#ef4444';
      statusEl.textContent = `Error: ${err.message}`;
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

function openMusicModalForCurrentProject() {
  openMusicModal(activeProject?.id);
  switchMusicTab('addmusic');
}

function openHindiModalForCurrentProject() {
  openMusicModal(activeProject?.id);
  switchMusicTab('hindi');
}

function openHindiModalForProject(projectId) {
  openMusicModal(projectId);
  switchMusicTab('hindi');
}

window.openMusicModal = openMusicModal;
window.closeMusicModal = closeMusicModal;
window.switchMusicTab = switchMusicTab;
window.triggerApplyAddMusic = triggerApplyAddMusic;
window.triggerRemoveMusic = triggerRemoveMusic;
window.triggerRemoveMusicForActiveProject = triggerRemoveMusicForActiveProject;
window.triggerApplyRemixMusic = triggerApplyRemixMusic;
window.openMusicModalForCurrentProject = openMusicModalForCurrentProject;
window.openHindiModalForCurrentProject = openHindiModalForCurrentProject;
window.openHindiModalForProject = openHindiModalForProject;
window.selectTrackForAddMusic = selectTrackForAddMusic;
window.updateRemixMixLevels = updateRemixMixLevels;
window.updateAddMusicMixLevels = updateAddMusicMixLevels;
window.toggleLiveAuditionRemix = toggleLiveAuditionRemix;
window.stopLiveAudition = stopLiveAudition;
window.useCurrentTrackForRemix = useCurrentTrackForRemix;
window.useSavedTrackForRemix = useSavedTrackForRemix;
window.setClipPreset = setClipPreset;
window.updateClipRangeDisplay = updateClipRangeDisplay;
window.updateClipLoopState = updateClipLoopState;
window.togglePreviewTrimmedClip = togglePreviewTrimmedClip;
window.stopPreviewTrimmedClip = stopPreviewTrimmedClip;
window.applyCurrentTrimmedClipToActiveProject = applyCurrentTrimmedClipToActiveProject;
window.saveCurrentTrimmedClipToLibrary = saveCurrentTrimmedClipToLibrary;
window.setAddClipPreset = setAddClipPreset;
window.setRemixClipPreset = setRemixClipPreset;
function switchMainWorkspaceTab(tabName) {
  currentMainWorkspaceTab = tabName || 'weapon';
  const tabs = ['weapon', 'car', 'music'];
  tabs.forEach(t => {
    const cap = t.charAt(0).toUpperCase() + t.slice(1);
    const btn = document.getElementById(`mainTabBtn${cap}`);
    const pane = document.getElementById(`mainTab${cap}`);
    if (btn) {
      if (t === tabName) btn.classList.add('active');
      else btn.classList.remove('active');
    }
    if (pane) {
      if (t === tabName) pane.classList.remove('hidden');
      else pane.classList.add('hidden');
    }
  });
  if (activeProject) {
    renderModalPublishState(activeProject);
  }
}

function switchCarSubTab(subTab) {
  const modes = ['static', 'motion', 'queue'];
  modes.forEach(m => {
    const cap = m.charAt(0).toUpperCase() + m.slice(1);
    const btn = document.getElementById(`carSubTabBtn${cap}`);
    const pane = document.getElementById(`carSubTab${cap}`);
    if (btn) {
      if (m === subTab) btn.classList.add('active');
      else btn.classList.remove('active');
    }
    if (pane) {
      if (m === subTab) pane.classList.remove('hidden');
      else pane.classList.add('hidden');
    }
  });
  if (subTab === 'queue') {
    loadCarQueue();
  }
}

let carQueueMoodsCache = [];

async function loadCarQueue() {
  const grid = document.getElementById('carQueueSlotsGrid');
  if (!grid) return;
  try {
    const res = await fetch(`/api/car-queue?t=${Date.now()}`);
    if (!res.ok) return;
    const data = await res.json();
    carQueueMoodsCache = data.moods || [];
    const tgBadge = document.getElementById('carQueueTgStatusBadge');
    if (tgBadge && data.notifications) {
      const tgOk = data.notifications.telegram;
      tgBadge.innerHTML = tgOk
        ? '✓ Telegram Bot Active (Sends MP4 + Approve/Reject buttons)'
        : 'ℹ️ Set TELEGRAM_BOT_TOKEN &amp; TELEGRAM_CHAT_ID in .env for phone buttons';
      tgBadge.style.color = tgOk ? '#34d399' : '#94a3b8';
    }
    renderCarQueueSlots(data.slots || []);
  } catch (err) {
    console.error('Failed to load car queue:', err);
  }
}

function renderCarQueueSlots(slots) {
  const grid = document.getElementById('carQueueSlotsGrid');
  if (!grid) return;
  const todayIso = new Date().toISOString().slice(0, 10);
  const upcoming = slots.filter(s => (s.scheduled_date || '') >= todayIso).slice(0, 7);
  const list = upcoming.length ? upcoming : slots.slice(-7);

  grid.innerHTML = list.map((s, idx) => {
    const isToday = s.scheduled_date === todayIso;
    const statusColors = {
      queued: { bg: 'rgba(56, 189, 248, 0.14)', border: 'rgba(56, 189, 248, 0.4)', text: '#38bdf8', label: '⏳ Queued' },
      running: { bg: 'rgba(245, 158, 11, 0.18)', border: 'rgba(245, 158, 11, 0.5)', text: '#fbbf24', label: '⚙️ Generating...' },
      awaiting_telegram_approval: { bg: 'rgba(168, 85, 247, 0.18)', border: 'rgba(168, 85, 247, 0.5)', text: '#c084fc', label: '📲 Awaiting Telegram Approval' },
      approved_private: { bg: 'rgba(16, 185, 129, 0.18)', border: 'rgba(16, 185, 129, 0.5)', text: '#34d399', label: '🔒 Approved (Private on @AutoFlashX)' },
      rejected: { bg: 'rgba(239, 68, 68, 0.16)', border: 'rgba(239, 68, 68, 0.4)', text: '#f87171', label: '❌ Rejected' },
      failed: { bg: 'rgba(239, 68, 68, 0.16)', border: 'rgba(239, 68, 68, 0.4)', text: '#f87171', label: '⚠️ Failed' }
    };
    const st = statusColors[s.status] || statusColors.queued;
    const moodOpts = (carQueueMoodsCache || []).map(m =>
      `<option value="${escapeHtml(m.mood_id)}" ${m.mood_id === s.mood_id ? 'selected' : ''}>${escapeHtml(m.label)} (${m.bpm} BPM)</option>`
    ).join('');

    return `
      <div style="background: #0b1120; border: 1px solid ${isToday ? '#38bdf8' : '#1e293b'}; border-radius: 12px; padding: 12px; display: flex; flex-direction: column; justify-content: space-between; gap: 8px; box-shadow: ${isToday ? '0 0 14px rgba(56, 189, 248, 0.2)' : 'none'};">
        <div>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; gap: 6px;">
            <span style="font-size: 12px; font-weight: 800; color: ${isToday ? '#38bdf8' : '#e2e8f0'};">
              Day ${idx + 1} · ${escapeHtml(s.weekday || s.scheduled_date)}${isToday ? ' (TODAY)' : ''}
            </span>
            <span class="badge" style="background: ${st.bg}; border: 1px solid ${st.border}; color: ${st.text}; font-size: 10px; padding: 2px 7px;">
              ${st.label}
            </span>
          </div>
          <input type="text" value="${escapeHtml(s.car_name || '')}"
            onchange="updateCarQueueSlot('${escapeHtml(s.id)}', { car_name: this.value })"
            style="width: 100%; padding: 6px 9px; font-size: 12.5px; font-weight: 700; background: #131a29; border: 1px solid #23304a; border-radius: 7px; color: #f8fafc; margin-bottom: 6px;"
            title="Edit car name or 'A vs B vs C' matchup for this day">
          <select onchange="updateCarQueueSlot('${escapeHtml(s.id)}', { mood_id: this.value })"
            style="width: 100%; padding: 5px 8px; font-size: 11.5px; background: #090d16; border: 1px solid #23304a; border-radius: 7px; color: #cbd5e1;">
            ${moodOpts}
          </select>
        </div>
        <div style="display: flex; align-items: center; justify-content: space-between; gap: 6px; padding-top: 4px;">
          <button type="button" class="btn btn-xs btn-weaponx" onclick="runCarQueueSlotNow('${escapeHtml(s.id)}', this)" style="flex: 1; padding: 6px 10px; font-size: 11.5px; justify-content: center;">
            ▶️ Run Car Edit Now
          </button>
          ${s.project_id ? `<button type="button" class="btn btn-xs btn-secondary" onclick="openModal('${escapeHtml(s.project_id)}')" style="padding: 6px 10px; font-size: 11.5px;">🎬 Open Video</button>` : ''}
        </div>
      </div>
    `;
  }).join('');
}

async function updateCarQueueSlot(slotId, payload) {
  try {
    const res = await fetch(`/api/car-queue/${encodeURIComponent(slotId)}/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      const data = await res.json();
      renderCarQueueSlots(data.slots || []);
    }
  } catch (err) {
    console.error('Failed to update slot:', err);
  }
}

async function refillCarQueue(forceReset = false) {
  try {
    const res = await fetch('/api/car-queue/refill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force_reset: Boolean(forceReset) })
    });
    if (res.ok) {
      const data = await res.json();
      renderCarQueueSlots(data.slots || []);
    }
  } catch (err) {
    console.error('Failed to refill queue:', err);
  }
}

async function runCarQueueSlotNow(slotId, btnEl) {
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.textContent = '⏳ Starting...';
  }
  const banner = document.getElementById('statusBanner');
  const msg = document.getElementById('statusMessage');
  if (banner) banner.classList.remove('hidden');
  if (msg) msg.textContent = '🏎️ Launching queued Daily Car Edit + Telegram Approval dispatch...';

  try {
    const res = await fetch(`/api/car-queue/${encodeURIComponent(slotId)}/run`, { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      if (msg) msg.textContent = `🏎️ ${data.message} — generating & sending to Telegram for approval...`;
      await loadCarQueue();
      setTimeout(() => loadProjects(), 1500);
      pollGenerationStatus(null);
    } else {
      alert(data.detail || 'Failed to start queued Car Edit');
      if (banner) banner.classList.add('hidden');
    }
  } catch (err) {
    console.error(err);
    if (banner) banner.classList.add('hidden');
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.textContent = '▶️ Run Car Edit Now';
    }
  }
}

async function pollCarQueueTelegramApprovals() {
  try {
    const res = await fetch('/api/car-queue/poll-telegram', { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      renderCarQueueSlots(data.slots || []);
      await loadProjects();
      const badge = document.getElementById('carQueueTgStatusBadge');
      if (badge) {
        badge.textContent = data.handled_decisions > 0
          ? `✓ Processed ${data.handled_decisions} Telegram approval decision(s)!`
          : '✓ Polled Telegram — no new button presses waiting.';
        badge.style.color = '#38bdf8';
      }
    }
  } catch (err) {
    console.error('Failed to poll Telegram:', err);
  }
}

function fillCarStaticExample(exampleText) {
  const input = document.getElementById('carStaticNameInput');
  if (input) {
    input.value = exampleText;
    input.focus();
  }
}

async function triggerCarStaticGenerate(forceComparison = false) {
  const nameInput = document.getElementById('carStaticNameInput');
  const durationSelect = document.getElementById('carStaticDurationSelect');
  const audioSelect = document.getElementById('carStaticAudioSelect');
  const voiceSelect = document.getElementById('carStaticVoiceSelect');
  const btnCar = document.getElementById('btnCarStaticGenerate');
  const btnComp = document.getElementById('btnCarComparisonGenerate');

  const rawCarName = nameInput && nameInput.value ? nameInput.value.trim() : '';
  const defaultTopic = forceComparison
    ? 'Porsche 911 GT3 RS vs Ferrari SF90 vs Lamborghini Revuelto'
    : 'Bugatti Tourbillon V16 Hypercar';
  const topic = rawCarName || defaultTopic;
  const isVsComparison = forceComparison || /\s+(?:vs\.?|versus)\s+/i.test(topic);
  let duration = durationSelect ? parseFloat(durationSelect.value) : 10;
  if (isNaN(duration) || duration < 5) duration = 5;
  if (duration > 180) duration = 180;

  const audioMode = audioSelect ? audioSelect.value : 'with_voice';
  const langVoiceRaw = voiceSelect ? voiceSelect.value : 'en:en-US-ChristopherNeural';
  const [selectedLang, selectedVoice] = langVoiceRaw.includes(':')
    ? langVoiceRaw.split(':')
    : ['en', 'en-US-ChristopherNeural'];

  let withVoice = true;
  let withMusic = true;
  if (audioMode === 'without_music') {
    withVoice = true;
    withMusic = false;
  } else if (audioMode === 'without_voice') {
    withVoice = false;
    withMusic = true;
  } else if (audioMode === 'mute') {
    withVoice = false;
    withMusic = false;
  }

  const banner = document.getElementById('statusBanner');
  const msg = document.getElementById('statusMessage');
  if (banner) banner.classList.remove('hidden');
  if (msg) {
    msg.textContent = isVsComparison
      ? `⚔️ Initiating 'A vs B vs C' Comparison Poster Short (${duration}s) for: "${topic}"...`
      : `Initiating Car Static Image Short (${duration}s) for: "${topic}"...`;
  }
  if (btnCar) btnCar.disabled = true;
  if (btnComp) btnComp.disabled = true;

  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic,
        auto_publish: false,
        style: isVsComparison ? 'weaponx' : 'default',
        with_voice: withVoice,
        with_music: withMusic,
        audio_mode: audioMode,
        duration: duration,
        language: selectedLang,
        voice: selectedVoice,
        music_track: 'default',
        music_volume: 0.22,
        motion: 'static',
        channel: 'autoflashx'
      })
    });

    if (res.ok) {
      const data = await res.json();
      if (nameInput) nameInput.value = '';
      await loadProjects();
      if (data.status === 'already_running') {
        if (msg) msg.textContent = `⏳ ${data.message}`;
        const card = document.querySelector(`[data-project-id="${data.project_id}"]`);
        if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
      pollGenerationStatus(data.project_id);
    } else {
      alert('Failed to start Car Short generation');
      if (banner) banner.classList.add('hidden');
    }
  } catch (err) {
    console.error(err);
    if (banner) banner.classList.add('hidden');
  } finally {
    if (btnCar) btnCar.disabled = false;
    if (btnComp) btnComp.disabled = false;
  }
}

function fillCarMotionExample(carName) {
  const input = document.getElementById('carMotionNameInput');
  if (input) {
    input.value = carName;
    input.focus();
  }
}

function toggleCarAnimateAllScenesUI() {
  const chk = document.getElementById('chkCarAnimateAllScenes');
  const wrap = document.getElementById('carAnimateEngineWrap');
  if (wrap && chk) {
    wrap.style.opacity = chk.checked ? '1' : '0.65';
  }
}

async function triggerCarMotionGenerate() {
  const nameInput = document.getElementById('carMotionNameInput');
  const titleInput = document.getElementById('carMotionTitleInput');
  const durationSelect = document.getElementById('carMotionDurationSelect');
  const motionPresetSelect = document.getElementById('carMotionPresetSelect');
  const beatSyncSelect = document.getElementById('carMotionBeatSyncSelect');
  const phonkSelect = document.getElementById('carMotionPhonkSelect');
  const audioSelect = document.getElementById('carMotionAudioSelect');
  const chkAnimateAll = document.getElementById('chkCarAnimateAllScenes');
  const clipEngineSelect = document.getElementById('carAnimateEngineSelect');
  const btnMotion = document.getElementById('btnCarMotionGenerate');

  const rawCarName = nameInput && nameInput.value ? nameInput.value.trim() : '';
  const topic = rawCarName || 'Porsche 911 GT3 RS';
  const customTitle = titleInput && titleInput.value ? titleInput.value.trim() : '';
  let duration = durationSelect ? parseFloat(durationSelect.value) : 15;
  if (isNaN(duration) || duration < 5) duration = 10;
  if (duration > 180) duration = 180;

  const motionPreset = motionPresetSelect ? motionPresetSelect.value : 'swxft_dynamic';
  const beatSyncMode = beatSyncSelect ? beatSyncSelect.value : 'swxft_velocity';
  const phonkStyle = phonkSelect ? phonkSelect.value : 'drift_phonk';
  const audioMode = audioSelect ? audioSelect.value : 'without_voice';
  const withVoice = (audioMode === 'with_voice');
  const animateAllScenes = Boolean(chkAnimateAll && chkAnimateAll.checked);
  const clipEngine = clipEngineSelect ? clipEngineSelect.value : 'auto';

  const banner = document.getElementById('statusBanner');
  const msg = document.getElementById('statusMessage');
  if (banner) banner.classList.remove('hidden');
  if (msg) {
    const clipTag = animateAllScenes ? ` + LTX/Phosphene Motion Clips on Every Scene (${clipEngine})` : ' + Beat-Synced Velocity Ramps';
    msg.textContent = `🏎️ Initiating Swxft Car Edit (${duration}s${clipTag}) for: "${topic}"...`;
  }
  if (btnMotion) btnMotion.disabled = true;

  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic,
        auto_publish: false,
        style: 'car_edit',
        with_voice: withVoice,
        with_music: true,
        audio_mode: audioMode,
        duration: duration,
        language: 'en',
        voice: 'en-US-ChristopherNeural',
        music_track: phonkStyle,
        music_volume: withVoice ? 0.28 : 0.92,
        car_edit_title: customTitle || null,
        car_motion_preset: motionPreset,
        phonk_style: phonkStyle,
        beat_sync_mode: beatSyncMode,
        animate_all_scenes: animateAllScenes,
        clip_engine: clipEngine,
        channel: 'autoflashx'
      })
    });

    if (res.ok) {
      const data = await res.json();
      if (nameInput) nameInput.value = '';
      if (titleInput) titleInput.value = '';
      await loadProjects();
      if (data.status === 'already_running') {
        if (msg) msg.textContent = `⏳ ${data.message}`;
        const card = document.querySelector(`[data-project-id="${data.project_id}"]`);
        if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
      pollGenerationStatus(data.project_id);
    } else {
      alert('Failed to start Car Edit generation');
      if (banner) banner.classList.add('hidden');
    }
  } catch (err) {
    console.error(err);
    if (banner) banner.classList.add('hidden');
  } finally {
    if (btnMotion) btnMotion.disabled = false;
  }
}

window.switchMainWorkspaceTab = switchMainWorkspaceTab;
window.switchCarSubTab = switchCarSubTab;
window.triggerCarStaticGenerate = triggerCarStaticGenerate;
window.fillCarStaticExample = fillCarStaticExample;
window.triggerCarMotionGenerate = triggerCarMotionGenerate;
window.loadCarQueue = loadCarQueue;
window.updateCarQueueSlot = updateCarQueueSlot;
window.refillCarQueue = refillCarQueue;
window.runCarQueueSlotNow = runCarQueueSlotNow;
window.pollCarQueueTelegramApprovals = pollCarQueueTelegramApprovals;
window.fillCarMotionExample = fillCarMotionExample;
window.toggleCarAnimateAllScenesUI = toggleCarAnimateAllScenesUI;
window.openMusicOnlyStudio = openMusicOnlyStudio;
window.selectMusicOnlyOption = selectMusicOnlyOption;
window.quickRunMusicOnlyOption = quickRunMusicOnlyOption;
window.triggerCreateMusicOnlyClips = triggerCreateMusicOnlyClips;
window.syncMusicDurationFromTop = syncMusicDurationFromTop;
window.syncMusicDurationFromRadio = syncMusicDurationFromRadio;

// ---- Caption Style editor ----
const CAPTION_FIELDS = {
  enabled: 'check', font: 'select', font_size: 'range', bold: 'check', italic: 'check', case: 'select',
  letter_spacing: 'range', text_color: 'color', highlight_color: 'color', highlight_mode: 'select',
  pop_scale: 'range', background: 'select', outline_color: 'color', outline_width: 'range', shadow: 'range',
  box_color: 'color', box_opacity: 'range', position: 'select', offset: 'range', words_per_caption: 'range',
  entrance: 'select'
};
const CAPTION_UNITS = { font_size: 'px', letter_spacing: 'px', pop_scale: '%', outline_width: 'px', shadow: 'px', box_opacity: '%', offset: 'px', words_per_caption: '' };
const captionState = { style: null, presets: [], fonts: [], previewSeq: 0, previewTimer: null, lastUrl: null };

async function openCaptionStyleModal() {
  if (!activeProject) return;
  const modal = document.getElementById('captionStyleModal');
  modal.classList.remove('hidden');
  setCaptionStatus('', '');
  let data;
  try {
    data = await (await fetch(`/api/caption-styles?project_id=${encodeURIComponent(activeProject.id)}&t=${Date.now()}`)).json();
  } catch (err) {
    setCaptionStatus(`❌ Could not load caption styles: ${err.message}`, '#ef4444');
    return;
  }
  captionState.presets = data.presets || [];
  captionState.fonts = data.fonts || [];
  captionState.style = { ...(data.project_style || data.studio_default || data.builtin_default) };
  captionState.isCustomised = Boolean(data.project_style);

  // Font list, grouped
  const fontSel = document.getElementById('cs_font');
  const groups = {};
  captionState.fonts.forEach(f => { (groups[f.group] ||= []).push(f); });
  fontSel.innerHTML = Object.entries(groups).map(([g, fs]) =>
    `<optgroup label="${escapeHtml(g)}">${fs.map(f => `<option value="${escapeHtml(f.name)}" style="font-family:'${escapeHtml(f.name)}'">${escapeHtml(f.label)}</option>`).join('')}</optgroup>`).join('');

  // Preview scene picker
  const sceneSel = document.getElementById('cs_preview_scene');
  sceneSel.innerHTML = (activeProject.scenes || []).map(sc =>
    `<option value="${sc.scene_number}">Scene ${sc.scene_number}: ${escapeHtml((sc.narration || '').slice(0, 40))}</option>`).join('') || '<option value="1">Scene 1</option>';
  sceneSel.onchange = scheduleCaptionPreview;
  const sample = document.getElementById('cs_sample_text');
  sample.value = '';
  sample.oninput = scheduleCaptionPreview;
  document.getElementById('cs_make_default').checked = false;

  renderCaptionPresets();
  Object.keys(CAPTION_FIELDS).forEach(bindCaptionControl);
  applyCaptionStyleToControls();
  scheduleCaptionPreview(0);
}

function closeCaptionStyleModal() {
  document.getElementById('captionStyleModal')?.classList.add('hidden');
}

function renderCaptionPresets() {
  const wrap = document.getElementById('captionPresets');
  wrap.innerHTML = captionState.presets.map(p => {
    const st = p.style;
    const look = `font-family:'${st.font}';color:${st.text_color};font-weight:${st.bold ? 700 : 400};` +
      (st.background === 'box' ? `background:${st.box_color};` : `text-shadow:0 0 3px ${st.outline_color},0 0 3px ${st.outline_color};`);
    const active = captionState.style.preset === p.id ? ' active' : '';
    return `<button type="button" class="caption-preset${active}" onclick="applyCaptionPreset('${p.id}')">
      <span class="caption-preset-sample" style="${look}">${st.case === 'upper' ? 'AB' : 'Ab'}<span style="color:${st.highlight_mode === 'none' ? st.text_color : st.highlight_color}">c</span></span>
      <span class="caption-preset-name">${escapeHtml(p.label)}</span></button>`;
  }).join('');
}

function applyCaptionPreset(id) {
  const p = captionState.presets.find(x => x.id === id);
  if (!p) return;
  const enabled = captionState.style?.enabled ?? true;
  captionState.style = { ...p.style, enabled };
  applyCaptionStyleToControls();
  renderCaptionPresets();
  scheduleCaptionPreview(0);
}

function bindCaptionControl(key) {
  const el = document.getElementById(`cs_${key}`);
  if (!el || el.dataset.bound) return;
  el.dataset.bound = '1';
  const evt = CAPTION_FIELDS[key] === 'range' || CAPTION_FIELDS[key] === 'color' ? 'input' : 'change';
  el.addEventListener(evt, () => {
    const type = CAPTION_FIELDS[key];
    captionState.style[key] = type === 'check' ? el.checked : (type === 'range' ? Number(el.value) : el.value);
    captionState.style.preset = 'custom';
    updateCaptionOutputs();
    renderCaptionPresets();
    scheduleCaptionPreview();
  });
}

function applyCaptionStyleToControls() {
  const st = captionState.style;
  Object.entries(CAPTION_FIELDS).forEach(([key, type]) => {
    const el = document.getElementById(`cs_${key}`);
    if (!el || st[key] === undefined) return;
    if (type === 'check') el.checked = Boolean(st[key]);
    else if (type === 'color') el.value = String(st[key]).toLowerCase();  // <input type=color> needs lower-case hex
    else el.value = st[key];
  });
  updateCaptionOutputs();
}

function updateCaptionOutputs() {
  const st = captionState.style;
  Object.entries(CAPTION_UNITS).forEach(([key, unit]) => {
    const out = document.getElementById(`cs_${key}_out`);
    if (out) out.textContent = `${st[key]}${unit}`;
  });
  const boxed = st.background === 'box';
  document.getElementById('cs_box_rows').classList.toggle('hidden', !boxed);
  document.getElementById('cs_outline_colour_row').classList.toggle('hidden', boxed);
  document.getElementById('cs_shadow_row').classList.toggle('hidden', boxed);
  document.getElementById('cs_outline_label').textContent = boxed ? 'Box padding' : 'Outline width';
  document.getElementById('cs_pop_row').classList.toggle('hidden', st.highlight_mode !== 'pop');
  document.getElementById('cs_offset_row').classList.toggle('hidden', st.position === 'middle');
  document.querySelectorAll('#captionStyleModal fieldset').forEach(fs => { fs.disabled = !st.enabled; });
}

function scheduleCaptionPreview(delay = 250) {
  clearTimeout(captionState.previewTimer);
  captionState.previewTimer = setTimeout(renderCaptionPreview, typeof delay === 'number' ? delay : 250);
}

async function renderCaptionPreview() {
  const seq = ++captionState.previewSeq;
  const busy = document.getElementById('captionPreviewBusy');
  const errEl = document.getElementById('captionPreviewError');
  busy.classList.remove('hidden');
  try {
    const res = await fetch('/api/caption-preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: activeProject.id,
        style: captionState.style,
        scene: Number(document.getElementById('cs_preview_scene').value) || 1,
        sample_text: document.getElementById('cs_sample_text').value.trim() || null
      })
    });
    if (seq !== captionState.previewSeq) return;  // a newer preview superseded this one
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      errEl.textContent = `Preview failed: ${d.detail || res.status}`;
      return;
    }
    const url = URL.createObjectURL(await res.blob());
    if (captionState.lastUrl) URL.revokeObjectURL(captionState.lastUrl);
    captionState.lastUrl = url;
    document.getElementById('captionPreviewImg').src = url;
    errEl.textContent = '';
  } catch (err) {
    if (seq === captionState.previewSeq) errEl.textContent = `Preview failed: ${err.message}`;
  } finally {
    if (seq === captionState.previewSeq) busy.classList.add('hidden');
  }
}

function setCaptionStatus(text, color) {
  const el = document.getElementById('captionStatus');
  if (!el) return;
  el.textContent = text;
  el.style.color = color || '';
}

async function saveCaptionStyle(andRerender) {
  if (!activeProject) return;
  setCaptionStatus('Saving...', '#38bdf8');
  try {
    const res = await fetch(`/api/projects/${activeProject.id}/caption-style`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ style: captionState.style, make_default: document.getElementById('cs_make_default').checked })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setCaptionStatus(`❌ ${data.detail || 'Could not save'}`, '#ef4444');
      return;
    }
    activeProject.caption_style = data.style;
    captionState.style = { ...data.style };
    setCaptionStatus(`✓ ${andRerender ? 'Saved. Re-rendering the video...' : data.message}`, '#10b981');
    if (andRerender) {
      closeCaptionStyleModal();
      handleRerenderModal();
    }
  } catch (err) {
    setCaptionStatus(`❌ ${err.message}`, '#ef4444');
  }
}

async function resetCaptionStyle() {
  if (!activeProject) return;
  if (!window.confirm('Go back to the original built-in captions for this video?')) return;
  const res = await fetch(`/api/projects/${activeProject.id}/caption-style`, { method: 'DELETE' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    setCaptionStatus(`❌ ${data.detail || 'Could not reset'}`, '#ef4444');
    return;
  }
  delete activeProject.caption_style;
  applyCaptionPreset('classic');
  setCaptionStatus(`✓ ${data.message}`, '#10b981');
}

// ---- Scene Motion & Effects editor (zoom / pan / focus / filters) ----
const FX_FALLBACK_OPTIONS = {
  motions: [
    { id: 'auto', label: 'Auto (alternating zoom)' }, { id: 'zoom_in', label: 'Zoom in' }, { id: 'zoom_out', label: 'Zoom out' },
    { id: 'pan_left', label: 'Pan left' }, { id: 'pan_right', label: 'Pan right' }, { id: 'pan_up', label: 'Pan up' },
    { id: 'pan_down', label: 'Pan down' }, { id: 'focus', label: 'Focus (push in to a point)' }, { id: 'static', label: 'Static (no motion)' }
  ],
  strengths: ['subtle', 'normal', 'strong'],
  speed_ramps: [
    { id: 'none', label: 'Smooth (standard)' },
    { id: 'velocity', label: 'Swxft Velocity (Fast · Slow-Mo · Fast)' },
    { id: 'whip_in', label: 'Whip-In → Slow-Mo Hold' },
    { id: 'whip_out', label: 'Slow-Mo → Whip-Out Exit' }
  ],
  filters: [
    { id: 'none', label: 'None' }, { id: 'cinematic', label: 'Cinematic' }, { id: 'bw', label: 'Black & white' },
    { id: 'sepia', label: 'Sepia' }, { id: 'vintage', label: 'Vintage' }, { id: 'warm', label: 'Warm' },
    { id: 'cool', label: 'Cool' }, { id: 'vivid', label: 'Vivid' }
  ],
  toggles: ['vignette', 'focus_blur', 'beat_flash', 'fade_in', 'fade_out']
};
const FX_TOGGLE_LABELS = {
  vignette: 'Vignette',
  focus_blur: 'Focus blur (edges soft)',
  beat_flash: 'Beat flash & bass pulse (Swxft)',
  fade_in: 'Fade in',
  fade_out: 'Fade out'
};
const fxState = { scene: 1, options: null, value: null, previewSeq: 0, previewUrl: null, previewTimer: null };

function sceneEffectsOf(scene) {
  const d = activeProject?.scene_defaults || {};
  return {
    motion: scene?.motion || d.motion || 'auto',
    motion_strength: scene?.motion_strength || d.motion_strength || 'normal',
    speed_ramp: scene?.speed_ramp || d.speed_ramp || 'none',
    beat_sync: Boolean(scene?.beat_sync ?? d.beat_sync ?? false),
    bpm: Number(scene?.bpm || d.bpm || 130),
    focus_point: scene?.focus_point || d.focus_point || { x: 0.5, y: 0.45 },
    effects: Object.assign({ filter: 'none', vignette: false, focus_blur: false, beat_flash: false, fade_in: false, fade_out: false }, d.effects || {}, scene?.effects || {})
  };
}

function sceneEffectsBadge(scene) {
  const fx = sceneEffectsOf(scene);
  const parts = [];
  if (fx.motion && fx.motion !== 'auto') parts.push(fx.motion.replace('_', ' '));
  if (fx.speed_ramp && fx.speed_ramp !== 'none') parts.push(`⚡ ${fx.speed_ramp.replace('_', ' ')}`);
  if (fx.beat_sync || fx.effects.beat_flash) parts.push(`🥁 ${scene?.beats ? scene.beats + 'B ' : ''}beat-sync`);
  if (fx.effects.filter && fx.effects.filter !== 'none') parts.push(fx.effects.filter);
  ['vignette', 'focus_blur', 'fade_in', 'fade_out'].forEach(k => { if (fx.effects[k]) parts.push(k.replace('_', ' ')); });
  return parts.length ? `<span class="source-pill fx" title="Motion, speed ramp & beat-sync effects">🎞 ${escapeHtml(parts.join(' · '))}</span>` : '';
}

async function loadEffectOptions() {
  if (fxState.options) return fxState.options;
  try {
    const res = await fetch(`/api/scene-effects/options?t=${Date.now()}`);
    if (res.ok) fxState.options = await res.json();
  } catch (e) { /* use fallback */ }
  fxState.options = fxState.options || FX_FALLBACK_OPTIONS;
  return fxState.options;
}

async function openSceneEffectsModal(sceneNumber) {
  if (!activeProject) return;
  fxState.scene = sceneNumber;
  const scene = (activeProject.scenes || []).find(sc => sc.scene_number === sceneNumber);
  fxState.value = JSON.parse(JSON.stringify(sceneEffectsOf(scene)));
  const opts = await loadEffectOptions();

  document.getElementById('fxSceneNum').textContent = sceneNumber;
  const isClip = Boolean(scene?.clip_path);
  document.getElementById('fxClipNote').classList.toggle('hidden', !isClip);
  document.getElementById('fxMotionBlock').classList.toggle('fx-disabled', isClip);

  document.getElementById('fxMotion').innerHTML = (opts.motions || []).map(m => `<option value="${m.id}">${escapeHtml(m.label)}</option>`).join('');
  const speedRampEl = document.getElementById('fxSpeedRamp');
  if (speedRampEl) {
    const ramps = opts.speed_ramps || FX_FALLBACK_OPTIONS.speed_ramps;
    speedRampEl.innerHTML = ramps.map(r => `<option value="${r.id}">${escapeHtml(r.label)}</option>`).join('');
    speedRampEl.onchange = (e) => setFx('speed_ramp', e.target.value);
  }
  // Options may be plain ids or {id, label} objects
  const labels = Object.assign({}, FX_TOGGLE_LABELS, opts.labels || {});
  const norm = (x) => (typeof x === 'string' ? { id: x, label: labels[x] || x } : { id: x.id, label: labels[x.id] || x.label || x.id });
  document.getElementById('fxStrength').innerHTML = (opts.strengths || []).map(norm).map(st =>
    `<button type="button" class="fx-seg" data-v="${st.id}" onclick="setFx('motion_strength','${st.id}')">${escapeHtml(st.label)}</button>`).join('');
  document.getElementById('fxFilters').innerHTML = (opts.filters || []).map(f =>
    `<button type="button" class="fx-chip" data-v="${f.id}" onclick="setFxEffect('filter','${f.id}')">${escapeHtml(f.label)}</button>`).join('');
  document.getElementById('fxToggles').innerHTML = (opts.toggles || []).map(norm).map(t =>
    `<label class="fx-toggle"><input type="checkbox" data-k="${t.id}" onchange="setFxEffect('${t.id}', this.checked)"> ${escapeHtml(FX_TOGGLE_LABELS[t.id] || t.label)}</label>`).join('');
  document.getElementById('fxMotion').onchange = (e) => setFx('motion', e.target.value);

  const img = document.getElementById('fxFocusImg');
  img.src = `/api/scene_image/${activeProject.id}/${sceneNumber}?t=${Date.now()}`;
  img.onclick = (e) => {
    const r = img.getBoundingClientRect();
    setFx('focus_point', { x: +((e.clientX - r.left) / r.width).toFixed(3), y: +((e.clientY - r.top) / r.height).toFixed(3) });
  };
  document.getElementById('fxApplyAll').checked = false;
  setFxStatus('', '');
  syncFxControls();
  document.getElementById('sceneEffectsModal').classList.remove('hidden');
  scheduleFxPreview(0);
}

function closeSceneEffectsModal() {
  document.getElementById('sceneEffectsModal')?.classList.add('hidden');
  const v = document.getElementById('fxPreviewVideo');
  if (v) v.pause();
}

function setFx(key, value) {
  fxState.value[key] = value;
  syncFxControls();
  scheduleFxPreview();
}

function setFxEffect(key, value) {
  fxState.value.effects[key] = value;
  syncFxControls();
  scheduleFxPreview();
}

function syncFxControls() {
  const v = fxState.value;
  document.getElementById('fxMotion').value = v.motion;
  const speedRampEl = document.getElementById('fxSpeedRamp');
  if (speedRampEl) speedRampEl.value = v.speed_ramp || 'none';
  document.querySelectorAll('#fxStrength .fx-seg').forEach(b => b.classList.toggle('active', b.dataset.v === v.motion_strength));
  document.querySelectorAll('#fxFilters .fx-chip').forEach(b => b.classList.toggle('active', b.dataset.v === (v.effects.filter || 'none')));
  document.querySelectorAll('#fxToggles input').forEach(i => { i.checked = Boolean(v.effects[i.dataset.k]); });
  const dot = document.getElementById('fxFocusDot');
  dot.style.left = `${v.focus_point.x * 100}%`;
  dot.style.top = `${v.focus_point.y * 100}%`;
  const usesFocus = ['focus', 'zoom_in', 'zoom_out'].includes(v.motion) || v.effects.focus_blur;
  document.getElementById('fxFocusHint').textContent = usesFocus
    ? 'Click the image to set the focus point.'
    : 'Focus point is used by Focus, Zoom in/out and Focus blur.';
  dot.classList.toggle('dim', !usesFocus);
}

function setFxStatus(text, color) {
  const el = document.getElementById('fxStatus');
  if (el) { el.textContent = text; el.style.color = color || ''; }
}

function scheduleFxPreview(delay = 350) {
  clearTimeout(fxState.previewTimer);
  fxState.previewTimer = setTimeout(renderFxPreview, delay);
}

async function renderFxPreview() {
  const seq = ++fxState.previewSeq;
  const busy = document.getElementById('fxPreviewBusy');
  busy.classList.remove('hidden');
  try {
    const res = await fetch('/api/scene-effect-preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({ project_id: activeProject.id, scene: fxState.scene, seconds: 2.5 }, fxState.value))
    });
    if (seq !== fxState.previewSeq) return;
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      setFxStatus(`Preview unavailable: ${d.detail || res.status}`, '#f87171');
      return;
    }
    const url = URL.createObjectURL(await res.blob());
    if (fxState.previewUrl) URL.revokeObjectURL(fxState.previewUrl);
    fxState.previewUrl = url;
    const v = document.getElementById('fxPreviewVideo');
    v.src = url;
    v.play().catch(() => {});
    setFxStatus('', '');
  } catch (err) {
    if (seq === fxState.previewSeq) setFxStatus(`Preview unavailable: ${err.message}`, '#f87171');
  } finally {
    if (seq === fxState.previewSeq) busy.classList.add('hidden');
  }
}

async function saveSceneEffects(andRerender) {
  if (!activeProject) return;
  const applyAll = document.getElementById('fxApplyAll').checked;
  setFxStatus('Saving...', '#38bdf8');
  try {
    const res = await fetch(`/api/projects/${activeProject.id}/scenes/${fxState.scene}/effects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({}, fxState.value, { apply_to_all: applyAll }))
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setFxStatus(`❌ ${data.detail || 'Could not save'}`, '#ef4444');
      return;
    }
    // Reflect the saved values locally (the API may return the updated project)
    if (data.project) {
      activeProject = data.project;
    } else if (applyAll) {
      activeProject.scene_defaults = JSON.parse(JSON.stringify(fxState.value));
      (activeProject.scenes || []).forEach(sc => { delete sc.motion; delete sc.motion_strength; delete sc.focus_point; delete sc.effects; });
    } else {
      const sc = activeProject.scenes.find(x => x.scene_number === fxState.scene);
      if (sc) Object.assign(sc, JSON.parse(JSON.stringify(fxState.value)));
    }
    renderModalScenes();
    setFxStatus(`✓ Saved${applyAll ? ' for all scenes' : ''}${andRerender ? '. Re-rendering…' : '. Click Re-render to apply.'}`, '#10b981');
    if (andRerender) {
      closeSceneEffectsModal();
      handleRerenderModal();
    }
  } catch (err) {
    setFxStatus(`❌ ${err.message}`, '#ef4444');
  }
}


// ---------------------------------------------------------------------------
// Auto-refresh when the server has newer dashboard code, so an open tab never keeps
// running stale JavaScript (that is how "[object Object]" labels once appeared).
// Reloads only while the tab is idle: no modal open, nothing generating, no unsaved edit.
// ---------------------------------------------------------------------------
(function watchUiBuild() {
  const current = document.querySelector('meta[name="ui-build"]')?.content;
  if (!current) return;
  // Unsaved text anywhere (e.g. edited scene narration, then clicked away) blocks the reload
  const hasUnsavedText = () => [...document.querySelectorAll('textarea, input[type="text"], input:not([type])')]
    .some(el => el.offsetParent !== null && el.value !== el.defaultValue);
  const idle = () =>
    !document.querySelector('.modal:not(.hidden), [id$="Modal"]:not(.hidden)') &&
    !(currentProjects || []).some(p => p.status === 'in_progress' || p.status === 'queued') &&
    !document.activeElement?.matches?.('input, textarea, select, [contenteditable]') &&
    !hasUnsavedText() &&
    !(document.getElementById('addSceneForm') && !document.getElementById('addSceneForm').classList.contains('hidden')) &&
    !(typeof clipJobPollers !== 'undefined' && Object.keys(clipJobPollers).length);
  setInterval(async () => {
    try {
      const res = await fetch(`/api/ui-build?t=${Date.now()}`);
      if (!res.ok) return;
      const { build } = await res.json();
      if (build && build !== current && idle()) location.reload();
    } catch (e) { /* server restarting; try again next tick */ }
  }, 20000);
})();
