//+------------------------------------------------------------------+
//| CR_Journal.mqh - journal and pushes (SPEC 2.6). Owner: S0.        |
//|                                                                  |
//| One line per event: CR|<utc>|<EVENT>|<code>|k=v|...              |
//|   utc   = lab time of the event, integer UTC seconds             |
//|   code  = sleeve code, symbol base name, or "-"                   |
//|   doubles are written with DoubleToString(x, -16): 17 digits,    |
//|   an exact round trip; booleans 0/1; times integer seconds.      |
//| Lines go to Print (live) and to MQL5/Files/ClaudeRobot/          |
//| <yyyymmdd>.log (server date; files older than 30 days removed).  |
//| Lines written while the history is replayed carry rp=1: they go  |
//| to the file only, never to Print (a rebuild writes thousands of  |
//| them); the file is flushed once per timer pass (JrnFlush, the    |
//| harness only in tester mode), not line by line (review F9).      |
//| Pushes (French, ASCII): "Robot Claude : ..." with the hands'     |
//| limits (ClaudeMains.mq5:161-184): at most 2 a second and 5 a     |
//| minute, of which 2 are kept for urgent messages.                 |
//+------------------------------------------------------------------+
#ifndef CR_JOURNAL_MQH
#define CR_JOURNAL_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"

#define CR_JRN_KEEP_DAYS 30

string   CR_JRN_DIR = "ClaudeRobot";   // MQL5/Files/ClaudeRobot (a variable: "a" + "b" of two literals is not C++)

int      g_jrn_h = INVALID_HANDLE;
datetime g_jrn_day = 0;                // server date of the open file
bool     g_jrn_print = true;           // also Print each line (the harness turns it off)
bool     g_jrn_file = true;            // write the daily file
long     g_jrn_lines = 0;
datetime g_push_sec = 0, g_push_min = 0;
int      g_push_n = 0, g_push_m = 0;
long     g_push_sent = 0, g_push_dropped = 0;
long     g_jrn_file_errors = 0;          // file calls that failed (the journal still goes to Print)
bool     g_jrn_dirty = false;            // lines written since the last flush
bool     g_jrn_replay = false;           // the history is replayed (CR_Main's rebuild): rules push nothing meanwhile

string CR_REASON_NAME[11] = {"stop", "target", "time", "trail", "eod", "nofill", "skip", "gap", "void", "refused", "rule"};

string JT(const datetime t) { return IntegerToString((long)t); }
string JD(const double x) { return DoubleToString(x, -16); }
string JI(const long v) { return IntegerToString(v); }
string JB(const bool b) { return b ? "1" : "0"; }
string KV(const string k, const string v) { return "|" + k + "=" + v; }
string KD(const string k, const double v) { return "|" + k + "=" + JD(v); }
string KI(const string k, const long v) { return "|" + k + "=" + JI(v); }
string KT(const string k, const datetime v) { return "|" + k + "=" + JT(v); }
string KB(const string k, const bool v) { return "|" + k + "=" + JB(v); }

string JrnReason(const int r)
  {
   if(r < 0 || r > 10) return "none";
   return CR_REASON_NAME[r];
  }

string JrnCode(const int sl)
  {
   if(sl < 0 || sl >= g_nsl) return "-";
   return g_sl[sl].code;
  }

string JrnSymCode(const int sym)
  {
   if(sym < 0 || sym >= CR_NSYM) return "-";
   return g_sym[sym].base;
  }

// yyyymmdd of a server date
string JrnDayName(const datetime srv_day)
  {
   MqlDateTime d;
   TimeToStruct(srv_day, d);
   return IntegerToString(d.year * 10000 + d.mon * 100 + d.day);
  }

