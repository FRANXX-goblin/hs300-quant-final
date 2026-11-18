"""Fama-MacBeth cross-sectional regressions and return attribution."""

from __future__ import annotations

import numpy as np
import pandas as pd

import config


def _ols(y, X):
    X = np.column_stack([np.ones(len(X)), X])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return coef, resid, r2, X


def fama_macbeth(panel: pd.DataFrame, factors=None, ret_col="fwd_excess"):
    factors = factors or config.ATTRIBUTION_FACTORS
    rows, resid_rows = [], []
    for t, g in panel.groupby("date"):
        d = g[factors + [ret_col, "code"]].dropna()
        if len(d) < 30:
            continue
        y = d[ret_col].to_numpy(dtype=float)
        X = d[factors].to_numpy(dtype=float)
        coef, resid, r2, Xfull = _ols(y, X)
        # White standard errors
        XtX_inv = np.linalg.pinv(Xfull.T @ Xfull)
        meat = (Xfull * (resid ** 2)[:, None]).T @ Xfull
        cov = XtX_inv @ meat @ XtX_inv
        se = np.sqrt(np.clip(np.diag(cov), 0, None))
        rec = {"date": t, "const": coef[0], "r2": r2, "n": len(d)}
        for i, f in enumerate(factors, 1):
            rec[f] = coef[i]
            rec[f + "_t"] = coef[i] / se[i] if se[i] > 0 else np.nan
        rows.append(rec)
        resid_rows.append(pd.Series(resid, index=d["code"].to_numpy(), name=t))
    factor_returns = pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()
    residuals = pd.DataFrame(resid_rows).T if resid_rows else pd.DataFrame()

    summary = []
    if not factor_returns.empty:
        for f in factors + ["const"]:
            s = factor_returns[f].dropna()
            mean, std = s.mean(), s.std(ddof=1)
            t = mean / std * np.sqrt(len(s)) if std else np.nan
            summary.append({
                "factor": f, "name": config.FACTOR_NAMES.get(f, f),
                "mean_monthly": mean, "annualized": mean * 12,
                "std": std, "t_stat": t, "n": len(s),
            })
    summary = pd.DataFrame(summary)
    return factor_returns, summary, residuals


def portfolio_attribution(panel, holdings, factor_returns, factors=None,
                           cost_by_signal=None, ret_col="fwd_excess"):
    factors = factors or config.ATTRIBUTION_FACTORS
    rows = []
    by_date = {t: g.set_index("code") for t, g in panel.groupby("date")}
    for signal, h in holdings.groupby("signal_date"):
        g = by_date.get(pd.Timestamp(signal))
        if g is None or signal not in factor_returns.index:
            continue
        codes = [c for c in h["code"] if c in g.index]
        if len(codes) < 5:
            continue
        w = h.set_index("code").loc[codes, "weight"].to_numpy(dtype=float)
        w = w / w.sum()
        d = g.loc[codes]
        exposures = {f: float(np.sum(w * d[f].fillna(0.0).to_numpy())) for f in factors}
        lam = factor_returns.loc[signal]
        port_ret = float(np.sum(w * d[ret_col].fillna(0.0).to_numpy()))
        contrib = {f: exposures[f] * lam[f] for f in factors}
        intercept = float(lam["const"])
        specific = port_ret - intercept - sum(contrib.values())
        cost = float(cost_by_signal.get(signal, 0.0)) if cost_by_signal is not None else 0.0
        rec = {"date": pd.Timestamp(signal), "port_ret": port_ret,
               "intercept": intercept, "specific": specific, "cost": cost,
               "net_ret": port_ret - cost, "n": len(codes)}
        rec.update({f"contrib_{f}": contrib[f] for f in factors})
        rec.update({f"exposure_{f}": exposures[f] for f in factors})
        rows.append(rec)
    out = pd.DataFrame(rows).set_index("date").sort_index() if rows else pd.DataFrame()
    return out


