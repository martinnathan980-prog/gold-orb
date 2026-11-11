//+------------------------------------------------------------------+
//|                                                 ClaudeMains.mq5  |
//|  "Les mains" du robot. Ce programme ne decide RIEN : il envoie    |
//|  les donnees du marche au cerveau (un programme sur l'ordinateur) |
//|  et execute les ordres que le cerveau lui renvoie.                |
//|                                                                  |
//|  Echanges par fichiers dans MQL5\Files\claude\ :                  |
//|   mains -> cerveau : account.txt, positions.csv, symbols.csv,     |
//|                      deals.csv, bars_<marche>_<M1|M5|H1|D1>.csv   |
//|   cerveau -> mains : cmd\<id>.txt   (lignes cle=valeur)           |
//|   mains -> cerveau : res\<id>.txt   (ok=1/0, raison, ticket...)   |
//|                                                                  |
//|  Les limites sont ICI et le cerveau ne peut pas les contourner :  |
//|   1. Aucun ordre sans stop ; le stop est pose chez le courtier.   |
//|   2. Un stop ne peut que se rapprocher du prix, jamais s'eloigner.|
//|   3. Risque max par trade : la taille est reduite d'office.       |
//|   4. Nombre max de positions (au total et par marche).            |
//|   5. Perte max du jour : tout est ferme, blocage jusqu'a demain.  |
//|   6. Arret definitif a -50 % du capital de depart.                |
//|   7. Cerveau muet : plus aucune nouvelle position (les stops      |
//|      restent en place) ; duree max par position respectee.        |
//|   8. Tout est ferme le vendredi soir.                             |
//|  Il ne touche jamais aux positions ouvertes a la main.            |
//+------------------------------------------------------------------+
#property copyright "gold-orb lab"
#property version   "1.00"
#property description "Les mains de Claude : exporte les donnees, execute les ordres du cerveau, impose les limites (stop obligatoire, risque max, perte du jour, arret a -50 %)."

#include <Trade\Trade.mqh>

input string InpSymbols         = "XAUUSD,US100,BTCUSD,ETHUSD,EURUSD,USDJPY"; // Marches (noms de base ; le suffixe du courtier est trouve tout seul)
input double InpMaxRiskPct      = 1.0;      // Risque max par trade si le stop est touche (% du solde)
input int    InpMaxPositions    = 6;        // Positions ouvertes en meme temps (total)
input int    InpMaxPerSymbol    = 2;        // Positions ouvertes en meme temps par marche
input double InpDailyLossPct    = 6.0;      // Perte max du jour (% du solde du debut de journee) : tout ferme + blocage
input double InpKillPct         = 50.0;     // Arret definitif si les fonds perdent ce % du capital de depart
input double InpStartBalance    = 0.0;      // Capital de depart (0 = solde au premier lancement)
input int    InpBrainTimeoutSec = 180;      // Cerveau muet depuis ce delai (secondes) : plus de nouvelle position
input int    InpFridayClose     = 2350;     // Vendredi, heure serveur HHMM ou tout est ferme (0 = desactive)
input long   InpMagic           = 20261110; // Numero magique des positions du robot
input int    InpSlippagePts     = 50;       // Glissement max accepte (points)
input bool   InpPush            = true;     // Notifications push (appli MT5 mobile) pour les blocages
input bool   InpResetLocks      = false;    // Mettre true UNE fois pour lever un blocage ou l'arret, puis remettre false

const string DIR     = "claude\\";
const string VERSION = "1.00";

CTrade   g_trade;
string   g_base[];            // noms de base demandes (XAUUSD, US100, ...)
string   g_name[];            // noms reels chez le courtier (XAUUSD.r, ...) ; "" = introuvable
datetime g_last_min   = 0;    // derniere minute serveur exportee
datetime g_last_fast  = 0;    // dernier export compte / positions
datetime g_last_close = 0;    // derniere tentative de fermeture forcee
datetime g_brain_ts   = 0;    // dernier signe de vie du cerveau (UTC)
bool     g_dirty      = true; // une transaction vient d'avoir lieu : exporter tout de suite
string   g_last_msg   = "";   // dernier evenement (affiche sur le graphique)

//+------------------------------------------------------------------+
//| Fichiers                                                         |
//+------------------------------------------------------------------+
// ecriture atomique : fichier temporaire puis renommage (le cerveau ne lit jamais un fichier a moitie ecrit)
bool Put(const string name, const string text)
  {
   string tmp = DIR + name + ".tmp";
   int h = FileOpen(tmp, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE) return false;
   FileWriteString(h, text);
   FileClose(h);
   return FileMove(tmp, 0, DIR + name, FILE_REWRITE);
  }

