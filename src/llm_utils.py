"""
LLM工具模块 - 使用Kimi API进行智能抽取
"""
import os
import json
from dotenv import load_dotenv
from typing import Dict, Any, Optional

# 加载环境变量
load_dotenv()

# 检查API key是否存在
MOONSHOT_API_KEY = os.getenv("MOONSHOT_API_KEY")
MODEL = os.getenv("MOONSHOT_MODEL", "moonshot-v1-8k")

# 只有在API key存在时才初始化客户端
client = None
if MOONSHOT_API_KEY:
    from openai import OpenAI
    client = OpenAI(
        api_key=MOONSHOT_API_KEY,
        base_url=os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
    )


def call_llm(prompt: str, system_prompt: str = "你是一个专业的金融文档分析助手。") -> Optional[str]:
    """调用LLM生成文本"""
    if not client:
        print("LLM不可用：未配置API key")
        return None
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"LLM调用失败: {e}")
        return None


def extract_fields_with_llm(text: str, announcement_type: str = "方案公告") -> Dict[str, Any]:
    """
    使用LLM从公告文本中抽取结构化字段
    
    Args:
        text: 公告文本内容
        announcement_type: 公告类型（方案公告/进展公告/结果公告）
    
    Returns:
        抽取的结构化数据字典
    """
    # 截取文本（避免超出token限制）
    text = text[:3000]
    
    if announcement_type == "方案公告":
        prompt = f"""请从以下股票回购方案公告中提取关键信息，返回JSON格式数据：

文本内容：
{text}

请严格按照以下JSON格式输出，只输出JSON，不要其他内容：
{{
    "repurchase_method": "回购方式（如：集中竞价交易/要约回购/大宗交易）",
    "total_amount_lower": 最低回购金额（亿元，数字）,
    "total_amount_upper": 最高回购金额（亿元，数字）,
    "price_upper": 回购价格上限（元/股，数字）,
    "repurchase_period_months": 回购期限（月，数字）,
    "funding_source": "资金来源（如：自有资金/募集资金）",
    "repurpose": "回购用途（如：股权激励/员工持股/市值管理/注销）"
}}

注意：
- 金额单位统一转换为亿元
- 如果无法提取某个字段，设为null
- 不要输出任何解释性文字"""
    else:
        # 进展/结果公告
        prompt = f"""请从以下股票回购{announcement_type}中提取执行信息，返回JSON格式数据：

文本内容：
{text}

请严格按照以下JSON格式输出，只输出JSON，不要其他内容：
{{
    "executed_amount": 已使用资金金额（亿元，数字）,
    "executed_quantity": 已回购数量（万股，数字）,
    "average_price": 平均成交价格（元/股，数字）,
    "max_price": 最高成交价格（元/股，数字）,
    "min_price": 最低成交价格（元/股，数字）,
    "completion_ratio": 完成比例（百分比，数字如：50.5表示50.5%）,
    "announcement_date": 公告日期（YYYY-MM-DD格式）
}}

注意：
- 金额单位统一转换为亿元
- 数量单位统一转换为万股
- 如果无法提取某个字段，设为null
- 不要输出任何解释性文字"""
    
    try:
        response = call_llm(prompt)
        if response:
            # 尝试解析JSON
            # 清理可能的markdown代码块
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            
            # 清理超长浮点数（Kimi可能返回精度极高的数字）
            import re
            response = re.sub(r'(\d+\.\d{10,})\d+', r'\1', response.strip())
            
            result = json.loads(response)
            return result
        return {}
    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}")
        print(f"原始响应: {response[:500]}...")
        return {}
    except Exception as e:
        print(f"LLM抽取失败: {e}")
        return {}


def validate_and_analyze(plan_data: Dict, execution_data: Dict, company_name: str) -> Dict[str, Any]:
    """
    使用LLM验证方案与执行数据的一致性
    
    Args:
        plan_data: 方案公告数据
        execution_data: 执行数据
        company_name: 公司名称
    
    Returns:
        分析结果字典
    """
    prompt = f"""请分析以下{company_name}的股票回购方案与执行结果的一致性：

方案数据：
{json.dumps(plan_data, ensure_ascii=False, indent=2)}

执行数据：
{json.dumps(execution_data, ensure_ascii=False, indent=2)}

请输出JSON格式分析结果：
{{
    "consistency_score": 一致性评分（0-1之间的数字）,
    "amount_compliance": "金额合规性（合规/部分合规/不合规）",
    "price_compliance": "价格合规性（合规/部分合规/不合规）",
    "execution_rate": 执行完成比例（数字）,
    "analysis": "详细分析说明（100字以内）",
    "issues": ["发现的问题列表"]
}}

只输出JSON格式，不要其他内容。"""
    
    try:
        response = call_llm(prompt)
        if response:
            result = json.loads(response.strip())
            return result
        return {}
    except Exception as e:
        print(f"LLM分析失败: {e}")
        return {}


def generate_summary_report(analysis_results: list) -> str:
    """
    使用LLM生成综合分析报告
    
    Args:
        analysis_results: 分析结果列表
    
    Returns:
        报告文本
    """
    prompt = f"""请基于以下50家公司的股票回购分析数据，生成一份专业的综合分析报告：

数据概览：
{json.dumps(analysis_results[:10], ensure_ascii=False, indent=2)}

请撰写一份中文分析报告，包含：
1. 整体完成情况概览
2. 完成率分布分析
3. 关键发现和趋势
4. 典型案例分析（选取2-3个代表性公司）

要求：
- 语言专业但易懂
- 突出数据洞察
- 篇幅适中（约500字）
"""
    
    response = call_llm(prompt, system_prompt="你是一个资深的金融分析师，擅长撰写专业的分析报告。")
    return response if response else "报告生成失败"


if __name__ == "__main__":
    # 测试代码
    test_text = """
    三七互娱公告：公司拟使用自有资金以集中竞价交易方式回购股份，
    回购资金总额不低于3亿元，不超过5亿元，
    回购价格不超过20元/股，
    回购期限为6个月，
    回购股份将用于实施股权激励计划。
    """
    
    print("测试LLM抽取：")
    result = extract_fields_with_llm(test_text, "方案公告")
    print(json.dumps(result, ensure_ascii=False, indent=2))
