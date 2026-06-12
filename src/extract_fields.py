import os
import sys
import json
import re
import hashlib
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.common import log_run, write_jsonl, normalize_amount, normalize_quantity
from src.schemas import RepurchaseExtract, Evidence

# 导入LLM工具
try:
    from src.llm_utils import extract_fields_with_llm, call_llm
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    print("警告：LLM工具模块未找到，将使用纯正则方法")

# 优化配置
MAX_WORKERS = 30  # 并行处理的最大线程数
CACHE_ENABLED = True  # 是否启用缓存
CACHE_DIR = "outputs/cache"  # 缓存目录

# 确保缓存目录存在
os.makedirs(CACHE_DIR, exist_ok=True)

# 证据来源权重配置
SOURCE_WEIGHTS = {
    'regex_high_confidence': 0.95,
    'regex_medium_confidence': 0.85,
    'regex_low_confidence': 0.7,
    'llm_direct': 0.75,
    'llm_supplement': 0.6,
    'rule_based': 0.88,
    'cross_validated': 0.98
}

def get_cache_key(text: str, announcement_type: str) -> str:
    """生成缓存键，基于文本内容和公告类型"""
    content_hash = hashlib.md5(f"{text[:5000]}{announcement_type}".encode('utf-8')).hexdigest()
    return content_hash

def load_cache(cache_key: str) -> Optional[Tuple[Dict, List]]:
    """从缓存加载抽取结果"""
    if not CACHE_ENABLED:
        return None
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('result'), data.get('evidences')
        except Exception:
            return None
    return None

def save_cache(cache_key: str, result: Dict, evidences: List):
    """保存抽取结果到缓存"""
    if not CACHE_ENABLED:
        return
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.json")
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump({'result': result, 'evidences': evidences}, f, ensure_ascii=False)
    except Exception as e:
        print(f"缓存保存失败: {e}")

def clean_number(num_str: str) -> Optional[float]:
    """清理数字字符串，处理千位分隔符"""
    if not num_str:
        return None
    cleaned = num_str.replace(',', '').replace('，', '').replace(' ', '').strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None

def extract_context(text: str, match_start: int, match_end: int, context_len: int = 80) -> str:
    """
    提取匹配文本的上下文（增强版）
    :param text: 原始文本
    :param match_start: 匹配开始位置
    :param match_end: 匹配结束位置
    :param context_len: 前后上下文长度
    :return: 包含上下文的文本
    """
    start = max(0, match_start - context_len)
    end = min(len(text), match_end + context_len)
    
    # 找到上下文的边界（中文标点）
    chinese_punctuation = ['。', '！', '？', '；', '：', '\n', '\r', '、', '，', '（', '）']
    while start > 0 and text[start] not in chinese_punctuation:
        start -= 1
    while end < len(text) and text[end] not in chinese_punctuation:
        end += 1
    
    # 如果上下文太短，扩大范围
    result = text[start:end].strip()
    if len(result) < 30 and context_len < 200:
        return extract_context(text, match_start, match_end, context_len * 2)
    
    return result

def extract_sentence_context(text: str, match_pos: int, window_size: int = 2) -> str:
    """
    提取匹配位置周围的完整句子作为上下文
    :param text: 原始文本
    :param match_pos: 匹配位置
    :param window_size: 前后句子数量
    :return: 包含上下文句子的文本
    """
    # 按句子分割
    sentences = re.split(r'[。！？；：\n\r]+', text)
    
    # 找到匹配所在的句子
    pos = 0
    target_sentence_idx = -1
    for i, sentence in enumerate(sentences):
        if pos <= match_pos < pos + len(sentence):
            target_sentence_idx = i
            break
        pos += len(sentence) + 1  # +1 for separator
    
    if target_sentence_idx == -1:
        return ""
    
    # 获取上下文句子
    start_idx = max(0, target_sentence_idx - window_size)
    end_idx = min(len(sentences), target_sentence_idx + window_size + 1)
    
    return '。'.join(sentences[start_idx:end_idx]) + '。'

def calculate_confidence(source: str, match_quality: float = 1.0, context_strength: float = 1.0, 
                       cross_validation: bool = False) -> float:
    """
    动态计算证据置信度
    :param source: 证据来源类型
    :param match_quality: 匹配质量 (0-1)
    :param context_strength: 上下文支撑强度 (0-1)
    :param cross_validation: 是否经过交叉验证
    :return: 综合置信度 (0-1)
    """
    base_weight = SOURCE_WEIGHTS.get(source, 0.7)
    
    # 应用匹配质量调整
    quality_adjusted = base_weight * (0.7 + match_quality * 0.3)
    
    # 应用上下文支撑调整
    context_adjusted = quality_adjusted * (0.85 + context_strength * 0.15)
    
    # 交叉验证加成
    if cross_validation:
        context_adjusted = min(0.98, context_adjusted * 1.05)
    
    return round(context_adjusted, 4)

