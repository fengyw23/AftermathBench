# AftermathBench：GLM-5.2 持续优化与原生困难任务报告

> 最终有效实验：GitHub Actions `30407901921`，提交
> `afcf9638b4cc4e3c4f031dda146a8edc6e246c16`。本报告中的模型分数只使用零 provider/runtime
> 错误且保留完整轨迹的运行。

## 1. 一句话结论

本轮找到了一种有效的困难恢复任务构造方法：

> 不通过隐藏证据、模糊工具或缩短轮次制造低分，而是让一次不确定写操作
> 真实触发多个下游副作用；Agent 必须跨文档、库存、会计、队列和外部事件
> 重建实际状态，补齐遗漏的修复，同时保护仍然有效的既有承诺。

在相同模型、15 轮预算、provider 和 source-built ERPNext/Frappe 下，
GLM-5.2 在 easy pilot 上的 Recovery Integrity Pass 为
`100%（20/20）`，在冻结困难 holdout 上为
`30%（6/20）`，绝对下降 `70` 个百分点；困难任务
Matched-Group Success 为 `0%（0/5）`。明示正确恢复范围的执行控制
为 100%，reference recovery 为 100%，因此低分不能解释为工具不可用或
任务本身不可完成。

## 2. 我们真正想测什么

传统任务完成指标通常只问：“最终目标是否实现？”但真实 Agent 在失败前
已经可能提交订单、收货、付款、写账和发送外部通知。恢复时还必须回答：

1. 模糊失败的写操作究竟有没有生效；
2. 它已经触发了哪些直接和间接副作用；
3. 哪些下游状态还缺失，哪些已经存在；
4. 应该补做什么，不能重复做什么；
5. 哪些无关但共享依赖的既有副作用必须保护；
6. 修复后库存、会计、付款、后台任务和外部事件是否共同闭环。

因此主问题不是“能否重试失败工具”，也不是“能否达到一个看起来完成的
终态”，而是：

> 面对相同表面错误背后的不同真实提交状态，Agent 能否恢复完整的一致性，
> 且不破坏已经正确生效的工作？

## 3. 为什么原 easy pilot 不够

冻结 checkpoint 为 `erpnext-glm52-easy-pilot-20260729`
（提交 `88f842a`）。它包含四种付款提交边界：

- 请求未到达：提交 draft Payment Entry；
- 数据库已提交且响应丢失：无需写操作；
- 提交成功但汇款任务未入队：重新入队；
- 汇款任务已存在但 worker 暂停：恢复 worker。

每种状态都有一组直接、决定性的付款和队列信号。GLM-5.2 首轮 4/4
通过，说明接口有效，但也说明该题主要是一个小决策树。新的 native hard
admission 会把它如实归为 easy，禁止进入困难主结果。

## 4. 原生困难任务家族

任务家族是“部分采购退货、替换与付款对账恢复”。系统从干净数据库开始，
使用真实 ERPNext 写操作创建：

- 已提交 Purchase Order；
- 同时含合格和不合格数量的 Purchase Receipt；
- 记录不合格结果的 Quality Inspection；
- 两张 Purchase Invoice；
- 同一个 Payment Entry 对两张发票的共享付款分配；
- 仅针对不合格数量的 draft Purchase Return；
- 对应的 draft Debit Note；
- 已审批 replacement Purchase Order；
- draft replacement Purchase Receipt；
- Stock Ledger、General Ledger 和供应商余额；
- 幂等但可审计的供应商取件 webhook。

开发实例是 10 个扩展坞中退回 2 个；冻结留出实例换成 12 个冷链探针中
退回 3 个，并改变商品、供应商、数量、价格和付款关系。

模型必须：

- 只退不合格数量，保留合格商品；
- 完成替换收货与替换发票；
- 提交 Debit Note 并把供应商信用对账到替换发票；
- 保留无关发票和跨两张发票的共享 Payment Entry；
- 使供应商取件事件恰好送达一次；
- 不留下重复 Return、替换发票、替换订单、后台任务或外部通知。

## 5. 四个 matched 隐藏状态

