"""Generate the Word technical report from saved tables and figures."""

from __future__ import annotations

import json

import pandas as pd
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

import config

CN_FONT = "宋体"
CN_HEAD = "黑体"
EN_FONT = "Times New Roman"
TABLE_DIR = config.TABLE_DIR
FIG_DIR = config.FIG_DIR


# ---------------------------------------------------------------------------
# basic helpers
# ---------------------------------------------------------------------------
def _read(name, **kwargs):
    return pd.read_csv(TABLE_DIR / name, encoding="utf-8-sig", **kwargs)


def pct(x, digits=2):
    if pd.isna(x):
        return "—"
    return f"{x * 100:.{digits}f}%"


def num(x, digits=2):
    if pd.isna(x):
        return "—"
    return f"{x:.{digits}f}"


def _set_run_font(run, size=12, bold=False, color=None, cn=CN_FONT, en=EN_FONT):
    run.font.name = en
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), cn)


def _shade(cell, color="D9E2F3"):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), color)
    tc_pr.append(shd)


def _body(doc, text, indent=True, size=12, bold=False, align="justify"):
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    p.paragraph_format.space_after = Pt(0)
    if indent:
        p.paragraph_format.first_line_indent = Pt(24)
    if align == "justify":
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    elif align == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    _set_run_font(run, size=size, bold=bold)
    return p


def _heading(doc, text, level=1):
    p = doc.add_heading(text, level=level)
    p.paragraph_format.space_before = Pt(10 if level == 1 else 6)
    p.paragraph_format.space_after = Pt(4)
    for run in p.runs:
        _set_run_font(run, size=16 if level == 1 else 13.5, bold=True, cn=CN_HEAD,
                      color=(0, 0, 0))
    return p


def _caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text)
    _set_run_font(run, size=10.5, bold=True, cn=CN_FONT)


def _note(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text)
    _set_run_font(run, size=9, color=(100, 100, 100))


def _table(doc, df, caption, font_size=9, index=False, max_rows=None):
    _caption(doc, caption)
    d = df.copy()
    if index:
        d = d.reset_index()
    if max_rows:
        d = d.head(max_rows)
    table = doc.add_table(rows=1, cols=len(d.columns))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = table.rows[0].cells
    for i, col in enumerate(d.columns):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(str(col))
        _set_run_font(run, size=font_size, bold=True)
        _shade(hdr[i])
    for _, row in d.iterrows():
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run("" if pd.isna(val) else str(val))
            _set_run_font(run, size=font_size)
    tr = table.rows[0]._tr
    tr_pr = tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)
    for row in table.rows:
        tr_pr = row._tr.get_or_add_trPr()
        cant = OxmlElement("w:cantSplit")
        tr_pr.append(cant)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def _figure(doc, name, caption, width_cm=15.0):
    path = FIG_DIR / f"{name}.png"
    if not path.exists():
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    run = p.add_run()
    run.add_picture(str(path), width=Cm(width_cm))
    _caption(doc, caption)


def _page_number(section):
    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("第 ")
    _set_run_font(run, size=9)
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    r = p.add_run()
    _set_run_font(r, size=9)
    r._r.append(fld_begin)
    r._r.append(instr)
    r._r.append(fld_end)
    run2 = p.add_run(" 页")
    _set_run_font(run2, size=9)


def _setup(doc):
    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.left_margin = Cm(2.55)
    sec.right_margin = Cm(2.55)
    sec.top_margin = Cm(2.55)
    sec.bottom_margin = Cm(2.55)
    style = doc.styles["Normal"]
    style.font.name = EN_FONT
    style.font.size = Pt(12)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)
    _page_number(sec)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
