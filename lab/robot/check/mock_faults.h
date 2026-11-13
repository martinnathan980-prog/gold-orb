// mock_faults.h - scripted broker failures for the replay mock (SPEC 7, T8). Owner: J.
//
// mock_replay.h includes this file after its internals (rp_pos, rp_deals, rp_orders, rp_syms, rp_res, rp_now ...), so a
// world can read and change them. A world is a text file named by MOCK_FAULTS, one action per line:
//     <server time> <action> [args...]          (server seconds; '#' starts a comment; times in any order)
// A timed action applies at the first hook call at or after its time (hooks run at every event, every timer pass through
// TerminalInfoInteger(TERMINAL_CONNECTED), every request and every CopyRates). Request modifiers wait for the next
// request(s) of their kind made at or after their time, n times (default 1):
//   refuse_open RC [n] [magic]      an open answers RC, nothing is made (a REJECTED history order is left)
//   refuse_close RC [n] [magic]     a close answers RC, the position stays
//   refuse_sltp RC [n] [magic]      a stop move answers RC, the stop stays
//   timeout_open_done [n] [magic] [shift] [hide]   the open is made, the answer is 10012 (timeout): a result the EA cannot
//                                   read; its order and deal are stamped `shift` s after TimeTradeServer() and its position
//                                   is listed `hide` s later (R5 e: a deal timed after the terminal's clock)
//   timeout_open_none [n] [magic]   nothing is made, the answer is 10012
//   slow_open SECS [n] [magic]      the open is made, the answer is 10012, and its order, deal and position appear only
//                                   SECS seconds later
//   drop_sl SECS [n] [magic]        the open is made without the stop it asked for (DONE); with SECS > 0 the position is
//                                   listed only SECS seconds later (its deal and order are there at once)
//   dup_open [n] [magic]            the broker makes the open twice (two positions, two IN deals)
//   deal_future SECS [n] [magic]    the open's deal and order are stamped SECS seconds after TimeTradeServer()
// Timed actions:
//   sl_remove MAGIC                 the stop of the open positions of that magic is removed (by hand on the phone)
//   comment MAGIC TEXT              the comment of the open positions of that magic becomes TEXT (no spaces)
//   hide_positions SECS             every open position is unlisted for SECS seconds (listed late after a restart)
//   disconnect SECS                 TERMINAL_CONNECTED is false for SECS seconds
//   gmt_shift SECS                  TimeGMT() is SECS seconds off from now on (a wrong computer clock)
//   freeze SYMBOL POINTS            the symbol's freeze level, from now on
//   stops SYMBOL POINTS             the symbol's stops level, from now on
//   lock_hold AGE_S                 the instance lock exists with a heartbeat AGE_S seconds old (another copy that runs
//                                   (AGE_S < 10) or a crashed one); lock_beat keeps it fresh at every hook call
//   lock_beat SECS                  another copy refreshes the lock for SECS seconds
//   hand_open SYMBOL SIDE VOL       a position opened by hand (magic 777) at the current quote (moves the equity)
//   hand_close                      the hand positions are closed at the current quote
//   (time 0 for lock_hold / lock_beat: applied before OnInit, against MOCK_FROM + 2 s, the first timer call)
//   session SYMBOL DOW FROM TO      SymbolInfoSessionTrade(SYMBOL, DOW) gives one more session FROM-TO (hhmm, server);
//                                   a symbol with no session line keeps the mock's default (no information)
// Every applied action and every faulted request is logged in _mock/log.txt as "FAULT ...", and counted in
// _mock/faults.txt (written at every hook call that changed something), so a test can check that it really happened.
#pragma once
#include <fstream>
#include <string>

struct MfAct
  {
   long   t = 0;
   string what;
   std::vector<string> a;
   bool   done = false;          // timed actions
   int    left = 1;              // request modifiers: how many requests are still to fault
  };
