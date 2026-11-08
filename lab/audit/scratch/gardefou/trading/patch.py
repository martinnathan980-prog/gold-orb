"""Apply the trading-lens fixes to a scratch copy: python3 -I patch.py orig.mq5 fix.mq5"""
import sys

src = open(sys.argv[1], encoding="ascii").read()


def rep(old, new):
    global src
    n = src.count(old)
    assert n == 1, (n, old[:70])
    src = src.replace(old, new)


# D) filtres dans les regles persistees (assouplissement differe de 24 h)
rep("""   int               cooldown_h, max_pos, news_min, grace_s;
  };""", """   int               cooldown_h, max_pos, news_min, grace_s;
   uchar             syms[128], magics[64], ccys[64];   // filtres : tout changement attend 24 h
  };""")
rep("""   Rules r;
   r.max_risk = InpMaxRiskPct;""", """   Rules r;
   ZeroMemory(r);
   StringToCharArray(InpSymbols, r.syms, 0, 127);
   StringToCharArray(InpIgnoreMagics, r.magics, 0, 63);
   StringToCharArray(InpNewsCurrencies, r.ccys, 0, 63);
   r.max_risk = InpMaxRiskPct;""")
rep("""a.news_min == b.news_min && a.grace_s == b.grace_s;""",
    """a.news_min == b.news_min && a.grace_s == b.grace_s &&
          ArrayCompare(a.syms, b.syms) == 0 && ArrayCompare(a.magics, b.magics) == 0 && ArrayCompare(a.ccys, b.ccys) == 0;""")
rep("""   if(InList(InpIgnoreMagics, IntegerToString(magic))) return false;
   if(InpSymbols != "" && !InList(InpSymbols, sym)) return false;""",
    """   string syms = CharArrayToString(s.active.syms);
   if(InList(CharArrayToString(s.active.magics), IntegerToString(magic))) return false;
   if(syms != "" && !InList(syms, sym)) return false;""")

# C) limite du jour : drapeau du jour + re-essai de fermeture ; F) dernier id accepte
rep("""   double            day_start_eq;
""", """   double            day_start_eq;
   datetime          day_hit;           // jour (00:00) ou la limite a ete atteinte
   ulong             last_id;           // derniere position acceptee
   double            last_best;         // son stop le plus serre (p_best)
""")

# H) calendrier : n_loaded seulement apres succes, alerte si illisible
rep("""   if(n_loaded != 0 && now - n_loaded < 1800) return;
   n_loaded = now;
   ArrayResize(n_time, 0);""", """   if(n_loaded != 0 && now - n_loaded < 1800) return;
   n_loaded = now;
   string ccys = CharArrayToString(s.active.ccys);
   ArrayResize(n_time, 0);""")
rep("""   int nc = StringSplit(InpNewsCurrencies, ',', cur);""", """   int nc = StringSplit(ccys, ',', cur);""")
rep("""      if(!CalendarValueHistory(v, now - 3600, now + 2 * 86400, NULL, ccy)) continue;""",
    """      if(!CalendarValueHistory(v, now - 3600, now + 2 * 86400, NULL, ccy))
        {   // souvent 5401 au 1er appel (calendrier en chargement) : nouvel essai dans 1 min
         n_loaded = now - 1740;
         if(now - n_warned_cal > 6 * 3600) { n_warned_cal = now; Notify("GardeFou : calendrier economique illisible (" + IntegerToString(GetLastError()) + ") : blocage annonces inactif."); }
         continue;
        }""")
rep("""datetime n_warned = 0;
""", """datetime n_warned = 0;
datetime n_warned_cal = 0;
datetime g_fail = 0;   // dernier refus d'un ordre du garde-fou
""")

# G) anti-rafale : CloseTicket + TradeOk ; A) ClosePart netting
rep("""bool CloseTicket(const ulong ticket, const string why)
  {
   bool ok = g_trade.PositionClose(ticket);
   uint rc = g_trade.ResultRetcode();
   if(!ok || (rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_DONE_PARTIAL))
     {
      Notify("GardeFou : fermeture refusee (" + g_trade.ResultRetcodeDescription() + ") - " + why + ". Fermez la position vous-meme.");
      return false;
     }
   return true;
  }""", """bool TradeOk()
  {
   return TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && MQLInfoInteger(MQL_TRADE_ALLOWED) && TimeLocal() - g_fail >= 10;
  }

bool CloseTicket(const ulong ticket, const string why)
  {
   static ulong s_warned = 0;
   if(!PositionSelectByTicket(ticket)) return true;   // deja fermee
   bool ok = g_trade.PositionClose(ticket);
   uint rc = g_trade.ResultRetcode();
   if(!ok || (rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_DONE_PARTIAL))
     {
      g_fail = TimeLocal();
      string m = "GardeFou : fermeture refusee (" + g_trade.ResultRetcodeDescription() + ") - " + why + ". Fermez la position vous-meme.";
      if(s_warned != ticket) { s_warned = ticket; Notify(m); }
      else Print(m);
      return false;
     }
   return true;
  }

// fermeture partielle : CTrade::PositionClosePartial ne marche qu'en hedging (Trade.mqh : "for hedging mode only")
bool ClosePart(const ulong ticket, const double vol)
  {
   if(!PositionSelectByTicket(ticket)) return false;
   g_trade.SetMarginMode();   // CTrade lit le mode une seule fois, a la construction (compte parfois pas encore charge)
   if(AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
      return g_trade.PositionClosePartial(ticket, vol);
   string sym = PositionGetString(POSITION_SYMBOL);
   double v = MathMin(vol, PositionGetDouble(POSITION_VOLUME));
   bool buy = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY);
   return buy ? g_trade.Sell(v, sym) : g_trade.Buy(v, sym);   // netting : ordre oppose plus petit = reduction
  }""")

