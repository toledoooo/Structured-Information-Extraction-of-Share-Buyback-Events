"""
质量感知的一致性计算器
将质量指标与一致性计算深度融合，实现动态加权评分和智能问题追溯
"""
import json
from typing import Dict, Any, Optional, List
from src.quality_metrics import QualityMetrics


class QualityAwareConsistencyCalculator:
    """质量感知的一致性计算器"""
    
    def __init__(self):
        self.quality_metrics = QualityMetrics()
    
    def calculate_base_consistency(self, plan_data: Dict, execution_data: Dict) -> Dict[str, float]:
        """
        计算基础一致性指标
        返回：金额一致性、价格合规性、期限合规性
        """
        # 金额一致性（处理None值）
        plan_upper = plan_data.get('total_amount_upper') or 0
        actual_amount = execution_data.get('actual_amount') or 0
        
        if plan_upper > 0 and actual_amount > 0:
            amount_consistency = 1.0 if actual_amount <= plan_upper else min(plan_upper / actual_amount, 1.0)
        else:
            amount_consistency = 0.5  # 默认值
        
        # 价格合规性（处理None值）
        plan_price_upper = plan_data.get('price_upper') or 0
        actual_avg_price = execution_data.get('actual_avg_price') or 0
        
        if plan_price_upper > 0 and actual_avg_price > 0:
            price_compliance = 1.0 if actual_avg_price <= plan_price_upper else min(plan_price_upper / actual_avg_price, 1.0)
        else:
            price_compliance = 0.5  # 默认值
        
        # 期限合规性（默认合规）
        period_compliance = plan_data.get('period_compliance', 1.0)
        
        # 完成比例
        if plan_upper > 0 and actual_amount > 0:
            completion_ratio = (actual_amount / plan_upper) * 100
        else:
            completion_ratio = 0.0
        
        return {
            'amount_consistency': amount_consistency,
            'price_compliance': price_compliance,
            'period_compliance': period_compliance,
            'completion_ratio': completion_ratio
        }
    
    def calculate_quality_weight(self, quality_scores: Dict[str, float]) -> float:
        """
        计算综合质量权重
        权重分配：Data(20%) + Section(15%) + Extraction(30%) + Evidence(20%) + Stability(15%)
        """
        return self.quality_metrics.calculate_composite_weight(quality_scores)
    
    def calculate_dynamic_threshold(self, quality_weight: float) -> float:
        """
        根据质量权重动态调整一致性判断阈值（中等严格模式）
        - 高质量数据(W>0.9): 阈值0.88
        - 中等质量数据(W>0.7): 阈值0.75
        - 低质量数据(W<=0.7): 阈值0.65，需人工复核
        """
        if quality_weight > 0.9:
            return 0.88, False
        elif quality_weight > 0.7:
            return 0.75, False
        else:
            return 0.65, True
    
    def analyze_quality_impact(self, quality_scores: Dict[str, float]) -> Dict[str, List[str]]:
        """
        分析质量指标对一致性评分的影响
        返回正向和负向影响因素
        """
        positive = []
        negative = []
        
        thresholds = {
            'data_quality': 0.8,
            'section_quality': 0.75,
            'extraction_quality': 0.8,
            'evidence_quality': 0.75,
            'pipeline_stability': 0.9
        }
        
        quality_names = {
            'data_quality': '数据质量',
            'section_quality': '章节质量',
            'extraction_quality': '抽取质量',
            'evidence_quality': '证据质量',
            'pipeline_stability': '流程稳定性'
        }
        
        for key, threshold in thresholds.items():
            score = quality_scores.get(key, 0.5)
            if score >= threshold:
                positive.append(f"{quality_names[key]}高({score:.2f})")
            elif score < 0.6:
                negative.append(f"{quality_names[key]}低({score:.2f})")
        
        return {
            'positive': positive,
            'negative': negative
        }
    
    def calculate(self, plan_data: Dict, execution_data: Dict, 
                  quality_scores: Dict[str, float], company_name: str = '') -> Dict[str, Any]:
        """
        执行质量感知的一致性计算
        """
        # 1. 计算基础一致性指标
        base_metrics = self.calculate_base_consistency(plan_data, execution_data)
        
        # 2. 计算综合质量权重
        quality_weight = self.calculate_quality_weight(quality_scores)
        
        # 3. 计算基础评分（传统一致性评分）
        base_score = (
            base_metrics['amount_consistency'] * 0.4 +
            base_metrics['price_compliance'] * 0.3 +
            base_metrics['period_compliance'] * 0.3
        )
        
        # 4. 质量加权修正
        adjusted_score = base_score * quality_weight
        
        # 5. 质量奖励分（高质量数据额外加分）
        quality_bonus = (quality_weight - 0.5) * 0.1 if quality_weight > 0.5 else 0
        final_score = adjusted_score + quality_bonus
        
        # 6. 动态阈值调整
        compliance_threshold, needs_review = self.calculate_dynamic_threshold(quality_weight)
        
        # 7. 质量影响分析
        quality_impact = self.analyze_quality_impact(quality_scores)
        
        # 8. 判断是否合规（增加额外的异常情况判定）
        completion_ratio = base_metrics['completion_ratio']
        
        # 基础判定：综合评分是否达到阈值
        base_compliant = final_score >= compliance_threshold
        
        # 额外判定：排除异常完成比例
        # - 超额完成超过110%（可能存在数据问题）
        # - 完成比例低于40%（明显未达标）
        excessive_completion = completion_ratio > 110
        insufficient_completion = completion_ratio < 40
        
        # 综合判定
        is_compliant = base_compliant and not excessive_completion and not insufficient_completion
        
        # 9. 问题追溯
        issues = self._identify_issues(base_metrics, quality_scores, final_score, compliance_threshold)
        
        return {
            'event_id': company_name,
            'company_name': company_name,
            'base_metrics': base_metrics,
            'base_score': round(base_score, 4),
            'quality_scores': quality_scores,
            'quality_weight': round(quality_weight, 4),
            'adjusted_score': round(adjusted_score, 4),
            'final_score': round(min(final_score, 1.0), 4),
            'confidence': round(quality_weight, 4),
            'compliance_threshold': compliance_threshold,
            'is_compliant': is_compliant,
            'needs_review': needs_review,
            'quality_impact': quality_impact,
            'issues': issues,
            'completion_ratio': round(base_metrics['completion_ratio'], 2)
        }
    
    def _identify_issues(self, base_metrics: Dict, quality_scores: Dict, 
                         final_score: float, threshold: float) -> List[str]:
        """
        识别影响一致性的问题
        """
        issues = []
        
        # 一致性问题
        if base_metrics['amount_consistency'] < 0.8:
            issues.append(f"金额一致性低({base_metrics['amount_consistency']:.2f})")
        if base_metrics['price_compliance'] < 0.8:
            issues.append(f"价格合规性低({base_metrics['price_compliance']:.2f})")
        if base_metrics['completion_ratio'] < 50:
            issues.append(f"完成比例低于50%({base_metrics['completion_ratio']:.1f}%)")
        
        # 质量问题
        if quality_scores.get('extraction_quality', 0) < 0.6:
            issues.append("抽取质量低，建议复核字段值")
        if quality_scores.get('evidence_quality', 0) < 0.6:
            issues.append("证据质量低，建议检查证据链")
        
        # 综合问题
        if final_score < threshold:
            issues.append(f"综合评分低于阈值({final_score:.2f} < {threshold})")
        
        return issues


