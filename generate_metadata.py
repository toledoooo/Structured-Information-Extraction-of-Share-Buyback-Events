import json
import os
import re

with open('companies_list.json', 'r', encoding='utf-8') as f:
    companies = json.load(f)

stock_codes = {
    "三一重工": "600031",
    "三七互娱": "002555",
    "东方财富": "300059",
    "中兴通讯": "000063",
    "中国平安": "601318",
    "中国建筑": "601668",
    "中联重科": "000157",
    "伊利股份": "600887",
    "保利发展": "600048",
    "信立泰": "002294",
    "兆易创新": "603986",
    "创新医疗": "002173",
    "同力股份": "834599",
    "国邦医药": "605507",
    "大华股份": "002236",
    "完美世界": "002624",
    "广宇集团": "002133",
    "康强电子": "002119",
    "恒瑞医药": "600276",
    "招商蛇口": "001979",
    "方大集团": "000055",
    "智飞生物": "300122",
    "格力电器": "000651",
    "歌尔股份": "002241",
    "比亚迪": "002594",
    "海天味业": "603288",
    "海尔智家": "600690",
    "海康威视": "002415",
    "海螺水泥": "600585",
    "爱尔眼科": "300015",
    "爱玛科技": "603529",
    "牧原股份": "002714",
    "用友网络": "600588",
    "百利天恒": "688506",
    "科大讯飞": "002230",
    "紫金矿业": "601899",
    "药明康德": "603259",
    "蓝思科技": "300433",
    "贵州茅台": "600519",
    "迈瑞医疗": "300760",
    "通威股份": "600438",
    "金山办公": "688111",
    "长春高新": "000661",
    "陕西煤业": "601225",
    "隆基绿能": "601012",
    "韦尔股份": "603501",
    "顺丰控股": "002352",
    "海 利 得": "002206",
    "京东方Ａ": "000725",
    "万科A": "000002"
}

lines = ["doc_id,company_name,stock_code,announcement_type,announcement_date,pdf_path"]

for company_name, pdfs in companies.items():
    stock_code = stock_codes.get(company_name, "unknown")
    
    plan_pdf = None
    progress_pdf = None
    result_pdf = None
    
    for pdf_full in pdfs:
        # 移除UUID后缀
        pdf_name = pdf_full.rsplit('-', 1)[0]
        # 确保只保留PDF文件名部分
        if '.pdf' in pdf_name:
            pdf_name = pdf_name[:pdf_name.rfind('.pdf') + 4]
        
        if "方案" in pdf_name or "预案" in pdf_name or "报告书" in pdf_name:
            if not plan_pdf or ("回购报告书" in pdf_name and "进展" not in pdf_name):
                plan_pdf = pdf_name
        elif "进展" in pdf_name:
            progress_pdf = pdf_name
        elif "结果" in pdf_name or "完成" in pdf_name or "届满" in pdf_name:
            result_pdf = pdf_name
    
    if plan_pdf:
        doc_id = re.sub(r'[^\w]', '', company_name) + "_plan"
        lines.append(f"{doc_id},{company_name},{stock_code},方案公告,2023-01-01,{plan_pdf}")
    
    if progress_pdf:
        doc_id = re.sub(r'[^\w]', '', company_name) + "_progress"
        lines.append(f"{doc_id},{company_name},{stock_code},进展公告,2023-06-01,{progress_pdf}")
    
    if result_pdf:
        doc_id = re.sub(r'[^\w]', '', company_name) + "_result"
        lines.append(f"{doc_id},{company_name},{stock_code},结果公告,2024-01-01,{result_pdf}")

with open('data/metadata/metadata.csv', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"生成了 {len(lines)-1} 条记录")