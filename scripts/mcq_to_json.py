#!/usr/bin/env python3
"""
Convert MCQ text files into the question bank used by the quiz website.

USAGE (from the repository root; no installs needed unless you lock the bank):
    python3 scripts/mcq_to_json.py

WHERE THE MCQs GO
    data/raw/2026-08.txt  (the FILE NAME gives the month: 2026-08, august, 08_august ...)
    or put "MONTH: August" on the very first line of a file.

QUESTION FORMAT
    QUESTION: Who is the President of ...?
    A. Option one
    B. Option two
    C. ...                     (2 to 6 options)
    ANSWER: C
    SOLUTION: Explanation (may run over several lines)
    TAG: RBI, Banking news, National news / Data Based, Statement Based

    Statement / data / match-the-column questions start with a TEXT: block:
    TEXT: <u>Consider the following statements:</u>
    &#8203;
    I. First statement
    II. Second statement
    &#8203;
    Which of the statements given above is/are correct?
    QUESTION: STATEMENT BASED QUESTION
    ...

THE TAG LINE  =  CATEGORIES  /  QUESTION TYPES
    * Before the "/" : one or more categories, separated by commas.
    * After  the "/" : one or more question types, separated by commas:
                       Oneliner, Data Based, Statement Based, Match the Column
    * The "/" part is optional. Without it the type is detected automatically
      (table -> Data Based, numbered statements -> Statement Based,
       "match the following" -> Match the Column, otherwise Oneliner).
    * A "/" inside a category name (e.g. "Repo Rate / Reverse Repo") is fine -
      the part after the LAST "/" only counts as types if every item in it is a
      known question type.
    * A question appears under EVERY category it lists.

OPTIONAL LINES (above a question):  MONTH: 8   MAIN: C   SUB: ...   MINOR: ...   TYPE: Oneliner

CATEGORY -> TOPIC TREE
    1. data/tag_map.json   (explicit; always wins)
    2. automatic matching against names in data/topics.json
    3. otherwise "Other / Unsorted" + a warning telling you which tag to add.

OUTPUT
    data/questions.json  =  {"built": ..., "questions": [...], "report": {...}}
    The report holds valid / invalid question counts per month (shown to the admin).

LOCKING THE BANK (optional, recommended once you have members)
    Set the environment variable GA_CONTENT_KEY (base64 of 32 random bytes - the
    Apps Script menu "GA Tool > Show content key" gives you one). The converter then
    writes data/questions.enc.json (AES-256-GCM) and DELETES the plain questions.json.
    The website can only decrypt it after a member logs in. Needs:  pip install cryptography
"""

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MONTH_NAMES = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

QTYPES = ["Oneliner", "Data Based", "Statement Based", "Match the Column"]
TYPE_ALIASES = {
    "oneliner": "Oneliner", "one liner": "Oneliner", "one line": "Oneliner", "oneline": "Oneliner",
    "factual": "Oneliner", "direct": "Oneliner",
    "data based": "Data Based", "databased": "Data Based", "data": "Data Based",
    "data interpretation": "Data Based", "di": "Data Based", "table based": "Data Based", "chart based": "Data Based",
    "statement based": "Statement Based", "statementbased": "Statement Based", "statement": "Statement Based",
    "statements": "Statement Based",
    "match the column": "Match the Column", "match the columns": "Match the Column",
    "match the following": "Match the Column", "match the list": "Match the Column",
    "matching": "Match the Column", "match": "Match the Column",
}

KEY_RE = re.compile(
    r"^\s*(TEXT|PASSAGE|QUESTION|ANSWER|ANS|SOLUTION|EXPLANATION|TAGS|TAG|TYPES|TYPE|MONTH|MAIN|SUB|MINOR)\s*:\s*(.*?)\s*$"
)
OPT_RE = re.compile(r"^\s*\(?([A-Fa-f])[.)]\s+(\S.*?)\s*$")
ZW_RE = re.compile(r"(&#0*8203;|&#x0*200b;|[\u200b\u200c\u200d\u2060\ufeff])", re.I)
STOPWORDS = {"and", "of", "the", "in", "for", "a", "an", "to", "on"}
OTHER_CODE, OTHER_SUB = "Z", "Unsorted"


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def gh_warn(msg, path=None, line=None):
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


