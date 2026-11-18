"""Capacity, fee and stress-test analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd

import config


def capacity_analysis(holdings, amount_panel, aum_grid=None):
    aum_grid = aum_grid or [1e8, 2e8, 5e8, 1e9, 2e9, 5e9, 1e10, 2e10, 5e10]
    adv = {}
    for signal, h in holdings.groupby("signal_date"):
        sig = pd.Timestamp(signal)
        hist = amount_panel.loc[:sig].tail(20)
        adv[sig] = hist.mean().reindex(h["code"].unique())
    rows = []
    for aum in aum_grid:
        parts, days = [], []
        for signal, h in holdings.groupby("signal_date"):
            sig = pd.Timestamp(signal)
            a = adv.get(sig)
            if a is None:
                continue
            n = len(h)
            pos = aum / n
            p = pos / a.replace(0, np.nan)
            parts.extend(p.dropna().tolist())
            days.extend((p / 0.2).dropna().tolist())
        if not parts:
            continue
        parts = np.array(parts)
        days = np.array(days)
        rows.append({
            "AUM(亿元)": aum / 1e8,
            "参与率中位数": np.median(parts),
            "参与率95分位": np.percentile(parts, 95),
            "参与率最大值": parts.max(),
            "20%参与率下交易日中位数": np.median(days),
            "20%参与率下交易日95分位": np.percentile(days, 95),
        })
    return pd.DataFrame(rows)


def max_capacity(cap_table, max_participation=0.10):
    if cap_table.empty:
        return np.nan
    ok = cap_table[cap_table["参与率95分位"] <= max_participation]
    return ok["AUM(亿元)"].max() if len(ok) else np.nan


def fee_scenarios(gross_ann, bm_ann, vol, rf=None, custody=0.002):
    rf = config.RISK_FREE if rf is None else rf
    scenarios = [
        (0.008, 0.0), (0.010, 0.0), (0.010, 0.10),
        (0.012, 0.15), (0.015, 0.20),
    ]
    rows = []
    for mgmt, perf in scenarios:
        base = mgmt + custody
        perf_fee = perf * max(0.0, gross_ann - bm_ann - base)
        net = gross_ann - base - perf_fee
        rows.append({
            "管理费": mgmt, "托管费": custody, "业绩报酬": perf,
            "固定费合计": base, "业绩报酬计提": perf_fee,
            "费后年化": net, "费后超额": net - bm_ann,
            "费后夏普": (net - rf) / vol if vol else np.nan,
            "费率侵蚀": gross_ann - net,
        })
    return pd.DataFrame(rows)


def terminal_wealth(gross_ann, net_ann, years=5, initial=1_000_000):
    return pd.DataFrame({
        "持有年限": range(1, years + 1),
        "费前终值": [initial * (1 + gross_ann) ** y for y in range(1, years + 1)],
        "费后终值": [initial * (1 + net_ann) ** y for y in range(1, years + 1)],
    }).assign(差额=lambda d: d["费前终值"] - d["费后终值"])


STRESS_PERIODS = {
    "2018年熊市": ("2018-01-01", "2018-12-31"),
    "2020年新冠冲击": ("2020-01-20", "2020-03-23"),
    "2021年核心资产回调": ("2021-02-10", "2021-03-09"),
    "2022年熊市": ("2022-01-01", "2022-12-31"),
    "2024年小盘流动性危机": ("2024-01-01", "2024-02-05"),
    "2025年4月关税冲击": ("2025-04-01", "2025-04-30"),
    "2026年样本外": ("2026-01-01", "2026-11-11"),
}
