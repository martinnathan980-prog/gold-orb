//+------------------------------------------------------------------+
//|                                                    ReleveFP.mq5  |
//|  SCRIPT a lancer une fois (le glisser sur n'importe quel          |
//|  graphique). Il ne passe AUCUN ordre ; il ajoute seulement ses    |
//|  marches a la liste Market Watch (pour lire leurs prix).          |
//|  Il releve ce que le courtier facture vraiment :                  |
//|   1. la fiche de chaque marche (lot minimum, taille du contrat,   |
//|      swaps, horaires)            -> claude\releve\fiches.csv      |
//|   2. pour chaque marche, minute par minute sur les derniers       |
//|      jours, les vrais prix vendeur (bid) et acheteur (ask) tires  |
//|      de l'historique des ticks, et en derniere colonne l'ecart    |
//|      le plus petit de la minute (sp_min)                          |
//|                                  -> claude\releve\m1_<marche>.csv |
//|   3. la liste de tous les marches du courtier                     |
//|                                  -> claude\releve\tous.csv        |
//|   4. pour les marches du robot (InpRateSymbols), les barres M1 du |
//|      terminal, celles que le robot lit (prix vendeur, ecart en    |
//|      points), sur le nombre de jours donne pour chaque marche     |
//|      (or 200, les autres 100 : le robot attend 120 ou 60 jours    |
//|      d'historique avant d'etre pret, plus la demo) ; les minutes  |
//|      de tous les marches sont ecrites avant                       |
//|                                  -> claude\releve\r1_<marche>.csv |
//|   5. (1.11) les positions ouvertes du compte au moment du releve  |
//|      (ticket, identifiant, heure, marche, sens, magic, lots, prix |
//|      d'ouverture, stop, objectif, prix courant, swap, resultat)   |
//|                                  -> claude\releve\positions.csv   |
//|   6. (1.11) tout l'historique des transactions du compte (deals), |
//|      de la plus ancienne a la plus recente : heure, ticket,       |
//|      ordre, position, marche, type, entree, raison, magic, lots,  |
//|      prix, stop, objectif, commission, swap, frais, resultat      |
//|                                  -> claude\releve\deals.csv       |
//|      Ni commentaire, ni identifiant externe, ni numero de compte, |
//|      ni nom, ni serveur : aucun texte sauf le nom du marche.      |
//|      Chaque ligne de ces deux fichiers finit par CR LF ("\r\n") : |
//|      FileWriteString ajoute un CR devant un LF seul dans un       |
//|      fichier texte et compte les octets ecrits ; avec le CR deja  |
//|      la, rien n'est ajoute et le compte vaut la longueur.         |
//|  A la fin : claude\releve\fini.txt (resume) et une alerte. Pour   |
//|  chaque marche : jours, minutes, ticks, du, au, derniere_erreur,  |
//|  jours_incomplets (les minutes), puis pour les barres : barres,   |
//|  jours_barres, erreur_barres (jours impossibles a lire),          |
//|  jours_courts (moins de barres que le terminal n'en annonce),     |
//|  erreur_r1 (derniere erreur), jours_r1 (jours demandes), debut_r1 |
//|  et fin_r1 (premiere et derniere barre du terminal), synchro_r1   |
//|  et attente_r1 (secondes d'attente du chargement) ; max_barres :  |
//|  le reglage "Max bars in chart" (il faut 500000, SPEC 1) ; puis   |
//|  positions (lignes de positions.csv, -1 = fichier impossible),    |
//|  positions_heure (heure serveur de la photo des positions),       |
//|  deals (lignes de deals.csv, -1 = fichier ou historique           |
//|  impossible), deals_du et deals_au (heure de la transaction la    |
//|  plus ancienne et de la plus recente, 0 = aucune), erreur_deals   |
//|  (code de GetLastError d'un echec de l'historique ou d'une        |
//|  ecriture, remis a zero juste avant chaque ecriture, -1           |
//|  sans code, 0 = aucun echec). Le nom du serveur n'est plus ecrit. |
//|  Il peut rester plusieurs minutes sur un marche pendant que le    |
//|  terminal telecharge l'historique : c'est normal.                 |
//|  Les heures ecrites sont celles du serveur (secondes).            |
//|  La commission et le swap de chaque transaction sont dans         |
//|  deals.csv (ceux des trades du robot pendant la demo).            |
//+------------------------------------------------------------------+
#property copyright "gold-orb lab"
#property version   "1.11"
#property description "Releve des vrais frais du courtier : fiches des marches, prix acheteur / vendeur minute par minute, barres M1 du terminal (r1), historique des transactions du compte (deals) et positions ouvertes. Ne passe aucun ordre."
#property script_show_inputs

input string InpSymbols  = "BTCUSD,ETHUSD,US100,XAUUSD,USDJPY,JP225,EURUSD,US500,GER40"; // Marches (noms de base, du plus important au moins important)
input int    InpDays     = 30;     // Jours d'historique de ticks a relever
// r1 days per market: the robot is READY on a market only once its bars reach back 120 days (gold) or 60 days (the others,
// CR_Registry.mqh depth), so the replay of the demo needs that depth + a demo of four weeks at most + a week: 155 and 95 days
input string InpRateSymbols = "XAUUSD:200,US100:100,BTCUSD:100,ETHUSD:100"; // Barres M1 du terminal (r1_<marche>.csv) : marche:jours
input int    InpRateWait = 300;    // Attente maximale (secondes) du chargement des barres M1 d'un marche
input int    InpMaxEmpty = 6;      // Passer au marche suivant apres ce nombre de jours vides d'affilee
input bool   InpAllList  = true;   // Ecrire aussi la liste de tous les marches du courtier

