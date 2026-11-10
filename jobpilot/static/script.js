/**
 * JobPortal Autonomous Matching Platform — Core Client Application
 * Clean, production-ready vanilla JS managing Auth, Gmail OTP,
 * Strict Multi-Filter Catalog, Personalized Matches, CV Vault, and Bookmarks.
 */

const API_BASE = '/api';

// Application State
const state = {
  token: localStorage.getItem('jobportal_token') || null,
  user: null,
  profile: null,
  currentView: 'landing', // 'landing', 'explorer', 'matches', 'saved', 'profile'
  filters: {
    search: '',
    job_type: 'all',
    work_arrangement: 'all',
    location: 'all',
    experience_level: 'all',
    industry: 'all',
    date_range: '24h', // Default 24h as required
    sort_by: 'newest',
    page: 1,
    limit: 25,
  },
  pendingRegister: {
    email: '',
    username: '',
  },
  otpTimer: null,
  resendCooldownTimer: null,
};

// ── HTTP Client Helper ────────────────────────────────────────────────────────
async function apiRequest(endpoint, options = {}) {
  const headers = options.headers || {};
  if (state.token) {
    headers['Authorization'] = `Bearer ${state.token}`;
  }
  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  const isJson = (res.headers.get('content-type') || '').includes('application/json');
  const data = isJson ? await res.json() : await res.text();

  if (!res.ok) {
    const errorMsg = (data && data.detail) || (data && data.message) || (typeof data === 'string' ? data : 'Request failed');
    throw new Error(errorMsg);
  }
  return data;
}

// ── Toast Notifications ───────────────────────────────────────────────────────
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}</span> <span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.2s ease';
    setTimeout(() => toast.remove(), 250);
  }, 4000);
}

// ── Navigation & View Switching ───────────────────────────────────────────────
function switchView(viewName) {
  state.currentView = viewName;

  document.querySelectorAll('.app-view').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));

  const activeBtn = document.getElementById(`nav-btn-${viewName}`);
  if (activeBtn) activeBtn.classList.add('active');

  const viewEl = document.getElementById(`view-${viewName}`);
  if (viewEl) {
    viewEl.style.display = 'block';
  }

  if (viewName === 'landing') {
    loadFeaturedJobs();
    loadTelemetry();
  } else if (viewName === 'explorer') {
    loadJobs();
  } else if (viewName === 'matches') {
    if (!state.user) {
      openAuthModal('login');
      return;
    }
    loadMatches();
  } else if (viewName === 'saved') {
    if (!state.user) {
      openAuthModal('login');
      return;
    }
    loadSavedJobs();
  } else if (viewName === 'profile') {
    if (!state.user) {
      openAuthModal('login');
      return;
    }
    loadProfile();
  }

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── Auth & Session Handling ───────────────────────────────────────────────────
async function checkAuthState() {
  if (!state.token) {
    renderUserNav();
    return;
  }
  try {
    const user = await apiRequest('/auth/me');
    state.user = user;
  } catch (err) {
    console.warn('Session expired or invalid:', err);
    state.token = null;
    state.user = null;
    localStorage.removeItem('jobportal_token');
  }
  renderUserNav();
}

function renderUserNav() {
  const authNav = document.getElementById('nav-user-actions');
  if (!authNav) return;

  if (state.user) {
    authNav.innerHTML = `
      <div style="display:flex; align-items:center; gap:10px;">
        <span style="font-size:13px; font-weight:700; color:var(--ink-primary); background:var(--bg-surface-raised); border:1px solid var(--border); padding:6px 12px; border-radius:9999px;">
          👤 ${state.user.username}
        </span>
        <button class="btn-outline" onclick="doLogout()">Sign Out</button>
      </div>
    `;
    const profileBtn = document.getElementById('nav-btn-profile');
    if (profileBtn) profileBtn.style.display = 'flex';
    const matchesBtn = document.getElementById('nav-btn-matches');
    if (matchesBtn) matchesBtn.style.display = 'flex';
    const savedBtn = document.getElementById('nav-btn-saved');
    if (savedBtn) savedBtn.style.display = 'flex';
  } else {
    authNav.innerHTML = `
      <button class="btn-outline" onclick="openAuthModal('login')">Sign In</button>
      <button class="btn-primary" onclick="openAuthModal('register')">Create Account</button>
    `;
    const profileBtn = document.getElementById('nav-btn-profile');
    if (profileBtn) profileBtn.style.display = 'none';
    const matchesBtn = document.getElementById('nav-btn-matches');
    if (matchesBtn) matchesBtn.style.display = 'none';
    const savedBtn = document.getElementById('nav-btn-saved');
    if (savedBtn) savedBtn.style.display = 'none';
  }
}

