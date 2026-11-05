// Minimal C++ declarations mirroring the MQL5 builtins / Trade.mqh (2000-2025) signatures used by
// GoldOrb_Donchian4H.mq5, so that g++ -fsyntax-only can check names, argument counts and types.
// Signatures copied from docs.mql5.com and ref_trade_mqh/T.mqh. Bodies are never needed.
#pragma once
#include <string>
#include <vector>
#include <cfloat>
#include <climits>
#undef SEEK_SET
#undef SEEK_CUR
#undef SEEK_END

using string = std::string;
typedef long datetime;              // MQL5: 8-byte date type
typedef unsigned long ulong;
typedef unsigned int uint;
typedef unsigned char uchar;
typedef unsigned short ushort;

template <typename T> struct MqlArray {   // stands for MQL5 "T name[]" (dynamic array)
   std::vector<T> v;
   T &operator[](int i) { return v[i]; }
   const T &operator[](int i) const { return v[i]; }
};

extern const string _Symbol;
extern const double _Point;
extern const int _Digits;

enum ENUM_TIMEFRAMES { PERIOD_CURRENT = 0, PERIOD_M1 = 1, PERIOD_M5 = 5 };
enum ENUM_ORDER_TYPE_TIME { ORDER_TIME_GTC, ORDER_TIME_DAY, ORDER_TIME_SPECIFIED, ORDER_TIME_SPECIFIED_DAY };
enum ENUM_TRADE_TRANSACTION_TYPE { TRADE_TRANSACTION_ORDER_ADD, TRADE_TRANSACTION_DEAL_ADD = 6 };
enum ENUM_SERIES_INFO_INTEGER { SERIES_BARS_COUNT, SERIES_SYNCHRONIZED = 5 };
enum ENUM_TERMINAL_INFO_INTEGER { TERMINAL_CONNECTED, TERMINAL_TRADE_ALLOWED, TERMINAL_MAXBARS };
enum ENUM_MQL_INFO_INTEGER { MQL_TESTER, MQL_TRADE_ALLOWED };
enum ENUM_ACCOUNT_INFO_INTEGER { ACCOUNT_LOGIN, ACCOUNT_TRADE_MODE };
enum ENUM_ACCOUNT_INFO_DOUBLE { ACCOUNT_EQUITY };
enum ENUM_ACCOUNT_TRADE_MODE { ACCOUNT_TRADE_MODE_DEMO, ACCOUNT_TRADE_MODE_CONTEST, ACCOUNT_TRADE_MODE_REAL };
enum ENUM_SYMBOL_INFO_INTEGER { SYMBOL_TRADE_STOPS_LEVEL, SYMBOL_TRADE_FREEZE_LEVEL, SYMBOL_EXPIRATION_MODE };
enum ENUM_SYMBOL_INFO_DOUBLE { SYMBOL_TRADE_TICK_SIZE, SYMBOL_TRADE_TICK_VALUE, SYMBOL_TRADE_TICK_VALUE_LOSS,
                               SYMBOL_VOLUME_MIN, SYMBOL_VOLUME_STEP, SYMBOL_VOLUME_MAX };
const int SYMBOL_EXPIRATION_GTC = 1, SYMBOL_EXPIRATION_DAY = 2, SYMBOL_EXPIRATION_SPECIFIED = 4;
enum ENUM_ORDER_PROPERTY_INTEGER { ORDER_MAGIC, ORDER_TYPE };
enum ENUM_ORDER_TYPE { ORDER_TYPE_BUY = 0, ORDER_TYPE_SELL = 1, ORDER_TYPE_BUY_LIMIT = 2, ORDER_TYPE_SELL_LIMIT = 3, ORDER_TYPE_BUY_STOP = 4, ORDER_TYPE_SELL_STOP = 5 };
enum ENUM_ORDER_PROPERTY_STRING { ORDER_SYMBOL };
enum ENUM_POSITION_PROPERTY_INTEGER { POSITION_TICKET, POSITION_TIME, POSITION_TYPE, POSITION_MAGIC, POSITION_IDENTIFIER };
enum ENUM_POSITION_PROPERTY_DOUBLE { POSITION_VOLUME, POSITION_PRICE_OPEN, POSITION_SL, POSITION_TP };
enum ENUM_POSITION_PROPERTY_STRING { POSITION_SYMBOL };
enum ENUM_POSITION_TYPE { POSITION_TYPE_BUY, POSITION_TYPE_SELL };
enum ENUM_DEAL_PROPERTY_INTEGER { DEAL_MAGIC, DEAL_ENTRY, DEAL_TYPE, DEAL_POSITION_ID };
enum ENUM_DEAL_PROPERTY_DOUBLE { DEAL_PRICE };
enum ENUM_DEAL_PROPERTY_STRING { DEAL_SYMBOL };
enum ENUM_DEAL_ENTRY { DEAL_ENTRY_IN, DEAL_ENTRY_OUT };
enum ENUM_DEAL_TYPE { DEAL_TYPE_BUY, DEAL_TYPE_SELL };
enum ENUM_INIT_RETCODE { INIT_SUCCEEDED = 0, INIT_FAILED = 1, INIT_PARAMETERS_INCORRECT = 32767 };
enum ENUM_FILE_POSITION { SEEK_SET, SEEK_CUR, SEEK_END };
const int REASON_REMOVE = 1, REASON_CHARTCLOSE = 4, REASON_ACCOUNT = 6, REASON_CLOSE = 9;
const uint TRADE_RETCODE_PLACED = 10008, TRADE_RETCODE_DONE = 10009, TRADE_RETCODE_DONE_PARTIAL = 10010,
           TRADE_RETCODE_NO_CHANGES = 10025;
