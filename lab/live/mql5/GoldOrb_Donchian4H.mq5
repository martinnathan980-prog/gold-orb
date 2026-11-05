//+------------------------------------------------------------------+
//|                                          GoldOrb_Donchian4H.mq5  |
//|  Cassure du canal 10 jours (60 bougies H4, grille UTC) - XAUUSD   |
//|  Regle du laboratoire : lab/tracks/trend, finaliste donch4h_stop. |
//|                                                                  |
//|  v2 - moteur "papier" identique au simulateur du labo :          |
//|  il traite chaque bougie M1 FERMEE avec les memes regles de       |
//|  remplissage (stop au pire du niveau / de l'ouverture, stop       |
//|  suiveur mis a jour apres la cloture de la bougie, sortie au      |
//|  temps a l'ouverture). Le meme code sert au rattrapage apres une  |
//|  coupure (REPLAY).                                                |
//|                                                                  |
//|  Modes : 0 = ALERTES + JOURNAL (defaut, aucun ordre)             |
//|          1 = alertes + gestion de VOTRE position manuelle         |
//|              (stop initial, stop suiveur, sortie au temps)        |
//|          2 = AUTOMATIQUE (ordres stop OCO chez le courtier ;      |
//|              compte DEMO uniquement sauf InpAllowAutoReal)        |
//+------------------------------------------------------------------+
#property copyright "gold-orb lab"
#property version   "2.00"
#property description "Cassure du canal 10 jours (H4 UTC) sur l'or. Mode observation par defaut. Regle non validee en reel."

#include <Trade\Trade.mqh>

enum ENUM_GO_MODE
  {
   GO_ALERTS = 0,        // Alertes + journal (aucun ordre)
   GO_MANAGE_MANUAL = 1, // Alertes + gestion de ma position manuelle
   GO_AUTO = 2           // Automatique (DEMO par defaut)
  };

enum ENUM_GO_TZ
  {
   GO_TZ_US = 0,         // Serveur = New York + 7h (UTC+2 / UTC+3 selon l'heure d'ete US) - le plus courant
   GO_TZ_EU = 1,         // Serveur UTC+2 / UTC+3 selon l'heure d'ete EUROPEENNE (EET)
   GO_TZ_FIXED = 2       // Decalage fixe toute l'annee
  };

input ENUM_GO_MODE InpMode          = GO_ALERTS;   // Mode
input ENUM_GO_TZ   InpServerTZ      = GO_TZ_US;    // Fuseau horaire du serveur du courtier
input int          InpFixedOffsetH  = 2;           // Decalage fixe serveur - UTC (heures), si "fixe"
input int          InpChannelBars   = 60;          // Bougies H4 du canal (60 = 10 jours)
input int          InpATRPeriod     = 14;          // ATR Wilder (H4)
input double       InpStopATR       = 2.0;         // Stop initial (x ATR)
input double       InpTrailATR      = 2.0;         // Stop suiveur (x ATR)
input int          InpMaxDays       = 5;           // Duree max (jours de bourse New York)
input double       InpRiskPct       = 0.5;         // Risque par trade (% du capital) pour la taille
input double       InpMaxRiskMult   = 1.5;         // Bloquer si le lot minimum risque plus que X fois le risque vise
input bool         InpNotifyLevels  = true;        // Notifier les niveaux a chaque cloture H4 (heures eveillees)
input int          InpWakeFrom      = 7;           // Heures eveillees : debut (heure de Paris)
input int          InpWakeTo        = 23;          // Heures eveillees : fin (heure de Paris)
input bool         InpPush          = true;        // Notifications push (appli MT5 mobile)
input bool         InpPopup         = true;        // Fenetre d'alerte dans le terminal
input string       InpTgToken       = "";          // Telegram : token du bot (optionnel)
input string       InpTgChat        = "";          // Telegram : chat_id (optionnel)
input bool         InpAllowAutoReal = false;       // Autoriser le mode auto sur compte REEL (deconseille)
input long         InpMagic         = 20261105;    // Numero magique (mode auto)
input long         InpManualMagic   = 0;           // Numero magique de vos positions manuelles (0 = manuel)
input int          InpHistoryDays   = 180;         // Historique M5 charge (>= 640 bougies H4)
input bool         InpLogSpread     = true;        // Journaliser l'ecart 16:45-18:30 New York

#define SLIP_NONE 0.0

