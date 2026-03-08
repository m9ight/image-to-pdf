# 📄 Image to PDF Bot

Telegram-бот с мини-приложением. Конвертирует изображения в PDF прямо в Telegram.

## Структура

```
├── bot.py            # Бот (aiogram 3 + aiohttp webhook)
├── webapp/
│   └── index.html    # Мини-приложение
├── requirements.txt
├── Procfile          # Для Railway
├── .env              # Конфиг (не в git)
└── .gitignore
```

## Деплой на Railway

### 1. Подготовка GitHub

```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/ВАШ_НИК/ВАШ_РЕПО.git
git push -u origin main
```

### 2. Railway

1. Зайди на [railway.app](https://railway.app) → **New Project → Deploy from GitHub**
2. Выбери репозиторий
3. Перейди в **Variables** и добавь:

| Переменная   | Значение                          |
|--------------|-----------------------------------|
| `BOT_TOKEN`  | Токен от @BotFather               |
| `WEBAPP_URL` | `https://xxx.up.railway.app` *(узнаешь после первого деплоя)* |
| `ADMIN_IDS`  | Твой Telegram user_id             |

4. После первого деплоя скопируй URL из **Settings → Domains**
5. Вставь его в `WEBAPP_URL` и нажми **Redeploy**

### 3. BotFather

```
/setdomain → @твой_бот → вставь домен railway (без https://)
```

### Переменные .env (локальный запуск)

```env
BOT_TOKEN=1234567890:AAF...
WEBAPP_URL=https://xxx.up.railway.app
ADMIN_IDS=123456789
```
