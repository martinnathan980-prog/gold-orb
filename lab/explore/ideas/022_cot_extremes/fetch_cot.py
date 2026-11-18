"""Fetch the CFTC legacy futures-only COT rows (Socrata 6dca-aqww) of the 12 contracts, report dates 2009-01-01 to
2021-12-31 (the cut is in the query itself), cached to ~/explore_data/idea_016/cot_legacy.json. One request."""
import json, os, urllib.request, urllib.parse as up
CUT = "2021-12-31"
CODES = {"eurusd": "099741", "usdjpy": "097741", "gbpusd": "096742", "audusd": "232741", "usdcad": "090741",
         "usdchf": "092741", "nzdusd": "112741", "xauusd": "088691", "xagusd": "084691", "us500": "13874A",
         "us100": "209742", "us30": "124603"}
OUT = os.path.expanduser("~/explore_data/idea_016/cot_legacy.json")
if __name__ == "__main__":
    if os.path.exists(OUT):
        print("cached", OUT); raise SystemExit
    q = {"$select": "report_date_as_yyyy_mm_dd,cftc_contract_market_code,market_and_exchange_names,"
                    "noncomm_positions_long_all,noncomm_positions_short_all,open_interest_all", "$limit": "50000",
         "$where": "cftc_contract_market_code in (%s) AND report_date_as_yyyy_mm_dd >= '2009-01-01T00:00:00.000' AND "
                   "report_date_as_yyyy_mm_dd <= '%sT00:00:00.000'" % (",".join("'%s'" % c for c in CODES.values()), CUT),
         "$order": "report_date_as_yyyy_mm_dd"}
    url = "https://publicreporting.cftc.gov/resource/6dca-aqww.json?" + up.urlencode(q)
    raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-client/1.0"}), timeout=120).read()
    rows = json.loads(raw)
    assert max(r["report_date_as_yyyy_mm_dd"] for r in rows) <= CUT + "T23:59:59"
    json.dump(rows, open(OUT, "w"))
    print(len(rows), "rows")
