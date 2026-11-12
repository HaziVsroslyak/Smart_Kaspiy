# Docker

Конфигурация запуска backend. Требуется Docker с Compose v2 и поддержкой Linux-контейнеров. FrontEnd пока не реализован и отдельного сервиса не имеет.

Из корня репозитория:

```shell
docker compose -f Docker/compose.yaml config
docker compose -f Docker/compose.yaml up --build -d
docker compose -f Docker/compose.yaml ps
docker compose -f Docker/compose.yaml logs -f backend
docker compose -f Docker/compose.yaml down
```

API доступен по адресу `http://127.0.0.1:8000`, Swagger UI — `/docs`. Порт публикуется только на localhost. После обучения модели и старта API healthcheck проверяет `/openapi.json`.

Сборка использует корень репозитория как контекст. `Dockerfile.dockerignore` разрешает отправлять в сборку только backend, исключая секреты, кэши, тесты и генерируемые данные. Образ работает с Python 3.11 от непривилегированного пользователя и запускает один worker, поскольку граф и модель хранятся в памяти.

Образ содержит копию исходников. После изменения файлов пересоберите его командой `up --build -d`. Volumes и внешние базы данных не требуются. При перезапуске модель снова обучается на синтетических данных, а граф создается заново.

Отдельная сборка без Compose из корня:

```shell
docker build -f Docker/Dockerfile -t smart-caspian-backend .
docker run --rm -p 127.0.0.1:8000:8000 smart-caspian-backend
```