// remove the daily files older than CR_JRN_KEEP_DAYS days (names are yyyymmdd.log)
void JrnPurge(const datetime srv_day)
  {
   if(g_cfg.harness) return;                      // the harness keeps the whole journal
   string limit = JrnDayName(srv_day - CR_JRN_KEEP_DAYS * 86400);
   string found = "";
   long h = FileFindFirst(CR_JRN_DIR + "\\*.log", found);
   if(h == INVALID_HANDLE) return;
   do
     {
      if(StringLen(found) == 12 && CrStrCmp(StringSubstr(found, 0, 8), limit) < 0)
        {
         bool gone = FileDelete(CR_JRN_DIR + "\\" + found);
         if(!gone) g_jrn_file_errors++;
        }
     }
   while(FileFindNext(h, found));
   FileFindClose(h);
  }

void JrnClose()
  {
   if(g_jrn_h != INVALID_HANDLE) FileClose(g_jrn_h);
   g_jrn_h = INVALID_HANDLE;
   g_jrn_day = 0;
   g_jrn_dirty = false;
  }

void JrnOpenDay(const datetime srv_day)
  {
   JrnClose();
   if(!g_jrn_file) return;
   bool made = FolderCreate(CR_JRN_DIR);
   if(!made) g_jrn_file_errors++;
   string path = CR_JRN_DIR + "\\" + JrnDayName(srv_day) + ".log";
   g_jrn_h = FileOpen(path, FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ);
   if(g_jrn_h == INVALID_HANDLE) g_jrn_file_errors++;
   else
     {
      bool at_end = FileSeek(g_jrn_h, 0, SEEK_END);
      if(!at_end) g_jrn_file_errors++;
     }
   g_jrn_day = srv_day;
   JrnPurge(srv_day);
  }

void JrnInit()
  {
   g_jrn_print = !g_cfg.harness;                  // the harness reads the files; Print would double them in its log
   g_jrn_lines = 0;
   g_push_sec = 0;
   g_push_min = 0;
   g_push_n = 0;
   g_push_m = 0;
   JrnOpenDay(ClkDay(TimeTradeServer()));
  }

// the one writer: CR|<utc>|<EVENT>|<code><kv>
void JrnAt(const datetime utc, const int ev, const string code, const string kv)
  {
   string name = (ev >= 0 && ev < CR_EV_N) ? CR_EV_NAME[ev] : "EV" + IntegerToString(ev);
   string line = "CR|" + JT(utc) + "|" + name + "|" + code + kv;
   datetime d = ClkDay(TimeTradeServer());
   if(g_jrn_file && d != g_jrn_day) JrnOpenDay(d);
   if(g_jrn_h != INVALID_HANDLE)
     {
      FileWriteString(g_jrn_h, line + "\n");
      g_jrn_dirty = true;
     }
   int n = StringLen(kv);
   bool rp = (n >= 5 && StringSubstr(kv, n - 5) == "|rp=1");   // JrnRp always ends the line
   if(g_jrn_print && !rp) Print(line);
   g_jrn_lines++;
  }

// once per timer pass (and at the end of OnInit): the lines of the pass reach the file (live and tester builds; a harness
// replay outside tester mode never flushes, as before)
void JrnFlush()
  {
   if(!g_jrn_dirty || g_jrn_h == INVALID_HANDLE) return;
   g_jrn_dirty = false;
   if(g_cfg.tester || !g_cfg.harness) FileFlush(g_jrn_h);
  }

// an event stamped now (the server clock converted to UTC)
void Jrn(const int ev, const string code, const string kv) { JrnAt(ClkServerToUtc(TimeTradeServer()), ev, code, kv); }

// push notification with the hands' limits; returns false when it was dropped
bool JrnPush(const string msg, const bool urgent)
  {
   datetime now = TimeTradeServer();
   if(!g_cfg.push || g_cfg.tester) return true;
   if(now != g_push_sec)
     {
      g_push_sec = now;
      g_push_n = 0;
     }
   if(now - now % 60 != g_push_min)
     {
      g_push_min = now - now % 60;
      g_push_m = 0;
     }
   if(g_push_n >= 2 || g_push_m >= (urgent ? 5 : 3))
     {
      g_push_dropped++;
      return false;
     }
   g_push_n++;
   g_push_m++;
   bool sent = SendNotification("Robot Claude : " + msg);
   if(sent) g_push_sent++;
   else g_push_dropped++;
   return sent;
  }