# F) OnNewPosition : heure d'ouverture serveur, reprise des positions deja acceptees
rep("""   datetime now = TimeTradeServer();
   string why = "";
   string news;
   if(s.blocked_until > now) why = BlockText();
   else if(ManagedCount(id) >= s.active.max_pos) why = "une position a la fois";
   else if(NewsNear(now, news)) why = "annonce forte : " + news;""",
    """   datetime now = TimeTradeServer();
   datetime pt = (datetime)PositionGetInteger(POSITION_TIME);   // heure serveur d'ouverture
   if(pt < s.last_entry || (id == s.last_id && pt == s.last_entry))
     {   // deja acceptee (redemarrage, resynchro) : reprise sans fermeture ni delai de grace
      AddPos(id, side, sl);
      p_open[ArraySize(p_open) - 1] = now - 3600;
      if(id == s.last_id && s.last_best != 0.0)   // stop elargi pendant l'arret : la boucle le remettra
         p_best[ArraySize(p_best) - 1] = (sl == 0.0) ? s.last_best : (side > 0 ? MathMax(sl, s.last_best) : MathMin(sl, s.last_best));
      return;
     }
   string why = "";
   string news;
   if(s.blocked_until > pt) why = BlockText();
   else if(ManagedCount(id) >= s.active.max_pos) why = "une position a la fois";
   else if(NewsNear(pt, news)) why = "annonce forte : " + news;""")
rep("""   s.last_entry = now;
   Block(now + s.active.cooldown_h * 3600, 1);""", """   s.last_entry = pt;
   s.last_id = id;
   s.last_best = sl;
   Block(pt + s.active.cooldown_h * 3600, 1);""")

# G) re-essai bloque
rep("""      static datetime s_retry = 0;   // position bloquee dont la fermeture a echoue : nouvel essai toutes les 10 s
      if(TimeLocal() - s_retry >= 10) { s_retry = TimeLocal(); CloseTicket(ticket, "position ouverte pendant un blocage"); }""",
    """      if(TradeOk()) CloseTicket(ticket, "position ouverte pendant un blocage");   // au plus toutes les 10 s apres un refus""")
rep("""      if(in_grace) return;
      double want""", """      if(in_grace || !TradeOk()) return;
      double want""")

# B) + A) : stop "ne s'eloigne pas" AVANT le controle du risque ; reduction via ClosePart
old_risk_start = src.index("   // 2) risque trop grand (taille ou stop trop loin) : on reduit la taille")
old_stop_start = src.index("   // 3) le stop ne peut que se rapprocher (apres le delai de grace)")
old_stop_end = src.index("   if((side > 0 && sl > p_best[i]) || (side < 0 && sl < p_best[i])) p_best[i] = sl;   // stop resserre : nouvelle reference\n")
end_line = "   if((side > 0 && sl > p_best[i]) || (side < 0 && sl < p_best[i])) p_best[i] = sl;   // stop resserre : nouvelle reference\n"
risk_block = src[old_risk_start:old_stop_start]
stop_block = src[old_stop_start:old_stop_end] + end_line
risk_block = risk_block.replace("   // 2) risque trop grand (taille ou stop trop loin) : on reduit la taille",
                                "   // 3) risque trop grand (taille, ou stop choisi pendant la grace) : on reduit la taille")
risk_block = risk_block.replace("if(!in_grace && beyond_entry && risk > max_money * 1.02)\n     {",
                                "if(beyond_entry && risk > max_money * 1.02)\n     {\n      if(!TradeOk()) return;")
risk_block = risk_block.replace("g_trade.PositionClosePartial(ticket, cut)", "ClosePart(ticket, cut)")
stop_block = stop_block.replace("   // 3) le stop ne peut que se rapprocher (apres le delai de grace)",
                                "   // 2) le stop ne peut que se rapprocher (apres le delai de grace) - AVANT le controle du risque")
