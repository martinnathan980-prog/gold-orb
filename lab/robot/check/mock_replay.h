// mock_replay.h - a MetaTrader 5 terminal + hedging broker imitation that REPLAYS recorded M1 bars minute by minute, so
// that the real MQL5 code of ClaudeRobot (translated by check/to_cpp.py, compiled with g++) runs offline and its journal
// can be compared with the lab. Extended from lab/robot/spike/check/mock_replay.h (S0). It is NOT MetaTrader: it
// imitates the documented behaviour of the functions the robot uses, and the lab's fill conventions.
//
// Clock (SPEC 7): one event per distinct M1 bar start T of any symbol (server seconds). At T the bar starting at T is
//   the FORMING bar (first tick at T: open = high = low = close = open); earlier bars are closed. A symbol without a bar
//   at T keeps its older forming bar. Then OnTick (when the first symbol has a bar at T) and OnTimer at T + 2 s (the
//   spec's T + 2.5 s: TimeTradeServer() has whole seconds; GetTickCount64() says T + 2.5 s). MOCK_TIMER_CALLS=n adds
//   calls at T + 3 s, T + 4 s, ...
//   Tick mode (MOCK_TICK=1): each forming bar plays O -> L -> H -> C (close >= open) or O -> H -> L -> C at T, T+15,
//   T+30, T+45 s; broker stops are checked on every tick (fill at the tick price x stop slippage); OnTimer after each.
//   Fast mode (default): broker stops are checked when a bar is complete, with the lab rule (stop on the bid low for a
//   long, ask high for a short; at the stop on the position's first bar, else at the worse of stop and open).
//   Tester mode (MOCK_TESTER=1): MQLInfoInteger(MQL_TESTER) = 1 and TimeGMT() = TimeTradeServer() = TimeCurrent().
// Bars: per symbol, a binary file written by check/export_frames.py (magic "CRB1", int32 digits, int64 count, then
//   records <int64 server time, int32 bid open, high, low, close in points, int32 spread in points>) or a CSV
//   "time,open,high,low,close,tick_volume,spread" (the spike's layout). Only PERIOD_M1 is served.
// Broker (hedging, account currency EUR, USD -> EUR 0.89 unless MOCK_USDEUR): market orders fill at the current tick
//   (ask x (1 + slip_mkt) for a buy, bid x (1 - slip_mkt) for a sell); the position ticket is the order ticket; every
//   request leaves a history order (FILLED or REJECTED) and a deal; the closing deal carries the closing request's
//   magic; a stop off the tick grid, on the wrong side or closer than the stops level is refused (10016); a modify
//   inside the freeze level is refused (10029). Profit = side x (close - open) x volume x units x usdeur; commission =
//   -MOCK_COMM_<S> EUR per side per lot. Margin = lots x units x price x usdeur / leverage; tick value = tick size x
//   units x usdeur. Balance operations (deposits > 0, withdrawals < 0) from MOCK_PAYMENTS (CSV "time_srv,amount"),
//   each a DEAL_TYPE_BALANCE deal with the amount in DEAL_PROFIT; MOCK_PAY_SKEW=s shows the balance s seconds before
//   (s > 0) or after (s < 0) its deal. Scripted closed trades (step I, T7a) from MOCK_DEALS (CSV
//   "t_in,t_out,symbol,side,volume,price_in,price_out,magic,profit,commission,swap,reason_out").
// Restarts: MOCK_FROM <= T < MOCK_TO; positions, orders, deals, balance, tickets and (non-temporary) global variables
//   are saved in <MOCK_FILES>/_mock and reloaded at the next start (OnDeinit, new process, OnInit at FROM).
// Env:
//   MOCK_FILES=dir            MQL5\Files of the fake terminal; dir/_mock holds the state, deals.csv, orders.csv, log.txt
//   MOCK_SYMS=A,B,...         symbols (the broker's names, e.g. XAUUSD.r); MOCK_BARS_<A>=path, MOCK_DIGITS_<A>=2
//   MOCK_UNITS_<A> MOCK_VMIN_<A> MOCK_VSTEP_<A> MOCK_VMAX_<A> MOCK_LEV_<A> MOCK_COMM_<A> MOCK_STOPS_<A> MOCK_FREEZE_<A>  specs
//   MOCK_SLIP_MKT_BPS_<A> / MOCK_SLIP_STOP_BPS_<A>   broker slippage (default: the lab's fp_costs.json values)
//   MOCK_BALANCE=10000        starting balance (first start only)
//   MOCK_ACCOUNT=demo|real|contest, MOCK_VPS=0|1, MOCK_TESTER=0|1, MOCK_GMT_SHIFT=s (a wrong clock)
//   MOCK_INPUT_<InpName>=v    another value for an input of the EA
//   MOCK_TIMER_CALLS=n, MOCK_TICK=1, MOCK_COPY_FAIL=p (+ MOCK_SEED), MOCK_STOP_MAGIC0=1 (stop deals carry magic 0)
//   MOCK_QUIET=1              no per-request log lines
//   MOCK_HOLE_<A>=a-b@u,...   bars starting in [a, b) are not returned by CopyRates until server time u (0: a hole
//                             that stays); MOCK_UNSYNC_<A>=a-b,... SERIES_SYNCHRONIZED false then; MOCK_REVISE_<A>=t@u:d
//                             the bar at t gets its close moved by d from server time u on (a late revision, LATEBAR)
//   open orders: rp_open_orders (empty; a fault world may add orders in any state)
// Faults: check/mock_faults.h (step J) defines the mf_* hooks declared below; the S0 stub is neutral.
#pragma once
#include "mql5_shim.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <dirent.h>
#include <map>
#include <set>
#include <sstream>
#include <type_traits>
#include <vector>
#include <sys/stat.h>
#undef SEEK_SET
#undef SEEK_CUR
#undef SEEK_END

int OnInit();
void OnDeinit(const int reason);
void OnTimer();
void OnTick();
void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result);

template <typename T> T mock_input(const char *name, T def)
  {
   const char *e = getenv((string("MOCK_INPUT_") + name).c_str());
   if(!e) return def;
   if constexpr(std::is_same_v<T, string>) return string(e);
   else if constexpr(std::is_same_v<T, bool>) return strcmp(e, "true") == 0 || strcmp(e, "1") == 0;
   else if constexpr(std::is_floating_point_v<T>) return (T)atof(e);
   else return (T)atoll(e);
  }

// ------------------------------------------------------------------ world
struct RpSym
  {
   string name;
   int    digits = 2;
   double point = 0.01;
   double slip_mkt = 0.0, slip_stop = 0.0;
   double units = 1.0, vmin = 0.01, vstep = 0.01, vmax = 100.0, comm = 0.0, lev = 500.0;
   long   stops_level = 0, freeze_level = 0;
   std::vector<MqlRates> bars;
   long   cur = -1;                 // index of the forming bar
   long   stop_done = 0;            // bars [0, stop_done) were checked for broker stops
   int    stage = 0;                // tick mode: ticks of the forming bar played (1..4); fast mode: 1
   double tick_bid = 0.0;           // the last tick
   long   tick_time = 0;
   double vis_h = 0.0, vis_l = 0.0; // tick mode: extremes of the forming bar so far
   std::vector<std::array<long, 3>> holes;      // bars starting in [a, b) hidden from CopyRates until server time u (0: always)
   std::vector<std::pair<long, long>> unsync;   // SERIES_SYNCHRONIZED false while the server time is in [a, b)
   std::vector<std::array<double, 3>> revise;   // the bar at time t gets close += d from server time u on (a late revision)
  };
struct RpPos  { ulong ticket; string symbol; int type; double volume, price_open, sl, tp; long magic, time; string comment; };
struct RpDeal { ulong deal, order, position; long time; string symbol; int type, entry; double volume, price; int reason; long magic;
                string comment; double commission, swap, profit; };
struct RpOrder { ulong ticket; string symbol; int type, state; long setup, done; ulong position; long magic; double volume, price, sl, tp;
                 int reason; string comment; };
struct RpPay  { long t_deal, t_bal; double amount; bool booked; };

static std::vector<RpSym> rp_syms;
static std::vector<RpPos> rp_pos;
static std::vector<RpDeal> rp_deals;
static std::vector<RpOrder> rp_orders;
static std::vector<RpPay> rp_pays;
static std::map<string, double> rp_gv;
static std::map<string, long> rp_gv_time;
static std::set<string> rp_gv_temp;
static long   rp_now = 0;
static long   rp_ms = 0;                     // milliseconds inside the current second (GetTickCount64)
static string rp_root = ".";
static ulong  rp_next_ticket = 70000001, rp_next_deal = 80000001;
static ulong  rp_magic = 0;
static ulong  rp_deviation = 0;
static long   rp_selected = -1;              // index in rp_pos of the selected position
static int    rp_last_error = 0;
static FILE  *rp_log = nullptr;
static long   rp_copy_calls = 0, rp_pushes = 0;
static long   rp_flushes = 0;                // FileFlush calls of the EA (SPEC 2.6: once per timer pass at most)
static std::set<ulong> rp_sl_stuck;          // positions whose broker stop the broker does not execute (mock_faults sl_stuck)
[[maybe_unused]] static long rp_timer_calls = 0;
static MqlTradeResult rp_res = MqlTradeResult();
static double rp_copy_fail = 0.0;
static unsigned long long rp_rng = 88172645463325252ULL;
static long   rp_copy_failed = 0;
static double rp_balance = 10000.0;          // all booked deals
static double rp_usdeur = 0.89;
static long   rp_account_mode = ACCOUNT_TRADE_MODE_DEMO;
static int    rp_vps = 0, rp_tester = 0, rp_quiet = 0, rp_stop_magic0 = 0;
[[maybe_unused]] static int rp_tick = 0;
static long   rp_gmt_shift = 0;
static long   rp_pay_skew = 0;
static std::vector<long> rp_hist_deals, rp_hist_orders;   // HistorySelect result (indexes)
static std::vector<std::pair<MqlTradeTransaction, MqlTradeRequest>> rp_tx;
static bool   rp_in_handler = false;

// ---- fault hooks (check/mock_faults.h)
static void mf_init();
static bool mf_copyrates_fail(const string &sym);
static int  mf_request(MqlTradeRequest &req, MqlTradeResult &res);   // 0 = the normal path; 1 = handled (res set)
static void mf_after(const MqlTradeRequest &req, MqlTradeResult &res);
static void mf_event(long T);                                       // before the handlers of event T
static bool mf_connected();
static int  mf_session(const string &sym, int dow, uint idx, datetime &from, datetime &to);   // -1 = not handled