struct MfHidden { long until; RpPos p; };
struct MfLate { long until; RpPos p; std::vector<RpDeal> deals; std::vector<RpOrder> orders; };
struct MfSess { string sym; int dow; long from, to; };

static std::vector<MfAct> mf_acts;
static std::vector<MfHidden> mf_hidden;
static std::vector<MfLate> mf_late;
static std::vector<MfSess> mf_sess;
static long mf_disc_until = 0;
static long mf_beat_until = 0;
static string mf_lock_name = "CR_lock_12345678";
static std::map<string, long> mf_count;
static bool mf_dirty = false;

static void mf_note(const string &what)
  {
   mf_count[what]++;
   mf_dirty = true;
   rp_logf("FAULT %ld %s", rp_now, what.c_str());
  }

static void mf_save_counts()
  {
   if(!mf_dirty) return;
   mf_dirty = false;
   FILE *f = fopen(rp_path("_mock/faults.txt").c_str(), "w");
   if(!f) return;
   for(const auto &kv : mf_count) fprintf(f, "%s %ld\n", kv.first.c_str(), kv.second);
   fclose(f);
  }

static long mf_arg(const MfAct &x, size_t i, long def) { return i < x.a.size() ? atol(x.a[i].c_str()) : def; }

static void mf_init()
  {
   const char *p = getenv("MOCK_FAULTS");
   if(!p) return;
   std::ifstream in(p);
   string line;
   while(std::getline(in, line))
     {
      size_t h = line.find('#');
      if(h != string::npos) line = line.substr(0, h);
      std::stringstream ss(line);
      MfAct x;
      if(!(ss >> x.t >> x.what)) continue;
      string w;
      while(ss >> w) x.a.push_back(w);
      if(x.what == "refuse_open" || x.what == "refuse_close" || x.what == "refuse_sltp") x.left = (int)mf_arg(x, 1, 1);
      else if(x.what == "timeout_open_done" || x.what == "timeout_open_none" || x.what == "dup_open") x.left = (int)mf_arg(x, 0, 1);
      else if(x.what == "slow_open" || x.what == "drop_sl" || x.what == "deal_future") x.left = (int)mf_arg(x, 1, 1);
      if(x.what == "session")
        {
         MfSess s;
         s.sym = x.a.size() > 0 ? x.a[0] : "";
         s.dow = (int)mf_arg(x, 1, -1);
         long f = mf_arg(x, 2, 0), t = mf_arg(x, 3, 0);
         s.from = (f / 100) * 3600 + (f % 100) * 60;
         s.to = (t / 100) * 3600 + (t % 100) * 60;
         mf_sess.push_back(s);
         continue;
        }
      mf_acts.push_back(x);
     }
   const char *fr = getenv("MOCK_FROM");
   long t_init = fr ? atol(fr) + 2 : 0;                       // the first timer call: OnInit runs then
   for(MfAct &x : mf_acts)
     {
      if(x.t != 0 || (x.what != "lock_hold" && x.what != "lock_beat")) continue;
      if(x.what == "lock_hold")
        {
         rp_gv[mf_lock_name] = (double)(t_init * 1000 + 500 - mf_arg(x, 0, 0) * 1000);
         rp_gv_time[mf_lock_name] = t_init;
         rp_gv_temp.insert(mf_lock_name);
        }
      else mf_beat_until = t_init + mf_arg(x, 0, 60);
      x.done = true;
      mf_note(x.what + " at init");
     }
   mf_note("init " + std::to_string(mf_acts.size()) + " actions");
  }

