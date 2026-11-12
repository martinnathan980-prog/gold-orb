// mock_replay.h - a MetaTrader 5 terminal + broker imitation that REPLAYS recorded M1 bars minute by minute, so that the
// real MQL5 code of a rule (translated by to_cpp_spike.py, compiled with g++) can be run offline and its decisions and
// trades compared with the lab's simulator (lab/goldlab/sim.py). It is NOT MetaTrader: it imitates the documented
// behaviour of the functions the spike uses, and the lab's fill conventions.
//
// Clock: one event per distinct M1 bar start of any symbol (server time). At an event T the bar starting at T is the
//   FORMING bar (only its first tick is visible: open = high = low = close = open, its spread); every earlier bar is
//   closed and visible in full. A symbol without a bar at T keeps its older forming bar (as MT5: a bar is known to be
//   finished only when a later bar starts). OnTimer() is called once per event (the real timer fires once a second:
//   the extra calls inside a minute see nothing new).
// Bars: CSV files "time,open,high,low,close,tick_volume,spread" (time = bar open, server seconds; prices = BID; spread
//   = integer points), the layout the hands export (ClaudeMains.mq5 ExportBars). Only PERIOD_M1 is served.
// Broker (hedging account, lab fill model, lab/goldlab/sim.py):
//   market buy fills at ask x (1 + slip_mkt), sell at bid x (1 - slip_mkt), at the forming bar's open quote;
//   a long's stop is hit when a bar's BID low <= sl, a short's when its ASK high >= sl (ask = bid + spread, on the grid);
//   the stop fills at sl on the position's first bar, else at the worse of sl and the bar's open, x (1 -/+ slip_stop);
//   the stop is checked when the bar is complete (before the EA sees the next bar); a stop that is not on the tick grid
//   or on the wrong side of the price is refused (10016).
// Env:
//   MOCK_FILES=dir            MQL5\Files of the fake terminal (journal), and dir/_mock (state, deals, log)
//   MOCK_SYMS=A,B             symbols; MOCK_BARS_<A>=path, MOCK_DIGITS_<A>=2 (point = tick size = 10^-digits)
//   MOCK_FROM / MOCK_TO       replay only events with FROM <= T < TO (server seconds); the broker state, the deals and
//                             the global variables are saved at the end and reloaded at the next start (a terminal
//                             restart: OnDeinit, then a new process, OnInit at FROM)
//   MOCK_SLIP_MKT_BPS / MOCK_SLIP_STOP_BPS   broker slippage (default 0.5 / 1.5: btcusd in lab/r2/fp_costs.json);
//                             MOCK_SLIP_MKT_BPS_<A> / MOCK_SLIP_STOP_BPS_<A> for one symbol
//   MOCK_INPUT_<InpName>=v    another value for an input of the EA
//   MOCK_TIMER_CALLS=n        OnTimer() n times per event, at T, T+1 s, ... (the real timer fires every second; default 1)
//   MOCK_COPY_FAIL=p          every CopyRates call fails (-1, error 4066 "history in update state") with probability p
//                             (deterministic pseudo-random sequence, MOCK_SEED)
#pragma once
#include "mql5_shim.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <map>
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
   int    digits;
   double point;
   double slip_mkt = 0.5 * 1e-4, slip_stop = 1.5 * 1e-4;   // lab fill model, per symbol
   std::vector<MqlRates> bars;
   long   cur = -1;          // index of the forming bar
   long   stop_done = 0;     // bars [0, stop_done) were checked for broker stops
  };
struct RpPos  { ulong ticket; string symbol; int type; double volume, price_open, sl, tp; long magic, time; string comment; };
struct RpDeal { ulong deal, position; long time; string symbol; int type, entry; double volume, price; int reason; long magic; string comment; };

