# Smart Caspian UI

React + TypeScript + Vite: маршрут, таможня, JIT/ESG и погода.

Запуск из FrontEnd: `pnpm install`, затем `pnpm dev`. Адрес: http://127.0.0.1:5173 . Backend: http://127.0.0.1:8000 . Другой адрес API задается через VITE_API_BASE_URL в .env.local (образец .env.example).

`src/api/client.ts`: calculateRoute, clearCustoms, optimizeJIT и интерфейсы запросов/ответов. Сеть, тайм-ауты и 5xx возвращают фиксированные mock-ответы с _meta.mode=mock. Они не рассчитаны по введенным параметрам. Таможенный mock никогда не выдает разрешение. Ошибки 4xx отображаются как ошибки. Для погоды выдуманный fallback не используется.

Проверка: `pnpm test`, `pnpm build`. Версии зафиксированы в pnpm-lock.yaml.

OPENWEATHER_API_KEY задается только на сервере, никогда в VITE-переменных.

Если в Windows зависимости уже установлены, но `pnpm` отсутствует в PATH, из `FrontEnd` выполните `./start-dev.ps1`. Скрипт запускает локальный Vite через установленный Node.js; на рабочей станции Codex также поддерживается резервный путь к его Node.js. Системный PATH и ExecutionPolicy не изменяются. Если PowerShell запрещает запуск скриптов, Vite можно вызвать напрямую: `node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort` (при наличии Node.js в PATH).

Контракты: [INTEGRATION.md](../Backend/INTEGRATION.md) и [OpenAPI](../Backend/contracts/openapi.json).