// timed actions due now, hidden positions and late requests whose time has come
static void mf_pump()
  {
   for(MfAct &x : mf_acts)
     {
      if(x.done || x.t > rp_now) continue;
      if(x.what == "sl_remove" || x.what == "comment")
        {
         long magic = mf_arg(x, 0, 0);
         for(RpPos &p : rp_pos)
            if(p.magic == magic)
              {
               if(x.what == "sl_remove") p.sl = 0.0;
               else p.comment = x.a.size() > 1 ? x.a[1] : "";
              }
         mf_note(x.what + " " + std::to_string(magic));
        }
      else if(x.what == "hide_positions")
        {
         long until = rp_now + mf_arg(x, 0, 5);
         for(const RpPos &p : rp_pos) mf_hidden.push_back({until, p});
         mf_note("hide_positions " + std::to_string(rp_pos.size()));
         rp_pos.clear();
        }
      else if(x.what == "disconnect")
        {
         mf_disc_until = rp_now + mf_arg(x, 0, 60);
         mf_note("disconnect");
        }
      else if(x.what == "gmt_shift")
        {
         rp_gmt_shift = mf_arg(x, 0, 0);
         mf_note("gmt_shift " + std::to_string(rp_gmt_shift));
        }
      else if(x.what == "freeze" || x.what == "stops")
        {
         RpSym *s = x.a.size() > 0 ? rp_find(x.a[0]) : nullptr;
         if(s)
           {
            if(x.what == "freeze") s->freeze_level = mf_arg(x, 1, 0);
            else s->stops_level = mf_arg(x, 1, 0);
           }
         mf_note(x.what);
        }
      else if(x.what == "lock_hold")
        {
         rp_gv[mf_lock_name] = (double)(GetTickCount64() - (ulong)(mf_arg(x, 0, 0) * 1000));
         rp_gv_time[mf_lock_name] = rp_now;
         rp_gv_temp.insert(mf_lock_name);
         mf_note("lock_hold");
        }
      else if(x.what == "lock_beat")
        {
         mf_beat_until = rp_now + mf_arg(x, 0, 60);
         mf_note("lock_beat");
        }
      else if(x.what == "hand_open")
        {
         RpSym *s = x.a.size() > 0 ? rp_find(x.a[0]) : nullptr;
         if(s && s->cur >= 0)
           {
            int type = mf_arg(x, 1, 1) > 0 ? 0 : 1;
            double vol = x.a.size() > 2 ? atof(x.a[2].c_str()) : 1.0;
            double bid = s->tick_bid, ask = rp_ask(*s, s->tick_bid, s->bars[s->cur].spread);
            double px = type == 0 ? ask : bid;
            ulong ord = rp_add_order(s->name, type, ORDER_STATE_FILLED, 0, 777, vol, px, 0.0, 0.0, "hand");
            RpPos p = {ord, s->name, type, vol, px, 0.0, 0.0, 777, rp_now, "hand"};
            rp_pos.push_back(p);
            rp_add_deal(p, type, DEAL_ENTRY_IN, vol, px, DEAL_REASON_CLIENT, 777, rp_now, 0.0, rp_comm(*s, vol), ord, "hand");
            mf_note("hand_open " + std::to_string(ord));
           }
        }
      else if(x.what == "hand_close")
        {
         for(long k = (long)rp_pos.size() - 1; k >= 0; k--)
           {
            if(rp_pos[k].magic != 777) continue;
            RpSym *s = rp_find(rp_pos[k].symbol);
            double bid = s->tick_bid, ask = rp_ask(*s, s->tick_bid, s->bars[s->cur].spread);
            rp_close_at(k, rp_pos[k].type == 0 ? bid : ask, DEAL_REASON_CLIENT, rp_now, 777);
            mf_note("hand_close");
           }
        }
      else continue;                              // a request modifier: it waits for its request
      x.done = true;
     }
   if(mf_beat_until > rp_now && rp_gv.count(mf_lock_name)) rp_gv[mf_lock_name] = (double)GetTickCount64();
   for(size_t i = 0; i < mf_hidden.size();)
     {
      if(mf_hidden[i].until <= rp_now)
        {
         rp_pos.push_back(mf_hidden[i].p);
         mf_note("listed " + std::to_string(mf_hidden[i].p.ticket));
         mf_hidden.erase(mf_hidden.begin() + i);
        }
      else i++;
     }
   for(size_t i = 0; i < mf_late.size();)
     {
      if(mf_late[i].until <= rp_now)
        {
         for(const RpDeal &d : mf_late[i].deals)
           {
            rp_deals.push_back(d);
            rp_balance += d.profit + d.commission;
            MqlTradeRequest q = MqlTradeRequest();
            rp_queue_tx(TRADE_TRANSACTION_DEAL_ADD, d.deal, d.order, d.symbol, d.position, q);
           }
         for(const RpOrder &o : mf_late[i].orders) rp_orders.push_back(o);
         rp_pos.push_back(mf_late[i].p);
         mf_note("late_appeared " + std::to_string(mf_late[i].p.ticket));
         mf_late.erase(mf_late.begin() + i);
        }
      else i++;
     }
   mf_save_counts();
  }

