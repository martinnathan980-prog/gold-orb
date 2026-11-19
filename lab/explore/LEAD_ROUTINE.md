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

## The next batch (written 2026-11-19 evening for 2026-11-20, after the user's new instruction)
**The user's instruction of 2026-11-19 evening (it replaces the plan written that afternoon):** only markets that
trade almost round the clock and move all the time (gold, euro-dollar, oil ...), with price rules: sudden shocks,
existing indicators, new indicators, mixes of indicators. No shares, no exotic data. The demo is for later: do not
bring it up. Credit: about 10 % of the weekly allowance a day at most (he was at 80 % on Thursday evening; it renews
on Saturday 00:00 Paris), so keep the lead's own steps few and add no review beyond what the scripts hold.
The plan is `lab/explore/lead/DIRECTION4.md` (a pre-registered SCAN of about 1,390 rules on 15 markets, in three
stages), not eight hand-written ideas. On 2026-11-20:
1. Bring `<scratchpad>/explore_wt` to the pushed head; run the kit's self-test (`231/231`).
2. Launch together: (a) idea 064, `Workflow({scriptPath: "<scratchpad>/wf/ideas4.js", args: {selftest: "...",
   ideas: [{num: "064", slug: "coinbase_premium_long_btc_eth", row: "IDEAS.md"}]}})`; (b) the scan's build,
   `Workflow({scriptPath: "<scratchpad>/wf/scan_build.js", args: {selftest: "..."}})` (copies in git:
   `lead/batch_ideas.js`, `lead/batch_scan_build.js`): a builder writes `lab/explore/scan/` on synthetic bars only,
   a verifier attacks it, at most two rounds of repair.
3. When the build is verified: copy `scan/` from the worktree into the main checkout, read `GRAMMAR.md` and the
   verifier's last report, commit the code WITH `scan/rules.csv` and its sha256 (the grammar is frozen by that
   commit), push. Only then start the real scan, detached: `bash lab/explore/scan/run_all.sh` (discovery on bars
   before 2019, selection, confirmation on 2019-2021, report; it resumes after a restart; it costs no credit).
4. Merge 064 as usual (re-run, ledger, status; if it passes: its two conditions, then the look with the extra bar).
5. When the scan has finished: commit its summaries (`discovery_summary.json`, `frozen_candidates.json`,
   `confirmation.json`), one ledger line (running total + the number of rule-unit cells), and write on the sheet, in
   plain French: how many rules, how many candidates, how many confirmed, which. Each confirmed candidate becomes an
   idea (number, row in IDEAS.md, declaration) and goes through the ordinary protocol on the following days.
The scout's remaining ideas (outside data) are set aside by the user's instruction: see the note at the top of
IDEAS.md. What the archives already hold on these markets: `lead/archive_map_2026-11-19.json`.
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
