//+------------------------------------------------------------------+
//|                                                    GardeFou.mq5  |
//|  Garde-fou de discipline pour le trading MANUEL (MetaTrader 5).   |
//|  Il ne prend aucune decision d'entree : vous decidez, il protege. |
//|                                                                  |
//|  Regles appliquees a toutes vos positions (tous symboles, sauf    |
//|  filtres) :                                                       |
//|   1. Stop obligatoire : sans stop apres InpGraceSec, il le pose   |
//|      lui-meme a la distance du risque maximum.                    |
//|   2. Risque max par trade : au-dela, il reduit la taille.         |
//|   3. Le stop ne peut que se rapprocher : eloigne ou retire, il    |
//|      est remis immediatement.                                     |
//|   4. Une position a la fois ; pas d'ajout a une position.         |
//|   5. Pause apres chaque entree et apres chaque perte.             |
//|   6. Perte max du jour : tout est ferme, blocage jusqu'au         |
//|      lendemain.                                                   |
//|   7. Pas de nouvelle position autour des annonces fortes.         |
//|   8. Durcir une regle s'applique tout de suite ; l'assouplir      |
//|      seulement 24 h plus tard.                                    |
//|  Toute position ouverte pendant un blocage est fermee aussitot.   |
//+------------------------------------------------------------------+
#property copyright "gold-orb lab"
#property version   "1.00"
#property description "Garde-fou : stop obligatoire, risque max, une position a la fois, pause, limite du jour, annonces, assouplissement differe de 24 h."

#include <Trade\Trade.mqh>

input double InpMaxRiskPct     = 10.0;      // Perte max par trade si le stop est touche (% du solde)
input double InpDailyLossPct   = 10.0;      // Perte max du jour (% des fonds au debut du jour) : tout ferme + blocage
input int    InpCooldownHours  = 6;         // Pause apres chaque entree et apres chaque perte (heures)
input int    InpMaxPositions   = 1;         // Positions ouvertes en meme temps (tous symboles surveilles)
input int    InpNewsBlockMin   = 30;        // Blocage avant / apres une annonce forte (minutes, 0 = desactive)
input string InpNewsCurrencies = "USD";     // Devises des annonces surveillees (ex. "USD,EUR")
input int    InpGraceSec       = 60;        // Delai pour poser ou ajuster le stop apres l'ouverture (secondes)
input string InpSymbols        = "";        // Symboles surveilles, separes par des virgules (vide = tous)
input string InpIgnoreMagics   = "20261105";// Numeros magiques ignores (programmes automatiques), separes par des virgules
input bool   InpPush           = true;      // Notifications push (appli MT5 mobile)
input bool   InpPopup          = true;      // Fenetre d'alerte dans le terminal

//--- regles effectivement appliquees (persistees, pour le delai de 24 h)
struct Rules
  {
   double            max_risk, daily_loss;
   int               cooldown_h, max_pos, news_min, grace_s;
  };

struct GState
  {
   int               has_rules;
   Rules             active, pending;
   datetime          pending_at;        // heure serveur d'application de l'assouplissement (0 = rien)
   datetime          day_key;           // jour serveur (00:00) de la reference de perte du jour
   double            day_start_eq;
   datetime          blocked_until;     // heure serveur
   int               block_reason;      // 1 pause apres entree, 2 pause apres perte, 3 limite du jour
   datetime          last_entry;
   int               w_trades, w_wins, w_blocks;
   double            w_pnl;
   datetime          week_sent;
  };

GState   s;
CTrade   g_trade;
bool     g_ready = false;
string   g_key = "";
string   g_push[];
datetime g_push_last = 0;

// memoire des positions (reconstruite au demarrage)
ulong    p_id[];        // POSITION_IDENTIFIER
datetime p_open[];      // heure serveur d'ouverture vue par le garde-fou
double   p_best[];      // stop le plus serre vu apres le delai de grace
int      p_side[];
ulong    blocked_ids[]; // positions fermees a l'ouverture par le garde-fou (pas de pause "perte" pour elles)

// annonces fortes (cache)
datetime n_time[];
string   n_name[];
datetime n_loaded = 0;
datetime n_warned = 0;
datetime g_algo_warned = 0;

//+------------------------------------------------------------------+
//| Outils                                                           |
//+------------------------------------------------------------------+
string Hm(const datetime t) { return TimeToString(t, TIME_MINUTES); }
string DayHm(const datetime t) { return TimeToString(t, TIME_DATE | TIME_MINUTES); }

