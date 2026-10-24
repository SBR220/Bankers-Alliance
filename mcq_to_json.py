#!/usr/bin/env python3
"""
Convert MCQ text files into data/questions.json for the quiz website.

USAGE (from the repository root, no extra installs needed):
    python3 scripts/mcq_to_json.py

    # or with custom paths:
    python3 scripts/mcq_to_json.py --raw data/raw --out data/questions.json

WHERE THE MCQs GO
    Put your text files in  data/raw/  - one file per month is the easiest:
        data/raw/2026-08.txt   or   data/raw/august.txt   or   data/raw/08_august.txt
    The month is read from the FILE NAME. (You can also write a line
    "MONTH: August" at the very top of a file, or inside one question.)

QUESTION FORMAT  (blank lines between questions are optional)
    QUESTION: Who is the President of ...?
    A. Option one
    B. Option two
    C. Option three
    D. Option four
    E. Option five            <- 2 to 6 options are fine
    ANSWER: C
    SOLUTION: Explanation text (can run over several lines)
    TAG: United Nations

    Statement-based / passage questions start with a TEXT: block:
    TEXT: <u>Consider the following statements:</u>
    &#8203;
    I. First statement
    II. Second statement
    &#8203;
    Which of the statements given above is/are correct?
    QUESTION: STATEMENT BASED QUESTION
    A. Only I
    ...
    ANSWER: A
    SOLUTION: ...
    TAG: RBI Monetary Policy

    * Keywords (TEXT, QUESTION, ANSWER, SOLUTION, TAG) must be UPPERCASE.
    * Simple HTML is fine anywhere: <b> <i> <u> <mark> <br> and even tables.
    * Lines containing only &#8203; (zero-width space) become paragraph gaps.

OPTIONAL PER-QUESTION LINES (rarely needed)
    MONTH: 8        MAIN: C        SUB: Global Organizations        MINOR: UN

HOW TAGS BECOME CATEGORIES
    1. data/tag_map.json   (explicit, always wins)
    2. automatic matching against the names in data/topics.json
    3. otherwise the question goes to "Other / Unsorted" and a warning lists
       the tag so you can add it to tag_map.json.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MONTH_NAMES = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

KEY_RE = re.compile(
    r"^\s*(TEXT|PASSAGE|QUESTION|ANSWER|ANS|SOLUTION|EXPLANATION|TAGS|TAG|MONTH|MAIN|SUB|MINOR)\s*:\s*(.*?)\s*$"
)
OPT_RE = re.compile(r"^\s*\(?([A-Fa-f])[.)]\s+(\S.*?)\s*$")
ZW_RE = re.compile(r"(&#0*8203;|&#x0*200b;|[\u200b\u200c\u200d\u2060\ufeff])", re.I)
STOPWORDS = {"and", "of", "the", "in", "for", "a", "an", "to", "on"}
OTHER_CODE, OTHER_SUB = "Z", "Unsorted"


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def gh_warn(msg, path=None, line=None):
    """Print a warning; GitHub Actions turns the '::warning' form into an annotation."""
    loc = ""
    if path:
        loc = f" file={path}" + (f",line={line}" if line else "")
    print(f"::warning{loc}::{msg}")


def tokens(text):
    words = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split()
    return [w for w in words if w not in STOPWORDS]


def is_blank(line):
    return not ZW_RE.sub("", line).replace("&nbsp;", "").strip()


def clean(line):
    return ZW_RE.sub("", line).strip()


def to_paragraphs(lines):
    """Lines -> <p>..</p> blocks. Blank / zero-width lines separate paragraphs."""
    paras, cur = [], []
    for ln in lines:
        if is_blank(ln):
            if cur:
                paras.append(cur)
                cur = []
        else:
            cur.append(clean(ln))
    if cur:
        paras.append(cur)
    return "".join("<p>" + "<br>".join(p) + "</p>" for p in paras)


def to_inline(lines):
    """Lines -> single string; paragraph gaps become <br><br>."""
    out, gap = [], False
    for ln in lines:
        if is_blank(ln):
            gap = bool(out)
        else:
            if gap:
                out.append("<br>")
                gap = False
            out.append(clean(ln))
    return "<br>".join(out).replace("<br><br><br>", "<br><br>")


def parse_month(value):
    if value is None:
        return None
    v = str(value).strip().lower()
    if not v:
        return None
    if v.isdigit() and 1 <= int(v) <= 12:
        return int(v)
    return MONTH_NAMES.get(v)


def month_from_filename(path):
    stem = path.stem.lower()
    for word in re.split(r"[^a-z]+", stem):
        if word in MONTH_NAMES:
            return MONTH_NAMES[word]
    m = re.search(r"(?:19|20)\d\d[-_.](\d{1,2})(?!\d)", stem)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1))
    m = re.match(r"^(\d{1,2})(?:[-_ ].*)?$", stem)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1))
    return None


def parse_answer(raw):
    m = re.search(r"\b([A-Fa-f])\b", raw or "")
    return m.group(1).upper() if m else None


# --------------------------------------------------------------------------
# parsing one text file into raw blocks
# --------------------------------------------------------------------------
def new_block(line_no=0):
    return {"line": line_no, "seen": set(), "text": [], "question": [], "options": [],
            "answer": None, "solution": [], "tag": "", "meta": {}}


def parse_file(path):
    """Split a text file into raw question blocks.

    Override lines (MONTH/MAIN/SUB/MINOR):
      * "MONTH:" before the very first question  -> default for the whole file
      * any override written while a question is still being typed (before its
        ANSWER/SOLUTION/TAG)                       -> applies to that question
      * any override after a finished question    -> applies to the NEXT question
    """
    blocks, defaults, warnings = [], {}, []
    pending = {}
    b, state = new_block(), None

    def flush():
        nonlocal b
        if b["seen"]:
            blocks.append(b)
        b = new_block()

    def start_block(line_no):
        """Called when the first keyword of a question appears."""
        b["line"] = line_no
        b["meta"].update(pending)
        pending.clear()

    lines = path.read_text(encoding="utf-8-sig").splitlines()
    for i, raw in enumerate(lines, 1):
        line = raw.rstrip()
        m = KEY_RE.match(line)
        if m:
            key, rest = m.group(1), m.group(2)
            if key in ("TEXT", "PASSAGE"):
                if b["seen"]:
                    flush()
                start_block(i)
                b["seen"].add("TEXT")
                b["text"] = [rest] if rest else []
                state = "text"
            elif key == "QUESTION":
                if {"QUESTION", "ANSWER"} & b["seen"] or b["options"]:
                    flush()
                if not b["line"]:
                    start_block(i)
                b["seen"].add("QUESTION")
                b["question"] = [rest] if rest else []
                state = "question"
            elif key in ("ANSWER", "ANS"):
                b["seen"].add("ANSWER")
                b["answer"] = rest
                state = "answer"
            elif key in ("SOLUTION", "EXPLANATION"):
                b["seen"].add("SOLUTION")
                b["solution"] = [rest] if rest else []
                state = "solution"
            elif key in ("TAG", "TAGS"):
                b["seen"].add("TAG")
                b["tag"] = rest
                state = "tag"
            else:  # MONTH / MAIN / SUB / MINOR
                k = key.lower()
                still_writing = b["seen"] and not ({"ANSWER", "SOLUTION", "TAG"} & b["seen"])
                if still_writing:
                    b["meta"][k] = rest
                elif k == "month" and not blocks and not b["seen"] and not pending:
                    defaults["month"] = rest
                else:
                    pending[k] = rest
                state = None
            continue

        om = OPT_RE.match(line) if state in ("question", "options") else None
        if om:
            b["options"].append([om.group(1).upper(), om.group(2)])
            b["seen"].add("OPTIONS")
            state = "options"
            continue

        if state == "text":
            b["text"].append(line)
        elif state == "question":
            b["question"].append(line)
        elif state == "options":
            if line.strip() and b["options"]:
                b["options"][-1][1] += " " + clean(line)
        elif state == "solution":
            b["solution"].append(line)
        elif line.strip():
            warnings.append((i, f"Ignored stray line: {line.strip()[:60]}"))
    flush()
    if pending:
        warnings.append((len(lines), "MONTH/MAIN/SUB/MINOR line at the end of the file is not "
                                     "followed by a question and was ignored"))
    return blocks, defaults, warnings


# --------------------------------------------------------------------------
# tag -> category mapping
# --------------------------------------------------------------------------
class Taxonomy:
    def __init__(self, topics, tag_map):
        self.topics = topics
        self.tag_map = {k.strip().lower(): v for k, v in tag_map.items() if not k.startswith("_")}
        self.by_code = {t["code"]: t for t in topics}

    def canon_sub(self, main, sub):
        top = self.by_code.get(main)
        if top:
            for s in top["subs"]:
                if tokens(s["name"]) == tokens(sub):
                    return s["name"]
        return sub

    @staticmethod
    def score(tag_tokens, target_tokens, prio):
        if not target_tokens:
            return 0
        a, b = set(tag_tokens), set(target_tokens)
        if a == b:
            return 1000 + prio
        if a <= b or b <= a:
            return 100 + 10 * len(a & b) + prio
        return 0

    def map_tag(self, tag):
        """Return (main, sub, minor, how) or None if nothing matches."""
        tag = tag.strip()
        if not tag:
            return None
        hit = self.tag_map.get(tag.lower())
        if hit:
            main = hit["main"].upper()
            return main, self.canon_sub(main, hit["sub"]), hit.get("minor") or tag, "tag_map.json"

        tt = tokens(tag)
        if not tt:
            return None
        best, best_score = None, 0
        for top in self.topics:
            for sub in top["subs"]:
                for minor in sub["minors"]:
                    s = self.score(tt, tokens(minor), 3)
                    if s > best_score:
                        best, best_score = (top["code"], sub["name"], minor), s
                s = self.score(tt, tokens(sub["name"]), 2)
                if s > best_score:
                    best, best_score = (top["code"], sub["name"], tag), s
            s = self.score(tt, tokens(top["name"]), 1)
            if s > best_score:
                sub = top["subs"][0]["name"] if len(top["subs"]) == 1 else "General"
                best, best_score = (top["code"], sub, tag), s
        if best:
            return best[0], best[1], best[2], "auto-match"
        return None


# --------------------------------------------------------------------------
# build final records
# --------------------------------------------------------------------------
def build_record(b, path, defaults, file_month, tax, report):
    where = (str(path), b["line"])
    problems = []

    question = to_inline(b["question"])
    passage = to_paragraphs(b["text"])
    options = {}
    for k, v in b["options"]:
        if k in options:
            problems.append(f"option {k} appears twice")
        options[k] = clean(v)
    answer = parse_answer(b["answer"])

    if not question and not passage:
        problems.append("no QUESTION or TEXT found")
    if len(options) < 2:
        problems.append("needs at least two options (A., B., ...)")
    if not answer:
        problems.append("missing or unreadable ANSWER")
    elif answer not in options:
        problems.append(f"ANSWER {answer} is not one of the options {sorted(options)}")

    month = (parse_month(b["meta"].get("month")) or parse_month(defaults.get("month")) or file_month)
    if not month:
        problems.append("month unknown")
    if problems:
        report["skipped"].append((where, "; ".join(problems)))
        return None

    # ---- category -------------------------------------------------------
    explicit_main = (b["meta"].get("main") or defaults.get("main") or "").strip().upper()
    explicit_sub = (b["meta"].get("sub") or defaults.get("sub") or "").strip()
    explicit_minor = (b["meta"].get("minor") or defaults.get("minor") or "").strip()
    tag_text = b["tag"].strip()
    unmapped_key = None

    if explicit_main:
        sub = tax.canon_sub(explicit_main, explicit_sub) if explicit_sub else "General"
        main, minor = explicit_main, explicit_minor or tag_text or "General"
        if explicit_main not in tax.by_code:
            report["warnings"].append((where, f"MAIN '{explicit_main}' is not a known topic code"))
    else:
        mapped = None
        for piece in [p.strip() for p in re.split(r"[;,]", tag_text) if p.strip()] or [""]:
            mapped = tax.map_tag(piece)
            if mapped:
                break
        if mapped:
            main, sub, minor, how = mapped
            if explicit_minor:
                minor = explicit_minor
            if how == "auto-match":
                report["auto"].setdefault(tag_text, f"{main} > {sub} > {minor}")
        else:
            main, sub, minor = OTHER_CODE, OTHER_SUB, tag_text or "Untagged"
            unmapped_key = tag_text or "(no TAG)"

    rec = {
        "month": month - 1,
        "main": main, "sub": sub, "minor": minor, "tag": tag_text,
        "passage": passage, "question": question,
        "options": options, "answer": answer,
        "solution": to_paragraphs(b["solution"]),
    }
    rec["_unmapped"] = unmapped_key
    digest = json.dumps([rec["month"], passage, question, options, answer], ensure_ascii=False)
    rec["id"] = hashlib.sha1(digest.encode("utf-8")).hexdigest()[:10]
    return rec


def main():
    ap = argparse.ArgumentParser(description="Build questions.json from MCQ text files")
    ap.add_argument("--raw", default=str(ROOT / "data" / "raw"))
    ap.add_argument("--out", default=str(ROOT / "data" / "questions.json"))
    ap.add_argument("--topics", default=str(ROOT / "data" / "topics.json"))
    ap.add_argument("--tagmap", default=str(ROOT / "data" / "tag_map.json"))
    args = ap.parse_args()

    topics = json.loads(Path(args.topics).read_text(encoding="utf-8"))
    tag_map = json.loads(Path(args.tagmap).read_text(encoding="utf-8")) if Path(args.tagmap).exists() else {}
    tax = Taxonomy(topics, tag_map)

    raw_dir = Path(args.raw)
    files = sorted(p for p in raw_dir.rglob("*.txt") if not p.name.startswith(("_", ".")))
    if not files:
        print(f"No .txt files found in {raw_dir} - writing an empty question bank.")

    report = {"skipped": [], "warnings": [], "auto": {}, "unmapped": {}}
    records, seen_ids, missing_month = [], set(), []

    for order, path in enumerate(files):
        blocks, defaults, stray = parse_file(path)
        rel = path.relative_to(ROOT) if ROOT in path.parents else path
        file_month = month_from_filename(path)
        if not file_month and not parse_month(defaults.get("month")):
            if not all(parse_month(b["meta"].get("month")) for b in blocks):
                missing_month.append(rel)
                continue
        for line_no, msg in stray:
            report["warnings"].append(((str(rel), line_no), msg))
        for seq, b in enumerate(blocks):
            rec = build_record(b, rel, defaults, file_month, tax, report)
            if not rec:
                continue
            if rec["id"] in seen_ids:
                report["warnings"].append(((str(rel), b["line"]), "duplicate question skipped"))
                continue
            seen_ids.add(rec["id"])
            key = rec.pop("_unmapped", None)
            if key:
                report["unmapped"][key] = report["unmapped"].get(key, 0) + 1
            records.append(((rec["month"], order, seq), rec))

    if missing_month:
        for p in missing_month:
            print(f"::error file={p}::Cannot tell which month this file is for. Rename it like "
                  f"2026-08.txt or august.txt, or put 'MONTH: August' on the first line.")
        sys.exit(2)

    records.sort(key=lambda x: x[0])
    out = [r for _, r in records]
    for r in out:  # drop empty optional fields to keep the file small
        for k in ("passage", "solution", "tag"):
            if not r[k]:
                del r[k]
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- report ---------------------------------------------------------
    print(f"\n✅ Wrote {len(out)} questions to {args.out}")
    by_month = {}
    for r in out:
        by_month[r["month"]] = by_month.get(r["month"], 0) + 1
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    if by_month:
        print("   Per month: " + ", ".join(f"{names[m]}={n}" for m, n in sorted(by_month.items())))
    if report["auto"]:
        print("\nℹ️  Tags matched automatically (add to data/tag_map.json to override):")
        for tag, dest in report["auto"].items():
            print(f"   '{tag}'  ->  {dest}")
    for tag, n in report["unmapped"].items():
        gh_warn(f"Tag '{tag}' ({n} question(s)) is not in data/tag_map.json and matched no topic - "
                f"filed under 'Other / Unsorted'. Add it to data/tag_map.json.")
    for (path, line), msg in report["warnings"]:
        gh_warn(msg, path, line)
    for (path, line), msg in report["skipped"]:
        gh_warn(f"Question SKIPPED - {msg}", path, line)
    if report["skipped"]:
        print(f"\n⚠️  {len(report['skipped'])} question(s) were skipped (see warnings above).")


if __name__ == "__main__":
    main()
