# DeepRacer All In One

这是一个面向 AWS DeepRacer 学习、比赛和二次开发的整合仓库。它本身不复制上游代码，而是通过 Git submodules 固定 AWS DeepRacer 车辆侧、训练侧、仿真侧和示例项目的公开源码版本，同时提供本仓库自有的资料导航和局域网模型分发服务。

完整说明见 [docs/USAGE_AND_DEVELOPMENT.md](docs/USAGE_AND_DEVELOPMENT.md)。

## 仓库内容

- `deepracer-open-source-navigator/` - Codex skill 和资料索引，用来快速定位 DeepRacer 官方仓库、文档和开发入口。
- `model-gateway/` - 本仓库自有的 FastAPI 服务，用于比赛现场模型上传、管理员审核、车辆诊断和模型下发。
- `vehicle-code/` - AWS DeepRacer 车辆侧 ROS2、设备控制、传感器、Web console 和示例项目 submodules。
- `training-code/` - DeepRacer on AWS、仿真器、RL 环境、notebook 和奖励函数相关 submodules。

## 快速开始

推荐直接递归克隆，保证所有 submodules 都被拉取：

```bash
git clone --recurse-submodules https://github.com/rogue-shadowdancer/deepracerallinone.git
cd deepracerallinone
```

如果已经普通克隆过：

```bash
git submodule update --init --recursive
```

检查 submodule 状态：

```bash
git submodule status --recursive
```

## DeepRacer on AWS 连接档案

`config/deepracer.connection.example.json` 是无真实账号、无凭据的版本控制示例。将它复制为 `config/deepracer.connection.local.json`，填入某次部署公开的 CloudFront、API Gateway、Cognito 和上传桶标识，以及本机使用的登录邮箱和邀请 ID；本地文件会被 Git 忽略。密码、Token、Cookie 和 AWS 密钥不属于任何项目配置文件，校验工具会递归拒绝这些字段。

不访问网络即可校验档案结构：

```powershell
py -3 tools\deepracer_connection.py validate config\deepracer.connection.local.json
```

只读实时检查会访问首页和 `/env.js`，逐项比较六个公开运行时字段，并确认未认证 `/profile` 返回 401 或 403。它不会登录、提交表单、读取浏览器存储或覆盖本地档案：

```powershell
py -3 tools\deepracer_connection.py check-live config\deepracer.connection.local.json
```

## 常见使用路径

- 查 DeepRacer 开源资料：阅读 [deepracer-open-source-navigator/references/source-map.md](deepracer-open-source-navigator/references/source-map.md)。
- 部署比赛模型网关：阅读 [model-gateway/README.md](model-gateway/README.md)，或按完整指南中的部署步骤执行。
- 研究车辆侧代码：从 `vehicle-code/aws-deepracer-launcher` 和 `vehicle-code/aws-deepracer-*` packages 开始。
- 研究训练和仿真代码：从 `training-code/deepracer-on-aws`、`training-code/deepsim` 和 `training-code/ude-*` 开始。

## Model Gateway 快速部署

Windows PowerShell:

```powershell
cd model-gateway
.\scripts\deploy-windows.ps1 -Mode competition -AllowInsecureLanCookie -RunTests
```

Linux:

```sh
cd model-gateway
./scripts/deploy-linux.sh --mode competition --allow-insecure-lan-cookie --run-tests
```

启动后默认入口：

- 用户登录：`http://<gateway-host>:8080/login`
- 管理员登录：`http://<gateway-host>:8080/admin/login`

比赛环境必须替换默认管理员密码、设置 `GATEWAY_SESSION_SECRET` 和 `GATEWAY_CREDENTIAL_SECRET`，并根据是否使用 HTTPS 正确配置 cookie 安全选项。

## 开发与验证

本仓库根目录主要维护文档、submodule 指针和 `model-gateway`。修改 `model-gateway` 前建议使用 Python 3.10+：

```powershell
cd model-gateway
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
python -m compileall src tests
python -m pytest tests
```

推送前在仓库根目录执行：

```bash
git diff --check
git status --short --branch
```

更多开发、测试、子模块维护和 GitHub 推送策略见 [docs/USAGE_AND_DEVELOPMENT.md](docs/USAGE_AND_DEVELOPMENT.md)。

## 上游来源

主要上游公开源码和文档：

- https://github.com/aws-deepracer
- https://github.com/aws-solutions/deepracer-on-aws
- https://docs.aws.amazon.com/solutions/deepracer-on-aws/

本仓库只在需要记录固定版本时提交 submodule 指针更新；常规研究和本地实验应优先在对应上游 submodule 内完成。
