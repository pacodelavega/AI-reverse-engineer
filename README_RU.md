# AI-Reverse-Engineer: Руководство по реверс-инжинирингу приложений на видеокарте с 8 ГБ VRAM

[![English Version](https://img.shields.io/badge/Language-English-blue.svg)](README.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Hardware: 8GB VRAM](https://img.shields.io/badge/Hardware-8GB%20VRAM%20Compatible-orange.svg)](https://www.nvidia.com)

Практическое руководство и архитектурный шаблон для анализа, аудита безопасности и «чистой» пересборки (clean-room rewrite) сложных мобильных приложений с использованием обычной потребительской видеокарты на **8 ГБ VRAM** (RTX 3060 / 4060 / 5060), статического триажа без расхода токенов и многоуровневой оркестрации нейросетей через [cli-subagent](https://github.com/pacodelavega/cli-subagent).

---

## Проблема: Ловушка контекстных окон и облачных токенов

Современные корпоративные мобильные приложения содержат десятки мегабайт скомпилированного Dalvik-байткода (`classes.dex`), тысячи обфусцированных классов и более 100 000 строк в пуле идентификаторов.

- **Наивный подход:** Загрузка декомпилированного Smali-кода или десятков Java/Kotlin-файлов целиком в контекст облачных моделей (Claude 3.5 Sonnet, GPT-4o, Codex) мгновенно сжигает контекстное окно, упирается в лимиты запросов (`429`), стоит огромных денег на API и регулярно наталкивается на морализаторские отказы нейросетей («as an AI, I cannot help analyze security controls...»).
- **Чисто локальный подход:** Запуск тяжелых моделей на 70B+ параметров требует от 48 до 80+ ГБ видеопамяти (многокарточные рабочие станции или кластеры серверов), что недоступно на обычном рабочем ПК или ноутбуке.

### Решение для 8 ГБ VRAM: Гибридная модель

```
┌────────────────────────────────────────────────────────────────────────┐
│                   Исследуемое приложение (APK / DEX)                   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  Уровень 0: Статический парсинг с 0 токенов (Python / Регулярки / DEX) │
│  - Прямой обход String ID таблицы DEX, аннотаций Retrofit, Moshi DTO   │
│  - Сжатие 100 000+ сырых строк до 30 доменных символов за < 500 мс     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  Уровень 1: Локальный агент на 8 ГБ VRAM (Qwen 2.5/3.5 9B Q4_K_M)      │
│  - Рантайм: LM Studio / vLLM / Ollama (OpenAI-совместимый API /v1)     │
│  - SecOps-анализ без цензуры, триаж AST-байткода, сжатие логов         │
│  - Генерация строгих DTO-моделей без затрат облачных токенов           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  Уровень 2: Роутер субагентов (/cli-subagent)                          │
│  - Балансировка пула, изоляция контекстов, отказоустойчивый failover   │
│  - Передача чистых схем весом всего 2 КБ архитектору верхнего уровня   │
│    (Codex 6.1 Sol / Claude Opus / Gemini Flash) для финального синтеза │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Реальный кейс: Реверс-инжиниринг домофона монополиста

В качестве примера рассмотрен разбор приложения «Ростелеком Ключ» (`ru.rt.key`): жильцы многоквартирного дома жаловались на то, что домофон блокирует вход в собственный подъезд при включённом VPN, а при малейшем сбое связи приложение выбрасывает необработанные исключения вместо показа аварийного кода, принудительно навязывая абонентскую плату и рекламу.

### 1. Двухконтурная блокировка VPN и Прокси
- **Клиентский детектор:** Обнаружен в классе `ru.rt.key.app.infrastructure.access.b` (`AppAppAccessManagerImpl.kt` / `VpnAccessChecker`):
  - Вызывает [`NetworkCapabilities.hasTransport(TRANSPORT_VPN)`](https://developer.android.com/reference/android/net/NetworkCapabilities#TRANSPORT_VPN).
  - Сканирует сетевые интерфейсы через [`LinkProperties.getInterfaceName()`](https://developer.android.com/reference/android/net/LinkProperties#getInterfaceName()) на наличие сигнатур (`tun0`, `ppp0`, `p2p0`).
  - Создает `AppAccessDeniedReason$Vpn` и блокирует экран через `NoAppAccessViewModel` (событие `show_blockingscreennet_vpn`).
- **Серверный WAF и Геоблокировка:** Эндпоинты `keyapis.key.rt.ru` и `vc.key.rt.ru` отслеживают IP-адреса клиентов и при запросах с зарубежных подсетей возвращают код `HTTP 477` (`show_blockingscreennet_waf_477`).

### 2. Сбои открытия дверей и баг аварийного кода
- **100% зависимость от облака:** Открытие двери управляется `OpenDoorInteractor` через REST `POST v2/app/devices/{id}/open` и SIP-шлюзы ([pjsip / SipService](https://github.com/gotev/android-sipservice)).
- **Фатальный сбой фоллбэка:** Аварийные коды загружаются в локальное хранилище `PersistentStorage` через `UpdateEmergencyCodesUseCase`. Однако при сбое сети обработчик ошибки (`Lqg5`) пытается повторно выполнить сетевой запрос `GetDeviceInteractor(deviceId)`. На слабом сигнале у двери второй запрос тоже падает с ошибкой, цепочка прерывается (`Lkg5`), и до чтения локального кэша приложение просто не доходит, оставляя человека на улице.

### 3. Реклама и навязанные услуги
- Вшитые модули баннеров: `BannersRepositoryImpl`, `CanShowNasledieBannerUseCase`, `CanShowDomaAiUseCase`.
- Трекеры и рекламные SDK: [Yandex Metrica](https://appmetrica.yandex.com/), [Google Mobile Ads](https://developers.google.com/admob/android/quick-start), Sentry.
- Платные пейволлы после окончания пробного периода (`Banner$SubscriptionEndedAfterPromoPeriodBanner`).

---

## Пошаговое руководство: Исследование на 8 ГБ VRAM

### Шаг 1: Извлечение строк и символов без токенов (0 Token Cost)
Не декомпилируйте гигабайты Smali-файлов, если вам нужны только доменные сущности. Скрипт на Python читает String ID таблицу DEX напрямую за `< 100 мс`:

```python
import struct, glob

def get_dex_strings(dex_path):
    strings = []
    with open(dex_path, 'rb') as f:
        data = f.read()
    string_ids_size, string_ids_off = struct.unpack('<II', data[56:64])
    for i in range(string_ids_size):
        off = struct.unpack('<I', data[string_ids_off + i*4 : string_ids_off + (i+1)*4])[0]
        # Чтение длины строки в формате ULEB128
        length, shift, idx = 0, 0, off
        while True:
            b = data[idx]; idx += 1; length |= (b & 0x7f) << shift
            if (b & 0x80) == 0: break
            shift += 7
        strings.append(data[idx:idx+length].decode('utf-8', errors='ignore'))
    return strings
```

### Шаг 2: Извлечение точных схем JSON из адаптеров Moshi
Современные Android-приложения на базе [Square Moshi](https://github.com/square/moshi) компилируют список ключей в вызовы `JsonReader.Options.of(...)` внутри классов `*JsonAdapter.kt`. Парсинг этих констант позволяет восстановить 100% оригинальных имен полей API без доступа к исходникам.

### Шаг 3: Настройка локальной модели на 8 ГБ видеопамяти
Запустите компактную модель с поддержкой кода через [LM Studio](https://lmstudio.ai/) или [vLLM](https://github.com/vllm-project/vllm):
- **Рекомендуемые модели:** `Qwen2.5-Coder-7B-Instruct`, `Qwen/Qwen2.5-7B-Instruct` или `qwen3.5-9b-uncensored` (в квантовании GGUF Q4_K_M или Q8_0).
- **Расход VRAM:**
  - Веса модели: ~5.5 ГБ
  - Квантованный KV-кэш (контекст 8K-16K при квантовании FP8/Q8): ~1.8 ГБ
  - Итого: **менее 7.5 ГБ VRAM** (идеально помещается в память видеокарт RTX 3060 8GB / RTX 4060 8GB / RTX 5060 8GB).
- **Задача локального агента:** Обработка дампов байткода, сжатие информации и генерация чистых Kotlin DTO без цензурных блокировок.

### Шаг 4: Многоагентная маршрутизация через `/cli-subagent`
Используйте маршрутизатор [cli-subagent](https://github.com/pacodelavega/cli-subagent) для автоматического разделения задач между локальным и облачными пулами:

```bash
# Локальный агент извлекает и сжимает структуры в DTO
python scripts/cli.py --provider custom --model qwen3.5-9b --tier fast -p "Сжать схемы Moshi в Kotlin DTO" --run

# Архитектор верхнего уровня (Codex 6.1 Sol / Claude Sonnet) проектирует чистое ядро
python scripts/cli.py --provider codex --model gpt-6.1-sol --effort xhigh -p "Спроектировать сетевое ядро clean-client" --run
```

---

## Архитектура чистого клиента («Ключ-Пульт»)

Чистый клиент решает все архитектурные дефекты официального приложения:

1. **Прямая привязка сокетов в обход VPN ([`PhysicalNetworkSelector.kt`](https://developer.android.com/reference/android/net/ConnectivityManager)):**
   Опрашивает `ConnectivityManager.getAllNetworks()`, находит физическую сеть (`TRANSPORT_CELLULAR` или `TRANSPORT_WIFI`), у которой **нет** флага `TRANSPORT_VPN`, и привязывает сокеты `OkHttpClient` напрямую к физическому интерфейсу. Запросы к API домофона идут напрямую через сотового оператора, даже если на телефоне работает глобальный VPN.
2. **Мгновенный оффлайн-сейф кодов за 0 мс ([`OfflineCodeVault.kt`](https://developer.android.com/reference/androidx/security/crypto/EncryptedSharedPreferences)):**
   Аварийные и суточные коды сохраняются в оперативной памяти и зашифрованном локальном хранилище. При сбое сети или таймауте контроллер **не совершает повторных сетевых запросов**, а мгновенно отдает жильцу кэшированный код.
3. **Аппаратная GSM-переадресация без интернета:**
   Интеграция с эндпоинтом `v2/app/phones-redirect` направляет звонки с домофона на сотовый телефон жильца через обычную голосовую связь: дверь открывается нажатием тональной клавиши (DTMF) без необходимости в интернете, SIP или пуш-уведомлениях.
4. **Интерфейс в стиле Physical Metaphor:**
   Отказ от веб-карточек и рекламных экранов в пользу аппаратного пульта: высококонтрастное табло кодов, тактильные клавиши, виджет на рабочем столе, плитка в шторке Android (Quick Settings Tile) и минималистичный циферблат для часов Wear OS (40 мм).

---

## Полезные ссылки и инструменты

- **Инструменты анализа байткода:**
  - [JADX Decompiler](https://github.com/skylot/jadx) — декомпилятор DEX в читаемый код Java.
  - [Apktool](https://apktool.org/) — разборка и сборка ресурсов APK.
  - [Android SDK Platform Tools (ADB)](https://developer.android.com/tools/adb) — отладка и сбор логов.
- **Локальные рантаймы LLM (для 8 ГБ VRAM):**
  - [LM Studio](https://lmstudio.ai/) — удобный локальный сервер с OpenAI-совместимым API (`localhost:1234/v1`).
  - [vLLM](https://github.com/vllm-project/vllm) — высокопроизводительный движок инференса.
  - [Ollama](https://ollama.ai/) — минималистичный инструмент для запуска квантованных моделей.
- **Оркестрация агентов:**
  - [cli-subagent](https://github.com/pacodelavega/cli-subagent) — маршрутизатор субагентов для локальных и облачных CLI.
- **Сетевой стек Android:**
  - [Square OkHttp](https://square.github.io/okhttp/) — HTTP-клиент с поддержкой кастомных SocketFactory.
  - [Square Moshi](https://github.com/square/moshi) — парсинг JSON с генерацией адаптеров.
  - [AndroidX Security Crypto](https://developer.android.com/reference/androidx/security/crypto/EncryptedSharedPreferences) — шифрованное хранение данных.

---

## Лицензия

Документация и вспомогательные скрипты распространяются под лицензией [MIT](LICENSE).
