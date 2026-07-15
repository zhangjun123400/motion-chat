# Motion Chat 项目文档

> 机器狗动作设计聊天工具 — 通过自然语言聊天生成四足机器狗运动轨迹 CSV + GIF 动画。

## 项目概述

内部团队成员在 Web 浏览器中用自然语言描述动作需求（如「开心小跑」「坐下握手」），后端调用 DeepSeek LLM 将描述转为 Python 脚本，自动执行脚本生成 24 列关节角 CSV，经质检流水线后渲染为 GIF 动画，前端实时展示进度和结果。

```
用户输入自然语言 → LLM 生成 generate.py → 子进程执行 → 质检 → MuJoCo 渲染 GIF → 前端展示
```

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | FastAPI + SSE 流式响应 |
| 前端 | Vue 3 (单文件组件) + Vite + Tailwind CSS |
| LLM | DeepSeek V4 Pro（Anthropic 兼容 API） |
| 运动学 | video2motion 代码库（FK/IK 管线、MuJoCo 渲染） |
| 存储 | 文件 JSON 持久化（`data/sessions/`） |

## 关键文件

### 后端 (`backend/`)

| 文件 | 职责 |
|------|------|
| `main.py` | FastAPI 入口。SSE 聊天端点 `/api/chat/{id}` 编排完整流水线：LLM 生成→执行→质检→GIF。**chat 端点必须在 `app.mount("/")` 之前注册** |
| `config.py` | 配置 dataclass。LLM 参数走 `MOTION_LLM_*` 环境变量（**与 Claude Code 完全隔离**） |
| `llm_proxy.py` | LLM API 代理。流式调用 DeepSeek，支持 generate/fix 两种模式。代码块提取用正则 `\`\`\`python` |
| `executor.py` | 子进程隔离执行 `generate.py`。设置 `PYTHONPATH`、`MOTION_XML_PATH`、`EGL_PLATFORM=surfaceless`，带 asyncio 信号量并发控制 |
| `quality_pipeline.py` | 质检编排。依次运行 check_csv / diagnose_feet / smoothness_check，解析文本输出为结构化报告 |
| `render_gif.py` | MuJoCo → GIF。加载 CSV 回放，ffmpeg 两遍编码（palettegen + paletteuse），25fps、loop=1 |
| `session_store.py` | 文件会话存储。`data/sessions/{sid}/` 下存 `conversation.json` + 每个 artifact 子目录 |
| `prompts/designer.md` | 动作设计师 system prompt（含 IK API 文档、代码模板） |
| `prompts/fixer.md` | 修复专家 system prompt（质检失败时自动修复） |

### 前端 (`frontend/src/App.vue`)

单文件 Vue 3 应用，包含：
- 左侧会话列表（新建/切换）
- 中间聊天区（消息气泡、进度时间线、思考输出）
- 结果面板（代码预览、GIF 预览、质检卡片、下载按钮）
- SSE 手动解析（`response.body.getReader()` + 行解析）

### video2motion 代码库（外部依赖）

路径：`/Users/zhangjun/Documents/jiqigou-pm/video2motion/`
motion-chat 通过符号链接 `video2motion -> ../video2motion` 引用。

核心 IK 模块：`generate_sit_handshake_csv.py`

**LLM 可调用的真实函数（已在 designer.md 中列出）：**
- `parse_model(xml_path)` → `(home_joint_values, joint_ranges, leg_specs, foot_radius)`
- `leg_fk(leg_spec, q)` → body-frame (x,y,z) 位置
- `solve_leg_ik(leg_spec, target_body, q_seed)` → `(q, error)` — 单腿 IK
- `rpy_matrix(roll, pitch, yaw)` → 3x3 旋转矩阵
- `ease_in_out(t)`, `interpolate_dict(a,b,t)`, `build_pose(base,extras)`, `rad(deg)`, `lerp(a,b,t)`

**关键常量：** `LEG_PREFIXES = ("FBL", "FAR", "RBL", "RAR")`、`LEG_LIMITS`、`DT=0.05`、`CSV_COLUMNS`、`LEG_CSV_COLUMNS`、`EXTRA_JOINT_COLUMNS`

**CSV 格式：** 24 列，坐标轴交换（CSV y = MuJoCo z 高度，CSV z = MuJoCo y 侧向），角度单位度，DT=0.02

机器人模型 `xxg`（17 自由度：12 腿 + 5 头），XML 在 `robots/xxg/xxg.xml`

## 已修复的关键 bug

1. **SSE 405 错误** — `app.mount("/")` 必须在所有路由之后注册（main.py）
2. **LLM 虚构函数名** — `forward_kinematics()`、`solve_ik()`、`get_home_pose()` 不存在，已在 prompt 中加入真实 API 文档并标记禁止
3. **代码被截断** — max_tokens 8192→16384，prompt 开头强制代码优先输出
4. **历史会话不显示结果** — `select()` 从 artifacts 重建 result 对象
5. **GIF 显示为视频** — `<video>` 改为 `<img>`（浏览器原生显示 GIF）
6. **mujoco 未安装** — `pip install mujoco --break-system-packages`

## 环境变量（.env）

```
MOTION_LLM_URL=https://api.deepseek.com/anthropic/messages
MOTION_LLM_MODEL=deepseek-v4-pro
MOTION_LLM_KEY=sk-d7f16692307942e0be4e40ed59189bc5
PORT=8000
```

`.env` 已 gitignore，`.env.example` 作为模板提交到 GitHub。

## 启动

```bash
cd /Users/zhangjun/Documents/jiqigou-pm/motion-chat
export $(grep -v '^#' .env | xargs)
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
# 或 ./run.sh
```

前端修改后重建：`npm --prefix frontend run build`

## 当前状态

- ✅ 完整流水线可运行（LLM 生成→执行→质检→GIF 渲染）
- ✅ GitHub：https://github.com/zhangjun123400/motion-chat
- ✅ LLM 与 Claude Code 完全隔离（独立 env var + 独立 API）
- ⚠️ 质检 FAIL 仅作优化建议，不阻断输出（最多自动重试 3 次）
- ⚠️ 无认证，仅供内网使用

## 待办方向

- 进程隔离 → Docker 容器隔离（生产部署）
- GIF 播放控件（暂停/循环/逐帧）
- 人工审核工作流
