//+------------------------------------------------------------------+
//| CR_Sizing.mqh - risk table, cushion multiplier, lots, the account |
//| checks in the lab's order (SPEC 5). Owner: I.                     |
//|                                                                  |
//| The lab's sizing (growth.py engine with the plan's key 1 and the  |
//| cushion_only stake rule, stake.py:166-192, account.py:95-115):    |
//|   rate(key)  pct of the last pair "from:pct" with from <= key,    |
//|              key = max(B, P_in) (growth.py:93-98, 118)             |
//|   unit       rate(max(B_w, P_in,w)) / 100 x B_w at the week's     |
//|              first ledger event (growth.py:274); w = robot close  |
//|              money of the week before S / unit (CR_Ledger)        |
//|   m          1 if w <= 0, else min(1, max(0.25, w / 4))            |
//|   lots       floor(B x rate x m x f / 100 / per_lot / step +      |
//|              1e-9) x step (growth.py:296), per_lot = r x          |
//|              tick_value_loss / tick_size; f = the stake factor of |
//|              a change while its switch is on (H2 0.750978,        |
//|              S0.75r 0.771793; g_sl rows of CR_Registry), else 1   |
//|   r (SPEC 4.2, P1)  quote_p = (quote + side x h) x (1 + side x    |
//|              sm), quote = ask (long) or bid (short), h = the      |
//|              paper half commission, sm = the lab's market slip;   |
//|              market: r = stop_dist, or side x (quote_p - stop)    |
//|              for an absolute stop; stop, limit, OCO (sent one bar |
//|              late): r = max(side x (paper fill - stop),           |
//|              side x (quote_p - stop)), late = 1                   |
//| Checks, in order (SPEC 5; the lab's order growth.py:291-309):     |
//|   NOTALLOWED (the caller's: the code is not in InpSleeves)        |
//|   SETTLE     the ledger moves: a wait, no line, nothing computed  |
//|   OBSERVE    plan unset on a real account, or the stamp is before |
//|              T                                                    |
//|   -- the week unit is set here (every sizing request sets it) --  |
//|   STOPPED, GUARD, LOCK   the history latches known at S           |
//|   the caller's reason    FRIDAY, CLOCK, NOTREADY, PREV_OPEN,      |
//|              NOTRADE ... (the follower puts it in it.skip)        |
//|   MIN_LOT    never rounded up (also: r <= 0 or B <= 0, why=...)    |
//|   CAP        6 robot positions, or 2 on the symbol, counting the  |
//|              positions closed with a stamp at or after S          |
//|   MARGIN     sum of OrderCalcMargin of those positions (at their  |
//|              open price) + the new one (at the quote) > B          |
//| Skips never touch the paper. Each call but SETTLE writes a SIZE   |
//| line: lots, want (lots before the checks), skip, B, P_in, rate,   |
//| m, f, unit, w, r, budget, late, quote (rp=1 in the replay).       |
//|                                                                  |
//| API (S0 signatures kept; the rest is new):                        |
//|   SizInit(err)                 parse g_cfg.risk_table; false =    |
//|                                ERROR at OnInit; copies the table  |
//|                                into the ledger (daily lock)       |
//|   SizParseTable(s, from, pct, n, err)   the parser itself: pairs  |
//|                                "from:pct" separated by ';' (one   |
//|                                ';' may end the list), plain       |
//|                                decimals, from[0] = 0, from        |
//|                                strictly increasing, pct in        |
//|                                (0, 10], at most 16 pairs (D2's    |
//|                                10 %; the notional and margin      |
//|                                checks stay)                       |
//|   SizRate(key)  SizM(w)  SizFactor(sl)  SizRisk(it)               |
//|   SizWeekUnit(S)               sets the week unit if the week has |
//|                                none; the follower calls it for a  |
//|                                MISSED reason=exited intent        |
//|   SizSize(it, S, dry)          lots and skip of an intent at      |
//|                                stamp S; on entry it.skip holds    |
//|                                the caller's reason (CR_SK_NONE if |
//|                                none); dry = the replay: no read   |
//|                                of the history, and only positions |
//|                                opened before the stamp's minute   |
//|                                count; returns it.skip             |
//|   SizSkipName(code)            journal name of a CR_SK_* code     |
//| CR_Registry is not included: it pulls the rule files in. The      |
//| stake factor is read from the g_sl row as RegStakeFactor does.    |
//+------------------------------------------------------------------+
#ifndef CR_SIZING_MQH
#define CR_SIZING_MQH
#include "CR_Types.mqh"
#include "CR_Ledger.mqh"

