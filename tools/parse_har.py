#!/usr/bin/env python3
"""Extract saveLog POST request from HAR file"""
import json, os

har_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "har", "10.111.36.3.har")
with open(har_path, "r", encoding="utf-8") as f:
    har = json.load(f)

entries = har["log"]["entries"]
print(f"Total entries: {len(entries)}")

for i, entry in enumerate(entries):
    req = entry["request"]
    url = req["url"]
    method = req["method"]

    if "saveLog" in url or (method == "POST" and "workLogView" in url):
        print(f"\n{'='*80}")
        print(f"Entry #{i}: {method} {url}")
        print(f"Time: {entry.get('startedDateTime', '?')}")

        print(f"\n--- Request Headers ---")
        for h in req["headers"]:
            if h["name"].lower() not in ("cookie",):
                print(f"  {h['name']}: {h['value']}")

        if "postData" in req:
            pd = req["postData"]
            print(f"\n--- Post Data (mimeType: {pd.get('mimeType', '?')}) ---")
            text = pd.get("text", "")
            if len(text) > 5000:
                print(f"  [TRUNCATED - length: {len(text)}]")
                print(text[:5000])
            else:
                print(text)

        resp = entry["response"]
        print(f"\n--- Response ---")
        print(f"  Status: {resp['status']}")
        print(f"  Content-Type: {resp['content'].get('mimeType', '?')}")
        ct = resp['content'].get('text', '')
        if ct:
            preview = ct[:1000] if len(ct) > 1000 else ct
            print(f"  Body preview: {preview}")

        print(f"{'='*80}")
