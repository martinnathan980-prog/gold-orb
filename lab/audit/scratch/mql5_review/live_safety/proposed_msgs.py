# Lengths of the PROPOSED replacement texts (worst case: long symbol, over-risk lot message, EUR account)
sym = "XAUUSD.pro"
clk = "jeu. 13/11 00:55 Paris (23:55 UTC)"            # proposed Clocks()
lot = "lot min 0.01 = 92 EUR = 1.2% du capital (TROP RISQUE)"
msgs = {
 "ENTRY": "GoldOrb %s VENTE (cassure baisse) ~%s | STOP %s (%.1f $) | suiveur %.1f $ du meilleur prix | sortie max %s | %s | regle non validee en reel"
          % (sym, "4012.35", "4103.95", 91.6, 91.6, clk, lot),
 "TRIGGER": "GoldOrb %s CASSURE BAISSIERE : vente maintenant ~%s | stop ~%s (%.1f $) | sortie max %s | %s"
          % (sym, "4012.35", "4103.95", 91.6, clk, lot),
 "EXIT": "GoldOrb %s FERMEZ la vente : %s touche a %s (%s) : %+.2f R | cumul %+.1f R / %d trades"
          % (sym, "stop suiveur", "4012.35", clk, 3.21, 123.4, 1234),
 "SKIP": "GoldOrb %s : ordres NON places : lot min %.2f = %.1f%% du capital au stop (limite %.2f%%). Capital trop faible ; relevez InpRiskPct ou InpMaxRiskMult seulement si vous acceptez ce risque."
          % (sym, 0.01, 1.2, 0.75),
 "REPLAY": "GoldOrb %s : redemarrage, %d bougies M1 rattrapees (%s -> %s). Position fictive : VENTE ~%s, stop %s, sortie max %s | trades pendant la coupure : %d (%+.2f R)"
          % (sym, 4321, "11.11 08:02", "13.11 08:05", "4012.35", "4050.10", clk, 2, -1.37),
 "SL_FAIL": "GoldOrb %s : STOP NON POSE sur #%d (%s). Posez-le vous-meme a %s MAINTENANT."
          % (sym, 1234567890, "AutoTrading disabled by client", "4103.95"),
}
for k, m in msgs.items():
    print(f"{k:8s} {len(m):4d} {'OK' if len(m) <= 255 else 'TOO LONG'}")