#define CR_SIZ_MAX_PAIRS 16             // pairs of InpRiskTable at most
#define CR_SIZ_PCT_MAX 10.0             // a rate above 10 % per trade is refused (SPEC 1: D2 starts at 10 %)
#define CR_SIZ_MAX_POS 6                // account.py LIMITS max_positions
#define CR_SIZ_MAX_SYM 2                // account.py LIMITS max_per_sym

double g_siz_from[];                   // the parsed InpRiskTable
double g_siz_pct[];
int    g_siz_n = 0;

string CR_SK_NAME[18] = {"none", "stopped", "guard", "lock", "friday", "clock", "notready", "observe", "settle", "prev_open",
                         "min_lot", "cap", "margin", "notallowed", "notrade", "late", "exited", "selftest"};

string SizSkipName(const int k)
  {
   if(k < 0 || k > 17) return "code" + IntegerToString(k);
   return CR_SK_NAME[k];
  }

// a plain decimal: digits with at most one '.', no sign, no exponent
bool SizNumber(const string s, double &v)
  {
   string t = s;
   StringTrimLeft(t);
   StringTrimRight(t);
   int len = StringLen(t);
   if(len == 0 || len > 24) return false;
   int digits = 0, dots = 0;
   for(int i = 0; i < len; i++)
     {
      int c = (int)StringGetCharacter(t, i);
      if(c >= '0' && c <= '9') digits++;
      else if(c == '.') dots++;
      else return false;
     }
   if(digits == 0 || dots > 1) return false;
   v = StringToDouble(t);
   return MathIsValidNumber(v);
  }

bool SizParseTable(const string s, double &from[], double &pct[], int &n, string &err)
  {
   n = 0;
   err = "";
   string t = s;
   StringTrimLeft(t);
   StringTrimRight(t);
   if(t == "")
     {
      err = "InpRiskTable is empty";
      return false;
     }
   string part[];
   int np = StringSplit(t, ';', part);
   if(np > 0)
     {
      string last = part[np - 1];
      StringTrimLeft(last);
      StringTrimRight(last);
      if(last == "") np--;                         // one ';' may end the list
     }
   if(np <= 0)
     {
      err = "InpRiskTable has no pair";
      return false;
     }
   if(np > CR_SIZ_MAX_PAIRS)
     {
      err = "InpRiskTable has more than 16 pairs";
      return false;
     }
   ArrayResize(from, np);
   ArrayResize(pct, np);
   for(int k = 0; k < np; k++)
     {
      string kv[];
      double f = 0.0, p = 0.0;
      if(StringSplit(part[k], ':', kv) != 2 || !SizNumber(kv[0], f) || !SizNumber(kv[1], p))
        {
         err = "InpRiskTable: '" + part[k] + "' is not a pair from:pct of plain numbers";
         return false;
        }
      if(k == 0 && f != 0.0)
        {
         err = "InpRiskTable must start with the pair 0:pct";
         return false;
        }
      if(k > 0 && !(f > from[k - 1]))
        {
         err = "InpRiskTable: the 'from' values must increase ('" + part[k] + "')";
         return false;
        }
      if(!(p > 0.0 && p <= CR_SIZ_PCT_MAX))
        {
         err = "InpRiskTable: a rate must be above 0 and at most 10 % ('" + part[k] + "')";
         return false;
        }
      from[k] = f;
      pct[k] = p;
     }
   n = np;
   return true;
  }

bool SizInit(string &err)
  {
   err = "";
   int n = 0;
   g_siz_n = 0;
   if(!SizParseTable(g_cfg.risk_table, g_siz_from, g_siz_pct, n, err)) return false;
   g_siz_n = n;
   LedSetRates(g_siz_from, g_siz_pct, n);
   return true;
  }

