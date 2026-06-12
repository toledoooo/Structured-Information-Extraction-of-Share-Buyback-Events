# 股份回购事件结构化信息抽取

## 1. 项目概述

本项目旨在从巨潮资讯网发布的上市公司股份回购公告PDF中，自动抽取结构化的金融信息，并进行合规性分析。系统采用多阶段处理流程，结合正则表达式、规则引擎和置信度评估等技术手段，实现高质量的信息抽取。

### 1.1 研究背景与金融问题

**研究公告类型：** 上市公司股份回购相关公告，包括方案公告、进展公告和结果公告。

**解决的金融问题：**
- 回购计划执行合规性评估：判断上市公司是否按计划完成股份回购
- 信息披露完整性分析：评估回购信息披露是否充分
- 市场信号分析：通过回购行为判断上市公司财务健康状况和市场信心
- 投资者保护：识别违规回购行为，保护中小投资者利益

### 1.2 核心目标

| 目标类别 | 具体目标 | 衡量指标 | 当前达成 |
|----------|----------|----------|----------|
| 信息抽取 | 从公告PDF中提取关键金融数据 | 字段抽取准确率≥90% | ✅ |
| 合规分析 | 评估回购计划执行的合规性 | 合规判定准确率≥85% | ✅ |
| 效率提升 | 实现自动化处理 | 处理时间≤5分钟/100份 | ✅ |
| 数据质量 | 保证抽取结果的可靠性 | 平均置信度≥0.75 | ✅ |

### 1.3 难度档位说明

**申请档位：1.1**

**理由：**
1. 数据来源明确（巨潮资讯网公开公告），但PDF格式多样，解析难度中等
2. 字段定义清晰，但存在单位混淆、格式不一致等问题
3. 需处理复杂的文档结构和章节定位
4. 需要建立完整的质量评估体系和置信度计算机制
5. 需要实现证据链完整可追溯
6. 涉及多阶段处理流程，需要优化性能和并行处理
7. 引入LLM补充抽取，提升了复杂场景的处理能力
8. 实现了人工验证机制，确保数据质量
9. 三份PDF公告（方案/进展/结果）匹配为一个完整事件，共处理50个回购事件，事件匹配逻辑复杂

### 1.4 技术架构

```
数据采集 → 文档解析 → 章节定位 → 字段抽取 → 置信度评估 → 冲突解决 → 一致性计算 → 合规判定 → 报告生成
```

---

## 2. 数据来源与采集

### 2.1 数据源入口

**数据源：** 巨潮资讯网（www.cninfo.com.cn）

**入口：** 巨潮资讯网 > 信息披露 > 上市公司公告 > 回购相关公告

### 2.2 关键词与公告类型

| 公告类型 | 搜索关键词 | 目的 |
|----------|----------|------|
| 方案公告 | 回购方案、回购预案、回购报告书 | 获取回购计划信息 |
| 进展公告 | 回购进展、回购实施、首次回购 | 跟踪回购执行进度 |
| 结果公告 | 回购结果、回购完成、回购期限届满 | 获取最终执行结果 |

### 2.3 时间范围与样本规模

| 统计项 | 数值 | 说明 |
|--------|------|------|
| 时间范围 | 2023年1月 - 2024年6月 | 覆盖18个月的数据 |
| 分析公司数 | 50家 | A股上市公司 |
| 公告总数 | 150份 | 平均每家公司3份公告 |
| 方案公告 | 50份 | 每家公司1份 |
| 进展公告 | 60份 | 部分公司多次披露进展 |
| 结果公告 | 40份 | 已完成回购的公司 |

### 2.4 数据质量保障

**三层验证机制：**
1. **文件完整性检查**：验证PDF文件是否损坏、能否正常读取
2. **内容有效性检查**：验证公告内容是否与回购相关
3. **字段完整性检查**：验证关键字段是否存在

---

## 3. 目录结构

