// Lightweight global fixed audio bar shown on any page when an <audio> starts playing
(function(){
  if (window.__nowbar_initialized__) return; window.__nowbar_initialized__ = true;

  let cachedLeft = 0;

  function injectStyles(){
    if (document.getElementById('nowbar-style')) return;
    const css = `
      .nowbar{position:fixed;left:0;right:0;top:0;background:var(--panel,#ffffff);border-bottom:1px solid var(--table-border,#e5e7eb);z-index:2000;display:none}
      .nowbar-inner{display:flex;align-items:center;gap:12px;padding:10px 16px}
      .nowbar .title{font-weight:600;max-width:360px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text,#1f2937)}
      .nowbar .meta{color:var(--muted,#6b7280);font-size:12px}
      .nowbar .btn{background:var(--accent,#4a76a8);color:#fff;border:none;border-radius:8px;padding:6px 10px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;min-width:36px;min-height:28px}
      .nowbar .range{height:6px}
      .nowbar input[type="range"]{accent-color:var(--accent,#4a76a8);appearance:none;-webkit-appearance:none;height:6px;background:var(--table-border,#e5e7eb);border-radius:999px}
      .nowbar input[type="range"]::-webkit-slider-runnable-track{height:6px;background:var(--table-border,#e5e7eb);border-radius:999px}
      .nowbar input[type="range"]::-webkit-slider-thumb{appearance:none;-webkit-appearance:none;width:12px;height:12px;border-radius:50%;background:var(--accent,#4a76a8);border:none;margin-top:-3px}
      .nowbar input[type="range"]::-moz-range-track{height:6px;background:var(--table-border,#e5e7eb);border-radius:999px}
      .nowbar input[type="range"]::-moz-range-thumb{width:12px;height:12px;border-radius:50%;background:var(--accent,#4a76a8);border:none}
      @media (max-width: 900px){ .nowbar{left:0} }
    `;
    const style = document.createElement('style'); style.id='nowbar-style'; style.textContent = css; document.head.appendChild(style);
  }

  function createBar(){
    if (document.getElementById('nowbar')) return document.getElementById('nowbar');
    injectStyles();
    const el = document.createElement('div'); el.id='nowbar'; el.className='nowbar';
    el.innerHTML = `
      <div class="nowbar-inner">
        <button class="btn" id="nb-play"><i id="nb-icon" class="fas fa-play"></i></button>
        <div class="title" id="nb-title">Аудио</div>
        <div class="meta"><span id="nb-cur">0:00</span>/<span id="nb-dur">0:00</span></div>
        <input class="range" id="nb-seek" type="range" min="0" max="1000" value="0" style="flex:1">
        <input class="range" id="nb-vol" type="range" min="0" max="1" step="0.01" value="1" style="width:110px">
      </div>`;
    document.body.appendChild(el);
    return el;
  }

  function fmt(s){ if(!isFinite(s)) return '0:00'; s=Math.floor(s); const m=Math.floor(s/60), ss=String(s%60).padStart(2,'0'); return `${m}:${ss}`; }

  let currentAudio = null;
  function bindControls(){
    const bar = createBar();
    const playBtn = document.getElementById('nb-play');
    const seek = document.getElementById('nb-seek');
    const vol = document.getElementById('nb-vol');
    playBtn.addEventListener('click', ()=>{ if(!currentAudio) return; if(currentAudio.paused) currentAudio.play(); else currentAudio.pause(); });
    seek.addEventListener('input', ()=>{ if(!currentAudio||!isFinite(currentAudio.duration)) return; currentAudio.currentTime = (parseInt(seek.value,10)/1000)*currentAudio.duration; });
    vol.addEventListener('input', ()=>{ if(currentAudio) currentAudio.volume = parseFloat(vol.value); });
  }

  function updateFromAudio(a){
    const bar = createBar();
    document.getElementById('nb-title').textContent = a.dataset.title || a.getAttribute('data-title') || a.title || document.title || 'Аудио';
    document.getElementById('nb-cur').textContent = fmt(a.currentTime);
    document.getElementById('nb-dur').textContent = fmt(a.duration);
    document.getElementById('nb-seek').value = isFinite(a.duration) ? Math.floor((a.currentTime/a.duration)*1000) : 0;
    document.getElementById('nb-vol').value = a.volume;
    bar.style.display = 'block';
    // Поднимаем контент, чтобы бар не перекрывал
    if (!document.body.dataset.nowbarPad){ document.body.dataset.nowbarPad = '0'; }
    // динамически учитываем высоту бара
    document.body.style.paddingTop = Math.max(0, bar.offsetHeight) + 'px';
    // Иконка
    const icon = document.getElementById('nb-icon');
    if (icon) icon.className = a.paused ? 'fas fa-play' : 'fas fa-pause';
    updateBarPosition();
  }

  function updateBarPosition(){
    const bar = createBar();
    // Вычисляем фактическую ширину и смещение сайдбара, если он есть
    const sb = document.querySelector('.sidebar');
    let left = 0;
    // На мобильных всегда тянем бар на всю ширину
    const isMobile = document.body.classList.contains('device-mobile') || window.innerWidth <= 900;
    if (!isMobile && sb){
      const cs = window.getComputedStyle(sb);
      // Учитываем сайдбар только если он действительно фиксирован у левого края
      if (cs.position === 'fixed'){
        const r = sb.getBoundingClientRect();
        left = Math.max(0, Math.round(r.left + r.width));
      }
    }
    if (left !== cachedLeft){
      bar.style.left = left + 'px';
      cachedLeft = left;
    }
    // на всякий случай снимаем паддинг, если бар скрыт
    if (bar.style.display === 'none'){ document.body.style.paddingTop = ''; }
  }

  function attachAudio(a){
    if (a.__nowbar_bound) return; a.__nowbar_bound = true;
    a.addEventListener('play', ()=>{ currentAudio = a; updateFromAudio(a); });
    a.addEventListener('timeupdate', ()=>{ if (currentAudio===a) updateFromAudio(a); });
    a.addEventListener('pause', ()=>{ if (currentAudio===a){ const i=document.getElementById('nb-icon'); if(i) i.className='fas fa-play'; } });
    a.addEventListener('playing', ()=>{ if (currentAudio===a){ const i=document.getElementById('nb-icon'); if(i) i.className='fas fa-pause'; } });
    a.addEventListener('ended', ()=>{ const bar = createBar(); if (currentAudio===a){ bar.style.display='none'; document.body.style.paddingTop=''; currentAudio=null; } });
  }

  function scan(){ document.querySelectorAll('audio').forEach(attachAudio); }

  // init
  createBar(); bindControls(); scan(); updateBarPosition();
  const mo = new MutationObserver(()=>{ scan(); updateBarPosition(); });
  mo.observe(document.documentElement, {subtree:true, childList:true, attributes:true, attributeFilter:['style','class']});
  window.addEventListener('resize', updateBarPosition);
})();


