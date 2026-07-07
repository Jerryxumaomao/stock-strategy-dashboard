# A股分支(ashare branch)

本分支把这套策略看板适配到**中国 A 股**。数据用 **akshare**(免费、无 token)。
**动手前必读 [`docs/A股量化知识手册.md`](docs/A股量化知识手册.md)** —— 美股的动量/追涨逻辑在 A 股会反向,照搬会亏。

## 快速开始
```bash
git checkout ashare
pip install akshare              # 已装则跳过
python run.py build              # 用 config.json(已是A股预设)构建看板
# 双击 dashboard.html 打开
```
代码用 **6 位数字**:600519(贵州茅台)、300750(宁德时代)、688981(中芯国际)、000001(平安银行)…

## 相比美股主分支,新增了什么
| 能力 | 位置 | 说明 |
|---|---|---|
| A股行情源 | `lab/datasource.py::akshare_history` | 东财+新浪双通道前复权;带成交量+换手率 |
| A股指数(大盘开关) | `lab/datasource.py::akshare_index` | 沪深300/中证500/1000/全指 |
| 板块与涨跌停 | `lab/ashare.py::board_and_limit / limit_state` | 主板±10/创业科创±20/北交所±30/ST±5;识别涨停/跌停/一字板 |
| **短期反转因子** | `lab/ashare.py::reversal_score` | **A股核心alpha**:超跌反转(与美股动量相反) |
| 换手率因子 | `lab/ashare.py::turnover_stats` | 流动性/拥挤度分位 |
| **缠论**(A股原生) | `lab/chanlun.py::analyze` | 自包含引擎:分型→笔→中枢→背驰→一买/二买/三买。无需外部skill |
| 龙虎榜 | `lab/ashare.py::dragon_tiger` | 游资/机构席位(需中国网络) |
| 北向资金 | `lab/ashare.py::northbound_flow` | 陆股通净流入(需中国网络) |
| 市场情绪周期 | `lab/ashare.py::sentiment_gauge` | 涨停家数/连板高度/炸板率(需中国网络) |

## 命令
```bash
python run.py build                  # 构建A股看板(含A股因子:反转/涨跌停/换手/缠论)
python run.py add 600519 300750      # 加自选
python run.py ashare                 # A股情报:情绪周期 + 北向 + 龙虎榜
python run.py review                 # 前向复盘(积累后验证策略)
# —— A股研究工具(曾被排除,现补齐;需中国可达网络)——
python run.py screen 10 50 3 20      # 选股筛选器: 价10-50、涨幅3-20%、成交>5亿
python run.py dossier 600519         # 个股档案: PE/PB分位 + 财务(营收/净利/ROE/负债率)
python run.py rotation               # 行业轮动: 领涨/领跌板块(资金方向)
python run.py lhb 近一月              # 龙虎榜因子: 净买额榜(游资/机构反复运作的票)
python run.py events                 # 事件风险: 未来解禁 + 市场质押
python run.py review-cn              # 盘后复盘: 市场宽度(涨跌家数) + 情绪周期
```

## 已补齐的 A股专属能力(曾因个人看板"IBKR美股专用"被排除)
| 能力 | 命令/位置 | 实测 |
|---|---|---|
| 缠论走势 | build 卡片 / `lab/chanlun.py` | ✅ |
| 龙虎榜因子 | `run.py lhb` | ✅ 1009只上榜统计 |
| 个股档案 | `run.py dossier` | ✅ PE/PB分位+财务 |
| 事件风险(解禁/质押) | `run.py events` | ✅ 解禁日历 |
| 行业轮动 | `run.py rotation` | ✅ 板块涨跌排名 |
| 选股筛选器 | `run.py screen` | ✅ 全A 5500+只 |
| 盘后复盘(宽度+情绪) | `run.py review-cn` | ✅ |

## 看板上的 A股因子
每张卡在综合评分下方多一块 **🇨🇳 A股因子**:板块±涨跌停幅、涨停/跌停状态(一字板会提示"买不进")、反转分(超跌反转候选 vs 强势易回吐)、换手率分位、**缠论买卖点**(一买/二买/三买/中枢/背驰)。缠论是自包含引擎(`lab/chanlun.py`),无需外部 skill;缠中说禅本就交易 A 股,故此项在 A 股尤为对味。

## ⚠️ 关键局限(务必读知识手册第六章)
1. **回测引擎仍是美股口径**(T+0、无涨跌停)——A股实际 T+1 + 涨跌停会让可成交性低于回测,**绝对期望值偏乐观**,只做相对比较。完整 T+1+涨跌停回测是路线图 TODO。
2. **龙虎榜/北向/情绪需中国可达网络**(东财);海外/VPN 环境会被挡,函数优雅返回错误。
3. **历史目录**:同一个 clone 里混跑美股(main)和A股(ashare)的 build 会让 `history/`(复盘数据)混市场。**A股请用独立 clone**,或只在本分支跑。
4. 个股期权模块不适用(A股个股无期权,只有ETF期权)。
5. 所有输出为决策辅助,非投资建议。

## 数据源切换
默认 akshare。若要 tushare/baostock,在 `lab/datasource.py` 的 `SOURCES` 里加一个同签名函数即可(返回 `[{date,o,h,l,c,v?,turnover?}]`)。
