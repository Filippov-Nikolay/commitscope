/**
 * ui.js — управление состояниями интерфейса, тост-уведомления, ripple.
 */

// ===========================================================
// Состояния страницы
// ===========================================================

/** Скрывает все блоки состояний */
function hideAllStates() {
  document.getElementById('state-empty').hidden   = true;
  document.getElementById('state-loading').hidden = true;
  document.getElementById('state-error').hidden   = true;
  document.getElementById('results').hidden       = true;
}

function showLoading() {
  hideAllStates();
  document.querySelector('#state-loading p').textContent = 'Загружаем данные из GitHub API...';
  document.getElementById('state-loading').hidden = false;
}

/** Плавно скрывает состояние загрузки перед переходом к результатам */
async function dissolveLoading() {
  const el = document.getElementById('state-loading');
  if (el.hidden) return;
  el.style.animation = 'fade-out-up 0.22s ease forwards';
  await new Promise(r => setTimeout(r, 200));
  el.style.animation = '';
}

function showError(message) {
  hideAllStates();
  document.getElementById('error-message').textContent = message;
  document.getElementById('state-error').hidden = false;
}

function setButtonLoading(isLoading) {
  document.querySelector('.btn-search').classList.toggle('loading', isLoading);
}

/** Обновляет состояние кнопки «Очистить»: disabled если результатов нет */
function updateClearBtn() {
  document.getElementById('btn-clear').disabled =
    document.getElementById('results').hidden;
}

// ===========================================================
// Тост-уведомление
// ===========================================================

let toastEl    = null;
let toastTimer = null;

function createToast() {
  toastEl = document.createElement('div');
  toastEl.className = 'toast';
  document.body.appendChild(toastEl);
}

function showToast(message) {
  if (!toastEl) return;
  toastEl.textContent = message;
  toastEl.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove('show'), 2000);
}

// ===========================================================
// Ripple-эффект
// ===========================================================

function ripple(e, btn) {
  const span = document.createElement('span');
  span.className = 'btn-ripple';
  const rect = btn.getBoundingClientRect();
  const size = Math.max(rect.width, rect.height);
  span.style.cssText = [
    `width:${size}px`,
    `height:${size}px`,
    `left:${e.clientX - rect.left - size / 2}px`,
    `top:${e.clientY - rect.top - size / 2}px`,
  ].join(';');
  btn.appendChild(span);
  span.addEventListener('animationend', () => span.remove());
}
