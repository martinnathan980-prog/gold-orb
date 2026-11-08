import sys
p = sys.argv[1]
s = open(p, encoding="ascii").read()
def rep(old, new):
    global s
    assert s.count(old) == 1, ("not unique/absent", old[:80])
    s = s.replace(old, new)

# A+B: helpers inserted before Block()
rep("""void Block(const datetime until, const int reason)""",
"""// reduction partielle valable en hedging ET en netting : CTrade::PositionClosePartial fait "if(!IsHedging()) return(false);"
bool ReducePos(const ulong ticket, const double vol)
  {
   if(!PositionSelectByTicket(ticket)) return false;
   MqlTradeRequest rq;
   MqlTradeResult  rs;
   ZeroMemory(rq);
   ZeroMemory(rs);
   bool buy = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY);
   rq.action    = TRADE_ACTION_DEAL;
   rq.position  = ticket;   // admis en netting ; volume > position => 10038 INVALID_CLOSE_VOLUME, jamais de retournement
   rq.symbol    = PositionGetString(POSITION_SYMBOL);
   rq.volume    = MathMin(vol, PositionGetDouble(POSITION_VOLUME));
   rq.type      = buy ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   rq.price     = SymbolInfoDouble(rq.symbol, buy ? SYMBOL_BID : SYMBOL_ASK);
   rq.deviation = 50;
   long fm = SymbolInfoInteger(rq.symbol, SYMBOL_FILLING_MODE);
   rq.type_filling = ((fm & SYMBOL_FILLING_FOK) != 0) ? ORDER_FILLING_FOK : (((fm & SYMBOL_FILLING_IOC) != 0) ? ORDER_FILLING_IOC : ORDER_FILLING_RETURN);
   bool ok = OrderSend(rq, rs) && (rs.retcode == TRADE_RETCODE_DONE || rs.retcode == TRADE_RETCODE_DONE_PARTIAL);
   static datetime s_warn = 0;
   if(!ok && TimeLocal() - s_warn >= 60)
     {
      s_warn = TimeLocal();
      Notify("GardeFou : reduction de " + rq.symbol + " refusee (code " + IntegerToString(rs.retcode) + "). Reduisez vous-meme.");
     }
   return ok;
  }

// ticket ACTUEL d'une position d'apres son POSITION_IDENTIFIER (0 = fermee) ; la selectionne.
// Le ticket change apres un retournement netting (DEAL_ENTRY_INOUT) ou une reouverture serveur, l'identifiant jamais.
ulong TicketById(const ulong id)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t != 0 && (ulong)PositionGetInteger(POSITION_IDENTIFIER) == id) return t;
     }
   return 0;
  }

void Block(const datetime until, const int reason)""")

# C: size reduction
rep("if(cut >= vstep && g_trade.PositionClosePartial(ticket, cut))", "if(cut >= vstep && ReducePos(ticket, cut))")

# D: daily-limit retry
rep("""                          s.active.daily_loss, DayHm(s.blocked_until)));
      SaveState();
     }
""", """                          s.active.daily_loss, DayHm(s.blocked_until)));
      SaveState();
     }
   // limite du jour active : ce qui reste ouvert (fermeture refusee, requote, Algo Trading coupe...) est re-ferme toutes les 30 s
   static datetime s_dl_retry = 0;
   if(s.block_reason == 3 && s.blocked_until > now && ManagedCount(0) > 0 && TimeLocal() - s_dl_retry >= 30)
     {
      s_dl_retry = TimeLocal();
      CloseAllManaged("limite de perte du jour");
     }
""")

# E1: disappearance loop -> exit accounting

# E2: OnTradeTransaction
rep("""   ulong pid = (ulong)HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);
   if(entry == DEAL_ENTRY_IN)""", """   ulong pid = (ulong)HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);
   long reason = HistoryDealGetInteger(trans.deal, DEAL_REASON);
   if(reason == DEAL_REASON_ROLLOVER || reason == DEAL_REASON_VMARGIN || reason == DEAL_REASON_SPLIT) return;   // operations de service
   if(entry == DEAL_ENTRY_IN)""")
rep("""      bool exists = PositionSelectByTicket(pid);
      bool is_add = exists && PositionGetDouble(POSITION_VOLUME) > add + 1e-8;   // volume deja present avant ce deal""",
"""      ulong tk = TicketById(pid);
      // ajout = deal d'un AUTRE ordre que l'ordre d'ouverture (POSITION_IDENTIFIER = ticket de l'ordre d'ouverture) ;
      // les executions partielles de l'ordre d'ouverture ne sont pas des ajouts
      bool is_add = (tk != 0 && (ulong)HistoryDealGetInteger(trans.deal, DEAL_ORDER) != pid);""")
rep("         if(g_trade.PositionClosePartial(pid, add))", "         if(ReducePos(tk, add))")
rep("      if(exists && !WasBlocked(pid)) OnNewPosition(pid);", "      if(tk != 0 && !WasBlocked(pid)) OnNewPosition(tk);")
rep("      bool closed = !PositionSelectByTicket(pid);",
    "      bool closed = (entry == DEAL_ENTRY_INOUT) || TicketById(pid) == 0;   // INOUT : l'ancienne position est close (meme identifiant)")
rep("""            if(d == 0) continue;
            pnl += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);""",
"""            if(d == 0) continue;
            if(d != trans.deal && HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_INOUT) { pnl = 0.0; continue; }   // retournement anterieur
            pnl += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION) + HistoryDealGetDouble(d, DEAL_FEE);
            if(d == trans.deal) break;""")

# F: LoadNews
rep("""   n_loaded = now;
   ArrayResize(n_time, 0);""", """   ArrayResize(n_time, 0);""")
rep("""      MqlCalendarValue v[];
      if(!CalendarValueHistory(v, now - 3600, now + 2 * 86400, NULL, ccy)) continue;""",
"""      MqlCalendarValue v[];
      ResetLastError();
      // doc : renvoie le NOMBRE de valeurs, -1 si erreur (5401 delai, 5402 pas de donnees) ; heures = heure serveur
      int got = CalendarValueHistory(v, now - s.active.news_min * 60 - 3600, now + 2 * 86400, NULL, ccy);
      if(got < 0 || (ArraySize(v) == 0 && GetLastError() != 0)) { err = GetLastError(); continue; }""")
rep("""   string cur[];
   int nc = StringSplit(InpNewsCurrencies, ',', cur);""", """   int err = 0;
   string cur[];
   int nc = StringSplit(InpNewsCurrencies, ',', cur);""")
rep("""         n_name[k] = ccy + " " + ev.name;
        }
     }
  }""", """         n_name[k] = ccy + " " + ev.name;
        }
     }
   n_loaded = (err == 0) ? now : now - 1800 + 60;   // echec : nouvel essai dans 1 min, pas 30
   static datetime s_cal_warned = 0;
   if(err != 0 && now - s_cal_warned > 3600)
     {
      s_cal_warned = now;
      Notify("GardeFou : calendrier economique indisponible (erreur " + IntegerToString(err) + ") : blocage des annonces inactif.");
     }
  }""")
open(p, "w", encoding="ascii").write(s)
print("patched")
