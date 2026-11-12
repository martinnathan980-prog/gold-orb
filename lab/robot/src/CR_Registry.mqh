//+------------------------------------------------------------------+
//| CR_Registry.mqh - symbol table, sleeve table, rule dispatch and   |
//| the change switches (SPEC 1, 2.3, 3.9). Owner: S0.                |
//|                                                                  |
//| Adding a rule = one rule file, one RegSleeve row below with its  |
//| case lines in the four Rules* functions, one reference entry in  |
//| check/ref_lab.py.                                                |
//+------------------------------------------------------------------+
#ifndef CR_REGISTRY_MQH
#define CR_REGISTRY_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Journal.mqh"
#include "CR_Rule_IdxUS.mqh"
#include "CR_Rule_Brk72.mqh"
#include "CR_Rule_F1.mqh"
#include "CR_Rule_NqBtc.mqh"
#include "CR_Rule_GoldFri.mqh"
#include "CR_Rule_Orb.mqh"
#include "CR_Rule_Donch.mqh"
#ifdef CR_HARNESS
#include "CR_Rule_Script.mqh"
#endif

// ---- one object per sleeve, by kind (no pointers: SPEC 1, MQL5 subset)
CRuleN30   g_r_n30;
CRuleOC4   g_r_oc4;
CRuleBrk72 g_r_brk[2];
CRuleF1    g_r_f1[2];
CRuleNqb   g_r_nqb;
CRuleGfp   g_r_gfp;
CRuleDonch g_r_d4h;
CRuleOrx   g_r_orx;
#ifdef CR_HARNESS
CRuleScript g_r_scr[CR_MAX_SL];
#endif

// ---- the frozen equal-swing stake factors (synthesis_A.json proposed_validation_look item 7; look_spec.json)
#define CR_FACTOR_H2 0.750978
#define CR_FACTOR_S075 0.771793

void RegSym(const int s, const string base, const string lab, const int family, const int comm_pts, const double slip_mkt_bps,
            const double slip_stop_bps, const int depth_days, const double model_bp)
  {
   g_sym[s].base = base;
   g_sym[s].lab = lab;
   g_sym[s].name = "";
   g_sym[s].family = family;
   g_sym[s].digits = 2;                         // read live at OnInit (CR_Main); 2 in the harness
   g_sym[s].point = 0.01;
   g_sym[s].comm_pts = comm_pts;
   g_sym[s].h = comm_pts * 0.5 * 0.01;
   g_sym[s].slip_mkt = slip_mkt_bps * 1e-4;
   g_sym[s].slip_stop = slip_stop_bps * 1e-4;
   g_sym[s].depth_days = depth_days;
   g_sym[s].model_bp = model_bp;
   g_sym[s].ok = false;
  }

void RegSleeve(const int id, const string code, const string lab, const int kind, const int slot, const int sym, const int sym2,
               const int change, const double factor_on, const int refuse_on)
  {
   int i = g_nsl;
   g_sl[i].id = id;
   g_sl[i].code = code;
   g_sl[i].lab = lab;
   g_sl[i].kind = kind;
   g_sl[i].slot = slot;
   g_sl[i].sym = sym;
   g_sl[i].sym2 = sym2;
   g_sl[i].change = change;
   g_sl[i].factor_on = factor_on;
   g_sl[i].refuse_on = refuse_on;
   g_sl[i].change_on = false;
   g_sl[i].allowed = true;
   g_sl[i].magic = CR_MAGIC_BASE + id;
   g_nsl++;
  }