def generate_quality_consistency_report(events: List[Dict]) -> Dict[str, Any]:
    """
    生成质量-一致性综合报告
    """
    # 统计数据
    total_events = len(events)
    compliant_count = sum(1 for e in events if e['is_compliant'])
    avg_final_score = sum(e['final_score'] for e in events) / total_events
    avg_quality_weight = sum(e['quality_weight'] for e in events) / total_events
    
    # 质量分布
    quality_buckets = {
        'high': sum(1 for e in events if e['quality_weight'] > 0.8),
        'medium': sum(1 for e in events if 0.6 <= e['quality_weight'] <= 0.8),
        'low': sum(1 for e in events if e['quality_weight'] < 0.6)
    }
    
    # 完成程度分布
    completion_buckets = {
        'high': sum(1 for e in events if e['completion_ratio'] >= 90),
        'medium': sum(1 for e in events if 50 <= e['completion_ratio'] < 90),
        'low': sum(1 for e in events if e['completion_ratio'] < 50)
    }
    
    # 需要人工复核的事件
    needs_review_events = [e['event_id'] for e in events if e['needs_review']]
    
    # 问题汇总
    all_issues = []
    for e in events:
        for issue in e['issues']:
            all_issues.append(issue)
    top_issues = {}
    for issue in all_issues:
        top_issues[issue] = top_issues.get(issue, 0) + 1
    top_issues = sorted(top_issues.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return {
        'summary': {
            'total_events': total_events,
            'compliant_count': compliant_count,
            'compliance_rate': round(compliant_count / total_events * 100, 2),
            'avg_final_score': round(avg_final_score, 4),
            'avg_quality_weight': round(avg_quality_weight, 4),
            'quality_distribution': quality_buckets,
            'completion_distribution': completion_buckets,
            'needs_review_count': len(needs_review_events),
            'needs_review_events': needs_review_events
        },
        'top_issues': top_issues,
        'detailed_scores': events
    }


if __name__ == "__main__":
    # 测试质量感知一致性计算
    test_plan = {
        'total_amount_upper': 50.0,
        'price_upper': 200.0,
        'repurchase_period_months': 6
    }
    
    test_execution = {
        'actual_amount': 49.8,
        'actual_avg_price': 185.5
    }
    
    test_quality = {
        'data_quality': 0.92,
        'section_quality': 0.88,
        'extraction_quality': 0.95,
        'evidence_quality': 0.90,
        'pipeline_stability': 0.98
    }
    
    calculator = QualityAwareConsistencyCalculator()
    result = calculator.calculate(test_plan, test_execution, test_quality, '比亚迪')
    
    print("=== 质量感知一致性计算测试 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # 测试报告生成
    report = generate_quality_consistency_report([result])
    print("\n=== 综合报告 ===")
    print(json.dumps(report['summary'], ensure_ascii=False, indent=2))
