# Bankers Alliance — Current Affairs MCQ Practice

Month → Main topic → Subtopic → Minor topic → **MCQ practice** with instant explanations,
score + analysis, and A4 PDF export (tilted watermark, header, footer).

```
├── index.html                  the whole website
├── data/
│   ├── raw/                    ★ YOUR MCQ TEXT FILES GO HERE  (2026-08.txt, 2026-09.txt …)
│   ├── tag_map.json            tells the site where each TAG belongs in the topic tree
│   ├── topics.json             the master GA structure (Main > Sub > Minor + weightage)
│   └── questions.json          generated automatically — don't edit by hand
├── scripts/mcq_to_json.py      converts data/raw/*.txt  ->  data/questions.json
└── .github/workflows/build-questions.yml   runs the converter on GitHub for you
```

## 1. Adding MCQs (the daily workflow)

1. Create/edit a text file in **`data/raw/`**. **The file name decides the month**:
   `2026-08.txt`, `august.txt`, `08_august.txt` all mean August.
   (Alternatively put `MONTH: August` on the very first line of the file.)
2. Paste your questions in this format (blank lines between questions are optional):

```
QUESTION: Who is the President of the 81st UNGA?
A. Annalena Baerbock
B. Mirza Fakhrul Alamgir
C. Khalilur Rahman
D. Peter Pellegrini
E. Hakainde Hichilema
ANSWER: C
SOLUTION: Bangladesh's Khalilur Rahman presides over the 81st session.
TAG: United Nations

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
TAG: RBI Monetary Policy
```

* Keywords `TEXT: QUESTION: ANSWER: SOLUTION: TAG:` must be **UPPERCASE**.
* 2 to 6 options (A–F). `SOLUTION` and `TEXT` may run over many lines.
* `&#8203;` lines (zero-width spaces) are turned into paragraph gaps automatically.
* HTML formatting works everywhere: `<b> <i> <u> <mark> <br>` and even `<table>`.
* A question that only has a label (e.g. `STATEMENT BASED QUESTION`) shows that label as a small tag above the passage.

3. **Commit & push.** The GitHub Action rebuilds `data/questions.json`; Vercel/GitHub Pages then redeploys.
   (Repo → *Actions* tab → *Build questions.json* → green tick = done. Warnings about skipped
   questions or unknown tags appear there as yellow annotations.)

*Prefer to run it yourself?* `python3 scripts/mcq_to_json.py` (no installs needed) and commit `data/questions.json`.

## 2. Where does a TAG go?  (`data/tag_map.json`)

Each question's `TAG:` is matched to a category in this order:

1. **`data/tag_map.json`** — explicit, always wins:
   `"United Nations": {"main": "C", "sub": "Global Organizations"}`  
   (`"minor"` is optional; by default the tag itself becomes a minor-topic chip.)
2. **Automatic matching** against the names in `topics.json` (e.g. `RBI Monetary Policy` → *RBI & Monetary Policy*, `UPI` → *UPI*).
   The converter prints what it matched so you can double-check.
3. Otherwise the question is filed under **Other / Unsorted** (a grey topic card that appears only when needed)
   and the Action shows a warning naming the tag — just add that tag to `tag_map.json`.

To override per question, write lines **above** a question: `MAIN: C`, `SUB: Global Organizations`, `MINOR: UN`, `MONTH: 8`.

## 3. What the site does

| | |
|---|---|
| **Navigation** | Header has only **Home** and **Back** (they also work with the phone's back button). The Main › Sub › Minor trail is shown inside each question card. |
| **"All"** | Every level (month, topic, subtopic) has a *Practice all …* button, plus an **All Months** tile. |
| **Practice mode** | Tap an option → instantly ✅/❌, correct answer highlighted, **explanation shown**. Answer locks. |
| **Test mode** | No feedback until the end; answers can be changed; full review afterwards. |
| **Result** | Score ring, correct/wrong/skipped, accuracy, time, avg time per question, per-topic bars, verdict. |
| **Extras** | Negative marking (−¼), shuffle, random subset (10/20/30/50), question palette, ⭐ save questions, **My Mistakes** (auto-collected; fixed ones disappear), Retry wrong, Review (filter wrong/correct/skipped), resume unfinished quizzes, recent-results history, keyboard shortcuts (`A–E` / `1–5` answer, `←/→` move, `S` save), share score. |
| **PDF** | At the bottom of every opened topic: **Question paper** or **With answers & solutions**. A4, tilted *BANKERS ALLIANCE* watermark on every page, header *"Target MCQs of {Section}"*, footer *"Created by BankersAlliance and Victory Banker"*, page numbers. Questions are never split across pages. |

Progress, saved questions, mistakes and history are stored in the learner's own browser (localStorage).

## 4. Easy settings (top of the `<script>` in `index.html`)

`BRAND`, `YEAR`, `NEG_MARK`, `PDF_HEADER_PREFIX` (change *"Target MCQs of"* if you prefer another wording),
`PDF_FOOTER_TEXT`, `PDF_WATERMARK`.

## 5. Good to know

* The PDF library (jsPDF) loads from a CDN, so the first PDF needs internet.
* PDF text uses built-in Latin fonts: **₹ prints as "Rs."** and Hindi/other scripts can't be shown in the PDF (they display fine on the website).
* Opening `index.html` by double-clicking won't load the data (browsers block `fetch` on `file://`); use your hosted site, or `python3 -m http.server` locally.
* Old story files (`news.json`, `csv_to_json.py`, `csv-to-json.yml`) are no longer used — delete them from your repo.
