// A small working imitation of the MetaTrader 5 functions ReleveFP.mq5 uses, so that the translated script can be RUN
// here (g++) by the demo tools' self-test (lab/robot/demo/test_demo_tools.py, review3 R2, R3, R4, R5, R7, R14).
// It starts from lab/live_ai/check/mock_mt5.h (the same symbols, ticks and files, not changed there) and adds the
// terminal's M1 bars: CopyRates, Bars, SeriesInfoInteger and TerminalInfoInteger(TERMINAL_MAXBARS), with scenarios read
// from the environment. It is not MetaTrader: it only proves the script's own logic.
//   MOCK_FILES          the MQL5/Files folder
//   MOCK_NOW            the server time of the run (default 1794479400, a Thursday 10:30)
//   MOCK_R1_LOAD_MS     the M1 series of each symbol is still loading until the script has slept that long since its first
//                       request of that symbol: Bars 0, CopyRates 0, not synchronized (MQL5: a script gets what is ready at
//                       its timeout while the download goes on)
//   MOCK_R1_AFTER_LAST  1: a day after the series' last bar answers -1 (error 4401), as CopyRates does for an interval out of
//                       the available data
//   MOCK_R1_PARTIAL     1: each day's first CopyRates gives only the first half of the day and every later call fails (-1)
//   MOCK_MAXBARS        TERMINAL_MAXBARS (default 500000)
//   MOCK_OPEN_LOG       a file where every FileOpen name is appended, one per line (the order the files are written)
#pragma once
#include "mql5_shim.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <sys/stat.h>

static long mock_env(const char *k, long dflt)
  {
   const char *v = getenv(k);
   return (v && *v) ? atol(v) : dflt;
  }
static const long MOCK_NOW = mock_env("MOCK_NOW", 1794479400);
static const long MOCK_HISTORY_START = MOCK_NOW - 10 * 86400;      // ticks (the m1 files)
static const long MOCK_R1_START = (MOCK_NOW - 40 * 86400) - (MOCK_NOW - 40 * 86400) % 86400;   // bars (the r1 files)
static const char *MOCK_SYMBOLS[] = {"EURUSD.r", "XAUUSD.r", "USDJPY.r", "BTCUSD", "ETHUSD", "NAS100", "JPN225", "US500", "DE40",
                                     "AAPL.US"};
static std::map<int, FILE *> g_files;
static int g_next_handle = 1, g_last_error = 0, g_copy_calls = 0;
static long g_slept_ms = 0;
static std::map<string, long> g_first_ask;                          // per symbol: g_slept_ms at its first bar request

static bool mock_known(const string &s)
  {
   for(const char *k : MOCK_SYMBOLS)
      if(s == k) return true;
   return false;
  }
static string mock_path(string name)
  {
   for(char &c : name)
      if(c == '\\') c = '/';
   const char *root = getenv("MOCK_FILES");
   return string(root ? root : ".") + "/" + name;
  }

// ---- templates declared in the shim
template <typename... A> void Print(A... a) {}
template <typename... A> void Alert(A... a) {}
template <typename... A> void Comment(A... a) {}
template <typename T> int ArraySize(const MqlArray<T> &a) { return (int)a.v.size(); }
template <typename T> int ArrayResize(MqlArray<T> &a, int n, int) { a.v.resize(n); return n; }
template <typename T> void ArrayFree(MqlArray<T> &a) { a.v.clear(); }
template <typename T> void ZeroMemory(T &v) { v = T(); }

// ---- strings
string IntegerToString(long number, int, ushort) { return std::to_string(number); }
string DoubleToString(double value, int digits)
  {
   char b[64];
   snprintf(b, sizeof b, "%.*f", digits, value);
   return b;
  }
string TimeToString(datetime value, int) { return std::to_string(value); }
int StringFind(const string s, const string m, int start) { size_t p = s.find(m, start); return p == string::npos ? -1 : (int)p; }
int StringReplace(string &s, const string f, const string r)
  {
   int n = 0;
   for(size_t p = s.find(f); p != string::npos; p = s.find(f, p + r.size())) { s.replace(p, f.size(), r); n++; }
   return n;
  }
int StringTrimLeft(string &s) { size_t p = s.find_first_not_of(" \t\r\n"); s.erase(0, p == string::npos ? s.size() : p); return 0; }
int StringTrimRight(string &s) { size_t p = s.find_last_not_of(" \t\r\n"); s.erase(p == string::npos ? 0 : p + 1); return 0; }
int StringSplit(const string s, const ushort sep, MqlArray<string> &out)
  {
   out.v.clear();
   size_t a = 0;
   while(true)
     {
      size_t b = s.find((char)sep, a);
      out.v.push_back(s.substr(a, b == string::npos ? string::npos : b - a));
      if(b == string::npos) break;
      a = b + 1;
     }
   return (int)out.v.size();
  }