def norm_type(text):
    key = re.sub(r"[^a-z]+", " ", (text or "").lower()).strip()
    return TYPE_ALIASES.get(key)


def dedupe(seq):
    out = []
    for x in seq:
        if x not in out:
            out.append(x)
    return out


def split_tag(tag_text):
    """'A, B / Data Based, Statement Based' -> (['A','B'], ['Data Based','Statement Based'])
    The part after the LAST '/' is treated as types only if EVERY item is a known type."""
    t = (tag_text or "").strip()
    pieces = lambda s: [p.strip() for p in re.split(r"[;,]", s) if p.strip()]
    if "/" in t:
        head, _, tail = t.rpartition("/")
        items = pieces(tail)
        types = [norm_type(x) for x in items]
        if items and all(types):
            return pieces(head), dedupe(types)
    return pieces(t), None


def infer_types(passage, question):
    """Used when the TAG has no '/ type' part."""
    low = (passage + " " + question).lower()
    text = re.sub(r"<[^>]+>", " ", low)
    if re.search(r"match (the )?(following|column|columns|list)|\bcolumn[\s-]*(i|1|a)\b|\blist[\s-]*(i|1)\b", text):
        return ["Match the Column"]
    found = []
    if "<table" in low or re.search(r"\b(table|graph|chart|pie chart|bar diagram|following data|data given)\b", text):
        found.append("Data Based")
    if re.search(r"statement based", text) or (
        re.search(r"\bstatements?\b", text)
        and re.search(r"(?:^|<br>|<p>|\n)\s*(?:i{1,3}|iv|v|[1-5])[.)]\s", low)
    ):
        found.append("Statement Based")
    return found or ["Oneliner"]


# --------------------------------------------------------------------------
# parsing one text file into raw blocks
# --------------------------------------------------------------------------
def new_block(line_no=0):
    return {"line": line_no, "seen": set(), "text": [], "question": [], "options": [],
            "answer": None, "solution": [], "tag": "", "type": "", "meta": {}}


def parse_file(path):
    """Override lines (MONTH/MAIN/SUB/MINOR/TYPE):
       before the very first question (MONTH only) -> default for the file;
       while a question is still being written     -> that question;
       after a finished question                   -> the NEXT question."""
    blocks, defaults, warnings = [], {}, []
    pending = {}
    b, state = new_block(), None

    def flush():
        nonlocal b
        if b["seen"]:
            blocks.append(b)
        b = new_block()

    def start_block(line_no):
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
            else:  # MONTH / MAIN / SUB / MINOR / TYPE
                k = "type" if key in ("TYPE", "TYPES") else key.lower()
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
        warnings.append((len(lines), "an override line (MONTH/MAIN/SUB/MINOR/TYPE) at the end of the file "
                                     "is not followed by a question and was ignored"))
    return blocks, defaults, warnings


