"""Claude as the final go / no-go on a signal: the algorithm proposes, Claude decides.

One call per signal: system prompt = how to decide + the rule that fired and its measured statistics
(identical for every signal of a rule, so it is cached); user message = the context sheet (context.py).
The answer is a small JSON object: decision (take / skip), quality 0-100, one short reason in French.

Used the same way by the blind test on past signals (experiment.py) and, later, by the live robot.
The prompt is frozen: `prompt_hash()` is stored with every run.
"""
import hashlib
import json
import os

import anthropic

MODEL = "claude-opus-5-5"
MAX_TOKENS = 6000            # thinking counts toward it; the answer itself is ~80 tokens

SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["take", "skip"]},
        "quality": {"type": "integer"},
        "reason_fr": {"type": "string"},
    },
    "required": ["decision", "quality", "reason_fr"],
    "additionalProperties": False,
}

SYSTEM = """You are the final go / no-go decision-maker of an automated trading robot.

How the robot works
- Simple mechanical rules watch the markets. When a rule fires, the robot sends you one context sheet and waits for your decision before it places the order.
- The stop-loss, the position size and the exit are set by the rule and are not yours to change. Your only decision is: take this signal, or skip it.

What you are given
- The rule that fired and its measured statistics on past data (below). On average the rule makes a little money: most of its signals are ordinary, and a good part of them lose.
- A context sheet built only from prices known at the moment of the decision: the clock, today's session, key levels, trend and momentum, volatility and liquidity, and the recent bars on three time scales. Prices are expressed relative to the current price (in % or in basis points; ATR = average true range). The sheet deliberately contains no date and no news.

Your job
- Judge whether THIS signal, in THIS context, is better or worse than an ordinary signal of this rule, then decide.
- "skip" is for signals you judge clearly worse than ordinary. Skipping a good trade costs as much as taking a bad one. As a guide, a useful decision-maker skips roughly a quarter to a third of the signals; skipping almost none or almost all of them is useless.
- Use only what is in the sheet. Do not invent news or events.

Answer with the JSON object only:
- decision: "take" or "skip"
- quality: an integer from 0 to 100, your estimate of this signal against the rule's ordinary signals (50 = ordinary, 0 = among the worst, 100 = among the best)
- reason_fr: one short sentence in French (25 words at most) with the main reason"""

RULES = {
    "noise30": "Intraday trend-following on the Nasdaq-100 during the US cash session. Around the session's reference "
               "price (the 09:30 open and the previous 16:00 close) the rule draws a 'noise band': the average absolute "
               "move from the open at that time of day over the last 14 sessions. At each half-hour check from 10:00 to "
               "15:30 New York, if the price is outside the band, it enters in that direction. It exits when the price "
               "is back inside the band at a later half-hour check, at 15:55 New York at the latest, or on the stop "
               "(the centre of the band).",
    "ocm4": "Opening momentum on the Nasdaq-100. If the move of the first 4 minutes of the US cash session (09:30 to "
            "09:34 New York) is at least as large as the median opening move of the previous 20 sessions, it enters in "
            "that direction at 09:34. Stop 0.3 daily ATR. Exit at 15:55 New York at the latest.",
    "brk72_24h_wd": "Breakout on hourly closes. At the end of an hourly bar (Monday to Friday) it goes long when the "
                    "close is above the highest close of the previous 72 hourly bars, short when it is below the "
                    "lowest. Stop 3 hourly ATR. Exit 24 hours after the entry, or at the Friday close.",
    "nq_btc_follow": "Bitcoin follows a Nasdaq shock. During the US cash session, when the last 1-minute bar of the "
                     "Nasdaq-100 moved by at least 6 times its usual 1-minute move, it enters Bitcoin in the same "
                     "direction at the next minute. Stop about 1.2 to 1.5% of the price. Exit 60 minutes after the entry.",
    "F2_brk_unfiltered": "Hourly breakout during the European and US day (02:00 to 16:00 New York, Monday to Friday). "
                         "At an hourly close it goes long when the close is above the highest high of the previous 14 "
                         "session bars, short when it is below their lowest low. Stop 2 x the average hourly range. "
                         "Exit 13 hours after the decision, and at 15:55 New York the same day at the latest.",
    "GOLD_FRI_PM": "Friday afternoon in gold. Every Friday at 13:30 New York it buys with a limit order at the current "
                   "bid (valid 60 minutes). Stop 3 hourly ATR. Exit at 16:45 New York.",
    "donch4h_stop": "Channel breakout on 4-hour bars in gold. A buy-stop sits at the highest high and a sell-stop at "
                    "the lowest low of the last 60 four-hour bars (10 trading days); one of them has just been "
                    "triggered. Initial stop 2 x ATR(14) of the 4-hour bars, then a trailing stop at the same distance "
                    "from the best price. Exit after 5 trading days at the latest.",
    "orb_asia_2d_buf10": "Asian-range breakout in gold. The range is the high and low of 00:00 to 07:00 London. From "
                         "07:00 to 12:00 London a stop order sits beyond each side of the range (10% of its width "
                         "further out); one of them has just been triggered. Stop at the opposite order level. Exit at "
                         "16:00 New York two business days later.",
}

