//+------------------------------------------------------------------+
//|                                                     SondeFP.mq5  |
//|  SCRIPT a lancer une fois, sur un compte de DEMONSTRATION         |
//|  uniquement (il refuse de tourner sur un compte reel).            |
//|  Pour chaque marche il achete le lot minimum avec un stop,        |
//|  attend une seconde, revend, puis lit dans l'historique ce que    |
//|  le courtier a vraiment preleve : commission, frais, et les prix  |
//|  obtenus. Les fiches des marches ne donnent pas la commission :   |
//|  c'est la seule facon de la lire.                                 |
//|  Resultat : MQL5\Files\claude\releve\sonde.csv                    |
//|  Il faut le bouton Algo Trading actif.                            |
//+------------------------------------------------------------------+
#property copyright "gold-orb lab"
#property version   "1.10"
#property description "Compte de demonstration uniquement : un aller-retour au lot minimum par marche, pour lire la commission reelle."
#property script_show_inputs

#include <Trade\Trade.mqh>

input string InpSymbols = "XAUUSD,EURUSD,USDJPY,US100,BTCUSD,ETHUSD,JP225"; // Marches (noms de base)
input double InpRiskPct = 0.4;      // Stop place pour que le lot minimum risque au plus ce % du solde
input long   InpMagic   = 20261112; // Numero magique des ordres de la sonde

const string DIR = "claude\\releve\\";
CTrade g_trade;
bool   g_no_stop = false;   // une position restee ouverte n'a pas de stop chez le courtier

bool Tradable(const string s)
  {
   return SymbolSelect(s, true) && SymbolInfoInteger(s, SYMBOL_TRADE_MODE) != SYMBOL_TRADE_MODE_DISABLED;
  }

// meme recherche que ReleveFP : nom + ".r" (compte Raw), nom exact, autres noms connus, sinon premier symbole qui commence pareil
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

bool Done(const bool ok)
  {
   uint rc = g_trade.ResultRetcode();
   return ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED || rc == TRADE_RETCODE_DONE_PARTIAL);
  }

// ticket de la position que la sonde a sur ce marche (meme numero magique) ; 0 = aucune. La position reste selectionnee.
ulong FindProbe(const string nm)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t != 0 && PositionGetString(POSITION_SYMBOL) == nm && PositionGetInteger(POSITION_MAGIC) == InpMagic) return t;
     }
   return 0;
  }

