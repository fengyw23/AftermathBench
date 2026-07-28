# AftermathBench：GLM-5.2 24 小时持续优化报告

> 状态：实验进行中。本文中的结果表只在对应原始轨迹、终态评价和
> GitHub Actions run 均已归档后填写。

## 1. 本轮目标

本轮不是通过接口陷阱压低模型得分，而是验证一种困难恢复任务的构造方法：

> 在多个真实 ERP 操作已经提交、一次写操作的结果因连接中断而不确定时，
> Agent 能否主动查询权威记录，重建真实状态，完成所有下游修复，并保护
> 不应撤销的既有副作用？

目标验收线：

- 困难 holdout 的 Recovery Integrity Pass@1 不高于 50%；
- 相对同期 easy pilot 下降至少 40 个百分点；
- Matched-Group Success 不高于 20%；
- reference recovery 为 100%；
- 明示正确恢复范围的 execution control 不低于 80%；
- provider、工具接口和运行环境错误率为 0%。

## 2. 冻结的 easy pilot

Checkpoint：`erpnext-glm52-easy-pilot-20260729`（`88f842a`）。

旧任务只需要根据付款单、汇款记录、队列和外部送达四组信号作出 0–1 次
修改。GLM-5.2 在四个 matched variants 上全部通过。因此它只作为 easy
对照，不进入困难任务主结果。

## 3. 新的原生困难家族

任务家族为“部分采购退货、替换与付款对账恢复”。它在 source-built
ERPNext/Frappe 中真实创建：

- 原始采购订单与收货；
- 合格与不合格数量；
- 不合格质量检查；
- 两张采购发票；
- 跨两张发票的共享 Payment Entry；
- 部分 Purchase Return；
- 部分 Debit Note；
- 替换采购、收货与发票；
- Stock Ledger、General Ledger 和供应商余额；
- 幂等的供应商取件外部事件。

四个变体向模型显示完全相同的连接中断，但真实边界分别是：请求未到达、
Return 已提交且响应丢失、Return 已提交但 enqueue 失败、以及异步任务
已存在但 worker 尚未执行。

## 4. 为什么难度来自恢复推理

准入结果来自真实回放，而不是 manifest 中的作者数字。验证器检查：

- 17 次成功前序写操作；
- 至少 3 个必须保护的已提交副作用；
- 文档、库存/会计账本、异步任务三类独立证据；
- 从原始 PO 到收货、发票、共享付款、退货、信用、替换和外部事件的
  多跳关系；
- 至少 5 次真实恢复修改；
- 至少 2 个下游闭环；
- 单一查询无法区分四种恢复动作；
- no-op、盲目重试、假定已提交、只修失败记录、全部撤销、取消共享付款
  和 compact boundary tree 均无法解决 matched group。

每条关系边必须能在 ERPNext 字段或审计记录中重放，例如
`purchase_order`、`purchase_receipt`、`Payment Entry.references`、
`return_against`、ledger `voucher_no`、RQ job 参数和外部 delivery key。

## 5. 评分与错误归因

主判分是确定性的终态检查：

- Goal Completion；
- Repair Completeness；
- Preservation；
- Protocol Safety；
- Recovery Integrity Pass（以上全部通过）。

失败轨迹进一步归因为：

- Investigation Failure；
- State-Inference Failure；
- Scope Failure；
- Execution Failure；
- Verification Failure；
- Infrastructure Failure（不计分并重跑）。

## 6. 实验结果

### 6.1 确定性控制

| 控制 | 变体数 | Pass@1 | Matched-Group | 备注 |
|---|---:|---:|---:|---|
| Reference recovery | 待填 | 待填 | 待填 | 仅使用模型可见工具 |
| Explicit-scope execution control | 待填 | 待填 | 待填 | 提供正确范围，不提供隐藏状态 |
| 固定策略中最强者 | 待填 | 待填 | 待填 | 从真实失败状态执行 |

### 6.2 GLM-5.2

| 数据 | 运行数 | Recovery Integrity | Matched-Group | 基础设施错误 |
|---|---:|---:|---:|---:|
| Easy pilot | 待填 | 待填 | 待填 | 待填 |
| Dev | 待填 | 待填 | 待填 | 待填 |
| Frozen holdout | 待填 | 待填 | 待填 | 待填 |

### 6.3 组件与错误类型

| 指标 | Easy | Dev | Holdout |
|---|---:|---:|---:|
| Goal Completion | 待填 | 待填 | 待填 |
| Repair Completeness | 待填 | 待填 | 待填 |
| Preservation | 待填 | 待填 | 待填 |
| Protocol Safety | 待填 | 待填 | 待填 |

错误分布及代表轨迹将在实验完成后由
`scripts/summarize_native_model_runs.py` 自动填充并人工复核。

## 7. 结构性迭代记录

每轮只允许增加真实共享依赖、数量关系、跨账本影响或反事实边界；不允许
隐藏必要证据、模糊工具参数、增加无关噪声或缩短轮次。

| 轮次 | Commit | 改动 | 有效性检查 | GLM 结果 |
|---|---|---|---|---|
| 0 | 待填 | 原生纵向切片 | 待填 | 待填 |
| 1 | 待填 | 如发生则填写 | 待填 | 待填 |
| 2 | 待填 | 如发生则填写 | 待填 | 待填 |
| 3 | 待填 | 如发生则填写 | 待填 | 待填 |

## 8. 当前结论与边界

最终只在完成冻结 holdout 后填写。无论是否达到目标降幅，都必须报告：

- 哪些策略仍能解决任务；
- GLM 失败究竟发生在调查、推断、范围、执行还是验证；
- 哪些困难结构可以迁移到 ITSM、云运维或 coding；
- 当前仍只有一个原生任务家族，不能宣称已经形成完整 benchmark。
