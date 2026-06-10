/**
 * render.js — построение DOM-карточек коммитов и вспомогательных блоков.
 * Зависит от: utils.js, ui.js
 */

// ===========================================================
// Главная функция рендеринга
// ===========================================================

/**
 * Отрисовывает список коммитов в DOM и сохраняет результат в localStorage.
 */
function renderResults(commits, { owner, repo, branch }, { scroll = true } = {}) {
  hideAllStates();

  if (!commits || commits.length === 0) {
    showError('Коммиты не найдены. Проверьте название репозитория и ветки.');
    return;
  }

  document.getElementById('results-header').innerHTML = buildResultsHeader(
    commits, owner, repo, branch,
  );

  const list = document.getElementById('commits-list');
  list.innerHTML = '';
  commits.forEach((commit, i) => list.appendChild(buildCommitCard(commit, i)));

  document.getElementById('results').hidden = false;
  updateClearBtn();

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
// Карточка коммита
// ===========================================================

/**
 * Строит DOM-элемент карточки для одного коммита.
 */
function buildCommitCard(commit, index = 0) {
  const card = document.createElement('div');
  card.className = 'commit-card';
  card.style.setProperty('--card-delay', `${Math.min(index * 55, 440)}ms`);

  const total  = commit.stats.additions + commit.stats.deletions;
  const addPct = total > 0 ? Math.round(commit.stats.additions / total * 100) : 50;

  card.innerHTML = `
    <div class="commit-card__accent" style="--add-pct: ${addPct}%"></div>

    <div class="commit-card__body">
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

      <div class="commit-message">${escHtml(commit.message.split('\n')[0])}</div>
      ${buildMessageBody(commit.message)}

      <div class="commit-stats">
        <span class="stat stat--add">+${commit.stats.additions}</span>
        <span class="stat stat--del">-${commit.stats.deletions}</span>
        ${buildStatsBar(commit.stats)}
        <span class="stat-files">${commit.files.length} файлов</span>
      </div>
    </div>

    ${commit.files.length    > 0 ? buildFilesSection(commit)           : ''}
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
        <span class="toggle-btn__arrow">▶</span>
        <span class="commit-body-label"> Описание</span>
      </button>
      <div class="commit-body" hidden>
        <div class="commit-body__inner">${escHtml(body)}</div>
      </div>
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
    added:    { icon: 'A', cls: 'added',    label: 'добавлен'     },
    modified: { icon: 'M', cls: 'modified', label: 'изменён'      },
    removed:  { icon: 'D', cls: 'removed',  label: 'удалён'       },
    renamed:  { icon: 'R', cls: 'renamed',  label: 'переименован' },
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
 *   +  → зелёная (добавление)
 *   -  → красная (удаление)
 *   @@ → синяя (заголовок блока)
 *   остальные → серые (контекст)
 */
function renderPatch(patch) {
  return patch.split('\n').map(line => {
    if (line.startsWith('@@'))      return `<span class="diff-line diff-line--hunk">${escHtml(line)}</span>`;
    if (line.startsWith('+'))       return `<span class="diff-line diff-line--add">${escHtml(line)}</span>`;
    if (line.startsWith('-'))       return `<span class="diff-line diff-line--del">${escHtml(line)}</span>`;
    return `<span class="diff-line diff-line--ctx">${escHtml(line)}</span>`;
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
// Аватар и SHA
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

  const colors = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
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

/** Копирует SHA-хэш в буфер обмена и показывает уведомление */
async function copySha(sha) {
  try {
    await navigator.clipboard.writeText(sha);
    showToast(`SHA скопирован: ${sha.substring(0, 7)}`);
  } catch {
    showToast('Не удалось скопировать');
  }
}