//--- etat persistant (fichier binaire)
struct GoState
  {
   // position papier
   int               side;
   double            fill, stop, init_stop, trail, best, atr;
   datetime          entry_utc, deadline_utc, decision_utc;
   long              fill_bar;          // heure serveur de la bougie M1 d'entree
   // niveaux (bracket) de la fenetre H4 en cours
   int               br_active;
   double            br_hi, br_lo, br_atr;
   datetime          br_decision_utc, br_expiry_utc;
   int               br_trigger_sent;
   // reel (modes 1 et 2)
   ulong             real_ticket;
   double            real_fill, real_best, real_D;
   datetime          real_deadline_utc;
   int               real_side;
   // tenue de compte
   datetime          last_m1;           // derniere bougie M1 traitee (heure serveur d'ouverture)
   datetime          last_bucket_utc;   // derniere decision H4 traitee
   double            cum_R, week_R;
   int               n_trades, week_n;
   datetime          week_sent_utc, heartbeat_utc;
  };

GoState  g;
bool     g_auto = false;
bool     g_replay = false;
CTrade   g_trade;
string   g_queue[];                     // messages Telegram en attente (envoyes dans OnTimer)

//+------------------------------------------------------------------+
//| Temps                                                            |
//+------------------------------------------------------------------+
datetime NthSunday(const int year, const int month, const int n)
  {
   MqlDateTime d;
   ZeroMemory(d);
   d.year = year; d.mon = month; d.day = 1;
   MqlDateTime x;
   TimeToStruct(StructToTime(d), x);
   int first = (x.day_of_week == 0) ? 1 : 1 + (7 - x.day_of_week);
   d.day = first + 7 * (n - 1);
   return StructToTime(d);
  }

datetime LastSunday(const int year, const int month)
  {
   MqlDateTime d;
   ZeroMemory(d);
   d.year = year; d.mon = month + 1; d.day = 1;
   if(d.mon == 13) { d.mon = 1; d.year = year + 1; }
   datetime t = StructToTime(d) - 86400;          // dernier jour du mois
   MqlDateTime x;
   TimeToStruct(t, x);
   return t - x.day_of_week * 86400;
  }

// heure d'ete US : 2e dimanche de mars 07:00 UTC -> 1er dimanche de novembre 06:00 UTC
bool IsUSDST(const datetime utc)
  {
   MqlDateTime x;
   TimeToStruct(utc, x);
   return (utc >= NthSunday(x.year, 3, 2) + 7 * 3600 && utc < NthSunday(x.year, 11, 1) + 6 * 3600);
  }

// heure d'ete UE : dernier dimanche de mars 01:00 UTC -> dernier dimanche d'octobre 01:00 UTC
bool IsEUDST(const datetime utc)
  {
   MqlDateTime x;
   TimeToStruct(utc, x);
   return (utc >= LastSunday(x.year, 3) + 3600 && utc < LastSunday(x.year, 10) + 3600);
  }

int RuleOffsetSecForUTC(const datetime utc)
  {
   if(InpServerTZ == GO_TZ_FIXED) return InpFixedOffsetH * 3600;
   if(InpServerTZ == GO_TZ_EU) return IsEUDST(utc) ? 3 * 3600 : 2 * 3600;
   return IsUSDST(utc) ? 3 * 3600 : 2 * 3600;
  }

datetime ToUTC(const datetime server_time)
  {
   // les changements d'heure ont lieu le dimanche, marche ferme : l'approximation est exacte
   return server_time - RuleOffsetSecForUTC(server_time - 2 * 3600);
  }
datetime ToServer(const datetime utc)     { return utc + RuleOffsetSecForUTC(utc); }
datetime NYfromUTC(const datetime utc)    { return utc - (IsUSDST(utc) ? 4 : 5) * 3600; }
datetime UTCfromNY(const datetime ny)     { return ny + (IsUSDST(ny + 5 * 3600) ? 4 : 5) * 3600; }
datetime ParisFromUTC(const datetime utc) { return utc + (IsEUDST(utc) ? 2 : 1) * 3600; }

// = labo : heure de New York + 7h, + N jours ouvres, - 7h, - 5 min ; si cela tombe dans la
// pause 17:00-18:00 New York ou le week-end : derniere minute avant la fermeture (16:59 NY).
datetime DeadlineUTC(const datetime decision_utc, const int days)
  {
   datetime td = NYfromUTC(decision_utc) + 7 * 3600;
   int added = 0;
   while(added < days)
     {
      td += 86400;
      MqlDateTime x;
      TimeToStruct(td, x);
      if(x.day_of_week >= 1 && x.day_of_week <= 5) added++;
     }
   datetime ny = td - 7 * 3600 - 300;
   MqlDateTime y;
   TimeToStruct(ny, y);
   int mins = y.hour * 60 + y.min;
   bool weekend = (y.day_of_week == 6) || (y.day_of_week == 0 && mins < 18 * 60) || (y.day_of_week == 5 && mins >= 17 * 60);
   bool brk = (mins >= 17 * 60 && mins < 18 * 60);
   if(weekend)
     {
      while(true)
        {
         MqlDateTime z;
         TimeToStruct(ny, z);
         if(z.day_of_week == 5) break;
         ny -= 86400;
        }
     }
   if(weekend || brk)
     {
      MqlDateTime w;
      TimeToStruct(ny, w);
      w.hour = 16; w.min = 59; w.sec = 0;
      ny = StructToTime(w);
     }
   return UTCfromNY(ny);
  }

