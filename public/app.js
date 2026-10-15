const $ = (selector) => document.querySelector(selector);
const AVATAR_URL = '/assets/moki-listening-avatar.png?v=20261015';
const state = {
  history: [], cart: [], orderNo: null, stateToken: null,
  staffChecked: false, tableId: 5,
  sources: [], menu: [], category: '커피', busy: false,
};

const won = (value) => `${Number(value || 0).toLocaleString('ko-KR')}원`;

function setConnection(kind, text) {
  const element = $('#connectionStatus');
  element.className = `connection ${kind || ''}`;
  element.querySelector('span').textContent = text;
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
      state.cart.splice(index, 1); state.orderNo = null; state.stateToken = null; state.staffChecked = false;
      renderCart(); renderStaffStatus(); saveState();
    };
    line.append(copy, remove); wrap.appendChild(line);
  });
  const total = state.cart.reduce((sum, item) => sum + Number(item.subtotal || 0), 0);
  $('#cartTotal').textContent = won(total);
}

function renderStaffStatus(message = '') {
  const status = $('#staffStatus');
  status.className = `setting-note${state.staffChecked ? ' ready' : ''}`;
  status.textContent = message || (state.staffChecked
    ? '직원 나이 확인이 완료되었습니다. 장바구니가 바뀌면 다시 확인합니다.'
    : '주류는 직원 확인 전까지 주문을 확정할 수 없습니다.');
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

function cartForRequest() {
  return state.cart.map(({ menu_id, variant_id, qty, bean, extra_shots, milk, sweetness, ice, warming }) =>
    ({ menu_id, variant_id, qty, bean, extra_shots, milk, sweetness, ice, warming }));
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

async function sendMessage(rawMessage) {
  const message = String(rawMessage || '').trim();
  if (!message || state.busy) return;
  state.busy = true; $('#sendButton').disabled = true; renderQuickReplies();
  // API는 최근 4턴(메시지 8개)만 받아 비용과 응답 시간을 제한한다.
  const previousHistory = state.history.slice(-8);
  appendMessage('user', message); $('#messageInput').value = ''; saveState();
  const thinking = document.createElement('div'); thinking.className = 'message assistant thinking';
  const thinkingBody = document.createElement('div'); thinkingBody.className = 'message-body';
  const thinkingSpeaker = document.createElement('div'); thinkingSpeaker.className = 'speaker'; thinkingSpeaker.textContent = '모키';
  const thinkingBubble = document.createElement('div'); thinkingBubble.className = 'bubble'; thinkingBubble.textContent = '메뉴 데이터를 확인하고 있어요…';
  thinkingBody.append(thinkingSpeaker, thinkingBubble); thinking.append(createAvatar(), thinkingBody);
  $('#messages').appendChild(thinking); $('#messages').scrollTop = $('#messages').scrollHeight;

  try {
    const response = await fetch('/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Moki-Password': $('#passwordInput').value },
      body: JSON.stringify({
        message, history: previousHistory, cart: cartForRequest(), state_token: state.stateToken,
        table_id: Number($('#tableSelect').value),
      }),
    });
    const data = await responsePayload(response);
    if (!response.ok) throw new Error(errorMessage(data.detail, '답변을 불러오지 못했습니다.'));
    thinking.remove(); appendMessage('assistant', data.reply);
    state.cart = data.cart.items; state.orderNo = data.cart.order_no;
    state.staffChecked = Boolean(data.cart.staff_checked);
    state.stateToken = data.state_token || null; state.sources = data.sources || [];
    renderCart(); renderStaffStatus(); renderSources(); renderQuickReplies(data.quick_replies); saveState();
  } catch (error) {
    thinking.remove(); appendMessage('assistant', `연결을 확인해 주세요. ${error.message}`, false);
    if (String(error.message).includes('비밀번호')) $('#passwordInput').focus();
  } finally {
    state.busy = false; $('#sendButton').disabled = false; $('#messageInput').focus();
  }
}

async function verifyStaff() {
  if (state.busy) return;
  const button = $('#staffVerifyButton'); const status = $('#staffStatus');
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
      }),
    });
    const data = await responsePayload(response);
    if (!response.ok) throw new Error(errorMessage(data.detail, '직원 확인을 완료하지 못했습니다.'));
    state.cart = data.cart.items; state.orderNo = data.cart.order_no;
    state.staffChecked = Boolean(data.cart.staff_checked); state.stateToken = data.state_token || null;
    renderCart(); renderStaffStatus(data.message); saveState();
  } catch (error) {
    state.staffChecked = false;
    status.className = 'setting-note error'; status.textContent = error.message;
  } finally {
    $('#staffPasswordInput').value = '';
    state.busy = false; button.disabled = false;
  }
}

function saveState() {
  localStorage.setItem('moki-web-state', JSON.stringify({
    history: state.history.slice(-20), cart: state.cart, orderNo: state.orderNo,
    stateToken: state.stateToken, staffChecked: state.staffChecked, tableId: state.tableId,
  }));
}

function restoreState() {
  try {
    const saved = JSON.parse(localStorage.getItem('moki-web-state') || '{}');
    state.history = Array.isArray(saved.history) ? saved.history : [];
    state.cart = Array.isArray(saved.cart) ? saved.cart : [];
    state.orderNo = saved.orderNo || null;
    state.stateToken = saved.stateToken || null;
    state.staffChecked = Boolean(saved.staffChecked && saved.stateToken);
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
    state.tableId = Number($('#tableSelect').value); state.orderNo = null; state.stateToken = null; state.staffChecked = false;
    $('#tableBadge').textContent = `TABLE ${String(state.tableId).padStart(2, '0')}`;
    renderStaffStatus(); saveState();
  };
  try {
    const [healthResponse, menuResponse] = await Promise.all([fetch('/api/health'), fetch('/api/menu')]);
    const health = await healthResponse.json(); const menu = await menuResponse.json();
    if (!health.ok) throw new Error('메뉴 자료 연결을 확인해 주세요.');
    const connectionText = health.ai_ready ? '데이터·AI 연결됨'
      : health.mock_mode ? '데이터 연결됨 · 화면 체험 모드' : '데이터 연결됨 · AI 설정 필요';
    setConnection(health.ai_ready ? 'ready' : '', connectionText);
    state.menu = menu.items; renderCategories(menu.categories); renderMenu();
  } catch (error) {
    setConnection('error', '연결 확인 필요');
    const notice = document.createElement('div');
    notice.className = 'loading-card'; notice.textContent = error.message;
    $('#menuGrid').replaceChildren(notice);
  }
}

$('#chatForm').addEventListener('submit', (event) => { event.preventDefault(); sendMessage($('#messageInput').value); });
$('#confirmButton').onclick = () => sendMessage('현재 장바구니를 보여주고 주문을 검토해 주세요');
$('#staffVerifyButton').onclick = verifyStaff;
$('#resetButton').onclick = () => {
  state.history = []; state.cart = []; state.orderNo = null; state.stateToken = null;
  state.staffChecked = false; state.sources = []; localStorage.removeItem('moki-web-state');
  renderHistory(); renderCart(); renderStaffStatus(); renderSources(); renderQuickReplies();
};
$('#speakButton').onclick = () => {
  const last = [...state.history].reverse().find((message) => message.role === 'assistant');
  if (!last) return;
  speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(last.content); utterance.lang = 'ko-KR'; speechSynthesis.speak(utterance);
};

boot();
