#!/usr/bin/env python3
"""Extract full POST data from entity.jsf saveLog and compare with our encoding"""
import json, os, sys
from urllib.parse import parse_qs, unquote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

har_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "har", "10.111.36.3.har")
with open(har_path, "r", encoding="utf-8") as f:
    har = json.load(f)

entries = har["log"]["entries"]

# Entry #3: entity.jsf save
entry = entries[3]
req = entry["request"]
resp = entry["response"]

print("=== REQUEST ===")
print(f"URL: {req['url']}")
print(f"Method: {req['method']}")
print(f"\nHeaders:")
for h in req["headers"]:
    print(f"  {h['name']}: {h['value']}")

print(f"\n=== POST DATA (raw) ===")
pd = req.get("postData", {})
text = pd.get("text", "")
print(f"Length: {len(text)}")
print(text[:3000])

print(f"\n\n=== POST FIELDS (decoded) ===")
params = parse_qs(text)
for k in sorted(params.keys()):
    val = params[k][0]
    if k == "unplannedInfo":
        print(f"  {k} ({len(val)} chars):")
        # Show with visible separators
        print(f"    {val}")
        # Also show each S3-separated row
        S3 = "#-%#!#-@-#@"
        rows = val.split(S3)
        print(f"    Rows: {len(rows)}")
        for ri, row in enumerate(rows):
            if row.strip():
                print(f"    Row {ri}: {row[:200]}")
    elif len(val) > 200:
        print(f"  {k}: <{len(val)} chars> {val[:150]}...")
    else:
        print(f"  {k}: {val}")

# Response
print(f"\n=== RESPONSE ===")
print(f"Status: {resp['status']}")
print(f"Content-Type: {resp['content'].get('mimeType', '?')}")
ct = resp['content'].get('text', '')
print(f"Body length: {len(ct)}")
print(ct[:2000])

# Also extract DWR call for taskWorkDays
print(f"\n\n=== DWR: dynGetTaskWorkDays (Entry #0) ===")
e0 = entries[0]
pd0 = e0["request"].get("postData", {})
print(f"URL: {e0['request']['url']}")
print(f"Data: {pd0.get('text', '')}")
print(f"Response ({e0['response']['status']}):", e0["response"]["content"].get("text", "")[:500])
