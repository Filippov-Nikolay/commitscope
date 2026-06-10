/**
 * accordion.js — плавное раскрытие/скрытие секций (Файлы, Описание, diff).
 *
 * Используем JS-анимацию высоты вместо CSS-transition на height:auto,
 * потому что браузеры не умеют плавно переходить от фиксированного
 * значения к auto. Высота всегда измеряется через scrollHeight перед
 * стартом анимации.
 *
 * dataset.open === 'true' — единственный источник истины о логическом
 * состоянии секции. Обновляется немедленно при каждом клике, не дожидаясь
 * завершения анимации, поэтому быстрые повторные клики не рассинхронизируют
 * стрелку с реальным состоянием.
 */

// Один таймер cleanup на каждый элемент; WeakMap не держит ссылки на элементы
const _slideTimers = new WeakMap();

/**
 * Плавно раскрывает элемент (height: 0 → scrollHeight → auto).
 * Если анимация закрытия уже идёт — плавно разворачивает её с текущей высоты,
 * не допуская прыжков.
 */
function slideDown(el) {
  // Читаем текущие значения ДО отмены transition, пока они ещё анимируются
  const wasHidden   = el.hidden;
  const fromH       = wasHidden ? 0 : el.offsetHeight;
  const fromOpacity = wasHidden ? 0 : (parseFloat(getComputedStyle(el).opacity) || 0);

  el.hidden           = false;
  el.style.overflow   = 'hidden';
  el.style.transition = 'none';
  el.style.height     = fromH + 'px';
  el.style.opacity    = String(fromOpacity);
  void el.offsetHeight; // force reflow — фиксируем стартовую позицию без flash

  el.style.transition = 'height 0.3s cubic-bezier(0.4,0,0.2,1), opacity 0.25s ease';
  el.style.height     = el.scrollHeight + 'px';
  el.style.opacity    = '1';

  clearTimeout(_slideTimers.get(el));
  _slideTimers.set(el, setTimeout(() => {
    if (el.dataset.open === 'true') {
      el.style.height = el.style.overflow = el.style.transition = el.style.opacity = '';
    }
  }, 310));
}

/**
 * Плавно скрывает элемент (height: current → 0).
 * Если анимация открытия уже идёт — плавно разворачивает её с текущей высоты.
 */
function slideUp(el) {
  if (el.hidden) return;
  const fromH       = el.offsetHeight;
  const fromOpacity = parseFloat(getComputedStyle(el).opacity) || 1;

  el.style.overflow   = 'hidden';
  el.style.transition = 'none';
  el.style.height     = fromH + 'px';
  el.style.opacity    = String(fromOpacity);
  void el.offsetHeight;

  el.style.transition = 'height 0.22s cubic-bezier(0.4,0,0.2,1), opacity 0.18s ease';
  el.style.height     = '0';
  el.style.opacity    = '0';

  clearTimeout(_slideTimers.get(el));
  _slideTimers.set(el, setTimeout(() => {
    if (el.dataset.open !== 'true') {
      el.hidden = true;
      el.style.height = el.style.overflow = el.style.transition = el.style.opacity = '';
    }
  }, 230));
}

/** Раскрывает/скрывает блок «Файлы» */
function toggleSection(btn) {
  const section  = btn.nextElementSibling;
  const willOpen = section.dataset.open !== 'true';
  section.dataset.open = willOpen;
  btn.classList.toggle('open', willOpen);
  if (willOpen) slideDown(section); else slideUp(section);
}

/** Раскрывает/скрывает блок «Описание» */
function toggleCommitBody(btn) {
  const body     = btn.nextElementSibling;
  const willOpen = body.dataset.open !== 'true';
  body.dataset.open = willOpen;
  btn.querySelector('.toggle-btn__arrow').style.transform = willOpen ? 'rotate(90deg)' : '';
  btn.querySelector('.commit-body-label').textContent     = willOpen ? ' Скрыть' : ' Описание';
  if (willOpen) slideDown(body); else slideUp(body);
}

/** Раскрывает/скрывает diff-блок внутри файла */
function toggleDiff(btn) {
  const diffView = btn.closest('.file-item').querySelector('.diff-view');
  if (!diffView) return;
  diffView.hidden = !diffView.hidden;
  btn.textContent = diffView.hidden ? 'diff' : 'скрыть';
}
