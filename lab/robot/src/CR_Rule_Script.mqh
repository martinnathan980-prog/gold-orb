//+------------------------------------------------------------------+
//| CR_Rule_Script.mqh - harness-only rule (CR_HARNESS). Owner: S0.   |
//|                                                                  |
//| Replays a file of lab orders written by check/ref_lab.py: each   |
//| row is a CrOrder and the barrier minute at which it is emitted.  |
//| A sleeve listed in the harness input InpScript gets this rule in |
//| place of its own (step J tests the execution with it, SPEC 8).   |
//| File MQL5/Files/<InpScriptDir>/<code>.csv, a header line, then   |
//| emit,oid,side,etype,level,level2,t_from,t_to,after_exit_of,      |
//| expiry_excl,stop,stop_dist,trail,be,target,target_dist,x_sched,  |
//| x_gap,xh,xh_r,refuse,void_le,dec,group                           |
//| (UTC seconds; doubles with 17 significant digits; rows sorted by |
//| emit). An order whose emit minute lies before the first barrier  |
//| the driver processes is history and is not emitted.             |
//+------------------------------------------------------------------+
#ifndef CR_RULE_SCRIPT_MQH
#define CR_RULE_SCRIPT_MQH
#include "CR_Types.mqh"
#include "CR_Journal.mqh"

#define CR_SCRIPT_COLS 24

class CRuleScript
  {
public:
   int      sl;
   CrOrder  m_ord[];
   datetime m_emit[];
   int      m_n;
   int      m_next;
   bool     m_loaded;

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_n = 0;
      m_next = 0;
      m_loaded = false;
      ArrayResize(m_ord, 0, 1024);
      ArrayResize(m_emit, 0, 1024);
      string path = g_cfg.script_dir + "\\" + g_sl[sl].code + ".csv";
      int h = FileOpen(path, FILE_READ | FILE_TXT | FILE_ANSI | FILE_SHARE_READ);
      if(h == INVALID_HANDLE)
        {
         JrnError(g_sl[sl].code, "script file missing: " + path);
         return false;
        }
      FileReadString(h);                         // the header line
      string f[];
      while(!FileIsEnding(h))
        {
         string line = FileReadString(h);
         if(StringLen(line) < 10) continue;
         int k = StringSplit(line, ',', f);
         if(k != CR_SCRIPT_COLS)
           {
            FileClose(h);
            JrnError(g_sl[sl].code, "script row with " + IntegerToString(k) + " fields");
            return false;
           }
         CrOrder o;
         CrOrderClear(o);
         o.sleeve = sl;
         o.oid = StringToInteger(f[1]);
         o.side = (int)StringToInteger(f[2]);
         o.etype = (int)StringToInteger(f[3]);
         o.level = StringToDouble(f[4]);
         o.level2 = StringToDouble(f[5]);
         o.t_from = (datetime)StringToInteger(f[6]);
         o.t_to = (datetime)StringToInteger(f[7]);
         o.after_exit_of = StringToInteger(f[8]);
         o.expiry_excl = (datetime)StringToInteger(f[9]);
         o.stop = StringToDouble(f[10]);
         o.stop_dist = StringToDouble(f[11]);
         o.trail = StringToDouble(f[12]);
         o.be = StringToDouble(f[13]);
         o.target = StringToDouble(f[14]);
         o.target_dist = StringToDouble(f[15]);
         o.x_sched = (datetime)StringToInteger(f[16]);
         o.x_gap = StringToInteger(f[17]) != 0;
         o.xh = (datetime)StringToInteger(f[18]);
         o.xh_r = StringToDouble(f[19]);
         o.refuse = (int)StringToInteger(f[20]);
         o.void_le = StringToInteger(f[21]) != 0;
         o.dec = (datetime)StringToInteger(f[22]);
         o.grp = (int)StringToInteger(f[23]);
         ArrayResize(m_ord, m_n + 1, 1024);
         ArrayResize(m_emit, m_n + 1, 1024);
         m_ord[m_n] = o;
         m_emit[m_n] = (datetime)StringToInteger(f[0]);
         m_n++;
        }
      FileClose(h);
      m_loaded = true;
      return true;
     }

   void OnBar(const int sym, const CrBar &b, CrOut &out) {}

   void OnMinute(const datetime M, CrOut &out)
     {
      while(m_next < m_n && m_emit[m_next] <= M)
        {
         if(m_emit[m_next] == M && !CrOutOrder(out, m_ord[m_next]))
            JrnError(g_sl[sl].code, "script: more than CR_OUT_MAX orders at " + IntegerToString((long)M));
         m_next++;
        }
     }

   // the scheduled exit of the order whose activation matches the position's open time (0 when unknown)
   datetime LatestExit(const datetime open_time, const datetime comment_dec)
     {
      for(int i = m_n - 1; i >= 0; i--)
         if(m_ord[i].t_from <= open_time && open_time <= m_ord[i].t_to + 300) return m_ord[i].x_sched;
      return 0;
     }
  };
#endif