// lit un fichier de lignes "cle=valeur" ; renvoie le nombre de couples, -1 si illisible
int ReadKV(const string path, string &keys[], string &vals[])
  {
   int h = FileOpen(path, FILE_READ | FILE_TXT | FILE_ANSI | FILE_SHARE_READ);
   if(h == INVALID_HANDLE) return -1;
   int n = 0;
   while(!FileIsEnding(h))
     {
      string ln = FileReadString(h);
      StringTrimRight(ln);
      StringTrimLeft(ln);
      int p = StringFind(ln, "=");
      if(p <= 0) continue;
      ArrayResize(keys, n + 1);
      ArrayResize(vals, n + 1);
      keys[n] = StringSubstr(ln, 0, p);
      vals[n] = StringSubstr(ln, p + 1);
      n++;
     }
   FileClose(h);
   return n;
  }

string KV(const string &keys[], const string &vals[], const string key, const string def = "")
  {
   for(int i = 0; i < ArraySize(keys); i++)
      if(keys[i] == key) return vals[i];
   return def;
  }

// un texte libre (etiquette, commentaire) ne doit jamais casser une ligne des fichiers csv
string Clean(string s)
  {
   StringReplace(s, ",", " ");
   StringReplace(s, "\r", " ");
   StringReplace(s, "\n", " ");
   return s;
  }

bool HasKey(const string &keys[], const string key)
  {
   for(int i = 0; i < ArraySize(keys); i++)
      if(keys[i] == key) return true;
   return false;
  }

void Notify(const string msg)
  {
   g_last_msg = TimeToString(TimeTradeServer(), TIME_DATE | TIME_MINUTES) + " " + msg;
   Print("ClaudeMains: ", msg);
   if(InpPush) SendNotification("Robot Claude : " + msg);
  }

//+------------------------------------------------------------------+
//| Marches                                                          |
//+------------------------------------------------------------------+
bool Tradable(const string s)
  {
   return SymbolSelect(s, true) && SymbolInfoInteger(s, SYMBOL_TRADE_MODE) != SYMBOL_TRADE_MODE_DISABLED;
  }

// nom reel d'un marche chez le courtier : nom exact, nom + ".r" (compte Raw), sinon premier symbole qui commence pareil
string Resolve(const string base)
  {
   if(Tradable(base + ".r")) return base + ".r";
   if(Tradable(base)) return base;
   string alt[];
   int na = 0;
   if(base == "US100") na = StringSplit("NAS100,USTEC,US100.cash,NDX100", ',', alt);
   if(base == "XAUUSD") na = StringSplit("GOLD", ',', alt);
   for(int a = 0; a < na; a++)
     {
      if(Tradable(alt[a] + ".r")) return alt[a] + ".r";
      if(Tradable(alt[a])) return alt[a];
     }
   int total = SymbolsTotal(false);
   for(int i = 0; i < total; i++)
     {
      string s = SymbolName(i, false);
      if(StringFind(s, base) == 0 && Tradable(s)) return s;
     }
   return "";
  }

// accepte le nom de base ou le nom reel ; renvoie le nom reel ("" si inconnu)
string NameOf(const string any)
  {
   for(int i = 0; i < ArraySize(g_base); i++)
      if(g_name[i] != "" && (g_base[i] == any || g_name[i] == any)) return g_name[i];
   return "";
  }

int CountPositions(const string nm = "")
  {
   int c = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(nm == "" || PositionGetString(POSITION_SYMBOL) == nm) c++;
     }
   return c;
  }

// perte en devise du compte si le stop est touche, pour `vol` lots
double RiskMoney(const string nm, const double price, const double sl, const double vol)
  {
   double ts = SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_SIZE);
   double tv = SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tv <= 0) tv = SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_VALUE);
   if(ts <= 0 || tv <= 0) return -1.0;
   return MathAbs(price - sl) / ts * tv * vol;
  }

//+------------------------------------------------------------------+
//| Limites                                                          |
//+------------------------------------------------------------------+
bool TradeAllowed()
  {
   return TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) != 0 && MQLInfoInteger(MQL_TRADE_ALLOWED) != 0
          && AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) != 0 && AccountInfoInteger(ACCOUNT_TRADE_EXPERT) != 0;
  }

bool FridayClosed(const datetime now)
  {
   if(InpFridayClose <= 0) return false;
   MqlDateTime d;
   TimeToStruct(now, d);
   return d.day_of_week == 6 || d.day_of_week == 0 || (d.day_of_week == 5 && d.hour * 100 + d.min >= InpFridayClose);
  }

// raison pour laquelle aucune NOUVELLE position n'est acceptee ("" = rien ne bloque)
string Blocked()
  {
   if(GlobalVariableGet("CM_killed") != 0) return "arret definitif (-" + DoubleToString(InpKillPct, 0) + " %)";
   if(GlobalVariableGet("CM_day_lock") != 0) return "perte max du jour atteinte";
   if(FridayClosed(TimeTradeServer())) return "fermeture du week-end";
   if(!TradeAllowed()) return "trading automatique desactive dans MT5";
   if(TimeGMT() - g_brain_ts > InpBrainTimeoutSec) return "cerveau muet";
   return "";
  }