const string DIR = "claude\\releve\\";

//+------------------------------------------------------------------+
//| Marches                                                          |
//+------------------------------------------------------------------+
bool Tradable(const string s)
  {
   return SymbolSelect(s, true) && SymbolInfoInteger(s, SYMBOL_TRADE_MODE) != SYMBOL_TRADE_MODE_DISABLED;
  }

// nom reel d'un marche chez le courtier : nom + ".r" (compte Raw), nom exact, autres noms connus, sinon premier
// symbole qui commence pareil
string Resolve(const string base)
  {
   if(Tradable(base + ".r")) return base + ".r";
   if(Tradable(base)) return base;
   string alt[];
   int na = 0;
   if(base == "US100") na = StringSplit("NAS100,USTEC,US100.cash,NDX100", ',', alt);
   if(base == "US500") na = StringSplit("SPX500,SP500,US500.cash", ',', alt);
   if(base == "GER40") na = StringSplit("DE40,DAX40,GER30,DE30", ',', alt);
   if(base == "JP225") na = StringSplit("JPN225,JP225.cash,NIKKEI225,NI225,JAP225", ',', alt);
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

string Clean(string s)
  {
   StringReplace(s, ",", " ");
   StringReplace(s, "\r", " ");
   StringReplace(s, "\n", " ");
   return s;
  }

// horaires de trading : "jour:debut-fin|" en minutes depuis minuit, heure du serveur (jour 0 = dimanche)
string Sessions(const string nm)
  {
   string s = "";
   for(int dw = 0; dw < 7; dw++)
      for(uint si = 0; si < 8; si++)
        {
         datetime f = 0, t = 0;
         if(!SymbolInfoSessionTrade(nm, (ENUM_DAY_OF_WEEK)dw, si, f, t)) break;
         s += IntegerToString(dw) + ":" + IntegerToString((long)f / 60) + "-" + IntegerToString((long)t / 60) + "|";
        }
   return s;
  }

//+------------------------------------------------------------------+
//| 1. Fiches                                                        |
//+------------------------------------------------------------------+
string FicheHeader()
  {
   string s = "base,name,path,description,digits,point,tick_size,tick_value,tick_value_loss,contract_size,";
   s += "vol_min,vol_step,vol_max,calc_mode,exe_mode,spread_float,spread_points,stops_level,swap_mode,swap_long,";
   s += "swap_short,swap_3days,margin_initial,margin_1lot,ccy_base,ccy_profit,ccy_margin,bid,ask,tick_time,sessions\n";
   return s;
  }

string Fiche(const string base, const string nm)
  {
   if(nm == "") return base + ",INTROUVABLE,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n";
   MqlTick k;
   ZeroMemory(k);
   SymbolInfoTick(nm, k);
   int dg = (int)SymbolInfoInteger(nm, SYMBOL_DIGITS);
   double margin = 0.0;
   if(k.ask <= 0 || !OrderCalcMargin(ORDER_TYPE_BUY, nm, 1.0, k.ask, margin)) margin = 0.0;
   string s = base + "," + nm + "," + Clean(SymbolInfoString(nm, SYMBOL_PATH)) + "," + Clean(SymbolInfoString(nm, SYMBOL_DESCRIPTION)) + ",";
   s += IntegerToString(dg) + "," + DoubleToString(SymbolInfoDouble(nm, SYMBOL_POINT), 8) + ",";
   s += DoubleToString(SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_SIZE), 8) + ",";
   s += DoubleToString(SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_VALUE), 8) + ",";
   s += DoubleToString(SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_VALUE_LOSS), 8) + ",";
   s += DoubleToString(SymbolInfoDouble(nm, SYMBOL_TRADE_CONTRACT_SIZE), 4) + ",";
   s += DoubleToString(SymbolInfoDouble(nm, SYMBOL_VOLUME_MIN), 4) + ",";
   s += DoubleToString(SymbolInfoDouble(nm, SYMBOL_VOLUME_STEP), 4) + ",";
   s += DoubleToString(SymbolInfoDouble(nm, SYMBOL_VOLUME_MAX), 2) + ",";
   s += IntegerToString(SymbolInfoInteger(nm, SYMBOL_TRADE_CALC_MODE)) + ",";
   s += IntegerToString(SymbolInfoInteger(nm, SYMBOL_TRADE_EXEMODE)) + ",";
   s += IntegerToString(SymbolInfoInteger(nm, SYMBOL_SPREAD_FLOAT)) + ",";
   s += IntegerToString(SymbolInfoInteger(nm, SYMBOL_SPREAD)) + ",";
   s += IntegerToString(SymbolInfoInteger(nm, SYMBOL_TRADE_STOPS_LEVEL)) + ",";
   s += IntegerToString(SymbolInfoInteger(nm, SYMBOL_SWAP_MODE)) + ",";
   s += DoubleToString(SymbolInfoDouble(nm, SYMBOL_SWAP_LONG), 4) + ",";
   s += DoubleToString(SymbolInfoDouble(nm, SYMBOL_SWAP_SHORT), 4) + ",";
   s += IntegerToString(SymbolInfoInteger(nm, SYMBOL_SWAP_ROLLOVER3DAYS)) + ",";
   s += DoubleToString(SymbolInfoDouble(nm, SYMBOL_MARGIN_INITIAL), 4) + ",";
   s += DoubleToString(margin, 2) + ",";
   s += SymbolInfoString(nm, SYMBOL_CURRENCY_BASE) + "," + SymbolInfoString(nm, SYMBOL_CURRENCY_PROFIT) + ",";
   s += SymbolInfoString(nm, SYMBOL_CURRENCY_MARGIN) + ",";
   s += DoubleToString(k.bid, dg) + "," + DoubleToString(k.ask, dg) + "," + IntegerToString((long)k.time) + ",";
   s += Sessions(nm) + "\n";
   return s;
  }