// the first request modifier of that name due now that matches the request's magic (args index of the magic)
static MfAct *mf_take(const char *name, const MqlTradeRequest &req, size_t magic_arg)
  {
   for(MfAct &x : mf_acts)
     {
      if(x.what != name || x.left <= 0 || x.t > rp_now) continue;
      long m = mf_arg(x, magic_arg, 0);
      if(m != 0 && m != (long)req.magic) continue;
      x.left--;
      return &x;
     }
   return nullptr;
  }

static bool mf_copyrates_fail(const string &) { mf_pump(); return false; }

static int mf_request(MqlTradeRequest &req, MqlTradeResult &res)
  {
   mf_pump();
   bool open = req.action == TRADE_ACTION_DEAL && req.position == 0;
   bool close = req.action == TRADE_ACTION_DEAL && req.position != 0;
   bool sltp = req.action == TRADE_ACTION_SLTP;
   MfAct *x = nullptr;
   if(open && (x = mf_take("refuse_open", req, 2)))
     {
      res.retcode = (uint)mf_arg(*x, 0, TRADE_RETCODE_REJECT);
      rp_add_order(req.symbol, req.type == ORDER_TYPE_BUY ? 0 : 1, ORDER_STATE_REJECTED, 0, (long)req.magic, req.volume, 0.0, req.sl, req.tp,
                   req.comment);
      mf_note("refuse_open " + std::to_string(res.retcode));
      return 1;
     }
   if(close && (x = mf_take("refuse_close", req, 2)))
     {
      res.retcode = (uint)mf_arg(*x, 0, TRADE_RETCODE_REJECT);
      mf_note("refuse_close " + std::to_string(res.retcode));
      return 1;
     }
   if(sltp && (x = mf_take("refuse_sltp", req, 2)))
     {
      res.retcode = (uint)mf_arg(*x, 0, TRADE_RETCODE_INVALID_STOPS);
      mf_note("refuse_sltp " + std::to_string(res.retcode));
      return 1;
     }
   if(open && (x = mf_take("timeout_open_none", req, 1)))
     {
      res.retcode = TRADE_RETCODE_TIMEOUT;
      mf_note("timeout_open_none");
      return 1;
     }
   if(open && (x = mf_take("timeout_open_done", req, 1)))
     {
      bool ok = rp_open(req.symbol, req.type == ORDER_TYPE_BUY ? 0 : 1, req.volume, req.sl, req.tp, req.comment, req.magic);
      ulong ord = rp_res.order;
      long shift = mf_arg(*x, 2, 0), hide = mf_arg(*x, 3, 0);
      if(ok && shift != 0)
        {
         for(RpDeal &d : rp_deals)
            if(d.order == ord) d.time += shift;
         for(RpOrder &o : rp_orders)
            if(o.ticket == ord) { o.setup += shift; o.done += shift; }
        }
      long i = rp_pos_index(ord);
      if(ok && hide > 0 && i >= 0)
        {
         mf_hidden.push_back({rp_now + hide, rp_pos[i]});
         rp_pos.erase(rp_pos.begin() + i);
        }
      res = MqlTradeResult();
      res.retcode = TRADE_RETCODE_TIMEOUT;
      mf_note("timeout_open_done shift=" + std::to_string(shift) + " hide=" + std::to_string(hide));
      return 1;
     }
   if(open && (x = mf_take("slow_open", req, 2)))
     {
      size_t nd = rp_deals.size(), no = rp_orders.size(), nt = rp_tx.size();
      double bal = rp_balance;
      bool ok = rp_open(req.symbol, req.type == ORDER_TYPE_BUY ? 0 : 1, req.volume, req.sl, req.tp, req.comment, req.magic);
      if(ok && !rp_pos.empty())
        {
         MfLate l;
         l.until = rp_now + mf_arg(*x, 0, 3);
         l.p = rp_pos.back();
         rp_pos.pop_back();
         for(size_t i = nd; i < rp_deals.size(); i++) l.deals.push_back(rp_deals[i]);
         for(size_t i = no; i < rp_orders.size(); i++) l.orders.push_back(rp_orders[i]);
         rp_deals.resize(nd);
         rp_orders.resize(no);
         rp_balance = bal;
         rp_tx.resize(nt);                        // its transactions come with it, later (none is delivered meanwhile)
         mf_late.push_back(l);
        }
      res = MqlTradeResult();
      res.retcode = TRADE_RETCODE_TIMEOUT;
      mf_note("slow_open");
      return 1;
     }
   return 0;
  }

