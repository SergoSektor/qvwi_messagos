// Global lightweight incoming-call listener for all pages
(function(){
  if (window.__calls_initialized__) return; window.__calls_initialized__ = true;

  function loadScript(src){
    return new Promise((resolve, reject)=>{
      const s = document.createElement('script'); s.src = src; s.onload = resolve; s.onerror = reject; document.head.appendChild(s);
    });
  }

  async function ensureSocket(){
    if (!window.io){
      try { await loadScript('https://cdn.socket.io/4.0.1/socket.io.min.js'); } catch(_e){ return null; }
    }
    try {
      window.__global_socket = window.__global_socket || window.io();
      return window.__global_socket;
    } catch(_e){ return null; }
  }

  function showIncomingBanner(fromUserId){
    if (document.getElementById('incoming-call-banner')) return;
    const wrap = document.createElement('div');
    wrap.id = 'incoming-call-banner';
    wrap.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:1200;background:var(--panel,#1e1e1e);color:var(--text,#e6edf3);border:1px solid var(--table-border,rgba(255,255,255,0.12));border-radius:12px;box-shadow:0 12px 40px rgba(0,0,0,.35);padding:12px 14px;display:flex;gap:10px;align-items:center;';
    wrap.innerHTML = '<div style="font-weight:700">Входящий звонок</div>'+
                     '<div style="margin-left:auto;display:flex;gap:8px">'+
                     '<button id="ic-accept" style="background:#22c55e;color:#fff;border:none;border-radius:8px;padding:8px 12px;cursor:pointer">Принять</button>'+
                     '<button id="ic-decline" style="background:#e11d48;color:#fff;border:none;border-radius:8px;padding:8px 12px;cursor:pointer">Отклонить</button>'+
                     '<button id="ic-open" style="background:#4a76a8;color:#fff;border:none;border-radius:8px;padding:8px 12px;cursor:pointer">Открыть</button>'+
                     '<button id="ic-close" style="background:transparent;color:var(--text,#e6edf3);border:1px solid var(--table-border,rgba(255,255,255,0.12));border-radius:8px;padding:8px 12px;cursor:pointer">Закрыть</button>'+
                     '</div>';
    document.body.appendChild(wrap);
    document.getElementById('ic-open').onclick = ()=>{ window.location.href = '/messages/'+fromUserId; };
    document.getElementById('ic-accept').onclick = ()=>{
      try{ sessionStorage.setItem('autoAcceptPeerId', String(fromUserId)); sessionStorage.setItem('autoAcceptTs', String(Date.now())); }catch(_e){}
      window.location.href = '/messages/'+fromUserId+'?auto=1';
    };
    document.getElementById('ic-decline').onclick = ()=>{
      try{ (window.__global_socket||window.io && window.io()).emit('webrtc_end_call', { receiver_id: fromUserId, reason: 'declined' }); }catch(_e){}
      wrap.remove();
    };
    document.getElementById('ic-close').onclick = ()=>{ wrap.remove(); };
    setTimeout(()=>{ try{ wrap.remove(); }catch(_e){} }, 10000);
    try{ if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission(); }catch(_e){}
    try{ if ('Notification' in window && Notification.permission === 'granted'){ const n = new Notification('Входящий звонок', { body: 'Открыть диалог?', silent:false }); setTimeout(()=>n.close(), 4000);} }catch(_e){}
  }

  (async function init(){
    const socket = await ensureSocket(); if (!socket) return;
    socket.off && socket.off('webrtc_offer');
    socket.on('webrtc_offer', (data)=>{ if (data && data.sender_id){ showIncomingBanner(data.sender_id); } });
    // Скрыть баннер, если звонок завершён/отклонён, и показать причину при отклонении
    socket.on('webrtc_end_call', (data)=>{
      const b = document.getElementById('incoming-call-banner'); if (b) b.remove();
      try{
        const reason = (data && data.reason) || '';
        if (/declined/i.test(reason) || /откл/i.test(reason)){
          // небольшой «бип» отклонения
          try{
            const AC = window.AudioContext || window.webkitAudioContext; const ctx = new AC();
            const g = ctx.createGain(); g.connect(ctx.destination);
            const o = ctx.createOscillator(); o.type='sawtooth'; o.connect(g);
            const now = ctx.currentTime; try{ g.gain.setValueAtTime(0.0001, now); }catch(_e){ g.gain.value=0.0001; }
            try{ o.frequency.setValueAtTime(820, now); o.frequency.linearRampToValueAtTime(360, now+0.35); }catch(_e){ o.frequency.value=600; }
            o.start(now); o.stop(now+0.36);
            try{ g.gain.setTargetAtTime(0.14, now, 0.01); g.gain.setTargetAtTime(0.0001, now+0.34, 0.02);}catch(_e){}
            setTimeout(()=>{ try{ g.disconnect(); ctx.close(); }catch(_e){} }, 500);
          }catch(_e){}
          const id = 'call-result-banner';
          const old = document.getElementById(id); if (old) old.remove();
          const wrap = document.createElement('div');
          wrap.id = id;
          wrap.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:1200;background:var(--panel,#1e1e1e);color:var(--text,#e6edf3);border:1px solid var(--table-border,rgba(255,255,255,0.12));border-radius:12px;box-shadow:0 12px 40px rgba(0,0,0,.35);padding:12px 14px;display:flex;gap:10px;align-items:center;';
          wrap.innerHTML = '<div style="font-weight:700">Вызов отклонён</div>'+
                           '<button id="crb-close" style="margin-left:12px;background:transparent;color:var(--text,#e6edf3);border:1px solid var(--table-border,rgba(255,255,255,0.12));border-radius:8px;padding:6px 10px;cursor:pointer">Закрыть</button>';
          document.body.appendChild(wrap);
          document.getElementById('crb-close').onclick = ()=>{ wrap.remove(); };
          setTimeout(()=>{ try{ wrap.remove(); }catch(_e){} }, 6000);
        }
      }catch(_e){}
    });
  })();
})();


