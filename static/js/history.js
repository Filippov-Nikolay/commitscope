/**
 * history.js — история ввода полей формы и восстановление состояния из localStorage.
 *
 * Каждое поле формы запоминает до HISTORY_MAX последних введённых значений.
 * При фокусе/вводе появляется выпадающий список с фильтрацией и кнопкой удаления.
 *
 * Дополнительно сохраняются «последние значения» полей (gh_last) —
 * они восстанавливаются при перезагрузке страницы.
 */

const HISTORY_MAX = 10;
const HISTORY_IDS = ['owner', 'repo', 'branch', 'max-commits'];

// ===========================================================
// CRUD истории в localStorage
// ===========================================================

function historyKey(id)  { return `gh_hist_${id}`; }

function historyLoad(id) {
  try { return JSON.parse(localStorage.getItem(historyKey(id)) || '[]'); }
  catch { return []; }
}

function historySave(id, arr) {
  localStorage.setItem(historyKey(id), JSON.stringify(arr));
}

function historyAdd(id, value) {
  if (!value.trim()) return;
  let arr = historyLoad(id).filter(v => v !== value);
  arr.unshift(value);
  historySave(id, arr.slice(0, HISTORY_MAX));
}

function historyRemove(id, value) {
  historySave(id, historyLoad(id).filter(v => v !== value));
}

// ===========================================================
// Сохранение / восстановление значений полей
// ===========================================================

/** Сохраняет последние использованные значения полей */
function saveLastValues(owner, repo, branch, maxCommits) {
  localStorage.setItem('gh_last', JSON.stringify({ owner, repo, branch, maxCommits }));
}

/** Восстанавливает значения полей из последнего сохранённого состояния */
function restoreLastValues() {
  try {
    const saved = JSON.parse(localStorage.getItem('gh_last') || 'null');
    if (!saved) return;
    if (saved.owner)      document.getElementById('owner').value       = saved.owner;
    if (saved.repo)       document.getElementById('repo').value        = saved.repo;
    if (saved.branch)     document.getElementById('branch').value      = saved.branch;
    if (saved.maxCommits) document.getElementById('max-commits').value = saved.maxCommits;
  } catch { /* повреждённый localStorage — просто игнорируем */ }
}

/** Восстанавливает результаты последнего успешного поиска */
function restoreSavedResults() {
  try {
    const saved = JSON.parse(localStorage.getItem('gh_results') || 'null');
    if (!saved?.commits?.length) { updateClearBtn(); return; }
    renderResults(
      saved.commits,
      { owner: saved.owner, repo: saved.repo, branch: saved.branch },
      { scroll: false },
    );
  } catch {
    updateClearBtn();
  }
}

// ===========================================================
// Выпадающий список истории
// ===========================================================

/** Инициализация: вешаем обработчики на поля формы */
function initHistory() {
  HISTORY_IDS.forEach(id => {
    const input = document.getElementById(id);
    if (!input) return;
    input.addEventListener('focus', () => renderDropdown(id));
    input.addEventListener('input', () => renderDropdown(id));
  });

  document.addEventListener('click', e => {
    if (!e.target.closest('.field')) closeDropdowns();
  });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeDropdowns();
  });
}

/** Рендерит (или обновляет) выпадающий список истории для поля */
function renderDropdown(id) {
  const input  = document.getElementById(id);
  const field  = input.closest('.field');
  const filter = input.value.trim().toLowerCase();

  // Закрываем дропдауны всех других полей
  document.querySelectorAll('.field.has-dropdown').forEach(f => {
    if (f !== field) {
      f.querySelector('.field-dropdown')?.remove();
      f.classList.remove('has-dropdown');
    }
  });

  let items = historyLoad(id);
  if (filter) items = items.filter(v => v.toLowerCase().includes(filter));

  field.querySelector('.field-dropdown')?.remove();

  if (!items.length) {
    field.classList.remove('has-dropdown');
    return;
  }

  field.classList.add('has-dropdown');

  const dropdown = document.createElement('div');
  dropdown.className = 'field-dropdown';

  items.forEach(value => {
    const item = document.createElement('div');
    item.className = 'field-dropdown-item';

    const text = document.createElement('span');
    text.className = 'field-dropdown-item__text';
    text.textContent = value;

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'field-dropdown-item__remove';
    removeBtn.title = 'Удалить из истории';
    removeBtn.textContent = '✕';
    // stopPropagation на mousedown: не даём всплыть до item,
    // иначе item.mousedown поставит input.value и закроет dropdown
    // раньше, чем сработает click на кнопке удаления
    removeBtn.addEventListener('mousedown', e => {
      e.stopPropagation();
      e.preventDefault();
    });
    removeBtn.addEventListener('click', e => {
      e.stopPropagation();
      historyRemove(id, value);
      renderDropdown(id);
    });

    // mousedown вместо click: срабатывает до blur на инпуте,
    // поэтому инпут не теряет фокус и dropdown не исчезает
    item.addEventListener('mousedown', e => {
      e.preventDefault();
      input.value = value;
      closeDropdowns();
      updateClearBtn();
    });

    item.append(text, removeBtn);
    dropdown.appendChild(item);
  });

  field.appendChild(dropdown);
}

function closeDropdowns() {
  document.querySelectorAll('.field-dropdown').forEach(d => d.remove());
  document.querySelectorAll('.field.has-dropdown').forEach(f => f.classList.remove('has-dropdown'));
}
