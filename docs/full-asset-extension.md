# 全资产扩展

## 能力与估值口径

“全资产”页在 PanWatch 原有股票持仓之外维护独立账本，不改写上游的
`stocks`、`accounts` 或 `positions` 表。支持：

- A 股、港股、B 股、ETF、公募基金、私募基金；
- 现金、负债与净值调整项；
- 内盘期货和期权；
- 每日收盘净资产快照、份额净值、沪深300ETF（510300）基准和超额收益。

所有汇总金额以人民币展示。证券类资产按以下公式估值：

```text
人民币市值 = 数量 × 原币价格 × 合约乘数 × 兑人民币汇率
```

沪市 B 股使用 USD/CNY，深市 B 股使用 HKD/CNY。币种与汇率保存在每项资产上，
不会把 B 股原币价格直接当成人民币价格。

负债始终按绝对值从总资产扣减。期货保存“账户权益/保证金”和“名义敞口”两个
数值：前者进入净资产，后者用于真实市值及杠杆率。期权可按数量、权利金、乘数和
多空方向估值，也可以使用直接金额记录账户权益。

## Google Sheets 同步

数据链路如下：

```text
Google Sheets
  └─ Apps Script 刷新完成
      └─ PUT 私有 Cloudflare Worker KV
          └─ PanWatch 工作日 23:10 拉取
              ├─ 幂等更新当前资产
              └─ 记录当日快照与基准
```

Apps Script 与 Worker 使用脚本属性 `PANWATCH_WORKER_TOKEN`。PanWatch 容器使用
同值环境变量 `PANWATCH_WEALTH_SYNC_TOKEN`。密钥只通过请求头传递，不写入数据库、
日志或同步负载。可通过 `PANWATCH_WEALTH_RELAY_URL` 覆盖默认中继地址。

日常 Worker 负载只保留当日数据，避免每天重复写入整段历史。首次迁移时可以直接
向 `/api/wealth-sync/google-sheets` 提交包含 `history` 的完整负载，请求头使用
`X-PanWatch-Sync-Token`。

同步以 `spreadsheet_id + source_key` 为幂等键：同一证券更新原记录，表格中删除的
项目会停用，不会产生重复持仓。手工录入资产使用独立来源，不受表格同步影响。

## 数据表与扩展边界

后端新增四张独立表：

- `wealth_assets`：当前资产、币种、汇率和估值输入；
- `wealth_snapshots`：每日净资产与基准；
- `wealth_snapshot_items`：每日分类明细；
- `wealth_sync_runs`：同步审计摘要。

代码边界：

- 后端实现：`src/extensions/wealth/`
- 前端实现：`frontend/src/extensions/wealth/`
- 后端注册：`src/web/app.py`
- 调度器生命周期：`server.py`
- 前端导航与路由：`frontend/src/App.tsx`

除三个入口文件外，不修改上游业务模块。同步上游时使用：

```bash
git fetch upstream
git merge upstream/main
```

冲突通常只会集中在入口注册位置；扩展目录可以原样保留。

## 调度与失败策略

Google Sheets 的 `main` 触发器约在 22:49 启动。PanWatch 调度器按
`Asia/Shanghai` 时区在周一至周五 23:10 执行，预留刷新与推送时间：

1. 从私有 Worker 拉取最新 Google Sheets 资产；
2. 幂等更新当前资产；
3. 获取 510300 最新价；
4. 覆盖或创建当日快照。

中继或基准行情失败时不伪造数据：中继失败会使用本地最后一次成功持仓继续快照，
基准失败则保留空值。每次同步结果写入 `wealth_sync_runs`，页面显示最近同步日期、
资产数和历史数。

## 验证

```bash
.venv/bin/python -m pytest tests -q
cd frontend && pnpm build
```

全资产扩展的定向测试位于 `tests/test_wealth_extension.py`，覆盖 B 股汇率、负债、
期货敞口、Google Sheets 幂等同步、历史导入、收益曲线和 Worker 中继。
