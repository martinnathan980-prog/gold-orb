"""The exact rule list of lead/DIRECTION4.md section 2: signal x frame x filter x exit, with stable ids
'<signal>|<frame>|<filter>|<exit>' (e.g. 'T04|H4|F1|72h'). Run as a script it writes scan/rules.csv and prints its
sha256 (the lead commits that hash before the first run on real bars).

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B -m scan.grammar [--out PATH]
"""
import argparse
import hashlib
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_CSV = os.path.join(HERE, "rules.csv")

MARKETS = ("xauusd", "xagusd", "oil", "eurusd", "gbpusd", "usdjpy", "audusd", "usdcad", "usdchf", "nzdusd", "eurjpy",
           "us100", "us500", "us30", "ger40")
UNITS = {
    "ALL15": MARKETS,
    "FX8": ("eurusd", "gbpusd", "usdjpy", "audusd", "usdcad", "usdchf", "nzdusd", "eurjpy"),
    "IDX4": ("us100", "us500", "us30", "ger40"),
    "COM3": ("xauusd", "xagusd", "oil"),
}
BASKETS = ("ALL15", "FX8", "IDX4", "COM3")
for _m in MARKETS:
    UNITS[_m] = (_m,)

FRAMES = ("H1", "H4", "D1")
ALL = FRAMES
# id: (family, frames, short definition). Exact definitions: GRAMMAR.md and signals.py.
SIGNALS = {
    "T01": ("trend", ALL, "EMA(10) crosses EMA(30)"),
    "T02": ("trend", ALL, "EMA(20) crosses EMA(50)"),
    "T03": ("trend", ALL, "EMA(50) crosses EMA(200)"),
    "T04": ("trend", ALL, "MACD(12,26,9) line crosses its signal line"),
    "T05": ("trend", ALL, "MACD(12,26) line crosses zero"),
    "T06": ("trend", ALL, "close beyond the highest high / lowest low of the previous 20 bars"),
    "T07": ("trend", ALL, "close beyond the highest high / lowest low of the previous 55 bars"),
    "T08": ("trend", ALL, "SuperTrend(ATR 10, x3) flips"),
    "T09": ("trend", ALL, "Ichimoku(9,26,52): close leaves the cloud"),
    "T10": ("trend", ALL, "close outside Keltner EMA20 +/- 2 ATR20: follow"),
    "T11": ("trend", ALL, "close outside Bollinger(20,2): follow"),
    "T12": ("trend", ALL, "+DI(14) crosses -DI(14) while ADX(14) >= 25"),
    "T13": ("trend", ALL, "Parabolic SAR(0.02,0.2) flips"),
    "R01": ("reversal", ALL, "RSI(2) < 10 buy / > 90 sell"),
    "R02": ("reversal", ALL, "RSI(7) < 20 buy / > 80 sell"),
    "R03": ("reversal", ALL, "RSI(14) < 30 buy / > 70 sell"),
    "R04": ("reversal", ALL, "Stochastic(14,3,3) %K crosses %D under 20 / over 80"),
    "R05": ("reversal", ALL, "close outside Bollinger(20,2): fade"),
    "R06": ("reversal", ALL, "CCI(20) back above -100 buy / back below +100 sell"),
    "R07": ("reversal", ALL, "three closes down in a row buy / up sell"),
    "R08": ("reversal", ("H4", "D1"), "IBS < 0.2 buy / > 0.8 sell"),
    "K01": ("shock", ALL, "bar return beyond 3 sd of the previous 500: follow"),
    "K02": ("shock", ALL, "bar return beyond 4 sd of the previous 500: follow"),
    "K03": ("shock", ALL, "bar return beyond 3 sd of the previous 500: fade"),
    "K04": ("shock", ALL, "bar return beyond 4 sd of the previous 500: fade"),
    "K05": ("shock", ALL, "bar range above 2.5 ATR(20): follow the bar's direction"),
    "K06": ("shock", ALL, "bar range above 2.5 ATR(20): fade the bar's direction"),
    "K07": ("shock", ALL, "after a 3-sd shock: first of the next 6 bars retracing 38.2 % and closing back: follow"),
    "C01": ("compression", ALL, "Bollinger width lowest of 120 at one of the previous 6 bars, close outside: follow"),
    "C02": ("compression", ALL, "previous bar narrowest of 7, close beyond its high / low: follow"),
    "C03": ("compression", ALL, "previous bar inside its predecessor, close beyond the predecessor: follow"),
    "P01": ("candle", ALL, "engulfing bar at a 10-bar low (buy) / high (sell)"),
    "P02": ("candle", ALL, "pin bar at a 10-bar low (buy) / high (sell)"),
    "L01": ("level", ALL, "close crosses a round level not crossed in the previous 120 bars: follow"),
    "H01": ("home-made", ALL, "ER(24) rises above 0.5: follow the 24-bar move"),
    "H02": ("home-made", ALL, "ER(24) < 0.15 and close highest / lowest of 24: fade"),
    "H03": ("home-made", ALL, ">= 85 % of the last 20 closes above EMA20 buy / <= 15 % sell"),
    "H04": ("home-made", ALL, "IBS > 0.8 three bars in a row buy / < 0.2 sell"),
    "H05": ("home-made", ALL, "24-bar move / (sd of returns x sqrt 24) rises above +3 buy / falls below -3 sell"),
}
FAMILY_CODE = {"trend": "T", "reversal": "R", "shock": "K", "compression": "C", "candle": "P", "level": "L",
               "home-made": "H"}
