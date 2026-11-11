//+------------------------------------------------------------------+
//|                                                 ClaudeMains.mq5  |
//|  "Les mains" du robot. Ce programme ne decide RIEN : il envoie    |
//|  les donnees du marche au cerveau (un programme sur l'ordinateur) |
//|  et execute les ordres que le cerveau lui renvoie.                |
//|                                                                  |
//|  Echanges par fichiers dans MQL5\Files\claude\ :                  |
//|   mains -> cerveau : account.txt, positions.csv, symbols.csv,     |
//|                      deals.csv, bars_<marche>_<M1|M5|H1|D1>.csv   |
//|   cerveau -> mains : brain_alive.txt (time_gmt=secondes UTC)      |
//|                      cmd\<id>.txt   (lignes cle=valeur)           |
//|   mains -> cerveau : res\<id>.txt   (ok=1/0, raison, ticket...)   |
//|   Un ordre est deplace dans done\ AVANT d'etre execute : il n'est |
//|   jamais execute deux fois. Au plus 5 ordres par seconde, et une  |
//|   seule ouverture par seconde. <id> commence par l'heure d'envoi  |
//|   en millisecondes UTC (13 chiffres) : les fichiers de res\ et    |
//|   done\ de plus de 24 h sont effaces.                             |
//|                                                                  |
//|  Les limites sont ICI et le cerveau ne peut pas les contourner :  |
//|   1. Aucun ordre sans stop ; le stop est pose chez le courtier    |
//|      (verifie apres l'execution ; une position du robot restee    |
//|      sans stop est refermee).                                     |
//|   2. Un stop ne peut que se rapprocher du prix, jamais s'eloigner.|
//|   3. Risque max par trade : la taille est reduite d'office.       |
//|      Stop a 3 ecarts achat-vente du prix au moins ; valeur de la  |
//|      position : 20 fois le solde au plus ; prix vieux de 10 s au  |
//|      plus ; si le risque au prix reellement obtenu depasse la     |
//|      limite de plus de 25 %, la position est refermee aussitot.   |
//|   4. Nombre max de positions (au total et par marche).            |
//|   5. Perte max du jour (resultat du robot depuis minuit, heure du |
//|      serveur, relu dans l'historique du compte : un depot ou un   |
//|      retrait ne compte pas) : tout est ferme, blocage jusqu'a     |
//|      demain.                                                      |
//|   6. Arret definitif a -50 % du capital de depart (note aussi     |
//|      dans le fichier MQL5\Files\ClaudeMains_arret.txt).           |
//|   7. Cerveau muet, ou dont l'horloge avance : plus aucune         |
//|      nouvelle position (les stops restent en place) ; duree max   |
//|      par position respectee.                                      |
//|   8. Tout est ferme le vendredi soir si MT5 tourne a ce moment ;  |
//|      sinon a la premiere occasion, des la reprise.                |
//|  Il ne touche jamais aux positions ouvertes a la main.            |
//|  Il refuse de demarrer avec le numero magique 0 ou sur un compte  |
//|  qui n'est pas en mode "hedging".                                 |
//+------------------------------------------------------------------+
#property copyright "gold-orb lab"
#property version   "1.10"
#property description "Les mains de Claude : exporte les donnees, execute les ordres du cerveau, impose les limites (stop obligatoire, risque max, perte du jour, arret a -50 %)."

#include <Trade\Trade.mqh>

input string InpSymbols         = "XAUUSD,US100,BTCUSD,ETHUSD,EURUSD,USDJPY"; // Marches (noms de base ; le suffixe du courtier est trouve tout seul)
input double InpMaxRiskPct      = 1.0;      // Risque max par trade si le stop est touche (% du solde)
input double InpMaxNotionalX    = 20.0;     // Valeur max d'une position, en nombre de fois le solde
input int    InpMaxTickAgeSec   = 10;       // Age max du dernier prix pour ouvrir une position, en secondes (0 = pas de controle)
input int    InpMaxPositions    = 6;        // Positions ouvertes en meme temps (total)
input int    InpMaxPerSymbol    = 2;        // Positions ouvertes en meme temps par marche
input double InpDailyLossPct    = 6.0;      // Perte max du jour (% du solde du debut de journee) : tout ferme + blocage
input double InpKillPct         = 50.0;     // Arret definitif si les fonds perdent ce % du capital de depart
input double InpStartBalance    = 0.0;      // Capital de depart (0 = solde au premier lancement)
input int    InpBrainTimeoutSec = 180;      // Cerveau muet depuis ce delai (secondes) : plus de nouvelle position
input int    InpFridayClose     = 2350;     // Vendredi, heure serveur HHMM ou tout est ferme (0 = desactive) ; plus tot les semaines de jour ferie
input long   InpMagic           = 20261110; // Numero magique des positions du robot (jamais 0)
input int    InpSlippagePts     = 50;       // Glissement max accepte (points)
input bool   InpPush            = true;     // Notifications push (appli MT5 mobile) pour les blocages
input bool   InpResetLocks      = false;    // Mettre true UNE fois pour lever un blocage ou l'arret, puis remettre false (laisse sur true, il est ignore)

