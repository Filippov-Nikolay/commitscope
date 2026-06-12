/**
 * api.js — взаимодействие с SSE-эндпоинтом /commits/stream.
 */

/** Обновляет текст под спиннером загрузки с пульс-анимацией */
function updateLoadingText(text) {
  const el = document.querySelector('#state-loading p');
  if (!el) return;
  el.classList.remove('count-update');
  void el.offsetWidth; // форс-рефлоу для перезапуска анимации
  el.textContent = text;
  el.classList.add('count-update');
}

/**
 * Подключается к /commits/stream и получает коммиты по одному.
 *
 * EventSource — встроенный в браузер механизм для получения потока событий.
 * Сервер держит соединение открытым и отправляет данные по мере готовности,
 * не дожидаясь завершения всей работы.
 *
 * @returns {Promise<Array>} список коммитов (разрешается когда всё загружено)
 */
function fetchCommits(owner, repo, branch, maxCommits, author) {
  const params = new URLSearchParams({ owner, repo, branch });
  if (maxCommits) params.set('max_commits', maxCommits);
  if (author)     params.set('author', author);

  return new Promise((resolve, reject) => {
    const source    = new EventSource(`/commits/stream?${params.toString()}`);
    const collected = [];

    source.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'total') {
        updateLoadingText(`Загружаем коммиты: 0 из ${data.total}`);
        if (data.total === 0) { source.close(); resolve([]); }

      } else if (data.type === 'progress') {
        collected.push(data.entry);
        updateLoadingText(`Загружаем коммиты: ${data.current} из ${data.total}`);

      } else if (data.type === 'done') {
        source.close();
        resolve(collected);

      } else if (data.type === 'error') {
        source.close();
        reject(new Error(data.message));
      }
    };

    source.onerror = () => {
      source.close();
      reject(new Error('Потеряно соединение с сервером'));
    };
  });
}
