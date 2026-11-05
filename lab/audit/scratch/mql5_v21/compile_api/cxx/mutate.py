"""Mutation test: each mutant must FAIL g++ -fsyntax-only, proving the shim harness catches that class of error."""
import subprocess, sys
base = open("ea.cpp").read()
muts = {
 "Journal arg count": ('Journal("EXIT", t_utc, g.side, price, g.stop, g.atr, R, why);', 'Journal("EXIT", t_utc, g.side, price, g.stop, g.atr, why);'),
 "struct member typo": ("g.br_trigger_sent = 1;", "g.br_trigger_send = 1;"),
 "BuyStop arg order (string for price)": ('g_trade.BuyStop(lots, hi, _Symbol,', 'g_trade.BuyStop(lots, _Symbol, hi,'),
 "undeclared id": ("g_tc = ToUTC(g.last_m1) + 60;", "g_tc = ToUTC(g.last_m1) + 60 + g_undefined;"),
 "use before decl (drop prototype)": ("void DeletePendings();   // declaration (definie plus bas)", "// removed prototype"),
 "CopyTicksRange arg order": ("CopyTicksRange(_Symbol, k, COPY_TICKS_INFO,", "CopyTicksRange(k, _Symbol, COPY_TICKS_INFO,"),
 "FileMove arg count": ("FileMove(tmp, FILE_COMMON, fn, FILE_COMMON | FILE_REWRITE)", "FileMove(tmp, fn, FILE_COMMON | FILE_REWRITE)"),
 "ArrayRemove on scalar": ("ArrayRemove(g_push, 0, 1);", "ArrayRemove(g_push_last, 0, 1);"),
 "SeriesInfoInteger wrong enum": ("SeriesInfoInteger(_Symbol, PERIOD_M5, SERIES_SYNCHRONIZED)", "SeriesInfoInteger(_Symbol, PERIOD_M5, TERMINAL_MAXBARS)"),
 "missing return value": ("   return k + 1;\n  }", "   return;\n  }"),
 "string+string literal": ('"until " + TimeToString(g.br_expiry_utc, TIME_DATE | TIME_MINUTES)', '"until " + "x"'),
 "Sent with 1 arg": ('Sent(g_trade.PositionClose(pos), "fermeture du 2e ordre OCO");', 'Sent(g_trade.PositionClose(pos));'),
 "brace removed": ("      g.side = 0;\n      g.br_active = 0;", "      g.side = 0;\n      {g.br_active = 0;"),
}
ok = True
for name, (a, b) in muts.items():
    if base.count(a) != 1:
        print("SKIP (pattern count", base.count(a), ")", name); ok = False; continue
    open("mut.cpp", "w").write(base.replace(a, b))
    r = subprocess.run(["g++", "-std=c++17", "-fsyntax-only", "mut.cpp"], capture_output=True, text=True)
    err = [l for l in r.stderr.splitlines() if "error" in l][:1]
    print(("CAUGHT " if r.returncode else "MISSED ") + name + " :: " + (err[0][:110] if err else ""))
    ok &= bool(r.returncode)
print("ALL CAUGHT" if ok else "SOME MISSED")
