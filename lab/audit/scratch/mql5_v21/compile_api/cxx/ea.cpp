//+------------------------------------------------------------------+
//|                                          GoldOrb_Donchian4H.mq5  |
//|  Cassure du canal 10 jours (60 bougies H4, grille UTC) - XAUUSD   |
//|  Regle du laboratoire : lab/tracks/trend, finaliste donch4h_stop. |
//|                                                                  |
//|  v2.1 - moteur "papier" identique au simulateur du labo (verifie |
//|  par le jumeau Python lab/live/ea_twin.py) + corrections de la   |
//|  revue independante (lab/results/review/ea_review.json, F1-F21). |
//|                                                                  |
//|  Modes : 0 = ALERTES + JOURNAL (defaut, aucun ordre)             |
//|          1 = alertes + gestion de VOTRE position manuelle         |
//|              (stop initial, stop suiveur, sortie au temps)        |
//|          2 = AUTOMATIQUE (ordres stop OCO chez le courtier ;      |
//|              compte DEMO uniquement sauf InpAllowAutoReal)        |
//+------------------------------------------------------------------+
// #property copyright "gold-orb lab"
// #property version   "2.10"
// #property description "Cassure du canal 10 jours (H4 UTC) sur l'or. Mode observation par defaut. Regle non validee en reel."

#include "mql5_shim.h"

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

const ENUM_GO_MODE InpMode          = GO_ALERTS;   // Mode
const ENUM_GO_TZ   InpServerTZ      = GO_TZ_US;    // Fuseau horaire du serveur du courtier
const int          InpFixedOffsetH  = 2;           // Decalage fixe serveur - UTC (heures), si "fixe"
const int          InpChannelBars   = 60;          // Bougies H4 du canal (60 = 10 jours)
const int          InpATRPeriod     = 14;          // ATR Wilder (H4)
const double       InpStopATR       = 2.0;         // Stop initial (x ATR)
const double       InpTrailATR      = 2.0;         // Stop suiveur (x ATR)
const int          InpMaxDays       = 5;           // Duree max (jours de bourse New York)
const double       InpRiskPct       = 0.5;         // Risque par trade (% du capital) pour la taille
const double       InpMaxRiskMult   = 1.5;         // Bloquer si le lot minimum risque plus que X fois le risque vise
const bool         InpNotifyLevels  = true;        // Notifier les niveaux a chaque cloture H4 (heures eveillees)
const int          InpWakeFrom      = 7;           // Heures eveillees : debut (heure de Paris)
const int          InpWakeTo        = 23;          // Heures eveillees : fin (heure de Paris)
const bool         InpPush          = true;        // Notifications push (appli MT5 mobile)
const bool         InpPopup         = true;        // Fenetre d'alerte dans le terminal
const string       InpTgToken       = "";          // Telegram : token du bot (optionnel)
const string       InpTgChat        = "";          // Telegram : chat_id (optionnel)
const bool         InpAllowAutoReal = false;       // Autoriser le mode auto sur compte REEL (deconseille)
const long         InpMagic         = 20261105;    // Numero magique (mode auto)
const long         InpManualMagic   = 0;           // Numero magique de vos positions manuelles (0 = manuel)
const int          InpHistoryDays   = 180;         // Historique M5 charge (>= 640 bougies H4)
const bool         InpLogSpread     = true;        // Journaliser l'ecart 16:45-18:30 New York

