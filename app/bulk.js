(function installBulkBotFeatures() {
  'use strict';
  const MAX_BATCH = 120;
  const CARD_RE = /\.(charx|risuchar|png|jpe?g|json|zip)$/i;
  const style = document.createElement('style');
  style.textContent = `
    .bk-batch-actions{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin:10px 0}
    .bk-batch-list{display:flex;flex-direction:column;gap:9px;max-height:38vh;overflow:auto;padding-right:3px}
    .bk-batch-item{display:grid;grid-template-columns:24px minmax(115px,2fr) minmax(100px,1fr);gap:9px;align-items:center;padding:10px;border:1px solid var(--line);border-radius:12px;background:var(--card)}
    .bk-batch-item .inp{width:100%;min-width:0}
    .bk-batch-item .meta{grid-column:2/-1;overflow-wrap:anywhere}
    .bk-batch-item .bk-state{grid-column:1/-1;font-size:12px;color:var(--mute)}
    .bk-batch-item.bk-done{opacity:.63}
    .bk-batch-item.bk-error{border-color:var(--red)}
    .bk-batch-foot{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap}
    .bk-batch-settings{display:flex;flex-direction:column;gap:16px}
    .bk-batch-settings .legend{margin-bottom:8px}
    .bk-selectbar{display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:12px 14px;border:1px solid var(--acc-line);background:var(--acc-soft);border-radius:14px;margin-bottom:18px}
    .bk-selectbar[hidden]{display:none}
    .bk-selectbar .bk-selectcount{font-weight:700;margin-right:auto}
    .bc .bk-check{display:none;position:absolute;top:9px;left:9px;z-index:2;width:24px;height:24px;border:2px solid #fff;border-radius:7px;background:rgba(0,0,0,.7);color:white;align-items:center;justify-content:center;font-weight:800}
    .grid.bk-selecting .bc .bk-check{display:flex}
    .grid.bk-selecting .bc.bk-picked .bk-check{background:var(--acc);color:var(--acc-ink);border-color:var(--acc)}
    .grid.bk-selecting .bc.bk-picked .cv{outline:3px solid var(--acc);outline-offset:2px}
    .bk-bulk-options{display:flex;flex-direction:column;gap:14px}
    .bk-bulk-options label{cursor:pointer}
    @media(max-width:620px){.bk-batch-item{grid-template-columns:24px minmax(0,1fr)}.bk-batch-item .meta{grid-column:2}.bk-batch-item .bk-author{grid-column:2}.bk-batch-item .bk-state{grid-column:1/-1}}
  `;
  document.head.append(style);

  const asEntries = files => files.filter(x => x && x.file && CARD_RE.test(x.file.name)).map(x => ({file:x.file,path:x.path || x.file.webkitRelativePath || x.file.name}));
  function chooseDirectory() {
    return new Promise(resolve => {
      const p = document.createElement('input');
      p.type = 'file';
      p.multiple = true;
      p.setAttribute('webkitdirectory', '');
      p.style.display = 'none';
      document.body.append(p);
      p.onchange = () => { const files = Array.from(p.files || []); p.remove(); resolve(files.map(file => ({file,path:file.webkitRelativePath || file.name}))); };
      p.click();
    });
  }
  async function fromDroppedEntries(entries) {
    const out = [];
    async function walk(entry) {
      if (entry.isFile) {
        const file = await new Promise((ok, no) => entry.file(ok, no));
        out.push({file, path:(entry.fullPath || file.name).replace(/^\//, '')});
      } else if (entry.isDirectory) {
        const reader = entry.createReader();
        while (true) {
          const chunk = await new Promise((ok, no) => reader.readEntries(ok, no));
          if (!chunk.length) break;
          for (const child of chunk) await walk(child);
        }
      }
    }
    for (const entry of entries) await walk(entry);
    return out;
  }
  async function openBatch(raw) {
    const files = asEntries(raw);
    if (!files.length) return toast('카드 파일(.charx · .png · .jpg · .json · .zip)이 없어요', true);
    if (files.length > MAX_BATCH) return toast(`한 번에 최대 ${MAX_BATCH}개까지 들일 수 있어요. 폴더를 나눠서 골라 주세요`, true);

    const m = modal(`<header><h2>봇 한꺼번에 들이기</h2><span>${files.length}개 카드 · 이름과 만든 사람을 파일에서 읽어요</span>${xBtn}</header>
      <div class="bd" style="display:flex;flex-direction:column;gap:18px">
        <p class="hint" id="bkRead">카드 정보 읽는 중…</p>
        <div class="bk-batch-list" id="bkRows"></div>
        <div class="bk-batch-settings" id="bkOptions" hidden>
          <div><p class="legend">모두 넣을 폴더 <span>여러 폴더를 고를 수 있어요</span></p><div class="ftiles" id="bkFolders"></div></div>
          <label class="field">일괄 제작자 (선택 사항)<input class="inp" id="bkWho" placeholder="비워두면 각 카드의 제작자를 유지해요"></label>
          <div class="field">지금 상태<div class="seg" id="bkStatus">${Object.entries(STATUS).map(([key,name]) => `<button class="pill" type="button" data-s="${h(key)}" aria-pressed="${key === 'later'}">${h(name)}</button>`).join('')}</div></div>
        </div>
        <div class="prog" id="bkProgress" hidden><i></i></div>
        <p class="hint" id="bkSummary" aria-live="polite"></p>
      </div>
      <footer class="bk-batch-foot"><button class="btn" data-close>닫기</button><button class="btn pri" id="bkStart" disabled>선택한 카드 들이기</button></footer>`);
    const chosenFolders = new Set();
    const rows = [];
    let status = 'later', busy = false;
    const list = $('#bkRows', m);
    const note = $('#bkSummary', m);
    const btn = $('#bkStart', m);
    for (let i = 0; i < files.length; i++) {
      if (!m.isConnected) return;
      const entry = files[i], file = entry.file;
      $('#bkRead', m).textContent = `카드 읽는 중… ${i + 1} / ${files.length}`;
      let info, err = '';
      try { info = await readCard(file); }
      catch (e) { info = {name:file.name.replace(/\.[^.]+$/, ''), creator:'', info:{}, cover:null}; err = e.message || String(e); }
      rows.push({file,info,err,done:false,blocked:false});
      list.insertAdjacentHTML('beforeend', `<div class="bk-batch-item ${err ? 'bk-error' : ''}" data-i="${i}">
        <input type="checkbox" data-use aria-label="${h(file.name)} 등록" ${err ? '' : 'checked'}>
        <input class="inp" data-name maxlength="200" value="${h(info.name)}" aria-label="봇 이름">
        <input class="inp bk-author" data-creator maxlength="200" value="${h(info.creator)}" placeholder="만든 사람" aria-label="제작자">
        <span class="meta" title="${h(entry.path)}">${h(entry.path)} · ${size(file.size)}</span>
        <span class="bk-state">${err ? `읽기 오류: ${h(err)} (확인 후 직접 선택해야 등록)` : '준비됨'}</span></div>`);
    }
    $('#bkRead', m).textContent = `${files.length}개를 읽었어요. 이름·제작자를 고치거나, 제외할 파일의 체크를 풀 수 있어요.`;
    $('#bkOptions', m).hidden = false;
    btn.disabled = false;
    folderTiles($('#bkFolders', m), chosenFolders);
    $$('#bkStatus .pill', m).forEach(x => x.onclick = () => {
      status = x.dataset.s;
      $$('#bkStatus .pill', m).forEach(y => y.setAttribute('aria-pressed', x === y));
    });
    btn.onclick = async () => {
      if (busy) return;
      const targets = rows.map((r,i)=>({r,i,el:$(`[data-i="${i}"]`,list)})).filter(x => !x.r.done && !x.r.blocked && $('[data-use]',x.el).checked);
      if (!targets.length) return toast('등록할 카드를 선택하시와요'.replace('하시와요','해주세요'), true);
      busy = true; btn.disabled = true;
      $$('[data-close]',m).forEach(b=>b.disabled = true);
      const sharedCreator = $('#bkWho',m).value.trim();
      let ok = 0, bad = 0;
      const bar = $('#bkProgress',m);
      bar.hidden = false;
      for (let n = 0; n < targets.length; n++) {
        const {r,i,el} = targets[n];
        const label = $('.bk-state',el);
        label.textContent = `올리는 중… ${n + 1} / ${targets.length}`;
        let made = null;
        try {
          const name = $('[data-name]',el).value.trim() || r.info.name || r.file.name.replace(/\.[^.]+$/, '');
          const creator = sharedCreator || $('[data-creator]',el).value.trim();
          made = await api('POST','/api/bots',{
            name, creator, status, folders:[...chosenFolders], info:r.info.info || {}, cover:r.info.cover || undefined
          });
          await upload(r.file, {bot:made.id,kind:'card',name:r.file.name}, p => {
            $('i',bar).style.width = (((n + p) / targets.length) * 100) + '%';
          });
          r.done = true;
          el.classList.add('bk-done');
          $('[data-use]',el).checked = false;
          $('[data-use]',el).disabled = true;
          label.textContent = '등록 완료';
          ok++;
        } catch(e) {
          bad++;
          let cleanup = '';
          if (made) {
            try { await api('DELETE',`/api/bots/${made.id}`); }
            catch(_) { r.blocked = true; cleanup = ' · 빈 봇 정리 실패, 중복 방지를 위해 재시도 제한'; }
          }
          el.classList.add('bk-error');
          label.textContent = `실패: ${e.message || String(e)}${cleanup}`;
        }
        note.textContent = `${n + 1} / ${targets.length} 처리 · 성공 ${ok} · 실패 ${bad}`;
      }
      busy = false;
      $$('[data-close]',m).forEach(b=>b.disabled = false);
      await loadState();
      if (!bad) {
        m.close();
        location.hash = '#/all';
        if (location.hash === '#/all') route();
        toast(`${ok}개 봇을 서재에 넣었어요`);
      } else {
        btn.disabled = false;
        btn.textContent = '실패한 카드 다시 시도';
        note.textContent = `${ok}개 등록, ${bad}개 실패했어요. 실패한 항목을 확인한 뒤 다시 시도할 수 있어요.`;
      }
    };
  }

  const oldAddBot = addBot;
  addBot = function() {
    const result = oldAddBot();
    const drop = $('#addDrop');
    if (!drop) return result;
    drop.insertAdjacentHTML('afterend', `<div class="bk-batch-actions">
      <button class="btn sm" type="button" id="bkMany">${ic('plus',16)}여러 파일 선택</button>
      <button class="btn sm ghost" type="button" id="bkDir">${ic('folder',16)}폴더째 선택</button>
      </div><p class="hint" style="text-align:center;margin:0">여러 파일이나 폴더를 위 칸에 끌어다 놓아도 돼요</p>`);
    $('#bkMany').onclick = async () => {
      const files = await pick('.charx,.risuchar,.png,.jpg,.jpeg,.json,.zip',true);
      if (!files.length) return;
      drop.closest('.dim').close();
      await openBatch(files.map(file=>({file,path:file.name})));
    };
    $('#bkDir').onclick = async () => {
      const files = await chooseDirectory();
      if (!files.length) return;
      drop.closest('.dim').close();
      await openBatch(files);
    };
    drop.addEventListener('drop', async e => {
      const items = Array.from(e.dataTransfer.items || []);
      const entries = items.filter(x=>x.kind === 'file').map(x => x.webkitGetAsEntry ? x.webkitGetAsEntry() : null).filter(Boolean);
      const isFolder = entries.some(x => x.isDirectory);
      const many = e.dataTransfer.files.length > 1;
      if (!isFolder && !many) return; // 기존 단일 파일 등록 창 사용
      e.preventDefault();
      e.stopImmediatePropagation(); // 기존 단일 파일 dropZone 실행 방지
      const fallback = Array.from(e.dataTransfer.files || []).map(file=>({file,path:file.name}));
      drop.closest('.dim').close();
      try {
        const files = entries.length ? await fromDroppedEntries(entries) : fallback;
        await openBatch(files);
      } catch (err) { toast(`폴더를 읽지 못했어요: ${err.message}`,true); }
    }, true);
    return result;
  };

  const oldViewHome = viewHome;
  viewHome = async function(folderId) {
    await oldViewHome(folderId);
    const view = $('#view'), grid = $('#grid',view);
    if (!grid || !$$('.bc',grid).length) return;
    const toolbar = $('.toolbar',view);
    if (!toolbar) return;
    const button = document.createElement('button');
    button.className = 'btn sm ghost';
    button.textContent = '여러 개 선택';
    toolbar.append(button);
    const selectBar = document.createElement('div');
    selectBar.className = 'bk-selectbar';
    selectBar.hidden = true;
    selectBar.innerHTML = `<span class="bk-selectcount">0개 선택</span>
      <button class="btn sm ghost" id="bkSelectVisible">보이는 봇 모두 선택</button>
      <button class="btn sm pri" id="bkBulkEdit" disabled>폴더·제작자 일괄 수정</button>
      <button class="btn sm ghost" id="bkClear">선택 해제</button>
      <button class="btn sm ghost" id="bkLeave">끝내기</button>`;
    grid.before(selectBar);
    const picked = new Set();
    let selecting = false;
    const cards = $$('.bc',grid);
    const update = () => {
      $('.bk-selectcount',selectBar).textContent = `${picked.size}개 선택`;
      $('#bkBulkEdit',selectBar).disabled = !picked.size;
      for (const a of cards) {
        const on = picked.has(+a.getAttribute('href').split('/').pop());
        a.classList.toggle('bk-picked',on);
        a.setAttribute('aria-pressed',String(on));
        const ch = $('.bk-check',a);
        if(ch) ch.textContent = on ? '✓' : '';
      }
    };
    const enter = on => {
      selecting = on;
      grid.classList.toggle('bk-selecting',on);
      button.hidden = on; selectBar.hidden = !on;
      if(!on) picked.clear();
      for (const a of cards) {
        if (on) { a.setAttribute('role','button'); a.setAttribute('aria-label',`선택: ${$('b',a).textContent}`); }
        else { a.removeAttribute('role'); a.removeAttribute('aria-label'); a.removeAttribute('aria-pressed'); }
      }
      update();
    };
    for (const a of cards) {
      const cv = $('.cv',a);
      if (cv) cv.insertAdjacentHTML('beforeend','<span class="bk-check" aria-hidden="true"></span>');
      a.addEventListener('click',e=>{
        if(!selecting) return;
        e.preventDefault();
        const id = +a.getAttribute('href').split('/').pop();
        picked.has(id) ? picked.delete(id) : picked.add(id);
        update();
      });
      a.addEventListener('keydown', e=>{
        if (selecting && e.key === ' ') {e.preventDefault();a.click();}
      });
    }
    button.onclick = () => enter(true);
    $('#bkLeave',selectBar).onclick = () => enter(false);
    $('#bkClear',selectBar).onclick = () => {picked.clear();update();};
    $('#bkSelectVisible',selectBar).onclick = () => {
      for (const a of cards) if (!a.hidden) picked.add(+a.getAttribute('href').split('/').pop());
      update();
    };
    $('#bkBulkEdit',selectBar).onclick = async () => {
      const ids = [...picked];
      if (!ids.length) return;
      const chosen = new Set();
      const m = modal(`<header><h2>여러 봇 한꺼번에 고치기</h2><span>${ids.length}개 선택됨</span>${xBtn}</header>
        <div class="bd bk-bulk-options">
          <label><input type="checkbox" id="bkChangeFolders"> 폴더를 한꺼번에 변경</label>
          <div id="bkFolderArea" hidden>
            <div class="ftiles" id="bkFolderChoices"></div>
            <div class="row" style="margin-top:12px">
              <label><input type="radio" name="bkFolderMode" value="move" checked> 선택한 폴더로 옮기기 (기존 폴더 교체)</label>
              <label><input type="radio" name="bkFolderMode" value="add"> 기존 폴더에도 남기기</label>
            </div>
          </div>
          <label><input type="checkbox" id="bkChangeCreator"> 제작자를 한꺼번에 변경</label>
          <input class="inp" id="bkNewCreator" maxlength="200" placeholder="새 제작자 이름 (빈칸이면 지우기)" disabled>
          <p class="hint" id="bkEditResult" aria-live="polite">선택한 항목만 바뀌고, 다른 정보는 그대로 남아요.</p>
        </div>
        <footer><button class="btn" data-close>취소</button><button class="btn pri" id="bkApply">일괄 적용</button></footer>`);
      folderTiles($('#bkFolderChoices',m),chosen);
      $('#bkChangeFolders',m).onchange = e => $('#bkFolderArea',m).hidden = !e.target.checked;
      $('#bkChangeCreator',m).onchange = e => $('#bkNewCreator',m).disabled = !e.target.checked;
      $('#bkApply',m).onclick = async () => {
        const changeFolders = $('#bkChangeFolders',m).checked, changeCreator = $('#bkChangeCreator',m).checked;
        if(!changeFolders && !changeCreator) return toast('변경할 항목을 선택해 주세요',true);
        if(changeFolders && !chosen.size) return toast('이동할 폴더를 하나 이상 선택해 주세요',true);
        const newCreator = $('#bkNewCreator',m).value.trim();
        const append = $('input[name="bkFolderMode"]:checked',m).value === 'add';
        const apply = $('#bkApply',m);
        apply.disabled = true;
        $$('[data-close]',m).forEach(b => b.disabled=true);
        let done = 0;
        const failures = [];
        const bots = await api('GET', '/api/bots');
        const byId = new Map(bots.map(b => [b.id,b]));
        for (const id of ids) {
          const old = byId.get(id);
          if(!old) continue;
          const patch = {};
          if(changeCreator) patch.creator = newCreator;
          if(changeFolders) patch.folders = append ? [...new Set([...(old.folders || []),...chosen])] : [...chosen];
          try { await api('PUT',`/api/bots/${id}`,patch); done++; }
          catch(e) {failures.push(`${old.name}: ${e.message}`);}
          $('#bkEditResult',m).textContent = `${done + failures.length} / ${ids.length} 처리 중…`;
        }
        m.close();
        await loadState();
        await route();
        if(failures.length) toast(`${done}개 수정, ${failures.length}개 실패: ${failures.slice(0,2).join('; ')}`,true);
        else toast(`${done}개 봇의 정보를 한꺼번에 수정했어요`);
      };
    };
  };
})();
