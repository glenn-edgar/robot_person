# CONTINUE.md — RCWD Hourly Water Usage Scraper

## Goal

Pull hourly water usage data from the Rancho California Water District
customer portal (`https://myaccount.ranchowater.com/secure/`) into a local
store suitable for anomaly detection (Welford running stats over hourly
buckets, a la the anomalisa pattern).

## Target architecture

```
RCWD portal  →  Playwright (auth)  →  JSON XHR endpoint  →  SQLite
                                                              ↓
                                                          NATS subject
                                                              ↓
                                                       Welford node (ChainTree)
```

Hourly residential flow is a near-ideal anomaly target: running toilets,
stuck irrigation valves, and slab leaks present as flat baseline shifts
that a z-score catches within 1–2 days.

## Status

- [x] Confirmed portal is ASP.NET WebForms, JS-required, login-gated.
- [x] Confirmed `/secure/` redirects to `default.aspx?ReturnUrl=%2Fsecure`
      pre-auth.
- [x] Drafted Playwright login flow with `storage_state` caching.
- [ ] **Discover the hourly-usage XHR endpoint** (manual, see below).
- [ ] Lock down selectors on login form (ASP.NET ids are ugly —
      `ctl00$MainContent$...`).
- [ ] Implement JSON fetch + parse for whatever shape they return.
- [ ] SQLite schema + idempotent upsert.
- [ ] NATS publish on new buckets.
- [ ] systemd timer or cron — once per hour, jittered.

## Environment

- Ubuntu 24.04 on Snapdragon Surface Laptop, WSL2.
- Python 3 with venv.
- `pip install playwright beautifulsoup4 lxml`
- `playwright install chromium`
- `playwright install-deps`  ← required on WSL or Chromium fails to launch.

Credentials in env vars, not source:

```bash
export RCWD_USER=...
export RCWD_PASS=...
```

## Next steps

### 1. Discover the hourly XHR endpoint (DO THIS FIRST)

Manual, in regular Chrome (not the script):

1. Log in to `https://myaccount.ranchowater.com/`.
2. Navigate to the consumption / usage page.
3. F12 → Network tab → filter **Fetch/XHR**.
4. Switch the chart to hourly view, change date range — trigger a
   fresh request.
5. Look for a response with timestamps + gallons (or CCF). Likely paths:
   - `/secure/api/usage`
   - `/secure/consumption.aspx/GetHourlyData`
   - A `.ashx` handler
6. Right-click the request → **Copy → Copy as cURL**. Paste into the
   notes section below.

The cURL captures: URL, method, JSON payload (date range, account id,
meter id), and required headers (typically `Content-Type: application/json`,
`X-Requested-With: XMLHttpRequest`, possibly an anti-forgery token).

### 2. If the cURL is messy, let Playwright sniff

Drop this into the script and click through the UI manually with
`headless=False`. Every relevant JSON response is dumped:

```python
def on_response(r):
    if r.status == 200 and "json" in r.headers.get("content-type", ""):
        if any(k in r.url.lower() for k in ("usage", "consumption", "hourly")):
            print(f">>> {r.request.method} {r.url}")
            try:
                print(r.json())
            except Exception:
                pass

page.on("response", on_response)
```

### 3. Wire it up

Skeleton (selectors and endpoint TBD from step 1):

```python
import os, json
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_FILE = "rancho_state.json"
USERNAME   = os.environ["RCWD_USER"]
PASSWORD   = os.environ["RCWD_PASS"]

def login_and_save_state():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto("https://myaccount.ranchowater.com/")

        # TODO: replace with the real ids from DevTools.
        page.fill('input[id*="Username" i]', USERNAME)
        page.fill('input[type="password"]', PASSWORD)
        page.click('input[type="submit"], button:has-text("Sign In")')

        page.wait_for_url("**/secure/**", timeout=15000)
        ctx.storage_state(path=STATE_FILE)
        browser.close()

def fetch_hourly(start: date, end: date):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=STATE_FILE)
        page = ctx.new_page()

        # Visit the usage page first so any per-page tokens are issued.
        page.goto("https://myaccount.ranchowater.com/secure/usage.aspx")
        page.wait_for_load_state("networkidle")

        resp = page.request.post(
            # TODO: replace with the discovered endpoint.
            "https://myaccount.ranchowater.com/secure/usage.aspx/GetHourlyData",
            data=json.dumps({
                "startDate": start.isoformat(),
                "endDate":   end.isoformat(),
                "interval":  "hourly",
            }),
            headers={
                "Content-Type":     "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        data = resp.json()
        browser.close()
        return data

if __name__ == "__main__":
    if not Path(STATE_FILE).exists():
        login_and_save_state()
    end   = date.today()
    start = end - timedelta(days=7)
    print(json.dumps(fetch_hourly(start, end), indent=2)[:2000])
```

