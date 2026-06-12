import os
import sys
import json
from typing import Dict, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.common import read_json, write_json, log_run
from src.schemas import ConsistencyScore

def calculate_consistency(timeline_path: str, output_path: str) -> None:
    """计算跨阶段一致性评分"""
    timeline_data = read_json(timeline_path)
    events = timeline_data.get('events', [])
    
    consistency_scores = []
    
    for event in events:
        event_id = event['event_id']
        company_name = event['company_name']
        plan = event.get('plan')
        execution = event.get('final_execution')
        
        amount_consistency = 0.0
        period_compliance = 1.0
        price_compliance = 0.0
        completion_ratio = 0.0
        
        if plan and execution:
            plan_upper = plan.get('total_amount_upper')
            actual_amount = execution.get('actual_amount')
            
            if plan_upper and actual_amount:
                completion_ratio = (actual_amount / plan_upper) * 100
                
                if actual_amount <= plan_upper:
                    amount_consistency = 1.0
                else:
                    amount_consistency = 0.5
            
            plan_price_upper = plan.get('price_upper')
            actual_avg_price = execution.get('actual_avg_price')
            
            if plan_price_upper and actual_avg_price:
                if actual_avg_price <= plan_price_upper:
                    price_compliance = 1.0
                else:
                    price_compliance = 0.0
        
        if completion_ratio >= 90:
            completion_level = "高完成"
        elif completion_ratio >= 50:
            completion_level = "中等完成"
        else:
            completion_level = "低完成"
        
        overall_score = (amount_consistency * 0.4 + period_compliance * 0.3 + price_compliance * 0.3)
        
        score = ConsistencyScore(
            event_id=event_id,
            company_name=company_name,
            amount_consistency=amount_consistency,
            period_compliance=period_compliance,
            price_compliance=price_compliance,
            completion_ratio=completion_ratio,
            completion_level=completion_level,
            overall_score=overall_score
        )
        consistency_scores.append(score.dict())
        log_run("calculate_consistency", event_id, "success")
    
    result = {
        "consistency_scores": consistency_scores,
        "summary": {
            "total_events": len(consistency_scores),
            "high_completion": sum(1 for s in consistency_scores if s['completion_level'] == '高完成'),
            "medium_completion": sum(1 for s in consistency_scores if s['completion_level'] == '中等完成'),
            "low_completion": sum(1 for s in consistency_scores if s['completion_level'] == '低完成'),
            "avg_completion_ratio": sum(s['completion_ratio'] for s in consistency_scores) / len(consistency_scores) if consistency_scores else 0,
            "avg_overall_score": sum(s['overall_score'] for s in consistency_scores) / len(consistency_scores) if consistency_scores else 0
        }
    }
    
    write_json(output_path, result)
    print(f"一致性计算完成，共处理 {len(consistency_scores)} 组事件")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="一致性计算")
    parser.add_argument("--timeline", default="outputs/results/event_timelines.json")
    parser.add_argument("--output", default="outputs/reports/consistency_report.json")
    args = parser.parse_args()
    
    calculate_consistency(args.timeline, args.output)