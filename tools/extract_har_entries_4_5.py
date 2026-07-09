#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Extract FULL entries 4 and 5 from the HAR file and dump ALL details."""

import json
import sys

HAR_PATH = r"D:\code\gongshi\tools\har\10.111.36.3.har"
OUTPUT_PATH = r"D:\code\gongshi\tools\har_entries_4_5_full.txt"


def format_entry(entry, index, out_lines):
    """Dump every field of a HAR entry with zero filtering."""
    sep = "=" * 80
    out_lines.append(sep)
    out_lines.append(f"ENTRY {index}")
    out_lines.append(sep)

    # --- Request ---
    request = entry.get("request", {})
    out_lines.append(f"")
    out_lines.append(f"--- REQUEST URL ---")
    out_lines.append(f"  Method:  {request.get('method', 'N/A')}")
    out_lines.append(f"  URL:     {request.get('url', 'N/A')}")
    out_lines.append(f"  HTTP Version: {request.get('httpVersion', 'N/A')}")
    out_lines.append(f"  Headers Size: {request.get('headersSize', 'N/A')}")
    out_lines.append(f"  Body Size:    {request.get('bodySize', 'N/A')}")

    out_lines.append(f"")
    out_lines.append(f"--- REQUEST HEADERS (all) ---")
    for h in request.get("headers", []):
        out_lines.append(f"  {h['name']}: {h['value']}")

    # Query string
    qs = request.get("queryString", [])
    if qs:
        out_lines.append(f"")
        out_lines.append(f"--- REQUEST QUERY STRING ---")
        for q in qs:
            out_lines.append(f"  {q['name']} = {q['value']}")

    # Cookies sent
    cookies = request.get("cookies", [])
    if cookies:
        out_lines.append(f"")
        out_lines.append(f"--- REQUEST COOKIES ---")
        for c in cookies:
            out_lines.append(f"  {c['name']} = {c['value']}")

    # POST data (full body)
    post_data = request.get("postData", {})
    if post_data:
        out_lines.append(f"")
        out_lines.append(f"--- POST DATA ---")
        out_lines.append(f"  Mime Type: {post_data.get('mimeType', 'N/A')}")
        out_lines.append(f"  Text (full body):")
        out_lines.append(json.dumps(post_data.get("text", ""), indent=2, ensure_ascii=False))

        params = post_data.get("params", [])
        if params:
            out_lines.append(f"  Params ({len(params)} total):")
            for i_p, p in enumerate(params):
                out_lines.append(f"    [{i_p}] {p.get('name', '?')} = {p.get('value', '')}")

    # --- Response ---
    response = entry.get("response", {})
    out_lines.append(f"")
    out_lines.append(f"--- RESPONSE ---")
    out_lines.append(f"  Status:       {response.get('status', 'N/A')}")
    out_lines.append(f"  Status Text:  {response.get('statusText', 'N/A')}")
    out_lines.append(f"  HTTP Version: {response.get('httpVersion', 'N/A')}")
    out_lines.append(f"  Headers Size: {response.get('headersSize', 'N/A')}")
    out_lines.append(f"  Body Size:    {response.get('bodySize', 'N/A')}")
    out_lines.append(f"  Redirect URL: {response.get('redirectURL', 'N/A')}")

    out_lines.append(f"")
    out_lines.append(f"--- RESPONSE HEADERS (all) ---")
    for h in response.get("headers", []):
        out_lines.append(f"  {h['name']}: {h['value']}")

    # Response body (complete)
    content = response.get("content", {})
    if content:
        out_lines.append(f"")
        out_lines.append(f"--- RESPONSE CONTENT ---")
        out_lines.append(f"  Size:       {content.get('size', 'N/A')}")
        out_lines.append(f"  Compression: {content.get('compression', 'N/A')}")
        out_lines.append(f"  Mime Type:   {content.get('mimeType', 'N/A')}")
        encoding = content.get("encoding", "")
        out_lines.append(f"  Encoding:    {encoding}")
        text = content.get("text", "")
        if not text:
            out_lines.append(f"  Text: (empty or binary, {len(text)} chars)")
        else:
            out_lines.append(f"  Text length: {len(text)} characters")
            out_lines.append(f"  Text (full, no truncation):")
            out_lines.append("--- BEGIN RESPONSE BODY ---")
            out_lines.append(text)
            out_lines.append("--- END RESPONSE BODY ---")

    # --- Timing / misc fields ---
    out_lines.append(f"")
    out_lines.append(f"--- OTHER ENTRY FIELDS ---")
    for key in sorted(entry.keys()):
        if key in ("request", "response"):
            continue
        val = entry[key]
        if isinstance(val, (dict, list)):
            out_lines.append(f"  {key}: (JSON) {json.dumps(val, indent=4, ensure_ascii=False)}")
        else:
            out_lines.append(f"  {key}: {val}")

    out_lines.append(f"")


def main():
    print(f"Loading HAR: {HAR_PATH}", file=sys.stderr)
    with open(HAR_PATH, "r", encoding="utf-8") as f:
        har = json.load(f)

    entries = har.get("log", {}).get("entries", [])
    print(f"Total entries in HAR: {len(entries)}", file=sys.stderr)

    out_lines = []
    out_lines.append("COMPLETE DUMP OF HAR ENTRIES 4 AND 5 (0-indexed)")
    out_lines.append(f"HAR file: {HAR_PATH}")
    out_lines.append(f"Total entries: {len(entries)}")
    out_lines.append("")
    out_lines.append("These are the A4J AJAX POST requests to myTask.jsf.")
    out_lines.append("NOTHING is filtered, truncated, or omitted.")
    out_lines.append("")

    for idx in (4, 5):
        if idx >= len(entries):
            print(f"WARNING: Entry {idx} does not exist (only {len(entries)} entries)", file=sys.stderr)
            out_lines.append(f"ENTRY {idx}: DOES NOT EXIST (only {len(entries)} entries total)")
            out_lines.append("")
            continue
        format_entry(entries[idx], idx, out_lines)

    output = "\n".join(out_lines)
    print(f"Writing {len(output)} chars to: {OUTPUT_PATH}", file=sys.stderr)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(output)

    print("[OK] Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
