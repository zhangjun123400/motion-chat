"""FastAPI application — session CRUD, chat endpoint, file serving."""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.config import config
from backend.session_store import SessionStore

app = FastAPI(title="Motion Chat")
store = SessionStore()


@app.get("/api/sessions")
async def list_sessions():
    return store.list_all()


@app.post("/api/sessions")
async def create_session(request: Request):
    body = await request.json()
    title = body.get("title", "新会话")
    session_id = store.create(title)
    return {"session_id": session_id}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    conv = store.get(session_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="session not found")
    return conv


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    store.delete(session_id)
    return {"ok": True}


@app.get("/api/files/{session_id}/{artifact_id}/{filename}")
async def download_file(session_id: str, artifact_id: str, filename: str):
    path = Path(store._session_dir(session_id)) / artifact_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path)



# --- Chat endpoint (SSE streaming) ---
import csv  # noqa: E402

from backend.llm_proxy import LLMProxy
from backend.executor import run_script
from backend.quality_pipeline import run_quality_checks
from backend.render_gif import render_gif

llm = LLMProxy()


@app.post("/api/chat/{session_id}")
async def chat(session_id: str, request: Request):
    """SSE streaming chat endpoint — orchestrates generate→execute→quality→render pipeline."""
    body = await request.json()
    user_message = body["message"]

    conv = store.get(session_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="session not found")

    async def event_stream():
        last = store.get_last_script(session_id)
        is_iteration = last is not None

        # Phase 1: LLM Generation
        yield f"event: status\ndata: {_sse('正在分析动作需求...')}\n\n"

        full_output = ""
        if is_iteration:
            prev_script, prev_quality = last
            quality_str = json.dumps(prev_quality, ensure_ascii=False, indent=2)
            async for chunk in llm.fix_stream(
                errors=quality_str, script=prev_script
            ):
                full_output += chunk
                yield f"event: thinking\ndata: {_sse(chunk)}\n\n"
        else:
            async for chunk in llm.generate_stream(user_message, None):
                full_output += chunk
                yield f"event: thinking\ndata: {_sse(chunk)}\n\n"

        # Phase 2: Code extraction + save
        yield f"event: status\ndata: {_sse('正在提取代码...')}\n\n"
        try:
            code = llm.extract_code(full_output)
        except ValueError as e:
            yield f"event: error\ndata: {_sse(str(e))}\n\n"
            return

        yield f"event: code\ndata: {_sse(code)}\n\n"

        artifact_id = f"gen_{len(conv.get('artifacts', [])) + 1:03d}"
        art_dir = store.add_artifact(session_id, artifact_id)
        script_path = art_dir / "generate.py"
        script_path.write_text(code)

        # Phase 3: Execute with retry loop
        max_retries = config.max_retries
        quality = {"overall": "FAIL"}
        retry_count = 0

        for attempt in range(max_retries + 1):
            retry_count = attempt
            yield f"event: status\ndata: {_sse(f'正在执行生成脚本... (尝试 {attempt+1}/{max_retries+1})')}\n\n"

            ok, output = await run_script(art_dir)
            csv_path = art_dir / "motion.csv"

            if not ok or not csv_path.exists():
                if attempt < max_retries:
                    yield f"event: status\ndata: {_sse('脚本执行失败，正在修复...')}\n\n"
                    full_output = ""
                    async for chunk in llm.fix_stream(
                        errors=f"Execution failed:\n{output[-2000:]}", script=code
                    ):
                        full_output += chunk
                    try:
                        code = llm.extract_code(full_output)
                        script_path.write_text(code)
                        yield f"event: code\ndata: {_sse(code)}\n\n"
                    except ValueError:
                        pass
                    continue
                else:
                    yield f"event: error\ndata: {_sse(f'脚本执行失败: {output[-500:]}')}\n\n"
                    return

            # Phase 4: Quality Checks
            yield f"event: status\ndata: {_sse('正在质检...')}\n\n"
            quality = await run_quality_checks(csv_path, art_dir)

            if quality["overall"] == "PASS":
                break

            if attempt < max_retries:
                error_details = "\n".join(quality.get("errors", []))
                yield f"event: status\ndata: {_sse(f'质检未通过，自动修复中 ({attempt+1}/{max_retries})...')}\n\n"
                full_output = ""
                async for chunk in llm.fix_stream(
                    errors=f"Quality check failed:\n{error_details}",
                    script=code,
                ):
                    full_output += chunk
                try:
                    code = llm.extract_code(full_output)
                    script_path.write_text(code)
                    yield f"event: code\ndata: {_sse(code)}\n\n"
                except ValueError:
                    pass

        # Save quality report
        (art_dir / "quality.json").write_text(
            json.dumps(quality, ensure_ascii=False, indent=2)
        )
        store.update_artifact_quality(session_id, artifact_id, quality)

        # Phase 5: Render GIF
        yield f"event: status\ndata: {_sse('正在渲染 GIF...')}\n\n"
        gif_path = art_dir / "motion.gif"
        try:
            await render_gif(csv_path, gif_path)
        except Exception as e:
            yield f"event: error\ndata: {_sse(f'GIF 渲染失败: {e}')}\n\n"
            return

        # Phase 6: Build result
        csv_url = f"/api/files/{session_id}/{artifact_id}/motion.csv"
        gif_url = f"/api/files/{session_id}/{artifact_id}/motion.gif"
        stats = {
            "frames": 0,
            "duration_s": 0,
            "dt": 0.02,
            "retry_count": retry_count,
        }
        if csv_path.exists():
            with csv_path.open() as f:
                reader = csv.DictReader(f)
                rows_list = list(reader)
                if len(rows_list) >= 2:
                    stats["frames"] = len(rows_list)
                    stats["duration_s"] = float(rows_list[-1]["time"])
                    stats["dt"] = float(rows_list[1]["time"]) - float(rows_list[0]["time"])

        result = {
            "artifact_id": artifact_id,
            "script": code,
            "csv_url": csv_url,
            "gif_url": gif_url,
            "quality": quality,
            "stats": stats,
        }

        store.add_message(session_id, "user", user_message)
        store.add_message(
            session_id, "assistant",
            full_output.split("```python")[0].split("```")[0][:200],
            artifact_id,
        )

        yield f"event: done\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(text: str) -> str:
    """Escape text for SSE data field."""
    return text.replace("\n", "\\n").replace('"', '\\"')

# Serve frontend static files in production
frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.host, port=config.port)