//--- etat persistant (fichier binaire)
struct GoState
  {
   // position papier
   int               side;
   double            fill, stop, init_stop, trail, best, atr;
   datetime          entry_utc, deadline_utc, decision_utc;
   long              fill_bar;          // heure serveur de la bougie M1 d'entree
   // niveaux de la fenetre H4 en cours
   int               br_active;
   double            br_hi, br_lo, br_atr;
   datetime          br_decision_utc, br_expiry_utc;
   int               br_trigger_sent;
   // reel (modes 1 et 2)
   ulong             real_ticket;
   ulong             real_id;           // POSITION_IDENTIFIER (le ticket peut etre remplace par le serveur)
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
bool     g_ready = false;               // compte connu : etat recharge, garde du mode auto evaluee
string   g_key = "";                    // suffixe des fichiers live : symbole + numero de compte
CTrade   g_trade;
MqlArray<string> g_queue;                     // Telegram en attente (envoye dans OnTimer)
MqlArray<string> g_push;                      // pushs en attente (MT5 : 2/s et 10/min au plus)
datetime g_push_last = 0;
MqlArray<string> g_jbuf;                      // lignes du journal pas encore ecrites (fichier verrouille)
bool     g_vbuy = false, g_vsell = false;   // mode 2 : niveau trop proche pour un ordre stop -> marche au toucher
datetime g_tx_try = 0;                  // dernier essai de sortie au temps
ulong    g_tx_warned = 0;               // position dont l'echec de sortie au temps a deja ete signale
datetime g_tc_bucket = 0, g_tc = 0;     // = labo : cloture de la derniere bougie M1 avant la decision

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

// les changements d'heure ont lieu le dimanche, marche ferme : l'approximation est exacte
datetime ToUTC(const datetime server_time) { return server_time - RuleOffsetSecForUTC(server_time - 2 * 3600); }
datetime ToServer(const datetime utc)      { return utc + RuleOffsetSecForUTC(utc); }
datetime NYfromUTC(const datetime utc)     { return utc - (IsUSDST(utc) ? 4 : 5) * 3600; }
datetime UTCfromNY(const datetime ny)      { return ny + (IsUSDST(ny + 5 * 3600) ? 4 : 5) * 3600; }
datetime ParisFromUTC(const datetime utc)  { return utc + (IsEUDST(utc) ? 2 : 1) * 3600; }

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

// date et heure de PARIS d'abord (l'heure UTC entre parentheses)
string Clocks(const datetime utc)
  {
   return TimeToString(ParisFromUTC(utc), TIME_DATE | TIME_MINUTES) + " Paris (" + TimeToString(utc, TIME_MINUTES) + " UTC)";
  }

//+------------------------------------------------------------------+
//| Notifications : popup immediat ; push et Telegram rythmes        |
//+------------------------------------------------------------------+
string JsonEscape(string s)
  {
   StringReplace(s, "\\", "\\\\");
   StringReplace(s, "\"", "\\\"");
   StringReplace(s, "\n", "\\n");
   return s;
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
   if(InpPush)
     {
      string p = text;
      if(StringLen(p) > 255) p = StringSubstr(p, 0, 252) + "...";
      int q = ArraySize(g_push);
      if(q == 0 && TimeLocal() - g_push_last >= 7) PushNow(p);        // sinon le push MT5 peut etre coupe
      else if(q < 20) { ArrayResize(g_push, q + 1); g_push[q] = p; }   // envoye ensuite par OnTimer
     }
   if(InpTgToken != "" && InpTgChat != "")
     {
      int n = ArraySize(g_queue);
      if(n < 50) { ArrayResize(g_queue, n + 1); g_queue[n] = text; }
      else Print("Telegram : file pleine, message non envoye");
     }
  }

void FlushPush()   // OnTimer : un push en attente toutes les 7 s au plus
  {
   if(ArraySize(g_push) == 0 || TimeLocal() - g_push_last < 7) return;
   PushNow(g_push[0]);
   ArrayRemove(g_push, 0, 1);
  }

void FlushTelegram()   // OnTimer : un message par appel, jamais depuis OnTick
  {
   if(ArraySize(g_queue) == 0 || MQLInfoInteger(MQL_TESTER)) return;
   string text = g_queue[0];
   ArrayRemove(g_queue, 0, 1);        // retire dans tous les cas : pas de boucle infinie
   string url = "https://api.telegram.org/bot" + InpTgToken + "/sendMessage";
   string body = "{\"chat_id\":\"" + InpTgChat + "\",\"text\":\"" + JsonEscape(text) + "\"}";
   MqlArray<char> data, res;
   string rh;
   int len = StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
   if(len > 0) ArrayResize(data, len - 1);
   int code = WebRequest("POST", url, "Content-Type: application/json\r\n", 5000, data, res, rh);
   if(code != 200)
      Print("Telegram : echec (code ", code, ", erreur ", GetLastError(),
            "). Ajoutez https://api.telegram.org dans Outils > Options > Expert Advisors > WebRequest.");
  }

//+------------------------------------------------------------------+
//| Fichiers (dossier commun : %APPDATA%\MetaQuotes\Terminal\Common\ |
//| Files\GoldOrb\) - live : suffixe symbole_compte                   |
//+------------------------------------------------------------------+
string FilePrefix() { return MQLInfoInteger(MQL_TESTER) ? "GoldOrb\\tester_" : "GoldOrb\\"; }
string FileKey()    { return MQLInfoInteger(MQL_TESTER) ? _Symbol : g_key; }

void Journal(const string ev, const datetime t_utc, const int side, const double price, const double stop,
             const double atr, const double R, const string note)
  {
   double meas = MQLInfoInteger(MQL_TESTER) ? 0.0 : ((double)((long)TimeTradeServer() - (long)TimeGMT())) / 3600.0;
   string row = TimeToString(t_utc, TIME_DATE | TIME_MINUTES | TIME_SECONDS) + ";" + ev + ";" + IntegerToString(side) + ";" +
                DoubleToString(price, _Digits) + ";" + DoubleToString(stop, _Digits) + ";" + DoubleToString(atr, _Digits) + ";" +
                DoubleToString(R, 3) + ";" + note + ";" +
                TimeToString(ParisFromUTC(t_utc), TIME_DATE | TIME_MINUTES) + ";" +
                TimeToString(ToServer(t_utc), TIME_DATE | TIME_MINUTES) + ";" +
                DoubleToString(RuleOffsetSecForUTC(t_utc) / 3600.0, 1) + ";" + DoubleToString(meas, 2) + ";" + (g_replay ? "1" : "0");
   int q = ArraySize(g_jbuf);
   if(q < 500) { ArrayResize(g_jbuf, q + 1); g_jbuf[q] = row; }   // gardee si le fichier est verrouille (Excel...)
   string fn = FilePrefix() + "journal_" + FileKey() + ".csv";
   int h = FileOpen(fn, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ, ';');
   if(h == INVALID_HANDLE) { Print("Journal : impossible d'ouvrir ", fn, " (", GetLastError(), "), lignes en attente : ", ArraySize(g_jbuf)); return; }
   if(FileSize(h) == 0)
      FileWrite(h, "time_utc", "event", "side", "price", "stop", "atr", "R", "note", "paris", "server", "offset_rule_h", "offset_measured_h", "replay");
   FileSeek(h, 0, SEEK_END);
   for(int i = 0; i < ArraySize(g_jbuf); i++) FileWrite(h, g_jbuf[i]);
   FileClose(h);
   ArrayResize(g_jbuf, 0);
  }

void SaveState()
  {
   if(MQLInfoInteger(MQL_TESTER) || !g_ready) return;   // le testeur ne relit jamais l'etat
   string fn = FilePrefix() + "state_" + FileKey() + ".bin";
   string tmp = fn + ".tmp";
   int h = FileOpen(tmp, FILE_WRITE | FILE_BIN | FILE_COMMON);
   if(h == INVALID_HANDLE) return;
   bool ok = (FileWriteStruct(h, g) == (uint)sizeof(GoState));
   FileClose(h);
   if(ok) FileMove(tmp, FILE_COMMON, fn, FILE_COMMON | FILE_REWRITE);   // remplacement d'un coup : jamais d'etat a moitie ecrit
  }

bool LoadState()
  {
   ZeroMemory(g);
   string fn = FilePrefix() + "state_" + FileKey() + ".bin";
   if(MQLInfoInteger(MQL_TESTER) || !FileIsExist(fn, FILE_COMMON)) return false;
   int h = FileOpen(fn, FILE_READ | FILE_BIN | FILE_COMMON);
   if(h == INVALID_HANDLE) return false;
   ulong sz = FileSize(h);
   uint n = FileReadStruct(h, g);
   FileClose(h);
   if(n != (uint)sizeof(GoState) || sz != (ulong)sizeof(GoState)) { ZeroMemory(g); return false; }   // autre version d'etat
   return true;
  }

//+------------------------------------------------------------------+
//| Bougies H4 (grille UTC, prix milieu) depuis le M5 du courtier     |
//+------------------------------------------------------------------+
struct Bar4 { datetime t; double o, h, l, c; };

int Build4H(MqlArray<Bar4> &out, const datetime upto_bucket)
  {
   MqlArray<MqlRates> r;
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

double WilderATR(const MqlArray<Bar4> &b, const int n, const int period)
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
//| Taille de position et prix normalises                            |
//+------------------------------------------------------------------+
double NormPrice(const double p)
  {
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   return (ts > 0) ? NormalizeDouble(MathRound(p / ts) * ts, _Digits) : NormalizeDouble(p, _Digits);
  }

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
   int    vd   = (int)MathMax(0.0, MathCeil(-MathLog10(vstep) - 1e-9));   // decimales du pas : 0.01 -> 2
   double lots = NormalizeDouble(MathFloor(eq * InpRiskPct / 100.0 / loss_per_lot / vstep + 1e-9) * vstep, vd);
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
// Cote ask d'une bougie M1 fermee. MqlRates.spread est l'ecart MINIMUM de la bougie : bid + spread
// sous-estime l'ask. On lit les ticks, sauf en rattrapage (CopyTicksRange peut etre lent).
void AskOHL(const MqlRates &b, double &ao, double &ah, double &al)
  {
   double spr = b.spread * _Point;
   ao = b.open + spr; ah = b.high + spr; al = b.low + spr;
   if(g_replay) return;
   MqlArray<MqlTick> k;
   int n = CopyTicksRange(_Symbol, k, COPY_TICKS_INFO, (ulong)b.time * 1000, (ulong)b.time * 1000 + 59999);
   double o = 0.0, h = 0.0, l = DBL_MAX;
   for(int i = 0; i < n; i++)
     {
      double a = k[i].ask;
      if(a <= 0.0) continue;
      if(o == 0.0) o = a;
      if(a > h) h = a;
      if(a < l) l = a;
     }
   if(o > 0.0) { ao = o; ah = h; al = l; }
  }

void DeletePendings();   // declaration (definie plus bas)

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
   if(g_auto) DeletePendings();   // le compte reel ne prend jamais le cote oppose du trade papier
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

// Une bougie M1 fermee (b = prix BID) ; t_utc = heure d'ouverture en UTC
void ProcessBar(const MqlRates &b, const datetime t_utc)
  {
   double ao = 0.0, ah = 0.0, al = 0.0;
   AskOHL(b, ao, ah, al);
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
//| Reel : resultats des requetes, ordres, positions                  |
//+------------------------------------------------------------------+
// resultat d'une requete CTrade : journalise et signale un refus (au plus une alerte par type et par 10 min)
bool Sent(const bool ok, const string what)
  {
   uint rc = g_trade.ResultRetcode();
   if(ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_DONE_PARTIAL || rc == TRADE_RETCODE_PLACED || rc == TRADE_RETCODE_NO_CHANGES))
      return true;
   Journal("ORDER_FAIL", TimeGMT(), 0, 0, 0, 0, 0, what + " : " + IntegerToString(rc) + " " + g_trade.ResultRetcodeDescription());
   static string   s_what = "";
   static datetime s_when = 0;
   if(what != s_what || TimeLocal() - s_when >= 600)
     {
      s_what = what;
      s_when = TimeLocal();
      Notify("GoldOrb " + _Symbol + " : " + what + " REFUSE par le courtier (" + g_trade.ResultRetcodeDescription() + ").");
     }
   return false;
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

bool RealPositionSelected()
  {
   if(g.real_ticket == 0) return false;
   if(PositionSelectByTicket(g.real_ticket)) return true;
   for(int i = PositionsTotal() - 1; i >= 0; i--)   // ticket remplace par le serveur : meme identifiant
     {
      ulong t = PositionGetTicket(i);
      if(t != 0 && g.real_id != 0 && (ulong)PositionGetInteger(POSITION_IDENTIFIER) == g.real_id) { g.real_ticket = t; return true; }
     }
   g.real_ticket = 0;   // fermee (stop touche...)
   return false;
  }

void PlacePendings()
  {
   DeletePendings();
   g_vbuy = false;
   g_vsell = false;
   string m;
   bool over;
   double D = InpStopATR * g.br_atr;
   double lots = LotsForRisk(D, m, over);
   if(lots <= 0 || over)
     {
      Journal("SKIP_SIZE", TimeGMT(), 0, 0, 0, g.br_atr, 0, m);
      static datetime s_skip = 0;   // une alerte par jour, pas toutes les 4 h
      if(TimeLocal() - s_skip >= 86400)
        {
         s_skip = TimeLocal();
         Notify("GoldOrb : ordres non places (" + m + "). " + (lots <= 0 ? "Infos du symbole indisponibles." :
                "Capital trop faible pour le lot minimum (baisser le risque n'aide pas) ; ne relevez InpRiskPct ou InpMaxRiskMult que si vous acceptez ce risque."));
        }
      return;
     }
   MqlTick k;
   if(!SymbolInfoTick(_Symbol, k)) return;
   double lvl = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   long emode = SymbolInfoInteger(_Symbol, SYMBOL_EXPIRATION_MODE);
   bool spec = (emode & SYMBOL_EXPIRATION_SPECIFIED) != 0;
   ENUM_ORDER_TYPE_TIME tt = spec ? ORDER_TIME_SPECIFIED : ORDER_TIME_GTC;
   datetime expiry = spec ? ToServer(g.br_expiry_utc) : 0;
   double hi = NormPrice(g.br_hi), lo = NormPrice(g.br_lo);
   // prix deja au-dela d'un niveau (gap, ouverture du dimanche) : entree au marche, comme le labo
   if(k.ask >= hi) { Sent(g_trade.Buy(lots, _Symbol, 0, NormPrice(k.ask - D), 0, "GoldOrb L mkt"), "achat au marche"); return; }
   if(k.bid <= lo) { Sent(g_trade.Sell(lots, _Symbol, 0, NormPrice(k.bid + D), 0, "GoldOrb S mkt"), "vente au marche"); return; }
   if(hi > k.ask + lvl) Sent(g_trade.BuyStop(lots, hi, _Symbol, NormPrice(hi - D), 0, tt, expiry, "GoldOrb L"), "achat stop");
   else { g_vbuy = true; Journal("STOPSLEVEL", TimeGMT(), 1, hi, 0, 0, 0, "buy level too close: market entry on touch"); }
   if(lo < k.bid - lvl) Sent(g_trade.SellStop(lots, lo, _Symbol, NormPrice(lo + D), 0, tt, expiry, "GoldOrb S"), "vente stop");
   else { g_vsell = true; Journal("STOPSLEVEL", TimeGMT(), -1, lo, 0, 0, 0, "sell level too close: market entry on touch"); }
  }

// mode 2 : niveau trop proche pour un ordre stop (STOPS_LEVEL) -> ordre au marche au premier toucher, comme le labo
void VirtualEntry()
  {
   if(!g_vbuy && !g_vsell) return;
   if(!g_auto || g.br_active == 0 || g.side != 0 || ToUTC(TimeCurrent()) >= g.br_expiry_utc || RealPositionSelected())
     {
      g_vbuy = false;
      g_vsell = false;
      return;
     }
   MqlTick k;
   if(!SymbolInfoTick(_Symbol, k)) return;
   int side = (g_vbuy && k.ask >= g.br_hi) ? 1 : ((g_vsell && k.bid <= g.br_lo) ? -1 : 0);
   if(side == 0) return;
   g_vbuy = false;
   g_vsell = false;
   string m;
   bool over;
   double D = InpStopATR * g.br_atr;
   double lots = LotsForRisk(D, m, over);
   if(lots <= 0 || over) return;
   DeletePendings();   // OCO : l'ordre stop oppose ne doit pas rester
   if(side > 0) Sent(g_trade.Buy(lots, _Symbol, 0, NormPrice(k.ask - D), 0, "GoldOrb L touch"), "achat au toucher");
   else         Sent(g_trade.Sell(lots, _Symbol, 0, NormPrice(k.bid + D), 0, "GoldOrb S touch"), "vente au toucher");
  }

// mode 1 : rattache la position manuelle du meme sens ouverte autour du dernier signal papier
// (appelee a chaque tick et toutes les 2 s ; la position papier peut deja etre sortie)
void BindManualPosition()
  {
   if(InpMode != GO_MANAGE_MANUAL || g.real_ticket != 0 || g.entry_utc == 0) return;
   int sig = (g.fill > g.init_stop) ? 1 : -1;   // sens du dernier trade papier (g.side repasse a 0 a la sortie)
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || !PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != InpManualMagic) continue;
      int side = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
      datetime opened = ToUTC((datetime)PositionGetInteger(POSITION_TIME));
      if(side != sig || opened < g.entry_utc - 600 || opened > g.entry_utc + 6 * 3600) continue;
      double vol = PositionGetDouble(POSITION_VOLUME), sl = PositionGetDouble(POSITION_SL), tp = PositionGetDouble(POSITION_TP);
      g.real_ticket = t;
      g.real_id = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
      g.real_side = side;
      g.real_fill = PositionGetDouble(POSITION_PRICE_OPEN);
      g.real_best = g.real_fill;
      g.real_D = InpStopATR * g.atr;
      g.real_deadline_utc = g.deadline_utc;
      double init = NormPrice(g.real_fill - side * g.real_D);
      Journal("REAL_BIND", TimeGMT(), side, g.real_fill, init, g.atr, 0, IntegerToString((long)t));
      bool stop_ok = (sl != 0.0 && ((side > 0 && sl >= init) || (side < 0 && sl <= init)));   // stop deja au moins aussi serre
      if(!stop_ok) stop_ok = g_trade.PositionModify(t, init, tp) && g_trade.ResultRetcode() == TRADE_RETCODE_DONE;
      Notify(StringFormat("GoldOrb : position #%I64u (%.2f lot) prise en charge : stop %s%s, suiveur %.1f, sortie %s.",
                          t, vol, DoubleToString(init, _Digits),
                          stop_ok ? "" : " NON POSE (" + g_trade.ResultRetcodeDescription() + "), posez-le vous-meme",
                          g.real_D, Clocks(g.real_deadline_utc)));
      SaveState();
      return;
     }
  }

// mode 2 : position du programme ouverte pendant un arret (ordre stop execute sans OnTradeTransaction) -> reprise en charge
void Reconcile()
  {
   if(!g_auto || RealPositionSelected()) return;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || !PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(g.real_ticket != 0) { Sent(g_trade.PositionClose(t), "fermeture du 2e ordre OCO"); continue; }   // les deux executes
      datetime op = (datetime)PositionGetInteger(POSITION_TIME);
      double sl = PositionGetDouble(POSITION_SL);
      g.real_ticket = t;
      g.real_id = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
      g.real_side = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
      g.real_fill = PositionGetDouble(POSITION_PRICE_OPEN);
      datetime dec = BucketUTC(ToUTC(op));
      MqlArray<Bar4> b4;
      int n4 = Build4H(b4, dec);
      double atr = (n4 > InpATRPeriod + 2) ? WilderATR(b4, n4, InpATRPeriod) : 0.0;
      g.real_D = (atr > 0) ? InpStopATR * atr : MathAbs(g.real_fill - sl);
      g.real_deadline_utc = DeadlineUTC(dec, InpMaxDays);
      g.real_best = g.real_fill;
      MqlArray<MqlRates> r;
      ArraySetAsSeries(r, false);
      int k = CopyRates(_Symbol, PERIOD_M1, (datetime)((long)op / 60 * 60), TimeCurrent(), r);
      for(int j = 0; j < k; j++)
         g.real_best = (g.real_side > 0) ? MathMax(g.real_best, r[j].high) : MathMin(g.real_best, r[j].low + r[j].spread * _Point);
      DeletePendings();
      Journal("REAL_ADOPT", TimeGMT(), g.real_side, g.real_fill, sl, atr, 0, IntegerToString((long)t));
      Notify(StringFormat("GoldOrb : position #%I64u ouverte pendant un arret, reprise en charge (sortie max %s).", t, Clocks(g.real_deadline_utc)));
      SaveState();
     }
  }

