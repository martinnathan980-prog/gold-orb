//+------------------------------------------------------------------+
//|                                          GoldOrb_Donchian4H.mq5  |
//|  Cassure du canal 10 jours (60 bougies H4 en grille UTC) - XAUUSD |
//|  Regle testee dans lab/tracks/trend (finaliste "donch4h_stop").   |
//|                                                                  |
//|  MODE PAR DEFAUT = ALERTES + JOURNAL (aucun ordre n'est passe).   |
//|  - Toutes les 4 h (00/04/08/12/16/20 UTC), si aucune position :   |
//|    niveau ACHAT = plus haut des 60 dernieres bougies H4,          |
//|    niveau VENTE = plus bas des 60 dernieres bougies H4,           |
//|    valables jusqu'a la prochaine cloture H4 (OCO).                |
//|  - Stop initial = 2 x ATR14(H4) ; stop suiveur = 2 x ATR depuis    |
//|    le meilleur prix, mis a jour a chaque cloture M1 ;             |
//|    sortie forcee apres 5 jours de bourse (heure de New York).     |
//|  Modes : 0 alertes | 1 alertes + gestion de VOS positions        |
//|          manuelles (stop/suiveur/sortie) | 2 automatique (DEMO).  |
//+------------------------------------------------------------------+
#property copyright "gold-orb lab"
#property version   "1.00"
#property description "Alertes de cassure du canal 10 jours (H4 UTC) sur l'or. Mode observation par defaut."

#include <Trade\Trade.mqh>

enum ENUM_GO_MODE
  {
   GO_ALERTS = 0,        // Alertes + journal (aucun ordre)
   GO_MANAGE_MANUAL = 1, // Alertes + gestion de mes positions manuelles
   GO_AUTO = 2           // Automatique (compte DEMO uniquement par defaut)
  };

enum ENUM_GO_TZ
  {
   GO_TZ_NY_CLOSE = 0,   // Serveur aligne sur 17h New York (UTC+2 hiver / UTC+3 ete US)
   GO_TZ_AUTO = 1,       // Automatique (TimeTradeServer - TimeGMT), compte reel uniquement
   GO_TZ_FIXED = 2       // Decalage fixe (heures)
  };

input ENUM_GO_MODE InpMode          = GO_ALERTS;   // Mode de fonctionnement
input ENUM_GO_TZ   InpServerTZ      = GO_TZ_NY_CLOSE; // Fuseau du serveur du courtier
input int          InpFixedOffsetH  = 2;           // Decalage fixe serveur-UTC (si mode fixe)
input int          InpChannelBars   = 60;          // Bougies H4 du canal (60 = 10 jours)
input int          InpATRPeriod     = 14;          // Periode ATR (H4, Wilder)
input double       InpStopATR       = 2.0;         // Stop initial (x ATR)
input double       InpTrailATR      = 2.0;         // Stop suiveur (x ATR)
input int          InpMaxDays       = 5;           // Duree max (jours de bourse)
input double       InpRiskPct       = 0.5;         // Risque par trade (% du capital) pour le calcul du lot
input double       InpPreAlertATR   = 0.25;        // Pre-alerte a X ATR du niveau (0 = desactive)
input bool         InpNotifyLevels  = false;       // Notifier les niveaux a chaque cloture H4
input bool         InpPush          = true;        // Notifications push (appli MT5 mobile)
input bool         InpPopup         = true;        // Fenetre d'alerte dans le terminal
input string       InpTgToken       = "";          // Telegram : token du bot (optionnel)
input string       InpTgChat        = "";          // Telegram : chat_id (optionnel)
input bool         InpAllowAutoReal = false;       // Autoriser le mode auto sur compte REEL (deconseille)
input long         InpMagic         = 20261105;    // Numero magique (mode auto)
input long         InpManualMagic   = 0;           // Numero magique des positions manuelles a gerer
input int          InpHistoryDays   = 90;          // Historique M5 charge pour construire les H4