def evaluate_match_quality(pattern: str, match_text: str, field_value) -> float:
    """
    评估匹配质量
    :param pattern: 使用的正则模式
    :param match_text: 匹配到的文本
    :param field_value: 提取的字段值
    :return: 匹配质量分数 (0-1)
    """
    score = 0.0
    
    # 1. 匹配长度评估
    if len(match_text) >= 10:
        score += 0.3
    elif len(match_text) >= 5:
        score += 0.2
    else:
        score += 0.1
    
    # 2. 字段值在匹配文本中的覆盖率
    if field_value is not None:
        value_str = str(field_value)
        if value_str in match_text:
            score += 0.4
        elif re.search(r'[\d.]+', value_str):
            # 检查数字部分是否匹配
            value_num = re.findall(r'[\d.]+', value_str)[0]
            if value_num in match_text:
                score += 0.3
    
    # 3. 模式复杂度评估（更复杂的模式匹配更可靠）
    pattern_complexity = len(pattern) / 20  # 归一化
    score += min(pattern_complexity, 0.3)
    
    return min(score, 1.0)

def evaluate_context_strength(context: str, field_name: str) -> float:
    """
    评估上下文支撑强度
    :param context: 上下文文本
    :param field_name: 字段名称
    :return: 上下文强度分数 (0-1)
    """
    score = 0.0
    
    if not context:
        return 0.5
    
    # 关键字上下文检查
    field_keywords = {
        'repurchase_method': ['回购', '方式', '集中竞价', '要约', '大宗'],
        'total_amount_upper': ['金额', '资金', '亿元', '万元', '上限'],
        'total_amount_lower': ['金额', '资金', '亿元', '万元', '下限'],
        'price_upper': ['价格', '元/股', '上限', '每股'],
        'repurchase_period_months': ['期限', '月', '内', '完成'],
        'funding_source': ['资金', '来源', '自有', '募集', '借款'],
        'repurpose': ['用途', '用于', '股权激励', '注销', '员工持股'],
        'actual_amount': ['成交', '金额', '已回购', '使用'],
        'actual_quantity': ['数量', '股', '万股', '回购'],
        'actual_avg_price': ['均价', '成交价', '价格'],
    }
    
    keywords = field_keywords.get(field_name, [])
    matched_keywords = sum(1 for kw in keywords if kw in context)
    
    if matched_keywords >= 2:
        score = 1.0
    elif matched_keywords == 1:
        score = 0.7
    else:
        score = 0.4
    
    # 上下文长度加分
    if len(context) >= 50:
        score = min(1.0, score + 0.1)
    
    return score

def create_evidence(field_name: str, field_value, match_text: str, source: str, 
                   context: str = "", confidence: float = None, 
                   match_quality: float = 1.0, cross_validation: bool = False) -> Dict:
    """
    创建标准证据对象（增强版）
    :param field_name: 字段名
    :param field_value: 字段值
    :param match_text: 匹配的原始文本
    :param source: 来源（regex_high_confidence/regex_medium_confidence/llm_direct/rule_based等）
    :param context: 上下文文本
    :param confidence: 置信度（如果不提供则自动计算）
    :param match_quality: 匹配质量
    :param cross_validation: 是否经过交叉验证
    :return: 证据字典
    """
    # 自动计算置信度
    if confidence is None:
        context_strength = evaluate_context_strength(context, field_name)
        confidence = calculate_confidence(source, match_quality, context_strength, cross_validation)
    
    return {
        "field": field_name,
        "value": field_value,
        "text": match_text,
        "context": context,
        "source": source,
        "confidence": confidence,
        "page_no": 1,  # MD文档默认为第1页
        "match_quality": match_quality,
        "cross_validated": cross_validation
    }

def validate_evidence(evidence: Dict, field_rules: Dict = None) -> Tuple[bool, str]:
    """
    验证证据有效性
    :param evidence: 证据对象
    :param field_rules: 字段规则
    :return: (是否有效, 验证信息)
    """
    field_name = evidence.get('field')
    value = evidence.get('value')
    
    # 基础检查
    if not field_name or value is None:
        return False, "字段名或值为空"
    
    # 数值范围检查
    numeric_rules = {
        'total_amount_upper': (0, 10000),    # 亿元
        'total_amount_lower': (0, 10000),
        'price_upper': (0, 10000),           # 元/股
        'repurchase_period_months': (1, 60), # 月
        'actual_amount': (0, 10000),
        'actual_quantity': (0, 1000000),    # 万股
        'actual_avg_price': (0, 10000),
    }
    
    if field_name in numeric_rules:
        min_val, max_val = numeric_rules[field_name]
        try:
            num_value = float(value)
            if num_value <= min_val or num_value > max_val:
                return False, f"数值超出合理范围 [{min_val}, {max_val}]"
        except (ValueError, TypeError):
            return False, "数值格式错误"
    
    # 字符串字段检查
    string_rules = {
        'repurchase_method': ['集中竞价交易', '要约回购', '大宗交易', '协议转让'],
        'funding_source': ['自有资金', '募集资金', '金融机构借款', '流动资金', '自筹资金'],
        'repurpose': ['股权激励', '员工持股计划', '市值管理', '注销减少注册资本', '库存股'],
    }
    
    if field_name in string_rules:
        valid_values = string_rules[field_name]
        if value not in valid_values:
            # 允许部分匹配（提高灵活性）
            matched = any(valid_val in str(value) for valid_val in valid_values)
            if not matched:
                return False, f"不在有效值列表中: {valid_values}"
    
    return True, "验证通过"