long StringToInteger(const string value) { return atol(value.c_str()); }

// ---- terminal, account, symbols
int GetLastError() { return g_last_error; }
void ResetLastError() { g_last_error = 0; }
datetime TimeTradeServer() { return MOCK_NOW; }
datetime TimeGMT() { return MOCK_NOW - 7200; }
void Sleep(int ms) { g_slept_ms += ms; }                           // no real wait: the mock's own clock
bool IsStopped() { return false; }
uint GetTickCount() { return (uint)g_slept_ms; }
int TerminalInfoInteger(ENUM_TERMINAL_INFO_INTEGER p) { return p == TERMINAL_MAXBARS ? (int)mock_env("MOCK_MAXBARS", 500000) : 1; }
string AccountInfoString(ENUM_ACCOUNT_INFO_STRING) { return "MOCK"; }
long AccountInfoInteger(ENUM_ACCOUNT_INFO_INTEGER p) { return p == ACCOUNT_LEVERAGE ? 500 : (long)ACCOUNT_TRADE_MODE_DEMO; }
bool SymbolSelect(const string name, bool) { return mock_known(name); }
int SymbolsTotal(bool) { return (int)(sizeof MOCK_SYMBOLS / sizeof *MOCK_SYMBOLS); }
string SymbolName(int pos, bool) { return MOCK_SYMBOLS[pos]; }
long SymbolInfoInteger(const string name, ENUM_SYMBOL_INFO_INTEGER p)
  {
   if(!mock_known(name)) return 0;
   if(p == SYMBOL_TRADE_MODE) return SYMBOL_TRADE_MODE_FULL;
   if(p == SYMBOL_DIGITS) return 2;
   return 7;
  }
double SymbolInfoDouble(const string, ENUM_SYMBOL_INFO_DOUBLE p) { return p == SYMBOL_POINT ? 0.01 : 1.0; }
string SymbolInfoString(const string name, ENUM_SYMBOL_INFO_STRING p)
  {
   if(p == SYMBOL_PATH) return "CFD\\Group, one\\" + name;
   if(p == SYMBOL_DESCRIPTION) return "Description, with a comma";
   return "USD";
  }
bool SymbolInfoTick(const string, MqlTick &k) { k.bid = 100.0; k.ask = 100.5; k.time = MOCK_NOW; return true; }
bool SymbolInfoSessionTrade(const string, ENUM_DAY_OF_WEEK d, uint si, datetime &from, datetime &to)
  {
   if(d == SUNDAY || d == SATURDAY || si > 0) return false;
   from = 60;
   to = 86400 - 300;
   return true;
  }
bool OrderCalcMargin(ENUM_ORDER_TYPE, const string, double, double, double &margin) { margin = 123.45; return true; }

// ---- ticks: one tick every 7 seconds on weekdays since MOCK_HISTORY_START (the same formula as live_ai/check/test_releve.py)
static bool mock_tick(long s, double &bid, double &ask)
  {
   long dow = ((s / 86400) + 4) % 7;                       // 0 = Sunday
   if(s % 7 != 3 || dow == 0 || dow == 6 || s < MOCK_HISTORY_START || s > MOCK_NOW) return false;
   bid = 100.0 + (double)((s * 2654435761L) % 1000) / 100.0;
   double sp = 0.10 + (double)((s / 60) % 5) * 0.01 + (s % 13 == 0 ? 0.20 : 0.0);
   ask = bid + sp;
   if(s % 997 == 0) bid = 0.0;                              // a broken tick now and then
   return true;
  }
int CopyTicksRange(const string name, MqlArray<MqlTick> &t, uint flags, ulong from_msc, ulong to_msc)
  {
   g_copy_calls++;
   t.v.clear();
   if(!mock_known(name) || flags != (uint)COPY_TICKS_INFO) { g_last_error = 4301; return -1; }
   for(long s = (long)(from_msc / 1000); s <= (long)(to_msc / 1000); s++)
     {
      double b, a;
      if(!mock_tick(s, b, a)) continue;
      MqlTick k = MqlTick();
      k.time = s; k.bid = b; k.ask = a; k.time_msc = s * 1000 + 250;
      t.v.push_back(k);
     }
   return (int)t.v.size();
  }

// ---- the terminal's M1 bars: one bar every weekday minute from MOCK_R1_START to the run, prices of the minute
static long mock_last_bar() { long m = MOCK_NOW - MOCK_NOW % 60 - 60; while((((m / 86400) + 4) % 7) % 6 == 0) m -= 60; return m; }
static bool mock_bar(long m, MqlRates &b)
  {
   long dow = ((m / 86400) + 4) % 7;
   if(dow == 0 || dow == 6 || m < MOCK_R1_START || m > mock_last_bar()) return false;
   b = MqlRates();
   b.time = m;
   b.open = 100.0 + (double)((m / 60) % 97) / 100.0;
   b.high = b.open + 0.05;
   b.low = b.open - 0.04;
   b.close = b.open + 0.01;
   b.tick_volume = 3 + (m / 60) % 7;
   b.spread = 10 + (int)((m / 60) % 3);
   b.real_volume = 0;
   return true;
  }
