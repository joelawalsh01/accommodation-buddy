// Feature toggle interactions handled by HTMX + Alpine.js
// This file provides any supplementary toggle behavior

document.addEventListener('htmx:afterSwap', function(evt) {
    // Update visual state after toggle
    const target = evt.detail.target;
    if (target && target.classList.contains('toggle-status')) {
        const card = target.closest('.feature-card');
        if (card) {
            const isEnabled = target.textContent.trim() === 'enabled';
            card.classList.toggle('enabled', isEnabled);
        }
    }
});