//+------------------------------------------------------------------+
//| Export vers le cerveau                                           |
//+------------------------------------------------------------------+
void ExportBars(const string base, const string nm, const ENUM_TIMEFRAMES tf, const string tag, const int count)
  {
   MqlRates r[];
   int n = CopyRates(nm, tf, 1, count, r);          // bougies terminees seulement, de la plus ancienne a la plus recente
   if(n <= 0) return;
   int dg = (int)SymbolInfoInteger(nm, SYMBOL_DIGITS);
   string s = "time,open,high,low,close,tick_volume,spread\n";
   for(int i = 0; i < n; i++)
      s += IntegerToString((long)r[i].time) + "," + DoubleToString(r[i].open, dg) + "," + DoubleToString(r[i].high, dg) + ","
           + DoubleToString(r[i].low, dg) + "," + DoubleToString(r[i].close, dg) + "," + IntegerToString(r[i].tick_volume) + ","
           + IntegerToString(r[i].spread) + "\n";
   Put("bars_" + base + "_" + tag + ".csv", s);
  }

void ExportSymbols()
  {
   string s = "base,name,digits,point,tick_size,tick_value,tick_value_loss,contract_size,vol_min,vol_step,vol_max,";
   s += "stops_level,freeze_level,spread_points,bid,ask,tick_time,trade_mode,swap_long,swap_short,swap_mode,";
   s += "swap_3days,margin_1lot,ccy_profit,ccy_margin\n";
   for(int i = 0; i < ArraySize(g_base); i++)
     {
      string nm = g_name[i];
      if(nm == "") { s += g_base[i] + ",,,,,,,,,,,,,,,,,,,,,,,,\n"; continue; }
      MqlTick k;
      ZeroMemory(k);
      SymbolInfoTick(nm, k);
      int dg = (int)SymbolInfoInteger(nm, SYMBOL_DIGITS);
      double margin = 0.0;
      if(k.ask <= 0 || !OrderCalcMargin(ORDER_TYPE_BUY, nm, 1.0, k.ask, margin)) margin = 0.0;
      s += g_base[i] + "," + nm + "," + IntegerToString(dg) + "," + DoubleToString(SymbolInfoDouble(nm, SYMBOL_POINT), 8) + ","
           + DoubleToString(SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_SIZE), 8) + ","
           + DoubleToString(SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_VALUE), 8) + ","
           + DoubleToString(SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_VALUE_LOSS), 8) + ","
           + DoubleToString(SymbolInfoDouble(nm, SYMBOL_TRADE_CONTRACT_SIZE), 4) + ","
           + DoubleToString(SymbolInfoDouble(nm, SYMBOL_VOLUME_MIN), 4) + ","
           + DoubleToString(SymbolInfoDouble(nm, SYMBOL_VOLUME_STEP), 4) + ","
           + DoubleToString(SymbolInfoDouble(nm, SYMBOL_VOLUME_MAX), 2) + ","
           + IntegerToString(SymbolInfoInteger(nm, SYMBOL_TRADE_STOPS_LEVEL)) + ","
           + IntegerToString(SymbolInfoInteger(nm, SYMBOL_TRADE_FREEZE_LEVEL)) + ","
           + IntegerToString(SymbolInfoInteger(nm, SYMBOL_SPREAD)) + ","
           + DoubleToString(k.bid, dg) + "," + DoubleToString(k.ask, dg) + "," + IntegerToString((long)k.time) + ","
           + IntegerToString(SymbolInfoInteger(nm, SYMBOL_TRADE_MODE)) + ","
           + DoubleToString(SymbolInfoDouble(nm, SYMBOL_SWAP_LONG), 4) + ","
           + DoubleToString(SymbolInfoDouble(nm, SYMBOL_SWAP_SHORT), 4) + ","
           + IntegerToString(SymbolInfoInteger(nm, SYMBOL_SWAP_MODE)) + ","
           + IntegerToString(SymbolInfoInteger(nm, SYMBOL_SWAP_ROLLOVER3DAYS)) + ","
           + DoubleToString(margin, 2) + "," + SymbolInfoString(nm, SYMBOL_CURRENCY_PROFIT) + ","
           + SymbolInfoString(nm, SYMBOL_CURRENCY_MARGIN) + "\n";
     }
   Put("symbols.csv", s);
  }

