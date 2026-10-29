/**
 * Bankers Alliance - GA Practice Tool : Google Sheets backend (Google Apps Script)
 * ---------------------------------------------------------------------------
 * Paste this whole file into  Extensions > Apps Script  of your Google Sheet,
 * then follow SETUP.md.  No server, no hosting, no cost.
 *
 * What it does
 *   - Member login (ID + password).  Passwords are stored ONLY as salted hashes
 *     in the "Members" sheet.  Nothing secret is ever put in the website's code.
 *   - Sync (mirror) of each member's results / saved questions to the Sheet.
 *   - Admin analytics (all members, all quizzes, question difficulty, reports).
 *   - Optional: hands the content key to logged-in members only, so the
 *     encrypted question bank can only be opened after login.
 *
 * Sheets created automatically:
 *   Members | Results | Attempts | UserData | Reports
 */

var SHEET_MEMBERS = 'Members', SHEET_RESULTS = 'Results', SHEET_ATTEMPTS = 'Attempts',
    SHEET_USERDATA = 'UserData', SHEET_REPORTS = 'Reports';

var H_MEMBERS  = ['ID', 'Name', 'Password (type here - it is secured automatically)', 'Role', 'Status',
                  'PassHash', 'Salt', 'Created', 'LastLogin', 'Logins'];
var H_RESULTS  = ['QuizID', 'Time', 'UserID', 'Name', 'Quiz', 'Mode', 'Month', 'Total', 'Right', 'Wrong',
                  'Skipped', 'Score', 'Percent', 'Accuracy', 'TimeSecs', 'NegMarking', 'Detail'];
var H_ATTEMPTS = ['QuizID', 'Time', 'UserID', 'QuestionID', 'QMonth', 'Category', 'Type', 'Selected', 'Result', 'TimeSecs'];
var H_USERDATA = ['UserID', 'Key', 'Value', 'UpdatedAt'];
var H_REPORTS  = ['Time', 'UserID', 'QuestionID', 'QMonth', 'Note', 'Quiz'];

var MC = { ID: 1, NAME: 2, PASS: 3, ROLE: 4, STATUS: 5, HASH: 6, SALT: 7, CREATED: 8, LAST: 9, LOGINS: 10 };

var HASH_ROUNDS = 100;      // password hashing rounds
var TOKEN_HOURS = 12;       // login lasts this long (page refresh still needs a fresh login)
var MAX_FAILS = 5;          // wrong passwords allowed ...
var LOCK_MINUTES = 15;      // ... before the ID is locked for this long
var MAX_DETAIL_CHARS = 45000;
var MAX_ATTEMPT_ROWS = 2000;

/* ======================================================================
   Entry points
   ====================================================================== */
function doPost(e) {
  var out;
  try {
    var req = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    out = route_(req);
  } catch (err) {
    console.error(err && err.stack ? err.stack : err);
    out = { ok: false, code: 'server', error: 'Server error. Please try again.' };
  }
  return json_(out);
}

