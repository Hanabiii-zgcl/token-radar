#!/usr/bin/env python3
"""
fetch_valliance.py — 对照源：Valliance AI Lab「AI Monetization Tracker」
----------------------------------------------------------------------
对方页面与本站同构：全部数据在单个 data.js（window.__DATA__ = {...}）。
本脚本每次运行抓取该文件，只保留我们没有一手来源的模块：

  arr          Frontier Lab ARR 外推模型（他们的估算模型，非披露值）
  gpu_ornn     Ornn OCPI GPU 租赁价指数（5 SKU，日频，91 天滚动窗）
  vercel       Vercel AI Gateway token/$ 份额（61 天滚动窗）
  sdk          npm / PyPI SDK 下载量（adoption proxy）
  datacenters  Epoch AI 数据中心汇总（CC-BY 4.0）

明确不抓：openrouter（本站一手，见 fetch.py）、signals/news（对方编辑内容）。

产出：
  data/valliance-latest.json   保留模块的最新完整载荷（覆盖写）
  data/valliance-history.json  按日累积（滚动窗之外的历史靠它，逐日合并）
  valliance.js                 window.__VDATA__，file:// 双击离线兜底

失败策略：任何抓取/解析错误 → 保留旧文件原样、exit 0，绝不拖垮主管道
（页面会显示旧的 as_of，一眼可见 staleness）。
署名：页面渲染处标注 via Valliance AI Lab；各模块上游（Ornn OCPI、
Epoch CC-BY 4.0、Vercel leaderboards、npm/pypi）的 source 字段原样透传。
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

URL = "https://www.valliance-ailab.com/ai-monetization-tracker/data.js"
UA = "token-radar-crossref/1.0 (+https://hanabiii-zgcl.github.io/token-radar/)"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
TIMEOUT = 30
KEEP = ("arr", "gpu", "vercel", "sdk", "datacenters")


def log(*a):
    print("[valliance]", *a, file=sys.stderr)


def fetch_raw():
    last = None
    for i in range(3):
        try:
            req = urllib.request.Request(
                URL + f"?ts={int(time.time())}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read().decode("utf-8")
        except Exception as e:
            last = e
            log(f"attempt {i + 1}/3 failed:", e)
            time.sleep(5 * (i + 1))
    raise last


def parse_payload(js_text):
    s = js_text[js_text.index("=") + 1:].strip().rstrip(";")
    return json.loads(s)


def merge_pairs(bucket, pairs):
    """bucket: {date -> value}；pairs: [[date, value], ...]。同日新值覆盖旧值。"""
    n = 0
    for it in pairs or []:
        try:
            d, v = it[0], it[1]
        except (TypeError, IndexError):
            continue
        if v is None:
            continue
        key = str(d)
        if bucket.get(key) != v:
            bucket[key] = v
            n += 1
    return n


def update_history(mod):
    hp = os.path.join(DATA_DIR, "valliance-history.json")
    if os.path.exists(hp):
        try:
            H = json.load(open(hp, encoding="utf-8"))
        except Exception as e:
            log("history parse error, starting fresh:", e)
            H = {}
    else:
        H = {}
    H.setdefault("note", "Per-date accumulation of Valliance cross-source; "
                         "preserves data beyond their rolling windows.")
    changed = 0

    # GPU: 91 天滚动窗 -> 逐日累积
    gpu = mod.get("gpu_ornn") or {}
    hg = H.setdefault("gpu_ornn", {})
    for sku, series in (gpu.get("series") or {}).items():
        changed += merge_pairs(hg.setdefault(sku, {}), series)

    # Vercel: 61 天滚动窗（days[] 与 series[lab][] 对齐）
    ver = mod.get("vercel") or {}
    for src_key, dst_key in (("tokens", "vercel_token_share"),
                             ("cost", "vercel_spend_share")):
        blk = (ver.get("history") or {}).get(src_key) or {}
        days = blk.get("days") or []
        hd = H.setdefault(dst_key, {})
        for lab, vals in (blk.get("series") or {}).items():
            bucket = hd.setdefault(lab, {})
            changed += merge_pairs(bucket, list(zip(days, vals or [])))

    # SDK: 窗口已长，仍然累积以防对方缩窗
    sdk = mod.get("sdk") or {}
    for src_key, dst_key in (("npm", "sdk_npm"), ("pypi", "sdk_pypi")):
        hd = H.setdefault(dst_key, {})
        for pkg, series in (sdk.get(src_key) or {}).items():
            changed += merge_pairs(hd.setdefault(pkg, {}), series)

    # ARR 模型参数漂移：按 updated 日期记每家公司的 (vLast, rMs, tLast, yoyDen)
    arr = mod.get("arr") or {}
    ha = H.setdefault("arr_model", {})
    upd = str(arr.get("updated") or datetime.now(timezone.utc).date())
    for comp, c in (arr.get("companies") or {}).items():
        counter = c.get("counter") or {}
        rec = {"vLast": counter.get("vLast"), "rMs": counter.get("rMs"),
               "tLast": counter.get("tLast"), "yoyDen": c.get("yoyDen")}
        if ha.setdefault(comp, {}).get(upd) != rec:
            ha[comp][upd] = rec
            changed += 1

    # DC 汇总快照：按 as_of 记 totals（月频变化，体积可忽略）
    dc = mod.get("datacenters") or {}
    if dc.get("totals"):
        hdc = H.setdefault("dc_totals", {})
        k = str(dc.get("as_of") or "")
        if k and hdc.get(k) != dc["totals"]:
            hdc[k] = dc["totals"]
            changed += 1

    json.dump(H, open(hp, "w", encoding="utf-8"), ensure_ascii=False,
              separators=(",", ":"), sort_keys=True)
    log(f"history: {changed} new/updated points")
    return changed


def main():
    try:
        D = parse_payload(fetch_raw())
    except Exception as e:
        log("FETCH/PARSE FAILED — keeping previous data untouched:", e)
        return 0

    modules = {
        "arr": D.get("arr"),
        "gpu_ornn": D.get("gpu"),
        "vercel": D.get("vercel"),
        "sdk": D.get("sdk"),
        "datacenters": D.get("datacenters"),
    }
    present = [k for k, v in modules.items() if v]
    if not present:
        log("payload parsed but no known modules found — schema changed? keeping previous data")
        return 0
    missing = [k for k, v in modules.items() if not v]
    if missing:
        log("WARNING missing modules this run:", ", ".join(missing))

    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source_page": "https://www.valliance-ailab.com/ai-monetization-tracker/",
        "attribution": "Cross-sourced from Valliance AI Lab (self-hosted rebuild). "
                       "Per-module upstream sources carried in each module's source field.",
        "modules": modules,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    update_history(modules)
    json.dump(payload, open(os.path.join(DATA_DIR, "valliance-latest.json"),
                            "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(HERE, "valliance.js"), "w", encoding="utf-8") as f:
        f.write("window.__VDATA__ = " + json.dumps(payload, ensure_ascii=False) + ";\n")
    log("wrote data/valliance-latest.json + data/valliance-history.json + valliance.js")
    log("modules:", ", ".join(present),
        "| arr updated:", (modules.get("arr") or {}).get("updated"),
        "| gpu as_of:", (modules.get("gpu_ornn") or {}).get("as_of"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
