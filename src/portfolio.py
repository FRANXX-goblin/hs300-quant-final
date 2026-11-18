"""Scoring models and portfolio construction."""

from __future__ import annotations

import pandas as pd

import config


def _factor_cols(model: str, neutralized: bool) -> list[str]:
    base = config.BASELINE_FACTORS if model == "baseline" else config.RESEARCH_FACTORS
    if not neutralized:
        return base
    out = []
    for c in base:
        out.append("value_zi" if c == "value" else f"{c}_zi")
    return out


def score_panel(panel: pd.DataFrame, model="research", neutralized=False) -> pd.Series:
    cols = _factor_cols(model, neutralized)
    z = panel[cols].astype(float)
    score = z.mean(axis=1, skipna=True)
    avail = z.notna().sum(axis=1)
    min_avail = max(2, len(cols) - 1)
    score = score.where(avail >= min_avail)
    return score


def select_portfolios(
    panel: pd.DataFrame,
    pairs,
    model="research",
    top_n=None,
    neutralized=False,
    industry_cap=None,
    score_col=None,
) -> tuple[dict, pd.DataFrame]:
    top_n = top_n or config.TOP_N
    p = panel.copy()
    if "code" in p.columns:
        p = p.set_index("code", drop=False)
    if score_col is None:
        p["_score"] = score_panel(p, model=model, neutralized=neutralized)
        score_col = "_score"
    by_date = {t: g for t, g in p.groupby("date")}
    selections, holdings = {}, []
    for signal, exec_date in pairs:
        g = by_date.get(pd.Timestamp(signal))
        if g is None:
            continue
        d = g.dropna(subset=[score_col]).sort_values(score_col, ascending=False)
        if d.empty:
            continue
        picked = []
        if industry_cap:
            counts = {}
            for code, row in d.iterrows():
                ind = row.get("industry", "其他")
                if counts.get(ind, 0) >= industry_cap:
                    continue
                picked.append(code)
                counts[ind] = counts.get(ind, 0) + 1
                if len(picked) >= top_n:
                    break
            if len(picked) < min(top_n, len(d)):
                for code in d.index:
                    if code not in picked:
                        picked.append(code)
                    if len(picked) >= top_n:
                        break
        else:
            picked = list(d.index[:top_n])
        if not picked:
            continue
        selections[signal] = picked
        w = 1.0 / len(picked)
        for rank, code in enumerate(picked, 1):
            holdings.append({
                "signal_date": pd.Timestamp(signal),
                "exec_date": pd.Timestamp(exec_date),
                "code": code,
                "rank": rank,
                "weight": w,
                "score": float(d.loc[code, score_col]),
                "industry": d.loc[code].get("industry", "其他"),
            })
    return selections, pd.DataFrame(holdings)
