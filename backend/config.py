"""Application configuration — env vars, paths, constants."""
import os
from pathlib import Path
from dataclasses import dataclass, field

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "sessions"
VIDEO2MOTION_DIR = PROJECT_ROOT / "video2motion"


@dataclass
class Config:
    """Singleton config loaded from env vars with sensible defaults."""

    # LLM
    llm_api_url: str = os.getenv(
        "MOTION_LLM_URL", "https://api.deepseek.com/anthropic/messages"
    )
    llm_api_key: str = os.getenv(
        "MOTION_LLM_KEY", ""
    )
    llm_model: str = os.getenv("MOTION_LLM_MODEL", "deepseek-v4-pro")

    # Paths
    data_dir: Path = DATA_DIR
    v2m_dir: Path = VIDEO2MOTION_DIR
    robot_xml: Path = VIDEO2MOTION_DIR / "robots" / "xxg" / "xxg.xml"
    designer_prompt_path: Path = (
        PROJECT_ROOT / "backend" / "prompts" / "designer.md"
    )
    fixer_prompt_path: Path = (
        PROJECT_ROOT / "backend" / "prompts" / "fixer.md"
    )

    # Execution
    max_concurrency: int = 4
    execution_timeout: int = 120
    max_retries: int = 3

    # GIF
    gif_fps: int = 25
    gif_width: int = 540
    gif_height: int = 405
    gif_max_size_mb: float = 15.0

    # Server
    host: str = "0.0.0.0"
    port: int = int(os.getenv("PORT", "8000"))


config = Config()