//+------------------------------------------------------------------+
//| 3. Tous les marches du courtier                                  |
//+------------------------------------------------------------------+
int AllSymbols()
  {
   int h = FileOpen(DIR + "tous.csv", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE) return -1;
   FileWriteString(h, "name,path,description,digits,contract_size,vol_min,vol_step,calc_mode,swap_long,swap_short,ccy_profit,trade_mode\n");
   int total = SymbolsTotal(false);
   for(int i = 0; i < total && !IsStopped(); i++)
     {
      string nm = SymbolName(i, false);
      string s = nm + "," + Clean(SymbolInfoString(nm, SYMBOL_PATH)) + "," + Clean(SymbolInfoString(nm, SYMBOL_DESCRIPTION)) + ",";
      s += IntegerToString(SymbolInfoInteger(nm, SYMBOL_DIGITS)) + ",";
      s += DoubleToString(SymbolInfoDouble(nm, SYMBOL_TRADE_CONTRACT_SIZE), 4) + ",";
      s += DoubleToString(SymbolInfoDouble(nm, SYMBOL_VOLUME_MIN), 4) + ",";
      s += DoubleToString(SymbolInfoDouble(nm, SYMBOL_VOLUME_STEP), 4) + ",";
      s += IntegerToString(SymbolInfoInteger(nm, SYMBOL_TRADE_CALC_MODE)) + ",";
      s += DoubleToString(SymbolInfoDouble(nm, SYMBOL_SWAP_LONG), 4) + ",";
      s += DoubleToString(SymbolInfoDouble(nm, SYMBOL_SWAP_SHORT), 4) + ",";
      s += SymbolInfoString(nm, SYMBOL_CURRENCY_PROFIT) + ",";
      s += IntegerToString(SymbolInfoInteger(nm, SYMBOL_TRADE_MODE)) + "\n";
      FileWriteString(h, s);
     }
   FileClose(h);
   return total;
  }

//+------------------------------------------------------------------+
//| 2. Prix vendeur / acheteur minute par minute                     |
//+------------------------------------------------------------------+
string Row(const long minute, const int dg, const double bo, const double bh, const double bl, const double bc,
           const double ao, const double ah, const double al, const double ac, const int n, const double sps,
           const double spx, const double spn)
  {
   string s = IntegerToString(minute * 60) + ",";
   s += DoubleToString(bo, dg) + "," + DoubleToString(bh, dg) + "," + DoubleToString(bl, dg) + "," + DoubleToString(bc, dg) + ",";
   s += DoubleToString(ao, dg) + "," + DoubleToString(ah, dg) + "," + DoubleToString(al, dg) + "," + DoubleToString(ac, dg) + ",";
   s += IntegerToString(n) + "," + DoubleToString(sps / n, dg + 2) + "," + DoubleToString(spx, dg) + ",";
   s += DoubleToString(spn, dg) + "\n";
   return s;
  }

