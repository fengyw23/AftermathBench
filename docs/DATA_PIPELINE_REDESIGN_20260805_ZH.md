# AftermathBench 数据来源与合成管线重构决策

日期：2026-08-05  
状态：生效，作为下一轮造题前的约束  
范围：公开开发题的数据来源、运行时选择、合成、筛选、正式化和 hidden 派生

## 一句话结论

旧管线不是“假的”，但顺序错了。它先由研究者想题，再花很大成本把题放进真实系统执行；这能证明状态真实可重放，却不能证明题来自真实需求、错误足够根本，或者强模型会被稳定区分。

下一版采用：

> **公开事故、上游 issue/PR/回归测试或官方可靠性规范提供问题种子；先证明同一可见报错下存在必须采取相反动作的真实边界，再选择最便宜且忠实的开源运行时做原生最小复现；通过人工独立审查和廉价公开模型筛选后，才做 formal packaging 和独立 hidden clone。**

ERPNext、Forgejo、Kubernetes 不再是预设的三条主线。它们只在某个高质量来源确实需要该系统、且成本和可见性合格时继续使用。

## 1. 旧管线正式存档

旧管线的准确定位是：

> **研究者设计、真实开源系统执行的合成 benchmark。**

它不是生产事故采集集，也不是从企业日志抽样得到的数据集。机器审计见 [`DATA_PROVENANCE_AUDIT_20260805_ZH.md`](DATA_PROVENANCE_AUDIT_20260805_ZH.md)：当前 21 个 active scenarios 中，0 个声明外部业务来源，0 个区分研究者编写内容与原生生成内容，0 个把生成 run、source commit 和 artifact digest 完整绑定到逐题来源。

旧工作保留，不删除、不改名冒充新数据：

- 三个固定版本开源运行时、reset/snapshot、故障注入、reference recovery、确定性 evaluator、证据哈希、hidden freeze 和 model-evidence registry 继续作为工程资产；
- 现有 public/formal/historical 题按当前 registry 原样保留，可作为回归测试、正控制、工具审计和方法演示；
- 已被模型看过的 development 数据永远不改名为 hidden；已冻结 hidden 数据在本次重构中不读取、不消费；
- 94 个 hard-admitted states 与 89 个 occupied target-slot states 仍是不同集合；94 个 states 也不是 94 道独立题；
- 当前 4 个 formal public slots 的 29/29 是 execution control，不是普通模型实验；机器 registry 认证的 current-formal ordinary count 仍为 0。

旧管线失败在以下位置：

1. **来源在最后补，而不是在最前面筛。** 研究者先决定答案和 fixture，之后再证明 fixture 能运行，无法排除“先定答案、再造支持答案的世界”。
2. **把可重放当成有区分度。** hard admission 证明 reference 能过、固定策略不能整组通过，不证明强模型会在核心恢复推理上失败。
3. **把状态数当成题量。** 大量 matched states 共享同一故事、运行时和故障机制，统计上高度相关。
4. **把工程复杂度当成认知难度。** 图更深、轨迹更长、CI 更多，仍可能只是逐项补洞；强模型可以轻易解决。
5. **失败后才审计 evaluator。** 部分所谓模型错误最终是 metadata 精确匹配、工具可见性、终止格式或 benchmark 私有合同问题。
6. **运行时先于研究问题。** 因为已搭好 ERPNext、Forgejo、Kubernetes，就不断在其中寻找题，而不是让真实故障来源决定应使用什么系统。
7. **过早投入昂贵包装。** 在反事实动作冲突和强模型区分度尚未成立时，就投入 native replay、七角色证据、CI、formal binding 和 hidden freeze。

具体案例质量教训见 [`CASE_QUALITY_DOCTRINE_20260805_ZH.md`](CASE_QUALITY_DOCTRINE_20260805_ZH.md)，真实轨迹复盘见 [`ADVISOR_CASE_DOSSIER_20260805_ZH.md`](ADVISOR_CASE_DOSSIER_20260805_ZH.md)。

## 2. 外部调研告诉了我们什么

### 2.1 顶会 benchmark 不是“自动抓取后跑通”