const string DIR              = "claude\\";
const string VERSION          = "1.10";
const string KILL_FILE        = "ClaudeMains_arret.txt";   // l'arret definitif est aussi note dans ce fichier (dans MQL5\Files)
const double MIN_STOP_SPREADS = 3.0;                       // distance minimale du stop a l'ouverture, en ecarts achat-vente
const int    MAX_PER_PASS     = 5;                         // ordres du cerveau executes par passage (un passage par seconde)

CTrade   g_trade;
string   g_base[];            // noms de base demandes (XAUUSD, US100, ...)
string   g_name[];            // noms reels chez le courtier (XAUUSD.r, ...) ; "" = introuvable
datetime g_last_min   = 0;    // derniere minute serveur exportee
datetime g_last_fast  = 0;    // dernier export compte / positions
datetime g_next_close = 0;    // prochaine tentative de fermeture d'office
datetime g_last_warn  = 0;    // dernier avertissement "fermeture impossible"
datetime g_last_sum   = 0;    // dernier releve des transactions du jour dans l'historique
datetime g_last_tidy  = 0;    // dernier menage
datetime g_brain_ts   = 0;    // dernier signe de vie du cerveau (UTC)
bool     g_brain_told = false;// l'horloge du cerveau en avance a deja ete signalee
datetime g_push_sec   = 0;    // seconde de la derniere notification push
int      g_push_n     = 0;    // notifications push envoyees dans cette seconde
bool     g_flat       = false;// un blocage impose de tout fermer (etat au passage precedent)
double   g_day_done   = 0.0;  // resultat du robot aujourd'hui, transactions faites (positions encore ouvertes non comprises)
double   g_day_bal    = 0.0;  // solde du debut de journee
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
   datetime now = TimeTradeServer();
   g_last_msg = TimeToString(now, TIME_DATE | TIME_MINUTES) + " " + msg;
   Print("ClaudeMains: ", msg);
   if(now != g_push_sec)
     {
      g_push_sec = now;
      g_push_n = 0;
     }
   if(InpPush && g_push_n < 2)                                          // MT5 tolere 2 notifications par seconde ; au-dela il peut couper le service
     {
      g_push_n++;
      SendNotification("Robot Claude : " + msg);
     }
  }

// l'arret definitif est aussi note dans un fichier : MT5 n'ecrit ses variables globales sur le disque qu'a sa fermeture
// normale (d'ou les GlobalVariablesFlush plus bas) et les efface apres 4 semaines sans usage
void KillFile(const bool on)
  {
   if(!on) { FileDelete(KILL_FILE); return; }
   int h = FileOpen(KILL_FILE, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE) return;
   FileWriteString(h, "start=" + DoubleToString(GlobalVariableGet("CM_start"), 2) + "\n");
   FileClose(h);
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

// perte en devise du compte si le stop est touche, pour `vol` lots (avec sl = 0 : la valeur de la position)
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

// compte "hedging" : plusieurs positions par marche, chacune avec son ticket (le robot ne sait pas faire autrement)
bool Hedging()
  {
   return AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING;
  }

bool FridayClosed(const datetime now)
  {
   if(InpFridayClose <= 0) return false;
   MqlDateTime d;
   TimeToStruct(now, d);
   return d.day_of_week == 6 || d.day_of_week == 0 || (d.day_of_week == 5 && d.hour * 100 + d.min >= InpFridayClose);
  }

// instant (heure serveur) de la derniere fermeture du vendredi soir : une position du robot ouverte avant aurait du etre
// fermee ce soir-la (0 si la fermeture du vendredi est desactivee)
datetime LastFridayClose(const datetime now)
  {
   if(InpFridayClose <= 0) return 0;
   MqlDateTime d;
   TimeToStruct(now, d);
   datetime t = now - now % 86400 - ((d.day_of_week + 2) % 7) * 86400 + (InpFridayClose / 100) * 3600 + (InpFridayClose % 100) * 60;
   if(t > now) t -= 7 * 86400;
   return t;
  }

// raison pour laquelle aucune NOUVELLE position n'est acceptee ("" = rien ne bloque)
string Blocked()
  {
   if(GlobalVariableGet("CM_killed") != 0) return "arret definitif (-" + DoubleToString(InpKillPct, 0) + " %)";
   if(GlobalVariableGet("CM_day_lock") != 0) return "perte max du jour atteinte";
   if(FridayClosed(TimeTradeServer())) return "fermeture du week-end";
   if(!TradeAllowed()) return "trading automatique desactive dans MT5";
   if(!Hedging()) return "compte sans hedging";
   if(TimeGMT() - g_brain_ts > InpBrainTimeoutSec) return "cerveau muet";
   return "";
  }

// resultat latent des positions ouvertes du robot
double RobotFloating()
  {
   double sum = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      sum += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
     }
   return sum;
  }