// du jour le plus recent au plus ancien ; renvoie le nombre de minutes ecrites (-1 = fichier impossible a ouvrir)
long Minutes(const string base, const string nm, const int pos, const int count, string &info)
  {
   int h = FileOpen(DIR + "m1_" + base + ".csv", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      info = "fichier impossible a ouvrir";
      return -1;
     }
   FileWriteString(h, "time,bo,bh,bl,bc,ao,ah,al,ac,n,sp_mean,sp_max,sp_min\n");
   int dg = (int)SymbolInfoInteger(nm, SYMBOL_DIGITS);
   long now = (long)TimeTradeServer();
   long day0 = now - now % 86400;
   long rows = 0, ticks = 0, oldest = 0, newest = 0;
   int empty = 0, days = 0, lasterr = 0, partial = 0;
   for(int d = 0; d < InpDays && !IsStopped(); d++)
     {
      long from = day0 - (long)d * 86400;
      ulong f_msc = (ulong)from * 1000;
      ulong t_msc = f_msc + 86399999;
      MqlTick t[];
      ResetLastError();
      int got = CopyTicksRange(nm, t, COPY_TICKS_INFO, f_msc, t_msc);
      int err = GetLastError();
      if(got < 0 || err == 4403)                    // 4403 = ERR_HISTORY_TIMEOUT : erreur, ou jour rendu incomplet
        {
         lasterr = err;
         Sleep(1000);
         ResetLastError();
         got = CopyTicksRange(nm, t, COPY_TICKS_INFO, f_msc, t_msc);
         err = GetLastError();
         if(got > 0 && err == 4403) partial++;      // toujours incomplet : le jour est ecrit, mais compte a part
        }
      if(got <= 0)
        {
         if(got < 0) lasterr = err;
         empty++;
         if(empty >= InpMaxEmpty) break;
         continue;
        }
      empty = 0;
      days++;
      ticks += got;
      long first = t[0].time_msc / 1000, last = t[got - 1].time_msc / 1000;
      if(oldest == 0 || first < oldest) oldest = first;
      if(last > newest) newest = last;
      long cur = -1;
      double bo = 0, bh = 0, bl = 0, bc = 0, ao = 0, ah = 0, al = 0, ac = 0, sps = 0, spx = 0, spn = 0;
      int n = 0;
      for(int i = 0; i < got; i++)
        {
         double b = t[i].bid, a = t[i].ask;
         if(b <= 0 || a <= 0) continue;
         long m = t[i].time_msc / 60000;
         if(m != cur)
           {
            if(n > 0)
              {
               FileWriteString(h, Row(cur, dg, bo, bh, bl, bc, ao, ah, al, ac, n, sps, spx, spn));
               rows++;
              }
            cur = m;
            bo = b; bh = b; bl = b;
            ao = a; ah = a; al = a;
            sps = 0; spx = 0; spn = 0; n = 0;
           }
         if(b > bh) bh = b;
         if(b < bl) bl = b;
         if(a > ah) ah = a;
         if(a < al) al = a;
         bc = b;
         ac = a;
         double sp = a - b;
         sps += sp;
         if(sp > spx) spx = sp;
         if(n == 0 || sp < spn) spn = sp;     // the smallest spread of the minute (the first tick sets it)
         n++;
        }
      if(n > 0)
        {
         FileWriteString(h, Row(cur, dg, bo, bh, bl, bc, ao, ah, al, ac, n, sps, spx, spn));
         rows++;
        }
      FileFlush(h);
      ArrayFree(t);
      Comment("Releve FP Markets en cours (aucun ordre n'est passe)\n",
              "marche ", IntegerToString(pos + 1), "/", IntegerToString(count), " : ", nm, "\n",
              "jour ", IntegerToString(d + 1), "/", IntegerToString(InpDays), " - ", IntegerToString(ticks), " ticks lus");
     }
   FileClose(h);
   info = "jours=" + IntegerToString(days) + " minutes=" + IntegerToString(rows) + " ticks=" + IntegerToString(ticks)
          + " du=" + TimeToString((datetime)oldest, TIME_DATE | TIME_MINUTES) + " au=" + TimeToString((datetime)newest, TIME_DATE | TIME_MINUTES)
          + " derniere_erreur=" + IntegerToString(lasterr) + " jours_incomplets=" + IntegerToString(partial);
   return rows;
  }

//+------------------------------------------------------------------+
//| 4. Barres M1 du terminal (celles que le robot lit)               |
//+------------------------------------------------------------------+
// one line of r1_<BASE>.csv: the bar as the terminal gives it (MqlRates: bid prices, spread in points)
string RateRow(const MqlRates &r, const int dg)
  {
   string s = IntegerToString((long)r.time) + ",";
   s += DoubleToString(r.open, dg) + "," + DoubleToString(r.high, dg) + "," + DoubleToString(r.low, dg) + "," + DoubleToString(r.close, dg) + ",";
   s += IntegerToString(r.tick_volume) + "," + IntegerToString(r.spread) + "," + IntegerToString(r.real_volume) + "\n";
   return s;
  }

// days of terminal bars asked for a market in InpRateSymbols ("BASE:days,..."); 0 = none (only the robot's markets need
// them: the files stay small enough to send, review R4)
int RateDays(const string base)
  {
   string part[];
   int n = StringSplit(InpRateSymbols, ',', part);
   for(int i = 0; i < n; i++)
     {
      string kv[];
      if(StringSplit(part[i], ':', kv) != 2) continue;
      string k = kv[0];
      StringTrimLeft(k);
      StringTrimRight(k);
      if(k == base) return (int)StringToInteger(kv[1]);
     }
   return 0;
  }

// the terminal's M1 series of a market made ready before it is read: in a script CopyRates returns what is ready at its
// timeout while the download goes on (MQL5 "Organizing Data Access"), so a series still loading would lose its newest days.
// Asks for the oldest day wanted once, then waits, one second at a time and InpRateWait seconds at most, until the series is
// synchronized with the server (SERIES_SYNCHRONIZED) and its bar count since that day (Bars) is the same twice in a row.
// first, last: the series' first and last bar (SERIES_FIRSTDATE, SERIES_LASTBAR_DATE; 0 = unknown). True when ready in time.
bool RatesReady(const string nm, const datetime from, datetime &first, datetime &last)
  {
   MqlRates one[];
   CopyRates(nm, PERIOD_M1, from, from + 3600, one);   // starts the download of the oldest day wanted
   ArrayFree(one);
   int prev = -1;
   bool ready = false;
   for(int w = 0; w <= InpRateWait && !IsStopped(); w++)
     {
      bool sync = (SeriesInfoInteger(nm, PERIOD_M1, SERIES_SYNCHRONIZED) != 0);
      int n = Bars(nm, PERIOD_M1, from, TimeTradeServer());
      if(sync && n > 0 && n == prev)
        {
         ready = true;
         break;
        }
      prev = n;
      Sleep(1000);
     }
   first = (datetime)SeriesInfoInteger(nm, PERIOD_M1, SERIES_FIRSTDATE);
   last = (datetime)SeriesInfoInteger(nm, PERIOD_M1, SERIES_LASTBAR_DATE);
   return ready;
  }