// pct of the last pair with from <= key (the table that SizInit gave the ledger)
double SizRate(const double key) { return LedRate(key); }

// the cushion_only stake rule (stake.py:166-192 with prot_k 4, prot_min 0.25)
double SizM(const double w)
  {
   if(w <= 0.0) return 1.0;
   double m = w / 4.0;
   if(m < 0.25) m = 0.25;
   if(m > 1.0) m = 1.0;
   return m;
  }

// the stake factor of a sleeve as resolved at OnInit (CR_Registry RegStakeFactor: off = 1)
double SizFactor(const int sl)
  {
   if(sl < 0 || sl >= g_nsl) return 1.0;
   return g_sl[sl].change_on ? g_sl[sl].factor_on : 1.0;
  }

// risk per unit for the sizing (SPEC 4.2, P1); sets it.late
double SizRisk(CrIntent &it)
  {
   int s = g_sl[it.sleeve].sym;
   double qp = (it.quote + it.side * g_sym[s].h) * (1.0 + it.side * g_sym[s].slip_mkt);
   if(it.etype == CR_ET_MARKET)
     {
      it.late = false;
      if(it.stop != 0.0) return it.side * (qp - it.stop);
      return it.stop_dist;
     }
   it.late = true;
   double st = (it.stop != 0.0) ? it.stop : it.paper_fill - it.side * it.stop_dist;
   double r1 = it.side * (it.paper_fill - st);
   double r2 = it.side * (qp - st);
   return (r2 > r1) ? r2 : r1;
  }

// the week unit of S's week, set at the week's first ledger event (growth.py:228-233, 274)
double SizWeekUnit(const datetime S)
  {
   double u = LedWeekUnit(S);
   if(u > 0.0) return u;
   datetime r = LedWeekRoll(S);
   double bw = LedBalance(r), pw = LedPaidIn(r);
   u = MathMax(SizRate(MathMax(bw, pw)) / 100.0 * bw, 1e-9);
   LedSetWeekUnit(S, u);
   return u;
  }

void SizLine(const CrIntent &it, const datetime S, const bool dry, const double want, const string why)
  {
   string kv = KI("oid", it.oid) + KI("side", it.side) + KI("et", it.etype) + KD("lots", it.lots) + KD("want", want)
               + KV("skip", SizSkipName(it.skip)) + KD("B", it.B) + KD("P_in", it.P_in) + KD("rate", it.rate) + KD("m", it.m)
               + KD("f", it.f) + KD("unit", it.unit) + KD("w", it.w) + KD("r", it.r) + KD("budget", it.budget)
               + KB("late", it.late) + KD("quote", it.quote);
   if(why != "") kv = kv + KV("why", why);
   JrnAt(S, CR_EV_SIZE, JrnCode(it.sleeve), kv + JrnRp(dry));
  }