// somme des transactions du robot depuis `since` (profit + swap + commission + frais), relue dans l'historique du compte.
// Une sortie faite par le courtier (stop, objectif) peut porter le numero magique 0 : une transaction est au robot si sa
// position a ete ouverte par lui. Renvoie false si l'historique n'a pas pu etre lu.
bool RobotDeals(const datetime since, double &sum)
  {
   if(!HistorySelect(0, TimeTradeServer() + 86400)) return false;
   long ids[];                                                          // identifiants des positions du robot
   int n = 0, total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0 || HistoryDealGetInteger(d, DEAL_MAGIC) != InpMagic) continue;
      ArrayResize(ids, n + 1, 1000);
      ids[n++] = HistoryDealGetInteger(d, DEAL_POSITION_ID);
     }
   sum = 0.0;
   for(int i = 0; i < total; i++)
     {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0 || HistoryDealGetInteger(d, DEAL_TIME) < since) continue;
      long type = HistoryDealGetInteger(d, DEAL_TYPE);
      if(type != DEAL_TYPE_BUY && type != DEAL_TYPE_SELL) continue;      // depot, retrait, correction : pas un resultat de trading
      long id = HistoryDealGetInteger(d, DEAL_POSITION_ID);
      bool mine = false;
      for(int j = n - 1; j >= 0 && !mine; j--) mine = (ids[j] == id);
      if(mine)
         sum += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION)
                + HistoryDealGetDouble(d, DEAL_FEE);
     }
   return true;
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
   s += "hedging=" + IntegerToString(Hedging() ? 1 : 0) + "\n";
   s += "server=" + AccountInfoString(ACCOUNT_SERVER) + "\n";
   s += "trade_allowed=" + IntegerToString(TradeAllowed() ? 1 : 0) + "\n";
   s += "blocked=" + Blocked() + "\n";
   s += "start_balance=" + DoubleToString(GlobalVariableGet("CM_start"), 2) + "\n";
   s += "day_start_balance=" + DoubleToString(g_day_bal, 2) + "\n";
   s += "day_result=" + DoubleToString(g_day_done + RobotFloating(), 2) + "\n";
   s += "max_risk_pct=" + DoubleToString(InpMaxRiskPct, 2) + "\n";
   s += "max_notional_x=" + DoubleToString(InpMaxNotionalX, 2) + "\n";
   s += "min_stop_spreads=" + DoubleToString(MIN_STOP_SPREADS, 2) + "\n";
   s += "max_tick_age_sec=" + IntegerToString(InpMaxTickAgeSec) + "\n";
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
      string gv = "CM_ttl_" + IntegerToString(PositionGetInteger(POSITION_IDENTIFIER));
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
// ferme la position selectionnee (ticket t) ; false si elle n'a pas ete fermee (le code du refus reste dans g_trade)
bool ClosePosition(const ulong t, const string why)
  {
   g_trade.SetTypeFillingBySymbol(PositionGetString(POSITION_SYMBOL));
   bool ok = g_trade.PositionClose(t);
   uint rc = g_trade.ResultRetcode();
   if(ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED || rc == TRADE_RETCODE_DONE_PARTIAL)) return true;
   Print("ClaudeMains: fermeture refusee (", why, ") ticket ", t, " : ", rc, " ", g_trade.ResultRetcodeDescription());
   return false;
  }

// ferme toutes les positions du robot ; renvoie le nombre de celles qui n'ont PAS pu etre fermees
int CloseAll(const string why)
  {
   int failed = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(!ClosePosition(t, why)) failed++;
     }
   g_dirty = true;
   return failed;
  }

