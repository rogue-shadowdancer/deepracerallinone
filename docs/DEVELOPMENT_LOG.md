# DeepRacer All In One 开发日志

本文档按父仓库已进入 Git 历史的里程碑记录“完成内容、可复核证据和仍未完成的真实环境工作”。它不是版本发布说明，也不为尚未执行的 AWS 部署、账号写入、实体车分发或赛事验收背书。当前可重复操作以[使用与开发手册](USAGE_AND_DEVELOPMENT.md)为准。

## 阅读规则

- **父仓库提交**固定本仓库文档、工具、Model Gateway 和 submodule gitlink；Training Admin 的实际网站/Lambda/CDK 改动位于 `training-code/deepracer-on-aws` 固定提交中。
- **自动化证据**只证明对应候选满足测试和构建约束。Mock HTTP、Fake Console、Fake SSH 和 AWS 客户端 mock 都不是真实系统验收。
- **现场状态**只有在真实 AWS、真实账号、真实车辆和实际网络上留存可审计结果后才能从“待验收”改为“已验收”。
- 测试数量只记录已合并 PR 中可复核的结果；早期里程碑没有稳定计数时，仅记录测试类别。

## 里程碑总览

| 日期 | 里程碑 | 父仓库证据 | 真实环境状态 |
| --- | --- | --- | --- |
| 2026-05-18 | 建立 DeepRacer 开源源码导航与固定版本仓库 | [`4df8fcc`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/4df8fcc551ad06f95fe8757c0d6e767ddd7200de) | 不涉及运行时验收 |
| 2026-05-18 至 2026-05-22 | 实现并强化 Model Gateway，加入 CI 和一键部署 | [`670d16c`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/670d16c2d9422b7e94339782e05532c49b457092) 至 [`2600a27`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/2600a270aa972c4fd63462d9f3375aea7fb95629) | 真实车辆和赛事待验收 |
| 2026-05-26 | 建立完整使用与开发说明 | [`8c14686`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/8c14686e94c69f067fc0987661546cd55ec1bff6) | 文档不代替运行时验收 |
| 2026-06-01 至 2026-07-20 | 实现并强化 Training Admin、连接档案和 Hosted CI | [PR #1](https://github.com/rogue-shadowdancer/deepracerallinone/pull/1) | 真实 AWS 部署/写入待验收 |
| 2026-07-21 | 完善 Training Admin 操作与两仓库开发说明 | [PR #2](https://github.com/rogue-shadowdancer/deepracerallinone/pull/2) | 未执行 AWS 或实体车操作 |

## 2026-07-21：Training Admin 文档化

### 完成内容

- 在根 README 增加 Training Admin 管理入口和预览/写入边界。
- 在完整手册记录管理员权限、配额语义、批量邀请 CSV、Cognito preview/apply 同步、批量 profile 更新和失败行处理。
- 固定 JDK 17、Node.js 22、Corepack pnpm 9.7.0、Nx 与父仓库/submodule 两仓库发布顺序。
- 修复文档中对 submodule 文件的 GitHub 链接，使其固定到 `b41185fd698eda1dcef918b48987a160271c50ae`。

### 提交与发布证据

- 父仓库提交：[`96109da`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/96109daa04486fe7397d964e8a5f516e199a6dec)、[`feb16e6`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/feb16e6431b8a09c61da1353415c082a8b537133)。
- 合并记录：[PR #2 — Document Training Admin usage and development](https://github.com/rogue-shadowdancer/deepracerallinone/pull/2)。
- 可复核验证：连接档案 example 校验、13 个根工具单元测试、UTF-8 回读、相对链接和隐私检查、`git diff --check`；精确 PR HEAD 的 `connection-config` 与 `checks` 均成功。

### 未执行/限制

- 该 PR 是文档候选，没有部署 AWS 资源、登录真实账号、执行后端写入或连接实体车。
- Hosted CI 成功说明代码候选可构建和测试，不证明任何具体学校/赛事环境已经上线。

## 2026-06-01 至 2026-07-20：Training Admin 与 AWS 用户同步

### 完成内容

- 增加批量邀请用户、CSV 浏览器端校验和 preview、失败行下载与重试。
- 增加 Cognito User Pool 与 DynamoDB profiles 的 preview/apply 同步；同步创建或更新匹配 profile，不删除未匹配 profile。
- 增加 profiles 多选批量更新，支持角色、训练使用时长和模型数配额的显式字段选择。
- 强化配额语义：`-1` 为 unlimited，`0` 为真实零配额，已勾选字段拒绝空字符串或纯空白。
- 增加无凭据连接档案 schema、example、离线 `validate`、只读 `check-live` 及敏感字段递归拒绝。
- 扩展 Training Admin Hosted CI，覆盖 model build、website typecheck/test、lambda test、infra test/build、CDK synth 和 workspace check。

### 两仓库提交关系

- 父仓库提交：[`6e271d1`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/6e271d10e436f17b1a1b8123ddc0cd70214cf662)、[`b0589c5`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/b0589c5d2221ca0dd04fd99899f7c37e115a83dd)、[`43a5b31`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/43a5b31942884f0eedfec103e7b7dd7cc6043b4b)、[`2f21d7b`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/2f21d7bb41cb39f6bda77215f9d16a73cf473d4a)。
- `deepracer-on-aws` 固定提交：[`71ee308`](https://github.com/rogue-shadowdancer/deepracer-on-aws/commit/71ee3083c4d94e813552eec79e1d0f25419f726c)、[`72e60ab`](https://github.com/rogue-shadowdancer/deepracer-on-aws/commit/72e60ab3785ce154b02eb04568f21c1e943247fb)、[`754f350`](https://github.com/rogue-shadowdancer/deepracer-on-aws/commit/754f3503b51d1132ee63714cdf3943e823f4e40b)、[`b41185f`](https://github.com/rogue-shadowdancer/deepracer-on-aws/commit/b41185fd698eda1dcef918b48987a160271c50ae)。
- 合并记录：[PR #1 — Add DeepRacer training administration and AWS user sync](https://github.com/rogue-shadowdancer/deepracerallinone/pull/1)。父仓库 `2f21d7b` 固定最终 submodule gitlink，并作为该 PR 的精确 publication candidate。

### 验证证据

- PR #1 记录的本地结果：连接档案 13 个测试、config 9 个测试、lambda 883 个测试、infra 264 个通过且 5 个按设计跳过；16 个 lint/typecheck/dependency targets、model build 和 diff checks 通过。
- 精确父仓库候选 `2f21d7bb41cb39f6bda77215f9d16a73cf473d4a` 的 Hosted `connection-config` 和 `checks` 成功后才合并。
- 这些测试使用受控配置或 AWS 客户端 mock；没有把测试凭据写入父仓库连接档案。

### 未执行/限制

- PR gate 明确不包含 AWS 部署或真实后端写入。
- Cognito、DynamoDB、SageMaker 和 CloudFormation 仍需对具体 AWS Account/Region 执行[真实 AWS 验收](USAGE_AND_DEVELOPMENT.md#13-真实-aws-验收清单)。

## 2026-05-26：完整使用与开发说明

### 完成内容

- 新增从递归克隆、源码导航、Model Gateway 部署，到开发、测试、submodule 维护和 GitHub 推送的完整中文入口。
- 将根 README 保持为快速入口，详细操作下沉到 `docs/USAGE_AND_DEVELOPMENT.md`。

### 提交与验证证据

- 父仓库提交：[`8c14686`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/8c14686e94c69f067fc0987661546cd55ec1bff6)。
- 可复核证据是该提交中的 README、手册内容和有效仓库路径；此里程碑没有记录稳定的运行时测试数量，因此不补写精确数字。

### 未执行/限制

- 文档覆盖范围不代表相关上游系统或实体车辆已经部署。

## 2026-05-18 至 2026-05-22：Model Gateway

### 2026-05-18：初始服务

- [`670d16c`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/670d16c2d9422b7e94339782e05532c49b457092) 增加 FastAPI Model Gateway、用户/管理员页面、SQLite 持久化、模型存储和初始车辆 Console API 分发。
- 提交同时加入 app、database、storage 和 vehicle tests；没有真实车辆或赛事证据。

### 2026-05-19：功能升级

- [`bc8fce7`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/bc8fce75d286152eb93458b9c88d64d2dd8cf35b) 扩展认证、团队、提交审核、车辆管理、SSH 分发和相应测试。
- 自动化覆盖服务与适配器路径，但 SSH/Console 模拟不能代替车辆现场验收。

### 2026-05-20：可编辑记录、CI、比赛强化和可靠性

- [`5fbe60b`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/5fbe60b98c2a238cc97f628c7629d9b45d45b18f) 增加管理员对用户、队伍、车辆和轮次等记录的编辑能力及测试。
- [`80b68c1`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/80b68c1e4cc825e65930197272f0446a2cbf2aff) 增加首版 Model Gateway GitHub Actions，在 Python 3.11 上运行安装、compileall、pytest 和根仓库 diff check。
- [`74f3be6`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/74f3be6b057ea107b3492cdd7688fadd3f669198) 增加 competition 模式、安全配置、事件/轮次、审计、维护、worker、Docker 和比赛操作页面。
- [`2312e8c`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/2312e8cb72d5d1792ab064debe4640b0e2d8790c) 增加诊断、备份、dispatch 时间线、字段可靠性、运维页面和相关测试。
- 这些提交建立自动化和操作能力，但没有记录真实车辆模型安装、人工激活或赛道运动结果。

### 2026-05-22：一键部署

- [`2600a27`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/2600a270aa972c4fd63462d9f3375aea7fb95629) 增加 Windows/Linux 部署脚本、运行脚本改进和 deployment-script tests，并把 CI 扩展到 Python 3.10/3.11/3.12、部署 dry-run、维护 CLI、Docker build 和独立 hygiene job。
- dry-run 与脚本测试只证明参数和部署路径可执行；生产/比赛服务器仍需配置密钥、Cookie 策略、备份和现场网络。

## 2026-05-18：源码导航与仓库基线

### 完成内容

- [`4df8fcc`](https://github.com/rogue-shadowdancer/deepracerallinone/commit/4df8fcc551ad06f95fe8757c0d6e767ddd7200de) 建立父仓库、30 个车辆/训练/仿真 submodules、根 README、Codex navigation skill 和 `source-map.md`。
- 明确车辆侧从 `vehicle-code/`、训练/仿真从 `training-code/`、跨仓库资料从源码导航进入。

### 验证证据与限制

- 可复核证据是 `.gitmodules`、gitlink 和 source map；固定某个上游提交不表示该上游项目已在本机、AWS 或车辆上完整构建运行。

## 下一阶段验收

- [ ] 按[真实 AWS 验收清单](USAGE_AND_DEVELOPMENT.md#13-真实-aws-验收清单)记录一次实际部署、管理员权限、隔离测试用户写入及 CloudWatch/DynamoDB/Cognito 结果。
- [ ] 按[实体车验收清单](USAGE_AND_DEVELOPMENT.md#14-实体车验收清单)记录 Console API、可选 SSH、`auto` 回退、车辆 console 确认和低速安全测试。
- [ ] 在真实赛事试运行中验证用户/队伍/轮次、模型上传审核、车辆分发、失败恢复、备份和 support bundle 的完整闭环。
- [ ] 只有对应证据完成后，才在后续日志追加“真实环境已验收”条目；不要修改历史条目来掩盖当时的验证边界。

## 维护本日志

1. 只为已经进入父仓库 Git 历史或拥有明确现场记录的里程碑追加条目。
2. 同时记录完成内容、父仓库提交/PR、适用的 submodule 固定提交、验证证据和未执行项。
3. 引用测试数量前，从已合并 PR、精确 CI run 或保存的验收记录复核；否则只写测试类别。
4. 不记录密码、Token、Cookie、AWS 密钥、车辆 SSH 私钥、真实用户数据或本机私有路径。
5. 更新后运行 Markdown 链接、UTF-8、隐私、`git diff --check` 和对应 Hosted CI 检查。