### 4. Parse + store

Likely response shapes (decide once endpoint is known):

```
[{ "timestamp": "...", "gallons": 12.4 }, ...]
{ "labels": ["..."], "values": [12.4, ...] }
{ "d": "<JSON string>" }    # ASP.NET WebMethod envelope — parse twice
```

SQLite schema (keep it boring):

```sql
CREATE TABLE IF NOT EXISTS usage_hourly (
    meter_id    TEXT NOT NULL,
    ts_utc      INTEGER NOT NULL,    -- epoch seconds, hour-aligned
    gallons     REAL NOT NULL,
    fetched_at  INTEGER NOT NULL,
    PRIMARY KEY (meter_id, ts_utc)
);
CREATE INDEX IF NOT EXISTS ix_usage_ts ON usage_hourly(ts_utc);
```

Use `INSERT ... ON CONFLICT DO UPDATE` so re-fetches are idempotent
(meter readings are sometimes corrected after the fact).

### 5. NATS bridge

On each new bucket inserted, publish:

- subject: `usage.rcwd.<meter_id>.hourly`
- payload: CBOR `{ts, gallons, meter_id}`

Downstream Welford node maintains `(n, mean, M2)` per meter, emits
`anomaly.rcwd.<meter_id>` when `|x - mean| / sqrt(M2/(n-1)) > 2.0` and
`n >= 3` (anomalisa defaults). Atomic check-and-set on the alert key
prevents duplicate alerts within a window.

## Gotchas

- **`playwright install-deps`** is non-optional on WSL2. Without it,
  Chromium throws cryptic shared-library errors at launch.
- **ASP.NET `__VIEWSTATE` / `__EVENTVALIDATION`** — Playwright handles
  these because it drives a real browser. Do NOT try to migrate this to
  plain `requests` later; replaying viewstate by hand is miserable.
- **`.aspx/Method` WebMethod envelope** — responses are wrapped in
  `{"d": ...}` and the inner value is sometimes a JSON *string* that
  needs a second `json.loads()`.
- **Rate limit yourself.** AMI meters report hourly at best; polling
  more than once per hour gains nothing and risks the account getting
  flagged. Add jitter (e.g. `sleep(random.randint(0, 600))`) before the
  hourly fetch to avoid hammering on the hour mark.
- **Session expiry.** If `storage_state` goes stale, the script will
  land back on the login page. Detect by checking `page.url` after
  `goto("/secure/")` and re-run `login_and_save_state()` on mismatch.
- **Time zones.** Portal will likely return local (Pacific) timestamps.
  Convert to UTC before storage to keep DST out of the anomaly math.
- **Bot detection.** RCWD's portal is low-traffic and unlikely to have
  Cloudflare / hCaptcha, but if a CAPTCHA appears, fall back to
  `playwright-stealth` and slow the flow down.

## Notes / scratch

```
# Paste the cURL from DevTools here once captured:


# Confirmed login form selectors:


# Confirmed hourly endpoint URL + payload shape:


# Sample response (first 20 lines):


```

## References

- Playwright Python: https://playwright.dev/python/
- anomalisa (Welford + hourly buckets pattern):
  https://github.com/uriva/anomalisa
- Welford's algorithm: O(1) running mean + variance, 3 scalars
  `(n, mean, M2)`. Already implemented in C for ChainTree/Cortex-M.


