import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

def setup_logging():
    """设置日志配置"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('outputs/logs/app.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def read_jsonl(file_path: str) -> list:
    """读取JSONL文件"""
    results = []
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    results.append(json.loads(line))
    return results

def write_jsonl(file_path: str, data: list, mode: str = 'w') -> None:
    """写入JSONL文件"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, mode, encoding='utf-8') as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

def read_json(file_path: str) -> Optional[Dict[str, Any]]:
    """读取JSON文件"""
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def write_json(file_path: str, data: Dict[str, Any]) -> None:
    """写入JSON文件"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def log_run(step: str, doc_id: str, status: str, error: Optional[str] = None, elapsed: Optional[float] = None):
    """记录运行日志"""
    log_entry = {
        "time": datetime.now().isoformat(),
        "step": step,
        "doc_id": doc_id,
        "status": status,
        "error": error,
        "elapsed": elapsed
    }
    write_jsonl('outputs/logs/run_log.jsonl', [log_entry], mode='a')

def normalize_amount(text: str) -> Optional[float]:
    """标准化金额，支持万元/亿元转换"""
    if not text:
        return None
    
    text = text.replace(',', '').replace('，', '').strip()
    
    import re
    match = re.search(r'([\d.]+)', text)
    if not match:
        return None
    
    amount = float(match.group(1))
    
    if '亿' in text or '亿元' in text:
        return amount
    elif '万' in text or '万元' in text:
        return amount / 10000
    elif '元' in text:
        return amount / 100000000
    else:
        return amount

def normalize_quantity(text: str) -> Optional[float]:
    """标准化数量，支持股/万股转换"""
    if not text:
        return None
    
    text = text.replace(',', '').replace('，', '').strip()
    
    import re
    match = re.search(r'([\d.]+)', text)
    if not match:
        return None
    
    amount = float(match.group(1))
    
    if '万股' in text:
        return amount
    elif '股' in text:
        return amount / 10000
    else:
        return amount