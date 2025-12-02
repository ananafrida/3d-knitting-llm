"""
txt_to_json_string.py for creating single-line strings that can be copy-pasted into instructions full text in the schema

Usage:
python txt_to_json_string.py full_text.txt -o json_text.txt
"""

import argparse
import sys
import json
from pathlib import Path

def escape_for_json_value(s: str) -> str:
    # Escape backslashes and double quotes, and convert newlines to \n so the result
    # can be safely placed as the value of a JSON string (without outer quotes).
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    s = s.replace("\r", "\\r")
    s = s.replace("\n", "\\n")
    return s

def main():
    p = argparse.ArgumentParser(description="Convert a text file into a single-line JSON-safe string (with \\n for newlines).")
    p.add_argument("input", type=Path, help="Input text file")
    p.add_argument("-o", "--output", type=Path, help="Write output to file (otherwise prints to stdout)")
    p.add_argument("--json", action="store_true", help="Wrap output as a JSON quoted string (includes surrounding quotes and proper escapes)")
    args = p.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} does not exist.", file=sys.stderr)
        sys.exit(2)

    text = args.input.read_text(encoding="utf-8")
    if args.json:
        # Use json.dumps to produce a correct JSON-quoted string (includes surrounding quotes).
        out = json.dumps(text, ensure_ascii=False)
    else:
        # Produce the escaped content without surrounding quotes (e.g., as used in your JSON file's value)
        out = escape_for_json_value(text)

    if args.output:
        args.output.write_text(out, encoding="utf-8")
    else:
        print(out)

if __name__ == "__main__":
    main()