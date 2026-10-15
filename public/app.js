const $ = (selector) => document.querySelector(selector);
const AVATAR_URL = '/assets/moki-listening-avatar.png?v=20261015';
const API_MODAL_DELAY_MS = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 350 : 2800;
let openAIAPIKey = '';
const state = {
  history: [], cart: [], orderNo: null, stateToken: null,
  cartStatus: null, staffChecked: false, tableId: 5,
  staffVerificationRequired: false, staffVerificationReason: null,
  staffChallenge: null, staffAuthorization: null, pendingStaffRequest: null,
  sources: [], menu: [], category: '커피', busy: false,
  contentReady: false, serverAIReady: false, mockMode: false,
};

const won = (value) => `${Number(value || 0).toLocaleString('ko-KR')}원`;

function setConnection(kind, text) {
  const element = $('#connectionStatus');
  element.className = `connection ${kind || ''}`;
  element.querySelector('span').textContent = text;
}

function refreshConnectionStatus() {
  const keyButton = $('#apiKeyButton');
  keyButton.classList.toggle('connected', Boolean(openAIAPIKey));
  keyButton.setAttribute('aria-label', openAIAPIKey ? 'OpenAI API 키 변경' : 'OpenAI API 키 입력');
  if (!state.contentReady) return;
  if (state.mockMode) {
    setConnection('', '데이터 연결됨 · 화면 체험 모드');
  } else if (state.serverAIReady || openAIAPIKey) {
    setConnection('ready', '데이터·AI 연결 준비됨');
  } else {
    setConnection('', '데이터 연결됨 · API 키 필요');
  }
}

function openAPIKeyModal() {
  const modal = $('#apiKeyModal');
  const input = $('#apiKeyInput');
  input.value = '';
  $('#apiKeyError').textContent = '';
  $('#apiKeyCancel').hidden = !(openAIAPIKey || state.serverAIReady || state.mockMode);
  document.body.classList.add('modal-open');
  if (!modal.open) modal.showModal();
  requestAnimationFrame(() => input.focus());
}

function closeAPIKeyModal() {
  const modal = $('#apiKeyModal');
  $('#apiKeyInput').value = '';
  $('#apiKeyError').textContent = '';
  document.body.classList.remove('modal-open');
  if (modal.open) modal.close();
}

function scheduleAPIKeyModal() {
  if (openAIAPIKey || state.serverAIReady || state.mockMode) return;
  window.setTimeout(() => {
    if (!openAIAPIKey && !state.serverAIReady && !state.mockMode) openAPIKeyModal();
  }, API_MODAL_DELAY_MS);
}

function submitAPIKey(event) {
  event.preventDefault();
  const input = $('#apiKeyInput');
  const candidate = input.value.trim();
  input.value = '';
  if (!candidate) {
    $('#apiKeyError').textContent = 'API 키를 입력해 주세요.';
    input.focus();
    return;
  }
  openAIAPIKey = candidate;
  closeAPIKeyModal();
  refreshConnectionStatus();
  if (state.staffAuthorization && state.pendingStaffRequest) {
    void retryPendingStaffRequest();
  } else {
    $('#messageInput').focus();
  }
}

function createAvatar() {
  const avatar = document.createElement('img');
  avatar.className = 'avatar'; avatar.src = AVATAR_URL; avatar.alt = '귀 기울이는 모키';
  avatar.onerror = () => {
    const fallback = document.createElement('span');
    fallback.className = 'avatar avatar-fallback'; fallback.role = 'img';
    fallback.ariaLabel = '모키'; fallback.textContent = '모키'; avatar.replaceWith(fallback);
  };
  return avatar;
}

