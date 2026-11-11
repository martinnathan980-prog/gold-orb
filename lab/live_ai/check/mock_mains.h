// A working imitation of the MetaTrader 5 terminal + broker, just large enough to RUN the real code of
// ClaudeMains.mq5 here (translated by to_cpp.py, compiled with g++) and to drive it with the real Python bridge
// (pont.py). Used by check/test_mains.py. It is NOT MetaTrader: see "What this cannot prove" in test_mains.py.
//
// Everything lives under the directory given by env MOCK_FILES (it stands for <terminal>/MQL5/Files):
//   claude/...            what the EA itself creates (the bridge)
//   _mock/control.txt     the fake world, re-read on every loop (written by the test), lines key=value:
//                           seq=N                    echoed in ack.txt once a full loop has run with this control
//                           server_offset=S          TimeTradeServer() = real clock + S seconds  (TimeGMT() = real clock)
//                           price.<symbol>=bid,ask
//                           sym.<symbol>.<prop>=v    stops_level freeze_level trade_mode order_mode vol_min vol_step vol_max
//                                                    tick_value tick_value_loss leverage
//                                                    tick_age (the last tick is that many seconds old)
//                                                    slip (a new position is filled that much worse than the quote)
//                           retcode=R                every trade request is answered with R (0 = normal behaviour)
//                           retcode_open / retcode_close / retcode_sltp = R      same, per kind of request
//                           ordersend_true=1         OrderSend returns true even with a failing retcode
//                           terminal_trade_allowed=0 the "Algo Trading" button is off (also mql_/account_trade_allowed,
//                                                    account_trade_expert)
//                           connected=0              the terminal has no connection yet: balance / equity / margin read 0
//                                                    (ASSUMPTION, not verified on a real terminal), requests answer 10031
//                           lag=1                    the terminal's list of positions is refreshed only after the running
//                                                    handler has returned (as OrderSend may return before the terminal
//                                                    has processed the trade events)
//                           hold=1                   OnTimer is not called (the real timer only fires once a second)
//                           drop_sl=1                the broker opens the position but does not keep the stop of the order
//                           sl_magic0=1              the deals the broker makes itself (stop, target) carry magic number 0
//                           race=1                   the broker closes the position (as its stop would) and the terminal's
//                                                    list is refreshed between the EA's own look at the position and the
//                                                    look CTrade takes before sending a close / modify
//                           stopped=1                IsStopped() is true: CTrade gives up before sending anything
//                           margin_mode=0            netting account (2 = hedging, the default)
//                           timer_fail=1             EventSetTimer fails
//                           ordersend_delay_ms=N     OrderSend blocks that long (network round trip)
//                           do.<n>=open SYM buy|sell VOL SL TP MAGIC [COMMENT]   a position opened outside the EA
//                           do.<n>=close TICKET | balance AMOUNT                 (each n is executed once, in order)
//                           do.<n>=sltp TICKET SL TP     stop / target changed outside the EA (by hand)
//                           do.<n>=reticket TICKET       the server gives the position a new ticket (same identifier)
//   _mock/state.txt       the broker: balance, positions, deals (kept across restarts of the binary, as a broker does)
//   _mock/globals.txt     the terminal's global variables: written on GlobalVariablesFlush() and at a clean exit only
//                         (the real terminal saves them when it closes; env MOCK_GV_SAVE=always saves on every change)
//   _mock/log.txt         Print / Alert / SendNotification / Comment / every trade request and its answer /
//                         "PASS n" for every OnTimer call that answered n orders (n > 0)
//   _mock/ack.txt         seq of the last control fully applied   |   _mock/stop : the binary ends (OnDeinit) when it appears
// Env: MOCK_MISSING=a,b  symbols the broker does not have; MOCK_CRLF_ONLY=1  FileReadString only ends a line at "\r\n";
//      MOCK_INPUT_<InpName>=value  another value for an input (test_mains.py rewrites the inputs of the TRANSLATED file).
// CTrade is a transcription of the Standard Library's Trade.mqh (2000-2025) for the methods the EA uses.
#pragma once
#include "mql5_shim.h"
#include <algorithm>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <map>
#include <sstream>
#include <type_traits>
#include <filesystem>
#include <fnmatch.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <unistd.h>

int OnInit();
void OnDeinit(const int reason);
void OnTimer();
void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result);

// ------------------------------------------------------------------ inputs (see test_mains.py: build)
template <typename T> T mock_input(const char *name, T def)
  {
   const char *e = getenv((string("MOCK_INPUT_") + name).c_str());
   if(!e) return def;
   if constexpr(std::is_same_v<T, string>) return string(e);
   else if constexpr(std::is_same_v<T, bool>) return strcmp(e, "true") == 0 || strcmp(e, "1") == 0;
   else if constexpr(std::is_floating_point_v<T>) return (T)atof(e);
   else return (T)atoll(e);
  }

// ------------------------------------------------------------------ the fake world
const uint MK_REJECT = 10006, MK_PLACED = 10008, MK_DONE = 10009, MK_DONE_PARTIAL = 10010, MK_ERROR = 10011, MK_INVALID = 10013,
           MK_INVALID_VOLUME = 10014, MK_INVALID_STOPS = 10016, MK_TRADE_DISABLED = 10017, MK_MARKET_CLOSED = 10018,
           MK_NO_MONEY = 10019, MK_NO_CHANGES = 10025, MK_CLIENT_DISABLES_AT = 10027, MK_INVALID_FILL = 10030,
           MK_INVALID_ORDER = 10035, MK_POSITION_CLOSED = 10036, MK_CLOSE_ONLY = 10044;

struct MkSym
  {
   string name;
   int    digits;
   double point, tick_size, tick_value, tick_value_loss, contract, vol_min, vol_step, vol_max;
   long   stops_level, freeze_level, trade_mode, order_mode;
   double leverage;        // margin of 1 lot = notional / leverage
   bool   forex;           // margin on the base currency (else on price x contract, in USD)
   double base_eur;        // forex: EUR for one unit of the base currency
   string ccy_base, ccy_profit;
   double commission_lot, fee_lot;   // charged on every deal, in EUR per lot
   double bid, ask;
   double swap_long, swap_short;
   bool   hidden;
   long   tick_age;        // age of the last tick, seconds
   double slip;            // a new position is filled that much worse than the quote
  };
static const double MK_USD_EUR = 0.8621;
static const MkSym MK_DEFAULTS[] = {
   //  name       dg  point    tick     tick_val   tv_loss    contract  vmin  vstep vmax  stops fr mode om   lev  forex base_eur  base   profit comm  fee    bid        ask
   {"EURUSD.r", 5, 0.00001, 0.00001, 0.8621,    0.8625,    100000.0, 0.01, 0.01, 100.0, 0,   0, 4, 127, 500, true,  1.0,    "EUR", "USD", 2.59, 0.0,   1.16000,   1.16002,   -7.10,  2.30, false},
   {"XAUUSD.r", 2, 0.01,    0.01,    0.8621,    0.8625,    100.0,    0.01, 0.01, 100.0, 0,   0, 4, 127, 500, false, 0.0,    "XAU", "USD", 2.59, 0.0,   4080.10,   4080.23,   -62.89, 37.52, false},
   {"USDJPY.r", 3, 0.001,   0.001,   0.5561,    0.5565,    100000.0, 0.01, 0.01, 100.0, 0,   0, 4, 127, 500, true,  0.8621, "USD", "JPY", 2.59, 0.0,   155.000,   155.004,   9.80,   -21.40, false},
   {"BTCUSD",   2, 0.01,    0.01,    0.008621,  0.008625,  1.0,      0.01, 0.01, 50.0,  0,   0, 4, 127, 10,  false, 0.0,    "BTC", "USD", 0.0,  17.24, 100000.00, 100012.00, -30.0,  -30.0, false},
   {"ETHUSD",   2, 0.01,    0.01,    0.008621,  0.008625,  1.0,      0.10, 0.10, 500.0, 0,   0, 4, 127, 10,  false, 0.0,    "ETH", "USD", 0.0,  0.60,  3500.00,   3501.20,   -30.0,  -30.0, false},
   {"NAS100",   2, 0.01,    0.01,    0.008621,  0.008625,  1.0,      0.10, 0.10, 250.0, 100, 0, 4, 127, 200, false, 0.0,    "USD", "USD", 0.0,  0.0,   25000.00,  25001.50,  -4.90,  1.10, false},
   {"JPN225",   2, 0.01,    0.01,    0.005561,  0.005565,  1.0,      0.10, 0.10, 250.0, 0,   0, 4, 127, 200, false, 0.0,    "JPY", "JPY", 0.0,  0.0,   50000.00,  50008.00,  0.0,    0.0, false},
   {"US500",    2, 0.01,    0.01,    0.008621,  0.008625,  1.0,      0.10, 0.10, 250.0, 0,   0, 4, 127, 200, false, 0.0,    "USD", "USD", 0.0,  0.0,   6800.00,   6800.50,   0.0,    0.0, false},
   {"DE40",     2, 0.01,    0.01,    0.01,      0.01,      1.0,      0.10, 0.10, 250.0, 0,   0, 4, 127, 200, false, 0.0,    "EUR", "EUR", 0.0,  0.0,   24000.00,  24001.50,  0.0,    0.0, false},
   {"AAPL.US",  2, 0.01,    0.01,    0.008621,  0.008625,  1.0,      1.0,  1.0,  1000.0, 0,  0, 4, 127, 5,   false, 0.0,    "USD", "USD", 0.0,  0.0,   270.00,    270.10,    0.0,    0.0, false},
};
static const int MK_NSYM = (int)(sizeof MK_DEFAULTS / sizeof *MK_DEFAULTS);
static MkSym mk_sym[MK_NSYM];