// an ERROR line and an urgent push
void JrnError(const string code, const string what)
  {
   string w = what;
   StringReplace(w, "|", "/");
   Jrn(CR_EV_ERROR, code, KV("what", w));
   JrnPush("ERREUR " + code + " : " + w, true);
  }

// ---- the lines of the driver (CR_Main) -----------------------------------------------------------------------------
string JrnRp(const bool rp) { return rp ? "|rp=1" : ""; }

// DEC line of an order (every field: compare.py checks them against ref_lab.py's orders)
void JrnOrder(const CrOrder &o, const datetime when, const bool rp)
  {
   string kv = KV("what", "ord") + KI("oid", o.oid) + KI("side", o.side) + KI("et", o.etype) + KD("lv", o.level)
               + KD("lv2", o.level2) + KT("tf", o.t_from) + KT("tt", o.t_to) + KI("ax", o.after_exit_of)
               + KT("exp", o.expiry_excl) + KD("st", o.stop) + KD("sd", o.stop_dist) + KD("tr", o.trail) + KD("be", o.be)
               + KD("tg", o.target) + KD("td", o.target_dist) + KT("x", o.x_sched) + KB("xg", o.x_gap) + KT("xh", o.xh)
               + KD("xr", o.xh_r) + KI("ref", o.refuse) + KB("vle", o.void_le) + KI("grp", o.grp) + KT("at", when);
   JrnAt(o.dec != 0 ? o.dec : when, CR_EV_DEC, JrnCode(o.sleeve), kv + JrnRp(rp));
  }

void JrnExitOrder(const CrExit &e, const datetime when, const bool rp)
  {
   string kv = KV("what", "exit") + KI("oid", e.oid) + KT("tf", e.t_from) + KT("tt", e.t_to) + KT("at", when);
   JrnAt(e.dec != 0 ? e.dec : when, CR_EV_DEC, JrnCode(e.sleeve), kv + JrnRp(rp));
  }

void JrnDecRec(const CrDec &d, const datetime when, const bool rp)
  {
   string what = (d.what == CR_DEC_SKIP_K1) ? "skip" : "info";
   string kv = KV("what", what) + KI("side", d.side) + KD("v1", d.v1) + KD("v2", d.v2) + KT("at", when);
   if(d.what == CR_DEC_SKIP_K1) kv = kv + KV("skip", "K1") + KD("riskbp", d.v1) + KD("T", d.v2);
   JrnAt(d.dec != 0 ? d.dec : when, CR_EV_DEC, JrnCode(d.sleeve), kv + JrnRp(rp));
  }

// PFILL, PEXIT, PSTOP, PREVISE, PVOID, PREFUSE, HOLD (SPEC 2.5)
void JrnPaper(const CrPEvent &e, const bool rp)
  {
   string kv = KI("oid", e.oid) + KI("side", e.side) + KT("bar", e.bar) + KD("px", e.px) + KD("stop", e.stop)
               + KD("st0", e.init_stop) + KT("x", e.x);
   if(e.ev == CR_EV_PEXIT || e.ev == CR_EV_PREVISE || e.ev == CR_EV_PVOID || e.ev == CR_EV_PREFUSE)
      kv = kv + KV("reason", JrnReason(e.reason));
   kv = kv + KI("s_raw", e.s_raw) + KD("s_paper", e.s_paper);
   JrnAt(e.t, e.ev, JrnCode(e.sleeve), kv + JrnRp(rp));
  }

// the bar dump of the debug build (CR_DEBUG): one line per fed bar
void JrnBar(const CrBar &b)
  {
   string kv = KD("bo", b.bo) + KD("bh", b.bh) + KD("bl", b.bl) + KD("bc", b.bc) + KD("ao", b.ao) + KD("ah", b.ah)
               + KD("al", b.al) + KD("ac", b.ac) + KI("s_raw", b.s_raw);
   JrnAt(b.t, CR_EV_BAR, JrnSymCode(b.sym), kv);
  }
#endif