function appendMessage(role, content, save = true) {
  if (save) state.history.push({ role, content });
  const row = document.createElement('div');
  row.className = `message ${role}`;
  if (role === 'assistant') row.appendChild(createAvatar());
  const body = document.createElement('div');
  body.className = 'message-body';
  if (role === 'assistant') {
    const speaker = document.createElement('div');
    speaker.className = 'speaker'; speaker.textContent = '모키'; body.appendChild(speaker);
  }
  const bubble = document.createElement('div');
  bubble.className = 'bubble'; bubble.textContent = content; body.appendChild(bubble);
  row.appendChild(body); $('#messages').appendChild(row);
  $('#messages').scrollTop = $('#messages').scrollHeight;
}

function renderHistory() {
  $('#messages').replaceChildren();
  if (!state.history.length) {
    appendMessage('assistant', '어서 오세요. 취향이나 피해야 할 재료를 편하게 말씀해 주세요. 메뉴 데이터에서 확인해 드릴게요. ☕', false);
    return;
  }
  state.history.forEach((message) => appendMessage(message.role, message.content, false));
}

function renderCategories(categories) {
  const tabs = $('#categoryTabs'); tabs.replaceChildren();
  categories.forEach((category) => {
    const button = document.createElement('button');
    button.type = 'button'; button.role = 'tab'; button.textContent = category;
    button.className = category === state.category ? 'active' : '';
    button.onclick = () => { state.category = category; renderCategories(categories); renderMenu(); };
    tabs.appendChild(button);
  });
}

function renderMenu() {
  const grid = $('#menuGrid'); grid.replaceChildren();
  state.menu.filter((item) => item.category === state.category).forEach((item) => {
    const card = document.createElement('article'); card.className = 'menu-card';
    const image = document.createElement('img'); image.src = item.image; image.alt = `${item.name} 대표 이미지`; image.loading = 'lazy';
    const body = document.createElement('div'); body.className = 'menu-card-body';
    const title = document.createElement('h3'); title.textContent = item.name;
    const english = document.createElement('small'); english.textContent = item.name_en;
    const bottom = document.createElement('div'); bottom.className = 'menu-card-bottom';
    const price = document.createElement('strong'); price.textContent = item.price_label;
    const ask = document.createElement('button'); ask.type = 'button'; ask.textContent = '모키에게 물어보기';
    ask.onclick = () => { document.querySelector('#conversation').scrollIntoView(); sendMessage(`${item.name}에 대해 자세히 알려주세요`); };
    bottom.append(price, ask); body.append(title, english, bottom); card.append(image, body); grid.appendChild(card);
  });
}

function renderCart() {
  const wrap = $('#cartItems'); wrap.replaceChildren();
  if (!state.cart.length) {
    const empty = document.createElement('p'); empty.className = 'empty'; empty.textContent = '아직 담긴 메뉴가 없습니다.'; wrap.appendChild(empty);
  }
  state.cart.forEach((item, index) => {
    const line = document.createElement('div'); line.className = 'cart-line';
    const copy = document.createElement('div');
    const name = document.createElement('b'); name.textContent = `${item.name} ×${item.qty}`;
    const options = document.createElement('small'); options.textContent = [item.temp, item.size, item.option_text].filter(Boolean).join(' · ');
    const price = document.createElement('div'); price.className = 'cart-line-price'; price.textContent = won(item.subtotal);
    copy.append(name, options, price);
    const remove = document.createElement('button'); remove.type = 'button'; remove.ariaLabel = `${item.name} 삭제`; remove.textContent = '×';
    remove.onclick = () => {
      state.cart.splice(index, 1); state.orderNo = null; state.stateToken = null;
      state.cartStatus = null; state.staffChecked = false;
      renderCart(); renderStaffStatus(); saveState();
    };
    line.append(copy, remove); wrap.appendChild(line);
  });
  const total = state.cart.reduce((sum, item) => sum + Number(item.subtotal || 0), 0);
  $('#cartTotal').textContent = won(total);
}

function cartHasAlcohol() {
  if (state.cartStatus === 'pending_staff_check') return true;
  const alcoholMenuIds = new Set(
    state.menu.filter((item) => item.category === '주류').map((item) => item.id),
  );
  return state.cart.some((item) => alcoholMenuIds.has(item.menu_id));
}

