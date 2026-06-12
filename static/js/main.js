/**
 * main.js — точка входа приложения.
 *
 * Инициализирует обработчики событий после загрузки DOM и запускает
 * восстановление сохранённого состояния из localStorage.
 *
 * Порядок подключения скриптов в index.html:
 *   utils.js → api.js → ui.js → render.js → accordion.js → history.js → modal.js → main.js
 */

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('search-form').addEventListener('submit', handleSubmit);

  const btnClear = document.getElementById('btn-clear');
  btnClear.addEventListener('click', e => { ripple(e, btnClear); openClearModal(); });

  document.getElementById('modal-cancel').addEventListener('click', () => closeClearModal());
  document.getElementById('modal-confirm').addEventListener('click', async () => {
    await closeClearModal();
    await clearForm();
  });
  document.getElementById('modal-clear').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeClearModal();
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
 * Читает значения полей, запускает SSE-запрос и рендерит результаты.
 * event.preventDefault() отменяет стандартную перезагрузку страницы.
 */
async function handleSubmit(event) {
  event.preventDefault();
  closeDropdowns();

  const owner      = document.getElementById('owner').value.trim();
  const repo       = document.getElementById('repo').value.trim();
  const branch     = document.getElementById('branch').value.trim() || 'main';
  const author     = document.getElementById('author').value.trim();
  const maxCommits = document.getElementById('max-commits').value.trim();

  if (!owner || !repo) return;

  historyAdd('owner', owner);
  historyAdd('repo', repo);
  historyAdd('branch', branch);
  if (author)     historyAdd('author', author);
  if (maxCommits) historyAdd('max-commits', maxCommits);
  saveLastValues(owner, repo, branch, maxCommits, author);

  showLoading();
  setButtonLoading(true);

  try {
    const commits = await fetchCommits(owner, repo, branch, maxCommits || null, author || null);
    await dissolveLoading();
    renderResults(commits, { owner, repo, branch, author: author || null });
  } catch (err) {
    await dissolveLoading();
    showError(err.message);
  } finally {
    setButtonLoading(false);
  }
}
