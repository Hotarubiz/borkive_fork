// 페어링 관리 화면. 코드 원문은 발급 응답에서 받아 이 화면의 한 입력칸에만 두고, '코드 지우기'나 새로고침으로 사라져요.
// 저장소(localStorage 등)·주소창·로그에는 쓰지 않아요. CSRF 토큰도 메모리에만 둬요.
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  // 봇카이브 화면 안의 창으로 열렸을 때(?embed=1)는 위쪽 제목을 숨겨요(창 제목과 겹쳐서).
  if (new URLSearchParams(location.search).has('embed')) document.documentElement.classList.add('pa-embed');
  let csrf = '', library = '', timer = null, pendingRevoke = null;

  const status = (text, bad) => { $('pa-status').textContent = text; $('pa-status').dataset.bad = bad ? '1' : ''; };
  const show = name => { for (const id of ['pa-nopass', 'pa-unlock', 'pa-admin']) $(id).hidden = id !== name; };

  async function call(path, body) {
    const init = body === undefined ? {method: 'GET', credentials: 'same-origin'}
      : {method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-BS': '1', 'X-Pairing-CSRF': csrf}, body: JSON.stringify(body)};
    const response = await fetch('/api/pairing/' + path, init);
    let data = {};
    try { data = await response.json(); } catch { /* 빈 응답 */ }
    if (response.status === 401 && path !== 'unlock') { lockedOut(); throw new Error(data.error || '관리 세션이 끝났어요.'); }
    if (!response.ok) throw new Error(data.error || '요청을 처리하지 못했어요.');
    return data;
  }

  function clearCode() {
    $('pa-code').value = '';
    $('pa-code').type = 'password';
    $('pa-show').textContent = '보이기';
    $('pa-show').setAttribute('aria-pressed', 'false');
    $('pa-copied').textContent = '';
    $('pa-issued-target').textContent = '';
    $('pa-issued').hidden = true;
  }

  function lockedOut() {
    csrf = '';
    clearCode();
    clearInterval(timer);
    $('pa-rows').replaceChildren();
    show('pa-unlock');
    status('관리 세션이 끝났어요. 비밀번호를 다시 확인해 주세요.', true);
  }

  function countdown(seconds) {
    clearInterval(timer);
    const end = Date.now() + seconds * 1000;
    const tick = () => {
      const left = Math.max(0, Math.round((end - Date.now()) / 1000));
      $('pa-left').textContent = `관리 세션 ${Math.floor(left / 60)}분 ${left % 60}초 남음`;
      if (!left) lockedOut();
    };
    tick();
    timer = setInterval(tick, 1000);
  }

  const when = seconds => new Date(seconds * 1000).toLocaleString('ko-KR');
  const rightsText = rights => rights.map(r => ({read: '읽기', prepare: '등록 준비', commit: '등록'}[r] || r)).join(' · ');

  function render(keys) {
    const rows = keys.map(key => {
      const tr = document.createElement('tr');
      tr.dataset.state = key.state;
      for (const text of [key.label || '(이름 없음)', key.library, key.source, rightsText(key.rights), when(key.created),
        key.state === 'active' ? '활성' : '폐기됨' + (key.revokedAt ? ' · ' + when(key.revokedAt) : ''), key.kid]) {
        const td = document.createElement('td');
        td.textContent = text;
        tr.append(td);
      }
      const td = document.createElement('td');
      if (key.state === 'active') {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'pa-btn pa-btn--danger';
        button.textContent = '폐기';
        button.addEventListener('click', () => askRevoke(key));
        td.append(button);
      }
      tr.append(td);
      return tr;
    });
    $('pa-rows').replaceChildren(...rows);
    $('pa-empty').hidden = keys.length > 0;
  }

  async function refresh() { render((await call('keys', {})).keys); }

  function askRevoke(key) {
    pendingRevoke = key;
    $('pa-confirm-text').textContent = `${key.label || '(이름 없음)'} · 출처 ${key.source} · 권한 ${rightsText(key.rights)} · 키 ${key.kid}`;
    $('pa-confirm-kid').value = '';
    $('pa-confirm-ok').disabled = true;
    $('pa-confirm').showModal();
    $('pa-confirm-kid').focus();
  }
  $('pa-confirm-kid').addEventListener('input', () => {
    $('pa-confirm-ok').disabled = !pendingRevoke || $('pa-confirm-kid').value !== pendingRevoke.kid;
  });
  $('pa-confirm').addEventListener('close', async () => {
    const key = pendingRevoke;
    pendingRevoke = null;
    if ($('pa-confirm').returnValue !== 'ok' || !key) return;
    try {
      await call('revoke', {kid: key.kid, confirm: $('pa-confirm-kid').value});
      status(`'${key.label}' 연결을 폐기했어요. 이 코드로는 더 이상 접속할 수 없어요.`);
      await refresh();
    } catch (error) { status('폐기하지 못했어요: ' + error.message, true); }
  });

  $('pa-unlock-form').addEventListener('submit', async event => {
    event.preventDefault();
    const password = $('pa-password');
    try {
      const data = await call('unlock', {password: password.value});
      csrf = data.csrf;
      password.value = '';
      show('pa-admin');
      countdown(data.expiresIn);
      status('확인했어요. 이제 연결을 관리할 수 있어요.');
      await refresh();
      $('pa-label').focus();
    } catch (error) { password.value = ''; status(error.message, true); }
  });

  $('pa-lock').addEventListener('click', async () => {
    try { await call('lock', {}); } catch { /* 이미 끝난 세션 */ }
    lockedOut();
    status('관리를 끝냈어요.');
  });

  const rights = () => [...document.querySelectorAll('input[name=right]:checked')].map(e => e.value);
  for (const box of document.querySelectorAll('input[name=right]'))
    box.addEventListener('change', () => { $('pa-risk').hidden = !rights().some(r => r !== 'read'); });

  $('pa-issue').addEventListener('submit', async event => {
    event.preventDefault();
    if (!rights().length) { status('권한을 하나 이상 골라 주세요.', true); return; }
    try {
      const data = await call('issue', {label: $('pa-label').value, source: $('pa-source').value, rights: rights(), library});
      $('pa-code').value = data.code;
      $('pa-issued-target').textContent = `연결 이름 ${data.key.label} · 서재 ${data.key.library} · 출처 ${data.key.source} · 권한 ${rightsText(data.key.rights)}`;
      $('pa-issued').hidden = false;
      $('pa-issue').reset();
      $('pa-library').value = library;
      $('pa-risk').hidden = true;
      status('코드를 만들었어요. 지금 한 번만 볼 수 있어요.');
      $('pa-copy').focus();
      await refresh();
    } catch (error) { status('만들지 못했어요: ' + error.message, true); }
  });

  $('pa-show').addEventListener('click', () => {
    const hidden = $('pa-code').type === 'password';
    $('pa-code').type = hidden ? 'text' : 'password';
    $('pa-show').textContent = hidden ? '숨기기' : '보이기';
    $('pa-show').setAttribute('aria-pressed', hidden ? 'true' : 'false');
  });
  $('pa-copy').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText($('pa-code').value);
      $('pa-copied').textContent = '복사했어요. 붙여 넣은 뒤 클립보드를 다른 글로 덮어 주세요.';
    } catch { $('pa-copied').textContent = '복사하지 못했어요. 보이기를 누른 뒤 직접 선택해 복사해 주세요.'; }
  });
  $('pa-done').addEventListener('click', () => { clearCode(); status('코드를 화면에서 지웠어요.'); });
  addEventListener('pagehide', clearCode);

  (async () => {
    try {
      const data = await call('status');
      library = data.library;
      $('pa-library').value = library;
      if (!data.hasPassword) return show('pa-nopass');
      show('pa-unlock');
      $('pa-password').focus();
    } catch (error) { status('상태를 확인하지 못했어요: ' + error.message, true); }
  })();
})();