static std::vector<RpSym> rp_syms;
static std::vector<RpPos> rp_pos;
static std::vector<RpDeal> rp_deals;
static std::map<string, double> rp_gv;
static long   rp_now = 0;
static string rp_root = ".";
static double rp_slip_mkt = 0.5 * 1e-4, rp_slip_stop = 1.5 * 1e-4;
static ulong  rp_next_ticket = 70000001, rp_next_deal = 80000001;
static ulong  rp_magic = 0;
static long   rp_selected = -1;              // index in rp_pos of the selected position
static int    rp_last_error = 0;
static FILE  *rp_log = nullptr;
static long   rp_copy_calls = 0, rp_timer_calls = 0;
static MqlTradeResult rp_res = MqlTradeResult();
static double rp_copy_fail = 0.0;
static unsigned long long rp_rng = 88172645463325252ULL;
static long rp_copy_failed = 0;
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
   if(reserve > 0 && (size_t)(n + reserve) > a.v.capacity()) a.v.reserve(n + reserve);
   a.v.resize(n);
   return n;
  }
template <typename T> void ArrayFree(MqlArray<T> &a) { a.v.clear(); }
template <typename T> bool ArraySetAsSeries(const MqlArray<T> &, bool flag) { return !flag; }
template <typename T> void ZeroMemory(T &v) { v = T(); }
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
double MathAbs(double v) { return std::fabs(v); }
double MathFloor(double v) { return std::floor(v); }
double MathCeil(double v) { return std::ceil(v); }
double MathRound(double v) { return std::round(v); }
double MathLog10(double v) { return std::log10(v); }
bool   MathIsValidNumber(double v) { return std::isfinite(v); }
double NormalizeDouble(double value, int digits) { return rp_norm(value, digits); }   // ASSUMPTION: as MT5 (nearest grid value)
int    GetLastError() { return rp_last_error; }
void   ResetLastError() { rp_last_error = 0; }
bool   IsStopped() { return false; }

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
datetime TimeGMT() { long u = rp_now - 2 * 3600; return rp_now - (rp_us_dst(u) ? 3 : 2) * 3600; }
datetime TimeLocal() { return TimeGMT(); }
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
void EventKillTimer() {}

// ------------------------------------------------------------------ symbols and bars
bool SymbolSelect(const string name, bool) { return rp_find(name) != nullptr; }
long SymbolInfoInteger(const string name, ENUM_SYMBOL_INFO_INTEGER p)
  {
   RpSym *s = rp_find(name);
   if(!s) return 0;
   if(p == SYMBOL_DIGITS) return s->digits;
   if(p == SYMBOL_SPREAD) return s->cur >= 0 ? s->bars[s->cur].spread : 0;
   if(p == SYMBOL_TRADE_MODE) return SYMBOL_TRADE_MODE_FULL;
   return 0;                                                  // stops level, freeze level: 0
  }
double SymbolInfoDouble(const string name, ENUM_SYMBOL_INFO_DOUBLE p)
  {
   RpSym *s = rp_find(name);
   if(!s) return 0.0;
   if(p == SYMBOL_POINT || p == SYMBOL_TRADE_TICK_SIZE) return s->point;
   if(p == SYMBOL_VOLUME_MIN || p == SYMBOL_VOLUME_STEP) return 0.01;
   if(p == SYMBOL_VOLUME_MAX) return 100.0;
   if(s->cur < 0) return 0.0;
   const MqlRates &b = s->bars[s->cur];
   if(p == SYMBOL_BID) return b.open;
   if(p == SYMBOL_ASK) return rp_ask(*s, b.open, b.spread);
   return 0.0;
  }
bool SymbolInfoTick(const string name, MqlTick &k)
  {
   RpSym *s = rp_find(name);
   if(!s || s->cur < 0) return false;
   k = MqlTick();
   const MqlRates &b = s->bars[s->cur];
   k.bid = b.open; k.ask = rp_ask(*s, b.open, b.spread); k.time = rp_now; k.time_msc = rp_now * 1000;
   return true;
  }
