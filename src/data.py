"""Data loading, universe construction and panel preparation."""

from __future__ import annotations

import numpy as np
import pandas as pd

import config


NUMERIC_COLS = [
    "close", "volume", "amount", "turn", "pctChg",
    "peTTM", "pbMRQ", "float_mktcap", "tradestatus", "isST",
]


def read_stock(code: str) -> pd.DataFrame | None:
    path = config.CACHE_DIR / f"{code}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = (df.drop_duplicates("date")
            .sort_values("date")
            .reset_index(drop=True))
    return df


def load_stock_data(codes, start=config.DATA_START, end=config.LIVE_END):
    data = {}
    for code in codes:
        df = read_stock(code)
        if df is None:
            continue
        df = df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))]
        if len(df) < 60:
            continue
        data[code] = df.reset_index(drop=True)
    return data


def load_benchmark(start=config.DATA_START, end=config.LIVE_END) -> pd.DataFrame:
    path = config.CACHE_DIR / "index_H00300.parquet"
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["pctChg"] = pd.to_numeric(df["pctChg"], errors="coerce")
    df = df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))]
    df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    df["ret"] = df["pctChg"] / 100.0
    df.loc[df.index[0], "ret"] = 0.0
    df["ret"] = df["ret"].fillna(0.0)
    return df[["date", "close", "ret"]]


def load_constituents() -> pd.DataFrame:
    path = config.DATA_DIR / "constituents_history.parquet"
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    return df.drop_duplicates(["date", "code"]).sort_values(["date", "code"])


def constituents_by_date(dates) -> dict[pd.Timestamp, list[str]]:
    """Return HS300 members for each date.

    For dates after the last historical snapshot, the latest available
    snapshot is frozen.  This avoids using future index changes in the
    2026 out-of-sample simulation.
    """
    hist = load_constituents()
    hist_dates = sorted(hist["date"].unique())
    by_date = hist.groupby("date")["code"].apply(list).to_dict()
    last_date = hist_dates[-1]
    last_codes = by_date[last_date]
    out = {}
    for d in dates:
        d = pd.Timestamp(d)
        if d in by_date:
            out[d] = list(by_date[d])
        else:
            # use most recent snapshot not later than d
            prev = [x for x in hist_dates if x <= d]
            out[d] = list(by_date[prev[-1]]) if prev else list(last_codes)
    return out


def load_industry() -> pd.DataFrame:
    path = config.DATA_DIR / "industry_map.parquet"
    df = pd.read_parquet(path)
    num = df["code"].astype(str).str.zfill(6)
    market = np.where(num.str.startswith("6"), "sh", "sz")
    df["code"] = [f"{m}.{n}" for m, n in zip(market, num)]
    return df[["code", "industry"]].drop_duplicates("code")


def build_panels(stock_data: dict[str, pd.DataFrame], calendar) -> dict[str, pd.DataFrame]:
    """Build wide daily panels indexed by trading date."""
    idx = pd.DatetimeIndex(sorted(pd.to_datetime(calendar)))
    fields = {
        "ret": {}, "turn": {}, "amount": {}, "pe": {}, "pb": {},
        "cap": {}, "close": {}, "valid": {},
    }
    for code, df in stock_data.items():
        d = df.set_index("date").reindex(idx)
        ret = d["pctChg"] / 100.0
        fields["ret"][code] = ret
        fields["turn"][code] = d["turn"]
        fields["amount"][code] = d["amount"]
        fields["pe"][code] = d["peTTM"]
        fields["pb"][code] = d["pbMRQ"]
        fields["cap"][code] = d["float_mktcap"]
        fields["close"][code] = d["close"]
        valid = ((d["tradestatus"] == 1) & (d["isST"] == 0) &
                 (d["close"] > 0) & d["close"].notna())
        fields["valid"][code] = valid.astype(float)

    panels = {k: pd.DataFrame(v).sort_index() for k, v in fields.items()}
    # cumulative return index (suspension -> 0 return, no jump)
    panels["cum"] = (1.0 + panels["ret"].fillna(0.0)).cumprod()
    return panels


def month_end_dates(calendar, start, end) -> list[pd.Timestamp]:
    s = pd.Series(pd.to_datetime(calendar))
    s = s[(s >= pd.Timestamp(start)) & (s <= pd.Timestamp(end))]
    if s.empty:
        return []
    ends = s.groupby(s.dt.to_period("M")).max()
    return sorted(pd.Timestamp(x) for x in ends.tolist())


def execution_pairs(calendar, signal_dates, end) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    cal = sorted(pd.to_datetime(calendar))
    pairs = []
    for s in signal_dates:
        s = pd.Timestamp(s)
        nxt = next((d for d in cal if d > s), None)
        if nxt is None or nxt > pd.Timestamp(end):
            continue
        pairs.append((s, nxt))
    return pairs


def forward_returns(cum_panel: pd.DataFrame, signal_dates, horizons=(1, 3, 6, 12)) -> dict[str, pd.DataFrame]:
    """Signal-to-signal forward returns for each horizon (in months)."""
    dates = list(signal_dates)
    out = {}
    for h in horizons:
        rows = {}
        for i, t in enumerate(dates):
            j = i + h
            if j >= len(dates):
                continue
            t2 = dates[j]
            if t not in cum_panel.index or t2 not in cum_panel.index:
                continue
            rows[t] = cum_panel.loc[t2] / cum_panel.loc[t] - 1.0
        out[f"fwd_{h}m"] = pd.DataFrame(rows).T
    return out
