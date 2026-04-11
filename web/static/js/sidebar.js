/**
 * 侧边栏导航 — 展开/收起 + 设备树 + 当前页高亮
 */
(function() {
    var sidebar = document.getElementById('sidebar');
    if (!sidebar) return;

    var STORAGE_KEY = 'sidebar_expanded';
    var devicesOpen = false;

    // ── 初始化状态 ──
    function init() {
        var saved = localStorage.getItem(STORAGE_KEY);
        // 桌面默认展开，移动默认收起
        var defaultExpanded = window.innerWidth > 768;
        var expanded = saved !== null ? saved === 'true' : defaultExpanded;
        if (expanded) sidebar.classList.add('expanded');

        highlightCurrent();
        loadDeviceTree();
        loadSystemStatus();

        // 每 5 秒刷新设备树和系统状态
        setInterval(function() {
            loadDeviceTree();
            loadSystemStatus();
        }, 5000);
    }

    // ── 展开/收起 ──
    window.toggleSidebar = function() {
        sidebar.classList.toggle('expanded');
        localStorage.setItem(STORAGE_KEY, sidebar.classList.contains('expanded'));
    };

    // ── 设备子菜单展开/收起 ──
    window.toggleDevices = function() {
        var el = document.getElementById('sidebar-devices');
        if (el) {
            devicesOpen = !devicesOpen;
            if (devicesOpen) {
                el.classList.add('open');
            } else {
                el.classList.remove('open');
            }
        }
    };

    // ── 当前页高亮 ──
    function highlightCurrent() {
        var path = window.location.pathname;
        var items = sidebar.querySelectorAll('.sidebar-item[data-page]');
        items.forEach(function(item) {
            item.classList.remove('active');
            var page = item.getAttribute('data-page');
            if (page === 'overview' && path === '/') {
                item.classList.add('active');
            } else if (page === 'settings' && path === '/settings') {
                item.classList.add('active');
            } else if (page === 'devices' && (path.indexOf('/machine') === 0)) {
                item.classList.add('active');
                // 自动展开设备子菜单
                var el = document.getElementById('sidebar-devices');
                if (el) { el.classList.add('open'); devicesOpen = true; }
            }
        });
    }

    // ── 加载设备树 ──
    function loadDeviceTree() {
        fetch('/api/overview').then(function(r) { return r.json(); }).then(function(data) {
            var container = document.getElementById('sidebar-devices');
            if (!container) return;

            var machines = data.machines || [];
            var path = window.location.pathname;
            var html = '';

            machines.forEach(function(m) {
                var plcClass = m.plc_connected ? 'ok' : 'err';
                var mActive = path === '/machine/' + m.id ? ' active' : '';
                html += '<div class="sidebar-machine' + mActive + '" onclick="location.href=\'/machine/' + m.id + '\'">';
                html += '<span class="sidebar-dot ' + plcClass + '"></span>';
                html += '<span>' + escSidebar(m.name) + '</span>';
                html += '</div>';

                (m.funnels || []).forEach(function(f) {
                    var camClass = f.camera_status === 'connected' ? 'ok' : (f.camera_status === 'not_available' ? 'off' : 'err');
                    var fActive = path === '/machine/' + m.id + '/funnel/' + f.id ? ' active' : '';
                    html += '<a class="sidebar-funnel' + fActive + '" href="/machine/' + m.id + '/funnel/' + f.id + '">';
                    html += '<span class="sidebar-dot ' + camClass + '"></span> ';
                    html += escSidebar(f.name);
                    html += '</a>';
                });
            });

            container.innerHTML = html;

            // 如果当前在设备页，自动展开
            if (path.indexOf('/machine') === 0 && !devicesOpen) {
                container.classList.add('open');
                devicesOpen = true;
            }
        }).catch(function() {});
    }

    // ── 加载系统状态 ──
    function loadSystemStatus() {
        fetch('/api/health').then(function(r) { return r.json(); }).then(function(h) {
            var footer = document.getElementById('sidebar-footer');
            if (!footer) return;

            var statusDot = h.status === 'ok' ? 'ok' : (h.status === 'degraded' ? 'err' : 'off');
            footer.innerHTML =
                '<div class="sidebar-footer-item">' +
                    '<span class="sidebar-dot ' + statusDot + '"></span>' +
                    '<span class="sidebar-footer-label">' + (h.uptime_h || 0) + 'h</span>' +
                '</div>' +
                '<div class="sidebar-footer-item">' +
                    '<span style="width:20px;text-align:center;font-size:10px">💾</span>' +
                    '<span class="sidebar-footer-label">' + (h.rss_mb || '?') + 'MB</span>' +
                '</div>';
        }).catch(function() {});
    }

    // ── HTML 转义 ──
    function escSidebar(t) {
        var d = document.createElement('div');
        d.textContent = t;
        return d.innerHTML;
    }

    // 启动
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