void ExportAccount()
  {
   datetime srv = TimeTradeServer(), gmt = TimeGMT();
   string s = "ea_version=" + VERSION + "\n";
   s += "ea_time_gmt=" + IntegerToString((long)gmt) + "\n";
   s += "server_time=" + IntegerToString((long)srv) + "\n";
   s += "server_minus_gmt_sec=" + IntegerToString((long)(srv - gmt)) + "\n";
   s += "balance=" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + "\n";
   s += "equity=" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) + "\n";
   s += "margin=" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN), 2) + "\n";
   s += "margin_free=" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2) + "\n";
   s += "currency=" + AccountInfoString(ACCOUNT_CURRENCY) + "\n";
   s += "leverage=" + IntegerToString(AccountInfoInteger(ACCOUNT_LEVERAGE)) + "\n";
   s += "demo=" + IntegerToString(AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO ? 1 : 0) + "\n";
   s += "hedging=" + IntegerToString(AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING ? 1 : 0) + "\n";
   s += "server=" + AccountInfoString(ACCOUNT_SERVER) + "\n";
   s += "trade_allowed=" + IntegerToString(TradeAllowed() ? 1 : 0) + "\n";
   s += "blocked=" + Blocked() + "\n";
   s += "start_balance=" + DoubleToString(GlobalVariableGet("CM_start"), 2) + "\n";
   s += "day_start_balance=" + DoubleToString(GlobalVariableGet("CM_day_bal"), 2) + "\n";
   s += "max_risk_pct=" + DoubleToString(InpMaxRiskPct, 2) + "\n";
   s += "max_positions=" + IntegerToString(InpMaxPositions) + "\n";
   s += "max_per_symbol=" + IntegerToString(InpMaxPerSymbol) + "\n";
   s += "daily_loss_pct=" + DoubleToString(InpDailyLossPct, 2) + "\n";
   s += "kill_pct=" + DoubleToString(InpKillPct, 2) + "\n";
   s += "magic=" + IntegerToString(InpMagic) + "\n";
   Put("account.txt", s);
  }

void ExportPositions()
  {
   string s = "ticket,symbol,side,volume,price_open,sl,tp,price_current,profit,swap,time_open,ttl_deadline,comment\n";
   for(int i = 0; i < PositionsTotal(); i++)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      string nm = PositionGetString(POSITION_SYMBOL);
      int dg = (int)SymbolInfoInteger(nm, SYMBOL_DIGITS);
      string gv = "CM_ttl_" + IntegerToString((long)t);
      s += IntegerToString((long)t) + "," + nm + "," + (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "buy" : "sell") + ","
           + DoubleToString(PositionGetDouble(POSITION_VOLUME), 4) + "," + DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN), dg) + ","
           + DoubleToString(PositionGetDouble(POSITION_SL), dg) + "," + DoubleToString(PositionGetDouble(POSITION_TP), dg) + ","
           + DoubleToString(PositionGetDouble(POSITION_PRICE_CURRENT), dg) + "," + DoubleToString(PositionGetDouble(POSITION_PROFIT), 2) + ","
           + DoubleToString(PositionGetDouble(POSITION_SWAP), 2) + "," + IntegerToString(PositionGetInteger(POSITION_TIME)) + ","
           + IntegerToString(GlobalVariableCheck(gv) ? (long)GlobalVariableGet(gv) : 0) + "," + Clean(PositionGetString(POSITION_COMMENT)) + "\n";
     }
   Put("positions.csv", s);
  }

// toutes les transactions des 7 derniers jours (le cerveau retrouve les siennes par numero de position)
void ExportDeals()
  {
   datetime now = TimeTradeServer();
   if(!HistorySelect(now - 7 * 86400, now + 86400)) return;
   string s = "deal,position,time,symbol,type,entry,volume,price,profit,swap,commission,fee,magic,reason,comment\n";
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      long type = HistoryDealGetInteger(d, DEAL_TYPE);
      if(type != DEAL_TYPE_BUY && type != DEAL_TYPE_SELL) continue;
      string nm = HistoryDealGetString(d, DEAL_SYMBOL);
      int dg = (int)SymbolInfoInteger(nm, SYMBOL_DIGITS);
      s += IntegerToString((long)d) + "," + IntegerToString(HistoryDealGetInteger(d, DEAL_POSITION_ID)) + ","
           + IntegerToString(HistoryDealGetInteger(d, DEAL_TIME)) + "," + nm + "," + (type == DEAL_TYPE_BUY ? "buy" : "sell") + ","
           + IntegerToString(HistoryDealGetInteger(d, DEAL_ENTRY)) + "," + DoubleToString(HistoryDealGetDouble(d, DEAL_VOLUME), 4) + ","
           + DoubleToString(HistoryDealGetDouble(d, DEAL_PRICE), dg) + "," + DoubleToString(HistoryDealGetDouble(d, DEAL_PROFIT), 2) + ","
           + DoubleToString(HistoryDealGetDouble(d, DEAL_SWAP), 2) + "," + DoubleToString(HistoryDealGetDouble(d, DEAL_COMMISSION), 2) + ","
           + DoubleToString(HistoryDealGetDouble(d, DEAL_FEE), 2) + ","
           + IntegerToString(HistoryDealGetInteger(d, DEAL_MAGIC)) + "," + IntegerToString(HistoryDealGetInteger(d, DEAL_REASON)) + ","
           + Clean(HistoryDealGetString(d, DEAL_COMMENT)) + "\n";
     }
   Put("deals.csv", s);
  }

void ExportMinute()
  {
   for(int i = 0; i < ArraySize(g_base); i++)
     {
      if(g_name[i] == "") continue;
      ExportBars(g_base[i], g_name[i], PERIOD_M1, "M1", 240);
      ExportBars(g_base[i], g_name[i], PERIOD_M5, "M5", 300);
      ExportBars(g_base[i], g_name[i], PERIOD_H1, "H1", 300);
      ExportBars(g_base[i], g_name[i], PERIOD_D1, "D1", 300);
     }
   ExportSymbols();
   ExportDeals();
  }