struct MkPos { ulong ticket; string symbol; int type; double volume, price_open, sl, tp, swap; long magic, time; string comment; ulong ident; };
struct MkDeal
  {
   ulong  deal, order, position;
   long   time;
   string symbol;
   int    type, entry;      // type: 0 buy, 1 sell, 2 balance ; entry: 0 in, 1 out
   double volume, price, profit, swap, commission, fee;
   long   magic, reason;    // reason: 0 client, 3 expert, 4 sl, 5 tp
   string comment;
  };

static string mk_root;                         // MOCK_FILES
static std::vector<MkPos>  mk_pos, mk_view;    // at the broker / as the terminal's Position* functions see them
static std::vector<MkDeal> mk_deals;
static std::vector<int>    mk_hist;            // deals selected by HistorySelect
static double mk_balance = 1000.0;
static ulong  mk_next_order = 50001001, mk_next_deal = 40002001;
static long   mk_last_do = 0;
static std::map<string, double> mk_gv;
static bool   mk_gv_always = false, mk_crlf_only = false, mk_timer = false;
static ulong  mk_selected = 0;
static int    mk_pending_tx = 0;
static long   mk_loops = 0;
// control
static string mk_control_raw = "\x01";
static long   mk_seq = 0, mk_acked = -1;
static double mk_server_offset = 7200.0;
static long   mk_gmt_skew = 0;
static uint   mk_rc_all = 0, mk_rc_open = 0, mk_rc_close = 0, mk_rc_sltp = 0;
static bool   mk_send_true = false, mk_lag = false, mk_hold = false;
static int    mk_term_allowed = 1, mk_mql_allowed = 1, mk_acc_allowed = 1, mk_acc_expert = 1, mk_connected = 1;
static bool   mk_drop_sl = false, mk_sl_magic0 = false, mk_race = false, mk_stopped = false, mk_timer_fail = false;
static long   mk_margin_mode = 2, mk_send_delay_ms = 0;
static int    mk_answers = 0;                  // files moved into claude/res during the running handler
static std::map<long, string> mk_do;
// the single CTrade object of the EA (the shim's class has no data members)
static MqlTradeRequest mk_req = MqlTradeRequest();
static MqlTradeResult  mk_res = MqlTradeResult();
static ulong mk_magic = 0, mk_deviation = 10;
static ENUM_ORDER_TYPE_FILLING mk_filling = ORDER_FILLING_FOK;

static string mk_path(string name)
  {
   for(char &c : name)
      if(c == '\\') c = '/';
   return mk_root + "/" + name;
  }
static void mk_write(const string &rel, const string &text)
  {
   string p = mk_path(rel), t = p + ".tmp";
   FILE *f = fopen(t.c_str(), "wb");
   if(!f) return;
   fwrite(text.data(), 1, text.size(), f);
   fclose(f);
   rename(t.c_str(), p.c_str());
  }
static bool mk_read(const string &path, string &out)
  {
   FILE *f = fopen(path.c_str(), "rb");
   if(!f) return false;
   out.clear();
   char b[4096];
   size_t n;
   while((n = fread(b, 1, sizeof b, f)) > 0) out.append(b, n);
   fclose(f);
   return true;
  }
static string mk_flat(string s)
  {
   for(char &c : s)
      if(c == '\n' || c == '\r' || c == '|') c = ' ';
   return s;
  }
static void mk_log(const char *kind, const string &text)
  {
   static FILE *f = nullptr;
   if(!f) f = fopen(mk_path("_mock/log.txt").c_str(), "ab");
   if(!f) return;
   string t = text;
   for(size_t p = t.find('\n'); p != string::npos; p = t.find('\n', p + 2)) t.replace(p, 1, "\\n");
   fprintf(f, "%s\t%s\n", kind, t.c_str());
   fflush(f);
  }
static string mk_fmt(const char *fmt, ...)
  {
   char b[1024];
   va_list ap;
   va_start(ap, fmt);
   vsnprintf(b, sizeof b, fmt, ap);
   va_end(ap);
   return b;
  }
static double mk_real_now()
  {
   struct timeval tv;
   gettimeofday(&tv, nullptr);
   return (double)tv.tv_sec + tv.tv_usec / 1e6;
  }
static MkSym *mk_find(const string &name)
  {
   for(int i = 0; i < MK_NSYM; i++)
      if(!mk_sym[i].hidden && mk_sym[i].name == name) return &mk_sym[i];
   return nullptr;
  }
static std::vector<string> mk_split(const string &s, char sep)
  {
   std::vector<string> out;
   size_t a = 0;
   while(true)
     {
      size_t b = s.find(sep, a);
      out.push_back(s.substr(a, b == string::npos ? string::npos : b - a));
      if(b == string::npos) break;
      a = b + 1;
     }
   return out;
  }

// ------------------------------------------------------------------ broker state on disk
static void mk_save_state()
  {
   string s = mk_fmt("balance=%.2f\nnext_order=%lu\nnext_deal=%lu\nlast_do=%ld\n", mk_balance, mk_next_order, mk_next_deal, mk_last_do);
   for(const MkPos &p : mk_pos)
      s += mk_fmt("P|%lu|%s|%d|%.8g|%.10g|%.10g|%.10g|%.2f|%ld|%ld|", p.ticket, p.symbol.c_str(), p.type, p.volume, p.price_open, p.sl,
                  p.tp, p.swap, p.magic, p.time) + mk_flat(p.comment) + mk_fmt("|%lu", p.ident) + "\n";
   for(const MkDeal &d : mk_deals)
      s += mk_fmt("D|%lu|%lu|%lu|%ld|%s|%d|%d|%.8g|%.10g|%.2f|%.2f|%.2f|%.2f|%ld|%ld|", d.deal, d.order, d.position, d.time,
                  d.symbol.c_str(), d.type, d.entry, d.volume, d.price, d.profit, d.swap, d.commission, d.fee, d.magic, d.reason)
           + mk_flat(d.comment) + "\n";
   mk_write("_mock/state.txt", s);
  }
static void mk_load_state()
  {
   string raw;
   if(!mk_read(mk_path("_mock/state.txt"), raw)) return;
   for(const string &ln : mk_split(raw, '\n'))
     {
      if(ln.compare(0, 8, "balance=") == 0) mk_balance = atof(ln.c_str() + 8);
      else if(ln.compare(0, 11, "next_order=") == 0) mk_next_order = strtoul(ln.c_str() + 11, nullptr, 10);
      else if(ln.compare(0, 10, "next_deal=") == 0) mk_next_deal = strtoul(ln.c_str() + 10, nullptr, 10);
      else if(ln.compare(0, 8, "last_do=") == 0) mk_last_do = atol(ln.c_str() + 8);
      else if(ln.compare(0, 2, "P|") == 0)
        {
         std::vector<string> f = mk_split(ln, '|');
         if(f.size() < 12) continue;
         MkPos p = {strtoul(f[1].c_str(), nullptr, 10), f[2], atoi(f[3].c_str()), atof(f[4].c_str()), atof(f[5].c_str()), atof(f[6].c_str()),
                    atof(f[7].c_str()), atof(f[8].c_str()), atol(f[9].c_str()), atol(f[10].c_str()), f[11],
                    strtoul(f.size() > 12 ? f[12].c_str() : f[1].c_str(), nullptr, 10)};
         mk_pos.push_back(p);
        }
      else if(ln.compare(0, 2, "D|") == 0)
        {
         std::vector<string> f = mk_split(ln, '|');
         if(f.size() < 17) continue;
         MkDeal d = {strtoul(f[1].c_str(), nullptr, 10), strtoul(f[2].c_str(), nullptr, 10), strtoul(f[3].c_str(), nullptr, 10),
                     atol(f[4].c_str()), f[5], atoi(f[6].c_str()), atoi(f[7].c_str()), atof(f[8].c_str()), atof(f[9].c_str()),
                     atof(f[10].c_str()), atof(f[11].c_str()), atof(f[12].c_str()), atof(f[13].c_str()), atol(f[14].c_str()),
                     atol(f[15].c_str()), f[16]};
         mk_deals.push_back(d);
        }
     }
   mk_view = mk_pos;
  }
