"""Factor validity tests: IC, quantile portfolios, correlation and decay."""

from __future__ import annotations

import numpy as np
import pandas as pd

import config

ANALYSIS_FACTORS = config.FACTORS + ["value"]


def _period(d: pd.Timestamp) -> str:
    if d <= pd.Timestamp(config.TRAIN_END):
        return "训练期(2018-2021)"
    if d < pd.Timestamp("2026-01-01"):
        return "验证期(2022-2025)"
    return "样本外(2026)"


def ic_detail(panel: pd.DataFrame, factors=None, ret_col="fwd_ret") -> pd.DataFrame:
    factors = factors or ANALYSIS_FACTORS
    rows = []
    for t, g in panel.groupby("date"):
        d = g.dropna(subset=[ret_col])
        if len(d) < 30:
            continue
        for f in factors:
            sub = d[[f, ret_col]].dropna()
            if len(sub) < 30:
                continue
            rows.append({"date": t, "factor": f,
                         "ic": sub[f].corr(sub[ret_col], method="spearman")})
    out = pd.DataFrame(rows)
    if not out.empty:
        out["period"] = out["date"].apply(_period)
        out["year"] = out["date"].dt.year
    return out


def ic_summary(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame()
    rows = []
    groups = [("全样本", detail)]
    for p in ["训练期(2018-2021)", "验证期(2022-2025)", "样本外(2026)"]:
        sub = detail[detail["period"] == p]
        if len(sub):
            groups.append((p, sub))
    for name, sub in groups:
        for f, g in sub.groupby("factor"):
            ic = g["ic"].dropna()
            if len(ic) < 3:
                continue
            mean, std = ic.mean(), ic.std(ddof=1)
            icir = mean / std if std else np.nan
            tstat = icir * np.sqrt(len(ic)) if np.isfinite(icir) else np.nan
            rows.append({
                "period": name, "factor": f,
                "name": config.FACTOR_NAMES.get(f, f),
                "mean_ic": mean, "ic_std": std, "icir": icir,
                "t_stat": tstat, "positive_ratio": (ic > 0).mean(),
                "n_periods": len(ic),
            })
    return pd.DataFrame(rows)


def ic_by_year(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame()
    return (detail.pivot_table(index="factor", columns="year", values="ic",
                               aggfunc="mean")
            .reindex(config.FACTORS))


def quantile_detail(panel, factor, n_quantiles=None, ret_col="fwd_ret"):
    nq = n_quantiles or config.N_QUANTILES
    rows = []
    for t, g in panel.groupby("date"):
        d = g[[factor, ret_col]].dropna()
        if len(d) < nq * 8:
            continue
        labels = pd.qcut(d[factor].rank(method="first"), nq, labels=False) + 1
        grp = d.groupby(labels)[ret_col].mean()
        for q, r in grp.items():
            rows.append({"date": t, "quantile": int(q), "ret": r})
    return pd.DataFrame(rows)


def quantile_summary(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame()
    s = detail.groupby("quantile")["ret"].agg(["mean", "std", "count"]).reset_index()
    s["annualized"] = (1.0 + s["mean"]) ** 12 - 1.0
    s["t_stat"] = s["mean"] / (s["std"] / np.sqrt(s["count"]))
    return s


def long_short_table(panel, factors=None, n_quantiles=None) -> pd.DataFrame:
    factors = factors or ANALYSIS_FACTORS
    nq = n_quantiles or config.N_QUANTILES
    rows = []
    for f in factors:
        ser = {}
        for t, g in panel.groupby("date"):
            d = g[[f, "fwd_ret"]].dropna()
            if len(d) < nq * 8:
                continue
            labels = pd.qcut(d[f].rank(method="first"), nq, labels=False) + 1
            grp = d.groupby(labels)["fwd_ret"].mean()
            if 1 in grp.index and nq in grp.index:
                ser[t] = grp.loc[nq] - grp.loc[1]
        if len(ser) < 12:
            continue
        s = pd.Series(ser)
        rows.append({
            "factor": f, "name": config.FACTOR_NAMES.get(f, f),
            "ls_monthly_mean": s.mean(), "ls_annualized": s.mean() * 12,
            "ls_t_stat": s.mean() / s.std(ddof=1) * np.sqrt(len(s)),
            "win_ratio": (s > 0).mean(), "n_periods": len(s),
        })
    return pd.DataFrame(rows).sort_values("ls_monthly_mean", ascending=False)


def factor_correlation(panel, factors=None) -> pd.DataFrame:
    factors = factors or ANALYSIS_FACTORS
    rows = []
    for t, g in panel.groupby("date"):
        c = g[factors].corr(method="spearman")
        c["date"] = t
        rows.append(c.reset_index().rename(columns={"index": "f1"}))
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows).groupby("f1")[factors].mean()


def ic_decay(panel, factors=None, horizons=(1, 3, 6, 12)) -> pd.DataFrame:
    factors = factors or ANALYSIS_FACTORS
    rows = []
    for h in horizons:
        col = f"fwd_{h}m"
        if col not in panel.columns:
            continue
        for f in factors:
            vals = []
            for t, g in panel.groupby("date"):
                d = g[[f, col]].dropna()
                if len(d) < 30:
                    continue
                vals.append(d[f].corr(d[col], method="spearman"))
            if vals:
                rows.append({"horizon": h, "factor": f,
                             "mean_ic": np.mean(vals),
                             "t_stat": np.mean(vals) / np.std(vals, ddof=1)
                             * np.sqrt(len(vals))})
    return pd.DataFrame(rows)


def save_analysis(panel, out_dir=None):
    out_dir = out_dir or config.TABLE_DIR
    detail = ic_detail(panel)
    summary = ic_summary(detail)
    years = ic_by_year(detail)
    ls = long_short_table(panel)
    corr = factor_correlation(panel)
    decay = ic_decay(panel)

    detail.to_csv(out_dir / "ic_detail.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(out_dir / "ic_summary.csv", index=False, encoding="utf-8-sig")
    years.to_csv(out_dir / "ic_by_year.csv", encoding="utf-8-sig")
    ls.to_csv(out_dir / "long_short.csv", index=False, encoding="utf-8-sig")
    corr.to_csv(out_dir / "factor_correlation.csv", encoding="utf-8-sig")
    decay.to_csv(out_dir / "ic_decay.csv", index=False, encoding="utf-8-sig")

    q_tables = {}
    for f in ["vol_20", "turn_20", "ivol_60", "size", "value"]:
        det = quantile_detail(panel, f)
        summ = quantile_summary(det)
        q_tables[f] = (det, summ)
        if not summ.empty:
            summ.to_csv(out_dir / f"quantile_{f}.csv", index=False, encoding="utf-8-sig")
    return {"ic_detail": detail, "ic_summary": summary, "ic_by_year": years,
            "long_short": ls, "correlation": corr, "ic_decay": decay,
            "quantiles": q_tables}