static bool mock_loading(const string &name)
  {
   if(!g_first_ask.count(name)) g_first_ask[name] = g_slept_ms;
   return g_slept_ms - g_first_ask[name] < mock_env("MOCK_R1_LOAD_MS", 0);
  }
static int mock_count(long from, long to)
  {
   int n = 0;
   MqlRates b;
   for(long m = from - from % 60; m <= to; m += 60)
      if(m >= from && mock_bar(m, b)) n++;
   return n;
  }
int Bars(const string name, ENUM_TIMEFRAMES tf) { return Bars(name, tf, MOCK_R1_START, MOCK_NOW); }
int Bars(const string name, ENUM_TIMEFRAMES tf, datetime from, datetime to)
  {
   if(!mock_known(name) || tf != PERIOD_M1 || mock_loading(name)) return 0;
   return mock_count((long)from, (long)to);
  }
long SeriesInfoInteger(const string name, ENUM_TIMEFRAMES tf, ENUM_SERIES_INFO_INTEGER p)
  {
   if(!mock_known(name) || tf != PERIOD_M1) return 0;
   bool loading = mock_loading(name);
   if(p == SERIES_SYNCHRONIZED) return loading ? 0 : 1;
   if(p == SERIES_FIRSTDATE || p == SERIES_SERVER_FIRSTDATE || p == SERIES_TERMINAL_FIRSTDATE) return loading ? 0 : MOCK_R1_START;
   if(p == SERIES_LASTBAR_DATE) return loading ? 0 : mock_last_bar();
   if(p == SERIES_BARS_COUNT) return loading ? 0 : mock_count(MOCK_R1_START, MOCK_NOW);
   return 0;
  }
bool SeriesInfoInteger(const string name, ENUM_TIMEFRAMES tf, ENUM_SERIES_INFO_INTEGER p, long &v) { v = SeriesInfoInteger(name, tf, p); return true; }
static std::map<string, std::map<long, int>> g_rates_day_calls;
int CopyRates(const string name, ENUM_TIMEFRAMES tf, datetime from, datetime to, MqlArray<MqlRates> &r)
  {
   r.v.clear();
   if(!mock_known(name) || tf != PERIOD_M1) { g_last_error = 4301; return -1; }
   if(mock_loading(name)) return 0;                         // still loading: what is ready at the timeout (nothing)
   long day = (long)from - (long)from % 86400;
   int k = g_rates_day_calls[name][day]++;
   if(mock_env("MOCK_R1_AFTER_LAST", 0) && (long)from > mock_last_bar()) { g_last_error = 4401; return -1; }
   long last = (long)to;
   if(mock_env("MOCK_R1_PARTIAL", 0))
     {
      if(k > 0) { g_last_error = 4401; return -1; }        // every call after the first fails
      last = day + 43200 - 1;                               // the first gives the first half of the day only
     }
   for(long m = (long)from - (long)from % 60; m <= last; m += 60)
     {
      MqlRates b;
      if(m >= (long)from && mock_bar(m, b)) r.v.push_back(b);
     }
   return (int)r.v.size();
  }
int CopyRates(const string name, ENUM_TIMEFRAMES tf, datetime from, int count, MqlArray<MqlRates> &r) { r.v.clear(); return -1; }
int CopyRates(const string name, ENUM_TIMEFRAMES tf, int pos, int count, MqlArray<MqlRates> &r) { r.v.clear(); return -1; }

// ---- files (no parent folder is created by FileOpen: the script's own FolderCreate calls must be enough)
bool FolderCreate(const string name, int) { return mkdir(mock_path(name).c_str(), 0755) == 0 || true; }
bool FileDelete(const string name, int) { return remove(mock_path(name).c_str()) == 0; }
int FileOpen(const string name, int flags, short, uint)
  {
   const char *log = getenv("MOCK_OPEN_LOG");
   if(log && *log)
     {
      FILE *l = fopen(log, "a");
      if(l) { fprintf(l, "%s\n", name.c_str()); fclose(l); }
     }
   FILE *f = fopen(mock_path(name).c_str(), (flags & FILE_WRITE) ? "w" : "r");
   if(!f) { g_last_error = 5004; return INVALID_HANDLE; }
   g_files[g_next_handle] = f;
   return g_next_handle++;
  }
uint FileWriteString(int h, const string text, int) { fputs(text.c_str(), g_files[h]); return (uint)text.size(); }
void FileFlush(int h) { fflush(g_files[h]); }
void FileClose(int h) { fclose(g_files[h]); g_files.erase(h); }