def resolve_conflicts(evidences: List[Dict]) -> List[Dict]:
    """
    解决证据冲突（同一字段有多个不同值）
    :param evidences: 证据列表
    :return: 去重并解决冲突后的证据列表
    """
    field_groups = {}
    
    # 按字段分组
    for e in evidences:
        field = e['field']
        if field not in field_groups:
            field_groups[field] = []
        field_groups[field].append(e)
    
    resolved = []
    
    for field, items in field_groups.items():
        if len(items) == 1:
            # 只有一个证据，直接保留
            resolved.append(items[0])
        else:
            # 多个证据，需要解决冲突
            # 策略：选择置信度最高的，或进行交叉验证
            items.sort(key=lambda x: x['confidence'], reverse=True)
            
            top_item = items[0]
            second_item = items[1] if len(items) > 1 else None
            
            if second_item and top_item['confidence'] - second_item['confidence'] < 0.1:
                # 置信度接近，检查是否值相同
                if str(top_item['value']) == str(second_item['value']):
                    # 值相同，合并并标记交叉验证
                    merged = top_item.copy()
                    merged['cross_validated'] = True
                    merged['confidence'] = min(0.98, top_item['confidence'] * 1.03)
                    resolved.append(merged)
                else:
                    # 值不同，保留置信度更高的，记录冲突
                    top_item['conflict_notes'] = f"存在冲突值: {second_item['value']} (置信度: {second_item['confidence']})"
                    resolved.append(top_item)
            else:
                # 置信度差距较大，直接保留最高的
                resolved.append(top_item)
    
    return resolved