void RealOnBar(const MqlRates &b, const datetime t_utc)
  {
   if(InpMode == GO_ALERTS || !RealPositionSelected()) return;
   if(g.real_side > 0) { if(b.high > g.real_best) g.real_best = b.high; }
   else
     {
      double ao = 0.0, ah = 0.0, al = 0.0;
      AskOHL(b, ao, ah, al);
      if(al < g.real_best) g.real_best = al;
     }
   if(g_replay) return;   // rattrapage : on suit l'extreme ; le stop est pose une fois a la fin (CatchUp)
   double trail = (InpStopATR > 0) ? g.real_D * InpTrailATR / InpStopATR : g.real_D;   // = papier : suiveur InpTrailATR x ATR
   double want = NormPrice(g.real_best - g.real_side * trail);
   double sl = PositionGetDouble(POSITION_SL), tp = PositionGetDouble(POSITION_TP);
   double init = NormPrice(g.real_fill - g.real_side * g.real_D);
   if(sl == 0.0) want = (g.real_side > 0) ? MathMax(want, init) : MathMin(want, init);
   bool tighter = (sl == 0.0) || (g.real_side > 0 && want > sl + _Point) || (g.real_side < 0 && want < sl - _Point);
   if(!tighter) return;
   MqlTick k;
   if(!SymbolInfoTick(_Symbol, k)) return;
   if((g.real_side > 0 && k.bid <= want) || (g.real_side < 0 && k.ask >= want))
     {   // stop de la regle deja franchi (souvent apres une coupure) : on sort comme le papier
      if(Sent(g_trade.PositionClose(g.real_ticket), "fermeture au stop de la regle"))
        {
         Journal("REAL_CLOSE", t_utc, g.real_side, g_trade.ResultPrice(), want, g.real_D, 0, "rule stop already crossed");
         Notify(StringFormat("GoldOrb : stop de la regle (%s) deja franchi, position #%I64u fermee a %s.",
                             DoubleToString(want, _Digits), g.real_ticket, DoubleToString(g_trade.ResultPrice(), _Digits)));
         g.real_ticket = 0;
        }
      return;
     }
   double lvl = (double)MathMax(SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL),
                                SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL)) * _Point;
   if(g.real_side > 0 && want > k.bid - lvl) return;   // trop pres : nouvel essai a la minute suivante
   if(g.real_side < 0 && want < k.ask + lvl) return;
   if(Sent(g_trade.PositionModify(g.real_ticket, want, tp), "deplacement du stop"))
      Journal("REAL_SL_MOD", t_utc, g.real_side, want, sl, g.real_D, 0, "");
  }

