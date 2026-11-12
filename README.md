# Smart Caspian Transit

MVP предиктивного цифрового двойника мультимодального хаба МТК «Север–Юг».

## Структура проекта

```text
Project/
├── Backend/
│   ├── main.py                 # FastAPI: маршруты, таможня, JIT
│   ├── ml_predictor.py         # Синтетические данные и Random Forest
│   ├── ml_pipeline.py          # CaspianPredictor: порты, ветер, волны, заторы и лед
│   ├── routing_engine.py       # NetworkX и алгоритм Дейкстры
│   ├── smart_customs.py        # Проверка SHA-256 груза
│   ├── smart_customs_and_jit.py # Общий интерфейс таможни и JIT для API
│   ├── jit_optimizer.py        # JIT Arrival, топливо и CO2
│   ├── requirements.txt        # Зависимости приложения
│   ├── requirements-dev.txt    # Зависимости тестов
│   ├── README.md               # Контракты, примеры и целевая архитектура
│   ├── .env.example            # Заготовка настроек
│   ├── pyproject.toml          # Заготовка конфигурации проекта
│   ├── app/                    # Сохраненный каркас будущей модульной архитектуры
│   ├── tests/
│   │   ├── unit/
│   │   └── integration/
│   ├── scripts/                # Заготовки служебных скриптов
│   ├── data/
│   │   ├── raw/
│   │   └── processed/
│   └── artifacts/
├── FrontEnd/
│   └── README.md               # Место для будущего интерфейса
├── Docker/
│   ├── Dockerfile              # Образ API на Python 3.11
│   ├── Dockerfile.dockerignore # Исключения контекста сборки
│   ├── compose.yaml            # Локальный запуск backend
│   └── README.md               # Команды Docker
├── .gitignore
└── README.md
```

Рабочая точка входа — `Backend/main.py`. Файлы внутри `Backend/app/` пока остаются заготовками. В `FrontEnd` реализована React/TypeScript оболочка. Из `FrontEnd` выполните `pnpm install` и `pnpm dev`, откройте http://127.0.0.1:5173 .

Контракты для команды: [Backend/INTEGRATION.md](Backend/INTEGRATION.md), [OpenAPI JSON](Backend/contracts/openapi.json), [схема обучающих записей](Backend/contracts/training_record.json).

## Локальный запуск (PowerShell)

Команды выполняются из корня репозитория. Требуется Python 3.10+; проект проверяется на Python 3.11. Если `.venv` уже существует, используйте его без пересоздания. Окружение хранится в корне, игнорируется Git и не переносится вместе с исходным кодом.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r Backend/requirements.txt
Set-Location Backend
..\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Для Linux/macOS после установки зависимостей: `cd Backend`, затем `../.venv/bin/python -m uvicorn main:app --reload`.

## Тесты (из корня репозитория)

```powershell
.\.venv\Scripts\python.exe -m pip install -r Backend/requirements-dev.txt
Set-Location Backend
..\.venv\Scripts\python.exe -m unittest discover -s tests/unit -v
..\.venv\Scripts\python.exe -m unittest discover -s tests/integration -v
```

## Docker (из корня репозитория)

```powershell
docker compose -f Docker/compose.yaml up --build -d
docker compose -f Docker/compose.yaml logs -f backend
docker compose -f Docker/compose.yaml down
```

Подробности: [Backend/README.md](Backend/README.md), [Docker/README.md](Docker/README.md), [FrontEnd/README.md](FrontEnd/README.md).

## Реализованный API

| Метод | Путь | Назначение |
| --- | --- | --- |
| POST | `/api/v1/route/calculate` | Быстрейший маршрут с прогнозом задержек |
| POST | `/api/v1/customs/clear` | Имитация предварительной таможенной проверки |
| POST | `/api/v1/optimize/jit` | Рекомендация скорости и расчет экономии топлива/CO2 |

Модели обучаются на синтетических данных при старте. Сеть и коэффициенты ESG демонстрационные. Погодный прогноз получаем через OpenWeather (серверная переменная `OPENWEATHER_API_KEY`), расписания поездов/автомобилей и реальная блокчейн-интеграция пока не реализованы. Детали новых погодных/ML-эндпоинтов — в INTEGRATION.md.