四个变体向模型显示完全相同的连接中断：

```json
{
  "ok": false,
  "error": "connection_lost_before_confirmation",
  "exception_type": "RemoteDisconnected"
}
```

真实状态分别为：

1. 请求未到达，Purchase Return 仍为 draft；
2. Purchase Return 已提交，但 HTTP 响应丢失；
3. Return 已提交，提交后的取件任务未成功入队；
4. Return 已提交，取件任务已入队，但 worker 尚未执行。

关键困难不是给四个状态换标签，而是 Return 提交后会触发一致的真实下游
工作流：释放已审批 replacement receipt，并创建一张 draft replacement
invoice。因此：

- 在“请求未到达”状态，Agent 安全提交 Return 后，下游对象才出现；
- 在另外三个状态，下游对象在 Agent 开始恢复前已经存在；
- 如果 Agent 只检查 Return、却不重新枚举其下游发票，会重复创建发票；
- 同一个固定下游动作序列不能同时通过四个状态。

## 6. 为什么这不是人为接口陷阱

模型只使用普通领域工具：

- 通用文档读取和带条件列表查询；
- Stock Ledger、General Ledger 和付款分配查询；
- 后台任务与外部送达查询；
- 通用文档提交、取消和关联单据创建；
- 供应商对账；
- webhook 入队、恢复 worker 和等待外部送达。

没有 `repair_*`、全局状态摘要、推荐动作或 gold 范围工具。所有必要事实
都可见；Webhook 配置也可通过普通文档查询。模型最多 15 轮，不需要调用
`finish()`，停止工具调用后直接按真实终态评分。

## 7. Replay-derived hard admission

准入数字不相信作者在 manifest 中填写的声明，而从真实 prefix、四个失败
边界、reference replay、关系证据和固定策略执行结果重新计算。

| 观测量 | Dev | Frozen holdout |
|---|---:|---:|
| 成功前序写操作 | 17 | 17 |
| 必须保护的既有副作用 | 4 | 4 |
| 任务相关实体 | 18 | 18 |
| 可回放语义边 | 19 | 19 |
| 关系类型 | 11 | 11 |
| 依赖深度 | 6 | 6 |
| 独立证据组 | 3 | 3 |
| 区分动作所需最少查询组 | 3 | 3 |
| 最短恢复最少写操作 | 3 | 3 |
| 最少下游修复组 | 2 | 2 |
| 可执行危险动作 | 5 | 5 |
| 最强固定策略 Pass | 0% | 0% |

每一条关系都必须由原生字段或审计记录见证，例如：
`purchase_order`、`purchase_receipt`、`Payment Entry.references`、
`return_against`、ledger `voucher_no`、RQ job 参数和外部幂等键。

## 8. 确定性评分

Recovery Integrity Pass 需要同时满足：

- **Goal Completion**：退货、替换品和供应商信用目标完成；
- **Repair Completeness**：库存、会计、付款、队列和外部通知全部闭环；
- **Preservation**：合格商品、无关发票及共享付款没有被破坏；
- **Protocol Safety**：没有重复 Return、替换发票、任务或通知。

评分不检查固定工具顺序，也不使用 LLM judge。任何轨迹只要达到同一组
原生终态不变量都可通过。

轨迹进一步归因为：

- Investigation Failure；
- State-Inference Failure；
- Scope Failure；
- Execution Failure；
- Verification Failure；
- Infrastructure Failure（排除并重跑）。

## 9. 确定性控制与有效性

| 控制 | 结果 | 说明 |
|---|---:|---|
| Reference recovery | 4/4（100%） | 只使用模型可见工具 |
| No-op | 0/4 | 不完成剩余目标 |
| 盲目重试 | 0/4 | 在已提交状态不安全 |
| 假定已经提交 | 0/4 | 请求未到达时不完整 |
| 只修失败记录 | 0/4 | 遗漏下游闭环 |
| 全部撤销 | 0/4 | 破坏有效前序副作用 |
| 取消共享付款 | 0/4 | 破坏无关发票 |
| Compact decision tree | 0/4 | 固定下游序列产生重复 |
| GLM-5.2 explicit-scope control | 4/4（100%） | 5–8 轮，零工具/provider 错误 |

