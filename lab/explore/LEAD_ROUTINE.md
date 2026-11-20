# The lead's daily routine (set on 2026-11-18 at the user's request)

The user asked for: **8 ideas a day**, and a **daily synthesis on one very simple sheet** (found or not, gain expected
or not, history, what is left to do, what not to redo), NOT in the conversation, where he gets lost. He gave the lead
a free hand on the direction ("you know my goal: make money on the markets"). A scheduled task wakes the lead's
session every day at 13:23 Paris with the instruction to follow this file. Keep your own steps few: the lead's turns
are the costly part; the idea agents are cheap.

## Every day
(The scheduled task's own text still names `ideas2.js` and DIRECTION2.md: this file is what counts.)
0. If a batch already ran today (the lead sometimes starts it before the task fires: look at the ledger's last lines
   and at the task list), do NOT start another: answer in one line with the sheet's link.
1. `cd /home/user/gold-orb && git pull --rebase origin lab`. Read the last lines of `lab/explore/LEDGER.md` and the
   statuses in `lab/explore/IDEAS.md`, and the CURRENT plan: the section "The next batch" below (directions 2 and 3,
   `lead/DIRECTION2.md` and `lead/DIRECTION3.md`, are done: US shares around results and news closed on 2026-11-19).
2. Choose AT MOST 8 ideas (8 is the user's ceiling, not a quota: run what is worth running): the current plan first,
   then the open ideas of IDEAS.md, varying the families. Count the ideas already handled today (ledger lines with
   today's date): 8 a day in all. Before a new direction's first batch, its data and kit changes are built, attacked
   by an independent verifier and repaired first (as on 2026-11-18: three reviews of kit v2.1, one of the data).
3. Bring the batch working copy to the pushed head (`git -C <scratchpad>/explore_wt checkout --detach <head>`, after
   `git clean -fdq lab/explore`), then launch the batch: `Workflow({scriptPath: "<scratchpad>/wf/ideas4.js", args:
   {ideas: [...], selftest: "<the self-test's last line>"}})`. Each entry: `{num, slug, row: "IDEAS.md"}` (or a file
   under `lead/`): the agent reads the table row that starts with `| <num> |` as its full brief, so write that
   row completely first (family, data, the exact rule, why, power); or `{num, slug, scout: k}` for
   a scout idea (row k of scout/ideas.md; idea number = k + 14); or `{num, slug, custom: "<the full brief>"}`; `note`
   adds a remark. If the script is gone (the scratchpad was cleaned),
   copy it back from `lab/explore/lead/batch_ideas.js` (its paths name the scratchpad folders: recreate the worktree
   with `git worktree prune && git worktree add --detach <scratchpad>/explore_wt <head>`).
   The agents work in the worktree, use prepared bars in `~/explore_data/h1` (built from the lab's minute files by
   `lab/explore/lead/build_h1_from_lab.py`, in sample only) and the earnings calendar in `~/explore_data/earnings`
   (rebuilt by `lab/explore/scout/earnings_edgar.py build`), never run git and never take a validation look.
   **Before choosing an idea, check it against the lab's own record** (CHARTER "Families the lab already closed",
   `lab/results/r2/autopsy/breadth/summary.json` for the ten rules carried to other markets, `lab/results/r2/stocks`
   for the opening rules on shares): on 2026-11-18 two ideas the lead was about to add had already failed there.
4. When the batch reports: read each verdict; copy the idea folders into `lab/explore/ideas/`; for each judged idea
   `judge.ledger_add(<rows of trials.jsonl>, results["ledger_line"])` in idea order (0 configurations and a hand-written
   line for an idea closed before a run); set the statuses in IDEAS.md; commit; push.
5. **A pass** (`pass` or `pass, weak against selection`, attack done by the agent): re-run its `run.py` yourself and
   read its attack; then the single validation look, yours alone: build `~/explore_data/h1_val/<key>.parquet` for the
   needed markets (2022-2025 only, never 2026; `build_h1_from_lab.py` reads only before 2022, so write the
   validation variant with care), write `val_declared.json`, `data.unlock_val`, `judge.val_verdict`, once, logged.
   A rule with at least 80 % of its trades on one side (and any idea whose row says so) carries the charter's extra
   bar: `"extra_null_bar": 90` in `val_declared.json`, and `judge.val_verdict(..., null_year=stats.null_test(<the
   validation trades>, <their books>, n_draws=2000, within="year", <the frozen rule>))` (CHARTER "Rules on one side,
   signals bunched in time"). Tell the user only what is verified.
6. **Update the sheet** (the user's daily synthesis): edit `lab/explore/synthese/synthese.json` (one row per idea
   handled: `marche` Oui / Non / Pas testée, `gain` Oui / Non / —, `pourquoi` in one plain French sentence; the `jour`
   row: date and three short texts; the `afaire` rows: what comes next; the `stop` rows: what not to redo). Then
   upload it to the sheet's artifact as an asset and point the dataset at it:
   `Artifact(publish, url=<sheet>, file_path=.../synthese.json, asset=true)` gives `/_blob/<id>`; then
   `ArtifactData(get datasets/synthese)` for its version and `ArtifactData(update, collection "datasets", doc_id
   "synthese", data {source: {url: "/_blob/<id>"}, updated: {at: <UTC now>, by: "Claude"}}, if_version)`. The page
   itself (`lab/explore/synthese/page.html`, stored as `files/index.html`) changes only if the layout must.
   The sheet's link is in the scheduled task's text and in the session's task list (not in this public repository).
7. Final message in the conversation: three lines at most, in plain French, with the sheet's link. Everything else
   goes on the sheet.

## The next batch (written 2026-11-20 for 2026-11-21, after the scan)
**The user's standing instructions (2026-11-19 evening, still in force):** only markets that trade almost round the
clock and move all the time (gold, euro-dollar, oil ...), with price rules: sudden shocks, existing indicators, new
indicators, mixes of indicators. No shares, no exotic data. The demo is for later: do not bring it up. Credit: about
10 % of the weekly allowance a day AT MOST (the week renews on Saturday 00:00 Paris); keep the lead's own steps few.
**Where things stand:** the scan of `lead/DIRECTION4.md` ran on 2026-11-20 (1,388 rules, 15 markets): 2 candidates,
0 confirmed; before costs the whole grammar is what chance gives. Results: `scan/results/`, LEDGER.md note of
2026-11-20. Idea 064 failed. The scan allows exactly two follow-ups, both post hoc: ideas 065 and 066 (IDEAS.md).
On 2026-11-21:
1. Bring `<scratchpad>/explore_wt` to the pushed head (it must hold `lab/explore/scan/`); run the kit's self-test
   (`231/231`).
2. Launch the two ideas in one batch: `Workflow({scriptPath: "<scratchpad>/wf/ideas4.js", args: {selftest: "...",
   ideas: [{num: "065", slug: "indices_fade_hourly_shock", row: "IDEAS.md"}, {num: "066", slug:
   "fx_follow_h4_shock_with_trend", row: "IDEAS.md"}], note: "..."}})` (copy in git: `lead/batch_ideas.js`). The note
   must say: build the signals with the scan's own code (`scan.frames`, `scan.signals`, run with
   `PYTHONPATH=lab/explore`, never run a file of `scan/` as a script); first reproduce the scan's discovery row given
   in the idea's row; compute CONDITION 1 (the main's trades entered in 2019-2021 alone against DIRECTION4 section 5)
   and write `fresh_years.json`; take no validation look.
3. Re-run each `run.py`, check the reproduced discovery row and condition 1 yourself, merge (folder, ledger line with
   `judge.ledger_add`, IDEAS status, commit, push).
4. Only if an idea passes condition 1 AND the ordinary in-sample verdict: build its 2022-2025 hourly bars with care
   (`~/explore_data/h1_val/<key>.parquet`, 2022-2025 only, logged in `lab/results/val_access.log`), write
   `val_declared.json`, take the one look. A survivor on indices or currencies is then compared with the robot's ten
   rules (weekly correlation <= 0.30).
5. Write the sheet (the two rows, the day's row, what is left to do) and the three-line message.
6. If both fail: say so plainly on the sheet. The search on price rules has then covered textbook rules (the scan),
   the clock and the neighbours (rounds 1 to 6, `lead/archive_map_2026-11-19.json`) and this week's 35 ideas; do not
   start a second scan by reflex. Read the archive map first: a scan of clock rules and of rules built from two
   markets is worth pre-registering only for the markets the earlier rounds did not cover (the 8 pairs outside the
   fixings, oil, silver, the DAX), and only if the lead can name why an effect larger than twice its cost should be
   there. Otherwise tell the user that the search has reached its end at this level and propose to keep his credit.
The scout's remaining ideas (outside data) stay set aside by the user's instruction: see the top of IDEAS.md.
Delete this section once done and write the next one.

## Rules that do not move
- In sample to 2021-12-31; one declared, logged look at 2022-2025 per finalist; never 2026.
- Never edit `lab/robot`, `lab/live_ai`, earlier rounds' files. No market data, secrets or personal data in git.
- Honest wording on the sheet: "Oui" only for an idea that passed in sample AND on the validation years AND was
  verified by the lead. A near miss is "Non".
- Credit: the user set the pace on 2026-11-19: about 10 % of his weekly allowance a day, never more than that day's
  work (this session on Fable 5.2, agents on Opus or Sonnet). If he reports his credit is short, slow down first,
  ask second.
- The scheduled worker runs (launcher trigger) are paused while this routine runs the daily batch.