//+------------------------------------------------------------------+
//| Limites (suite)                                                  |
//+------------------------------------------------------------------+
// renvoie le nombre de positions du robot qui n'ont PAS pu etre fermees
int CloseAll(const string why)
  {
   int failed = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      g_trade.SetTypeFillingBySymbol(PositionGetString(POSITION_SYMBOL));
      bool ok = g_trade.PositionClose(t);
      uint rc = g_trade.ResultRetcode();
      if(!ok || (rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_PLACED && rc != TRADE_RETCODE_DONE_PARTIAL))
        {
         failed++;
         Print("ClaudeMains: fermeture refusee (", why, ") ticket ", t, " : ", rc, " ", g_trade.ResultRetcodeDescription());
        }
     }
   g_dirty = true;
   return failed;
  }

void Watch()
  {
   datetime now = TimeTradeServer();
   datetime day = now - now % 86400;
   double bal = AccountInfoDouble(ACCOUNT_BALANCE), eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(!TerminalInfoInteger(TERMINAL_CONNECTED) || bal <= 0) return;     // compte pas encore charge (MT5 vient de demarrer) : ne rien conclure
   if(GlobalVariableGet("CM_start") <= 0)
     {
      GlobalVariableSet("CM_start", InpStartBalance > 0 ? InpStartBalance : bal);
      GlobalVariablesFlush();
     }
   if((datetime)GlobalVariableGet("CM_day") != day)                     // nouvelle journee serveur
     {
      GlobalVariableSet("CM_day", (double)day);
      GlobalVariableSet("CM_day_bal", bal);
      GlobalVariableSet("CM_day_lock", 0.0);
      GlobalVariablesFlush();                                           // ecrit sur le disque tout de suite (sinon perdu si MT5 plante)
     }
   double start = GlobalVariableGet("CM_start");
   if(GlobalVariableGet("CM_killed") == 0 && start > 0 && eq <= start * (1.0 - InpKillPct / 100.0))
     {
      GlobalVariableSet("CM_killed", 1.0);
      GlobalVariablesFlush();
      Notify("ARRET DEFINITIF : fonds " + DoubleToString(eq, 2) + ", capital de depart " + DoubleToString(start, 2) + ". Tout est ferme.");
     }
   double dbal = GlobalVariableGet("CM_day_bal");
   if(GlobalVariableGet("CM_day_lock") == 0 && InpDailyLossPct > 0 && dbal > 0 && eq <= dbal * (1.0 - InpDailyLossPct / 100.0))
     {
      GlobalVariableSet("CM_day_lock", 1.0);
      GlobalVariablesFlush();
      Notify("Perte max du jour atteinte : tout est ferme, reprise demain.");
     }
   bool flat = GlobalVariableGet("CM_killed") != 0 || GlobalVariableGet("CM_day_lock") != 0 || FridayClosed(now);
   if(flat && CountPositions() > 0 && (now - g_last_close >= 10 || now < g_last_close))   // on insiste toutes les 10 s tant qu'il reste une position
     {
      g_last_close = now;
      CloseAll("blocage");
     }
   // duree max par position (posee a l'ouverture par le cerveau) ; nettoyage des echeances des positions disparues
   bool due = (now - g_last_close >= 10 || now < g_last_close);         // une tentative toutes les 10 s, pour TOUTES les positions arrivees a echeance
   for(int i = GlobalVariablesTotal() - 1; i >= 0; i--)
     {
      string gv = GlobalVariableName(i);
      if(StringFind(gv, "CM_ttl_") != 0) continue;
      ulong t = (ulong)StringToInteger(StringSubstr(gv, 7));
      if(!PositionSelectByTicket(t))                                    // pas (encore) dans la liste du terminal : on garde l'echeance jusqu'a son heure
        {
         if(now >= (datetime)GlobalVariableGet(gv)) GlobalVariableDel(gv);
         continue;
        }
      if(now >= (datetime)GlobalVariableGet(gv) && due)
        {
         g_last_close = now;
         g_trade.SetTypeFillingBySymbol(PositionGetString(POSITION_SYMBOL));
         if(g_trade.PositionClose(t)) Notify("Duree max atteinte : position " + IntegerToString((long)t) + " fermee.");
         g_dirty = true;
        }
     }
  }

//+------------------------------------------------------------------+
//| Ordres du cerveau                                                |
//+------------------------------------------------------------------+
bool Done(const bool ok)
  {
   uint rc = g_trade.ResultRetcode();
   return ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED || rc == TRADE_RETCODE_DONE_PARTIAL || rc == TRADE_RETCODE_NO_CHANGES);
  }

string Refusal()
  {
   return "refuse par le serveur : " + IntegerToString((long)g_trade.ResultRetcode()) + " " + g_trade.ResultRetcodeDescription();
  }

