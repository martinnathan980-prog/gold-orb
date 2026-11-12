//+------------------------------------------------------------------+
//| RobotJournal.mqh  -  one CSV journal for every rule module         |
//|                                                                  |
//| MQL5\Files\<name> (on the MetaQuotes VPS this file stays inside   |
//| the VPS sandbox: it is the offline replay's observation channel,  |
//| live the same lines also go to Print, i.e. the VPS journal).      |
//| Times are written as integer seconds (UTC unless said otherwise), |
//| prices with 17 significant digits (DoubleToString(x, -16)).       |
//+------------------------------------------------------------------+
#ifndef ROBOT_JOURNAL_MQH
#define ROBOT_JOURNAL_MQH

int  g_jrn = INVALID_HANDLE;
bool g_jrn_print = false;      // also Print every line (live)

bool JrnOpen(const string name, const bool append)
  {
   int flags = FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ;
   if(append) flags |= FILE_READ;
   g_jrn = FileOpen(name, flags);
   if(g_jrn == INVALID_HANDLE) return false;
   if(append) FileSeek(g_jrn, 0, SEEK_END);
   return true;
  }

void JrnClose()
  {
   if(g_jrn != INVALID_HANDLE) FileClose(g_jrn);
   g_jrn = INVALID_HANDLE;
  }

void JrnLine(const string line)
  {
   if(g_jrn != INVALID_HANDLE) FileWriteString(g_jrn, line + "\n");
   if(g_jrn_print) Print(line);
  }

string JrnT(const datetime t) { return IntegerToString((long)t); }
string JrnD(const double x)   { return DoubleToString(x, -16); }
#endif