// releve le compte et pose les blocages (arret definitif, perte max du jour). Appelee a chaque passage ET avant chaque
// ordre du cerveau. Renvoie false tant que le compte n'est pas charge (MT5 vient de demarrer) : rien n'est alors conclu.
bool Locks()
  {
   datetime now = TimeTradeServer();
   datetime day = now - now % 86400;
   double bal = AccountInfoDouble(ACCOUNT_BALANCE), eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(TerminalInfoInteger(TERMINAL_CONNECTED) == 0 || bal <= 0) return false;
   if(GlobalVariableGet("CM_start") <= 0)
     {
      GlobalVariableSet("CM_start", InpStartBalance > 0 ? InpStartBalance : bal);
      GlobalVariablesFlush();                                           // ecrit sur le disque tout de suite (sinon perdu si MT5 plante)
     }
   if(GlobalVariableGet("CM_day_from") < 0)                             // InpResetLocks vient d'agir : la perte du jour repart de maintenant
     {
      GlobalVariableSet("CM_day_from", (double)(now + 1));
      GlobalVariablesFlush();
     }
   if((datetime)GlobalVariableGet("CM_day") != day)                     // nouvelle journee serveur
     {
      GlobalVariableSet("CM_day", (double)day);
      GlobalVariableSet("CM_day_lock", 0.0);
      GlobalVariablesFlush();
      g_last_sum = 0;
     }
   // resultat du jour relu dans l'historique : apres chaque transaction, et une fois par minute
   if(g_dirty || g_last_sum == 0 || now - g_last_sum >= 60 || now < g_last_sum)
     {
      datetime since = (datetime)GlobalVariableGet("CM_day_from");
      double sum = 0.0;
      if(RobotDeals(since > day ? since : day, sum))
        {
         g_day_done = sum;
         g_last_sum = now;
        }
     }
   g_day_bal = bal - g_day_done;                                        // solde du debut de journee (un depot ou un retrait du jour y est compte)
   double start = GlobalVariableGet("CM_start");
   if(GlobalVariableGet("CM_killed") == 0 && start > 0 && eq <= start * (1.0 - InpKillPct / 100.0))
     {
      GlobalVariableSet("CM_killed", 1.0);
      GlobalVariablesFlush();
      KillFile(true);
      Notify("ARRET DEFINITIF : fonds " + DoubleToString(eq, 2) + ", capital de depart " + DoubleToString(start, 2) + ". Tout est ferme.");
     }
   if(GlobalVariableGet("CM_day_lock") == 0 && InpDailyLossPct > 0 && g_day_bal > 0
      && g_day_done + RobotFloating() <= -g_day_bal * InpDailyLossPct / 100.0)
     {
      GlobalVariableSet("CM_day_lock", 1.0);
      GlobalVariablesFlush();
      Notify("Perte max du jour atteinte : tout est ferme, reprise demain.");
     }
   return true;
  }

// raison pour laquelle la position selectionnee (du robot) doit etre fermee d'office ("" = aucune)
string MustClose(const datetime now, const bool flat, const datetime friday)
  {
   if(flat) return "blocage";
   datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
   if(opened < friday) return "Fermeture du week-end manquee";
   if(PositionGetDouble(POSITION_SL) <= 0 && now - opened >= 5) return "Position sans stop chez le courtier";
   // duree max posee a l'ouverture ; rangee sous l'identifiant de la position, qui ne change jamais (le ticket, lui, peut changer)
   string gv = "CM_ttl_" + IntegerToString(PositionGetInteger(POSITION_IDENTIFIER));
   if(GlobalVariableCheck(gv) && now >= (datetime)GlobalVariableGet(gv)) return "Duree max atteinte";
   return "";
  }