static MqlRates rp_visible(const RpSym &s, long i)
  {
   MqlRates b = s.bars[i];
   if(i == s.cur) { b.high = b.low = b.close = b.open; b.tick_volume = 1; }   // the forming bar at its first tick
   return b;
  }
static void rp_fill(const RpSym &s, long a, long b, MqlArray<MqlRates> &r)
  {
   r.v.clear();
   for(long i = std::max(a, 0L); i <= b; i++) r.v.push_back(rp_visible(s, i));
  }
int CopyRates(const string name, ENUM_TIMEFRAMES tf, int start_pos, int count, MqlArray<MqlRates> &r)
  {
   rp_copy_calls++;
   RpSym *s = rp_find(name);
   r.v.clear();
   if(rp_fail_now()) return -1;
   if(!s || tf != PERIOD_M1 || s->cur < 0 || count <= 0 || start_pos < 0) { rp_last_error = 4401; return -1; }
   long hi = s->cur - start_pos;
   if(hi < 0) { rp_last_error = 4401; return -1; }
   rp_fill(*s, hi - count + 1, hi, r);
   return (int)r.v.size();
  }
static long rp_lower(const RpSym &s, long t)           // first bar with time >= t
  {
   auto it = std::lower_bound(s.bars.begin(), s.bars.end(), t, [](const MqlRates &b, long v) { return b.time < v; });
   return (long)(it - s.bars.begin());
  }
int CopyRates(const string name, ENUM_TIMEFRAMES tf, datetime start_time, datetime stop_time, MqlArray<MqlRates> &r)
  {
   rp_copy_calls++;
   RpSym *s = rp_find(name);
   r.v.clear();
   if(rp_fail_now()) return -1;
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
   if(rp_fail_now()) return -1;
   if(!s || tf != PERIOD_M1 || s->cur < 0 || count <= 0) { rp_last_error = 4401; return -1; }
   long b = std::min(rp_lower(*s, start_time + 1) - 1, s->cur);
   rp_fill(*s, b - count + 1, b, r);
   return (int)r.v.size();
  }

// ------------------------------------------------------------------ files (journal) and global variables
static std::map<int, FILE *> rp_files;
static int rp_next_handle = 1;
bool FolderCreate(const string name, int) { mkdir(rp_path(name).c_str(), 0755); return true; }
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
void FileFlush(int h) { if(rp_files.count(h)) fflush(rp_files[h]); }
void FileClose(int h) { if(rp_files.count(h)) { fclose(rp_files[h]); rp_files.erase(h); } }
bool GlobalVariableCheck(const string name) { return rp_gv.count(name) > 0; }
double GlobalVariableGet(const string name) { auto it = rp_gv.find(name); return it == rp_gv.end() ? 0.0 : it->second; }
datetime GlobalVariableSet(const string name, double value) { rp_gv[name] = value; return rp_now; }
bool GlobalVariableDel(const string name) { return rp_gv.erase(name) > 0; }
void GlobalVariablesFlush() {}                                // saved at the end of the process (a clean terminal stop)

// ------------------------------------------------------------------ broker: positions, deals, CTrade
static void rp_deal(const RpPos &p, int type, int entry, double price, int reason, long when)
  {
   rp_deals.push_back({rp_next_deal++, p.ticket, when, p.symbol, type, entry, p.volume, price, reason, p.magic, p.comment});
  }