datetime BucketUTC(const datetime utc) { return (datetime)(((long)utc / 14400) * 14400); }

string Clocks(const datetime utc)
  {
   return TimeToString(utc, TIME_DATE | TIME_MINUTES) + " UTC / " + TimeToString(ParisFromUTC(utc), TIME_MINUTES) + " Paris";
  }

//+------------------------------------------------------------------+
//| Notifications (push et popup immediats ; Telegram via OnTimer)    |
//+------------------------------------------------------------------+
string JsonEscape(string s)
  {
   StringReplace(s, "\\", "\\\\");
   StringReplace(s, "\"", "\\\"");
   StringReplace(s, "\n", "\\n");
   return s;
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
         Print("Push : echec (", GetLastError(), "). Configurez votre MetaQuotes ID : Outils > Options > Notifications.");
     }
   if(InpTgToken != "" && InpTgChat != "")
     {
      int n = ArraySize(g_queue);
      ArrayResize(g_queue, n + 1);
      g_queue[n] = text;
     }
  }

void FlushTelegram()
  {
   if(ArraySize(g_queue) == 0 || MQLInfoInteger(MQL_TESTER)) return;
   string text = g_queue[0];
   string url = "https://api.telegram.org/bot" + InpTgToken + "/sendMessage";
   string body = "{\"chat_id\":\"" + InpTgChat + "\",\"text\":\"" + JsonEscape(text) + "\"}";
   char data[], res[];
   string rh;
   int len = StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
   if(len > 0) ArrayResize(data, len - 1);
   int code = WebRequest("POST", url, "Content-Type: application/json\r\n", 5000, data, res, rh);
   if(code != 200)
      Print("Telegram : echec (code ", code, ", erreur ", GetLastError(),
            "). Ajoutez https://api.telegram.org dans Outils > Options > Expert Advisors > WebRequest.");
   // on retire le message dans tous les cas (pas de boucle infinie)
   int n = ArraySize(g_queue);
   for(int i = 1; i < n; i++) g_queue[i - 1] = g_queue[i];
   ArrayResize(g_queue, n - 1);
  }

//+------------------------------------------------------------------+
//| Journal CSV (dossier commun : %APPDATA%\MetaQuotes\Terminal\     |
//| Common\Files\GoldOrb\)                                           |
//+------------------------------------------------------------------+
string FilePrefix() { return MQLInfoInteger(MQL_TESTER) ? "GoldOrb\\tester_" : "GoldOrb\\"; }

void Journal(const string ev, const datetime t_utc, const int side, const double price, const double stop,
             const double atr, const double R, const string note)
  {
   string fn = FilePrefix() + "journal_" + _Symbol + ".csv";
   int h = FileOpen(fn, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ, ';');
   if(h == INVALID_HANDLE) { Print("Journal : impossible d'ouvrir ", fn, " (", GetLastError(), ")"); return; }
   if(FileSize(h) == 0)
      FileWrite(h, "time_utc", "event", "side", "price", "stop", "atr", "R", "note", "paris", "server", "offset_rule_h", "offset_measured_h", "replay");
   FileSeek(h, 0, SEEK_END);
   double meas = MQLInfoInteger(MQL_TESTER) ? 0.0 : ((double)((long)TimeTradeServer() - (long)TimeGMT())) / 3600.0;
   FileWrite(h, TimeToString(t_utc, TIME_DATE | TIME_MINUTES | TIME_SECONDS), ev, side,
             DoubleToString(price, _Digits), DoubleToString(stop, _Digits), DoubleToString(atr, _Digits),
             DoubleToString(R, 3), note,
             TimeToString(ParisFromUTC(t_utc), TIME_DATE | TIME_MINUTES),
             TimeToString(ToServer(t_utc), TIME_DATE | TIME_MINUTES),
             DoubleToString(RuleOffsetSecForUTC(t_utc) / 3600.0, 1), DoubleToString(meas, 2),
             g_replay ? 1 : 0);
   FileClose(h);
  }

void SaveState()
  {
   int h = FileOpen(FilePrefix() + "state_" + _Symbol + ".bin", FILE_WRITE | FILE_BIN | FILE_COMMON);
   if(h == INVALID_HANDLE) return;
   FileWriteStruct(h, g);
   FileClose(h);
  }

