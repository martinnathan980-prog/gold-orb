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

## The search is paused (2026-11-20 evening): read this before doing anything
**Why.** On 2026-11-20 the scan of `lead/DIRECTION4.md` confirmed nothing (1,388 rules, 15 markets, 2 candidates, 0
confirmed) and its only two follow-ups, ideas 065 and 066, lost on the fresh years 2019-2021 the same evening. The
week's tally: 37 ideas (30 tested, 7 set aside) plus the scan, nothing found; no rule has been kept since round 2
(2026-11-10); the ledger's running total is 29,081. The user then asked for the plain truth ("if we are chasing an
illusion, be honest"). The lead's answer, checked by two independent readings of the repository (a skeptic and a
realist, 2026-11-20):
- More search for price rules is not worth his credit: before costs the scan's rules are distributed as chance, so
  there is nothing for more time, computing power or history to amplify.
- His earlier demand (about +100 % a month) needs about 0.35 R a trade against the robot's 0.08 (PROTOCOL_V3,
  Addendum G): out of reach.
- The robot is neither an illusion nor proven: +428.6 R on 5,400 trades in 2022-2025, four years of four, but the
  rules come from about 2,500 tries, the edge per trade shrank by about 40 % from in sample to validation (65 to 80 %
  on the crypto breakouts), six rules of ten have a validation t under 1.5, costs are a model and no real trade
  exists. Both readings put the chance of a real edge after real costs near one in two (35-55 % and 45-60 %), at a
  quarter to a half of the paper figures if it is real.
- The stake matters most: the S7 plan of the demo guide (7 % a trade at the start, no guard) halves the account
  within three years in 49 / 75 / 82 / 90 % of the lab's simulated paths (paper / half / quarter / zero edge);
  F3S (3 % with stop and guard) in 0.7 / 2.5 / 4.3 / 7.4 % (`lab/results/r2/stake/scaled_summary.json`).
**What was done.** The daily lead trigger is DISABLED (re-enable it only on the user's word). Nothing else changed.
**What is proposed to the user, and is his to decide (do none of it without his word):** (1) the stake plan (F3S
instead of S7) before any real money; (2) the one look at 2026 on the frozen ten-rule robot, with its reading written
first (PROTOCOL_V2: under PF 1.0 against, 1.0 to 1.3 weak, 1.3 or more strong; gold 2026 to 5 November was already
seen for D4H and ORX); (3) the demo, when he has time, read for fills and costs, not for profit. Do not push the demo.
**The survey of commercial robots (2026-11-20 evening and 21 morning, at the user's request).** About 75 web researches and
adversarial checks, the whole public MQL5 signal catalogue (3,794 real signals screened by a read-only script), 297
Darwinex strategies, 348 robots of the MQL5 Market. Outcome: no robot is "sure"; what shows explosive gains is nearly
always a grid or a martingale; what stands is two Darwinex strategies (SYO, SUG: about 11 to 14 % a year net over 8
to 10 years), trend-following funds, and a handful of gold breakout robots with stops (Gold Trade Pro, SteadyRock,
Dudu, Gold Reaper), proven on 2 to 4 years of a gold rally: the same family as the robot's own gold rules. The
result is the user's private page "Robots à l'épreuve" (its link is not kept in this public repository); the raw
notes are in `~/explore_data/robots_survey/` (out of git: they name third-party sellers). Sites that refuse automatic
access (Myfxbook, FP Markets' site, FOLLOWME) were not read and must not be worked around.
**If the user asks for the search to resume:** take only an idea that brings a new kind of information, with a
written reason why an effect larger than twice its cost should be there; no second scan of price rules; no other
follow-up of the scan. The scout's remaining ideas (outside data) stay set aside by his instruction of 2026-11-19.

## Rules that do not move
- In sample to 2021-12-31; one declared, logged look at 2022-2025 per finalist; never 2026.
- Never edit `lab/robot`, `lab/live_ai`, earlier rounds' files. No market data, secrets or personal data in git.
- Honest wording on the sheet: "Oui" only for an idea that passed in sample AND on the validation years AND was
  verified by the lead. A near miss is "Non".
- Credit: the user set the pace on 2026-11-19: about 10 % of his weekly allowance a day, never more than that day's
  work (this session on Fable 5.2, agents on Opus or Sonnet). If he reports his credit is short, slow down first,
  ask second.
- The scheduled worker runs (launcher trigger) are paused while this routine runs the daily batch.