// les fermetures d'office : blocage (arret definitif, perte du jour, week-end), fermeture du week-end manquee, position
// restee sans stop, duree max atteinte. On insiste toutes les 10 s tant qu'il en reste (toutes les 60 s si le marche est ferme).
void Watch()
  {
   if(!Locks()) return;
   datetime now = TimeTradeServer();
   bool flat = GlobalVariableGet("CM_killed") != 0 || GlobalVariableGet("CM_day_lock") != 0 || FridayClosed(now);
   if(flat != g_flat)                                                   // un blocage vient de tomber : on ferme tout de suite
     {
      g_flat = flat;
      g_next_close = 0;
     }
   if(now < g_next_close && g_next_close - now <= 120) return;         // (au-dela de 120 s : l'horloge du serveur a recule)
   datetime friday = LastFridayClose(now);
   int tried = 0, bad = 0, shut = 0;
   string told = "";                                                    // ce qui a ete ferme a ce passage (une seule notification)
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      string why = MustClose(now, flat, friday);
      if(why == "") continue;
      tried++;
      if(ClosePosition(t, why))
        {
         if(!flat) told += (told == "" ? "" : ", ") + why + " : position " + IntegerToString((long)t) + " fermee";
        }
      else
        {
         bad++;
         if(g_trade.ResultRetcode() == TRADE_RETCODE_MARKET_CLOSED) shut++;
        }
     }
   if(tried == 0) return;
   g_dirty = true;
   g_next_close = now + ((bad > 0 && shut == bad) ? 60 : 10);
   if(told != "") Notify(StringSubstr(told, 0, 230) + ".");
   if(bad > 0 && (now - g_last_warn >= 3600 || now < g_last_warn))    // l'utilisateur doit le savoir (une fois par heure au plus)
     {
      g_last_warn = now;
      Notify("ATTENTION : " + IntegerToString(bad) + " position(s) du robot devraient etre fermees et ne le sont pas ("
             + (shut == bad ? "marche ferme" : (TradeAllowed() ? "refus du courtier" : "trading automatique desactive dans MT5")) + ").");
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
   uint rc = g_trade.ResultRetcode();
   // CTrade peut renoncer avant tout envoi : le code lu est alors celui de l'ordre PRECEDENT (souvent "fait"), a ne pas montrer
   if(rc == 0 || rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED || rc == TRADE_RETCODE_DONE_PARTIAL)
      return "refuse avant l'envoi au serveur (rien n'a ete envoye)";
   return "refuse par le serveur : " + IntegerToString((long)rc) + " " + g_trade.ResultRetcodeDescription();
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
   // la taille est calculee sur ce prix : s'il date, le prix obtenu peut etre loin et le risque reel au-dessus de la limite
   if(InpMaxTickAgeSec > 0 && (long)TimeTradeServer() - (long)tk.time > InpMaxTickAgeSec) return "prix trop ancien (marche ferme ou en pause)";
   if(SymbolInfoInteger(nm, SYMBOL_TRADE_MODE) != SYMBOL_TRADE_MODE_FULL) return "marche ferme ou non negociable";
   if((SymbolInfoInteger(nm, SYMBOL_ORDER_MODE) & SYMBOL_ORDER_SL) == 0) return "ce marche n'accepte pas de stop chez le courtier";   // sinon CTrade enleve le stop sans rien dire
   int dg = (int)SymbolInfoInteger(nm, SYMBOL_DIGITS);
   double pt = SymbolInfoDouble(nm, SYMBOL_POINT);
   double lvl = (double)SymbolInfoInteger(nm, SYMBOL_TRADE_STOPS_LEVEL) * pt;
   double price = (dir > 0) ? tk.ask : tk.bid;
   double sl = NormalizeDouble(StringToDouble(KV(k, v, "sl", "0")), dg);
   double tp = NormalizeDouble(StringToDouble(KV(k, v, "tp", "0")), dg);
   double want = StringToDouble(KV(k, v, "volume", "0"));
   if(!MathIsValidNumber(sl) || !MathIsValidNumber(tp) || !MathIsValidNumber(want)) return "nombre illisible dans l'ordre";
   if(sl <= 0) return "stop obligatoire";
   if((dir > 0 && sl >= tk.bid - lvl) || (dir < 0 && sl <= tk.ask + lvl)) return "stop du mauvais cote ou trop pres";
   // un stop colle au prix donnerait une taille enorme pour le meme risque affiche : le moindre saut de prix le depasserait
   double room = (dir > 0) ? tk.bid - sl : sl - tk.ask;
   double mind = MIN_STOP_SPREADS * (tk.ask - tk.bid);
   if(room < mind - pt / 2)
      return "stop trop serre : il doit etre a au moins " + DoubleToString(MIN_STOP_SPREADS, 0) + " ecarts achat-vente du prix (" + DoubleToString(mind, dg) + ")";
   if(tp > 0 && ((dir > 0 && tp <= tk.ask + lvl) || (dir < 0 && tp >= tk.bid - lvl))) return "objectif du mauvais cote ou trop pres";
   double vmin = SymbolInfoDouble(nm, SYMBOL_VOLUME_MIN), vstep = SymbolInfoDouble(nm, SYMBOL_VOLUME_STEP);
   double vmax = SymbolInfoDouble(nm, SYMBOL_VOLUME_MAX);
   if(vstep <= 0) vstep = vmin;
   double r1 = RiskMoney(nm, price, sl, 1.0);                           // perte d'un lot si le stop est touche
   double n1 = RiskMoney(nm, price, 0.0, 1.0);                          // valeur d'un lot
   if(!MathIsValidNumber(r1) || r1 <= 0 || n1 <= 0 || vmin <= 0) return "risque impossible a calculer";
   if(want < vmin) return "volume demande nul ou inferieur au lot minimum (" + DoubleToString(vmin, 2) + ")";
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double cap = bal * InpMaxRiskPct / 100.0;                            // perte max si le stop est touche
   double big = bal * InpMaxNotionalX;                                  // valeur max de la position
   double vol = MathMin(MathMin(want, vmax), MathMin(cap / r1, big / n1));
   vol = NormalizeDouble(MathFloor(vol / vstep + 1e-9) * vstep, 8);     // taille reduite d'office (multiple exact du pas, jamais arrondie vers le haut)
   if(vol < vmin && r1 * vmin > cap)
      return "limite de risque : le lot minimum (" + DoubleToString(vmin, 2) + ") risquerait " + DoubleToString(r1 * vmin, 2)
             + ", limite " + DoubleToString(cap, 2);
   if(vol < vmin)
      return "limite de taille : le lot minimum (" + DoubleToString(vmin, 2) + ") vaut " + DoubleToString(n1 * vmin, 2)
             + ", limite " + DoubleToString(big, 2);
   if(CountPositions() >= InpMaxPositions) return "trop de positions ouvertes";
   if(CountPositions(nm) >= InpMaxPerSymbol) return "trop de positions sur ce marche";
   double need = 0.0;
   if(OrderCalcMargin(dir > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, nm, vol, price, need) && need > AccountInfoDouble(ACCOUNT_MARGIN_FREE))
      return "marge insuffisante";
   g_trade.SetTypeFillingBySymbol(nm);
   string cm = StringSubstr("CM " + Clean(KV(k, v, "tag")), 0, 27);
   bool ok = (dir > 0) ? g_trade.Buy(vol, nm, 0.0, sl, tp, cm) : g_trade.Sell(vol, nm, 0.0, sl, tp, cm);
   if(!Done(ok)) return Refusal();
   // la position telle que le courtier la tient : prix reellement obtenu, stop reellement pose
   ulong pos = g_trade.ResultOrder();
   double fill = g_trade.ResultPrice(), got = g_trade.ResultVolume();
   bool seen = (pos > 0 && PositionSelectByTicket(pos));                // (MT5 peut ne la lister qu'un instant plus tard)
   if(seen)
     {
      fill = PositionGetDouble(POSITION_PRICE_OPEN);
      got = PositionGetDouble(POSITION_VOLUME);
     }
   if(fill <= 0) fill = price;
   if(got <= 0) got = vol;
   double risk = RiskMoney(nm, fill, sl, got);
   extra = "ticket=" + IntegerToString((long)pos) + "\nprice=" + DoubleToString(fill, dg) + "\nvolume=" + DoubleToString(got, 4)
           + "\nsl=" + DoubleToString(sl, dg) + "\nrisk_money=" + DoubleToString(risk, 2) + "\n";
   string bad = "";
   if(risk > cap * 1.25) bad = "glissement trop fort (risque " + DoubleToString(risk, 2) + " pour une limite de " + DoubleToString(cap, 2) + ")";
   else if(seen && PositionGetDouble(POSITION_SL) <= 0)                 // stop absent chez le courtier : on le pose ; s'il est refuse, on referme
     {
      bool placed = g_trade.PositionModify(pos, sl, tp);
      if(!Done(placed) && g_trade.ResultRetcode() != TRADE_RETCODE_NO_CHANGES) bad = "le courtier n'a pas pose le stop";
     }
   long ttl = StringToInteger(KV(k, v, "ttl_min", "0"));
   datetime until = 0;                                                  // duree max de la position (voir MustClose)
   if(ttl > 0) until = (datetime)(TimeTradeServer() + ttl * 60);
   if(bad != "")
     {
      Notify("Ouverture annulee, " + bad + " : position " + IntegerToString((long)pos) + " refermee d'office.");
      until = 0;
      if(!seen || !ClosePosition(pos, bad))                             // pas encore listee, ou fermeture refusee : Watch() s'en charge
        {
         until = TimeTradeServer();
         g_next_close = 0;
        }
     }
   if(until > 0 && pos > 0)
     {
      GlobalVariableSet("CM_ttl_" + IntegerToString((long)pos), (double)until);
      GlobalVariablesFlush();
     }
   return (bad == "") ? "" : bad + " : position refermee d'office";
  }