function renderStaffStatus(message = '', focus = false) {
  const verification = $('#staffVerification');
  const status = $('#staffStatus');
  const hasAlcohol = cartHasAlcohol();
  const visible = state.staffVerificationRequired || hasAlcohol;
  const needsCode = state.staffVerificationRequired || (hasAlcohol && !state.staffChecked);
  const codeLabel = verification.querySelector('label');
  const codeInput = $('#staffPasswordInput');
  const verifyButton = $('#staffVerifyButton');
  verification.hidden = !visible;
  codeLabel.hidden = !needsCode;
  codeInput.hidden = !needsCode;
  verifyButton.hidden = !needsCode;
  if (!visible) {
    codeInput.value = '';
    status.textContent = '';
    return;
  }
  status.className = `setting-note${state.staffChecked && !state.staffVerificationRequired ? ' ready' : ''}`;
  status.textContent = message || (state.staffVerificationRequired
    ? '직원 확인이 필요한 내용입니다. 직원을 부르겠습니다.'
    : state.staffChecked
      ? '직원 나이 확인이 완료되었습니다. 장바구니가 바뀌면 다시 확인합니다.'
      : '주류가 담겨 있어 직원 확인이 필요합니다.');
  if (focus && needsCode) {
    requestAnimationFrame(() => codeInput.focus());
  }
}

function renderSources() {
  const wrap = $('#sources'); wrap.replaceChildren();
  if (!state.sources.length) {
    const empty = document.createElement('p'); empty.className = 'empty'; empty.textContent = '이번 답변에는 별도의 메뉴 자료가 필요하지 않았습니다.'; wrap.appendChild(empty); return;
  }
  state.sources.forEach((source) => {
    const row = document.createElement('div'); row.className = 'source-chip';
    const label = document.createElement('span'); label.textContent = source.label;
    const name = document.createTextNode(source.name); row.append(label, name); wrap.appendChild(row);
  });
}

function renderQuickReplies(replies = []) {
  const wrap = $('#quickReplies'); wrap.replaceChildren();
  replies.forEach((reply) => {
    const button = document.createElement('button'); button.type = 'button'; button.textContent = reply.label;
    button.onclick = () => sendMessage(reply.value); wrap.appendChild(button);
  });
}

function renderStaffRetryButton() {
  const wrap = $('#quickReplies'); wrap.replaceChildren();
  const button = document.createElement('button');
  button.type = 'button'; button.textContent = '직원 확인된 요청 다시 시도';
  button.onclick = () => retryPendingStaffRequest();
  wrap.appendChild(button);
}

function cartForRequest() {
  return state.cart.map(({ menu_id, variant_id, qty, bean, extra_shots, milk, sweetness, ice, warming }) =>
    ({ menu_id, variant_id, qty, bean, extra_shots, milk, sweetness, ice, warming }));
}

function chatHeaders() {
  const headers = {
    'Content-Type': 'application/json',
    'X-Moki-Password': $('#passwordInput').value,
  };
  if (openAIAPIKey) headers['X-OpenAI-API-Key'] = openAIAPIKey;
  return headers;
}

function applyServerState(data) {
  if (data.cart) {
    state.cart = Array.isArray(data.cart.items) ? data.cart.items : [];
    state.orderNo = data.cart.order_no || null;
    state.cartStatus = data.cart.status || null;
    state.staffChecked = Boolean(data.cart.staff_checked);
  }
  state.stateToken = data.state_token || null;
  state.sources = Array.isArray(data.sources) ? data.sources : [];
  if (Object.hasOwn(data, 'staff_challenge')) {
    state.staffChallenge = data.staff_challenge || null;
  }
}

function errorMessage(detail, fallback = '요청을 처리하지 못했습니다.') {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item && item.msg ? item.msg : String(item)).join(' · ');
  }
  return fallback;
}

