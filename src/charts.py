"""All report figures."""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150
plt.rcParams["savefig.dpi"] = 180


def _save(fig, name):
    path = config.FIG_DIR / f"{name}.png"
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def plot_nav(results: dict, name="fig_nav"):
    fig, ax = plt.subplots(figsize=(10, 5.2))
    for label, res in results.items():
        ax.plot(res.index, res["nav"], label=label, linewidth=1.8)
    ax.set(xlabel="日期", ylabel="累计净值（初始=1）", title="净值曲线对比")
    ax.grid(alpha=0.25)
    ax.legend(loc="upper left", frameon=False)
    return _save(fig, name)


def plot_drawdown(results: dict, name="fig_drawdown"):
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for label, res in results.items():
        dd = res["nav"] / res["nav"].cummax() - 1.0
        ax.plot(dd.index, dd, label=label, linewidth=1.3)
    ax.set(xlabel="日期", ylabel="回撤", title="回撤曲线")
    ax.grid(alpha=0.25)
    ax.legend(loc="lower left", frameon=False)
    return _save(fig, name)


def plot_annual(annual: pd.DataFrame, name="fig_annual"):
    cols = [c for c in ["基准模型", "研究模型", "沪深300"] if c in annual.columns]
    if not cols:
        cols = list(annual.columns[:2])
    fig, ax = plt.subplots(figsize=(10, 4.5))
    x = np.arange(len(annual))
    w = 0.8 / len(cols)
    for i, c in enumerate(cols):
        ax.bar(x + (i - (len(cols) - 1) / 2) * w, annual[c] * 100, w,
               label=c)
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(annual.index)
    ax.set(xlabel="年份", ylabel="收益率（%）", title="分年度收益对比")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.25)
    return _save(fig, name)


def plot_ic_bar(summary: pd.DataFrame, name="fig_ic"):
    d = summary[summary["period"] == "全样本"].copy()
    d = d.sort_values("mean_ic")
    fig, ax = plt.subplots(figsize=(9, 6))
    colors = ["#2f6f9f" if v >= 0 else "#b04a4a" for v in d["mean_ic"]]
    ax.barh(d["name"], d["mean_ic"], color=colors, alpha=0.85)
    ax.axvline(0, color="black", linewidth=0.8)
    for i, (v, t) in enumerate(zip(d["mean_ic"], d["t_stat"])):
        ax.text(v + (0.001 if v >= 0 else -0.001), i,
                f"{v:.3f} (t={t:.1f})", va="center",
                ha="left" if v >= 0 else "right", fontsize=8)
    ax.set(xlabel="月度Rank IC均值", title="全样本因子IC均值（括号内为t值）")
    ax.grid(axis="x", alpha=0.25)
    return _save(fig, name)


def plot_ic_heatmap(ic_year: pd.DataFrame, name="fig_ic_heatmap"):
    d = ic_year.copy()
    labels = [config.FACTOR_NAMES.get(i, i) for i in d.index]
    fig, ax = plt.subplots(figsize=(9, 7))
    im = ax.imshow(d.to_numpy(dtype=float), cmap="RdBu_r", aspect="auto",
                   vmin=-0.15, vmax=0.15)
    ax.set_xticks(range(len(d.columns)))
    ax.set_xticklabels(d.columns, rotation=0)
    ax.set_yticks(range(len(d)))
    ax.set_yticklabels(labels)
    for i in range(d.shape[0]):
        for j in range(d.shape[1]):
            v = d.iloc[i, j]
            if pd.notna(v):
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=ax, label="IC均值")
    ax.set_title("分年度因子IC均值")
    return _save(fig, name)


def plot_quantiles(q_tables: dict, name="fig_quantile"):
    items = [(k, v) for k, v in q_tables.items() if not v[1].empty][:2]
    if not items:
        return None
    fig, axes = plt.subplots(1, len(items), figsize=(6 * len(items), 4.2))
    if len(items) == 1:
        axes = [axes]
    for ax, (f, (_, summ)) in zip(axes, items):
        ax.bar(summ["quantile"], summ["annualized"] * 100, color="#2f6f9f", alpha=0.85)
        ax.axhline(0, color="gray", linewidth=0.8)
        ax.set(xlabel="分组（1=最低，5=最高）", ylabel="年化收益（%）",
               title=f"{config.FACTOR_NAMES.get(f, f)} 分组年化收益")
        ax.grid(axis="y", alpha=0.25)
    return _save(fig, name)


def plot_corr(corr: pd.DataFrame, name="fig_factor_corr"):
    labels = [config.FACTOR_NAMES.get(i, i) for i in corr.index]
    fig, ax = plt.subplots(figsize=(9, 7.5))
    im = ax.imshow(corr.to_numpy(dtype=float), cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr)))
    ax.set_xticklabels(labels, rotation=60, ha="right", fontsize=8)
    ax.set_yticks(range(len(corr)))
    ax.set_yticklabels(labels, fontsize=8)
    for i in range(corr.shape[0]):
        for j in range(corr.shape[1]):
            v = corr.iloc[i, j]
            if pd.notna(v):
                ax.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=6)
    fig.colorbar(im, ax=ax, label="平均截面Spearman相关系数")
    ax.set_title("因子相关性")
    return _save(fig, name)


def plot_exposure(exposure: pd.DataFrame, name="fig_exposure"):
    fig, ax = plt.subplots(figsize=(10, 4.8))
    for c in exposure.columns:
        ax.plot(exposure.index, exposure[c],
                label=config.FACTOR_NAMES.get(c, c), linewidth=1.5)
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set(xlabel="日期", ylabel="组合加权平均暴露（z值）", title="研究模型风格暴露")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, ncol=2)
    return _save(fig, name)