static void mk_gv_save()
  {
   string s;
   for(const auto &kv : mk_gv) s += kv.first + "=" + mk_fmt("%.17g", kv.second) + "\n";
   mk_write("_mock/globals.txt", s);
  }
static void mk_gv_load()
  {
   string raw;
   if(!mk_read(mk_path("_mock/globals.txt"), raw)) return;
   for(const string &ln : mk_split(raw, '\n'))
     {
      size_t p = ln.find('=');
      if(p != string::npos && p > 0) mk_gv[ln.substr(0, p)] = atof(ln.c_str() + p + 1);
     }
  }

// ------------------------------------------------------------------ clock
datetime TimeTradeServer() { return (datetime)std::floor(mk_real_now() + mk_server_offset); }
datetime TimeCurrent() { return TimeTradeServer(); }
datetime TimeGMT() { return (datetime)time(nullptr) + mk_gmt_skew; }
datetime TimeLocal() { return (datetime)time(nullptr); }
bool TimeToStruct(datetime dt, MqlDateTime &d)
  {
   time_t t = (time_t)dt;
   struct tm tm;
   gmtime_r(&t, &tm);
   d.year = tm.tm_year + 1900; d.mon = tm.tm_mon + 1; d.day = tm.tm_mday; d.hour = tm.tm_hour; d.min = tm.tm_min; d.sec = tm.tm_sec;
   d.day_of_week = tm.tm_wday; d.day_of_year = tm.tm_yday;
   return true;
  }
string TimeToString(datetime value, int mode)
  {
   MqlDateTime d;
   TimeToStruct(value, d);
   string s;
   if(mode & TIME_DATE) s += mk_fmt("%04d.%02d.%02d", d.year, d.mon, d.day);
   if(mode & (TIME_MINUTES | TIME_SECONDS)) s += mk_fmt("%s%02d:%02d", s.empty() ? "" : " ", d.hour, d.min);
   if(mode & TIME_SECONDS) s += mk_fmt(":%02d", d.sec);
   return s;
  }

// ------------------------------------------------------------------ output, arrays, strings, maths
template <typename... A> void Print(A... a)
  {
   std::ostringstream o;
   ((o << a), ...);
   mk_log("PRINT", o.str());
  }
template <typename... A> void Alert(A... a)
  {
   std::ostringstream o;
   ((o << a), ...);
   mk_log("ALERT", o.str());
  }
template <typename... A> void Comment(A... a)
  {
   static string last = "\x01";
   std::ostringstream o;
   ((o << a), ...);
   if(o.str() == last) return;
   last = o.str();
   mk_log("COMMENT", last);
   mk_write("_mock/comment.txt", last);
  }
bool SendNotification(const string text) { mk_log("NOTIFY", text); return true; }
template <typename T> int ArraySize(const MqlArray<T> &a) { return (int)a.v.size(); }
template <typename T> int ArrayResize(MqlArray<T> &a, int n, int) { a.v.resize(n); return n; }
template <typename T> void ArrayFree(MqlArray<T> &a) { a.v.clear(); }
template <typename T> void ZeroMemory(T &v) { v = T(); }
template <typename A, typename B> auto MathMax(A a, B b) -> decltype(a + b) { return a > b ? a : b; }
template <typename A, typename B> auto MathMin(A a, B b) -> decltype(a + b) { return a < b ? a : b; }
double MathAbs(double v) { return std::fabs(v); }
double MathCeil(double v) { return std::ceil(v); }
double MathFloor(double v) { return std::floor(v); }
double MathLog10(double v) { return std::log10(v); }
double MathRound(double v) { return std::round(v); }
bool MathIsValidNumber(double v) { return std::isfinite(v); }
double NormalizeDouble(double v, int digits)
  {
   if(!std::isfinite(v)) return v;
   double p = std::pow(10.0, digits);
   return std::round(v * p) / p;
  }
string IntegerToString(long number, int str_len, ushort fill)
  {
   string s = std::to_string(number);
   if((int)s.size() < str_len) s.insert(0, str_len - s.size(), (char)fill);
   return s;
  }
string DoubleToString(double value, int digits)
  {
   char b[400];
   snprintf(b, sizeof b, "%.*f", digits, value);
   return b;
  }
long StringToInteger(const string value) { return strtoll(value.c_str(), nullptr, 10); }
double StringToDouble(const string value) { return strtod(value.c_str(), nullptr); }   // also reads "nan" and "inf" (worst case)
int StringLen(const string s) { return (int)s.size(); }
string StringSubstr(const string s, int start, int length)
  {
   if(start < 0 || start >= (int)s.size()) return "";
   return length < 0 ? s.substr(start) : s.substr(start, length);
  }
int StringFind(const string s, const string m, int start) { size_t p = s.find(m, start); return p == string::npos ? -1 : (int)p; }
int StringReplace(string &s, const string f, const string r)
  {
   int n = 0;
   if(f.empty()) return 0;
   for(size_t p = s.find(f); p != string::npos; p = s.find(f, p + r.size())) { s.replace(p, f.size(), r); n++; }
   return n;
  }
int StringCompare(const string &a, const string &b, bool) { int c = a.compare(b); return c < 0 ? -1 : (c > 0 ? 1 : 0); }
int StringTrimLeft(string &s) { size_t p = s.find_first_not_of(" \t\r\n"); s.erase(0, p == string::npos ? s.size() : p); return 0; }
int StringTrimRight(string &s) { size_t p = s.find_last_not_of(" \t\r\n"); s.erase(p == string::npos ? 0 : p + 1); return 0; }
int StringSplit(const string s, const ushort sep, MqlArray<string> &out)
  {
   out.v = mk_split(s, (char)sep);
   return (int)out.v.size();
  }

// ------------------------------------------------------------------ files (rooted at MOCK_FILES; no parent folder is created)
struct MkFile { FILE *w; string data; size_t pos; };
static std::map<int, MkFile> mk_files;
static int mk_next_handle = 1;
static std::map<long, std::pair<std::vector<string>, size_t>> mk_finds;
static long mk_next_find = 1;
bool FolderCreate(const string name, int) { mkdir(mk_path(name).c_str(), 0755); struct stat st; return stat(mk_path(name).c_str(), &st) == 0 && S_ISDIR(st.st_mode); }
bool FileIsExist(const string name, int) { struct stat st; return stat(mk_path(name).c_str(), &st) == 0 && S_ISREG(st.st_mode); }
bool FileDelete(const string name, int) { return unlink(mk_path(name).c_str()) == 0; }
bool FileMove(const string src, int, const string dst, int flags)
  {
   struct stat st;
   if(!(flags & FILE_REWRITE) && stat(mk_path(dst).c_str(), &st) == 0) return false;
   if(rename(mk_path(src).c_str(), mk_path(dst).c_str()) != 0) return false;
   if(dst.compare(0, 11, "claude\\res\\") == 0) mk_answers++;
   return true;
  }
int FileOpen(const string name, int flags, short, uint)
  {
   MkFile f = {nullptr, "", 0};
   if(flags & FILE_WRITE)
     {
      f.w = fopen(mk_path(name).c_str(), "wb");
      if(!f.w) return INVALID_HANDLE;
     }
   else
     {
      struct stat st;
      if(stat(mk_path(name).c_str(), &st) != 0 || !S_ISREG(st.st_mode) || !mk_read(mk_path(name), f.data)) return INVALID_HANDLE;
     }
   mk_files[mk_next_handle] = f;
   return mk_next_handle++;
  }
uint FileWriteString(int h, const string text, int) { fwrite(text.data(), 1, text.size(), mk_files.at(h).w); return (uint)text.size(); }
void FileFlush(int h) { if(mk_files.at(h).w) fflush(mk_files.at(h).w); }
void FileClose(int h)
  {
   if(mk_files.at(h).w) fclose(mk_files.at(h).w);
   mk_files.erase(h);
  }