static bool rp_on_grid(const RpSym &s, double v) { return std::fabs(v - rp_norm(v, s.digits)) < 1e-9 * std::max(1.0, std::fabs(v)); }
static bool rp_open(const string symbol, int type, double volume, double sl, double tp, const string comment)
  {
   rp_res = MqlTradeResult();
   RpSym *s = rp_find(symbol);
   if(!s || s->cur < 0 || volume <= 0) { rp_res.retcode = 10013; return false; }
   const MqlRates &b = s->bars[s->cur];
   double bid = b.open, ask = rp_ask(*s, b.open, b.spread);
   if(sl != 0.0 && (!rp_on_grid(*s, sl) || (type == 0 ? sl >= bid : sl <= ask))) { rp_res.retcode = 10016; return false; }
   double px = (type == 0) ? ask * (1 + s->slip_mkt) : bid * (1 - s->slip_mkt);
   RpPos p = {rp_next_ticket++, symbol, type, volume, px, sl, tp, (long)rp_magic, rp_now, comment};
   rp_pos.push_back(p);
   rp_deal(p, type, 0, px, 3, rp_now);
   rp_res.retcode = TRADE_RETCODE_DONE; rp_res.order = p.ticket; rp_res.deal = rp_next_deal - 1; rp_res.price = px; rp_res.volume = volume;
   rp_res.bid = bid; rp_res.ask = ask;
   rp_logf("OPEN %s %s %.2f px=%.10g sl=%.10g t=%ld ticket=%lu", symbol.c_str(), type == 0 ? "buy" : "sell", volume, px, sl, rp_now, p.ticket);
   return true;
  }
static long rp_pos_index(ulong ticket)
  {
   for(size_t i = 0; i < rp_pos.size(); i++)
      if(rp_pos[i].ticket == ticket) return (long)i;
   return -1;
  }
// `when`: the deal's time. A stop fills DURING its bar: stamped at the last second of that bar (the mock does not know
// the tick); a close asked by the EA is stamped at the current time (the forming bar's first tick)
static void rp_close_at(long i, double px, int reason, long when)
  {
   RpPos p = rp_pos[i];
   rp_deal(p, p.type == 0 ? 1 : 0, 1, px, reason, when);
   rp_logf("CLOSE %s ticket=%lu px=%.10g reason=%d t=%ld", p.symbol.c_str(), p.ticket, px, reason, when);
   rp_pos.erase(rp_pos.begin() + i);
   rp_selected = -1;
  }
uint   CTrade::ResultRetcode(void) const { return rp_res.retcode; }
double CTrade::ResultPrice(void) const { return rp_res.price; }
ulong  CTrade::ResultDeal(void) const { return rp_res.deal; }
ulong  CTrade::ResultOrder(void) const { return rp_res.order; }
double CTrade::ResultVolume(void) const { return rp_res.volume; }
string CTrade::ResultRetcodeDescription(void) const { return "retcode " + std::to_string(rp_res.retcode); }
void   CTrade::SetDeviationInPoints(const ulong) {}
bool   CTrade::SetTypeFillingBySymbol(const string) { return true; }
void   CTrade::SetExpertMagicNumber(const ulong magic) { rp_magic = magic; }
bool CTrade::Buy(const double volume, const string symbol, double, const double sl, const double tp, const string comment)
  { return rp_open(symbol, 0, volume, sl, tp, comment); }
bool CTrade::Sell(const double volume, const string symbol, double, const double sl, const double tp, const string comment)
  { return rp_open(symbol, 1, volume, sl, tp, comment); }
bool CTrade::PositionModify(const ulong ticket, const double sl, const double tp)
  {
   rp_res = MqlTradeResult();
   long i = rp_pos_index(ticket);
   if(i < 0) { rp_res.retcode = 10036; return false; }
   RpPos &p = rp_pos[i];
   RpSym *s = rp_find(p.symbol);
   const MqlRates &b = s->bars[s->cur];
   double bid = b.open, ask = rp_ask(*s, b.open, b.spread);
   if(sl != 0.0 && (!rp_on_grid(*s, sl) || (p.type == 0 ? sl >= bid : sl <= ask))) { rp_res.retcode = 10016; return false; }
   p.sl = sl; p.tp = tp;
   rp_res.retcode = TRADE_RETCODE_DONE;
   return true;
  }
