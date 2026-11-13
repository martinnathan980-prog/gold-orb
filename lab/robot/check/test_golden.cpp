// T10 golden: the self-test vectors of src/CR_Golden.mqh (tools/gen_golden.py) run by the shipped single file
// build: entry=dist/ClaudeRobot.mq5 sanitize
//
// What it checks (SPEC 7 T10; step K). The entry is dist/ClaudeRobot.mq5, the file the user installs, translated by
// check/to_cpp.py (harness build: CR_HARNESS, CR_XAU_COMM_PTS=0, as every replay), with the sanitizer:
//   1. GoldenCheck passes on the vectors as generated (CR_GOLDEN_N of them), and leaves the live risk table as it was
//      (InpRiskTable F1S here, so that a forgotten restore shows);
//   2. one vector of each kind, changed by more than its tolerance, makes GoldenCheck fail and name that vector
//      (clock, NYSE, AddTradingDays, BusinessDays, ORX exit, F1 score, riskbp, risk table rate, risk table text,
//      Wilder value, Wilder NaN, SMA value, SMA NaN); each change is undone and the check passes again;
//   3. a double changed by less than its tolerance (1e-14 relative on an F1 score and a Wilder value) still passes:
//      the tolerance is SPEC 7's 1e-12, not exact equality;
//   4. speed: GoldenCheck repeated 200 times, the mean time per call (it runs once at OnInit).
// The build-constant part of T10 (a build without CR_HARNESS refuses CR_NO_GUARD and CR_XAU_COMM_PTS other than 6,
// and a failed self-test blocks trading) is check/test_release.py's: it needs builds without CR_HARNESS.
// Exit 0 when every check holds; one line per check, then "N checks, F failed".
#include "mock_replay.h"
// the whole EA comes with its own handlers; the mock (MOCK_REPLAY_NO_MAIN) has weak ones: the EA's are renamed
#define OnInit ea_OnInit
#define OnDeinit ea_OnDeinit
#define OnTick ea_OnTick
#define OnTimer ea_OnTimer
#define OnTradeTransaction ea_OnTradeTransaction
#include "ea.cpp"
#undef OnInit
#undef OnDeinit
#undef OnTick
#undef OnTimer
#undef OnTradeTransaction
#include <chrono>
#include <cstdio>
#include <string>

static int g_checks = 0, g_failed = 0;

static void check(bool ok, const std::string &what, const std::string &info = "")
  {
   g_checks++;
   if(!ok) g_failed++;
   printf("%s %s%s%s\n", ok ? "PASS" : "FAIL", what.c_str(), info.empty() ? "" : " | ", info.c_str());
  }

// GoldenCheck must fail and its message must start with "golden <kind> <k>:"
static void expect_fail(const std::string &kind, int k)
  {
   string why = "";
   bool ok = GoldenCheck(why);
   std::string want = "golden " + kind + " " + std::to_string(k) + ":";
   check(!ok && why.rfind(want, 0) == 0, "a changed " + kind + " vector " + std::to_string(k) + " is refused", why);
  }

static void expect_pass(const std::string &what)
  {
   string why = "";
   bool ok = GoldenCheck(why);
   check(ok && why == "", what, why);
  }