void RealTimeExit()
  {
   if(InpMode == GO_ALERTS || !RealPositionSelected()) return;
   datetime now = ToUTC(TimeCurrent());
   if(now < g.real_deadline_utc || TimeLocal() - g_tx_try < 15) return;   // au plus un essai toutes les 15 s
   g_tx_try = TimeLocal();
   if(g_trade.PositionClose(g.real_ticket) && g_trade.ResultRetcode() == TRADE_RETCODE_DONE)
     {
      Journal("REAL_CLOSE", now, g.real_side, g_trade.ResultPrice(), 0, 0, 0, "time");
      g.real_ticket = 0;
      SaveState();
     }
   else if(g_tx_warned != g.real_ticket)   // une seule alerte par position
     {
      g_tx_warned = g.real_ticket;
      Notify(StringFormat("GoldOrb : fermeture au temps refusee (%s). Nouvel essai toutes les 15 s ; fermez la position #%I64u vous-meme.",
                          g_trade.ResultRetcodeDescription(), g.real_ticket));
     }
  }

//+------------------------------------------------------------------+
//| Decision H4 : niveaux si aucune position papier                  |
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

bool Decide(const datetime bucket, const datetime tc)
  {
   g.br_active = 0;
   g.br_trigger_sent = 0;
   g_vbuy = false;
   g_vsell = false;
   if(g_auto) DeletePendings();                  // les ordres d'une fenetre ne lui survivent jamais
   if(g.side != 0) return true;                  // une seule position PAPIER a la fois
   if(!g_replay && !OffsetOK()) return true;
   MqlArray<Bar4> b;
   int n = Build4H(b, bucket);
   bool sync = MQLInfoInteger(MQL_TESTER) || SeriesInfoInteger(_Symbol, PERIOD_M5, SERIES_SYNCHRONIZED);
   if(!sync || n < InpChannelBars + InpATRPeriod + 2)
     {
      static datetime s_warned = 0;   // une ligne et une alerte par fenetre, pas une par minute
      if(s_warned != bucket)
        {
         s_warned = bucket;
         Journal("DATA_WARN", bucket, 0, 0, 0, 0, 0, "4h bars " + IntegerToString(n) + (sync ? "" : " M5 not synchronized"));
         if(sync && !g_replay)
            Notify("GoldOrb : historique M5 insuffisant (" + IntegerToString(n) + " bougies H4), aucun niveau. Outils > Options > Graphiques > Nombre max. de barres = illimite.");
        }
      return false;                              // on reessaiera a la bougie suivante
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
   g.br_decision_utc = tc;                       // = labo : echeance comptee depuis la cloture de la bougie terminee
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
      if(g_auto) { Reconcile(); if(!RealPositionSelected()) PlacePendings(); }
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Boucle : traite toutes les bougies M1 fermees non encore vues     |
//+------------------------------------------------------------------+
void CatchUp()
  {
   datetime cur = iTime(_Symbol, PERIOD_M1, 0);
   if(cur == 0) return;
   if(g.last_m1 == 0)   // 1er lancement : on n'arme rien en cours de fenetre
     {
      g.last_m1 = cur - 60;
      g.last_bucket_utc = BucketUTC(ToUTC(cur));
      SaveState();
      return;
     }
   if(cur <= g.last_m1 + 60) return;
   if(!MQLInfoInteger(MQL_TESTER) && (!TerminalInfoInteger(TERMINAL_CONNECTED) || !SeriesInfoInteger(_Symbol, PERIOD_M1, SERIES_SYNCHRONIZED)))
      return;   // historique pas encore recharge (redemarrage, reconnexion) : nouvel essai dans 2 s
   MqlArray<MqlRates> r;
   ArraySetAsSeries(r, false);
   int n = CopyRates(_Symbol, PERIOD_M1, g.last_m1 + 60, cur - 60, r);
   if(n < 0 && (long)(cur - g.last_m1) / 60 > TerminalInfoInteger(TERMINAL_MAXBARS))
     {   // coupure plus longue que l'historique du terminal : CopyRates rendrait -1 pour toujours
      Journal("GAP_RESET", ToUTC(cur), g.side, 0, 0, 0, 0, "last M1 " + TimeToString(g.last_m1, TIME_DATE | TIME_MINUTES));
      Notify("GoldOrb : arret trop long pour etre rattrape, position papier et niveaux remis a zero.");
      g.side = 0;
      g.br_active = 0;
      g.last_m1 = cur - 60;
      g.last_bucket_utc = BucketUTC(ToUTC(cur));
      SaveState();
      return;
     }
   if(n <= 0) return;
   g_replay = (n > 5);   // vrai retard (arret, reconnexion) ; une fermeture du marche ne rend qu'UNE bougie
   if(g_replay) Journal("REPLAY", ToUTC(cur), 0, 0, 0, 0, 0, IntegerToString(n) + " M1 bars");
   for(int i = 0; i < n; i++)
     {
      if(r[i].time <= g.last_m1) continue;
      datetime t_utc = ToUTC(r[i].time);
      datetime bucket = BucketUTC(t_utc);
      if(bucket != g.last_bucket_utc)
        {
         if(g_tc_bucket != bucket) { g_tc_bucket = bucket; g_tc = ToUTC(g.last_m1) + 60; }   // = labo : t_close de la bougie H4 terminee
         if(Decide(bucket, g_tc)) g.last_bucket_utc = bucket;   // sinon on reessaiera a la bougie suivante
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
      Reconcile();
      RealOnBar(r[n - 1], ToUTC(r[n - 1].time));   // un seul deplacement de stop, depuis l'extreme rattrape
      Notify(StringFormat("GoldOrb : rattrapage de %d bougies M1 termine. Position papier : %s.", n,
                          g.side == 0 ? "aucune" : (g.side > 0 ? "achat" : "vente")));
      if(g_auto && g.br_active != 0 && g.side == 0 && ToUTC(TimeCurrent()) < g.br_expiry_utc && !RealPositionSelected() && OffsetOK())
         PlacePendings();   // re-arme la fenetre en cours : Decide n'a rien place pendant le rattrapage
     }
   SaveState();
  }

void TickTrigger()
  {
   // alerte instantanee au franchissement (la position papier est enregistree a la cloture M1)
   if(g.side != 0 || g.br_active == 0 || g.br_trigger_sent != 0) return;
   MqlTick k;
   if(!SymbolInfoTick(_Symbol, k)) return;
   if(ToUTC(TimeCurrent()) >= g.br_expiry_utc) return;
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
     }
  }

void Housekeeping()
  {
   datetime now = ToUTC(TimeCurrent());
   MqlDateTime x;
   TimeToStruct(now, x);
   if(x.day_of_week == 5 && x.hour >= 20 && now - g.week_sent_utc > 3 * 86400)   // vendredi apres 20:00 UTC
     {
      Notify(StringFormat("GoldOrb %s semaine : %d trade(s) %+.2f R | cumul %+.1f R / %d trades%s",
                          _Symbol, g.week_n, g.week_R, g.cum_R, g.n_trades, g.side != 0 ? " | position ouverte" : ""));
      Journal("WEEK", now, 0, 0, 0, 0, g.week_R, IntegerToString(g.week_n));
      g.week_R = 0; g.week_n = 0; g.week_sent_utc = now;
      SaveState();
     }
   if(now - g.heartbeat_utc > 86400)
     {
      Journal("HEARTBEAT", now, g.side, g.stop, 0, 0, g.cum_R, g.br_active ? "levels armed" : "");
      g.heartbeat_utc = now;
     }
  }

//+------------------------------------------------------------------+
//| Demarrage : on attend que le compte soit connu                    |
//+------------------------------------------------------------------+
// Au demarrage du terminal, OnInit tourne avant la connexion : ACCOUNT_LOGIN et ACCOUNT_TRADE_MODE valent 0 (= DEMO).
bool AccountReady()
  {
   if(g_ready) return true;
   bool tester = (MQLInfoInteger(MQL_TESTER) != 0);
   if(!tester && (AccountInfoInteger(ACCOUNT_LOGIN) == 0 || !TerminalInfoInteger(TERMINAL_CONNECTED))) return false;
   g_key = _Symbol + "_" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN));
   bool had = LoadState();
   g_auto = (InpMode == GO_AUTO);
   if(g_auto && !tester && AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL && !InpAllowAutoReal)
     {
      g_auto = false;
      Notify("GoldOrb : mode automatique refuse sur compte REEL (InpAllowAutoReal = false). Mode alertes.");
     }
   if(InpMode == GO_ALERTS) g.real_ticket = 0;   // un ticket laisse par un autre mode ne bloque plus rien
   if(InpMode != GO_ALERTS && !tester && (!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED)))
      Notify("GoldOrb : Algo Trading desactive : le programme ne peut ni poser, ni deplacer, ni fermer vos stops.");
   g_ready = true;
   Print("GoldOrb v2.1 demarre. Compte ", AccountInfoInteger(ACCOUNT_LOGIN), " | mode ", EnumToString(InpMode), g_auto ? " (ordres actifs)" : "",
         had ? " | etat recharge" : " | nouvel etat", " | position papier ", g.side, " | cumul ", DoubleToString(g.cum_R, 2), " R / ", g.n_trades, " trades");
   return true;
  }

