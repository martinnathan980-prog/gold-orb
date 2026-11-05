"""Stage 5: robustness neighbours of the pre-declared finalist F3 (decided from IS before this run):
F3 = Asia range 00:00-07:00 London, OCO stop entries at range +/- 10% width until 12:00 London,
stop = opposite side, exit 16:00 NY two business days later.
Neighbours, one parameter at a time: continuous +/-20%, discrete/clock params = adjacent grid cell.
(buf 0.0 = A3 already logged; buf 0.2 = adjacent cell on the other side.)"""
from research import run, n_trials
from stage2 import BASE, ASIA

F3 = {**ASIA, "hold_days": 2, "buf_frac": 0.1}
NB = {
    "N01_buf0.08": {**F3, "buf_frac": 0.08},
    "N02_buf0.12": {**F3, "buf_frac": 0.12},
    "N03_buf0.20": {**F3, "buf_frac": 0.20},
    "N04_hold1": {**F3, "hold_days": 1},
    "N05_hold3": {**F3, "hold_days": 3},
    "N06_rangeend06": {**F3, "range_end": "06:00"},
    "N07_rangeend08": {**F3, "range_end": "08:00"},
    "N08_rangestart23": {**F3, "range_start": "-01:00"},
    "N09_rangestart01": {**F3, "range_start": "01:00"},
    "N10_entryend11": {**F3, "entry_end": "11:00"},
    "N11_entryend13": {**F3, "entry_end": "13:00"},
    "N12_exit14ny": {**F3, "exit_time": "14:00"},
    "N13_exit18ny": {**F3, "exit_time": "18:00"},
    "N14_stopmid": {**F3, "stop_mode": "mid"},
}
if __name__ == "__main__":
    for k, v in NB.items():
        run(k, {**BASE, **v}, stage="5-neighbours-F3")
    print("trials so far:", n_trials())