# --------------------------------------------------------------------------
# category -> topic tree
# --------------------------------------------------------------------------
class Taxonomy:
    def __init__(self, topics, tag_map):
        self.topics = topics
        self.tag_map = {k.strip().lower(): v for k, v in tag_map.items() if not k.startswith("_")}
        self.by_code = {t["code"]: t for t in topics}

    def default_sub(self, main):
        top = self.by_code.get(main)
        if top and len(top["subs"]) == 1:
            return top["subs"][0]["name"]
        return "General"

    def canon_sub(self, main, sub):
        top = self.by_code.get(main)
        if not sub:
            return self.default_sub(main)
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
        """Return (main, sub, minor, how) or None."""
        tag = tag.strip()
        if not tag:
            return None
        hit = self.tag_map.get(tag.lower())
        if hit:
            main = hit["main"].upper()
            return main, self.canon_sub(main, hit.get("sub")), hit.get("minor") or tag, "tag_map.json"
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
                best, best_score = (top["code"], self.default_sub(top["code"]), tag), s
        return (best[0], best[1], best[2], "auto-match") if best else None


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
    month = parse_month(b["meta"].get("month")) or parse_month(defaults.get("month")) or file_month

    if not question and not passage:
        problems.append("no QUESTION or TEXT found")
    if len(options) < 2:
        problems.append("needs at least two options starting 'A. ', 'B. ' ... (note: TEXT: must come BEFORE QUESTION:)")
    if not answer:
        problems.append("missing or unreadable ANSWER")
    elif answer not in options:
        problems.append(f"ANSWER {answer} is not one of the options {sorted(options)}")
    if not month:
        problems.append("month unknown")
    if problems:
        preview = re.sub(r"<[^>]+>", " ", question or passage)
        preview = re.sub(r"\s+", " ", preview).strip()[:80]
        report["skipped"].append({"where": where, "month": month, "reason": "; ".join(problems), "preview": preview})
        return None

    # ---- categories + types --------------------------------------------
    tag_text = b["tag"].strip()
    cat_pieces, tag_types = split_tag(tag_text)
    cats, seen_cat = [], set()

    def add_cat(main, sub, minor):
        key = (main, sub, minor)
        if key not in seen_cat:
            seen_cat.add(key)
            cats.append({"main": main, "sub": sub, "minor": minor})

    explicit_main = (b["meta"].get("main") or "").strip().upper()
    if explicit_main:
        if explicit_main not in tax.by_code:
            report["warnings"].append((where, f"MAIN '{explicit_main}' is not a known topic code"))
        add_cat(explicit_main,
                tax.canon_sub(explicit_main, (b["meta"].get("sub") or "").strip()),
                (b["meta"].get("minor") or "").strip() or (cat_pieces[0] if cat_pieces else "General"))

    unmatched = []
    for piece in cat_pieces:
        mapped = tax.map_tag(piece)
        if mapped:
            main, sub, minor, how = mapped
            if (b["meta"].get("minor") or "").strip() and not explicit_main and not cats:
                minor = b["meta"]["minor"].strip()
            add_cat(main, sub, minor)
            if how == "auto-match":
                report["auto"].setdefault(piece, f"{main} > {sub} > {minor}")
        else:
            unmatched.append(piece)

    unmapped_key = None
    if not cats:
        unmapped_key = (cat_pieces[0] if cat_pieces else "(no TAG)")
        add_cat(OTHER_CODE, OTHER_SUB, cat_pieces[0] if cat_pieces else "Untagged")
    else:
        for piece in unmatched:
            report["warnings"].append((where, f"category '{piece}' matched no topic (question is still filed under "
                                              f"{cats[0]['main']}). Add '{piece}' to data/tag_map.json."))

    explicit_type = [norm_type(x) for x in re.split(r"[;,]", b["meta"].get("type", "")) if x.strip()]
    if explicit_type and not all(explicit_type):
        report["warnings"].append((where, f"TYPE '{b['meta'].get('type')}' has an unknown type "
                                          f"(use: {', '.join(QTYPES)})"))
        explicit_type = [t for t in explicit_type if t]
    types = dedupe(explicit_type) or tag_types or infer_types(passage, question)

    rec = {
        "month": month - 1,
        "main": cats[0]["main"], "sub": cats[0]["sub"], "minor": cats[0]["minor"],
        "cats": cats, "types": types, "tag": tag_text,
        "passage": passage, "question": question,
        "options": options, "answer": answer,
        "solution": to_paragraphs(b["solution"]),
    }
    digest = json.dumps([rec["month"], passage, question, options, answer], ensure_ascii=False)
    rec["id"] = hashlib.sha1(digest.encode("utf-8")).hexdigest()[:10]
    rec["_unmapped"] = unmapped_key
    return rec