int main()
  {
   string err = "";
   check(ClkInit("", err), "ClkInit", err);
   g_cfg.risk_table = "0:1;12000:0.5";                     // F1S as the live table: GoldenCheck must give it back
   check(SizInit(err), "SizInit F1S", err);
   double before5k = LedRate(5000.0), before20k = LedRate(20000.0);

   // 1. as generated
   expect_pass("GoldenCheck passes on the generated vectors");
   check(CR_GOLDEN_N == CR_GOLD_NCLK + CR_GOLD_NNYSE + CR_GOLD_NATD + CR_GOLD_NBDAY + CR_GOLD_NORX + CR_GOLD_NF1 + CR_GOLD_NRBP
                           + CR_GOLD_NRISK * (CR_GOLD_NKEY + 1) + 2 * CR_GOLD_NSER,
         "CR_GOLDEN_N counts every vector", std::to_string(CR_GOLDEN_N));
   check(CR_GOLD_NCLK == 60 && CR_GOLD_NNYSE == 40 && CR_GOLD_NATD == 20 && CR_GOLD_NBDAY == 20 && CR_GOLD_NF1 == 30
         && CR_GOLD_NRBP == 10 && CR_GOLD_NRISK == 3, "SPEC 7 T10 sizes: 60 clock, 40 NYSE, 20 + 20 days, 30 F1, 10 riskbp, 3 tables");
   check(LedRate(5000.0) == before5k && LedRate(20000.0) == before20k && before5k == 1.0 && before20k == 0.5,
         "the live risk table (F1S) is put back", std::to_string(LedRate(5000.0)) + " " + std::to_string(LedRate(20000.0)));

   // 2. one vector of each kind, beyond its tolerance
   long l0 = CR_GOLD_CLK[7 * 13 + 1];
   CR_GOLD_CLK[7 * 13 + 1] = l0 + 1;
   expect_fail("clock", 13);
   CR_GOLD_CLK[7 * 13 + 1] = l0;
   l0 = CR_GOLD_CLK[7 * 7 + 4];                             // the server clock back to UTC in the repeated autumn hour
   CR_GOLD_CLK[7 * 7 + 4] = l0 + 3600;
   expect_fail("clock", 7);
   CR_GOLD_CLK[7 * 7 + 4] = l0;
   l0 = CR_GOLD_CLK[7 * 20 + 6];
   CR_GOLD_CLK[7 * 20 + 6] = 1 - l0;
   expect_fail("clock", 20);
   CR_GOLD_CLK[7 * 20 + 6] = l0;
   l0 = CR_GOLD_NYSE[2 * 9 + 1];
   CR_GOLD_NYSE[2 * 9 + 1] = (l0 + 1) % 3;
   expect_fail("nyse", 9);
   CR_GOLD_NYSE[2 * 9 + 1] = l0;
   l0 = CR_GOLD_ATD[3 * 4 + 2];
   CR_GOLD_ATD[3 * 4 + 2] = l0 + 60;
   expect_fail("add_trading_days", 4);
   CR_GOLD_ATD[3 * 4 + 2] = l0;
   l0 = CR_GOLD_BDAY[3 * 11 + 2];
   CR_GOLD_BDAY[3 * 11 + 2] = l0 - 86400;
   expect_fail("business_days", 11);
   CR_GOLD_BDAY[3 * 11 + 2] = l0;
   l0 = CR_GOLD_ORX[2 * 3 + 1];
   CR_GOLD_ORX[2 * 3 + 1] = l0 + 3600;
   expect_fail("orx_exit", 3);
   CR_GOLD_ORX[2 * 3 + 1] = l0;
   int sb = (CR_F1_NFEAT + 1) * 17 + CR_F1_NFEAT;
   double d0 = CR_GOLD_F1[sb];
   CR_GOLD_F1[sb] = d0 * (1.0 + 1e-9);
   expect_fail("f1_score", 17);
   CR_GOLD_F1[sb] = d0;
   int fb = (CR_F1_NFEAT + 1) * 26 + 13;                    // a feature (the hour of a made-up vector): its dummy moves
   d0 = CR_GOLD_F1[fb];
   CR_GOLD_F1[fb] = d0 + 3.0;
   expect_fail("f1_score", 26);
   CR_GOLD_F1[fb] = d0;
   d0 = CR_GOLD_RBP[3 * 6 + 2];
   CR_GOLD_RBP[3 * 6 + 2] = d0 * (1.0 + 1e-9);
   expect_fail("riskbp", 6);
   CR_GOLD_RBP[3 * 6 + 2] = d0;
   d0 = CR_GOLD_RISK[1 * CR_GOLD_NKEY + 6];
   CR_GOLD_RISK[1 * CR_GOLD_NKEY + 6] = d0 + 0.5;
   expect_fail("risk_table", 1);
   CR_GOLD_RISK[1 * CR_GOLD_NKEY + 6] = d0;
   string t0 = CR_GOLD_RISK_TXT[2];
   CR_GOLD_RISK_TXT[2] = "0:1;12000";
   expect_fail("risk_table", 2);
   CR_GOLD_RISK_TXT[2] = t0;
   check(LedRate(5000.0) == before5k && LedRate(20000.0) == before20k, "the live risk table is put back after a failed table too");
   d0 = CR_GOLD_WIL[30];
   CR_GOLD_WIL[30] = d0 * (1.0 + 1e-9);
   expect_fail("wilder", 30);
   CR_GOLD_WIL[30] = d0;
   int n0 = CR_GOLD_WIL_NAN[0];
   CR_GOLD_WIL_NAN[0] = 1 - n0;
   expect_fail("wilder", 0);
   CR_GOLD_WIL_NAN[0] = n0;
   d0 = CR_GOLD_SMA[44];
   CR_GOLD_SMA[44] = d0 * (1.0 + 1e-9);
   expect_fail("sma", 44);
   CR_GOLD_SMA[44] = d0;
   int k_nan = -1;
   for(int k = 0; k < CR_GOLD_NSER && k_nan < 0; k++)
      if(CR_GOLD_SMA_NAN[k] != 0 && k > 0) k_nan = k;
   n0 = CR_GOLD_SMA_NAN[k_nan];
   CR_GOLD_SMA_NAN[k_nan] = 1 - n0;
   expect_fail("sma", k_nan);
   CR_GOLD_SMA_NAN[k_nan] = n0;
   expect_pass("every change undone: GoldenCheck passes again");

   // 3. inside the tolerance
   d0 = CR_GOLD_F1[sb];
   CR_GOLD_F1[sb] = d0 * (1.0 + 1e-14);
   double d1 = CR_GOLD_WIL[30];
   CR_GOLD_WIL[30] = d1 * (1.0 + 1e-14);
   expect_pass("a change of 1e-14 relative (an F1 score, a Wilder value) is inside SPEC 7's 1e-12");
   CR_GOLD_F1[sb] = d0;
   CR_GOLD_WIL[30] = d1;

   // 4. speed
   auto t_a = std::chrono::steady_clock::now();
   bool all = true;
   for(int i = 0; i < 200; i++)
     {
      string why = "";
      all = all && GoldenCheck(why);
     }
   double us = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - t_a).count() / 200.0;
   char buf[64];
   snprintf(buf, sizeof(buf), "%.1f us per call", us);
   check(all && us < 50000.0, "GoldenCheck 200 times", buf);
   printf("%d checks, %d failed\n", g_checks, g_failed);
   return g_failed == 0 ? 0 : 1;
  }
