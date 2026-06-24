#!/usr/bin/env python3
"""
token-radar fetcher
-------------------
Pulls AI token-usage data from public/auth'd sources and builds a single
`data.js` payload that the static dashboard (index.html) reads.

Sources (all confirmed against OpenRouter's live OpenAPI spec, 2026-06):
  - GET /api/v1/models           (PUBLIC, no key) -> model landscape
  - GET /api/v1/datasets/rankings-daily  (needs OPENROUTER_API_KEY) -> token totals / top50 models / day
  - GET /api/v1/datasets/app-rankings    (needs OPENROUTER_API_KEY) -> top apps by token usage

The rankings datasets accept start_date/end_date, so on the very first run we
backfill BACKFILL_DAYS of history in one shot — the time-series charts are
populated on day one, no waiting.

Run:
  OPENROUTER_API_KEY=sk-or-... python3 fetch.py     # full
  python3 fetch.py                                   # landscape only (no key)
"""
import json
import os
import sys
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime, timezone, timedelta

BASE = "https://openrouter.ai/api/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
SNAP_DIR = os.path.join(DATA_DIR, "snapshots")
BACKFILL_DAYS = 90          # how much rankings history to pull on each run
TOP_MODELS_SHOWN = 20       # bar chart: top-N models latest day
TOP_APPS_SHOWN = 25
TIMEOUT = 30

API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()


def log(*a):
    print("[token-radar]", *a, file=sys.stderr)


def http_get(path, params=None, auth=False):
    url = BASE + path
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={"User-Agent": "token-radar/1.0"})
    if auth:
        if not API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        req.add_header("Authorization", "Bearer " + API_KEY)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def provider_of(slug):
    """Group key: the author/provider prefix before the first '/'."""
    if not slug:
        return "unknown"
    return slug.split("/", 1)[0].lower()


# ---------------------------------------------------------------- landscape
def build_landscape():
    """Public model catalog -> KPIs + launch timeline + provider mix.
    Always works, no key required."""
    out = {"ok": False}
    try:
        data = http_get("/models").get("data", [])
    except Exception as e:
        log("models fetch failed:", e)
        return out

    now = datetime.now(timezone.utc)
    providers = defaultdict(int)
    launches_by_month = defaultdict(int)
    prices_in = []
    ctx_lengths = []
    new_7 = new_30 = 0
    reasoning_models = 0

    for m in data:
        prov = provider_of(m.get("id", ""))
        providers[prov] += 1
        created = m.get("created")
        if created:
            dt = datetime.fromtimestamp(created, tz=timezone.utc)
            launches_by_month[dt.strftime("%Y-%m")] += 1
            age = (now - dt).days
            if age <= 7:
                new_7 += 1
            if age <= 30:
                new_30 += 1
        pr = m.get("pricing", {}) or {}
        try:
            p = float(pr.get("prompt", 0))
            if p > 0:
                prices_in.append(p * 1_000_000)  # $ per 1M prompt tokens
        except (TypeError, ValueError):
            pass
        cl = m.get("context_length")
        if isinstance(cl, (int, float)) and cl > 0:
            ctx_lengths.append(cl)
        if "reasoning" in (m.get("supported_parameters") or []):
            reasoning_models += 1

    prices_in.sort()
    median_price = prices_in[len(prices_in) // 2] if prices_in else None
    top_providers = sorted(providers.items(), key=lambda x: -x[1])[:15]
    launch_series = sorted(launches_by_month.items())[-24:]  # last 24 months

    out.update({
        "ok": True,
        "total_models": len(data),
        "total_providers": len(providers),
        "new_7d": new_7,
        "new_30d": new_30,
        "reasoning_models": reasoning_models,
        "median_prompt_price_per_m": median_price,
        "provider_mix": [{"provider": p, "models": c} for p, c in top_providers],
        "launches_by_month": [{"month": mth, "count": c} for mth, c in launch_series],
    })
    log(f"landscape: {len(data)} models, {len(providers)} providers")
    return out


# ---------------------------------------------------------------- rankings
def build_rankings():
    """Daily token totals for top-50 models -> headline trend, provider share,
    top models today. Needs key."""
    out = {"ok": False, "reason": "no_key"}
    if not API_KEY:
        return out
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=BACKFILL_DAYS)
    try:
        resp = http_get("/datasets/rankings-daily", {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }, auth=True)
    except Exception as e:
        log("rankings fetch failed:", e)
        return {"ok": False, "reason": str(e)}

    rows = resp.get("data", [])
    meta = resp.get("meta", {})
    if not rows:
        return {"ok": False, "reason": "empty"}

    # archive raw snapshot
    _save_snapshot("rankings", rows)

    # per-day total + per-day provider totals
    by_day_total = defaultdict(int)
    by_day_provider = defaultdict(lambda: defaultdict(int))
    by_model_latest = {}
    latest_date = max(r["date"] for r in rows)
    prev_date = None
    dates_sorted = sorted({r["date"] for r in rows})
    if len(dates_sorted) >= 2:
        prev_date = dates_sorted[-2]
    by_model_prev = {}

    for r in rows:
        d = r["date"]
        slug = r.get("model_permaslug", "unknown")
        tok = int(r.get("total_tokens", "0") or 0)
        by_day_total[d] += tok
        by_day_provider[d][provider_of(slug)] += tok
        if d == latest_date:
            by_model_latest[slug] = by_model_latest.get(slug, 0) + tok
        if prev_date and d == prev_date:
            by_model_prev[slug] = by_model_prev.get(slug, 0) + tok

    # headline daily total time-series
    total_series = [{"date": d, "tokens": by_day_total[d]} for d in dates_sorted]

    # provider share over time -> keep top providers by total volume, rest -> "other"
    prov_totals = defaultdict(int)
    for d in by_day_provider:
        for p, t in by_day_provider[d].items():
            prov_totals[p] += t
    # OpenRouter's dataset already emits a long-tail "other" row; fold our own
    # minor-provider remainder into the SAME "other" bucket (additive) so the key
    # never appears twice in the legend / series.
    top_provs = [p for p, _ in sorted(prov_totals.items(), key=lambda x: -x[1])[:8]]
    provider_series = []
    for d in dates_sorted:
        row = {"date": d}
        other = 0
        for p, t in by_day_provider[d].items():
            if p in top_provs and p != "other":
                row[p] = t
            else:
                other += t
        row["other"] = other
        provider_series.append(row)
    tracked = [p for p in top_provs if p != "other"] + ["other"]

    # top models latest day (with dod change) — drop OpenRouter's synthetic
    # "other" long-tail row, it's not a real model.
    real_models = {k: v for k, v in by_model_latest.items() if k != "other"}
    top_models = sorted(real_models.items(), key=lambda x: -x[1])[:TOP_MODELS_SHOWN]
    top_models_out = []
    for slug, tok in top_models:
        prev = by_model_prev.get(slug)
        dod = ((tok - prev) / prev * 100) if prev else None
        top_models_out.append({
            "model": slug, "provider": provider_of(slug),
            "tokens": tok, "dod_pct": dod,
        })

    out = {
        "ok": True,
        "as_of": meta.get("as_of"),
        "latest_date": latest_date,
        "date_range": [dates_sorted[0], dates_sorted[-1]],
        "providers_tracked": tracked,
        "total_series": total_series,
        "provider_series": provider_series,
        "top_models": top_models_out,
        "latest_total": by_day_total[latest_date],
    }
    log(f"rankings: {len(rows)} rows, {len(dates_sorted)} days, latest {latest_date}")
    return out