bool LoadState()
  {
   ZeroMemory(g);
   string fn = FilePrefix() + "state_" + _Symbol + ".bin";
   if(MQLInfoInteger(MQL_TESTER) || !FileIsExist(fn, FILE_COMMON)) return false;
   int h = FileOpen(fn, FILE_READ | FILE_BIN | FILE_COMMON);
   if(h == INVALID_HANDLE) return false;
   uint n = FileReadStruct(h, g);
   FileClose(h);
   if(n != sizeof(GoState)) { ZeroMemory(g); return false; }   // version d'etat differente
   return true;
  }

//+------------------------------------------------------------------+
//| Bougies H4 (grille UTC, prix milieu) depuis le M5 du courtier     |
//+------------------------------------------------------------------+
struct Bar4 { datetime t; double o, h, l, c; };

int Build4H(Bar4 &out[], const datetime upto_bucket)
  {
   MqlRates r[];
   ArraySetAsSeries(r, false);
   ArrayResize(out, 0);
   int n = CopyRates(_Symbol, PERIOD_M5, 0, InpHistoryDays * 288, r);
   if(n <= 0) return -1;
   int k = -1;
   datetime cur = 0;
   for(int i = 0; i < n; i++)
     {
      datetime b = BucketUTC(ToUTC(r[i].time));
      if(b >= upto_bucket) break;
      double hs = r[i].spread * _Point * 0.5;
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
//| Taille de position                                               |
//+------------------------------------------------------------------+
double LotsForRisk(const double stop_dist, string &msg, bool &over_risk)
  {
   over_risk = false;
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tick_val = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tick_val <= 0) tick_val = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vstep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(eq <= 0 || tick_size <= 0 || tick_val <= 0 || vstep <= 0 || stop_dist <= 0) { msg = "lot n/d"; return 0.0; }
   double loss_per_lot = stop_dist / tick_size * tick_val;
   double lots = MathFloor(eq * InpRiskPct / 100.0 / loss_per_lot / vstep + 1e-9) * vstep;
   if(lots < vmin)
     {
      double pct = vmin * loss_per_lot / eq * 100.0;
      over_risk = (pct > InpMaxRiskMult * InpRiskPct);
      msg = StringFormat("lot min %.2f = %.1f%% du capital%s", vmin, pct, over_risk ? " (TROP RISQUE)" : "");
      return vmin;
     }
   lots = MathMin(lots, vmax);
   msg = StringFormat("lot %.2f (%.2f%%)", lots, InpRiskPct);
   return lots;
  }

//+------------------------------------------------------------------+
//| Moteur papier - une bougie M1 fermee a la fois (regles du labo)   |
//+------------------------------------------------------------------+
void PaperExit(const double price, const datetime t_utc, const string why)
  {
   double risk = MathAbs(g.fill - g.init_stop);
   double R = (risk > 0) ? g.side * (price - g.fill) / risk : 0.0;
   g.cum_R += R; g.n_trades++;
   g.week_R += R; g.week_n++;
   Journal("EXIT", t_utc, g.side, price, g.stop, g.atr, R, why);
   string txt = StringFormat("GoldOrb %s SORTIE %s (%s) %s a %s : %+.2f R | cumul %+.1f R / %d trades%s",
                             _Symbol, g.side > 0 ? "achat" : "vente", why, Clocks(t_utc),
                             DoubleToString(price, _Digits), R, g.cum_R, g.n_trades, g_replay ? " [rattrapage]" : "");
   if(!g_replay) Notify(txt); else Print(txt);
   g.side = 0;
  }

void PaperEnter(const int side, const double price, const datetime t_utc, const datetime bar_time)
  {
   g.side = side;
   g.fill = price;
   g.atr = g.br_atr;
   g.trail = InpTrailATR * g.br_atr;
   g.init_stop = price - side * InpStopATR * g.br_atr;
   g.stop = g.init_stop;
   g.best = price;
   g.entry_utc = t_utc;
   g.decision_utc = g.br_decision_utc;
   g.deadline_utc = DeadlineUTC(g.br_decision_utc, InpMaxDays);
   g.fill_bar = (long)bar_time;
   g.br_active = 0;
   Journal("ENTRY", t_utc, side, price, g.init_stop, g.atr, 0, "deadline " + TimeToString(g.deadline_utc, TIME_DATE | TIME_MINUTES));
   if(g_replay) return;
   string m;
   bool over;
   LotsForRisk(MathAbs(price - g.init_stop), m, over);
   Notify(StringFormat("GoldOrb %s %s ~%s | stop %s (%.1f) | suiveur %.1f | sortie max %s | %s | REGLE NON VALIDEE EN REEL",
                       _Symbol, side > 0 ? "CASSURE HAUSSE: ACHAT" : "CASSURE BAISSE: VENTE",
                       DoubleToString(price, _Digits), DoubleToString(g.init_stop, _Digits), MathAbs(price - g.init_stop),
                       g.trail, Clocks(g.deadline_utc), m));
  }

// Une bougie M1 fermee (b = prix BID, spread en points) ; t_utc = heure d'ouverture en UTC
void ProcessBar(const MqlRates &b, const datetime t_utc)
  {
   double spr = b.spread * _Point;
   double ao = b.open + spr, ah = b.high + spr, al = b.low + spr;
   // 1) position : sortie au temps (a l'ouverture), puis stop, puis mise a jour du suiveur
   if(g.side != 0)
     {
      bool first = ((long)b.time == g.fill_bar);
      if(!first && t_utc >= g.deadline_utc)
        {
         PaperExit(g.side > 0 ? b.open : ao, t_utc, "temps");
        }
      else if(g.side > 0)
        {
         if(b.low <= g.stop)
            PaperExit(first ? g.stop : MathMin(g.stop, b.open), t_utc + 60, g.stop > g.init_stop ? "suiveur" : "stop");
         else
           {
            if(b.high > g.best) g.best = b.high;
            if(g.best - g.trail > g.stop) g.stop = g.best - g.trail;
           }
        }
      else
        {
         if(ah >= g.stop)
            PaperExit(first ? g.stop : MathMax(g.stop, ao), t_utc + 60, g.stop < g.init_stop ? "suiveur" : "stop");
         else
           {
            if(al < g.best) g.best = al;
            if(g.best + g.trail < g.stop) g.stop = g.best + g.trail;
           }
        }
      return;
     }
   // 2) aucune position : cassure dans la fenetre des niveaux ?
   if(g.br_active == 0) return;
   if(t_utc >= g.br_expiry_utc) { g.br_active = 0; return; }
   bool hu = ah >= g.br_hi, hd = b.low <= g.br_lo;
   if(!hu && !hd) return;
   int side = (hu && hd) ? (b.close >= b.open ? -1 : 1) : (hu ? 1 : -1);   // les deux : cote adverse (labo)
   double px = (side > 0) ? MathMax(g.br_hi, ao) : MathMin(g.br_lo, b.open);
   PaperEnter(side, px, t_utc, b.time);
   // meme bougie : le stop peut deja etre touche ; sinon le suiveur part des extremes de la bougie
   if(side > 0)
     {
      if(b.low <= g.stop) PaperExit(g.stop, t_utc + 60, "stop");
      else
        {
         if(b.high > g.best) g.best = b.high;
         if(g.best - g.trail > g.stop) g.stop = g.best - g.trail;
        }
     }
   else
     {
      if(ah >= g.stop) PaperExit(g.stop, t_utc + 60, "stop");
      else
        {
         if(al < g.best) g.best = al;
         if(g.best + g.trail < g.stop) g.stop = g.best + g.trail;
        }
     }
  }

//+------------------------------------------------------------------+
//| Decision H4 : niveaux si aucune position                         |
//+------------------------------------------------------------------+
bool OffsetOK()
  {
   if(MQLInfoInteger(MQL_TESTER)) return true;
   long meas = (long)TimeTradeServer() - (long)TimeGMT();
   long rule = RuleOffsetSecForUTC(TimeGMT());
   if(MathAbs(meas - rule) <= 1800) return true;
   Notify(StringFormat("GoldOrb OFFSET_WARN : decalage serveur mesure %.1f h, regle choisie %.1f h. Aucun niveau arme. Verifiez InpServerTZ.",
                       meas / 3600.0, rule / 3600.0));
   Journal("OFFSET_WARN", TimeGMT(), 0, 0, 0, 0, 0, StringFormat("measured %.2f rule %.2f", meas / 3600.0, rule / 3600.0));
   return false;
  }

bool Decide(const datetime bucket)
  {
   g.br_active = 0;
   g.br_trigger_sent = 0;
   if(g.side != 0 || g.real_ticket != 0) return true;           // une seule position a la fois
   if(!g_replay && !OffsetOK()) return true;
   Bar4 b[];
   int n = Build4H(b, bucket);
   if(n < InpChannelBars + InpATRPeriod + 2)
     {
      Journal("DATA_WARN", bucket, 0, 0, 0, 0, 0, "4h bars " + IntegerToString(n));
      return false;                                              // on reessaiera a la bougie suivante
     }
   double hi = -DBL_MAX, lo = DBL_MAX;
   for(int i = n - InpChannelBars; i < n; i++)
     {
      if(b[i].h > hi) hi = b[i].h;
      if(b[i].l < lo) lo = b[i].l;
     }
   double atr = WilderATR(b, n, InpATRPeriod);
   if(atr <= 0) return false;
   g.br_hi = hi; g.br_lo = lo; g.br_atr = atr;
   g.br_decision_utc = bucket;
   g.br_expiry_utc = bucket + 14400;
   g.br_active = 1;
   Journal("LEVELS", bucket, 0, hi, lo, atr, 0, "until " + TimeToString(g.br_expiry_utc, TIME_DATE | TIME_MINUTES));
   if(!g_replay)
     {
      MqlDateTime p;
      TimeToStruct(ParisFromUTC(bucket), p);
      if(InpNotifyLevels && p.hour >= InpWakeFrom && p.hour < InpWakeTo)
         Notify(StringFormat("GoldOrb %s niveaux jusqu'a %s Paris : achat > %s | vente < %s | stop %.1f",
                             _Symbol, TimeToString(ParisFromUTC(g.br_expiry_utc), TIME_MINUTES),
                             DoubleToString(hi, _Digits), DoubleToString(lo, _Digits), InpStopATR * atr));
      if(g_auto) PlacePendings();
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Reel : mode 2 (ordres) et mode 1 (gestion de la position manuelle)|
//+------------------------------------------------------------------+
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
   DeletePendings();
   string m;
   bool over;
   double D = InpStopATR * g.br_atr;
   double lots = LotsForRisk(D, m, over);
   if(lots <= 0 || over)
     {
      Notify("GoldOrb : niveaux non places (" + m + "). Augmentez le capital ou baissez le risque.");
      Journal("SKIP_SIZE", TimeGMT(), 0, 0, 0, g.br_atr, 0, m);
      return;
     }
   MqlTick k;
   if(!SymbolInfoTick(_Symbol, k)) return;
   double lvl = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   long emode = SymbolInfoInteger(_Symbol, SYMBOL_EXPIRATION_MODE);
   bool spec = (emode & SYMBOL_EXPIRATION_SPECIFIED) != 0;
   ENUM_ORDER_TYPE_TIME tt = spec ? ORDER_TIME_SPECIFIED : ORDER_TIME_GTC;
   datetime exp = spec ? ToServer(g.br_expiry_utc) : 0;
   double hi = NormalizeDouble(g.br_hi, _Digits), lo = NormalizeDouble(g.br_lo, _Digits);
   // prix deja au-dela d'un niveau (gap, ouverture du dimanche) : entree au marche, comme le labo
   if(k.ask >= hi) { g_trade.Buy(lots, _Symbol, 0, NormalizeDouble(k.ask - D, _Digits), 0, "GoldOrb L mkt"); return; }
   if(k.bid <= lo) { g_trade.Sell(lots, _Symbol, 0, NormalizeDouble(k.bid + D, _Digits), 0, "GoldOrb S mkt"); return; }
   if(hi > k.ask + lvl) g_trade.BuyStop(lots, hi, _Symbol, NormalizeDouble(hi - D, _Digits), 0, tt, exp, "GoldOrb L");
   else Journal("STOPSLEVEL", TimeGMT(), 1, hi, 0, 0, 0, "buy level too close: virtual market entry on touch");
   if(lo < k.bid - lvl) g_trade.SellStop(lots, lo, _Symbol, NormalizeDouble(lo + D, _Digits), 0, tt, exp, "GoldOrb S");
   else Journal("STOPSLEVEL", TimeGMT(), -1, lo, 0, 0, 0, "sell level too close: virtual market entry on touch");
  }

bool RealPositionSelected()
  {
   if(g.real_ticket == 0) return false;
   if(!PositionSelectByTicket(g.real_ticket)) { g.real_ticket = 0; return false; }   // fermee (stop touche...)
   return true;
  }

// mode 1 : rattache la premiere position manuelle du meme sens ouverte autour du signal
void BindManualPosition()
  {
   if(InpMode != GO_MANAGE_MANUAL || g.side == 0 || g.real_ticket != 0) return;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || !PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != InpManualMagic) continue;
      int side = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
      datetime opened = ToUTC((datetime)PositionGetInteger(POSITION_TIME));
      if(side != g.side || opened < g.entry_utc - 600 || opened > g.entry_utc + 6 * 3600) continue;
      g.real_ticket = t;
      g.real_side = side;
      g.real_fill = PositionGetDouble(POSITION_PRICE_OPEN);
      g.real_best = g.real_fill;
      g.real_D = InpStopATR * g.atr;
      g.real_deadline_utc = g.deadline_utc;
      Journal("REAL_BIND", TimeGMT(), side, g.real_fill, g.real_fill - side * g.real_D, g.atr, 0, IntegerToString((long)t));
      Notify(StringFormat("GoldOrb : position #%I64u prise en charge (stop %.2f, suiveur %.1f, sortie %s).",
                          t, g.real_fill - side * g.real_D, g.real_D, Clocks(g.real_deadline_utc)));
      return;
     }
  }