bool FileIsEnding(int h) { MkFile &f = mk_files.at(h); return f.pos >= f.data.size(); }
string FileReadString(int h, int)
  {
   MkFile &f = mk_files.at(h);
   size_t nl = mk_crlf_only ? f.data.find("\r\n", f.pos) : f.data.find('\n', f.pos);
   string ln = f.data.substr(f.pos, nl == string::npos ? string::npos : nl - f.pos);
   f.pos = (nl == string::npos) ? f.data.size() : nl + (mk_crlf_only ? 2 : 1);
   if(!mk_crlf_only && !ln.empty() && ln.back() == '\r') ln.pop_back();
   return ln;
  }
long FileFindFirst(const string filter, string &name, int)
  {
   string p = mk_path(filter);
   size_t slash = p.rfind('/');
   string dir = p.substr(0, slash), pat = p.substr(slash + 1);
   std::error_code ec;
   std::vector<string> found;
   for(std::filesystem::directory_iterator it(dir, ec), end; !ec && it != end; it.increment(ec))
     {
      string n = it->path().filename().string();
      if(fnmatch(pat.c_str(), n.c_str(), 0) != 0) continue;
      if(it->is_directory(ec)) n += "\\";
      found.push_back(n);
     }
   if(found.empty()) return INVALID_HANDLE;
   std::sort(found.rbegin(), found.rend());              // deliberately NOT in increasing order: the EA must sort by itself
   name = found[0];
   mk_finds[mk_next_find] = std::make_pair(found, (size_t)1);
   return mk_next_find++;
  }
bool FileFindNext(long h, string &name)
  {
   auto &f = mk_finds.at(h);
   if(f.second >= f.first.size()) return false;
   name = f.first[f.second++];
   return true;
  }
void FileFindClose(long h) { mk_finds.erase(h); }

// ------------------------------------------------------------------ terminal global variables
bool GlobalVariableCheck(const string name) { return mk_gv.count(name) > 0; }
double GlobalVariableGet(const string name) { auto it = mk_gv.find(name); return it == mk_gv.end() ? 0.0 : it->second; }
datetime GlobalVariableSet(const string name, double value)
  {
   mk_gv[name] = value;
   if(mk_gv_always) mk_gv_save();
   return TimeLocal();
  }
bool GlobalVariableDel(const string name)
  {
   bool had = mk_gv.erase(name) > 0;
   if(mk_gv_always) mk_gv_save();
   return had;
  }
int GlobalVariablesTotal() { return (int)mk_gv.size(); }
string GlobalVariableName(int index)
  {
   if(index < 0 || index >= (int)mk_gv.size()) return "";
   auto it = mk_gv.begin();
   std::advance(it, index);
   return it->first;
  }
void GlobalVariablesFlush() { mk_gv_save(); }

// ------------------------------------------------------------------ symbols
bool SymbolSelect(const string name, bool) { return mk_find(name) != nullptr; }
int SymbolsTotal(bool)
  {
   int n = 0;
   for(int i = 0; i < MK_NSYM; i++) n += mk_sym[i].hidden ? 0 : 1;
   return n;
  }
string SymbolName(int pos, bool)
  {
   for(int i = 0; i < MK_NSYM; i++)
      if(!mk_sym[i].hidden && pos-- == 0) return mk_sym[i].name;
   return "";
  }
long SymbolInfoInteger(const string name, ENUM_SYMBOL_INFO_INTEGER p)
  {
   MkSym *s = mk_find(name);
   if(!s) return 0;
   if(p == SYMBOL_DIGITS) return s->digits;
   if(p == SYMBOL_TRADE_MODE) return s->trade_mode;
   if(p == SYMBOL_TRADE_STOPS_LEVEL) return s->stops_level;
   if(p == SYMBOL_TRADE_FREEZE_LEVEL) return s->freeze_level;
   if(p == SYMBOL_SPREAD) return (long)std::llround((s->ask - s->bid) / s->point);
   if(p == SYMBOL_FILLING_MODE) return SYMBOL_FILLING_FOK | SYMBOL_FILLING_IOC;
   if(p == SYMBOL_TRADE_EXEMODE) return 2;                 // SYMBOL_TRADE_EXECUTION_MARKET
   if(p == SYMBOL_SWAP_MODE) return 1;
   if(p == SYMBOL_SWAP_ROLLOVER3DAYS) return s->forex ? 3 : 5;
   if(p == SYMBOL_ORDER_MODE) return s->order_mode;
   return 0;
  }
double SymbolInfoDouble(const string name, ENUM_SYMBOL_INFO_DOUBLE p)
  {
   MkSym *s = mk_find(name);
   if(!s) return 0.0;
   if(p == SYMBOL_BID) return s->bid;
   if(p == SYMBOL_ASK) return s->ask;
   if(p == SYMBOL_POINT) return s->point;
   if(p == SYMBOL_TRADE_TICK_SIZE) return s->tick_size;
   if(p == SYMBOL_TRADE_TICK_VALUE) return s->tick_value;
   if(p == SYMBOL_TRADE_TICK_VALUE_LOSS) return s->tick_value_loss;
   if(p == SYMBOL_TRADE_CONTRACT_SIZE) return s->contract;
   if(p == SYMBOL_VOLUME_MIN) return s->vol_min;
   if(p == SYMBOL_VOLUME_STEP) return s->vol_step;
   if(p == SYMBOL_VOLUME_MAX) return s->vol_max;
   if(p == SYMBOL_SWAP_LONG) return s->swap_long;
   if(p == SYMBOL_SWAP_SHORT) return s->swap_short;
   return 0.0;
  }
string SymbolInfoString(const string name, ENUM_SYMBOL_INFO_STRING p)
  {
   MkSym *s = mk_find(name);
   if(!s) return "";
   if(p == SYMBOL_CURRENCY_PROFIT) return s->ccy_profit;
   if(p == SYMBOL_CURRENCY_MARGIN) return s->forex ? s->ccy_base : s->ccy_profit;
   if(p == SYMBOL_CURRENCY_BASE) return s->ccy_base;
   if(p == SYMBOL_DESCRIPTION) return s->name + " (mock)";
   return "";
  }
bool SymbolInfoTick(const string name, MqlTick &k)
  {
   MkSym *s = mk_find(name);
   if(!s) return false;
   k = MqlTick();
   k.bid = s->bid; k.ask = s->ask; k.time = TimeTradeServer() - s->tick_age; k.time_msc = k.time * 1000;
   return true;
  }
static double mk_margin(const MkSym &s, double volume, double price)
  {
   return s.forex ? volume * s.contract * s.base_eur / s.leverage : volume * s.contract * price * MK_USD_EUR / s.leverage;
  }
bool OrderCalcMargin(ENUM_ORDER_TYPE, const string name, double volume, double price, double &margin)
  {
   MkSym *s = mk_find(name);
   if(!s) return false;
   margin = mk_margin(*s, volume, price);
   return true;
  }

// completed and current bars: one bar per period, without gaps; the same formula is recomputed in test_mains.py
static long mk_tf_sec(ENUM_TIMEFRAMES tf) { return tf == PERIOD_M1 ? 60 : tf == PERIOD_M5 ? 300 : tf == PERIOD_H1 ? 3600 : tf == PERIOD_D1 ? 86400 : 0; }
int CopyRates(const string name, ENUM_TIMEFRAMES tf, int start_pos, int count, MqlArray<MqlRates> &r)
  {
   MkSym *s = mk_find(name);
   long sec = mk_tf_sec(tf);
   r.v.clear();
   if(!s || sec == 0 || count <= 0 || start_pos < 0) return -1;
   const MkSym *d = nullptr;
   for(int i = 0; i < MK_NSYM; i++)
      if(MK_DEFAULTS[i].name == name) d = &MK_DEFAULTS[i];
   long cur = TimeTradeServer() / sec;                      // index of the bar being built
   for(long k = cur - start_pos - count + 1; k <= cur - start_pos; k++)
     {
      MqlRates b = MqlRates();
      double o = d->bid * (1.0 + (double)((k * 37) % 201 - 100) * 1e-5), c = d->bid * (1.0 + (double)(((k + 1) * 37) % 201 - 100) * 1e-5);
      b.time = k * sec; b.open = o; b.close = c;
      b.high = std::max(o, c) + 3 * s->point; b.low = std::min(o, c) - 2 * s->point;
      b.tick_volume = 50 + k % 17; b.spread = (int)std::llround((d->ask - d->bid) / s->point);
      r.v.push_back(b);
     }
   return (int)r.v.size();
  }

// ------------------------------------------------------------------ account, positions, history
static double mk_round2(double v) { return std::round(v * 100.0) / 100.0; }
static double mk_money(const MkSym &s, int type, double volume, double from, double to)
  {
   double diff = (type == 0) ? to - from : from - to;
   return mk_round2(diff / s.tick_size * (diff >= 0 ? s.tick_value : s.tick_value_loss) * volume);
  }