bool InList(const string list, const string item)
  {
   if(list == "") return false;
   string parts[];
   int n = StringSplit(list, ',', parts);
   for(int i = 0; i < n; i++)
     {
      string p = parts[i];
      StringTrimLeft(p);
      StringTrimRight(p);
      if(p == item) return true;
     }
   return false;
  }

bool Managed(const string sym, const long magic)
  {
   if(InList(InpIgnoreMagics, IntegerToString(magic))) return false;
   if(InpSymbols != "" && !InList(InpSymbols, sym)) return false;
   return true;
  }

void PushNow(const string p)
  {
   g_push_last = TimeLocal();
   if(!SendNotification(p))
      Print("Push : echec (", GetLastError(), "). Configurez votre MetaQuotes ID : Outils > Options > Notifications.");
  }

void Notify(const string text)
  {
   Print(text);
   if(MQLInfoInteger(MQL_TESTER)) return;
   if(InpPopup) Alert(text);
   if(!InpPush) return;
   string p = text;
   if(StringLen(p) > 255) p = StringSubstr(p, 0, 252) + "...";
   int q = ArraySize(g_push);
   if(q == 0 && TimeLocal() - g_push_last >= 7) PushNow(p);
   else if(q < 20) { ArrayResize(g_push, q + 1); g_push[q] = p; }
  }

void FlushPush()
  {
   if(ArraySize(g_push) == 0 || TimeLocal() - g_push_last < 7) return;
   PushNow(g_push[0]);
   ArrayRemove(g_push, 0, 1);
  }

void Journal(const string ev, const string sym, const ulong pid, const double value, const string note)
  {
   if(g_key == "") return;
   string fn = "GardeFou\\journal_" + g_key + ".csv";
   int h = FileOpen(fn, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ, ';');
   if(h == INVALID_HANDLE) { Print("Journal : impossible d'ouvrir ", fn, " (", GetLastError(), ")"); return; }
   if(FileSize(h) == 0) FileWrite(h, "server_time", "event", "symbol", "position", "value", "note");
   FileSeek(h, 0, SEEK_END);
   FileWrite(h, TimeToString(TimeTradeServer(), TIME_DATE | TIME_SECONDS), ev, sym, IntegerToString((long)pid),
             DoubleToString(value, 2), note);
   FileClose(h);
  }

void SaveState()
  {
   if(!g_ready || MQLInfoInteger(MQL_TESTER)) return;
   string fn = "GardeFou\\state_" + g_key + ".bin";
   string tmp = fn + ".tmp";
   int h = FileOpen(tmp, FILE_WRITE | FILE_BIN | FILE_COMMON);
   if(h == INVALID_HANDLE) return;
   bool ok = (FileWriteStruct(h, s) == (uint)sizeof(GState));
   FileClose(h);
   if(ok) FileMove(tmp, FILE_COMMON, fn, FILE_COMMON | FILE_REWRITE);
  }

bool LoadState()
  {
   ZeroMemory(s);
   string fn = "GardeFou\\state_" + g_key + ".bin";
   if(MQLInfoInteger(MQL_TESTER) || !FileIsExist(fn, FILE_COMMON)) return false;
   int h = FileOpen(fn, FILE_READ | FILE_BIN | FILE_COMMON);
   if(h == INVALID_HANDLE) return false;
   ulong sz = FileSize(h);
   uint n = FileReadStruct(h, s);
   FileClose(h);
   if(n != (uint)sizeof(GState) || sz != (ulong)sizeof(GState)) { ZeroMemory(s); return false; }
   return true;
  }

datetime DayStart(const datetime t) { return (datetime)(((long)t / 86400) * 86400); }

//+------------------------------------------------------------------+
//| Regles : durcir tout de suite, assouplir 24 h plus tard           |
//+------------------------------------------------------------------+
Rules FromInputs()
  {
   Rules r;
   r.max_risk = InpMaxRiskPct;
   r.daily_loss = InpDailyLossPct;
   r.cooldown_h = InpCooldownHours;
   r.max_pos = InpMaxPositions;
   r.news_min = InpNewsBlockMin;
   r.grace_s = InpGraceSec;
   return r;
  }