void RealOnBar(const MqlRates &b, const datetime t_utc)
  {
   if(InpMode == GO_ALERTS || !RealPositionSelected()) return;
   double spr = b.spread * _Point;
   if(g.real_side > 0) { if(b.high > g.real_best) g.real_best = b.high; }
   else { if(b.low + spr < g.real_best) g.real_best = b.low + spr; }
   double want = NormalizeDouble(g.real_best - g.real_side * g.real_D, _Digits);
   double sl = PositionGetDouble(POSITION_SL), tp = PositionGetDouble(POSITION_TP);
   double init = NormalizeDouble(g.real_fill - g.real_side * g.real_D, _Digits);
   if(sl == 0.0) want = (g.real_side > 0) ? MathMax(want, init) : MathMin(want, init);
   bool tighter = (sl == 0.0) || (g.real_side > 0 && want > sl + _Point) || (g.real_side < 0 && want < sl - _Point);
   if(!tighter) return;
   MqlTick k;
   if(!SymbolInfoTick(_Symbol, k)) return;
   double lvl = (double)MathMax(SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL),
                                SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL)) * _Point;
   if(g.real_side > 0 && want > k.bid - lvl) return;   // trop pres : nouvel essai a la minute suivante
   if(g.real_side < 0 && want < k.ask + lvl) return;
   if(g_trade.PositionModify(g.real_ticket, want, tp))
      Journal("REAL_SL_MOD", t_utc, g.real_side, want, sl, g.real_D, 0, "");
  }

