document.addEventListener('DOMContentLoaded', function() {
    const themeToggle = document.getElementById('themeToggle');
    const icon = themeToggle.querySelector('i');
    
    // Применяем тему мгновенно при загрузке
    const currentTheme = localStorage.getItem('theme') || 'light';
    if (currentTheme === 'dark') {
        applyDarkTheme();
    }
    
    // Настраиваем обработчик для плавного переключения
    themeToggle.addEventListener('click', function() {
        toggleThemeWithAnimation();
    });
    
    function toggleThemeWithAnimation() {
        // Запоминаем текущее состояние
        const wasDark = document.body.classList.contains('dark-theme');
        
        // Применяем новую тему мгновенно
        if (wasDark) {
            removeDarkTheme();
        } else {
            applyDarkTheme();
        }
        
        // Включаем анимацию и временно возвращаем предыдущую тему
        document.body.classList.add('theme-animating');
        document.body.classList.toggle('dark-theme', wasDark);
        
        // Даем браузеру время на отрисовку
        requestAnimationFrame(() => {
            // Запускаем анимацию перехода
            document.body.classList.add('theme-transition');
            document.body.classList.toggle('dark-theme', !wasDark);
            
            // Сохраняем состояние и убираем анимацию после завершения
            setTimeout(() => {
                document.body.classList.remove('theme-transition', 'theme-animating');
                localStorage.setItem('theme', !wasDark ? 'dark' : 'light');
                updateIcon(!wasDark);
            }, 500);
        });
    }
    
    function applyDarkTheme() {
        document.body.classList.add('dark-theme');
        updateIcon(true);
    }
    
    function removeDarkTheme() {
        document.body.classList.remove('dark-theme');
        updateIcon(false);
    }
    
    function updateIcon(isDark) {
        if (isDark) {
            icon.classList.replace('fa-moon', 'fa-sun');
        } else {
            icon.classList.replace('fa-sun', 'fa-moon');
        }
    }
});