# --------------------------------------------------------------------------
# encryption (optional)
# --------------------------------------------------------------------------
def encrypt_text(text, key_b64):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        sys.exit("::error::GA_CONTENT_KEY is set but the 'cryptography' package is missing. "
                 "Run: pip install cryptography")
    key = base64.b64decode(key_b64.strip())
    if len(key) != 32:
        sys.exit("::error::GA_CONTENT_KEY must be base64 of exactly 32 bytes (use GA Tool > Show content key).")
    nonce = os.urandom(12)
    data = AESGCM(key).encrypt(nonce, text.encode("utf-8"), None)   # ciphertext || 16-byte tag
    return {"v": 1, "alg": "AES-256-GCM",
            "iv": base64.b64encode(nonce).decode(), "data": base64.b64encode(data).decode()}


def main():
    ap = argparse.ArgumentParser(description="Build the question bank from MCQ text files")
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
    records, seen_ids, missing_month, dup_count = [], set(), [], 0

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
                dup_count += 1
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
    for r in out:
        for k in ("passage", "solution", "tag"):
            if not r[k]:
                del r[k]

    # ---- validity report (per month) ------------------------------------
    months = {str(m): {"valid": 0, "invalid": 0} for m in range(1, 13)}
    months["unknown"] = {"valid": 0, "invalid": 0}
    type_counts = {t: 0 for t in QTYPES}
    for r in out:
        months[str(r["month"] + 1)]["valid"] += 1
        for t in r["types"]:
            type_counts[t] += 1
    for s in report["skipped"]:
        months[str(s["month"]) if s["month"] else "unknown"]["invalid"] += 1
    bank_report = {
        "months": months,
        "types": type_counts,
        "valid": len(out),
        "invalid": len(report["skipped"]),
        "duplicates": dup_count,
        "invalidList": [{"file": s["where"][0], "line": s["where"][1], "month": s["month"],
                         "reason": s["reason"], "preview": s["preview"]} for s in report["skipped"]][:200],
        "unmappedTags": report["unmapped"],
    }
    bundle = {"built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "questions": out, "report": bank_report}
    text = json.dumps(bundle, ensure_ascii=False, indent=1)

    out_path = Path(args.out)
    key = os.environ.get("GA_CONTENT_KEY", "").strip()
    if key:
        enc_path = out_path.with_name(out_path.stem + ".enc.json")
        enc_path.write_text(json.dumps(encrypt_text(text, key)), encoding="utf-8")
        if out_path.exists():
            out_path.unlink()
        written = f"{enc_path} (ENCRYPTED; plain questions.json removed)"
    else:
        out_path.write_text(text, encoding="utf-8")
        enc = out_path.with_name(out_path.stem + ".enc.json")
        if enc.exists():
            enc.unlink()
        written = str(out_path)

    # ---- console report --------------------------------------------------
    print(f"\n✅ Wrote {len(out)} valid questions to {written}")
    per = [f"{MONTH_ABBR[int(m)-1]}={v['valid']}" + (f"(+{v['invalid']} invalid)" if v["invalid"] else "")
           for m, v in months.items() if m != "unknown" and (v["valid"] or v["invalid"])]
    if per:
        print("   Per month: " + ", ".join(per))
    print("   Types: " + ", ".join(f"{t}={n}" for t, n in type_counts.items()))
    if report["auto"]:
        print("\nℹ️  Categories matched automatically (add to data/tag_map.json to override):")
        for tag, dest in report["auto"].items():
            print(f"   '{tag}'  ->  {dest}")
    for tag, n in report["unmapped"].items():
        gh_warn(f"Category '{tag}' ({n} question(s)) is not in data/tag_map.json and matched no topic - "
                f"filed under 'Other / Unsorted'. Add it to data/tag_map.json.")
    for (path, line), msg in report["warnings"]:
        gh_warn(msg, path, line)
    for s in report["skipped"]:
        gh_warn(f"Question INVALID and skipped - {s['reason']}", s["where"][0], s["where"][1])
    if report["skipped"]:
        print(f"\n⚠️  {len(report['skipped'])} question(s) were invalid and skipped (see warnings above).")


if __name__ == "__main__":
    main()