string DoClose(const string &k[], const string &v[], string &extra)
  {
   ulong t = (ulong)StringToInteger(KV(k, v, "ticket", "0"));
   if(t == 0 || !PositionSelectByTicket(t) || PositionGetInteger(POSITION_MAGIC) != InpMagic) return "position introuvable";
   string nm = PositionGetString(POSITION_SYMBOL);
   double have = PositionGetDouble(POSITION_VOLUME), vol = StringToDouble(KV(k, v, "volume", "0"));
   g_trade.SetTypeFillingBySymbol(nm);
   bool ok = (vol > 0 && vol < have - 1e-9) ? g_trade.PositionClosePartial(t, vol) : g_trade.PositionClose(t);
   if(!Done(ok)) return PositionSelectByTicket(t) ? Refusal() : "position introuvable (deja fermee)";
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
   if(cur_sl <= 0)                                                      // position restee sans stop : le stop demande doit tenir dans la limite de risque
     {
      double risk = RiskMoney(nm, PositionGetDouble(POSITION_PRICE_OPEN), sl, PositionGetDouble(POSITION_VOLUME));
      if(risk < 0 || risk > AccountInfoDouble(ACCOUNT_BALANCE) * InpMaxRiskPct / 100.0 * 1.25)
         return "position sans stop : le stop demande depasse la limite de risque";
     }
   if(MathAbs(sl - cur_sl) > pt / 2 && ((buy && sl >= tk.bid - lvl) || (!buy && sl <= tk.ask + lvl))) return "stop trop pres du prix";
   if(MathAbs(sl - cur_sl) > pt / 2 || MathAbs(tp - cur_tp) > pt / 2)   // rien a changer = deja fait (le serveur repondrait 10025 "no changes")
      if(!Done(g_trade.PositionModify(t, sl, tp))) return PositionSelectByTicket(t) ? Refusal() : "position introuvable (deja fermee)";
   extra = "sl=" + DoubleToString(sl, dg) + "\ntp=" + DoubleToString(tp, dg) + "\n";
   return "";
  }

