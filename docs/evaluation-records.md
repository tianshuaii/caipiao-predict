# T13：历史与前瞻评估记录

统一格式 `evaluation-record-v1` 保留模式、彩种、策略、目标期、训练截止期、票组、逐注奖级和奖金、预算、状态、错误及来源证据。共享基础单式结算和票组汇总口径；未知中奖金额保持null，亏损与未能评估分开。

历史模式为 `historical`，记录保存在每次回测的artifact内：`report.forecast_audit[].forecasts[策略].evaluation`。文件内容寻址，数据库Experiment保留报告摘要和文件名。未重写旧报告，也没有将历史回测插入CandidateForecast或CandidateScore。

前瞻模式为 `prospective`，只读投影Prediction/Settlement及CandidateForecast/CandidateScore；通过当前官方开奖指纹选择结算。更正后旧结算留存源表，当前视图等待重新结算，绝不复用旧奖金。截止时间以UTC表示，保留训练数据hash。没有新增业务表或迁移。

状态：

| 值 | 含义 |
| --- | --- |
| settled | 已结算且奖金完整 |
| amount_pending | 已核对奖级，部分奖金未知 |
| failed | 模型生成或评估失败 |
| waiting | 等待开奖 |
| unscored | 已开奖但缺少当前指纹的结算 |
| draw_conflict | 官方来源冲突 |
| invalid_score | 原结算缺失逐注字段或票数不一致，保留原记录但排除比较 |
| invalid_cutoff | 生成超过截止或训练截止不早于目标期 |

历史回测的个别模型失败会保留，其他策略继续；配对Brier、命中数和校准表使用所有参加策略共同成功的期次。`evaluation_periods`为计划验证期数，`evaluated_periods`为共同有效期数，`failed_periods`为各策略失败期数。`random_simulations`仍表示配置的模拟次数；无共同期时不执行随机模拟且区间为null。零有效期时分数和净收益为null，前端显示无有效样本。无法重建严格历史观测或存在目标期泄漏时仍中止整个回测，不退回当前数据。

`comparison.issues`保留共同有效期；`excluded`保留缺模型、失败、模式/彩种/规则/预算不同的排除原因。`money_issues`另要求全部策略奖金完整，`money_excluded`保留未知奖金期。金额未知的票组仍参与已知奖级统计，其全区间净收益不按0填补。随机100组对照也要求各期同预算、同规则，缺失及金额排除可检查。

只读入口：

`GET /api/evaluations?game=ssq&limit=50&offset=0`

返回前瞻记录（最新在前）和候选共同期比较；limit上限200。可用`strategies=版本A,版本B`选择候选版本，否则选择所有已存候选版本。不同版本运行时间不重叠时，共同期可以为空，这是证据不足而不是平局；该接口不生成排名、不触发晋升。分页仅作用于records，comparison覆盖所选版本全部记录。

本轮未改正式选号、每彩种5注、推送、前瞻晋升规则或候选版本计算。后续T14–T17扩展绩效指标、区间与可解释排行。