// ouverture au marche, stop obligatoire ; renvoie "" si executee, sinon la raison du refus
string DoOpen(const string &k[], const string &v[], string &extra)
  {
   string why = Blocked();
   if(why != "") return why;
   string nm = NameOf(KV(k, v, "symbol"));
   if(nm == "") return "marche inconnu";
   string side = KV(k, v, "side");
   int dir = (side == "buy") ? 1 : ((side == "sell") ? -1 : 0);
   if(dir == 0) return "side doit etre buy ou sell";
   long expire = StringToInteger(KV(k, v, "expire", "0"));
   if(expire > 0 && (long)TimeTradeServer() > expire) return "ordre perime";
   MqlTick tk;
   if(!SymbolInfoTick(nm, tk) || tk.bid <= 0 || tk.ask <= 0) return "pas de prix";
   if(SymbolInfoInteger(nm, SYMBOL_TRADE_MODE) != SYMBOL_TRADE_MODE_FULL) return "marche ferme ou non negociable";
   if((SymbolInfoInteger(nm, SYMBOL_ORDER_MODE) & SYMBOL_ORDER_SL) == 0) return "ce marche n'accepte pas de stop chez le courtier";   // sinon CTrade enleve le stop sans rien dire
   int dg = (int)SymbolInfoInteger(nm, SYMBOL_DIGITS);
   double lvl = (double)SymbolInfoInteger(nm, SYMBOL_TRADE_STOPS_LEVEL) * SymbolInfoDouble(nm, SYMBOL_POINT);
   double price = (dir > 0) ? tk.ask : tk.bid;
   double sl = NormalizeDouble(StringToDouble(KV(k, v, "sl", "0")), dg);
   double tp = NormalizeDouble(StringToDouble(KV(k, v, "tp", "0")), dg);
   double want = StringToDouble(KV(k, v, "volume", "0"));
   if(!MathIsValidNumber(sl) || !MathIsValidNumber(tp) || !MathIsValidNumber(want)) return "nombre illisible dans l'ordre";
   if(sl <= 0) return "stop obligatoire";
   if((dir > 0 && sl >= tk.bid - lvl) || (dir < 0 && sl <= tk.ask + lvl)) return "stop du mauvais cote ou trop pres";
   if(tp > 0 && ((dir > 0 && tp <= tk.ask + lvl) || (dir < 0 && tp >= tk.bid - lvl))) return "objectif du mauvais cote ou trop pres";
   double vmin = SymbolInfoDouble(nm, SYMBOL_VOLUME_MIN), vstep = SymbolInfoDouble(nm, SYMBOL_VOLUME_STEP);
   double vmax = SymbolInfoDouble(nm, SYMBOL_VOLUME_MAX);
   if(vstep <= 0) vstep = vmin;
   double r1 = RiskMoney(nm, price, sl, 1.0);
   if(!MathIsValidNumber(r1) || r1 <= 0 || vmin <= 0) return "risque impossible a calculer";
   if(want < vmin) return "volume demande nul ou inferieur au lot minimum (" + DoubleToString(vmin, 2) + ")";
   double cap = AccountInfoDouble(ACCOUNT_BALANCE) * InpMaxRiskPct / 100.0;
   double vol = MathMin(want, MathMin(cap / r1, vmax));
   vol = NormalizeDouble(MathFloor(vol / vstep + 1e-9) * vstep, 8);     // taille reduite d'office a la limite de risque (multiple exact du pas, jamais arrondie vers le haut)
   if(vol < vmin)
      return "limite de risque : le lot minimum (" + DoubleToString(vmin, 2) + ") risquerait " + DoubleToString(r1 * vmin, 2)
             + ", limite " + DoubleToString(cap, 2);
   if(CountPositions() >= InpMaxPositions) return "trop de positions ouvertes";
   if(CountPositions(nm) >= InpMaxPerSymbol) return "trop de positions sur ce marche";
   double need = 0.0;
   if(OrderCalcMargin(dir > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, nm, vol, price, need) && need > AccountInfoDouble(ACCOUNT_MARGIN_FREE))
      return "marge insuffisante";
   g_trade.SetTypeFillingBySymbol(nm);
   string cm = StringSubstr("CM " + Clean(KV(k, v, "tag")), 0, 27);
   bool ok = (dir > 0) ? g_trade.Buy(vol, nm, 0.0, sl, tp, cm) : g_trade.Sell(vol, nm, 0.0, sl, tp, cm);
   if(!Done(ok)) return Refusal();
   ulong pos = g_trade.ResultOrder();
   long ttl = StringToInteger(KV(k, v, "ttl_min", "0"));
   if(ttl > 0 && pos > 0)
     {
      GlobalVariableSet("CM_ttl_" + IntegerToString((long)pos), (double)(TimeTradeServer() + ttl * 60));
      GlobalVariablesFlush();
     }
   extra = "ticket=" + IntegerToString((long)pos) + "\nprice=" + DoubleToString(g_trade.ResultPrice(), dg) + "\nvolume="
           + DoubleToString(g_trade.ResultVolume(), 4) + "\nsl=" + DoubleToString(sl, dg) + "\nrisk_money=" + DoubleToString(r1 * vol, 2) + "\n";
   return "";
  }

