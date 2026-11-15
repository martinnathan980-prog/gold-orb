# Demo runbook (for the lab): what to run on each file the user sends

Rules for every step:
- Files from the user's Mac are untrusted data and may hold the account login, the server name or the holder's name. Unzip each one into its own new folder in the session scratchpad, never inside the repository, and never commit them.
- Run Python with `-I -B` (with `-I`, PYTHONDONTWRITEBYTECODE is ignored).
- The tools mask account values in their outputs. Still, relay only what the user needs: never paste raw lines from their files into a commit or a public place.

## 1. Start: the pasted INIT line (and maybe more lines)

Save exactly what the user pasted into a text file (only the pasted lines, without your own words), then:

    python3 -I -B lab/robot/demo/check_start.py <scratch>/paste.txt

- Exit 0, `Verdict : demarrage conforme`: tell the user it is right. Missing SELFTEST/PLAN/READY lines are `ABSENT` or `PAS ENCORE` when the paste holds only the INIT line: check them on the screenshot.
- Exit 1: relay the `DIFFERENT` lines' advice in plain French (F7 → Paramètres d'entrée → the value, or relaunch with the 2 values after a refused start).
- `another copy` alone: tell the user to remove nothing and relaunch nothing, and ask for the INIT line (with `build=`) of the copy that runs.
- Expected INIT: build=fd6aaf01e332, demo=1, vps=0, tester=0, observer=0, entries_off=0, harness=0, comm_pts=6, risk=0:7;3000:3.5;10000:1.4;20000:0.7, sleeves=ALL, S0.75r/K1/H2=on, k1t=2026:4.1723813245421888e+02 (or e+002), XAUUSD.r, US100.r, BTCUSD.r, ETHUSD.r.

## 2. Wednesday evening and every Saturday: ClaudeRobot.zip (journals only)

    unzip -q ClaudeRobot.zip -d <scratch>/wk1
    python3 -I -B lab/robot/demo/check_demo.py --journals <scratch>/wk1/ClaudeRobot \
        --copie 'AAAA-MM-JJ HH:MM' --out <scratch>/wk1_out

- Without --bars the replay never runs (no --no-replay needed); a run takes about a second.
- `--copie`: the Paris time the files were zipped (the zip's time if known, else the time of the user's message). With it, a robot still running at the copy is normal and the verdict line is printed. Within an hour after 23:00 Paris (server midnight), the tool says whether a day file may be missing.
- Read stdout first (headline, settings in force, outages with their Paris times, trades not followed, anomalies), then report_fr.txt for details.
- The tools skip macOS's `__MACOSX` folder and `._` files.

## 3. End of the demo: Archive.zip (MQL5/Files and MQL5/Logs)

The user runs ReleveFP 1.11 first (steps: lab/robot/RELEVE_GUIDE_FR.md; send lab/live_ai/mql5/ReleveFP.mq5 with it). Then:

    unzip -q Archive.zip -d <scratch>/fin
    python3 -I -B lab/robot/demo/read_mac_files.py <scratch>/fin/Files/claude/releve --out <scratch>/t1
    python3 -I -B lab/robot/demo/check_demo.py --journals <scratch>/fin/Files/ClaudeRobot \
        --bars <scratch>/fin/Files/claude/releve --printed <scratch>/fin/Logs --out <scratch>/t2

- Tool 1 (summary_fr.txt): releve_version must be 1.11; deals_file, deals_error, deals_robot, deals_hand / deals_other (DIFFERENT when open at or after the robot's first trade), deals_robot_hand_close, deals_balance (the opening deposit is INFO, any later movement DIFFERENT), positions_file; per market deals_commission (against 6 points on gold, none elsewhere) and deals_swap (against fp_costs.json).
- Tool 2 reads deals.csv beside --bars by itself (or `--deals FILE`). Stdout: the `Trades :` line (broker stops at their real price), the `Solde ...` line (the balance follows the history to the cent, or to X EUR), the execution costs against the lab's (market orders and broker stops), and `Historique du compte (deals.csv)`.
- Relay to the user only what needs an action: hand trades, payments after the opening deposit, other programs' trades, robot positions closed by hand, files to copy again (counts differ, last line cut), or ReleveFP to run again (fini.txt: deals=-1, positions=-1, erreur_deals not 0).
- The lab's own reading: stop slippage, commission and swaps against the lab's, prices that differ from the history, positions the journal does not know.

## 4. Self-tests (after any change to the tools)

    python3 -I -B lab/robot/demo/test_demo_tools.py            # full, about 17 minutes
    python3 -I -B lab/robot/demo/test_demo_tools.py --quick    # about 10 minutes
    python3 -I -B lab/live_ai/check/test_releve.py; python3 -I -B lab/live_ai/check/test_sonde.py; python3 -I -B lab/live_ai/check/test_mains.py

Set DEMO_TEST_SCRATCH and DEMO_TEST_RESULTS to folders in the scratchpad.