// un aller-retour sur un marche ; renvoie la ligne du fichier
string Probe(const string base, const string nm, bool &left_open)
  {
   string head = base + "," + nm + ",";
   MqlTick k;
   ZeroMemory(k);
   // un marche que le script vient d'ajouter a l'Observatoire n'a pas tout de suite son premier prix : on attend 5 s au plus
   bool priced = false;
   for(int w = 0; w < 20 && !priced && !IsStopped(); w++)
     {
      priced = SymbolInfoTick(nm, k) && k.bid > 0 && k.ask > 0;
      if(!priced) Sleep(250);
     }
   if(!priced) return head + "pas de prix\n";
   if(SymbolInfoInteger(nm, SYMBOL_TRADE_MODE) != SYMBOL_TRADE_MODE_FULL) return head + "marche ferme ou non negociable\n";
   if((SymbolInfoInteger(nm, SYMBOL_ORDER_MODE) & SYMBOL_ORDER_SL) == 0) return head + "ce marche n'accepte pas de stop chez le courtier\n";   // sinon CTrade enleve le stop sans rien dire
   int dg = (int)SymbolInfoInteger(nm, SYMBOL_DIGITS);
   double pt = SymbolInfoDouble(nm, SYMBOL_POINT);
   double vmin = SymbolInfoDouble(nm, SYMBOL_VOLUME_MIN);
   double ts = SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_SIZE);
   double tv = SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_VALUE);
   double tvl = SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tvl <= 0) tvl = tv;
   if(vmin <= 0 || ts <= 0 || tvl <= 0) return head + "fiche du marche incomplete\n";
   double spread = k.ask - k.bid;
   double per_price = vmin * tvl / ts;                                   // argent perdu par unite de prix, au lot minimum
   double dist = InpRiskPct / 100.0 * AccountInfoDouble(ACCOUNT_BALANCE) / per_price;
   if(dist > 0.015 * k.bid) dist = 0.015 * k.bid;
   double floor_dist = MathMax(8.0 * spread, (double)SymbolInfoInteger(nm, SYMBOL_TRADE_STOPS_LEVEL) * pt + 2.0 * spread);
   if(dist < floor_dist) return head + "lot minimum trop gros pour un stop a " + DoubleToString(InpRiskPct, 2) + " % du solde\n";
   double sl = NormalizeDouble(MathRound((k.bid - dist) / ts) * ts, dg);   // sur un multiple du pas de cotation, sinon le serveur peut refuser le stop
   double need = 0.0;
   if(OrderCalcMargin(ORDER_TYPE_BUY, nm, vmin, k.ask, need) && need > AccountInfoDouble(ACCOUNT_MARGIN_FREE)) return head + "marge insuffisante\n";

   g_trade.SetTypeFillingBySymbol(nm);
   if(!Done(g_trade.Buy(vmin, nm, 0.0, sl, 0.0, "sonde")))
      return head + "achat refuse : " + IntegerToString((long)g_trade.ResultRetcode()) + " " + g_trade.ResultRetcodeDescription() + "\n";
   ulong pos = g_trade.ResultOrder();
   double buy = g_trade.ResultPrice();
   Sleep(1500);

   MqlTick k2;
   ZeroMemory(k2);
   SymbolInfoTick(nm, k2);
   bool closed = false;
   double sell = 0.0;
   bool no_stop = false;
   for(int a = 0; a < 5 && !closed; a++)
     {
      // la position : en principe le ticket de l'ordre d'achat ; sinon celle que la sonde a sur ce marche
      ulong tk = (pos != 0 && PositionSelectByTicket(pos)) ? pos : FindProbe(nm);
      if(tk == 0)
        {
         Sleep(1000);                       // pas encore dans la liste, ou deja fermee par son stop : l'historique le dira
         continue;
        }
      if(tk != pos) pos = (ulong)PositionGetInteger(POSITION_IDENTIFIER);   // l'identifiant sert a relire l'historique
      g_trade.SetTypeFillingBySymbol(nm);
      closed = Done(g_trade.PositionClose(tk));
      if(closed) sell = g_trade.ResultPrice();
      else
        {
         // elle reste ouverte pour l'instant : si le courtier n'a pas garde le stop, on le repose
         if(PositionSelectByTicket(tk) && PositionGetDouble(POSITION_SL) <= 0) no_stop = !Done(g_trade.PositionModify(tk, sl, 0.0));
         Sleep(1000);
        }
     }

   // l'historique met parfois un instant a recevoir les transactions
   double com = 0.0, fee = 0.0, profit = 0.0, swap = 0.0;
   int nd = 0;
   bool in_seen = false, out_seen = false;
   for(int a = 0; a < 10; a++)
     {
      Sleep(700);
      com = 0.0; fee = 0.0; profit = 0.0; swap = 0.0; nd = 0;
      in_seen = false; out_seen = false;
      if(pos != 0 && HistorySelectByPosition((long)pos))
        {
         int total = HistoryDealsTotal();
         for(int i = 0; i < total; i++)
           {
            ulong d = HistoryDealGetTicket(i);
            if(d == 0) continue;
            com += HistoryDealGetDouble(d, DEAL_COMMISSION);
            fee += HistoryDealGetDouble(d, DEAL_FEE);
            profit += HistoryDealGetDouble(d, DEAL_PROFIT);
            swap += HistoryDealGetDouble(d, DEAL_SWAP);
            long entry = HistoryDealGetInteger(d, DEAL_ENTRY);
            if(entry == DEAL_ENTRY_IN)
              {
               in_seen = true;
               if(buy <= 0) buy = HistoryDealGetDouble(d, DEAL_PRICE);
              }
            if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY)
              {
               out_seen = true;
               if(sell <= 0) sell = HistoryDealGetDouble(d, DEAL_PRICE);
              }
            nd++;
           }
        }
      if((in_seen && out_seen) || !closed) break;
     }
   // "ok" seulement si l'achat ET la revente ont ete relus dans l'historique : sinon la commission ecrite serait fausse
   string st = "ok";
   if(closed && !(in_seen && out_seen)) st = "revendu mais transactions non relues dans l'historique (relancez la sonde)";
   if(!closed && out_seen) st = "position fermee par son stop avant la revente (relancez la sonde)";
   if(!closed && !out_seen)
     {
      left_open = true;
      if(no_stop) g_no_stop = true;
      st = no_stop ? "POSITION RESTEE OUVERTE SANS STOP (fermez-la a la main tout de suite)" : "POSITION RESTEE OUVERTE (fermez-la a la main)";
     }
   string s = head + st + ",";
   s += DoubleToString(vmin, 4) + "," + DoubleToString(k.bid, dg) + "," + DoubleToString(k.ask, dg) + "," + DoubleToString(buy, dg) + ",";
   s += DoubleToString(k2.bid, dg) + "," + DoubleToString(k2.ask, dg) + "," + DoubleToString(sell, dg) + ",";
   s += IntegerToString(nd) + "," + DoubleToString(com, 4) + "," + DoubleToString(fee, 4) + "," + DoubleToString(profit, 4) + ",";
   s += DoubleToString(swap, 4) + "," + DoubleToString(ts, 8) + "," + DoubleToString(tv, 8) + ",";
   s += DoubleToString(SymbolInfoDouble(nm, SYMBOL_TRADE_CONTRACT_SIZE), 4) + "," + IntegerToString((long)pos) + "\n";
   return s;
  }