string DoClose(const string &k[], const string &v[], string &extra)
  {
   ulong t = (ulong)StringToInteger(KV(k, v, "ticket", "0"));
   if(t == 0 || !PositionSelectByTicket(t) || PositionGetInteger(POSITION_MAGIC) != InpMagic) return "position introuvable";
   string nm = PositionGetString(POSITION_SYMBOL);
   double have = PositionGetDouble(POSITION_VOLUME), vol = StringToDouble(KV(k, v, "volume", "0"));
   g_trade.SetTypeFillingBySymbol(nm);
   bool ok = (vol > 0 && vol < have - 1e-9) ? g_trade.PositionClosePartial(t, vol) : g_trade.PositionClose(t);
   if(!Done(ok)) return Refusal();
   extra = "price=" + DoubleToString(g_trade.ResultPrice(), (int)SymbolInfoInteger(nm, SYMBOL_DIGITS)) + "\n";
   return "";
  }

// modification : le stop ne peut que se rapprocher du prix ; l'objectif est libre
string DoModify(const string &k[], const string &v[], string &extra)
  {
   ulong t = (ulong)StringToInteger(KV(k, v, "ticket", "0"));
   if(t == 0 || !PositionSelectByTicket(t) || PositionGetInteger(POSITION_MAGIC) != InpMagic) return "position introuvable";
   string nm = PositionGetString(POSITION_SYMBOL);
   int dg = (int)SymbolInfoInteger(nm, SYMBOL_DIGITS);
   double pt = SymbolInfoDouble(nm, SYMBOL_POINT);
   double lvl = (double)SymbolInfoInteger(nm, SYMBOL_TRADE_STOPS_LEVEL) * pt;
   bool buy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
   double cur_sl = PositionGetDouble(POSITION_SL), cur_tp = PositionGetDouble(POSITION_TP);
   double sl = HasKey(k, "sl") ? NormalizeDouble(StringToDouble(KV(k, v, "sl")), dg) : cur_sl;
   double tp = HasKey(k, "tp") ? NormalizeDouble(StringToDouble(KV(k, v, "tp")), dg) : cur_tp;
   MqlTick tk;
   if(!SymbolInfoTick(nm, tk)) return "pas de prix";
   if(!MathIsValidNumber(sl) || !MathIsValidNumber(tp)) return "nombre illisible dans l'ordre";
   if(sl <= 0) return "stop obligatoire";
   if(cur_sl > 0 && ((buy && sl < cur_sl - pt / 2) || (!buy && sl > cur_sl + pt / 2))) return "le stop ne peut que se rapprocher du prix";
   if(MathAbs(sl - cur_sl) > pt / 2 && ((buy && sl >= tk.bid - lvl) || (!buy && sl <= tk.ask + lvl))) return "stop trop pres du prix";
   if(MathAbs(sl - cur_sl) > pt / 2 || MathAbs(tp - cur_tp) > pt / 2)   // rien a changer = deja fait (le serveur repondrait 10025 "no changes")
      if(!Done(g_trade.PositionModify(t, sl, tp))) return Refusal();
   extra = "sl=" + DoubleToString(sl, dg) + "\ntp=" + DoubleToString(tp, dg) + "\n";
   return "";
  }

void RunCommand(const string file)
  {
   string k[], v[];
   string id = StringSubstr(file, 0, StringLen(file) - 4);
   string path = DIR + "cmd\\" + file;
   string why = "", extra = "";
   // l'ordre est d'abord retire du dossier cmd : quoi qu'il arrive ensuite, il ne peut pas etre execute deux fois
   string taken = DIR + "done\\" + file;
   if(!FileMove(path, 0, taken, FILE_REWRITE))
     {
      FolderCreate("claude\\done");                                     // dossier efface ? on le recree
      if(!FileMove(path, 0, taken, FILE_REWRITE)) return;               // encore en cours d'ecriture, ou deja pris : au prochain tour
     }
   ReadKV(taken, k, v);                                                 // illisible = aucune cle = "action inconnue"
   string action = KV(k, v, "action");
   if(action == "open") why = DoOpen(k, v, extra);
   else if(action == "close") why = DoClose(k, v, extra);
   else if(action == "modify") why = DoModify(k, v, extra);
   else if(action == "close_all")
     {
      int failed = CloseAll("ordre du cerveau");
      if(failed > 0) why = IntegerToString(failed) + " position(s) non fermee(s)";
     }
   else if(action == "ping") extra = "pong=1\n";
   else why = "action inconnue";
   Put("res\\" + id + ".txt", "id=" + id + "\naction=" + action + "\nok=" + (why == "" ? "1" : "0") + "\nreason=" + why + "\n" + extra
       + "server_time=" + IntegerToString((long)TimeTradeServer()) + "\n");
   if(action != "ping") g_last_msg = TimeToString(TimeTradeServer(), TIME_MINUTES) + " " + action + " " + KV(k, v, "symbol") + " "
                                     + KV(k, v, "side") + (why == "" ? " : execute" : " : refuse (" + why + ")");
   g_dirty = true;
  }

