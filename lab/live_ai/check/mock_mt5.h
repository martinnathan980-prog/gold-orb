// A tiny working imitation of the MetaTrader 5 functions used by ReleveFP.mq5, so that the translated script can
// be RUN here (g++), and its output files compared with what the Python reader expects (check/test_releve.py).
// It is not MetaTrader: it only proves the script's own logic (minute aggregation, file formats, symbol search).
// ReleveFP 1.11 (check_111): the account's deal history and open positions, read from MOCK_DEALS_FILE and MOCK_POSITIONS_FILE (block
// 'ReleveFP 1.11' below, the same as lab/robot/demo/releve_mock/mock_mt5.h's); without them, an empty history and no position.
// review8 (test_releve.py imitation_doc): FileWriteString follows the documentation (a CR before a bare LF of a TXT or CSV file, the bytes
// written returned), FileOpen and FileWriteString fail on demand, the deal getters answer for the listed deals only, a symbol may be 'not
// selected in Market Watch' (4302), and the account has a planted server, company, holder's name and login.
#pragma once
#include "mql5_shim.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <sys/stat.h>

static const long MOCK_NOW = 1794479400;            // 2026-11-12 10:30:00, server clock (a Thursday)
static const long MOCK_HISTORY_START = MOCK_NOW - 10 * 86400;
static const char *MOCK_SYMBOLS[] = {"EURUSD.r", "XAUUSD.r", "USDJPY.r", "BTCUSD", "ETHUSD", "NAS100", "JPN225", "US500", "DE40",
                                     "AAPL.US"};
static std::map<int, FILE *> g_files;
static int g_next_handle = 1, g_last_error = 0, g_copy_calls = 0;

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

// ---- terminal, account, symbols
int GetLastError() { return g_last_error; }
void ResetLastError() { g_last_error = 0; }
datetime TimeTradeServer() { return MOCK_NOW; }
datetime TimeGMT() { return MOCK_NOW - 7200; }
void Sleep(int) {}
bool IsStopped() { return false; }
uint GetTickCount() { return 0; }
// the account (review8 IMIT-LOOSE c): its server, company, holder's name and login are planted, so that a script writing any of them is
// caught by the tests' scan of its files (ReleveFP writes none: test_releve.py ACCOUNT_PLANTED)
string AccountInfoString(ENUM_ACCOUNT_INFO_STRING p)
  {
   if(p == ACCOUNT_CURRENCY) return "EUR";
   if(p == ACCOUNT_SERVER) return "FPMarketsSC-Demo7";
   if(p == ACCOUNT_COMPANY) return "First Prudential Markets Ltd";
   if(p == ACCOUNT_NAME) return "Marie-Claire Fontanel";
   return "";
  }
long AccountInfoInteger(ENUM_ACCOUNT_INFO_INTEGER p)
  {
   if(p == ACCOUNT_CURRENCY_DIGITS) { const char *v = getenv("MOCK_CCY_DIGITS"); return (v && *v) ? atol(v) : 2; }   // ReleveFP 1.11
   if(p == ACCOUNT_LOGIN) return 51234987;
   return p == ACCOUNT_LEVERAGE ? 500 : (long)ACCOUNT_TRADE_MODE_DEMO;
  }
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
static double mk11_vstep(const string &name);                       // ReleveFP 1.11: the volume step of each symbol (below)
double SymbolInfoDouble(const string name, ENUM_SYMBOL_INFO_DOUBLE p)
  {
   if(p == SYMBOL_VOLUME_STEP) return mk11_vstep(name);
   return p == SYMBOL_POINT ? 0.01 : 1.0;
  }
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

