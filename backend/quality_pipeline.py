"""Quality check pipeline — runs check_csv, diagnose_feet, smoothness_check as subprocesses."""
import asyncio
import os
from pathlib import Path

from backend.config import config


def _parse_check_output(output: str) -> dict:
    """Parse check_csv.py text output into structured dict."""
    result = {"violations": 0, "base_active": True}
    for line in output.split("\n"):
        if "Violations:" in line:
            try:
                result["violations"] = int(line.split(":")[1].strip())
            except ValueError:
                pass
        if "Base active:" in line:
            result["base_active"] = "YES" in line
    return result


def _parse_diagnose_output(output: str) -> dict:
    """Parse diagnose_feet.py text output into structured dict."""
    result = {"penetration": False, "max_penetration_cm": 0.0, "details": []}
    for line in output.split("\n"):
        if "PENETRATION!" in line:
            result["penetration"] = True
            result["details"].append(line.strip())
            try:
                cm = float(line.split("=")[-1].replace("cm", "").strip())
                result["max_penetration_cm"] = max(
                    result["max_penetration_cm"], cm
                )
            except ValueError:
                pass
    return result


def _parse_smoothness_output(output: str) -> dict:
    """Parse smoothness_check.py text output into structured dict."""
    passed = "SMOOTHNESS: PASS" in output
    max_delta = 0.0
    for line in output.split("\n"):
        if "Avg max joint delta:" in line:
            try:
                max_delta = float(line.split(":")[1].strip().split()[0])
            except (ValueError, IndexError):
                pass
    return {"passed": passed, "max_joint_delta": max_delta}


async def run_quality_checks(csv_path: Path, working_dir: Path) -> dict:
    """Run all three checks and return a unified quality report."""
    checks = [
        ("check", config.v2m_dir / "check_csv.py", _parse_check_output),
        ("diagnose", config.v2m_dir / "diagnose_feet.py", _parse_diagnose_output),
        ("smoothness", config.v2m_dir / "smoothness_check.py", _parse_smoothness_output),
    ]

    report: dict = {"overall": "PASS"}
    errors: list[str] = []

    for name, script, parser in checks:
        try:
            proc = await asyncio.create_subprocess_exec(
                "python3",
                str(script),
                str(csv_path),
                cwd=str(working_dir),
                env={**os.environ, "PYTHONPATH": str(config.v2m_dir)},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=30
            )
            output = stdout.decode("utf-8", errors="replace")
            parsed = parser(output)
            report[name] = parsed

            if name == "check" and (parsed["violations"] > 0 or not parsed["base_active"]):
                report["overall"] = "FAIL"
                if parsed["violations"] > 0:
                    errors.append(f"check_csv: {parsed['violations']} joint limit violations")
                if not parsed["base_active"]:
                    errors.append("check_csv: base has static columns (no 6-DOF participation)")
            elif name == "diagnose" and parsed["penetration"]:
                report["overall"] = "FAIL"
                errors.append(f"diagnose_feet: foot penetration detected, max={parsed['max_penetration_cm']}cm")
            elif name == "smoothness" and not parsed["passed"]:
                report["overall"] = "FAIL"
                errors.append(f"smoothness_check: frame-to-frame jerk detected, max_delta={parsed['max_joint_delta']:.1f} deg/frame")

        except asyncio.TimeoutError:
            report[name] = {"error": "timeout"}
            report["overall"] = "FAIL"
            errors.append(f"{name}: check timed out")
        except Exception as e:
            report[name] = {"error": str(e)}
            report["overall"] = "FAIL"
            errors.append(f"{name}: {e}")

    report["errors"] = errors
    return report