static bool rp_fail_now()                                   // fault injection: a terminal whose history is not ready
  {
   if(rp_copy_fail <= 0.0) return false;
   rp_rng ^= rp_rng << 13; rp_rng ^= rp_rng >> 7; rp_rng ^= rp_rng << 17;
   if((double)(rp_rng % 1000000) / 1e6 >= rp_copy_fail) return false;
   rp_last_error = 4066;
   rp_copy_failed++;
   return true;
  }

static string rp_path(string name)
  {
   for(char &c : name)
      if(c == '\\') c = '/';
   return rp_root + "/" + name;
  }
static RpSym *rp_find(const string &name)
  {
   for(RpSym &s : rp_syms)
      if(s.name == name) return &s;
   return nullptr;
  }
static double rp_norm(double v, int digits) { double p = std::pow(10.0, digits); return std::round(v * p) / p; }
static double rp_ask(const RpSym &s, double bid, int spread) { return rp_norm(bid + spread * s.point, s.digits); }
static void rp_logf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void rp_logf(const char *fmt, ...)
  {
   if(!rp_log) return;
   va_list ap;
   va_start(ap, fmt);
   vfprintf(rp_log, fmt, ap);
   va_end(ap);
   fputc('\n', rp_log);
  }

// ------------------------------------------------------------------ templates of the shim
template <typename T> static auto rp_arg(const T &v)
  {
   if constexpr(std::is_same_v<T, string>) return v.c_str();
   else return v;
  }
template <typename... A> static string rp_join(A... a)
  {
   std::ostringstream o;
   o.precision(17);
   ((o << a), ...);
   return o.str();
  }
template <typename... A> void Print(A... a) { if(rp_log) { fputs(rp_join(a...).c_str(), rp_log); fputc('\n', rp_log); } }
template <typename... A> void Alert(A... a) { Print(a...); }
template <typename... A> void Comment(A... a) {}
template <typename... A> string StringFormat(const string format, A... a)
  {
   char b[2048];
   snprintf(b, sizeof b, format.c_str(), rp_arg(a)...);
   return b;
  }
template <typename T> int ArraySize(const MqlArray<T> &a) { return (int)a.v.size(); }
template <typename T> int ArrayResize(MqlArray<T> &a, int n, int reserve)
  {
   if(n < 0) n = 0;
   if(reserve > 0 && (size_t)(n + reserve) > a.v.capacity() && (size_t)n > a.v.capacity()) a.v.reserve(n + reserve);
   a.v.resize(n);
   return n;
  }
template <typename T> void ArrayFree(MqlArray<T> &a) { a.v.clear(); }
template <typename T> bool ArraySetAsSeries(const MqlArray<T> &, bool flag) { return !flag; }
template <typename T> void ZeroMemory(T &v) { v = T(); }
template <typename T> int ArrayInitialize(MqlArray<T> &a, T value) { for(T &x : a.v) x = value; return (int)a.v.size(); }
template <typename T> int ArrayCopy(MqlArray<T> &d, const MqlArray<T> &s, int ds, int ss, int count)
  {
   int n = (count < 0) ? (int)s.v.size() - ss : count;
   if(n <= 0) return 0;
   if((int)d.v.size() < ds + n) d.v.resize(ds + n);
   for(int i = 0; i < n; i++) d.v[ds + i] = s.v[ss + i];
   return n;
  }
template <typename T> bool ArraySort(MqlArray<T> &a) { std::sort(a.v.begin(), a.v.end()); return true; }
template <typename T> int ArrayMaximum(const MqlArray<T> &a, int start, int count)
  {
   int n = (count < 0) ? (int)a.v.size() - start : count, best = -1;
   for(int i = start; i < start + n && i < (int)a.v.size(); i++)
      if(best < 0 || a.v[i] > a.v[best]) best = i;
   return best;
  }
template <typename T> int ArrayMinimum(const MqlArray<T> &a, int start, int count)
  {
   int n = (count < 0) ? (int)a.v.size() - start : count, best = -1;
   for(int i = start; i < start + n && i < (int)a.v.size(); i++)
      if(best < 0 || a.v[i] < a.v[best]) best = i;
   return best;
  }
template <typename T> void ArrayFill(MqlArray<T> &a, int start, int count, T value)
  {
   if((int)a.v.size() < start + count) a.v.resize(start + count);
   for(int i = start; i < start + count; i++) a.v[i] = value;
  }
bool StringToUpper(string &s) { for(char &c : s) c = (char)toupper((unsigned char)c); return true; }
bool StringToLower(string &s) { for(char &c : s) c = (char)tolower((unsigned char)c); return true; }
template <typename A, typename B> auto MathMax(A a, B b) -> decltype(a + b) { return a > b ? a : b; }
template <typename A, typename B> auto MathMin(A a, B b) -> decltype(a + b) { return a < b ? a : b; }

// ------------------------------------------------------------------ strings, maths
string IntegerToString(long number, int, ushort) { return std::to_string(number); }
string DoubleToString(double value, int digits)
  {
   char b[64];
   if(digits < 0) snprintf(b, sizeof b, "%.*e", -digits, value);      // docs: -1..-16 = scientific format
   else snprintf(b, sizeof b, "%.*f", digits > 16 ? 16 : digits, value);
   return b;
  }
ushort StringGetCharacter(const string s, int pos) { return (pos >= 0 && pos < (int)s.size()) ? (ushort)(unsigned char)s[pos] : 0; }
int StringLen(const string s) { return (int)s.size(); }
string StringSubstr(const string s, int start, int length)
  {
   if(start < 0 || start >= (int)s.size()) return "";
   return length < 0 ? s.substr(start) : s.substr(start, length);
  }
int StringFind(const string s, const string m, int start) { size_t p = s.find(m, start < 0 ? 0 : start); return p == string::npos ? -1 : (int)p; }
int StringReplace(string &s, const string f, const string r)
  {
   if(f.empty()) return 0;
   int n = 0;
   size_t p = 0;
   while((p = s.find(f, p)) != string::npos) { s.replace(p, f.size(), r); p += r.size(); n++; }
   return n;
  }
int StringSplit(const string s, const ushort sep, MqlArray<string> &r)
  {
   r.v.clear();
   if(s.empty()) return 0;
   string cur;
   for(char c : s)
     {
      if((ushort)(unsigned char)c == sep) { r.v.push_back(cur); cur.clear(); }
      else cur += c;
     }
   r.v.push_back(cur);
   return (int)r.v.size();
  }
int StringTrimLeft(string &s) { size_t p = s.find_first_not_of(" \t\r\n"); int n = (int)(p == string::npos ? s.size() : p); s.erase(0, n); return n; }
int StringTrimRight(string &s) { size_t p = s.find_last_not_of(" \t\r\n"); int n = (int)(p == string::npos ? s.size() : s.size() - p - 1); s.erase(s.size() - n); return n; }
double StringToDouble(const string s) { return strtod(s.c_str(), nullptr); }
long StringToInteger(const string s) { return strtoll(s.c_str(), nullptr, 10); }
int StringCompare(const string &a, const string &b, bool) { int c = a.compare(b); return c < 0 ? -1 : (c > 0 ? 1 : 0); }
double MathAbs(double v) { return std::fabs(v); }
double MathFloor(double v) { return std::floor(v); }
double MathCeil(double v) { return std::ceil(v); }
double MathRound(double v) { return std::round(v); }
double MathLog10(double v) { return std::log10(v); }
double MathSqrt(double v) { return std::sqrt(v); }
double MathLog(double v) { return std::log(v); }
double MathExp(double v) { return std::exp(v); }
double MathPow(double b, double e) { return std::pow(b, e); }
double MathMod(double a, double b) { return std::fmod(a, b); }
bool   MathIsValidNumber(double v) { return std::isfinite(v); }
double NormalizeDouble(double value, int digits) { return rp_norm(value, digits); }   // ASSUMPTION: as MT5 (nearest, half away)
int    GetLastError() { return rp_last_error; }
void   ResetLastError() { rp_last_error = 0; }
bool   IsStopped() { return false; }
bool   SendNotification(const string text) { rp_pushes++; rp_logf("PUSH %ld %s", rp_now, text.c_str()); return true; }

// ------------------------------------------------------------------ clock
datetime TimeTradeServer() { return rp_now; }
datetime TimeCurrent() { return rp_now; }
static bool rp_us_dst(long utc)                       // independent of the EA's code: tm arithmetic on the rule's dates
  {
   time_t t = (time_t)utc;
   struct tm g;
   gmtime_r(&t, &g);
   auto nth_sunday = [](int y, int m, int n) {
      struct tm a = {};
      a.tm_year = y - 1900; a.tm_mon = m - 1; a.tm_mday = 1;
      time_t f = timegm(&a);
      struct tm b;
      gmtime_r(&f, &b);
      return (long)f + (long)(((7 - b.tm_wday) % 7) + 7 * (n - 1)) * 86400;
   };
   long a = nth_sunday(g.tm_year + 1900, 3, 2) + 7 * 3600, b = nth_sunday(g.tm_year + 1900, 11, 1) + 6 * 3600;
   return utc >= a && utc < b;
  }
static long rp_srv_to_utc(long srv) { long u3 = srv - 3 * 3600; return rp_us_dst(u3) ? u3 : u3 + 3600; }
datetime TimeGMT() { return rp_tester ? rp_now : rp_srv_to_utc(rp_now) + rp_gmt_shift; }
datetime TimeLocal() { return TimeGMT(); }
ulong GetTickCount64() { return (ulong)rp_now * 1000ULL + (ulong)rp_ms; }
uint GetTickCount() { return (uint)(GetTickCount64() & 0xFFFFFFFFULL); }
bool TimeToStruct(datetime dt, MqlDateTime &d)
  {
   time_t t = (time_t)dt;
   struct tm tm;
   gmtime_r(&t, &tm);
   d.year = tm.tm_year + 1900; d.mon = tm.tm_mon + 1; d.day = tm.tm_mday; d.hour = tm.tm_hour; d.min = tm.tm_min; d.sec = tm.tm_sec;
   d.day_of_week = tm.tm_wday; d.day_of_year = tm.tm_yday;
   return true;
  }
datetime StructToTime(MqlDateTime &d)
  {
   struct tm tm = {};
   tm.tm_year = d.year - 1900; tm.tm_mon = d.mon - 1; tm.tm_mday = d.day; tm.tm_hour = d.hour; tm.tm_min = d.min; tm.tm_sec = d.sec;
   return (datetime)timegm(&tm);
  }
string TimeToString(datetime value, int mode)
  {
   MqlDateTime d;
   TimeToStruct(value, d);
   char b[40];
   if(mode & TIME_SECONDS) snprintf(b, sizeof b, "%04d.%02d.%02d %02d:%02d:%02d", d.year, d.mon, d.day, d.hour, d.min, d.sec);
   else snprintf(b, sizeof b, "%04d.%02d.%02d %02d:%02d", d.year, d.mon, d.day, d.hour, d.min);
   return b;
  }