def build_apps():
    out = {"ok": False, "reason": "no_key"}
    if not API_KEY:
        return out
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=7)  # apps: trailing week
    try:
        resp = http_get("/datasets/app-rankings", {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "limit": TOP_APPS_SHOWN,
        }, auth=True)
    except Exception as e:
        log("apps fetch failed:", e)
        return {"ok": False, "reason": str(e)}
    rows = resp.get("data", [])
    if not rows:
        return {"ok": False, "reason": "empty"}
    _save_snapshot("apps", rows)
    apps = [{
        "rank": r.get("rank"),
        "name": r.get("app_name") or f"app#{r.get('app_id')}",
        "tokens": int(r.get("total_tokens", "0") or 0),
        "requests": r.get("total_requests", 0),
    } for r in rows]
    apps.sort(key=lambda x: x["rank"] if x["rank"] else 9999)
    log(f"apps: {len(apps)} apps")
    return {"ok": True, "apps": apps, "as_of": resp.get("meta", {}).get("as_of")}


# ---------------------------------------------------------------- macro
def load_macro():
    """Hand-maintained macro context (first-party token disclosures etc.).
    Edit data/macro.json. Each item MUST carry a source + as_of so nothing
    here reads as automated/verified when it isn't."""
    p = os.path.join(DATA_DIR, "macro.json")
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception as e:
            log("macro.json parse error:", e)
    return []


def load_gpu():
    """Hand-maintained GPU rental-price series (Silicon Data SDH100RT/SDB200RT,
    Bloomberg-sourced). Edit data/gpu.json — colleague refreshes from Bloomberg."""
    p = os.path.join(DATA_DIR, "gpu.json")
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception as e:
            log("gpu.json parse error:", e)
    return {}


# ---------------------------------------------------------------- io
def _save_snapshot(kind, rows):
    os.makedirs(SNAP_DIR, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(SNAP_DIR, f"{kind}-{day}.json")
    json.dump(rows, open(path, "w"), ensure_ascii=False)


def main():
    os.makedirs(SNAP_DIR, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "has_key": bool(API_KEY),
        "landscape": build_landscape(),
        "rankings": build_rankings(),
        "apps": build_apps(),
        "macro": load_macro(),
        "gpu": load_gpu(),
    }
    # data.js: loadable via <script src> so the dashboard works by double-click
    # (file://) with zero server, AND over http for GitHub Pages.
    js = "window.__DATA__ = " + json.dumps(payload, ensure_ascii=False) + ";\n"
    open(os.path.join(HERE, "data.js"), "w").write(js)
    json.dump(payload, open(os.path.join(DATA_DIR, "latest.json"), "w"),
              ensure_ascii=False, indent=2)
    log("wrote data.js + data/latest.json")
    log("rankings ok:", payload["rankings"].get("ok"),
        "| apps ok:", payload["apps"].get("ok"),
        "| landscape ok:", payload["landscape"].get("ok"))


if __name__ == "__main__":
    main()
