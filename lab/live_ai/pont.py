"""Le pont entre le cerveau (ce programme, sur l'ordinateur) et les mains (ClaudeMains.mq5, dans MT5).

Tout passe par des fichiers du dossier MQL5/Files/claude du terminal (protocole décrit en tête de
mql5/ClaudeMains.mq5) :
    lecture   account.txt, symbols.csv, positions.csv, deals.csv, bars_<marché>_<M1|M5|H1|D1>.csv
    écriture  brain_alive.txt (signe de vie), cmd/<id>.txt (un ordre)   ->   réponse dans res/<id>.txt

    h = Hands.find()                 # trouve le dossier tout seul (Mac ou Windows)
    h.alive()                        # à appeler au moins toutes les 60 s, sinon les mains refusent tout nouvel ordre
    h.bars("XAUUSD", "M5")           # bougies terminées, index en heure UTC
    r = h.open("XAUUSD", "buy", volume=0.05, sl=4051.20, ttl_min=240, tag="pivot")
    h.modify(r["ticket"], sl=4055.00);  h.close(r["ticket"])

Test du branchement (aucun ordre n'est passé) :   python3 pont.py
"""
import glob
import itertools
import os
import sys
import time
from pathlib import Path

import pandas as pd

NY = "America/New_York"


def server_to_utc(sec):
    """Heure serveur MT5 (secondes, horloge du courtier) -> UTC. FP Markets : serveur = New York + 7 h,
    soit UTC+2 l'hiver et UTC+3 pendant l'heure d'été américaine."""
    s = pd.to_datetime(pd.Series(sec, dtype="int64"), unit="s")
    u3 = (s - pd.Timedelta(hours=3)).dt.tz_localize("UTC")
    summer = (u3.dt.tz_convert(NY).dt.tz_localize(None) - u3.dt.tz_localize(None)) == pd.Timedelta(hours=-4)
    return pd.DatetimeIndex(u3.where(summer, u3 + pd.Timedelta(hours=1)))