bool EventSetTimer(int) { return true; }
bool EventSetMillisecondTimer(int) { return true; }
void EventKillTimer() {}

// ------------------------------------------------------------------ terminal, account
int MQLInfoInteger(ENUM_MQL_INFO_INTEGER p) { return p == MQL_TESTER ? rp_tester : 1; }
int TerminalInfoInteger(ENUM_TERMINAL_INFO_INTEGER p)
  {
   if(p == TERMINAL_CONNECTED) return mf_connected() ? 1 : 0;
   if(p == TERMINAL_VPS) return rp_vps;
   if(p == TERMINAL_MAXBARS) return 500000;
   return 1;
  }
static double rp_floating()
  {
   double f = 0.0;
   for(const RpPos &p : rp_pos)
     {
      RpSym *s = rp_find(p.symbol);
      if(!s || s->cur < 0) continue;
      double bid = s->tick_bid, ask = rp_ask(*s, s->tick_bid, s->bars[s->cur].spread);
      double px = p.type == 0 ? bid : ask;
      f += (p.type == 0 ? 1 : -1) * (px - p.price_open) * p.volume * s->units * rp_usdeur;
     }
   return f;
  }
static double rp_margin()
  {
   double m = 0.0;
   for(const RpPos &p : rp_pos)
      if(RpSym *s = rp_find(p.symbol)) m += p.volume * s->units * p.price_open * rp_usdeur / s->lev;
   return m;
  }
static double rp_balance_shown()                      // a payment can show in the balance before or after its deal
  {
   double b = rp_balance;
   for(const RpPay &p : rp_pays)
     {
      bool deal_in = p.booked, bal_in = p.t_bal <= rp_now;
      if(deal_in && !bal_in) b -= p.amount;
      else if(!deal_in && bal_in) b += p.amount;
     }
   return b;
  }
long AccountInfoInteger(ENUM_ACCOUNT_INFO_INTEGER p)
  {
   if(p == ACCOUNT_TRADE_MODE) return rp_account_mode;
   if(p == ACCOUNT_LEVERAGE) return 500;
   if(p == ACCOUNT_MARGIN_MODE) return ACCOUNT_MARGIN_MODE_RETAIL_HEDGING;
   if(p == ACCOUNT_LOGIN) return 12345678;
   return 1;
  }
double AccountInfoDouble(ENUM_ACCOUNT_INFO_DOUBLE p)
  {
   double bal = rp_balance_shown();
   if(p == ACCOUNT_BALANCE) return bal;
   if(p == ACCOUNT_EQUITY) return bal + rp_floating();
   if(p == ACCOUNT_MARGIN) return rp_margin();
   if(p == ACCOUNT_MARGIN_FREE) return bal + rp_floating() - rp_margin();
   return 0.0;
  }
string AccountInfoString(ENUM_ACCOUNT_INFO_STRING p) { return p == ACCOUNT_CURRENCY ? "EUR" : (p == ACCOUNT_COMPANY ? "Mock Markets" : "Mock-Server"); }

// ------------------------------------------------------------------ symbols and bars
bool SymbolSelect(const string name, bool) { return rp_find(name) != nullptr; }
bool SymbolIsSynchronized(const string name) { return rp_find(name) != nullptr; }
int SymbolsTotal(bool) { return (int)rp_syms.size(); }
string SymbolName(int pos, bool) { return (pos >= 0 && pos < (int)rp_syms.size()) ? rp_syms[pos].name : ""; }
long SymbolInfoInteger(const string name, ENUM_SYMBOL_INFO_INTEGER p)
  {
   RpSym *s = rp_find(name);
   if(!s) return 0;
   if(p == SYMBOL_DIGITS) return s->digits;
   if(p == SYMBOL_SPREAD) return s->cur >= 0 ? s->bars[s->cur].spread : 0;
   if(p == SYMBOL_TRADE_MODE) return SYMBOL_TRADE_MODE_FULL;
   if(p == SYMBOL_TRADE_STOPS_LEVEL) return s->stops_level;
   if(p == SYMBOL_TRADE_FREEZE_LEVEL) return s->freeze_level;
   if(p == SYMBOL_FILLING_MODE) return SYMBOL_FILLING_IOC;
   if(p == SYMBOL_ORDER_MODE) return SYMBOL_ORDER_MARKET | SYMBOL_ORDER_SL | SYMBOL_ORDER_TP | SYMBOL_ORDER_STOP | SYMBOL_ORDER_LIMIT;
   if(p == SYMBOL_EXPIRATION_MODE) return SYMBOL_EXPIRATION_GTC;
   if(p == SYMBOL_CHART_MODE) return SYMBOL_CHART_MODE_BID;
   if(p == SYMBOL_TIME) return s->tick_time;
   return 0;
  }
double SymbolInfoDouble(const string name, ENUM_SYMBOL_INFO_DOUBLE p)
  {
   RpSym *s = rp_find(name);
   if(!s) return 0.0;
   if(p == SYMBOL_POINT || p == SYMBOL_TRADE_TICK_SIZE) return s->point;
   if(p == SYMBOL_TRADE_TICK_VALUE || p == SYMBOL_TRADE_TICK_VALUE_LOSS) return s->point * s->units * rp_usdeur;
   if(p == SYMBOL_TRADE_CONTRACT_SIZE) return s->units;
   if(p == SYMBOL_VOLUME_MIN) return s->vmin;
   if(p == SYMBOL_VOLUME_STEP) return s->vstep;
   if(p == SYMBOL_VOLUME_MAX) return s->vmax;
   if(s->cur < 0) return 0.0;
   if(p == SYMBOL_BID) return s->tick_bid;
   if(p == SYMBOL_ASK) return rp_ask(*s, s->tick_bid, s->bars[s->cur].spread);
   return 0.0;
  }
string SymbolInfoString(const string name, ENUM_SYMBOL_INFO_STRING p)
  {
   if(p == SYMBOL_DESCRIPTION || p == SYMBOL_PATH) return name;
   if(p == SYMBOL_CURRENCY_BASE) return name.substr(0, 3);
   return "USD";
  }
bool SymbolInfoTick(const string name, MqlTick &k)
  {
   RpSym *s = rp_find(name);
   if(!s || s->cur < 0) return false;
   k = MqlTick();
   k.bid = s->tick_bid;
   k.ask = rp_ask(*s, s->tick_bid, s->bars[s->cur].spread);
   k.time = s->tick_time;
   k.time_msc = s->tick_time * 1000;
   return true;
  }
bool SymbolInfoSessionTrade(const string name, ENUM_DAY_OF_WEEK dow, uint idx, datetime &from, datetime &to)
  {
   int r = mf_session(name, (int)dow, idx, from, to);
   if(r >= 0) return r == 1;
   from = 0;
   to = 0;
   return false;                                    // no session information unless a fault world gives one
  }
long SeriesInfoInteger(const string name, ENUM_TIMEFRAMES, ENUM_SERIES_INFO_INTEGER p)
  {
   RpSym *s = rp_find(name);
   if(!s) return 0;
   if(p == SERIES_SYNCHRONIZED)
     {
      for(const auto &u : s->unsync)
         if(rp_now >= u.first && rp_now < u.second) return 0;
      return 1;
     }
   if(p == SERIES_BARS_COUNT) return s->cur + 1;
   if(p == SERIES_FIRSTDATE || p == SERIES_SERVER_FIRSTDATE || p == SERIES_TERMINAL_FIRSTDATE) return s->bars.empty() ? 0 : s->bars[0].time;
   if(p == SERIES_LASTBAR_DATE) return s->cur >= 0 ? s->bars[s->cur].time : 0;
   return 0;
  }
bool SeriesInfoInteger(const string name, ENUM_TIMEFRAMES tf, ENUM_SERIES_INFO_INTEGER p, long &v) { v = SeriesInfoInteger(name, tf, p); return true; }
static bool rp_hidden(const RpSym &s, long t)
  {
   for(const auto &h : s.holes)
      if(t >= h[0] && t < h[1] && (h[2] == 0 || rp_now < h[2])) return true;
   return false;
  }
static MqlRates rp_visible(const RpSym &s, long i)
  {
   MqlRates b = s.bars[i];
   for(const auto &r : s.revise)
      if((long)r[0] == b.time && rp_now >= (long)r[1])
        {
         b.close += r[2];
         b.high = std::max(b.high, b.close);
         b.low = std::min(b.low, b.close);
        }
   if(i == s.cur && s.stage < 4)                          // the forming bar as far as its ticks went
     {
      b.close = s.tick_bid;
      b.high = s.vis_h;
      b.low = s.vis_l;
      b.tick_volume = s.stage;
     }
   return b;
  }
static void rp_fill(const RpSym &s, long a, long b, MqlArray<MqlRates> &r)
  {
   r.v.clear();
   for(long i = std::max(a, 0L); i <= b; i++)
      if(!rp_hidden(s, s.bars[i].time)) r.v.push_back(rp_visible(s, i));
  }
int CopyRates(const string name, ENUM_TIMEFRAMES tf, int start_pos, int count, MqlArray<MqlRates> &r)
  {
   rp_copy_calls++;
   RpSym *s = rp_find(name);
   r.v.clear();
   if(rp_fail_now() || mf_copyrates_fail(name)) return -1;
   if(!s || tf != PERIOD_M1 || s->cur < 0 || count <= 0 || start_pos < 0) { rp_last_error = 4401; return -1; }
   long hi = s->cur - start_pos;
   if(hi < 0) { rp_last_error = 4401; return -1; }
   rp_fill(*s, hi - count + 1, hi, r);
   return (int)r.v.size();
  }
static long rp_lower(const RpSym &s, long t)           // first bar with time >= t (by hand: under _GLIBCXX_DEBUG
  {                                                   // std::lower_bound checks the whole range on every call)
   long lo = 0, hi = (long)s.bars.size();
   while(lo < hi)
     {
      long mid = lo + (hi - lo) / 2;
      if(s.bars[mid].time < t) lo = mid + 1;
      else hi = mid;
     }
   return lo;
  }
int CopyRates(const string name, ENUM_TIMEFRAMES tf, datetime start_time, datetime stop_time, MqlArray<MqlRates> &r)
  {
   rp_copy_calls++;
   RpSym *s = rp_find(name);
   r.v.clear();
   if(rp_fail_now() || mf_copyrates_fail(name)) return -1;
   if(!s || tf != PERIOD_M1 || s->cur < 0) { rp_last_error = 4401; return -1; }
   long a = rp_lower(*s, start_time), b = std::min(rp_lower(*s, stop_time + 1) - 1, s->cur);
   if(b < a) return 0;
   rp_fill(*s, a, b, r);
   return (int)r.v.size();
  }
