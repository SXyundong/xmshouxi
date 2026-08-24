# 电商公司多部门 Agent 系统 V1

一个可扩展的电商多部门 AI Agent 基础框架。V1 聚焦「基础架构」，实现前端部门入口 + 聊天页面、后端 Agent 运行框架、Agent 路由、Tool 调用框架、统一 LLM 调用与基础日志。

## 技术栈

- 前端：Next.js 14 + TypeScript + Tailwind CSS
- 后端：Python + FastAPI
- 部署：Docker + Docker Compose

## 目录结构

```
ecommerce-agent-v1/
├── frontend/                 # Next.js 前端
│   └── src/
│       ├── app/              # 页面（/ 及 9 个部门路由）
│       ├── components/       # 部门卡片、聊天组件
│       └── services/         # API 调用、部门配置
├── backend/                  # FastAPI 后端
│   └── app/
│       ├── main.py           # 应用入口
│       ├── api/chat.py       # Chat 接口
│       ├── agents/           # BaseAgent + 9 个 Agent + 注册中心
│       ├── tools/            # BaseTool + Mock 领星 Tool + 注册中心
│       ├── core/             # AgentEngine、LLMClient
│       ├── models/           # 请求/响应模型
│       └── config/           # 配置（读取 .env）
├── docker-compose.yml
└── README.md
```

## 部门路由

首页 `/` 展示 9 个部门卡片，点击进入对应 Agent 聊天页：

| 路由 | 部门 | Agent |
| --- | --- | --- |
| `/sales` | 销售 | 销售分析Agent |
| `/inventory` | 库存 | 库存Agent |
| `/logistics` | 物流 | 物流Agent |
| `/product` | 选品 | 选品Agent |
| `/ads` | 广告 | 广告Agent |
| `/operation` | 运营 | 运营Agent |
| `/finance` | 财务 | 财务Agent |
| `/design` | 美工 | 美工Agent |
| `/hr` | 招聘 | 招聘Agent |

## 架构说明

- **Agent 路由**：`POST /api/chat` 收到 `{department, message}` 后，由 `AgentEngine` 从 `AgentRegistry` 找到对应 Agent 并执行。
- **BaseAgent**：统一负责接收用户输入、管理工具、调用 LLM、返回结果。所有 Agent 继承它，业务逻辑不写在 API 里。
- **Tool 框架**：所有 Tool 继承 `BaseTool`，通过 `ToolRegistry` 按名称注册/获取，与 Agent 解耦。
- **Mock 领星 Tool**：`lingxing_sales` 当前返回 mock 数据，未来替换为真实领星 API 即可。
- **LLM Client**：统一入口 `LLMClient.chat()`，从 `.env` 读取 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `MODEL`。Agent 不直接调用 OpenAI。
- **基础日志**：使用 `uvicorn` 标准访问日志；业务侧通过 Python `logging` 扩展。

## 环境变量

后端（`backend/.env` 或 Docker Compose 根目录 `.env`）：

| 变量 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | 否 | 空 | 不填时返回本地 mock 回复 |
| `OPENAI_BASE_URL` | 否 | `https://api.openai.com/v1` | 兼容 OpenAI 协议的网关地址 |
| `MODEL` | 否 | `gpt-4o-mini` | 模型名称 |

前端（`frontend/.env`，仅本地开发用）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `BACKEND_URL` | `http://localhost:8000` | 后端地址，Docker 内自动为 `http://backend:8000` |

## 一、Docker 部署（推荐）

前置：已安装 Docker 与 Docker Compose。

```bash
cd ecommerce-agent-v1

# 可选：配置 LLM（不配也能跑，返回 mock）
cp .env.example .env   # 然后编辑 .env 填入 OPENAI_API_KEY

# 构建并启动
docker compose up --build -d

# 查看运行状态
docker compose ps
```

启动完成后访问：

- 前端首页：<http://localhost:3000>
- 后端接口文档（Swagger）：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/>

常用命令：

```bash
docker compose logs -f        # 查看日志
docker compose restart        # 重启
docker compose down           # 停止并删除容器
docker compose down -v        # 停止并删除容器 + 数据卷
```

## 二、本地开发运行（不使用 Docker）

### 1. 启动后端

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

# 可选：配置 LLM
cp .env.example .env

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 <http://localhost:3000>。

## API 示例

`POST /api/chat`

请求：

```json
{
  "department": "sales",
  "message": "昨天销售怎么样"
}
```

响应：

```json
{
  "agent": "销售分析Agent",
  "answer": "..."
}
```

## 扩展方式

- 新增 Agent：在 `backend/app/agents/` 新建文件继承 `BaseAgent`，然后在 `agents/registry.py` 注册。
- 新增 Tool：在 `backend/app/tools/` 新建文件继承 `BaseTool`，然后在 `tools/registry.py` 注册。
- 替换真实领星 API：修改 `backend/app/tools/lingxing_tool.py` 的 `execute()`。

## 物流销量写入备货表工作流

物流部门页面右侧工具栏提供“健腹轮销量写入备货表”工作流。执行时会：

1. 通过领星 Streamable HTTP MCP 查询 SKU `70017-3`；
2. 分别统计包含当天在内的近 3、7、15、30 天销量；
3. 校验 `Sheet1!A156` 为 `70017-3`、`C156` 为 `健腹轮（黑色）`；
4. 将销量依次写入 `Sheet1!AJ156:AM156`；
5. 写入前创建 `备货逻辑看板表.workflow-backup.xlsx` 备份。

需要在根目录 `.env` 配置以下本地变量（`.env` 不会提交到 Git）：

```dotenv
LINGXING_MCP_URL=https://openmcp.lingxing.com/mcp-servers/lingxing-mcp
LINGXING_MCP_KEY=<领星 MCP Key>
STOCK_WORKBOOK_PATH=\\192.168.12.158\e\备货逻辑看板表.xlsx
SMB_USERNAME=<网络共享用户名>
SMB_PASSWORD=<网络共享密码>
```

领星账号需要拥有“亚马逊 → 统计 → 产品表现 → 查看”权限。Docker 无法继承 Windows 当前用户的 SMB 登录会话，因此容器部署时必须显式配置 `SMB_USERNAME` 和 `SMB_PASSWORD`；Windows 原生运行后端且 UNC 已登录时可不配置这两项。
