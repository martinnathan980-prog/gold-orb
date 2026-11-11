import sys
sys.path.insert(0, "/home/user/gold-orb/lab")
from pivbb.tracks.run.harness import trial
O2 = ["D_R2", "D_S2"]; O4 = ["D_R2", "D_S2", "D_R3", "D_S3"]
for tag, prm in [("G1 R2/S2/R3/S3", dict(levels=O4)), ("G2 R2/S2 02-12", dict(levels=O2, hours=[2, 12])), ("G3 R2/S2 no target", dict(levels=O2, target=None)),
                 ("G4 R2-3/S2-3 02-12 no target", dict(levels=O4, hours=[2, 12], target=None)), ("G5 R2/S2 touch market", dict(levels=O2, entry="touch"))]:
    trial(tag, prm)