int CopyRates(const string name, ENUM_TIMEFRAMES tf, datetime start_time, int count, MqlArray<MqlRates> &r)
  {
   rp_copy_calls++;
   RpSym *s = rp_find(name);
   r.v.clear();
   if(rp_fail_now() || mf_copyrates_fail(name)) return -1;
   if(!s || tf != PERIOD_M1 || s->cur < 0 || count <= 0) { rp_last_error = 4401; return -1; }
   long b = std::min(rp_lower(*s, start_time + 1) - 1, s->cur);
   rp_fill(*s, b - count + 1, b, r);
   return (int)r.v.size();
  }

// ------------------------------------------------------------------ files and global variables
static std::map<int, FILE *> rp_files;
static int rp_next_handle = 1;
static void rp_mkdirs(const string &p)
  {
   for(size_t i = 1; i <= p.size(); i++)
      if(i == p.size() || p[i] == '/') mkdir(p.substr(0, i).c_str(), 0755);
  }
bool FolderCreate(const string name, int) { rp_mkdirs(rp_path(name)); return true; }
bool FileIsExist(const string name, int) { struct stat st; return stat(rp_path(name).c_str(), &st) == 0; }
bool FileDelete(const string name, int) { return remove(rp_path(name).c_str()) == 0; }
int FileOpen(const string name, int flags, short, uint)
  {
   string p = rp_path(name);
   const char *mode = (flags & FILE_WRITE) ? ((flags & FILE_READ) ? (FileIsExist(name, 0) ? "r+" : "w+") : "w") : "r";
   FILE *f = fopen(p.c_str(), mode);
   if(!f) { rp_last_error = 5004; return INVALID_HANDLE; }
   rp_files[rp_next_handle] = f;
   return rp_next_handle++;
  }
bool FileSeek(int h, long offset, ENUM_FILE_POSITION origin)
  {
   if(!rp_files.count(h)) return false;
   return fseek(rp_files[h], offset, origin == SEEK_END ? 2 : origin == SEEK_CUR ? 1 : 0) == 0;
  }
uint FileWriteString(int h, const string text, int) { if(!rp_files.count(h)) return 0; fputs(text.c_str(), rp_files[h]); return (uint)text.size(); }
string FileReadString(int h, int)
  {
   if(!rp_files.count(h)) return "";
   string out;
   int c;
   while((c = fgetc(rp_files[h])) != EOF && c != '\n')
      if(c != '\r') out += (char)c;
   return out;
  }
bool FileIsEnding(int h)
  {
   if(!rp_files.count(h)) return true;
   int c = fgetc(rp_files[h]);
   if(c == EOF) return true;
   ungetc(c, rp_files[h]);
   return false;
  }
void FileFlush(int h) { rp_flushes++; if(rp_files.count(h)) fflush(rp_files[h]); }
void FileClose(int h) { if(rp_files.count(h)) { fclose(rp_files[h]); rp_files.erase(h); } }
static std::map<long, std::pair<std::vector<string>, size_t>> rp_finds;
static long rp_next_find = 1;
static bool rp_glob(const string &pat, const string &s)      // '*' and '?' only
  {
   size_t p = 0, q = 0, star = string::npos, mark = 0;
   while(q < s.size())
     {
      if(p < pat.size() && (pat[p] == '?' || pat[p] == s[q])) { p++; q++; }
      else if(p < pat.size() && pat[p] == '*') { star = p++; mark = q; }
      else if(star != string::npos) { p = star + 1; q = ++mark; }
      else return false;
     }
   while(p < pat.size() && pat[p] == '*') p++;
   return p == pat.size();
  }
long FileFindFirst(const string filter, string &found, int)
  {
   string f = filter;
   for(char &c : f)
      if(c == '\\') c = '/';
   size_t k = f.rfind('/');
   string dir = k == string::npos ? "" : f.substr(0, k), pat = k == string::npos ? f : f.substr(k + 1);
   std::vector<string> names;
   if(DIR *d = opendir(rp_path(dir).c_str()))
     {
      while(struct dirent *e = readdir(d))
         if(e->d_name[0] != '.' && rp_glob(pat, e->d_name)) names.push_back(e->d_name);
      closedir(d);
     }
   std::sort(names.begin(), names.end());
   if(names.empty()) return INVALID_HANDLE;
   found = names[0];
   rp_finds[rp_next_find] = {names, 1};
   return rp_next_find++;
  }
bool FileFindNext(long h, string &found)
  {
   auto it = rp_finds.find(h);
   if(it == rp_finds.end() || it->second.second >= it->second.first.size()) return false;
   found = it->second.first[it->second.second++];
   return true;
  }
void FileFindClose(long h) { rp_finds.erase(h); }
bool GlobalVariableCheck(const string name) { return rp_gv.count(name) > 0; }
double GlobalVariableGet(const string name) { auto it = rp_gv.find(name); return it == rp_gv.end() ? 0.0 : it->second; }
datetime GlobalVariableSet(const string name, double value) { rp_gv[name] = value; rp_gv_time[name] = rp_now; return rp_now; }
datetime GlobalVariableTime(const string name) { auto it = rp_gv_time.find(name); return it == rp_gv_time.end() ? 0 : it->second; }
bool GlobalVariableDel(const string name) { rp_gv_temp.erase(name); rp_gv_time.erase(name); return rp_gv.erase(name) > 0; }
bool GlobalVariableTemp(const string name)
  {
   if(rp_gv.count(name)) return true;
   rp_gv[name] = 0.0;
   rp_gv_time[name] = rp_now;
   rp_gv_temp.insert(name);
   return true;
  }
bool GlobalVariableSetOnCondition(const string name, double value, double check)
  {
   auto it = rp_gv.find(name);
   if(it == rp_gv.end() || it->second != check) return false;
   it->second = value;
   rp_gv_time[name] = rp_now;
   return true;
  }
int GlobalVariablesTotal() { return (int)rp_gv.size(); }
string GlobalVariableName(int index) { int i = 0; for(auto &kv : rp_gv) if(i++ == index) return kv.first; return ""; }
void GlobalVariablesFlush() {}

// ------------------------------------------------------------------ broker: orders, positions, deals, CTrade
static void rp_queue_tx(int type, ulong deal, ulong order, const string &sym, ulong position, const MqlTradeRequest &req)
  {
   MqlTradeTransaction t = MqlTradeTransaction();
   t.type = (ENUM_TRADE_TRANSACTION_TYPE)type;
   t.deal = deal;
   t.order = order;
   t.symbol = sym;
   t.position = position;
   rp_tx.push_back({t, req});
  }
static void rp_deliver_tx()
  {
   if(rp_in_handler) return;
   while(!rp_tx.empty())
     {
      auto x = rp_tx.front();
      rp_tx.erase(rp_tx.begin());
      MqlTradeResult r = MqlTradeResult();
      rp_in_handler = true;
      OnTradeTransaction(x.first, x.second, r);
      rp_in_handler = false;
     }
  }
static ulong rp_add_deal(const RpPos &p, int type, int entry, double vol, double price, int reason, long magic, long when,
                         double profit, double commission, ulong order, const string &comment)
  {
   RpDeal d = {rp_next_deal++, order, p.ticket, when, p.symbol, type, entry, vol, price, reason, magic, comment, commission, 0.0, profit};
   rp_deals.push_back(d);
   rp_balance += profit + commission;
   MqlTradeRequest q = MqlTradeRequest();
   rp_queue_tx(TRADE_TRANSACTION_DEAL_ADD, d.deal, order, p.symbol, p.ticket, q);
   return d.deal;
  }
static ulong rp_add_order(const string &sym, int type, int state, ulong position, long magic, double vol, double price, double sl,
                          double tp, const string &comment)
  {
   RpOrder o = {rp_next_ticket++, sym, type, state, rp_now, rp_now, position, magic, vol, price, sl, tp, 3, comment};
   if(o.position == 0 && state == ORDER_STATE_FILLED) o.position = o.ticket;   // an opening order: the position id is its ticket
   rp_orders.push_back(o);
   return o.ticket;
  }
static bool rp_on_grid(const RpSym &s, double v) { return std::fabs(v - rp_norm(v, s.digits)) < 1e-9 * std::max(1.0, std::fabs(v)); }
static bool rp_stop_ok(const RpSym &s, int type, double sl, double bid, double ask)
  {
   if(sl == 0.0) return true;
   if(!rp_on_grid(s, sl)) return false;
   double lvl = s.stops_level * s.point;
   return type == 0 ? sl <= bid - lvl && sl < bid : sl >= ask + lvl && sl > ask;
  }
static double rp_comm(const RpSym &s, double vol) { return -s.comm * vol; }
static double rp_profit(const RpSym &s, int type, double open, double close, double vol)
  {
   return (type == 0 ? 1 : -1) * (close - open) * vol * s.units * rp_usdeur;
  }
static bool rp_open(const string symbol, int type, double volume, double sl, double tp, const string comment, ulong magic)
  {
   rp_res = MqlTradeResult();
   RpSym *s = rp_find(symbol);
   if(!s || s->cur < 0 || volume <= 0) { rp_res.retcode = 10013; return false; }
   double bid = s->tick_bid, ask = rp_ask(*s, s->tick_bid, s->bars[s->cur].spread);
   if(!rp_stop_ok(*s, type, sl, bid, ask))
     {
      rp_res.retcode = TRADE_RETCODE_INVALID_STOPS;
      rp_add_order(symbol, type, ORDER_STATE_REJECTED, 0, (long)magic, volume, 0.0, sl, tp, comment);
      return false;
     }
   double px = (type == 0) ? ask * (1 + s->slip_mkt) : bid * (1 - s->slip_mkt);
   ulong ord = rp_add_order(symbol, type, ORDER_STATE_FILLED, 0, (long)magic, volume, px, sl, tp, comment);
   RpPos p = {ord, symbol, type, volume, px, sl, tp, (long)magic, rp_now, comment};
   rp_pos.push_back(p);
   ulong deal = rp_add_deal(p, type, DEAL_ENTRY_IN, volume, px, DEAL_REASON_EXPERT, (long)magic, rp_now, 0.0, rp_comm(*s, volume), ord, comment);
   rp_res.retcode = TRADE_RETCODE_DONE; rp_res.order = ord; rp_res.deal = deal; rp_res.price = px; rp_res.volume = volume;
   rp_res.bid = bid; rp_res.ask = ask;
   if(!rp_quiet) rp_logf("OPEN %s %s %.2f px=%.10g sl=%.10g t=%ld ticket=%lu magic=%lu", symbol.c_str(), type == 0 ? "buy" : "sell", volume, px, sl, rp_now, ord, magic);
   return true;
  }