// ---- ticks: one tick every 7 seconds on weekdays since MOCK_HISTORY_START (same formula in test_releve.py)
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
// One day (two days before "today") comes back INCOMPLETE with error 4403 (history not yet synchronised):
// for ETHUSD on the first request only (the script's retry gets the full day), for US500 on every request.
static const long MOCK_PARTIAL_DAY = MOCK_NOW - MOCK_NOW % 86400 - 2 * 86400;
static std::map<string, int> g_day_calls;
int CopyTicksRange(const string name, MqlArray<MqlTick> &t, uint flags, ulong from_msc, ulong to_msc)
  {
   g_copy_calls++;
   t.v.clear();
   if(!mock_known(name) || flags != (uint)COPY_TICKS_INFO) { g_last_error = 4301; return -1; }
   long last = (long)(to_msc / 1000);
   if((long)(from_msc / 1000) == MOCK_PARTIAL_DAY && (name == "US500" || (name == "ETHUSD" && g_day_calls[name]++ == 0)))
     {
      last = MOCK_PARTIAL_DAY + 43200 - 1;                  // only the first half of the day
      g_last_error = 4403;
     }
   for(long s = (long)(from_msc / 1000); s <= last; s++)
     {
      double b, a;
      if(!mock_tick(s, b, a)) continue;
      MqlTick k = MqlTick();
      k.time = s; k.bid = b; k.ask = a; k.time_msc = s * 1000 + 250;
      t.v.push_back(k);
     }
   return (int)t.v.size();
  }


// ---- ReleveFP 1.10 (lab/robot/demo/releve_mock/mock_mt5.h has the same bars with scenarios)
static long g_slept_ms = 0;
static std::map<string, long> g_first_ask;
static const long MOCK_R1_START = (MOCK_NOW - 40 * 86400) - (MOCK_NOW - 40 * 86400) % 86400;
long StringToInteger(const string value) { return atol(value.c_str()); }
int TerminalInfoInteger(ENUM_TERMINAL_INFO_INTEGER p) { return p == TERMINAL_MAXBARS ? 500000 : 1; }
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
   return g_slept_ms - g_first_ask[name] < 0;
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
   if(0 && (long)from > mock_last_bar()) { g_last_error = 4401; return -1; }
   long last = (long)to;
   if(0)
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