int OnInit()
  {
   if(InpChannelBars < 1 || InpATRPeriod < 1 || InpStopATR <= 0 || InpTrailATR <= 0 || InpMaxDays < 1 || InpHistoryDays < 30 ||
      InpRiskPct <= 0 || InpRiskPct > 2.0 || InpMaxRiskMult < 1.0 || InpWakeFrom < 0 || InpWakeTo > 24 || InpWakeFrom > InpWakeTo)
     {
      Alert("GoldOrb : parametre hors limites (canal et ATR >= 1, stops > 0, duree >= 1 jour, historique >= 30 jours, risque 0-2 %, heures 0-24).");
      return INIT_PARAMETERS_INCORRECT;
     }
   if(StringFind(_Symbol, "XAU") < 0 && StringFind(_Symbol, "GOLD") < 0)
      Print("GoldOrb : attention, regle testee uniquement sur l'or (XAUUSD). Symbole : ", _Symbol);
   FolderCreate("GoldOrb", FILE_COMMON);
   if(MQLInfoInteger(MQL_TESTER)) FileDelete(FilePrefix() + "journal_" + _Symbol + ".csv", FILE_COMMON);   // un journal neuf par test
   ZeroMemory(g);
   g_ready = false;   // un EA garde ses globales d'un OnInit a l'autre (changement de compte, de parametres)
   g_key = "";
   g_auto = false;    // decide dans AccountReady(), une fois le compte connu
   g_trade.SetExpertMagicNumber((ulong)InpMagic);
   EventSetTimer(2);
   AccountReady();    // immediat si le terminal est deja connecte
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   if(g_auto && (reason == REASON_REMOVE || reason == REASON_CHARTCLOSE)) DeletePendings();   // EA retire : pas d'ordre orphelin
   SaveState();
  }

