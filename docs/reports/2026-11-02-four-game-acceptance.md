# 四彩种统一流程验收记录（本地）

日期：2026-11-02

本分支将大乐透、双色球、七乐彩、七星彩纳入同一条受审计流程。七乐彩使用 7 个基本号和 1 个特别号；七星彩保留七个位置，前六位为 0–9，第七位在 `2020100` 起为 0–14。七星彩研究不会混合规则边界两侧的数据。

已验证的本地环节：

- 官方来源解析、原始响应留存、来源冲突处理、年度日历与期次计算；
- 结构化号码校验、五注冻结预测、开奖结算、未知奖金待定处理；
- 分区/分位概率、滚动研究回测、Brier 评分、冻结候选、60 期/1%/最近 30 期/e-value 晋升门槛；
- 前瞻排行、随机对照、分析接口和四彩种界面展示；
- 晨报和运行监控按注册表遍历全部彩种。

本轮验证命令：

```sh
backend/.venv/bin/python -m pytest backend/tests/test_feature_service.py backend/tests/test_experiments.py -q
backend/.venv/bin/python -m pytest backend/tests/test_prospective.py backend/tests/test_ranking.py backend/tests/test_evaluation.py backend/tests/test_performance.py -q
backend/.venv/bin/python -m pytest backend/tests/test_monitoring.py backend/tests/test_schedule.py backend/tests/test_workflow.py -q
cd frontend && pnpm build
```

生产状态：尚未迁移或部署本分支，尚未将七乐彩、七星彩全量历史导入生产库。因此不能声称这两个彩种已经在线生成推荐或积累前瞻样本。上线前必须完成备份恢复演练、执行加法迁移、全量导入与官方库存核验、核对日历、确认四彩种候选均在销售截止前冻结，并验证晨报与监控。