void RealTimeExit()
  {
   if(InpMode == GO_ALERTS || !RealPositionSelected()) return;
   datetime now = ToUTC(TimeCurrent());
   if(now < g.real_deadline_utc) return;
   if(g_trade.PositionClose(g.real_ticket))
     {
      Journal("REAL_CLOSE", now, g.real_side, 0, 0, 0, 0, "time");
      g.real_ticket = 0;
     }
   else
      Notify("GoldOrb : fermeture au temps refusee (" + g_trade.ResultRetcodeDescription() + "). Fermez manuellement.");
  }

//+------------------------------------------------------------------+
//| Boucle : traite toutes les bougies M1 fermees non encore vues     |
//+------------------------------------------------------------------+
void CatchUp()
  {
   datetime cur = iTime(_Symbol, PERIOD_M1, 0);
   if(cur == 0) return;
   if(g.last_m1 == 0) { g.last_m1 = cur - 60; g.last_bucket_utc = BucketUTC(ToUTC(cur)); return; }  // 1er lancement
   if(cur <= g.last_m1 + 60) return;
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(_Symbol, PERIOD_M1, g.last_m1 + 60, cur - 60, r);
   if(n <= 0) return;
   g_replay = (cur - g.last_m1 > 5 * 60);       // plus de quelques minutes de retard : rattrapage
   if(g_replay) Journal("REPLAY", ToUTC(cur), 0, 0, 0, 0, 0, IntegerToString(n) + " M1 bars");
   for(int i = 0; i < n; i++)
     {
      if(r[i].time <= g.last_m1) continue;
      datetime t_utc = ToUTC(r[i].time);
      datetime bucket = BucketUTC(t_utc);
      if(bucket != g.last_bucket_utc)
        {
         if(Decide(bucket)) g.last_bucket_utc = bucket;            // sinon on reessaiera a la bougie suivante
        }
      ProcessBar(r[i], t_utc);
      RealOnBar(r[i], t_utc);
      if(InpLogSpread && !g_replay)
        {
         MqlDateTime x;
         TimeToStruct(NYfromUTC(t_utc), x);
         int mm = x.hour * 60 + x.min;
         if(mm >= 16 * 60 + 45 && mm <= 18 * 60 + 30)
            Journal("SPREAD", t_utc, 0, r[i].close, 0, 0, 0, DoubleToString(r[i].spread * _Point, 3));
        }
      g.last_m1 = r[i].time;
     }
   if(g_replay)
     {
      g_replay = false;
      Notify(StringFormat("GoldOrb : rattrapage de %d minutes termine. Position papier : %s.", n,
                          g.side == 0 ? "aucune" : (g.side > 0 ? "achat" : "vente")));
     }
   SaveState();
  }

