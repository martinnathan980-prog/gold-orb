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

## The next batch (written 2026-11-19 for the batch of 2026-11-20)
`Workflow({scriptPath: "<scratchpad>/wf/ideas4.js", args: {selftest: "<N/N checks passed, from today's run>", ideas: [
{num: "064", slug: "coinbase_premium_long_btc_eth", row: "IDEAS.md"},
{num: "029", slug: "round_numbers_fx", scout: 15}, {num: "047", slug: "gold_option_expiry", scout: 33},
{num: "046", slug: "treasury_settlement_days", scout: 32}, {num: "045", slug: "rate_gaps_fx", scout: 31},
{num: "033", slug: "dix_long_sp", scout: 19}, {num: "034", slug: "btc_fee_spike", scout: 20},
{num: "044", slug: "btc_active_addresses", scout: 30}]}})`
after bringing `<scratchpad>/explore_wt` to the pushed head. The script's copy in git is `lab/explore/lead/batch_ideas.js`
(kit v2.3 wording): if the scratchpad was lost, copy it back to `<scratchpad>/wf/ideas4.js`.
Direction 3 (US shares around results and news) is closed: the ledger's note of 2026-11-19 says why. Idea 064 is the
one lead of the batch of 2026-11-19 that stood against the same-year null (021's buying side): its row in IDEAS.md is
the full brief, with the two conditions on any validation look; if it passes in sample, re-run it, read its attack,
check condition (1) on the ether leg, and only then declare the look (condition 2). The other seven come
from the scout's queue, on the markets that are cheap to trade (currencies, gold, indices, bitcoin); each needs outside
data the scout checked (`scout/sources.md`), and an idea agent closes its idea as blocked or insufficient when a source
refuses or the count is short. Every run now also gives the same-year null (kit v2.3, information); before any
validation look read the charter's paragraph "Rules on one side, signals bunched in time".
What the queue still holds after this batch: 024 and 041 (Wikipedia: one request every 10 seconds at most), 027, 032,
037, 049, 035; and 003, 004, 006, 012, 013, 014, which have only a sketch in IDEAS.md (write a full brief first). 007 and 008
need traded volume and ask prices the local bars do not have. The nature ideas (028, 031, 039, 040, 050) stay aside.
When the queue is done the next direction is the lead's to choose (the user gave free rein on 2026-11-18): start from
what the failures have in common (short holds die on costs; one-sided rules ride a market's drift; shares cost too
much) and from where the ten rules came from (intraday momentum and breakouts on cheap, liquid markets).
Delete this section once the batch is merged and write the next one.

## Rules that do not move
- In sample to 2021-12-31; one declared, logged look at 2022-2025 per finalist; never 2026.
- Never edit `lab/robot`, `lab/live_ai`, earlier rounds' files. No market data, secrets or personal data in git.
- Honest wording on the sheet: "Oui" only for an idea that passed in sample AND on the validation years AND was
  verified by the lead. A near miss is "Non".
- Credit: the user set the pace (8 ideas a day, this session on Fable 5.2, idea agents on Opus). If he reports his
  weekly credit is short, slow down first, ask second.
- The scheduled worker runs (launcher trigger) are paused while this routine runs the daily batch.