# USD per million tokens: input, output, cache read, 5-minute cache write (shared/models.md of the claude-api
# skill, 2026-11; cache write = 1.25 x input; the Haiku cache-read price is an assumption). Batch = half.
PRICES = {"claude-opus-5-5": (4.0, 20.0, 0.20, 5.0), "claude-sonnet-5-5": (2.0, 10.0, 0.10, 2.5),
          "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125), "claude-fable-5-2": (8.0, 40.0, 0.20, 10.0)}


def client():
    """API client. On the user's machine the key comes from ANTHROPIC_API_KEY; in the cloud session the network
    proxy injects the saved credential, so a placeholder is enough for the SDK to start."""
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY") or "injected-by-the-session-proxy", max_retries=4)


def rule_sheet(name, asset, st):
    side = lambda v: "none" if v is None else f"{v:+.3f} R on average"
    return (f"RULE THAT FIRED: {name} on {asset}\n{RULES[name]}\n"
            f"Measured on past data: {st['n']} trades, {st['win_rate'] * 100:.0f}% winners, average win "
            f"+{st['avg_win_R']:.2f} R, average loss {st['avg_loss_R']:.2f} R, average result {st['exp_R']:+.3f} R per trade "
            f"(R = the amount risked between entry and stop), median holding time {st['med_hold_h']:.1f} h. "
            f"Long trades: {side(st['long_exp_R'])}; short trades: {side(st['short_exp_R'])}.")


def system_blocks(name, asset, st):
    return [{"type": "text", "text": SYSTEM + "\n\n" + rule_sheet(name, asset, st), "cache_control": {"type": "ephemeral"}}]


def prompt_hash():
    return hashlib.sha256((SYSTEM + json.dumps(RULES, sort_keys=True) + json.dumps(SCHEMA, sort_keys=True)).encode()).hexdigest()[:12]


def request(model, system, sheet, effort):
    """Parameters of one Messages API call (same dict for a live call and for a batch entry)."""
    return dict(model=model, max_tokens=MAX_TOKENS, system=system, messages=[{"role": "user", "content": sheet}],
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}})


def parse(msg):
    """Message -> {decision, quality, reason_fr, stop_reason, usage}; decision is None when there is no usable answer."""
    u = msg.usage
    out = {"decision": None, "quality": None, "reason_fr": None, "stop_reason": msg.stop_reason, "model": msg.model,
           "usage": {"in": u.input_tokens, "out": u.output_tokens,
                     "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                     "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0}}
    if msg.stop_reason != "end_turn":             # refusal, max_tokens, ...: no decision
        return out
    text = next((b.text for b in msg.content if b.type == "text"), None)
    try:
        d = json.loads(text)
    except (TypeError, ValueError):
        return out
    if d.get("decision") in ("take", "skip"):
        out.update(decision=d["decision"], quality=int(min(100, max(0, d.get("quality", 50)))),
                   reason_fr=str(d.get("reason_fr", ""))[:300])
    return out


def decide(cl, model, system, sheet, effort="medium"):
    """One live decision. Network / API errors are raised to the caller (the robot then applies its default)."""
    return parse(cl.messages.create(**request(model, system, sheet, effort)))


def cost(usage, model, batch=False):
    """USD for one usage dict."""
    pi, po, pr, pw = PRICES[model]
    c = (usage["in"] * pi + usage["out"] * po + usage["cache_read"] * pr + usage["cache_write"] * pw) / 1e6
    return c * (0.5 if batch else 1.0)