void TickTrigger()
  {
   // alerte instantanee au franchissement (la position papier est enregistree a la cloture M1)
   if(g.side != 0 || g.br_active == 0 || g.br_trigger_sent != 0) return;
   MqlTick k;
   if(!SymbolInfoTick(_Symbol, k)) return;
   if(k.ask >= g.br_hi || k.bid <= g.br_lo)
     {
      g.br_trigger_sent = 1;
      int side = (k.ask >= g.br_hi) ? 1 : -1;
      string m;
      bool over;
      LotsForRisk(InpStopATR * g.br_atr, m, over);
      Notify(StringFormat("GoldOrb %s CASSURE %s maintenant (%s) | stop a %.1f du prix d'entree | %s",
                          _Symbol, side > 0 ? "HAUSSIERE : achat" : "BAISSIERE : vente",
                          DoubleToString(side > 0 ? k.ask : k.bid, _Digits), InpStopATR * g.br_atr, m));
      BindManualPosition();
     }
  }

void Housekeeping()
  {
   datetime now = ToUTC(TimeCurrent());
   MqlDateTime x;
   TimeToStruct(now, x);
   if(x.day_of_week == 5 && x.hour >= 20 && now - g.week_sent_utc > 3 * 86400)
     {
      Notify(StringFormat("GoldOrb %s semaine : %d trade(s) %+.2f R | cumul %+.1f R / %d trades%s",
                          _Symbol, g.week_n, g.week_R, g.cum_R, g.n_trades, g.side != 0 ? " | position ouverte" : ""));
      Journal("WEEK", now, 0, 0, 0, 0, g.week_R, IntegerToString(g.week_n));
      g.week_R = 0; g.week_n = 0; g.week_sent_utc = now;
     }
   if(now - g.heartbeat_utc > 86400)
     {
      Journal("HEARTBEAT", now, g.side, g.stop, 0, 0, g.cum_R, g.br_active ? "levels armed" : "");
      g.heartbeat_utc = now;
     }
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(StringFind(_Symbol, "XAU") < 0 && StringFind(_Symbol, "GOLD") < 0)
      Print("GoldOrb : attention, regle testee uniquement sur l'or (XAUUSD). Symbole : ", _Symbol);
   FolderCreate("GoldOrb", FILE_COMMON);
   bool had = LoadState();
   g_trade.SetExpertMagicNumber((ulong)InpMagic);
   g_auto = (InpMode == GO_AUTO);
   if(g_auto && AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL && !InpAllowAutoReal)
     {
      g_auto = false;
      Notify("GoldOrb : mode automatique refuse sur compte REEL (InpAllowAutoReal = false). Mode alertes.");
     }
   EventSetTimer(2);
   Print("GoldOrb v2 demarre. Mode ", EnumToString(InpMode), had ? " | etat recharge" : " | nouvel etat",
         " | position papier ", g.side, " | cumul ", DoubleToString(g.cum_R, 2), " R / ", g.n_trades, " trades");
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   SaveState();
  }