//--- position fictive (journal / "paper trading")
struct GoState
  {
   int               side;          // 0 = aucune, +1 achat, -1 vente
   double            fill;          // prix d'entree theorique
   double            stop;          // stop courant
   double            init_stop;     // stop initial
   double            trail;         // distance du suiveur
   double            best;          // meilleur prix depuis l'entree
   double            atr;
   datetime          entry_utc;
   datetime          deadline_utc;
   double            cum_R;         // cumul depuis le debut
   int               n_trades;
   double            week_R;
   int               week_n;
   datetime          week_sent_utc; // derniere synthese hebdo envoyee
  };

GoState  g;
bool     g_br_active = false;
double   g_br_hi = 0, g_br_lo = 0, g_br_atr = 0;
datetime g_br_expiry_utc = 0;
bool     g_pre_hi = false, g_pre_lo = false;
datetime g_bucket = 0;       // debut (UTC) de la bougie H4 en cours
datetime g_last_m1 = 0;      // derniere bougie M1 traitee (heure serveur)
bool     g_auto = false;
CTrade   g_trade;

//+------------------------------------------------------------------+
//| Outils de temps                                                  |
//+------------------------------------------------------------------+
datetime NthSunday(const int year, const int month, const int n)
  {
   MqlDateTime d;
   ZeroMemory(d);
   d.year = year; d.mon = month; d.day = 1;
   datetime t = StructToTime(d);
   MqlDateTime x;
   TimeToStruct(t, x);
   int first = (x.day_of_week == 0) ? 1 : 1 + (7 - x.day_of_week);
   d.day = first + 7 * (n - 1);
   return StructToTime(d);
  }

// Heure d'ete US : du 2e dimanche de mars 07:00 UTC au 1er dimanche de novembre 06:00 UTC
bool IsUSDST(const datetime utc)
  {
   MqlDateTime x;
   TimeToStruct(utc, x);
   datetime s = NthSunday(x.year, 3, 2) + 7 * 3600;
   datetime e = NthSunday(x.year, 11, 1) + 6 * 3600;
   return (utc >= s && utc < e);
  }

int ServerOffsetSec(const datetime server_time)
  {
   if(InpServerTZ == GO_TZ_FIXED)
      return InpFixedOffsetH * 3600;
   if(InpServerTZ == GO_TZ_AUTO && !MQLInfoInteger(MQL_TESTER))
     {
      long d = (long)TimeTradeServer() - (long)TimeGMT();
      return (int)(MathRound((double)d / 900.0) * 900);
     }
   return IsUSDST(server_time - 2 * 3600) ? 3 * 3600 : 2 * 3600;
  }

datetime ToUTC(const datetime server_time)    { return server_time - ServerOffsetSec(server_time); }
datetime ToServer(const datetime utc)
  {
   if(InpServerTZ == GO_TZ_FIXED) return utc + InpFixedOffsetH * 3600;
   if(InpServerTZ == GO_TZ_AUTO && !MQLInfoInteger(MQL_TESTER)) return utc + ServerOffsetSec(TimeTradeServer());
   return utc + (IsUSDST(utc) ? 3 * 3600 : 2 * 3600);
  }
datetime NowUTC()                             { return ToUTC(TimeCurrent()); }
datetime NYfromUTC(const datetime utc)        { return utc - (IsUSDST(utc) ? 4 : 5) * 3600; }
datetime UTCfromNY(const datetime ny)
  {
   datetime guess = ny + 5 * 3600;
   return ny + (IsUSDST(guess) ? 4 : 5) * 3600;
  }

// decision + N jours de bourse (lun-ven, meme heure de New York) - 5 min ;
// si cela tombe dans la fermeture du week-end : vendredi 16:55 New York.
datetime DeadlineUTC(const datetime decision_utc, const int days)
  {
   datetime ny = NYfromUTC(decision_utc);
   int added = 0;
   while(added < days)
     {
      ny += 86400;
      MqlDateTime x;
      TimeToStruct(ny, x);
      if(x.day_of_week >= 1 && x.day_of_week <= 5) added++;
     }
   ny -= 300;
   MqlDateTime y;
   TimeToStruct(ny, y);
   int mins = y.hour * 60 + y.min;
   bool closed = (y.day_of_week == 6) || (y.day_of_week == 0 && mins < 18 * 60) ||
                 (y.day_of_week == 5 && mins >= 17 * 60);
   if(closed)
     {
      // recule jusqu'au vendredi 16:55 New York
      while(true)
        {
         MqlDateTime z;
         TimeToStruct(ny, z);
         if(z.day_of_week == 5) break;
         ny -= 86400;
        }
      MqlDateTime w;
      TimeToStruct(ny, w);
      w.hour = 16; w.min = 55; w.sec = 0;
      ny = StructToTime(w);
     }
   return UTCfromNY(ny);
  }

