# Motion Chat — 机器狗动作生成聊天工具

通过自然语言描述，自动生成四足机器狗动作 CSV + GIF。

## 快速启动

```bash
./run.sh
# 浏览器打开 http://localhost:8000
```

## 前置依赖

- Python 3.12+ with mujoco, fastapi, uvicorn, httpx
- ffmpeg (GIF 编码)
- Node.js 20+ (前端构建)

## API 文档

启动后访问 http://localhost:8000/docs 查看 Swagger UI。

## 目录结构

- `backend/` — FastAPI 后端
- `frontend/` — Vue 3 + Vite 前端
- `video2motion/` — 符号链接到现有运动学代码库
- `data/sessions/` — 会话持久化存储