FILTERS = {"H1": ("F0", "F1", "F2", "F3", "F4", "F5", "F6", "F7"),
           "H4": ("F0", "F1", "F2", "F3", "F4"), "D1": ("F0", "F1", "F2", "F3", "F4")}
FILTER_TEXT = {"F0": "none", "F1": "with the H4 EMA200 trend", "F2": "against the H4 EMA200 trend",
               "F3": "ADX(14) of the frame >= 25", "F4": "ADX(14) of the frame < 20",
               "F5": "Asia 18:00-02:59 NY", "F6": "Europe 03:00-07:59 NY", "F7": "US 08:00-16:59 NY"}
EXITS = {"H1": (6, 24), "H4": (24, 72), "D1": (48, 120)}
STOP = ("d20", 2.0)
NO_MARKET = {"L01": ("oil",)}          # L01 is not run on oil (roll-adjusted bars)
# neighbouring parameters of one family (section 4 siblings): ordered lists, neighbours = adjacent entries
PARAM_CHAINS = (("T01", "T02", "T03"), ("T06", "T07"), ("R01", "R02", "R03"), ("K01", "K02"), ("K03", "K04"))


def rule_id(sig, frame, filt, hours):
    return f"{sig}|{frame}|{filt}|{hours}h"


def parse(rid):
    s, f, flt, ex = rid.split("|")
    return s, f, flt, int(ex[:-1])


def rules():
    """The ordered rule list: dicts with id, signal, family, frame, filter, exit_h."""
    out = []
    for sig, (fam, frames, _) in SIGNALS.items():
        for fr in FRAMES:
            if fr not in frames:
                continue
            for flt in FILTERS[fr]:
                for hrs in EXITS[fr]:
                    out.append({"id": rule_id(sig, fr, flt, hrs), "signal": sig, "family": fam, "frame": fr,
                                "filter": flt, "exit_h": hrs})
    return out


def markets_of(sig):
    return tuple(m for m in MARKETS if m not in NO_MARKET.get(sig, ()))


def siblings(rid):
    """Section 4: the same signal, frame and filter with the other exit; and the neighbouring parameter(s) of the
    same family with the same frame, filter and exit."""
    s, fr, flt, hrs = parse(rid)
    out = [rule_id(s, fr, flt, h) for h in EXITS[fr] if h != hrs]
    for ch in PARAM_CHAINS:
        if s in ch:
            i = ch.index(s)
            for j in (i - 1, i + 1):
                if 0 <= j < len(ch) and fr in SIGNALS[ch[j]][1]:
                    out.append(rule_id(ch[j], fr, flt, hrs))
    return out


def csv_text():
    buf = io.StringIO()
    buf.write("idx,id,signal,family,frame,filter,exit_h,stop,markets,siblings\n")
    for i, r in enumerate(rules()):
        buf.write(f"{i},{r['id']},{r['signal']},{r['family']},{r['frame']},{r['filter']},{r['exit_h']},"
                  f"d20x2.0,{' '.join(markets_of(r['signal']))},{' '.join(siblings(r['id']))}\n")
    return buf.getvalue()


def sha256_text(txt):
    return hashlib.sha256(txt.encode("utf-8")).hexdigest()


def write(path=RULES_CSV):
    txt = csv_text()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)
    return sha256_text(txt)


def file_sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_rules_file(path=RULES_CSV):
    """The committed rules.csv must equal the list this code generates (else the code or the file changed)."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{path}: run python3 -B -m scan.grammar first")
    with open(path, "r", encoding="utf-8") as f:
        if f.read() != csv_text():
            raise ValueError(f"{path} differs from the rule list generated by scan/grammar.py")
    return file_sha256(path)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=RULES_CSV)
    a = ap.parse_args(argv)
    sha = write(a.out)
    rs = rules()
    cells = sum(len(markets_of(r["signal"])) for r in rs)
    print(f"rules: {len(rs)}  cells: {cells}  file: {a.out}")
    print(f"sha256 {sha}")


if __name__ == "__main__":
    main()