// ---- ReleveFP 1.11: the account's deal history and its open positions (HistorySelect, HistoryDealsTotal, HistoryDealGetTicket,
// HistoryDealGetInteger/Double/String, PositionsTotal, PositionGetTicket, PositionSelectByTicket, PositionGetInteger/Double/String,
// EnumToString of the deal and position enumerations), with MetaTrader's documented behaviour (docs.mql5.com, read 2026-11-15):
//   HistorySelect(from, to) "creates a list of orders and a list of trades": here every deal whose DEAL_TIME is in [from, to], in the
//     order of the MOCK_DEALS_FILE lines (the documentation promises no order: the files give them shuffled, the script must sort);
//   HistoryDealGetTicket(i) returns 0 outside the list; the getters take a deal ticket and answer only for a deal of the list HistorySelect
//     made (HistoryDealSelect "clears in a mql5-program the list of deals available for reference": the getters refer to that list): 0 or ""
//     with error 4755 ERR_TRADE_DEAL_NOT_FOUND for any other ticket (review8 IMIT-LOOSE a; the code is this imitation's choice, the pages
//     name none);
//   PositionGetTicket(i) "automatically selects the position", 0 when it fails; PositionSelectByTicket selects (false: no such position);
//   EnumToString: the identifier's name, "ENUM_DEAL_TYPE::17" for a value outside the enumeration (the page's example prints
//     "ENUM_ORDER_TYPE::-1");
//   SymbolInfoInteger / SymbolInfoDouble with a result variable: false for a symbol the terminal does not know (4301), and for a symbol of
//     MOCK_SYM_NOT_SELECTED (4302 ERR_MARKET_NOT_SELECTED "Symbol is not selected in MarketWatch", listed by the SymbolInfoInteger page;
//     review8 IMIT-LOOSE b);
//   FileWriteString (files/filewritestring): "When writing to a CSV or TXT file: if there is a symbol in the string '\n' (LF) without previous
//     character '\r' (CR), then before '\n' the missing '\r' is added"; "If successful the function returns the number of bytes written":
//     a file opened FILE_TXT or FILE_CSV gets the CR, and the count includes it (one byte per character: FILE_ANSI); a BIN file gets the
//     text as it is (review8 IMIT-CRLF: the first imitation wrote the text unchanged and returned its length, which hid a script that
//     rejected every row).
// The deals and positions come from files written by the tests (a comment and an external id ride along: the script must never write
// them); no file = an empty history and no position:
//   MOCK_DEALS_FILE     CSV "ticket,order,position,time,time_msc,symbol,type,entry,reason,magic,volume,price,sl,tp,commission,swap,fee,
//                       profit,comment,external_id" (type, entry, reason: the enumerations' positions in the documentation's lists)
//   MOCK_POSITIONS_FILE CSV "ticket,identifier,time,time_msc,symbol,type,magic,volume,price_open,sl,tp,price_current,swap,profit,comment,
//                       external_id"
//   MOCK_HISTORY_FAIL   HistorySelect returns false and sets this error code (0: no code)
//   MOCK_POSITION_GONE  a position ticket listed by PositionGetTicket that PositionSelectByTicket no longer finds (closed meanwhile)
//   MOCK_WRITE_FAIL     "deals.csv:N": the N-th FileWriteString into that file writes nothing, returns 0 and sets error 5026; "deals.csv:N:C"
//                       sets error C instead, and "deals.csv:N:0" sets none (the last error stays what an earlier call left: review8
//                       LASTERR-STALE)
//   MOCK_OPEN_FAIL      "deals.csv" or "positions.csv" (a comma list): FileOpen of that name fails, INVALID_HANDLE and error 5004
//                       ERR_CANNOT_OPEN_FILE (review8 OPEN-FAIL-UNTESTED)
//   MOCK_SYM_NOT_SELECTED  "NAME,...": SymbolInfoInteger / SymbolInfoDouble with a result variable fail with 4302 for these names
//   MOCK_CCY_DIGITS     ACCOUNT_CURRENCY_DIGITS (default 2)
//   MOCK_SYMS_EXTRA     "NAME:digits:volume_step,..." symbols the terminal knows besides the fixed list (the harness's .r names)
struct Mk11Deal
  {
   ulong ticket, order, position;
   long time, time_msc;
   string symbol;
   long type, entry, reason, magic;
   double volume, price, sl, tp, commission, swap, fee, profit;
   string comment, external_id;
  };
struct Mk11Pos
  {
   ulong ticket, identifier;
   long time, time_msc;
   string symbol;
   long type, magic;
   double volume, price_open, sl, tp, price_current, swap, profit;
   string comment, external_id;
  };
static std::vector<Mk11Deal> g11_deals;
static std::vector<Mk11Pos> g11_pos;
static std::vector<int> g11_hist;                               // the deals HistorySelect listed
static bool g11_loaded = false;
static ulong g11_selected = 0;
static std::map<int, string> g11_file_of;                       // file handle -> file name (MOCK_WRITE_FAIL)
static std::map<int, bool> g11_text_of;                         // file handle -> opened FILE_TXT or FILE_CSV (the CR before a bare LF)
static std::map<string, int> g11_writes;
static long mk11_env(const char *k, long dflt)
  {
   const char *v = getenv(k);
   return (v && *v) ? atol(v) : dflt;
  }