// execute un ordre ; renvoie 0 si le fichier n'a pas pu etre pris (il reste pour le passage suivant), 1 si l'ordre a recu
// sa reponse, 2 si en plus une position vient d'etre ouverte (voir ProcessCommands)
int RunCommand(const string file)
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
      if(!FileMove(path, 0, taken, FILE_REWRITE)) return 0;             // encore en cours d'ecriture, ou deja pris : au prochain tour
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
   return (action == "open" && extra != "") ? 2 : 1;
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
      ArrayResize(files, n + 1, 1000);
      files[n++] = fn;
     }
   while(FileFindNext(h, fn) && n < 5000);
   FileFindClose(h);
   // au plus 5 ordres par passage, du plus ancien identifiant au plus recent, et le passage s'arrete des qu'une position a
   // ete ouverte : la suite attend la seconde d'apres, quand MT5 a mis a jour le compte et la liste des positions.
   // Les blocages sont reverifies avant CHAQUE ordre.
   int count = 0;
   for(int i = 0; i < n && count < MAX_PER_PASS; i++)
     {
      for(int j = i + 1; j < n; j++)                                    // le plus ancien identifiant qui reste vient en files[i]
         if(StringCompare(files[j], files[i]) < 0) { string tmp = files[i]; files[i] = files[j]; files[j] = tmp; }
      Locks();
      int r = RunCommand(files[i]);
      if(r > 0) count++;
      if(r == 2) break;
     }
  }

void ReadBrain()
  {
   string k[], v[];
   if(ReadKV(DIR + "brain_alive.txt", k, v) <= 0) return;
   datetime t = (datetime)StringToInteger(KV(k, v, "time_gmt", "0"));
   if(t > TimeGMT() + 5)                                                // date dans le futur : l'horloge du cerveau est fausse, on ne le croit pas
     {
      if(!g_brain_told) Notify("Signe de vie du cerveau date dans le futur : ignore, cerveau considere comme muet (verifier son horloge).");
      g_brain_told = true;
      t = 0;
     }
   g_brain_ts = t;
  }

// efface dans res\ ou done\ les fichiers de plus de 24 h. L'age est lu dans le nom : l'identifiant d'un ordre commence par
// son heure d'envoi en millisecondes UTC (13 chiffres, voir pont.py) ; un fichier nomme autrement n'est pas touche.
void Purge(const string sub)
  {
   string fn;
   string names[];
   int n = 0;
   long limit = ((long)TimeGMT() - 86400) * 1000;
   long h = FileFindFirst(DIR + sub + "\\*.txt", fn);
   if(h == INVALID_HANDLE) return;
   do
     {
      long ms = StringToInteger(StringSubstr(fn, 0, 13));
      if(StringLen(fn) >= 17 && ms >= 1000000000000 && ms < limit)
        {
         ArrayResize(names, n + 1, 1000);
         names[n++] = fn;
        }
     }
   while(FileFindNext(h, fn) && n < 5000);
   FileFindClose(h);
   for(int i = 0; i < n; i++) FileDelete(DIR + sub + "\\" + names[i]);
  }