[Datasheets for Datasets](https://arxiv.org/abs/1803.09010) 要求记录数据的动机、组成、采集过程、建议用途和限制。对本项目而言，这意味着每题必须回答“原始事件来自哪里、研究者改了什么、系统自己生成了什么、为什么这些参数合理”，不能只给 runtime hash。

[SWE-bench](https://arxiv.org/abs/2310.06770) 的关键优点是把 2,294 个真实 GitHub issue 与对应 PR、代码版本和测试联系起来，而不是研究者凭空写题。但这条来源链本身仍不够。[SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/) 由 93 名有经验的软件开发者审查 1,699 个样本，每题由 3 人独立标注并取最严重判断；最终 68.3% 因题意不充分、测试会误杀正确答案或其他问题被过滤。其中 38.3% 被标为题意不充分，61.1% 的测试可能不公平拒绝有效解。

这对 AftermathBench 的直接含义是：

- “来自真实 issue”只是来源门，不是质量终点；
- evaluator 必须允许所有真正满足完整性约束的终态，不能只认作者的操作序列；
- 环境必须容器化、固定版本、可重复建立；
- 至少要有独立人工复核，而不能由同一个人设计题、写 reference、写 scorer 后自证正确。

[SWE-bench-Live](https://arxiv.org/abs/2505.23419) 进一步用持续更新的近期 issue、自动构建和逐题 Docker 镜像降低静态 benchmark 的污染和人工瓶颈。这支持我们采用“滚动来源窗口 + 自动采集 + 冻结发布批次”，而不是把一批公开开发题长期反复调优。

### 2.2 真实环境有价值，但必须测对能力

[WebArena](https://arxiv.org/abs/2307.13854) 使用功能完整、可复现的网站并按功能终态评分，动机正是避免简化合成网页与真实任务脱节。[OSWorld](https://arxiv.org/abs/2404.07972) 给每题提供初始状态配置和执行式 evaluator；369 个任务来自真实电脑使用案例。[WorkArena](https://arxiv.org/abs/2403.07718) 使用 ServiceNow 企业环境。[tau-bench](https://arxiv.org/abs/2406.12045) 用最终数据库状态评分，并用 `pass^k` 测多次执行的一致性。

这些工作支持保留“真实环境 + 初始状态 + 执行式评分”，但也给出三个警告：

- 全 GUI 环境会把 GUI grounding 和操作知识混入结果，不适合本项目作为核心变量；
- 远程托管或闭源平台会增加复现和许可风险；
- LLM 用户模拟器带来随机性，适合扩展实验，不适合作为主判分依据。

因此本项目应继续使用普通 CLI/API/查询工具和确定性终态评分，不转成 GUI benchmark，也不把 LLM judge 或 LLM 用户模拟器放进核心闭环。

### 2.3 “不确定是否写成功”在真实系统中确实是根本问题

这条研究问题不是人为编造出来的，多个生产系统的官方材料都明确描述了它：

- [AWS Builders' Library](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/) 直接给出网络超时后不知道 singleton EC2 workload 是否已创建的两难：直接重试可能产生两个实例，不重试可能什么都没有；AWS 用 caller-provided request identifier、可审计日志和语义等价响应处理。
- [Stripe idempotent requests](https://docs.stripe.com/api/idempotent_requests) 明确说明连接错误后应使用同一 idempotency key 安全重试，并返回第一次请求的同一结果；这正对应“写成功但响应丢失”。
- [Temporal Activity 文档](https://docs.temporal.io/activity-definition) 说明 Activity 可能执行多次：业务函数已经成功，但 worker 在向 Temporal Service 报告前崩溃，Event History 不记录成功，Activity 会重试；非幂等 Activity 可造成重复扣款。
- [Kafka delivery semantics](https://kafka.apache.org/documentation/#semantics) 说明发送方未收到确认时只能重发，而第一次请求可能已成功，因此默认至少一次语义可产生重复；事务 producer 和 read-committed consumer 才能把输出与 offset 原子绑定。
- [RabbitMQ confirms](https://www.rabbitmq.com/docs/confirms) 明确把 publisher confirm 和 consumer acknowledgement 定义为数据安全机制，并要求消费者为 redelivery 做幂等处理。
- [PostgreSQL libpq status](https://www.postgresql.org/docs/current/libpq-status.html) 在连接损坏时报告 `PQTRANS_UNKNOWN`，说明断链后不能把客户端观察到的错误直接当作服务端未提交。

这些来源比“研究者觉得某个 ERP 流程应该这样恢复”更有说服力。它们还天然给出可见证据面：idempotency key、Event History、producer transaction、consumer offset、delivery tag/redelivery flag、数据库事务和审计日志。

### 2.4 事故报告适合提供故事和后果，但通常不能单独生成题

[Google SRE 的 postmortem 指南](https://sre.google/sre-book/postmortem-culture/) 把 postmortem 定义为事故、影响、缓解动作、根因和后续行动的书面记录，并要求正式评审。公开 postmortem 因此适合证明“这个问题发生过、后果为什么重要、运维人员当时掌握什么信息”。

但多数公开 postmortem 不包含可运行快照、完整日志、精确版本和反事实边界，单靠文章很难做确定性复现。最佳用法是把 postmortem 与官方语义、上游 issue/PR/回归测试三角互证，而不是把文章改写成一个作者自拟 fixture。

### 2.5 公开不等于可以任意再发布

[GitHub 的许可说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository) 明确指出：没有许可证时默认版权仍然适用，公开仓库只自动赋予查看和 fork 权利，并不自动允许复制、分发或制作衍生作品。

所以来源门必须检查许可证。优先选择 OSI 许可的代码和测试；issue/postmortem 只保存必要短引文、URL、作者/日期和我们自己的结构化摘要。若许可不清，发布可重建脚本和上游标识，不把全文或大段日志重新打包进数据集。

## 3. 数据来源比较

下表的“最好用途”比总分更重要。没有一种来源能单独满足所有要求。

| 来源 | 真实性 | 能否自动重放 | 能否直接支持本课题 | 主要风险 | 最好用途 |
|---|---|---|---|---|---|
| 上游 issue + 修复 PR + 回归测试 | 高 | 高 | 中到高，需筛出恢复类问题 | issue 仍可能写得不清；测试可能过窄；污染 | **核心首选种子** |
| 官方可靠性文档 + 官方示例/测试 | 高 | 高 | 高，尤其是幂等、重试、事务 | 可能是规范示例而非真实事故 | **核心首选种子/语义依据** |
| 公开 postmortem | 很高 | 低 | 高 | 状态和日志不完整，难精确复现 | 后果与参数校准，需三角互证 |
| 公开运维 trace/log 数据集 | 中到高 | 低到中 | 低到中 | 常缺用户目标、正确动作和反事实 | 参数分布、噪声和时间尺度校准 |
| 专家访谈重构 | 高 | 中 | 高 | 成本高、不可公开细节、主观偏差 | 独立审查和现实性验证 |
| 企业真实日志 | 很高 | 低 | 高 | 隐私、商业秘密、许可、难发布 | 只做外部有效性/参数校准 |
| 研究者从零设计 | 低到中 | 高 | 可以定向设计 | 最大的“先定答案再造世界”风险 | 仅作方法原型或正控制 |
| LLM 自动生成故事/题目 | 低 | 高 | 表面相关 | 事实幻觉、模板重复、模型自测偏差 | 只作 fuzz/stress 候选，不进核心集 |

最终选择不是单一来源，而是**三角来源**：

1. `incident_or_issue`：证明问题真实出现过，或至少由上游用户/维护者提出；
2. `normative_semantics`：官方文档、协议规范或维护者确认，证明正确语义不是 benchmark 作者发明；
3. `executable_witness`：回归测试、最小 reproducer 或官方 sample，证明边界可以运行并自动判断。

三者齐全为 A 级来源；缺少事故但有官方语义和可执行 witness 为 B 级，可进入公开开发集但不能单独支撑“生产事故代表性”；只有研究者故事和原生执行为 C 级，只保留为控制/原型。

## 4. 运行时不再预先固定

运行时必须由幸存来源决定。当前候选的实际判断如下：

| 系统族 | 为什么适合 | 主要问题 | 建议 |
|---|---|---|---|
| Temporal/Cadence 类工作流 | Event History、Activity retry、worker crash 和幂等语义天然匹配；查询面清楚 | 外部业务副作用仍需一个真实系统承载；搭建成本中等 | **第一优先 pilot** |
| RabbitMQ + 一个有持久状态的开源服务 | 单机/容器便宜；confirm、ack、redelivery 很容易制造真实边界 | 单独“重复消息”后果不够，需要来源支持的下游业务不变量 | **低成本批量筛选 pilot** |
| Kafka/Redpanda + 状态存储 | producer transaction、offset、read-committed 提供强原生不变量；适合重复/丢失/部分可见 | 环境和概念更重；易测成 Kafka 配置知识 | **跨系统验证 pilot** |
| PostgreSQL/MySQL/CockroachDB | reset 快、SQL 证据透明、事务边界确定性高 | 单数据库提交后通常一次查询即可确认，可能太容易；跨系统才产生强冲突 | 作为共同状态底座，不单独押注 |
| GitHub/GitLab/Forgejo | issue、PR、job、release、webhook 来源丰富，审计记录好 | 旧题已证明 metadata 和 webhook 重放容易变成局部错误 | 有高质量 issue/test 来源时再用 |
| ERPNext/Odoo 等业务系统 | 后果直观，库存/账本/履约是真实业务状态 | reset 慢、fixture 重、业务来源难证明、每题成本高 | 暂停扩张；只做少量来源充分的题 |
| Kubernetes | 控制器、resourceVersion、Job 等状态可查 | 很容易把 benchmark 自写 ConfigMap 合同包装成 Kubernetes 原生语义 | 不作默认主线；只接受纯原生上游事故种子 |
| 云厂商真实 API | 现实性最高，官方 postmortem 丰富 | 费用、凭证、限流、外部漂移、不可离线复现 | 只作来源/外部验证，不作发布运行时 |

这里的关键不是宣布 Temporal 永远最好，而是 pilot 阶段它最容易把“官方语义、可见历史、真实重试、相反安全动作”同时放进一个可复现环境。若首轮来源审计发现 RabbitMQ/Kafka 的 issue+test 种子更强，就应让来源结果改变系统排序。

## 5. 推荐的最终管线

### 阶段 A：只做来源卡，不搭环境

从 Temporal、RabbitMQ、Kafka、PostgreSQL/CockroachDB、GitHub/GitLab 以及支付幂等资料中搜集候选。每个候选先写一张不超过两页的 `source card`：

- 上游 URL、issue/PR/test ID、作者、日期、产品版本和许可证；
- 原始事故或规范到底说了什么，哪些内容没有说；
- 同一句模型可见错误；
- 至少两个真实可能的写入边界；
- A 状态必须做而 B 状态禁止做的动作；
- 反用动作造成的原生损害；
- 模型可用普通工具看到的决定性证据；
- 哪些参数来自来源，哪些必须由研究者补充。

以下任一项不清楚，立即拒绝，不进入环境工程：

- 只有“系统很复杂”，没有相反动作；
- 错误后果只是 label、格式、描述或 benchmark 审计字段；
- 正确答案依赖模型看不到的事实；
- 来源没有许可证/引用边界；
- 需要作者自写大量合同才能让错误显得重要；
- 把一种状态的正确方案用于另一状态不会造成可见损害。

### 阶段 B：三角互证和独立评审

每张来源卡至少由两名不参与实现的人独立判断：

1. 这是恢复推理问题，还是工具/配置/知识问答？
2. 相反动作是否真的由来源和产品语义支持？
3. 后果是否足够重要且可由原生状态检查？
4. 输入信息是否足够让一个认真调查的模型做对？

分歧不靠作者解释强行通过；补来源或淘汰。目标不是提高通过率，而是尽早拒绝弱题。

### 阶段 C：原生最小复现

只为通过 A/B 的候选选择最便宜运行时：

1. 固定上游源码/镜像 revision；
2. 运行来源中的 regression test/sample，或把公开 reproducer 缩成最小环境；
3. 在真实请求的确认边界注入断链/worker crash/ack 丢失，不手填“已提交/未提交”答案；
4. 让系统自己生成 Event History、transaction、offset、delivery 或 ledger 证据；
5. 捕获 commit-before-loss、loss-before-commit 等 matched boundaries；
6. 证明把 A 的完整恢复用于 B、把 B 的恢复用于 A 都会破坏原生不变量；
7. evaluator 只看业务/系统终态和事件历史，不看作者偏好的命令序列。

### 阶段 D：便宜筛选，再昂贵封装

顺序固定为：

1. reference 100%；
2. counterfactual inversion 100%；
3. 一个简单固定策略不能整组解决；
4. 一个较便宜普通模型在公开开发实例上完整运行，检查错误是否真来自调查/边界重建/安全动作；
5. 一个强模型做少量确认；若强模型稳定通过，降为正控制，不继续包装成 hard；
6. 只有出现稳定、实质且公平的能力缺陷，才生成 formal evidence、独立参数实例和 frozen hidden clone。

这一步直接修正过去的成本结构：大多数候选应在几十分钟的来源卡和反事实审查阶段死亡，而不是在数天 CI 与数亿 token 后死亡。

### 阶段 E：独立派生 public 与 hidden

同一个生成器可共享机制，但 public 和 hidden 必须使用不同来源记录或独立参数抽样，并在任何模型调用前冻结：

- 来源集合按 incident/issue ID 分组，不能把同一 issue 的边界拆到 train/test；
- 按 failure mechanism 和上游项目分组切分，避免近重复泄漏；
- public 开发实例可迭代，hidden 实例一次冻结、一次消费；
- 每个发布批次记录截止日期；后续用滚动新 issue 建新批次，降低污染；
- hidden 的 evaluator salt、instance hash、source hash 和 artifact digest 在模型调用前承诺。

## 6. 每题必须机器记录的来源字段

后续 schema 至少需要：

```json
{
  "dataset_kind": "incident-seeded-native-executed-synthetic",
  "source": {
    "incident_or_issue": [{"url": "...", "id": "...", "date": "..."}],
    "normative_semantics": [{"url": "...", "section": "..."}],
    "executable_witness": [{"repo": "...", "revision": "...", "path": "...", "sha256": "..."}],
    "license": {"spdx": "...", "redistribution_review": "pass"},
    "source_tier": "A"
  },
  "authorship": {
    "source_derived": ["failure_mechanism", "required_invariants"],
    "researcher_authored": ["names", "small_scale_parameters"],
    "native_generated": ["event_history", "transactions", "deliveries"]
  },
  "counterfactual": {
    "shared_observation": "...",
    "boundary_a": "...",
    "boundary_b": "...",
    "action_required_in_a_forbidden_in_b": "...",
    "native_harm_a_to_b": "...",
    "native_harm_b_to_a": "..."
  },
  "generation": {
    "builder": "...",
    "workflow": "...",
    "source_commit": "...",
    "run_id": "...",
    "artifact_sha256": "..."
  }
}
```

`source_tier`、许可证、三角来源、作者/原生分工、counterfactual inversion 和 generation closure 任一缺失，都不能进入正式发布。

## 7. Pilot：先证明这条管线比旧管线好

首轮不是再造 30 个 formal slots，而是做一个有明确淘汰率和成本记录的 pilot：

1. 搜集至少 40 张原始来源卡，覆盖至少 5 个系统族；
2. 只让 12 张左右进入独立评审；预期大部分因没有相反动作或缺可执行 witness 被拒绝；
3. 只实现最强的 6 个最小 reproducer，覆盖 Temporal、轻量消息系统、事务/流系统至少 3 类；
4. 每个 reproducer 最多先做 2 个关键 matched boundaries，不用状态变体虚增数量；
5. 先跑便宜公开模型，再对仍有区分度的少量题跑强模型；
6. 只有至少 3 个来自不同 failure mechanism 的题通过全部 gate，才恢复 formal/hidden 生产。

Pilot 成功不是“造出多少 states”，而是同时满足：

- 每个幸存题都有 A/B 级外部来源；
- 两名独立审查者认可题意和评分；
- 错误动作造成来源支持的原生损害；
- 决定性证据普通可见；
- 强模型失败能从真实轨迹解释为恢复推理缺陷，而非接口或 evaluator 缺陷；
- 单个候选从来源卡到筛选结论的中位成本显著低于旧管线；
- 报告 source cards 数、独立 failure mechanisms 数和最终 survivors，不再用 matched states 冒充独立题量。

## 8. 主方案、备选方案和明确放弃项

**主方案：来源优先的多运行时管线。** 以上游 issue/PR/test 和官方可靠性规范为主种子，postmortem 提供影响与参数校准，运行时跟随来源。首个工程 pilot 优先 Temporal，再用 RabbitMQ 和 Kafka/数据库做跨机制复现。

**备选方案：官方规范/示例驱动。** 若高质量 issue 的可执行 witness 产量太低，就用 AWS/Stripe/Temporal/Kafka/RabbitMQ 官方规范定义机制，再在可开源运行时中复现；这类题必须诚实标为 `specification-seeded`，不能写成采集到的生产事故。

明确放弃以下做法作为核心数据来源：

- 先固定 ERPNext/Forgejo/Kubernetes，再为填矩阵寻找故事；
- 纯 LLM 生成题；
- 只有公开 trace、没有目标和反事实的自动转题；
- 用企业私有日志直接组成不可发布主榜；
- 以更多实体、更多状态、更长轨迹或更苛刻轮次制造 hard；
- 在普通强模型区分度未确认前做大规模 formal/hidden 包装。

## 9. 当前立即生效的执行决定

1. 旧三域扩张顺序暂停，现有数据和收据只归档、不删除。
2. 本次研究不读取或消费 frozen hidden，不调用模型。
3. 在来源 pilot 完成前，不新建 ERPNext、Forgejo、Kubernetes 的大规模题族。
4. 下一次实现应先建立 `source card` schema、validator 和候选来源清单，然后做 40 -> 12 -> 6 的漏斗。
5. 任何系统都可进入，也可被淘汰；系统名不再是矩阵完整性的依据，独立且有来源的 failure mechanism 才是。

这不是否定已有 80 小时工程，而是把其中真正可复用的 native replay、reset、evaluator、evidence binding 和 hidden governance 留下来，把造成低产出的“研究者先造故事、最后才问真实性和模型区分度”替换掉。
