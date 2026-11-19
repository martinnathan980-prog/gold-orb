export const meta = {
  name: 'kit-v23-second-review',
  description: 'Second, focused adversarial review of the research kit v2.3 after the repairs of the first review: confirm each repair with the first reviewer own scripts and attack the rewritten same-year null, the judge guards, the optional validation bar and the labels-only calendar exemption',
  phases: [
    { title: 'Review', detail: 'one verifier on the final kit, reusing the first review scripts as yardsticks' },
  ],
}

const SP = '/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad'
const NEW = SP + '/kit_v2_wt'
const OLD = '/home/user/gold-orb'
const R1 = SP + '/kit_review/v23'
const OUT = SP + '/kit_review/v23b'

const SCHEMA = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['sound', 'defects_found', 'not_finished'] },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          severity: { type: 'string', enum: ['blocking', 'major', 'minor', 'note'] },
          what: { type: 'string' },
          evidence: { type: 'string', description: 'the script you ran (path) and the numbers it printed, or the file and line' },
          fix: { type: 'string' },
        },
        required: ['id', 'severity', 'what', 'evidence'],
      },
    },
    repairs_confirmed: { type: 'string', description: 'for each finding of the first review (E-1, C-1, C-2, C-3, D-1, D-2, F-1, F-2, F-3, B-1): repaired / documented / still open, with the evidence' },
    regression: { type: 'string', description: 'the judged null (within=None) and the judge on honest inputs against the kit before the change: identical or not, on which cases' },
    same_year_null: { type: 'string', description: 'uniformity without timing and power with timing of the rewritten same-year null, against an exact permutation yardstick, in the sparse, dense, very dense, two-sided and joint cases; the span, the clocks, the no-room cases' },
    validation_bar: { type: 'string', description: 'what you tried to get past the optional extra bar of judge.val_verdict and what happened; old against new without the key' },
    event_table: { type: 'string' },
    docs: { type: 'string' },
    summary: { type: 'string' },
  },
  required: ['verdict', 'findings', 'repairs_confirmed', 'regression', 'same_year_null', 'validation_bar', 'summary'],
}