async function responsePayload(response) {
  const text = await response.text();
  if (!text) return {};
  try { return JSON.parse(text); }
  catch (_) { return { detail: response.ok ? '' : '서버 응답 형식을 확인해 주세요.' }; }
}

async function sendMessage(rawMessage, options = {}) {
  const message = String(rawMessage || '').trim();
  if (!message || state.busy) return;
  if (!openAIAPIKey && !state.serverAIReady && !state.mockMode) {
    openAPIKeyModal();
    return;
  }
  if (state.staffVerificationRequired) {
    renderStaffStatus('', true);
    return;
  }
  state.busy = true; $('#sendButton').disabled = true; renderQuickReplies();
  // API는 최근 4턴(메시지 8개)만 받아 비용과 응답 시간을 제한한다.
  const previousHistory = Array.isArray(options.historyOverride)
    ? options.historyOverride.slice(-8) : state.history.slice(-8);
  if (options.appendUser !== false) {
    appendMessage('user', message); $('#messageInput').value = ''; saveState();
  }
  const thinking = document.createElement('div'); thinking.className = 'message assistant thinking';
  const thinkingBody = document.createElement('div'); thinkingBody.className = 'message-body';
  const thinkingSpeaker = document.createElement('div'); thinkingSpeaker.className = 'speaker'; thinkingSpeaker.textContent = '모키';
  const thinkingBubble = document.createElement('div'); thinkingBubble.className = 'bubble'; thinkingBubble.textContent = '메뉴 데이터를 확인하고 있어요…';
  thinkingBody.append(thinkingSpeaker, thinkingBubble); thinking.append(createAvatar(), thinkingBody);
  $('#messages').appendChild(thinking); $('#messages').scrollTop = $('#messages').scrollHeight;

  try {
    const response = await fetch('/api/chat', {
      method: 'POST', headers: chatHeaders(),
      body: JSON.stringify({
        message, history: previousHistory, cart: cartForRequest(), state_token: state.stateToken,
        staff_authorization: options.staffAuthorization || null,
        table_id: Number($('#tableSelect').value),
      }),
    });
    const data = await responsePayload(response);
    if (data.requires_staff_verification) {
      thinking.remove();
      const notice = '직원 확인이 필요한 내용입니다. 직원을 부르겠습니다.';
      appendMessage('assistant', notice, false);
      applyServerState(data);
      state.staffVerificationRequired = true;
      state.staffVerificationReason = 'alcohol_inquiry';
      state.staffAuthorization = null;
      state.pendingStaffRequest = { message, history: previousHistory };
      renderCart(); renderSources(); renderQuickReplies();
      renderStaffStatus(notice, true); saveState();
      return;
    }
    if (!response.ok) throw new Error(errorMessage(data.detail, '답변을 불러오지 못했습니다.'));
    thinking.remove(); appendMessage('assistant', data.reply);
    applyServerState(data);
    state.staffVerificationRequired = false;
    state.staffVerificationReason = null;
    state.staffChallenge = null;
    state.staffAuthorization = null;
    state.pendingStaffRequest = null;
    renderCart(); renderStaffStatus(); renderSources(); renderQuickReplies(data.quick_replies); saveState();
  } catch (error) {
    if (thinking.isConnected) thinking.remove();
    appendMessage('assistant', `연결을 확인해 주세요. ${error.message}`, false);
    if (String(error.message).includes('비밀번호')) $('#passwordInput').focus();
    if (String(error.message).includes('API 키')) openAPIKeyModal();
    if (options.staffAuthorization && state.pendingStaffRequest) renderStaffRetryButton();
  } finally {
    state.busy = false; $('#sendButton').disabled = false;
    if (!$('#apiKeyModal').open && !state.staffVerificationRequired) $('#messageInput').focus();
  }
}

