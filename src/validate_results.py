import os
import sys
import json
import csv
from typing import List, Dict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.common import read_jsonl, write_jsonl, log_run
from src.schemas import RepurchaseExtract

def validate_results(extract_path: str, validated_path: str, errors_path: str) -> None:
    """校验抽取结果"""
    results = read_jsonl(extract_path)
    validated = []
    errors = []
    
    for i, item in enumerate(results):
        try:
            extract_obj = RepurchaseExtract(**item)
            validated.append(extract_obj.dict())
            log_run("validate", item['doc_id'], "success")
        except Exception as e:
            error_entry = {
                "index": i,
                "doc_id": item.get('doc_id', 'unknown'),
                "error": str(e),
                "original_data": item
            }
            errors.append(error_entry)
            log_run("validate", item.get('doc_id', 'unknown'), "failed", error=str(e))
    
    write_jsonl(validated_path, validated)
    write_jsonl(errors_path, errors)
    
    print(f"校验完成，有效记录: {len(validated)}, 错误记录: {len(errors)}")

def convert_to_csv(jsonl_path: str, csv_path: str) -> None:
    """将JSONL转换为CSV"""
    results = read_jsonl(jsonl_path)
    
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        fieldnames = [
            'doc_id', 'company_name', 'stock_code', 'event_id',
            'announcement_type', 'announcement_date',
            'repurchase_method', 'total_amount_upper', 'total_amount_lower',
            'price_upper', 'price_lower', 'repurchase_period_months',
            'funding_source', 'repurpose',
            'actual_amount', 'actual_quantity', 'actual_avg_price',
            'extraction_confidence'
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for item in results:
            row = {
                'doc_id': item['doc_id'],
                'company_name': item['company_name'],
                'stock_code': item['stock_code'],
                'event_id': item['event_id'],
                'announcement_type': item['announcement_type'],
                'announcement_date': item.get('announcement_date', ''),
                'extraction_confidence': item.get('extraction_confidence', '')
            }
            
            if item.get('plan'):
                row.update({
                    'repurchase_method': item['plan'].get('repurchase_method', ''),
                    'total_amount_upper': item['plan'].get('total_amount_upper', ''),
                    'total_amount_lower': item['plan'].get('total_amount_lower', ''),
                    'price_upper': item['plan'].get('price_upper', ''),
                    'price_lower': item['plan'].get('price_lower', ''),
                    'repurchase_period_months': item['plan'].get('repurchase_period_months', ''),
                    'funding_source': item['plan'].get('funding_source', ''),
                    'repurpose': item['plan'].get('repurpose', '')
                })
            
            if item.get('execution'):
                row.update({
                    'actual_amount': item['execution'].get('actual_amount', ''),
                    'actual_quantity': item['execution'].get('actual_quantity', ''),
                    'actual_avg_price': item['execution'].get('actual_avg_price', '')
                })
            
            writer.writerow(row)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="结果校验")
    parser.add_argument("--extract", default="outputs/results/extract_results.jsonl")
    parser.add_argument("--validated", default="outputs/results/records_validated.jsonl")
    parser.add_argument("--errors", default="outputs/logs/validation_errors.jsonl")
    parser.add_argument("--csv", default="outputs/results/records_validated.csv")
    args = parser.parse_args()
    
    validate_results(args.extract, args.validated, args.errors)
    convert_to_csv(args.validated, args.csv)