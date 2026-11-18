# The lead's daily routine (set on 2026-11-18 at the user's request)

The user asked for: **8 ideas a day**, and a **daily synthesis on one very simple sheet** (found or not, gain expected
or not, history, what is left to do, what not to redo), NOT in the conversation, where he gets lost. He gave the lead
a free hand on the direction ("you know my goal: make money on the markets"). A scheduled task wakes the lead's
session every day at 13:23 Paris with the instruction to follow this file. Keep your own steps few: the lead's turns
are the costly part; the idea agents are cheap.

## Every day
1. `cd /home/user/gold-orb && git pull --rebase origin lab`. Read the last lines of `lab/explore/LEDGER.md` and the
   statuses in `lab/explore/IDEAS.md` (and `lab/explore/lead/DIRECTION2.md` for the current plan).
2. Choose 8 ideas: the plan of DIRECTION2.md first, then the open ideas of IDEAS.md, varying the families. Count the
   ideas already handled today (ledger lines with today's date): 8 a day in all.
3. Bring the batch working copy to the pushed head (`git -C <scratchpad>/explore_wt checkout --detach <head>`, after
   `git clean -fdq lab/explore`), then launch the batch: `Workflow({scriptPath: "<scratchpad>/wf/ideas3.js", args:
   {ideas: [...], selftest: "<the self-test's last line>"}})`. Each entry: `{num, slug, row: "lead/DIRECTION2.md"}`
   (or `row: "IDEAS.md"`): the agent reads the table row that starts with `| <num> |` as its full brief, so write that
   row completely first (family, data, the exact rule, why, power); or `{num, slug, scout: k}` for
   a scout idea (row k of scout/ideas.md); `note` adds a remark. If the script is gone (the scratchpad was cleaned),
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
   Tell the user only what is verified.
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

## Rules that do not move
- In sample to 2021-12-31; one declared, logged look at 2022-2025 per finalist; never 2026.
- Never edit `lab/robot`, `lab/live_ai`, earlier rounds' files. No market data, secrets or personal data in git.
- Honest wording on the sheet: "Oui" only for an idea that passed in sample AND on the validation years AND was
  verified by the lead. A near miss is "Non".
- Credit: the user set the pace (8 ideas a day, this session on Fable 5.2, idea agents on Opus). If he reports his
  weekly credit is short, slow down first, ask second.
- The scheduled worker runs (launcher trigger) are paused while this routine runs the daily batch.