// the newest day first, no tick read (cheap); returns the bars written (-1 = the file could not be opened). The days after
// the series' last bar (a weekend run) and before its first bar (the start of the history, or the "Max bars in chart" limit)
// are no error. A day is asked again (one second apart, 5 times at most) while CopyRates fails or gives fewer bars than the
// terminal lists for it (Bars); the best answer is written, never a last call that could fail (review R7).
// info = "barres=.. jours_barres=.. erreur_barres=.. jours_courts=.. erreur_r1=.. jours_r1=.. debut_r1=.. fin_r1=..
// synchro_r1=.. attente_r1=.." (erreur_barres: days that could not be read at all; jours_courts: days with fewer bars than
// the terminal lists)
long Rates(const string base, const string nm, const int days_asked, const int pos, const int count, string &info)
  {
   int h = FileOpen(DIR + "r1_" + base + ".csv", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      info = "barres=-1 jours_barres=0 erreur_barres=-1 jours_courts=0 erreur_r1=" + IntegerToString(GetLastError())
             + " jours_r1=" + IntegerToString(days_asked);
      return -1;
     }
   FileWriteString(h, "time,open,high,low,close,tick_volume,spread,real_volume\n");
   int dg = (int)SymbolInfoInteger(nm, SYMBOL_DIGITS);
   long now = (long)TimeTradeServer();
   long day0 = now - now % 86400;
   datetime first = 0, last = 0;
   uint w0 = GetTickCount();
   bool ready = RatesReady(nm, (datetime)(day0 - (long)(days_asked - 1) * 86400), first, last);
   int waited = (int)((GetTickCount() - w0) / 1000);
   long bars = 0;
   int days = 0, empty = 0, errors = 0, short_days = 0, lasterr = 0;
   for(int d = 0; d < days_asked && !IsStopped(); d++)
     {
      datetime from = (datetime)(day0 - (long)d * 86400);
      datetime to = (datetime)(day0 - (long)d * 86400 + 86399);
      if(last > 0 && from > last) continue;            // after the newest bar (a weekend run): no bar, no error
      if(first > 0 && to < first) break;               // before the oldest bar of the series: the end of what can be read
      int want = Bars(nm, PERIOD_M1, from, to);        // the bars the terminal lists for that day
      MqlRates r[];
      string keep = "";
      int got = -1;
      bool in_r = false;                               // r holds the best answer (else keep has it, as text)
      for(int k = 0; k < 5 && !IsStopped(); k++)
        {
         if(k > 0) Sleep(1000);                        // never two calls at once: a day still loading gets a second
         ResetLastError();
         int n = CopyRates(nm, PERIOD_M1, from, to, r);
         int err = GetLastError();
         in_r = false;
         if(n < 0)
           {
            lasterr = err;
            continue;
           }
         if(n > got)
           {
            got = n;
            in_r = true;
            if(got >= want) break;
            keep = "";                                 // fewer bars than listed: kept in case the next call fails
            for(int i = 0; i < n; i++) keep += RateRow(r[i], dg);
           }
         want = Bars(nm, PERIOD_M1, from, to);
         if(got >= want) break;
        }
      if(got < 0)
        {
         errors++;                                     // no answer at all for that day
         ArrayFree(r);
         continue;
        }
      if(got < want) short_days++;
      if(got > 0)
        {
         if(in_r)
           {
            for(int i = 0; i < got; i++) FileWriteString(h, RateRow(r[i], dg));
           }
         else FileWriteString(h, keep);
         bars += got;
         days++;
         empty = 0;
        }
      else if(first == 0)
        {
         empty++;                                      // no first date known: six empty days in a row end the history
         if(empty >= InpMaxEmpty) break;
        }
      ArrayFree(r);                                    // ArrayFree: frees the dynamic array
      FileFlush(h);
      Comment("Releve FP Markets en cours (aucun ordre n'est passe)\n",
              "marche ", IntegerToString(pos + 1), "/", IntegerToString(count), " : ", nm, "\n",
              "barres M1 du terminal, jour ", IntegerToString(d + 1), "/", IntegerToString(days_asked));
     }
   FileClose(h);
   info = "barres=" + IntegerToString(bars) + " jours_barres=" + IntegerToString(days) + " erreur_barres=" + IntegerToString(errors)
          + " jours_courts=" + IntegerToString(short_days) + " erreur_r1=" + IntegerToString(lasterr) + " jours_r1=" + IntegerToString(days_asked)
          + " debut_r1=" + IntegerToString((long)first) + " fin_r1=" + IntegerToString((long)last) + " synchro_r1=" + (ready ? "1" : "0")
          + " attente_r1=" + IntegerToString(waited);
   return bars;
  }