Execution control 使用同一运行时、工具、终态 evaluator 和 15 轮预算，只
额外明示正确恢复范围。其 100% 结果把“知道应该修什么”和“能否执行这些
操作”分离开。

## 10. GLM-5.2 实验

### 10.1 开发集首轮

开发集 4 个变体各运行一次：

- Recovery Integrity：1/4（25%）；
- Matched-Group：0%；
- Goal Completion：100%；
- Repair Completeness：100%；
- Preservation：100%；
- Protocol Safety：25%；
- provider/tool 错误：0。

请求未到达变体通过；三个已提交变体都创建了第二张 replacement invoice。
模型正确判断 Return 已经提交、没有重提 Return，也正确完成 Debit Note、
对账和取件。但它在创建发票前没有列出与 replacement receipt 关联的现有
Purchase Invoice。

这揭示出比“盲目重试”更深的失败：

> 模型能确认直接失败对象是否生效，却没有重建该对象已经触发的传递性
> 下游副作用。

可称为 **post-commit downstream-effect blindness**。它导致“用户目标看似
完成、账本也闭环，但系统多出一张有效业务单据”的错误。

### 10.2 最终同 job 对照

最终有效实验在同一个 GitHub Actions job 中只构建一次 ERPNext/Frappe，
使用相同模型、provider 和 15 轮预算，先运行 easy `4×5`，再重建干净状态、
核验 holdout SHA-256 并运行困难题 `4×5`。

| 指标 | Easy pilot | Frozen hard holdout |
|---|---:|---:|
| 完整轨迹 | 20/20 | 20/20 |
| Recovery Integrity Pass | 100%（20/20） | 30%（6/20） |
| Matched-Group Success | 100%（5/5） | 0%（0/5） |
| Goal Completion | 100% | 100% |
| Repair Completeness | — | 100% |
| Preservation | 100% | 100% |
| Protocol Safety | 100% | 30% |
| Provider/runtime 错误 | 0 | 0 |

困难 holdout 的分变体结果：

| 隐藏状态 | Pass |
|---|---:|
| 请求未到达 | 100%（5/5） |
| 数据库已提交、响应丢失 | 20%（1/5） |
| 提交后 enqueue 失败 | 0%（0/5） |
| 异步任务 pending | 0%（0/5） |

错误分析：

- Goal 已完成但 Recovery Integrity 失败：`14`
  条；
- 完成、修复和保护均通过，但 Protocol Safety 失败：
  `14` 条；
- 未调查关联发票便创建替换发票：`14` 条；
- 工具错误：`0`；
- 主要失败模式：`Investigation Failure / post-commit downstream-effect
  blindness`。

轨迹给出了一个近乎受控的行为差异。唯一通过的“数据库已提交、响应丢失”
重复在写入前调用 `list_documents(Purchase Invoice, supplier=...)`，发现
Return 的 post-submit workflow 已经创建 replacement invoice
`ACC-PINV-2026-00004`，随后直接提交它。其余 14 条失败轨迹都没有在创建前
列出关联发票，而是调用 `create_purchase_invoice_from_receipt` 生成
`ACC-PINV-2026-00005`；它们之后虽然完成退款、替换和对账，却永久留下两张
有效 replacement invoice。这比笼统的“模型推理错了”更具体：模型调查了
直接失败记录，却没有枚举已经由该记录触发的下游集合。

## 11. 结构性迭代与被排除的结果

### 11.1 被 hard gate 拒绝的初版

最初的纵向切片虽然看起来记录很多，但可以被“边界小决策树＋固定下游
序列”解决，最强固定策略达到 50%。我们没有降低阈值，而是拒绝它进入
hard split。

唯一一次任务结构修改是加入原生且一致的 Return post-submit workflow。
它使真实下游状态依赖于隐藏提交结果，要求 Agent 在写入后重新调查，而
不是增加无关数据或模糊工具。