function doGet() {
  return json_({ ok: true, service: 'GA Practice Tool backend', time: Date.now() });
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function route_(req) {
  switch (req.action) {
    case 'login':          return login_(req);
    case 'pull':           return pull_(req);
    case 'push':           return push_(req);
    case 'changePassword': return changePassword_(req);
    case 'adminStats':     return adminStats_(req);
    case 'adminResult':    return adminResult_(req);
    default:               return { ok: false, code: 'bad', error: 'Unknown request.' };
  }
}

/* ======================================================================
   Small helpers
   ====================================================================== */
function ss_() { return SpreadsheetApp.getActiveSpreadsheet(); }

function sheet_(name, headers) {
  var s = ss_().getSheetByName(name);
  if (!s) {
    s = ss_().insertSheet(name);
    s.getRange(1, 1, 1, headers.length).setValues([headers]);
    s.setFrozenRows(1);
  }
  return s;
}

function norm_(id) { return String(id == null ? '' : id).trim().toLowerCase(); }
function str_(v) { return String(v == null ? '' : v); }
function num_(v) { var n = Number(v); return isFinite(n) ? n : 0; }
function ms_(v) {
  if (v instanceof Date) return v.getTime();
  var n = Number(v); if (isFinite(n) && n > 0) return n;
  var t = Date.parse(v); return isFinite(t) ? t : 0;
}

function toHex_(bytes) {
  var s = '';
  for (var i = 0; i < bytes.length; i++) { var b = bytes[i] & 0xff; s += (b < 16 ? '0' : '') + b.toString(16); }
  return s;
}
function sha256Hex_(str) {
  return toHex_(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, str, Utilities.Charset.UTF_8));
}
function hashPassword_(salt, pw) {
  var h = sha256Hex_(salt + ':' + pw);
  for (var i = 0; i < HASH_ROUNDS; i++) h = sha256Hex_(h + salt + pw);
  return h;
}
function newSalt_() {
  return Utilities.getUuid().replace(/-/g, '') + Utilities.getUuid().replace(/-/g, '').slice(0, 8);
}
function safeEq_(a, b) {
  a = String(a); b = String(b);
  if (a.length !== b.length) return false;
  var r = 0;
  for (var i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

/* ---------- signed login tokens (stateless) ---------- */
function secret_() {
  var p = PropertiesService.getScriptProperties();
  var s = p.getProperty('TOKEN_SECRET');
  if (!s) { s = Utilities.getUuid() + Utilities.getUuid() + Utilities.getUuid(); p.setProperty('TOKEN_SECRET', s); }
  return s;
}
function signToken_(payload) {
  var body = Utilities.base64EncodeWebSafe(JSON.stringify(payload));
  var sig = Utilities.base64EncodeWebSafe(Utilities.computeHmacSha256Signature(body, secret_()));
  return body + '.' + sig;
}
function readToken_(token) {
  if (!token || typeof token !== 'string') return null;
  var parts = token.split('.');
  if (parts.length !== 2) return null;
  var expect = Utilities.base64EncodeWebSafe(Utilities.computeHmacSha256Signature(parts[0], secret_()));
  if (!safeEq_(expect, parts[1])) return null;
  var data;
  try { data = JSON.parse(Utilities.newBlob(Utilities.base64DecodeWebSafe(parts[0])).getDataAsString()); }
  catch (e) { return null; }
  if (!data || !data.id || !data.exp || data.exp < Date.now()) return null;
  return data;
}

/* ---------- members ---------- */
function readMembers_() {
  var s = sheet_(SHEET_MEMBERS, H_MEMBERS);
  var last = s.getLastRow();
  if (last < 2) return [];
  var vals = s.getRange(2, 1, last - 1, H_MEMBERS.length).getValues();
  var out = [];
  for (var i = 0; i < vals.length; i++) {
    var v = vals[i];
    if (norm_(v[MC.ID - 1]) === '') continue;
    out.push({
      row: i + 2, id: str_(v[MC.ID - 1]).trim(), key: norm_(v[MC.ID - 1]), name: str_(v[MC.NAME - 1]).trim(),
      pass: str_(v[MC.PASS - 1]), role: str_(v[MC.ROLE - 1]).trim().toLowerCase() === 'admin' ? 'admin' : 'member',
      status: str_(v[MC.STATUS - 1]).trim().toLowerCase() || 'active',
      hash: str_(v[MC.HASH - 1]), salt: str_(v[MC.SALT - 1]),
      created: ms_(v[MC.CREATED - 1]), last: ms_(v[MC.LAST - 1]), logins: num_(v[MC.LOGINS - 1])
    });
  }
  return out;
}
function findMember_(id) {
  var key = norm_(id);
  var all = readMembers_();
  for (var i = 0; i < all.length; i++) if (all[i].key === key) return all[i];
  return null;
}

/** Hash any password typed into column C (rows from..to) and clear the plain text. */
function secureRows_(from, to) {
  var s = sheet_(SHEET_MEMBERS, H_MEMBERS);
  var last = Math.min(to, s.getLastRow());
  var done = 0;
  for (var r = Math.max(from, 2); r <= last; r++) {
    var row = s.getRange(r, 1, 1, H_MEMBERS.length).getValues()[0];
    var id = str_(row[MC.ID - 1]).trim();
    var pw = str_(row[MC.PASS - 1]);
    if (!id || pw === '') continue;
    var salt = newSalt_();
    row[MC.ID - 1] = id;
    row[MC.PASS - 1] = '';
    row[MC.SALT - 1] = salt;
    row[MC.HASH - 1] = hashPassword_(salt, pw);
    if (!str_(row[MC.ROLE - 1]).trim()) row[MC.ROLE - 1] = 'member';
    if (!str_(row[MC.STATUS - 1]).trim()) row[MC.STATUS - 1] = 'active';
    if (!row[MC.CREATED - 1]) row[MC.CREATED - 1] = new Date();
    if (!str_(row[MC.NAME - 1]).trim()) row[MC.NAME - 1] = id;
    s.getRange(r, 1, 1, H_MEMBERS.length).setValues([row]);
    done++;
  }
  return done;
}

function lockWrite_(fn) {
  var lock = LockService.getScriptLock();
  lock.waitLock(25000);
  try { return fn(); } finally { lock.releaseLock(); }
}

/* ======================================================================
   login
   ====================================================================== */
function login_(req) {
  var key = norm_(req.id), pw = str_(req.password);
  if (!key || !pw) return { ok: false, code: 'auth', error: 'Enter your ID and password.' };

  var cache = CacheService.getScriptCache(), ck = 'lf:' + key;
  var rec = null;
  try { rec = JSON.parse(cache.get(ck) || 'null'); } catch (e) { rec = null; }
  if (rec && rec.until && rec.until > Date.now()) {
    var mins = Math.max(1, Math.ceil((rec.until - Date.now()) / 60000));
    return { ok: false, code: 'locked', error: 'Too many wrong attempts. Try again in ' + mins + ' minute(s).' };
  }

  var m = findMember_(key), good = false;
  if (m && m.status === 'active') {
    if (m.hash) {
      good = safeEq_(hashPassword_(m.salt, pw), m.hash);
    } else if (m.pass !== '') {                       // typed password that was not secured yet
      good = safeEq_(m.pass, pw);
      if (good) lockWrite_(function () { secureRows_(m.row, m.row); });
    }
  }

  if (!good) {
    var n = (rec && rec.n ? rec.n : 0) + 1;
    var next = { n: n };
    if (n >= MAX_FAILS) next = { n: 0, until: Date.now() + LOCK_MINUTES * 60000 };
    cache.put(ck, JSON.stringify(next), LOCK_MINUTES * 60);
    return { ok: false, code: 'auth', error: 'Invalid ID or password, or the account is disabled.' };
  }
  cache.remove(ck);

  var s = sheet_(SHEET_MEMBERS, H_MEMBERS);
  s.getRange(m.row, MC.LAST).setValue(new Date());
  s.getRange(m.row, MC.LOGINS).setValue(m.logins + 1);

  var exp = Date.now() + TOKEN_HOURS * 3600 * 1000;
  var contentKey = PropertiesService.getScriptProperties().getProperty('CONTENT_KEY') || null;
  return {
    ok: true, id: m.id, name: m.name || m.id, role: m.role, exp: exp,
    token: signToken_({ id: m.key, exp: exp }), contentKey: contentKey, serverTime: Date.now()
  };
}

/** Verify token AND that the member still exists and is active. */
function auth_(token, needAdmin) {
  var t = readToken_(token);
  if (!t) return { ok: false, res: { ok: false, code: 'expired', error: 'Session expired. Please log in again.' } };
  var m = findMember_(t.id);
  if (!m || m.status !== 'active') return { ok: false, res: { ok: false, code: 'expired', error: 'Account not available.' } };
  if (needAdmin && m.role !== 'admin') return { ok: false, res: { ok: false, code: 'forbidden', error: 'Admins only.' } };
  return { ok: true, member: m };
}

/* ======================================================================
   pull : everything this member has stored in the Sheet
   ====================================================================== */
function resultFromRow_(v) {
  var detail = {};
  try { detail = JSON.parse(str_(v[16]) || '{}'); } catch (e) { detail = {}; }
  return {
    qid: str_(v[0]), ts: ms_(v[1]), uid: str_(v[2]), name: str_(v[3]), label: str_(v[4]), mode: str_(v[5]),
    month: v[6] === '' ? null : num_(v[6]) - 1, total: num_(v[7]), right: num_(v[8]), wrong: num_(v[9]),
    skipped: num_(v[10]), score: num_(v[11]), pct: num_(v[12]), acc: num_(v[13]), secs: num_(v[14]),
    neg: str_(v[15]).toLowerCase() === 'true' || v[15] === true, detail: detail
  };
}

function pull_(req) {
  var a = auth_(req.token); if (!a.ok) return a.res;
  var uid = a.member.key;
  var results = [];
  var rs = sheet_(SHEET_RESULTS, H_RESULTS), rl = rs.getLastRow();
  if (rl >= 2) {
    var vals = rs.getRange(2, 1, rl - 1, H_RESULTS.length).getValues();
    for (var i = 0; i < vals.length; i++) if (norm_(vals[i][2]) === uid) results.push(resultFromRow_(vals[i]));
  }
  results.sort(function (x, y) { return y.ts - x.ts; });
  results = results.slice(0, 300);

  var kv = {};
  var us = sheet_(SHEET_USERDATA, H_USERDATA), ul = us.getLastRow();
  if (ul >= 2) {
    var uv = us.getRange(2, 1, ul - 1, H_USERDATA.length).getValues();
    for (var j = 0; j < uv.length; j++) {
      if (norm_(uv[j][0]) !== uid) continue;
      try { kv[str_(uv[j][1])] = { v: JSON.parse(str_(uv[j][2]) || 'null'), ts: num_(uv[j][3]) }; } catch (e) { /* skip */ }
    }
  }
  return { ok: true, results: results, kv: kv, serverTime: Date.now() };
}

/* ======================================================================
   push : results, saved questions, flags (idempotent - safe to resend)
   ====================================================================== */
function push_(req) {
  var a = auth_(req.token); if (!a.ok) return a.res;
  var m = a.member, ops = req.ops;
  if (!Array.isArray(ops)) return { ok: false, code: 'bad', error: 'Nothing to save.' };
  if (ops.length > 40) ops = ops.slice(0, 40);

  return lockWrite_(function () {
    var applied = { results: 0, kv: 0, reports: 0 };

    var rs = sheet_(SHEET_RESULTS, H_RESULTS), rl = rs.getLastRow();
    var seen = {};
    if (rl >= 2) {
      var ids = rs.getRange(2, 1, rl - 1, 1).getValues();
      for (var i = 0; i < ids.length; i++) seen[str_(ids[i][0])] = true;
    }

    for (var k = 0; k < ops.length; k++) {
      var op = ops[k] || {}, d = op.data || {};
      if (op.op === 'result') {
        var qid = str_(d.qid).slice(0, 60);
        if (!qid) continue;
        if (!seen[qid]) {
          var detail = JSON.stringify(d.detail || {});
          if (detail.length > MAX_DETAIL_CHARS) {
            var slim = d.detail || {}; slim.times = {};
            detail = JSON.stringify(slim).slice(0, MAX_DETAIL_CHARS);
          }
          rs.appendRow([
            qid, new Date(num_(d.ts) || Date.now()), m.id, m.name || m.id, str_(d.label).slice(0, 200), str_(d.mode).slice(0, 12),
            d.month === null || d.month === undefined || d.month === '' ? '' : num_(d.month) + 1,
            num_(d.total), num_(d.right), num_(d.wrong), num_(d.skipped),
            Math.round(num_(d.score) * 100) / 100, Math.round(num_(d.pct) * 100) / 100, Math.round(num_(d.acc) * 100) / 100,
            num_(d.secs), d.neg ? 'TRUE' : 'FALSE', detail
          ]);
          seen[qid] = true;

          var att = Array.isArray(d.att) ? d.att.slice(0, MAX_ATTEMPT_ROWS) : [];
          if (att.length) {
            var when = new Date(num_(d.ts) || Date.now()), rows = [];
            for (var q = 0; q < att.length; q++) {
              var r = att[q];
              rows.push([qid, when, m.id, str_(r[0]), r[1] === null || r[1] === undefined ? '' : num_(r[1]) + 1,
                         str_(r[2]).slice(0, 80), str_(r[3]).slice(0, 30), str_(r[4]).slice(0, 2),
                         str_(r[5]).slice(0, 6), num_(r[6])]);
            }
            var as = sheet_(SHEET_ATTEMPTS, H_ATTEMPTS);
            as.getRange(as.getLastRow() + 1, 1, rows.length, H_ATTEMPTS.length).setValues(rows);
          }
        }
        applied.results++;
      } else if (op.op === 'kv') {
        var key = str_(op.key).slice(0, 30);
        if (!/^(saved|mistakes)$/.test(key)) continue;
        var ts = num_(op.ts) || Date.now();
        var us = sheet_(SHEET_USERDATA, H_USERDATA), ul = us.getLastRow(), found = 0;
        if (ul >= 2) {
          var uv = us.getRange(2, 1, ul - 1, 4).getValues();
          for (var j = 0; j < uv.length; j++) if (norm_(uv[j][0]) === m.key && str_(uv[j][1]) === key) { found = j + 2; break; }
        }
        var text = JSON.stringify(op.value === undefined ? null : op.value).slice(0, 45000);
        if (found) {
          var cur = num_(us.getRange(found, 4).getValue());
          if (ts >= cur) us.getRange(found, 1, 1, 4).setValues([[m.id, key, text, ts]]);
        } else {
          us.appendRow([m.id, key, text, ts]);
        }
        applied.kv++;
      } else if (op.op === 'report') {
        var rp = sheet_(SHEET_REPORTS, H_REPORTS);
        rp.appendRow([new Date(num_(d.ts) || Date.now()), m.id, str_(d.qid).slice(0, 40),
                      d.qmonth === null || d.qmonth === undefined ? '' : num_(d.qmonth) + 1,
                      str_(d.note).slice(0, 300), str_(d.quiz).slice(0, 150)]);
        applied.reports++;
      }
    }
    return { ok: true, applied: applied };
  });
}

/* ======================================================================
   change own password
   ====================================================================== */
function changePassword_(req) {
  var a = auth_(req.token); if (!a.ok) return a.res;
  var m = a.member, oldPw = str_(req.oldPassword), newPw = str_(req.newPassword);
  if (newPw.length < 6) return { ok: false, code: 'bad', error: 'New password must be at least 6 characters.' };
  var good = m.hash ? safeEq_(hashPassword_(m.salt, oldPw), m.hash) : (m.pass !== '' && safeEq_(m.pass, oldPw));
  if (!good) return { ok: false, code: 'auth', error: 'Current password is incorrect.' };
  return lockWrite_(function () {
    var s = sheet_(SHEET_MEMBERS, H_MEMBERS), salt = newSalt_();
    s.getRange(m.row, MC.PASS).setValue('');
    s.getRange(m.row, MC.SALT).setValue(salt);
    s.getRange(m.row, MC.HASH).setValue(hashPassword_(salt, newPw));
    return { ok: true };
  });
}

/* ======================================================================
   admin
   ====================================================================== */
function adminStats_(req) {
  var a = auth_(req.token, true); if (!a.ok) return a.res;
  var members = readMembers_(), byId = {};
  for (var i = 0; i < members.length; i++) {
    byId[members[i].key] = {
      id: members[i].id, name: members[i].name || members[i].id, role: members[i].role, status: members[i].status,
      lastLogin: members[i].last, logins: members[i].logins,
      quizzes: 0, sumPct: 0, right: 0, wrong: 0, secs: 0, lastQuiz: 0
    };
  }

  var rs = sheet_(SHEET_RESULTS, H_RESULTS), rl = rs.getLastRow(), results = [];
  var monthAgg = {}, totalQuizzes = 0, sumPct = 0;
  if (rl >= 2) {
    var vals = rs.getRange(2, 1, rl - 1, H_RESULTS.length).getValues();
    for (var j = 0; j < vals.length; j++) {
      var v = vals[j];
      var row = {
        qid: str_(v[0]), ts: ms_(v[1]), uid: str_(v[2]), name: str_(v[3]), label: str_(v[4]), mode: str_(v[5]),
        month: v[6] === '' ? null : num_(v[6]) - 1, total: num_(v[7]), right: num_(v[8]), wrong: num_(v[9]),
        skipped: num_(v[10]), score: num_(v[11]), pct: num_(v[12]), acc: num_(v[13]), secs: num_(v[14])
      };
      results.push(row);
      totalQuizzes++; sumPct += row.pct;
      var u = byId[norm_(row.uid)];
      if (u) { u.quizzes++; u.sumPct += row.pct; u.right += row.right; u.wrong += row.wrong; u.secs += row.secs; u.lastQuiz = Math.max(u.lastQuiz, row.ts); }
      var mk = row.month === null ? -1 : row.month;           // -1 = quizzes over "All months"
      var ma = monthAgg[mk] || (monthAgg[mk] = { month: mk < 0 ? null : mk, quizzes: 0, sumPct: 0 });
      ma.quizzes++; ma.sumPct += row.pct;
    }
  }
  results.sort(function (x, y) { return y.ts - x.ts; });

  var qa = {}, attempts = 0;
  var as = sheet_(SHEET_ATTEMPTS, H_ATTEMPTS), al = as.getLastRow();
  if (al >= 2) {
    var av = as.getRange(2, 1, al - 1, H_ATTEMPTS.length).getValues();
    for (var k = 0; k < av.length; k++) {
      var res = str_(av[k][8]);
      if (res !== 'right' && res !== 'wrong') continue;
      var id = str_(av[k][3]);
      var o = qa[id] || (qa[id] = { qid: id, n: 0, right: 0, secs: 0 });
      o.n++; if (res === 'right') o.right++; o.secs += num_(av[k][9]); attempts++;
    }
  }
  var qlist = [];
  for (var q in qa) if (qa[q].n >= 3) qlist.push({ qid: qa[q].qid, attempts: qa[q].n, accuracy: qa[q].right / qa[q].n * 100, avgTime: qa[q].secs / qa[q].n });
  var hardest = qlist.slice().sort(function (x, y) { return (x.accuracy - y.accuracy) || (y.attempts - x.attempts); }).slice(0, 15);
  var slowest = qlist.slice().sort(function (x, y) { return y.avgTime - x.avgTime; }).slice(0, 15);

  var reports = [];
  var rp = sheet_(SHEET_REPORTS, H_REPORTS), pl = rp.getLastRow();
  if (pl >= 2) {
    var pv = rp.getRange(Math.max(2, pl - 99), 1, Math.min(100, pl - 1), H_REPORTS.length).getValues();
    for (var p = pv.length - 1; p >= 0; p--) reports.push({ ts: ms_(pv[p][0]), uid: str_(pv[p][1]), qid: str_(pv[p][2]),
                                                          qmonth: pv[p][3] === '' ? null : num_(pv[p][3]) - 1, note: str_(pv[p][4]), quiz: str_(pv[p][5]) });
  }

  var list = [], weekAgo = Date.now() - 7 * 86400000, active7 = 0;
  for (var key in byId) {
    var b = byId[key];
    if (b.lastLogin >= weekAgo) active7++;
    list.push({ id: b.id, name: b.name, role: b.role, status: b.status, lastLogin: b.lastLogin, logins: b.logins,
                quizzes: b.quizzes, avgPct: b.quizzes ? b.sumPct / b.quizzes : 0,
                accuracy: (b.right + b.wrong) ? b.right / (b.right + b.wrong) * 100 : 0, secs: b.secs, lastQuiz: b.lastQuiz });
  }
  var months = [];
  for (var mk2 in monthAgg) months.push({ month: monthAgg[mk2].month, quizzes: monthAgg[mk2].quizzes, avgPct: monthAgg[mk2].sumPct / monthAgg[mk2].quizzes });

  return {
    ok: true, generated: Date.now(),
    totals: { members: list.length, active7: active7, quizzes: totalQuizzes, avgPct: totalQuizzes ? sumPct / totalQuizzes : 0, attempts: attempts },
    members: list, results: results.slice(0, 3000), months: months, hardest: hardest, slowest: slowest, reports: reports
  };
}

function adminResult_(req) {
  var a = auth_(req.token, true); if (!a.ok) return a.res;
  var rs = sheet_(SHEET_RESULTS, H_RESULTS), rl = rs.getLastRow();
  if (rl < 2) return { ok: false, code: 'bad', error: 'Not found.' };
  var vals = rs.getRange(2, 1, rl - 1, H_RESULTS.length).getValues();
  for (var i = 0; i < vals.length; i++) if (str_(vals[i][0]) === str_(req.qid)) return { ok: true, result: resultFromRow_(vals[i]) };
  return { ok: false, code: 'bad', error: 'Not found.' };
}

/* ======================================================================
   Menu + triggers (run inside the Google Sheet)
   ====================================================================== */
function onOpen() {
  SpreadsheetApp.getUi().createMenu('GA Tool')
    .addItem('1. Set up sheets (first time)', 'setup')
    .addItem('Secure typed passwords now', 'securePasswords')
    .addItem('Show / create content key', 'showContentKey')
    .addToUi();
}

/** Simple trigger: as soon as a password is typed in column C it is hashed and the plain text removed. */
function onEdit(e) {
  try {
    if (!e || !e.range) return;
    var r = e.range;
    if (r.getSheet().getName() !== SHEET_MEMBERS) return;
    if (r.getColumn() > MC.PASS || r.getLastColumn() < MC.PASS) return;
    secureRows_(r.getRow(), r.getLastRow());
  } catch (err) { /* never block editing */ }
}

function setup() {
  sheet_(SHEET_MEMBERS, H_MEMBERS); sheet_(SHEET_RESULTS, H_RESULTS); sheet_(SHEET_ATTEMPTS, H_ATTEMPTS);
  sheet_(SHEET_USERDATA, H_USERDATA); sheet_(SHEET_REPORTS, H_REPORTS);
  var ms = ss_().getSheetByName(SHEET_MEMBERS);
  ms.getRange(2, MC.ID, 2000, 1).setNumberFormat('@');          // keep IDs like 007 as text
  ms.getRange(2, MC.PASS, 2000, 1).setNumberFormat('@');        // keep passwords like 000123 as text
  ms.getRange(2, MC.CREATED, 2000, 2).setNumberFormat('yyyy-mm-dd hh:mm');
  secret_();
  try { SpreadsheetApp.getUi().alert('Sheets are ready.\n\nNow add members in the "Members" sheet: type ID, Name, Password and (for you) Role = admin.'); } catch (e) { /* ignore */ }
}

function securePasswords() {
  var n = lockWrite_(function () { return secureRows_(2, sheet_(SHEET_MEMBERS, H_MEMBERS).getLastRow()); });
  try { SpreadsheetApp.getUi().alert(n + ' password(s) secured.'); } catch (e) { /* ignore */ }
  return n;
}

function showContentKey() {
  var p = PropertiesService.getScriptProperties(), key = p.getProperty('CONTENT_KEY');
  if (!key) {
    key = Utilities.base64Encode(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,
          Utilities.getUuid() + Utilities.getUuid() + Date.now() + Math.random(), Utilities.Charset.UTF_8));
    p.setProperty('CONTENT_KEY', key);
  }
  try {
    SpreadsheetApp.getUi().alert('CONTENT KEY (keep it private):\n\n' + key +
      '\n\nAdd it to GitHub:  Settings > Secrets and variables > Actions > New secret\nName: GA_CONTENT_KEY   Value: the key above.\n' +
      'Then re-run the "Build questions" action. Members receive this key automatically when they log in.');
  } catch (e) { /* ignore */ }
  return key;
}