async function retryPendingStaffRequest() {
  const pending = state.pendingStaffRequest;
  const authorization = state.staffAuthorization;
  if (!pending || !authorization || state.busy) return;
  await sendMessage(pending.message, {
    appendUser: false,
    historyOverride: pending.history,
    staffAuthorization: authorization,
  });
}

async function verifyStaff() {
  if (state.busy) return;
  const button = $('#staffVerifyButton'); const status = $('#staffStatus');
  let retryRequest = null;
  let refreshRequest = null;
  state.busy = true; button.disabled = true;
  status.className = 'setting-note'; status.textContent = '직원 확인을 처리하고 있습니다…';
  try {
    const response = await fetch('/api/staff/verify', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Moki-Password': $('#passwordInput').value,
        'X-Moki-Staff-Password': $('#staffPasswordInput').value,
      },
      body: JSON.stringify({
        table_id: Number($('#tableSelect').value), cart: cartForRequest(), state_token: state.stateToken,
        staff_challenge: state.staffChallenge,
      }),
    });
    const data = await responsePayload(response);
    if (!response.ok && response.status === 410 && state.pendingStaffRequest) {
      refreshRequest = state.pendingStaffRequest;
      state.staffVerificationRequired = false;
      state.staffVerificationReason = null;
      state.staffChallenge = null;
      state.staffAuthorization = null;
      state.pendingStaffRequest = null;
      status.textContent = '직원 확인 요청을 새로 준비하고 있습니다…';
      saveState();
    } else {
      if (!response.ok) throw new Error(errorMessage(data.detail, '직원 확인을 완료하지 못했습니다.'));
      applyServerState(data);
      state.staffVerificationRequired = false;
      state.staffVerificationReason = null;
      state.staffChallenge = null;
      state.staffAuthorization = data.staff_authorization || null;
      retryRequest = state.pendingStaffRequest;
      renderCart(); renderStaffStatus(data.message); saveState();
    }
  } catch (error) {
    status.className = 'setting-note error'; status.textContent = error.message;
    $('#staffPasswordInput').focus();
  } finally {
    $('#staffPasswordInput').value = '';
    state.busy = false; button.disabled = false;
  }
  if (refreshRequest) {
    await sendMessage(refreshRequest.message, {
      appendUser: false, historyOverride: refreshRequest.history,
    });
  } else if (retryRequest) {
    await retryPendingStaffRequest();
  }
}

function saveState() {
  localStorage.setItem('moki-web-state', JSON.stringify({
    history: state.history.slice(-20), cart: state.cart, orderNo: state.orderNo,
    stateToken: state.stateToken, cartStatus: state.cartStatus,
    staffChecked: state.staffChecked, tableId: state.tableId,
    staffVerificationRequired: state.staffVerificationRequired,
    staffChallenge: state.staffChallenge,
    pendingStaffRequest: state.staffVerificationRequired ? state.pendingStaffRequest : null,
  }));
}

function restoreState() {
  try {
    const saved = JSON.parse(localStorage.getItem('moki-web-state') || '{}');
    state.history = Array.isArray(saved.history) ? saved.history : [];
    state.cart = Array.isArray(saved.cart) ? saved.cart : [];
    state.orderNo = saved.orderNo || null;
    state.stateToken = saved.stateToken || null;
    state.cartStatus = typeof saved.cartStatus === 'string' ? saved.cartStatus : null;
    state.staffChecked = Boolean(saved.staffChecked && saved.stateToken);
    state.staffVerificationRequired = Boolean(saved.staffVerificationRequired && saved.staffChallenge);
    state.staffChallenge = typeof saved.staffChallenge === 'string' ? saved.staffChallenge : null;
    state.pendingStaffRequest = saved.pendingStaffRequest && typeof saved.pendingStaffRequest.message === 'string'
      ? saved.pendingStaffRequest : null;
    state.tableId = Number.isInteger(saved.tableId) && saved.tableId >= 1 && saved.tableId <= 12 ? saved.tableId : 5;
  } catch (_) { localStorage.removeItem('moki-web-state'); }
}

