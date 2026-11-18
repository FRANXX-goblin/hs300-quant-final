"""Raw factor construction and monthly cross-section preparation."""

from __future__ import annotations

import numpy as np
import pandas as pd

import config
from .data import forward_returns


def _safe_div(a, b):
    return a / b.replace(0, np.nan)


def compute_stock_factors(df: pd.DataFrame, bench_ret: pd.Series) -> pd.DataFrame:
    d = df.set_index("date").sort_index()
    ret = pd.to_numeric(d["pctChg"], errors="coerce") / 100.0
    turn = pd.to_numeric(d["turn"], errors="coerce")
    amount = pd.to_numeric(d["amount"], errors="coerce")
    close = pd.to_numeric(d["close"], errors="coerce")
    cap = pd.to_numeric(d["float_mktcap"], errors="coerce")
    pe = pd.to_numeric(d["peTTM"], errors="coerce")
    pb = pd.to_numeric(d["pbMRQ"], errors="coerce")
    bench = bench_ret.reindex(d.index)

    cum = (1.0 + ret.fillna(0.0)).cumprod()
    out = pd.DataFrame(index=d.index)
    out["cum"] = cum
    out["ep"] = np.where(pe > 0, 1.0 / pe, np.nan)
    out["bp"] = np.where(pb > 0, 1.0 / pb, np.nan)
    out["size"] = -np.log(cap.where(cap > 0))
    out["mom_12_1"] = cum.shift(21) / cum.shift(252) - 1.0
    out["rev_1m"] = -(cum / cum.shift(21) - 1.0)
    out["vol_20"] = -ret.rolling(20, min_periods=15).std() * np.sqrt(252)
    out["vol_60"] = -ret.rolling(60, min_periods=40).std() * np.sqrt(252)
    out["turn_20"] = -turn.rolling(20, min_periods=15).mean()
    out["turn_60"] = -turn.rolling(60, min_periods=40).mean()
    out["turn_cv_20"] = -(turn.rolling(20, min_periods=15).std() /
                          turn.rolling(20, min_periods=15).mean())
    out["max_20"] = -ret.rolling(20, min_periods=15).max()
    out["downvol_60"] = -np.sqrt(
        (ret.clip(upper=0.0) ** 2).rolling(60, min_periods=40).mean() * 252
    )
    out["amihud_20"] = (ret.abs() / amount.replace(0, np.nan)
                        ).rolling(20, min_periods=15).mean() * 1e8

    cov = ret.rolling(60, min_periods=40).cov(bench)
    var = bench.rolling(60, min_periods=40).var()
    beta = cov / var.replace(0, np.nan)
    out["beta_60"] = -beta
    resid_var = ret.rolling(60, min_periods=40).var() - beta ** 2 * var
    out["ivol_60"] = -np.sqrt(resid_var.clip(lower=0.0) * 252)

    t20 = turn.rolling(20, min_periods=15).mean()
    t250 = turn.rolling(250, min_periods=150).mean()
    out["turn_abn"] = -(t20 / t250.replace(0, np.nan))

    out["valid"] = ((d.get("tradestatus", 1) == 1) &
                    (d.get("isST", 0) == 0) &
                    close.notna() & (close > 0)).astype(float)
    out["nobs"] = np.arange(1, len(out) + 1)
    return out


def winsorize(s: pd.Series, lower=0.01, upper=0.99) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    if s.notna().sum() < 10:
        return s
    lo, hi = s.quantile([lower, upper])
    return s.clip(lo, hi)


def zscore(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    mu, sd = s.mean(), s.std(ddof=0)
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return (s - mu) / sd


def industry_zscore(s: pd.Series, industry: pd.Series, min_n=5) -> pd.Series:
    s = winsorize(s)
    df = pd.DataFrame({"s": s, "ind": industry})
    overall_mu = s.mean()
    overall_sd = s.std(ddof=0)
    grp = df.groupby("ind")["s"]
    mu = grp.transform("mean")
    sd = grp.transform("std")
    n = grp.transform("count")
    mu = mu.where(n >= min_n, overall_mu)
    sd = sd.where((n >= min_n) & (sd > 0), overall_sd)
    z = (s - mu) / sd
    return z


def build_monthly_panel(
    stock_data,
    signal_dates,
    cons_by_date,
    bench_ret,
    industry_map,
    horizons=(1, 3, 6, 12),
) -> pd.DataFrame:
    factors = {}
    for code, df in stock_data.items():
        factors[code] = compute_stock_factors(df, bench_ret)

    cum_panel = pd.DataFrame({c: f["cum"] for c, f in factors.items()}).sort_index()
    fwd = forward_returns(cum_panel, signal_dates, horizons)

    bm_cum = (1.0 + bench_ret.fillna(0.0)).cumprod()
    next_signal = {pd.Timestamp(t): pd.Timestamp(signal_dates[i + 1])
                   for i, t in enumerate(signal_dates[:-1])}

    rows = []
    for t in signal_dates:
        t = pd.Timestamp(t)
        codes = cons_by_date.get(t, [])
        recs = {}
        for code in codes:
            f = factors.get(code)
            if f is None or t not in f.index:
                continue
            row = f.loc[t]
            if row["nobs"] < config.MIN_HISTORY or row["valid"] <= 0:
                continue
            rec = {k: row[k] for k in config.FACTORS}
            rec["cap"] = np.exp(-row["size"]) if np.isfinite(row["size"]) else np.nan
            recs[code] = rec
        if len(recs) < 30:
            continue
        xs = pd.DataFrame(recs).T
        xs.index.name = "code"
        ind_series = industry_map.set_index("code")["industry"]
        xs["industry"] = ind_series.reindex(xs.index).fillna("其他")

        for key, df in fwd.items():
            if t in df.index:
                xs[key] = df.loc[t].reindex(xs.index)
            else:
                xs[key] = np.nan

        z = pd.DataFrame(index=xs.index)
        zi = pd.DataFrame(index=xs.index)
        for f in config.FACTORS:
            z[f] = zscore(winsorize(xs[f]))
            zi[f] = industry_zscore(xs[f], xs["industry"])
        z["value"] = z[["ep", "bp"]].mean(axis=1)
        z["value_zi"] = zi[["ep", "bp"]].mean(axis=1)
        for f in config.FACTORS:
            z[f + "_zi"] = zi[f]

        z["baseline"] = z[config.BASELINE_FACTORS].mean(axis=1)
        z["research"] = z[config.RESEARCH_FACTORS].mean(axis=1)
        zi_scores = zi.copy()
        zi_scores["value"] = zi[["ep", "bp"]].mean(axis=1)
        z["baseline_zi"] = zi_scores[config.BASELINE_FACTORS].mean(axis=1)
        z["research_zi"] = zi_scores[config.RESEARCH_FACTORS].mean(axis=1)

        z["industry"] = xs["industry"]
        z["cap"] = xs["cap"]
        z["fwd_ret"] = xs.get("fwd_1m")
        for h in horizons:
            z[f"fwd_{h}m"] = xs.get(f"fwd_{h}m")
        t2 = next_signal.get(t)
        if t2 is not None and t in bm_cum.index and t2 in bm_cum.index:
            bm_fwd = bm_cum.loc[t2] / bm_cum.loc[t] - 1.0
        else:
            bm_fwd = np.nan
        z["fwd_excess"] = z["fwd_ret"] - bm_fwd
        z["bm_fwd"] = bm_fwd
        z["date"] = t
        rows.append(z.reset_index())

    if not rows:
        return pd.DataFrame()
    panel = pd.concat(rows, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])
    return panel.sort_values(["date", "code"]).reset_index(drop=True)