const int FILE_READ = 1, FILE_WRITE = 2, FILE_BIN = 4, FILE_CSV = 8, FILE_ANSI = 32, FILE_SHARE_READ = 128,
          FILE_REWRITE = 512, FILE_COMMON = 4096, INVALID_HANDLE = -1;
const int COPY_TICKS_ALL = -1, COPY_TICKS_INFO = 1, WHOLE_ARRAY = -1, TIME_DATE = 1, TIME_MINUTES = 2, TIME_SECONDS = 4;
const uint CP_UTF8 = 65001;

struct MqlDateTime { int year, mon, day, hour, min, sec, day_of_week, day_of_year; };
struct MqlRates { datetime time; double open, high, low, close; long tick_volume; int spread; long real_volume; };
struct MqlTick { datetime time; double bid, ask, last; ulong volume; long time_msc; uint flags; double volume_real; };
enum ENUM_TRADE_REQUEST_ACTIONS { TRADE_ACTION_DEAL = 1, TRADE_ACTION_PENDING = 5, TRADE_ACTION_SLTP = 6, TRADE_ACTION_MODIFY = 7, TRADE_ACTION_REMOVE = 8 };
struct MqlTradeRequest { ENUM_TRADE_REQUEST_ACTIONS action; ulong magic, order; string symbol; double volume, price, stoplimit, sl, tp; };
struct MqlTradeResult { uint retcode; ulong deal, order; double volume, price, bid, ask; string comment; };
struct MqlTradeTransaction { ulong deal, order; string symbol; ENUM_TRADE_TRANSACTION_TYPE type; };

template <typename... A> void Print(A... a);
template <typename... A> void Alert(A... a);
template <typename... A> string StringFormat(const string format, A... a);
bool SendNotification(const string text);
int GetLastError();
datetime TimeLocal();
datetime TimeCurrent();
datetime TimeGMT();
datetime TimeTradeServer();
bool TimeToStruct(datetime dt, MqlDateTime &dt_struct);
datetime StructToTime(MqlDateTime &dt_struct);
string TimeToString(datetime value, int mode = TIME_DATE | TIME_MINUTES);
string DoubleToString(double value, int digits = 8);
string IntegerToString(long number, int str_len = 0, ushort fill_symbol = ' ');
template <typename E> string EnumToString(E value);
int StringReplace(string &str, const string find, const string replacement);
int StringLen(const string string_value);
string StringSubstr(const string string_value, int start_pos, int length = -1);
int StringFind(const string string_value, const string match_substring, int start_pos = 0);
int StringToCharArray(const string text_string, MqlArray<uchar> &array, int start = 0, int count = -1, uint codepage = 0);
// MQL5 also accepts char[] here (verified: forum 487425 code "char post[]" ... StringToCharArray(data, post, ...))
int StringToCharArray(const string text_string, MqlArray<char> &array, int start = 0, int count = -1, uint codepage = 0);
int WebRequest(const string method, const string url, const string headers, int timeout, const MqlArray<char> &data,
               MqlArray<char> &result, string &result_headers);
template <typename T> int ArraySize(const MqlArray<T> &array);
template <typename T> int ArrayResize(MqlArray<T> &array, int new_size, int reserve_size = 0);
template <typename T> bool ArrayRemove(MqlArray<T> &array, uint start, uint count = 0xFFFFFFFFu);
template <typename T> bool ArraySetAsSeries(const MqlArray<T> &array, bool flag);
template <typename T> void ZeroMemory(T &variable);
int MQLInfoInteger(ENUM_MQL_INFO_INTEGER property_id);
int TerminalInfoInteger(ENUM_TERMINAL_INFO_INTEGER property_id);
long AccountInfoInteger(ENUM_ACCOUNT_INFO_INTEGER property_id);
double AccountInfoDouble(ENUM_ACCOUNT_INFO_DOUBLE property_id);
long SymbolInfoInteger(const string name, ENUM_SYMBOL_INFO_INTEGER prop_id);
double SymbolInfoDouble(const string name, ENUM_SYMBOL_INFO_DOUBLE prop_id);
bool SymbolInfoTick(const string symbol, MqlTick &tick);
long SeriesInfoInteger(const string symbol_name, ENUM_TIMEFRAMES timeframe, ENUM_SERIES_INFO_INTEGER prop_id);
bool SeriesInfoInteger(const string symbol_name, ENUM_TIMEFRAMES timeframe, ENUM_SERIES_INFO_INTEGER prop_id, long &long_var);
int CopyRates(const string symbol_name, ENUM_TIMEFRAMES timeframe, int start_pos, int count, MqlArray<MqlRates> &rates_array);
int CopyRates(const string symbol_name, ENUM_TIMEFRAMES timeframe, datetime start_time, int count,
              MqlArray<MqlRates> &rates_array);