static double mk_profit(const MkPos &p)
  {
   MkSym *s = mk_find(p.symbol);
   if(!s) return 0.0;
   return mk_money(*s, p.type, p.volume, p.price_open, p.type == 0 ? s->bid : s->ask);
  }
static double mk_equity()
  {
   double e = mk_balance;
   for(const MkPos &p : mk_pos) e += mk_profit(p) + p.swap;
   return e;
  }
static double mk_used_margin()
  {
   double m = 0.0;
   for(const MkPos &p : mk_pos)
      if(MkSym *s = mk_find(p.symbol)) m += mk_margin(*s, p.volume, p.price_open);
   return m;
  }
double AccountInfoDouble(ENUM_ACCOUNT_INFO_DOUBLE p)
  {
   if(!mk_connected) return 0.0;
   if(p == ACCOUNT_BALANCE) return mk_balance;
   if(p == ACCOUNT_EQUITY) return mk_equity();
   if(p == ACCOUNT_MARGIN) return mk_used_margin();
   if(p == ACCOUNT_MARGIN_FREE) return mk_equity() - mk_used_margin();
   return 0.0;
  }
long AccountInfoInteger(ENUM_ACCOUNT_INFO_INTEGER p)
  {
   if(p == ACCOUNT_LOGIN) return 7654321;
   if(p == ACCOUNT_TRADE_MODE) return ACCOUNT_TRADE_MODE_DEMO;
   if(p == ACCOUNT_LEVERAGE) return 500;
   if(p == ACCOUNT_MARGIN_MODE) return mk_margin_mode;
   if(p == ACCOUNT_TRADE_ALLOWED) return mk_acc_allowed;
   if(p == ACCOUNT_TRADE_EXPERT) return mk_acc_expert;
   return 0;
  }
string AccountInfoString(ENUM_ACCOUNT_INFO_STRING p)
  {
   if(p == ACCOUNT_CURRENCY) return "EUR";
   if(p == ACCOUNT_SERVER) return "FPMarketsSC-Demo";
   return "FP Markets (mock)";
  }
int TerminalInfoInteger(ENUM_TERMINAL_INFO_INTEGER p) { return p == TERMINAL_TRADE_ALLOWED ? mk_term_allowed : (p == TERMINAL_CONNECTED ? mk_connected : 1); }
int MQLInfoInteger(ENUM_MQL_INFO_INTEGER p) { return p == MQL_TRADE_ALLOWED ? mk_mql_allowed : 0; }
bool IsStopped() { return mk_stopped; }
int GetLastError() { return 0; }
void ResetLastError() {}
bool EventSetTimer(int) { if(mk_timer_fail) return false; mk_timer = true; return true; }
void EventKillTimer() { mk_timer = false; }

static const MkPos *mk_view_find(ulong ticket)
  {
   for(const MkPos &p : mk_view)
      if(p.ticket == ticket) return &p;
   return nullptr;
  }
int PositionsTotal() { return (int)mk_view.size(); }
ulong PositionGetTicket(int index)
  {
   if(index < 0 || index >= (int)mk_view.size()) return 0;
   mk_selected = mk_view[index].ticket;
   return mk_selected;
  }
bool PositionSelectByTicket(ulong ticket)
  {
   if(!mk_view_find(ticket)) return false;
   mk_selected = ticket;
   return true;
  }
long PositionGetInteger(ENUM_POSITION_PROPERTY_INTEGER p)
  {
   const MkPos *q = mk_view_find(mk_selected);
   if(!q) return 0;
   if(p == POSITION_TICKET) return (long)q->ticket;
   if(p == POSITION_IDENTIFIER) return (long)q->ident;
   if(p == POSITION_TIME) return q->time;
   if(p == POSITION_TYPE) return q->type == 0 ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
   if(p == POSITION_MAGIC) return q->magic;
   return 0;
  }
double PositionGetDouble(ENUM_POSITION_PROPERTY_DOUBLE p)
  {
   const MkPos *q = mk_view_find(mk_selected);
   if(!q) return 0.0;
   if(p == POSITION_VOLUME) return q->volume;
   if(p == POSITION_PRICE_OPEN) return q->price_open;
   if(p == POSITION_SL) return q->sl;
   if(p == POSITION_TP) return q->tp;
   if(p == POSITION_SWAP) return q->swap;
   if(p == POSITION_PROFIT) return mk_profit(*q);
   if(p == POSITION_PRICE_CURRENT) { MkSym *s = mk_find(q->symbol); return s ? (q->type == 0 ? s->bid : s->ask) : 0.0; }
   return 0.0;
  }
string PositionGetString(ENUM_POSITION_PROPERTY_STRING p)
  {
   const MkPos *q = mk_view_find(mk_selected);
   if(!q) return "";
   return p == POSITION_SYMBOL ? q->symbol : q->comment;
  }
bool HistorySelect(datetime from, datetime to)
  {
   mk_hist.clear();
   for(int i = 0; i < (int)mk_deals.size(); i++)
      if(mk_deals[i].time >= from && mk_deals[i].time <= to) mk_hist.push_back(i);
   return true;
  }
int HistoryDealsTotal() { return (int)mk_hist.size(); }
ulong HistoryDealGetTicket(int index) { return (index < 0 || index >= (int)mk_hist.size()) ? 0 : mk_deals[mk_hist[index]].deal; }
static const MkDeal *mk_deal(ulong ticket)
  {
   for(const MkDeal &d : mk_deals)
      if(d.deal == ticket) return &d;
   return nullptr;
  }
long HistoryDealGetInteger(ulong ticket, ENUM_DEAL_PROPERTY_INTEGER p)
  {
   const MkDeal *d = mk_deal(ticket);
   if(!d) return 0;
   if(p == DEAL_MAGIC) return d->magic;
   if(p == DEAL_ENTRY) return d->entry;
   if(p == DEAL_TYPE) return d->type;
   if(p == DEAL_POSITION_ID) return (long)d->position;
   if(p == DEAL_ORDER) return (long)d->order;
   if(p == DEAL_REASON) return d->reason;
   if(p == DEAL_TIME) return d->time;
   return 0;
  }
double HistoryDealGetDouble(ulong ticket, ENUM_DEAL_PROPERTY_DOUBLE p)
  {
   const MkDeal *d = mk_deal(ticket);
   if(!d) return 0.0;
   if(p == DEAL_VOLUME) return d->volume;
   if(p == DEAL_PRICE) return d->price;
   if(p == DEAL_COMMISSION) return d->commission;
   if(p == DEAL_SWAP) return d->swap;
   if(p == DEAL_PROFIT) return d->profit;
   if(p == DEAL_FEE) return d->fee;
   return 0.0;
  }
string HistoryDealGetString(ulong ticket, ENUM_DEAL_PROPERTY_STRING p)
  {
   const MkDeal *d = mk_deal(ticket);
   if(!d) return "";
   return p == DEAL_SYMBOL ? d->symbol : d->comment;
  }

// ------------------------------------------------------------------ the broker
static void mk_changed()
  {
   mk_pending_tx++;
   if(!mk_lag) mk_view = mk_pos;
   mk_save_state();
  }
static bool mk_volume_ok(const MkSym &s, double v)
  {
   if(!std::isfinite(v) || v < s.vol_min - 1e-9 || v > s.vol_max + 1e-9) return false;
   double k = v / s.vol_step;
   return std::fabs(k - std::round(k)) < 1e-6;
  }
// SL / TP against the price at which the position would be closed now (bid for a buy, ask for a sell)
static bool mk_stops_ok(const MkSym &s, int type, double sl, double tp)
  {
   if(std::isnan(sl) || std::isnan(tp) || sl < 0 || tp < 0) return false;
   double lvl = s.stops_level * s.point, px = (type == 0) ? s.bid : s.ask;
   if(type == 0) return (sl == 0 || sl < px - lvl + 1e-9 * px) && (sl == 0 || sl < px) && (tp == 0 || tp > px + lvl - 1e-9 * px);
   return (sl == 0 || (sl > px + lvl - 1e-9 * px && sl > px)) && (tp == 0 || tp < px - lvl + 1e-9 * px);
  }
static void mk_add_deal(const MkPos &p, int type, int entry, double volume, double price, double profit, long magic, long reason,
                        const string &comment, ulong order)
  {
   const MkSym *s = mk_find(p.symbol);
   MkDeal d = {mk_next_deal++, order, p.ident, (long)TimeTradeServer(), p.symbol, type, entry, volume, price, profit, 0.0,
               s ? -mk_round2(s->commission_lot * volume) : 0.0, s ? -mk_round2(s->fee_lot * volume) : 0.0, magic, reason, comment};
   if(d.commission == 0.0) d.commission = 0.0;             // no "-0.00"
   if(d.fee == 0.0) d.fee = 0.0;
   mk_balance = mk_round2(mk_balance + d.profit + d.swap + d.commission + d.fee);
   mk_deals.push_back(d);
  }