void ProcessCommands()
  {
   string fn;
   string files[];
   long h = FileFindFirst(DIR + "cmd\\*.txt", fn);
   if(h == INVALID_HANDLE) return;
   int n = 0;
   do
     {
      ArrayResize(files, n + 1);
      files[n++] = fn;
     }
   while(FileFindNext(h, fn) && n < 100);
   FileFindClose(h);
   for(int i = 0; i < n - 1; i++)                                       // dans l'ordre des identifiants
      for(int j = i + 1; j < n; j++)
         if(StringCompare(files[j], files[i]) < 0) { string tmp = files[i]; files[i] = files[j]; files[j] = tmp; }
   for(int i = 0; i < n; i++) RunCommand(files[i]);
  }

void ReadBrain()
  {
   string k[], v[];
   if(ReadKV(DIR + "brain_alive.txt", k, v) > 0) g_brain_ts = (datetime)StringToInteger(KV(k, v, "time_gmt", "0"));
  }

void Show()
  {
   string why = Blocked();
   string s = "ROBOT CLAUDE - les mains (v" + VERSION + ")\n";
   s += "Cerveau : ";
   s += (TimeGMT() - g_brain_ts <= InpBrainTimeoutSec ? "connecte" : "MUET");
   s += "\n";
   s += "Nouvelles positions : " + (why == "" ? "autorisees" : "BLOQUEES (" + why + ")") + "\n";
   s += "Positions du robot : " + IntegerToString(CountPositions()) + " / " + IntegerToString(InpMaxPositions) + "\n";
   s += "Fonds : " + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) + "   depart : " + DoubleToString(GlobalVariableGet("CM_start"), 2) + "\n";
   string mk = "";
   for(int i = 0; i < ArraySize(g_base); i++) mk += g_base[i] + " -> " + (g_name[i] == "" ? "INTROUVABLE" : g_name[i]) + "   ";
   s += "Marches : " + mk + "\n";
   s += "Dernier evenement : " + g_last_msg + "\n";
   Comment(s);
  }

//+------------------------------------------------------------------+
//| Evenements                                                       |
//+------------------------------------------------------------------+
int OnInit()
  {
   FolderCreate("claude");
   FolderCreate("claude\\cmd");
   FolderCreate("claude\\res");
   FolderCreate("claude\\done");
   int n = StringSplit(InpSymbols, ',', g_base);
   ArrayResize(g_name, n);
   string all = "";
   for(int i = 0; i < n; i++)
     {
      StringTrimLeft(g_base[i]);
      StringTrimRight(g_base[i]);
      g_name[i] = Resolve(g_base[i]);
      Print("ClaudeMains: ", g_base[i], " -> ", g_name[i] == "" ? "INTROUVABLE" : g_name[i]);
     }
   int total = SymbolsTotal(false);
   for(int i = 0; i < total && i < 5000; i++) all += SymbolName(i, false) + "\n";
   Put("all_symbols.txt", all);                                         // pour retrouver un nom si un marche est introuvable
   g_trade.SetExpertMagicNumber((ulong)InpMagic);
   g_trade.SetDeviationInPoints((ulong)InpSlippagePts);
   if(InpResetLocks)
     {
      GlobalVariableSet("CM_killed", 0.0);
      GlobalVariableSet("CM_day_lock", 0.0);
      GlobalVariableSet("CM_day", 0.0);                                 // la reference du jour repart du solde actuel, sinon le blocage revient aussitot
      GlobalVariableDel("CM_start");
     }
   if(!GlobalVariableCheck("CM_start")) GlobalVariableSet("CM_start", 0.0);   // fixe dans Watch() des que le compte est charge
   if(!GlobalVariableCheck("CM_killed")) GlobalVariableSet("CM_killed", 0.0);
   if(!GlobalVariableCheck("CM_day_lock")) GlobalVariableSet("CM_day_lock", 0.0);
   GlobalVariablesFlush();
   EventSetTimer(1);
   Watch();
   ExportAccount();
   ExportPositions();
   ExportMinute();
   Show();
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   Comment("");
  }

void OnTimer()
  {
   datetime now = TimeTradeServer();
   ReadBrain();
   ProcessCommands();
   Watch();
   if(g_dirty || now - g_last_fast >= 5 || now < g_last_fast)          // (now < ... : l'horloge du serveur a recule)
     {
      bool traded = g_dirty;
      g_dirty = false;
      g_last_fast = now;
      ExportAccount();
      ExportPositions();
      if(traded) ExportDeals();                    // le cerveau voit ses transactions tout de suite, pas a la minute suivante
     }
   datetime minute = now - now % 60;
   if(minute != g_last_min)
     {
      g_last_min = minute;
      ExportMinute();
     }
   Show();
  }

void OnTick()
  {
  }

void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
  {
   g_dirty = true;
  }