function openAuthModal(mode = 'login') {
  const modal = document.getElementById('auth-modal');
  if (!modal) return;
  modal.style.display = 'flex';
  switchAuthTab(mode);
}

function closeAuthModal() {
  const modal = document.getElementById('auth-modal');
  if (modal) modal.style.display = 'none';
  clearInterval(state.otpTimer);
  clearInterval(state.resendCooldownTimer);
}

function switchAuthTab(tab) {
  document.querySelectorAll('.auth-tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.auth-tab-pane').forEach(p => p.style.display = 'none');

  const tabBtn = document.getElementById(`tab-btn-${tab}`);
  if (tabBtn) tabBtn.classList.add('active');

  const pane = document.getElementById(`auth-pane-${tab}`);
  if (pane) pane.style.display = 'block';

  const errEl = document.getElementById('auth-error-msg');
  if (errEl) errEl.textContent = '';
}

async function handleLoginSubmit(event) {
  event.preventDefault();
  const emailInput = document.getElementById('login-email').value.trim();
  const passInput = document.getElementById('login-password').value;
  const btn = document.getElementById('btn-login-submit');

  if (!emailInput || !passInput) {
    showAuthError('Please fill in both email/username and password.');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Signing in...';

  try {
    const data = await apiRequest('/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        username_or_email: emailInput,
        password: passInput,
      }),
    });

    state.token = data.token;
    state.user = data.user;
    localStorage.setItem('jobportal_token', data.token);

    closeAuthModal();
    renderUserNav();
    showToast(`Welcome back, ${data.user.username}!`, 'success');
    switchView('explorer');
  } catch (err) {
    showAuthError(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Sign In';
  }
}