static long rp_pos_index(ulong ticket)
  {
   for(size_t i = 0; i < rp_pos.size(); i++)
      if(rp_pos[i].ticket == ticket) return (long)i;
   return -1;
  }
// `when`: the deal's time. A stop filled during a bar in fast mode is stamped at the last second of that bar.
static void rp_close_at(long i, double px, int reason, long when, long magic)
  {
   RpPos p = rp_pos[i];
   RpSym *s = rp_find(p.symbol);
   ulong ord = rp_add_order(p.symbol, p.type == 0 ? 1 : 0, ORDER_STATE_FILLED, p.ticket, magic, p.volume, px, 0.0, 0.0, "");
   rp_add_deal(p, p.type == 0 ? 1 : 0, DEAL_ENTRY_OUT, p.volume, px, reason, magic, when, rp_profit(*s, p.type, p.price_open, px, p.volume),
               rp_comm(*s, p.volume), ord, p.comment);
   if(!rp_quiet) rp_logf("CLOSE %s ticket=%lu px=%.10g reason=%d t=%ld magic=%ld", p.symbol.c_str(), p.ticket, px, reason, when, magic);
   rp_pos.erase(rp_pos.begin() + i);
   rp_selected = -1;
  }
static bool rp_close(ulong ticket, ulong magic)
  {
   rp_res = MqlTradeResult();
   long i = rp_pos_index(ticket);
   if(i < 0) { rp_res.retcode = TRADE_RETCODE_POSITION_CLOSED; return false; }
   RpSym *s = rp_find(rp_pos[i].symbol);
   if(s->cur < 0) { rp_res.retcode = TRADE_RETCODE_MARKET_CLOSED; return false; }
   double bid = s->tick_bid, ask = rp_ask(*s, s->tick_bid, s->bars[s->cur].spread);
   double px = (rp_pos[i].type == 0) ? bid * (1 - s->slip_mkt) : ask * (1 + s->slip_mkt);
   rp_res.retcode = TRADE_RETCODE_DONE; rp_res.price = px; rp_res.order = rp_next_ticket; rp_res.volume = rp_pos[i].volume;
   rp_close_at(i, px, DEAL_REASON_EXPERT, rp_now, (long)magic);
   rp_res.deal = rp_next_deal - 1;
   return true;
  }
static bool rp_modify(ulong ticket, double sl, double tp)
  {
   rp_res = MqlTradeResult();
   long i = rp_pos_index(ticket);
   if(i < 0) { rp_res.retcode = TRADE_RETCODE_POSITION_CLOSED; return false; }
   RpPos &p = rp_pos[i];
   RpSym *s = rp_find(p.symbol);
   double bid = s->tick_bid, ask = rp_ask(*s, s->tick_bid, s->bars[s->cur].spread);
   if(!rp_stop_ok(*s, p.type, sl, bid, ask)) { rp_res.retcode = TRADE_RETCODE_INVALID_STOPS; return false; }
   double fz = s->freeze_level * s->point;
   if(fz > 0 && p.sl != 0.0 && (p.type == 0 ? bid - p.sl <= fz : p.sl - ask <= fz)) { rp_res.retcode = TRADE_RETCODE_FROZEN; return false; }
   p.sl = sl; p.tp = tp;
   rp_res.retcode = TRADE_RETCODE_DONE;
   return true;
  }
// one request through the fault hooks
static bool rp_request(MqlTradeRequest &req)
  {
   rp_res = MqlTradeResult();
   int h = mf_request(req, rp_res);
   bool ok = false;
   if(h == 1) ok = rp_res.retcode == TRADE_RETCODE_DONE;
   else if(req.action == TRADE_ACTION_DEAL && req.position != 0) ok = rp_close(req.position, req.magic);
   else if(req.action == TRADE_ACTION_DEAL) ok = rp_open(req.symbol, req.type == ORDER_TYPE_BUY ? 0 : 1, req.volume, req.sl, req.tp, req.comment, req.magic);
   else if(req.action == TRADE_ACTION_SLTP) ok = rp_modify(req.position, req.sl, req.tp);
   else rp_res.retcode = 10013;
   mf_after(req, rp_res);
   return ok;
  }
string CTrade::ResultComment(void) const { return rp_res.comment; }
void   CTrade::SetAsyncMode(const bool) {}
void   CTrade::SetTypeFilling(const ENUM_ORDER_TYPE_FILLING) {}
ulong  CTrade::RequestMagic(void) const { return rp_magic; }
bool OrderCheck(const MqlTradeRequest &, MqlTradeCheckResult &r)
  {
   r = MqlTradeCheckResult();
   r.retcode = 0;                                      // 0: the check passed (the request itself decides later)
   r.balance = AccountInfoDouble(ACCOUNT_BALANCE);
   r.equity = AccountInfoDouble(ACCOUNT_EQUITY);
   r.margin = rp_margin();
   r.margin_free = r.equity - r.margin;
   return true;
  }
uint   CTrade::ResultRetcode(void) const { return rp_res.retcode; }
double CTrade::ResultPrice(void) const { return rp_res.price; }
ulong  CTrade::ResultDeal(void) const { return rp_res.deal; }
ulong  CTrade::ResultOrder(void) const { return rp_res.order; }
double CTrade::ResultVolume(void) const { return rp_res.volume; }
string CTrade::ResultRetcodeDescription(void) const { return "retcode " + std::to_string(rp_res.retcode); }
void   CTrade::SetDeviationInPoints(const ulong d) { rp_deviation = d; }
bool   CTrade::SetTypeFillingBySymbol(const string) { return true; }
void   CTrade::SetExpertMagicNumber(const ulong magic) { rp_magic = magic; }
static MqlTradeRequest rp_req(int action, const string &sym, int type, double vol, double sl, double tp, ulong position, const string &comment)
  {
   MqlTradeRequest q = MqlTradeRequest();
   q.action = (ENUM_TRADE_REQUEST_ACTIONS)action; q.symbol = sym; q.type = (ENUM_ORDER_TYPE)type; q.volume = vol; q.sl = sl; q.tp = tp;
   q.position = position; q.comment = comment; q.magic = rp_magic; q.deviation = rp_deviation;
   return q;
  }
bool CTrade::Buy(const double volume, const string symbol, double, const double sl, const double tp, const string comment)
  { MqlTradeRequest q = rp_req(TRADE_ACTION_DEAL, symbol, ORDER_TYPE_BUY, volume, sl, tp, 0, comment); return rp_request(q); }
bool CTrade::Sell(const double volume, const string symbol, double, const double sl, const double tp, const string comment)
  { MqlTradeRequest q = rp_req(TRADE_ACTION_DEAL, symbol, ORDER_TYPE_SELL, volume, sl, tp, 0, comment); return rp_request(q); }
bool CTrade::PositionModify(const ulong ticket, const double sl, const double tp)
  {
   long i = rp_pos_index(ticket);
   MqlTradeRequest q = rp_req(TRADE_ACTION_SLTP, i >= 0 ? rp_pos[i].symbol : "", 0, 0.0, sl, tp, ticket, "");
   return rp_request(q);
  }
bool CTrade::PositionClose(const ulong ticket, const ulong)
  {
   long i = rp_pos_index(ticket);
   if(i < 0) { rp_res = MqlTradeResult(); rp_res.retcode = TRADE_RETCODE_POSITION_CLOSED; return false; }
   MqlTradeRequest q = rp_req(TRADE_ACTION_DEAL, rp_pos[i].symbol, rp_pos[i].type == 0 ? ORDER_TYPE_SELL : ORDER_TYPE_BUY, rp_pos[i].volume,
                              0.0, 0.0, ticket, "");
   return rp_request(q);
  }
bool OrderSend(const MqlTradeRequest &request, MqlTradeResult &result)
  {
   MqlTradeRequest q = request;
   bool ok = rp_request(q);
   result = rp_res;
   return ok;
  }
bool OrderCalcMargin(ENUM_ORDER_TYPE, const string symbol, double volume, double price, double &margin)
  {
   RpSym *s = rp_find(symbol);
   if(!s) return false;
   margin = volume * s->units * price * rp_usdeur / s->lev;
   return true;
  }
bool OrderCalcProfit(ENUM_ORDER_TYPE action, const string symbol, double volume, double po, double pc, double &profit)
  {
   RpSym *s = rp_find(symbol);
   if(!s) return false;
   profit = rp_profit(*s, action == ORDER_TYPE_BUY ? 0 : 1, po, pc, volume);
   return true;
  }
// open orders: market orders never stay open here; a fault world (mock_faults.h) may put some in rp_open_orders
static std::vector<RpOrder> rp_open_orders;
static long rp_osel = -1;
int OrdersTotal() { return (int)rp_open_orders.size(); }
ulong OrderGetTicket(int i) { if(i < 0 || i >= (int)rp_open_orders.size()) return 0; rp_osel = i; return rp_open_orders[i].ticket; }
bool OrderSelect(ulong t)
  {
   for(size_t i = 0; i < rp_open_orders.size(); i++)
      if(rp_open_orders[i].ticket == t) { rp_osel = (long)i; return true; }
   return false;
  }
long OrderGetInteger(ENUM_ORDER_PROPERTY_INTEGER p)
  {
   if(rp_osel < 0 || rp_osel >= (long)rp_open_orders.size()) return 0;
   const RpOrder &o = rp_open_orders[rp_osel];
   if(p == ORDER_MAGIC) return o.magic;
   if(p == ORDER_TYPE) return o.type;
   if(p == ORDER_TICKET) return (long)o.ticket;
   if(p == ORDER_TIME_SETUP) return o.setup;
   if(p == ORDER_STATE) return o.state;
   if(p == ORDER_POSITION_ID) return (long)o.position;
   return 0;
  }
double OrderGetDouble(ENUM_ORDER_PROPERTY_DOUBLE p)
  {
   if(rp_osel < 0 || rp_osel >= (long)rp_open_orders.size()) return 0.0;
   const RpOrder &o = rp_open_orders[rp_osel];
   if(p == ORDER_VOLUME_INITIAL || p == ORDER_VOLUME_CURRENT) return o.volume;
   if(p == ORDER_PRICE_OPEN || p == ORDER_PRICE_CURRENT) return o.price;
   if(p == ORDER_SL) return o.sl;
   if(p == ORDER_TP) return o.tp;
   return 0.0;
  }
string OrderGetString(ENUM_ORDER_PROPERTY_STRING p)
  {
   if(rp_osel < 0 || rp_osel >= (long)rp_open_orders.size()) return "";
   return p == ORDER_SYMBOL ? rp_open_orders[rp_osel].symbol : rp_open_orders[rp_osel].comment;
  }
