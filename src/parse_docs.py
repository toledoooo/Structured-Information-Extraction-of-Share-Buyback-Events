import os
import sys
import json
import shutil
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.common import log_run, write_jsonl

# 本地MinerU文件夹路径
MINERU_MAPPING_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mineru_mapping.json")

def load_mineru_mapping():
    """加载MinerU文件映射关系"""
    if os.path.exists(MINERU_MAPPING_PATH):
        with open(MINERU_MAPPING_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def extract_info_from_filename(md_name):
    """从MD文件名中提取公司名称和公告类型"""
    # 移除扩展名
    name = md_name.replace('.md', '')
    
    # 提取公司名称（第一个冒号之前的部分）
    if '：' in name:
        company_name = name.split('：')[0]
    elif ':' in name:
        company_name = name.split(':')[0]
    else:
        company_name = name
    
    # 移除公司名称中的空格（与metadata保持一致，如"海 利 得" -> "海利得"）
    company_name_clean = company_name.replace(' ', '')
    
    # 判断公告类型
    announcement_type = "方案公告"  # 默认值
    if '进展' in name:
        announcement_type = "进展公告"
    elif '结果' in name or '完成' in name or '完毕' in name:
        announcement_type = "结果公告"
    
    # 生成标准的 doc_id 后缀
    doc_id_suffix = "plan"
    if announcement_type == "进展公告":
        doc_id_suffix = "progress"
    elif announcement_type == "结果公告":
        doc_id_suffix = "result"
    
    # 检查是否有"期数"信息（如"第2期"），用于区分同一家公司的多个回购方案
    phase_suffix = ""
    import re
    phase_match = re.search(r'第(\d+)期', name)
    if phase_match:
        phase_suffix = f"_v{phase_match.group(1)}"
    
    return company_name, announcement_type, doc_id_suffix, company_name_clean, phase_suffix

def parse_all_pdfs(metadata_path, pdf_dir, output_dir, limit=None, md_dir=None):
    """解析所有PDF文件，优先使用MD文件，处理所有MD文件"""
    import pandas as pd
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取所有MD文件名
    all_md_files = set()
    if md_dir and os.path.exists(md_dir):
        all_md_files = set(f for f in os.listdir(md_dir) if f.endswith('.md'))
    
    parsed_docs = []
    processed_md_files = set()
    used_doc_ids = set()  # 跟踪已使用的doc_id
    
    # 先处理metadata中的记录
    if os.path.exists(metadata_path):
        metadata = pd.read_csv(metadata_path)
        if limit:
            metadata = metadata.head(limit)
        
        for _, row in metadata.iterrows():
            doc_id = row['doc_id']
            pdf_name = row['pdf_path']
            
            # 记录已使用的doc_id
            used_doc_ids.add(doc_id)
            
            # 从PDF文件名获取MD文件名
            md_name = pdf_name.replace('.pdf', '.md')
            
            # 查找MD文件
            md_path = None
            if md_dir and os.path.exists(md_dir):
                md_candidate = os.path.join(md_dir, md_name)
                if os.path.exists(md_candidate):
                    md_path = md_candidate
                    processed_md_files.add(md_name)
                    print(f"找到MD文件: {md_path}")
            
            if not md_path:
                print(f"MD文件不存在: {md_name}")
                log_run("parse", doc_id, "failed", error="MD文件不存在")
                continue
            
            print(f"正在解析: {md_path}")
            
            start_time = datetime.now()
            
            # 读取MD文件内容
            with open(md_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            # MD文档作为单页处理
            pages_info = [{"page_no": 1, "text": md_content}]
            
            # 根据文件名重新判断公告类型（修复metadata中可能的错误标注）
            filename = md_name
            corrected_type = row['announcement_type']
            if '进展' in filename:
                corrected_type = "进展公告"
            elif '结果' in filename or '完成' in filename or '完毕' in filename:
                corrected_type = "结果公告"
            
            # 根据修正后的公告类型重新生成doc_id后缀
            corrected_suffix = "plan"
            if corrected_type == "进展公告":
                corrected_suffix = "progress"
            elif corrected_type == "结果公告":
                corrected_suffix = "result"
            
            # 如果原来的doc_id后缀与修正后的不一致，更新doc_id
            corrected_doc_id = doc_id
            if not doc_id.endswith(f'_{corrected_suffix}'):
                # 移除原来的后缀，添加新后缀
                corrected_doc_id = doc_id.replace('_plan', '').replace('_progress', '').replace('_result', '')
                corrected_doc_id = f"{corrected_doc_id}_{corrected_suffix}"
            
            parsed_doc = {
                "doc_id": corrected_doc_id,
                "company_name": row['company_name'],
                "stock_code": row['stock_code'],
                "announcement_type": corrected_type,
                "announcement_date": row['announcement_date'],
                "pdf_path": os.path.join(pdf_dir, pdf_name) if pdf_dir else pdf_name,
                "markdown_path": md_path,
                "parser": "md-direct",
                "pages": pages_info,
                "parse_time": elapsed
            }
            parsed_docs.append(parsed_doc)
            log_run("parse", doc_id, "success", elapsed=elapsed)
            print(f"  解析完成")
    
    # 处理metadata中未记录但存在的MD文件
    missing_md_files = all_md_files - processed_md_files
    if missing_md_files:
        print(f"\n发现 {len(missing_md_files)} 个未在metadata中记录的MD文件，正在处理...")
        
        for md_name in sorted(missing_md_files):
            md_path = os.path.join(md_dir, md_name)
            print(f"正在解析(补充): {md_path}")
            
            # 从文件名提取信息
            company_name, announcement_type, doc_id_suffix, company_name_clean, phase_suffix = extract_info_from_filename(md_name)
            # 使用干净的公司名称（无空格）生成doc_id，以匹配metadata中的格式
            # 对于补充文件，不使用期数后缀，而是使用序号后缀来避免重复
            doc_id = f"{company_name_clean}_{doc_id_suffix}"
            
            # 如果doc_id已存在，添加序号后缀
            counter = 1
            original_doc_id = doc_id
            while doc_id in used_doc_ids:
                doc_id = f"{original_doc_id}_{counter}"
                counter += 1
            used_doc_ids.add(doc_id)
            
            start_time = datetime.now()
            
            # 读取MD文件内容
            with open(md_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            # MD文档作为单页处理
            pages_info = [{"page_no": 1, "text": md_content}]
            
            parsed_doc = {
                "doc_id": doc_id,
                "company_name": company_name_clean,  # 使用干净的公司名称以匹配metadata
                "stock_code": None,
                "announcement_type": announcement_type,
                "announcement_date": None,
                "pdf_path": None,
                "markdown_path": md_path,
                "parser": "md-direct",
                "pages": pages_info,
                "parse_time": elapsed
            }
            parsed_docs.append(parsed_doc)
            log_run("parse", doc_id, "success", elapsed=elapsed)
            print(f"  解析完成")
    
    output_path = os.path.join(output_dir, "parsed_docs.jsonl")
    write_jsonl(output_path, parsed_docs)
    print(f"\n解析完成，共处理 {len(parsed_docs)} 份文档")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="解析PDF文件")
    parser.add_argument("--metadata", default="data/metadata/metadata.csv")
    parser.add_argument("--pdf_dir", default="data/pdf")
    parser.add_argument("--output_dir", default="data/parsed")
    parser.add_argument("--md_dir", default="data/md")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    
    parse_all_pdfs(args.metadata, args.pdf_dir, args.output_dir, args.limit, args.md_dir)
