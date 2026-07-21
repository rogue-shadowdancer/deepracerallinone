# DeepRacer All In One 使用与开发说明

本文档是本仓库的完整使用和开发入口。根 `README.md` 保持简洁，本文件说明从克隆、资料导航、模型网关部署、车辆侧和训练侧源码研究，到本地开发、测试、子模块维护、真实环境验收和推送 GitHub 的完整流程。功能演进和历史验证证据另见 [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md)。

## 目录

- [0. 阅读对象、前置条件与证据边界](#0-阅读对象前置条件与证据边界)
- [1. 项目定位](#1-项目定位)
- [2. 获取代码和初始化](#2-获取代码和初始化)
- [3. 按目标选择入口](#3-按目标选择入口)
- [4. Model Gateway 使用说明](#4-model-gateway-使用说明)
- [5. 开发流程](#5-开发流程)
- [6. 子模块维护](#6-子模块维护)
- [7. GitHub 推送策略](#7-github-推送策略)
- [8. 安全和比赛注意事项](#8-安全和比赛注意事项)
- [9. 排障速查](#9-排障速查)
- [10. 参考入口](#10-参考入口)
- [11. DeepRacer on AWS 配置分层](#11-deepracer-on-aws-配置分层)
- [12. Training Admin 操作说明](#12-training-admin-操作说明)
- [13. 真实 AWS 验收清单](#13-真实-aws-验收清单)
- [14. 实体车验收清单](#14-实体车验收清单)
- [15. 文档维护规则](#15-文档维护规则)

## 0. 阅读对象、前置条件与证据边界

### 0.1 谁应该读哪一部分

| 读者 | 建议入口 | 主要目标 |
| --- | --- | --- |
| 初学者或授课人员 | 第 1-3 节、源码导航 | 了解仓库组成，找到奖励函数、训练、车辆和仿真资料。 |
| DeepRacer on AWS 运维人员 | 第 3.5、11-13 节 | 校验连接档案，操作 Training Admin，完成真实 AWS 验收。 |
| 比赛现场管理员 | 第 4、8、9、14 节 | 部署 Model Gateway，管理模型和车辆，留存现场证据。 |
| 开发者和维护者 | 第 5-7、15 节与开发日志 | 修改父仓库或 submodule，运行检查并通过 PR 发布。 |

### 0.2 前置条件

| 工作 | 前置条件 |
| --- | --- |
| 克隆和源码研究 | Git，能够访问上游 GitHub 仓库；首次获取必须初始化全部 submodules。 |
| 连接档案校验 | Python 3；某次真实部署公开的 CloudFront、API Gateway、Cognito、Region 和上传桶标识。档案不得保存密码、Token、Cookie 或 AWS 密钥。 |
| Training Admin 开发 | JDK 17、Node.js 22、Corepack pnpm 9.7.0，以及已初始化的 `training-code/deepracer-on-aws` submodule。 |
| Model Gateway | Python 3.10+；管理员机器和车辆网络互通；使用 SSH 时还需可信 host key、车辆账号和可写目录。 |
| 实体车验收 | 可控局域网、已充电车辆、已知可用的物理模型、空旷测试区域、急停/断电手段和现场安全观察员。 |

### 0.3 当前状态和证据矩阵

| 能力 | 代码/文档状态 | 自动化证据 | 真实环境状态 |
| --- | --- | --- | --- |
| 开源源码导航与固定版本 | 已实现 | Git submodule 指针和仓库路径可检查 | 不涉及运行时验收 |
| Model Gateway | 已实现上传、审核、诊断、分发、维护和审计流程 | Python 测试、脚本 dry-run、Docker build 和 GitHub Actions | 真实车辆分发及完整赛事仍需按第 14 节验收 |
| DeepRacer on AWS Training Admin | 已实现批量邀请、用户同步、批量配额/角色更新和配置校验 | model、website、lambda、infra 测试，typecheck、CDK synth 和 Hosted CI | 真实 AWS 部署与真实账号写入仍需按第 13 节验收 |
| DeepRacer 连接档案工具 | 已实现 schema、离线 `validate` 和只读 `check-live` | 根仓库单元测试和 Hosted CI | 只有针对指定真实部署运行并保存结果后，才能证明该部署的公开配置可达 |
| 实体车/真实赛事端到端 | 提供适配器、操作说明和验收步骤 | 模拟 Console、SSH 和 HTTP 路径不能代替真车证据 | 当前仓库没有足够证据宣称已经完成 |

“自动化通过”只表示候选代码与测试约束一致；“协议或路由匹配”只表示实现具备对接条件。真实 AWS、真实账号、真实车辆和现场网络必须分别执行验收，并记录环境、时间、候选 SHA、结果和可回收的审计证据。

### 0.4 四条端到端路径

1. **源码研究**：递归克隆 -> 检查 submodule 状态 -> 在源码导航中选择车辆/训练/仿真入口 -> 在对应 submodule 内阅读或实验。只读研究不改变父仓库 gitlink。
2. **DeepRacer on AWS 连接检查**：复制无凭据 example -> 在被忽略的 local 档案中填入公开部署值 -> 运行 `validate` -> 获得授权后运行只读 `check-live` -> 保存命令、时间和结果。该流程不登录、不写入后端。
3. **Training Admin 管理**：先确认真实部署、管理员账号和 `dr-admins` 权限 -> 打开 `Instance management` -> 先 preview -> 核对影响人数与配额 -> 只在明确授权后执行 `Submit`、`Apply sync` 或 `Update N users` -> 保存逐行结果。完整规则见第 12-13 节。
4. **Model Gateway 比赛现场**：准备密钥并部署 -> 创建用户、队伍、事件和轮次 -> 注册并诊断车辆 -> 用户上传、管理员审核 -> 分发候选模型 -> 在车辆 console 手动确认和低速测试 -> 备份并导出时间线/support bundle。完整规则见第 4、8、14 节。

## 1. 项目定位

`deepracerallinone` 是一个 AWS DeepRacer 开源资料整合仓库：

- 上游 DeepRacer 车辆侧、训练侧、仿真侧和示例项目代码通过 Git submodules 管理。
- 根仓库只固定上游版本、提供资料导航、维护本地说明文档，并承载自有的 `model-gateway` 服务。
- 不建议把上游仓库源码复制到根仓库中；需要更新上游代码时，应更新对应 submodule 指针。
- 本仓库自有的主要可运行项目是 `model-gateway`，用于比赛现场的模型上传、审核、车辆诊断和模型下发。

目录职责：

| 路径 | 职责 |
| --- | --- |
| `README.md` | GitHub 首页快速入口。 |
| `docs/USAGE_AND_DEVELOPMENT.md` | 本完整说明。 |
| `docs/DEVELOPMENT_LOG.md` | 已进入父仓库历史的功能里程碑、验证证据和未完成项。 |
| `deepracer-open-source-navigator/` | DeepRacer 开源生态导航资料和 Codex skill。 |
| `model-gateway/` | 局域网模型上传与车辆分发服务。 |
| `vehicle-code/` | 车辆侧 ROS2、设备控制、Web console、传感器和样例项目 submodules。 |
| `training-code/` | DeepRacer on AWS、仿真器、RL 环境和 notebooks submodules。 |
| `.github/workflows/model-gateway.yml` | `model-gateway` 的 GitHub Actions 测试和部署脚本检查。 |
| `.github/workflows/training-admin.yml` | 连接档案和固定 Training Admin submodule 候选的 Hosted CI。 |

## 2. 获取代码和初始化

推荐递归克隆：

```bash
git clone --recurse-submodules https://github.com/rogue-shadowdancer/deepracerallinone.git
cd deepracerallinone
```

如果已经普通克隆过，初始化所有 submodules：

```bash
git submodule update --init --recursive
```

查看当前固定的上游版本：

```bash
git submodule status --recursive
```

如果某个目录为空、只有 gitlink 或无法打开上游代码，通常是 submodule 未初始化。重新运行：

```bash
git submodule update --init --recursive
```

## 3. 按目标选择入口

### 3.1 只查资料或定位源码

先读：

- `deepracer-open-source-navigator/references/source-map.md`
- `deepracer-open-source-navigator/SKILL.md`

`source-map.md` 按车辆侧、训练侧、仿真侧、官方文档和样例项目整理了入口。定位问题时先判断属于哪类：

- 车辆运行、传感器、相机、LiDAR、舵机、ROS2 service、Web console：看 `vehicle-code/`。
- 训练、奖励函数、SageMaker、模型导入导出、自托管比赛平台：看 `training-code/deepracer-on-aws`。
- 仿真环境、RL 环境、UDE、Gym bridge、ROS bridge：看 `training-code/deepsim`、`training-code/deepracer-env`、`training-code/ude-*`。
- 现场比赛模型收集和分发：看 `model-gateway/`。

### 3.2 部署比赛模型网关

`model-gateway` 运行在管理员笔记本或局域网服务器上，不运行在 DeepRacer 小车或训练栈里。它提供：

- 用户登录、组队、上传物理 DeepRacer 模型 `.tar.gz`。
- 管理员审核、候选版本标记、事件和轮次管理。
- 车辆注册、健康检查、诊断、模型分发、重试、取消和时间线。
- Console API 和 SSH 两种交付方式，`auto` 模式会优先尝试 Console API，再按配置尝试 SSH。
- 备份、恢复、清理、CSV 导出、support bundle 和审计日志。

详细功能说明见 `model-gateway/README.md`。

### 3.3 研究车辆侧代码

车辆侧代码在 `vehicle-code/`，常见入口：

- `vehicle-code/aws-deepracer-launcher`：车辆侧依赖安装、构建和 launch 流程。
- `vehicle-code/aws-deepracer`：导航、仿真、Gazebo 描述和 ROS Navigation 示例。
- `vehicle-code/aws-deepracer-camera-pkg`：相机节点。
- `vehicle-code/aws-deepracer-inference-pkg`：OpenVINO 推理节点。
- `vehicle-code/aws-deepracer-navigation-pkg`：根据推理结果和 action space 生成控制命令。
- `vehicle-code/aws-deepracer-ctrl-pkg`：控制模式、手动/自动/校准等状态。
- `vehicle-code/aws-deepracer-servo-pkg`：转向和油门比例到 PWM 的映射。
- `vehicle-code/aws-deepracer-webserver-pkg`：车辆 Web console 后端 API。
- `vehicle-code/aws-deepracer-interfaces-pkg`：自定义 ROS2 service 和 message。

车辆侧开源栈通常假设 Ubuntu 20.04、ROS2 Foxy、Intel OpenVINO 2021.1.110 和 Python 3.8。更新实体车到 ROS2 开源栈会清除设备数据，执行前需要备份和确认。

### 3.4 研究训练和仿真代码

训练侧和仿真侧代码在 `training-code/`，常见入口：

- `training-code/deepracer-on-aws`：自托管 DeepRacer on AWS 解决方案，包含网站、API、CDK、训练、评估和模型导入导出。
- `training-code/deepsim`：ROS 和 Gazebo 相关 RL 环境构建工具。
- `training-code/deepracer-env`：RL Lab DeepRacer 环境 Python 接口。
- `training-code/deepracer-env-config`：通过 UDE side channel 操作环境配置。
- `training-code/deepracer-env-state`：环境状态工具。
- `training-code/deepracer-track-geometry`：赛道几何数据访问。
- `training-code/ude`、`training-code/ude-gym-bridge`、`training-code/ude-ros-bridge`：UDE、Gym 和 ROS 桥接。
- `training-code/aws-deepracer-notebooks`：训练和实验 notebooks。
- `training-code/deepracer-compat-reward-function`：奖励函数兼容工具。

### 3.5 管理 DeepRacer on AWS 用户

已经部署 DeepRacer on AWS、并以管理员账号登录后，从侧边栏进入 `Instance management`（`/manageInstance`）。这里可以管理实例和新用户默认配额、批量邀请用户、从 Cognito User Pool 同步 profiles，以及对表格中选中的用户批量更新角色和配额。非管理员访问该页面会看到 `Unauthorized`，不会获得这些操作入口。

完整操作和写入边界见第 12 节。连接档案的 `validate` 与 `check-live` 仍是独立的本机只读工具，不会代替管理员登录、用户同步或部署。

## 4. Model Gateway 使用说明

### 4.1 运行环境

最低要求：

- Python 3.10 或更新版本。
- 管理员机器和 DeepRacer 小车处于同一网络，能访问车辆 console URL。
- 如果使用 SSH 交付，网关机器需要能 SSH 到车辆，并确认 host key fingerprint。

本地生成文件默认不提交：

- `model-gateway/.gateway.env`
- `model-gateway/.venv/`
- `model-gateway/data/`
- `model-gateway/backups/`
- `model-gateway/*.log`

### 4.2 Windows 一键部署

```powershell
cd model-gateway
.\scripts\deploy-windows.ps1 -Mode competition -AllowInsecureLanCookie -RunTests
```

参数说明：

- `-Mode competition`：比赛模式，会阻止默认弱配置。
- `-AllowInsecureLanCookie`：允许 HTTP-only 局域网比赛使用非 HTTPS cookie。生产级 HTTPS 部署应改用 `GATEWAY_COOKIE_SECURE=true`。
- `-RunTests`：部署前运行测试。
- `-NoStart`：只安装和初始化，不启动服务。
- `-Port 8081`：换端口。
- `-DataDir D:\deepracer-gateway-data`：换数据目录。

重新启动，不重新安装：

```powershell
cd model-gateway
.\scripts\run-windows.ps1 -Host 0.0.0.0 -Port 8080
```

### 4.3 Linux 一键部署

```sh
cd model-gateway
./scripts/deploy-linux.sh --mode competition --allow-insecure-lan-cookie --run-tests
```

重新启动：

```sh
cd model-gateway
./scripts/run-linux.sh --host 0.0.0.0 --port 8080
```

长期运行可以交给 `screen`、`tmux`、`pm2`、Docker 或 systemd。仓库脚本不替站点管理员强制选择进程管理方式。

### 4.4 手动开发运行

Windows PowerShell:

```powershell
cd model-gateway
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
python -m uvicorn model_gateway.app:app --host 0.0.0.0 --port 8080
```

Linux:

```sh
cd model-gateway
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test]"
python -m uvicorn model_gateway.app:app --host 0.0.0.0 --port 8080
```

入口：

- 用户登录：`http://<gateway-host>:8080/login`
- 管理员登录：`http://<gateway-host>:8080/admin/login`

如果数据库中没有管理员，启动时会根据 `GATEWAY_BOOTSTRAP_ADMIN_USERNAME` 和 `GATEWAY_BOOTSTRAP_ADMIN_PASSWORD` 创建初始管理员。开发默认值是 `admin/admin`，比赛环境不能使用。

### 4.5 关键配置

常用环境变量：

| 变量 | 作用 |
| --- | --- |
| `GATEWAY_DATA_DIR` | SQLite 数据库、上传文件和备份目录。 |
| `GATEWAY_BOOTSTRAP_ADMIN_USERNAME` | 初始管理员用户名。 |
| `GATEWAY_BOOTSTRAP_ADMIN_PASSWORD` | 初始管理员密码。 |
| `GATEWAY_SESSION_SECRET` | session cookie 签名和环境隔离密钥。 |
| `GATEWAY_CREDENTIAL_SECRET` | 车辆 Console 和 SSH 密码的加密密钥。 |
| `GATEWAY_COMPETITION_MODE` | 比赛模式，启用启动时安全校验。 |
| `GATEWAY_COOKIE_SECURE` | HTTPS 部署时设为 `true`。 |
| `GATEWAY_ALLOW_INSECURE_LAN_COOKIE` | HTTP-only 局域网比赛的显式例外。 |
| `GATEWAY_MAX_UPLOAD_BYTES` | 最大上传文件大小，默认 1 GB。 |
| `GATEWAY_DISPATCH_WORKER_ENABLED` | 是否启用后台分发 worker。 |
| `GATEWAY_AUTO_BACKUP_ENABLED` | 高风险管理操作前是否自动备份。 |

比赛前最低安全要求：

- `GATEWAY_COMPETITION_MODE=true`
- 不使用 `admin/admin`
- 设置非默认 `GATEWAY_SESSION_SECRET`
- 设置 `GATEWAY_CREDENTIAL_SECRET`
- HTTPS 部署设 `GATEWAY_COOKIE_SECURE=true`；HTTP-only 局域网比赛才使用 `GATEWAY_ALLOW_INSECURE_LAN_COOKIE=true`

### 4.6 管理员流程

1. 登录 `/admin/login`。
2. 在 `/admin/teams` 设置是否开放自注册和默认队伍人数上限。
3. 在 `/admin/users` 创建用户、批量生成用户、导入 CSV、审批自注册用户、重置密码或撤销 session。
4. 在 `/admin/teams` 创建队伍、调整人数限制、移动用户和重置 join code。
5. 在 `/admin/vehicles` 注册车辆，填写 Console URL、交付模式和可选 SSH 设置。
6. 在 `/admin/events` 创建比赛事件和轮次，设置上传和分发限制。
7. 在 `/admin/health` 执行车辆诊断。
8. 在 `/admin` 审核模型上传，批准或拒绝，并选择车辆下发。
9. 通过 dispatch timeline 查看分发状态、重试、取消和错误信息。
10. 赛后导出 users、teams、submissions、dispatches CSV，并保存 support bundle。

### 4.7 用户流程

1. 打开 `/login` 登录；如果管理员开放自注册，也可以打开 `/register`。
2. 在 `/teams` 创建队伍或使用 join code 加入队伍。
3. 在 `/upload` 上传物理 DeepRacer 模型 `.tar.gz`。
4. 在 `/dashboard` 查看提交状态和审核结果。

用户必须是 active 状态并且属于一个 active team，才能上传模型。当前版本中，一个用户同时只属于一个 active team。

### 4.8 车辆交付方式

Console API 是默认交付方式，会调用车辆 Web console：

- `POST /api/uploadModels`
- `GET /api/is_model_installed?filename=<model-folder>`
- `GET /api/isModelLoading`

SSH 是可选兜底方式，要求网关机器能 SSH 到车辆，并能写入 `/opt/aws/deepracer/artifacts`。默认安装命令会调用 ROS2 `console_model_action` service。若车辆 ROS2 环境路径不同，应在车辆表单中配置自定义 install command template。

`auto` 模式会先尝试 Console API。如果失败且 SSH 配置完整，会继续尝试 SSH，并记录每次 attempt。

### 4.9 运维命令

备份：

```powershell
cd model-gateway
python -m model_gateway.maintenance backup .\backups
```

诊断指定车辆：

```powershell
cd model-gateway
python -m model_gateway.maintenance doctor --vehicle-id 1
```

恢复：

```powershell
cd model-gateway
python -m model_gateway.maintenance restore .\backups\deepracer-gateway-backup-YYYYMMDDTHHMMSSZ.tar.gz
```

清理七天前失败上传：

```powershell
cd model-gateway
python -m model_gateway.maintenance cleanup --older-than-days 7
```

只预览清理：

```powershell
cd model-gateway
python -m model_gateway.maintenance cleanup --older-than-days 7 --dry-run
```

## 5. 开发流程

### 5.1 分支和工作树

开始前确认状态：

```bash
git status --short --branch
git remote -v
git submodule status --recursive
```

为改动创建主题分支：

```bash
git switch -c codex/<short-description>
```

不要直接修改上游 submodule 指针，除非目标就是升级上游固定版本。不要把 `model-gateway/.gateway.env`、`data/`、`.venv/`、日志或备份文件提交进仓库。

### 5.2 Model Gateway 开发环境

Windows 推荐使用 Python Launcher 指定 Python 3.10+：

```powershell
cd model-gateway
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

Linux:

```sh
cd model-gateway
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

运行应用：

```bash
python -m uvicorn model_gateway.app:app --host 0.0.0.0 --port 8080
```

### 5.3 测试和本地检查

在 `model-gateway/` 目录运行：

```bash
python -m compileall src tests
python -m pytest tests
```

在仓库根目录运行：

```bash
git diff --check
git status --short --branch
```

CI 还会执行：

```bash
bash -n scripts/run-linux.sh scripts/deploy-linux.sh
bash scripts/deploy-linux.sh --dry-run
bash scripts/deploy-linux.sh --mode dev --dry-run
pwsh -NoProfile -File scripts/deploy-windows.ps1 -DryRun
pwsh -NoProfile -File scripts/deploy-windows.ps1 -Mode dev -DryRun
pwsh -NoProfile -File scripts/run-windows.ps1 -DryRun
model-gateway-maintenance --help
python -m model_gateway.maintenance --help
docker build -t deepracer-model-gateway:test .
```

如果只改根文档，最低本地检查是 `git diff --check`、相对链接和命令路径核对，以及与改动相关的轻量测试。`README.md`、本文档、连接配置和 `training-code/deepracer-on-aws` 指针都在 `Training Admin` workflow 的 path filter 中；正式发布仍以新父仓库 SHA 的完整 Hosted CI 为准。

如果修改 `training-code/deepracer-on-aws` 中的 Training Admin，在 `training-code/deepracer-on-aws/source` 使用与 Hosted CI 相同的运行时：JDK 17、Node.js 22 和 Corepack pnpm 9.7.0。

```bash
corepack enable
corepack prepare pnpm@9.7.0 --activate
corepack pnpm install --frozen-lockfile
corepack pnpm nx run model:build --output-style=static
corepack pnpm nx run website:typecheck --output-style=static
corepack pnpm nx run website:test --output-style=static
corepack pnpm nx run lambda:test --output-style=static
corepack pnpm nx run infra:test --output-style=static
corepack pnpm nx run infra:build --output-style=static
corepack pnpm check
```

迭代小改动时先运行直接相关的 website、lambda 或 infra target；推送或 publication 前再要求上述完整 gate 在精确候选上通过。不要用旧 SHA 的 CI 结果替代新候选验证。

### 5.4 常见代码修改边界

- 修改根 README、docs 或 navigator 资料：只需保持链接、路径和 submodule 事实准确。
- 修改 `model-gateway`：必须运行 pytest，并关注上传校验、session、CSRF、车辆交付、备份和诊断相关测试。
- 修改 submodule 内代码：确认这是有意修改对应 checkout。先在 submodule 当前分支选择性提交、验证并推送，再回到父仓库提交新的 gitlink；根仓库不会自动把 submodule 工作树改动纳入提交，也不能替代 submodule 自身的远端发布。

## 6. 子模块维护

查看 submodule 当前状态：

```bash
git submodule status --recursive
```

初始化或恢复缺失 submodule：

```bash
git submodule update --init --recursive
```

拉取所有 submodule 的远端信息：

```bash
git submodule foreach --recursive git fetch --all --tags
```

如果需要把某个 submodule 固定到新的上游提交：

```bash
cd vehicle-code/aws-deepracer-launcher
git fetch origin
git switch main
git pull --ff-only
cd ../..
git status --short
git add vehicle-code/aws-deepracer-launcher
git commit -m "chore: update aws-deepracer-launcher submodule"
```

注意事项：

- 不要在不确认影响的情况下批量更新所有 submodules。
- 更新 submodule 指针会改变复现环境，需要在提交说明中写清楚原因。
- 如果 submodule 内出现未提交改动，先进入对应 submodule 查看 `git status`，不要在根仓库中盲目覆盖。

## 7. GitHub 推送策略

默认流程：

```bash
git status --short --branch
git diff --check
```

如果修改了 `model-gateway`：

```bash
cd model-gateway
python -m compileall src tests
python -m pytest tests
cd ..
```

提交并推送分支：

```bash
git add README.md docs/USAGE_AND_DEVELOPMENT.md docs/DEVELOPMENT_LOG.md
git commit -m "docs: improve manual and add development log"
git push -u origin <branch-name>
```

如果同时调整文档 CI 触发范围，再显式暂存 `.github/workflows/training-admin.yml`。不要使用 `git add .`，避免把本地连接档案、教学输出或 submodule 内工作一起带入候选。

如果测试失败，不要推送，除非维护者明确要求带失败风险继续。若没有可运行测试，也应说明未运行原因和风险。

## 8. 安全和比赛注意事项

- `.gateway.env` 保存本地密钥和初始管理员密码，不要提交。
- `GATEWAY_CREDENTIAL_SECRET` 为空时只适合开发环境；比赛环境必须设置。
- HTTP-only 局域网比赛需要显式设置 `GATEWAY_ALLOW_INSECURE_LAN_COOKIE=true`，并在赛事 runbook 中记录原因。
- HTTPS 部署应设置 `GATEWAY_COOKIE_SECURE=true`。
- DeepRacer 车辆 SSH host key fingerprint 应先记录再保存 SSH 凭据。
- 支持包和导出文件用于赛后排查，但仍应按比赛数据处理规范保存。
- 更新实体车辆到 Ubuntu 20.04/ROS2 开源栈会清除设备数据，执行前必须备份。

## 9. 排障速查

| 现象 | 处理 |
| --- | --- |
| submodule 目录为空 | 运行 `git submodule update --init --recursive`。 |
| submodule 显示 detached HEAD | 读取固定版本是正常状态；要开发时先在 submodule 内创建或切换明确分支，不要直接覆盖父仓库 gitlink。 |
| Windows 默认 `python` 版本过低 | 使用 `py -3.10` 或更新版本创建虚拟环境。 |
| 连接档案 `validate` 失败 | 对照 schema 修正 URL、Region、Cognito ID 和必填字段；删除密码、Token、Cookie、AWS 密钥等禁止字段。 |
| `check-live` 与 `/env.js` 不一致 | 确认档案对应同一次部署及同一 Region，不要用猜测值覆盖线上结果；该命令不会自动修改档案。 |
| Training Admin 显示 `Unauthorized` | 确认当前 Cognito 用户属于 `dr-admins`，并核对部署使用的 User Pool；不要通过前端绕过权限检查。 |
| 批量邀请 CSV 无法提交 | 使用下载模板，检查表头、邮箱、alias、role、配额格式和重复行；有任一 validation error 时先修正再提交。 |
| 批量配额输入被拒绝 | 勾选的字段不能留空；`-1` 表示 unlimited，`0` 是会实际阻止对应资源使用的零配额。 |
| competition 模式启动失败 | 检查默认管理员、`GATEWAY_SESSION_SECRET`、`GATEWAY_CREDENTIAL_SECRET` 和 cookie 安全配置。 |
| 浏览器反复退出或 cookie 不生效 | HTTPS 使用 `GATEWAY_COOKIE_SECURE=true`；HTTP-only 局域网必须显式允许 insecure LAN cookie，并记录站点风险。 |
| 用户无法上传 | 确认用户 active、属于 active team、当前轮次允许上传、模型是合法 `.tar.gz`。 |
| Console API 下发失败 | 确认车辆 Console URL、密码、固件路由、证书行为、Cookie、网络连通性和 `/api/isModelLoading` 状态；不要全局关闭 TLS 校验。 |
| SSH 下发失败 | 确认 host key、账号权限、artifact root 可写、rsync/SFTP 可用和 ROS2 install command。 |
| CI 脚本检查失败 | 先在 `model-gateway/` 本地运行对应 dry-run 命令复现。 |
| 车辆更新或重装前无法确认数据影响 | 停止操作并先备份；更新到 Ubuntu 20.04/ROS2 开源栈会清除设备数据。 |

## 10. 参考入口

- 根快速入口：`README.md`
- 开发里程碑与证据：[DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md)
- Model Gateway 详细说明：`model-gateway/README.md`
- DeepRacer 开源来源图：`deepracer-open-source-navigator/references/source-map.md`
- AWS DeepRacer GitHub 组织：https://github.com/aws-deepracer
- DeepRacer on AWS 源码：https://github.com/aws-solutions/deepracer-on-aws
- DeepRacer on AWS 文档：https://docs.aws.amazon.com/solutions/deepracer-on-aws/

## 11. DeepRacer on AWS 配置分层

- 子模块的 `source/libs/config/src/data/defaultConfig.json`：版本控制中的应用和部署默认值，由 TypeScript 运行时解析器严格校验。
- 子模块的 `source/apps/infra/cdk.json` 与环境变量/CDK context：部署时覆盖；ECR 和 CDK context 继续留在这里。
- CloudFormation Outputs 与线上 `/env.js`：部署后生成的六个公开运行时值，前端 `window.EnvironmentConfig` 接口不变。
- 根仓库的 `config/deepracer.connection.local.json`：本机只读运维检查档案。它由 `config/deepracer.connection.example.json` 创建，并由根级 `.gitignore` 忽略。
- 密码、Cognito Token、Cookie 和 AWS 密钥：不属于上述任何配置。连接 Schema 不定义这些字段，Python 工具也会递归拒绝敏感键。

连接档案只接受 HTTPS URL，并校验 Region 与 Cognito 资源 ID 前缀一致。`login.invitationAccountId` 是邀请标识，不是十二位 AWS Account ID；不知道 `racerAlias` 时保留空字符串，不猜测线上值。

```powershell
py -3 tools\deepracer_connection.py validate config\deepracer.connection.local.json
py -3 tools\deepracer_connection.py check-live config\deepracer.connection.local.json
```

`validate` 只检查文件结构和安全规则。`check-live` 请求 CloudFront 首页并确认 DeepRacer 页面标识，安全解析仅包含 JSON 赋值的 `window.EnvironmentConfig`，逐项比较 API Endpoint、User Pool、User Pool Client、Identity Pool、Region 和上传桶，并以未认证 `/profile` 的 401/403 确认鉴权边界。它不会登录、写入后端、读取浏览器存储或自动修改档案。GitHub CI 只校验无真实账号的 example，不访问本地档案或真实部署。

## 12. Training Admin 操作说明

### 12.1 权限、入口和写入边界

本节描述已经部署的 DeepRacer on AWS 网站功能，不执行或替代部署。管理员登录后，从侧边栏进入 `Instance management`，也可以访问 `/manageInstance`。页面会检查当前用户是否属于 `dr-admins`；非管理员只会看到 `Unauthorized`。

页面中的操作分为预览和写入两类：

- 只读或本地预览：批量邀请的 CSV 解析与 preview、`Sync AWS users` 初始 preview、`Refresh preview`。
- 后端写入：批量邀请的 `Submit`、Cognito 同步的 `Apply sync`、批量更新的 `Update N users`，以及现有单用户/实例配额操作。

提交前先核对预览、影响人数和配额值。页面返回逐行结果；不能仅凭成功通知推断每一行都成功。

### 12.2 配额和批量更新

`Instance quotas` 管理实例级训练资源配额，`New user quotas` 管理新建 profile 的默认训练时长和模型数。SageMaker instance type、Service Quotas 名称和部署配置关系见子模块精确提交中的 [`source/docs/configuration.md`](https://github.com/rogue-shadowdancer/deepracer-on-aws/blob/b41185fd698eda1dcef918b48987a160271c50ae/source/docs/configuration.md)。运行时配置解析和 CDK synth 会拒绝不受支持的训练实例类型。

批量修改现有用户：

1. 在 profiles 表格中选择一个或多个用户。
2. 打开 `Actions`，选择 `Batch update users`。
3. 勾选要修改的 `Update role`、`Update usage limit` 或 `Update model limit`；未勾选字段保持不变。
4. 检查 `Update N users` 中的人数，再提交。

配额值规则：

- `usage limit` 以小时输入，非负数会换算为分钟；`-1` 表示 unlimited。
- `model limit` 只接受非负整数；`-1` 表示 unlimited。
- 显式 `0` 是合法的零配额，会阻止对应训练或模型创建；不要把 `0` 当成“未设置”。
- 已勾选的配额字段不能为空或只包含空白；页面会显示 validation error，并且不会发送 batch mutation。
- 至少勾选一个字段才能提交。全部行成功时页面会清除表格选择；部分失败时保留逐行结果供管理员检查。

### 12.3 批量邀请用户

打开 `Batch invite users` 后，优先点击 `Download template` 获取 CSV。固定表头是：

```csv
email,alias,role,usageHours,modelLimit
student@example.com,student01,racer,2,5
```

字段规则：

- `email` 必填，同一 CSV 中不能重复，并且必须是有效邮箱格式。
- `alias` 可选；填写时必须为 3-20 个字符，只能使用字母、数字、下划线或连字符。
- `role` 可选；接受 `racer`、`race facilitator`、`admin`，也接受 `dr-racers`、`dr-race-facilitators`、`dr-admins` 等对应组名。留空时使用服务默认值。
- `usageHours` 可选；接受 `-1`、`unlimited` 或非负小时数，非负值会换算为分钟。
- `modelLimit` 可选；接受 `-1`、`unlimited` 或非负整数。

上传 CSV 或粘贴文本后，浏览器先按行校验并生成 `Preview`。只要存在 validation error，或没有任何有效数据行，`Submit` 就保持禁用。提交后检查 summary 和 `Batch results`；若有失败行，使用 `Download failed rows` 下载 `failed-batch-invites.csv`，修正后只重试失败记录。

### 12.4 同步 Cognito 用户

`Sync AWS users` 会分页读取当前配置的 Cognito User Pool，并与 DynamoDB profiles 比较。打开 modal 时自动生成 preview，也可以使用 `Refresh preview` 重新获取。结果状态含义：

- `Created`：Cognito 用户属于 DeepRacer 角色组，但不存在对应 profile；Apply 时使用当前新用户默认配额创建。
- `Updated`：现有 profile 的 email 或 DeepRacer role 与 Cognito 不一致；Apply 时只更新这些差异字段。
- `Unchanged`：两侧已一致。
- `Skipped`：例如 Cognito 用户缺少 username/email、未加入 DeepRacer 角色组，或既有 profile 没有匹配 Cognito 用户；不会写入或删除。
- `Failed`：该行比较或应用失败，需要根据 message 单独排查。

只有 preview 中 `Created + Updated` 大于零时，`Apply sync` 才可用。Apply 完成后按钮会被锁定，结果表切换为实际执行结果；需要再次同步时关闭并重新打开，或先重新获取 preview。同步不会删除 profile，也不会修改既有 profile 的 alias、训练时长或模型数配额。

### 12.5 开发、测试和两仓库提交

Training Admin 由父仓库 workflow、父仓库连接配置工具，以及 `training-code/deepracer-on-aws` submodule 中的网站、Lambda、配置和 CDK 共同组成。修改 submodule 代码时必须保持以下顺序：

1. 在 submodule 运行直接相关测试，并在发布候选上运行第 5.3 节的完整 gate。
2. 只暂存预期 submodule 文件，完成 review 后先提交并推送 submodule 分支。
3. 回到父仓库，只暂存更新后的 `training-code/deepracer-on-aws` gitlink 及明确批准的父文件。
4. 推送父分支后，以父仓库精确 SHA 的 Hosted `Training Admin` workflow 作为 publication gate。

如果只修改本文档和根 README，不要创建 submodule 提交或改变 gitlink。推送前至少运行：

```powershell
py -3 tools\deepracer_connection.py validate config\deepracer.connection.example.json
py -3 -m unittest discover -s tests -p "test_deepracer_connection.py"
git diff --check
git status --short --branch
```

文档、测试和 CI 通过只证明当前 GitHub 候选与描述一致，不代表真实 AWS 部署、真实账号写入或实体车现场验收已经完成。

## 13. 真实 AWS 验收清单

本清单是需要真实账号和现场授权的人工验收，不由本文档、单元测试或 GitHub CI 自动完成。执行时记录父仓库 SHA、`training-code/deepracer-on-aws` gitlink、AWS Account/Region 的非敏感标识、时间和操作者；不要把密码、Token、Cookie 或密钥写入仓库。

### 13.1 部署和公开运行时配置

- [ ] CloudFormation/CDK 部署成功，并保存 stack 名称、Region 和最终状态。
- [ ] 保存 CloudFormation Outputs 中 CloudFront、API Gateway、Cognito User Pool/Client、Identity Pool 和上传桶的非敏感值。
- [ ] CloudFront 首页可以访问，页面内容与 DeepRacer on AWS 部署一致。
- [ ] `/env.js` 中六个公开运行时字段与同次部署 Outputs 一致。
- [ ] 使用本机 local 档案运行 `validate` 和只读 `check-live`，记录命令、时间、退出码和目标主机；不提交 local 档案。

### 13.2 身份、数据和训练资源

- [ ] 使用测试管理员登录，并确认其属于 `dr-admins`；普通测试用户访问 `/manageInstance` 被拒绝。
- [ ] Cognito 角色组、DynamoDB profiles 和 Training Admin preview 的用户映射一致。
- [ ] 确认部署所用 SageMaker instance type 与 Service Quotas/配置约束一致。
- [ ] 确认上传桶、DynamoDB 表和训练资源位于预期 Region，且 IAM 权限没有越过部署要求。

### 13.3 授权写入和留证

- [ ] 在隔离测试用户上运行一次批量邀请，先保存 preview，再经授权执行 `Submit`，逐行核对结果。
- [ ] 对同一测试范围运行一次 Cognito sync preview；只有确认 `Created`/`Updated` 集合后才执行 `Apply sync`。
- [ ] 对隔离测试用户运行一次批量角色或配额更新，验证未勾选字段保持不变，`-1` 与 `0` 语义正确。
- [ ] 核对 CloudWatch、Cognito、DynamoDB 和应用返回结果，确保成功提示与实际记录一致。
- [ ] 清理或保留测试数据时遵循现场数据策略，并记录清理结果。

以上项目全部完成前，状态应写为“具备真实 AWS 对接代码，真实部署/写入尚未完成验收”，不能写成“已上线”或“真实后端已跑通”。

## 14. 实体车验收清单

车辆验收可能产生模型安装、SSH 写入和物理运动。必须由拥有车辆与网络权限的现场人员执行；首次运动测试使用低速、架空车轮或空旷封闭区域，并安排观察员随时断电。

### 14.1 安全和连通性预检

- [ ] 记录车辆标识、固件/系统版本、电池状态、测试地点、时间和候选父仓库 SHA。
- [ ] 管理员机器与车辆位于可控网络；确认车辆 IP/hostname 可达，不暴露到不可信公网。
- [ ] 能通过 `https://<vehicle-ip>` 或 `https://<hostname>.local` 打开车辆 console，并核对证书警告、登录和 Cookie 行为。
- [ ] 如使用 SSH，先独立核对并记录 host key fingerprint，再配置凭据；禁止通过全局关闭 host key 或 TLS 校验规避问题。
- [ ] 准备已知可以在该车辆版本运行的物理模型 `.tar.gz`、急停/断电手段和清晰测试区域。

### 14.2 注册、诊断和分发

- [ ] 在 Model Gateway 注册车辆，选择 `console_api`、`ssh` 或 `auto`，只填写该方式必需的信息。
- [ ] 运行 `/admin/health` 和车辆诊断，确认目标 URL/SSH、存储空间、认证和基本网络状态。
- [ ] 上传并审核已知可用模型，记录 submission、candidate、vehicle 和 dispatch 标识。
- [ ] 单独验证 Console API；如现场允许 SSH，再单独验证 SSH；最后验证 `auto` 的优先级和回退记录。
- [ ] 等待 `/api/is_model_installed` 和 `/api/isModelLoading` 对应状态完成，超时或断连时停止并排查，不重复盲目分发。

### 14.3 车辆确认、低速测试和收尾

- [ ] 在车辆 console 中确认模型出现；网关负责安装，不应声称已经自动激活模型。
- [ ] 手动选择模型，先检查相机、校准、转向和油门状态，再进行最低安全速度测试。
- [ ] 由观察员确认车辆行为和停止手段正常后，才能转入封闭赛道测试。
- [ ] 导出 dispatch 时间线、审计记录和 support bundle；检查其中不含明文密码、Token、Cookie、私钥或 AWS 密钥。
- [ ] 完成数据库与 artifact 备份，记录失败重试、取消、清理和最终车辆状态。

只有实际车辆上的模型安装确认、人工选择和安全运动测试均留有证据时，才能将该车辆/模型组合标记为“真车验收通过”。

## 15. 文档维护规则

- 使用手册描述当前可重复执行的流程；[开发日志](DEVELOPMENT_LOG.md)记录已经进入父仓库历史的里程碑、证据和限制，两者不要互相复制整段内容。
- 功能、命令、环境变量、路由或 CI gate 变化时，同一候选必须同步更新对应文档。
- 开发日志按日期追加，不回填无法从提交、PR、CI 或现场记录复核的精确测试数量。
- 自动化、真实 AWS 和实体车证据必须分栏表达；没有现场证据时明确写“未执行”或“待验收”。
- 文档候选至少检查 UTF-8、Markdown 相对链接、敏感信息、`git diff --check` 和适用的轻量测试；正式合并以精确 PR HEAD 的 Hosted CI 为准。
