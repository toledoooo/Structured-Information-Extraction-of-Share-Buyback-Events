import os
import sys
import json
from typing import List, Dict, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.common import read_jsonl, write_json, log_run
from src.schemas import EventTimeline

def match_events(validated_path: str, timeline_output_path: str) -> None:
    """匹配同一事件的多阶段公告"""
    results = read_jsonl(validated_path)
    
    events: Dict[str, Dict] = {}
    
    for item in results:
        event_id = item['event_id']
        announcement_type = item['announcement_type']
        
        if event_id not in events:
            events[event_id] = {
                "event_id": event_id,
                "company_name": item['company_name'],
                "stock_code": item['stock_code'],
                "plan_doc_id": None,
                "progress_doc_ids": [],
                "result_doc_id": None,
                "plan": None,
                "executions": []
            }
        
        if announcement_type == "方案公告":
            events[event_id]["plan_doc_id"] = item['doc_id']
            if item.get('plan'):
                events[event_id]["plan"] = item['plan']
        
        elif announcement_type == "进展公告":
            events[event_id]["progress_doc_ids"].append(item['doc_id'])
            if item.get('execution'):
                events[event_id]["executions"].append(item['execution'])
        
        elif announcement_type == "结果公告":
            events[event_id]["result_doc_id"] = item['doc_id']
            if item.get('execution'):
                events[event_id]["executions"].append(item['execution'])
    
    timelines = []
    for event_id, data in events.items():
        final_execution = None
        if data['executions']:
            final_execution = data['executions'][-1]
        
        has_plan = data['plan_doc_id'] is not None
        has_progress = len(data['progress_doc_ids']) > 0
        has_result = data['result_doc_id'] is not None
        
        if has_plan and has_result:
            completeness = 1.0
        elif has_plan and has_progress:
            completeness = 0.6
        elif has_plan:
            completeness = 0.3
        else:
            completeness = 0.0
        
        timeline = EventTimeline(
            event_id=event_id,
            company_name=data['company_name'],
            stock_code=data['stock_code'],
            plan_doc_id=data['plan_doc_id'],
            progress_doc_ids=data['progress_doc_ids'],
            result_doc_id=data['result_doc_id'],
            plan=data['plan'],
            final_execution=final_execution,
            timeline_completeness=completeness
        )
        timelines.append(timeline.dict())
        log_run("match_events", event_id, "success")
    
    write_json(timeline_output_path, {"events": timelines})
    print(f"事件匹配完成，共匹配 {len(timelines)} 组事件")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="事件匹配")
    parser.add_argument("--validated", default="outputs/results/records_validated.jsonl")
    parser.add_argument("--output", default="outputs/results/event_timelines.json")
    args = parser.parse_args()
    
    match_events(args.validated, args.output)