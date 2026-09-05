#!/usr/bin/env python3
"""
pageflag.py

Goes through a list of URLs and checks whether a specific piece of HTML
(a literal snippet, or a regex pattern) is present on each page. Links
where the snippet is found can be flagged as "invalid" (the default),
or you can flip that logic with --invert so a match means "valid".

Designed to run on Linux (cron / systemd timer friendly), but works
anywhere Python 3 + requests run.

USAGE
-----
    # Basic: read URLs from a file, one per line
    ./pageflag.py -f urls.txt -s '<span class="select-none" data-new-page-greeting-text="">You're here!</span>'

    # URLs passed directly on the command line
    ./pageflag.py -u https://example.com https://example.org -s "some html"

    # Treat the snippet as a regex instead of a literal string
    ./pageflag.py -f urls.txt -s 'data-new-page-greeting-text="[^"]*"' --regex

    # Invert logic: presence of the snippet means the page IS valid
    ./pageflag.py -f urls.txt -s "og:site_name" --invert

    # Save results as CSV, use 20 concurrent workers, custom timeout
    ./pageflag.py -f urls.txt -s "You're here" -o results.csv --format csv -w 20 -t 15

    # By default, only VALID links are shown/written.
    # To see the invalid ones instead, or everything:
    ./pageflag.py -f urls.txt -s "You're here" --show invalid
    ./pageflag.py -f urls.txt -s "You're here" --show all

EXIT CODE
---------
    0  -> ran fine (even if some/all URLs came back invalid)
    1  -> ran fine, but at least one URL was invalid, and --fail-on-invalid was set
    2  -> bad usage / no URLs supplied

Dependencies: requests  (pip install requests --break-system-packages)
"""

import argparse
import concurrent.futures
import csv
import json
import re
import sys
from dataclasses import dataclass, asdict
from typing import Optional

try:
    import requests
except ImportError:
    print(
        "This script requires the 'requests' library.\n"
        "Install it with: pip install requests --break-system-packages",
        file=sys.stderr,
    )
    sys.exit(2)


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 link-checker/1.0"
)


@dataclass
class Result:
    url: str
    status_code: Optional[int]
    snippet_found: bool
    valid: bool
    error: Optional[str] = None

    def to_row(self):
        return asdict(self)


def load_urls(args) -> list:
    urls = []

    if args.urls_file:
        try:
            with open(args.urls_file, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        urls.append(line)
        except OSError as e:
            print(f"Could not read urls file '{args.urls_file}': {e}", file=sys.stderr)
            sys.exit(2)

    if args.urls:
        urls.extend(args.urls)

    # de-dupe while preserving order
    seen = set()
    deduped = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)

    return deduped


def check_url(url: str, pattern, use_regex: bool, invert: bool,
              timeout: int, user_agent: str, verify_ssl: bool) -> Result:
    headers = {"User-Agent": user_agent}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, verify=verify_ssl)
        html = resp.text

        if use_regex:
            found = pattern.search(html) is not None
        else:
            found = pattern in html

        # Default behavior: finding the snippet marks the page INVALID.
        # --invert flips that: finding the snippet marks it VALID.
        valid = (not found) if not invert else found

        return Result(
            url=url,
            status_code=resp.status_code,
            snippet_found=found,
            valid=valid,
        )

    except requests.exceptions.RequestException as e:
        # Can't fetch it at all -> treat as invalid, and say why.
        return Result(
            url=url,
            status_code=None,
            snippet_found=False,
            valid=False,
            error=str(e),
        )


def write_output(results, args):
    if args.format == "csv":
        target = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout
        writer = csv.writer(target)
        writer.writerow(["url", "status_code", "snippet_found", "valid", "error"])
        for r in results:
            writer.writerow([r.url, r.status_code, r.snippet_found, r.valid, r.error or ""])
        if args.output:
            target.close()

    elif args.format == "json":
        data = [r.to_row() for r in results]
        text = json.dumps(data, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
        else:
            print(text)

    else:  # plain text
        lines = []
        for r in results:
            status = "VALID" if r.valid else "INVALID"
            extra = f" (HTTP {r.status_code})" if r.status_code else ""
            err = f" [error: {r.error}]" if r.error else ""
            lines.append(f"{status}\t{r.url}{extra}{err}")
        text = "\n".join(lines)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
        else:
            print(text)


def main():
    parser = argparse.ArgumentParser(
        description="Check a list of URLs for the presence of a specific HTML snippet, "
                    "flagging matches as invalid links (or valid, with --invert).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-f", "--urls-file", help="Path to a text file with one URL per line")
    parser.add_argument("-u", "--urls", nargs="+", help="One or more URLs given directly")
    parser.add_argument("-s", "--snippet", required=True,
                        help="The HTML snippet (or regex, with --regex) to search for")
    parser.add_argument("--regex", action="store_true",
                        help="Treat --snippet as a regex pattern instead of a literal string")
    parser.add_argument("--invert", action="store_true",
                        help="Flip the logic: finding the snippet means the page is VALID "
                             "(default: finding it means INVALID)")
    parser.add_argument("-o", "--output", help="Write results to this file instead of stdout")
    parser.add_argument("--format", choices=["text", "csv", "json"], default="text",
                        help="Output format (default: text)")
    parser.add_argument("-w", "--workers", type=int, default=10,
                        help="Number of concurrent requests (default: 10)")
    parser.add_argument("-t", "--timeout", type=int, default=10,
                        help="Per-request timeout in seconds (default: 10)")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT,
                        help="Custom User-Agent header")
    parser.add_argument("--no-verify-ssl", action="store_true",
                        help="Disable SSL certificate verification")
    parser.add_argument("--show", choices=["valid", "invalid", "all"], default="valid",
                        help="Which results to show/write: 'valid' (default), "
                             "'invalid', or 'all'")
    parser.add_argument("--fail-on-invalid", action="store_true",
                        help="Exit with code 1 if any URL is invalid (useful in CI/cron)")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Suppress the progress summary printed to stderr")

    args = parser.parse_args()

    urls = load_urls(args)
    if not urls:
        print("No URLs provided. Use -f/--urls-file and/or -u/--urls.", file=sys.stderr)
        sys.exit(2)

    if args.no_verify_ssl:
        requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]

    pattern = re.compile(args.snippet) if args.regex else args.snippet
    verify_ssl = not args.no_verify_ssl

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_url = {
            executor.submit(
                check_url, url, pattern, args.regex, args.invert,
                args.timeout, args.user_agent, verify_ssl
            ): url
            for url in urls
        }
        done = 0
        for future in concurrent.futures.as_completed(future_to_url):
            results.append(future.result())
            done += 1
            if not args.quiet:
                print(f"\rChecked {done}/{len(urls)}", end="", file=sys.stderr, flush=True)

    if not args.quiet:
        print("", file=sys.stderr)

    # keep original input order in the output
    order = {u: i for i, u in enumerate(urls)}
    results.sort(key=lambda r: order.get(r.url, 0))

    invalid_count = sum(1 for r in results if not r.valid)
    total_checked = len(results)

    if args.show == "valid":
        shown = [r for r in results if r.valid]
    elif args.show == "invalid":
        shown = [r for r in results if not r.valid]
    else:
        shown = results

    write_output(shown, args)

    if not args.quiet:
        print(f"Done. {invalid_count} invalid / {total_checked} checked "
              f"({len(shown)} shown, --show={args.show}).", file=sys.stderr)

    if args.fail_on_invalid and invalid_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
