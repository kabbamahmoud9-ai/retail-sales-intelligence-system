// ===== NOTIFICATION PANEL =====
function toggleNotifications() {
    const panel = document.getElementById('notifPanel');
    const overlay = document.getElementById('notifOverlay');
    panel.classList.toggle('open');
    overlay.classList.toggle('open');
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

// Auto-show Django messages as toasts
document.addEventListener('DOMContentLoaded', function() {
    const messages = document.querySelectorAll('.django-message');
    messages.forEach(msg => {
        const type = msg.dataset.type === 'error' ? 'error' :
                     msg.dataset.type === 'warning' ? 'warning' : 'success';
        showToast(msg.dataset.text, type);
    });
});