int PositionsTotal() { return (int)rp_pos.size(); }
ulong PositionGetTicket(int index) { if(index < 0 || index >= (int)rp_pos.size()) return 0; rp_selected = index; return rp_pos[index].ticket; }
string PositionGetSymbol(int index) { if(index < 0 || index >= (int)rp_pos.size()) return ""; rp_selected = index; return rp_pos[index].symbol; }
bool PositionSelectByTicket(ulong ticket) { rp_selected = rp_pos_index(ticket); return rp_selected >= 0; }
bool PositionSelect(const string symbol)
  {
   for(size_t i = 0; i < rp_pos.size(); i++)
      if(rp_pos[i].symbol == symbol) { rp_selected = (long)i; return true; }
   return false;
  }
long PositionGetInteger(ENUM_POSITION_PROPERTY_INTEGER p)
  {
   if(rp_selected < 0) return 0;
   const RpPos &x = rp_pos[rp_selected];
   if(p == POSITION_TICKET || p == POSITION_IDENTIFIER) return (long)x.ticket;
   if(p == POSITION_TIME) return x.time;
   if(p == POSITION_TYPE) return x.type;
   if(p == POSITION_MAGIC) return x.magic;
   return 0;
  }
double PositionGetDouble(ENUM_POSITION_PROPERTY_DOUBLE p)
  {
   if(rp_selected < 0) return 0.0;
   const RpPos &x = rp_pos[rp_selected];
   if(p == POSITION_VOLUME) return x.volume;
   if(p == POSITION_PRICE_OPEN) return x.price_open;
   if(p == POSITION_SL) return x.sl;
   if(p == POSITION_TP) return x.tp;
   RpSym *s = rp_find(x.symbol);
   if(!s || s->cur < 0) return 0.0;
   double px = x.type == 0 ? s->tick_bid : rp_ask(*s, s->tick_bid, s->bars[s->cur].spread);
   if(p == POSITION_PRICE_CURRENT) return px;
   if(p == POSITION_PROFIT) return rp_profit(*s, x.type, x.price_open, px, x.volume);
   return 0.0;
  }
string PositionGetString(ENUM_POSITION_PROPERTY_STRING p)
  {
   if(rp_selected < 0) return "";
   return p == POSITION_SYMBOL ? rp_pos[rp_selected].symbol : rp_pos[rp_selected].comment;
  }
// ---- history
bool HistorySelect(datetime from, datetime to)
  {
   rp_hist_deals.clear();
   rp_hist_orders.clear();
   for(size_t i = 0; i < rp_deals.size(); i++)
      if(rp_deals[i].time >= from && rp_deals[i].time <= to) rp_hist_deals.push_back((long)i);
   for(size_t i = 0; i < rp_orders.size(); i++)
      if(rp_orders[i].setup >= from && rp_orders[i].setup <= to) rp_hist_orders.push_back((long)i);
   return true;
  }
bool HistorySelectByPosition(long position_id)
  {
   rp_hist_deals.clear();
   rp_hist_orders.clear();
   for(size_t i = 0; i < rp_deals.size(); i++)
      if((long)rp_deals[i].position == position_id) rp_hist_deals.push_back((long)i);
   for(size_t i = 0; i < rp_orders.size(); i++)
      if((long)rp_orders[i].position == position_id) rp_hist_orders.push_back((long)i);
   return true;
  }
int HistoryDealsTotal() { return (int)rp_hist_deals.size(); }
ulong HistoryDealGetTicket(int i) { return (i >= 0 && i < (int)rp_hist_deals.size()) ? rp_deals[rp_hist_deals[i]].deal : 0; }
static const RpDeal *rp_deal_of(ulong t)
  {
   for(const RpDeal &d : rp_deals)
      if(d.deal == t) return &d;
   return nullptr;
  }
bool HistoryDealSelect(ulong t) { return rp_deal_of(t) != nullptr; }
long HistoryDealGetInteger(ulong t, ENUM_DEAL_PROPERTY_INTEGER p)
  {
   const RpDeal *d = rp_deal_of(t);
   if(!d) return 0;
   if(p == DEAL_MAGIC) return d->magic;
   if(p == DEAL_ENTRY) return d->entry;
   if(p == DEAL_TYPE) return d->type;
   if(p == DEAL_POSITION_ID) return (long)d->position;
   if(p == DEAL_ORDER) return (long)d->order;
   if(p == DEAL_REASON) return d->reason;
   if(p == DEAL_TIME) return d->time;
   if(p == DEAL_TIME_MSC) return d->time * 1000;
   if(p == DEAL_TICKET) return (long)d->deal;
   return 0;
  }
double HistoryDealGetDouble(ulong t, ENUM_DEAL_PROPERTY_DOUBLE p)
  {
   const RpDeal *d = rp_deal_of(t);
   if(!d) return 0.0;
   if(p == DEAL_VOLUME) return d->volume;
   if(p == DEAL_PRICE) return d->price;
   if(p == DEAL_COMMISSION) return d->commission;
   if(p == DEAL_SWAP) return d->swap;
   if(p == DEAL_PROFIT) return d->profit;
   return 0.0;
  }
string HistoryDealGetString(ulong t, ENUM_DEAL_PROPERTY_STRING p)
  {
   const RpDeal *d = rp_deal_of(t);
   if(!d) return "";
   return p == DEAL_SYMBOL ? d->symbol : d->comment;
  }
int HistoryOrdersTotal() { return (int)rp_hist_orders.size(); }
ulong HistoryOrderGetTicket(int i) { return (i >= 0 && i < (int)rp_hist_orders.size()) ? rp_orders[rp_hist_orders[i]].ticket : 0; }
static const RpOrder *rp_order_of(ulong t)
  {
   for(const RpOrder &o : rp_orders)
      if(o.ticket == t) return &o;
   return nullptr;
  }
bool HistoryOrderSelect(ulong t) { return rp_order_of(t) != nullptr; }
long HistoryOrderGetInteger(ulong t, ENUM_ORDER_PROPERTY_INTEGER p)
  {
   const RpOrder *o = rp_order_of(t);
   if(!o) return 0;
   if(p == ORDER_MAGIC) return o->magic;
   if(p == ORDER_TYPE) return o->type;
   if(p == ORDER_TICKET) return (long)o->ticket;
   if(p == ORDER_TIME_SETUP) return o->setup;
   if(p == ORDER_TIME_SETUP_MSC) return o->setup * 1000;
   if(p == ORDER_TIME_DONE) return o->done;
   if(p == ORDER_STATE) return o->state;
   if(p == ORDER_POSITION_ID) return (long)o->position;
   if(p == ORDER_REASON) return o->reason;
   return 0;
  }
double HistoryOrderGetDouble(ulong t, ENUM_ORDER_PROPERTY_DOUBLE p)
  {
   const RpOrder *o = rp_order_of(t);
   if(!o) return 0.0;
   if(p == ORDER_VOLUME_INITIAL || p == ORDER_VOLUME_CURRENT) return o->volume;
   if(p == ORDER_PRICE_OPEN || p == ORDER_PRICE_CURRENT) return o->price;
   if(p == ORDER_SL) return o->sl;
   if(p == ORDER_TP) return o->tp;
   return 0.0;
  }
string HistoryOrderGetString(ulong t, ENUM_ORDER_PROPERTY_STRING p)
  {
   const RpOrder *o = rp_order_of(t);
   if(!o) return "";
   return p == ORDER_SYMBOL ? o->symbol : o->comment;
  }

// the broker's stops on bar i of symbol s (fast mode), once that bar is complete
static void rp_broker_stops(RpSym &s, long i)
  {
   const MqlRates &b = s.bars[i];
   for(long k = (long)rp_pos.size() - 1; k >= 0; k--)
     {
      RpPos &p = rp_pos[k];
      if(p.symbol != s.name || p.sl == 0.0 || p.time > b.time + 59 || rp_sl_stuck.count(p.ticket)) continue;
      bool first = (p.time >= b.time);
      long magic = rp_stop_magic0 ? 0 : p.magic;
      if(p.type == 0 && b.low <= p.sl)
         rp_close_at(k, (first ? p.sl : std::min(p.sl, b.open)) * (1 - s.slip_stop), DEAL_REASON_SL, b.time + 59, magic);
      else if(p.type == 1 && rp_ask(s, b.high, b.spread) >= p.sl)
         rp_close_at(k, (first ? p.sl : std::max(p.sl, rp_ask(s, b.open, b.spread))) * (1 + s.slip_stop), DEAL_REASON_SL, b.time + 59, magic);
     }
  }
// the broker's stops on one tick (tick mode): fill at the tick price x stop slippage
static void rp_tick_stops(RpSym &s)
  {
   double bid = s.tick_bid, ask = rp_ask(s, s.tick_bid, s.bars[s.cur].spread);
   for(long k = (long)rp_pos.size() - 1; k >= 0; k--)
     {
      RpPos &p = rp_pos[k];
      if(p.symbol != s.name || p.sl == 0.0 || rp_sl_stuck.count(p.ticket)) continue;
      long magic = rp_stop_magic0 ? 0 : p.magic;
      if(p.type == 0 && bid <= p.sl) rp_close_at(k, bid * (1 - s.slip_stop), DEAL_REASON_SL, s.tick_time, magic);
      else if(p.type == 1 && ask >= p.sl) rp_close_at(k, ask * (1 + s.slip_stop), DEAL_REASON_SL, s.tick_time, magic);
     }
  }

// ------------------------------------------------------------------ payments and scripted deals
static void rp_book_payments(long T)
  {
   for(RpPay &p : rp_pays)
      if(!p.booked && p.t_deal <= T)
        {
         RpDeal d = {rp_next_deal++, 0, 0, p.t_deal, "", DEAL_TYPE_BALANCE, DEAL_ENTRY_IN, 0.0, 0.0, 0, 0, p.amount >= 0 ? "deposit" : "withdrawal",
                     0.0, 0.0, p.amount};
         rp_deals.push_back(d);
         rp_balance += p.amount;
         p.booked = true;
         MqlTradeRequest q = MqlTradeRequest();
         rp_queue_tx(TRADE_TRANSACTION_DEAL_ADD, d.deal, 0, "", 0, q);
         rp_logf("PAY t=%ld amount=%.2f", p.t_deal, p.amount);
        }
  }
static void rp_load_payments(const char *path)
  {
   FILE *f = fopen(path, "r");
   if(!f) return;
   char line[256];
   while(fgets(line, sizeof line, f))
     {
      long t = 0;
      double a = 0.0;
      if(sscanf(line, "%ld,%lf", &t, &a) == 2)
        {
         RpPay p = {t, t - rp_pay_skew, a, false};
         bool already = false;                         // booked by an earlier process (restart)
         for(const RpDeal &d : rp_deals)
            if(d.type == DEAL_TYPE_BALANCE && d.time == t && d.profit == a) already = true;
         p.booked = already;
         rp_pays.push_back(p);
        }
     }
   fclose(f);
  }