stop_block = stop_block.replace("      double back = p_best[i];\n", "      if(!TradeOk()) return;\n      double back = p_best[i];\n")
stop_block = stop_block.replace(end_line, "   if((side > 0 && sl > p_best[i]) || (side < 0 && sl < p_best[i]))\n     {   // stop resserre : nouvelle reference (persistee)\n      p_best[i] = sl;\n      if(id == s.last_id) { s.last_best = sl; SaveState(); }\n     }\n")
src = src[:old_risk_start] + stop_block + risk_block + src[old_stop_end + len(end_line):]

# C) limite du jour
rep("""   if(s.day_start_eq > 0 && eq <= s.day_start_eq * (1.0 - s.active.daily_loss / 100.0) && s.block_reason != 3)
     {
      Block(dk + 86400, 3);
      s.blocked_until = dk + 86400;
      s.block_reason = 3;
      Journal("DAILY_LIMIT", "", 0, eq, StringFormat("start %.2f", s.day_start_eq));
      CloseAllManaged("limite de perte du jour");
      Notify(""", """   if(s.day_hit != dk && s.day_start_eq > 0 && eq <= s.day_start_eq * (1.0 - s.active.daily_loss / 100.0))
     {
      s.day_hit = dk;
      Block(dk + 86400, 3);   // ne raccourcit jamais une pause plus longue
      Journal("DAILY_LIMIT", "", 0, eq, StringFormat("start %.2f", s.day_start_eq));
      Notify(""")
rep("""                          s.active.daily_loss, DayHm(s.blocked_until)));
      SaveState();
     }""", """                          s.active.daily_loss, DayHm(s.blocked_until)));
      SaveState();
     }
   static datetime s_dl = 0;
   if(s.day_hit == dk && TradeOk() && TimeLocal() - s_dl >= 5) { s_dl = TimeLocal(); CloseAllManaged("limite de perte du jour"); }   // jusqu'a etre a plat""")

# F) AccountReady : reprise via OnNewPosition si etat recharge
rep("""      ulong id = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
      if(FindPos(id) >= 0) continue;
      AddPos(id, (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1, PositionGetDouble(POSITION_SL));
      p_open[ArraySize(p_open) - 1] = TimeTradeServer() - 3600;   // pas de delai de grace pour elles""",
    """      ulong id = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
      if(FindPos(id) >= 0 || WasBlocked(id)) continue;   // bloquee (re-init) : la boucle la referme
      if(had) { OnNewPosition(t); continue; }            // connue -> reprise ; ouverte pendant l'arret -> regles a son heure
      datetime pt = (datetime)PositionGetInteger(POSITION_TIME);
      AddPos(id, (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1, PositionGetDouble(POSITION_SL));
      p_open[ArraySize(p_open) - 1] = TimeTradeServer() - 3600;   // pas de delai de grace pour elles
      if(pt >= s.last_entry) { s.last_entry = pt; s.last_id = id; }""")
rep("""   g_ready = true;
   for(int i = PositionsTotal() - 1; i >= 0; i--)""", """   g_ready = true;
   LoadNews();
   for(int i = PositionsTotal() - 1; i >= 0; i--)""")

# E) fills partiels ; I) ticket via identifiant ; A) ClosePart
rep("""// reaction immediate aux executions : nouvelle position, ajout, sortie""",
    """// ticket de la position d'identifiant id (en netting, le ticket change apres un retournement) ; 0 si fermee
ulong TicketOf(const ulong id)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t != 0 && PositionSelectByTicket(t) && (ulong)PositionGetInteger(POSITION_IDENTIFIER) == id) return t;
     }
   return 0;
  }

// reaction immediate aux executions : nouvelle position, ajout, sortie""")
rep("""      bool exists = PositionSelectByTicket(pid);
      bool is_add = exists && PositionGetDouble(POSITION_VOLUME) > add + 1e-8;   // volume deja present avant ce deal""",
    """      bool fill = ((ulong)HistoryDealGetInteger(trans.deal, DEAL_ORDER) == pid);   // fill partiel de l'ordre d'ouverture
      ulong tk = TicketOf(pid);
      bool exists = (tk != 0);
      bool is_add = exists && !fill && PositionGetDouble(POSITION_VOLUME) > add + 1e-8;""")
rep("""         if(g_trade.PositionClosePartial(pid, add))""", """         if(ClosePart(tk, add))""")
rep("""      if(exists && !WasBlocked(pid)) OnNewPosition(pid);""", """      if(exists && !WasBlocked(pid)) OnNewPosition(tk);""")
rep("""      bool closed = !PositionSelectByTicket(pid);""", """      bool closed = (TicketOf(pid) == 0);""")

open(sys.argv[2], "w", encoding="ascii").write(src)
print("ok")
