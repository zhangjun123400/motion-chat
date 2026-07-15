"""File-based session persistence — one directory per session."""
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.config import config


class SessionStore:
    def __init__(self) -> None:
        self.data_dir = config.data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _session_dir(self, session_id: str) -> Path:
        return self.data_dir / session_id

    def _conv_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "conversation.json"

    def _load_conv(self, session_id: str) -> dict:
        path = self._conv_path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"session {session_id} not found")
        return json.loads(path.read_text())

    def _save_conv(self, session_id: str, conv: dict) -> None:
        self._conv_path(session_id).write_text(
            json.dumps(conv, ensure_ascii=False, indent=2)
        )

    def create(self, title: str) -> str:
        sid = f"sess_{uuid.uuid4().hex[:12]}"
        conv = {
            "session_id": sid,
            "title": title,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "robot_model": "xxg",
            "messages": [],
            "artifacts": [],
        }
        self._session_dir(sid).mkdir(parents=True, exist_ok=True)
        self._save_conv(sid, conv)
        return sid

    def get(self, session_id: str) -> dict | None:
        try:
            return self._load_conv(session_id)
        except FileNotFoundError:
            return None

    def list_all(self) -> list[dict]:
        sessions = []
        for d in sorted(
            self.data_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            if d.is_dir():
                try:
                    conv = self._load_conv(d.name)
                    sessions.append({
                        "session_id": conv["session_id"],
                        "title": conv["title"],
                        "created_at": conv["created_at"],
                        "artifact_count": len(conv.get("artifacts", [])),
                    })
                except (FileNotFoundError, json.JSONDecodeError, KeyError):
                    continue
        return sessions

    def delete(self, session_id: str) -> None:
        shutil.rmtree(self._session_dir(session_id), ignore_errors=True)

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        artifact_id: str | None = None,
    ) -> None:
        conv = self._load_conv(session_id)
        msg = {"role": role, "content": content}
        if artifact_id:
            msg["artifact_id"] = artifact_id
        conv["messages"].append(msg)
        self._save_conv(session_id, conv)

    def add_artifact(self, session_id: str, artifact_id: str) -> Path:
        conv = self._load_conv(session_id)
        art_dir = self._session_dir(session_id) / artifact_id
        art_dir.mkdir(parents=True, exist_ok=True)
        art = {
            "artifact_id": artifact_id,
            "script_path": str(art_dir / "generate.py"),
            "csv_path": str(art_dir / "motion.csv"),
            "gif_path": str(art_dir / "motion.gif"),
            "quality_report": {},
            "review_status": "pending",
            "parent_id": None,
        }
        if conv.get("artifacts"):
            art["parent_id"] = conv["artifacts"][-1]["artifact_id"]
        conv["artifacts"].append(art)
        self._save_conv(session_id, conv)
        return art_dir

    def update_artifact_quality(
        self, session_id: str, artifact_id: str, quality: dict
    ) -> None:
        conv = self._load_conv(session_id)
        for art in conv["artifacts"]:
            if art["artifact_id"] == artifact_id:
                art["quality_report"] = quality
                break
        self._save_conv(session_id, conv)

    def get_last_script(self, session_id: str) -> tuple[str, dict] | None:
        """Return (script_content, quality_report) of the last artifact."""
        conv = self._load_conv(session_id)
        if not conv.get("artifacts"):
            return None
        last = conv["artifacts"][-1]
        script_path = Path(last["script_path"])
        if not script_path.exists():
            return None
        return script_path.read_text(), last.get("quality_report", {})