static ulong mk_open(const MkSym &s, int type, double volume, double sl, double tp, long magic, const string &comment, long reason,
                     double &price)
  {
   price = (type == 0) ? s.ask + s.slip : s.bid - s.slip;
   MkPos p = {mk_next_order++, s.name, type, volume, price, sl, tp, 0.0, magic, (long)TimeTradeServer(), comment, 0};
   p.ident = p.ticket;
   mk_pos.push_back(p);
   mk_add_deal(p, type, 0, volume, price, 0.0, magic, reason, comment, p.ticket);
   mk_changed();
   return p.ticket;
  }
// closes `volume` of the position at `price`; the position disappears when nothing is left
static void mk_close(ulong ticket, double volume, double price, long magic, long reason, const string &comment)
  {
   for(size_t i = 0; i < mk_pos.size(); i++)
     {
      if(mk_pos[i].ticket != ticket) continue;
      MkPos &p = mk_pos[i];
      const MkSym *s = mk_find(p.symbol);
      double profit = s ? mk_money(*s, p.type, volume, p.price_open, price) : 0.0;
      mk_add_deal(p, p.type == 0 ? 1 : 0, 1, volume, price, profit, magic, reason, comment, mk_next_order++);
      if(volume >= p.volume - 1e-9) mk_pos.erase(mk_pos.begin() + i);
      else p.volume = std::round((p.volume - volume) * 1e8) / 1e8;
      mk_changed();
      return;
     }
  }
// what the broker does on its own when the price moves: stops and targets
static void mk_broker_tick()
  {
   for(size_t i = 0; i < mk_pos.size();)
     {
      MkPos p = mk_pos[i];
      MkSym *s = mk_find(p.symbol);
      if(!s || s->bid <= 0 || s->ask <= 0) { i++; continue; }
      double px = (p.type == 0) ? s->bid : s->ask;
      bool hit_sl = p.sl > 0 && ((p.type == 0) ? px <= p.sl : px >= p.sl);
      bool hit_tp = p.tp > 0 && ((p.type == 0) ? px >= p.tp : px <= p.tp);
      if(!hit_sl && !hit_tp) { i++; continue; }
      string c = mk_fmt("[%s %.*f]", hit_sl ? "sl" : "tp", s->digits, hit_sl ? p.sl : p.tp);
      mk_log("BROKER", mk_fmt("position %lu closed by its %s at %.*f", p.ticket, hit_sl ? "stop" : "target", s->digits, px));
      mk_close(p.ticket, p.volume, px, mk_sl_magic0 ? 0 : p.magic, hit_sl ? 4 : 5, c);   // filled at the market price (gap = slippage)
     }
  }
static bool mk_answer(MqlTradeResult &res, uint retcode, const MkSym *s)
  {
   res.retcode = retcode;
   if(s) { res.bid = s->bid; res.ask = s->ask; }
   bool ok = retcode == MK_DONE || retcode == MK_PLACED || retcode == MK_DONE_PARTIAL;
   return ok || mk_send_true;
  }
bool OrderSend(const MqlTradeRequest &req, MqlTradeResult &res)
  {
   res = MqlTradeResult();
   if(mk_send_delay_ms > 0) usleep((useconds_t)mk_send_delay_ms * 1000);
   MkSym *s = mk_find(req.symbol);
   bool ret = false;
   const char *kind = req.action == TRADE_ACTION_SLTP ? "sltp" : (req.position != 0 ? "close" : "open");
   uint forced = mk_rc_all ? mk_rc_all : (req.action == TRADE_ACTION_SLTP ? mk_rc_sltp : (req.position != 0 ? mk_rc_close : mk_rc_open));
   if(!mk_term_allowed || !mk_mql_allowed || !mk_acc_allowed || !mk_acc_expert) { res.retcode = MK_CLIENT_DISABLES_AT; ret = false; }
   else if(!mk_connected) ret = mk_answer(res, 10031, s);
   else if(forced) ret = mk_answer(res, forced, s);
   else if(!s) ret = mk_answer(res, MK_INVALID, s);
   else if(req.action == TRADE_ACTION_DEAL && req.position == 0)
     {
      int type = (req.type == ORDER_TYPE_BUY) ? 0 : 1;
      double price = 0.0;
      if(s->trade_mode == 0) ret = mk_answer(res, MK_TRADE_DISABLED, s);
      else if(s->trade_mode != 4) ret = mk_answer(res, MK_CLOSE_ONLY, s);
      else if(s->bid <= 0 || s->ask <= 0) ret = mk_answer(res, MK_MARKET_CLOSED, s);
      else if(!mk_volume_ok(*s, req.volume)) ret = mk_answer(res, MK_INVALID_VOLUME, s);
      else if(!mk_stops_ok(*s, type, req.sl, req.tp)) ret = mk_answer(res, MK_INVALID_STOPS, s);
      else if(mk_margin(*s, req.volume, type == 0 ? s->ask : s->bid) > mk_equity() - mk_used_margin()) ret = mk_answer(res, MK_NO_MONEY, s);
      else
        {
         res.order = mk_open(*s, type, req.volume, mk_drop_sl ? 0.0 : req.sl, req.tp, (long)req.magic, req.comment, 3, price);
         res.deal = mk_next_deal - 1; res.volume = req.volume; res.price = price;
         ret = mk_answer(res, MK_DONE, s);
        }
     }
   else if(req.action == TRADE_ACTION_DEAL)
     {
      const MkPos *p = nullptr;
      for(const MkPos &q : mk_pos)
         if(q.ticket == req.position) p = &q;
      if(!p) ret = mk_answer(res, MK_POSITION_CLOSED, s);
      else if(s->trade_mode == 0) ret = mk_answer(res, MK_TRADE_DISABLED, s);
      else if(s->bid <= 0 || s->ask <= 0) ret = mk_answer(res, MK_MARKET_CLOSED, s);
      else if(!mk_volume_ok(*s, req.volume) || req.volume > p->volume + 1e-9) ret = mk_answer(res, MK_INVALID_VOLUME, s);
      else
        {
         double price = (p->type == 0) ? s->bid : s->ask;
         res.order = mk_next_order; res.deal = mk_next_deal; res.volume = req.volume; res.price = price;
         mk_close(req.position, req.volume, price, (long)req.magic, 3, req.comment);
         ret = mk_answer(res, MK_DONE, s);
        }
     }
   else if(req.action == TRADE_ACTION_SLTP)
     {
      MkPos *p = nullptr;
      for(MkPos &q : mk_pos)
         if(q.ticket == req.position) p = &q;
      if(!p) ret = mk_answer(res, MK_POSITION_CLOSED, s);
      else if(std::fabs(req.sl - p->sl) < s->point / 2 && std::fabs(req.tp - p->tp) < s->point / 2) ret = mk_answer(res, MK_NO_CHANGES, s);
      else if(!mk_stops_ok(*s, p->type, req.sl, req.tp)) ret = mk_answer(res, MK_INVALID_STOPS, s);
      else
        {
         p->sl = req.sl; p->tp = req.tp;
         mk_changed();
         ret = mk_answer(res, MK_DONE, s);
        }
     }
   else ret = mk_answer(res, MK_INVALID, s);
   mk_log("TRADE", mk_fmt("%s %s position=%lu type=%d volume=%.8g sl=%.10g tp=%.10g magic=%lu comment=%s -> retcode=%u order=%lu "
                          "price=%.10g ret=%d", kind, req.symbol.c_str(), req.position, (int)req.type, req.volume, req.sl, req.tp,
                          req.magic, req.comment.c_str(), res.retcode, res.order, res.price, ret ? 1 : 0));
   return ret;
  }

// ------------------------------------------------------------------ CTrade (transcribed from Trade.mqh 2000-2025)
static bool mk_hedging() { return AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING; }
static void mk_clear() { mk_req = MqlTradeRequest(); mk_res = MqlTradeResult(); }
static bool mk_filling_check(const string &symbol)          // FillingCheck(), "market execution" branch
  {
   uint filling = (uint)SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK) { mk_filling = ORDER_FILLING_FOK; mk_req.type_filling = mk_filling; return true; }
   if((filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC) { mk_filling = ORDER_FILLING_IOC; mk_req.type_filling = mk_filling; return true; }
   mk_res.retcode = MK_INVALID_FILL;
   return false;
  }