int CopyRates(const string symbol_name, ENUM_TIMEFRAMES timeframe, datetime start_time, datetime stop_time,
              MqlArray<MqlRates> &rates_array);
int CopyTicksRange(const string symbol_name, MqlArray<MqlTick> &ticks_array, uint flags = COPY_TICKS_ALL, ulong from_msc = 0,
                   ulong to_msc = 0);
datetime iTime(const string symbol, ENUM_TIMEFRAMES timeframe, int shift);
int FileOpen(const string file_name, int open_flags, short delimiter = '\t', uint codepage = 0);
void FileClose(int file_handle);
ulong FileSize(int file_handle);
bool FileSeek(int file_handle, long offset, ENUM_FILE_POSITION origin);
template <typename... A> uint FileWrite(int file_handle, A... a);
template <typename T> uint FileWriteStruct(int file_handle, const T &struct_object, int size = -1);
template <typename T> uint FileReadStruct(int file_handle, T &struct_object, int size = -1);
bool FileMove(const string src_file_name, int common_flag, const string dst_file_name, int mode_flags);
bool FileIsExist(const string file_name, int common_flag = 0);
bool FileDelete(const string file_name, int common_flag = 0);
bool FolderCreate(const string folder_name, int common_flag = 0);
double MathAbs(double value);
double MathCeil(double val);
double MathFloor(double val);
double MathLog10(double val);
double MathRound(double value);
template <typename A, typename B> auto MathMax(A value1, B value2) -> decltype(value1 + value2);
template <typename A, typename B> auto MathMin(A value1, B value2) -> decltype(value1 + value2);
double NormalizeDouble(double value, int digits);
int OrdersTotal();
ulong OrderGetTicket(int index);
long OrderGetInteger(ENUM_ORDER_PROPERTY_INTEGER property_id);
string OrderGetString(ENUM_ORDER_PROPERTY_STRING property_id);
int PositionsTotal();
ulong PositionGetTicket(int index);
bool PositionSelectByTicket(ulong ticket);
long PositionGetInteger(ENUM_POSITION_PROPERTY_INTEGER property_id);
double PositionGetDouble(ENUM_POSITION_PROPERTY_DOUBLE property_id);
string PositionGetString(ENUM_POSITION_PROPERTY_STRING property_id);
bool HistoryDealSelect(ulong ticket);
long HistoryDealGetInteger(ulong ticket_number, ENUM_DEAL_PROPERTY_INTEGER property_id);
double HistoryDealGetDouble(ulong ticket_number, ENUM_DEAL_PROPERTY_DOUBLE property_id);
string HistoryDealGetString(ulong ticket_number, ENUM_DEAL_PROPERTY_STRING property_id);
bool EventSetTimer(int seconds);
void EventKillTimer();

class CTrade   // public interface of Trade.mqh (Copyright 2000-2025) used by the EA, signatures verbatim
  {
public:
   uint   ResultRetcode(void) const;
   string ResultRetcodeDescription(void) const;
   double ResultPrice(void) const;
   void   SetExpertMagicNumber(const ulong magic);
   bool   PositionModify(const string symbol, const double sl, const double tp);
   bool   PositionModify(const ulong ticket, const double sl, const double tp);
   bool   PositionClose(const string symbol, const ulong deviation = ULONG_MAX);
   bool   PositionClose(const ulong ticket, const ulong deviation = ULONG_MAX);
   bool   OrderDelete(const ulong ticket);
   bool   Buy(const double volume, const string symbol = "", double price = 0.0, const double sl = 0.0, const double tp = 0.0,
              const string comment = "");
   bool   Sell(const double volume, const string symbol = "", double price = 0.0, const double sl = 0.0, const double tp = 0.0,
               const string comment = "");
   bool   BuyStop(const double volume, const double price, const string symbol = "", const double sl = 0.0, const double tp = 0.0,
                  const ENUM_ORDER_TYPE_TIME type_time = ORDER_TIME_GTC, const datetime expiration = 0, const string comment = "");
   bool   SellStop(const double volume, const double price, const string symbol = "", const double sl = 0.0, const double tp = 0.0,
                   const ENUM_ORDER_TYPE_TIME type_time = ORDER_TIME_GTC, const datetime expiration = 0, const string comment = "");
  };

bool OrderSendAsync(const MqlTradeRequest &request, MqlTradeResult &result);
bool IsStopped();
