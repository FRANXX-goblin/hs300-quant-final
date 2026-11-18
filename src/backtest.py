"""Monthly-rebalanced long-only backtest engine and performance metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd

import config


def run_backtest(
    calendar,
    pairs,
    selections,
    ret_panel,
    benchmark,
    end,
    cost_rate=None,
    initial_nav=1.0,
):
    """Run a long-only equal-weight portfolio.

    ``cost_rate`` is the one-side transaction cost.  One-way turnover is
    ``0.5 * sum(abs(target - current))``; both the sell and the buy leg are
    charged, hence the round-trip cost is ``2 * turnover * cost_rate``.
    """
    cost_rate = config.COST_RATE if cost_rate is None else cost_rate
    cal = sorted(pd.to_datetime(calendar))
    exec_to_signal = {pd.Timestamp(e): pd.Timestamp(s) for s, e in pairs}
    if not pairs:
        raise ValueError("no valid rebalance periods")
    first_exec = pd.Timestamp(pairs[0][1])
    last_date = min(pd.Timestamp(end), cal[-1])
    dates = [d for d in cal if first_exec <= d <= last_date]

    weights = {}
    nav = initial_nav
    records, turnover_log, holdings_log = [], [], []

    for d in dates:
        row = ret_panel.loc[d] if d in ret_panel.index else None
        gross = 0.0
        if weights:
            for code, w in weights.items():
                r = row.get(code, np.nan) if row is not None else np.nan
                if pd.notna(r):
                    gross += w * r

        if weights:
            denom = 1.0 + gross
            new_w = {}
            for code, w in weights.items():
                r = row.get(code, 0.0) if row is not None else 0.0
                if pd.isna(r):
                    r = 0.0
                new_w[code] = w * (1.0 + r) / denom if denom != 0 else w
            weights = new_w

        cost = 0.0
        turnover = 0.0
        if d in exec_to_signal:
            signal = exec_to_signal[d]
            codes = [c for c in selections.get(signal, []) if c in ret_panel.columns]
            if codes:
                target = {c: 1.0 / len(codes) for c in codes}
                universe = set(target) | set(weights)
                turnover = 0.5 * sum(abs(target.get(c, 0.0) - weights.get(c, 0.0))
                                     for c in universe)
                cost = 2.0 * turnover * cost_rate
                turnover_log.append({
                    "signal_date": signal, "exec_date": d,
                    "turnover_oneway": turnover, "cost": cost,
                    "n_holdings": len(codes),
                })
                for c, w in target.items():
                    holdings_log.append({
                        "signal_date": signal, "exec_date": d,
                        "code": c, "weight": w,
                    })
                weights = target

        net = (1.0 + gross) * (1.0 - cost) - 1.0
        nav *= (1.0 + net)
        records.append({
            "date": d, "ret": net, "gross_ret": gross,
            "cost": cost, "turnover": turnover, "nav": nav,
        })

    daily = pd.DataFrame(records).set_index("date")
    bm = benchmark.copy()
    bm["date"] = pd.to_datetime(bm["date"])
    bm = bm.set_index("date").sort_index()
    bm_ret = bm["ret"].reindex(daily.index).fillna(0.0)
    daily["bm_ret"] = bm_ret
    daily["bm_nav"] = (1.0 + bm_ret).cumprod()
    daily["excess_nav"] = daily["nav"] / daily["bm_nav"]
    daily["excess_ret"] = daily["ret"] - daily["bm_ret"]
    return daily, pd.DataFrame(turnover_log), pd.DataFrame(holdings_log)


def drawdown_series(nav: pd.Series) -> pd.Series:
    return nav / nav.cummax() - 1.0


def calc_metrics(result: pd.DataFrame, rf=None) -> tuple[dict, pd.Series]:
    rf = config.RISK_FREE if rf is None else rf
    ret = result["ret"].dropna()
    bm = result["bm_ret"].reindex(ret.index).fillna(0.0)
    nav = result["nav"].reindex(ret.index)
    n = len(ret)
    if n < 20:
        raise ValueError("not enough observations")

    ann = nav.iloc[-1] ** (252.0 / n) - 1.0
    vol = ret.std(ddof=1) * np.sqrt(252)
    sharpe = (ann - rf) / vol if vol else np.nan
    dd = drawdown_series(nav)
    mdd = dd.min()
    calmar = ann / abs(mdd) if mdd else np.nan

    bm_nav = (1.0 + bm).cumprod()
    bm_ann = bm_nav.iloc[-1] ** (252.0 / n) - 1.0
    bm_vol = bm.std(ddof=1) * np.sqrt(252)
    bm_sharpe = (bm_ann - rf) / bm_vol if bm_vol else np.nan
    bm_dd = drawdown_series(bm_nav).min()

    diff = ret - bm
    te = diff.std(ddof=1) * np.sqrt(252)
    ir = diff.mean() * 252 / te if te else np.nan
    beta = ret.cov(bm) / bm.var() if bm.var() else np.nan
    alpha = (ret.mean() - beta * bm.mean()) * 252 if np.isfinite(beta) else np.nan

    m_port = (1.0 + ret).resample("ME").prod() - 1.0
    m_bm = (1.0 + bm).resample("ME").prod() - 1.0
    monthly_win = (m_port > m_bm).mean()

    up = bm > 0
    down = bm < 0
    up_capture = (ret[up].mean() / bm[up].mean()) if up.any() and bm[up].mean() != 0 else np.nan
    down_capture = (ret[down].mean() / bm[down].mean()) if down.any() and bm[down].mean() != 0 else np.nan

    var95 = -ret.quantile(0.05)
    cvar95 = -ret[ret <= ret.quantile(0.05)].mean()
    best_month = m_port.max()
    worst_month = m_port.min()

    metrics = {
        "累计收益": nav.iloc[-1] - 1.0,
        "年化收益": ann,
        "年化波动": vol,
        "夏普比率": sharpe,
        "最大回撤": mdd,
        "卡玛比率": calmar,
        "基准累计收益": bm_nav.iloc[-1] - 1.0,
        "基准年化收益": bm_ann,
        "基准年化波动": bm_vol,
        "基准夏普比率": bm_sharpe,
        "基准最大回撤": bm_dd,
        "年化超额收益": ann - bm_ann,
        "跟踪误差": te,
        "信息比率": ir,
        "Beta": beta,
        "年化Alpha": alpha,
        "月度胜率": monthly_win,
        "上行捕获率": up_capture,
        "下行捕获率": down_capture,
        "日VaR95": var95,
        "日CVaR95": cvar95,
        "月度最佳": best_month,
        "月度最差": worst_month,
        "日收益偏度": ret.skew(),
        "日收益峰度": ret.kurtosis(),
        "交易日数": n,
    }
    return metrics, dd


def annual_returns(result: pd.DataFrame) -> pd.DataFrame:
    ret = result["ret"]
    bm = result["bm_ret"]
    p = (1.0 + ret).resample("YE").prod() - 1.0
    b = (1.0 + bm).resample("YE").prod() - 1.0
    out = pd.DataFrame({"组合": p.values, "基准": b.values}, index=p.index.year)
    out["超额"] = out["组合"] - out["基准"]
    out.index.name = "年份"
    return out


def monthly_returns(result: pd.DataFrame) -> pd.DataFrame:
    p = (1.0 + result["ret"]).resample("ME").prod() - 1.0
    b = (1.0 + result["bm_ret"]).resample("ME").prod() - 1.0
    out = pd.DataFrame({"组合": p, "基准": b})
    out["超额"] = out["组合"] - out["基准"]
    return out


def rolling_metrics(result: pd.DataFrame, window=252) -> pd.DataFrame:
    ret = result["ret"]
    bm = result["bm_ret"]
    ann_ret = (1.0 + ret).rolling(window).apply(np.prod, raw=True) ** (252 / window) - 1
    ann_bm = (1.0 + bm).rolling(window).apply(np.prod, raw=True) ** (252 / window) - 1
    vol = ret.rolling(window).std() * np.sqrt(252)
    sharpe = (ann_ret - config.RISK_FREE) / vol
    out = pd.DataFrame({
        "rolling_ann": ann_ret, "rolling_bm": ann_bm,
        "rolling_excess": ann_ret - ann_bm, "rolling_sharpe": sharpe,
    })
    return out.dropna()


def drawdown_table(result: pd.DataFrame, top=5) -> pd.DataFrame:
    nav = result["nav"]
    dd = drawdown_series(nav)
    episodes = []
    in_dd = False
    start = None
    for d, v in dd.items():
        if v < 0 and not in_dd:
            in_dd, start = True, d
        elif v == 0 and in_dd:
            seg = dd.loc[start:d]
            trough = seg.idxmin()
            episodes.append({
                "开始": start, "谷底": trough, "恢复": d,
                "最大回撤": seg.min(),
                "持续天数": (d - start).days,
                "修复天数": (d - trough).days,
            })
            in_dd = False
    if in_dd:
        seg = dd.loc[start:]
        trough = seg.idxmin()
        episodes.append({
            "开始": start, "谷底": trough, "恢复": pd.NaT,
            "最大回撤": seg.min(),
            "持续天数": (dd.index[-1] - start).days,
            "修复天数": np.nan,
        })
    out = pd.DataFrame(episodes).sort_values("最大回撤").head(top)
    return out.reset_index(drop=True)


def stress_periods(result: pd.DataFrame, periods: dict) -> pd.DataFrame:
    rows = []
    for name, (start, end) in periods.items():
        seg = result.loc[pd.Timestamp(start):pd.Timestamp(end)]
        if len(seg) < 2:
            continue
        p_ret = (1.0 + seg["ret"]).prod() - 1.0
        b_ret = (1.0 + seg["bm_ret"]).prod() - 1.0
        p_dd = drawdown_series((1.0 + seg["ret"]).cumprod()).min()
        b_dd = drawdown_series((1.0 + seg["bm_ret"]).cumprod()).min()
        rows.append({"区间": name, "组合收益": p_ret, "基准收益": b_ret,
                     "超额": p_ret - b_ret, "组合最大回撤": p_dd,
                     "基准最大回撤": b_dd})
    return pd.DataFrame(rows)
