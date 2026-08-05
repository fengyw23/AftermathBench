# AftermathBench 完整上下文交接（2026-08-05）

> 用途：把长对话中的研究演化、已确定的方法、仓库事实、实验口径、经验和下一步工作迁移到新的 Codex 会话。
>
> 当前事实的权威顺序：机器可验证的 CLI/manifest > 已归档原始证据 > 本文 > 叙述性 README/旧阶段文档 > 聊天记忆。

## 0. 新会话应先记住的十件事

1. 当前项目名是 **AftermathBench**，不是早期的 RepairScope-Bench。
2. 当前核心问题不是“寻找经济上最优的回退”，而是**写操作报错且真实结果不确定时的完整、保守、无重复恢复**。
3. 前序副作用必须来自 ERPNext、Forgejo、Kubernetes 等原生运行时的真实写操作；固定失败快照只是为了控制变量。
4. 模型看到的是普通查询/操作工具，不是答案式 `repair_*` 工具，也不是作者直接写出的状态总结。
5. 同一 matched group 中，不同真实边界给模型相同的表面错误，但需要不同恢复范围；每一道边界本身仍由确定性终态检查判分。
6. “至少三种正确恢复范围”指**同一组不同边界之间至少有三种正确恢复签名**，不是一道题同时随意接受三种相互矛盾的答案。
7. 当前 `94` 表示 replay-admitted hard failure states，不表示 94 道题都做过普通强模型实验，也不表示 94 道正式发布题。
8. 当前普通强模型证据至少覆盖 `25` 个仍有效的 hard development states，但其中只有 `21` 个属于当前 active 94；另有 `12` 个历史轨迹对应已变化的任务定义。
9. 隐藏题冻结后不得用模型结果反向调题；模型已消费的开发题也不能改名冒充 hidden test。
10. 眼前优先级是：收拢正在运行的 Forgejo 实验、建立机器可验证的模型证据 registry、补公共困难题的普通模型覆盖，然后继续补齐正式矩阵。

## 1. 仓库与即时状态

- 本地仓库：`C:\Users\Richard\Documents\New project 5\AftermathBench`
- GitHub：<https://github.com/fengyw23/AftermathBench>
- 当前分支：`native-hard-recovery-v1`
- 当前提交：`eadc580`
- 工作树在本次交接文档写入前为 clean，且本地分支与 `origin/native-hard-recovery-v1` 对齐。
- Python 包版本：`0.4.0`。
- 当前发布状态：`partial_release`。
- 当前 release manifest：`aftermathbench-2026.08-r1`，`validate-release` 通过。

2026-08-05 本次迁移时的两个在途/刚结束实验：