def extract_from_plan(text: str) -> Dict[str, Any]:
    """从方案公告中抽取字段（正则+LLM混合模式，增强版）"""
    result = {}
    evidences = []
    llm_result = {}

    # 去除换行符，使跨行文本连续，但保留空格
    text = text.replace('\n', ' ').replace('\r', ' ')
    
    # 第一步：使用正则表达式抽取（带质量评估）
    method_patterns = [
        (r'(集中竞价交易)', 'regex_high_confidence'),
        (r'(集中竞价方式)', 'regex_high_confidence'),
        (r'(集中竞价)', 'regex_high_confidence'),
        (r'(要约回购)', 'regex_high_confidence'),
        (r'(大宗交易)', 'regex_high_confidence'),
        (r'(协议转让)', 'regex_high_confidence')
    ]
    for pattern, source_type in method_patterns:
        match = re.search(pattern, text)
        if match:
            method = match.group(1)
            # 统一回购方式名称，将"集中竞价方式"映射为"集中竞价交易"
            if method in ['集中竞价方式', '集中竞价']:
                method = '集中竞价交易'
            result['repurchase_method'] = method
            
            # 获取上下文和句子级上下文
            context = extract_context(text, match.start(), match.end())
            sentence_context = extract_sentence_context(text, match.start())
            
            # 评估匹配质量
            match_quality = evaluate_match_quality(pattern, match.group(0), method)
            
            # 创建证据（自动计算置信度）
            evidence = create_evidence(
                "repurchase_method", method, match.group(0), source_type, 
                context=context + " " + sentence_context.strip(),
                match_quality=match_quality
            )
            
            # 验证证据
            is_valid, msg = validate_evidence(evidence)
            if is_valid:
                evidences.append(evidence)
            else:
                evidence['validation_error'] = msg
                evidences.append(evidence)
            break
    
    amount_patterns = [
        (r'不低于.*?([\d,，.]+)\s*(万元).*?不超过.*?([\d,，.]+)\s*(万元)', 'regex_high_confidence'),
        (r'不低于.*?([\d,，.]+)\s*(亿元).*?不超过.*?([\d,，.]+)\s*(亿元)', 'regex_high_confidence'),
        (r'([\d,，.]+)\s*(万元).*?至.*?([\d,，.]+)\s*(万元)', 'regex_high_confidence'),
        (r'([\d,，.]+)\s*(亿元).*?至.*?([\d,，.]+)\s*(亿元)', 'regex_high_confidence'),
        (r'回购资金总额.*?([\d,，.]+)\s*(万元).*?([\d,，.]+)\s*(万元)', 'regex_high_confidence'),
        (r'回购资金总额.*?([\d,，.]+)\s*(亿元).*?([\d,，.]+)\s*(亿元)', 'regex_high_confidence'),
        (r'回购金额.*?([\d,，.]+)\s*(亿元).*?至.*?([\d,，.]+)\s*(亿元)', 'regex_high_confidence'),
        (r'回购金额.*?([\d,，.]+)\s*(万元).*?至.*?([\d,，.]+)\s*(万元)', 'regex_high_confidence'),
        (r'([\d,，.]+)\s*(亿元)\s*到\s*([\d,，.]+)\s*(亿元)', 'regex_medium_confidence'),
        (r'([\d,，.]+)\s*(万元)\s*到\s*([\d,，.]+)\s*(万元)', 'regex_medium_confidence'),
        (r'金额.*?([\d,，.]+)\s*(亿元).*?([\d,，.]+)\s*(亿元)', 'regex_medium_confidence'),
        (r'金额.*?([\d,，.]+)\s*(万元).*?([\d,，.]+)\s*(万元)', 'regex_medium_confidence')
    ]
    
    for pattern, source_type in amount_patterns:
        match = re.search(pattern, text)
        if match:
            unit1 = match.group(2)
            unit2 = match.group(4) if len(match.groups()) > 3 else match.group(2)
            lower = clean_number(match.group(1))
            upper = clean_number(match.group(3))
            
            if unit1 == '万元':
                lower = lower / 10000
            if unit2 == '万元':
                upper = upper / 10000
            
            result['total_amount_lower'] = lower
            result['total_amount_upper'] = upper
            context = extract_context(text, match.start(), match.end())
            sentence_context = extract_sentence_context(text, match.start())
            
            # 评估匹配质量（取上限值作为参考）
            match_quality = evaluate_match_quality(pattern, match.group(0), upper)
            
            evidence_upper = create_evidence(
                "total_amount_upper", upper, match.group(0), source_type,
                context=context + " " + sentence_context.strip(),
                match_quality=match_quality
            )
            is_valid, msg = validate_evidence(evidence_upper)
            if is_valid:
                evidences.append(evidence_upper)
            else:
                evidence_upper['validation_error'] = msg
                evidences.append(evidence_upper)
            
            if lower != upper:
                evidence_lower = create_evidence(
                    "total_amount_lower", lower, match.group(0), source_type,
                    context=context + " " + sentence_context.strip(),
                    match_quality=match_quality
                )
                is_valid, msg = validate_evidence(evidence_lower)
                if is_valid:
                    evidences.append(evidence_lower)
                else:
                    evidence_lower['validation_error'] = msg
                    evidences.append(evidence_lower)
            break
    
    if not 'total_amount_upper' in result:
        single_upper_patterns = [
            (r'(不超过|上限为|最高.*?)([\d,，.]+)\s*(亿元)', 'regex_medium_confidence'),
            (r'(不超过|上限为|最高.*?)([\d,，.]+)\s*(万元)', 'regex_medium_confidence'),
            (r'资金总额.*?([\d,，.]+)\s*(亿元)', 'regex_low_confidence'),
            (r'资金总额.*?([\d,，.]+)\s*(万元)', 'regex_low_confidence'),
            (r'回购金额.*?([\d,，.]+)\s*(亿元)', 'regex_low_confidence'),
            (r'回购金额.*?([\d,，.]+)\s*(万元)', 'regex_low_confidence'),
            (r'金额.*?([\d,，.]+)\s*(亿元)', 'regex_low_confidence'),
            (r'金额.*?([\d,，.]+)\s*(万元)', 'regex_low_confidence'),
            (r'([\d,，.]+)\s*(亿元)\s*以内', 'regex_low_confidence'),
            (r'([\d,，.]+)\s*(万元)\s*以内', 'regex_low_confidence')
        ]
        for pattern, source_type in single_upper_patterns:
            match = re.search(pattern, text)
            if match:
                num_groups = len(match.groups())
                amount = clean_number(match.group(num_groups - 1))
                unit = match.group(num_groups)
                if unit == '万元':
                    amount = amount / 10000
                result['total_amount_upper'] = amount
                result['total_amount_lower'] = amount  # 单金额时上下限相同
                context = extract_context(text, match.start(), match.end())
                sentence_context = extract_sentence_context(text, match.start())
                
                match_quality = evaluate_match_quality(pattern, match.group(0), amount)
                
                evidence = create_evidence(
                    "total_amount_upper", amount, match.group(0), source_type,
                    context=context + " " + sentence_context.strip(),
                    match_quality=match_quality
                )
                is_valid, msg = validate_evidence(evidence)
                if is_valid:
                    evidences.append(evidence)
                else:
                    evidence['validation_error'] = msg
                    evidences.append(evidence)
                break
    
    price_patterns = [
        (r'(价格.*?不超过|回购价格.*?不超过)([\d,，.]+)\s*元/股', 'regex_high_confidence'),
        (r'(价格.*?不超过|回购价格.*?不超过)([\d,，.]+)\s*元', 'regex_high_confidence'),
        (r'([\d,，.]+)\s*元/股.*?回购', 'regex_high_confidence'),
        (r'回购价格.*?([\d,，.]+)\s*元', 'regex_medium_confidence'),
        (r'回购价格上限.*?([\d,，.]+)\s*元', 'regex_medium_confidence'),
        (r'最高.*?([\d,，.]+)\s*元/股', 'regex_medium_confidence'),
        (r'([\d,，.]+)\s*元.*?股', 'regex_low_confidence'),
        (r'每股.*?([\d,，.]+)\s*元', 'regex_low_confidence')
    ]
    for pattern, source_type in price_patterns:
        match = re.search(pattern, text)
        if match:
            price_value = clean_number(match.group(len(match.groups())))
            result['price_upper'] = price_value
            context = extract_context(text, match.start(), match.end())
            sentence_context = extract_sentence_context(text, match.start())
            
            match_quality = evaluate_match_quality(pattern, match.group(0), price_value)
            
            evidence = create_evidence(
                "price_upper", price_value, match.group(0), source_type,
                context=context + " " + sentence_context.strip(),
                match_quality=match_quality
            )
            is_valid, msg = validate_evidence(evidence)
            if is_valid:
                evidences.append(evidence)
            else:
                evidence['validation_error'] = msg
                evidences.append(evidence)
            break
    
    period_patterns = [
        (r'(\d+)\s*个月', 'regex_high_confidence'),
        (r'(\d+)\s*月.*?期限', 'regex_high_confidence'),
        (r'期限.*?(\d+)\s*个月', 'regex_high_confidence'),
        (r'(\d+)\s*个月.*?内', 'regex_medium_confidence'),
        (r'自.*?起.*?(\d+)\s*个月', 'regex_medium_confidence'),
        (r'(\d+)\s*月内完成', 'regex_medium_confidence'),
        (r'(\d+)个月.*?期限', 'regex_low_confidence')
    ]
    for pattern, source_type in period_patterns:
        match = re.search(pattern, text)
        if match:
            period_value = int(match.group(1))
            result['repurchase_period_months'] = period_value
            context = extract_context(text, match.start(), match.end())
            sentence_context = extract_sentence_context(text, match.start())
            
            match_quality = evaluate_match_quality(pattern, match.group(0), period_value)
            
            evidence = create_evidence(
                "repurchase_period_months", period_value, match.group(0), source_type,
                context=context + " " + sentence_context.strip(),
                match_quality=match_quality
            )
            is_valid, msg = validate_evidence(evidence)
            if is_valid:
                evidences.append(evidence)
            else:
                evidence['validation_error'] = msg
                evidences.append(evidence)
            break
    
    source_patterns = [
        (r'(自有资金)', 'regex_high_confidence'),
        (r'(募集资金)', 'regex_high_confidence'),
        (r'(金融机构借款)', 'regex_high_confidence'),
        (r'(流动资金)', 'regex_high_confidence'),
        (r'(公司自有资金)', 'regex_high_confidence'),
        (r'(自筹资金)', 'regex_high_confidence'),
        (r'(资金来源.*?自有)', 'regex_medium_confidence'),
        (r'(自有.*?资金)', 'regex_medium_confidence')
    ]
    for pattern, source_type in source_patterns:
        match = re.search(pattern, text)
        if match:
            if '自有' in match.group(1):
                source_value = '自有资金'
            elif '募集' in match.group(1):
                source_value = '募集资金'
            elif '借款' in match.group(1):
                source_value = '金融机构借款'
            elif '流动' in match.group(1):
                source_value = '流动资金'
            else:
                source_value = match.group(1)
            result['funding_source'] = source_value
            context = extract_context(text, match.start(), match.end())
            sentence_context = extract_sentence_context(text, match.start())
            
            match_quality = evaluate_match_quality(pattern, match.group(0), source_value)
            
            evidence = create_evidence(
                "funding_source", source_value, match.group(0), source_type,
                context=context + " " + sentence_context.strip(),
                match_quality=match_quality
            )
            is_valid, msg = validate_evidence(evidence)
            if is_valid:
                evidences.append(evidence)
            else:
                evidence['validation_error'] = msg
                evidences.append(evidence)
            break
    
    purpose_patterns = [
        (r'(股权激励)', 'regex_high_confidence'),
        (r'(员工持股)', 'regex_high_confidence'),
        (r'(市值管理)', 'regex_high_confidence'),
        (r'(注销.*?注册资本)', 'regex_high_confidence'),
        (r'(减少注册资本)', 'regex_high_confidence'),
        (r'(股权激励计划)', 'regex_high_confidence'),
        (r'(员工持股计划)', 'regex_high_confidence'),
        (r'(用于.*?股权激励)', 'regex_medium_confidence'),
        (r'(用于.*?员工持股)', 'regex_medium_confidence'),
        (r'(回购.*?注销)', 'regex_medium_confidence'),
        (r'(注销股份)', 'regex_medium_confidence'),
        (r'(库存股)', 'regex_low_confidence'),
        (r'(实施股权激励)', 'regex_low_confidence')
    ]
    for pattern, source_type in purpose_patterns:
        match = re.search(pattern, text)
        if match:
            if '股权激励' in match.group(1):
                purpose_value = '股权激励'
            elif '员工持股' in match.group(1):
                purpose_value = '员工持股计划'
            elif '市值管理' in match.group(1):
                purpose_value = '市值管理'
            elif '注销' in match.group(1) or '减少注册资本' in match.group(1):
                purpose_value = '注销减少注册资本'
            elif '库存股' in match.group(1):
                purpose_value = '库存股'
            else:
                purpose_value = match.group(1)
            result['repurpose'] = purpose_value
            context = extract_context(text, match.start(), match.end())
            sentence_context = extract_sentence_context(text, match.start())
            
            match_quality = evaluate_match_quality(pattern, match.group(0), purpose_value)
            
            evidence = create_evidence(
                "repurpose", purpose_value, match.group(0), source_type,
                context=context + " " + sentence_context.strip(),
                match_quality=match_quality
            )
            is_valid, msg = validate_evidence(evidence)
            if is_valid:
                evidences.append(evidence)
            else:
                evidence['validation_error'] = msg
                evidences.append(evidence)
            break
    
    # 第二步：使用LLM补充抽取
    if LLM_AVAILABLE:
        try:
            llm_result = extract_fields_with_llm(text, "方案公告")
            if llm_result:
                for key, value in llm_result.items():
                    if value is not None and key not in result:
                        result[key] = value
                        # LLM抽取的证据，使用专门的来源类型
                        evidence = create_evidence(
                            key, value, f"LLM抽取: {key}={value}", "llm_supplement",
                            confidence=0.65  # LLM补充抽取置信度稍低
                        )
                        evidences.append(evidence)
        except Exception as e:
            print(f"LLM抽取失败: {e}")
    
    # 第三步：解决证据冲突
    evidences = resolve_conflicts(evidences)
    
    return result, evidences