bool CTrade::PositionClose(const ulong ticket, const ulong)
  {
   rp_res = MqlTradeResult();
   long i = rp_pos_index(ticket);
   if(i < 0) { rp_res.retcode = 10036; return false; }
   RpSym *s = rp_find(rp_pos[i].symbol);
   const MqlRates &b = s->bars[s->cur];
   double px = (rp_pos[i].type == 0) ? b.open * (1 - s->slip_mkt) : rp_ask(*s, b.open, b.spread) * (1 + s->slip_mkt);
   rp_res.retcode = TRADE_RETCODE_DONE; rp_res.price = px; rp_res.order = ticket;
   rp_close_at(i, px, 3, rp_now);
   return true;
  }
int PositionsTotal() { return (int)rp_pos.size(); }
ulong PositionGetTicket(int index) { if(index < 0 || index >= (int)rp_pos.size()) return 0; rp_selected = index; return rp_pos[index].ticket; }
bool PositionSelectByTicket(ulong ticket) { rp_selected = rp_pos_index(ticket); return rp_selected >= 0; }
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
   return 0.0;
  }
string PositionGetString(ENUM_POSITION_PROPERTY_STRING p)
  {
   if(rp_selected < 0) return "";
   return p == POSITION_SYMBOL ? rp_pos[rp_selected].symbol : rp_pos[rp_selected].comment;
  }

// the broker's stops on bar i of symbol s, once that bar is complete
static void rp_broker_stops(RpSym &s, long i)
  {
   const MqlRates &b = s.bars[i];
   for(long k = (long)rp_pos.size() - 1; k >= 0; k--)
     {
      RpPos &p = rp_pos[k];
      if(p.symbol != s.name || p.sl == 0.0 || p.time > b.time) continue;
      bool first = (p.time == b.time);
      if(p.type == 0 && b.low <= p.sl)
         rp_close_at(k, (first ? p.sl : std::min(p.sl, b.open)) * (1 - s.slip_stop), 4, b.time + 59);
      else if(p.type == 1 && rp_ask(s, b.high, b.spread) >= p.sl)
         rp_close_at(k, (first ? p.sl : std::max(p.sl, rp_ask(s, b.open, b.spread))) * (1 + s.slip_stop), 4, b.time + 59);
     }
  }

// ------------------------------------------------------------------ state across restarts (a broker keeps it)
static void rp_save_state()
  {
   FILE *f = fopen(rp_path("_mock/state.txt").c_str(), "w");
   if(!f) return;
   fprintf(f, "next %lu %lu\n", rp_next_ticket, rp_next_deal);
   for(const RpSym &s : rp_syms) fprintf(f, "sym %s %ld\n", s.name.c_str(), s.stop_done);
   for(const RpPos &p : rp_pos)
      fprintf(f, "pos %lu %s %d %.17g %.17g %.17g %.17g %ld %ld %s\n", p.ticket, p.symbol.c_str(), p.type, p.volume, p.price_open, p.sl, p.tp,
              p.magic, p.time, p.comment.empty() ? "-" : p.comment.c_str());
   for(const auto &kv : rp_gv) fprintf(f, "gv %s %.17g\n", kv.first.c_str(), kv.second);
   fclose(f);
   FILE *d = fopen(rp_path("_mock/deals.csv").c_str(), "a");
   if(!d) return;
   static size_t written = 0;
   for(size_t i = written; i < rp_deals.size(); i++)
     {
      const RpDeal &x = rp_deals[i];
      fprintf(d, "%lu,%lu,%ld,%s,%d,%d,%.4f,%.17g,%d,%ld,%s\n", x.deal, x.position, x.time, x.symbol.c_str(), x.type, x.entry, x.volume,
              x.price, x.reason, x.magic, x.comment.c_str());
     }
   written = rp_deals.size();
   fclose(d);
  }
static void rp_load_state()
  {
   FILE *f = fopen(rp_path("_mock/state.txt").c_str(), "r");
   if(!f) return;
   char line[1024];
   while(fgets(line, sizeof line, f))
     {
      char a[256], b[256];
      if(strncmp(line, "next ", 5) == 0) sscanf(line + 5, "%lu %lu", &rp_next_ticket, &rp_next_deal);
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
     }
   fclose(f);
  }

