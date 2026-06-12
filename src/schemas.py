from typing import Optional, Literal, List
from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """证据信息"""
    evidence_doc_type: Literal["方案公告", "进展公告", "结果公告"] = Field(description="证据来源文档类型")
    evidence_text: str = Field(description="原文片段（100字内）")
    page_no: Optional[int] = Field(default=None, description="证据所在页码")


class RepurchasePlan(BaseModel):
    """回购方案信息"""
    repurchase_method: Optional[Literal["集中竞价交易", "要约回购", "其他"]] = Field(
        default=None, description="回购方式"
    )
    total_amount_upper: Optional[float] = Field(
        default=None, description="回购资金总额上限（亿元）"
    )
    total_amount_lower: Optional[float] = Field(
        default=None, description="回购资金总额下限（亿元）"
    )
    price_upper: Optional[float] = Field(
        default=None, description="回购价格上限（元/股）"
    )
    price_lower: Optional[float] = Field(
        default=None, description="回购价格下限（元/股）"
    )
    repurchase_period_months: Optional[int] = Field(
        default=None, description="实施期限（月）"
    )
    funding_source: Optional[str] = Field(
        default=None, description="资金来源"
    )
    repurpose: Optional[Literal["股权激励", "员工持股计划", "市值管理", "注销减少注册资本", "其他"]] = Field(
        default=None, description="回购用途"
    )


class RepurchaseExecution(BaseModel):
    """回购执行信息"""
    actual_amount: Optional[float] = Field(
        default=None, description="实际回购金额（亿元）"
    )
    actual_quantity: Optional[float] = Field(
        default=None, description="实际回购数量（万股）"
    )
    actual_avg_price: Optional[float] = Field(
        default=None, description="实际回购均价（元/股）"
    )


class RepurchaseExtract(BaseModel):
    """回购公告抽取结果"""
    doc_id: str = Field(description="文档唯一标识")
    company_name: str = Field(description="公司名称")
    stock_code: str = Field(description="股票代码")
    event_id: str = Field(description="事件唯一标识")
    announcement_type: Literal["方案公告", "进展公告", "结果公告"] = Field(description="公告类型")
    announcement_date: str = Field(description="公告日期")
    
    plan: Optional[RepurchasePlan] = Field(default=None, description="方案信息")
    execution: Optional[RepurchaseExecution] = Field(default=None, description="执行信息")
    
    evidence: List[Evidence] = Field(default_factory=list, description="证据列表")
    extraction_confidence: Optional[float] = Field(default=None, description="抽取置信度")


class EventTimeline(BaseModel):
    """事件时间线"""
    event_id: str = Field(description="事件唯一标识")
    company_name: str = Field(description="公司名称")
    stock_code: str = Field(description="股票代码")
    plan_doc_id: Optional[str] = Field(default=None, description="方案公告ID")
    progress_doc_ids: List[str] = Field(default_factory=list, description="进展公告ID列表")
    result_doc_id: Optional[str] = Field(default=None, description="结果公告ID")
    plan: Optional[RepurchasePlan] = Field(default=None, description="方案信息")
    final_execution: Optional[RepurchaseExecution] = Field(default=None, description="最终执行信息")
    timeline_completeness: float = Field(description="时间线完整度(0-1)")


class ConsistencyScore(BaseModel):
    """一致性评分"""
    event_id: str = Field(description="事件唯一标识")
    company_name: str = Field(description="公司名称")
    amount_consistency: float = Field(description="金额一致性(0-1)")
    period_compliance: float = Field(description="期限合规性(0-1)")
    price_compliance: float = Field(description="价格合规性(0-1)")
    completion_ratio: float = Field(description="完成比例(%)")
    completion_level: Literal["高完成", "中等完成", "低完成"] = Field(description="完成程度分级")
    overall_score: float = Field(description="综合一致性评分(0-1)")