```
repurchase_project_package/
├── src/                    # 核心源代码目录
│   ├── pipeline_run.py     # 主入口，执行完整工作流
│   ├── extract_fields.py   # 字段抽取模块（正则+LLM混合）
│   ├── llm_utils.py        # LLM工具模块
│   ├── parse_docs.py       # 文档解析模块
│   ├── route_sections.py   # 章节路由模块
│   ├── match_events.py     # 事件匹配模块
│   ├── calculate_consistency.py  # 一致性计算
│   ├── validate_results.py # 结果校验模块
│   ├── common.py           # 通用工具函数
│   └── schemas.py          # 数据结构定义
├── configs/                # 配置文件目录
│   ├── workflow.yaml       # 工作流配置
│   ├── model_config.yaml   # LLM模型配置
│   └── section_rules.yaml  # 章节规则配置
├── data/                   # 数据目录
│   ├── metadata/           # 元数据文件
│   │   └── metadata.csv    # 公告元数据（50家公司147份公告）
│   └── md/                 # 公告MD文件（MinerU解析结果）
├── outputs/                # 分析结果输出
│   ├── reports/            # 分析报告
│   │   ├── integrated_report_v2.html  # 综合技术报告
│   │   └── summary_report_v2.md       # 评估结果汇总
│   └── results/            # 结构化数据结果
│       ├── records_validated.csv       # 字段抽取结果
│       ├── event_timelines.json        # 事件时间线
│       ├── parsed_docs.jsonl           # 解析文档
│       └── sections.jsonl             # 章节路由结果
├── .env                    # 环境变量配置（不提交）
├── .env.example            # 环境变量配置模板
├── AGENTS.md               # Agent角色说明
├── ai_usage_statement.md   # AI使用声明
├── ai_worklog_all.md       # AI交互工作日志
├── companies_list.json     # 公司列表
└── README.md               # 项目说明文档
```

---

## 4. 环境安装方法

### 4.1 前置依赖
- Python 3.10+
- pip 包管理工具

### 4.2 安装步骤

```bash
# 1. 克隆项目（如果需要）
git clone <repository-url>
cd repurchase_project_package

# 2. 创建虚拟环境（可选但推荐）
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

# 3. 安装依赖包
pip install -r requirements.txt

# 或手动安装核心依赖：
pip install openai python-dotenv pandas pydantic beautifulsoup4
```

---

## 5. .env.example 变量说明

```bash
# LLM配置
LLM_PROVIDER=siliconflow           # LLM服务提供商
LLM_BASE_URL=https://api.siliconflow.cn/v1  # API地址
LLM_API_KEY=your_api_key_here      # API密钥（必填）
LLM_MODEL=Qwen/Qwen3-8B           # 模型名称
LLM_TEMPERATURE=0                  # 温度参数（0表示确定性输出）
LLM_MAX_TOKENS=2048               # 最大输出token数

# MinerU配置（用于PDF解析）
MINERU_API_KEY=your_mineru_key_here  # MinerU API密钥
```

### 配置说明
| 变量 | 必填 | 说明 |
|------|------|------|
| LLM_API_KEY | 是 | LLM服务的API密钥 |
| MINERU_API_KEY | 否 | 用于PDF转Markdown，如已有MD文件可省略 |
| LLM_MODEL | 否 | 默认Qwen/Qwen3-8B，可更换其他模型 |
| LLM_TEMPERATURE | 否 | 建议设为0以保证输出一致性 |

---

## 6. 最小运行命令

### 6.1 配置环境变量

```bash
# 复制配置模板
copy .env.example .env

# 编辑.env文件，填入API密钥
# 推荐使用文本编辑器打开.env文件进行修改
```

### 6.2 执行完整工作流

```bash
# 执行所有步骤（推荐）
python src/pipeline_run.py --step all
```

### 6.3 分步执行

```bash
# 解析文档（读取MD文件）
python src/pipeline_run.py --step parse

# 章节路由（识别文档结构）
python src/pipeline_run.py --step route

# 字段抽取（正则+LLM混合抽取）
python src/pipeline_run.py --step extract

# 结果校验（Pydantic校验）
python src/pipeline_run.py --step validate

# 事件匹配（关联方案/进展/结果公告）
python src/pipeline_run.py --step match

# 质量评估（计算质量权重）
python src/pipeline_run.py --step quality

# 一致性分析（评估方案与执行偏差）
python src/pipeline_run.py --step consistency

# 生成报告（生成汇总报告）
python src/pipeline_run.py --step report
```

---

## 7. 输出文件说明

### 7.1 outputs/reports/

| 文件 | 格式 | 说明 |
|------|------|------|
| integrated_report_v2.html | HTML | **完整技术报告**，包含架构设计、抽取规则、质量评估、Demo等（2400+行） |
| summary_report_v2.md | Markdown | **评估结果汇总**，包含50家公司的完成比例、评分、合规判定 |

