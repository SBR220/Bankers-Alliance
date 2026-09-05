# GA Pulse — Current Affairs Revision Site

A single-page revision app: Month → Main Topic → Subtopic → Minor Topic → News cards
with "Remember This" and "Static Points" boxes.

```
ga-pulse/
├── index.html              ← the app (structure, styling, logic)
├── data/
│   ├── news.json           ← THE CONTENT — edit this to add/change news
│   └── news_template.csv   ← spreadsheet template for bulk entry
└── scripts/
    └── csv_to_json.py      ← converts a bulk CSV into news.json
```

---

## 1. Host it on GitHub Pages (free, no server needed)

1. Create a new GitHub repository (e.g. `ga-pulse`).
2. Upload these three items to the **root** of the repo, keeping the folder
   structure exactly as above (`index.html` at root, `data/` and `scripts/`
   as subfolders).
3. Go to **Settings → Pages**.
4. Under "Build and deployment", set **Source: Deploy from a branch**,
   branch: **main**, folder: **/ (root)**. Save.
5. Wait ~1 minute, then GitHub shows your live URL, typically:
   `https://<your-username>.github.io/ga-pulse/`
6. Open it — the page will fetch `data/news.json` automatically and render.

Every time you push a change to `data/news.json` (or edit it directly on
github.com), the live site updates within a minute or two — no rebuild step,
no server code.

> ⚠️ One thing that trips people up: don't just double-click `index.html`
> on your own computer to test it — `fetch()` is blocked on the `file://`
> protocol by browser security rules, so the news won't load locally unless
> you run a local dev server (e.g. `python3 -m http.server` from the folder,
> then visit `http://localhost:8000`). On GitHub Pages this is a non-issue
> since it's served over `https://`.

---

## 2. Adding news in bulk — two ways

### Option A: Edit `data/news.json` directly
Good for occasional additions. Copy this block, fill it in, add a comma
after the previous item, paste it in:

```json
{
  "id": 13,
  "month": 8,
  "main": "A",
  "sub": "RBI & Monetary Policy",
  "minor": "Inflation Target",
  "date": "Sep 10",
  "importance": 3,
  "title": "Your headline with an emoji 🎯",
  "body": "One or two sentence plain-English summary of the news.",
  "remember": ["Key point one", "Key point two", "Key point three"],
  "statics": ["Static fact one", "Static fact two"],
  "source": "Where this came from"
}
```

- `month` is **0-indexed**: January = 0, December = 11.
- `main` must be one of the topic codes: `A B C D E F G H`.
- `sub` and `minor` must match the exact text used in `index.html`'s
  `TOPICS` structure — otherwise the card won't show up under that filter
  (it'll still appear when "Show all" is selected, since that ignores
  sub/minor matching).
- `importance` is 1–3 and controls the ⭐ rating shown on the card.

### Option B: Bulk import from a spreadsheet (recommended for lots of entries)
This is the easiest way to add dozens of news items at once without
hand-writing JSON.

1. Open `data/news_template.csv` in Google Sheets / Excel.
2. Add one row per news item. Columns:

   | column | notes |
   |---|---|
   | id | any unique number |
   | month | **1–12** (human-friendly here — the script converts it) |
   | main | topic code A–H |
   | sub | exact subtopic name |
   | minor | exact minor-topic name |
   | date | display text, e.g. `Sep 10` |
   | importance | 1, 2, or 3 |
   | title | headline (emoji welcome) |
   | body | 1–2 sentence summary |
   | remember | bullet points separated by `\|` e.g. `Point one\|Point two` |
   | statics | same `\|`-separated format |
   | source | citation/source note |

3. Export as CSV (File → Download → CSV).
4. Run the converter (needs Python 3, no extra installs):
   ```bash
   python3 scripts/csv_to_json.py data/your_export.csv data/news.json
   ```
5. Commit and push the updated `data/news.json`. Done — the whole batch is live.

This workflow means non-technical contributors can fill in a spreadsheet,
and you just run one command to publish the batch.

---

## 3. Does all this data make the file heavy / slow to load?

Short answer: **no, not at your realistic scale.**

- The current `news.json` (12 items) is about **6 KB**.
- Even **500 detailed news items** (a very thick full-year dataset) would be
  roughly **250–350 KB** of JSON — still loads in well under a second on
  any connection, and the browser caches it after the first visit.
- `index.html` itself (structure + styling + logic) is ~35 KB regardless of
  how much news content you add, since content now lives separately in JSON.

**When it would actually start to matter:** if you eventually have several
thousand entries covering many years. At that point, the fix isn't to
avoid JSON — it's to **split it by month or year** instead of one giant
file, and only fetch what's needed:

```js
// instead of one fetch("data/news.json"), fetch per month on demand:
fetch(`data/2026/${String(monthIndex+1).padStart(2,"0")}.json`)
```

That's a ~15-minute change to `loadData()` if/when you need it — for now,
a single `data/news.json` file is simpler and completely fine.

---

## 4. New: themed story cards, simplified nav, and PDF export

**Story card redesign.** Each news card is now a full magazine-style layout
(dark themed header per topic, drop-cap lead paragraph, Remember This /
Static Points boxes, optional Key News and Exam Focus sections, footer with
ministry name + hashtags). The header gradient automatically uses that
story's topic colour — no per-topic CSS to maintain, it's computed from the
same `main` code you already set.

**Optional fields** (add these columns to your CSV/JSON if you want the
richer sections — leave them out and the card still renders fine without
them):
- `highlights` → renders a "📰 Key News" bullet list
- `examFocus` → renders a "🎯 Exam Focus" flashcard strip. Format each item
  as `Label → Value`, e.g. `Launch date → 1 March 2021`
- `footerTitle` → bold name in the card's footer (defaults to the topic name)
- `hashtags` → pipe-separated tags in the footer (defaults to auto-generated ones)

**Simplified header nav.** The top bar now shows only **🏠 Home** and
**← Back** — no breadcrumb trail up there. The full path (Topic › Subtopic ›
Minor Topic) still shows on every individual story card, same as your sample.

**PDF export.** Every news list screen (a specific minor topic, or any
"Show all" view) has a **📄 Download PDF** button at the bottom. It exports
exactly what's on screen at A4 size, with:
- A tilted "BANKERS ALLIANCE" watermark on every page
- A header reading **"Target News of {Section}"** — the section name is
  whichever filter is currently most specific (minor topic name, or the
  subtopic/topic/month name when "Show all" is used)
- A footer reading **"Created by BankersAlliance and Victory Banker"** with
  page numbers
- Automatic pagination — long lists span multiple pages cleanly

This uses the [jsPDF](https://github.com/parallax/jsPDF) library loaded from
a CDN (`cdnjs.cloudflare.com`), so it needs an internet connection to load
the very first time the button is used (cached by the browser after that).

---

## 5. Quick content checklist before publishing a batch
- [ ] Every `main` code matches A–H exactly
- [ ] Every `sub` / `minor` string matches the app's topic list exactly (case-sensitive)
- [ ] `data/news.json` is valid JSON (run `python3 -m json.tool data/news.json` to check — it'll error out if a comma or quote is off)
- [ ] Facts in `body` / `remember` / `statics` are verified against an official source, not left as placeholder text
