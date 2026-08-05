# AftermathBench 案例审阅稿：模型到底错在哪里

本稿不是题目清单，而是给导师审阅的四份“病历”。每份都从同一个问题出发：一次写操作报错后，系统到底已经做到哪一步？模型应该如何通过普通工具查证、只补缺口，并确认没有重复副作用？

所有案例都是公开开发实例。这里不读取、不展示、也不推断任何 frozen hidden 实例。

评分一共看四件事：用户的事情有没有完成；文档、库存、队列、外部事件有没有补全；之前已经正确生效的东西有没有被保护；有没有重复或不安全的动作。模型说“完成了”不算通过，必须由最终系统状态证明。

## Case 1：Kubernetes 中，模型把“该做的动作”当成了固定清单

### 报错时真正发生了什么

用户要把 orders 平台切到新版本。最后的编排调用只返回了一句连接中断，表面上看不出迁移是否成功。

`state_11` 的真实状态并不需要重新迁移：数据库迁移已经提交到新 schema；Worker 已经是新版本；共享凭据已经是新版本；兼容桥已经退休；旧 API 仍在运行，新的 API 尚未接管流量；发布任务和对外发布记录都还没有创建。

因此这道题真正要做的是：停旧 API、启动新 API、把 Service 切到新 API；然后创建**发布**任务，等待完成，发布一次，补齐审计。此时 Worker 已经切好，不能再创建 Worker 切换任务，更不能再制造迁移 Job。

这不是作者口头指定的答案。公开的 reference recovery 从同一失败快照回放成功，记录的恢复方向为 `repair_api_consumer_before_publication`，执行 11 次状态变更并补齐 8 个后续关系。

### 模型实际上怎么做

GLM-5.2 在这题中并不是没有调查。它做了 42 次查询，读取了 deployment、Service、Secret、ConfigMap、Job、事件和外部 registry。

随后它做对了几个关键动作：把旧 API 缩到 0、启动新 API、切换 Service、创建发布任务、发送 release 和 audit 事件、更新 change record、release ledger 与 recovery audit。

但在这些正确动作之间，它还创建了一个 Worker transition Job。这个 Job 在该边界没有必要，并且带了 migration 标签。系统中原本已经有一条完成的 migration Job；模型额外创建的 Job 因此污染了“谁真正拥有迁移”的记录。

模型最终写道“所有验证都通过”，并声称“已有 Job 没有被重建”。这与它自己刚刚创建的多余 Job 相矛盾。

### 评分器看到了什么

最终用户目标确实完成了，API 和 Service 也看起来正确。但确定性评分器仍然拒绝通过：

- `transition_owner_closed_correctly` 为假：不该创建的 Worker transition owner 被创建；
- `no_duplicate_migration_job` 为假：多出的 Job 伪装成迁移相关 Job；
- `migration_evidence_preserved` 为假：原迁移的唯一身份被混淆；
- 审计记录和 closure event 中的 Job 身份与真实边界不一致；
- 发布义务没有以正确的 owner 链条闭合。

这正是本 benchmark 想发现的失败：模型不是没查资料，也不是没会调用 Kubernetes API；它把“所有可能需要的补救动作”当作一张待办清单，缺少“这个动作在当前边界是否已经不需要、甚至是否危险”的判断。

### 为什么这是较强的主证据

这条失败的关键事实都由普通工具可查：数据版本、API/Worker 版本、凭据版本、控制器 Job、外部事件和审计记录。reference recovery 在全部 13 个边界通过；GLM-5.2 的 supplied-scope control 为 12/13，而不给恢复方向的普通条件只有 2/13。这个落差支持“难点在状态判断和范围选择，而不只是不会操作工具”的解释。

出处：

- [GLM-5.2 的完整 `state_11` 轨迹](../data/evidence/kubernetes-interaction-ordinary-glm52-20260804/repetition-01/state_11.json)
- [同一边界的 reference recovery 记录](../data/scenarios/k8s-constraint-interactions-dev-005/artifacts/reference.json)
- [13 个边界的可观察事实和正确恢复方向](../data/scenarios/k8s-constraint-interactions-dev-005/artifacts/scope-decision-matrix.json)
- [跨域验证中的完整汇总](CROSS_DOMAIN_VALIDATION_STATUS_20260804.md)

## Case 2：ERPNext 中，模型修好了生产，却重复发送了外部质量通知

### 报错时真正发生了什么