bool SameRules(const Rules &a, const Rules &b)
  {
   return MathAbs(a.max_risk - b.max_risk) < 1e-9 && MathAbs(a.daily_loss - b.daily_loss) < 1e-9 &&
          a.cooldown_h == b.cooldown_h && a.max_pos == b.max_pos && a.news_min == b.news_min && a.grace_s == b.grace_s;
  }

void SyncRules()
  {
   Rules in = FromInputs();
   datetime now = TimeTradeServer();
   if(s.has_rules == 0)
     {
      s.active = in;
      s.has_rules = 1;
      s.pending_at = 0;
      return;
     }
   Rules cur = s.active;
   // la partie la plus stricte de chaque regle s'applique tout de suite
   Rules strict = cur;
   strict.max_risk   = MathMin(cur.max_risk, in.max_risk);
   strict.daily_loss = MathMin(cur.daily_loss, in.daily_loss);
   strict.cooldown_h = (int)MathMax(cur.cooldown_h, in.cooldown_h);
   strict.max_pos    = (int)MathMin(cur.max_pos, in.max_pos);
   strict.news_min   = (int)MathMax(cur.news_min, in.news_min);
   strict.grace_s    = (int)MathMin(cur.grace_s, in.grace_s);
   bool looser = !SameRules(strict, in);
   if(!SameRules(strict, cur))
     {
      s.active = strict;
      Journal("RULES_TIGHTENED", "", 0, 0, "applied now");
     }
   if(looser)
     {
      if(s.pending_at == 0 || !SameRules(s.pending, in))
        {
         s.pending = in;
         s.pending_at = now + 24 * 3600;
         Journal("RULES_LOOSER_PENDING", "", 0, 0, "applies " + DayHm(s.pending_at));
         Notify("GardeFou : assouplissement des regles demande. Il s'appliquera le " + DayHm(s.pending_at) +
                " (heure serveur). D'ici la, les regles actuelles restent en vigueur.");
        }
     }
   else
      s.pending_at = 0;
  }

void ApplyPending()
  {
   if(s.pending_at == 0 || TimeTradeServer() < s.pending_at) return;
   s.active = s.pending;
   s.pending_at = 0;
   Journal("RULES_LOOSENED", "", 0, 0, "applied after 24 h");
   Notify(StringFormat("GardeFou : nouvelles regles en vigueur : risque %.1f%%/trade, %.1f%%/jour, pause %d h, %d position(s), annonces %d min.",
                       s.active.max_risk, s.active.daily_loss, s.active.cooldown_h, s.active.max_pos, s.active.news_min));
   SaveState();
  }

//+------------------------------------------------------------------+
//| Annonces economiques fortes (calendrier integre de MT5)           |
//+------------------------------------------------------------------+
void LoadNews()
  {
   if(MQLInfoInteger(MQL_TESTER) || s.active.news_min <= 0) return;
   datetime now = TimeTradeServer();
   if(n_loaded != 0 && now - n_loaded < 1800) return;
   ArrayResize(n_time, 0);
   ArrayResize(n_name, 0);
   int err = 0;
   string cur[];
   int nc = StringSplit(InpNewsCurrencies, ',', cur);
   for(int c = 0; c < nc; c++)
     {
      string ccy = cur[c];
      StringTrimLeft(ccy);
      StringTrimRight(ccy);
      if(ccy == "") continue;
      MqlCalendarValue v[];
      ResetLastError();
      // doc : renvoie le NOMBRE de valeurs, -1 si erreur (5401 delai, 5402 pas de donnees) ; heures = heure serveur
      int got = CalendarValueHistory(v, now - s.active.news_min * 60 - 3600, now + 2 * 86400, NULL, ccy);
      if(got < 0 || (ArraySize(v) == 0 && GetLastError() != 0)) { err = GetLastError(); continue; }
      int n = ArraySize(v);
      for(int i = 0; i < n; i++)
        {
         MqlCalendarEvent ev;
         if(!CalendarEventById(v[i].event_id, ev)) continue;
         if(ev.importance != CALENDAR_IMPORTANCE_HIGH) continue;
         int k = ArraySize(n_time);
         ArrayResize(n_time, k + 1);
         ArrayResize(n_name, k + 1);
         n_time[k] = v[i].time;
         n_name[k] = ccy + " " + ev.name;
        }
     }
   n_loaded = (err == 0) ? now : now - 1800 + 60;   // echec : nouvel essai dans 1 min, pas 30
   static datetime s_cal_warned = 0;
   if(err != 0 && now - s_cal_warned > 3600)
     {
      s_cal_warned = now;
      Notify("GardeFou : calendrier economique indisponible (erreur " + IntegerToString(err) + ") : blocage des annonces inactif.");
     }
  }