datetime BucketUTC(const datetime utc) { return (datetime)(((long)utc / 14400) * 14400); }

//+------------------------------------------------------------------+
//| Bougies H4 en grille UTC (prix milieu) a partir du M5 du courtier |
//+------------------------------------------------------------------+
struct Bar4 { datetime t; double o, h, l, c; };

int Build4H(Bar4 &out[], const datetime upto_bucket)
  {
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(_Symbol, PERIOD_M5, 0, InpHistoryDays * 288, r);
   ArrayResize(out, 0);
   if(n <= 0) return 0;
   int k = -1;
   datetime cur = 0;
   for(int i = 0; i < n; i++)
     {
      datetime b = BucketUTC(ToUTC(r[i].time));
      if(b >= upto_bucket) break;                      // bougie H4 en cours exclue
      double hs = r[i].spread * _Point * 0.5;          // bid -> milieu
      double mh = r[i].high + hs, ml = r[i].low + hs, mo = r[i].open + hs, mc = r[i].close + hs;
      if(b != cur)
        {
         k++;
         ArrayResize(out, k + 1);
         out[k].t = b; out[k].o = mo; out[k].h = mh; out[k].l = ml; out[k].c = mc;
         cur = b;
        }
      else
        {
         if(mh > out[k].h) out[k].h = mh;
         if(ml < out[k].l) out[k].l = ml;
         out[k].c = mc;
        }
     }
   return k + 1;
  }

double WilderATR(const Bar4 &b[], const int n, const int period)
  {
   if(n < period + 2) return 0.0;
   double atr = 0.0;
   for(int i = 1; i < n; i++)
     {
      double tr = MathMax(b[i].h - b[i].l, MathMax(MathAbs(b[i].h - b[i - 1].c), MathAbs(b[i].l - b[i - 1].c)));
      atr = (i == 1) ? tr : atr + (tr - atr) / period;
     }
   return atr;
  }

//+------------------------------------------------------------------+
//| Notifications et journal                                         |
//+------------------------------------------------------------------+
string JsonEscape(string s)
  {
   StringReplace(s, "\\", "\\\\");
   StringReplace(s, "\"", "\\\"");
   StringReplace(s, "\n", "\\n");
   return s;
  }

void Telegram(const string text)
  {
   if(InpTgToken == "" || InpTgChat == "" || MQLInfoInteger(MQL_TESTER)) return;
   string url = "https://api.telegram.org/bot" + InpTgToken + "/sendMessage";
   string body = "{\"chat_id\":\"" + InpTgChat + "\",\"text\":\"" + JsonEscape(text) + "\"}";
   char data[], res[];
   string rh;
   int len = StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
   if(len > 0) ArrayResize(data, len - 1);
   int code = WebRequest("POST", url, "Content-Type: application/json\r\n", 5000, data, res, rh);
   if(code != 200)
      Print("Telegram: echec (code ", code, ", erreur ", GetLastError(),
            "). Ajoutez https://api.telegram.org dans Outils > Options > Expert Advisors > WebRequest.");
  }

void Notify(const string text)
  {
   Print(text);
   if(MQLInfoInteger(MQL_TESTER)) return;
   if(InpPopup) Alert(text);
   if(InpPush)
     {
      string p = text;
      if(StringLen(p) > 255) p = StringSubstr(p, 0, 252) + "...";
      if(!SendNotification(p))
         Print("Push: echec (", GetLastError(), "). Configurez votre MetaQuotes ID dans Outils > Options > Notifications.");
     }
   Telegram(text);
  }

string FilePrefix() { return MQLInfoInteger(MQL_TESTER) ? "GoldOrb\\tester_" : "GoldOrb\\"; }