void OnTick()
  {
   if(!AccountReady()) return;
   CatchUp();
   BindManualPosition();
   VirtualEntry();
   TickTrigger();
   RealTimeExit();
  }

void OnTimer()
  {
   if(!AccountReady()) return;
   CatchUp();
   BindManualPosition();
   RealTimeExit();
   static datetime s_rec = 0;
   if(TimeLocal() - s_rec >= 60) { s_rec = TimeLocal(); Reconcile(); }
   Housekeeping();
   FlushPush();
   FlushTelegram();
  }

// Mode auto : sur execution d'un ordre -> annule l'autre, recale le stop sur le vrai prix
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
   if(g.real_ticket != 0 && g.real_id != pos && RealPositionSelected())
     {
      // les deux ordres ont ete executes : on ferme le second immediatement
      Sent(g_trade.PositionClose(pos), "fermeture du 2e ordre OCO");
      Journal("REAL_CLOSE", TimeGMT(), side, 0, 0, 0, 0, "second OCO leg");
      return;
     }
   g.real_ticket = pos;
   g.real_id = pos;
   g.real_side = side;
   g.real_fill = HistoryDealGetDouble(trans.deal, DEAL_PRICE);
   g.real_best = g.real_fill;
   g.real_D = InpStopATR * g.br_atr;
   g.real_deadline_utc = DeadlineUTC(g.br_decision_utc, InpMaxDays);
   Journal("REAL_FILL", TimeGMT(), side, g.real_fill, g.real_fill - side * g.real_D, g.br_atr, 0, IntegerToString((long)pos));
   if(PositionSelectByTicket(pos))
      Sent(g_trade.PositionModify(pos, NormPrice(g.real_fill - side * g.real_D), PositionGetDouble(POSITION_TP)), "recalage du stop initial");
   SaveState();
  }
//+------------------------------------------------------------------+

const string _Symbol = "XAUUSD";
const double _Point = 0.01;
const int _Digits = 2;
