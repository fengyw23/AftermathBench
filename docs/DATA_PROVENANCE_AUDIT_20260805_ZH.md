# AftermathBench 数据来源与合成管线审计

## 结论

当前数据合成管线只能评价为**部分可靠**。

说得更直白一些：仓库较有力地证明了“研究者设计的任务确实在固定版本的 ERPNext、Forgejo 和 Kubernetes 中执行，并产生了可回放的真实系统状态”；但还不能证明“这些业务任务和参数来自现实事件、公开资料或系统使用统计”。因此，AftermathBench 目前应被准确称为：

> 研究者设计、原生系统执行的合成 benchmark，而不是生产事故采集集，也不是从真实企业日志抽样得到的数据集。

这个定位本身可以成立。真正的问题不是“用了合成数据”，而是仓库目前没有逐题公开说明哪些内容由研究者设计、哪些内容由原生系统生成、参数为什么合理、具体由哪个脚本和哪次运行生成。

## 机器审计结果

以下数字由 `scripts/audit_data_lineage.py` 从活动场景、运行时清单和公开证据重新计算，不读取 frozen hidden 数据。

| 检查内容 | 当前结果 | 大白话解释 |
|---|---:|---|
| 活动运行时 | 3/3 来源和版本可核验 | ERPNext、Forgejo、Kubernetes 都固定了上游仓库和 revision，并有运行准入证据。 |
| 活动场景 | 21 个，110 个 matched states | 这是仓库当前实际实现量，不等于正式发布量。 |
| 当前 1.0 场景格式 | 19/21 | 两个早期 easy 场景仍使用 0.x 格式。 |
| 找得到内部 blueprint | 18/21 | 大部分场景能追到仓库内的设计蓝图，但蓝图本身仍是研究者写的。 |
| 原生回放链完整且严格可读 | 18/21 | 18 个场景同时具备运行时准入、reference、replay 和一致身份；另外三个有明确缺口。 |
| hard admission 报告通过 | 17/21 | 与当前 17 个 hard-admitted scenarios 一致；这只证明构造和回放，不证明现实性或模型区分度。 |
| 实例规格哈希 | 9/21 | 只有 9 个场景把实例规格哈希写进场景，且并非所有证据层都统一传播。 |
| 业务来源说明 | 0/21 | 没有场景声明业务模板来自事故、文档、专家访谈还是研究者自拟。 |
| 作者/原生数据分工说明 | 0/21 | 没有逐题区分 fixture、目标、参数、原生记录和 benchmark 扩展分别是谁生成的。 |
| 生成脚本和 workflow 绑定 | 0/21 | 脚本和 workflow 客观存在，但 scenario 没有机器可读地指向它们。 |
| 生成 run、commit、artifact 绑定 | 0/21 | 运行证据散落在 manifest、workflow 和文档中，没有逐题闭环。 |
| 参数来源说明 | 0/21 | 数量、价格、版本、拓扑等参数没有现实分布或专家依据。 |
| 达到完整论文级 lineage | 0/21 | 因此不能声称当前每题具有完整的数据来源链。 |

机器报告保存在 `data/data_lineage_audit.json`。审计器明确把“原生执行可靠性”和“场景语义来源可靠性”分开，前者通过不能覆盖后者缺失。

## 数据到底由什么组成

### 第一层：真实开源运行时

这一层是目前最扎实的。

- ERPNext 使用 `frappe/frappe_docker@412de117...`、`frappe/erpnext@b9c9b76...`、`frappe/frappe@c1afa13...` 和 Toxiproxy `v2.12.0`。出处：`data/runtimes/erpnext-v15/runtime.json`。
- Forgejo 使用 `codeberg.org/forgejo/forgejo@fbafae6...`。出处：`data/runtimes/forgejo-main/runtime.json`。
- Kubernetes 使用 kind `9a205e8...` 和 Kubernetes `f28b4c9...`（v1.34.0）。出处：`data/runtimes/kubernetes-v1.34/runtime.json`。

三份 runtime manifest 都声明并通过源码可得、固定版本、确定性 reset、故障边界回放和终态检查。这里可以说：状态不是手写成 JSON 后假装来自真实系统，而是由真实产品 API、数据库、控制器、队列或 Webhook 执行产生。

但这只能证明“执行载体是真实系统”，不能证明“任务故事来自真实事故”。

### 第二层：研究者设计的任务

这一层包括：用户目标、产品名、数量、价格、版本号、依赖拓扑、故障注入位置、matched variants 和期望恢复方向。

例如 ERPNext manufacturing 中的 12 台设备、9 台已验收、3 台返工、具体物料和估值；Forgejo publication 中的仓库名、三个发布文件和两个 Webhook consumer；Kubernetes interaction 中的 schema epoch、两个 consumer、bridge、credential 和 publication contract，都是 benchmark fixture 的一部分。

仓库没有证据表明这些值是从生产日志、公开事故报告、行业统计或专家访谈抽样而来。它们应当被诚实标注为 researcher-authored，不应笼统称为“真实数据”。

### 第三层：原生系统生成的证据

研究者设计 fixture 后，流水线使用真实工具建立前序状态、注入故障边界，再采集文档、库存、账本、队列、Release、Webhook delivery、Kubernetes object 和外部 receiver/registry 记录。reference recovery 和确定性 evaluator 也在这些状态上运行。

因此，第三层不是研究者直接填写的答案表；它是由真实系统执行生成的合成证据。准确说法是“native-generated evidence”。

## 三条完整链路抽查

### ERPNext manufacturing

设计蓝图在 `data/scenario_blueprints/erpnext-manufacturing-rework-public-dev-002/scenario.json`。它先由 `scripts/render_erpnext_native_blueprint.py` 绑定实例，再由 `scripts/build_erpnext_manufacturing_prefix.py` 通过 ERPNext API 建立 Work Order、Job Card、Quality Inspection、Stock Entry 和相关账本状态。