void OnTick()
  {
   CatchUp();
   TickTrigger();
   RealTimeExit();
  }

void OnTimer()
  {
   CatchUp();
   Housekeeping();
   FlushTelegram();
  }

// Mode auto : sur execution d'un ordre stop -> annule l'autre, recale le stop sur le vrai prix
void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
  {
   if(!g_auto || trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
   if(!HistoryDealSelect(trans.deal)) return;
   if(HistoryDealGetString(trans.deal, DEAL_SYMBOL) != _Symbol) return;
   if(HistoryDealGetInteger(trans.deal, DEAL_MAGIC) != InpMagic) return;
   if(HistoryDealGetInteger(trans.deal, DEAL_ENTRY) != DEAL_ENTRY_IN) return;
   int side = (HistoryDealGetInteger(trans.deal, DEAL_TYPE) == DEAL_TYPE_BUY) ? 1 : -1;
   ulong pos = (ulong)HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);
   DeletePendings();
   if(g.real_ticket != 0 && g.real_ticket != pos)
     {
      // les deux ordres ont ete executes : on ferme le second immediatement
      g_trade.PositionClose(pos);
      Journal("REAL_CLOSE", TimeGMT(), side, 0, 0, 0, 0, "second OCO leg");
      return;
     }
   g.real_ticket = pos;
   g.real_side = side;
   g.real_fill = HistoryDealGetDouble(trans.deal, DEAL_PRICE);
   g.real_best = g.real_fill;
   g.real_D = InpStopATR * g.br_atr;
   g.real_deadline_utc = DeadlineUTC(g.br_decision_utc, InpMaxDays);
   Journal("REAL_FILL", TimeGMT(), side, g.real_fill, g.real_fill - side * g.real_D, g.br_atr, 0, IntegerToString((long)pos));
   if(PositionSelectByTicket(pos))
      g_trade.PositionModify(pos, NormalizeDouble(g.real_fill - side * g.real_D, _Digits), PositionGetDouble(POSITION_TP));
   SaveState();
  }
//+------------------------------------------------------------------+