// annonce forte dans la fenetre [t - news_min, t + news_min] ? (heure serveur)
bool NewsNear(const datetime t, string &what)
  {
   what = "";
   if(s.active.news_min <= 0) return false;
   for(int i = 0; i < ArraySize(n_time); i++)
      if(MathAbs((long)(n_time[i] - t)) <= (long)s.active.news_min * 60)
        {
         what = n_name[i] + " a " + Hm(n_time[i]);
         return true;
        }
   return false;
  }

//+------------------------------------------------------------------+
//| Positions                                                        |
//+------------------------------------------------------------------+
int FindPos(const ulong id)
  {
   for(int i = 0; i < ArraySize(p_id); i++) if(p_id[i] == id) return i;
   return -1;
  }

void AddPos(const ulong id, const int side, const double sl)
  {
   int k = ArraySize(p_id);
   ArrayResize(p_id, k + 1);
   ArrayResize(p_open, k + 1);
   ArrayResize(p_best, k + 1);
   ArrayResize(p_side, k + 1);
   p_id[k] = id;
   p_open[k] = TimeTradeServer();
   p_best[k] = sl;
   p_side[k] = side;
  }

void RemovePos(const int i)
  {
   ArrayRemove(p_id, i, 1);
   ArrayRemove(p_open, i, 1);
   ArrayRemove(p_best, i, 1);
   ArrayRemove(p_side, i, 1);
  }

bool WasBlocked(const ulong id)
  {
   for(int i = 0; i < ArraySize(blocked_ids); i++) if(blocked_ids[i] == id) return true;
   return false;
  }

// perte en devise du compte pour 1 lot et 1 unite de prix
double ValuePerUnit(const string sym)
  {
   double ts = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   double tv = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tv <= 0) tv = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
   return (ts > 0) ? tv / ts : 0.0;
  }

double NormPriceSym(const string sym, const double p)
  {
   double ts = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   int dg = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   return (ts > 0) ? NormalizeDouble(MathRound(p / ts) * ts, dg) : NormalizeDouble(p, dg);
  }

double MaxRiskMoney() { return AccountInfoDouble(ACCOUNT_BALANCE) * s.active.max_risk / 100.0; }

int ManagedCount(const ulong except_id)
  {
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || !PositionSelectByTicket(t)) continue;
      if(!Managed(PositionGetString(POSITION_SYMBOL), PositionGetInteger(POSITION_MAGIC))) continue;
      if((ulong)PositionGetInteger(POSITION_IDENTIFIER) == except_id) continue;
      n++;
     }
   return n;
  }

bool CloseTicket(const ulong ticket, const string why)
  {
   bool ok = g_trade.PositionClose(ticket);
   uint rc = g_trade.ResultRetcode();
   if(!ok || (rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_DONE_PARTIAL))
     {
      Notify("GardeFou : fermeture refusee (" + g_trade.ResultRetcodeDescription() + ") - " + why + ". Fermez la position vous-meme.");
      return false;
     }
   return true;
  }

// reduction partielle valable en hedging ET en netting : CTrade::PositionClosePartial fait "if(!IsHedging()) return(false);"
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

void Block(const datetime until, const int reason)
  {
   if(until > s.blocked_until) { s.blocked_until = until; s.block_reason = reason; }
  }

string BlockText()
  {
   string r = (s.block_reason == 3) ? "limite de perte du jour" : (s.block_reason == 2 ? "pause apres une perte" : "pause apres une entree");
   return r + " jusqu'a " + DayHm(s.blocked_until);
  }

