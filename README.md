# Bankers Alliance — GA MCQ Practice (members edition)

Member login (ID + password from a Google Sheet) → Month → Topic → Subtopic → Minor topic →
**quiz** with instant solutions, scorecard & analytics, quiz history, saved questions, PDF export and an admin monitor panel.

**First time? Follow [SETUP.md](SETUP.md)** (Google Sheet + free Apps Script, ~10 minutes).

```
├── index.html                       the whole website (paste your Apps Script URL into API_URL)
├── SETUP.md                         step-by-step: Google Sheet backend, members, locking the bank
├── apps-script/Code.gs              the backend — pasted into the Google Sheet (not served on the site)
├── data/
│   ├── raw/                         ★ YOUR MCQ TEXT FILES  (2026-08.txt, 2026-09.txt …)
│   ├── tag_map.json                 category name → place in the topic tree
│   ├── topics.json                  master GA structure (Main > Sub > Minor + weightage)
│   └── questions.json | questions.enc.json    generated automatically (enc = locked)
├── scripts/mcq_to_json.py           converts data/raw/*.txt → the question bank
├── .github/workflows/build-questions.yml     runs the converter on GitHub
└── vercel.json                      hides raw files / scripts on the live site
```

## 1. Writing questions

File name = month (`2026-08.txt`, `august.txt`). Blank lines between questions are optional.

```
QUESTION: Who is the President of the 81st UNGA?
A. Annalena Baerbock
B. Mirza Fakhrul Alamgir
C. Khalilur Rahman
D. Peter Pellegrini
E. Hakainde Hichilema
ANSWER: C
SOLUTION: Bangladesh's Khalilur Rahman presides over the 81st session.
TAG: United Nations, International news/Oneliner

TEXT: <u>Consider the following statements:</u>
&#8203;
I. First statement
II. Second statement
&#8203;
Which of the statements given above is/are correct?
QUESTION: STATEMENT BASED QUESTION
A. Only I
B. Only II
C. Both I and II
D. Neither
ANSWER: C
SOLUTION: Both are correct because …
TAG: RBI, Banking news, National news/Statement Based
```

### The TAG line:  `categories / question types`

`TAG: RBI, Banking news, National news/Data Based, Statement Based`

* **Left of the `/`**: one or more **categories** (comma-separated). The question appears under **every** category listed.
* **Right of the `/`**: one or more **question types**: `Oneliner`, `Data Based`, `Statement Based`, `Match the Column`.
* The `/ type` part is optional. If you leave it out, the type is **detected automatically** (a `<table>` gives Data Based, numbered statements give Statement Based, "match the following / Column I" gives Match the Column, otherwise Oneliner).
* A `/` inside a category name (e.g. `Repo Rate / Reverse Repo`) is fine.
* Categories are placed in the topic tree through **`data/tag_map.json`** (explicit) or automatic name-matching; unknown ones go to *Other / Unsorted* with a warning telling you what to add.
* Other rules: keywords UPPERCASE · `TEXT:` comes **before** `QUESTION:` · 2–6 options · HTML (`<b> <u> <mark> <table>` …) is allowed · `&#8203;` lines become paragraph gaps.
* Optional lines above a question: `MONTH:` `MAIN:` `SUB:` `MINOR:` `TYPE:`.

Push to GitHub and the Action rebuilds the bank. Invalid questions are **skipped and counted** (shown to the admin per month, with file/line/reason, and as yellow warnings in the Action log).

## 2. What members get

* **Login** per member (separate ID/password). Refreshing the page always asks for login again, and then the quiz, screen and timers **resume exactly where they were**.
* **Set-up panel:** *Question type* dropdown (Default-Random, Oneliner, Data Based, Statement Based, Match the Column) and *Number of questions* dropdown (Default = 5, 10, 20, 30, 50, Unlimited = everything in that category; if fewer exist you get what exists). Plus Practice/Test mode, shuffle, ¼ negative marking.
* **Quiz:** formatted text/tables, solution embedded **below the options** after every attempt (right or wrong), **Skip →** for unattempted, ★ save, 🚩 report a wrong question, palette, **full-screen** (⛶ / key `F`), whole-quiz stopwatch **and** time recorded per question, keyboard shortcuts (`A–E`/`1–5`, `←/→`, `S`).
* **Result:** scorecard with ¼ negative marking, right / wrong / skipped, accuracy, attempt rate, penalty, total/avg/fastest/slowest time, time-per-question chart, breakdown by topic / type / minor topic, written insights, comparison with your previous attempt, and **below it every question with its solution** (filter by wrong/right/skipped).
* **Quiz History:** name, date & time, right, wrong, score, percentage (tap to reopen the full scorecard; CSV download).
* **Dashboard:** KPIs, score trend, focus areas, accuracy by topic/type, day streak, change password. **Saved questions** page. **My Mistakes** practice set.
* **PDF** of any category (question paper, or with answers & solutions): A4, tilted watermark, header *"Target MCQs of …"*, footer *"Created by BankersAlliance and Victory Banker"*.
* Data lives in the browser (separate per member) and is mirrored to the Sheet, so history follows the member to a new device.

## 3. Admin panel (admin login only)

Overview · Members · **Quiz log of everyone** (with login ID, date & time; open any attempt) · **Content health: valid vs invalid questions per month** · member-reported questions · hardest/slowest questions. Details in SETUP.md.

## 4. Settings (top of the script in `index.html`)

`API_URL` · `BRAND` · `YEAR` · `NEG_MARK` · `DEFAULT_COUNT` · `COUNT_CHOICES` · `PDF_HEADER_PREFIX` · `PDF_FOOTER_TEXT` · `PDF_WATERMARK`.
Backend knobs (top of `Code.gs`): `TOKEN_HOURS`, `MAX_FAILS`, `LOCK_MINUTES`.

## 5. Ideas that would upgrade the tool further

**Easy wins:** daily 10-question "Quiz of the Day" · personal notes on saved questions · images/charts in explanations · dark mode · font-size control · installable app (PWA) with an offline question bank · "revise only mistakes from the last 7 days".
**Engagement:** weekly leaderboard (per batch) · badges & streak rewards · timed sectional tests with countdown & auto-submit · member groups/batches with batch-level analytics.
**Content:** spaced-repetition scheduling for mistakes · difficulty ratings from real accuracy · monthly PDF "magazine" of questions + answers · Hindi/English toggle (needs a Unicode PDF font) · question comments.
**Admin:** assign a test to a batch · weekly progress report by email/WhatsApp · inactive-member alerts · bulk member import from CSV.
**Platform:** move to a real database (Firebase/Supabase) when you pass a few thousand active members.
