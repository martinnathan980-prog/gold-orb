"""Stage C -- silver as an independent check: the five stage-B configurations that passed the basic
in-sample criteria on gold, run with the SAME parameters on xagusd (declared before running)."""
import json, os
from research import RES, run, n_configs
import stageB

C = ["B1_d1h_n240_k2", "B1_d1h_n240_k3", "B1_d1h_n120_k3", "B3_d1h_n48_tr240_k2", "B5_sq1h_n24_07"]
if __name__ == "__main__":
    pth = os.path.join(RES, "plan_stageC.json")
    if not os.path.exists(pth):
        json.dump({"stage": "C-silver-replication", "declared_before_running": True, "sym": "xagusd", "configs": C}, open(pth, "w"), indent=1)
    for k in C:
        run(k, "C-silver", "xagusd", stageB.B[k], full=True)
    print("configurations so far:", n_configs())