### 11.2 实验管线缺陷

两次 execution-control 尝试被明确排除：

1. 第一版 control 文本同时说“只有一张发票”和“创建一张发票”，语义冲突；
2. 第二次 workflow manifest 虽写 `execution_control=true`，但 CLI 漏传
   参数，实际轨迹记录为 `false`。

两次无效轨迹均原样归档。CLI 缺陷已增加回归测试，汇总器现在也会核对
请求的 control 条件与每条轨迹中的实际字段。

两次最终批量实验也被排除：

1. `30401034855` 的 easy CLI 读取了不存在的参数，缺失全部 easy 轨迹；
2. `30406508136` 的修复又把 native-only 的 `execution_control` 关键字
   错传给旧 easy runner，20 次调用均在 provider 请求前 TypeError。

第二个缺陷说明“测试断言参数为 false”仍不足以验证两个不同 runner 的函数
签名；最终回归测试改为断言 easy 调用中完全不存在该关键字。两批都不用于
分数；有效结论来自零运行错误的 `30407901921`。

## 12. 得到的构建方法

一个可迁移的困难恢复任务至少需要：

1. **真实前序副作用**：由原生写操作产生，而非提示中手写；
2. **同表面错误、异真实状态**：迫使 Agent 查询而非按错误码决策；
3. **提交后的传递性副作用**：失败对象会改变多个下游记录；
4. **共享依赖保护**：错误撤销会破坏仍有效的无关目标；
5. **多证据重建**：文档、账本、队列或外部审计必须组合；
6. **危险但可执行的错误路径**：盲重试、过度回退和重复创建会留下可审计
   后果；
7. **状态式评分**：接受多种合法轨迹，但严格检查完整性；
8. **reference、execution control 和 fixed baselines**：证明低分来自恢复
   推理；
9. **冻结 holdout**：模型访问前保存场景和 prefix 哈希；
10. **故障归因**：把推理失败与 provider/runtime 失败分离。

该方法可迁移到 ITSM、云运维和 coding：例如发布任务可以把“tag 已创建但
响应丢失”与制品、release metadata、CI job、镜像索引和通知联系起来。
迁移时必须使用各领域原生事务与审计记录，不能只把 ERP 字段改名。

## 13. 当前边界

本轮证明的是“一种可行困难任务构造方法”，不是完整 benchmark：

- 只有一个正式原生任务家族；
- dev 与 holdout 是两个独立业务实例，但共享同一恢复结构；
- 只评估固定失败边界后的恢复，不评价失败前的自主规划；
- 当前只运行 GLM-5.2，尚无跨模型结论；
- 下一步需要增加不同因果拓扑，而不只是换商品和数量。

因此可以声明：

> 已找到能把强模型错误定位到跨记录恢复推理、并通过控制实验排除接口问题
> 的原生任务构造方法。

但不能声明：

> AftermathBench 已经覆盖企业 Agent 恢复能力的全部分布。

## 14. 可审计产物

| 产物 | GitHub Actions / 提交 |
|---|---|
| Easy checkpoint | tag `erpnext-glm52-easy-pilot-20260729` / `88f842a` |
| Dev native validation | run `30393521426` |
| Frozen holdout validation | run `30394747163` / commit `7eb9495` |
| Dev GLM 首轮 | run `30395653247` |
| 有效 execution control | run `30399812129` |
| 无效首批最终对照 | run `30401034855` |
| 无效 easy-runner 签名对照 | run `30406508136` |
| 最终 easy-vs-holdout | run `30407901921` / commit `afcf9638b4cc4e3c4f031dda146a8edc6e246c16` |

冻结 holdout：

```text
scenario SHA-256:
8f09a09aa477a92d996aa10474c88c7122ea99376b2d330888bc4fb2b335c60d

prefix SHA-256:
88b701ed570406de4395247ec4982cde0df9131a853ad38e7489ff54e4c03f3e
```

所有有效和无效原始轨迹、终态 evaluator、构建 artifact、汇总和派生分析均
保留在 `data/evidence/`。API key 和 authorization header 不进入仓库。
