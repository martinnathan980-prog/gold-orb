"""validation_hi -- the lenses' code, imported (never edited), and ONE registry of the frozen rules.

Several lenses name their helper module `common`; each lens module is imported here under a private name with its
own `common` visible to it during the import only, so they never collide.

The rules: lab/r2/recalc.py::sleeves() is called exactly ONCE per process (it re-executes the strategy modules and
replaces their sys.modules entries on every call; a second call would leave earlier make_orders functions bound to
stale module globals, e.g. an empty nq_btc_follow leader registry whose default loader reads to 2025). The lenses
that build orders themselves (synthesis_B common, payoff common) receive this registry in memory (their module
attribute `_REG`), so every component calls the same function objects. `assert_registry_live()` checks it before
every order build.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
AUTOPSY = os.path.join(LAB, "r2", "tracks", "autopsy")
if LAB not in sys.path:
    sys.path.insert(0, LAB)

TEN = [("ocm4", "us100"), ("noise30", "us100"),
       ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd"), ("GOLD_FRI_PM", "xauusd"),
       ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
       ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"),
       ("nq_btc_follow", "btcusd")]
RULES = ["noise30", "ocm4", "donch4h_stop", "orb_asia_2d_buf10", "GOLD_FRI_PM", "brk72_24h_wd",
         "F1_brk_ridge_filter", "nq_btc_follow"]
STRATEGY_MODULES = ("r2_idx_us_strategy", "r2_crypto_strategy", "r2_leadlag_strategy", "r2_ml_strategy",
                    "r2_overnight_strategy", "strategy_trend", "strategy_orb")

_M = {}


def load_file(path, alias, provide=None):
    """Import the file `path` as module `alias`. `provide` maps bare module names the file imports (e.g. 'common')
    to module objects; they are visible under those names during the import only. The file's directory is first on
    sys.path during the import; nothing else is left behind in sys.modules under a bare name."""
    if alias in sys.modules:
        return sys.modules[alias]
    provide = provide or {}
    d = os.path.dirname(os.path.abspath(path))
    saved = {n: sys.modules.pop(n) for n in list(provide) + ["common"] if n in sys.modules}
    for n, m in provide.items():
        sys.modules[n] = m
    sys.path.insert(0, d)
    try:
        spec = importlib.util.spec_from_file_location(alias, path)
        m = importlib.util.module_from_spec(spec)
        sys.modules[alias] = m
        spec.loader.exec_module(m)
    finally:
        sys.path.remove(d)
        for n in list(provide) + ["common"]:
            got = sys.modules.pop(n, None)
            if got is not None and n not in provide:
                sys.modules[f"{alias}__{n}"] = got
        sys.modules.update(saved)
    return m


def registry():
    """{"sleeves": {(name, sym): (track, make_orders, params)}, "rules": {name: (track, make_orders, params)},
    "recalc": module}. recalc.sleeves() is called once."""
    if "reg" not in _M:
        rec = load_file(os.path.join(LAB, "r2", "recalc.py"), "vhi_r2_recalc")
        sl, rules = {}, {}
        for track, name, sym, mo, params in rec.sleeves():
            if name == "F2_brk_unfiltered":
                continue
            sl[(name, sym)] = (track, mo, dict(params))
            rules.setdefault(name, (track, mo, dict(params)))
        assert set(sl) == set(TEN), sorted(sl)
        assert set(rules) == set(RULES), sorted(rules)
        mods = {n: sys.modules[n] for n in STRATEGY_MODULES}
        _M["reg"] = {"sleeves": sl, "rules": rules, "recalc": rec, "modules": mods}
    return _M["reg"]


def assert_registry_live():
    """The strategy modules in sys.modules are still the ones the registry's functions are bound to."""
    reg = registry()
    for n, m in reg["modules"].items():
        assert sys.modules.get(n) is m, f"{n} was re-imported after the registry was built (a second sleeves() call)"
    _, mo, _ = reg["rules"]["nq_btc_follow"]
    assert mo.__globals__ is reg["modules"]["r2_leadlag_strategy"].__dict__


def synthesis_B():
    """synthesis_B's common, s1_run (K1 signal table, fold fit, walk-forward) and s2_portfolio (book, metrics), with
    the registry injected (their build_orders then calls the same make_orders objects)."""
    if "sB" not in _M:
        d = os.path.join(AUTOPSY, "synthesis_B")
        c = load_file(os.path.join(d, "common.py"), "vhi_sB_common")
        c._REG = registry()["rules"]
        s1 = load_file(os.path.join(d, "s1_run.py"), "vhi_sB_s1_run", {"common": c})
        s2 = load_file(os.path.join(d, "s2_portfolio.py"), "vhi_sB_s2_portfolio", {"common": c})
        assert s1.C is c and s2.C is c
        _M["sB"] = {"C": c, "S1": s1, "S2": s2}
    return _M["sB"]


def payoff():
    """The payoff lens's common (fills, censoring, statistics) and variants (S, T, H, B, info, hold decision)."""
    if "payoff" not in _M:
        d = os.path.join(AUTOPSY, "payoff")
        c = load_file(os.path.join(d, "common.py"), "vhi_payoff_common")
        c._REG = {k: v for k, v in registry()["sleeves"].items()}
        v = load_file(os.path.join(d, "variants.py"), "vhi_payoff_variants", {"common": c})
        assert v.C is c
        _M["payoff"] = {"C": c, "V": v}
    return _M["payoff"]


def cluster_engine():
    """The cluster lens's portfolio engine (run_engine: guards, 6 / 2 position caps)."""
    if "cluster" not in _M:
        _M["cluster"] = load_file(os.path.join(AUTOPSY, "cluster", "engine.py"), "vhi_cluster_engine")
    return _M["cluster"]


def stake_account():
    """lab/r2/tracks/stake/account.py (the small-account loop with the 6 / 2 caps) and its stake module."""
    if "account" not in _M:
        d = os.path.join(LAB, "r2", "tracks", "stake")
        s = load_file(os.path.join(d, "stake.py"), "vhi_stake_stake")
        a = load_file(os.path.join(d, "account.py"), "vhi_stake_account", {"stake": s})
        assert a.S is s
        if d in sys.path:                       # account.py inserts its own directory: take it out again
            sys.path.remove(d)
        _M["account"] = {"A": a, "S": s}
    return _M["account"]


def clear_rule_caches():
    """The rule modules cache bar frames keyed on id(frame) + length + ends: cleared before every build (the union
    of what the lenses clear)."""
    for name, mod in registry()["modules"].items():
        for attr in ("_cache", "_bar_cache", "_daily_cache", "_grid_cache", "_atr_cache", "_model_cache_unused"):
            c = getattr(mod, attr, None)
            if isinstance(c, dict):
                c.clear()
        cm = getattr(mod, "cm", None)
        if cm is not None:
            for attr in ("_grid_cache", "_atr_cache"):
                c = getattr(cm, attr, None)
                if isinstance(c, dict):
                    c.clear()


def set_leader(leader):
    """Register the cut us100 mid closes as nq_btc_follow's leader, through the make_orders function's own globals."""
    _, mo, _ = registry()["rules"]["nq_btc_follow"]
    g = mo.__globals__
    g["clear_leaders"]()
    g["set_leader"]("us100", leader)
    assert "us100" in g["_LEADERS"]


def leader_last_minute():
    _, mo, _ = registry()["rules"]["nq_btc_follow"]
    L = mo.__globals__["_LEADERS"].get("us100")
    return None if L is None else int(L[0][-1])
