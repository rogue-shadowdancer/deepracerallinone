# DeepRacer All In One 使用与开发说明

本文档是本仓库的完整使用和开发入口。根 `README.md` 保持简洁，本文件说明从克隆、资料导航、模型网关部署、车辆侧和训练侧源码研究，到本地开发、测试、子模块维护和推送 GitHub 的完整流程。

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
| `deepracer-open-source-navigator/` | DeepRacer 开源生态导航资料和 Codex skill。 |
| `model-gateway/` | 局域网模型上传与车辆分发服务。 |
| `vehicle-code/` | 车辆侧 ROS2、设备控制、Web console、传感器和样例项目 submodules。 |
| `training-code/` | DeepRacer on AWS、仿真器、RL 环境和 notebooks submodules。 |
| `.github/workflows/model-gateway.yml` | `model-gateway` 的 GitHub Actions 测试和部署脚本检查。 |

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

如果只改根文档，最低检查是 `git diff --check`。但如果推送策略要求项目适用测试，建议仍执行 `model-gateway` 测试，因为这是仓库当前唯一自有可运行项目和 CI 覆盖重点。

### 5.4 常见代码修改边界

- 修改根 README、docs 或 navigator 资料：只需保持链接、路径和 submodule 事实准确。
- 修改 `model-gateway`：必须运行 pytest，并关注上传校验、session、CSRF、车辆交付、备份和诊断相关测试。
- 修改上游 submodule 内代码：确认这是有意修改上游 checkout。根仓库只会记录 submodule 指针或未提交的 submodule 工作树状态，不会自动把上游仓库改动纳入根仓库。

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
git add README.md docs/USAGE_AND_DEVELOPMENT.md
git commit -m "docs: expand usage and development guide"
git push -u origin <branch-name>
```

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
| Windows 默认 `python` 版本过低 | 使用 `py -3.10` 或更新版本创建虚拟环境。 |
| competition 模式启动失败 | 检查默认管理员、`GATEWAY_SESSION_SECRET`、`GATEWAY_CREDENTIAL_SECRET` 和 cookie 安全配置。 |
| 用户无法上传 | 确认用户 active、属于 active team、当前轮次允许上传、模型是合法 `.tar.gz`。 |
| Console API 下发失败 | 确认车辆 Console URL、密码、网络连通性和 `/api/isModelLoading` 状态。 |
| SSH 下发失败 | 确认 host key、账号权限、artifact root 可写、rsync/SFTP 可用和 ROS2 install command。 |
| CI 脚本检查失败 | 先在 `model-gateway/` 本地运行对应 dry-run 命令复现。 |

## 10. 参考入口

- 根快速入口：`README.md`
- Model Gateway 详细说明：`model-gateway/README.md`
- DeepRacer 开源来源图：`deepracer-open-source-navigator/references/source-map.md`
- AWS DeepRacer GitHub 组织：https://github.com/aws-deepracer
- DeepRacer on AWS 源码：https://github.com/aws-solutions/deepracer-on-aws
- DeepRacer on AWS 文档：https://docs.aws.amazon.com/solutions/deepracer-on-aws/
