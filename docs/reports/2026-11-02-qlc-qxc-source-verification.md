# 七乐彩、七星彩开奖源字段验证

验证时间：2026-11-02（北京时间）。本次为只读网络检查；未写数据库、未导入历史、未触发调度或通知。

## 七乐彩

- 主源：中国福彩网 `findDrawNotice`，参数 `name=qlc&pageNo=1&pageSize=20&systemType=PC`。
- 独立源：上海福彩数据中心七乐彩历史页及其 `lottcode=07` 数据链路。
- 主源样本 `2026125`：基本号 `02,05,10,15,22,23,28`，特别号 `03`，日期 `2026-10-30`，销售额 `5582756`，奖池 `0`；奖级列表包含奖级、中奖注数和单注金额。
- 字段映射：`code`→期号，`date`→开奖日，`red`→基本号，`blue`→特别号，`prizegrades`→奖级，`sales`→销售额，`poolmoney`→奖池。

## 七星彩

- 主源：中国体彩网 `getHistoryPageListV1.qry`，参数 `gameNo=04&provinceId=0&pageSize=20&isVerify=1&pageNo=1`。
- 独立源：江苏体彩网 `/Lottery/_ListData?itemType=s7&pageindex=1`。
- 两源样本 `26125`：开奖日 `2026-11-01`，有序号码 `2 9 4 5 6 3 2`。主源同时给出销售额、奖池、开奖 PDF 与奖级注数/单注奖金。
- 字段映射：`lotteryDrawNum`→期号（由五位期号规范化为七位），`lotteryDrawTime`→开奖日，`lotteryDrawResult`→七个有序位置，`prizeLevelList`→奖级，`totalSaleAmount`→销售额，`poolBalanceAfterdraw`→奖池。

## 结论与边界

两项主源均可获得解析所需的号码、日期和奖级信息；独立源可用于号码和日期交叉核对。夹具仅保留最小字段集，避免把不必要的第三方页面内容纳入测试。后续采集接入必须保留每次完整原始响应到 `raw_fetches`，分页重复、字段异常、主/次源号码不一致或奖级待确认都不得静默通过。
