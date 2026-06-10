/**
 * GitHub Commits Parser - фронтенд
 *
 * Что делает этот файл:
 * 1. Слушает отправку формы
 * 2. Делает запрос к нашему FastAPI-серверу (/commits?...)
 * 3. Берёт JSON-ответ и рисует красивые карточки коммитов в DOM
 *
 * Никаких внешних библиотек - чистый JavaScript (Vanilla JS).
 */

// ===========================================================
// Инициализация - запускаем всё когда страница загружена
// ===========================================================

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('search-form');
  form.addEventListener('submit', handleSubmit);

  const btnClear = document.getElementById('btn-clear');
  btnClear.addEventListener('click', e => { ripple(e, btnClear); openClearModal(); });
  document.getElementById('modal-cancel').addEventListener('click', () => closeClearModal());
  document.getElementById('modal-confirm').addEventListener('click', async () => { await closeClearModal(); await clearForm(); });
  document.getElementById('modal-clear').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeClearModal(); // клик по оверлею
  });

  createToast();
  initHistory();
  restoreLastValues();
  restoreSavedResults();
});

// ===========================================================
// Обработка отправки формы
// ===========================================================

/**
 * Вызывается при нажатии «Анализировать».
 * event.preventDefault() - отменяет стандартную перезагрузку страницы.
 */
async function handleSubmit(event) {
  event.preventDefault();
  closeDropdowns();

  // Читаем значения из полей формы
  const owner      = document.getElementById('owner').value.trim();
  const repo       = document.getElementById('repo').value.trim();
  const branch     = document.getElementById('branch').value.trim() || 'main';
  const maxCommits = document.getElementById('max-commits').value.trim();

  if (!owner || !repo) return;

  // Сохраняем введённые значения в историю и как «последние»
  historyAdd('owner', owner);
  historyAdd('repo', repo);
  historyAdd('branch', branch);
  if (maxCommits) historyAdd('max-commits', maxCommits);
  saveLastValues(owner, repo, branch, maxCommits);

  // Переходим в состояние загрузки
  showLoading();
  setButtonLoading(true);

  try {
    const commits = await fetchCommits(owner, repo, branch, maxCommits || null);
    await dissolveLoading();
    renderResults(commits, { owner, repo, branch });
  } catch (err) {
    await dissolveLoading();
    showError(err.message);
  } finally {
    setButtonLoading(false);
  }
}

// ===========================================================
// API-запрос через Server-Sent Events (SSE)
// ===========================================================

/**
 * Подключается к /commits/stream и получает коммиты по одному.
 *
 * EventSource - встроенный в браузер механизм для получения потока событий
 * от сервера. Сервер держит соединение открытым и отправляет данные по мере
 * готовности, не дожидаясь завершения всей работы.
 *
 * Почему не обычный fetch:
 * - fetch ждёт полного ответа - мы видим результат только в конце
 * - EventSource получает данные по мере поступления - можно показывать прогресс
 *
 * @returns {Promise<Array>} - список коммитов (разрешается когда всё загружено)
 */
function fetchCommits(owner, repo, branch, maxCommits) {
  const params = new URLSearchParams({ owner, repo, branch });
  if (maxCommits) params.set('max_commits', maxCommits);

  // Возвращаем Promise: снаружи код всё так же делает await fetchCommits(...)
  // но внутри используем EventSource для получения прогресса
  return new Promise((resolve, reject) => {
    const source = new EventSource(`/commits/stream?${params.toString()}`);
    const collected = []; // Накапливаем коммиты по мере получения

    source.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'total') {
        // Получили общее количество - обновляем текст под спиннером
        updateLoadingText(`Загружаем коммиты: 0 из ${data.total}`);

        if (data.total === 0) {
          source.close();
          resolve([]);
        }

      } else if (data.type === 'progress') {
        // Пришёл очередной коммит - добавляем в список и обновляем счётчик
        collected.push(data.entry);
        updateLoadingText(`Загружаем коммиты: ${data.current} из ${data.total}`);

      } else if (data.type === 'done') {
        // Всё загружено - закрываем соединение и возвращаем результат
        source.close();
        resolve(collected);

      } else if (data.type === 'error') {
        source.close();
        reject(new Error(data.message));
      }
    };

    // Потеря соединения (сервер упал, сеть пропала и т.д.)
    source.onerror = () => {
      source.close();
      reject(new Error('Потеряно соединение с сервером'));
    };
  });
}

