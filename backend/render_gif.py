"""Render CSV motion to GIF via MuJoCo offscreen + ffmpeg two-pass encoding."""
import asyncio
import csv
import math
import os
import tempfile
from pathlib import Path

import numpy as np

from backend.config import config


CSV_TO_MODEL_JOINT = {
    "FBL_ABAD_JOINT_y": "FBL_ABAD_JOINT", "FBL_HIP_JOINT_y": "FBL_HIP_JOINT",
    "FBL_KNEE_JOINT_y": "FBL_KNEE_JOINT", "FAR_ABAD_JOINT_y": "FAR_ABAD_JOINT",
    "FAR_HIP_JOINT_y": "FAR_HIP_JOINT", "FAR_KNEE_JOINT_y": "FAR_KNEE_JOINT",
    "RAR_ABAD_JOINT_y": "RAR_ABAD_JOINT", "RAR_HIP_JOINT_y": "RAR_HIP_JOINT",
    "RAR_KNEE_JOINT_y": "RAR_KNEE_JOINT", "RBL_ABAD_JOINT_y": "RBL_ABAD_JOINT",
    "RBL_HIP_JOINT_y": "RBL_HIP_JOINT", "RBL_KNEE_JOINT_y": "RBL_KNEE_JOINT",
    "NECK_JOINT_y": "NECK_YAW_JOINT", "HEAD_JOINT_y": "HEAD_PITCH_JOINT",
    "MOUTH_JOINT_y": "MOUTH_PITCH_JOINT", "EAR_JOINT_y": "EAR_PITCH_JOINT",
    "TAIL_JOINT_y": "TAIL_YAW_JOINT",
}

INTERP_COLS = list(CSV_TO_MODEL_JOINT.keys()) + [
    "BASE_JOINT_x", "BASE_JOINT_y", "BASE_JOINT_z",
    "BASE_JOINT_rx", "BASE_JOINT_ry", "BASE_JOINT_rz",
]


def _rpy_to_quat(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr = math.cos(roll * 0.5); sr = math.sin(roll * 0.5)
    cp = math.cos(pitch * 0.5); sp = math.sin(pitch * 0.5)
    cy = math.cos(yaw * 0.5); sy = math.sin(yaw * 0.5)
    q = np.array([
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    ])
    return q / np.linalg.norm(q)


async def render_gif(
    csv_path: Path,
    output_path: Path,
    xml_path: Path | None = None,
) -> Path:
    """Render a CSV motion file to GIF. Returns the path to the generated GIF."""
    import mujoco
    import imageio_ffmpeg
    import imageio as iio

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    if xml_path is None:
        xml_path = config.robot_xml

    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    dt_csv = float(rows[1]["time"]) - float(rows[0]["time"])

    csv_times = np.arange(len(rows)) * dt_csv
    duration = csv_times[-1]
    n_out = int(duration * config.gif_fps) + 1
    interp_rows = []
    for k in range(n_out):
        t = k / config.gif_fps
        idx = np.searchsorted(csv_times, t, side="right") - 1
        idx = max(0, min(idx, len(rows) - 2))
        t0, t1 = csv_times[idx], csv_times[idx + 1]
        alpha = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
        alpha = max(0.0, min(1.0, alpha))
        ra, rb = rows[idx], rows[idx + 1]
        frame = {}
        for col in INTERP_COLS:
            if col in ra and col in rb:
                frame[col] = float(ra[col]) + (float(rb[col]) - float(ra[col])) * alpha
        interp_rows.append(frame)

    model = mujoco.MjModel.from_xml_path(str(xml_path))
    data = mujoco.MjData(model)
    renderer = mujoco.Renderer(model, config.gif_height, config.gif_width)

    joint_addrs = {}
    for cn, mn in CSV_TO_MODEL_JOINT.items():
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, mn)
        joint_addrs[cn] = model.jnt_qposadr[jid]

    camera = mujoco.MjvCamera()
    camera.type = mujoco.mjtCamera.mjCAMERA_FREE
    camera.distance = 1.0
    camera.azimuth = 135
    camera.elevation = -20
    camera.lookat[:] = [0.10, 0.05, 0.18]

    tmpdir = tempfile.mkdtemp(prefix="mujoco_gif_")
    try:
        for i, frame in enumerate(interp_rows):
            bx = float(frame.get("BASE_JOINT_x", 0))
            byz = float(frame.get("BASE_JOINT_y", 0))
            bzy = float(frame.get("BASE_JOINT_z", 0))

            data.qpos[0:3] = [bx, bzy, byz]
            rx = math.radians(float(frame.get("BASE_JOINT_rx", 0)))
            ry = math.radians(float(frame.get("BASE_JOINT_ry", 0)))
            rz = math.radians(float(frame.get("BASE_JOINT_rz", 0)))
            data.qpos[3:7] = _rpy_to_quat(rx, ry, rz)

            for cn, addr in joint_addrs.items():
                if cn in frame:
                    data.qpos[addr] = math.radians(float(frame[cn]))

            mujoco.mj_forward(model, data)
            camera.lookat[:] = [bx, 0.05, 0.18]
            renderer.update_scene(data, camera)
            pixels = renderer.render()
            out = os.path.join(tmpdir, f"frame_{i:06d}.png")
            iio.imwrite(out, pixels)

        palette = os.path.join(tmpdir, "palette.png")
        cmd_pal = [
            ffmpeg, "-y",
            "-framerate", str(config.gif_fps),
            "-i", os.path.join(tmpdir, "frame_%06d.png"),
            "-vf", "palettegen=stats_mode=diff",
            palette,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd_pal, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()

        cmd_gif = [
            ffmpeg, "-y",
            "-framerate", str(config.gif_fps),
            "-i", os.path.join(tmpdir, "frame_%06d.png"),
            "-i", palette,
            "-lavfi", "paletteuse=dither=bayer:bayer_scale=2",
            "-loop", "1",
            str(output_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd_gif, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
        renderer.close()

    return output_path