void OnStart()
  {
   if(AccountInfoInteger(ACCOUNT_TRADE_MODE) != ACCOUNT_TRADE_MODE_DEMO)
     {
      Alert("SondeFP : compte REEL. Ce script ne passe d'ordres que sur un compte de demonstration. Rien n'a ete fait.");
      return;
     }
   if(AccountInfoInteger(ACCOUNT_MARGIN_MODE) != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
     {
      Alert("SondeFP : ce compte n'est pas en mode hedging (une position par ordre). Rien n'a ete fait.");
      return;
     }
   if(TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) == 0)
     {
      Alert("SondeFP : le trading automatique est desactive. Activez le bouton Algo Trading (barre d'outils de MetaTrader), puis relancez le script.");
      return;
     }
   if(MQLInfoInteger(MQL_TRADE_ALLOWED) == 0)
     {
      Alert("SondeFP : le trading est interdit pour ce script. Relancez-le et cochez la case qui autorise le trading algorithmique (onglet Commun de sa fenetre).");
      return;
     }
   FolderCreate("claude");
   FolderCreate("claude\\releve");
   FileDelete(DIR + "sonde.csv");                 // pas de vieux resultat a relire si la sonde est interrompue en route
   g_trade.SetExpertMagicNumber((ulong)InpMagic);
   g_trade.SetDeviationInPoints(100);
   string base[];
   int nb = StringSplit(InpSymbols, ',', base);
   string out = "base,name,status,volume,bid_before,ask_before,buy_price,bid_at_close,ask_at_close,sell_price,deals,commission,fee,profit,swap,tick_size,tick_value,contract_size,position\n";
   bool left_open = false;
   int done = 0;
   for(int i = 0; i < nb && !IsStopped(); i++)
     {
      StringTrimLeft(base[i]);
      StringTrimRight(base[i]);
      if(base[i] == "") continue;                 // virgule en trop dans la liste : la recherche ne doit pas prendre le premier marche venu
      string nm = Resolve(base[i]);
      Comment("Sonde en cours (compte de demonstration) : ", base[i], " (", IntegerToString(i + 1), "/", IntegerToString(nb), ")");
      if(nm == "")
        {
         out += base[i] + ",,INTROUVABLE\n";
         continue;
        }
      string line = Probe(base[i], nm, left_open);
      out += line;
      if(StringFind(line, ",ok,") > 0) done++;
     }
   out += "#currency=" + AccountInfoString(ACCOUNT_CURRENCY) + ",server=" + AccountInfoString(ACCOUNT_SERVER) + ",server_time=" + IntegerToString((long)TimeTradeServer()) + "\n";
   bool written = false;
   int h = FileOpen(DIR + "sonde.csv", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h != INVALID_HANDLE)
     {
      written = FileWriteString(h, out) > 0;
      FileClose(h);
     }
   Print("SondeFP termine\n", out);
   Comment("Sonde terminee : ", IntegerToString(done), " marches sur ", IntegerToString(nb), ".\nFichier : MQL5\\Files\\claude\\releve\\sonde.csv");
   if(!written) Alert("SondeFP : le fichier MQL5\\Files\\claude\\releve\\sonde.csv n'a pas pu etre ecrit. Le resultat est dans l'onglet Experts ; relancez le script.");
   if(left_open) Alert("SondeFP : une position n'a pas pu etre refermee. Fermez-la a la main dans l'onglet Trading ", (g_no_stop ? "TOUT DE SUITE : elle n'a PAS de stop." : "(elle a un stop)."));
   else if(written) Alert("Sonde terminee : ", IntegerToString(done), " marches sur ", IntegerToString(nb), ". Vous pouvez le dire a Claude.");
  }
//+------------------------------------------------------------------+