// nouvelle position (ou ajout) : on decide de la garder ou de la fermer
void OnNewPosition(const ulong ticket)
  {
   if(!PositionSelectByTicket(ticket)) return;
   string sym = PositionGetString(POSITION_SYMBOL);
   if(!Managed(sym, PositionGetInteger(POSITION_MAGIC))) return;
   ulong id = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
   int side = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
   double sl = PositionGetDouble(POSITION_SL);
   datetime now = TimeTradeServer();
   string why = "";
   string news;
   if(s.blocked_until > now) why = BlockText();
   else if(ManagedCount(id) >= s.active.max_pos) why = "une position a la fois";
   else if(NewsNear(now, news)) why = "annonce forte : " + news;
   if(why != "")
     {
      int k = ArraySize(blocked_ids);
      ArrayResize(blocked_ids, k + 1);
      blocked_ids[k] = id;
      s.w_blocks++;
      Journal("BLOCKED_OPEN", sym, id, 0, why);
      if(CloseTicket(ticket, why))
         Notify("GardeFou : position " + sym + " fermee aussitot (" + why + ").");
      SaveState();
      return;
     }
   AddPos(id, side, sl);
   s.last_entry = now;
   Block(now + s.active.cooldown_h * 3600, 1);
   Journal("ENTRY", sym, id, PositionGetDouble(POSITION_VOLUME), side > 0 ? "buy" : "sell");
   SaveState();
  }

// controles permanents : stop present, risque, stop jamais eloigne
void CheckPosition(const ulong ticket)
  {
   if(!PositionSelectByTicket(ticket)) return;
   string sym = PositionGetString(POSITION_SYMBOL);
   if(!Managed(sym, PositionGetInteger(POSITION_MAGIC))) return;
   ulong id = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
   int i = FindPos(id);
   if(i < 0)
     {   // ouverte apres le demarrage et pas encore vue : c'est une NOUVELLE position (les blocages s'appliquent)
      if(!WasBlocked(id)) { OnNewPosition(ticket); return; }
      static datetime s_retry = 0;   // position bloquee dont la fermeture a echoue : nouvel essai toutes les 10 s
      if(TimeLocal() - s_retry >= 10) { s_retry = TimeLocal(); CloseTicket(ticket, "position ouverte pendant un blocage"); }
      return;
     }
   int side = p_side[i];
   double open = PositionGetDouble(POSITION_PRICE_OPEN);
   double vol = PositionGetDouble(POSITION_VOLUME);
   double sl = PositionGetDouble(POSITION_SL), tp = PositionGetDouble(POSITION_TP);
   double vpu = ValuePerUnit(sym);
   bool in_grace = (TimeTradeServer() - p_open[i] < s.active.grace_s);
   if(vpu <= 0 || vol <= 0) return;
   double max_money = MaxRiskMoney();
   double max_dist = max_money / (vol * vpu);
   MqlTick k;
   if(!SymbolInfoTick(sym, k)) return;
   double px = (side > 0) ? k.bid : k.ask;
   double lvl = (double)MathMax(SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL),
                                SymbolInfoInteger(sym, SYMBOL_TRADE_FREEZE_LEVEL)) * SymbolInfoDouble(sym, SYMBOL_POINT);
   // 1) pas de stop apres le delai : on le pose au risque maximum (ou on ferme si le prix y est deja)
   if(sl == 0.0)
     {
      if(in_grace) return;
      double want = (p_best[i] != 0.0) ? p_best[i] : NormPriceSym(sym, open - side * max_dist);   // stop retire : on remet le dernier
      if((side > 0 && px <= want + lvl) || (side < 0 && px >= want - lvl))
        {
         Journal("CLOSED_NO_STOP", sym, id, 0, "price already beyond max-risk stop");
         if(CloseTicket(ticket, "pas de stop et perte deja au maximum")) Notify("GardeFou : " + sym + " sans stop et deja a la perte maximum : position fermee.");
         return;
        }
      if(g_trade.PositionModify(ticket, want, tp))
        {
         p_best[i] = want;
         Journal("STOP_ADDED", sym, id, want, "max risk distance");
         Notify("GardeFou : stop obligatoire pose sur " + sym + " a " + DoubleToString(want, (int)SymbolInfoInteger(sym, SYMBOL_DIGITS)) + ".");
        }
      else if(CloseTicket(ticket, "impossible de poser le stop"))
         Notify("GardeFou : impossible de poser le stop sur " + sym + " : position fermee.");
      return;
     }
   // 2) risque trop grand (taille ou stop trop loin) : on reduit la taille
   double risk = MathAbs(open - sl) * vol * vpu;
   bool beyond_entry = (side > 0 && sl < open) || (side < 0 && sl > open);
   if(!in_grace && beyond_entry && risk > max_money * 1.02)
     {
      double vstep = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP), vmin = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
      double keep = MathFloor(max_money / (MathAbs(open - sl) * vpu) / vstep + 1e-9) * vstep;
      int vd = (int)MathMax(0.0, MathCeil(-MathLog10(vstep) - 1e-9));
      keep = NormalizeDouble(keep, vd);
      if(keep < vmin)
        {
         Journal("CLOSED_RISK", sym, id, risk, "even min lot exceeds max risk");
         if(CloseTicket(ticket, "risque superieur au maximum")) Notify("GardeFou : " + sym + " : risque au-dela du maximum meme au lot minimum, position fermee.");
         return;
        }
      double cut = NormalizeDouble(vol - keep, vd);
      if(cut >= vstep && ReducePos(ticket, cut))
        {
         Journal("SIZE_REDUCED", sym, id, cut, StringFormat("risk %.2f > max %.2f", risk, max_money));
         Notify(StringFormat("GardeFou : taille %s reduite de %.2f lot (risque %.0f > maximum %.0f).", sym, cut, risk, max_money));
        }
      return;
     }
   // 3) le stop ne peut que se rapprocher (apres le delai de grace)
   if(in_grace) { p_best[i] = sl; return; }
   if(p_best[i] == 0.0) p_best[i] = sl;
   bool widened = (side > 0 && sl < p_best[i] - SymbolInfoDouble(sym, SYMBOL_POINT) / 2) ||
                  (side < 0 && sl > p_best[i] + SymbolInfoDouble(sym, SYMBOL_POINT) / 2);
   if(widened)
     {
      double back = p_best[i];
      if((side > 0 && px <= back + lvl) || (side < 0 && px >= back - lvl))
        {   // le prix a deja depasse le stop d'origine : on sort comme le stop l'aurait fait
         Journal("CLOSED_STOP_MOVED", sym, id, back, "stop was moved away and price passed the original stop");
         if(CloseTicket(ticket, "stop eloigne")) Notify("GardeFou : stop de " + sym + " eloigne alors que le prix l'avait depasse : position fermee.");
         return;
        }
      if(g_trade.PositionModify(ticket, back, tp))
        {
         Journal("STOP_RESTORED", sym, id, back, "stop moved away");
         Notify("GardeFou : le stop de " + sym + " ne peut pas etre eloigne. Remis a " +
                DoubleToString(back, (int)SymbolInfoInteger(sym, SYMBOL_DIGITS)) + ".");
        }
      return;
     }
   if((side > 0 && sl > p_best[i]) || (side < 0 && sl < p_best[i])) p_best[i] = sl;   // stop resserre : nouvelle reference
  }