def extract_from_execution(text: str, announcement_type: str = "进展公告") -> Dict[str, Any]:
    """从进展/结果公告中抽取执行信息（正则+LLM混合模式，增强版）"""
    result = {}
    evidences = []

    # 去除换行符和中文逗号，使跨行文本连续，但保留空格
    # 注意：保留英文逗号以便处理千位分隔符
    text = text.replace('，', '').replace('\n', ' ').replace('\r', ' ')
    
    # 第一步：使用正则表达式抽取（带质量评估）
    # 成交金额模式 - 增强版
    amount_patterns = [
        # 处理 "成交总金额1,291,541,933.32元（不含交易费用）" 格式
        (r'成交总金额([\d,]+[\.]?[\d]*)\s*元\s*[（(]不含交易费用', 'regex_high_confidence'),
        (r'成交总金额\s*[为:]\s*([\d,]+[\.]?[\d]*)\s*元', 'regex_high_confidence'),
        (r'成交总金额\s*[为:]\s*([\d,]+[\.]?[\d]*)\s*(亿元)', 'regex_high_confidence'),
        (r'成交总金额\s*[为:]\s*([\d,]+[\.]?[\d]*)\s*(万元)', 'regex_high_confidence'),
        (r'累计回购.*?成交总金额\s*([\d,]+[\.]?[\d]*)\s*元', 'regex_high_confidence'),
        (r'累计回购.*?成交总金额\s*([\d,]+[\.]?[\d]*)\s*(亿元)', 'regex_high_confidence'),
        (r'累计回购.*?成交总金额\s*([\d,]+[\.]?[\d]*)\s*(万元)', 'regex_high_confidence'),
        (r'回购金额\s*([\d,]+[\.]?[\d]*)\s*元', 'regex_medium_confidence'),
        (r'回购金额\s*([\d,]+[\.]?[\d]*)\s*(亿元)', 'regex_medium_confidence'),
        (r'回购金额\s*([\d,]+[\.]?[\d]*)\s*(万元)', 'regex_medium_confidence'),
        (r'已回购金额\s*([\d,]+[\.]?[\d]*)\s*元', 'regex_medium_confidence'),
        (r'已回购金额\s*([\d,]+[\.]?[\d]*)\s*(亿元)', 'regex_medium_confidence'),
        (r'已回购金额\s*([\d,]+[\.]?[\d]*)\s*(万元)', 'regex_medium_confidence'),
        (r'使用资金\s*([\d,]+[\.]?[\d]*)\s*(亿元)', 'regex_low_confidence'),
        (r'使用资金\s*([\d,]+[\.]?[\d]*)\s*(万元)', 'regex_low_confidence'),
        (r'([\d,]+[\.]?[\d]*)\s*(亿元)\s*[（(]不含交易费用', 'regex_low_confidence'),
        (r'([\d,]+[\.]?[\d]*)\s*(万元)\s*[（(]不含交易费用', 'regex_low_confidence'),
    ]
    for pattern, source_type in amount_patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            if len(groups) == 2:
                amount = clean_number(groups[0])
                unit = groups[1]
                if unit == '万元':
                    amount = amount / 10000
                elif unit == '元':
                    amount = amount / 100000000
                # 如果是百分比，跳过（这是完成比例，不是金额）
                elif '%' in unit:
                    continue
            else:
                # 默认单位是元
                amount = clean_number(groups[0]) / 100000000  # 转换为亿元
            
            result['actual_amount'] = round(amount, 4)
            context = extract_context(text, match.start(), match.end())
            sentence_context = extract_sentence_context(text, match.start())
            
            match_quality = evaluate_match_quality(pattern, match.group(0), result['actual_amount'])
            
            evidence = create_evidence(
                "actual_amount", result['actual_amount'], match.group(0), source_type,
                context=context + " " + sentence_context.strip(),
                match_quality=match_quality
            )
            is_valid, msg = validate_evidence(evidence)
            if is_valid:
                evidences.append(evidence)
            else:
                evidence['validation_error'] = msg
                evidences.append(evidence)
            break
    
    # 回购数量模式 - 增强版
    quantity_patterns = [
        # 处理 "累计回购了公司 A股 72,955,992 股" 格式
        (r'累计回购.*?([\d,]+)\s*股', 'regex_high_confidence'),
        (r'已回购.*?([\d,]+)\s*股', 'regex_high_confidence'),
        (r'回购数量.*?([\d,]+)\s*股', 'regex_high_confidence'),
        (r'([\d,]+)\s*股.*?回购', 'regex_high_confidence'),
        (r'回购.*?([\d,]+)\s*股', 'regex_high_confidence'),
        # 万股格式
        (r'累计回购.*?([\d,]+[\.]?[\d]*)\s*万股', 'regex_high_confidence'),
        (r'已回购.*?([\d,]+[\.]?[\d]*)\s*万股', 'regex_high_confidence'),
        (r'回购数量.*?([\d,]+[\.]?[\d]*)\s*万股', 'regex_high_confidence'),
        (r'([\d,]+[\.]?[\d]*)\s*万股.*?回购', 'regex_high_confidence'),
    ]
    for pattern, source_type in quantity_patterns:
        match = re.search(pattern, text)
        if match:
            quantity = clean_number(match.group(1))
            if quantity is None:
                continue
            # 如果匹配到的是"股"，转换为"万股"
            if '万股' in match.group(0):
                result['actual_quantity'] = round(quantity, 4)
            else:
                result['actual_quantity'] = round(quantity / 10000, 4)
            context = extract_context(text, match.start(), match.end())
            sentence_context = extract_sentence_context(text, match.start())
            
            match_quality = evaluate_match_quality(pattern, match.group(0), result['actual_quantity'])
            
            evidence = create_evidence(
                "actual_quantity", result['actual_quantity'], match.group(0), source_type,
                context=context + " " + sentence_context.strip(),
                match_quality=match_quality
            )
            is_valid, msg = validate_evidence(evidence)
            if is_valid:
                evidences.append(evidence)
            else:
                evidence['validation_error'] = msg
                evidences.append(evidence)
            break
    
    # 平均价格模式 - 增强版
    avg_price_patterns = [
        (r'(成交均价|均价|平均成交价)\s*[为:]*\s*([\d.]+)\s*元/股', 'regex_high_confidence'),
        (r'(成交均价|均价|平均成交价)\s*[为:]*\s*([\d.]+)\s*元', 'regex_high_confidence'),
        (r'最高成交价.*?([\d.]+)\s*元/股.*?最低成交价.*?([\d.]+)\s*元/股', 'regex_high_confidence'),
        (r'最低成交价.*?([\d.]+)\s*元/股.*?最高成交价.*?([\d.]+)\s*元/股', 'regex_high_confidence'),
        (r'([\d.]+)\s*元/股.*?成交', 'regex_medium_confidence'),
        (r'成交价格.*?([\d.]+)\s*元/股', 'regex_medium_confidence'),
    ]
    for pattern, source_type in avg_price_patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            context = extract_context(text, match.start(), match.end())
            sentence_context = extract_sentence_context(text, match.start())
            
            if len(groups) == 2 and '最高' in match.group(0):
                # 同时有最高和最低价，计算平均值
                high = float(groups[0])
                low = float(groups[1]) if len(groups) > 1 else high
                result['actual_avg_price'] = round((high + low) / 2, 2)
                result['actual_max_price'] = high
                result['actual_min_price'] = low
                
                avg_quality = evaluate_match_quality(pattern, match.group(0), result['actual_avg_price'])
                
                evidence_avg = create_evidence(
                    "actual_avg_price", result['actual_avg_price'], match.group(0), source_type,
                    context=context + " " + sentence_context.strip(),
                    match_quality=avg_quality
                )
                is_valid, msg = validate_evidence(evidence_avg)
                if is_valid:
                    evidences.append(evidence_avg)
                else:
                    evidence_avg['validation_error'] = msg
                    evidences.append(evidence_avg)
                
                evidence_max = create_evidence(
                    "actual_max_price", result['actual_max_price'], match.group(0), source_type,
                    context=context + " " + sentence_context.strip(),
                    match_quality=avg_quality
                )
                is_valid, msg = validate_evidence(evidence_max)
                if is_valid:
                    evidences.append(evidence_max)
                else:
                    evidence_max['validation_error'] = msg
                    evidences.append(evidence_max)
                
                evidence_min = create_evidence(
                    "actual_min_price", result['actual_min_price'], match.group(0), source_type,
                    context=context + " " + sentence_context.strip(),
                    match_quality=avg_quality
                )
                is_valid, msg = validate_evidence(evidence_min)
                if is_valid:
                    evidences.append(evidence_min)
                else:
                    evidence_min['validation_error'] = msg
                    evidences.append(evidence_min)
            else:
                result['actual_avg_price'] = round(float(groups[-1]), 2)
                
                match_quality = evaluate_match_quality(pattern, match.group(0), result['actual_avg_price'])
                
                evidence = create_evidence(
                    "actual_avg_price", result['actual_avg_price'], match.group(0), source_type,
                    context=context + " " + sentence_context.strip(),
                    match_quality=match_quality
                )
                is_valid, msg = validate_evidence(evidence)
                if is_valid:
                    evidences.append(evidence)
                else:
                    evidence['validation_error'] = msg
                    evidences.append(evidence)
            break
    
    # 第二步：使用LLM补充抽取
    if LLM_AVAILABLE:
        try:
            llm_result = extract_fields_with_llm(text, announcement_type)
            if llm_result:
                for key, value in llm_result.items():
                    if value is not None and key not in result:
                        # 映射LLM字段名到标准字段名
                        field_mapping = {
                            'executed_amount': 'actual_amount',
                            'executed_quantity': 'actual_quantity',
                            'average_price': 'actual_avg_price',
                            'max_price': 'actual_max_price',
                            'min_price': 'actual_min_price',
                            'completion_ratio': 'completion_ratio'
                        }
                        mapped_key = field_mapping.get(key, key)
                        result[mapped_key] = value
                        
                        evidence = create_evidence(
                            mapped_key, value, f"LLM抽取: {key}={value}", "llm_supplement",
                            confidence=0.65
                        )
                        evidences.append(evidence)
        except Exception as e:
            print(f"LLM抽取失败: {e}")
    
    # 第三步：解决证据冲突
    evidences = resolve_conflicts(evidences)
    
    return result, evidences

