import os
import sys
import json
import yaml
from typing import List, Dict, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.common import read_jsonl, write_jsonl, log_run

def load_section_rules(rule_path: str) -> Dict:
    """加载章节路由规则"""
    with open(rule_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def match_section(text: str, include_keywords: List[str], exclude_keywords: List[str]) -> bool:
    """检查文本是否匹配章节规则"""
    text_lower = text.lower()
    
    for exclude in exclude_keywords:
        if exclude.lower() in text_lower:
            return False
    
    for include in include_keywords:
        if include.lower() in text_lower:
            return True
    
    return False

def extract_sections(parsed_docs: List[Dict], rules: Dict) -> List[Dict]:
    """从解析文档中提取目标章节"""
    results = []
    
    for doc in parsed_docs:
        doc_id = doc['doc_id']
        announcement_type = doc['announcement_type']
        
        matched_sections = []
        
        for section_name, rule in rules.get('target_sections', {}).items():
            include_keywords = rule.get('include_keywords', [])
            exclude_keywords = rule.get('exclude_keywords', [])
            min_chars = rule.get('min_chars', 200)
            
            for page in doc['pages']:
                page_text = page['text']
                
                if match_section(page_text, include_keywords, exclude_keywords):
                    if len(page_text) >= min_chars:
                        matched_sections.append({
                            "section_name": section_name,
                            "page_no": page['page_no'],
                            "text": page_text[:5000],
                            "quality_issue": "ok"
                        })
                    else:
                        matched_sections.append({
                            "section_name": section_name,
                            "page_no": page['page_no'],
                            "text": page_text,
                            "quality_issue": "too_short"
                        })
        
        result = {
            "doc_id": doc_id,
            "company_name": doc['company_name'],
            "stock_code": doc['stock_code'],
            "announcement_type": announcement_type,
            "sections": matched_sections,
            "has_target_section": len(matched_sections) > 0
        }
        results.append(result)
        
        log_run("route_sections", doc_id, "success" if matched_sections else "partial")
    
    return results

def generate_section_report(sections_data: List[Dict], output_path: str) -> None:
    """生成章节检查报告"""
    import csv
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'doc_id', 'company_name', 'stock_code', 'announcement_type',
            'found', 'section_count', 'quality_issues'
        ])
        
        for item in sections_data:
            issues = [s['quality_issue'] for s in item['sections'] if s['quality_issue'] != 'ok']
            writer.writerow([
                item['doc_id'],
                item['company_name'],
                item['stock_code'],
                item['announcement_type'],
                item['has_target_section'],
                len(item['sections']),
                ';'.join(issues) if issues else 'none'
            ])

def route_sections(parsed_path: str, rules_path: str, section_report_path: str, sections_output_path: str) -> None:
    """执行章节路由"""
    parsed_docs = read_jsonl(parsed_path)
    rules = load_section_rules(rules_path)
    
    sections_data = extract_sections(parsed_docs, rules)
    write_jsonl(sections_output_path, sections_data)
    generate_section_report(sections_data, section_report_path)
    
    print(f"章节路由完成，共处理 {len(sections_data)} 份文档")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="章节路由")
    parser.add_argument("--parsed", default="data/parsed/parsed_docs.jsonl")
    parser.add_argument("--rules", default="configs/section_rules.yaml")
    parser.add_argument("--section_report", default="outputs/reports/section_check_report.csv")
    parser.add_argument("--output", default="data/parsed/sections.jsonl")
    args = parser.parse_args()
    
    route_sections(args.parsed, args.rules, args.section_report, args.output)