static void mf_after(const MqlTradeRequest &req, MqlTradeResult &res)
  {
   bool open = req.action == TRADE_ACTION_DEAL && req.position == 0 && res.retcode == TRADE_RETCODE_DONE;
   if(!open) { mf_save_counts(); return; }
   MfAct *x = nullptr;
   long i = rp_pos_index(res.order);
   if(i >= 0 && (x = mf_take("drop_sl", req, 2)))
     {
      rp_pos[i].sl = 0.0;
      long secs = mf_arg(*x, 0, 0);
      if(secs > 0)
        {
         mf_hidden.push_back({rp_now + secs, rp_pos[i]});
         rp_pos.erase(rp_pos.begin() + i);
         i = -1;
        }
      mf_note("drop_sl " + std::to_string(secs));
     }
   if(i >= 0 && (x = mf_take("dup_open", req, 1)))
     {
      RpPos p = rp_pos[i];
      RpSym *s = rp_find(p.symbol);
      ulong ord = rp_add_order(p.symbol, p.type, ORDER_STATE_FILLED, 0, p.magic, p.volume, p.price_open, p.sl, p.tp, p.comment);
      p.ticket = ord;
      rp_pos.push_back(p);
      rp_add_deal(p, p.type, DEAL_ENTRY_IN, p.volume, p.price_open, DEAL_REASON_EXPERT, p.magic, rp_now, 0.0, s ? rp_comm(*s, p.volume) : 0.0,
                  ord, p.comment);
      mf_note("dup_open " + std::to_string(ord));
     }
   if(i >= 0 && (x = mf_take("deal_future", req, 1)))
     {
      long secs = mf_arg(*x, 0, 5);
      for(RpDeal &d : rp_deals)
         if(d.order == res.order) d.time += secs;
      for(RpOrder &o : rp_orders)
         if(o.ticket == res.order) { o.setup += secs; o.done += secs; }
      mf_note("deal_future " + std::to_string(secs));
     }
   mf_save_counts();
  }

static void mf_event(long) { mf_pump(); }
static bool mf_connected() { mf_pump(); return rp_now >= mf_disc_until; }
static int  mf_session(const string &sym, int dow, uint idx, datetime &from, datetime &to)
  {
   bool any = false;
   uint k = 0;
   for(const MfSess &s : mf_sess)
     {
      if(s.sym != sym) continue;
      any = true;
      if(s.dow != dow) continue;
      if(k == idx)
        {
         from = s.from;
         to = s.to;
         return 1;
        }
      k++;
     }
   return any ? 0 : -1;
  }