void CloseAllManaged(const string why)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || !PositionSelectByTicket(t)) continue;
      if(!Managed(PositionGetString(POSITION_SYMBOL), PositionGetInteger(POSITION_MAGIC))) continue;
      CloseTicket(t, why);
     }
  }

//+------------------------------------------------------------------+
//| Boucle principale                                                |
//+------------------------------------------------------------------+
void Enforce()
  {
   datetime now = TimeTradeServer();
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   // nouveau jour serveur : nouvelle reference ; la limite du jour est levee
   datetime dk = DayStart(now);
   if(s.day_key != dk)
     {
      s.day_key = dk;
      s.day_start_eq = eq;
      if(s.block_reason == 3) { s.blocked_until = 0; s.block_reason = 0; }
      Journal("DAY_START", "", 0, eq, "");
      SaveState();
     }
   ApplyPending();
   LoadNews();
   if((!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED)) && TimeLocal() - g_algo_warned > 3600)
     {
      g_algo_warned = TimeLocal();
      Notify("GardeFou : Algo Trading est coupe. Vous n'etes plus protege (stops, pause, limite du jour).");
      Journal("ALGO_OFF", "", 0, 0, "");
     }
   // limite de perte du jour (fonds, pertes latentes comprises)
   if(s.day_start_eq > 0 && eq <= s.day_start_eq * (1.0 - s.active.daily_loss / 100.0) && s.block_reason != 3)
     {
      Block(dk + 86400, 3);
      s.blocked_until = dk + 86400;
      s.block_reason = 3;
      Journal("DAILY_LIMIT", "", 0, eq, StringFormat("start %.2f", s.day_start_eq));
      CloseAllManaged("limite de perte du jour");
      Notify(StringFormat("GardeFou : limite de perte du jour atteinte (%.1f%%). Tout est ferme. Trading bloque jusqu'a %s.",
                          s.active.daily_loss, DayHm(s.blocked_until)));
      SaveState();
     }
   // limite du jour active : ce qui reste ouvert (fermeture refusee, requote, Algo Trading coupe...) est re-ferme toutes les 30 s
   static datetime s_dl_retry = 0;
   if(s.block_reason == 3 && s.blocked_until > now && ManagedCount(0) > 0 && TimeLocal() - s_dl_retry >= 30)
     {
      s_dl_retry = TimeLocal();
      CloseAllManaged("limite de perte du jour");
     }
   // positions : nouvelles et controles
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || !PositionSelectByTicket(t)) continue;
      if(!Managed(PositionGetString(POSITION_SYMBOL), PositionGetInteger(POSITION_MAGIC))) continue;
      CheckPosition(t);
     }
   // positions disparues de la memoire
   for(int j = ArraySize(p_id) - 1; j >= 0; j--)
     {
      bool alive = false;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong t = PositionGetTicket(i);
         if(t != 0 && PositionSelectByTicket(t) && (ulong)PositionGetInteger(POSITION_IDENTIFIER) == p_id[j]) { alive = true; break; }
        }
      if(!alive) RemovePos(j);
     }
   // annonce forte imminente : rappel unique
   string what;
   if(NewsNear(now + s.active.news_min * 60, what) && now - n_warned > 3600)
     {
      n_warned = now;
      Notify("GardeFou : annonce forte (" + what + "). Pas de nouvelle position de " + IntegerToString(s.active.news_min) +
             " min avant a " + IntegerToString(s.active.news_min) + " min apres.");
     }
  }