int SizSize(CrIntent &it, const datetime S, const bool dry)
  {
   int pre = it.skip;
   it.skip = CR_SK_NONE;
   it.lots = 0.0;
   it.budget = 0.0;
   it.rate = 0.0;
   it.m = 0.0;
   it.B = 0.0;
   it.P_in = 0.0;
   it.unit = 0.0;
   it.w = 0.0;
   it.r = 0.0;
   it.late = (it.etype != CR_ET_MARKET);
   it.f = SizFactor(it.sleeve);
   if(it.sleeve < 0 || it.sleeve >= g_nsl)
     {
      it.skip = CR_SK_NOTREADY;
      JrnError("-", "SizSize: no sleeve row " + IntegerToString(it.sleeve));
      return it.skip;
     }
   if(pre == CR_SK_NOTALLOWED)
     {
      it.skip = pre;
      SizLine(it, S, dry, 0.0, "");
      return it.skip;
     }
   if(!dry) LedRead(TimeTradeServer());            // the latest history: a position opened a moment ago counts
   if(!LedSettled())
     {
      it.skip = CR_SK_SETTLE;                      // a wait inside the intent's window (SPEC 5): no line
      return it.skip;
     }
   if(LedPlanAt(S) != CR_PLAN_OK)
     {
      it.skip = CR_SK_OBSERVE;
      SizLine(it, S, dry, 0.0, "");
      return it.skip;
     }
   it.unit = SizWeekUnit(S);
   it.B = LedBalance(S);
   it.P_in = LedPaidIn(S);
   it.w = LedWeekW(S);
   it.m = SizM(it.w);
   it.rate = SizRate(MathMax(it.B, it.P_in));
   int g = CR_SK_NONE;
   if(LedStoppedAt(S)) g = CR_SK_STOPPED;
   else if(LedGuardAt(S)) g = CR_SK_GUARD;
   else if(LedDayLockedAt(S)) g = CR_SK_LOCK;
   else if(pre != CR_SK_NONE) g = pre;
   if(g != CR_SK_NONE)
     {
      it.skip = g;
      SizLine(it, S, dry, 0.0, "");
      return it.skip;
     }
   int s = g_sl[it.sleeve].sym;
   string nm = g_sym[s].name;
   it.r = SizRisk(it);
   double tvl = SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_VALUE_LOSS), ts = SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_SIZE);
   double step = SymbolInfoDouble(nm, SYMBOL_VOLUME_STEP), vmin = SymbolInfoDouble(nm, SYMBOL_VOLUME_MIN);
   if(!(tvl > 0.0) || !(ts > 0.0) || !(step > 0.0))
     {
      it.skip = CR_SK_NOTREADY;
      SizLine(it, S, dry, 0.0, "symbol");
      return it.skip;
     }
   if(!(it.r > 0.0) || !MathIsValidNumber(it.r))
     {
      it.skip = CR_SK_MIN_LOT;
      SizLine(it, S, dry, 0.0, "risk");
      return it.skip;
     }
   if(!(it.B > 0.0))
     {
      it.skip = CR_SK_MIN_LOT;
      SizLine(it, S, dry, 0.0, "balance");
      return it.skip;
     }
   double per_lot = it.r * (tvl / ts);
   it.budget = it.B * it.rate * it.m * it.f / 100.0;
   double lots = MathFloor(it.B * it.rate * it.m * it.f / 100.0 / per_lot / step + 1e-9) * step;
   if(lots < vmin)
     {
      it.skip = CR_SK_MIN_LOT;
      SizLine(it, S, dry, lots, "");
      return it.skip;
     }
   int nall = 0, nsym = 0;
   double used = 0.0;
   bool mok = true;
   int np = LedPosCount();
   CrLedPos p;
   for(int k = 0; k < np; k++)
     {
      if(!LedPosAt(k, p) || !p.robot) continue;
      if(dry && !(p.t_in < S)) continue;            // the replay: only positions opened before the stamp's minute
      if(p.closed && p.stamp < S) continue;          // booked before S: no longer open for the lab
      nall++;
      if(p.sym == s) nsym++;
      if(p.sym >= 0 && p.side != 0)
        {
         double mg = 0.0;
         if(OrderCalcMargin(p.side > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, g_sym[p.sym].name, p.vol_in, p.px_in, mg)) used += mg;
         else mok = false;
        }
     }
   if(nall >= CR_SIZ_MAX_POS || nsym >= CR_SIZ_MAX_SYM)
     {
      it.skip = CR_SK_CAP;
      SizLine(it, S, dry, lots, "n=" + IntegerToString(nall) + ",sym=" + IntegerToString(nsym));
      return it.skip;
     }
   double q = (it.quote > 0.0) ? it.quote : it.paper_fill;
   double mnew = 0.0;
   if(!mok || !(q > 0.0) || !OrderCalcMargin(it.side > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, nm, lots, q, mnew))
     {
      it.skip = CR_SK_MARGIN;
      SizLine(it, S, dry, lots, "calc");
      return it.skip;
     }
   if(used + mnew > it.B)
     {
      it.skip = CR_SK_MARGIN;
      SizLine(it, S, dry, lots, "");
      return it.skip;
     }
   it.lots = lots;
   SizLine(it, S, dry, lots, "");
   return it.skip;
  }
#endif
