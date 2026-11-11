import sys
sys.path.insert(0, "/home/user/gold-orb/lab")
from pivbb.tracks.run.harness import trial
CORE = ["D_R1", "D_S1", "D_R2", "D_S2", "PDH", "PDL"]
B = dict(levels=CORE)
blocks = {
 "A": [("A1 close15 market", dict(B)), ("A2 touch stop-order", dict(B, entry="touch", fill="pending")), ("A3 touch market", dict(B, entry="touch")),
       ("A4 retest limit", dict(B, entry="retest", fill="pending")), ("A5 retest market", dict(B, entry="retest"))],
 "B": [("B1 P", dict(levels=["D_P"])), ("B2 R1/S1", dict(levels=["D_R1", "D_S1"])), ("B3 R2/S2", dict(levels=["D_R2", "D_S2"])),
       ("B4 PDH/PDL", dict(levels=["PDH", "PDL"])), ("B5 weekly P/R1/S1", dict(levels=["W_P", "W_R1", "W_S1"])), ("B6 R3/S3", dict(levels=["D_R3", "D_S3"])),
       ("B7 core outward", dict(B, away=1)), ("B8 core toward P", dict(B, away=-1))],
 "C": [("C1 18-02", dict(B, hours=[18, 2])), ("C2 02-08", dict(B, hours=[2, 8])), ("C3 08-12", dict(B, hours=[8, 12])), ("C4 12-16", dict(B, hours=[12, 16])),
       ("C5 02-12", dict(B, hours=[2, 12]))],
 "D": [("D1 first break", dict(B, nth="first")), ("D2 later breaks", dict(B, nth="later"))],
 "E": [("E1 squeeze<0.7", dict(B, sq_max=0.7)), ("E2 expansion>=1.6", dict(B, sq_min=1.6)), ("E3 band walk>=2", dict(B, walk_min=2)),
       ("E4 close outside band", dict(B, bbout=True)), ("E5 close inside band", dict(B, bbout=False)), ("E6 squeeze & outside", dict(B, sq_max=0.7, bbout=True))],
 "F": [("F1 no target", dict(B, target=None)), ("F2 trail mid, no target", dict(B, target=None, trail_mid=True)), ("F3 target + trail mid", dict(B, trail_mid=True)),
       ("F4 stop mid, target", dict(B, stop="mid", stop_atr=0.05)), ("F5 stop mid + trail mid", dict(B, stop="mid", stop_atr=0.05, target=None, trail_mid=True)),
       ("F6 stop 0.15", dict(B, stop_atr=0.15)), ("F7 stop 0.40", dict(B, stop_atr=0.40)), ("F8 target 1R", dict(B, target=1.0)),
       ("F9 trail mid, hold 1d", dict(B, target=None, trail_mid=True, hold_days=1))],
}
for blk in sys.argv[1:]:
    for tag, prm in blocks[blk]:
        trial(tag, prm, full=True)