//+------------------------------------------------------------------+
//| 5 et 6. Positions ouvertes et historique des transactions (1.11)  |
//+------------------------------------------------------------------+
// the error code of a call that failed (GetLastError), -1 when MetaTrader gave none (a failure is never written as 0)
int FailCode()
  {
   int e = GetLastError();
   if(e == 0) return -1;
   return e;
  }

// one line written whole (review8 RELEVE111-CRLF). FileWriteString (docs): "When writing to a CSV or TXT file: if there is a symbol in the
// string '\n' (LF) without previous character '\r' (CR), then before '\n' the missing '\r' is added"; "If successful the function returns
// the number of bytes written" (FILE_ANSI: one per character). Every row of deals.csv and positions.csv ends in "\r\n" itself, so nothing
// is added and the count equals StringLen; a count at least StringLen is a whole write (whatever the terminal adds), a short or zero one a
// failure. The error is reset just before the write, so a failure reports its own code (or -1 without one), never one an earlier call left
// (SymbolInfoInteger 4301/4302, EnumToString 4003, PositionSelectByTicket 4753: review8 LASTERR-STALE)
bool WriteRow(const int h, const string s)
  {
   ResetLastError();
   uint n = FileWriteString(h, s);
   return n >= (uint)StringLen(s);
  }

// decimals of a symbol's prices (SYMBOL_DIGITS); 8 when the symbol is empty (a balance deal) or unknown to the terminal, so that
// nothing is rounded away
int PriceDigits(const string sym)
  {
   long dg = 0;
   if(sym == "") return 8;
   if(!SymbolInfoInteger(sym, SYMBOL_DIGITS, dg)) return 8;
   if(dg < 0 || dg > 8) return 8;
   return (int)dg;
  }

// decimals of a symbol's volume step (SYMBOL_VOLUME_STEP 0.01 -> 2, 0.1 -> 1, 1 -> 0); 8 when the symbol is empty or unknown
int VolumeDigits(const string sym)
  {
   double st = 0.0;
   if(sym == "") return 8;
   if(!SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP, st)) return 8;
   if(!(st > 0.0)) return 8;
   int d = 0;
   while(d < 8 && MathAbs(st - MathRound(st)) > 0.0000001)
     {
      st = st * 10.0;
      d++;
     }
   return d;
  }

// decimals of money: the account currency's (ACCOUNT_CURRENCY_DIGITS, "required for an accurate display of trading results"),
// 2 at least
int MoneyDigits()
  {
   long cd = AccountInfoInteger(ACCOUNT_CURRENCY_DIGITS);
   if(cd < 2) return 2;
   if(cd > 8) return 8;
   return (int)cd;
  }

// tickets in the order of their keys (time in milliseconds, then ticket): an insertion sort (the terminal's lists promise no order;
// when a list is already in time order, one pass)
void SortByKey(ulong &tk[], long &key[], const int n)
  {
   for(int i = 1; i < n; i++)
     {
      ulong t = tk[i];
      long k = key[i];
      int j = i - 1;
      while(j >= 0)
        {
         if(key[j] < k) break;
         if(key[j] == k && tk[j] <= t) break;
         tk[j + 1] = tk[j];
         key[j + 1] = key[j];
         j--;
        }
      tk[j + 1] = t;
      key[j + 1] = k;
     }
  }

// 5. every position open at the run, oldest first (positions.csv); returns the rows written, -1 when the file could not be opened
// (err = its error). Every line ends in "\r\n" (WriteRow). A position closed between the list and its line (the robot runs) is left
// out. Never POSITION_COMMENT nor POSITION_EXTERNAL_ID: no text but the symbol
int Positions(int &err)
  {
   ResetLastError();
   int h = FileOpen(DIR + "positions.csv", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      err = FailCode();
      return -1;
     }
   if(!WriteRow(h, "ticket,identifier,time,time_msc,symbol,type,magic,volume,price_open,sl,tp,price_current,swap,profit\r\n"))
     {
      err = FailCode();
      FileClose(h);
      return -1;
     }
   int n = PositionsTotal();
   if(n < 0) n = 0;
   ulong tk[];
   long key[];
   ArrayResize(tk, n);
   ArrayResize(key, n);
   int m = 0;
   for(int i = 0; i < n; i++)
     {
      ulong t = PositionGetTicket(i);                  // selects the position
      if(t == 0) continue;
      long ms = PositionGetInteger(POSITION_TIME_MSC);
      if(ms <= 0) ms = PositionGetInteger(POSITION_TIME) * 1000;
      tk[m] = t;
      key[m] = ms;
      m++;
     }
   SortByKey(tk, key, m);
   int md = MoneyDigits();
   int rows = 0;
   for(int k = 0; k < m && !IsStopped(); k++)
     {
      if(!PositionSelectByTicket(tk[k])) continue;     // closed meanwhile
      string sym = Clean(PositionGetString(POSITION_SYMBOL));
      int pd = PriceDigits(sym);
      int vd = VolumeDigits(sym);
      ENUM_POSITION_TYPE ptype = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      string s = IntegerToString((long)tk[k]) + "," + IntegerToString(PositionGetInteger(POSITION_IDENTIFIER)) + ",";
      s += IntegerToString(PositionGetInteger(POSITION_TIME)) + "," + IntegerToString(PositionGetInteger(POSITION_TIME_MSC)) + ",";
      s += sym + "," + EnumToString(ptype) + "," + IntegerToString(PositionGetInteger(POSITION_MAGIC)) + ",";
      s += DoubleToString(PositionGetDouble(POSITION_VOLUME), vd) + "," + DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN), pd) + ",";
      s += DoubleToString(PositionGetDouble(POSITION_SL), pd) + "," + DoubleToString(PositionGetDouble(POSITION_TP), pd) + ",";
      s += DoubleToString(PositionGetDouble(POSITION_PRICE_CURRENT), pd) + "," + DoubleToString(PositionGetDouble(POSITION_SWAP), md) + ",";
      s += DoubleToString(PositionGetDouble(POSITION_PROFIT), md) + "\r\n";
      if(!WriteRow(h, s))
        {
         err = FailCode();
         break;
        }
      rows++;
     }
   FileClose(h);
   ArrayFree(tk);
   ArrayFree(key);
   return rows;
  }

