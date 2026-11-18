"""Download or update the local data cache with akshare.

The historical constituent file ``data/constituents_history.parquet`` is
included in the repository, so this script only needs to download prices,
valuation data and the benchmark index.

Usage:
    python scripts/update_data.py
    python scripts/update_data.py --refresh
    python scripts/update_data.py --workers 4
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import akshare as ak
import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config


def _fetch_one(code: str, start: str, end: str) -> pd.DataFrame | None:
    num = code.split(".")[1]
    sina = code.replace(".", "")
    s_date = pd.Timestamp(start).strftime("%Y%m%d")
    e_date = pd.Timestamp(end).strftime("%Y%m%d")

    price = None
    for attempt in range(4):
        try:
            price = ak.stock_zh_a_daily(
                symbol=sina, start_date=s_date, end_date=e_date, adjust="hfq")
            if price is not None and len(price) > 0:
                break
        except Exception:
            time.sleep(2 + attempt * 2)
    if price is None or len(price) == 0:
        return None

    price["date"] = pd.to_datetime(price["date"])
    price = price[(price["date"] >= pd.Timestamp(start)) &
                  (price["date"] <= pd.Timestamp(end))].copy()

    val = None
    for attempt in range(4):
        try:
            v = ak.stock_value_em(symbol=num)
            if v is not None and len(v) > 0:
                val = v.iloc[:, [0, 4, 7, 9]].copy()
                val.columns = ["date", "float_mktcap", "peTTM", "pbMRQ"]
                val["date"] = pd.to_datetime(val["date"])
                val = val[(val["date"] >= pd.Timestamp(start)) &
                          (val["date"] <= pd.Timestamp(end))]
                break
        except Exception:
            time.sleep(2 + attempt * 2)

    if val is None:
        price["float_mktcap"] = np.nan
        price["peTTM"] = np.nan
        price["pbMRQ"] = np.nan
        df = price
    else:
        df = price.merge(val, on="date", how="left")

    df = df.sort_values("date").reset_index(drop=True)
    df["code"] = code
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["turn"] = pd.to_numeric(df["turnover"], errors="coerce") * 100.0
    df["pctChg"] = pd.to_numeric(df["close"], errors="coerce").pct_change() * 100.0
    df["pctChg"] = df["pctChg"].fillna(0.0)
    df["tradestatus"] = 1
    df["isST"] = 0
    cols = ["date", "code", "close", "volume", "amount", "turn", "pctChg",
            "peTTM", "pbMRQ", "float_mktcap", "tradestatus", "isST"]
    return df[cols]


def _job(code, start, end, refresh):
    path = config.CACHE_DIR / f"{code}.parquet"
    if path.exists() and not refresh:
        old = pd.read_parquet(path)
        old["date"] = pd.to_datetime(old["date"])
        if old["date"].max() >= pd.Timestamp(end):
            return code, "cached", old["date"].max()
        fetch_start = old["date"].max().strftime("%Y-%m-%d")
    else:
        old = None
        fetch_start = start

    df = _fetch_one(code, fetch_start, end)
    if df is None or len(df) == 0:
        return code, "fail", None

    if old is not None:
        # fetch starts on the old last date to get a correct first return,
        # then drop the overlapping row before appending.
        df = df[df["date"] > old["date"].max()]
        df = pd.concat([old, df], ignore_index=True)
        df = df.drop_duplicates("date", keep="last").sort_values("date")
    df.to_parquet(path, index=False)
    return code, "ok", df["date"].max()


def download_benchmark(start, end):
    path = config.CACHE_DIR / "index_H00300.parquet"
    try:
        raw = ak.stock_zh_index_hist_csindex(
            symbol="H00300",
            start_date=pd.Timestamp(start).strftime("%Y%m%d"),
            end_date=pd.Timestamp(end).strftime("%Y%m%d"))
        df = raw.iloc[:, [0, 9]].copy()
        df.columns = ["date", "close"]
        df["date"] = pd.to_datetime(df["date"])
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["pctChg"] = df["close"].pct_change() * 100.0
        df.to_parquet(path, index=False)
        print("    benchmark ok:", df["date"].min().date(), df["date"].max().date())
    except Exception as e:
        print("    benchmark fail:", e)


def update_current_constituents():
    try:
        df = ak.index_stock_cons_csindex(symbol="000300")
        num = df.iloc[:, 4].astype(str).str.zfill(6)
        market = np.where(num.str.startswith("6"), "sh", "sz")
        codes = [f"{m}.{n}" for m, n in zip(market, num)]
        pd.DataFrame({"code": codes}).to_parquet(
            config.DATA_DIR / "constituents_current_2026.parquet", index=False)
        print(f"    current constituents: {len(codes)}")
    except Exception as e:
        print("    current constituents fail:", e)


def update_industry_map():
    path = config.DATA_DIR / "industry_map.parquet"
    if path.exists():
        return
    print("    building industry map (84 requests) ...")
    try:
        sectors = ak.stock_sector_spot(indicator="行业")
        rows = []
        for lab, name in zip(sectors["label"], sectors["板块"]):
            for attempt in range(3):
                try:
                    d = ak.stock_sector_detail(sector=lab)
                    if d is not None and len(d) > 0:
                        d = d[["symbol", "code", "name"]].copy()
                        d["industry"] = name
                        rows.append(d)
                        break
                except Exception:
                    time.sleep(1 + attempt)
        m = pd.concat(rows, ignore_index=True).drop_duplicates("code")
        m.to_parquet(path, index=False)
        print("    industry map:", m.shape)
    except Exception as e:
        print("    industry map fail:", e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=config.DATA_START)
    parser.add_argument("--end", default=config.LIVE_END)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    hist = pd.read_parquet(config.DATA_DIR / "constituents_history.parquet")
    codes = sorted(set(hist["code"]))
    cur_path = config.DATA_DIR / "constituents_current_2026.parquet"
    if cur_path.exists():
        codes = sorted(set(codes) | set(pd.read_parquet(cur_path)["code"]))
    print(f"universe: {len(codes)} stocks, {args.start} ~ {args.end}")

    ok = fail = cached = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_job, c, args.start, args.end, args.refresh): c
                for c in codes}
        for i, f in enumerate(as_completed(futs), 1):
            code, status, last = f.result()
            if status == "ok":
                ok += 1
            elif status == "cached":
                cached += 1
            else:
                fail += 1
                print("    fail:", code)
            if i % 20 == 0 or i == len(codes):
                print(f"    {i}/{len(codes)} ok={ok} cached={cached} fail={fail} "
                      f"elapsed={time.time()-t0:.0f}s")

    update_current_constituents()
    download_benchmark(args.start, args.end)
    update_industry_map()
    print("done")


if __name__ == "__main__":
    main()