/** Обновляет текст под спиннером загрузки с пульс-анимацией */
function updateLoadingText(text) {
  const el = document.querySelector('#state-loading p');
  if (!el) return;
  el.classList.remove('count-update');
  void el.offsetWidth; // форс-рефлоу для перезапуска анимации
  el.textContent = text;
  el.classList.add('count-update');
}

// ===========================================================
// Управление состояниями интерфейса
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

// ===========================================================
// Рендеринг результатов
// ===========================================================

/**
 * Главная функция отрисовки.
 * Берёт массив коммитов и вставляет HTML-карточки в DOM.
 */
function renderResults(commits, { owner, repo, branch }, { scroll = true } = {}) {
  hideAllStates();

  if (!commits || commits.length === 0) {
    showError('Коммиты не найдены. Проверьте название репозитория и ветки.');
    return;
  }

  // Шапка результатов
  document.getElementById('results-header').innerHTML = buildResultsHeader(
    commits, owner, repo, branch
  );

  // Список карточек
  const list = document.getElementById('commits-list');
  list.innerHTML = '';
  commits.forEach((commit, i) => {
    list.appendChild(buildCommitCard(commit, i));
  });

  document.getElementById('results').hidden = false;
  updateClearBtn();

  // Сохраняем результаты для восстановления после перезагрузки
  try {
    localStorage.setItem('gh_results', JSON.stringify({ commits, owner, repo, branch }));
  } catch { /* quota exceeded — просто не сохраняем */ }

  if (scroll) {
    document.getElementById('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

/** Строит HTML шапки с метаданными о запросе */
function buildResultsHeader(commits, owner, repo, branch) {
  const totalAdd = commits.reduce((s, c) => s + c.stats.additions, 0);
  const totalDel = commits.reduce((s, c) => s + c.stats.deletions, 0);

  return `
    <div class="results-header__title">${escHtml(owner)}/${escHtml(repo)}</div>
    <span class="results-header__badge">⎇ ${escHtml(branch)}</span>
    <span class="results-header__badge" style="color:var(--green)">+${totalAdd}</span>
    <span class="results-header__badge" style="color:var(--red)">-${totalDel}</span>
    <span class="results-header__count">${commits.length} коммитов</span>
  `;
}

// ===========================================================
// Построение карточки коммита
// ===========================================================

/**
 * Строит DOM-элемент карточки для одного коммита.
 * Возвращает HTMLElement, который вставляем в список.
 */
function buildCommitCard(commit, index = 0) {
  const card = document.createElement('div');
  card.className = 'commit-card';
  card.style.setProperty('--card-delay', `${Math.min(index * 55, 440)}ms`);

  // Высчитываем процент добавлений для цветной полоски сверху карточки
  const total  = commit.stats.additions + commit.stats.deletions;
  const addPct = total > 0 ? Math.round(commit.stats.additions / total * 100) : 50;

  card.innerHTML = `
    <!-- Цветная полоска: зелёная часть = % добавлений, красная = % удалений -->
    <div class="commit-card__accent"
         style="--add-pct: ${addPct}%"></div>

    <div class="commit-card__body">

      <!-- Заголовок: аватар, автор, SHA, дата, ссылка -->
      <div class="commit-card__header">
        ${buildAvatar(commit.author, 32, 'avatar', commit.avatar_url || null)}
        <span class="commit-card__author">${escHtml(commit.author)}</span>
        <span class="commit-sha" title="Нажмите чтобы скопировать SHA"
              onclick="copySha('${escHtml(commit.sha)}')">
          ${escHtml(commit.short)}
        </span>
        <span class="commit-date">${formatDate(commit.date)}</span>
        <a class="commit-link" href="${escHtml(commit.url)}" target="_blank"
           title="Открыть на GitHub" rel="noopener">
          <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14">
            <path d="M10.604 1h4.146a.25.25 0 01.25.25v4.146a.25.25 0 01-.427.177L13.03
              3.927 8.09 8.867a.75.75 0 01-1.06-1.06l4.94-4.94-1.646-1.644a.25.25 0
              01.177-.427zM3.75 2A1.75 1.75 0 002 3.75v8.5c0 .966.784 1.75 1.75
              1.75h8.5A1.75 1.75 0 0014 12.25v-3.5a.75.75 0 00-1.5 0v3.5a.25.25 0
              01-.25.25h-8.5a.25.25 0 01-.25-.25v-8.5a.25.25 0 01.25-.25h3.5a.75.75
              0 000-1.5h-3.5z"/>
          </svg>
        </a>
      </div>

      <!-- Сообщение коммита -->
      <div class="commit-message">${escHtml(commit.message.split('\n')[0])}</div>
      ${buildMessageBody(commit.message)}

      <!-- Статистика -->
      <div class="commit-stats">
        <span class="stat stat--add">+${commit.stats.additions}</span>
        <span class="stat stat--del">-${commit.stats.deletions}</span>
        ${buildStatsBar(commit.stats)}
        <span class="stat-files">${commit.files.length} файлов</span>
      </div>

    </div>

    <!-- Раскрывающийся список файлов -->
    ${commit.files.length > 0 ? buildFilesSection(commit) : ''}

    <!-- Комментарии -->
    ${commit.comments.length > 0 ? buildCommentsSection(commit.comments) : ''}
  `;

  return card;
}

/**
 * Строит блок с телом коммита (всё после первой строки).
 * Возвращает пустую строку если тела нет.
 */
function buildMessageBody(message) {
  const body = message.split('\n').slice(1).join('\n').trim();
  if (!body) return '';

  return `
    <div class="commit-body-section">
      <button class="commit-body-toggle" onclick="toggleCommitBody(this)">
        <span class="toggle-btn__arrow">▶</span><span class="commit-body-label"> Описание</span>
      </button>
      <div class="commit-body" hidden><div class="commit-body__inner">${escHtml(body)}</div></div>
    </div>
  `;
}

/** Строит визуальную полоску статистики (зелёная / красная) */
function buildStatsBar(stats) {
  const total  = stats.additions + stats.deletions;
  const addPct = total > 0 ? Math.round(stats.additions / total * 100) : 50;
  return `
    <div class="stats-bar" title="${stats.additions} добавлено, ${stats.deletions} удалено">
      <div class="stats-bar__add" style="width:${addPct}%"></div>
      <div class="stats-bar__del" style="width:${100 - addPct}%"></div>
    </div>
  `;
}

// ===========================================================
// Секция файлов
// ===========================================================

/** Строит раскрывающийся блок с изменёнными файлами */
function buildFilesSection(commit) {
  const filesHtml = commit.files.map(buildFileItem).join('');

  return `
    <div class="commit-card__footer">
      <!-- Кнопка-тогл: показать/скрыть список файлов -->
      <button class="toggle-btn" onclick="toggleSection(this)">
        <span class="toggle-btn__arrow">▶</span>
        Файлы (${commit.files.length})
      </button>
      <div class="files-list" hidden>
        <div class="files-list__inner">${filesHtml}</div>
      </div>
    </div>
  `;
}

/** Строит одну строку в списке файлов */
function buildFileItem(file) {
  const statusConfig = {
    added:    { icon: 'A', cls: 'added',    label: 'добавлен'       },
    modified: { icon: 'M', cls: 'modified', label: 'изменён'        },
    removed:  { icon: 'D', cls: 'removed',  label: 'удалён'         },
    renamed:  { icon: 'R', cls: 'renamed',  label: 'переименован'   },
  };

  const cfg = statusConfig[file.status] || { icon: '?', cls: 'modified', label: file.status };

  const diffBlock = file.patch
    ? `<div class="diff-view" hidden>${renderPatch(file.patch)}</div>`
    : '';

  const diffBtn = file.patch
    ? `<button class="diff-toggle" onclick="toggleDiff(this)" title="Показать diff">diff</button>`
    : '';

  return `
    <div class="file-item">
      <div class="file-item__header">
        <span class="file-status file-status--${cfg.cls}" title="${cfg.label}">${cfg.icon}</span>
        <span class="file-item__name" title="${escHtml(file.filename)}">${escHtml(file.filename)}</span>
        <span class="file-item__stats">
          <span class="file-stat--add">+${file.additions}</span>
          <span class="file-stat--del">-${file.deletions}</span>
        </span>
        ${diffBtn}
      </div>
      ${diffBlock}
    </div>
  `;
}

/**
 * Разбирает текст unified diff и превращает в HTML со строками.
 * Каждая строка раскрашивается по первому символу:
 *   +  → зелёная (добавление)
 *   -  → красная (удаление)
 *   @@ → синяя (заголовок блока)
 *   остальные → серые (контекст)
 */
function renderPatch(patch) {
  return patch.split('\n').map(line => {
    if (line.startsWith('@@')) {
      return `<span class="diff-line diff-line--hunk">${escHtml(line)}</span>`;
    } else if (line.startsWith('+')) {
      return `<span class="diff-line diff-line--add">${escHtml(line)}</span>`;
    } else if (line.startsWith('-')) {
      return `<span class="diff-line diff-line--del">${escHtml(line)}</span>`;
    } else {
      return `<span class="diff-line diff-line--ctx">${escHtml(line)}</span>`;
    }
  }).join('');
}

// ===========================================================
// Секция комментариев
// ===========================================================

function buildCommentsSection(comments) {
  const items = comments.map(c => {
    const pathInfo = c.path
      ? `<span class="comment-path"> ${escHtml(c.path)}:${c.line || '?'}</span>`
      : '';

    return `
      <div class="comment-item">
        ${buildAvatar(c.user, 28, 'comment-avatar', c.avatar_url || null)}
        <div class="comment-body">
          <div class="comment-meta">
            <span class="comment-user">${escHtml(c.user)}</span>
            ${pathInfo}
            <span class="comment-date"> · ${formatDate(c.created)}</span>
          </div>
          <div class="comment-text">${escHtml(c.body)}</div>
        </div>
      </div>
    `;
  }).join('');

  return `
    <div class="comments-section">
      <div class="comments-title">Комментарии (${comments.length})</div>
      ${items}
    </div>
  `;
}

// ===========================================================
// Тогл-функции (раскрыть/скрыть секции)
// ===========================================================

// Таймеры cleanup-анимаций: один таймер на элемент
const _slideTimers = new WeakMap();

/**
 * Плавно раскрывает элемент.
 * Если анимация закрытия уже идёт — плавно разворачивает её с текущей высоты.
 * dataset.open === 'true' — единый источник истины о логическом состоянии.
 */
function slideDown(el) {
  // Читаем текущую анимированную высоту и прозрачность ДО отмены transition
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
 * Плавно скрывает элемент.
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

/** Раскрывает/скрывает следующий DOM-элемент после кнопки */
function toggleSection(btn) {
  const section  = btn.nextElementSibling;
  const willOpen = section.dataset.open !== 'true';
  section.dataset.open = willOpen;
  btn.classList.toggle('open', willOpen);
  if (willOpen) slideDown(section); else slideUp(section);
}

/** Раскрывает/скрывает тело коммита */
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

// ===========================================================
// Вспомогательные функции
// ===========================================================

/**
 * Строит HTML-аватара.
 * Если есть avatarUrl — показывает реальное фото с GitHub.
 * Иначе — цветной круг с инициалами (цвет детерминирован по имени).
 */
function buildAvatar(name, size, extraClass = 'avatar', avatarUrl = null) {
  if (avatarUrl) {
    return `<img class="${extraClass}"
                 src="${escHtml(avatarUrl)}"
                 alt="${escHtml(name)}"
                 title="${escHtml(name)}"
                 width="${size}" height="${size}"
                 loading="lazy">`;
  }

  const initials = name
    .split(/[\s\-_]+/)
    .map(w => w[0] || '')
    .join('')
    .substring(0, 2)
    .toUpperCase();

  const colors = ['#3b82f6','#10b981','#f59e0b','#8b5cf6','#ec4899','#06b6d4','#84cc16'];
  const hash   = [...name].reduce((acc, ch) => acc + ch.charCodeAt(0), 0);
  const color  = colors[hash % colors.length];

  return `
    <div class="${extraClass}"
         style="background:${color}; width:${size}px; height:${size}px"
         title="${escHtml(name)}">
      ${escHtml(initials)}
    </div>
  `;
}

/**
 * Форматирует ISO-дату в читаемый вид.
 * "2024-01-15T10:00:00Z" → "15 янв. 2024"
 */
function formatDate(isoStr) {
  const d = new Date(isoStr);
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' });
}

/**
 * Экранирует HTML-спецсимволы, чтобы данные из API не ломали разметку.
 * Защита от XSS: если имя автора содержит <script> - он не выполнится.
 */
function escHtml(str) {
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return String(str).replace(/[&<>"']/g, ch => map[ch]);
}

/** Копирует SHA-хэш в буфер обмена и показывает уведомление */
async function copySha(sha) {
  try {
    await navigator.clipboard.writeText(sha);
    showToast(`SHA скопирован: ${sha.substring(0, 7)}`);
  } catch {
    showToast('Не удалось скопировать');
  }
}

// ===========================================================
// История полей формы (localStorage)
// ===========================================================

const HISTORY_MAX  = 10;
const HISTORY_IDS  = ['owner', 'repo', 'branch', 'max-commits'];

function historyKey(id)      { return `gh_hist_${id}`; }
function historyLoad(id)     {
  try { return JSON.parse(localStorage.getItem(historyKey(id)) || '[]'); }
  catch { return []; }
}
function historySave(id, arr) { localStorage.setItem(historyKey(id), JSON.stringify(arr)); }

function historyAdd(id, value) {
  if (!value.trim()) return;
  let arr = historyLoad(id).filter(v => v !== value);
  arr.unshift(value);
  historySave(id, arr.slice(0, HISTORY_MAX));
}

function historyRemove(id, value) {
  historySave(id, historyLoad(id).filter(v => v !== value));
}

/** Сохраняет последние использованные значения полей */
function saveLastValues(owner, repo, branch, maxCommits) {
  localStorage.setItem('gh_last', JSON.stringify({ owner, repo, branch, maxCommits }));
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

/** Восстанавливает поля из последнего сохранённого состояния */
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

/** Обновляет состояние кнопки «Очистить»: disabled если результатов нет */
function updateClearBtn() {
  document.getElementById('btn-clear').disabled =
    document.getElementById('results').hidden;
}

/** Очищает результаты поиска с анимацией карточек */
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

function openClearModal() {
  const overlay = document.getElementById('modal-clear');
  overlay.hidden = false;
  // Фокус на кнопку «Отмена» — безопаснее как действие по умолчанию
  document.getElementById('modal-cancel').focus();
}

async function closeClearModal() {
  const overlay = document.getElementById('modal-clear');
  overlay.classList.add('is-closing');
  await new Promise(r => setTimeout(r, 190));
  overlay.classList.remove('is-closing');
  overlay.hidden = true;
}

function ripple(e, btn) {
  const span = document.createElement('span');
  span.className = 'btn-ripple';
  const rect = btn.getBoundingClientRect();
  const size = Math.max(rect.width, rect.height);
  span.style.cssText = `width:${size}px;height:${size}px;left:${e.clientX - rect.left - size / 2}px;top:${e.clientY - rect.top - size / 2}px`;
  btn.appendChild(span);
  span.addEventListener('animationend', () => span.remove());
}

// Закрыть модал по Escape
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !document.getElementById('modal-clear').hidden) {
    closeClearModal();
  }
});

/** Инициализация: вешаем обработчики на поля формы */
function initHistory() {
  HISTORY_IDS.forEach(id => {
    const input = document.getElementById(id);
    if (!input) return;
    input.addEventListener('focus', () => renderDropdown(id));
    input.addEventListener('input', () => renderDropdown(id));
  });

  // Закрыть при клике вне поля
  document.addEventListener('click', e => {
    if (!e.target.closest('.field')) closeDropdowns();
  });

  // Закрыть по Escape
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

  // Убираем существующий дропдаун текущего поля
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
    removeBtn.addEventListener('mousedown', e => {
      e.stopPropagation(); // не даём всплыть до item (который ставит input.value и закрывает dropdown)
      e.preventDefault();  // сохраняем фокус на инпуте
    });
    removeBtn.addEventListener('click', e => {
      e.stopPropagation();
      historyRemove(id, value);
      renderDropdown(id);
    });

    item.append(text, removeBtn);

    // Выбор значения — mousedown чтобы сработало до blur на инпуте
    item.addEventListener('mousedown', e => {
      e.preventDefault(); // не уводим фокус с инпута
      input.value = value;
      closeDropdowns();
      updateClearBtn();
    });

    dropdown.appendChild(item);
  });

  field.appendChild(dropdown);
}

function closeDropdowns() {
  document.querySelectorAll('.field-dropdown').forEach(d => d.remove());
  document.querySelectorAll('.field.has-dropdown').forEach(f => f.classList.remove('has-dropdown'));
}

// ===========================================================
// Тост-уведомление
// ===========================================================

let toastEl = null;
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
