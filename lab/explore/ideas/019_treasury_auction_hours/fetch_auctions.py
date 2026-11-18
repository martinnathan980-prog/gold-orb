"""Fetch the Treasury note/bond auction calendar 2012-2021 (fiscaldata API, scout/sources.md 7) into the cache.
   python3 -I fetch_auctions.py ~/explore_data/idea_019/auctions_2012_2021.csv"""
import json, urllib.request, pandas as pd, sys
CUT="2021-12-31"
UA={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
def raw(url): return urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=60).read()
fields=("auction_date,announcemt_date,issue_date,security_type,security_term,reopening,inflation_index_security,floating_rate,"
        "offering_amt,closing_time_comp,cusip,original_security_term")
out,page=[],1
while True:
    url=("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
         f"?filter=auction_date:lte:{CUT},auction_date:gte:2012-01-01,security_type:in:(Note,Bond)&fields={fields}&sort=auction_date&page[size]=10000&page[number]={page}")
    j=json.loads(raw(url)); out+=j["data"]
    if page>=j["meta"]["total-pages"]: break
    page+=1
df=pd.DataFrame(out)
assert (pd.to_datetime(df.auction_date)<=CUT).all()
df.to_csv(sys.argv[1],index=False); print(len(df))
