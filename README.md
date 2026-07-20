# Travel Content Factory

Локальный веб-инструмент для управления медиаархивом путешествий и создания контента для TikTok, Instagram Reels и Facebook. Загружайте фото и видео, извлекайте геоданные, монтируйте ролики с AI-сценариями — всё на вашем компьютере.

## Возможности

###   Архив медиафайлов
- Drag & drop папок или выбор в браузере
- Извлечение метаданных через exiftool: дата съёмки, GPS-координаты, длительность, разрешение
- Сетка с фильтрами: страна, год, тип (фото/видео), хэштеги
- Хранение в SQLite, всё асинхронно

### ✂️ Три режима монтажа
| Режим | Как работает |
|-------|-------------|
| **Авто** | Задаёте тему/страну/длительность → система подбирает клипы по метаданным и склеивает через FFmpeg |
| **Ручной** | Выбираете клипы вручную, задаёте порядок и длительность |
| **По сценарию** | Вставляете текст → AI (DeepSeek) разбивает на сцены → код подбирает клипы по EXIF |

###   Контент-завод
- Поле ввода темы + выбор платформы (TikTok / Reels / Facebook)
- Запрос к DeepSeek API → сценарий, текст поста, хэштеги
- Копирование в один клик

###   Экспорт
- Рендер финального видео в папку `exports/`
- Кнопка скачать в браузере

## Скриншоты

*(добавьте свои скриншоты в `docs/screenshots/`)*

## Стек

| Слой | Технологии |
|------|-----------|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy (async), aiosqlite |
| **Frontend** | HTML5 + CSS3 + Vanilla JS (без фреймворков) |
| **AI** | DeepSeek API через httpx (архитектура позволяет заменить на локальную LLM) |
| **Медиа** | FFmpeg (subprocess), exiftool (EXIF/GPS) |
| **База** | SQLite (aiosqlite); готова замена на PostgreSQL одной строкой |

## Требования

- macOS / Linux (на MacBook Pro 2015 i5 16GB работает)
- Python 3.11+
- FFmpeg: `brew install ffmpeg`
- exiftool: `brew install exiftool`
- DeepSeek API ключ (для AI-функций)

## Быстрый старт

```bash
git clone git@github.com:dmpotekhin/travel-content-factory.git
cd travel-content-factory

# Установите внешние зависимости
brew install ffmpeg exiftool

# Создайте .env и пропишите API-ключ
cp .env.example .env
# отредактируйте DEEPSEEK_API_KEY=***

# Запуск
chmod +x start.sh
./start.sh
```

Приложение откроется на **http://localhost:8000**

## Конфигурация (.env)

```env
# DeepSeek API (обязательно для AI-функций)
DEEPSEEK_API_KEY=*** Paths
MEDIA_ROOT=./uploads        # куда сохраняются загруженные файлы
EXPORT_ROOT=./exports       # куда рендерятся финальные видео
DATABASE_URL=sqlite+aiosqlite:///./data/travel_factory.db  # (опционально)

# Сервер
HOST=127.0.0.1
PORT=8000

# Бета-функции
USE_VISION=false            # анализ контента через vision-модель (пока не активно)
```

Если `DATABASE_URL` не задан, путь вычисляется автоматически относительно корня проекта.

## API

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/api/health` | Проверка работоспособности |
| `POST` | `/api/media/scan` | Сканировать папку (body: `{"path": "..."}`) |
| `GET` | `/api/media/list` | Список медиа (query: `media_type`, `country`, `year`, `page`) |
| `GET` | `/api/media/countries` | Список стран из архива |
| `GET` | `/api/media/years` | Список годов из архива |
| `GET` | `/api/media/{id}/thumbnail` | Превью (JPEG, генерируется FFmpeg) |
| `DELETE` | `/api/media/{id}` | Удалить медиафайл |
| `GET` | `/api/projects` | Список проектов |
| `POST` | `/api/projects` | Создать проект |
| `GET` | `/api/projects/{id}` | Детали проекта |
| `PUT` | `/api/projects/{id}` | Обновить проект |
| `DELETE` | `/api/projects/{id}` | Удалить проект |
| `POST` | `/api/projects/{id}/clips` | Задать список клипов |
| `POST` | `/api/projects/{id}/render` | Рендер финального видео |
| `GET` | `/api/projects/{id}/download` | Скачать видео |
| `POST` | `/api/ai/generate` | Генерация сценария (body: `{"topic":"...","platform":"tiktok"}`) |
| `POST` | `/api/ai/script-to-scenes` | Разбивка сценария на сцены |

## Структура проекта

```
travel-content-factory/
├── backend/
│   ├── main.py              # FastAPI: lifespan, CORS, статика
│   ├── database.py          # Async engine + session factory
│   ├── models.py            # MediaFile, Project, ProjectClip, Generation
│   ├── routers/
│   │   ├── media.py         # /api/media/*
│   │   ├── projects.py      # /api/projects/*
│   │   └── ai.py            # /api/ai/*
│   └── services/
│       ├── scanner.py       # Обход папок, exiftool, EXIF/GPS
│       ├── ffmpeg.py        # trim, concat, thumbnail, frame extraction
│       └── deepseek.py      # DeepSeek API (BaseAIClient → заменяемый)
├── frontend/
│   ├── index.html           # SPA: Archive / Projects / Factory
│   ├── css/style.css        # Тёмная тема
│   └── js/app.js            # Vanilla JS: вся логика
├── uploads/                 # Загруженные медиафайлы
├── exports/                 # Срендеренные видео
├── data/                    # SQLite база
├── requirements.txt
├── .env.example
└── start.sh
```

## Архитектурные решения

- **BaseAIClient** — абстрактный класс для AI-бэкенда. Сейчас `DeepSeekClient`, легко заменить на локальную LLM (Ollama, llama.cpp)
- **Без ORM-миграций** — таблицы создаются автоматически при старте (`Base.metadata.create_all`). Для продакшена добавить Alembic
- **Eager loading** — связи `Project.clips` загружаются через `selectinload` для избежания `DetachedInstanceError`
- **FFmpeg без GPU** — все флаги только CPU: `libx264`, `-preset fast`, без `-hwaccel`
- **GPS без гарантии** — если EXIF без координат, поля `latitude/longitude/country/city` остаются `NULL`, это не ломает фильтры

## Дорожная карта

- [ ] Замена SQLite → PostgreSQL (одна строка в .env)
- [ ] Celery для фонового рендера
- [ ] Локальная LLM вместо DeepSeek API (Ollama)
- [ ] Vision-анализ контента кадров
- [ ] Reverse geocoding (GPS → страна/город)
- [ ] Музыкальная библиотека и наложение аудио
- [ ] Предпросмотр монтажа в браузере
- [ ] Экспорт в несколько форматов (вертикальный/горизонтальный)

## Лицензия

MIT
