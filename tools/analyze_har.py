#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Extract A4J/AJAX POST requests from HAR files and dump to output file."""

import base64
import json
import os

OUTPUT = r"D:\code\gongshi\tools\har_analysis_output.txt"

HAR_FILES = [
    r"D:\code\gongshi\tools\har\执行日报.har",
    r"D:\code\gongshi\tools\har\任务列表.har",
]

# Headers worth highlighting
KEY_HEADERS = {
    "content-type", "faces-request", "accept", "referer", "origin",
    "x-requested-with", "cookie", "user-agent", "content-length",
    "ajax-request", "dwr-window", "dwr-batchid",
}


def header_value(headers, name):
    """Case-insensitive header lookup."""
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return "(not present)"


def decode_response_body(content):
    """Decode response body from HAR content dict.
    Returns (body_text, encoding_note).
    """
    body_text = content.get("text", "")
    body_encoding = content.get("encoding")
    body_size = content.get("size", 0)

    if not body_text:
        return "(empty or not captured)", f"encoding={body_encoding}, size={body_size}"

    if body_encoding == "base64":
        # Fix base64 padding
        b64 = body_text.strip()
        missing = len(b64) % 4
        if missing:
            b64 += "=" * (4 - missing)
        try:
            decoded = base64.b64decode(b64).decode("utf-8", errors="replace")
            return decoded, f"encoding=base64 (decoded), size={body_size}"
        except Exception as e:
            # Try raw text fallback
            raw = body_text[:3000]
            return f"[base64 decode failed: {e}]\nRaw: {raw}", f"encoding=base64 (decode error), size={body_size}"
    elif body_encoding is None:
        # Raw text already decoded
        decoded = body_text[:3000]
        return decoded, f"encoding=None (raw text), size={body_size}"
    else:
        decoded = body_text[:3000]
        return decoded, f"encoding={body_encoding}, size={body_size}"


def format_post_data(req):
    """Extract POST fields (form-urlencoded or multipart or text/plain)."""
    post_data = req.get("postData", {})
    if not post_data:
        return "(no POST data)"

    mime = post_data.get("mimeType", "")
    text = post_data.get("text", "")
    params = post_data.get("params", [])

    if "urlencoded" in mime:
        lines = ["Post Data (urlencoded):\n"]
        if params:
            # Use structured params array (HAR spec)
            for p in params:
                name = p.get("name", "?")
                value = p.get("value", "")
                # Truncate long values like ViewState
                if len(value) > 200:
                    lines.append(f"  {name} = <{len(value)} chars, starts: {value[:100]}...>")
                else:
                    lines.append(f"  {name} = {value}")
        elif text:
            # Fallback: parse manually
            for pair in text.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    if len(v) > 200:
                        lines.append(f"  {k} = <{len(v)} chars>")
                    else:
                        lines.append(f"  {k} = {v}")
                else:
                    lines.append(f"  {pair}")
        return "\n".join(lines)

    elif "multipart" in mime:
        lines = ["Post Data (multipart):\n"]
        for p in params:
            name = p.get("name", "?")
            if "fileName" in p:
                lines.append(f"  {name} = <file: {p['fileName']}>")
            else:
                lines.append(f"  {name} = {p.get('value', '')}")
        return "\n".join(lines)

    elif "text/plain" in mime:
        # DWR-style: key=value per line
        lines = ["Post Data (text/plain):\n"]
        lines.append(text)
        return "\n".join(lines)

    else:
        return f"Post Data (mime={mime}): length={len(text)} bytes\n{text[:5000]}"


def is_ajax_request(entry):
    """Check if an entry is an A4J/AJAX request."""
    url = entry["request"]["url"]
    if "myTask.jsf" in url:
        return True

    # Check postData params for AJAXREQUEST field
    post_data = entry["request"].get("postData", {})
    for p in post_data.get("params", []):
        if p.get("name") == "AJAXREQUEST":
            return True

    # Check for AJAX-related headers
    for h in entry["request"].get("headers", []):
        name_lower = h["name"].lower()
        if name_lower in ("faces-request", "ajax-request"):
            val = h["value"].lower()
            if "partial/ajax" in val or val == "true":
                return True
    return False


