"""Runs the queued requests of the blind test where the API key lives.

The cloud session that develops this project cannot hold an Anthropic API key, so the calls are made by a
GitHub Actions job (.github/workflows/llm-blind-test.yml) that reads the key from the repository secret
ANTHROPIC_API_KEY. The key never appears in the repository, in the logs or in a chat.

A request is a small JSON file in lab/llm/requests/:
    {"cmd": "ping"}                                               one tiny call: is the key valid, are there credits?
    {"cmd": "run",    "name": "...", "period": "is", "per_sleeve": 12, "model": "...", "effort": "medium"}
    {"cmd": "probe",  "name": "...", "model": "..."}
    {"cmd": "submit", "name": "...", "period": "val", "per_sleeve": null, "model": "...", "effort": "medium"}
    {"cmd": "collect", "name": "...", "wait": true}
    {"cmd": "analyse", "name": "..."}
Each request runs once; its outcome is written next to it as <file>.done.json (status and the end of the output).
"""
import contextlib
import datetime
import glob
import io
import json
import os
import sys
import traceback

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LAB)
REQ = os.path.join(LAB, "llm", "requests")


def ping():
    from llm import judge
    msg = judge.client().messages.create(model="claude-haiku-5-5", max_tokens=512, output_config={"effort": "low"},
                                         messages=[{"role": "user", "content": "Reply with the single word: ready"}])
    text = next((b.text for b in msg.content if b.type == "text"), "")
    print(f"key accepted, credits available | model {msg.model} | answer: {text.strip()[:40]} | "
          f"tokens in {msg.usage.input_tokens} out {msg.usage.output_tokens}")


def execute(r):
    from llm import experiment as ex, judge
    cmd, name = r["cmd"], r.get("name")
    model, effort = r.get("model", judge.MODEL), r.get("effort", "medium")
    if cmd == "ping":
        ping()
    elif cmd == "run":
        ex.run(name, r.get("period", "is"), r.get("per_sleeve"), model, effort, workers=int(r.get("workers", 4)))
        ex.analyse(name)
    elif cmd == "probe":
        ex.probe(name, model)
    elif cmd == "submit":
        ex.submit(name, r.get("period", "val"), r.get("per_sleeve"), model, effort)
    elif cmd == "collect":
        ex.collect(name, bool(r.get("wait", True)))
    elif cmd == "analyse":
        ex.analyse(name)
    else:
        raise ValueError(f"unknown cmd {cmd}")


def main():
    todo = [p for p in sorted(glob.glob(os.path.join(REQ, "*.json"))) if not p.endswith(".done.json")
            and not os.path.exists(p[:-5] + ".done.json")]
    print(f"{len(todo)} request(s) to run")
    for p in todo:
        r = json.load(open(p))
        buf, status = io.StringIO(), "ok"
        try:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError("the repository secret ANTHROPIC_API_KEY is not set")
            with contextlib.redirect_stdout(buf):
                execute(r)
        except Exception as e:                                    # noqa: BLE001  (reported in the outcome file)
            status = "error"
            buf.write(f"\n{type(e).__name__}: {str(e)[:600]}\n")
            traceback.print_exc()
        out = buf.getvalue()
        print(f"--- {os.path.basename(p)}: {status}\n{out[-6000:]}", flush=True)
        json.dump({"request": r, "status": status, "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                   "output": out[-12000:]}, open(p[:-5] + ".done.json", "w"), indent=1)


if __name__ == "__main__":
    main()