// menage, une fois par heure
void Tidy(const datetime now)
  {
   Purge("res");
   Purge("done");
   if(TerminalInfoInteger(TERMINAL_CONNECTED) == 0) return;
   // echeances (duree max) des positions disparues : jetees un jour apres leur date, jamais avant (une position tout juste
   // ouverte, ou un terminal pas encore synchronise, peut ne pas etre listee)
   for(int i = GlobalVariablesTotal() - 1; i >= 0; i--)
     {
      string gv = GlobalVariableName(i);
      if(StringFind(gv, "CM_ttl_") != 0 || now < (datetime)GlobalVariableGet(gv) + 86400) continue;
      long id = StringToInteger(StringSubstr(gv, 7));
      bool alive = false;
      for(int j = PositionsTotal() - 1; j >= 0 && !alive; j--)
         alive = (PositionGetTicket(j) != 0 && PositionGetInteger(POSITION_IDENTIFIER) == id);
      if(!alive) GlobalVariableDel(gv);
     }
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
   // reglages avec lesquels les promesses ne peuvent pas etre tenues : on ne demarre pas
   if(InpMagic == 0)
     {
      Alert("ClaudeMains ne demarre pas : le numero magique (InpMagic) ne doit pas etre 0, c'est celui des positions ouvertes a la main.");
      return INIT_FAILED;
     }
   if(TerminalInfoInteger(TERMINAL_CONNECTED) != 0 && !Hedging())
     {
      Alert("ClaudeMains ne demarre pas : ce compte n'est pas en mode hedging (plusieurs positions par marche). Il faut un compte hedging.");
      return INIT_FAILED;
     }
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
   // InpResetLocks n'agit qu'UNE fois : il faut que les mains l'aient vu sur false a un lancement precedent. Laisse sur true,
   // il leverait l'arret definitif a chaque redemarrage de MT5.
   if(InpResetLocks && GlobalVariableGet("CM_reset_ok") != 0)
     {
      GlobalVariableSet("CM_killed", 0.0);
      GlobalVariableSet("CM_day_lock", 0.0);
      GlobalVariableSet("CM_day_from", -1.0);                           // la perte du jour repart de zero (voir Locks)
      GlobalVariableDel("CM_start");                                    // le capital de depart redevient le solde actuel
      KillFile(false);
      g_last_msg = "blocages leves (InpResetLocks) ; remettre InpResetLocks sur false";
      Print("ClaudeMains: ", g_last_msg);
     }
   else if(InpResetLocks)
     {
      g_last_msg = "InpResetLocks est reste sur true : ignore (le remettre sur false, valider, puis sur true pour lever un blocage)";
      Print("ClaudeMains: ", g_last_msg);
     }
   GlobalVariableSet("CM_reset_ok", InpResetLocks ? 0.0 : 1.0);
   if(!GlobalVariableCheck("CM_start")) GlobalVariableSet("CM_start", 0.0);   // fixe dans Locks() des que le compte est charge
   if(!GlobalVariableCheck("CM_killed")) GlobalVariableSet("CM_killed", 0.0);
   if(!GlobalVariableCheck("CM_day_lock")) GlobalVariableSet("CM_day_lock", 0.0);
   if(FileIsExist(KILL_FILE) && GlobalVariableGet("CM_killed") == 0)    // arret definitif note dans le fichier mais oublie par MT5
     {
      string sk[], sv[];
      if(ReadKV(KILL_FILE, sk, sv) > 0 && StringToDouble(KV(sk, sv, "start", "0")) > 0)
         GlobalVariableSet("CM_start", StringToDouble(KV(sk, sv, "start", "0")));
      GlobalVariableSet("CM_killed", 1.0);
     }
   GlobalVariablesFlush();
   if(!EventSetTimer(1))
     {
      Alert("ClaudeMains ne demarre pas : la minuterie de MT5 n'a pas pu etre lancee. Retirer le robot du graphique et le remettre.");
      return INIT_FAILED;
     }
   g_last_tidy = TimeTradeServer();
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
   if(now - g_last_tidy >= 3600 || now < g_last_tidy)
     {
      g_last_tidy = now;
      Tidy(now);
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
