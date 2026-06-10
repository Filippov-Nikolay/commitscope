/**
 * modal.js — модальное окно подтверждения очистки результатов.
 * Зависит от: ui.js (hideAllStates, updateClearBtn), history.js (closeDropdowns)
 */

function openClearModal() {
  const overlay = document.getElementById('modal-clear');
  overlay.hidden = false;
  // Фокус на «Отмена» — безопаснее как действие по умолчанию
  document.getElementById('modal-cancel').focus();
}

async function closeClearModal() {
  const overlay = document.getElementById('modal-clear');
  overlay.classList.add('is-closing');
  await new Promise(r => setTimeout(r, 190));
  overlay.classList.remove('is-closing');
  overlay.hidden = true;
}

/** Очищает результаты поиска с каскадной анимацией карточек */
async function clearForm() {
  const cards = [...document.querySelectorAll('#commits-list .commit-card')];
  if (cards.length > 0) {
    document.getElementById('results-header').style.animation = 'fade-out-up 0.2s ease forwards';
    cards.forEach((card, i) => {
      card.style.setProperty('--exit-delay', `${Math.min(i, 12) * 35}ms`);
      card.classList.add('is-exiting');
    });
    await new Promise(r => setTimeout(r, 260 + Math.min(cards.length - 1, 12) * 35));
    document.getElementById('results-header').style.animation = '';
  }
  hideAllStates();
  document.getElementById('state-empty').hidden = false;
  localStorage.removeItem('gh_results');
  closeDropdowns();
  updateClearBtn();
}

// Закрыть модал по Escape
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !document.getElementById('modal-clear').hidden) {
    closeClearModal();
  }
});