void Journal(const string ev, const int side, const double price, const double stop,
             const double atr, const double R, const string note)
  {
   string fn = FilePrefix() + "journal_" + _Symbol + ".csv";
   int h = FileOpen(fn, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ, ';');
   if(h == INVALID_HANDLE) { Print("Journal: impossible d'ouvrir ", fn, " (", GetLastError(), ")"); return; }
   if(FileSize(h) == 0)
      FileWrite(h, "time_utc", "event", "side", "price", "stop", "atr", "R", "note");
   FileSeek(h, 0, SEEK_END);
   FileWrite(h, TimeToString(NowUTC(), TIME_DATE | TIME_MINUTES | TIME_SECONDS), ev, side,
             DoubleToString(price, _Digits), DoubleToString(stop, _Digits), DoubleToString(atr, _Digits),
             DoubleToString(R, 3), note);
   FileClose(h);
  }

void SaveState()
  {
   string fn = FilePrefix() + "state_" + _Symbol + ".bin";
   int h = FileOpen(fn, FILE_WRITE | FILE_BIN | FILE_COMMON);
   if(h == INVALID_HANDLE) return;
   FileWriteStruct(h, g);
   FileClose(h);
  }

void LoadState()
  {
   ZeroMemory(g);
   string fn = FilePrefix() + "state_" + _Symbol + ".bin";
   if(MQLInfoInteger(MQL_TESTER) || !FileIsExist(fn, FILE_COMMON)) return;
   int h = FileOpen(fn, FILE_READ | FILE_BIN | FILE_COMMON);
   if(h == INVALID_HANDLE) return;
   FileReadStruct(h, g);
   FileClose(h);
  }

//+------------------------------------------------------------------+
//| Taille de position pour InpRiskPct % du capital                   |
//+------------------------------------------------------------------+
double LotsForRisk(const double stop_dist, string &msg)
  {
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tick_val = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tick_val <= 0) tick_val = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vstep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(tick_size <= 0 || tick_val <= 0 || vstep <= 0 || stop_dist <= 0) { msg = "lot: n/a"; return 0.0; }
   double loss_per_lot = stop_dist / tick_size * tick_val;
   double lots = MathFloor(eq * InpRiskPct / 100.0 / loss_per_lot / vstep) * vstep;
   if(lots < vmin)
     {
      double pct = vmin * loss_per_lot / eq * 100.0;
      msg = StringFormat("lot min %.2f = %.1f%% du capital (> %.1f%% vise)", vmin, pct, InpRiskPct);
      return vmin;
     }
   lots = MathMin(lots, vmax);
   msg = StringFormat("lot %.2f (%.1f%% du capital)", lots, InpRiskPct);
   return lots;
  }

//+------------------------------------------------------------------+
//| Positions reelles (modes 1 et 2)                                  |
//+------------------------------------------------------------------+
bool SelectManagedPosition(ulong &ticket)
  {
   long magic = (InpMode == GO_AUTO) ? InpMagic : InpManualMagic;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || !PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != magic) continue;
      long type = PositionGetInteger(POSITION_TYPE);
      int side = (type == POSITION_TYPE_BUY) ? 1 : -1;
      if(side != g.side) continue;
      ticket = t;
      return true;
     }
   return false;
  }

void SyncRealStop()
  {
   if(InpMode == GO_ALERTS || g.side == 0) return;
   ulong t;
   if(!SelectManagedPosition(t)) return;
   double sl = PositionGetDouble(POSITION_SL), tp = PositionGetDouble(POSITION_TP);
   double want = NormalizeDouble(g.stop, _Digits);
   bool better = (sl == 0.0) || (g.side > 0 && want > sl + _Point) || (g.side < 0 && want < sl - _Point);
   if(!better) return;
   MqlTick k;
   if(!SymbolInfoTick(_Symbol, k)) return;
   double lvl = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   if(g.side > 0 && want > k.bid - lvl) return;   // trop pres du prix : reessai plus tard
   if(g.side < 0 && want < k.ask + lvl) return;
   if(!g_trade.PositionModify(t, want, tp))
      Print("Modification du stop refusee : ", g_trade.ResultRetcodeDescription());
  }

