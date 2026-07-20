<p align="center">
  <img src="https://raw.githubusercontent.com/dmpotekhin/travel-content-factory/main/docs/logo.png" alt="Travel Content Factory" width="120" onerror="this.style.display='none'">
</p>

<h1 align="center"> Travel Content Factory</h1>

<p align="center">
  <b>Локальная фабрика контента для путешественников</b><br>
  <sub>Архивируй фото и видео  •  Монтируй ролики с AI  •  Публикуй на TikTok, Reels, Facebook</sub>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/frontend-Vanilla_JS-F7DF1E?logo=javascript&logoColor=black" alt="Vanilla JS">
  <img src="https://img.shields.io/badge/AI-DeepSeek-4B32C3?logo=openai&logoColor=white" alt="DeepSeek">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

---

##   Что это

**Travel Content Factory** — это твой персональный видеопродакшн на ноутбуке.

Вернулся из путешествия с гигабайтами фото и видео? Загрузи всё в архив, и приложение само:
-   Извлечёт GPS-координаты и даты из EXIF
-   Сгруппирует медиа по странам и годам
-   Сгенерирует сценарий, хэштеги и текст поста через AI
-   Смонтирует ролик под TikTok, Reels или Facebook
-   Отдаст готовый `.mp4` на скачивание

Всё локально. Никаких облаков. Никаких подписок.

---

##   Возможности

###   Архив медиафайлов

|   |   |
|---|---|
| **Авто-скан папок** | Выбери папку с фото/видео — система рекурсивно обойдёт и извлечёт EXIF |
| **Метаданные** | Дата съёмки, GPS, длительность, разрешение, размер |
| **Фильтры** | Страна, год, тип (фото/видео), хэштеги |
| **Хранение** | SQLite, всё асинхронно, без тормозов |

### ✂️ Три режима монтажа

<p align="center">
  <table>
    <tr>
      <td align="center" width="33%">
        <h3>  Авто</h3>
        <sub>Задаёшь тему и длительность</sub><br><br>
        Система сама подбирает клипы по стране/году, нарезает FFmpeg и склеивает
      </td>
      <td align="center" width="33%">
        <h3>  Ручной</h3>
        <sub>Полный контроль</sub><br><br>
        Выбираешь клипы вручную, задаёшь порядок, длительность и переходы
      </td>
      <td align="center" width="33%">
        <h3>  По сценарию</h3>
        <sub>AI-драматургия</sub><br><br>
        Вставляешь текст → AI разбивает на сцены → код подбирает клипы по EXIF
      </td>
    </tr>
  </table>
</p>

###   Контент-завод

```
Ты: «Завтрак в Париже, рилс на 30 секунд»
   ↓
 AI:  Сценарий  +  Текст поста  +  #хэштеги
   ↓
 Ты:  [Copy] → вставляешь в TikTok/Instagram
```

-   Поле ввода темы + выбор платформы (TikTok / Reels / Facebook)
-   DeepSeek API возвращает готовый сценарий, цепляющий заголовок и подборку хэштегов
-   Копирование результата в один клик

###   Экспорт

-   FFmpeg собирает клипы в финальный `.mp4`
-     Наложение фоновой музыки (fade in/out, громкость, loop)
-     Нормализация громкости (loudnorm, -14 LUFS)
-   ✏️ AI-генерация и наложение текста на видео (drawtext)
-   Видео сохраняется в `exports/`
-   Кнопка **Download** в браузере

---

##   Стек

<p align="center">
  <table>
    <tr>
      <td align="center"> <b>Backend</b></td>
      <td>Python 3.11+  •  FastAPI  •  SQLAlchemy 2.0 (async)  •  aiosqlite</td>
    </tr>
    <tr>
      <td align="center"> <b>Frontend</b></td>
      <td>HTML5  •  CSS3 (темная тема)  •  Vanilla JS (0 зависимостей)</td>
    </tr>
    <tr>
      <td align="center"> <b>AI</b></td>
      <td>DeepSeek API (httpx)  •  Архитектура под замену на Ollama / llama.cpp</td>
    </tr>
    <tr>
      <td align="center"> <b>Медиа</b></td>
      <td>FFmpeg  •  exiftool (EXIF/GPS)</td>
    </tr>
    <tr>
      <td align="center"> <b>База</b></td>
      <td>SQLite (aiosqlite)  •  Одна строка для миграции на PostgreSQL</td>
    </tr>
  </table>
</p>

---

##   Быстрый старт

```bash
# 1. Клонируй репозиторий
git clone git@github.com:dmpotekhin/travel-content-factory.git
cd travel-content-factory

# 2. Установи внешние зависимости (macOS)
brew install ffmpeg exiftool

# 3. Создай конфиг и пропиши API-ключ DeepSeek
cp .env.example .env
#  → отредактируй DEEPSEEK_API_KEY=***

# 4. Запуск одной командой
chmod +x start.sh
./start.sh
```

**Открывай http://localhost:8000** — и ты в деле  

>   На MacBook Pro 2015 (i5, 16GB RAM) работает без GPU

---

