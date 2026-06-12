"""
质量指标计算模块
实现Data Quality、Section Quality、Extraction Quality、Evidence Quality、Pipeline Stability五大维度的量化评估
改进目标：增加评分区分度，引入动态调整机制
"""
import re
import hashlib
from typing import Dict, Any, Optional, List


class QualityMetrics:
    """质量指标计算器"""
    
    def __init__(self):
        # 关键词库 - 扩展版本
        self.repo_keywords = ['回购', '股份', '方案', '进展', '结果', '实施', '完成']
        self.section_keywords = {
            '方案公告': ['回购方案', '回购计划', '回购预案', '回购报告书', '回购股份方案', 
                       '回购部分社会公众股份', '回购A股股份', '回购公司股份'],
            '进展公告': ['进展', '实施进展', '回购进展', '首次回购', '回购进展情况', 
                       '回购股份进展', '回购实施进展'],
            '结果公告': ['结果', '完成', '完毕', '股份变动', '回购期届满', '回购期限届满',
                       '回购方案完成', '回购方案实施完毕']
        }
        # 惩罚因子 - 用于动态调整
        self.penalty_factors = {
            'empty_field': 0.1,      # 空字段惩罚
            'format_error': 0.15,    # 格式错误惩罚
            'value_abnormal': 0.2,   # 数值异常惩罚
            'no_evidence': 0.15,     # 无证据惩罚
            'section_missing': 0.2   # 关键章节缺失惩罚
        }
    
    def calculate_data_quality(self, doc: Dict[str, Any]) -> float:
        """
        计算数据质量得分 (0-1)
        评估维度：标题匹配率、文档完整性、格式有效性、来源可靠性
        改进：大幅增加评分梯度和区分度
        """
        score = 0.0
        weight_sum = 0
        
        # 1. 标题匹配率（权重25%）- 大幅降低要求，增加更多梯度
        title = doc.get('title', '') or doc.get('doc_id', '')
        title_len = len(title)
        
        # 核心关键词（包含任意一个即可）
        core_keywords = ['回购', '股份', 'buyback', 'repurchase']
        core_match = sum(1 for kw in core_keywords if kw.lower() in title.lower())
        
        # 根据匹配数量和标题长度综合评分
        if core_match >= 1 and title_len >= 10:
            title_score = 1.0
        elif core_match >= 1 and title_len >= 5:
            title_score = 0.8
        elif core_match >= 1:
            title_score = 0.6
        elif '股' in title or '购' in title:
            title_score = 0.4
        else:
            title_score = 0.2
        score += title_score * 0.25
        weight_sum += 0.25
        
        # 2. 文档完整性（权重30%）- 更多级评分，扩大范围
        content = doc.get('content', '')
        content_len = len(content)
        if content_len >= 5000:
            content_score = 1.0
        elif content_len >= 3000:
            content_score = 0.9
        elif content_len >= 2000:
            content_score = 0.8
        elif content_len >= 1000:
            content_score = 0.65
        elif content_len >= 500:
            content_score = 0.5
        elif content_len >= 200:
            content_score = 0.35
        elif content_len >= 50:
            content_score = 0.2
        else:
            content_score = 0.1
        score += content_score * 0.3
        weight_sum += 0.3
        
        # 3. 格式有效性（权重20%）- 细粒度评估
        md_path = doc.get('markdown_path', '')
        if md_path and md_path.endswith('.md'):
            format_score = 1.0
        elif doc.get('content', '').strip() and len(doc.get('content', '')) > 100:
            format_score = 0.75
        elif doc.get('content', '').strip():
            format_score = 0.5
        else:
            format_score = 0.2
        score += format_score * 0.2
        weight_sum += 0.2
        
        # 4. 来源可靠性（权重25%）- 更细粒度
        source = doc.get('source', '')
        if '巨潮资讯' in source or 'cninfo' in source.lower():
            source_score = 1.0
        elif '证券时报' in source or '上海证券报' in source or '中国证券报' in source:
            source_score = 0.9
        elif source and len(source) > 5:
            source_score = 0.7
        elif source:
            source_score = 0.5
        else:
            source_score = 0.3
        score += source_score * 0.25
        weight_sum += 0.25
        
        return round(score / weight_sum if weight_sum > 0 else 0.4, 4)
    
    def calculate_section_quality(self, sections: List[Dict], announcement_type: str) -> float:
        """
        计算章节质量得分 (0-1)
        评估维度：关键章节找到率、章节完整性、表格处理质量、章节结构合理性
        改进：增加评分梯度，支持模糊匹配
        """
        score = 0.0
        weight_sum = 0
        
        if not sections:
            return 0.4  # 默认分稍低，激励找到章节
        
        # 1. 关键章节找到率（权重35%）- 多级评分
        expected_sections = self.section_keywords.get(announcement_type, [])
        expected_count = max(len(expected_sections), 1)
        
        found_count = 0
        for sec in sections:
            # 兼容两种字段名：section_name/text 和 title/content
            sec_title = sec.get('section_name', '') or sec.get('title', '')
            sec_text = sec.get('text', '') or sec.get('content', '')
            sec_title_lower = sec_title.lower()
            sec_text_lower = sec_text.lower()
            
            for kw in expected_sections:
                # 在章节标题和内容中都搜索关键词
                if kw.lower() in sec_title_lower or kw.lower() in sec_text_lower:
                    found_count += 1
                    break
        
        # 多级评分：0→0.3, 1→0.6, 2→0.8, >=3→1.0
        if found_count == 0:
            section_score = 0.3
        elif found_count == 1:
            section_score = 0.6
        elif found_count == 2:
            section_score = 0.8
        elif found_count >= expected_count:
            section_score = 1.0
        else:
            section_score = 0.8 + (found_count - 2) * 0.2 / (expected_count - 2)
        score += section_score * 0.35
        weight_sum += 0.35
        
        # 2. 章节完整性（权重25%）- 多级评分
        total_chars = sum(len(sec.get('text', '') or sec.get('content', '')) for sec in sections)
        if total_chars >= 1000:
            completeness_score = 1.0
        elif total_chars >= 500:
            completeness_score = 0.8
        elif total_chars >= 200:
            completeness_score = 0.6
        else:
            completeness_score = 0.3
        score += completeness_score * 0.25
        weight_sum += 0.25
        
        # 3. 表格处理质量（权重20%）- 细粒度评估
        table_count = sum(1 for sec in sections 
                         if 'table' in (sec.get('text', '') or sec.get('content', '')).lower())
        if table_count >= 2:
            table_score = 1.0
        elif table_count == 1:
            table_score = 0.85
        else:
            table_score = 0.5  # 无表格但有文字内容
        score += table_score * 0.2
        weight_sum += 0.2
        
        # 4. 章节结构合理性（权重20%）- 新增维度
        # 检查是否有层次结构（标题包含序号）
        has_structure = any(
            re.match(r'^[\d一二三四五六七八九十]+[、.．]', 
                    sec.get('section_name', '') or sec.get('title', '')) 
            for sec in sections
        )
        structure_score = 1.0 if has_structure else 0.7
        score += structure_score * 0.2
        weight_sum += 0.2
        
        return round(score / weight_sum if weight_sum > 0 else 0.5, 4)
    
    def calculate_extraction_quality(self, extracted: Dict[str, Any], announcement_type: str) -> float:
        """
        计算抽取质量得分 (0-1)
        评估维度：字段完整性、格式正确性、数值合理性、字段值有效性
        改进：大幅增加评分区分度，增加更多惩罚机制
        """
        score = 0.0
        weight_sum = 0
        penalty = 0.0
        
        # 定义关键字段
        if announcement_type == '方案公告':
            key_fields = ['repurchase_method', 'total_amount_upper', 'price_upper', 
                         'repurchase_period_months', 'funding_source', 'repurpose']
        else:
            key_fields = ['actual_amount', 'actual_quantity', 'actual_avg_price']
        
        # 1. 字段完整性（权重25%）- 更细粒度评分
        filled_count = sum(1 for f in key_fields if extracted.get(f) is not None)
        completeness_ratio = filled_count / len(key_fields)
        
        if completeness_ratio == 1.0:
            completeness_score = 1.0
        elif completeness_ratio >= 0.83:  # 5/6或3/3
            completeness_score = 0.9
        elif completeness_ratio >= 0.67:  # 4/6或2/3
            completeness_score = 0.75
        elif completeness_ratio >= 0.5:   # 3/6或1/3
            completeness_score = 0.6
        elif completeness_ratio >= 0.33:  # 2/6
            completeness_score = 0.45
        elif completeness_ratio >= 0.17:  # 1/6
            completeness_score = 0.3
        else:
            completeness_score = 0.15
        score += completeness_score * 0.25
        weight_sum += 0.25
        
        # 2. 格式正确性（权重25%）- 更严格的检查
        format_errors = 0
        total_checks = 0
        
        # 检查数值字段格式
        numeric_fields = ['total_amount_upper', 'price_upper', 'repurchase_period_months',
                         'actual_amount', 'actual_quantity', 'actual_avg_price']
        for field in numeric_fields:
            if field in extracted:
                total_checks += 1
                value = extracted[field]
                if value is None:
                    format_errors += 0.5
                elif not isinstance(value, (int, float)):
                    try:
                        float(value)
                    except (ValueError, TypeError):
                        format_errors += 1
        
        # 检查字符串字段格式
        string_fields = ['repurchase_method', 'funding_source', 'repurpose']
        for field in string_fields:
            if field in extracted:
                total_checks += 1
                value = extracted[field]
                if value is None or (isinstance(value, str) and len(value.strip()) == 0):
                    format_errors += 0.5
        
        format_score = max(0.1, 1 - (format_errors / max(total_checks, 1)))
        score += format_score * 0.25
        weight_sum += 0.25
        
        # 3. 数值合理性（权重25%）- 更严格的异常检测
        value_score = 1.0
        amount_fields = ['total_amount_upper', 'actual_amount']
        for field in amount_fields:
            value = extracted.get(field)
            if value:
                try:
                    num_value = float(value)
                    if num_value <= 0:
                        value_score -= 0.4
                    elif num_value > 1000000:  # 超过100万可能有问题
                        value_score -= 0.3
                    elif num_value > 100000:   # 超过10万可能有问题
                        value_score -= 0.15
                except:
                    value_score -= 0.3
        
        price_fields = ['price_upper', 'actual_avg_price']
        for field in price_fields:
            value = extracted.get(field)
            if value:
                try:
                    num_value = float(value)
                    if num_value <= 0:
                        value_score -= 0.4
                    elif num_value > 100000:  # 超过10万可能有问题
                        value_score -= 0.3
                    elif num_value > 10000:   # 超过1万可能有问题
                        value_score -= 0.1
                except:
                    value_score -= 0.3
        
        period_fields = ['repurchase_period_months']
        for field in period_fields:
            value = extracted.get(field)
            if value:
                try:
                    num_value = float(value)
                    if num_value <= 0:
                        value_score -= 0.3
                    elif num_value > 60:  # 超过5年可能有问题
                        value_score -= 0.2
                except:
                    value_score -= 0.2
        
        value_score = max(0.2, value_score)
        score += value_score * 0.25
        weight_sum += 0.25
        
        # 4. 字段值有效性（权重25%）- 检查无效值和占位符
        validity_score = 1.0
        invalid_patterns = ['暂无', '未披露', '不适用', 'n/a', 'null', 'none', '-', '—', '', ' ', 
                           'None', 'NULL', 'N/A', 'NA', '未说明', '待定', '待披露']
        
        for field in key_fields:
            value = extracted.get(field)
            if value is not None:
                str_value = str(value).strip().lower()
                if str_value in invalid_patterns or len(str_value) == 0:
                    validity_score -= 0.2
                elif len(str_value) == 1:  # 单个字符可能是无效值
                    validity_score -= 0.1
        
        validity_score = max(0.3, validity_score)
        score += validity_score * 0.25
        weight_sum += 0.25
        
        # 应用惩罚因子
        final_score = score / weight_sum if weight_sum > 0 else 0.4
        final_score = max(0.15, final_score - penalty)
        
        return round(min(final_score, 1.0), 4)
    
    def calculate_evidence_quality(self, evidences: List[Dict]) -> float:
        """
        计算证据质量得分 (0-1)
        评估维度：证据覆盖率、证据命中率、页码有效性、证据相关性
        改进：增加评分梯度，支持模糊匹配
        """
        score = 0.0
        weight_sum = 0
        
        if not evidences:
            return 0.45  # 默认分，激励提供证据
        
        # 1. 证据覆盖率（权重30%）- 多级评分
        covered_fields = len(set(e.get('field') for e in evidences))
        if covered_fields >= 4:
            coverage_score = 1.0
        elif covered_fields == 3:
            coverage_score = 0.85
        elif covered_fields == 2:
            coverage_score = 0.7
        elif covered_fields == 1:
            coverage_score = 0.5
        else:
            coverage_score = 0.3
        score += coverage_score * 0.3
        weight_sum += 0.3
        
        # 2. 证据命中率（权重30%）- 支持模糊匹配
        hit_count = 0
        total_checks = 0
        
        for e in evidences:
            field_value = e.get('value')
            evidence_text = e.get('text', '') or e.get('evidence_text', '')
            
            if field_value and evidence_text:
                total_checks += 1
                # 尝试精确匹配
                if str(field_value) in evidence_text:
                    hit_count += 1
                else:
                    # 尝试模糊匹配：检查数字部分
                    value_str = str(field_value)
                    value_numbers = re.findall(r'[\d.]+', value_str)
                    text_numbers = re.findall(r'[\d.]+', evidence_text)
                    
                    # 如果有数字匹配，也算命中
                    if value_numbers and text_numbers:
                        if value_numbers[0] in text_numbers:
                            hit_count += 0.7  # 模糊匹配权重稍低
        
        hit_score = hit_count / max(total_checks, 1)
        score += hit_score * 0.3
        weight_sum += 0.3
        
        # 3. 页码有效性（权重20%）- 更宽松的检查
        valid_page_count = 0
        for e in evidences:
            page_no = e.get('page_no')
            if page_no is not None and page_no >= 0:
                valid_page_count += 1
        
        page_score = valid_page_count / max(len(evidences), 1)
        score += page_score * 0.2
        weight_sum += 0.2
        
        # 4. 证据相关性（权重20%）- 新增维度：检查证据文本长度
        relevance_score = 0.0
        total_len = sum(len(e.get('text', '') or e.get('evidence_text', '')) for e in evidences)
        avg_len = total_len / max(len(evidences), 1)
        
        if avg_len >= 50:
            relevance_score = 1.0
        elif avg_len >= 30:
            relevance_score = 0.8
        elif avg_len >= 10:
            relevance_score = 0.6
        else:
            relevance_score = 0.4
        score += relevance_score * 0.2
        weight_sum += 0.2
        
        return round(score / weight_sum if weight_sum > 0 else 0.5, 4)
    
    def calculate_pipeline_stability(self, step_status: Dict[str, bool], warnings: List[str] = None) -> float:
        """
        计算工作流稳定性得分 (0-1)
        评估维度：各步骤成功率、警告数量
        改进：考虑警告信息，增加区分度
        """
        if not step_status:
            return 0.75  # 降低默认分
        
        success_count = sum(1 for status in step_status.values() if status)
        base_score = success_count / len(step_status)
        
        # 考虑警告信息
        warning_count = len(warnings) if warnings else 0
        penalty = min(warning_count * 0.05, 0.2)  # 最多扣0.2分
        
        final_score = max(0.5, base_score - penalty)
        return round(final_score, 4)
    
    def calculate_composite_weight(self, doc_quality: Dict[str, float], 
                                  announcement_type: str = None) -> float:
        """
        计算综合质量权重
        权重分配：Data(20%) + Section(15%) + Extraction(30%) + Evidence(20%) + Stability(15%)
        改进：移除归一化限制，让分数分布更宽
        """
        # 基础权重
        weights = {
            'data_quality': 0.2,
            'section_quality': 0.15,
            'extraction_quality': 0.3,
            'evidence_quality': 0.2,
            'pipeline_stability': 0.15
        }
        
        # 根据公告类型调整权重
        if announcement_type:
            adjustments = {
                '方案公告': {'section_quality': 0.03, 'extraction_quality': 0.03},   # 方案公告更看重章节和抽取
                '结果公告': {'evidence_quality': 0.03, 'extraction_quality': 0.03},  # 结果公告更看重证据
            }
            adj = adjustments.get(announcement_type, {})
            for key, delta in adj.items():
                if key in weights:
                    weights[key] = min(weights[key] + delta, 0.4)
        
        total = 0.0
        for key, weight in weights.items():
            total += doc_quality.get(key, 0.4) * weight
        
        # 移除归一化，让分数自然分布
        # 但限制最小值为0.2，最大值为1.0
        final_score = max(0.2, min(total, 1.0))
        
        return round(final_score, 4)
    
    def calculate_all_metrics(self, doc: Dict[str, Any], sections: List[Dict], 
                            extracted: Dict[str, Any], evidences: List[Dict],
                            step_status: Dict[str, bool], warnings: List[str] = None) -> Dict[str, float]:
        """
        计算所有质量指标并返回详细结果
        """
        announcement_type = doc.get('announcement_type', '')
        
        metrics = {
            'data_quality': self.calculate_data_quality(doc),
            'section_quality': self.calculate_section_quality(sections, announcement_type),
            'extraction_quality': self.calculate_extraction_quality(extracted, announcement_type),
            'evidence_quality': self.calculate_evidence_quality(evidences),
            'pipeline_stability': self.calculate_pipeline_stability(step_status, warnings),
        }
        
        metrics['composite_weight'] = self.calculate_composite_weight(metrics, announcement_type)
        
        return metrics