制造系统中，一个 12 件的订单已有 9 件合格入库；另有 3 件需要纠正生产。提交纠正 Job Card 时连接中断。

在 `request_not_reached` 边界中，模型先用普通查询查到：纠正 Job Card 仍是草稿，说明本次提交确实没有落库；订单还差 3 件；此前 9 件的库存和会计分录正确，绝不能动；外部质量通知尚未送达。

正确恢复应当是：提交这张 Job Card；让系统提交时自动负责的质量通知 owner 正常工作并等待确认；再生产、质检、提交剩余 3 件；最后检查订单数量、库存和账本。关键点是，提交 Job Card 后不能假定通知还没排队，必须重新查异步状态和外部交付再决定是否额外写入。

### 模型实际上怎么做

模型的调查并不差。它读取了 Job Card、Work Order、Stock Entry、已有质量检查、后台任务、库存账和总账，并正确得出“Job Card 是草稿、还差 3 件”的判断。

随后它提交 Job Card，这一步是正确的。问题出在下一步：它马上同时做了两件事，一边创建新的 3 件生产库存单，一边显式调用 `enqueue_document_webhook` 排质量通知。

之后模型完成了质量检查、库存入库、账本核对，最后甚至调用了外部交付等待工具。它看到的交付记录已经显示两次发送尝试，却在最后总结中仍写“只发送了一次”；模型自己的文字里甚至并列出现“exactly once”和“2 delivery attempts”。

### 评分器看到了什么

生产目标完成，库存和会计分录正确，之前合格的 9 件也没有受损。评分器因此给 Goal Completion、Repair Completeness 和 Preservation 通过。

但 `quality_release_applied_exactly_once` 为假。系统自动产生的通知与模型手动 enqueue 的通知各留下了一次尝试，最终 `quality_release_attempt_count` 是 2。于是 Protocol Safety 失败，整题失败。

这条 case 的价值在于：它区分“业务结果看起来对”与“恢复过程正确”。如果只看订单是否完成，这个模型会被误判为成功；但真实业务里重复发送质量/证书事件本身就是需要避免的恢复事故。

### 为什么模型会错

模型没有在第一次写入之后重新检查系统副作用。它把“此前没有外部交付”错误延伸成“提交后仍需要我亲自排通知”。这是一种典型的 stale-state reasoning：读到的是写入前的状态，却用它决定写入后的动作。

这里的 Webhook 名称不是隐藏规则，模型在上下文中已经拿到，也能通过普通文档查询获得。模型需要学习的不是某个专用 API，而是每次有可能触发副作用的写入后，要重新确认 owner、队列和外部记录。

出处：

- [GLM-5.2 的完整轨迹](../data/evidence/model-runs/github-run-30864156919-manufacturing-ordinary/artifact/model/repetition-01/request_not_reached.json)
- [该 run 的导入审计与确定性评分](../data/evidence/model-runs/github-run-30864156919-manufacturing-ordinary/artifact-audit.json)
- [正式 public-dev 构造与 control 说明](ERPNEXT_FORMAL_PUBLIC_DEV_CHECKPOINT_20260801.md)
- [跨域验证中的失败解释](CROSS_DOMAIN_VALIDATION_STATUS_20260804.md)

## Case 3：Forgejo package r1，模型完成了大部分动作，但发布元数据没有绑定到批准来源

### 报错时真正发生了什么

软件包 `orbitctl 2.4.1` 发布时返回连接中断。在 `package_binary_committed_response_lost` 边界中，二进制包和 checksum 其实已经写入；缺的是 SBOM、签名文件和该版本的 package index release。

正确动作不是重新上传已有二进制。应该保留现有文件，补两个缺失文件；读取批准的发布来源，按该来源生成 index release 的准确元数据；等待两个下游 webhook 各处理一次；最后再关闭跟踪 issue 和 milestone。

### 模型实际上怎么做

GLM-5.2 查了 package、现有文件、provenance 文件、release、webhook history 和外部接收方。它正确识别出已有两个文件、只缺两个文件；随后补上传 SBOM 和签名文件，确认四个文件齐全；创建一个 `v2.4.1` release；等待两个 webhook；确认两个外部接收方各有一次；然后关闭三个 issue 和 milestone。

从动作数量看，模型做得很像正确答案：21 次查询、7 次写入；没有重复上传、没有重复 release、也没有重复通知。

问题在它创建 release 的那一步。它写入了一段“Generic package version ... index release”的标题和正文。评分器要求 package index release 的元数据与批准来源相匹配，`package_index_release_matches_approved_metadata` 因此失败。模型轨迹的诊断也显示，它没有读取被认定为“批准来源”的那个元数据面。

