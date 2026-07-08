#!/usr/bin/env python3
"""Dump all HAR entries"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

har_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "har", "10.111.36.3.har")
with open(har_path, "r", encoding="utf-8") as f:
    har = json.load(f)

entries = har["log"]["entries"]
for i, entry in enumerate(entries):
    req = entry["request"]
    resp = entry["response"]
    print(f"[{i}] {req['method']} {req['url']} -> {resp['status']} ({resp['content'].get('size', 0)} bytes)")

    # Show postData if any
    if req['method'] == 'POST':
        pd = req.get('postData', {})
        text = pd.get('text', '')
        # Just show the field names
        from urllib.parse import parse_qs
        params = parse_qs(text)
        print(f"    Fields: {list(params.keys())}")

        # Show unplannedInfo value specifically
        if 'unplannedInfo' in params:
            val = params['unplannedInfo'][0]
            print(f"    unplannedInfo ({len(val)} chars):")
            print(f"    {val}")

        # Show AJAXREQUEST if present
        if 'AJAXREQUEST' in params:
            print(f"    AJAXREQUEST: {params['AJAXREQUEST'][0]}")

    print()