def detect_duplicate_docs(docs: List[Dict]) -> List[str]:
    """
    检测重复文档
    返回重复的doc_id列表
    """
    seen_hashes = {}
    duplicates = []
    
    for doc in docs:
        content = doc.get('content', '') or doc.get('title', '')
        doc_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        
        if doc_hash in seen_hashes:
            duplicates.append(doc['doc_id'])
        else:
            seen_hashes[doc_hash] = doc['doc_id']
    
    return duplicates


def validate_data_format(doc: Dict[str, Any]) -> Dict[str, bool]:
    """
    验证数据格式
    返回各字段的格式验证结果
    """
    checks = {
        'has_content': bool(doc.get('content')),
        'has_title': bool(doc.get('title')),
        'valid_doc_id': bool(doc.get('doc_id')),
        'valid_type': doc.get('announcement_type') in ['方案公告', '进展公告', '结果公告'],
        'valid_company': bool(doc.get('company_name'))
    }
    return checks


if __name__ == "__main__":
    # 测试质量指标计算
    test_doc = {
        'doc_id': '比亚迪_plan',
        'title': '比亚迪：关于回购股份方案的公告',
        'content': '公司拟使用自有资金回购股份，金额不超过50亿元...',
        'announcement_type': '方案公告',
        'markdown_path': 'data/md/比亚迪：关于回购股份方案的公告.md'
    }
    
    test_sections = [
        {'title': '回购方案', 'content': '回购金额上限50亿元...'},
        {'title': '资金来源', 'content': '自有资金'}
    ]
    
    test_extracted = {
        'repurchase_method': '集中竞价交易',
        'total_amount_upper': 50.0,
        'price_upper': 200.0,
        'repurchase_period_months': 6,
        'funding_source': '自有资金',
        'repurpose': '股权激励'
    }
    
    test_evidences = [
        {'field': 'total_amount_upper', 'value': 50.0, 'text': '金额不超过50亿元', 'page_no': 3}
    ]
    
    qm = QualityMetrics()
    
    print("=== 质量指标测试 ===")
    print(f"数据质量: {qm.calculate_data_quality(test_doc):.4f}")
    print(f"章节质量: {qm.calculate_section_quality(test_sections, '方案公告'):.4f}")
    print(f"抽取质量: {qm.calculate_extraction_quality(test_extracted, '方案公告'):.4f}")
    print(f"证据质量: {qm.calculate_evidence_quality(test_evidences):.4f}")
    
    composite = qm.calculate_composite_weight({
        'data_quality': qm.calculate_data_quality(test_doc),
        'section_quality': qm.calculate_section_quality(test_sections, '方案公告'),
        'extraction_quality': qm.calculate_extraction_quality(test_extracted, '方案公告'),
        'evidence_quality': qm.calculate_evidence_quality(test_evidences),
        'pipeline_stability': 0.98
    })
    print(f"综合质量权重: {composite:.4f}")