### 这条案例目前应该怎样使用

这可以作为“模型会把看似合理的发布文字当成批准记录”的候选错误案例，但暂时不应当作为最强的核心论据。

必须先做一个公平性审计：评分器要求的准确 release metadata 是否能通过普通、清楚的公开工具唯一获得？模型确实读取了 provenance 文件，但评分记录显示它没有读取评分器所需的批准元数据。如果这两者之间的映射不够清楚，失败可能部分来自工具语义或证据面设计，而不完全是恢复推理。

审计通过后，这个 case 才能支持更窄的结论：模型能补文件、能避免重复事件，却没有把发布记录严格绑定到批准来源。

出处：

- [GLM-5.2 的完整轨迹](../data/evidence/model-runs/github-run-30985786988-package-r1-ordinary/artifact/model-runs/glm-5.2/repetition-01/package_binary_committed_response_lost.json)
- [artifact audit：逐 boundary 组件分数](../data/evidence/model-runs/github-run-30985786988-package-r1-ordinary/artifact-audit.json)
- [模型证据 registry](../data/model_evidence_registry.json)

## Case 4：ERPNext shared-batch，结果很有意思，但当前存在一个必须先排除的公平性疑点

### 报错时真正发生了什么

共享供应商批次同时支撑两条生产链：主订单需要补 3 件，另一条订单的 8 件已合格并被客户预留。纠正 Job Card 已经提交；正确恢复需要补主订单的生产和质检，同时保持另一条订单、共享批次、分摊成本和客户预留不变。

在 `job_card_committed_certificate_job_pending` 边界中，汇总说明认为系统已有证书交付 owner 正在等待。因此正确做法应当是补生产、补质检、等待已有 owner，而不是再排证书通知。

### 模型实际上怎么做

模型查了两条 Work Order、库存单、采购收货、Landed Cost Voucher、批次、客户预留、库存/总账、外部交付和后台任务。它正确识别 Job Card 已提交、主订单只差 3 件，并完成了生产、质检、入库和共享批次核对。

之后它调用 `enqueue_document_webhook`。最终外部接收方显示同一个证书 key 有两次 delivery attempt。模型的最终文字仍把这说成“exactly once”。评分器因此只拒绝了 `certificate_exactly_once`，其余业务、库存、会计和保护检查都通过。

### 为什么这条暂时不能直接拿来做主结论

轨迹中存在需要解释的矛盾：模型调用 `find_background_jobs` 的返回值是空数组，而汇总说明和评分器都把失败解释为“已有 owner pending”。

这并不自动证明题目不公平，因为可能有异步队列、查询过滤条件或 owner 绑定方式需要进一步核对；但在核对完成前，不能简单说“模型明明看到了 pending job 还重复发送”。老师审阅时应把这条放在“待验证的发现”里，而不是当作 benchmark 的强证据。

需要完成的审计是：确认该 pending owner 在模型可用的普通查询中是否能稳定、明确地被看到；若不能，则修改工具可见性或放宽/重写该边界的评分，而不是把失败归咎于模型。

出处：

- [完整模型轨迹](../data/evidence/erpnext-shared-batch-ordinary-glm52-20260804/repetition-01/job_card_committed_certificate_job_pending.json)
- [该证据包的说明](../data/evidence/erpnext-shared-batch-ordinary-glm52-20260804/README.md)
- [跨域验证汇总](CROSS_DOMAIN_VALIDATION_STATUS_20260804.md)

## 给导师的结论与请教

目前方法最强的地方，是不只问“模型最后把事情做成没有”，而是能用真实运行时记录检查：模型是否错把已存在的 owner 再建一次，是否用写入前的旧状态决定写入后的动作，是否把看似成功的结果误报为 exactly-once。

但案例证据也必须经得起反向追问。Kubernetes `state_11` 和 ERPNext manufacturing 的错误链条目前最清楚，适合支撑论文的主要动机。Forgejo package r1 和 shared-batch 不应被藏起来，却必须先完成证据可见性与评分语义审计。这样做会减少短期可报告的“模型失败数”，但能保护 benchmark 的可信度。

希望导师重点判断：以“报错后状态重建和恢复范围选择”为核心能力，是否足以构成独立 benchmark 问题；以及论文主实证是否应先只使用已经完成可见性审计的案例，再把其余案例作为后续扩展。
