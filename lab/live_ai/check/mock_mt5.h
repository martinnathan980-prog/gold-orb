// A tiny working imitation of the MetaTrader 5 functions used by ReleveFP.mq5, so that the translated script can
// be RUN here (g++), and its output files compared with what the Python reader expects (check/test_releve.py).
// It is not MetaTrader: it only proves the script's own logic (minute aggregation, file formats, symbol search).
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

// ---- files (no parent folder is created by FileOpen: the script's own FolderCreate calls must be enough)
bool FolderCreate(const string name, int) { return mkdir(mock_path(name).c_str(), 0755) == 0 || true; }
bool FileDelete(const string name, int) { return remove(mock_path(name).c_str()) == 0; }
int FileOpen(const string name, int flags, short, uint)
  {
   FILE *f = fopen(mock_path(name).c_str(), (flags & FILE_WRITE) ? "w" : "r");
   if(!f) { g_last_error = 5004; return INVALID_HANDLE; }
   g_files[g_next_handle] = f;
   return g_next_handle++;
  }
uint FileWriteString(int h, const string text, int) { fputs(text.c_str(), g_files[h]); return (uint)text.size(); }
void FileFlush(int h) { fflush(g_files[h]); }
void FileClose(int h) { fclose(g_files[h]); g_files.erase(h); }
