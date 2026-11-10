"""Test du pont côté ordinateur, sans MT5 : de fausses mains écrivent les mêmes fichiers que ClaudeMains.mq5
et répondent aux ordres (mêmes formats, mêmes refus de base).   python3 test_pont.py"""
import tempfile
import threading
import time
from pathlib import Path

import pandas as pd

from pont import Hands, server_to_utc


class FakeHands(threading.Thread):
    """Imite ClaudeMains : exporte l'état, exécute cmd/*.txt, écrit res/*.txt (stop obligatoire, stop qui ne recule pas)."""

    def __init__(self, folder):
        super().__init__(daemon=True)
        self.d = Path(folder)
        for sub in ("cmd", "res", "done"):
            (self.d / sub).mkdir(parents=True, exist_ok=True)
        self.pos, self.next_ticket, self.stop = {}, 1000, False
        self.bid, self.ask = 4080.10, 4080.23
        self.export()

    def put(self, name, text):
        tmp = self.d / (name + ".tmp")
        tmp.write_text(text, encoding="latin-1")
        tmp.replace(self.d / name)

    def export(self):
        now = int(time.time())
        self.put("account.txt", f"ea_version=1.00\nea_time_gmt={now}\nserver_time={now + 7200}\nserver_minus_gmt_sec=7200\n"
                 "balance=1000.00\nequity=1000.00\nmargin=0.00\nmargin_free=1000.00\ncurrency=EUR\nleverage=500\ndemo=1\n"
                 "hedging=1\nserver=FPMarkets-Demo\ntrade_allowed=1\nblocked=\nstart_balance=1000.00\nday_start_balance=1000.00\n"
                 "max_risk_pct=1.00\nmax_positions=6\nmax_per_symbol=2\ndaily_loss_pct=6.00\nkill_pct=50.00\nmagic=20261110\n")
        self.put("symbols.csv", "base,name,digits,point,tick_size,tick_value,tick_value_loss,contract_size,vol_min,vol_step,vol_max,"
                 "stops_level,freeze_level,spread_points,bid,ask,tick_time,trade_mode,swap_long,swap_short,swap_mode,swap_3days,"
                 "margin_1lot,ccy_profit,ccy_margin\n"
                 f"XAUUSD,XAUUSD.r,2,0.01000000,0.01000000,0.89000000,0.89000000,100.0000,0.0100,0.0100,100.00,0,0,13,"
                 f"{self.bid:.2f},{self.ask:.2f},{now + 7200},4,-62.8900,37.5200,1,3,726.00,USD,USD\n"
                 "US100,,,,,,,,,,,,,,,,,,,,,,,,\n")
        rows = "".join(f"{t},XAUUSD.r,{p['side']},{p['volume']:.4f},{p['price']:.2f},{p['sl']:.2f},{p['tp']:.2f},{self.bid:.2f},0.00,0.00,"
                       f"{now + 7200},0,CM {p['tag']}\n" for t, p in self.pos.items())
        self.put("positions.csv", "ticket,symbol,side,volume,price_open,sl,tp,price_current,profit,swap,time_open,ttl_deadline,comment\n" + rows)
        self.put("deals.csv", "deal,position,time,symbol,type,entry,volume,price,profit,swap,commission,magic,reason,comment\n")
        t0 = (now + 7200) // 60 * 60
        self.put("bars_XAUUSD_M1.csv", "time,open,high,low,close,tick_volume,spread\n" + "".join(
            f"{t0 - 60 * (240 - i)},4080.00,4081.00,4079.50,4080.{i % 100:02d},50,13\n" for i in range(240)))

    def handle(self, f):
        raw = f.read_bytes().decode("latin-1")
        assert "\r\n" in raw                                    # le cerveau écrit des fins de ligne Windows pour MT5
        kv = dict(ln.split("=", 1) for ln in raw.splitlines() if "=" in ln)
        why, extra, a = "", "", kv.get("action")
        if a == "ping":
            extra = "pong=1\n"
        elif a == "open":
            sl, buy = float(kv.get("sl", 0)), kv["side"] == "buy"
            if sl <= 0:
                why = "stop obligatoire"
            elif (buy and sl >= self.bid) or (not buy and sl <= self.ask):
                why = "stop du mauvais cote ou trop pres"
            else:
                price = self.ask if buy else self.bid
                vol = min(float(kv["volume"]), int(10.0 / (abs(price - sl) * 100 * 0.89) / 0.01 + 1e-9) * 0.01)   # 1 % de 1000
                if vol < 0.01:
                    why = "limite de risque : le lot minimum (0.01) risquerait trop"
                else:
                    self.next_ticket += 1
                    self.pos[self.next_ticket] = dict(side=kv["side"], volume=vol, price=price, sl=sl, tp=float(kv.get("tp", 0)), tag=kv.get("tag", ""))
                    extra = f"ticket={self.next_ticket}\nprice={price:.2f}\nvolume={vol:.4f}\nsl={sl:.2f}\nrisk_money={abs(price - sl) * 100 * 0.89 * vol:.2f}\n"
        elif a == "modify":
            p = self.pos.get(int(kv.get("ticket", 0)))
            if p is None:
                why = "position introuvable"
            else:
                sl = float(kv.get("sl", p["sl"]))
                if (p["side"] == "buy" and sl < p["sl"]) or (p["side"] == "sell" and sl > p["sl"]):
                    why = "le stop ne peut que se rapprocher du prix"
                else:
                    p["sl"], p["tp"] = sl, float(kv.get("tp", p["tp"]))
                    extra = f"sl={p['sl']:.2f}\ntp={p['tp']:.2f}\n"
        elif a == "close":
            why = "" if self.pos.pop(int(kv.get("ticket", 0)), None) else "position introuvable"
        elif a == "close_all":
            self.pos.clear()
        else:
            why = "action inconnue"
        self.put(f"res/{f.stem}.txt", f"id={f.stem}\naction={a}\nok={'0' if why else '1'}\nreason={why}\n{extra}server_time={int(time.time()) + 7200}\n")
        f.replace(self.d / "done" / f.name)
        self.export()

    def run(self):
        while not self.stop:
            for f in sorted((self.d / "cmd").glob("*.txt")):
                self.handle(f)
            time.sleep(0.05)


