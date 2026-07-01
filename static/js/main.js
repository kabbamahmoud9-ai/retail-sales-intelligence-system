// ===== NOTIFICATION PANEL =====
function toggleNotifications() {
    const panel = document.getElementById('notifPanel');
    const overlay = document.getElementById('notifOverlay');
    panel.classList.toggle('open');
    overlay.classList.toggle('open');
    if (panel.classList.contains('open')) {
        loadNotifications();
    }
}

function loadNotifications() {
    fetch('/notifications/api/recent/')
        .then(r => r.json())
        .then(data => {
            const list = document.getElementById('notifList');
            const badge = document.getElementById('notifCount');

            if (data.count > 0) {
                badge.textContent = data.count;
                badge.style.display = 'flex';
            } else {
                badge.style.display = 'none';
            }

            if (data.notifications.length === 0) {
                list.innerHTML = `
                    <div class="empty-state" style="padding:40px 20px;">
                        <i class="bi bi-bell-slash" style="font-size:32px; opacity:0.3;"></i>
                        <p style="margin-top:12px; font-size:13px; color:var(--text-muted);">No notifications</p>
                        <span style="font-size:12px; color:var(--text-muted);">AI insights will appear here</span>
                    </div>`;
                return;
            }

            list.innerHTML = data.notifications.map(n => `
                <div class="notif-item" id="np-${n.id}">
                    <div class="notif-dot" style="background:${n.dot_color};"></div>
                    <div class="notif-content">
                        <p>${n.title}</p>
                        <span>${n.message.substring(0, 80)}...</span>
                        <div style="margin-top:6px; display:flex; gap:10px; align-items:center;">
                            <span style="font-size:11px; color:var(--text-muted);">${n.created_at}</span>
                            ${n.action_url ? `<a href="${n.action_url}" style="font-size:11px; color:var(--primary); font-weight:600; text-decoration:none;">${n.action_label} →</a>` : ''}
                        </div>
                    </div>
                    <button onclick="markReadPanel(${n.id})" style="background:none; border:none; color:var(--text-muted); cursor:pointer; font-size:16px; padding:4px;" title="Mark read">×</button>
                </div>
            `).join('');

            // Add "View All" link at bottom
            list.innerHTML += `
                <div style="padding:12px; text-align:center; border-top:1px solid var(--border);">
                    <a href="/notifications/" style="font-size:13px; color:var(--primary); font-weight:600; text-decoration:none;">
                        View All Notifications →
                    </a>
                </div>`;
        });
}

function markReadPanel(id) {
    fetch(`/notifications/mark-read/${id}/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') }
    }).then(() => {
        const item = document.getElementById(`np-${id}`);
        if (item) item.remove();
        loadNotifications();
    });
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            cookie = cookie.trim();
            if (cookie.startsWith(name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// ===== TOAST NOTIFICATIONS =====
function showToast(message, type = 'success') {
    const icons = { success: '✅', error: '❌', warning: '⚠️' };
    const toast = document.createElement('div');
    toast.className = `toast-modern ${type !== 'success' ? type : ''}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type]}</span>
        <span class="toast-text">${message}</span>
        <button class="toast-close" onclick="this.parentElement.remove()">×</button>
    `;
    document.querySelector('.toast-container').appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

// ===== AUTO LOAD BADGE ON PAGE LOAD =====
document.addEventListener('DOMContentLoaded', function() {
    // Show Django messages as toasts
    const messages = document.querySelectorAll('.django-message');
    messages.forEach(msg => {
        const type = msg.dataset.type === 'error' ? 'error' :
                     msg.dataset.type === 'warning' ? 'warning' : 'success';
        showToast(msg.dataset.text, type);
    });

    // Load notification count on every page
    fetch('/notifications/api/count/')
        .then(r => r.json())
        .then(data => {
            const badge = document.getElementById('notifCount');
            if (badge && data.count > 0) {
                badge.textContent = data.count;
                badge.style.display = 'flex';
            }
        }).catch(() => {});
});