def plot_attribution(attr: pd.DataFrame, name="fig_attribution"):
    cols = [c for c in attr.columns if c.startswith("contrib_")]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    cum = attr[cols].cumsum()
    for c in cols:
        ax.plot(cum.index, cum[c] * 100,
                label=config.FACTOR_NAMES.get(c.replace("contrib_", ""), c),
                linewidth=1.5)
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set(xlabel="日期", ylabel="累计贡献（%）", title="研究模型收益的因子归因（加总口径）")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, ncol=2)
    return _save(fig, name)


def plot_rolling(rolling: pd.DataFrame, name="fig_rolling"):
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    axes[0].plot(rolling.index, rolling["rolling_excess"] * 100,
                 color="#2f6f9f", linewidth=1.5)
    axes[0].axhline(0, color="gray", linewidth=0.8)
    axes[0].set(ylabel="滚动12月超额（%）")
    axes[0].grid(alpha=0.25)
    axes[1].plot(rolling.index, rolling["rolling_sharpe"],
                 color="#b04a4a", linewidth=1.5)
    axes[1].axhline(0, color="gray", linewidth=0.8)
    axes[1].set(xlabel="日期", ylabel="滚动1年夏普")
    axes[1].grid(alpha=0.25)
    fig.suptitle("滚动业绩稳定性")
    return _save(fig, name)


def plot_stress(stress: pd.DataFrame, name="fig_stress"):
    fig, ax = plt.subplots(figsize=(10, 4.2))
    x = np.arange(len(stress))
    ax.bar(x - 0.2, stress["组合收益"] * 100, 0.4, label="研究模型")
    ax.bar(x + 0.2, stress["基准收益"] * 100, 0.4, label="沪深300")
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(stress["区间"], rotation=20, ha="right")
    ax.set(ylabel="区间收益（%）", title="极端行情压力测试")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.25)
    return _save(fig, name)


def plot_capacity(cap: pd.DataFrame, name="fig_capacity"):
    d = cap[cap["AUM(亿元)"] <= 50].copy()
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    ax.plot(d["AUM(亿元)"], d["参与率中位数"] * 100, marker="o", label="中位数")
    ax.plot(d["AUM(亿元)"], d["参与率95分位"] * 100, marker="s", label="95分位")
    ax.axhline(10, color="#b04a4a", linestyle="--", linewidth=1, label="10%参与率上限")
    ax.set_xscale("log")
    ax.set_ylim(0, 400)
    ax.set(xlabel="管理规模AUM（亿元，对数轴）", ylabel="持仓占20日日均成交额（%）",
           title="容量测算：调仓参与率随规模变化")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    return _save(fig, name)


def plot_fee(fee: pd.DataFrame, name="fig_fee"):
    fig, ax = plt.subplots(figsize=(9, 4.5))
    labels = [f"{m*100:.1f}%+{p*100:.0f}%" for m, p in zip(fee["管理费"], fee["业绩报酬"])]
    x = np.arange(len(fee))
    ax.bar(x - 0.2, fee["费后年化"] * 100, 0.4, label="费后年化收益")
    ax.bar(x + 0.2, fee["费率侵蚀"] * 100, 0.4, label="费率侵蚀")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set(xlabel="管理费+业绩报酬", ylabel="年化（%）", title="不同费率情景下的费后收益")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.25)
    return _save(fig, name)


def plot_industry(industry_avg: pd.Series, name="fig_industry"):
    d = pd.concat([industry_avg.head(10), industry_avg.tail(10)]).sort_values()
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    colors = ["#2f6f9f" if v >= 0 else "#b04a4a" for v in d.values]
    ax.barh(d.index, d.values * 100, color=colors, alpha=0.85)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.tick_params(axis="y", labelsize=8)
    ax.set(xlabel="平均主动行业权重（%，组合-等权沪深300）", title="行业配置偏离（最高10个与最低10个）")
    ax.grid(axis="x", alpha=0.25)
    return _save(fig, name)


def plot_turnover(turnover: pd.DataFrame, name="fig_turnover"):
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.bar(turnover["exec_date"], turnover["turnover_oneway"] * 100,
           width=20, color="#2f6f9f", alpha=0.8)
    ax.set(xlabel="调仓日", ylabel="单边换手率（%）", title="月度调仓换手率")
    ax.grid(axis="y", alpha=0.25)
    return _save(fig, name)


def plot_sensitivity(sens: pd.DataFrame, name="fig_sensitivity"):
    piv = sens.pivot(index="top_n", columns="cost", values="sharpe")
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    im = ax.imshow(piv.to_numpy(dtype=float), cmap="YlGnBu", aspect="auto")
    ax.set_xticks(range(len(piv.columns)))
    ax.set_xticklabels([f"{c*100:.2f}%" for c in piv.columns])
    ax.set_yticks(range(len(piv.index)))
    ax.set_yticklabels(piv.index)
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.iloc[i, j]
            if pd.notna(v):
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=9)
    fig.colorbar(im, ax=ax, label="夏普比率")
    ax.set(xlabel="单边交易成本", ylabel="持仓数量", title="参数敏感性：夏普比率")
    return _save(fig, name)


def plot_live(live: pd.DataFrame, name="fig_live"):
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.plot(live.index, live["nav"], label="研究模型", linewidth=1.6)
    ax.plot(live.index, live["bm_nav"], label="沪深300", linewidth=1.6)
    ax.set(xlabel="日期", ylabel="累计净值（2025年末=1）",
           title="2026年样本外模拟净值")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    return _save(fig, name)