struct RpScripted { long t_in, t_out; string sym; int side; double vol, pin, pout; long magic; double profit, comm, swap; int reason; bool in_done, out_done; ulong ticket; };
static std::vector<RpScripted> rp_scripted;
static void rp_load_scripted(const char *path)
  {
   FILE *f = fopen(path, "r");
   if(!f) return;
   char line[512];
   while(fgets(line, sizeof line, f))
     {
      RpScripted x = {};
      char sym[64];
      if(sscanf(line, "%ld,%ld,%63[^,],%d,%lf,%lf,%lf,%ld,%lf,%lf,%lf,%d", &x.t_in, &x.t_out, sym, &x.side, &x.vol, &x.pin, &x.pout, &x.magic,
                &x.profit, &x.comm, &x.swap, &x.reason) == 12)
        {
         x.sym = sym;
         for(const RpDeal &d : rp_deals)                   // booked by an earlier process (restart)
            if(d.symbol == x.sym && d.magic == x.magic && d.type != DEAL_TYPE_BALANCE)
              {
               if(d.entry == DEAL_ENTRY_IN && d.time == x.t_in) { x.in_done = true; x.ticket = d.position; }
               if(d.entry == DEAL_ENTRY_OUT && d.time == x.t_out) x.out_done = true;
              }
         rp_scripted.push_back(x);
        }
     }
   fclose(f);
  }
static void rp_book_scripted(long T)
  {
   for(RpScripted &x : rp_scripted)
     {
      if(!x.in_done && x.t_in <= T)
        {
         x.ticket = rp_next_ticket++;
         RpPos p = {x.ticket, x.sym, x.side > 0 ? 0 : 1, x.vol, x.pin, 0.0, 0.0, x.magic, x.t_in, ""};
         rp_add_deal(p, p.type, DEAL_ENTRY_IN, x.vol, x.pin, DEAL_REASON_EXPERT, x.magic, x.t_in, 0.0, x.comm / 2, x.ticket, "");
         x.in_done = true;
        }
      if(x.in_done && !x.out_done && x.t_out <= T)
        {
         RpPos p = {x.ticket, x.sym, x.side > 0 ? 0 : 1, x.vol, x.pin, 0.0, 0.0, x.magic, x.t_in, ""};
         rp_add_deal(p, p.type == 0 ? 1 : 0, DEAL_ENTRY_OUT, x.vol, x.pout, x.reason, x.magic, x.t_out, x.profit, x.comm / 2, x.ticket, "");
         rp_deals.back().swap = x.swap;
         rp_balance += x.swap;
         x.out_done = true;
        }
     }
  }

// ------------------------------------------------------------------ state across restarts (a broker keeps it)
static void rp_save_state()
  {
   FILE *f = fopen(rp_path("_mock/state.txt").c_str(), "w");
   if(!f) return;
   fprintf(f, "next %lu %lu\n", rp_next_ticket, rp_next_deal);
   fprintf(f, "balance %.17g\n", rp_balance);
   for(const RpSym &s : rp_syms) fprintf(f, "sym %s %ld\n", s.name.c_str(), s.stop_done);
   for(const RpPos &p : rp_pos)
      fprintf(f, "pos %lu %s %d %.17g %.17g %.17g %.17g %ld %ld %s\n", p.ticket, p.symbol.c_str(), p.type, p.volume, p.price_open, p.sl, p.tp,
              p.magic, p.time, p.comment.empty() ? "-" : p.comment.c_str());
   for(const auto &kv : rp_gv)
      if(!rp_gv_temp.count(kv.first)) fprintf(f, "gv %s %.17g\n", kv.first.c_str(), kv.second);
   for(const RpDeal &d : rp_deals)
      fprintf(f, "deal %lu %lu %lu %ld %s %d %d %.17g %.17g %d %ld %.17g %.17g %.17g %s\n", d.deal, d.order, d.position, d.time,
              d.symbol.empty() ? "-" : d.symbol.c_str(), d.type, d.entry, d.volume, d.price, d.reason, d.magic, d.commission, d.swap, d.profit,
              d.comment.empty() ? "-" : d.comment.c_str());
   for(const RpOrder &o : rp_orders)
      fprintf(f, "order %lu %s %d %d %ld %ld %lu %ld %.17g %.17g %.17g %.17g %d %s\n", o.ticket, o.symbol.c_str(), o.type, o.state, o.setup,
              o.done, o.position, o.magic, o.volume, o.price, o.sl, o.tp, o.reason, o.comment.empty() ? "-" : o.comment.c_str());
   fclose(f);
   FILE *d = fopen(rp_path("_mock/deals.csv").c_str(), "w");
   if(!d) return;
   fprintf(d, "deal,order,position,time,symbol,type,entry,volume,price,reason,magic,commission,swap,profit,comment\n");
   for(const RpDeal &x : rp_deals)
      fprintf(d, "%lu,%lu,%lu,%ld,%s,%d,%d,%.4f,%.17g,%d,%ld,%.17g,%.17g,%.17g,%s\n", x.deal, x.order, x.position, x.time, x.symbol.c_str(),
              x.type, x.entry, x.volume, x.price, x.reason, x.magic, x.commission, x.swap, x.profit, x.comment.c_str());
   fclose(d);
  }
static void rp_load_state()
  {
   FILE *f = fopen(rp_path("_mock/state.txt").c_str(), "r");
   if(!f) return;
   char line[2048];
   while(fgets(line, sizeof line, f))
     {
      char a[256], b[256];
      if(strncmp(line, "next ", 5) == 0) sscanf(line + 5, "%lu %lu", &rp_next_ticket, &rp_next_deal);
      else if(strncmp(line, "balance ", 8) == 0) sscanf(line + 8, "%lf", &rp_balance);
      else if(strncmp(line, "sym ", 4) == 0)
        {
         long done = 0;
         if(sscanf(line + 4, "%255s %ld", a, &done) == 2)
            if(RpSym *s = rp_find(a)) s->stop_done = done;
        }
      else if(strncmp(line, "pos ", 4) == 0)
        {
         RpPos p;
         if(sscanf(line + 4, "%lu %255s %d %lf %lf %lf %lf %ld %ld %255s", &p.ticket, a, &p.type, &p.volume, &p.price_open, &p.sl, &p.tp,
                   &p.magic, &p.time, b) == 10)
           {
            p.symbol = a;
            p.comment = strcmp(b, "-") == 0 ? "" : b;
            rp_pos.push_back(p);
           }
        }
      else if(strncmp(line, "gv ", 3) == 0)
        {
         double v = 0;
         if(sscanf(line + 3, "%255s %lf", a, &v) == 2) rp_gv[a] = v;
        }
      else if(strncmp(line, "deal ", 5) == 0)
        {
         RpDeal d;
         if(sscanf(line + 5, "%lu %lu %lu %ld %255s %d %d %lf %lf %d %ld %lf %lf %lf %255s", &d.deal, &d.order, &d.position, &d.time, a,
                   &d.type, &d.entry, &d.volume, &d.price, &d.reason, &d.magic, &d.commission, &d.swap, &d.profit, b) == 15)
           {
            d.symbol = strcmp(a, "-") == 0 ? "" : a;
            d.comment = strcmp(b, "-") == 0 ? "" : b;
            rp_deals.push_back(d);
           }
        }
      else if(strncmp(line, "order ", 6) == 0)
        {
         RpOrder o;
         if(sscanf(line + 6, "%lu %255s %d %d %ld %ld %lu %ld %lf %lf %lf %lf %d %255s", &o.ticket, a, &o.type, &o.state, &o.setup, &o.done,
                   &o.position, &o.magic, &o.volume, &o.price, &o.sl, &o.tp, &o.reason, b) == 14)
           {
            o.symbol = a;
            o.comment = strcmp(b, "-") == 0 ? "" : b;
            rp_orders.push_back(o);
           }
        }
     }
   fclose(f);
  }

// ------------------------------------------------------------------ bars
static bool rp_load_bars(RpSym &s, const char *path)
  {
   FILE *f = fopen(path, "rb");
   if(!f) return false;
   char magic[4];
   if(fread(magic, 1, 4, f) == 4 && memcmp(magic, "CRB1", 4) == 0)
     {
      int32_t digits = 2;
      int64_t n = 0;
      if(fread(&digits, 4, 1, f) != 1 || fread(&n, 8, 1, f) != 1) { fclose(f); return false; }
      s.digits = digits;
      s.point = std::pow(10.0, -digits);
      double sc = std::pow(10.0, digits);
      s.bars.resize((size_t)n);
      unsigned char rec[28];
      for(int64_t i = 0; i < n; i++)
        {
         if(fread(rec, 1, 28, f) != 28) { fclose(f); return false; }
         int64_t t;
         int32_t v[5];
         memcpy(&t, rec, 8);
         memcpy(v, rec + 8, 20);
         MqlRates b = MqlRates();
         b.time = t;
         b.open = v[0] / sc; b.high = v[1] / sc; b.low = v[2] / sc; b.close = v[3] / sc;   // exact integer / 10^d: the nearest double
         b.spread = v[4];
         b.tick_volume = 1;
         s.bars[(size_t)i] = b;
        }
      fclose(f);
      return true;
     }
   fseek(f, 0, SEEK_SET);                                  // the spike's CSV layout
   char line[512];
   if(!fgets(line, sizeof line, f)) { fclose(f); return false; }
   while(fgets(line, sizeof line, f))
     {
      MqlRates b = MqlRates();
      char *p = line;
      b.time = strtol(p, &p, 10); p++;
      b.open = strtod(p, &p); p++;
      b.high = strtod(p, &p); p++;
      b.low = strtod(p, &p); p++;
      b.close = strtod(p, &p); p++;
      b.tick_volume = strtol(p, &p, 10); p++;
      b.spread = (int)strtol(p, &p, 10);
      s.bars.push_back(b);
     }
   fclose(f);
   return true;
  }

#include "mock_faults.h"

static double rp_envd(const string &k, double def) { const char *e = getenv(k.c_str()); return e ? atof(e) : def; }