static std::vector<string> mk11_split(const string &s, char sep)
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
static std::vector<std::vector<string>> mk11_rows(const char *env)
  {
   std::vector<std::vector<string>> out;
   const char *p = getenv(env);
   if(!p || !*p) return out;
   FILE *f = fopen(p, "r");
   if(!f) return out;
   char line[4096];
   bool head = true;
   while(fgets(line, sizeof line, f))
     {
      string s = line;
      while(!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
      if(head) { head = false; continue; }
      if(!s.empty()) out.push_back(mk11_split(s, ','));
     }
   fclose(f);
   return out;
  }
static void mk11_load()
  {
   if(g11_loaded) return;
   g11_loaded = true;
   for(const auto &r : mk11_rows("MOCK_DEALS_FILE"))
     {
      if(r.size() < 20) continue;
      Mk11Deal d;
      d.ticket = strtoul(r[0].c_str(), nullptr, 10); d.order = strtoul(r[1].c_str(), nullptr, 10); d.position = strtoul(r[2].c_str(), nullptr, 10);
      d.time = atol(r[3].c_str()); d.time_msc = atol(r[4].c_str()); d.symbol = r[5];
      d.type = atol(r[6].c_str()); d.entry = atol(r[7].c_str()); d.reason = atol(r[8].c_str()); d.magic = atol(r[9].c_str());
      d.volume = atof(r[10].c_str()); d.price = atof(r[11].c_str()); d.sl = atof(r[12].c_str()); d.tp = atof(r[13].c_str());
      d.commission = atof(r[14].c_str()); d.swap = atof(r[15].c_str()); d.fee = atof(r[16].c_str()); d.profit = atof(r[17].c_str());
      d.comment = r[18]; d.external_id = r[19];
      g11_deals.push_back(d);
     }
   for(const auto &r : mk11_rows("MOCK_POSITIONS_FILE"))
     {
      if(r.size() < 16) continue;
      Mk11Pos q;
      q.ticket = strtoul(r[0].c_str(), nullptr, 10); q.identifier = strtoul(r[1].c_str(), nullptr, 10);
      q.time = atol(r[2].c_str()); q.time_msc = atol(r[3].c_str()); q.symbol = r[4]; q.type = atol(r[5].c_str()); q.magic = atol(r[6].c_str());
      q.volume = atof(r[7].c_str()); q.price_open = atof(r[8].c_str()); q.sl = atof(r[9].c_str()); q.tp = atof(r[10].c_str());
      q.price_current = atof(r[11].c_str()); q.swap = atof(r[12].c_str()); q.profit = atof(r[13].c_str());
      q.comment = r[14]; q.external_id = r[15];
      g11_pos.push_back(q);
     }
  }
// the extra symbols of MOCK_SYMS_EXTRA: digits and volume step, or false
static bool mk11_extra(const string &name, long &digits, double &step)
  {
   const char *e = getenv("MOCK_SYMS_EXTRA");
   if(!e || !*e) return false;
   for(const string &it : mk11_split(e, ','))
     {
      std::vector<string> p = mk11_split(it, ':');
      if(p.size() == 3 && p[0] == name)
        {
         digits = atol(p[1].c_str());
         step = atof(p[2].c_str());
         return true;
        }
     }
   return false;
  }
// the volume step of the fixed symbols (the fiche's SYMBOL_VOLUME_STEP too)
static double mk11_vstep(const string &name)
  {
   long dg = 0;
   double st = 0.0;
   if(mk11_extra(name, dg, st)) return st;
   if(name == "NAS100" || name == "JPN225" || name == "US500" || name == "DE40") return 0.1;
   if(name == "AAPL.US") return 1.0;
   return 0.01;
  }
static bool mk11_known(const string &name)
  {
   long dg = 0;
   double st = 0.0;
   return mock_known(name) || mk11_extra(name, dg, st);
  }
// a name of a comma list held by an environment variable (MOCK_SYM_NOT_SELECTED, MOCK_OPEN_FAIL)
static bool mk11_listed(const char *env, const string &name)
  {
   const char *e = getenv(env);
   if(!e || !*e) return false;
   for(const string &it : mk11_split(e, ','))
      if(it == name) return true;
   return false;
  }

int StringLen(const string s) { return (int)s.size(); }
double MathAbs(double v) { return std::fabs(v); }
double MathRound(double v) { return std::round(v); }
bool SymbolInfoInteger(const string name, ENUM_SYMBOL_INFO_INTEGER p, long &v)
  {
   if(!mk11_known(name)) { g_last_error = 4301; return false; }      // ERR_MARKET_UNKNOWN_SYMBOL
   if(mk11_listed("MOCK_SYM_NOT_SELECTED", name)) { g_last_error = 4302; return false; }   // ERR_MARKET_NOT_SELECTED
   long dg = 2;
   double st = 0.0;
   mk11_extra(name, dg, st);
   v = (p == SYMBOL_DIGITS) ? dg : SymbolInfoInteger(name, p);
   return true;
  }
bool SymbolInfoDouble(const string name, ENUM_SYMBOL_INFO_DOUBLE p, double &v)
  {
   if(!mk11_known(name)) { g_last_error = 4301; return false; }
   if(mk11_listed("MOCK_SYM_NOT_SELECTED", name)) { g_last_error = 4302; return false; }
   v = SymbolInfoDouble(name, p);
   return true;
  }

static const char *MK11_DEAL_TYPE[] = {"DEAL_TYPE_BUY", "DEAL_TYPE_SELL", "DEAL_TYPE_BALANCE", "DEAL_TYPE_CREDIT", "DEAL_TYPE_CHARGE",
                                       "DEAL_TYPE_CORRECTION", "DEAL_TYPE_BONUS", "DEAL_TYPE_COMMISSION", "DEAL_TYPE_COMMISSION_DAILY",
                                       "DEAL_TYPE_COMMISSION_MONTHLY", "DEAL_TYPE_COMMISSION_AGENT_DAILY", "DEAL_TYPE_COMMISSION_AGENT_MONTHLY",
                                       "DEAL_TYPE_INTEREST", "DEAL_TYPE_BUY_CANCELED", "DEAL_TYPE_SELL_CANCELED", "DEAL_DIVIDEND",
                                       "DEAL_DIVIDEND_FRANKED", "DEAL_TAX"};
static const char *MK11_DEAL_ENTRY[] = {"DEAL_ENTRY_IN", "DEAL_ENTRY_OUT", "DEAL_ENTRY_INOUT", "DEAL_ENTRY_OUT_BY"};
static const char *MK11_DEAL_REASON[] = {"DEAL_REASON_CLIENT", "DEAL_REASON_MOBILE", "DEAL_REASON_WEB", "DEAL_REASON_EXPERT", "DEAL_REASON_SL",
                                         "DEAL_REASON_TP", "DEAL_REASON_SO", "DEAL_REASON_ROLLOVER", "DEAL_REASON_VMARGIN", "DEAL_REASON_SPLIT",
                                         "DEAL_REASON_CORPORATE_ACTION"};
static const char *MK11_POSITION_TYPE[] = {"POSITION_TYPE_BUY", "POSITION_TYPE_SELL"};
static string mk11_name(const char *const *names, int n, const char *type, long v)
  {
   if(v >= 0 && v < n) return names[v];
   g_last_error = 4003;                                            // ERR_INVALID_PARAMETER ("can't allow the name of the enumeration value")
   return string(type) + "::" + std::to_string(v);
  }
template <> string EnumToString<ENUM_DEAL_TYPE>(ENUM_DEAL_TYPE v) { return mk11_name(MK11_DEAL_TYPE, 18, "ENUM_DEAL_TYPE", (long)v); }
template <> string EnumToString<ENUM_DEAL_ENTRY>(ENUM_DEAL_ENTRY v) { return mk11_name(MK11_DEAL_ENTRY, 4, "ENUM_DEAL_ENTRY", (long)v); }
template <> string EnumToString<ENUM_DEAL_REASON>(ENUM_DEAL_REASON v) { return mk11_name(MK11_DEAL_REASON, 11, "ENUM_DEAL_REASON", (long)v); }
template <> string EnumToString<ENUM_POSITION_TYPE>(ENUM_POSITION_TYPE v) { return mk11_name(MK11_POSITION_TYPE, 2, "ENUM_POSITION_TYPE", (long)v); }

bool HistorySelect(datetime from, datetime to)
  {
   mk11_load();
   g11_hist.clear();
   const char *fail = getenv("MOCK_HISTORY_FAIL");
   if(fail && *fail) { g_last_error = atoi(fail); return false; }
   for(int i = 0; i < (int)g11_deals.size(); i++)
      if(g11_deals[i].time >= (long)from && g11_deals[i].time <= (long)to) g11_hist.push_back(i);
   return true;
  }
int HistoryDealsTotal() { return (int)g11_hist.size(); }
ulong HistoryDealGetTicket(int i) { return (i >= 0 && i < (int)g11_hist.size()) ? g11_deals[g11_hist[i]].ticket : 0; }
static const Mk11Deal *mk11_deal(ulong t)
  {
   for(int i : g11_hist)                                           // only a deal of the list HistorySelect made
      if(g11_deals[i].ticket == t) return &g11_deals[i];
   g_last_error = 4755;                                            // ERR_TRADE_DEAL_NOT_FOUND
   return nullptr;
  }
long HistoryDealGetInteger(ulong t, ENUM_DEAL_PROPERTY_INTEGER p)
  {
   const Mk11Deal *d = mk11_deal(t);
   if(!d) return 0;
   if(p == DEAL_TICKET) return (long)d->ticket;
   if(p == DEAL_ORDER) return (long)d->order;
   if(p == DEAL_TIME) return d->time;
   if(p == DEAL_TIME_MSC) return d->time_msc;
   if(p == DEAL_TYPE) return d->type;
   if(p == DEAL_ENTRY) return d->entry;
   if(p == DEAL_MAGIC) return d->magic;
   if(p == DEAL_REASON) return d->reason;
   if(p == DEAL_POSITION_ID) return (long)d->position;
   return 0;
  }
double HistoryDealGetDouble(ulong t, ENUM_DEAL_PROPERTY_DOUBLE p)
  {
   const Mk11Deal *d = mk11_deal(t);
   if(!d) return 0.0;
   if(p == DEAL_VOLUME) return d->volume;
   if(p == DEAL_PRICE) return d->price;
   if(p == DEAL_COMMISSION) return d->commission;
   if(p == DEAL_SWAP) return d->swap;
   if(p == DEAL_PROFIT) return d->profit;
   if(p == DEAL_FEE) return d->fee;
   if(p == DEAL_SL) return d->sl;
   if(p == DEAL_TP) return d->tp;
   return 0.0;
  }
string HistoryDealGetString(ulong t, ENUM_DEAL_PROPERTY_STRING p)
  {
   const Mk11Deal *d = mk11_deal(t);
   if(!d) return "";
   if(p == DEAL_SYMBOL) return d->symbol;
   if(p == DEAL_EXTERNAL_ID) return d->external_id;
   return d->comment;                                              // DEAL_COMMENT
  }
int PositionsTotal() { mk11_load(); return (int)g11_pos.size(); }
static const Mk11Pos *mk11_pos(ulong t)
  {
   if((long)t == mk11_env("MOCK_POSITION_GONE", -1)) return nullptr;
   for(const Mk11Pos &q : g11_pos)
      if(q.ticket == t) return &q;
   return nullptr;
  }
ulong PositionGetTicket(int i)
  {
   mk11_load();
   if(i < 0 || i >= (int)g11_pos.size()) return 0;
   g11_selected = g11_pos[i].ticket;
   return g11_selected;
  }
bool PositionSelectByTicket(ulong t)
  {
   mk11_load();
   if(!mk11_pos(t)) { g_last_error = 4753; return false; }        // ERR_TRADE_POSITION_NOT_FOUND
   g11_selected = t;
   return true;
  }
long PositionGetInteger(ENUM_POSITION_PROPERTY_INTEGER p)
  {
   const Mk11Pos *q = mk11_pos(g11_selected);
   if(!q) return 0;
   if(p == POSITION_TICKET) return (long)q->ticket;
   if(p == POSITION_IDENTIFIER) return (long)q->identifier;
   if(p == POSITION_TIME) return q->time;
   if(p == POSITION_TIME_MSC) return q->time_msc;
   if(p == POSITION_TYPE) return q->type;
   if(p == POSITION_MAGIC) return q->magic;
   return 0;
  }
double PositionGetDouble(ENUM_POSITION_PROPERTY_DOUBLE p)
  {
   const Mk11Pos *q = mk11_pos(g11_selected);
   if(!q) return 0.0;
   if(p == POSITION_VOLUME) return q->volume;
   if(p == POSITION_PRICE_OPEN) return q->price_open;
   if(p == POSITION_SL) return q->sl;
   if(p == POSITION_TP) return q->tp;
   if(p == POSITION_PRICE_CURRENT) return q->price_current;
   if(p == POSITION_SWAP) return q->swap;
   if(p == POSITION_PROFIT) return q->profit;
   return 0.0;
  }
string PositionGetString(ENUM_POSITION_PROPERTY_STRING p)
  {
   const Mk11Pos *q = mk11_pos(g11_selected);
   if(!q) return "";
   if(p == POSITION_SYMBOL) return q->symbol;
   if(p == POSITION_EXTERNAL_ID) return q->external_id;
   return q->comment;                                              // POSITION_COMMENT
  }

// ---- files (no parent folder is created by FileOpen: the script's own FolderCreate calls must be enough)
bool FolderCreate(const string name, int) { return mkdir(mock_path(name).c_str(), 0755) == 0 || true; }
bool FileDelete(const string name, int) { return remove(mock_path(name).c_str()) == 0; }
int FileOpen(const string name, int flags, short, uint)
  {
   size_t sl = name.find_last_of("\\/");
   string base = sl == string::npos ? name : name.substr(sl + 1);
   if(mk11_listed("MOCK_OPEN_FAIL", base)) { g_last_error = 5004; return INVALID_HANDLE; }   // review8 OPEN-FAIL-UNTESTED
   FILE *f = fopen(mock_path(name).c_str(), (flags & FILE_WRITE) ? "w" : "r");
   if(!f) { g_last_error = 5004; return INVALID_HANDLE; }
   g_files[g_next_handle] = f;
   g11_file_of[g_next_handle] = base;                              // ReleveFP 1.11: MOCK_WRITE_FAIL
   g11_text_of[g_next_handle] = (flags & (FILE_TXT | FILE_CSV)) != 0;
   return g_next_handle++;
  }
uint FileWriteString(int h, const string text, int)
  {
   const char *wf = getenv("MOCK_WRITE_FAIL");                      // ReleveFP 1.11: "deals.csv:N[:code]", the N-th write of that file fails
   if(wf && *wf)
     {
      std::vector<string> p = mk11_split(wf, ':');
      string nm = g11_file_of.count(h) ? g11_file_of[h] : "";
      if((p.size() == 2 || p.size() == 3) && p[0] == nm && ++g11_writes[nm] == atol(p[1].c_str()))
        {
         int code = p.size() == 3 ? atoi(p[2].c_str()) : 5026;
         if(code != 0) g_last_error = code;                        // 0: the failure sets no code of its own
         return 0;
        }
     }
   string out = text;
   if(g11_text_of.count(h) && g11_text_of[h])                      // TXT or CSV: the CR the documentation adds before a bare LF
     {
      out.clear();
      for(size_t i = 0; i < text.size(); i++)
        {
         if(text[i] == '\n' && (i == 0 || text[i - 1] != '\r')) out += '\r';
         out += text[i];
        }
     }
   fputs(out.c_str(), g_files[h]);
   return (uint)out.size();                                        // the bytes written (FILE_ANSI: one per character, the CR included)
  }
void FileFlush(int h) { fflush(g_files[h]); }
void FileClose(int h) { fclose(g_files[h]); g_files.erase(h); }
