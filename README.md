# Gold Signal Bot

בוט ששומע שתי קבוצות טלגרם, מריץ עסקאות XAUUSD ב-MT5 לפי התבנית, ורק אחרי הביצוע מתעד כל פוזיציה לאקסל — בנפרד לכל קבוצה.

## איך זה עובד

1. מגיע איתות בקבוצה.
2. **קודם** נפתחות פקודות מרקט — פוזיציה אחת לכל שורת `TP`, עם אותו `SL`.
3. **אחר כך** נרשמות כניסה, יציאה, ושייכות לקבוצה.
4. אחרי שנוגעים ב-TP3, שאר הסטופים עולים למחיר הכניסה.
5. ב-01 לחודש הבא נוצר קובץ חודשי סופי לכל קבוצה.

אין כניסה לאיתות שני כל עוד יש איתות פתוח. אחרי 5 שניות, פוזיציה בלי סטופ או בלי טייק מקבלת הגנה של 50 פיפס.

## תבנית האיתות

```
#XAUUSD SELL 4315-4318

TP 4312
TP 4309
TP 4305
TP 4300
TP 4295
TP 4285

SL 4327
```

אותו מבנה ל-BUY. הטווח בשורה הראשונה נשמר לדוח בלבד; הכניסה היא **מרקט**.

## GitHub ו-VPS (הרצה 24/7)

הבוט מיועד לרוץ על **VPS חלונות** ליד טרמינל MT5 פתוח ומחובר לחשבון גידור. אחרי `git clone`:

### חלונות (מומלץ ל-MT5)

```powershell
cd gold-signal-bot
powershell -ExecutionPolicy Bypass -File scripts\vps\setup.ps1
# ממלאים .env (טלגרם + MT5) ואת config.yaml:
#   dry_run: false
#   broker.type: mt5_native
.\.venv\Scripts\python.exe scripts\login_telegram.py
powershell -ExecutionPolicy Bypass -File scripts\vps\install-task.ps1
```

המשימה `GoldSignalBot` עולה בלוגין ומנסה שוב אחרי כשל. MT5 חייב להישאר מחובר באותו סשן.

`.env` ו-`config.yaml` לא עולים לגיט — רק `.env.example` ו-`config.example.yaml`.

### לינוקס

`scripts/vps/setup.sh` + `scripts/vps/gold-signal-bot.service` להאזנה ולדוחות. פקודות MT5 דרך `MetaTrader5` של Python **לא רצות בלינוקס**.

## התקנה מקומית

צריך Python 3.11+.

```bash
cd ~/gold-signal-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp config.example.yaml config.yaml
```

### טלגרם

1. ב-[my.telegram.org](https://my.telegram.org) → API development tools: מעתיקים `api_id` ו-`api_hash` ל-`.env`.
2. ממלאים גם `TELEGRAM_PHONE` (עם קידומת, למשל `+972...`).
3. מתחברים פעם אחת:

```bash
python scripts/login_telegram.py
python scripts/list_chats.py
```

4. מדביקים `chat_id` מספרי או `username` ציבורי (`@TechnicalPips6273`) ב-`config.yaml` תחת `telegram.groups`.
5. אופציונלי: `TELEGRAM_ADMIN_CHAT_ID` — הצ'אט שלך לקבלת דוחות ואקסל.

חשבון הטלגרם חייב להיות חבר בשתי הקבוצות.

### MT5

| מצב | מתי | מה לעשות |
|---|---|---|
| `dry_run` | בדיקות, ברירת מחדל | אין עסקאות אמיתיות, האקסל כן נכתב |
| `file_bridge` | מק / כל מחשב עם טרמינל MT5 | להדר `mt5/GoldSignalBridge.mq5`, לצרף לגרף XAUUSD, למלא `broker.common_files_dir` |
| `mt5_native` | Windows / VPS חלונות | `pip install MetaTrader5`, למלא login ב-`.env`, חשבון **גידור (hedging)** |

ב-Mac החבילה הרשמית `MetaTrader5` לא רצה. לכן במק משתמשים ב-`file_bridge`.

נתיב טיפוסי ל-Common/Files:

- מק: `~/Library/Application Support/MetaQuotes/Terminal/Common/Files`
- חלונות: `%APPDATA%\MetaQuotes\Terminal\Common\Files`

אחרי שהגשר חי, ב-`config.yaml`:

```yaml
dry_run: false
broker:
  type: file_bridge
  common_files_dir: "/path/to/MetaQuotes/Terminal/Common/Files"
```

וב-`.env`: `DRY_RUN=false`.

חשוב: האסטרטגיה פותחת כמה פוזיציות על אותו סימול — רק חשבון hedging.

## הרצה

```bash
python main.py
```

לוגים: `logs/bot.log`. אקסל חי: `reports/<שם_קבוצה>/YYYY-MM.xlsx`. ב-01 לחודש: קובץ `YYYY-MM_final.xlsx` נשלח לאדמין אם הוגדר.

## אקסל

לכל קבוצה קובץ נפרד. בכל שורת TP:

- מתי האיתות נקלט
- מתי נכנסה הפוזיציה (תאריך, שעה, מחיר)
- מספר ה-TP ומחירו
- מתי מומשה / יצאה
- סיבת יציאה, רווח, פיפס

גיליון **סטטיסטיקה**: אחוז האיתותים שהגיעו לפחות עד TP1…TP6, והתפלגות ה-TP המקסימלי שנלקח.

## הגדרות חשובות

- `lot` לכל קבוצה ב-`config.yaml` — גודל לכל פוזיציית TP (6 טייקים = 6×לוט).
- `pip_size: 0.1` לזהב — 50 פיפס = 5.0 במחיר.
- `max_concurrent_signals: 1` — נעילה גלובלית לשתי הקבוצות.

בדיקות:

```bash
python -m pytest
```

סימולציה בלי טלגרם:

```bash
python scripts/replay_sample.py
```
