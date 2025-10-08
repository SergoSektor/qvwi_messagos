(function(){
  try {
    var width = Math.max(screen.width || 0, window.innerWidth || 0);
    var ua = (navigator.userAgent || '').toLowerCase();
    var isTablet = /(ipad|tablet|sm-t\d+)/.test(ua) || (width >= 768 && width <= 1024);
    var isMobile = !isTablet && (/(iphone|ipod|android|mobile)/.test(ua) || width < 768);
    var cls = isMobile ? 'device-mobile' : (isTablet ? 'device-tablet' : 'device-desktop');
    document.documentElement.classList.add(cls);
    document.body && document.body.classList.add(cls);
    window.__deviceType = cls;
  } catch(e) { /* no-op */ }
})();


