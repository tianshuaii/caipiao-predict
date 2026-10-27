# Lottery Analysis Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 本地运行双彩种官方数据采集、可追溯预测复盘、微信通知与仪表盘。
**Architecture:** 两个独立项目；Python API 与单实例调度器共享业务模块和 MySQL，React 通过 API 展示真实数据。采集失败与实验不足均如实展示。
**Tech Stack:** Python/FastAPI/SQLAlchemy/Alembic/APScheduler，React/TypeScript/HeroUI/Vite，Docker MySQL。
**Spec:** ../specs/2026-10-23-lottery-analysis-design.md

## Global Constraints
- Asia/Shanghai，周一、三、五 08:00；两彩种各 5 注单式，不追加、不倍投。
- MySQL 127.0.0.1:9999；本地运行；密钥不入版本控制、不出现在日志。
- 原始响应、期次、规则、预测、结算、模型与任务均可追溯；重试不覆盖正式预测。
- 前瞻预测与回测分离，所有策略与同成本随机基线比较。

## Review Focus
- 官方源超时、返回 HTML、截断分页或多源冲突：不能声称历史完整或使用旧数据预测。
- 2019/2026 大乐透规则变化与派奖：按开奖期规则、已公布奖金结算，未知金额为待结算。
- 跨年、休市、过销售截止、休眠恢复：不生成已经截止的正式预测。
- 同期重复执行与推送响应不确定：预测不变、不盲目重发。
- 无历史预测、无实验数据、后端断开：前端有明确空状态和错误状态。

## Task 1: 领域规则与可复现选号
Files: backend/lottery/domain.py, backend/lottery/predict.py, backend/tests/test_domain.py
Interfaces: validate_ticket(game, front, back); prize_level(game, issue, front_hits, back_hits); generate_tickets(game, seed, count=5).
- [x] 先写校验、历史奖级分界、种子复现与唯一性测试，运行确认缺失实现失败。
- [x] 实现最小规则和均匀随机策略；运行 pytest 全部通过。

## Task 2: 持久化与官方采集
Files: backend/lottery/db.py, models.py, collectors.py, ingestion.py, migrations/, tests/test_ingestion.py, compose.yaml
Interfaces: collect(game, full); ingest(session, parsed_draw, raw_id); coverage(session, game).
- [x] 核验官方实际响应与历史分页；保存解析器测试样本。
- [x] 写重复入库、内容修订/冲突、缺期及缺奖金测试，确认失败后实现。
- [x] 启动 MySQL、运行迁移、采集全历史，校验覆盖范围与真实 SQL 记录。

## Task 3: 工作流、结算、通知、回测
Files: backend/lottery/workflow.py, reporting.py, notify.py, experiments.py, scheduler.py, cli.py; backend/tests/test_workflow.py, test_experiments.py
Interfaces: run_workflow(notify=True); settle(session); backtest(session, game); send_report(report).
- [x] 写过期拦截、同期幂等、缺数据保护、旧预测结算及无未来数据测试，确认失败。
- [x] 实现任务互斥、正式批次冻结、逐期结算、原始数据快照、通知记录及重试状态。
- [x] 实现均匀基线、平滑频率、正则化模型的滚动评价；保存评价协议和结果。
- [x] 验证 CLI，运行真实数据工作流；仅在密钥可用时联调微信。

## Task 4: API 与 React 仪表盘
Files: backend/lottery/api.py; frontend/package.json, src/api.ts, src/App.tsx, src/components/, src/styles.css
Interfaces: GET /api/overview, /api/draws, /api/predictions, /api/experiments, /api/tasks, /api/health.
- [x] API 测试覆盖分页、空数据、彩种过滤、秘密不泄露。
- [x] 构建有侧栏、概览卡、各 5 注、最近 20 期表格/图表、复盘/实验/任务页的响应式仪表盘。
- [x] 运行后端测试、前端类型检查与构建；required browser_mcp：真实浏览器打开页面、切换彩种与页面、核对 API 数据、验证窄屏。

## Task 5: 本地运维、文档与独立审查
Files: scripts/, knowledge/, README.md, docs/verification.md
- [x] 提供启动/停止/备份/恢复入口和知识库，演练数据备份恢复。
- [x] 启动本地服务与调度器，检查下次运行时间；审阅全项目并修复重要问题。
- [x] 记录验证证据及未完成的外部依赖，如未配置的 SendKey 或不可达的官方接口。

## Execution ledger
- Ruling: 用户已明确“开始实施”，本轮直接按计划执行，不重复请求实施授权。
- Ruling: 当前目录只有设计文档且不是 Git 仓库；在用户指定目录构建，保留文档，不额外创建工作树或提交。
- Ruling: 用户明确本地 Python/React 双项目，采用 Sites 技能的 local-only 路径，不注册或发布云站点。

- 验收日期：2026-10-23。真实记录、测试与限制见 ../../verification.md。
- 审查修复：更正回退、结算事务独立提交、全量期号清单校验、过期预测过滤；手机表格溢出已修复。
- 运维边界：年度休市日历须按公告更新；未安装操作系统自动登录启动项；北京福彩原站不可达，已采用获准补充来源。