#ifdef MOCK_REPLAY_NO_MAIN
// a module test with its own main(): the EA's handlers may be absent (weak definitions; the EA's, when present, win)
__attribute__((weak)) int OnInit() { return INIT_SUCCEEDED; }
__attribute__((weak)) void OnDeinit(const int) {}
__attribute__((weak)) void OnTimer() {}
__attribute__((weak)) void OnTick() {}
__attribute__((weak)) void OnTradeTransaction(const MqlTradeTransaction &, const MqlTradeRequest &, const MqlTradeResult &) {}
#else
int main()
  {
   const char *e = getenv("MOCK_FILES");
   rp_root = e ? e : ".";
   rp_mkdirs(rp_path("_mock"));
   rp_log = fopen(rp_path("_mock/log.txt").c_str(), "a");
   if((e = getenv("MOCK_COPY_FAIL"))) rp_copy_fail = atof(e);
   if((e = getenv("MOCK_SEED"))) rp_rng ^= strtoull(e, nullptr, 10) * 2654435761ULL;
   if((e = getenv("MOCK_USDEUR"))) rp_usdeur = atof(e);
   if((e = getenv("MOCK_ACCOUNT"))) rp_account_mode = strcmp(e, "real") == 0 ? ACCOUNT_TRADE_MODE_REAL : (strcmp(e, "contest") == 0 ? ACCOUNT_TRADE_MODE_CONTEST : ACCOUNT_TRADE_MODE_DEMO);
   rp_vps = getenv("MOCK_VPS") ? atoi(getenv("MOCK_VPS")) : 0;
   rp_tester = getenv("MOCK_TESTER") ? atoi(getenv("MOCK_TESTER")) : 0;
   rp_tick = getenv("MOCK_TICK") ? atoi(getenv("MOCK_TICK")) : 0;
   rp_quiet = getenv("MOCK_QUIET") ? atoi(getenv("MOCK_QUIET")) : 0;
   rp_stop_magic0 = getenv("MOCK_STOP_MAGIC0") ? atoi(getenv("MOCK_STOP_MAGIC0")) : 0;
   rp_gmt_shift = getenv("MOCK_GMT_SHIFT") ? atol(getenv("MOCK_GMT_SHIFT")) : 0;
   rp_pay_skew = getenv("MOCK_PAY_SKEW") ? atol(getenv("MOCK_PAY_SKEW")) : 0;
   int timer_calls = getenv("MOCK_TIMER_CALLS") ? std::max(1, atoi(getenv("MOCK_TIMER_CALLS"))) : 1;
   string syms = getenv("MOCK_SYMS") ? getenv("MOCK_SYMS") : "XAUUSD.r";
   std::stringstream ss(syms);
   string name;
   auto t_load = std::chrono::steady_clock::now();
   while(std::getline(ss, name, ','))
     {
      RpSym s;
      s.name = name;
      bool xau = name.rfind("XAU", 0) == 0, idx = name.rfind("US100", 0) == 0, btc = name.rfind("BTC", 0) == 0;
      // defaults: lab/r2/fp_costs.json (units per lot, minimum lot, step, leverage, slippage); gold commission 3 USD/side/lot
      s.units = rp_envd("MOCK_UNITS_" + name, xau ? 100.0 : 1.0);
      s.vmin = rp_envd("MOCK_VMIN_" + name, idx ? 0.1 : 0.01);
      s.vstep = rp_envd("MOCK_VSTEP_" + name, idx ? 0.1 : 0.01);
      s.vmax = rp_envd("MOCK_VMAX_" + name, 100.0);                    // SYMBOL_VOLUME_MAX (step K: T7b raises it)
      s.lev = rp_envd("MOCK_LEV_" + name, xau ? 500.0 : (idx ? 200.0 : 50.0));
      s.comm = rp_envd("MOCK_COMM_" + name, xau ? 3.0 * rp_usdeur : 0.0);
      s.stops_level = (long)rp_envd("MOCK_STOPS_" + name, 0);
      s.freeze_level = (long)rp_envd("MOCK_FREEZE_" + name, 0);
      s.slip_mkt = rp_envd("MOCK_SLIP_MKT_BPS_" + name, xau ? 0.3 : (idx ? 0.2 : (btc ? 0.5 : 0.7))) * 1e-4;
      s.slip_stop = rp_envd("MOCK_SLIP_STOP_BPS_" + name, xau ? 1.0 : (idx ? 0.5 : (btc ? 1.5 : 2.0))) * 1e-4;
      if(const char *h = getenv(("MOCK_HOLE_" + name).c_str()))          // "a-b@u,a-b@u" (server seconds; u 0 = stays)
        {
         std::stringstream hs(h);
         string it;
         while(std::getline(hs, it, ','))
           {
            long a = 0, b = 0, u = 0;
            if(sscanf(it.c_str(), "%ld-%ld@%ld", &a, &b, &u) == 3) s.holes.push_back({a, b, u});
           }
        }
      if(const char *h = getenv(("MOCK_UNSYNC_" + name).c_str()))        // "a-b,a-b"
        {
         std::stringstream hs(h);
         string it;
         while(std::getline(hs, it, ','))
           {
            long a = 0, b = 0;
            if(sscanf(it.c_str(), "%ld-%ld", &a, &b) == 2) s.unsync.push_back({a, b});
           }
        }
      if(const char *h = getenv(("MOCK_REVISE_" + name).c_str()))        // "t@u:d,t@u:d" (close += d from u on)
        {
         std::stringstream hs(h);
         string it;
         while(std::getline(hs, it, ','))
           {
            long t = 0, u = 0;
            double d = 0;
            if(sscanf(it.c_str(), "%ld@%ld:%lf", &t, &u, &d) == 3) s.revise.push_back({(double)t, (double)u, d});
           }
        }
      const char *path = getenv(("MOCK_BARS_" + name).c_str());
      if(!path || !rp_load_bars(s, path)) { fprintf(stderr, "no bars for %s\n", name.c_str()); return 2; }
      if(const char *dg = getenv(("MOCK_DIGITS_" + name).c_str())) { s.digits = atoi(dg); s.point = std::pow(10.0, -s.digits); }
      rp_syms.push_back(s);
     }
   long from = getenv("MOCK_FROM") ? atol(getenv("MOCK_FROM")) : LONG_MIN, to = getenv("MOCK_TO") ? atol(getenv("MOCK_TO")) : LONG_MAX;
   std::vector<long> ev;
   for(const RpSym &s : rp_syms)
      for(const MqlRates &b : s.bars)
         if(b.time >= from && b.time < to) ev.push_back(b.time);
   std::sort(ev.begin(), ev.end());
   ev.erase(std::unique(ev.begin(), ev.end()), ev.end());
   if(ev.empty()) { fprintf(stderr, "no event\n"); return 2; }
   bool fresh = !FileIsExist("_mock/state.txt", 0);
   if(fresh && getenv("MOCK_BALANCE")) rp_balance = atof(getenv("MOCK_BALANCE"));
   rp_load_state();
   if((e = getenv("MOCK_PAYMENTS"))) rp_load_payments(e);
   if((e = getenv("MOCK_DEALS"))) rp_load_scripted(e);
   mf_init();
   // forming bar of every symbol at T; broker stops on the bars that closed (fast mode)
   auto advance = [](long T) {
      for(RpSym &s : rp_syms)
        {
         long c = s.cur;
         while(c + 1 < (long)s.bars.size() && s.bars[c + 1].time <= T) c++;
         long complete = (c >= 0 && s.bars[c].time + 60 <= T) ? c + 1 : c;   // bars whose minute is over at T
         if(!rp_tick)
            for(long i = std::max(s.stop_done, 0L); i < complete; i++) rp_broker_stops(s, i);
         if(complete > s.stop_done) s.stop_done = complete;
         if(c != s.cur && c >= 0)
           {
            s.cur = c;
            s.stage = 1;
            s.tick_bid = s.bars[c].open;
            s.vis_h = s.vis_l = s.tick_bid;
            s.tick_time = s.bars[c].time;
           }
         if(c >= 0 && s.bars[c].time + 60 <= T)                // no bar at T: its last bar is complete, its last tick at :59
           {
            s.stage = 4;
            s.tick_bid = s.bars[c].close;
            s.vis_h = s.bars[c].high;
            s.vis_l = s.bars[c].low;
            s.tick_time = s.bars[c].time + 59;
           }
        }
      rp_book_payments(T);
      rp_book_scripted(T);
   };
   double load_s = std::chrono::duration<double>(std::chrono::steady_clock::now() - t_load).count();
   auto t0 = std::chrono::steady_clock::now();
   rp_now = ev[0];
   advance(rp_now);
   rp_now = ev[0] + 2;
   rp_ms = 500;
   int rc = OnInit();
   if(rc != INIT_SUCCEEDED) { fprintf(stderr, "OnInit failed (%d)\n", rc); if(rp_log) fclose(rp_log); return 3; }
   rp_deliver_tx();
   for(long T : ev)
     {
      rp_now = T;
      rp_ms = 0;
      advance(T);
      mf_event(T);
      if(!rp_syms.empty() && rp_syms[0].cur >= 0 && rp_syms[0].bars[rp_syms[0].cur].time == T) { OnTick(); rp_deliver_tx(); }
      if(rp_tick)
        {
         for(int k = 1; k <= 4; k++)
           {
            if(k > 1)
               for(RpSym &s : rp_syms)
                 {
                  if(s.cur < 0 || s.bars[s.cur].time != T) continue;
                  const MqlRates &b = s.bars[s.cur];
                  bool up = b.close >= b.open;
                  double px = k == 2 ? (up ? b.low : b.high) : (k == 3 ? (up ? b.high : b.low) : b.close);
                  s.tick_bid = px;
                  s.vis_h = std::max(s.vis_h, px);
                  s.vis_l = std::min(s.vis_l, px);
                  s.stage = k;
                  s.tick_time = T + 15 * (k - 1);
                 }
            for(RpSym &s : rp_syms)
               if(s.cur >= 0 && s.bars[s.cur].time == T) rp_tick_stops(s);
            rp_now = T + 15 * (k - 1) + 2;
            rp_ms = 500;
            OnTimer();
            rp_timer_calls++;
            rp_deliver_tx();
           }
         continue;
        }
      for(int c = 0; c < timer_calls; c++)
        {
         rp_now = T + 2 + c;
         rp_ms = 500;
         OnTimer();
         rp_timer_calls++;
         rp_deliver_tx();
        }
     }
   OnDeinit(REASON_CLOSE);
   double run_s = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
   rp_save_state();
   printf("events %zu from %ld to %ld  load %.3f s  replay %.3f s  timer calls %ld  copyrates %ld (failed %ld)  open positions %zu  deals %zu  pushes %ld  flushes %ld\n",
          ev.size(), ev.front(), ev.back(), load_s, run_s, rp_timer_calls, rp_copy_calls, rp_copy_failed, rp_pos.size(), rp_deals.size(), rp_pushes,
          rp_flushes);
   if(rp_log) fclose(rp_log);
   return 0;
  }
#endif