## ⚙️ Конфигурация

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `DEEPSEEK_API_KEY` | Ключ DeepSeek API (  для AI-функций) | *обязательно* |
| `MEDIA_ROOT` | Куда сохраняются загруженные файлы | `./uploads` |
| `EXPORT_ROOT` | Куда рендерятся финальные видео | `./exports` |
| `DATABASE_URL` | Строка подключения к БД | *авто-вычисляется* |
| `HOST` | Адрес сервера | `127.0.0.1` |
| `PORT` | Порт | `8000` |
| `USE_VISION` | Vision-анализ кадров ( ) | `false` |

---

##   API

###   Медиа

| Метод | Путь | Что делает |
|---|---|---|
| `POST` | `/api/media/scan` | Сканировать папку и импортировать метаданные |
| `GET` | `/api/media/list` | Список с фильтрами (`media_type`, `country`, `year`, `page`) |
| `GET` | `/api/media/countries` | Все страны из архива |
| `GET` | `/api/media/years` | Все годы из архива |
| `GET` | `/api/media/{id}` | Детали медиафайла |
| `GET` | `/api/media/{id}/thumbnail` | Превьюшка (FFmpeg → JPEG) |
| `DELETE` | `/api/media/{id}` | Удалить медиафайл |

###   Проекты

| Метод | Путь | Что делает |
|---|---|---|
| `GET` | `/api/projects` | Список проектов |
| `POST` | `/api/projects` | Создать проект (auto / manual / script) |
| `GET` | `/api/projects/{id}` | Детали + список клипов |
| `PUT` | `/api/projects/{id}` | Обновить параметры |
| `DELETE` | `/api/projects/{id}` | Удалить |
| `POST` | `/api/projects/{id}/clips` | Задать клипы вручную |
| `POST` | `/api/projects/{id}/render` |   Смонтировать видео (body: `{"music_path":"...", "add_captions":true, "caption_text":"..."}`) |
| `GET` | `/api/projects/{id}/download` |   Скачать `.mp4` |

###   Музыка

| Метод | Путь | Что делает |
|---|---|---|
| `GET` | `/api/music/list` | Список треков с длительностью и размером |
| `POST` | `/api/music/upload` | Загрузить трек (multipart `file`) |
| `DELETE` | `/api/music/{filename}` | Удалить трек |

###   AI

| Метод | Путь | Что делает |
|---|---|---|
| `POST` | `/api/ai/generate` | Сгенерировать сценарий + пост + хэштеги |
| `POST` | `/api/ai/script-to-scenes` | Разбить текст на сцены |

###   Система

| Метод | Путь |
|---|---|
| `GET` | `/api/health` |

---

##   Структура

```
travel-content-factory/
│
├──   backend/
│   ├── main.py                   FastAPI: lifespan, CORS, mount static
│   ├── database.py               Async engine + session factory
│   ├── models.py                 MediaFile, Project, ProjectClip, Generation
│   ├── routers/
│   │   ├── media.py              /api/media/*
│   │   ├── projects.py           /api/projects/*  +  auto-match  +  render
│   │   ├── ai.py                 /api/ai/*  +  DeepSeek content generation
│   │   └── music.py              /api/music/*  +  upload/list/delete
│   └── services/
│       ├── scanner.py            exiftool → EXIF, GPS, дата, размер
│       ├── ffmpeg.py             trim, concat, overlay_audio, normalize_audio
│       └── deepseek.py           BaseAIClient → DeepSeekClient (retry, JSON mode)
│
├──   frontend/
│   ├── index.html                SPA: Archive  |  Projects  |  Factory
│   ├── css/style.css             Тёмная тема, responsive grid
│   └── js/app.js                 Fetch API, модалки, drag & drop
│
├──   uploads/                    Загруженные медиа
├──   exports/                    Готовые ролики
├──   music/                      Фоновая музыка (.mp3)
├──   data/                       SQLite travel_factory.db
│
├── requirements.txt
├── .env.example
├── start.sh
└── README.md
```

---

##   Архитектурные фишки

-   **BaseAIClient** — абстрактный AI-бэкенд. Сейчас DeepSeek, завтра Ollama — замена в 2 строки
-   **Без миграций** — таблицы создаются при старте (`Base.metadata.create_all`). Alembic добавится когда нужно
- ⚡ **Eager loading** — `selectinload` для связей, никаких `DetachedInstanceError`
-   **FFmpeg CPU-only** — `libx264`, `-preset fast`, без CUDA/VideoToolbox
-   **GPS опционален** — нет координат? Не ломается, просто фильтр по стране пустой

---

##   Roadmap

- [ ] PostgreSQL вместо SQLite (одна строка в `.env`)
- [ ] Celery / фоновая очередь рендера
- [ ] Ollama / llama.cpp вместо DeepSeek API
- [ ] Vision: AI-анализ содержимого кадров
- [ ] Reverse geocoding: GPS → страна / город
- [ ]   Аудиодорожки и музыкальная библиотека
- [ ]   Live-предпросмотр монтажа
- [ ] Экспорт в 9:16 / 1:1 / 16:9

---

<p align="center">
  <sub>Made with   for travellers • MIT License</sub>
</p>
