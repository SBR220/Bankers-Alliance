# SETUP — logins, member data and admin panel (all inside one Google Sheet)

You need: a Google account, your GitHub repo and Vercel (what you already use). **No other server, tool or cost.**

How it fits together

```
Member's phone/PC  ──►  your website (Vercel)  ──►  Google Apps Script  ──►  your Google Sheet
   (quiz data kept            (index.html)         (a free script that        (Members, Results,
    in the browser)                                  lives INSIDE the Sheet)    Attempts, ...)
```

* IDs and passwords live **only in the Sheet** (passwords as salted hashes). The website code contains just the script's address.
* Everything a member does is kept in **their own browser storage** (works offline, resumes after refresh) and is **mirrored to the Sheet** in the background so the admin can monitor and so a member's history follows them to a new phone.

---

## Part 1 — Create the Sheet and the script (about 10 minutes)

1. Go to <https://sheets.new> → name it **GA Practice Tool**. Keep it **private** (never share this Sheet with members).
2. Menu **Extensions → Apps Script**. A code editor opens.
3. Delete everything in the editor, open **`apps-script/Code.gs`** from this project, copy ALL of it, paste it in, press **💾 Save**.
4. In the toolbar choose the function **`setup`** (drop-down next to ▶ Run) and press **▶ Run**.
   * Google asks for permission → **Review permissions** → pick your account → **Advanced** → **Go to GA Practice Tool (unsafe)** → **Allow**.
     (It says "unsafe" only because *you* wrote/pasted the script and Google hasn't reviewed it. It only touches this Sheet.)
   * When it finishes you get "Sheets are ready".
5. Go back to the Sheet tab and **reload the page**. You now have 5 tabs (Members, Results, Attempts, UserData, Reports) and a new menu **GA Tool**.

## Part 2 — Add yourself (admin) and your members

Open the **Members** tab. Columns: `ID | Name | Password | Role | Status | …`. Fill only the first four:

| ID | Name | Password | Role |
|---|---|---|---|
| admin | Chief Admin | *(choose a strong password)* | admin |
| rahul01 | Rahul Sharma | rahul@123 | *(leave blank = member)* |
| priya | Priya Verma | priya@456 | |

* The moment you type a password it **disappears** and is replaced by a scrambled hash in the `PassHash`/`Salt` columns. Nobody — including you — can read it again. That is normal.
* **Bulk add:** paste many rows (ID, Name, Password, Role) at once; they are all secured together. If any password stays visible, use **GA Tool → Secure typed passwords now**.
* **Reset a password:** type a new one in the Password cell of that member. **Block someone:** change `Status` from `active` to `blocked`. (Blocked members are cut off on their next action.)
* IDs are not case-sensitive (`Rahul01` = `rahul01`); passwords **are** case-sensitive.
* Don't start a password with `=` (Sheets treats it as a formula).
* Members can change their own password from **My Dashboard → Change my password**.
* After 5 wrong passwords an ID is locked for 15 minutes.

## Part 3 — Publish the script (the "web app")

1. In the Apps Script editor: **Deploy → New deployment**.
2. Click the ⚙️ next to "Select type" → **Web app**.
3. Settings: **Description:** `v1` · **Execute as:** `Me` · **Who has access:** `Anyone`.
   (*Anyone* only means the script can be **called** without a Google login. Without a valid member ID and password it returns nothing.)
4. **Deploy** → copy the **Web app URL** (ends with `/exec`).
5. Open **`index.html`** in your repo, find near the top of the script:
   ```js
   const API_URL = "";
   ```
   and paste the URL between the quotes. **Commit & push.** Vercel redeploys.
6. Open your site → you should see the login screen → sign in with `admin` → you land on Home with a 🛡️ **Admin Panel** button.

> **If you ever edit `Code.gs`:** Deploy → **Manage deployments** → ✏️ edit → *Version: New version* → Deploy. (The URL stays the same.)

## Part 4 — (Strongly recommended) lock the question bank

Without this, a login screen protects the *pages*, but a clever visitor could still download `data/questions.json` directly. Locking encrypts the bank so it can only be opened **after login**.

1. In the Sheet: **GA Tool → Show / create content key** → copy the long key it shows.
2. GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**
   Name: `GA_CONTENT_KEY` · Value: *the key* → Add secret.
3. Make the repo **private**: Settings → General → *Danger zone* → **Change visibility → Private**.
   (Your raw question files in `data/raw/` are in the repo — private keeps them private. Vercel works fine with private repos.)
4. Actions tab → **Build questions from MCQ text files → Run workflow**.
   It now writes `data/questions.enc.json` (unreadable without the key) and deletes the plain `questions.json`.
5. Done. Members receive the key automatically when they log in; their browser unlocks the bank in memory only.

Notes: `vercel.json` (included) also hides `/data/raw`, `/scripts`, `/apps-script` and `/.github` on the live site. If you change the key later, re-run the workflow.

## Part 5 — Daily use

* **Add questions:** put text files in `data/raw/` (see README) → push → the Action rebuilds → live in ~1–2 minutes.
* **Watch members:** open the site as admin → **🛡️ Admin Panel**
  * *Overview* – members, active this week, quizzes taken, average score, activity by month, hardest & slowest questions
  * *Members* – last login, number of logins, quizzes, average %, accuracy, time spent
  * *Quiz log* – **every** quiz by every member with their ID, date & time, right/wrong, score, % (tap a row to see that member's exact answers and time per question; filter by ID; download CSV)
  * *Content health* – **valid vs invalid question counts per month**, each invalid question with file/line/reason, unmapped categories, questions members have 🚩 reported
* You can also read/filter/chart the raw data directly in the Sheet tabs (Results, Attempts).

## What is stored where

| Data | Browser (device) | Google Sheet |
|---|---|---|
| ID & password | ❌ never (only the ID if "Remember my ID" is ticked) | ID + password **hash** |
| Login session | ❌ memory only → refresh = log in again | — |
| Quiz in progress, answers, timers | ✅ (resumes after refresh + re-login) | — |
| Finished quiz results & history | ✅ | ✅ mirrored (Results + Attempts) |
| Saved ⭐ questions, mistakes | ✅ | ✅ mirrored (UserData) |
| Reports 🚩 | queued until sent | ✅ Reports |

## Honest limits

* Results are **reported by the member's browser**, so a technically skilled member could fake their own score. Fine for monitoring/practice; don't use it for money-prize contests without a stricter design.
* The script URL is public (it has to be). Brute-force is limited by the 5-attempt lock **per ID** (note: that also means someone could lock a member's ID for 15 min by guessing).
* Google limits for free accounts are generous (about 30 simultaneous requests; 6 min per request). Hundreds of members are fine; thousands studying at the same second would need a real database.
* Logins last 12 hours; if one expires mid-quiz nothing is lost — results wait on the device and upload at the next login.

## Troubleshooting

| You see | Fix |
|---|---|
| "Login is not connected yet" | `API_URL` in index.html is empty — paste the /exec URL (Part 3, step 5). |
| "Unexpected reply from the server…" | Deploy settings: *Execute as: Me* and *Who has access: **Anyone***. Re-deploy as a **new version**. |
| "Could not reach the server" | Offline, or the URL is wrong/old. |
| "Invalid ID or password" for a correct one | IDs ignore case but passwords don't; also check `Status` is `active` and no spaces in the ID. |
| "The question bank is locked but the server sent no key" | Run **GA Tool → Show / create content key** once, then re-deploy a new version. |
| "key mismatch" | The GitHub secret differs from the Sheet's key. Copy the key again, re-run the workflow. |
| Admin Panel shows no data | Nobody has finished a quiz yet, or press 🔄 Refresh. |