def main():
    # horloge serveur -> UTC (New York + 7 h) : hiver, été, et les deux côtés du changement d'heure américain de mars 2026
    ts = lambda s: int(pd.Timestamp(s).timestamp())
    got = server_to_utc([ts("2026-01-15 12:00"), ts("2026-07-15 12:00"), ts("2026-03-08 08:30"), ts("2026-03-08 10:30"), ts("2026-11-10 20:00")])
    want = ["2026-01-15 10:00", "2026-07-15 09:00", "2026-03-08 06:30", "2026-03-08 07:30", "2026-11-10 18:00"]
    assert list(got.strftime("%Y-%m-%d %H:%M")) == want, got

    with tempfile.TemporaryDirectory() as d:
        fake = FakeHands(d)
        fake.start()
        h = Hands(d)
        assert h.ea_alive() and h.account()["balance"] == 1000.0 and h.account()["blocked"] == ""
        s = h.symbols()
        assert s.loc["XAUUSD", "name"] == "XAUUSD.r" and s.loc["XAUUSD", "vol_min"] == 0.01 and pd.isna(s.loc["US100", "name"])
        b = h.bars("XAUUSD", "M1")
        assert len(b) == 240 and str(b.index.tz) == "UTC" and b.index.is_monotonic_increasing
        assert abs((pd.Timestamp.now(tz="UTC") - b.index[-1]).total_seconds()) < 180      # dernière bougie = il y a une minute, en UTC
        assert h.ping()
        assert not h.open("XAUUSD", "buy", 0.05, sl=0)["ok"]                               # pas de stop -> refusé
        assert not h.open("XAUUSD", "buy", 0.05, sl=4090.0)["ok"]                          # stop du mauvais côté -> refusé
        r = h.open("XAUUSD", "buy", 0.50, sl=4075.23, ttl_min=60, tag="test")
        assert r["ok"] and r["ticket"] > 1000 and abs(r["volume"] - 0.02) < 1e-9, r        # taille réduite au risque max (1 %)
        assert len(h.positions()) == 1
        assert not h.modify(r["ticket"], sl=4070.0)["ok"]                                  # éloigner le stop -> refusé
        assert h.modify(r["ticket"], sl=4078.0)["ok"]                                      # le rapprocher -> accepté
        assert h.close(r["ticket"])["ok"] and len(h.positions()) == 0
        assert not h.close(424242)["ok"]
        fake.stop = True
        fake.join(1)
        assert h.send("ping", timeout=1.0)["reason"] == "pas de réponse des mains" and not list((Path(d) / "cmd").glob("*.txt"))
    print("pont : tous les tests passent")


if __name__ == "__main__":
    main()