// the static rows (no terminal call): symbols then sleeves (SPEC 2.3; slippage fp_costs.json; COST model bp SPEC 2.6)
void RegInit()
  {
   //     id      base      lab       family      commission       mkt  stop  depth  model bp
   RegSym(CR_XAU, "XAUUSD", "xauusd", CR_FAM_XAU, CR_XAU_COMM_PTS, 0.3, 1.0, 120, 0.47);
   RegSym(CR_IDX, "US100", "us100", CR_FAM_IDX, 0, 0.2, 0.5, 60, 0.37);
   RegSym(CR_BTC, "BTCUSD", "btcusd", CR_FAM_CRY, 0, 0.5, 1.5, 60, 2.96);
   RegSym(CR_ETH, "ETHUSD", "ethusd", CR_FAM_CRY, 0, 0.7, 2.0, 60, 13.0);
   g_nsl = 0;
   //        id code   lab sleeve (sort key)            kind        slot sym     sym2    change      factor          refusal
   RegSleeve(1, "N30", "noise30_us100", CR_K_N30, 0, CR_IDX, -1, CR_CH_NONE, 1.0, CR_REF_NONE);
   RegSleeve(2, "OC4", "ocm4_us100", CR_K_OC4, 0, CR_IDX, -1, CR_CH_NONE, 1.0, CR_REF_NONE);
   RegSleeve(3, "BKB", "brk72_24h_wd_btcusd", CR_K_BRK72, 0, CR_BTC, -1, CR_CH_S075, CR_FACTOR_S075, CR_REF_PAYOFF);
   RegSleeve(4, "BKE", "brk72_24h_wd_ethusd", CR_K_BRK72, 1, CR_ETH, -1, CR_CH_K1, 1.0, CR_REF_SB);
   RegSleeve(5, "F1B", "F1_brk_ridge_filter_btcusd", CR_K_F1, 0, CR_BTC, -1, CR_CH_NONE, 1.0, CR_REF_NONE);
   RegSleeve(6, "F1E", "F1_brk_ridge_filter_ethusd", CR_K_F1, 1, CR_ETH, -1, CR_CH_H2, CR_FACTOR_H2, CR_REF_PAYOFF);
   RegSleeve(7, "NQB", "nq_btc_follow_btcusd", CR_K_NQB, 0, CR_BTC, CR_IDX, CR_CH_NONE, 1.0, CR_REF_NONE);
   RegSleeve(8, "GFP", "GOLD_FRI_PM_xauusd", CR_K_GFP, 0, CR_XAU, -1, CR_CH_NONE, 1.0, CR_REF_NONE);
   RegSleeve(9, "D4H", "donch4h_stop_xauusd", CR_K_D4H, 0, CR_XAU, -1, CR_CH_NONE, 1.0, CR_REF_NONE);
   RegSleeve(10, "ORX", "orb_asia_2d_buf10_xauusd", CR_K_ORX, 0, CR_XAU, -1, CR_CH_NONE, 1.0, CR_REF_NONE);
  }

// the paper half commission once the symbol's point is known (SPEC 2.2: h = comm_pts / 2 x point)
void RegSetPoint(const int s, const int digits, const double point)
  {
   g_sym[s].digits = digits;
   g_sym[s].point = point;
   g_sym[s].h = g_sym[s].comm_pts * 0.5 * point;
  }

string RegChangeName(const int ch)
  {
   if(ch == CR_CH_K1) return "K1";
   if(ch == CR_CH_H2) return "H2";
   if(ch == CR_CH_S075) return "S0.75r";
   return "-";
  }

// SPEC 3.9: -1 = on for a demo or contest account, off for a real one; 0 = off; 1 = on. Resolved once at OnInit.
bool ChangeSwitchOn(const int sw) { return sw == 1 || (sw == -1 && g_cfg.demo); }

void ChangeOn()
  {
   for(int i = 0; i < g_nsl; i++)
     {
      int sw = 0;
      if(g_sl[i].change == CR_CH_K1) sw = g_cfg.k1;
      else if(g_sl[i].change == CR_CH_H2) sw = g_cfg.h2;
      else if(g_sl[i].change == CR_CH_S075) sw = g_cfg.s075;
      g_sl[i].change_on = (g_sl[i].change != CR_CH_NONE) && ChangeSwitchOn(sw);
      if(g_sl[i].change_on && !g_cfg.demo)
        {
         Jrn(CR_EV_INIT, g_sl[i].code, KV("change", RegChangeName(g_sl[i].change)) + KV("on_real", "1"));
         JrnPush("le changement " + RegChangeName(g_sl[i].change) + " est actif sur le compte REEL (" + g_sl[i].code + ")", true);
        }
     }
  }