def process_single_doc(item, parsed_docs_map):
    """处理单个文档的抽取（可并行执行）"""
    doc_id = item['doc_id']
    announcement_type = item['announcement_type']
    
    if item['sections']:
        all_text = "\n\n".join([s['text'] for s in item['sections']])
    else:
        parsed_doc = parsed_docs_map.get(doc_id, {})
        all_text = "\n\n".join([page['text'] for page in parsed_doc.get('pages', [])])
    
    # 生成event_id
    event_id = doc_id.replace('_plan', '').replace('_progress', '').replace('_result', '')
    event_id = re.sub(r'_\d+$', '', event_id)
    event_id = re.sub(r'_v\d+$', '', event_id)
    
    # 尝试从缓存加载
    cache_key = get_cache_key(all_text, announcement_type)
    cached_result = load_cache(cache_key)
    
    if cached_result:
        data, evidences = cached_result
    else:
        # 执行抽取
        if announcement_type == "方案公告":
            data, evidences = extract_from_plan(all_text)
        else:
            data, evidences = extract_from_execution(all_text, announcement_type)
        # 保存到缓存
        save_cache(cache_key, data, evidences)
    
    extract_result = {
        "doc_id": doc_id,
        "company_name": item['company_name'],
        "stock_code": str(item['stock_code']),
        "event_id": event_id,
        "announcement_type": announcement_type,
        "announcement_date": "",
        "plan": None,
        "execution": None,
        "evidence": [],
        "extraction_confidence": 0.7,
        "evidence_details": []
    }
    
    if announcement_type == "方案公告" and data:
        extract_result["plan"] = data
        if evidences:
            avg_confidence = sum(e.get('confidence', 0.7) for e in evidences) / len(evidences)
            extract_result["extraction_confidence"] = round(avg_confidence, 4)
        
        for e in evidences:
            extract_result["evidence"].append({
                "evidence_doc_type": "方案公告",
                "evidence_text": e["text"],
                "page_no": e.get("page_no", 1)
            })
            extract_result["evidence_details"].append({
                "field": e.get("field", ""),
                "value": e.get("value", ""),
                "text": e["text"],
                "context": e.get("context", ""),
                "source": e.get("source", "unknown"),
                "confidence": e.get("confidence", 0.7),
                "match_quality": e.get("match_quality", 1.0),
                "cross_validated": e.get("cross_validated", False),
                "validation_error": e.get("validation_error", None),
                "page_no": e.get("page_no", 1)
            })
    
    elif announcement_type in ["进展公告", "结果公告"] and data:
        extract_result["execution"] = data
        if evidences:
            avg_confidence = sum(e.get('confidence', 0.7) for e in evidences) / len(evidences)
            extract_result["extraction_confidence"] = round(avg_confidence, 4)
        
        for e in evidences:
            extract_result["evidence"].append({
                "evidence_doc_type": announcement_type,
                "evidence_text": e["text"],
                "page_no": e.get("page_no", 1)
            })
            extract_result["evidence_details"].append({
                "field": e.get("field", ""),
                "value": e.get("value", ""),
                "text": e["text"],
                "context": e.get("context", ""),
                "source": e.get("source", "unknown"),
                "confidence": e.get("confidence", 0.7),
                "match_quality": e.get("match_quality", 1.0),
                "cross_validated": e.get("cross_validated", False),
                "validation_error": e.get("validation_error", None),
                "page_no": e.get("page_no", 1)
            })
    
    log_run("extract", doc_id, "success")
    return extract_result