void Weekly()
  {
   datetime now = TimeTradeServer();
   MqlDateTime x;
   TimeToStruct(now, x);
   if(x.day_of_week != 5 || x.hour < 22 || now - s.week_sent < 3 * 86400) return;
   Notify(StringFormat("GardeFou semaine : %d trade(s), %d gagnant(s), resultat %+.2f, %d ouverture(s) bloquee(s).",
                       s.w_trades, s.w_wins, s.w_pnl, s.w_blocks));
   Journal("WEEK", "", 0, s.w_pnl, StringFormat("%d trades %d wins %d blocks", s.w_trades, s.w_wins, s.w_blocks));
   s.w_trades = 0; s.w_wins = 0; s.w_blocks = 0; s.w_pnl = 0; s.week_sent = now;
   SaveState();
  }

bool AccountReady()
  {
   if(g_ready) return true;
   if(AccountInfoInteger(ACCOUNT_LOGIN) == 0 || !TerminalInfoInteger(TERMINAL_CONNECTED)) return false;
   g_key = IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN));
   bool had = LoadState();
   SyncRules();
   g_ready = true;
   for(int i = PositionsTotal() - 1; i >= 0; i--)   // positions deja ouvertes au demarrage : prises en charge sans fermeture
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || !PositionSelectByTicket(t)) continue;
      if(!Managed(PositionGetString(POSITION_SYMBOL), PositionGetInteger(POSITION_MAGIC))) continue;
      ulong id = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
      if(FindPos(id) >= 0) continue;
      AddPos(id, (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1, PositionGetDouble(POSITION_SL));
      p_open[ArraySize(p_open) - 1] = TimeTradeServer() - 3600;   // pas de delai de grace pour elles
      Journal("ADOPTED", PositionGetString(POSITION_SYMBOL), id, PositionGetDouble(POSITION_VOLUME), "already open at start");
     }
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
      Notify("GardeFou : Algo Trading desactive. Le garde-fou ne peut rien proteger tant qu'il est coupe.");
   Print(StringFormat("GardeFou demarre (compte %s, etat %s) : risque %.1f%%/trade, %.1f%%/jour, pause %d h, %d position(s), annonces %d min, grace %d s.",
                      g_key, had ? "recharge" : "nouveau", s.active.max_risk, s.active.daily_loss, s.active.cooldown_h,
                      s.active.max_pos, s.active.news_min, s.active.grace_s));
   Journal("START", "", 0, AccountInfoDouble(ACCOUNT_EQUITY), had ? "state reloaded" : "new state");
   SaveState();
   return true;
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpMaxRiskPct <= 0 || InpMaxRiskPct > 50 || InpDailyLossPct <= 0 || InpDailyLossPct > 100 || InpCooldownHours < 0 ||
      InpMaxPositions < 1 || InpNewsBlockMin < 0 || InpGraceSec < 5 || InpGraceSec > 600)
     {
      Alert("GardeFou : parametre hors limites.");
      return INIT_PARAMETERS_INCORRECT;
     }
   FolderCreate("GardeFou", FILE_COMMON);
   ZeroMemory(s);
   g_ready = false;
   g_key = "";
   ArrayResize(p_id, 0); ArrayResize(p_open, 0); ArrayResize(p_best, 0); ArrayResize(p_side, 0);
   EventSetTimer(1);
   AccountReady();
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   if(g_ready) Journal("STOP", "", 0, AccountInfoDouble(ACCOUNT_EQUITY), "reason " + IntegerToString(reason));
   SaveState();
  }

