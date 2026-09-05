#!/usr/bin/env python3
"""
Convert a bulk news CSV into data/news.json for the GA Pulse revision site.

USAGE:
    python3 scripts/csv_to_json.py data/news_template.csv data/news.json

REQUIRED CSV COLUMNS (header row required, exact names, any order):
    id, month, main, sub, minor, date, importance, title, body, remember, statics, source

OPTIONAL CSV COLUMNS (leave the whole column out, or leave cells blank —
the story card just won't show that section):
    highlights   -- "Key News" bullet list, pipe-separated, e.g. "Point A|Point B"
    examFocus    -- "Exam Focus" flashcard lines, pipe-separated, each formatted
                    "Label → Value" or "Label: Value", e.g.
                    "Launch date → 1 March 2021|FRS → Take-Home Rations"
    footerTitle  -- bold name shown in the card's footer (defaults to the topic name)
    hashtags     -- pipe-separated tags shown in the footer, without '#', e.g.
                    "PoshanTracker|MissionPoshan2.0" (defaults to auto-generated tags)

NOTES:
  - month: use 1-12 (Jan=1 ... Dec=12). The script converts it to the
    0-indexed value the site expects.
  - main: single letter code, must match a topic code in the app (A-H).
  - sub / minor: must match the exact subtopic/minor-topic text used in the
    app's TOPICS structure in index.html, so filtering works correctly.
  - remember / statics / highlights / hashtags / examFocus: put multiple
    values in ONE cell, separated by a pipe character "|".
  - importance: a number 1-3 (shown as star rating on the card).
  - Wrap any cell that contains a comma in double quotes (standard CSV rule
    -- Excel/Google Sheets do this for you automatically on export).

You can maintain the master list in Google Sheets / Excel, export as CSV,
then run this script to regenerate data/news.json. Existing news.json
content is fully REPLACED by the CSV content each time you run this --
so keep your CSV as the single source of truth, or append your new rows
to the existing CSV before re-running.
"""

import csv
import json
import sys

REQUIRED_COLUMNS = {"id", "month", "main", "sub", "minor", "date",
                    "importance", "title", "body", "remember", "statics", "source"}
OPTIONAL_LIST_COLUMNS = ["highlights", "examFocus", "hashtags"]
OPTIONAL_TEXT_COLUMNS = ["footerTitle"]


def split_pipes(value):
    return [p.strip() for p in value.split("|") if p.strip()]


def convert(csv_path: str, json_path: str) -> None:
    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - fieldnames
        if missing:
            sys.exit(f"CSV is missing required column(s): {', '.join(sorted(missing))}")

        present_optional_lists = [c for c in OPTIONAL_LIST_COLUMNS if c in fieldnames]
        present_optional_text = [c for c in OPTIONAL_TEXT_COLUMNS if c in fieldnames]

        for i, row in enumerate(reader, start=2):  # row 1 is the header
            try:
                item = {
                    "id": int(row["id"]),
                    "month": int(row["month"]) - 1,  # convert 1-12 -> 0-11
                    "main": row["main"].strip(),
                    "sub": row["sub"].strip(),
                    "minor": row["minor"].strip(),
                    "date": row["date"].strip(),
                    "importance": int(row["importance"]),
                    "title": row["title"].strip(),
                    "body": row["body"].strip(),
                    "remember": split_pipes(row["remember"]),
                    "statics": split_pipes(row["statics"]),
                    "source": row["source"].strip(),
                }
                for col in present_optional_lists:
                    val = split_pipes(row.get(col, "") or "")
                    if val:
                        item[col] = val
                for col in present_optional_text:
                    val = (row.get(col, "") or "").strip()
                    if val:
                        item[col] = val
                rows.append(item)
            except (ValueError, KeyError) as e:
                sys.exit(f"Error on CSV row {i}: {e}")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print(f"✅ Wrote {len(rows)} news items to {json_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python3 csv_to_json.py <input.csv> <output.json>")
    convert(sys.argv[1], sys.argv[2])
