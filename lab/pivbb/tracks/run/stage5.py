import sys
sys.path.insert(0, "/home/user/gold-orb/lab")
from pivbb.tracks.run.harness import trial
BAND = ["B_U", "B_D"]
trial("control B: close +/-0.88 dATR", dict(levels=BAND, band_k=0.88, hours=[2, 12], target=None), kind="control")
trial("control A: close +/-0.88 dATR, 2R", dict(levels=BAND, band_k=0.88, entry="touch", target=2.0), kind="control")
