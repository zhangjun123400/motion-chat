"""Subprocess execution engine with timeout, isolation, and concurrency control."""
import asyncio
import os
from pathlib import Path

from backend.config import config

_semaphore = asyncio.Semaphore(config.max_concurrency)


async def run_script(working_dir: Path) -> tuple[bool, str]:
    """Execute generate.py in the given working directory.

    Returns (success: bool, output: str).
    The working_dir must contain generate.py.
    The script is run from working_dir with video2motion in sys.path.
    """
    script = working_dir / "generate.py"
    if not script.exists():
        return False, f"Script not found: {script}"

    env = os.environ.copy()
    env["EGL_PLATFORM"] = "surfaceless"
    env["PYTHONPATH"] = str(config.v2m_dir)
    env["MOTION_XML_PATH"] = str(config.robot_xml)

    try:
        proc = await asyncio.create_subprocess_exec(
            "python3",
            str(script),
            cwd=str(working_dir),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=config.execution_timeout
        )
        output = stdout.decode("utf-8", errors="replace")
        if stderr:
            output += "\n[STDERR]\n" + stderr.decode("utf-8", errors="replace")
        success = proc.returncode == 0
        return success, output
    except asyncio.TimeoutError:
        return False, f"Execution timed out after {config.execution_timeout}s"
    except Exception as e:
        return False, f"Execution error: {e}"