async function boot() {
  restoreState(); renderHistory(); renderCart(); renderStaffStatus(); renderSources();
  for (let table = 1; table <= 12; table += 1) {
    const option = document.createElement('option'); option.value = table; option.textContent = `${table}번 테이블`; option.selected = table === state.tableId; $('#tableSelect').appendChild(option);
  }
  $('#tableBadge').textContent = `TABLE ${String(state.tableId).padStart(2, '0')}`;
  $('#tableSelect').onchange = () => {
    state.tableId = Number($('#tableSelect').value); state.orderNo = null; state.stateToken = null;
    state.cartStatus = null; state.staffChecked = false; state.staffVerificationRequired = false;
    state.staffVerificationReason = null; state.staffChallenge = null;
    state.staffAuthorization = null; state.pendingStaffRequest = null;
    $('#tableBadge').textContent = `TABLE ${String(state.tableId).padStart(2, '0')}`;
    renderStaffStatus(); saveState();
  };
  try {
    const [healthResponse, menuResponse] = await Promise.all([fetch('/api/health'), fetch('/api/menu')]);
    const health = await healthResponse.json(); const menu = await menuResponse.json();
    if (!health.ok) throw new Error('메뉴 자료 연결을 확인해 주세요.');
    state.contentReady = true; state.serverAIReady = Boolean(health.ai_ready);
    state.mockMode = Boolean(health.mock_mode); refreshConnectionStatus();
    state.menu = menu.items; renderCategories(menu.categories); renderMenu(); renderStaffStatus();
    scheduleAPIKeyModal();
  } catch (error) {
    setConnection('error', '연결 확인 필요');
    const notice = document.createElement('div');
    notice.className = 'loading-card'; notice.textContent = error.message;
    $('#menuGrid').replaceChildren(notice);
    scheduleAPIKeyModal();
  }
}

$('#chatForm').addEventListener('submit', (event) => { event.preventDefault(); sendMessage($('#messageInput').value); });
$('#confirmButton').onclick = () => sendMessage('현재 장바구니를 보여주고 주문을 검토해 주세요');
$('#staffVerifyButton').onclick = verifyStaff;
$('#staffPasswordInput').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') { event.preventDefault(); verifyStaff(); }
});
$('#apiKeyButton').onclick = openAPIKeyModal;
$('#apiKeyForm').addEventListener('submit', submitAPIKey);
$('#apiKeyCancel').onclick = closeAPIKeyModal;
$('#apiKeyModal').addEventListener('cancel', (event) => {
  event.preventDefault();
  if (openAIAPIKey || state.serverAIReady || state.mockMode) closeAPIKeyModal();
});
$('#resetButton').onclick = () => {
  state.history = []; state.cart = []; state.orderNo = null; state.stateToken = null;
  state.cartStatus = null; state.staffChecked = false; state.staffVerificationRequired = false;
  state.staffVerificationReason = null; state.staffChallenge = null;
  state.staffAuthorization = null; state.pendingStaffRequest = null;
  state.sources = []; localStorage.removeItem('moki-web-state');
  renderHistory(); renderCart(); renderStaffStatus(); renderSources(); renderQuickReplies();
};
$('#speakButton').onclick = () => {
  const last = [...state.history].reverse().find((message) => message.role === 'assistant');
  if (!last) return;
  speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(last.content); utterance.lang = 'ko-KR'; speechSynthesis.speak(utterance);
};
window.addEventListener('pagehide', () => {
  openAIAPIKey = '';
  state.staffAuthorization = null;
  $('#apiKeyInput').value = '';
  $('#staffPasswordInput').value = '';
});
window.addEventListener('pageshow', () => {
  refreshConnectionStatus();
  if (state.contentReady && !openAIAPIKey && !state.serverAIReady && !state.mockMode) {
    scheduleAPIKeyModal();
  }
});

boot();