void CloseRealPosition(const string why)
  {
   if(InpMode == GO_ALERTS) return;
   ulong t;
   if(SelectManagedPosition(t))
     {
      if(!g_trade.PositionClose(t))
         Notify("GoldOrb: fermeture refusee (" + why + ") : " + g_trade.ResultRetcodeDescription() + ". Fermez manuellement.");
     }
  }

void DeletePendings()
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong t = OrderGetTicket(i);
      if(t == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) == _Symbol && OrderGetInteger(ORDER_MAGIC) == InpMagic)
         g_trade.OrderDelete(t);
     }
  }

void PlacePendings()
  {
   if(!g_auto) return;
   DeletePendings();
   string m;
   double lots = LotsForRisk(InpStopATR * g_br_atr, m);
   if(lots <= 0) return;
   MqlTick k;
   if(!SymbolInfoTick(_Symbol, k)) return;
   double lvl = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   long emode = SymbolInfoInteger(_Symbol, SYMBOL_EXPIRATION_MODE);
   bool spec = (emode & SYMBOL_EXPIRATION_SPECIFIED) != 0;
   ENUM_ORDER_TYPE_TIME tt = spec ? ORDER_TIME_SPECIFIED : ORDER_TIME_GTC;
   datetime exp = spec ? ToServer(g_br_expiry_utc) : 0;
   double hi = NormalizeDouble(g_br_hi, _Digits), lo = NormalizeDouble(g_br_lo, _Digits);
   if(hi > k.ask + lvl)
      g_trade.BuyStop(lots, hi, _Symbol, NormalizeDouble(hi - InpStopATR * g_br_atr, _Digits), 0, tt, exp, "GoldOrb L");
   if(lo < k.bid - lvl)
      g_trade.SellStop(lots, lo, _Symbol, NormalizeDouble(lo + InpStopATR * g_br_atr, _Digits), 0, tt, exp, "GoldOrb S");
  }

//+------------------------------------------------------------------+
//| Logique de la strategie                                          |
//+------------------------------------------------------------------+
void NewBracket(const datetime bucket)
  {
   g_br_active = false;
   g_pre_hi = false; g_pre_lo = false;
   if(g.side != 0) return;                         // on ne place des niveaux que sans position
   Bar4 b[];
   int n = Build4H(b, bucket);
   if(n < InpChannelBars + InpATRPeriod + 2)
     {
      Print("GoldOrb: historique insuffisant (", n, " bougies H4). Augmentez InpHistoryDays ou ouvrez un graphique M5.");
      return;
     }
   double hi = -DBL_MAX, lo = DBL_MAX;
   for(int i = n - InpChannelBars; i < n; i++)
     {
      if(b[i].h > hi) hi = b[i].h;
      if(b[i].l < lo) lo = b[i].l;
     }
   g_br_hi = hi; g_br_lo = lo;
   g_br_atr = WilderATR(b, n, InpATRPeriod);
   g_br_expiry_utc = bucket + 14400;
   if(g_br_atr <= 0) return;
   g_br_active = true;
   Journal("LEVELS", 0, hi, lo, g_br_atr, 0, "valid_until_utc " + TimeToString(g_br_expiry_utc, TIME_DATE | TIME_MINUTES));
   if(InpNotifyLevels)
      Notify(StringFormat("GoldOrb %s niveaux jusqu'a %s UTC : achat > %s | vente < %s | ATR %.2f",
                          _Symbol, TimeToString(g_br_expiry_utc, TIME_MINUTES), DoubleToString(hi, _Digits),
                          DoubleToString(lo, _Digits), g_br_atr));
   PlacePendings();
  }

void Enter(const int side, const double price)
  {
   g.side = side;
   g.fill = price;
   g.atr = g_br_atr;
   g.trail = InpTrailATR * g_br_atr;
   g.init_stop = price - side * InpStopATR * g_br_atr;
   g.stop = g.init_stop;
   g.best = price;
   g.entry_utc = NowUTC();
   g.deadline_utc = DeadlineUTC(g_br_expiry_utc - 14400, InpMaxDays);
   g_br_active = false;
   string m;
   LotsForRisk(MathAbs(price - g.init_stop), m);
   string txt = StringFormat("GoldOrb %s %s ~%s | stop %s (%.1f) | suiveur %.1f | sortie max %s UTC | %s | NON VALIDE EN REEL",
                             _Symbol, side > 0 ? "CASSURE HAUSSE: ACHAT" : "CASSURE BAISSE: VENTE",
                             DoubleToString(price, _Digits), DoubleToString(g.init_stop, _Digits),
                             MathAbs(price - g.init_stop), g.trail,
                             TimeToString(g.deadline_utc, TIME_DATE | TIME_MINUTES), m);
   Notify(txt);
   Journal("ENTRY", side, price, g.init_stop, g.atr, 0, TimeToString(g.deadline_utc, TIME_DATE | TIME_MINUTES));
   SaveState();
  }