def attribution_summary(attr: pd.DataFrame, factors=None) -> pd.DataFrame:
    factors = factors or config.ATTRIBUTION_FACTORS
    if attr.empty:
        return pd.DataFrame()
    total = attr["port_ret"].sum()
    rows = []
    for col, name in [("intercept", "截距项")] + \
                     [(f"contrib_{f}", config.FACTOR_NAMES.get(f, f)) for f in factors] + \
                     [("specific", "特质收益")]:
        s = attr[col]
        rows.append({
            "项目": name, "月均贡献": s.mean(), "年化贡献": s.mean() * 12,
            "累计贡献": s.sum(), "占超额收益比例": s.sum() / total if total else np.nan,
            "胜率": (s > 0).mean(),
        })
    return pd.DataFrame(rows)


def style_exposure(panel, holdings, factors=None) -> pd.DataFrame:
    factors = factors or config.ATTRIBUTION_FACTORS
    by_date = {t: g.set_index("code") for t, g in panel.groupby("date")}
    rows = []
    for signal, h in holdings.groupby("signal_date"):
        g = by_date.get(pd.Timestamp(signal))
        if g is None:
            continue
        codes = [c for c in h["code"] if c in g.index]
        if not codes:
            continue
        w = h.set_index("code").loc[codes, "weight"].to_numpy(dtype=float)
        w = w / w.sum()
        d = g.loc[codes]
        rec = {"date": pd.Timestamp(signal)}
        for f in factors:
            rec[f] = float(np.sum(w * d[f].fillna(0.0).to_numpy()))
        rows.append(rec)
    return pd.DataFrame(rows).set_index("date").sort_index() if rows else pd.DataFrame()


def industry_exposure(panel, holdings):
    by_date = {t: g.set_index("code") for t, g in panel.groupby("date")}
    rows = []
    for signal, h in holdings.groupby("signal_date"):
        g = by_date.get(pd.Timestamp(signal))
        if g is None:
            continue
        codes = [c for c in h["code"] if c in g.index]
        if not codes:
            continue
        hh = h.set_index("code").loc[codes]
        w = hh["weight"] / hh["weight"].sum()
        port = w.groupby(hh["industry"]).sum()
        uni = pd.Series(1.0, index=g.index).groupby(g["industry"]).sum()
        uni = uni / uni.sum()
        for ind in sorted(set(port.index) | set(uni.index)):
            rows.append({"date": pd.Timestamp(signal), "industry": ind,
                         "portfolio": float(port.get(ind, 0.0)),
                         "universe": float(uni.get(ind, 0.0)),
                         "active": float(port.get(ind, 0.0) - uni.get(ind, 0.0))})
    return pd.DataFrame(rows)


def risk_decomposition(attr: pd.DataFrame, factor_returns: pd.DataFrame,
                       factors=None) -> pd.DataFrame:
    factors = factors or config.ATTRIBUTION_FACTORS
    if attr.empty or factor_returns.empty:
        return pd.DataFrame()
    contrib = attr[[f"contrib_{f}" for f in factors]].dropna()
    if contrib.empty:
        return pd.DataFrame()
    var_factor = contrib.sum(axis=1).var(ddof=1)
    var_specific = attr["specific"].var(ddof=1)
    total = var_factor + var_specific
    rows = [{"来源": "因子共同风险", "月度方差": var_factor,
             "占比": var_factor / total if total else np.nan},
            {"来源": "特质风险", "月度方差": var_specific,
             "占比": var_specific / total if total else np.nan}]
    # individual factor marginal contribution via covariance
    for f in factors:
        c = np.cov(contrib[f"contrib_{f}"], contrib.sum(axis=1), ddof=1)[0, 1]
        rows.append({"来源": config.FACTOR_NAMES.get(f, f), "月度方差": c,
                     "占比": c / total if total else np.nan})
    return pd.DataFrame(rows)