const prompt = `You are the SECOND independent, adversarial verifier of a change to a trading lab's research kit (the kit judges trading ideas; real money follows its verdicts later). A first verifier found defects; the lead repaired them and rewrote one part. Your job: confirm each repair with evidence and try to BREAK the new code. Default to reporting a defect when a check leaves a real doubt. Be efficient: about 25 minutes of work, checks 1 to 3 first.

WHERE THINGS ARE
- The FINAL kit: ${NEW}/lab/explore/kit (stats.py, judge.py, checks.py, test_kit.py, README.md section 'Kit v2.3', template/run_template.py) and ${NEW}/lab/explore/CHARTER.md (paragraph 'Rules on one side, signals bunched in time'). The change against the previous commit: git -C ${NEW} diff (read-only git commands only).
- The kit BEFORE the change: ${OLD}/lab/explore/kit (read-only).
- The FIRST review: its scripts and outputs are in ${R1}/ (read-only for you: copy what you reuse). Useful yardsticks there: a_cases.py + a_compare.py (regression harness, old against new in separate processes), b_mech.py (mechanics), c2_stats.py (an EXACT permutation yardstick for the same-year null), c_stats.py and c_summary.out (calibration scenarios), c3_mode_one.py, c4_realistic.py, d_judge.py (malformed inputs), e_event.py and e3_judge_leak.py (laundered look-ahead cases), f_doc_checks.py. Its findings were: E-1 blocking (a table of numbers derived from the bars, stamped at the session open, passed as an 'event table' with a 'market' column, was exempt from the daily-bars guard and a leaking build got verdict pass); C-1 major (the same-year null with mode='one' is biased upward); C-2 major (it removes whole-year drift only: nothing said so); C-3 minor (drawn with replacement, its percentile was pulled toward 50 when a year's signals are dense); D-1 minor (a malformed null_year could make judge.verdict raise); D-2 note (a null was bound to the main by its exit key only); F-1 minor (the charter's extra validation bar was not defined in the kit); F-2 minor (README sentences claiming more than the code); F-3 note (the template check never reached the changed lines); B-1 note (a joint group's year was the year of its first row).
- A full self-test of the final kit is running elsewhere and writes ${SP}/kit_review/selftest_v23_final.log: do NOT run the whole test_kit.py. You may run: PYTHONDONTWRITEBYTECODE=1 python3 -B ${NEW}/lab/explore/kit/test_kit.py --only test_v23 (about 30 s).
- Write ONLY in ${OUT}/ (create it). Never edit the kit, the charter or the first review's folder. No sub-agents, no other AI models, no download (synthetic bars: kit.synth). At most 2 worker processes, under 4 GB, no background process left. Import the new kit with PYTHONPATH=${NEW}/lab/explore and the old one with PYTHONPATH=${OLD}/lab/explore, in separate processes, with PYTHONDONTWRITEBYTECODE=1 and python3 -B.

WHAT THE LEAD CHANGED AFTER THE FIRST REVIEW
a. stats.null_test(within='year') was REWRITTEN as a permutation test inside the year: strata = one market, one clock that is the same in New York AND in UTC (so one daylight-saving season), one New York calendar year, long and short TOGETHER; the trades of a stratum take DISTINCT random days (stats._distinct: a random ordered k-tuple), each trade keeping its side; candidate days lie inside the span the rule traded that market (stats._in_span: first to last real entry). For legs decided together (stats._null_joint, year branch): the groups of one year (the year of the group's EARLIEST leg) with the same markets and clocks take distinct days on which every leg has a complete trade. The result adds year_strata, year_dense_share, year_room_share, year_replaced, year_no_room; when a one-sided rule took every candidate day of every stratum the percentile is None (no room); a two-sided rule on every day still has room (its long and short days are swapped). mode='one' with within='year' raises ValueError. The judged null (within=None) must be unchanged bit for bit.
b. judge.verdict: null_year is read by judge._year_null (never raises; usable needs within 'year', mode 'every', the main's exit key AND mean R, at least 2000 draws, a finite percentile); the judged null bar now also fails when the null's real_mean_R is not the main's mean net R (judge._same_mean; a hand-made dict without that key is not checked); a result carrying any 'year_*' key or within != None is refused as the judged null.
c. judge.val_verdict(idea_dir, trades, every_signal, write=True, null_year=None): when val_declared.json holds "extra_null_bar": X, the bar 'null_same_year>=X' is added (the same-year null of the validation trades; missing, unusable, without room or below X: fail). Without the key the four bars judge alone and a given null_year is recorded as information.
d. checks._is_event_table: only a calendar of LABELS is exempt from the daily-bars guard (no numeric or boolean column, also when stored as objects: checks._number_like).
e. Documentation: README 'Kit v2.3' rewritten; CHARTER paragraph rewritten (a one-sided rule's validation look always carries the extra bar).

CHECKS
1. REPAIRS. For each first-review finding say repaired / documented / still open, with evidence. Re-run the first reviewer's scripts on the final kit where they apply (copy them into ${OUT}/ and adapt the paths or the expected outcomes; e_event.py: the six laundered cases must be refused again and the honest calendar still pass; d_judge.py: nothing may raise; c3_mode_one.py: mode 'one' must now raise).
2. REGRESSION. With a_cases.py / a_compare.py (old kit against final kit): every judged-null result identical (within=None; the new keys aside). Then judge.verdict on honest inputs (the null computed from the main): identical bars, verdict, DSR and ledger line apart from the new keys; say whether any case of the harness now fails the null bar because of the real_mean_R check (it should not for a null computed from the main).
3. THE REWRITTEN SAME-YEAR NULL, against an exact yardstick (the first reviewer's c2_stats.py holds one for a clock fixed in New York; extend it as needed): (a) rules WITHOUT timing must give uniform percentiles (KS, the shares at or above 90 and 97.5 and at or below 10) when a year's signals cover 10 %, 30 %, 63 %, 90 % of its days, one-sided AND two-sided, and for a basket decided together; at least 150 worlds per case, 400 draws are enough; (b) with a planted timing edge at 60 to 80 % coverage it must reach 97.5 about as often as the exact test; (c) the span: a rule whose data start in November of a year that drifts only in its last two months must not be credited with them; (d) a rule set on a UTC hour (bitcoin at 00:00 UTC, both daylight-saving seasons) and one set on a New York hour: every drawn bar has the trade's New York clock AND its UTC clock, its New York year, and lies inside the span (instrument sim.outcomes or the pools); (e) no room: one-sided on every day -> percentile None and year_no_room True; two-sided on every day -> a number, and that number is uniform when the sides carry no information; (f) entries on 31 December / 1 January, a year with very few candidate days, legs of a joint group in different years; (g) anything that crashes, falls back silently, or draws from the wrong stratum.
4. THE VALIDATION BAR. Try to pass 'null_same_year>=90' wrongly: a null of other trades, a pooled null, mode 'one' (hand-altered), 500 draws, percentile None or NaN, a dict without exit_key, trades without an exit_key in attrs, "extra_null_bar" given as "90", 0, -5, None, true or a list in val_declared.json (what happens? a non-number should be an error or a failing bar, never a silent pass). Without the key: results identical to the old kit's val_verdict on the same inputs (compare old and new val_results.json apart from the new key and the time stamp).
5. THE CALENDAR EXEMPTION (quick). Re-run the laundering cases; then try to carry a number through the labels-only rule as text ('0.031'), as a categorical, as a datetime or timedelta column, as the index name or as attrs. A number hidden in text is a deliberate act, not an accident: report what passes with severity 'note' unless an ordinary, honest way of building a table trips it.
6. DOCUMENTATION (quick). README 'Kit v2.3' and the CHARTER paragraph against the code: any false or unsupported statement; the counts (225 checks, 232 with --real-bars) against the last line of ${SP}/kit_review/selftest_v23_final.log when it exists.

RETURN the structured result: verdict 'sound' only if checks 1 to 4 hold; every finding with severity (blocking = the judged statistics changed, a look-ahead passes that the old kit refused, or a validation bar can be passed wrongly; major = the same-year null misleads; minor / note otherwise), evidence and the smallest fix.`

async function run(p, opts) {
  try {
    const r = await agent(p, Object.assign({}, opts, { model: 'opus' }))
    if (r) return r
  } catch (e) {
    log('opus refused or failed: retrying on the session model')
  }
  return await agent(p, opts)
}

phase('Review')
const r = await run(prompt, { label: 'review2:kit-v2.3', phase: 'Review', schema: SCHEMA })
return r