| Run | 内容 | 工作流状态 | 研究结果是否已入库 |
|---|---|---|---|
| [30985603153](https://github.com/fengyw23/AftermathBench/actions/runs/30985603153) | Forgejo migration，GLM-5.2，4 个 matched boundaries | workflow `success`，771,020 B artifact 已上传 | 否；成功仅表示工作流完成，仍需导入并读取 summary/轨迹 |
| [30985786988](https://github.com/fengyw23/AftermathBench/actions/runs/30985786988) | Forgejo package provenance r1，GLM-5.2 + DeepSeek-V4-Pro | workflow `success`，343,828 B artifact 已上传 | 否；仍需导入并审计确定性得分 |

注意：GitHub workflow 的绿色成功不等于 `Recovery Integrity Pass`。只有拿到轨迹和确定性 evaluator summary 后才能计入模型证据。

另有几项已经产生、但尚未全部进入 canonical registry 的 CI 结果：

- Kubernetes interaction 两个 hidden candidate 收据分别来自 runs [30948104711](https://github.com/fengyw23/AftermathBench/actions/runs/30948104711) 和 [30948101250](https://github.com/fengyw23/AftermathBench/actions/runs/30948101250)，均为 13 states；验证并合并相应独立分支后，理论上可再登记 2 个 frozen slots / 26 states。在合入前不得计入当前 `48`。
- ERPNext multiwarehouse formal run `30956795224` 失败；需要一次聚焦诊断，按仓库执行契约最多两次 CI 重试，仍是个案失败则隔离并推进其他 slot。
- Forgejo package provenance 的 hidden/admission runs `30957543199`、`30957560584` 失败，当前不能计数。

## 2. 研究问题如何演化到当前版本

### 2.1 最初观察：失败后不应机械撤销所有已成功步骤

最初由 RAC 式副作用补偿工作启发。上海参会例子是：机票、酒店、接送已经订好，餐厅预订失败；通常不应因为晚餐失败就取消保证参会的机票。这里得到的第一条直觉是：

> 失败发生在哪里，只说明哪里需要处理，不能直接决定此前哪些成功操作应被撤销。

随后把问题表述为“恢复范围选择”，并用旅行、采购案例探索保留、修改、撤销哪些承诺。

### 2.2 RepairScope-Bench 阶段：客观经济最优

早期原型尝试通过取消费、退款、返利追回、许可证费等，把主观的“价值感知”改成可计算的经济判定。该阶段先后尝试过：

- 固定失败状态，所有模型从相同快照开始；
- Pareto 非支配的二维经济指标；
- 单一“增量恢复成本”和唯一最低成本范围；
- 旅行与售后采购的原生化；
- 沉没成本、多跳影响、阈值、条件合同、部分数量回退、桥接修复等推理结构；
- 单事实反事实对，要求模型随一个政策/价格事实改变恢复范围。

这个阶段产生了重要方法经验，但不再是当前论文主线。主要暴露的问题是：

- 很多题最终退化为“找到最低价格”或“唯一硬约束可行项”；
- 状态空间和工具返回过于干净时，强模型通过率很高；
- 人工槽位账本和宏动作缺乏领域真实性；
- 规则证据若没有在模型可见工具中出现，会造成评分歧义；
- 价格差距刻意拉大、数值不真实，会让题目显得人为构造；
- “最优恢复”容易让论文重心落到作者选择的目标函数，而不是 Agent 恢复能力本身。

### 2.3 导师反馈后的转向：复杂原生状态中的正确恢复

导师建议不再把论文说成“最优恢复”，而应扩大数据库和操作之间的真实依赖，评测 Agent 是否能正确恢复。领域也不应局限于旅行/采购，coding/DevOps 同样适合。

因此建立全新仓库 AftermathBench，并收敛为当前问题：

> 当长工具工作流已经产生持久副作用，随后某次写操作报错、其真实执行结果不确定时，Agent 能否通过原生系统的普通工具重建实际状态，修复完整的受影响依赖子图，保留仍有效的前序副作用，并避免重复执行、错误撤销或破坏共享依赖？

这里的科学对象是 **integrity-preserving recovery under ambiguous side effects**，不是单纯 rollback，也不是一般动态重规划。

## 3. 当前论文故事线

### 3.1 动机

现实工具系统中的报错不等于“没有执行”。超时、连接中断或 5xx 可能对应：

- 请求根本没有到达；
- 主写入已经提交，但响应丢失；
- 主写入完成，某个下游副作用没有产生；
- 异步任务已排队、已投递甚至被外部系统接受，但本地状态仍旧。

如果 Agent 盲目重试，可能重复退款、重复发布、重复通知；如果全量撤销，又可能破坏已生效的付款、库存、发布和共享依赖；如果只修最后一步，则可能留下账本、队列或外部事件不一致。

### 3.2 能力缺口

Agent 必须完成四件相互关联的事：

1. **调查**：选择普通工具读取哪些记录、账本、队列和外部事件；
2. **状态重建**：从分散证据判断报错动作究竟提交到哪一层；
3. **恢复范围推理**：决定哪些主记录、下游分支和共享承诺要修，哪些必须保留；
4. **执行与验证**：通过真实工具闭环修复，并确认没有重复或残余不一致。

### 3.3 与邻近 benchmark 的工作区别

最终论文仍需重新做严格文献核验。当前可用的保守定位是：

- RAC 类工作关注如何补偿/撤销副作用；AftermathBench 重点评测**报错之后实际发生了什么，以及应修复哪个范围**。
- STATE-Bench 已覆盖持久状态上的修改、取消和跨记录协调；AftermathBench 增加**同一表面错误下的提交不确定性、既有副作用保护和 matched recovery signatures**。
- STT-Arena 关注动态冲突后的适应与继续执行；AftermathBench 的中心变量是**报错写操作可能已产生部分或异步持久副作用**，恢复要核对原生账本/控制器/外部事件。
- StreamBench/Revisable by Design 一类工作讨论可修订执行或流式工作；AftermathBench 不把恢复局限于修改文本/计划，而要求改变并验证真实运行时状态。
- 早期聊天中出现过难以核验的 ReflectAgent/ERRRECOV-HARD 等引用。未经原论文、代码和数据三方核验，不得写入论文事实或比较表。

不要声称“首次提出部分回退”。更稳健的贡献是：

> 首次系统评测现代工具 Agent 在原生持久系统中，面对表面相同但实际提交边界不同的错误，能否从可查询证据推导恢复范围并保持全局完整性。

## 4. “工具交互”和原生性具体是什么

工具是模型 runner 暴露的 JSON function schema，它们调用真实运行时的普通 API、控制器或受审计适配器，并把真实结果序列化给模型。

- ERPNext：DocType 读取/列举、提交/取消/创建文档、Stock Ledger、GL Entry、付款分配、队列任务、外部取件或通知记录。
- Forgejo：仓库、PR、Git ref、Actions、release、asset、package、provenance、webhook delivery 和外部 receiver 记录。
- Kubernetes：原生 API 对象、Job/CronJob、控制器状态、事件、资源版本，以及可审计的跨系统 contract/event 记录。

工具的设计原则：

- 提供普通领域查询和操作，不提供全局“真实状态摘要”或“推荐修复范围”；
- 关键证据必须可见、可查询、可重放；
- 参数和返回语义应清楚，不靠接口陷阱降分；
- 每个评分约束都应能追溯到用户输入、前序轨迹、原生字段、工具结果或明确规则；
- benchmark-authored 的跨系统记录必须明确标注，不能伪称原生产品自带语义。

EnterpriseOps-Gym 早期 ITSM slice 只保留为 concept prototype：它发布了数据种子，但未公开足够的服务端事务实现，不能支撑最终“原生恢复”声明。当前正式 runtime 都是完全开源、版本固定且有源码/构建/回放证据的 ERPNext、Forgejo 和 Kubernetes。

## 5. 一道题到底怎样构造

### 5.1 名词口径

- **family**：一类业务恢复工作流，如 ERPNext manufacturing rework。
- **instance**：使用不同实体、数量和依赖关系独立构建的一次业务实例。
- **boundary / matched state / case**：同一实例在某个报错操作上的一种真实持久状态。
- **matched group**：同一实例的一组边界。用户目标和表面错误尽量相同，但正确恢复签名不同。
- **scenario**：仓库里的可执行场景包；开发副本、正式绑定副本等可能指向同一家族/实例，因此 scenario 数不能直接当论文题数。

### 5.2 构建流水线

1. 从干净、版本固定的原生数据库/集群开始。
2. 使用与模型同源的真实写工具执行前序工作流。
3. 生成订单、库存、账本、控制器任务、发布记录、外部通知等持久副作用。
4. 在目标写操作处注入错误，并真实生成不同提交边界。
5. 为每个边界保存可恢复快照、输入锁、哈希和原生证据。
6. 使用仅由公开工具组成的 reference recovery 恢复每个边界。
7. 运行 blind retry、assume committed、repair last step、full rollback 等固定策略。
8. 使用确定性 evaluator 检查终态。
9. 运行 explicit-scope execution control：告诉模型正确范围，但仍让它自己调用同一套工具。
10. 只有 reference、回放、固定策略拒绝、控制和 provenance gate 都满足，才能进入相应发布层级。

### 5.3 为什么固定失败快照仍有价值

当前主榜不评价失败前规划质量。所有模型从相同真实失败边界开始，是为了隔离恢复能力。前序承诺虽然不是本轮被测模型自由生成，但确实由原生工具执行、持久化、入账并可追溯。这不是“把答案写进文字”，而是 controlled evaluation。

未来可以增加端到端轨，但不应在当前规模未稳定时同时混入前序规划差异。

### 5.4 边界与恢复签名

全局 taxonomy 有四类：

1. `no_primary_effect`：主操作没有持久效果；
2. `primary_effect_uncertain`：主效果可能已生效，但调用者没有权威确认；
3. `downstream_effect_missing`：主效果已生效，至少一个必要下游分支缺失；
4. `downstream_effect_pending_or_accepted`：下游可能已排队、投递或被接受，本地状态滞后。

具体家族可以有 4、8、13 个更细边界。matched group 至少应覆盖三种正确恢复签名，例如：

- 创建缺失主记录并完成下游；
- 保留已提交主记录，只补缺失分支；
- 恢复已有异步任务，不重复入队；
- 所有义务已完成时只验证，不写入；
- 主记录错误时替换它，同时保护无关共享依赖。

## 6. Hard admission：什么才算困难题

当前 `docs/BENCHMARK_SPEC.md` 的 gate 要求所有数字来自实际 replay，而不是作者手填：

- 至少 8 次成功前序写操作；
- 至少 3 个要保护的持久前序副作用；
- 至少 20 个相关原生实体、8 类关系；
- 依赖深度至少 5；
- 至少 4 个独立证据组，reference recovery 实际使用全部 4 组；
- 任一单次查询不能决定全部正确动作，至少需要 2 个查询组；
- 每条语义关系都有原生字段或审计记录的回放证据；
- 最短正确恢复至少 4 次 mutation，至少修复 2 个下游依赖；
- 至少 2 个受保护共享依赖；
- 至少 3 个动作在部分 matched variants 中危险；
- 至少 3 个独立动作分支，其中至少 2 个随边界变化；
- matched group 至少 3 种恢复签名；
- 每种固定启发式 task pass 低于 50%，matched-group success 为 0；
- reference recovery 在全部边界通过。

重要经验：这些门槛只是必要条件，不是模型难度的充分条件。图大、证据多、reference 长、固定策略失败，仍可能被强模型一次看穿。

## 7. 评价指标与错误归因

主指标 `Recovery Integrity Pass` 是以下四项全部通过：

- `Goal Completion`：剩余用户目标完成；
- `Repair Completeness`：文档、库存、账本、队列和外部事件闭环，无失败/悬空残留；
- `Preservation`：合法前序副作用和共享承诺未被破坏；
- `Protocol Safety`：没有重复、禁止或不安全副作用。

同时报告：

- per-boundary task pass；
- `Matched-Group Success`：同一模型/策略是否同时解决整组反事实边界；
- 组件通过率、危险动作数、无效重试、验证遗漏；
- clean task / supplied-scope control / full recovery 之间的差距。

失败归因：

- `Investigation Failure`：未获取必要证据；
- `State-Inference Failure`：证据已获取但误判实际提交状态；
- `Scope Failure`：修复过多、过少或破坏共享依赖；
- `Execution Failure`：范围正确但工具操作未完成；
- `Verification Failure`：没有发现修复后的残余不一致；
- `Infrastructure Failure`：provider、容器、网络或工具 runtime 错误；排除并重跑，不计模型失败。

execution control 不等于普通模型实验。它只说明“给出正确恢复范围后，模型能否通过工具执行”，用于排除接口/执行能力不足。

## 8. 当前数据规模：必须分四种口径

以下数字来自 2026-08-05 在提交 `eadc580` 上执行：

```powershell
$env:PYTHONPATH = "src"
python -m aftermath_bench status
python -m aftermath_bench validate-release
```

### 8.1 目标矩阵

| 项目 | 数量 |
|---|---:|
| 原生领域 | 3（ERPNext、Forgejo、Kubernetes） |
| 目标家族 | 12（每领域 4） |
| 目标实例 | 36（每家族 1 public dev + 2 hidden test） |
| 目标 matched states/cases | 183 |

### 8.2 已实现和已准入

| 口径 | 数量 |
|---|---:|
| 仓库 scenario | 21 |
| 已实现 matched states | 110 |
| replay-admitted hard scenarios | 17 |
| replay-admitted hard states | 94 |
| 已有实现覆盖的目标家族 | 12/12 |
| 已有 hard-admitted 覆盖的目标家族 | 10/12 |

### 8.3 目标 slot 的发布层级

| 状态 | slots | matched states | 含义 |
|---|---:|---:|---|
| `formal_bound` | 4 | 29 | 正式 public-dev 绑定，manifest 和证据验证通过 |
| `frozen_hidden` | 10 | 48 | 已冻结候选，尚未作为正式 leaderboard hidden 绑定/消费 |
| `hard_candidate` | 3 | 12 | public hard candidate，尚未完成全部正式发布绑定 |
| `missing` | 19 | 94 | 目标矩阵仍缺失的 slots/cases |

当前 formal public-dev 四个槽位：

| 家族/实例 | cases |
|---|---:|
| Forgejo release package publication `dev-002` | 8 |
| Kubernetes constraint interaction `dev-006` | 13 |
| ERPNext sales return/exchange/reconciliation `dev-001` | 4 |
| ERPNext manufacturing rework `dev-002` | 4 |
| 合计 | 29 |

当前 frozen hidden 48 states 的分布：

- ERPNext manufacturing：2 个实例，8 states；
- ERPNext multiwarehouse：2 个实例，8 states；
- ERPNext sales return：2 个实例，8 states；
- Forgejo release publication：2 个实例，16 states；
- Forgejo migration：2 个实例，8 states。

当前 hard candidates：ERPNext multiwarehouse、Forgejo migration、Forgejo package provenance，各 4 states，共 12。

`29 + 48 + 12 = 89` 是已经落在目标 slot 状态中的 cases。`94` 个 hard-admitted states 是从 active scenario 文档计算的另一套、与发布槽位统计有重叠但不等价的集合：它会计入同一 slot 的开发/正式多身份，而 `89` 又包含未进入 active scenarios 的 frozen hidden candidates。因此**不能写成“89 加 5 等于 94”**，也不能把二者相减解释成五道额外题。不要把 `94`、`89`、`29`、`25` 混成一个数。

### 8.4 已知文档漂移

仓库部分叙述文档内部混有不同阶段的快照：

- `README.md` 顶部的 4 个 formal slots / 29 cases 是当前的，但后部仍有更早阶段数字，Kubernetes 历史普通实验结果也存在 `1/13` 与最新证据核算 `2/13` 的不一致；
- `docs/BENCHMARK_SPEC.md` 的 Current release boundary 仍写 3 个 formal slots、25 cases；
- `docs/ROADMAP.md` 末尾仍包含更早的 9 scenarios/49 states 阶段快照。
- `docs/RELEASE_GOVERNANCE.md` 仍含 1 个 formal slot 的旧状态；`data/release_manifest.json` 的 prose gap 仍称没有未消费 hidden instance，与 10 个 frozen candidates 的 registry 不同步。

这些不影响 machine-readable status，但后续应统一更新。新会话不得引用旧叙述数字覆盖 CLI 结果。

## 9. 当前强模型证据

### 9.1 仍有效的 ordinary strong-model evidence：25 states

这里的 ordinary 表示没有向模型提供正确恢复范围。

这 25 个 states 不是“当前 active 94 的已测子集”：其中 Kubernetes 13 + manufacturing 4 + package provenance 4，共 21 个属于当前 active scenario 口径；shared-batch 的 4 个仍有有效 hard replay/model evidence，但没有注册进当前 active scenario/status 94。应分别报告“跨全部 hard development evidence 的 25”和“当前 active 94 中的 21”。

| 家族/实例 | states | 模型 | Recovery Integrity 结果 | matched group |
|---|---:|---|---:|---|
| Kubernetes constraint interactions `dev-005` | 13 | GLM-5.2 | 2/13 | 失败 |
| ERPNext manufacturing rework `dev-002` | 4 | GLM-5.2 | 3/4 | 失败 |
| ERPNext shared-batch corrective recovery `dev-001` | 4 | GLM-5.2 | 2/4 | 失败 |
| Forgejo package provenance r2 | 4 | GLM-5.2、DeepSeek-V4-Pro | 均 4/4 | 通过，已饱和 |

Forgejo package provenance r2 应作为 positive/saturated control，而不是拿来证明强模型困难。

Kubernetes interaction 的 supplied-scope execution control 为 12/13，而 ordinary 为 2/13，且没有 provider/runtime 错误。这是目前最重要的科学信号：主要瓶颈在调查/状态判断/范围推理，而不是单纯不会调用工具。

这里的 12/13 对应历史开发实例 `dev-005`。当前四个 formal public slots 的 supplied-scope controls 在各自正式 summary 中合计 29/29；两者实例和证据身份不同，不能互相覆盖。

### 9.2 历史诊断：12 states

- Forgejo release publication `dev-002`：8 states，旧 GLM 结果 7/8；之后公开工具契约补充了 delivery identity 语义，不能直接当当前 formal score。
- 旧 ERPNext sales return `dev-001`：4 states，已有 GLM/DeepSeek 轨迹；当前 formal 场景是 `erpnext-sales-return-public-dev-001-r1`，身份不同。

历史证据不能因发布包装升级而随意作废，也不能在任务定义变化后冒充当前榜单结果。只有以下情况才需要重跑：场景/实例变了、模型可见工具契约变了、evaluator 变了、缺少足以核验身份的原始轨迹，或该题按设计从未给模型看过。

另有 12 个已经消费的 hidden methodology states：Forgejo hidden 8/8、ERPNext manufacturing hidden test-003 3/4。它们只证明 hidden lifecycle 方法，不是当前 leaderboard；hidden registry 中还有 3 个 invalidated lifecycle，不能计分。当前新冻结的 48 states 尚未被模型消费，必须继续保护。

### 9.3 当前最需要补的证据

- 在 model-evidence registry 落位前，严格口径是“0 个由机器 registry 认证的 current-formal ordinary states”；29/29 formal controls 全部是 `control-only`。Manufacturing `dev-002` 的 3/4 ordinary 与当前场景最接近，可先做 fingerprint equivalence audit，若输入锁、工具契约和 evaluator 身份相容再晋升，不要直接手工改标签；
- 四个 current formal public slots 的 lock-bound ordinary runs；
- ERPNext multiwarehouse、当前 sales-return r1、Kubernetes dev-006 等尚未有当前正式普通模型证据的公共题；
- 当前 Forgejo migration 与 package provenance 两个工作流的产物导入；
- 后续 GPT、Claude、Qwen、DeepSeek、GLM 等跨模型统一评测。

## 10. 已验证的构造经验

### 10.1 什么不够难

- 只把数据库做大或把 reference 轨迹做长；
- 只有一个清楚的缺失义务；
- 每个 boundary 都可由一个局部 repair 对应解决；
- 工具直接返回完整状态总结；
- 使用同一固定动作序列也能通过整组；
- 靠金额差、格式、轮次、终止协议或含糊参数制造失败；
- 将作者声明的复杂度当成真实难度，而不从 native replay 计算。

Forgejo cross-system reconciliation 曾达到 replayed evidence depth 6/6、固定策略失败，但 ordinary GLM 仍 6/6。这证明“查询证据多”与“恢复决策难”不是同一件事。

### 10.2 什么更可能形成真实困难

- 多个相互作用的义务，而不是多个彼此独立的缺口；
- 同一动作在一个 boundary 必须执行，在另一个 boundary 会造成重复副作用；
- 共享依赖同时服务待修目标和受保护目标；
- 主状态、账本、异步任务和外部 exactly-once 事件给出非单调组合；
- 证据分散但相关，每次查询都改变后续安全动作集合；
- 需要组合干预计划，而不是“发现一个 gap，调用一个 local repair”；
- 修复一个分支会改变另一个分支是否还需要/允许修复；
- 最后必须通过不同证据面验证闭环。

下一代 hardness 应同时记录：evidence-query depth、恢复签名数、intervention plan length、overlapping action pairs、variant-dependent unsafe actions、共享依赖数和非单调状态组合。不能只看实体/边数。

### 10.3 公平性底线

- 所有必要事实对模型可查询；
- 评分约束不得来自模型不可见常量；
- explicit-scope control 至少 80%；
- reference 100%；
- provider/runtime errors 为 0 或排除重跑；
- 不靠终止格式、`finish()`、工具命名陷阱或无关噪声降分；
- 模型如果找到一个评分器未覆盖但真实正确的终态，应审计 evaluator，而不是直接惩罚模型。

## 11. 顶会级论文要回答的假设

1. **Ambiguous-boundary gap**：模型在 clean/明确状态任务上成功，但在相同工具、相同目标的 ambiguous boundary 上显著下降。
2. **Scope bottleneck**：ordinary recovery 显著低于 supplied-scope control，说明瓶颈是调查、状态重建和范围推理。
3. **Matched-group brittleness**：模型 per-case 偶尔成功，却难以同时解决表面相同、正确动作相反的整个 matched group，暴露固定启发式。
4. **Integrity gap**：模型可能完成主目标，却在 preservation、repair completeness 或 exactly-once protocol 上失败。
5. **Interaction-over-size**：干预间交互和非单调性比数据库大小、图深或工具数量更能预测强模型失败。
6. **Cross-domain generality**：上述现象应在 ERP、coding/DevOps 和基础设施三个原生系统复现，而不是单一业务模板。

论文贡献应是：任务形式化、原生可重放构造方法、matched-boundary 设计、确定性完整性评价、强模型错误分析。不要再以经济最优、部分回退或“数据量大”作为主贡献。

## 12. 下一阶段的执行顺序

### P0：立即收口在途实验

1. 检查 runs `30985603153`、`30985786988`。
2. 通过已有 GitHub Actions evidence-import 模式获取 artifact；本地 GitHub CLI 未登录时，不要把密钥写入命令或仓库。
3. 校验 raw trajectory、模型输入、工具契约、evaluator summary 和基础设施错误。
4. 只有身份哈希一致且无基础设施错误时才计入 ordinary evidence。
5. 更新 `docs/MODEL_EVIDENCE_ACCOUNTING.md` 和机器 registry。

### P1：实现 model-evidence registry

新增机器可验证记录，至少包含：

- scenario/instance/variant 身份；
- scenario、input lock、tool contract、evaluator 的 SHA-256；
- model/provider/condition/repetition；
- ordinary、execution-control 或 historical 的角色；
- raw trajectory 和 summary 路径/哈希；
- infrastructure validity；
- 四项组件结果、总 pass、matched-group 结果；
- 自动错误归因；
- `ordinary-model-tested`、`historical-development`、`control-only`、`current-formal-model-tested`、`unrun` 状态。

加入测试，确保同一运行不能被重复计数、变更后的工具/evaluator 不能被错误晋升。

### P2：迅速增加“强模型已验证的困难题”

优先补测已有公共 hard 题，而不是马上发明新家族：

1. Forgejo migration（已启动）；
2. Forgejo package provenance r1（已启动）；
3. ERPNext multiwarehouse；
4. 当前 ERPNext sales-return r1；
5. Kubernetes public `dev-006`；
6. formal ERPNext manufacturing `dev-002` 的身份等价审计/必要时复跑；
7. Forgejo publication r1 的当前契约复跑。

每次都保留完整输入、工具调用、工具结果、终态和 evaluator 诊断。不要为了增加数字重跑完全等价的历史证据。

### P3：把 hard candidates 晋升为 formal public slots

当前三个候选：ERPNext multiwarehouse、Forgejo migration、Forgejo package provenance。补齐七类 formal evidence、execution control、输入锁和 manifest binding。晋升前先确认普通模型实验不会反向改题。

### P4：继续补齐 183-case 矩阵

优先补缺少 hard family 的两个目标家族：

- ERPNext partial-return/replacement/reconciliation；
- Forgejo PR/merge/release/webhook。

旧版本分别是 easy/candidate，不能只改标签。必须增加真实交互义务后重新 native replay。

之后按 family 独立构建缺失 public/hidden instances。hidden 先冻结，公共接口和 evaluator 稳定前不要消费。

在新造题前，先验证并合并已经成功生成的两个 Kubernetes hidden 收据；这一步若通过，可直接增加 26 个 frozen states，比另写一轮发展性文档更符合仓库的 progress-first contract。

### P5：构造真正交互型新 slice

Forgejo 已有一个 intervention-plan 设计：9 states、8 个组合修复状态、最大安全计划长度 3、30 个 overlapping action pairs、39 个诱人但不安全的选择。下一步是把它物化为真实 Forgejo 快照，逐个重放动作效果；若 native 行为不能复现设计声明，则拒绝该题。

同样原则应扩展到 ERPNext 的共享付款/批次/库存/账本闭环，以及 Kubernetes 的控制器状态、资源版本和外部结算事件。

### P6：论文级实验和发布

- 统一评测 GPT、Claude、Qwen、DeepSeek、GLM 和开源权重模型；
- 报告 task pass、matched-group、四组件、调查覆盖、危险重试和验证遗漏；
- 做 clean、supplied-scope、普通恢复、工具/证据消融；
- 比较固定策略与通用 Agent；
- 发布数据卡、污染控制、环境固定、reset/replay 和 evaluator 文档；
- 重新核验 RAC、STATE-Bench、STT-Arena、StreamBench 等相关工作，所有结论引用原论文和仓库中的可复核证据。

## 13. 研究与工程上的不可回退决策

- 保留固定失败边界作为当前主榜；端到端前序规划以后作为扩展。
- 前序副作用必须由原生工具真实生成，不能手写假数据库状态冒充。
- 不以经济“最优恢复”为论文主问题。
- 不用 LLM judge 判终态；主判分必须确定性、可重放。
- 不使用答案式工具、隐藏约束和接口陷阱。
- 每个 matched group 必须要求随真实边界改变恢复签名。
- 模型饱和的题可保留为 easy/positive control，但不能包装成 hard。
- replay admission、ordinary model evidence、formal release evidence 三种成熟度必须分开报告。
- 隐藏集严格一次性；开发实例不能改名为隐藏实例。
- 优先推进有效题数量和模型证据覆盖，不为形式化包装反复重跑相同实验。

## 14. 当前风险与应对

| 风险 | 当前表现 | 应对 |
|---|---|---|
| hard 数量和实证数量混淆 | 94 active hard-admitted；普通证据跨全部 hard development 为 25、其中 active 为 21 | model-evidence registry；所有汇报并列多个口径 |
| 复杂度门槛不能预测模型难度 | Forgejo depth 6/6 仍被 GLM 6/6 | 增加 intervention interaction/non-monotonicity 指标 |
| 原生性被质疑 | Kubernetes 部分跨系统 contract 为 benchmark-authored | 明确标注；用 ERPNext/Forgejo 原生证据做主要现实性支撑 |
| 文档数字漂移 | spec/roadmap/README 含旧阶段数字 | 由 CLI 生成状态表，减少手写数字 |
| hidden contamination | 已有 consumed/invalidation 历史 | 冻结 registry、usage ledger、一次性调用和哈希绑定 |
| 工具语义变化导致历史分数失效 | Forgejo delivery identity 补充 | 用 fingerprint equivalence audit 决定晋升或重跑 |
| 题目只是局部 gap repair | 强模型容易饱和 | 构造相互作用义务和跨分支动作副作用 |
| 追求低通过率导致人为刁难 | 早期接口/终止/规则歧义教训 | control、证据可见性、infra 归因和公平性 gate |

## 15. 新会话的首个工作包

新会话不要重新调研整个历史，也不要从 RepairScope 重新设计。直接执行：

1. 读取本文、`docs/MODEL_EVIDENCE_ACCOUNTING.md`、`data/release_manifest.json` 和 CLI status。
2. 检查两个 GitHub runs 的最终状态。
3. 导入并审计新的普通模型轨迹。
4. 实现 model-evidence registry 和回归测试。
5. 更新准确的模型覆盖数字和过时叙述文档。
6. 启动下一批公共 hard 普通模型测试，优先 multiwarehouse、sales-return r1、Kubernetes dev-006。
7. 在不消耗 frozen hidden 的前提下，继续把三个 hard candidates 晋升为正式 public slots。

验收：新会话应能回答“有多少题通过 hard admission、多少进入正式发布、多少被普通强模型实际跑过、各自结果是什么”，并且每个数字都能由 registry/manifest/轨迹哈希复算。

## 16. 关键文件索引

- `README.md`：项目入口，但部分阶段数字可能过时。
- `docs/BENCHMARK_SPEC.md`：研究问题、hard gate、指标；Current release boundary 需同步。
- `docs/MODEL_EVIDENCE_ACCOUNTING.md`：当前最重要的模型证据口径。
- `docs/HARD_TASK_CONSTRUCTION.md`：困难题构造经验。
- `docs/DIRECTIONAL_HARDNESS.md`：恢复方向难度。
- `docs/BOUNDARY_RELATIVE_RECOVERY_INTEGRITY.md`：边界相对恢复完整性。
- `docs/ROADMAP.md`：研究阶段演化；末尾状态数字较旧。
- `data/benchmark_matrix.json`：183-case 目标矩阵。
- `data/release_manifest.json`：正式 public binding 和七角色证据。
- `data/frozen_hidden_candidates.json`：冻结 hidden candidate registry。
- `data/hidden_evaluation_registry.json`：已消费/作废的历史 hidden lifecycle。
- `data/scenarios/`：活动可执行 scenarios。
- `data/evidence/`：模型、控制、正式和隐藏生命周期证据。
- `.github/workflows/`：native build/replay/model/evidence-import 流水线。

## 17. 密钥和运行安全

- 聊天历史中曾出现多个 provider API key；本交接不复制任何密钥。
- 密钥只通过 GitHub Secrets/本地环境变量注入，不写入仓库、轨迹、命令输出或交接文档。
- 当前 GLM 工作流使用仓库 secret（历史命名包括 `ZHIPU_CODING_API_KEY`）；新 provider 采用同样方式。
- 导入轨迹前检查凭证清理步骤和日志脱敏。

## 18. 一句话版本

> AftermathBench 评测的是：当真实系统中的写操作报错且提交结果不确定时，Agent 能否从分散的原生证据中重建边界状态，选择随边界变化的正确恢复范围，完整修复受影响链路，同时保护已经生效且仍有效的副作用。