// ------------------------------------------------------------------ bars
static bool rp_load_bars(RpSym &s, const char *path)
  {
   FILE *f = fopen(path, "r");
   if(!f) return false;
   char line[512];
   if(!fgets(line, sizeof line, f)) { fclose(f); return false; }        // header
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

#ifndef MOCK_REPLAY_NO_MAIN
int main()
  {
   const char *e = getenv("MOCK_FILES");
   rp_root = e ? e : ".";
   mkdir(rp_path("_mock").c_str(), 0755);
   rp_log = fopen(rp_path("_mock/log.txt").c_str(), "a");
   if((e = getenv("MOCK_SLIP_MKT_BPS"))) rp_slip_mkt = atof(e) * 1e-4;
   if((e = getenv("MOCK_SLIP_STOP_BPS"))) rp_slip_stop = atof(e) * 1e-4;
   if((e = getenv("MOCK_COPY_FAIL"))) rp_copy_fail = atof(e);
   if((e = getenv("MOCK_SEED"))) rp_rng ^= strtoull(e, nullptr, 10) * 2654435761ULL;
   int timer_calls = getenv("MOCK_TIMER_CALLS") ? std::max(1, atoi(getenv("MOCK_TIMER_CALLS"))) : 1;
   string syms = getenv("MOCK_SYMS") ? getenv("MOCK_SYMS") : "BTCUSD";
   std::stringstream ss(syms);
   string name;
   auto t_load = std::chrono::steady_clock::now();
   while(std::getline(ss, name, ','))
     {
      RpSym s;
      s.name = name;
      const char *dg = getenv(("MOCK_DIGITS_" + name).c_str());
      s.digits = dg ? atoi(dg) : 2;
      s.point = std::pow(10.0, -s.digits);
      s.slip_mkt = rp_slip_mkt;
      s.slip_stop = rp_slip_stop;
      if(const char *v = getenv(("MOCK_SLIP_MKT_BPS_" + name).c_str())) s.slip_mkt = atof(v) * 1e-4;
      if(const char *v = getenv(("MOCK_SLIP_STOP_BPS_" + name).c_str())) s.slip_stop = atof(v) * 1e-4;
      const char *path = getenv(("MOCK_BARS_" + name).c_str());
      if(!path || !rp_load_bars(s, path)) { fprintf(stderr, "no bars for %s\n", name.c_str()); return 2; }
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
   rp_load_state();
   auto advance = [](long T) {                                  // forming bar of every symbol at T; broker stops on closed bars
      for(RpSym &s : rp_syms)
        {
         long c = s.cur;
         while(c + 1 < (long)s.bars.size() && s.bars[c + 1].time <= T) c++;
         s.cur = c;
         for(long i = std::max(s.stop_done, 0L); i < c; i++) rp_broker_stops(s, i);
         if(c > s.stop_done) s.stop_done = c;
        }
   };
   double load_s = std::chrono::duration<double>(std::chrono::steady_clock::now() - t_load).count();
   auto t0 = std::chrono::steady_clock::now();
   rp_now = ev[0];
   advance(rp_now);
   int rc = OnInit();
   if(rc != INIT_SUCCEEDED) { fprintf(stderr, "OnInit failed\n"); return 3; }
   for(long T : ev)
     {
      rp_now = T;
      advance(T);
      for(int c = 0; c < timer_calls; c++)
        {
         rp_now = T + c;
         OnTimer();
         rp_timer_calls++;
        }
     }
   OnDeinit(REASON_CLOSE);
   double run_s = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
   rp_save_state();
   printf("events %zu from %ld to %ld  load %.3f s  replay %.3f s  timer calls %ld  copyrates %ld (failed %ld)  open positions %zu\n",
          ev.size(), ev.front(), ev.back(), load_s, run_s, rp_timer_calls, rp_copy_calls, rp_copy_failed, rp_pos.size());
   if(rp_log) fclose(rp_log);
   return 0;
  }
#endif