`.github/workflows/erpnext-manufacturing-public-dev.yml` 会重置运行时，逐个制造四种失败边界，调用 `scripts/capture_erpnext_manufacturing_state_evidence.py` 采集原生状态，运行 reference recovery、固定基线和 admission builder，最后形成 `data/scenarios/erpnext-manufacturing-rework-public-dev-002/`。

场景、prefix 和实例规格使用同一个 `instance_spec_sha256=2a7683af...`。这条链证明实例身份和原生执行较强。但 blueprint 仍未说明医疗设备名称、12/9/3 数量和估值的外部来源，也没有在 scenario 中绑定 workflow run 和 artifact digest。

### Forgejo release publication

设计蓝图在 `data/scenario_blueprints/public-dev-slot-002/scenario.json`。`.github/workflows/forgejo-publication-public-dev.yml` 构建 Forgejo，调用 `scripts/build_forgejo_publication_prefix.py` 建立仓库、PR、issue、release branch、manifest 和 Webhook，再逐边界采集 native delivery 和外部 receiver 状态，运行 reference、基线、control 和 formal evidence builder。

正式公开实例 `forgejo-release-publication-public-dev-002-r1` 的 scenario、prefix、reference 和 replay 都传播了同一个实例哈希 `c060b3f5...`，是三条抽查链中身份绑定较完整的一条。

但历史活动副本 `forgejo-release-publication-dev-002/artifacts/prefix.json` 顶层重复出现 `scenario_id`。宽松 `json.load` 会静默接受，严格解析会拒绝。现有 native admission 使用宽松解析，所以旧 gate 没发现这个问题。审计器将该场景标为 `artifact_not_strict_json`，不改写旧证据，也不把它算作严格完整链。

### Kubernetes constraint interaction

设计蓝图在 `data/scenario_blueprints/public-dev-slot-003/scenario.json`。`.github/workflows/kubernetes-interaction-public-dev-instance.yml` 先验证参数化实例；`.github/workflows/kubernetes-interaction-public-dev-admission.yml` 在 kind/Kubernetes 中制造 13 个边界，调用 `scripts/capture_kubernetes_interaction_state_evidence.py` 采集对象、控制器和 registry 状态，再由 `scripts/build_kubernetes_interaction_admission.py` 生成场景证据。

这里的 Deployment、Service、Secret、Job、RBAC 等是 Kubernetes 原生对象；但 catalog、bridge、change record、recovery audit 等 ConfigMap 合约以及外部 registry 语义是 benchmark 设计的应用层协议，不是 Kubernetes 产品原生提供的业务含义。若不逐项标注，容易把“存储在 Kubernetes 里”误写成“Kubernetes 原生语义”。

此外，场景声明了实例哈希 `bc5159a9...`，但活动 prefix/reference/replay 没有统一携带该哈希，因此身份传播仍不完整。

## 当前可以说什么

可以说：

- benchmark 使用固定版本、可审计的真实开源系统；
- hard 场景的前序状态、故障边界、reference recovery 和终态是通过原生执行与回放建立的；
- 17 个场景通过了现有 hard admission，94 个 hard states 是构造准入量；
- 数据是研究者设计、原生执行的合成数据。

现在不能说：

- 数据来自真实生产事故或真实企业日志；
- 任务参数代表现实世界分布；
- 每个场景都能从 scenario 一步追到唯一的 builder、workflow、commit、run 和 artifact；
- replay-admitted 就等于现实有效、无噪声或具有模型区分度；
- Kubernetes 中所有合约字段都是 Kubernetes 自身的原生业务语义。

## 为什么目前仍可能被攻击为低质量或有噪声

最强的攻击点不是“状态有没有真的执行”，而是“为什么要执行这套业务，为什么是这些数字和约束”。当前仓库无法机器回答这两个问题。

另一个攻击点是作者可以先设计恢复答案，再构造恰好支持该答案的 fixture。matched replay、reference 通过和固定策略失败都不能排除这种风险。要降低风险，必须为每个家族提供独立的业务来源或专家依据，并明确哪些约束是产品原生不变量，哪些只是 benchmark-authored application contract。

最后，严格 JSON 重复键问题说明现有 validator 主要关注任务准入，没有形成统一的数据卫生门。只要不同验证器使用不同解析规则，就可能出现“CI 绿色但证据文件不唯一解释”的情况。

## 可靠管线应补齐的最小字段

每个活动 scenario 后续应有一个 `data_provenance` 声明，至少包含：

- `dataset_kind`：固定写明 `researcher-designed-native-executed-synthetic`；
- `business_basis`：来源类型、引用和为什么能支持这个任务；若完全自拟，也要明确写出；
- `authorship`：分别列出 researcher-authored 和 native-generated 字段/证据；
- `benchmark_authored_extensions`：显式列出外部 registry、contract ConfigMap 等扩展，可以为空但不能省略；
- `parameter_sources`：数量、金额、版本和拓扑的来源或合理性依据；
- `generator`：builder paths 和 workflow path；
- `generation_run`：run id、source commit 和 artifact SHA-256。

在这些字段补齐并由审计器通过前，论文数据卡应保留“semantic provenance incomplete”的限制说明。

## 复现命令

```powershell
$env:PYTHONPATH = "src"
python scripts/audit_data_lineage.py --output data/data_lineage_audit.json
python -m unittest discover -s tests -p "test_data_lineage.py" -v
```

该审计只读取 `data/scenarios/`、`data/scenario_blueprints/`、`data/runtimes/` 及其公开证据，不读取、解封或消费 frozen hidden instances，也不调用任何模型。