void OnTick()
  {
   if(!AccountReady()) return;
   Enforce();
  }

void OnTimer()
  {
   if(!AccountReady()) return;
   Enforce();
   Weekly();
   FlushPush();
  }

// reaction immediate aux executions : nouvelle position, ajout, sortie
void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
  {
   if(!g_ready || trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
   if(!HistoryDealSelect(trans.deal)) return;
   string sym = HistoryDealGetString(trans.deal, DEAL_SYMBOL);
   long magic = HistoryDealGetInteger(trans.deal, DEAL_MAGIC);
   long entry = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   ulong pid = (ulong)HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);
   long reason = HistoryDealGetInteger(trans.deal, DEAL_REASON);
   if(reason == DEAL_REASON_ROLLOVER || reason == DEAL_REASON_VMARGIN || reason == DEAL_REASON_SPLIT) return;   // operations de service
   if(entry == DEAL_ENTRY_IN)
     {
      // le garde-fou ferme lui-meme : ses propres deals (magic de CTrade) ne sont pas des entrees
      if(!Managed(sym, magic)) return;
      double add = HistoryDealGetDouble(trans.deal, DEAL_VOLUME);
      ulong tk = TicketById(pid);
      // ajout = deal d'un AUTRE ordre que l'ordre d'ouverture (POSITION_IDENTIFIER = ticket de l'ordre d'ouverture) ;
      // les executions partielles de l'ordre d'ouverture ne sont pas des ajouts
      bool is_add = (tk != 0 && (ulong)HistoryDealGetInteger(trans.deal, DEAL_ORDER) != pid);
      if(FindPos(pid) >= 0 && !is_add) return;   // deal d'ouverture deja traite par la boucle principale
      if(is_add)
        {   // ajout a une position deja ouverte (compte "netting") : on retire le volume ajoute
         s.w_blocks++;
         Journal("BLOCKED_ADD", sym, pid, add, "adding to an open position");
         if(ReducePos(tk, add))
            Notify("GardeFou : ajout a la position " + sym + " annule (pas d'ajout a une position ouverte).");
         SaveState();
         return;
        }
      if(tk != 0 && !WasBlocked(pid)) OnNewPosition(tk);
      return;
     }
   if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY || entry == DEAL_ENTRY_INOUT)
     {
      if(!Managed(sym, magic) && FindPos(pid) < 0) return;
      bool closed = (entry == DEAL_ENTRY_INOUT) || TicketById(pid) == 0;   // INOUT : l'ancienne position est close (meme identifiant)
      if(!closed || WasBlocked(pid)) return;   // sortie partielle, ou position fermee a l'ouverture par le garde-fou
      // resultat total de la position fermee
      double pnl = 0.0;
      if(HistorySelectByPosition(pid))
         for(int i = 0; i < HistoryDealsTotal(); i++)
           {
            ulong d = HistoryDealGetTicket(i);
            if(d == 0) continue;
            if(d != trans.deal && HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_INOUT) { pnl = 0.0; continue; }   // retournement anterieur
            pnl += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION) + HistoryDealGetDouble(d, DEAL_FEE);
            if(d == trans.deal) break;
           }
      s.w_trades++;
      s.w_pnl += pnl;
      if(pnl > 0) s.w_wins++;
      Journal("EXIT", sym, pid, pnl, pnl < 0 ? "loss" : "win");
      if(pnl < 0)
        {
         Block(TimeTradeServer() + s.active.cooldown_h * 3600, 2);
         Notify(StringFormat("GardeFou : perte de %.2f sur %s. Pause : pas de nouvelle position avant %s.",
                             -pnl, sym, DayHm(s.blocked_until)));
        }
      int i = FindPos(pid);
      if(i >= 0) RemovePos(i);
      SaveState();
     }
  }
//+------------------------------------------------------------------+
