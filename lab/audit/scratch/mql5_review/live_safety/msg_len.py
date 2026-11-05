# Reproduce the EA's StringFormat outputs with worst-case realistic values; check the 255-char push limit.
sym_list = ["XAUUSD", "XAUUSD.r", "XAUUSD.pro", "GOLD"]
for sym in sym_list:
    clocks = "2026.11.12 23:55 UTC / 00:55 Paris"
    entry = ("GoldOrb %s %s ~%s | stop %s (%.1f) | suiveur %.1f | sortie max %s | %s | REGLE NON VALIDEE EN REEL"
             % (sym, "CASSURE BAISSE: VENTE", "4012.35", "4103.95", 91.6, 91.6, clocks,
                "lot min 0.01 = 1.2% du capital (TROP RISQUE)"))
    trig = ("GoldOrb %s CASSURE %s maintenant (%s) | stop a %.1f du prix d'entree | %s"
            % (sym, "BAISSIERE : vente", "4012.35", 91.6, "lot min 0.01 = 1.2% du capital (TROP RISQUE)"))
    exitm = ("GoldOrb %s SORTIE %s (%s) %s a %s : %+.2f R | cumul %+.1f R / %d trades%s"
             % (sym, "vente", "suiveur", clocks, "4012.35", 3.21, 123.4, 1234, ""))
    lev = ("GoldOrb %s niveaux jusqu'a %s Paris : achat > %s | vente < %s | stop %.1f"
           % (sym, "16:00", "4123.45", "3987.65", 91.6))
    bind = ("GoldOrb : position #%d prise en charge (stop %.2f, suiveur %.1f, sortie %s)."
            % (1234567890, 4103.95, 91.6, clocks))
    skip = "GoldOrb : niveaux non places (lot min 0.01 = 1.2% du capital (TROP RISQUE)). Augmentez le capital ou baissez le risque."
    for name, m in [("ENTRY", entry), ("TRIGGER", trig), ("EXIT", exitm), ("LEVELS", lev), ("BIND", bind), ("SKIP", skip)]:
        cut = m if len(m) <= 255 else m[:252] + "..."
        flag = "  <-- TRUNCATED, push shows: ..." + cut[-40:] if len(m) > 255 else ""
        print(f"{sym:11s} {name:8s} {len(m):4d}{flag}")
    print()
