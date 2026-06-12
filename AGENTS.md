# Agent Instructions for Repurchase Project

## Project Goal
本项目从巨潮资讯网公告 PDF 中抽取股份回购事件的结构化金融信息。

## Data Rules
- 主数据必须来自巨潮资讯网公开公告。
- 不绕过登录、验证码或访问限制。
- 原始 PDF 不得修改。

## Secret Rules
- 不要把 API Key 写入代码。
- 不要提交 .env。
- 只维护 .env.example。

## Coding Rules
- 每个脚本必须支持命令行运行。
- 所有输出写入 outputs/。
- 所有错误写入 outputs/logs/。
- 修改代码后必须说明运行哪个命令验证。

## Extraction Rules
- 字段值必须来自公告文本。
- 每个关键字段要有 evidence_text。
- 无法判断时输出 null。
- 抽取结果必须通过 Pydantic 校验。