// ── Step 1: Registration Request (Sends Gmail OTP) ───────────────────────────
async function handleRegisterRequest(event) {
  event.preventDefault();
  const username = document.getElementById('reg-username').value.trim();
  const email = document.getElementById('reg-email').value.trim();
  const password = document.getElementById('reg-password').value;
  const btn = document.getElementById('btn-reg-request');

  if (username.length < 3) {
    showAuthError('Username must be at least 3 characters.');
    return;
  }
  if (!email.includes('@') || !email.includes('.')) {
    showAuthError('Please enter a valid email address.');
    return;
  }
  if (password.length < 6) {
    showAuthError('Password must be at least 6 characters.');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Sending Verification Code...';

  try {
    const res = await apiRequest('/auth/register-request', {
      method: 'POST',
      body: JSON.stringify({ username, email, password }),
    });

    state.pendingRegister = { email, username };

    // Move to Step 2 OTP Screen
    document.getElementById('auth-pane-register').style.display = 'none';
    document.getElementById('auth-pane-otp').style.display = 'block';
    document.getElementById('otp-target-email').textContent = email;

    if (res.dev_code) {
      document.getElementById('otp-dev-hint').innerHTML = `
        <span style="background:#fef3c7; color:#b45309; padding:4px 8px; border-radius:4px; font-weight:700;">
          [DEV MODE CODE]: ${res.dev_code}
        </span>
      `;
    } else {
      document.getElementById('otp-dev-hint').innerHTML = '';
    }

    startOtpCountdown(res.expires_in_seconds || 600);
    startResendCooldown(res.cooldown_seconds || 60);

    showToast('Verification code dispatched to your email!', 'success');
  } catch (err) {
    showAuthError(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Continue to Verification';
  }
}

// ── Step 2: Verify Registration OTP ──────────────────────────────────────────
async function handleOtpSubmit(event) {
  event.preventDefault();
  const otp = document.getElementById('otp-code-input').value.trim();
  const btn = document.getElementById('btn-verify-otp');

  if (otp.length !== 6) {
    showAuthError('Please enter the complete 6-digit code.');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Verifying Code...';

  try {
    const res = await apiRequest('/auth/register-verify', {
      method: 'POST',
      body: JSON.stringify({
        email: state.pendingRegister.email,
        otp: otp,
      }),
    });

    state.token = res.token;
    state.user = res.user;
    localStorage.setItem('jobportal_token', res.token);

    closeAuthModal();
    renderUserNav();
    showToast('Account activated successfully! Welcome to JobPortal.', 'success');
    switchView('profile');
  } catch (err) {
    showAuthError(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Verify & Activate Account';
  }
}

async function handleResendOtp() {
  const btn = document.getElementById('btn-resend-otp');
  if (btn.disabled) return;

  btn.disabled = true;
  try {
    const res = await apiRequest('/auth/resend-otp', {
      method: 'POST',
      body: JSON.stringify({
        email: state.pendingRegister.email,
        purpose: 'registration',
      }),
    });

    if (res.dev_code) {
      document.getElementById('otp-dev-hint').innerHTML = `
        <span style="background:#fef3c7; color:#b45309; padding:4px 8px; border-radius:4px; font-weight:700;">
          [DEV MODE CODE]: ${res.dev_code}
        </span>
      `;
    }

    startResendCooldown(res.cooldown_seconds || 60);
    showToast('New verification code sent!', 'success');
  } catch (err) {
    showAuthError(err.message);
    btn.disabled = false;
  }
}

function startOtpCountdown(seconds) {
  clearInterval(state.otpTimer);
  let remaining = seconds;
  const timerEl = document.getElementById('otp-countdown');

  state.otpTimer = setInterval(() => {
    remaining--;
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    if (timerEl) {
      timerEl.textContent = `${mins}:${secs < 10 ? '0' : ''}${secs}`;
    }
    if (remaining <= 0) {
      clearInterval(state.otpTimer);
      if (timerEl) timerEl.textContent = 'Expired';
    }
  }, 1000);
}

function startResendCooldown(seconds) {
  clearInterval(state.resendCooldownTimer);
  let remaining = seconds;
  const btn = document.getElementById('btn-resend-otp');
  if (!btn) return;

  btn.disabled = true;
  btn.textContent = `Resend Code (${remaining}s)`;

  state.resendCooldownTimer = setInterval(() => {
    remaining--;
    if (remaining <= 0) {
      clearInterval(state.resendCooldownTimer);
      btn.disabled = false;
      btn.textContent = 'Resend Code';
    } else {
      btn.textContent = `Resend Code (${remaining}s)`;
    }
  }, 1000);
}

// ── Forgot Password Flow ──────────────────────────────────────────────────────
async function handleForgotSubmit(event) {
  event.preventDefault();
  const email = document.getElementById('forgot-email').value.trim();
  const btn = document.getElementById('btn-forgot-submit');

  if (!email) {
    showAuthError('Please enter your account email.');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Sending Reset Code...';

  try {
    const res = await apiRequest('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });

    state.pendingRegister.email = email;
    document.getElementById('auth-pane-forgot').style.display = 'none';
    document.getElementById('auth-pane-reset').style.display = 'block';

    if (res.dev_code) {
      document.getElementById('reset-dev-hint').innerHTML = `
        <span style="background:#fef3c7; color:#b45309; padding:4px 8px; border-radius:4px; font-weight:700;">
          [DEV RESET CODE]: ${res.dev_code}
        </span>
      `;
    }

    showToast('Password reset code sent to your email.', 'success');
  } catch (err) {
    showAuthError(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Send Reset Code';
  }
}

async function handleResetSubmit(event) {
  event.preventDefault();
  const otp = document.getElementById('reset-otp').value.trim();
  const newPassword = document.getElementById('reset-new-password').value;
  const btn = document.getElementById('btn-reset-submit');

  if (otp.length !== 6 || newPassword.length < 6) {
    showAuthError('Please enter the 6-digit code and a new password (min 6 chars).');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Updating Password...';

  try {
    await apiRequest('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({
        email: state.pendingRegister.email,
        otp,
        new_password: newPassword,
      }),
    });

    showToast('Password reset successfully. Please sign in.', 'success');
    switchAuthTab('login');
  } catch (err) {
    showAuthError(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Update Password';
  }
}

function showAuthError(msg) {
  const errEl = document.getElementById('auth-error-msg');
  if (errEl) errEl.textContent = msg;
}

function doLogout() {
  if (state.token) {
    apiRequest('/auth/logout', { method: 'POST' }).catch(() => {});
  }
  state.token = null;
  state.user = null;
  localStorage.removeItem('jobportal_token');
  renderUserNav();
  showToast('You have signed out.', 'info');
  switchView('landing');
}

// ── Job Catalog & Strict Multi-Filter Logic ──────────────────────────────────
async function loadJobs() {
  const container = document.getElementById('job-cards-container');
  const countEl = document.getElementById('total-jobs-count');
  const tagsBar = document.getElementById('applied-filters-bar');
  if (!container) return;

  container.innerHTML = `
    <div style="text-align:center; padding:60px 20px; color:var(--ink-secondary);">
      <div style="font-size:24px; margin-bottom:8px;">⏳</div>
      <div>Loading verified job opportunities...</div>
    </div>
  `;

  const queryParams = new URLSearchParams();
  if (state.filters.search) queryParams.set('search', state.filters.search);
  if (state.filters.job_type !== 'all') queryParams.set('job_type', state.filters.job_type);
  if (state.filters.work_arrangement !== 'all') queryParams.set('work_arrangement', state.filters.work_arrangement);
  if (state.filters.location !== 'all') queryParams.set('location', state.filters.location);
  if (state.filters.experience_level !== 'all') queryParams.set('experience_level', state.filters.experience_level);
  if (state.filters.industry !== 'all') queryParams.set('industry', state.filters.industry);
  if (state.filters.date_range) queryParams.set('date_range', state.filters.date_range);
  if (state.filters.sort_by) queryParams.set('sort_by', state.filters.sort_by);

  const offset = (state.filters.page - 1) * state.filters.limit;
  queryParams.set('offset', offset);
  queryParams.set('limit', state.filters.limit);

  try {
    const data = await apiRequest(`/jobs?${queryParams.toString()}`);

    if (countEl) countEl.innerHTML = `<span>${data.total}</span> Jobs Matching Filter`;

    // Render applied filter tags
    if (tagsBar) {
      if (data.applied_filters && data.applied_filters.length > 0) {
        tagsBar.innerHTML = data.applied_filters.map(tag => `
          <div class="applied-tag">
            <span>${tag}</span>
          </div>
        `).join('') + `
          <button class="btn-reset-filters" onclick="resetAllFilters()">Clear All</button>
        `;
      } else {
        tagsBar.innerHTML = '';
      }
    }

    if (!data.jobs || data.jobs.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🔍</div>
          <h3 class="empty-title">No listings match your exact filter criteria</h3>
          <p class="empty-desc">Try broadening your date range to "All Historical" or resetting specific experience/location constraints.</p>
          <button class="btn-primary" onclick="resetAllFilters()">Reset Filters</button>
        </div>
      `;
      renderPagination(0);
      return;
    }

    container.innerHTML = data.jobs.map(renderJobCardHtml).join('');
    renderPagination(data.total);

  } catch (err) {
    container.innerHTML = `
      <div class="empty-state" style="border-color:var(--crimson-border);">
        <div class="empty-icon">⚠️</div>
        <h3 class="empty-title">Could not load job listings</h3>
        <p class="empty-desc">${err.message}</p>
        <button class="btn-outline" onclick="loadJobs()">Retry</button>
      </div>
    `;
  }
}

function renderJobCardHtml(job) {
  const remoteBadge = job.remote_type === 'remote' ? `<span class="badge-remote">Remote</span>` :
                      job.remote_type === 'hybrid' ? `<span class="badge-hybrid">Hybrid</span>` : '';
  const internBadge = (job.employment_type === 'internship' || job.title.toLowerCase().includes('intern')) ?
                      `<span class="badge-intern">Internship</span>` : '';

  const salaryDisplay = job.salary_max ?
    `$${job.salary_min ? job.salary_min.toLocaleString() + ' - ' : ''}${job.salary_max.toLocaleString()}` :
    (job.salary_raw || 'Competitive');

  const matchBadge = job.match_score ? `
    <div class="match-score-badge ${job.match_score >= 80 ? 'match-high' : job.match_score >= 60 ? 'match-good' : 'match-possible'}">
      ★ ${job.match_score}% Match
    </div>
  ` : '';

  const postedDate = job.posting_date ? new Date(job.posting_date).toLocaleDateString() : 'Recent';

  return `
    <div class="job-card" onclick="openJobDetail('${job.id}')">
      <div class="job-main">
        <div class="job-title-row">
          <span class="job-title">${escapeHtml(job.title)}</span>
          ${internBadge}
          ${remoteBadge}
          ${matchBadge}
        </div>
        <div class="job-company">${escapeHtml(job.company)}</div>
        <div class="job-meta-row">
          <span class="job-meta-item">📍 ${escapeHtml(job.location)}</span>
          <span class="job-meta-item">💰 ${salaryDisplay}</span>
          <span class="job-meta-item">🌐 ${escapeHtml(job.source_name)}</span>
          <span class="job-meta-item">📅 ${postedDate}</span>
        </div>
        ${job.match_reason ? `<div style="font-size:12px; color:var(--primary); font-weight:600; margin-top:4px;">✨ ${escapeHtml(job.match_reason)}</div>` : ''}
      </div>
      <div class="job-actions" onclick="event.stopPropagation()">
        <button class="btn-bookmark ${job.is_saved ? 'active' : ''}" title="${job.is_saved ? 'Saved' : 'Save Job'}" onclick="toggleSaveJob('${job.id}', this)">
          ${job.is_saved ? '★' : '☆'}
        </button>
        <button class="btn-outline" onclick="openJobDetail('${job.id}')">View Details</button>
      </div>
    </div>
  `;
}

function renderPagination(total) {
  const container = document.getElementById('pagination-container');
  if (!container) return;

  const totalPages = Math.ceil(total / state.filters.limit);
  if (totalPages <= 1) {
    container.innerHTML = '';
    return;
  }

  const currentPage = state.filters.page;
  container.innerHTML = `
    <button class="btn-outline" ${currentPage <= 1 ? 'disabled style="opacity:0.5"' : ''} onclick="changePage(${currentPage - 1})">← Previous</button>
    <span style="font-size:13px; font-weight:700; color:var(--ink-secondary); padding:0 8px;">
      Page ${currentPage} of ${totalPages}
    </span>
    <button class="btn-outline" ${currentPage >= totalPages ? 'disabled style="opacity:0.5"' : ''} onclick="changePage(${currentPage + 1})">Next →</button>
  `;
}

function changePage(page) {
  state.filters.page = page;
  loadJobs();
}

function applyFilterChange(key, value) {
  state.filters[key] = value;
  state.filters.page = 1;
  loadJobs();
}

function handleSearchKeydown(event) {
  if (event.key === 'Enter') {
    state.filters.search = event.target.value.trim();
    state.filters.page = 1;
    loadJobs();
  }
}

function resetAllFilters() {
  state.filters = {
    search: '',
    job_type: 'all',
    work_arrangement: 'all',
    location: 'all',
    experience_level: 'all',
    industry: 'all',
    date_range: '24h',
    sort_by: 'newest',
    page: 1,
    limit: 25,
  };

  // Reset UI elements
  const searchInput = document.getElementById('explorer-search-input');
  if (searchInput) searchInput.value = '';
  document.querySelectorAll('.filter-select').forEach(s => s.value = 'all');
  const dateRangeSelect = document.getElementById('filter-date-range');
  if (dateRangeSelect) dateRangeSelect.value = '24h';

  loadJobs();
}

// ── Job Details Slide-over Drawer ─────────────────────────────────────────────
async function openJobDetail(jobId) {
  const drawer = document.getElementById('job-detail-drawer');
  const content = document.getElementById('drawer-job-content');
  if (!drawer || !content) return;

  drawer.style.display = 'flex';
  content.innerHTML = `<div style="text-align:center; padding:60px;">⏳ Loading job details...</div>`;

  try {
    const job = await apiRequest(`/jobs/${jobId}`);

    const salaryText = job.salary_max ?
      `$${job.salary_min ? job.salary_min.toLocaleString() + ' - ' : ''}${job.salary_max.toLocaleString()}` :
      (job.salary_raw || 'Competitive / Not Disclosed');

    const matchBlock = job.match ? `
      <div style="background:var(--primary-light); border:1px solid var(--primary-border); border-radius:var(--radius-md); padding:16px; margin-bottom:16px;">
        <div style="font-weight:800; color:var(--primary); font-size:15px; margin-bottom:6px;">
          ★ ${job.match.overall_score}% Match Score (${job.match.score_label})
        </div>
        <div style="font-size:13px; color:var(--ink-secondary); line-height:1.5;">
          ${escapeHtml(job.match.reasons)}
        </div>
        ${job.match.strong_matches && job.match.strong_matches.length > 0 ? `
          <div style="margin-top:10px; display:flex; flex-wrap:wrap; gap:6px;">
            ${job.match.strong_matches.map(s => `<span class="skill-tag" style="background:#dbeafe; color:#1d4ed8;">✓ ${escapeHtml(s)}</span>`).join('')}
          </div>
        ` : ''}
      </div>
    ` : '';

    content.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px;">
        <div>
          <h2 style="font-size:24px; font-weight:800; color:var(--ink-primary); letter-spacing:-0.02em; margin-bottom:6px;">
            ${escapeHtml(job.title)}
          </h2>
          <div style="font-size:16px; font-weight:600; color:var(--primary);">
            ${escapeHtml(job.company)}
          </div>
        </div>
        <button class="modal-close-btn" onclick="closeJobDrawer()">✕</button>
      </div>

      ${matchBlock}

      <div style="display:grid; grid-template-columns:repeat(2, 1fr); gap:12px; margin-bottom:20px; font-size:13px; background:var(--bg-surface-raised); padding:16px; border-radius:var(--radius-md);">
        <div><strong>Location:</strong> ${escapeHtml(job.location)}</div>
        <div><strong>Arrangement:</strong> ${job.remote_type.toUpperCase()}</div>
        <div><strong>Job Type:</strong> ${job.employment_type.replace('_', ' ').toUpperCase()}</div>
        <div><strong>Compensation:</strong> ${salaryText}</div>
        <div><strong>Discovered:</strong> ${job.discovered_at ? new Date(job.discovered_at).toLocaleDateString() : 'Recent'}</div>
        <div><strong>Source:</strong> ${escapeHtml(job.source_name)}</div>
      </div>

      <div style="display:flex; gap:12px; margin-bottom:24px;">
        <a href="${escapeHtml(job.application_url)}" target="_blank" rel="noopener noreferrer" class="btn-primary" style="flex:1; justify-content:center; text-align:center;">
          Apply on Company Site ↗
        </a>
        <button class="btn-outline ${job.is_saved ? 'btn-bookmark active' : ''}" onclick="toggleSaveJob('${job.id}', this)">
          ${job.is_saved ? '★ Saved' : '☆ Save Job'}
        </button>
      </div>

      <h3 style="font-size:16px; font-weight:700; margin-bottom:8px;">Job Description</h3>
      <div class="drawer-desc-box">
        ${escapeHtml(job.description)}
      </div>
    `;

  } catch (err) {
    content.innerHTML = `
      <div style="padding:40px; text-align:center; color:var(--crimson);">
        <p>Could not load listing: ${err.message}</p>
        <button class="btn-outline" onclick="closeJobDrawer()">Close</button>
      </div>
    `;
  }
}

function closeJobDrawer() {
  const drawer = document.getElementById('job-detail-drawer');
  if (drawer) drawer.style.display = 'none';
}

// ── Bookmark / Save Job ──────────────────────────────────────────────────────
async function toggleSaveJob(jobId, btnElement) {
  if (!state.user) {
    openAuthModal('login');
    return;
  }

  const isSaved = btnElement.classList.contains('active');
  try {
    if (isSaved) {
      await apiRequest(`/jobs/${jobId}/save`, { method: 'DELETE' });
      btnElement.classList.remove('active');
      btnElement.innerHTML = '☆';
      showToast('Removed from saved jobs', 'info');
    } else {
      await apiRequest(`/jobs/${jobId}/save`, { method: 'POST' });
      btnElement.classList.add('active');
      btnElement.innerHTML = '★';
      showToast('Job bookmarked to Saved Jobs', 'success');
    }
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ── Personalized Matches Tab ──────────────────────────────────────────────────
async function loadMatches() {
  const container = document.getElementById('matches-cards-container');
  if (!container) return;

  container.innerHTML = `<div style="text-align:center; padding:60px;">⏳ Scoring catalog against your profile...</div>`;

  try {
    const data = await apiRequest('/matches?min_score=40');
    if (!data.matches || data.matches.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🎯</div>
          <h3 class="empty-title">No Personalized Matches Yet</h3>
          <p class="empty-desc">Upload your PDF CV in the Profile tab to unlock automatic, explainable job matches tailored to your skills.</p>
          <button class="btn-primary" onclick="switchView('profile')">Upload CV</button>
        </div>
      `;
      return;
    }

    container.innerHTML = data.matches.map(m => `
      <div class="job-card" onclick="openJobDetail('${m.id}')">
        <div class="job-main">
          <div class="job-title-row">
            <span class="job-title">${escapeHtml(m.title)}</span>
            <span class="match-score-badge ${m.overall_score >= 80 ? 'match-high' : 'match-good'}">
              ★ ${m.overall_score}% Match
            </span>
            ${m.remote_type === 'remote' ? '<span class="badge-remote">Remote</span>' : ''}
          </div>
          <div class="job-company">${escapeHtml(m.company)} • 📍 ${escapeHtml(m.location)}</div>
          <div style="font-size:13px; color:var(--primary); font-weight:600; margin:4px 0;">
            ✨ Why it matches: ${escapeHtml(m.reasons || 'Direct skill & title fit')}
          </div>
          ${m.strong_matches && m.strong_matches.length > 0 ? `
            <div class="skills-tags-row">
              ${m.strong_matches.map(s => `<span class="skill-tag" style="background:#eff6ff; color:#2563eb;">✓ ${escapeHtml(s)}</span>`).join('')}
            </div>
          ` : ''}
        </div>
        <div class="job-actions" onclick="event.stopPropagation()">
          <button class="btn-primary" onclick="openJobDetail('${m.id}')">View Details</button>
        </div>
      </div>
    `).join('');

  } catch (err) {
    container.innerHTML = `<div class="empty-state"><p>${err.message}</p></div>`;
  }
}

// ── Saved Jobs Tab ────────────────────────────────────────────────────────────
async function loadSavedJobs() {
  const container = document.getElementById('saved-cards-container');
  if (!container) return;

  container.innerHTML = `<div style="text-align:center; padding:60px;">⏳ Loading your saved jobs...</div>`;

  try {
    const list = await apiRequest('/saved-jobs');
    if (!list || list.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📑</div>
          <h3 class="empty-title">You haven't bookmarked any jobs yet</h3>
          <p class="empty-desc">Click the star button on any job card to save it for later review.</p>
          <button class="btn-primary" onclick="switchView('explorer')">Explore Catalog</button>
        </div>
      `;
      return;
    }

    container.innerHTML = list.map(job => `
      <div class="job-card" onclick="openJobDetail('${job.job_id}')">
        <div class="job-main">
          <div class="job-title-row">
            <span class="job-title">${escapeHtml(job.title)}</span>
            ${job.remote_type === 'remote' ? '<span class="badge-remote">Remote</span>' : ''}
          </div>
          <div class="job-company">${escapeHtml(job.company)} • 📍 ${escapeHtml(job.location)}</div>
          <div class="job-meta-row">
            <span>Saved on: ${new Date(job.saved_at).toLocaleDateString()}</span>
            <span>Source: ${escapeHtml(job.source_name)}</span>
          </div>
        </div>
        <div class="job-actions" onclick="event.stopPropagation()">
          <a href="${escapeHtml(job.application_url)}" target="_blank" rel="noopener noreferrer" class="btn-primary">Apply ↗</a>
          <button class="btn-outline" onclick="removeSavedJobDirect('${job.job_id}')">Remove</button>
        </div>
      </div>
    `).join('');

  } catch (err) {
    container.innerHTML = `<div class="empty-state"><p>${err.message}</p></div>`;
  }
}

async function removeSavedJobDirect(jobId) {
  try {
    await apiRequest(`/jobs/${jobId}/save`, { method: 'DELETE' });
    showToast('Removed from saved jobs', 'info');
    loadSavedJobs();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ── Profile & CV Upload ───────────────────────────────────────────────────────
async function loadProfile() {
  try {
    const p = await apiRequest('/profile');
    state.profile = p;

    document.getElementById('prof-name').value = p.name || '';
    document.getElementById('prof-email').value = p.email || '';
    document.getElementById('prof-phone').value = p.phone || '';
    document.getElementById('prof-location').value = p.location || '';
    document.getElementById('prof-remote-pref').value = p.remote_preference || 'worldwide_remote';
    document.getElementById('prof-exp-years').value = p.years_experience || 1;
    document.getElementById('prof-skills').value = (p.skills || []).join(', ');
    document.getElementById('prof-roles').value = (p.preferred_roles || []).join(', ');
    document.getElementById('prof-summary').value = p.summary || '';

    const cvStatus = document.getElementById('cv-status-indicator');
    if (cvStatus) {
      if (p.has_cv) {
        cvStatus.innerHTML = `
          <div style="background:#ecfdf5; border:1px solid #a7f3d0; color:#065f46; padding:10px 14px; border-radius:6px; font-weight:600; font-size:13px;">
            ✓ Active CV: ${escapeHtml(p.cv_filename || 'Uploaded PDF')} (Parsed & Indexed)
          </div>
        `;
      } else {
        cvStatus.innerHTML = `
          <div style="background:#fffbeb; border:1px solid #fde68a; color:#92400e; padding:10px 14px; border-radius:6px; font-size:13px;">
            ⚠️ No CV uploaded yet. Upload your PDF below to auto-extract skills and target roles.
          </div>
        `;
      }
    }
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function handleProfileUpdate(event) {
  event.preventDefault();
  const btn = document.getElementById('btn-save-profile');
  btn.disabled = true;
  btn.textContent = 'Saving Changes...';

  const skillsList = document.getElementById('prof-skills').value.split(',').map(s => s.trim()).filter(Boolean);
  const rolesList = document.getElementById('prof-roles').value.split(',').map(r => r.trim()).filter(Boolean);

  const payload = {
    name: document.getElementById('prof-name').value.trim(),
    phone: document.getElementById('prof-phone').value.trim(),
    location: document.getElementById('prof-location').value.trim(),
    remote_preference: document.getElementById('prof-remote-pref').value,
    years_experience: parseFloat(document.getElementById('prof-exp-years').value) || 1.0,
    skills: skillsList,
    preferred_roles: rolesList,
    summary: document.getElementById('prof-summary').value.trim(),
  };

  try {
    await apiRequest('/profile', {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    showToast('Profile and preferences updated! Matches recalculating in background.', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Save Profile Changes';
  }
}

async function handleCvUpload(file) {
  if (!file) return;

  if (!file.name.toLowerCase().endsWith('.pdf') && !file.name.toLowerCase().endsWith('.docx') && !file.name.toLowerCase().endsWith('.txt')) {
    showToast('Please upload a PDF, DOCX, or TXT file.', 'error');
    return;
  }

  const formData = new FormData();
  formData.append('file', file);
  formData.append('name', file.name);

  const statusEl = document.getElementById('cv-upload-status');
  if (statusEl) {
    statusEl.innerHTML = `<span style="color:var(--primary); font-weight:700;">⏳ Uploading and parsing CV with AI fallback engine...</span>`;
  }

  try {
    const data = await apiRequest('/cvs/upload', {
      method: 'POST',
      body: formData,
    });

    if (statusEl) {
      statusEl.innerHTML = `<span style="color:var(--emerald); font-weight:700;">✓ CV successfully parsed! Extracted ${data.skills ? data.skills.length : 0} skills.</span>`;
    }

    showToast('CV uploaded and parsed! Profile updated.', 'success');
    loadProfile();
  } catch (err) {
    if (statusEl) {
      statusEl.innerHTML = `<span style="color:var(--crimson); font-weight:700;">✕ Upload failed: ${err.message}</span>`;
    }
    showToast(err.message, 'error');
  }
}

// ── Landing Page Featured Jobs & Telemetry ─────────────────────────────────────
async function loadFeaturedJobs() {
  const container = document.getElementById('featured-jobs-grid');
  if (!container) return;

  try {
    const data = await apiRequest('/jobs?limit=6&date_range=24h');
    if (!data.jobs || data.jobs.length === 0) {
      container.innerHTML = `<p style="text-align:center; color:var(--ink-secondary);">No fresh jobs in the last 24h. Browse all historical listings in the Catalog.</p>`;
      return;
    }
    container.innerHTML = data.jobs.map(renderJobCardHtml).join('');
  } catch (err) {
    console.error('Featured jobs load error:', err);
  }
}

async function loadTelemetry() {
  try {
    const t = await apiRequest('/jobs/telemetry');
    const jobsCountEl = document.getElementById('telemetry-total-jobs');
    const sourcesCountEl = document.getElementById('telemetry-total-sources');
    const fresh24hEl = document.getElementById('telemetry-fresh-24h');

    if (jobsCountEl) jobsCountEl.textContent = t.total_jobs ? t.total_jobs.toLocaleString() : '680+';
    if (sourcesCountEl) sourcesCountEl.textContent = t.total_sources || '14';
    if (fresh24hEl) fresh24hEl.textContent = t.fresh_24h || '24';
  } catch (err) {
    console.error('Telemetry error:', err);
  }
}

function handleHeroSearch() {
  const input = document.getElementById('hero-search-input');
  if (!input) return;
  const term = input.value.trim();
  state.filters.search = term;
  state.filters.page = 1;
  switchView('explorer');
}

function selectQuickPill(type, value) {
  state.filters = {
    ...state.filters,
    search: '',
    job_type: 'all',
    industry: 'all',
    location: 'all',
    date_range: 'all',
  };
  state.filters[type] = value;
  switchView('explorer');
}

// ── Helper ────────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ── Initialization ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  checkAuthState();
  switchView('landing');
});
