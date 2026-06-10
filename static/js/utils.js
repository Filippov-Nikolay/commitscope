/**
 * utils.js — чистые утилиты без зависимостей от DOM.
 */

/**
 * Экранирует HTML-спецсимволы, чтобы данные из API не ломали разметку.
 * Защита от XSS: если имя автора содержит <script> — он не выполнится.
 */
function escHtml(str) {
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return String(str).replace(/[&<>"']/g, ch => map[ch]);
}

/**
 * Форматирует ISO-дату в читаемый вид.
 * "2024-01-15T10:00:00Z" → "15 янв. 2024 г."
 */
function formatDate(isoStr) {
  const d = new Date(isoStr);
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' });
}