void Exit(const double price, const string why)
  {
   double risk = MathAbs(g.fill - g.init_stop);
   double R = (risk > 0) ? g.side * (price - g.fill) / risk : 0.0;
   g.cum_R += R; g.n_trades++;
   g.week_R += R; g.week_n++;
   string txt = StringFormat("GoldOrb %s SORTIE %s (%s) a %s : %+.2f R | cumul %+.1f R sur %d trades",
                             _Symbol, g.side > 0 ? "achat" : "vente", why, DoubleToString(price, _Digits),
                             R, g.cum_R, g.n_trades);
   Notify(txt);
   Journal("EXIT", g.side, price, g.stop, g.atr, R, why);
   CloseRealPosition(why);
   g.side = 0;
   SaveState();
  }

void OnNewM1()
  {
   if(g.side == 0) return;
   // la bougie M1 qui vient de se fermer : index 1
   double hi = iHigh(_Symbol, PERIOD_M1, 1);
   double lo = iLow(_Symbol, PERIOD_M1, 1);
   long spr = iSpread(_Symbol, PERIOD_M1, 1);
   if(hi <= 0 || lo <= 0) return;
   if(g.side > 0)
     {
      if(hi > g.best) g.best = hi;                                   // plus haut bid
      if(g.best - g.trail > g.stop) g.stop = g.best - g.trail;
     }
   else
     {
      double alo = lo + spr * _Point;                               // plus bas ask
      if(alo < g.best) g.best = alo;
      if(g.best + g.trail < g.stop) g.stop = g.best + g.trail;
     }
   SyncRealStop();
   SaveState();
  }

void WeeklySummary()
  {
   datetime now = NowUTC();
   MqlDateTime x;
   TimeToStruct(now, x);
   if(x.day_of_week != 5 || x.hour < 20) return;      // vendredi apres 20:00 UTC (le marche ferme vers 21-22h)
   if(now - g.week_sent_utc < 3 * 86400) return;
   Notify(StringFormat("GoldOrb %s semaine : %d trade(s), %+.2f R | cumul %+.1f R sur %d trades%s",
                       _Symbol, g.week_n, g.week_R, g.cum_R, g.n_trades,
                       g.side != 0 ? " | position ouverte" : ""));
   Journal("WEEK", 0, 0, 0, 0, g.week_R, IntegerToString(g.week_n) + " trades");
   g.week_R = 0; g.week_n = 0; g.week_sent_utc = now;
   SaveState();
  }