// 6. every deal of the account's whole history (HistorySelect from 0 to the server time + a day), oldest first (deals.csv); returns
// the rows written, -1 when the file could not be opened or the history not read (err = its error). first, last: the earliest and the
// latest DEAL_TIME written (server seconds; 0 without any). Every line ends in "\r\n" (WriteRow). Types, entries and reasons by name
// (EnumToString), prices with the symbol's digits, volumes with its volume step's, money with the account currency's (2 at least).
// Never DEAL_COMMENT nor DEAL_EXTERNAL_ID: no text but the symbol (empty for a balance deal)
int Deals(int &err, long &first, long &last)
  {
   first = 0;
   last = 0;
   ResetLastError();
   int h = FileOpen(DIR + "deals.csv", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      err = FailCode();
      return -1;
     }
   if(!WriteRow(h, "time,time_msc,ticket,order,position,symbol,type,entry,reason,magic,volume,price,sl,tp,commission,swap,fee,profit\r\n"))
     {
      err = FailCode();
      FileClose(h);
      return -1;
     }
   ResetLastError();
   if(!HistorySelect(0, TimeTradeServer() + 86400))
     {
      err = FailCode();
      FileClose(h);
      return -1;
     }
   int n = HistoryDealsTotal();
   if(n < 0) n = 0;
   ulong tk[];
   long key[];
   ArrayResize(tk, n);
   ArrayResize(key, n);
   int m = 0;
   for(int i = 0; i < n; i++)
     {
      ulong t = HistoryDealGetTicket(i);
      if(t == 0) continue;
      long ms = HistoryDealGetInteger(t, DEAL_TIME_MSC);
      if(ms <= 0) ms = HistoryDealGetInteger(t, DEAL_TIME) * 1000;
      tk[m] = t;
      key[m] = ms;
      m++;
     }
   SortByKey(tk, key, m);
   int md = MoneyDigits();
   int rows = 0;
   for(int k = 0; k < m && !IsStopped(); k++)
     {
      ulong t = tk[k];
      string sym = Clean(HistoryDealGetString(t, DEAL_SYMBOL));
      int pd = PriceDigits(sym);
      int vd = VolumeDigits(sym);
      long tm = HistoryDealGetInteger(t, DEAL_TIME);
      ENUM_DEAL_TYPE dtype = (ENUM_DEAL_TYPE)HistoryDealGetInteger(t, DEAL_TYPE);
      ENUM_DEAL_ENTRY dentry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(t, DEAL_ENTRY);
      ENUM_DEAL_REASON dreason = (ENUM_DEAL_REASON)HistoryDealGetInteger(t, DEAL_REASON);
      string s = IntegerToString(tm) + "," + IntegerToString(HistoryDealGetInteger(t, DEAL_TIME_MSC)) + "," + IntegerToString((long)t) + ",";
      s += IntegerToString(HistoryDealGetInteger(t, DEAL_ORDER)) + "," + IntegerToString(HistoryDealGetInteger(t, DEAL_POSITION_ID)) + ",";
      s += sym + "," + EnumToString(dtype) + "," + EnumToString(dentry) + "," + EnumToString(dreason) + ",";
      s += IntegerToString(HistoryDealGetInteger(t, DEAL_MAGIC)) + ",";
      s += DoubleToString(HistoryDealGetDouble(t, DEAL_VOLUME), vd) + "," + DoubleToString(HistoryDealGetDouble(t, DEAL_PRICE), pd) + ",";
      s += DoubleToString(HistoryDealGetDouble(t, DEAL_SL), pd) + "," + DoubleToString(HistoryDealGetDouble(t, DEAL_TP), pd) + ",";
      s += DoubleToString(HistoryDealGetDouble(t, DEAL_COMMISSION), md) + "," + DoubleToString(HistoryDealGetDouble(t, DEAL_SWAP), md) + ",";
      s += DoubleToString(HistoryDealGetDouble(t, DEAL_FEE), md) + "," + DoubleToString(HistoryDealGetDouble(t, DEAL_PROFIT), md) + "\r\n";
      if(!WriteRow(h, s))
        {
         err = FailCode();
         break;
        }
      if(rows == 0 || tm < first) first = tm;          // the earliest and the latest DEAL_TIME written (review8: never the file's order)
      if(rows == 0 || tm > last) last = tm;
      rows++;
     }
   FileClose(h);
   ArrayFree(tk);
   ArrayFree(key);
   return rows;
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   FolderCreate("claude");
   FolderCreate("claude\\releve");
   FileDelete(DIR + "fini.txt");
   string base[];
   int nb = StringSplit(InpSymbols, ',', base);
   string name[];
   ArrayResize(name, nb);
   uint t0 = GetTickCount();

   // 1. fiches
   string fiches = FicheHeader();
   for(int i = 0; i < nb; i++)
     {
      StringTrimLeft(base[i]);
      StringTrimRight(base[i]);
      name[i] = Resolve(base[i]);
      fiches += Fiche(base[i], name[i]);
     }
   int h = FileOpen(DIR + "fiches.csv", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      Alert("ReleveFP : impossible d'ecrire dans MQL5\\Files\\claude\\releve (erreur ", IntegerToString(GetLastError()), ")");
      return;
     }
   FileWriteString(h, fiches);
   FileClose(h);

   // 3. tous les marches
   int all = -1;
   if(InpAllList) all = AllSymbols();

   // 2. minutes
   datetime srv = TimeTradeServer(), gmt = TimeGMT();
   string res = "version=1.11\n";                     // 1.11: the server's name is no longer written (it names the account)
   res += "currency=" + AccountInfoString(ACCOUNT_CURRENCY) + "\n";
   res += "leverage=" + IntegerToString(AccountInfoInteger(ACCOUNT_LEVERAGE)) + "\n";
   res += "demo=" + IntegerToString(AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO ? 1 : 0) + "\n";
   res += "server_time=" + IntegerToString((long)srv) + "\n";
   res += "server_minus_gmt_sec=" + IntegerToString((long)(srv - gmt)) + "\n";
   res += "all_symbols=" + IntegerToString(all) + "\n";
   res += "max_barres=" + IntegerToString(TerminalInfoInteger(TERMINAL_MAXBARS)) + "\n";
   // the minutes of every market first: a slow history of the terminal's bars below never delays them (review R14)
   string info_m[], info_r[];
   ArrayResize(info_m, nb);
   ArrayResize(info_r, nb);
   for(int i = 0; i < nb; i++)
     {
      info_m[i] = "";
      info_r[i] = "";
     }
   int done = 0;
   for(int i = 0; i < nb && !IsStopped(); i++)
     {
      if(name[i] == "") continue;
      string info = "";
      long rows = Minutes(base[i], name[i], i, nb, info);
      info_m[i] = info;
      if(rows > 0) done++;
     }
   // 4. then the terminal's M1 bars of the robot's markets (InpRateSymbols)
   for(int i = 0; i < nb && !IsStopped(); i++)
     {
      int rd = RateDays(base[i]);
      if(name[i] == "" || rd <= 0) continue;
      string rinfo = "";
      Rates(base[i], name[i], rd, i, nb, rinfo);
      info_r[i] = rinfo;
     }
   for(int i = 0; i < nb; i++)
     {
      if(name[i] == "")
        {
         res += base[i] + "=INTROUVABLE\n";
         continue;
        }
      res += base[i] + "=" + name[i] + " " + info_m[i] + (info_r[i] != "" ? " " + info_r[i] : "") + "\n";
     }
   // 5 and 6 (1.11): at the end of the run, the positions open now, then the whole history of the account's deals
   Comment("Releve FP Markets en cours (aucun ordre n'est passe)\n", "positions ouvertes et historique des transactions du compte");
   int err_p = 0, err_d = 0;
   long d_first = 0, d_last = 0;
   long t_pos = (long)TimeTradeServer();
   int n_pos = Positions(err_p);
   int n_deals = Deals(err_d, d_first, d_last);
   res += "positions=" + IntegerToString(n_pos) + "\n";
   res += "positions_heure=" + IntegerToString(t_pos) + "\n";
   res += "deals=" + IntegerToString(n_deals) + "\n";
   res += "deals_du=" + IntegerToString(d_first) + "\n";
   res += "deals_au=" + IntegerToString(d_last) + "\n";
   res += "erreur_deals=" + IntegerToString(err_d != 0 ? err_d : err_p) + "\n";
   res += "stopped=" + IntegerToString(IsStopped() ? 1 : 0) + "\n";
   res += "seconds=" + IntegerToString((long)((GetTickCount() - t0) / 1000)) + "\n";
   h = FileOpen(DIR + "fini.txt", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h != INVALID_HANDLE)
     {
      FileWriteString(h, res);
      FileClose(h);
     }
   Comment("Releve FP Markets termine : ", IntegerToString(done), " marches sur ", IntegerToString(nb),
           ".\nFichiers dans MQL5\\Files\\claude\\releve");
   Print("ReleveFP termine\n", res);
   Alert("Releve termine : ", IntegerToString(done), " marches sur ", IntegerToString(nb), ". Vous pouvez le dire a Claude.");
  }
//+------------------------------------------------------------------+