// stake factor and refusal of a sleeve as resolved (off: the official rule, factor 1, no refusal)
double RegStakeFactor(const int sl) { return g_sl[sl].change_on ? g_sl[sl].factor_on : 1.0; }
int    RegRefuse(const int sl) { return g_sl[sl].change_on ? g_sl[sl].refuse_on : CR_REF_NONE; }

// InpSleeves: "ALL" or codes separated by commas; false on an unknown code
bool RegParseSleeves(const string s, string &err)
  {
   string t = s;
   StringTrimLeft(t);
   StringTrimRight(t);
   bool all = (t == "ALL" || t == "all");
   for(int i = 0; i < g_nsl; i++) g_sl[i].allowed = all;
   if(all) return true;
   if(t == "") return true;                     // nothing allowed: every sleeve is paper only
   string part[];
   int n = StringSplit(t, ',', part);
   for(int k = 0; k < n; k++)
     {
      string c = part[k];
      StringTrimLeft(c);
      StringTrimRight(c);
      int sl = CrSleeveOfCode(c);
      if(sl < 0)
        {
         err = "InpSleeves: unknown code '" + c + "'";
         return false;
        }
      g_sl[sl].allowed = true;
     }
   return true;
  }

#ifdef CR_HARNESS
// harness: the sleeves listed in g_cfg.script replay ref_lab.py's orders through CR_Rule_Script
bool RegApplyScript(string &err)
  {
   if(g_cfg.script == "") return true;
   string part[];
   int n = StringSplit(g_cfg.script, ',', part);
   for(int k = 0; k < n; k++)
     {
      int sl = CrSleeveOfCode(part[k]);
      if(sl < 0)
        {
         err = "InpScript: unknown code '" + part[k] + "'";
         return false;
        }
      g_sl[sl].kind = CR_K_SCRIPT;
      g_sl[sl].slot = sl;
     }
   return true;
  }
#endif

// the input checks of SPEC 1 that belong to the registry (switches, sleeves); false -> ERROR at OnInit
bool RegCheckInputs(string &err)
  {
   if(g_cfg.k1 < -1 || g_cfg.k1 > 1 || g_cfg.h2 < -1 || g_cfg.h2 > 1 || g_cfg.s075 < -1 || g_cfg.s075 > 1)
     {
      err = "InpK1, InpH2 and InpS075 must be -1, 0 or 1";
      return false;
     }
   if(!RegParseSleeves(g_cfg.sleeves, err)) return false;
#ifdef CR_HARNESS
   if(!RegApplyScript(err)) return false;
#endif
   return true;
  }

// ---- dispatch (one case per kind) -----------------------------------------------------------------------------------
// Init every rule object afresh (OnInit and every rebuild); false and err on a bad configuration (e.g. InpK1T)
bool RulesInit(string &err)
  {
   for(int sl = 0; sl < g_nsl; sl++)
     {
      bool ok = true;
      int k = g_sl[sl].slot;
      switch(g_sl[sl].kind)
        {
         case CR_K_N30: ok = g_r_n30.Init(sl); break;
         case CR_K_OC4: ok = g_r_oc4.Init(sl); break;
         case CR_K_BRK72: ok = g_r_brk[k].Init(sl); break;
         case CR_K_F1: ok = g_r_f1[k].Init(sl); break;
         case CR_K_NQB: ok = g_r_nqb.Init(sl); break;
         case CR_K_GFP: ok = g_r_gfp.Init(sl); break;
         case CR_K_D4H: ok = g_r_d4h.Init(sl); break;
         case CR_K_ORX: ok = g_r_orx.Init(sl); break;
#ifdef CR_HARNESS
         case CR_K_SCRIPT: ok = g_r_scr[k].Init(sl); break;
#endif
         default: ok = false;
        }
      if(!ok)
        {
         err = "rule " + g_sl[sl].code + ": Init refused its configuration";
         return false;
        }
     }
   return true;
  }

