//+------------------------------------------------------------------+
//|                                                    ReleveFP.mq5  |
//|  SCRIPT a lancer une fois (le glisser sur n'importe quel          |
//|  graphique). Il ne passe AUCUN ordre et ne modifie rien.          |
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
//|   4. pour chaque marche, les barres M1 du terminal, celles que le |
//|      robot lit (prix vendeur, ecart en points), sur InpRateDays   |
//|      jours                       -> claude\releve\r1_<marche>.csv |
//|  A la fin : claude\releve\fini.txt (resume) et une alerte. Pour   |
//|  chaque marche : jours, minutes, ticks, du, au, derniere_erreur,  |
//|  jours_incomplets (les minutes), puis barres, jours_barres et     |
//|  erreur_barres (jours de barres impossibles a lire).              |
//|  Il peut rester plusieurs minutes sur un marche pendant que le    |
//|  terminal telecharge l'historique : c'est normal.                 |
//|  Les heures ecrites sont celles du serveur (secondes).            |
//|  La commission n'est pas dans les fiches : elle se lit sur un     |
//|  aller-retour en demo (voir releve.py).                           |
//+------------------------------------------------------------------+
#property copyright "gold-orb lab"
#property version   "1.10"
#property description "Releve des vrais frais du courtier : fiches des marches et prix acheteur / vendeur minute par minute. Ne passe aucun ordre."
#property script_show_inputs

input string InpSymbols  = "BTCUSD,ETHUSD,US100,XAUUSD,USDJPY,JP225,EURUSD,US500,GER40"; // Marches (noms de base, du plus important au moins important)
input int    InpDays     = 30;     // Jours d'historique de ticks a relever
input int    InpRateDays = 200;    // Jours de barres M1 du terminal a relever (r1_<marche>.csv)
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

// the newest day first, no tick read (cheap); returns the bars written (-1 = the file could not be opened);
// info = "barres=.. jours_barres=.. erreur_barres=.." (erreur_barres: days whose bars could not be read)
long Rates(const string base, const string nm, const int pos, const int count, string &info)
  {
   int h = FileOpen(DIR + "r1_" + base + ".csv", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      info = "barres=-1 jours_barres=0 erreur_barres=-1";
      return -1;
     }
   FileWriteString(h, "time,open,high,low,close,tick_volume,spread,real_volume\n");
   int dg = (int)SymbolInfoInteger(nm, SYMBOL_DIGITS);
   long now = (long)TimeTradeServer();
   long day0 = now - now % 86400;
   long bars = 0;
   int days = 0, empty = 0, errors = 0;
   for(int d = 0; d < InpRateDays && !IsStopped(); d++)
     {
      datetime from = (datetime)(day0 - (long)d * 86400);
      datetime to = (datetime)(day0 - (long)d * 86400 + 86399);
      MqlRates r[];
      int got = -1;
      // CopyRates(name, PERIOD_M1, start, stop, array) copies the M1 bars whose open time lies between start and stop,
      // oldest first, and returns how many (-1 on error). In a script it waits for missing history only up to a timeout
      // and returns what is ready: ask again (at once, then once a second) while the count grows or the call fails,
      // 6 times at most
      for(int k = 0; k < 6 && !IsStopped(); k++)
        {
         if(k >= 2) Sleep(1000);                // Sleep(ms): the script waits (allowed in a script)
         int n = CopyRates(nm, PERIOD_M1, from, to, r);
         if(n < 0) continue;                    // not ready yet, or an error: ask again
         if(n <= got) break;                    // the count no longer grows: the day is complete
         got = n;
        }
      int n_ok = 0;
      if(got > 0) n_ok = CopyRates(nm, PERIOD_M1, from, to, r);   // one last call gives the bars to write
      if(got < 0) errors++;
      if(n_ok > 0)
        {
         for(int i = 0; i < n_ok; i++) FileWriteString(h, RateRow(r[i], dg));
         bars += n_ok;
         days++;
         empty = 0;
        }
      else
        {
         empty++;
         if(empty >= InpMaxEmpty) break;        // the start of the broker's history
        }
      ArrayFree(r);                             // ArrayFree: frees the dynamic array
      FileFlush(h);
      Comment("Releve FP Markets en cours (aucun ordre n'est passe)\n",
              "marche ", IntegerToString(pos + 1), "/", IntegerToString(count), " : ", nm, "\n",
              "barres M1 du terminal, jour ", IntegerToString(d + 1), "/", IntegerToString(InpRateDays));
     }
   FileClose(h);
   info = "barres=" + IntegerToString(bars) + " jours_barres=" + IntegerToString(days) + " erreur_barres=" + IntegerToString(errors);
   return bars;
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
   string res = "version=1.10\n";
   res += "server=" + AccountInfoString(ACCOUNT_SERVER) + "\n";
   res += "company=" + AccountInfoString(ACCOUNT_COMPANY) + "\n";
   res += "currency=" + AccountInfoString(ACCOUNT_CURRENCY) + "\n";
   res += "leverage=" + IntegerToString(AccountInfoInteger(ACCOUNT_LEVERAGE)) + "\n";
   res += "demo=" + IntegerToString(AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO ? 1 : 0) + "\n";
   res += "server_time=" + IntegerToString((long)srv) + "\n";
   res += "server_minus_gmt_sec=" + IntegerToString((long)(srv - gmt)) + "\n";
   res += "all_symbols=" + IntegerToString(all) + "\n";
   int done = 0;
   for(int i = 0; i < nb && !IsStopped(); i++)
     {
      if(name[i] == "")
        {
         res += base[i] + "=INTROUVABLE\n";
         continue;
        }
      string info = "";
      long rows = Minutes(base[i], name[i], i, nb, info);
      string rinfo = "";
      Rates(base[i], name[i], i, nb, rinfo);    // after the minutes: a problem here never stops them
      res += base[i] + "=" + name[i] + " " + info + " " + rinfo + "\n";
      if(rows > 0) done++;
     }
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
