# ClaudeRobot: acceptance of the shipped file (step K)

Step K checked the single file the user installs, `dist/ClaudeRobot.mq5`, against the lab on the in-sample data
(2013-2021, every read cut before 2022-01-01 inside the read call). The file is translated to C++ by `check/to_cpp.py`
and compiled with `g++ -std=c++17 -O2 -ffp-contract=off -Wall`, plus a sanitizer build
(`-fsanitize=address,undefined -D_GLIBCXX_DEBUG`). It runs in the replay mock (`check/mock_replay.h`), which imitates
MetaTrader 5 and a hedging broker. MetaEditor itself cannot run here: section 6 lists what only the user's Mac can check.

**Verdict.** ⟨pending: suite⟩

| File | CR_BUILD | Lines |
|---|---|---|
| `dist/ClaudeRobot.mq5` (what the user compiles) | `1ca53085c0c1` | 12,134 |
| `dist/ClaudeRobot_debug.mq5` (the same, plus `CR_DEBUG`: aggregate lines and a bar dump) | `0f6a32ec1ea3` | 12,135 |

Both are `tools/amalgam.py`'s output of the 24 files of `src/`, pure ASCII, each file inlined once; the only include
left is `<Trade\Trade.mqh>`.