static bool mk_order_type_check(const string &symbol)       // OrderTypeCheck(): note that it REMOVES sl / tp the symbol does not allow
  {
   long flags = SymbolInfoInteger(symbol, SYMBOL_ORDER_MODE);
   if((flags & SYMBOL_ORDER_MARKET) == 0)
     {
      mk_res.retcode = MK_INVALID_ORDER;
      mk_log("PRINT", "CTrade::OrderTypeCheck: Invalid order type");
      return false;
     }
   if(mk_req.sl != 0.0 || mk_req.tp != 0.0)
     {
      if((flags & SYMBOL_ORDER_SL) == 0) mk_req.sl = 0.0;
      if((flags & SYMBOL_ORDER_TP) == 0) mk_req.tp = 0.0;
     }
   return true;
  }
// control race=1: the position disappears at the broker (its stop) and from the terminal's list just before CTrade looks
static void mk_race_now(ulong ticket)
  {
   if(!mk_race) return;
   for(const MkPos &p : mk_pos)
      if(p.ticket == ticket)
        {
         MkSym *s = mk_find(p.symbol);
         mk_log("BROKER", mk_fmt("position %lu closed by its stop while the EA was working on it", p.ticket));
         mk_close(p.ticket, p.volume, s ? (p.type == 0 ? s->bid : s->ask) : p.price_open, p.magic, 4, "[sl]");
         break;
        }
   mk_view = mk_pos;
  }
static bool mk_position_open(const string &symbol, ENUM_ORDER_TYPE type, double volume, double price, double sl, double tp,
                             const string &comment)
  {
   if(IsStopped()) return false;                              // as in Trade.mqh: before ClearStructures()
   mk_clear();
   mk_req.action = TRADE_ACTION_DEAL; mk_req.symbol = symbol; mk_req.magic = mk_magic; mk_req.volume = volume; mk_req.type = type;
   mk_req.price = price; mk_req.sl = sl; mk_req.tp = tp; mk_req.deviation = mk_deviation;
   if(!mk_order_type_check(symbol)) return false;
   if(!mk_filling_check(symbol)) return false;
   mk_req.comment = comment;
   return OrderSend(mk_req, mk_res);
  }
uint   CTrade::ResultRetcode(void) const { return mk_res.retcode; }
double CTrade::ResultPrice(void) const { return mk_res.price; }
ulong  CTrade::ResultDeal(void) const { return mk_res.deal; }
ulong  CTrade::ResultOrder(void) const { return mk_res.order; }
double CTrade::ResultVolume(void) const { return mk_res.volume; }
void   CTrade::SetDeviationInPoints(const ulong deviation) { mk_deviation = deviation; }
void   CTrade::SetExpertMagicNumber(const ulong magic) { mk_magic = magic; }
bool   CTrade::SetTypeFillingBySymbol(const string symbol)
  {
   uint filling = (uint)SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK) { mk_filling = ORDER_FILLING_FOK; return true; }
   if((filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC) { mk_filling = ORDER_FILLING_IOC; return true; }
   return false;
  }
string CTrade::ResultRetcodeDescription(void) const        // FormatRequestResult()
  {
   int digits = (int)SymbolInfoInteger(mk_req.symbol, SYMBOL_DIGITS);
   switch(mk_res.retcode)
     {
      case 10004: return "requote (" + DoubleToString(mk_res.bid, digits) + "/" + DoubleToString(mk_res.ask, digits) + ")";
      case 10009: return mk_req.action == TRADE_ACTION_DEAL ? "done at " + DoubleToString(mk_res.price, digits) : string("done");
      case 10010: return "done partially " + DoubleToString(mk_res.volume, 2) + " at " + DoubleToString(mk_res.price, digits);
      case 10006: return "rejected";
      case 10007: return "canceled";
      case 10008: return "placed";
      case 10011: return "common error";
      case 10012: return "timeout";
      case 10013: return "invalid request";
      case 10014: return "invalid volume";
      case 10015: return "invalid price";
      case 10016: return "invalid stops";
      case 10017: return "trade disabled";
      case 10018: return "market closed";
      case 10019: return "not enough money";
      case 10020: return "price changed";
      case 10021: return "off quotes";
      case 10022: return "invalid expiration";
      case 10023: return "order changed";
      case 10024: return "too many requests";
      case 10025: return "no changes";
      case 10026: return "auto trading disabled by server";
      case 10027: return "auto trading disabled by client";
      case 10028: return "locked";
      case 10029: return "frozen";
      case 10030: return "invalid fill";
      case 10031: return "no connection";
      case 10032: return "only real";
      case 10033: return "limit orders";
      case 10034: return "limit volume";
      case 10036: return "position closed";
      case 10035: return "invalid order";
      case 10039: return "close order already exists";
      case 10040: return "limit positions";
      default: return "unknown retcode " + std::to_string(mk_res.retcode);
     }
  }
bool CTrade::Buy(const double volume, const string symbol, double price, const double sl, const double tp, const string comment)
  {
   if(volume <= 0.0) { mk_res.retcode = MK_INVALID_VOLUME; return false; }
   if(price == 0.0) price = SymbolInfoDouble(symbol, SYMBOL_ASK);
   return mk_position_open(symbol, ORDER_TYPE_BUY, volume, price, sl, tp, comment);
  }
bool CTrade::Sell(const double volume, const string symbol, double price, const double sl, const double tp, const string comment)
  {
   if(volume <= 0.0) { mk_res.retcode = MK_INVALID_VOLUME; return false; }
   if(price == 0.0) price = SymbolInfoDouble(symbol, SYMBOL_BID);
   return mk_position_open(symbol, ORDER_TYPE_SELL, volume, price, sl, tp, comment);
  }
bool CTrade::PositionModify(const ulong ticket, const double sl, const double tp)
  {
   if(IsStopped()) return false;
   mk_race_now(ticket);
   if(!PositionSelectByTicket(ticket)) return false;        // as in Trade.mqh: the previous result is NOT cleared here
   mk_clear();
   mk_req.action = TRADE_ACTION_SLTP; mk_req.position = ticket; mk_req.symbol = PositionGetString(POSITION_SYMBOL);
   mk_req.magic = mk_magic; mk_req.sl = sl; mk_req.tp = tp;
   return OrderSend(mk_req, mk_res);
  }
static bool mk_position_close(const ulong ticket, double volume, const ulong deviation)
  {
   string symbol = PositionGetString(POSITION_SYMBOL);
   mk_clear();
   if(!mk_filling_check(symbol)) return false;
   if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) { mk_req.type = ORDER_TYPE_SELL; mk_req.price = SymbolInfoDouble(symbol, SYMBOL_BID); }
   else { mk_req.type = ORDER_TYPE_BUY; mk_req.price = SymbolInfoDouble(symbol, SYMBOL_ASK); }
   double position_volume = PositionGetDouble(POSITION_VOLUME);
   if(volume >= 0 && position_volume > volume) position_volume = volume;
   mk_req.action = TRADE_ACTION_DEAL; mk_req.position = ticket; mk_req.symbol = symbol; mk_req.volume = position_volume;
   mk_req.magic = mk_magic; mk_req.deviation = (deviation == ULONG_MAX) ? mk_deviation : deviation;
   return OrderSend(mk_req, mk_res);
  }
bool CTrade::PositionClose(const ulong ticket, const ulong deviation)
  {
   if(IsStopped()) return false;
   mk_race_now(ticket);
   if(!PositionSelectByTicket(ticket)) return false;
   return mk_position_close(ticket, -1.0, deviation);
  }
bool CTrade::PositionClosePartial(const ulong ticket, const double volume, const ulong deviation)
  {
   if(IsStopped()) return false;
   if(!mk_hedging()) return false;
   mk_race_now(ticket);
   if(!PositionSelectByTicket(ticket)) return false;
   return mk_position_close(ticket, volume, deviation);
  }