def extract_fields(sections_path, output_path):
    """执行字段抽取（优化版：并行处理 + 缓存）"""
    from src.common import read_jsonl
    
    sections_data = read_jsonl(sections_path)
    parsed_docs_data = read_jsonl(sections_path.replace('sections.jsonl', 'parsed_docs.jsonl'))
    parsed_docs_map = {doc['doc_id']: doc for doc in parsed_docs_data}
    
    total_docs = len(sections_data)
    results = []
    completed = 0
    hit_cache = 0
    
    print(f"开始抽取字段，共 {total_docs} 份文档，使用 {MAX_WORKERS} 个线程...")
    
    # 使用线程池并行处理
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有任务
        futures = {}
        for item in sections_data:
            future = executor.submit(process_single_doc, item, parsed_docs_map)
            futures[future] = item['doc_id']
        
        # 处理完成的任务
        for future in as_completed(futures):
            doc_id = futures[future]
            try:
                result = future.result()
                results.append(result)
                
                # 检查是否命中缓存
                cache_key = get_cache_key(
                    "\n\n".join([s['text'] for s in sections_data[0]['sections']]) if sections_data[0].get('sections') else "",
                    sections_data[0].get('announcement_type', '')
                )
                if os.path.exists(os.path.join(CACHE_DIR, f"{cache_key}.json")):
                    hit_cache += 1
                
            except Exception as e:
                print(f"处理 {doc_id} 时出错: {e}")
            
            completed += 1
            # 打印进度
            progress = (completed / total_docs) * 100
            print(f"\r进度: [{completed}/{total_docs}] {progress:.1f}%", end="")
    
    print(f"\n字段抽取完成，共处理 {len(results)} 份文档，缓存命中 {hit_cache} 次")
    
    write_jsonl(output_path, results)
    print(f"结果已保存到 {output_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="字段抽取")
    parser.add_argument("--sections", default="data/parsed/sections.jsonl")
    parser.add_argument("--output", default="outputs/results/extract_results.jsonl")
    args = parser.parse_args()
    
    extract_fields(args.sections, args.output)