void RulesOnBar(const int sl, const int sym, const CrBar &b, CrOut &out)
  {
   int k = g_sl[sl].slot;
   switch(g_sl[sl].kind)
     {
      case CR_K_N30: g_r_n30.OnBar(sym, b, out); break;
      case CR_K_OC4: g_r_oc4.OnBar(sym, b, out); break;
      case CR_K_BRK72: g_r_brk[k].OnBar(sym, b, out); break;
      case CR_K_F1: g_r_f1[k].OnBar(sym, b, out); break;
      case CR_K_NQB: g_r_nqb.OnBar(sym, b, out); break;
      case CR_K_GFP: g_r_gfp.OnBar(sym, b, out); break;
      case CR_K_D4H: g_r_d4h.OnBar(sym, b, out); break;
      case CR_K_ORX: g_r_orx.OnBar(sym, b, out); break;
#ifdef CR_HARNESS
      case CR_K_SCRIPT: g_r_scr[k].OnBar(sym, b, out); break;
#endif
      default: break;
     }
  }

void RulesOnMinute(const int sl, const datetime M, CrOut &out)
  {
   int k = g_sl[sl].slot;
   switch(g_sl[sl].kind)
     {
      case CR_K_N30: g_r_n30.OnMinute(M, out); break;
      case CR_K_OC4: g_r_oc4.OnMinute(M, out); break;
      case CR_K_BRK72: g_r_brk[k].OnMinute(M, out); break;
      case CR_K_F1: g_r_f1[k].OnMinute(M, out); break;
      case CR_K_NQB: g_r_nqb.OnMinute(M, out); break;
      case CR_K_GFP: g_r_gfp.OnMinute(M, out); break;
      case CR_K_D4H: g_r_d4h.OnMinute(M, out); break;
      case CR_K_ORX: g_r_orx.OnMinute(M, out); break;
#ifdef CR_HARNESS
      case CR_K_SCRIPT: g_r_scr[k].OnMinute(M, out); break;
#endif
      default: break;
     }
  }

// SPEC 4.8 table: the latest time exit of a position opened at open_time (0 = unknown)
datetime RulesLatestExit(const int sl, const datetime open_time, const datetime comment_dec)
  {
   int k = g_sl[sl].slot;
   datetime x = 0;
   switch(g_sl[sl].kind)
     {
      case CR_K_N30: x = g_r_n30.LatestExit(open_time, comment_dec); break;
      case CR_K_OC4: x = g_r_oc4.LatestExit(open_time, comment_dec); break;
      case CR_K_BRK72: x = g_r_brk[k].LatestExit(open_time, comment_dec); break;
      case CR_K_F1: x = g_r_f1[k].LatestExit(open_time, comment_dec); break;
      case CR_K_NQB: x = g_r_nqb.LatestExit(open_time, comment_dec); break;
      case CR_K_GFP: x = g_r_gfp.LatestExit(open_time, comment_dec); break;
      case CR_K_D4H: x = g_r_d4h.LatestExit(open_time, comment_dec); break;
      case CR_K_ORX: x = g_r_orx.LatestExit(open_time, comment_dec); break;
#ifdef CR_HARNESS
      case CR_K_SCRIPT: x = g_r_scr[k].LatestExit(open_time, comment_dec); break;
#endif
      default: x = 0;
     }
   return x;
  }

// does sleeve sl read symbol sym (its traded symbol or its second one)?
bool RegReads(const int sl, const int sym) { return g_sl[sl].sym == sym || g_sl[sl].sym2 == sym; }
#endif
