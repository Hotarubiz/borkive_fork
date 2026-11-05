// PocketRisu 연결(페어링) 관리를 주소(/pairing)를 치지 않고 '봇 들이기' 옆 단추로 열어요. 화면 안의 창(팝업)으로 떠요.
// 연동이 꺼져 있으면(/api/pairing/status가 404) 단추를 만들지 않아요. 관리 화면 자체는 기존 /pairing 그대로라
// 비밀번호 다시 확인·CSRF·엄격한 CSP 같은 보호도 그대로예요(같은 출처에서만 창 안에 띄울 수 있어요).
// 단추 자리: 홈은 홈 위쪽 막대(봇 들이기 옆), 다른 화면의 넓은 폭은 왼쪽 목차 아래(봇 들이기 위),
// 다른 화면의 좁은 폭은 위쪽 막대(봇 들이기 옆). 홈에서는 왼쪽 목차와 위쪽 막대가 숨겨져요.
(function installLinkButton() {
  'use strict';
  const style = document.createElement('style');
  style.textContent = `
    .bk-pair-dlg .bd{padding:0;overflow:hidden}
    .bk-pair-frame{display:block;width:100%;height:min(74vh,760px);border:0;background:transparent;border-radius:0 0 24px 24px}
    .topbar #bkPairTop{margin-left:6px}
    #bkPairSide{margin:8px 4px 0}
    .mtop #bkPairHome{margin-left:6px}
    @media (max-width:640px){#bkPairTop .t{display:none}#bkPairTop,#bkPairHome{padding-inline:10px}.bk-pair-frame{height:82vh;border-radius:0}}
    @media (max-width:480px){.mtop:has(#bkPairHome) .lw{display:none}}`;  // 단추 자리가 모자라 로고 글자가 여러 줄로 깨져요
  document.head.append(style);

  function openPairing() {
    return modal(`<header><h2>PocketRisu 연결</h2><span>페어링 코드 만들기 · 폐기</span>${xBtn}</header>
      <div class="bd"><iframe class="bk-pair-frame" src="/pairing?embed=1" title="PocketRisu 연결 관리"></iframe></div>`, 'bk-pair-dlg');
  }
  function button(id, cls, size) {
    const b = document.createElement('button');
    b.type = 'button';
    b.id = id;
    b.className = cls;
    b.title = 'PocketRisu 연결 관리(페어링 코드)';
    b.innerHTML = `${ic('link', size)}<span class="t">PocketRisu 연결</span>`;
    b.onclick = () => { document.body.classList.remove('drawer'); openPairing(); };
    return b;
  }
  let enabled = false, asking = false;
  function place() {
    if (!enabled) return;
    const top = document.querySelector('.topbar [data-act="add"]');
    if (top && !document.getElementById('bkPairTop')) top.after(button('bkPairTop', 'btn sm', 16));
    const side = document.querySelector('#side [data-act="add"]');
    if (side && !document.getElementById('bkPairSide')) side.before(button('bkPairSide', 'btn', 18));
    const home = document.querySelector('.mtop [data-act="add"]');
    if (home && !document.getElementById('bkPairHome')) home.before(button('bkPairHome', 'btn sm', 16));
  }
  async function check() {
    if (enabled) return place();
    if (asking) return;
    asking = true;
    try {
      const r = await fetch('/api/pairing/status', {cache: 'no-store', credentials: 'same-origin'});
      await r.text();  // 본문을 다 읽어야 요청이 끝나요(안 읽으면 브라우저가 연결을 붙잡고 있어요)
      enabled = r.ok;  // 404 = 연동 꺼짐, 401 = 잠금 로그인 전(화면이 바뀌면 다시 봐요)
      place();
    } catch (e) { /* 연결이 안 되면 단추 없이 둬요 */ } finally { asking = false; }
  }
  // 왼쪽 목차는 상태가 바뀔 때마다 다시 그려져요. 그때마다 단추를 다시 붙여요(bulk.js와 같은 방식).
  if (typeof renderSide === 'function') {
    const oldRenderSide = renderSide;
    renderSide = function () { const out = oldRenderSide.apply(this, arguments); place(); return out; };
  }
  // 홈 화면은 자료를 받은 뒤에 그려지고 화면을 옮길 때마다 새로 그려져요. 그때마다 단추를 다시 붙여요.
  const view = document.getElementById('view');
  if (view) new MutationObserver(place).observe(view, {childList: true});
  check();
  window.addEventListener('hashchange', check);
  window.BotkivePairing = {open: openPairing};
})();