def extract_entry(entry, index, label=""):
    """Format a single HAR entry."""
    req = entry["request"]
    resp = entry["response"]

    method = req["method"]
    url = req["url"]
    header_label = f"  {label} " if label else "  "

    lines = [
        f"{'=' * 100}",
        f"{header_label}Entry #{index}",
        f"{'=' * 100}",
        f"",
        f"URL:    {url}",
        f"Method: {method}",
        f"",
        "Request Headers (key):",
    ]

    for h in req["headers"]:
        name_lower = h["name"].lower()
        if name_lower in KEY_HEADERS:
            lines.append(f"  {h['name']}: {h['value']}")

    lines.append("")
    lines.append("All Request Headers:")
    for h in req["headers"]:
        lines.append(f"  {h['name']}: {h['value']}")

    lines.append("")

    if method == "POST":
        lines.append(format_post_data(req))
        lines.append("")

    # Response
    status = resp["status"]
    status_text = resp.get("statusText", "")
    resp_content_type = header_value(resp.get("headers", []), "content-type")
    lines.append(f"Response Status: {status} {status_text}")
    lines.append(f"Response Content-Type: {resp_content_type}")
    lines.append("")

    # Response body
    content = resp.get("content", {})
    body_decoded, encoding_note = decode_response_body(content)
    lines.append(f"Response body: {encoding_note}")

    if body_decoded != "(empty or not captured)":
        trunc_note = ""
        if len(body_decoded) > 3000:
            trunc_note = " [TRUNCATED]"
        lines.append(f"Response Body Preview (first {min(len(body_decoded), 3000)} chars){trunc_note}:")
        lines.append("-" * 60)
        lines.append(body_decoded[:3000])
    lines.append("")
    return "\n".join(lines)


def main():
    output_lines = []

    for har_path in HAR_FILES:
        fname = os.path.basename(har_path)
        output_lines.append(f"{'#' * 100}")
        output_lines.append(f"#  HAR File: {fname}")
        output_lines.append(f"{'#' * 100}")
        output_lines.append("")

        with open(har_path, "r", encoding="utf-8") as f:
            har = json.load(f)

        entries = har["log"]["entries"]
        output_lines.append(f"Total entries: {len(entries)}")
        output_lines.append("")

        # List all entries first
        output_lines.append("-" * 100)
        output_lines.append("ALL ENTRIES (summary):")
        output_lines.append("-" * 100)
        for i, e in enumerate(entries):
            req = e["request"]
            output_lines.append(f"  [{i}] {req['method']:4s} {req['url']}")
        output_lines.append("")

        # Find POST entries
        post_entries = [(i, e) for i, e in enumerate(entries) if e["request"]["method"] == "POST"]

        # Filter for A4J/AJAX-related
        ajax_entries = [(i, e) for i, e in post_entries if is_ajax_request(e)]
        non_ajax_posts = [(i, e) for i, e in post_entries if not is_ajax_request(e)]

        # Section 1: A4J/AJAX POST requests
        output_lines.append("-" * 100)
        output_lines.append(f"A4J/AJAX POST REQUESTS: ({len(ajax_entries)} found)")
        output_lines.append("-" * 100)
        output_lines.append("")

        if not ajax_entries:
            output_lines.append("  (none found matching A4J/AJAX criteria)")
            output_lines.append("")

        for idx, entry in ajax_entries:
            output_lines.append(extract_entry(entry, idx, label="[A4J/AJAX]"))
            output_lines.append("")

        # Section 2: Non-AJAX POST requests (DWR)
        output_lines.append("-" * 100)
        output_lines.append(f"OTHER POST REQUESTS (non-A4J, e.g., DWR): ({len(non_ajax_posts)} found)")
        output_lines.append("-" * 100)
        output_lines.append("")

        for idx, entry in non_ajax_posts:
            output_lines.append(extract_entry(entry, idx, label="[DWR/Other]"))
            output_lines.append("")

        output_lines.append("")

    # Write output
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print(f"[OK] Output written to: {OUTPUT}")
    print(f"     Size: {os.path.getsize(OUTPUT)} bytes")
    print(f"     Lines: {len(output_lines)}")


if __name__ == "__main__":
    main()