void Process()
  {
   MqlTick k;
   if(!SymbolInfoTick(_Symbol, k) || k.bid <= 0 || k.ask <= 0) return;
   datetime now = NowUTC();
   // 1) nouvelle bougie M1 -> mise a jour du suiveur
   datetime m1 = iTime(_Symbol, PERIOD_M1, 0);
   if(m1 != 0 && m1 != g_last_m1)
     {
      if(g_last_m1 != 0) OnNewM1();
      g_last_m1 = m1;
     }
   // 2) nouvelle bougie H4 (grille UTC) -> nouveaux niveaux si aucune position
   datetime bucket = BucketUTC(now);
   if(bucket != g_bucket)
     {
      g_bucket = bucket;
      NewBracket(bucket);
     }
   // 3) position en cours : stop / suiveur / sortie au temps
   if(g.side > 0)
     {
      if(k.bid <= g.stop) Exit(k.bid, g.stop > g.init_stop ? "suiveur" : "stop");
      else if(now >= g.deadline_utc) Exit(k.bid, "temps");
     }
   else if(g.side < 0)
     {
      if(k.ask >= g.stop) Exit(k.ask, g.stop < g.init_stop ? "suiveur" : "stop");
      else if(now >= g.deadline_utc) Exit(k.ask, "temps");
     }
   // 4) aucune position : cassure ?
   else if(g_br_active)
     {
      if(now >= g_br_expiry_utc) g_br_active = false;
      else if(k.ask >= g_br_hi) Enter(1, k.ask);
      else if(k.bid <= g_br_lo) Enter(-1, k.bid);
      else if(InpPreAlertATR > 0)
        {
         if(!g_pre_hi && k.ask >= g_br_hi - InpPreAlertATR * g_br_atr)
           {
            g_pre_hi = true;
            Notify(StringFormat("GoldOrb %s : le prix approche du niveau d'ACHAT %s (ecart %.1f). Preparez-vous.",
                                _Symbol, DoubleToString(g_br_hi, _Digits), g_br_hi - k.ask));
           }
         if(!g_pre_lo && k.bid <= g_br_lo + InpPreAlertATR * g_br_atr)
           {
            g_pre_lo = true;
            Notify(StringFormat("GoldOrb %s : le prix approche du niveau de VENTE %s (ecart %.1f). Preparez-vous.",
                                _Symbol, DoubleToString(g_br_lo, _Digits), k.bid - g_br_lo));
           }
        }
     }
   WeeklySummary();
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(StringFind(_Symbol, "XAU") < 0 && StringFind(_Symbol, "GOLD") < 0)
      Print("GoldOrb: attention, regle testee uniquement sur l'or (XAUUSD). Symbole actuel : ", _Symbol);
   FolderCreate("GoldOrb", FILE_COMMON);
   LoadState();
   g_trade.SetExpertMagicNumber(InpMagic);
   g_auto = (InpMode == GO_AUTO);
   if(g_auto && AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL && !InpAllowAutoReal)
     {
      g_auto = false;
      Notify("GoldOrb: mode automatique refuse sur compte REEL (InpAllowAutoReal=false). Passage en mode alertes.");
     }
   if(InpServerTZ == GO_TZ_NY_CLOSE && !MQLInfoInteger(MQL_TESTER))
     {
      long d = (long)TimeTradeServer() - (long)TimeGMT();
      int expected = ServerOffsetSec(TimeTradeServer());
      if(MathAbs(d - expected) > 1800)
         Print("GoldOrb: ATTENTION le decalage serveur mesure (", d / 3600.0, " h) differe de l'hypothese 17h New York (",
               expected / 3600, " h). Choisissez InpServerTZ = Automatique ou Fixe.");
     }
   EventSetTimer(30);
   Print("GoldOrb demarre. Mode ", EnumToString(InpMode), " | position fictive : ", g.side,
         " | cumul ", DoubleToString(g.cum_R, 2), " R sur ", g.n_trades, " trades");
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   SaveState();
  }

void OnTick()  { Process(); }
void OnTimer() { Process(); }

// Mode auto : quand un ordre en attente est execute, on aligne la position fictive sur le vrai prix
void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
  {
   if(!g_auto || trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
   if(!HistoryDealSelect(trans.deal)) return;
   if(HistoryDealGetString(trans.deal, DEAL_SYMBOL) != _Symbol) return;
   if(HistoryDealGetInteger(trans.deal, DEAL_MAGIC) != InpMagic) return;
   if(HistoryDealGetInteger(trans.deal, DEAL_ENTRY) != DEAL_ENTRY_IN) return;
   long dtype = HistoryDealGetInteger(trans.deal, DEAL_TYPE);
   int side = (dtype == DEAL_TYPE_BUY) ? 1 : -1;
   double px = HistoryDealGetDouble(trans.deal, DEAL_PRICE);
   DeletePendings();
   if(g.side == 0) Enter(side, px);
   else if(g.side == side)
     {
      // la position fictive a deja ete ouverte sur ce tick : on recale sur le prix reel
      g.fill = px;
      g.init_stop = px - side * InpStopATR * g.atr;
      g.stop = g.init_stop;
      g.best = px;
      SaveState();
     }
   SyncRealStop();
  }
//+------------------------------------------------------------------+