### 7.2 outputs/results/

| 文件 | 格式 | 说明 |
|------|------|------|
| records_validated.csv | CSV | **字段抽取结果**，包含所有公告的结构化字段 |
| event_timelines.json | JSON | 事件时间线，关联同一回购事件的多份公告 |
| parsed_docs.jsonl | JSONL | 解析后的文档内容 |
| sections.jsonl | JSONL | 章节路由结果 |

### 7.3 输出示例

**字段抽取结果结构**（records_validated.csv）：
| 字段名 | 类型 | 说明 |
|--------|------|------|
| company_name | str | 公司名称 |
| stock_code | str | 股票代码 |
| announcement_type | str | 公告类型（方案/进展/结果） |
| repurchase_method | str | 回购方式 |
| total_amount_upper | float | 计划金额上限（亿元） |
| price_upper | float | 价格上限（元/股） |
| actual_amount | float | 实际回购金额（亿元） |
| actual_quantity | float | 实际回购数量（万股） |

---

## 8. 评估结果摘要

### 8.1 整体统计

| 指标 | 数值 |
|------|------|
| 分析公司数 | 50家 |
| 公告文件数 | 147份 |
| 平均完成比例 | 69.45% |
| 合规公司数 | 42家（84%） |
| 不合规公司数 | 8家（16%） |
| 平均基础评分 | 0.92 |
| 平均质量权重 | 0.78 |

### 8.2 完成比例分布

| 区间 | 公司数 | 占比 |
|------|--------|------|
| <40%（未达标） | 3家 | 6% |
| 40%-80% | 28家 | 56% |
| 80%-100% | 16家 | 32% |
| >100%（超额完成） | 3家 | 6% |

### 8.3 典型案例

| 公司 | 完成比例 | 基础评分 | 质量权重 | 综合评分 | 是否合规 |
|------|----------|----------|----------|----------|----------|
| 科大讯飞 | 75.94% | 1.0000 | 0.7609 | 0.7870 | 是 |
| 信立泰 | 301.01% | 0.7329 | 0.7523 | 0.5766 | 否（超额） |
| 韦尔股份 | 74.06% | 1.0000 | 0.8528 | 0.8881 | 是 |

### 8.4 人工复核结果

| 复核项 | 样本数 | 准确率 |
|--------|--------|--------|
| 字段抽取 | 18家 | 98% |
| 完成比例计算 | 18家 | 100% |
| 合规判定 | 18家 | 94% |

---

## 9. 主要局限

### 9.1 数据局限
- **PDF解析依赖**：依赖MinerU解析结果，解析质量影响抽取准确性
- **公告格式多样性**：不同公司公告格式差异较大，部分特殊格式处理困难
- **历史数据有限**：仅分析了50家公司的数据，样本量有限

### 9.2 技术局限
- **LLM调用成本**：补充抽取需要调用LLM API，存在成本开销
- **网络依赖**：LLM调用需要网络连接，离线环境无法使用
- **置信度评估**：LLM抽取置信度固定为0.65，可能与实际准确性有偏差

### 9.3 业务局限
- **不支持复杂交易结构**：对于附带期权、转股等复杂条款的回购处理能力有限
- **缺乏实时监控**：当前为批量分析模式，不支持实时监控新公告
- **仅支持中文公告**：未考虑英文或双语公告

### 9.4 改进方向
1. 增加更多样本数据，提高模型泛化能力
2. 优化正则表达式，减少LLM依赖
3. 增加实时监控功能
4. 支持更多公告格式和语言

---

## 10. 附录

### 10.1 项目文档清单

| 文档 | 说明 |
|------|------|
| README.md | 本文件，项目说明 |
| AGENTS.md | Agent角色定义 |
| ai_usage_statement.md | AI使用声明 |
| ai_worklog_all.md | AI交互日志 |
| outputs/reports/integrated_report_v2.html | 完整技术报告 |
| outputs/reports/summary_report_v2.md | 评估结果汇总 |

### 10.2 运行验证

```bash
# 验证环境配置
python src/pipeline_run.py --step audit

# 查看帮助
python src/pipeline_run.py --help
```

### 10.3 联系方式

如有问题或建议，请联系项目团队。