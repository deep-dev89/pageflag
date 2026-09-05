# pageflag

A small, dependency-light Python script that checks a list of URLs for the
presence of a specific piece of HTML, and flags matching pages as **invalid**
(or valid, if you flip the logic). Built for Linux (cron / systemd timers),
but it's plain Python 3 + `requests`, so it runs anywhere.

## Why

Sometimes you have a list of links and you want to know whether a page still
shows a particular element — a "you're here!" marker, an error banner, a
"sold out" tag, a redirect notice, whatever. `pageflag` fetches each URL,
looks for that HTML snippet, and reports which links are still good and
which ones aren't.

## Features

- Reads URLs from a file, the command line, or both
- Match on a literal HTML string or a regex pattern
- Invert the logic: "snippet found" can mean valid *or* invalid
- Concurrent requests (configurable worker count)
- Configurable timeout, User-Agent, and SSL verification
- Output as plain text, CSV, or JSON — to stdout or a file
- Optional non-zero exit code on any invalid result, for cron/CI use

## Requirements

- Python 3.7+
- `requests`

```bash
pip install requests --break-system-packages
```

(Drop `--break-system-packages` if you're using a virtualenv.)

## Installation

```bash
git clone https://github.com/deep-dev89/pageflag.git
cd pageflag
chmod +x pageflag.py
```

## Usage

```bash
./pageflag.py -f urls.txt -s '<span class="select-none" data-new-page-greeting-text="">You're here!</span>'
```

By default, finding the snippet marks a page **invalid**. Add `--invert` if
finding the snippet should mean the page is **valid** instead.

### Common examples

Pass URLs directly instead of a file:

```bash
./pageflag.py -u https://example.com https://example.org -s "some html"
```

Match with a regex instead of a literal string:

```bash
./pageflag.py -f urls.txt -s 'data-new-page-greeting-text="[^"]*"' --regex
```

Save results as CSV, use 20 concurrent workers, 15s timeout:

```bash
./pageflag.py -f urls.txt -s "You're here" -o results.csv --format csv -w 20 -t 15
```

By default, only **valid** links are shown/written. To see the invalid
ones instead, or everything:

```bash
./pageflag.py -f urls.txt -s "You're here" --show invalid
./pageflag.py -f urls.txt -s "You're here" --show all
```

Use in a cron job / CI and fail loudly if anything's invalid:

```bash
./pageflag.py -f urls.txt -s "You're here" --fail-on-invalid
```

## Options

| Flag | Description |
|---|---|
| `-f, --urls-file` | Path to a text file with one URL per line |
| `-u, --urls` | One or more URLs given directly |
| `-s, --snippet` | HTML snippet (or regex, with `--regex`) to search for |
| `--regex` | Treat `--snippet` as a regex pattern |
| `--invert` | Finding the snippet means VALID instead of INVALID |
| `-o, --output` | Write results to a file instead of stdout |
| `--format` | `text` (default), `csv`, or `json` |
| `-w, --workers` | Number of concurrent requests (default: 10) |
| `-t, --timeout` | Per-request timeout in seconds (default: 10) |
| `--user-agent` | Custom User-Agent header |
| `--no-verify-ssl` | Disable SSL certificate verification |
| `--show` | Which results to show/write: `valid` (default), `invalid`, or `all` |
| `--fail-on-invalid` | Exit code 1 if any URL is invalid |
| `-q, --quiet` | Suppress the progress output on stderr |

## Limitations

- Matches against the raw HTML `requests` receives — it does not execute
  JavaScript. If your snippet only appears after client-side rendering,
  this won't detect it (a headless-browser variant using something like
  Playwright would be needed for that case).
- Exact whitespace/attribute-order/quoting matters for literal matches;
  use `--regex` for more flexible matching.

## License

MIT — see [LICENSE](LICENSE).