class Hands:
    def __init__(self, folder):
        self.dir = Path(folder)
        self._ids = itertools.count(1)

    # ------------------------------------------------------------------ localisation
    @staticmethod
    def find():
        """Dossier .../MQL5/Files/claude créé par les mains au premier lancement."""
        home = str(Path.home())
        pats = [home + "/Library/Application Support/**/MQL5/Files/claude",            # MetaTrader 5 pour Mac
                os.environ.get("APPDATA", "") + "/MetaQuotes/Terminal/*/MQL5/Files/claude",   # Windows
                home + "/.wine/**/MQL5/Files/claude", home + "/.mt5/**/MQL5/Files/claude"]    # Linux (Wine)
        found = [p for pat in pats if pat for p in glob.glob(pat, recursive=True)]
        if not found:
            raise FileNotFoundError("dossier MQL5/Files/claude introuvable : les mains (ClaudeMains) ont-elles été "
                                    "lancées une fois sur un graphique de MT5 ?")
        found.sort(key=lambda p: os.path.getmtime(os.path.join(p, "account.txt")) if os.path.exists(os.path.join(p, "account.txt")) else 0)
        return Hands(found[-1])

    # ------------------------------------------------------------------ lecture
    def _read(self, name, tries=5):
        for _ in range(tries):                       # les mains remplacent les fichiers d'un coup ; on réessaie au besoin
            try:
                return (self.dir / name).read_text(encoding="latin-1")
            except (FileNotFoundError, PermissionError):
                time.sleep(0.05)
        raise FileNotFoundError(str(self.dir / name))

    def _kv(self, name):
        out = {}
        for ln in self._read(name).splitlines():
            if "=" in ln:
                k, v = ln.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    def _csv(self, name):
        from io import StringIO
        return pd.read_csv(StringIO(self._read(name)))

    def account(self):
        a = self._kv("account.txt")
        num = ("balance", "equity", "margin", "margin_free", "start_balance", "day_start_balance", "max_risk_pct",
               "daily_loss_pct", "kill_pct")
        for k in num:
            a[k] = float(a[k])
        for k in ("ea_time_gmt", "server_time", "server_minus_gmt_sec", "leverage", "demo", "hedging", "trade_allowed",
                  "max_positions", "max_per_symbol"):
            a[k] = int(a[k])
        return a

    def ea_alive(self, max_age=30):
        """Les mains tournent-elles ? (elles réécrivent account.txt toutes les 5 s)"""
        try:
            return time.time() - self.account()["ea_time_gmt"] <= max_age
        except (FileNotFoundError, KeyError, ValueError):
            return False

    def symbols(self):
        return self._csv("symbols.csv").set_index("base")

    def positions(self):
        return self._csv("positions.csv")

    def deals(self):
        d = self._csv("deals.csv")
        d["time_utc"] = server_to_utc(d["time"].to_numpy()) if len(d) else pd.DatetimeIndex([], tz="UTC")
        return d

    def bars(self, base, tf):
        """Bougies terminées du marché `base` ("XAUUSD", "US100", "BTCUSD") en M1, M5, H1 ou D1 ; index UTC (début de bougie)."""
        b = self._csv(f"bars_{base}_{tf}.csv")
        b.index = server_to_utc(b.pop("time").to_numpy())
        b.index.name = "time_utc"
        return b

    # ------------------------------------------------------------------ écriture
    def _put(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(text, encoding="latin-1", newline="")
        os.replace(tmp, p)

    def alive(self):
        self._put("brain_alive.txt", f"time_gmt={int(time.time())}\r\n")

    def send(self, action, timeout=20.0, **kw):
        """Envoie un ordre aux mains et attend leur réponse : dict avec ok (bool), reason, et selon l'ordre
        ticket, price, volume, sl... Si les mains ne répondent pas à temps : ok=False, reason="pas de réponse"."""
        cid = f"{int(time.time() * 1000):013d}_{next(self._ids):04d}"
        lines = [f"action={action}"] + [f"{k}={v}" for k, v in kw.items() if v is not None]
        self._put(f"cmd/{cid}.txt", "\r\n".join(lines) + "\r\n")
        res, t0 = self.dir / "res" / f"{cid}.txt", time.time()
        while time.time() - t0 < timeout:
            if res.exists():
                r = self._kv(f"res/{cid}.txt")
                r["ok"] = r.get("ok") == "1"
                for k in ("ticket",):
                    if k in r:
                        r[k] = int(r[k])
                for k in ("price", "volume", "sl", "tp", "risk_money"):
                    if k in r:
                        r[k] = float(r[k])
                return r
            time.sleep(0.2)
        try:                                           # jamais d'ordre « en retard » : on le retire s'il n'a pas été pris
            (self.dir / "cmd" / f"{cid}.txt").unlink()
        except FileNotFoundError:
            pass
        return {"id": cid, "action": action, "ok": False, "reason": "pas de réponse des mains"}

    def ping(self):
        return self.send("ping", timeout=10).get("pong") == "1"

    def open(self, symbol, side, volume, sl, tp=0.0, ttl_min=0, tag="", valid_sec=20):
        """Ordre au marché avec stop obligatoire. Les mains réduisent la taille au risque maximum autorisé.
        ttl_min : durée de vie maximale de la position (les mains la ferment même si le cerveau s'arrête)."""
        expire = int(self.account()["server_time"]) + valid_sec
        return self.send("open", symbol=symbol, side=side, volume=f"{volume:.4f}", sl=repr(float(sl)), tp=repr(float(tp)),
                         ttl_min=int(ttl_min), tag=str(tag)[:20], expire=expire)

    def close(self, ticket, volume=0.0):
        return self.send("close", ticket=int(ticket), volume=f"{volume:.4f}")

    def modify(self, ticket, sl=None, tp=None):
        """Le stop ne peut que se rapprocher du prix (les mains refusent sinon) ; l'objectif est libre."""
        return self.send("modify", ticket=int(ticket), sl=None if sl is None else repr(float(sl)),
                         tp=None if tp is None else repr(float(tp)))

    def close_all(self):
        return self.send("close_all")


def main():
    """Test du branchement : ne passe aucun ordre."""
    try:
        h = Hands(sys.argv[1]) if len(sys.argv) > 1 else Hands.find()
    except FileNotFoundError as e:
        print("ECHEC :", e)
        return 1
    print("Dossier du pont :", h.dir)
    if not h.ea_alive():
        print("ECHEC : les mains ne donnent pas signe de vie (ClaudeMains est-il sur un graphique, bouton Algo Trading vert ?)")
        return 1
    a = h.account()
    print(f"Compte : {'DEMO' if a['demo'] else 'REEL'} | serveur {a['server']} | solde {a['balance']:.2f} {a['currency']} | "
          f"levier 1:{a['leverage']} | {'hedging' if a['hedging'] else 'netting'}")
    off = a["server_minus_gmt_sec"] / 3600
    print(f"Horloge : serveur = UTC{off:+.2f} h (attendu +2 ou +3)")
    s = h.symbols()
    for base, r in s.iterrows():
        if not isinstance(r["name"], str):
            print(f"  {base}: INTROUVABLE chez ce courtier (voir all_symbols.txt)")
            continue
        spread = (r["ask"] - r["bid"])
        print(f"  {base} -> {r['name']}: lot min {r['vol_min']:g}, pas {r['vol_step']:g}, contrat {r['contract_size']:g}, "
              f"spread {spread:.{int(r['digits'])}f} ({spread / r['bid'] * 1e4:.1f} pb), marge pour 1 lot {r['margin_1lot']:.0f} {a['currency']}")
        for tf in ("M1", "M5", "H1", "D1"):
            try:
                b = h.bars(base, tf)
                print(f"      {tf}: {len(b)} bougies, dernière {b.index[-1]:%Y-%m-%d %H:%M} UTC")
            except FileNotFoundError:
                print(f"      {tf}: pas encore de données (attendre une minute)")
    h.alive()
    time.sleep(2.5)
    ok = h.ping()
    print("Aller-retour d'un message :", "OK" if ok else "ECHEC (les mains n'ont pas répondu)")
    print("Blocage en cours :", a["blocked"] or "aucun")
    print("\nLE PONT FONCTIONNE." if ok else "\nLe pont ne fonctionne pas encore.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