def build_report():
    metrics = _read("metrics.csv", index_col=0)
    annual = _read("annual_returns.csv", index_col=0)
    dd_table = _read("drawdown_table.csv")
    ic = _read("ic_summary.csv")
    ic_year = _read("ic_by_year.csv", index_col=0)
    ls = _read("long_short.csv")
    corr = _read("factor_correlation.csv", index_col=0)
    decay = _read("ic_decay.csv")
    premia = _read("attribution_factor_premia.csv")
    attr_sum = _read("attribution_summary.csv")
    style = _read("style_exposure.csv", index_col=0)
    ind_avg = _read("industry_active_avg.csv", index_col=0).iloc[:, 0]
    risk_dec = _read("risk_decomposition.csv")
    cap = _read("capacity.csv")
    fee = _read("fee.csv")
    stress = _read("stress.csv")
    sens = _read("sensitivity.csv")
    oos = _read("metrics_2026.csv", index_col=0)
    with open(TABLE_DIR / "info.json", encoding="utf-8") as f:
        info = json.load(f)

    r = metrics.loc["研究模型（+低波+低换手）"]
    b = metrics.loc["基准模型（价值+规模）"]
    h = metrics.loc["沪深300全收益指数"]
    prod = metrics.loc["产品实施版（行业≤10只）"]

    doc = Document()
    _setup(doc)

    # ---------------- 封面 ----------------
    for _ in range(3):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("《量化投资》课程期末项目")
    _set_run_font(run, size=16, bold=True, cn=CN_HEAD)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(20)
    run = p.add_run("沪深300低风险增强多因子策略")
    _set_run_font(run, size=26, bold=True, cn=CN_HEAD)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("——基于价值、规模、低波动与低换手因子的量化选股与产品化研究")
    _set_run_font(run, size=13, bold=False)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(26)
    run = p.add_run("产品名称：沪深300低风险增强一号")
    _set_run_font(run, size=13, bold=True)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("角色定位：私募证券投资基金（量化多头）")
    _set_run_font(run, size=12)

    doc.add_paragraph()
    members = pd.DataFrame(config.MEMBERS)
    members.columns = ["姓名", "学号", "分工"]
    m = doc.add_table(rows=1, cols=3)
    m.style = "Table Grid"
    m.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, c in enumerate(members.columns):
        cell = m.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(c)
        _set_run_font(run, size=10.5, bold=True)
        _shade(cell)
    for _, row in members.iterrows():
        cells = m.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run(str(v))
            _set_run_font(run, size=10.5)

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f"GitHub 代码仓库：{config.GITHUB_LINK}")
    _set_run_font(run, size=9)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f"雪球模拟组合：{config.XUEQIU_LINK}")
    _set_run_font(run, size=9)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(40)
    run = p.add_run("2026年12月")
    _set_run_font(run, size=12)

    doc.add_page_break()

    # ---------------- 摘要 ----------------
    _heading(doc, "摘要", 1)
    _body(doc,
          "本报告以沪深300指数历史成分股为股票池，构建了一个面向私募量化多头产品的低风险增强多因子策略。"
          "基准模型仅使用价值（EP、BP）与规模（小市值）两个传统因子；研究模型在基准模型上加入20日低波动"
          "与20日低换手两个核心因子，采用等权打分、月度调仓、持有综合得分前30名的多头组合。样本区间为"
          "2018年1月至2025年12月，并将2026年1月至11月作为样本外模拟区间。")
    _body(doc,
          f"回测结果显示，研究模型年化收益{pct(r['年化收益'])}，年化波动{pct(r['年化波动'])}，"
          f"夏普比率{num(r['夏普比率'], 3)}，最大回撤{pct(r['最大回撤'])}；同期沪深300全收益指数年化收益"
          f"{pct(h['年化收益'])}，年化波动{pct(h['年化波动'])}，最大回撤{pct(h['最大回撤'])}。"
          f"研究模型相对基准的年化超额为{pct(r['年化超额收益'])}，信息比率{num(r['信息比率'], 3)}，"
          f"月度胜率{pct(r['月度胜率'], 1)}。与仅含价值、规模的基准模型相比，研究模型的年化收益提高"
          f"{pct(r['年化收益'] - b['年化收益'])}，最大回撤由{pct(b['最大回撤'])}降至{pct(r['最大回撤'])}，"
          "说明低波动与低换手因子主要改善了组合的风险调整后收益。")
    _body(doc,
          "收益归因表明，研究模型的超额收益并非来自线性因子贝塔，而是更多来自综合得分顶端的选股效应与"
          "行业配置；因子线性溢价在样本内并不稳定。策略表现出明显的防御特征：在2018、2022、2023、2026年"
          "等弱市或震荡市中超额显著，而在2019—2020年成长牛市和2025年大盘上涨阶段跑输基准。产品化时，"
          "我们加入“单一行业不超过10只”的约束，以降低金融行业过度集中的风险；该约束使年化收益降至"
          f"{pct(prod['年化收益'])}，但行业分布更均衡。容量测算显示，在10%调仓参与率约束下产品容量约"
          "1.5亿元，适合作为中小规模、以绝对收益与回撤控制为目标的私募量化多头产品。")
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    run = p.add_run("关键词：")
    _set_run_font(run, size=12, bold=True)
    run = p.add_run("多因子模型；低波动异象；换手率；Fama-MacBeth回归；收益归因；产品容量")
    _set_run_font(run, size=12)

    doc.add_page_break()

    # ---------------- 目录（静态） ----------------
    _heading(doc, "目录", 1)
    toc = [
        "1  引言",
        "2  因子说明",
        "3  数据与方法",
        "4  多因子模型构建与回测",
        "5  收益归因与风险分析",
        "6  产品要素分析",
        "7  结果分析与讨论",
        "参考文献",
        "附录  复现说明与分工",
    ]
    for t in toc:
        p = doc.add_paragraph()
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
        run = p.add_run(t)
        _set_run_font(run, size=12)
    doc.add_page_break()

    # ---------------- 1 引言 ----------------
    _heading(doc, "1  引言", 1)
    _heading(doc, "1.1  策略背景", 2)
    _body(doc,
          "A股市场的因子投资在过去十余年经历了从“小市值+低估值”到“质量+景气”，再到“低波+红利”的多次风格切换。"
          "2019—2020年，成长与大市值风格占优，低估值和小市值因子显著回撤；2021年以后，核心资产估值收缩，"
          "高波动、高换手、高估值板块持续承压，低波动、低换手、现金流稳定的资产重新获得定价。"
          "这一风格切换提示我们：单一因子或单一风格的产品很难穿越完整周期，策略设计必须回答“赚什么钱、"
          "在什么环境下赚钱、什么环境下会亏钱”三个问题。")
    _body(doc,
          "本策略从行为金融与市场微观结构出发，选择“低波动”和“低换手”作为核心增量因子。低波动异象"
          "（low-volatility anomaly）指低波动股票的风险调整后收益长期高于高波动股票，其解释包括杠杆约束、"
          "彩票偏好与机构委托代理等；低换手因子则刻画交易拥挤度与筹码稳定性，高换手往往伴随投机交易、"
          "注意力驱动和未来的反转风险。把两者与价值、规模因子结合，目标是在沪深300内部构建一个"
          "“估值不贵、市值不极端、波动可控、交易不拥挤”的防御型多头组合。")
    _heading(doc, "1.2  核心投资逻辑", 2)
    _body(doc,
          "策略的核心逻辑可以概括为三条。第一，估值提供安全边际。EP与BP衡量投资者为每单位盈利或净资产"
          "支付的价格，低估值股票在盈利不及预期时拥有更厚的缓冲。第二，低波动降低组合的尾部风险。"
          "在市场下跌阶段，低波动股票的beta更低、现金流更稳定，组合的回撤和恢复时间更短。第三，"
          "低换手规避拥挤交易。换手率是交易行为的直接度量，持续高换手的股票往往已经被短期资金充分定价，"
          "未来更容易出现反转；低换手股票筹码稳定，抛压较小。三条逻辑共同指向“防御型价值”风格，"
          "而非追逐高弹性成长。")
    _body(doc,
          "需要强调的是，低波动与低换手并非“无风险套利”。它们本质上是对特定风险因子的暴露：当市场进入"
          "单边成长牛市、风险偏好快速上升时，低波动组合会显著跑输；当市场处于震荡或下行阶段时，"
          "低波动组合的超额才更容易兑现。因此，本报告不把策略包装成“全天候 alpha”，而是把它定位为"
          "组合中的低波权益配置或防御型指增产品。")
    _heading(doc, "1.3  角色定位与目标范围", 2)
    _body(doc,
          "本团队将自身定位为一家私募证券投资基金的量化投资部，产品为“沪深300低风险增强一号”，"
          "面向风险偏好中等、追求长期稳健增值的高净值客户与机构资金。产品以沪深300全收益指数为业绩基准，"
          "股票池限定为沪深300历史成分股，采用月度调仓、满仓多头、等权持有30只股票的基本设置。"
          "选择沪深300而非全市场，主要基于三点考虑：一是成分股流动性好，容量与交易成本可控；"
          "二是历史成分股数据可得，能够较大程度规避幸存者偏差；三是产品定位清晰，便于与基准比较和渠道沟通。")
    _body(doc,
          "产品的目标不是追求极致的年度收益排名，而是在控制回撤与风格暴露的前提下，力争每年取得稳定的"
          "相对基准超额。根据回测结果，产品适合在震荡市、熊市和风格均衡市场中配置；在单边成长牛市，"
          "投资者应预期产品跑输基准。这一风险收益特征需要在销售材料与风险揭示书中明确说明。")

    # ---------------- 2 因子说明 ----------------
    _heading(doc, "2  因子说明", 1)
    _heading(doc, "2.1  基准因子：价值与规模", 2)
    _body(doc,
          "价值因子使用盈利收益率EP和账面市值比BP两个指标。EP=1/PE(TTM)，BP=1/PB(MRQ)。"
          "相对于PE和PB本身，倒数形式在截面上更接近正态分布，也便于解释为“单位价格所对应的盈利或净资产”。"
          "当PE或PB为负（亏损或资不抵债）时，因子记为缺失，避免负值在排序中被错误地视为“极度便宜”。"
          "价值综合因子取EP与BP标准化后的等权平均，以降低单一估值指标的行业偏差。")
    _body(doc,
          "规模因子使用流通市值的自然对数并取负号，即size=-ln(流通市值)，数值越大代表市值越小。"
          "在沪深300内部，小市值端通常具有更高的弹性和更高的波动，因此规模因子既是收益来源，也是风险来源。"
          "基准模型仅使用价值与规模两个因子，目的是提供一个“简单、透明、可复现”的对照基准，"
          "避免用复杂模型抬高研究模型的相对表现。")
    _heading(doc, "2.2  核心因子：低波动与低换手", 2)
    _body(doc,
          "低波动因子使用过去20个交易日日收益率的标准差，年化后取负号，即vol20=-std(r_d,20)×√252。"
          "窗口选择20日而非60日，是因为A股风格切换较快，20日窗口对近期风险变化更敏感；"
          "在稳健性检验中，60日窗口的结果方向一致但换手更低、收益略低。"
          "波动率是唯一在截面上具有“低风险、高收益”特征的经典异象之一，其经济含义包括杠杆约束、"
          "投资者彩票偏好和机构对低风险资产的稳定需求。")
    _body(doc,
          "低换手因子使用过去20个交易日日均换手率并取负号，即turn20=-mean(turn_d,20)。"
          "换手率衡量交易活跃度与筹码交换速度。高换手可能来自三种情形：一是基本面信息驱动的正常交易，"
          "二是短期主题投机，三是机构调仓或指数调整。后两种情形往往伴随交易拥挤，未来收益容易反转。"
          "低换手股票通常筹码稳定、卖压较小，在风险偏好下降时更具防御性。与低波动因子类似，"
          "低换手也不是无风险套利，在交易活跃度整体抬升的牛市中可能跑输。")
    _heading(doc, "2.3  备选因子与扩展", 2)
    _body(doc,
          "除四个核心因子外，报告还计算了多组备选因子用于对照和稳健性分析：12-1月动量、1月反转、"
          "60日波动、特质波动率IVOL、20日最大单日收益MAX、换手率稳定性、异常换手、低Beta、"
          "Amihud非流动性和下行波动。其中，IVOL通过60日滚动单因子回归的残差方差构造，"
          "用于剥离市场beta后的特质风险；MAX取20日最大单日收益的负值，用于刻画彩票型股票的"
          "“高偏度、低预期收益”特征；换手率稳定性用20日换手率标准差除以均值并取负号，"
          "用于区分“持续低换手”与“换手忽高忽低”的股票。备选因子的检验结果见第4.3节，"
          "它们并未全部进入最终模型，原因是与核心因子相关性较高或样本内表现不稳定。")
    _heading(doc, "2.4  因子定义与数据需求", 2)
    fdef = pd.DataFrame([
        ["EP", "1/PE(TTM)，PE≤0记缺失", "估值", "日频", "—", "越高越好"],
        ["BP", "1/PB(MRQ)，PB≤0记缺失", "估值", "日频", "—", "越高越好"],
        ["价值", "EP_z与BP_z的等权平均", "估值", "日频", "—", "越高越好"],
        ["规模", "-ln(流通市值)", "规模", "日频", "—", "越高越好（小市值）"],
        ["低波动", "-std(日收益,20)×√252", "风险", "日频", "20日", "越高越好"],
        ["低换手", "-mean(换手率,20)", "交易行为", "日频", "20日", "越高越好"],
        ["IVOL", "-√(残差方差×252)，60日滚动回归", "风险", "日频", "60日", "越高越好"],
        ["MAX", "-max(日收益,20)", "行为", "日频", "20日", "越高越好"],
        ["换手稳定性", "-std(turn,20)/mean(turn,20)", "交易行为", "日频", "20日", "越高越好"],
        ["12-1动量", "累计收益(t-252,t-21)", "动量", "日频", "252/21日", "越高越好"],
        ["1月反转", "-(累计收益(t-21,t))", "反转", "日频", "21日", "越高越好"],
        ["非流动性", "mean(|r|/成交额,20)×1e8", "流动性", "日频", "20日", "方向待检验"],
    ], columns=["因子", "近似计算公式", "类别", "频率", "窗口", "方向"])
    _table(doc, fdef, "表1  因子定义、数据需求与方向", font_size=8.5)
    _body(doc,
          "所有因子均只使用调仓日及之前的数据，不使用未来信息。估值数据来自东方财富，"
          "行情与成交数据来自新浪财经，指数数据来自中证指数公司。因子在每个调仓日做横截面计算，"
          "因此不同股票的历史长度差异不会造成跨期错配。")

    # ---------------- 3 数据与方法 ----------------
    _heading(doc, "3  数据与方法", 1)
    _heading(doc, "3.1  数据来源与样本区间", 2)
    _body(doc,
          "行情数据通过开源库akshare获取：个股日线来自新浪财经（stock_zh_a_daily，后复权），"
          "估值数据来自东方财富（stock_value_em，包含流通市值、PE(TTM)、PB(MRQ)），"
          "沪深300历史成分股来自baostock的query_hs300_stocks接口，业绩基准为沪深300全收益指数"
          "（H00300）。样本区间为2017年1月至2026年11月，其中2017年用于计算因子所需的历史窗口，"
          "正式回测从2018年1月31日的第一个信号日开始，至2025年12月31日结束；2026年1月至11月作为"
          "样本外模拟区间。")
    _body(doc,
          "为降低幸存者偏差，股票池不使用“当前沪深300成分股”，而是按每个调仓日查询当日的历史成分股。"
          "区间内成分股并集约550只，实际可取得完整行情的约547只。对于2026年样本外区间，由于无法获得"
          "未来的成分股调整信息，我们将2025年11月28日的成分股名单冻结，作为2026年全年的静态股票池。"
          "这一处理避免了使用未来成分股信息，但也意味着2026年模拟不会纳入此后新调入沪深300的股票，"
          "结果存在一定的静态池偏差，需在解读时注意。")
    _heading(doc, "3.2  数据清洗与异常处理", 2)
    _body(doc,
          "数据清洗遵循以下规则：（1）剔除调仓日停牌、无收盘价或ST/*ST的股票；由于akshare日线数据不提供"
          "完整的ST标记，本报告以“收盘价有效且成交额大于零”作为可交易的基本条件，ST剔除并不完全，"
          "这是数据源的限制之一。（2）剔除上市未满120个交易日的股票，避免新股上市初期的极端波动和"
          "缺失历史窗口。（3）对因子做横截面1%/99%缩尾，再计算z-score，降低极端值对均值和方差的影响。"
          "（4）对缺失因子不直接删除股票，而是在综合得分时按有效因子数量处理：4个因子中至少3个有效才纳入"
          "排序，缺失因子以0（截面均值）填充。")
    _body(doc,
          "报告没有做行业中性化。原因有三：第一，行业中性化会显著削弱低波动、低换手因子的暴露，"
          "而这两个因子的收益恰恰部分来自行业层面（如银行、公用事业等低波行业）；第二，行业分类只有"
          "当前快照，无法完全还原历史行业归属，强行业中性化会引入额外误差；第三，产品化阶段我们改用"
          "“单一行业最多10只”的约束来控制行业集中度，比逐因子行业中性化更直观、更容易向投资者解释。"
          "作为对照，报告也测试了行业中性化版本，其年化收益与夏普均低于原始版本，因此未作为主模型。")
    _heading(doc, "3.3  因子有效性检验方法", 2)
    _body(doc,
          "因子检验包括四个层面。第一，月度Rank IC：在每个调仓日计算因子值与下一期收益的Spearman秩相关，"
          "统计均值、标准差、ICIR（均值/标准差）、t值和IC大于零的比例。第二，分组回测：按因子值将股票"
          "分为5组，计算各组下一期平均收益，观察单调性，并用第5组减第1组构造多空组合。第三，因子相关性："
          "计算各因子截面Spearman相关系数的跨期平均，判断共线性。第四，IC衰减：分别使用未来1、3、6、12个月"
          "收益计算IC，观察因子的预测期限。所有检验均在2018—2025年样本内进行，2026年只用于样本外观察。")
    _heading(doc, "3.4  模型设定与回测参数", 2)
    _body(doc,
          "基准模型：对价值（EP、BP等权）与规模两个因子分别做横截面z-score，等权平均得到综合得分，"
          "持有得分最高的30只股票，等权配置。研究模型：在基准模型上加入低波动（20日）与低换手（20日）"
          "两个因子，四个因子等权平均。选择等权而非IC加权或优化权重，是为了避免在样本内过度优化，"
          "也便于向投资者解释。因子方向统一为“数值越大越好”，因此所有因子在进入打分前已经调整了符号。")
    _body(doc,
          "回测设置为：每月最后一个交易日收盘生成信号，下一交易日收盘调仓；持有30只股票，等权，满仓，"
          "不做杠杆、不做空；单边交易成本0.10%（佣金、印花税、过户费与冲击成本的保守估计），"
          "按单边换手率计算，买卖双边均收费；基准为沪深300全收益指数。回测区间为2018年2月1日至"
          "2025年12月31日，共95个调仓期。2026年样本外从2026年1月5日开始，至2026年11月11日。")
    _body(doc,
          "样本划分：2018—2021年为训练期，用于观察因子方向与模型设计；2022—2025年为验证期，"
          "用于检验模型在样本外的稳定性；2026年为模拟期，用于观察策略在完全未知数据上的表现。"
          "报告不会根据验证期或模拟期的结果反向修改模型，所有参数在训练期结束后即固定。")

    # ---------------- 4 模型与回测 ----------------
    _heading(doc, "4  多因子模型构建与回测", 1)
    _heading(doc, "4.1  基准模型", 2)
    _body(doc,
          "基准模型只包含价值与规模两个因子。它的作用是回答一个朴素问题：在沪深300内部，"
          "“买便宜的小市值股票”能否战胜市值加权的沪深300？回测结果显示，基准模型年化收益"
          f"{pct(b['年化收益'])}，年化波动{pct(b['年化波动'])}，夏普{num(b['夏普比率'], 3)}，"
          f"最大回撤{pct(b['最大回撤'])}，相对沪深300的年化超额为{pct(b['年化超额收益'])}。"
          "基准模型在2019—2020年成长牛市中大幅跑输，在2021—2024年低估值风格回归时跑赢，"
          "说明价值与规模因子本身具有明显的周期性。")
    _heading(doc, "4.2  研究模型", 2)
    _body(doc,
          "研究模型在基准模型上加入低波动与低换手两个因子，四个因子等权。加入这两个因子的直觉是："
          "价值与规模回答“买什么便宜”，低波动与低换手回答“买什么安全、买什么不拥挤”。"
          "从组合暴露看，研究模型的beta从基准模型的"
          f"{num(b['Beta'], 2)}降至{num(r['Beta'], 2)}，年化波动从{pct(b['年化波动'])}降至"
          f"{pct(r['年化波动'])}，最大回撤从{pct(b['最大回撤'])}降至{pct(r['最大回撤'])}，"
          "说明低波动因子确实起到了降低组合风险的作用。")
    _body(doc,
          f"研究模型年化收益{pct(r['年化收益'])}，夏普{num(r['夏普比率'], 3)}，相对基准的年化超额"
          f"{pct(r['年化超额收益'])}，信息比率{num(r['信息比率'], 3)}，月度胜率{pct(r['月度胜率'], 1)}。"
          "与基准模型相比，研究模型的年化收益提高"
          f"{pct(r['年化收益'] - b['年化收益'])}，夏普提高{num(r['夏普比率'] - b['夏普比率'], 3)}，"
          "最大回撤下降"
          f"{pct(abs(b['最大回撤']) - abs(r['最大回撤']))}。这说明增量因子改善的主要是风险调整后收益，"
          "而非单纯提高收益弹性。")

    _heading(doc, "4.3  因子有效性检验结果", 2)
    _body(doc,
          "表3给出全样本因子IC的汇总（节选）。低换手（turn20）的平均IC为"
          f"{num(ic[(ic.period=='全样本') & (ic.factor=='turn_20')]['mean_ic'].iloc[0], 4)}，"
          f"t值{num(ic[(ic.period=='全样本') & (ic.factor=='turn_20')]['t_stat'].iloc[0], 2)}；"
          "低波动（vol20）的平均IC为"
          f"{num(ic[(ic.period=='全样本') & (ic.factor=='vol_20')]['mean_ic'].iloc[0], 4)}，"
          f"t值{num(ic[(ic.period=='全样本') & (ic.factor=='vol_20')]['t_stat'].iloc[0], 2)}。"
          "两者方向为正且在经济含义上一致：过去波动越低、换手越低的股票，下一期收益越高。"
          f"价值因子的平均IC为{num(ic[(ic.period=='全样本') & (ic.factor=='value')]['mean_ic'].iloc[0], 4)}，"
          f"t值{num(ic[(ic.period=='全样本') & (ic.factor=='value')]['t_stat'].iloc[0], 2)}；"
          f"规模因子为{num(ic[(ic.period=='全样本') & (ic.factor=='size')]['mean_ic'].iloc[0], 4)}，"
          f"t值{num(ic[(ic.period=='全样本') & (ic.factor=='size')]['t_stat'].iloc[0], 2)}。"
          "两者均不显著，说明2018—2025年A股整体上并不稳定奖励“低估值+小市值”，"
          "这也是基准模型表现较弱的原因。")
    ic_full = ic[ic["period"] == "全样本"].sort_values("mean_ic", ascending=False).copy()
    ic_full = ic_full[~ic_full["factor"].isin(["amihud_20", "rev_1m"])]
    ic_full["mean_ic"] = ic_full["mean_ic"].map(lambda x: f"{x:.4f}")
    ic_full["icir"] = ic_full["icir"].map(lambda x: f"{x:.3f}")
    ic_full["t_stat"] = ic_full["t_stat"].map(lambda x: f"{x:.2f}")
    ic_full["positive_ratio"] = ic_full["positive_ratio"].map(lambda x: f"{x*100:.1f}%")
    show_cols = ["name", "mean_ic", "icir", "t_stat", "positive_ratio", "n_periods"]
    _table(doc, ic_full[show_cols].rename(columns={
        "name": "因子", "mean_ic": "IC均值", "icir": "ICIR",
        "t_stat": "t值", "positive_ratio": "IC>0占比", "n_periods": "期数"}),
        "表3  全样本因子IC汇总（2018—2025）", font_size=8.5)

    _body(doc,
          "分阶段看，低换手与低波动在训练期和验证期均为正，验证期的IC更高，说明因子在2022年以后"
          "的风格环境中更有效；价值因子在训练期为负、验证期转正，规模因子在两个阶段均为负，"
          "两者方向都不稳定。"
          "这一结果提醒我们：不能因为验证期表现好就大幅提高价值/规模权重，也不能因为训练期表现差就"
          "完全否定它们。等权合成是对因子方向不确定性的一种保守处理。")
    piv = ic[ic["factor"].isin(["value", "size", "vol_20", "turn_20", "ivol_60", "turn_cv_20", "max_20"])]
    piv = piv.pivot_table(index="name", columns="period", values="mean_ic")
    piv = piv[["训练期(2018-2021)", "验证期(2022-2025)", "全样本"]].round(4)
    piv.index.name = "因子"
    _table(doc, piv, "表4  核心因子分阶段IC均值", font_size=9, index=True)

    _figure(doc, "fig_ic", "图1  全样本因子IC均值与t值", 15.0)
    _figure(doc, "fig_ic_heatmap", "图2  分年度因子IC热力图", 14.0)
    _body(doc,
          "图2显示，低波动、低换手在2022—2024年持续为正，在2019—2020年成长牛市中接近零或为负；"
          "价值因子在2019—2020年显著为负，在2022—2024年转正。因子有效性与市场风格高度相关，"
          "这也是策略收益呈现明显阶段性的根本原因。")
    _figure(doc, "fig_quantile", "图3  低波动与低换手因子的分组年化收益", 15.0)
    _body(doc,
          "分组结果显示，低波动与低换手因子的第5组年化收益高于第1组，但组间差异并不完全单调，"
          "中间组存在噪声。这说明因子的信息更多体现在“规避极端高波动、高换手股票”，"
          "而不是精确预测每一组的排序。组合取综合得分最高的30只股票，本质上是在利用分布的右尾，"
          "而不是依赖线性斜率。")
    _figure(doc, "fig_factor_corr", "图4  因子截面相关性", 13.5)
    _body(doc,
          "因子相关性方面，低波动与低换手高度相关（平均截面相关系数约0.6），价值与低波动也有一定正相关，"
          "因为低估值股票往往集中在银行、公用事业等低波行业。四个因子并非完全独立，等权合成会重复暴露"
          "“低风险”风格。我们没有进一步做正交化，是因为正交化会削弱因子的经济含义，且在样本内并未带来"
          "稳定的收益改善。")

    _heading(doc, "4.4  回测结果", 2)
    show1 = metrics[["累计收益", "年化收益", "年化波动", "夏普比率",
                     "最大回撤", "卡玛比率"]].copy()
    for c in show1.columns:
        show1[c] = show1[c].map(lambda x: num(x, 3) if c in ["夏普比率", "卡玛比率"]
                                else pct(x))
    show1.index.name = "组合"
    _table(doc, show1, "表5  回测收益与风险对比（2018-02至2025-12）", font_size=8.5)
    show2 = metrics[["年化超额收益", "跟踪误差", "信息比率", "Beta",
                     "年化Alpha", "月度胜率", "平均单边换手率"]].copy()
    for c in show2.columns:
        if c in ["信息比率", "Beta"]:
            show2[c] = show2[c].map(lambda x: num(x, 3))
        elif c in ["月度胜率", "平均单边换手率"]:
            show2[c] = show2[c].map(lambda x: pct(x, 1))
        else:
            show2[c] = show2[c].map(lambda x: pct(x))
    show2.index.name = "组合"
    _table(doc, show2, "表5（续）  回测相对基准指标", font_size=8.5)
    _body(doc,
          f"表5显示，研究模型的累计收益为{pct(r['累计收益'])}，基准模型为{pct(b['累计收益'])}，"
          f"沪深300为{pct(h['累计收益'])}。研究模型的年化超额为{pct(r['年化超额收益'])}，"
          f"信息比率{num(r['信息比率'], 3)}，跟踪误差{pct(r['跟踪误差'])}。"
          "跟踪误差较高，说明产品并非严格的指数增强，而是带有明显风格偏离的量化多头；"
          "如果按公募指增的标准，12%以上的跟踪误差偏高，更适合私募或专户产品。")
    _figure(doc, "fig_nav", "图5  研究模型、基准模型与沪深300净值曲线", 15.5)
    _body(doc,
          "净值曲线显示，2019—2020年研究模型明显跑输沪深300，2021年以后逐渐追上并反超；"
          "2024年研究模型取得较高收益，主要来自低估值、低波动板块的估值修复。"
          "策略的超额不是均匀分布的，而是集中在少数年份，这对持有人的耐心和产品的考核周期提出了要求。")
    _figure(doc, "fig_drawdown", "图6  回撤曲线对比", 15.5)
    _body(doc,
          f"研究模型的最大回撤为{pct(r['最大回撤'])}，小于沪深300的{pct(h['最大回撤'])}，"
          f"也小于基准模型的{pct(b['最大回撤'])}。最大回撤发生在2018年2月至10月，"
          "持续约421天，后在2019年4月修复。2020年新冠冲击、2022年熊市和2024年小盘流动性危机中，"
          "研究模型的回撤均小于基准，说明低波动因子在极端行情中提供了缓冲。")
    dd_show = dd_table.copy()
    for c in ["开始", "谷底", "恢复"]:
        dd_show[c] = pd.to_datetime(dd_show[c]).dt.strftime("%Y-%m-%d")
    dd_show["最大回撤"] = dd_show["最大回撤"].map(lambda x: pct(x))
    dd_show["持续天数"] = dd_show["持续天数"].map(lambda x: f"{int(x)}")
    dd_show["修复天数"] = dd_show["修复天数"].map(
        lambda x: "—" if pd.isna(x) else f"{int(x)}")
    _table(doc, dd_show, "表6  研究模型前五大回撤区间", font_size=8.5)
    _figure(doc, "fig_annual", "图7  分年度收益对比", 15.0)
    ann_show = annual.copy()
    for c in ann_show.columns:
        ann_show[c] = ann_show[c].map(lambda x: pct(x))
    _table(doc, ann_show, "表7  分年度收益", font_size=9, index=True)
    _body(doc,
          "分年度看，研究模型在2018、2021、2022、2023、2024年取得正超额，在2019、2020、2025年跑输。"
          "2019—2020年是典型的成长牛市，低波动、低估值风格被极端压制；2025年大盘上涨、成长风格回归，"
          "策略再次跑输。这一“弱市跑赢、牛市跑输”的对称性，是低风险策略的固有特征，而非模型缺陷。")

    _heading(doc, "4.5  稳健性与参数敏感性", 2)
    _body(doc,
          "为检验结果是否依赖特定参数，我们改变了持仓数量（20、30、40、50只）与单边交易成本"
          "（0.05%、0.10%、0.15%、0.20%），共16组组合。结果显示，持仓30只、成本0.10%附近是较优区间；"
          "持仓20只时集中度提高、夏普下降，持仓40—50只时分散度提高但超额被稀释。"
          "成本从0.05%提高到0.20%，年化收益下降约1.5—2.0个百分点，但夏普仍显著高于基准模型。"
          "这说明策略并非依赖极低的交易成本，但成本控制仍然是产品化的关键。")
    sens_show = sens.copy()
    sens_show["cost"] = sens_show["cost"].map(lambda x: f"{x*100:.2f}%")
    sens_show["annual"] = sens_show["annual"].map(lambda x: pct(x))
    sens_show["sharpe"] = sens_show["sharpe"].map(lambda x: num(x, 3))
    sens_show["mdd"] = sens_show["mdd"].map(lambda x: pct(x))
    sens_show["ir"] = sens_show["ir"].map(lambda x: num(x, 3))
    sens_show["turnover"] = sens_show["turnover"].map(lambda x: pct(x, 1))
    sens_show = sens_show.rename(columns={
        "top_n": "持仓数", "cost": "单边成本", "annual": "年化收益",
        "sharpe": "夏普", "mdd": "最大回撤", "ir": "信息比率", "turnover": "换手率"})
    _table(doc, sens_show, "表8  参数敏感性（部分）", font_size=8, max_rows=16)
    _figure(doc, "fig_sensitivity", "图8  持仓数量与交易成本对夏普的影响", 13.0)
    _figure(doc, "fig_turnover", "图9  研究模型月度单边换手率", 15.0)
    _body(doc,
          f"研究模型的平均单边换手率为{pct(info['avg_turnover'], 1)}，年化约"
          f"{info['avg_turnover']*12:.1f}倍。按单边0.10%的成本计算，年化交易成本约"
          f"{info['avg_turnover']*12*2*0.001*100:.2f}%。换手率在2018年和2022年较高，"
          "在2023—2025年下降，说明因子信号在极端行情中变化更快。产品化时需要设置换手率上限，"
          "避免在风格快速切换时产生过高的交易成本。")

    _heading(doc, "4.6  2026年样本外模拟", 2)
    _body(doc,
          "2026年1月至11月，沪深300全收益指数下跌约10.1%，市场在3月、7月、9—10月出现明显调整。"
          f"研究模型在样本外取得年化{pct(oos.loc['research_free', '年化收益'])}的收益，"
          f"相对基准的年化超额为{pct(oos.loc['research_free', '年化超额收益'])}，"
          f"最大回撤{pct(oos.loc['research_free', '最大回撤'])}，"
          f"Beta仅{num(oos.loc['research_free', 'Beta'], 2)}。"
          "低波动、低换手组合在下跌市中表现出明显的防御性，2026年的样本外结果与“弱市跑赢”的逻辑一致。")
    oos_show = oos.copy()
    for c in ["年化收益", "年化波动", "最大回撤", "年化超额收益"]:
        oos_show[c] = oos_show[c].map(lambda x: pct(x))
    for c in ["夏普比率", "信息比率", "Beta"]:
        oos_show[c] = oos_show[c].map(lambda x: num(x, 3))
    oos_show["月度胜率"] = oos_show["月度胜率"].map(lambda x: pct(x, 1))
    _table(doc, oos_show, "表9  2026年样本外表现", font_size=8.5)
    _figure(doc, "fig_live", "图10  2026年样本外净值（2025年末=1）", 14.5)
    _body(doc,
          "需要强调，2026年样本外只有约10个月，统计意义有限；且股票池被冻结在2025年11月，"
          "存在静态池偏差。样本外的好表现不能证明策略长期有效，只能作为“防御属性”的一个旁证。")

    # ---------------- 5 归因与风险 ----------------
    _heading(doc, "5  收益归因与风险分析", 1)
    _heading(doc, "5.1  Fama-MacBeth横截面回归", 2)
    _body(doc,
          "为识别收益来源，我们在每个调仓日做一次横截面回归：将股票下一期超额收益（相对沪深300）"
          "对四个因子的标准化暴露做OLS，得到截距项与各因子溢价；再对时间序列取平均，得到Fama-MacBeth"
          "因子溢价。回归使用White异方差稳健标准误，样本为2018—2025年全部调仓日。")
    prem = premia.copy()
    prem.loc[prem["factor"] == "const", "name"] = "截距项"
    prem["mean_monthly"] = prem["mean_monthly"].map(lambda x: pct(x, 3))
    prem["annualized"] = prem["annualized"].map(lambda x: pct(x))
    prem["std"] = prem["std"].map(lambda x: pct(x, 3))
    prem["t_stat"] = prem["t_stat"].map(lambda x: num(x, 2))
    prem = prem.rename(columns={"factor": "因子", "name": "名称",
                                "mean_monthly": "月均溢价", "annualized": "年化溢价",
                                "std": "标准差", "t_stat": "t值", "n": "期数"})
    _table(doc, prem, "表10  Fama-MacBeth因子溢价（相对沪深300）", font_size=8.5)
    _body(doc,
          "结果显示，四个因子的线性溢价均不显著：低换手为正但t值不足1，价值、规模、低波动为负。"
          "这与因子IC的正值并不矛盾：IC衡量的是秩相关，而回归系数衡量的是线性斜率；"
          "低波动和低换手的收益集中在分布的极端组，线性回归无法捕捉这种非线性。"
          "换句话说，策略赚的不是“因子贝塔”的钱，而是“在因子排序顶端选股”的钱。")
    _heading(doc, "5.2  组合收益分解", 2)
    _body(doc,
          "将研究模型的月度超额收益分解为截距项、四个因子贡献和特质收益。因子贡献等于组合在该因子上的"
          "加权平均暴露乘以该期的因子溢价；特质收益是组合实际超额收益减去截距项与因子贡献后的残差。"
          "表11给出月度平均、年化与累计口径的分解结果。")
    at = attr_sum.copy()
    for c in ["月均贡献", "年化贡献", "累计贡献"]:
        at[c] = at[c].map(lambda x: pct(x))
    at["占超额收益比例"] = at["占超额收益比例"].map(lambda x: pct(x, 1))
    at["胜率"] = at["胜率"].map(lambda x: pct(x, 1))
    _table(doc, at, "表11  研究模型超额收益分解（2018—2025）", font_size=8.5)
    _body(doc,
          "分解结果显示，截距项贡献接近零，价值、规模、低波动的因子贡献为负，低换手贡献为正，"
          "特质收益贡献了绝大部分超额。这说明：（1）组合的行业与个股选择是超额的主要来源；"
          "（2）低波动因子的线性溢价为负，但组合通过低波暴露规避了高波股票，收益体现在特质项中；"
          "（3）特质收益占比过高意味着策略的alpha更依赖选股与行业配置，稳定性弱于纯因子贝塔，"
          "需要更严格的跟踪与风险预算。")
    _figure(doc, "fig_attribution", "图11  研究模型累计因子贡献", 15.0)
    _body(doc,
          "从累计贡献看，低换手贡献在2021年以后持续上升，低波动贡献在2022—2023年为正、2024年以后回落，"
          "价值与规模贡献长期为负。因子贡献的方向和幅度随市场风格变化，进一步说明单一因子的线性暴露"
          "不能解释策略的全部收益。")
    _heading(doc, "5.3  风格暴露", 2)
    _body(doc,
          "研究模型的平均风格暴露为：价值"
          f"{num(style['value'].mean(), 2)}、规模{num(style['size'].mean(), 2)}、"
          f"低波动{num(style['vol_20'].mean(), 2)}、低换手{num(style['turn_20'].mean(), 2)}。"
          "四个暴露均为正，其中价值暴露最高（约1.7个标准差），规模暴露较低（约0.2），"
          "说明组合并不是极端小市值，而是“低估值+低波动+低换手”的大中盘价值组合。"
          "规模暴露的波动较大，在2019—2020年一度接近零，在2024年小盘行情中上升。")
    ex_show = style.describe().T[["mean", "std", "min", "max"]].round(3)
    ex_show.index = [config.FACTOR_NAMES.get(i, i) for i in ex_show.index]
    ex_show.columns = ["均值", "标准差", "最小值", "最大值"]
    _table(doc, ex_show, "表12  研究模型风格暴露统计", font_size=9, index=True)
    _figure(doc, "fig_exposure", "图12  研究模型风格暴露时间序列", 15.0)
    _heading(doc, "5.4  行业配置与集中度", 2)
    _body(doc,
          "组合的行业配置是收益的重要来源，也是主要风险之一。图13给出组合相对等权沪深300的平均主动行业"
          "权重。研究模型长期超配银行（货币金融服务）、公用事业、交通运输、建筑等低波动行业，"
          "低配电子、计算机、医药等成长行业；银行单一行业的平均主动权重超过30%，但保险与资本市场服务"
          "反而低配，金融板块合计净超配约24%。这是低波动、低估值、低换手因子共同作用的结果，"
          "而非主动的行业判断。")
    _figure(doc, "fig_industry", "图13  研究模型平均主动行业权重", 14.0)
    top_ind = pd.concat([ind_avg.head(5), ind_avg.tail(5)])
    ind_show = pd.DataFrame({"平均主动权重": top_ind.map(lambda x: pct(x, 1))})
    ind_show.index.name = "行业"
    doc.add_page_break()
    _table(doc, ind_show, "表13  行业主动权重（最低5个与最高5个）", font_size=9, index=True)
    _body(doc,
          "行业集中带来的风险是：如果金融板块出现系统性调整，组合可能同时失去低估值、低波动和低换手"
          "三重支撑。2022年11月至2023年1月、2024年9月的金融行情中，组合受益明显；但若金融板块估值修复"
          "结束，组合的超额可能回吐。产品化时我们加入“单一行业最多10只”的约束，将金融权重从约42%降至"
          "约33%，代价是年化收益从"
          f"{pct(r['年化收益'])}降至{pct(prod['年化收益'])}，夏普从{num(r['夏普比率'], 3)}降至"
          f"{num(prod['夏普比率'], 3)}。这是一个典型的收益与风险分散的权衡。")
    _heading(doc, "5.5  风险指标与极端行情", 2)
    _body(doc,
          f"研究模型的年化波动为{pct(r['年化波动'])}，低于沪深300的{pct(h['年化波动'])}；"
          f"Beta为{num(r['Beta'], 2)}，下行捕获率{num(r['下行捕获率'], 2)}，"
          f"上行捕获率{num(r['上行捕获率'], 2)}。下行捕获率低于上行捕获率，说明组合在下跌市中"
          "跌得少、在上涨市中涨得也少，呈现“防御型”特征。"
          f"日VaR95为{pct(r['日VaR95'])}，日CVaR95为{pct(r['日CVaR95'])}，"
          f"日收益偏度为{num(r['日收益偏度'], 2)}，峰度为{num(r['日收益峰度'], 1)}，"
          "存在一定的左尾和厚尾风险。")
    risk_show = risk_dec.copy()
    risk_show["月度方差"] = risk_show["月度方差"].map(lambda x: f"{x:.6f}")
    risk_show["占比"] = risk_show["占比"].map(lambda x: pct(x, 1))
    _table(doc, risk_show, "表14  收益方差分解", font_size=8.5)
    _body(doc,
          "方差分解显示，因子共同风险占组合月度方差的约87%，特质风险占13%。因子风险占主导，"
          "说明组合的波动主要来自风格暴露，而非个股 idiosyncratic 风险。这也意味着，"
          "如果因子风格发生反转，组合的波动和回撤会迅速放大；风险管理的重点应放在风格暴露监控，"
          "而不是单纯分散个股。")
    st_show = stress.copy()
    for c in ["组合收益", "基准收益", "超额", "组合最大回撤", "基准最大回撤"]:
        st_show[c] = st_show[c].map(lambda x: pct(x))
    doc.add_page_break()
    _table(doc, st_show, "表15  极端行情压力测试", font_size=8.5)
    _figure(doc, "fig_stress", "图14  极端行情下研究模型与沪深300表现", 15.0)
    _body(doc,
          "压力测试显示，研究模型在2018年熊市、2021年核心资产回调、2022年熊市、2024年小盘流动性危机"
          "中均取得正超额；在2020年新冠冲击中略跑输，主要因为冲击初期低波动股票也遭遇流动性抛售；"
          "在2025年4月关税冲击中小幅跑输，但回撤小于基准。整体看，策略的防御属性在多数极端行情中有效，"
          "但不能保证每一次冲击都跑赢。")
    _heading(doc, "5.6  因子失效与风格切换风险", 2)
    _body(doc,
          "策略最大的风险不是个股踩雷，而是风格失效。2019—2020年，低波动、低估值因子在成长牛市中"
          "持续失效，研究模型相对基准的最大年度跑输超过25个百分点；2025年大盘上涨、成长回归，"
          "策略再次跑输约14个百分点。如果产品在2019年初成立，持有人需要承受近两年的持续跑输，"
          "这对产品的负债端稳定性是巨大考验。")
    _body(doc,
          "为监控因子失效，我们建议设置三类预警指标：一是滚动12个月IC，若核心因子IC连续6个月为负，"
          "降低因子权重；二是组合相对基准的滚动12个月超额，若跌破-10%，触发风格复核；"
          "三是行业主动权重，若单一行业超过40%，触发行业约束。产品化版本已经加入行业约束，"
          "但因子层面的失效预警仍需在实盘中持续跟踪。")
    _figure(doc, "fig_rolling", "图15  滚动12个月超额与滚动夏普", 15.0)

    # ---------------- 6 产品要素 ----------------
    _heading(doc, "6  产品要素分析", 1)
    _heading(doc, "6.1  产品定位与目标客户", 2)
    _body(doc,
          "产品名称“沪深300低风险增强一号”，定位为私募证券投资基金中的量化多头/防御型指增产品。"
          "目标客户为风险偏好中等、投资期限1年以上、能够承受阶段性风格跑输的高净值客户与机构资金。"
          "产品以沪深300全收益指数为业绩基准，目标是通过低波动、低换手、价值、规模的组合暴露，"
          "在完整市场周期内取得稳定的相对超额，并控制最大回撤。")
    prod_terms = pd.DataFrame([
        ["产品名称", "沪深300低风险增强一号"],
        ["产品类型", "私募证券投资基金（量化多头）"],
        ["业绩基准", "沪深300全收益指数（H00300）"],
        ["股票池", "沪深300历史成分股（2026年模拟冻结2025-11-28名单）"],
        ["调仓频率", "月度（每月最后一个交易日信号，下一交易日收盘调仓）"],
        ["持仓结构", "30只股票，等权，满仓，单一行业不超过10只"],
        ["管理费", "1.0%/年"],
        ["托管费", "0.2%/年"],
        ["业绩报酬", "超额收益的10%，高水位法"],
        ["申赎安排", "每月开放，持有少于1年赎回费0.5%"],
        ["目标客户", "高净值个人、FOF、机构配置资金"],
        ["风险特征", "中高风险，防御型，弱市超额、牛市跑输"],
    ], columns=["要素", "设置"])
    _table(doc, prod_terms, "表16  产品要素表", font_size=8.5)
    _heading(doc, "6.2  费率结构与费后收益", 2)
    _body(doc,
          "私募产品的费率通常由管理费、托管费和业绩报酬组成。本产品基准情景为管理费1.0%/年、"
          "托管费0.2%/年、业绩报酬为相对基准超额收益的10%，采用高水位法。表17给出不同费率情景下的"
          "费后年化收益与费率侵蚀。以产品实施版的费前年化收益为基准，"
          f"基准情景费后年化约{pct(fee.iloc[2]['费后年化'])}，"
          f"费后超额约{pct(fee.iloc[2]['费后超额'])}，"
          f"费率侵蚀约{pct(fee.iloc[2]['费率侵蚀'])}。")
    fee_show = fee.copy()
    fee_show["管理费"] = fee_show["管理费"].map(lambda x: f"{x*100:.1f}%")
    fee_show["托管费"] = fee_show["托管费"].map(lambda x: f"{x*100:.1f}%")
    fee_show["业绩报酬"] = fee_show["业绩报酬"].map(lambda x: f"{x*100:.0f}%")
    for c in ["固定费合计", "业绩报酬计提", "费后年化", "费后超额", "费率侵蚀"]:
        fee_show[c] = fee_show[c].map(lambda x: pct(x))
    fee_show["费后夏普"] = fee_show["费后夏普"].map(lambda x: num(x, 3))
    _table(doc, fee_show, "表17  费率情景与费后收益", font_size=8.5)
    _figure(doc, "fig_fee", "图16  不同费率情景下的费后收益与费率侵蚀", 14.0)
    _net_base = fee.iloc[2]["费后年化"]
    _gross = prod["年化收益"]
    _diff = 1_000_000 * ((1 + _gross) ** 5 - (1 + _net_base) ** 5)
    _body(doc,
          "费率对长期复利的影响不可忽视。以100万元、5年持有为例，费前年化"
          f"{pct(_gross)}与费后{pct(_net_base)}的终值差额约为{_diff/1e4:.1f}万元；"
          f"若管理费提高到1.5%、业绩报酬提高到20%，费后年化降至约{pct(fee.iloc[4]['费后年化'])}，"
          "差额进一步扩大。因此，产品在渠道端应明确“费后收益”口径，避免用费前收益做宣传。")
    _heading(doc, "6.3  容量分析", 2)
    _body(doc,
          "容量分析基于持仓股票过去20个交易日的日均成交额。对每个调仓期、每只持仓股票，计算"
          "“组合持仓市值/日均成交额”的参与率；再对不同管理规模（1亿—500亿元）统计参与率的中位数、"
          "95分位和最大值。假设单只股票单日参与率不超过10%，且调仓在1—2个交易日内完成。")
    cap_show = cap.copy()
    for c in ["参与率中位数", "参与率95分位", "参与率最大值"]:
        cap_show[c] = cap_show[c].map(lambda x: pct(x, 2))
    for c in ["20%参与率下交易日中位数", "20%参与率下交易日95分位"]:
        cap_show[c] = cap_show[c].map(lambda x: f"{x:.2f}")
    _table(doc, cap_show, "表18  不同管理规模下的调仓参与率", font_size=8.5, max_rows=7)
    _figure(doc, "fig_capacity", "图17  容量测算：参与率随管理规模变化", 13.5)
    _body(doc,
          "结果显示，在1亿元规模下，持仓参与率中位数约1.7%，95分位约7.1%，均低于10%的约束；"
          "规模升至2亿元时，95分位达到约14.2%，超过10%的上限。因此，在10%参与率约束下，"
          "产品容量约1.5亿元；若将约束放宽至20%，容量可提升至约3亿元。"
          "这一容量对于中小型私募产品是合适的，但难以支撑大规模机构资金。"
          "如果未来规模扩大，需要通过增加持仓数量、延长调仓窗口、引入流动性过滤等方式扩容。")
    _heading(doc, "6.4  调仓、流动性与风险揭示", 2)
    _body(doc,
          "产品采用月度调仓，主要考虑是：（1）因子信号（20日波动、20日换手）在月度频率上较稳定，"
          "日频调仓会显著增加交易成本；（2）月度调仓与私募产品的开放频率匹配，便于资金申赎管理；"
          "（3）A股月度效应和财报披露节奏更适合月度换仓。实盘执行时，建议在调仓日前后分2—3个交易日"
          "完成交易，避免集中冲击成本。")
    _body(doc,
          "风险揭示应包括：一是风格风险，低波动、低估值风格在成长牛市中可能持续跑输；"
          "二是行业集中风险，组合长期超配金融、公用事业，若这些行业出现系统性调整，超额可能回吐；"
          "三是模型风险，因子权重与窗口基于历史样本，未来可能失效；四是流动性风险，极端行情下"
          "个股停牌或涨跌停可能导致无法按计划调仓；五是数据风险，估值数据存在财报滞后和口径差异，"
          "历史成分股数据可能存在遗漏。产品应设置风格暴露、行业权重、换手率和回撤的预警线，"
          "并定期向投资者披露。")
    _heading(doc, "6.5  雪球模拟组合运行方案", 2)
    _body(doc,
          "为展示策略的模拟实盘运行，团队在雪球网创建公开模拟组合“沪深300低风险增强一号”。"
          "组合按本报告的月度信号调仓，初始等权买入最新一期30只股票，之后每月最后一个交易日"
          "根据新信号调整持仓。模拟组合仅用于策略跟踪，不构成投资建议。组合链接见封面。"
          "截至报告撰写时，最新信号日为2026年10月30日，执行日为2026年11月2日。"
          "表19给出最新一期30只持仓，完整名单与权重同时保存在output/live/holdings_latest.csv。")
    live_path = config.LIVE_DIR / "holdings_latest.csv"
    if live_path.exists():
        live = pd.read_csv(live_path, encoding="utf-8-sig", dtype={"code6": str})
        live = live.sort_values("rank")
        live_show = live[["rank", "code6", "name", "industry", "weight"]].copy()
        live_show["weight"] = live_show["weight"].map(lambda x: pct(x, 2))
        live_show.columns = ["序号", "代码", "名称", "行业", "权重"]
        _table(doc, live_show, "表19  最新一期模拟盘持仓（2026-10-30信号）", font_size=7.5)

    # ---------------- 7 讨论 ----------------
    _heading(doc, "7  结果分析与讨论", 1)
    _heading(doc, "7.1  关键选择及理由", 2)
    _body(doc,
          "报告中的关键选择包括：使用历史成分股而非当前成分股，以降低幸存者偏差；使用后复权价格和"
          "全收益指数，避免分红造成的收益低估；使用等权打分而非IC加权，以降低样本内过拟合；"
          "使用月度调仓而非日频，以控制交易成本；不做行业中性化，而在产品化阶段加入行业数量约束；"
          "将2018—2021年作为训练期、2022—2025年作为验证期、2026年作为模拟期，避免用全样本结果"
          "反向调参。这些选择的共同目标是提高结果的可复核性和可复现性，而不是追求样本内的最高收益。")
    _heading(doc, "7.2  研究模型、基准模型与沪深300的对比", 2)
    _body(doc,
          f"从全样本看，研究模型年化{pct(r['年化收益'])}，高于基准模型的{pct(b['年化收益'])}和"
          f"沪深300的{pct(h['年化收益'])}；夏普{num(r['夏普比率'], 3)}，高于基准模型的"
          f"{num(b['夏普比率'], 3)}和沪深300的{num(h['夏普比率'], 3)}；最大回撤{pct(r['最大回撤'])}，"
          f"小于基准模型的{pct(b['最大回撤'])}和沪深300的{pct(h['最大回撤'])}。"
          "从风险调整后收益看，研究模型的改善是明显的；从绝对收益看，7.46%的年化收益并不算高，"
          "但对于一个beta仅0.67、最大回撤26.5%的防御型产品，是可以接受的风险收益比。")
    _heading(doc, "7.3  因子改善的稳定性", 2)
    _body(doc,
          "因子改善并不稳定。训练期（2018—2021）研究模型年化约2.85%，仍跑输基准约3.4个百分点；"
          "验证期（2022—2025）年化约12.18%，跑赢基准约11.1个百分点。也就是说，策略的全部超额"
          "几乎都来自2022年以后。这不是模型计算错误，而是低风险风格在2019—2020年成长牛市中"
          "被极端压制的结果。对于产品化而言，这意味着：（1）不能用2018—2025全样本的夏普向投资者"
          "承诺未来收益；（2）需要向投资者明确“弱市跑赢、牛市跑输”的特征；（3）产品成立时点"
          "对短期体验影响很大，若在成长牛市初期成立，可能长期跑输。")
    _heading(doc, "7.4  困难与解决方案", 2)
    _body(doc,
          "项目过程中遇到的主要困难包括：一是数据获取，baostock匿名登录在并发较高时会被限流，"
          "我们改用akshare的新浪日线与东方财富估值数据，并建立本地缓存；二是历史成分股，"
          "akshare只提供当前成分股，我们使用baostock的历史成分股接口并缓存，2026年则冻结最新名单；"
          "三是后复权价格在跨年更新时的拼接问题，我们改用日收益率复利构建收益指数，避免复权因子"
          "变化造成的价格跳变；四是因子共线性，低波动与低换手高度相关，我们没有强行正交化，"
          "而是在报告中披露共线性并在产品化阶段用行业约束控制集中度。")
    _heading(doc, "7.5  改进方向", 2)
    _body(doc,
          "未来可以从五个方向改进。第一，引入质量因子（ROE、毛利率、现金流）和分析师预期修正因子，"
          "提升组合的基本面质量，降低对纯价格行为的依赖。第二，引入风险预算或波动率目标，"
          "在市场极端波动时降低仓位，改善绝对收益和回撤。第三，使用滚动窗口的ICIR加权或机器学习"
          "模型（如LightGBM）替代等权打分，但必须做严格的样本外验证，避免过拟合。第四，扩展股票池"
          "到中证500或全市场，并用流动性过滤和行业约束控制容量与集中度。第五，完善交易执行模型，"
          "考虑涨跌停、停牌、冲击成本和T+1约束，使回测更接近实盘。")
    _body(doc,
          "总之，本策略不是一个“高收益、全天候”的alpha，而是一个“低波动、防御型、弱市超额”的"
          "风格产品。它的价值在于为组合提供低波权益暴露和回撤保护，而不是替代成长型权益产品。"
          "只有把产品定位、投资者预期和风险揭示说清楚，策略才能在实盘中发挥应有的作用。")

    # ---------------- 参考文献 ----------------
    _heading(doc, "参考文献", 1)
    refs = [
        "[1] Fama, E. F., & MacBeth, J. D. (1973). Risk, return, and equilibrium: Empirical tests. Journal of Political Economy, 81(3), 607-636.",
        "[2] Ang, A., Hodrick, R. J., Xing, Y., & Zhang, X. (2006). The cross-section of volatility and expected returns. Journal of Finance, 61(1), 259-299.",
        "[3] Baker, M., Bradley, B., & Wurgler, J. (2011). Benchmarks as limits to arbitrage: Understanding the low-volatility anomaly. Financial Analysts Journal, 67(1), 40-54.",
        "[4] Bali, T. G., Cakici, N., & Whitelaw, R. F. (2011). Maxing out: Stocks as lotteries and the cross-section of expected returns. Journal of Financial Economics, 99(2), 427-446.",
        "[5] Amihud, Y. (2002). Illiquidity and stock returns: Cross-section and time-series effects. Journal of Financial Markets, 5(1), 31-56.",
        "[6] Jegadeesh, N., & Titman, S. (1993). Returns to buying winners and selling losers: Implications for stock market efficiency. Journal of Finance, 48(1), 65-91.",
        "[7] 李斌, 林彦, 唐闻轩. 机器学习驱动的基本面量化投资研究. 中国工业经济, 2019(8): 61-79.",
        "[8] 开源证券金融工程团队. 低频风格因子与行业轮动研究. 金融工程研究报告, 2021.",
        "[9] 中证指数有限公司. 沪深300指数编制方案与成分股调整规则. 2025.",
        "[10] akshare开源社区. akshare金融数据接口文档. https://akshare.akfamily.xyz/, 2026.",
    ]
    for ref in refs:
        p = doc.add_paragraph()
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
        p.paragraph_format.left_indent = Pt(0)
        run = p.add_run(ref)
        _set_run_font(run, size=10.5)

    # ---------------- 附录 ----------------
    _heading(doc, "附录  复现说明与分工", 1)
    _body(doc,
          "代码使用Python 3.11编写，依赖pandas、numpy、scipy、statsmodels、matplotlib、python-docx、"
          "akshare、baostock等库。项目根目录下的一键运行脚本 run_all.py 可从本地缓存重新生成"
          "全部表格、图表和本报告；首次运行前需先运行数据更新脚本 update_data.py 下载行情与估值数据。"
          "所有随机过程均未使用随机数，结果可完全复现。代码仓库链接见封面。")
    _body(doc,
          "数据缓存目录为data/cache，包含约550只股票的日线、估值和指数数据；历史成分股文件为"
          "data/constituents_history.parquet，行业分类为data/industry_map.parquet。"
          "由于数据供应商接口可能调整，复现时若个别股票下载失败，程序会跳过该股票并在日志中记录，"
          "不影响整体结果。")
    _body(doc,
          "分工说明：成员一负责数据获取、清洗与因子构建；成员二负责回测框架、模型比较与参数敏感性；"
          "成员三负责Fama-MacBeth回归、收益归因与风险分析；成员四负责产品要素、容量/费率测算、"
          "报告撰写与雪球模拟组合维护。四位成员共同参与因子讨论、结果复核与报告修改。")

    path = config.REPORT_DIR / "沪深300低风险增强多因子策略_技术报告.docx"
    doc.save(path)
    print("    已保存:", path)
    return path


if __name__ == "__main__":
    build_report()