// ------------------------------------------------------------------ control file, main loop
static void mk_apply_control()
  {
   string raw;
   if(!mk_read(mk_path("_mock/control.txt"), raw) || raw == mk_control_raw) return;
   mk_control_raw = raw;
   bool hidden[MK_NSYM];
   for(int i = 0; i < MK_NSYM; i++) { hidden[i] = mk_sym[i].hidden; mk_sym[i] = MK_DEFAULTS[i]; mk_sym[i].hidden = hidden[i]; }
   mk_seq = 0; mk_gmt_skew = 0; mk_rc_all = mk_rc_open = mk_rc_close = mk_rc_sltp = 0;
   mk_send_true = false; mk_term_allowed = mk_mql_allowed = mk_acc_allowed = mk_acc_expert = mk_connected = 1;
   mk_drop_sl = mk_sl_magic0 = mk_race = mk_stopped = mk_timer_fail = false;
   mk_margin_mode = 2; mk_send_delay_ms = 0;
   bool lag = false;
   mk_hold = false;
   mk_do.clear();
   for(const string &ln0 : mk_split(raw, '\n'))
     {
      string ln = ln0;
      StringTrimRight(ln);
      size_t p = ln.find('=');
      if(p == string::npos || p == 0) continue;
      string k = ln.substr(0, p), v = ln.substr(p + 1);
      if(k == "seq") mk_seq = atol(v.c_str());
      else if(k == "server_offset") mk_server_offset = atof(v.c_str());
      else if(k == "gmt_skew") mk_gmt_skew = atol(v.c_str());
      else if(k == "retcode") mk_rc_all = (uint)atol(v.c_str());
      else if(k == "retcode_open") mk_rc_open = (uint)atol(v.c_str());
      else if(k == "retcode_close") mk_rc_close = (uint)atol(v.c_str());
      else if(k == "retcode_sltp") mk_rc_sltp = (uint)atol(v.c_str());
      else if(k == "ordersend_true") mk_send_true = atoi(v.c_str()) != 0;
      else if(k == "terminal_trade_allowed") mk_term_allowed = atoi(v.c_str());
      else if(k == "mql_trade_allowed") mk_mql_allowed = atoi(v.c_str());
      else if(k == "account_trade_allowed") mk_acc_allowed = atoi(v.c_str());
      else if(k == "account_trade_expert") mk_acc_expert = atoi(v.c_str());
      else if(k == "connected") mk_connected = atoi(v.c_str());
      else if(k == "lag") lag = atoi(v.c_str()) != 0;
      else if(k == "hold") mk_hold = atoi(v.c_str()) != 0;
      else if(k == "drop_sl") mk_drop_sl = atoi(v.c_str()) != 0;
      else if(k == "sl_magic0") mk_sl_magic0 = atoi(v.c_str()) != 0;
      else if(k == "race") mk_race = atoi(v.c_str()) != 0;
      else if(k == "stopped") mk_stopped = atoi(v.c_str()) != 0;
      else if(k == "timer_fail") mk_timer_fail = atoi(v.c_str()) != 0;
      else if(k == "margin_mode") mk_margin_mode = atol(v.c_str());
      else if(k == "ordersend_delay_ms") mk_send_delay_ms = atol(v.c_str());
      else if(k.compare(0, 3, "do.") == 0) mk_do[atol(k.c_str() + 3)] = v;
      else if(k.compare(0, 6, "price.") == 0)
        {
         for(int i = 0; i < MK_NSYM; i++)
            if(mk_sym[i].name == k.substr(6)) sscanf(v.c_str(), "%lf,%lf", &mk_sym[i].bid, &mk_sym[i].ask);
        }
      else if(k.compare(0, 4, "sym.") == 0)
        {
         size_t dot = k.rfind('.');
         string name = k.substr(4, dot - 4), prop = k.substr(dot + 1);
         double x = atof(v.c_str());
         for(int i = 0; i < MK_NSYM; i++)
           {
            MkSym &s = mk_sym[i];
            if(s.name != name) continue;
            if(prop == "stops_level") s.stops_level = (long)x;
            else if(prop == "freeze_level") s.freeze_level = (long)x;
            else if(prop == "trade_mode") s.trade_mode = (long)x;
            else if(prop == "order_mode") s.order_mode = (long)x;
            else if(prop == "vol_min") s.vol_min = x;
            else if(prop == "vol_step") s.vol_step = x;
            else if(prop == "vol_max") s.vol_max = x;
            else if(prop == "tick_value") s.tick_value = x;
            else if(prop == "tick_value_loss") s.tick_value_loss = x;
            else if(prop == "leverage") s.leverage = x;
            else if(prop == "tick_age") s.tick_age = (long)x;
            else if(prop == "slip") s.slip = x;
           }
        }
     }
   if(mk_lag && !lag) mk_view = mk_pos;
   mk_lag = lag;
   for(const auto &op : mk_do)                                // positions opened outside the EA, deposits
     {
      if(op.first <= mk_last_do) continue;
      mk_last_do = op.first;
      std::vector<string> a = mk_split(op.second, ' ');
      if(a[0] == "open" && a.size() >= 7)
        {
         MkSym *s = mk_find(a[1]);
         double price = 0.0;
         string comment;
         for(size_t i = 7; i < a.size(); i++) comment += (i > 7 ? " " : "") + a[i];
         if(s) mk_open(*s, a[2] == "buy" ? 0 : 1, atof(a[3].c_str()), atof(a[4].c_str()), atof(a[5].c_str()), atol(a[6].c_str()), comment, 0, price);
        }
      else if(a[0] == "close" && a.size() >= 2)
        {
         ulong t = strtoul(a[1].c_str(), nullptr, 10);
         for(const MkPos &p : mk_pos)
            if(p.ticket == t)
              {
               MkSym *s = mk_find(p.symbol);
               mk_close(t, p.volume, p.type == 0 ? s->bid : s->ask, 0, 0, "");
               break;
              }
        }
      else if(a[0] == "sltp" && a.size() >= 4)
        {
         for(MkPos &p : mk_pos)
            if(p.ticket == strtoul(a[1].c_str(), nullptr, 10)) { p.sl = atof(a[2].c_str()); p.tp = atof(a[3].c_str()); }
         mk_changed();
        }
      else if(a[0] == "reticket" && a.size() >= 2)
        {
         for(MkPos &p : mk_pos)
            if(p.ticket == strtoul(a[1].c_str(), nullptr, 10)) p.ticket = mk_next_order++;
         mk_changed();
        }
      else if(a[0] == "balance" && a.size() >= 2)
        {
         MkDeal d = {mk_next_deal++, 0, 0, (long)TimeTradeServer(), "", 2, 0, 0.0, 0.0, atof(a[1].c_str()), 0.0, 0.0, 0.0, 0, 0, "deposit"};
         mk_balance = mk_round2(mk_balance + d.profit);
         mk_deals.push_back(d);
         mk_changed();
        }
      mk_save_state();
     }
  }
// the trade events reach the EA only between two handlers (MQL5 programs run in a single thread)
static void mk_deliver()
  {
   mk_view = mk_pos;
   int n = mk_pending_tx;
   mk_pending_tx = 0;
   for(int i = 0; i < n; i++)
     {
      MqlTradeTransaction t = MqlTradeTransaction();
      MqlTradeRequest q = MqlTradeRequest();
      MqlTradeResult r = MqlTradeResult();
      t.type = TRADE_TRANSACTION_DEAL_ADD;
      OnTradeTransaction(t, q, r);
     }
  }
#ifndef MOCK_MAINS_NO_MAIN
int main()
  {
   const char *root = getenv("MOCK_FILES");
   mk_root = root ? root : ".";
   mkdir(mk_path("_mock").c_str(), 0755);
   const char *e = getenv("MOCK_GV_SAVE");
   mk_gv_always = e && strcmp(e, "always") == 0;
   e = getenv("MOCK_CRLF_ONLY");
   mk_crlf_only = e && strcmp(e, "1") == 0;
   for(int i = 0; i < MK_NSYM; i++) mk_sym[i] = MK_DEFAULTS[i];
   if((e = getenv("MOCK_MISSING")))
      for(const string &m : mk_split(e, ','))
         for(int i = 0; i < MK_NSYM; i++)
            if(mk_sym[i].name == m) mk_sym[i].hidden = true;
   mk_load_state();
   mk_gv_load();
   mk_apply_control();
   mk_log("MOCK", "start");
   int rc = OnInit();
   mk_deliver();
   if(rc != INIT_SUCCEEDED)                                   // the EA is unloaded (docs: Deinit event, reason REASON_INITFAILED)
     {
      OnDeinit(8);
      mk_log("MOCK", "OnInit failed");
      return 3;
     }
   struct stat st;
   while(stat(mk_path("_mock/stop").c_str(), &st) != 0)
     {
      mk_apply_control();
      mk_broker_tick();
      mk_deliver();
      if(mk_timer && !mk_hold)
        {
         mk_answers = 0;
         OnTimer();
         if(mk_answers > 0) mk_log("PASS", std::to_string(mk_answers));
         mk_deliver();
        }
      mk_loops++;
      if(mk_seq != mk_acked)
        {
         mk_acked = mk_seq;
         mk_write("_mock/ack.txt", mk_fmt("seq=%ld\nloops=%ld\n", mk_seq, mk_loops));
        }
      usleep(15000);
     }
   OnDeinit(REASON_REMOVE);
   mk_gv_save();                                             // a terminal that closes normally saves its global variables
   mk_log("MOCK", "clean stop");
   return 0;
  }
#endif
