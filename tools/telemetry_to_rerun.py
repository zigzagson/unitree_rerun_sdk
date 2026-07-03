#!/usr/bin/env python3
"""Convert unitree_rerun telemetry.bin files to Rerun time-series .rrd recordings."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import rerun as rr

from telemetry_bin import iter_samples, motor_names, read_header


def latest_session_dir(logs_dir: Path = Path("unitree_logs")) -> Path:
    sessions = sorted(path for path in logs_dir.iterdir() if (path / "telemetry.bin").is_file())
    if not sessions:
        raise FileNotFoundError(f"no telemetry sessions found under {logs_dir}")
    return sessions[-1]


def resolve_input_path(input_path: Path | None) -> Path:
    if input_path is None:
        return latest_session_dir() / "telemetry.bin"
    if input_path.is_dir():
        return input_path / "telemetry.bin"
    return input_path


def log_static_series(motor_count: int) -> None:
    names = motor_names(motor_count)
    for path in (
        "robot/motors/q",
        "robot/motors/dq",
        "robot/motors/tau_est",
        "robot/motors/temp_case",
        "robot/motors/temp_winding",
        "robot/motors/state",
    ):
        rr.log(path, rr.SeriesLines(names=names), static=True)

    rr.log("robot/imu/rpy", rr.SeriesLines(names=["roll", "pitch", "yaw"]), static=True)
    rr.log("robot/imu/gyro", rr.SeriesLines(names=["gx", "gy", "gz"]), static=True)
    rr.log("robot/imu/accel", rr.SeriesLines(names=["ax", "ay", "az"]), static=True)
    rr.log(
        "robot/health/summary",
        rr.SeriesLines(
            names=["max_temp", "max_temp_motor", "imu_temp", "max_abs_tau", "max_abs_dq", "dropped"]
        ),
        static=True,
    )


def log_sample(sample: dict) -> None:
    rr.set_time("unix_time", timestamp=np.datetime64(sample["unix_time_ns"], "ns"))
    rr.set_time("sequence", sequence=sample["sequence"])

    rr.log("robot/motors/q", rr.Scalars(sample["q"]))
    rr.log("robot/motors/dq", rr.Scalars(sample["dq"]))
    rr.log("robot/motors/tau_est", rr.Scalars(sample["tau"]))
    rr.log("robot/motors/temp_case", rr.Scalars(sample["temp_case"]))
    rr.log("robot/motors/temp_winding", rr.Scalars(sample["temp_winding"]))
    rr.log("robot/motors/state", rr.Scalars(sample["motor_state"]))

    rr.log("robot/imu/rpy", rr.Scalars(sample["imu_rpy"]))
    rr.log("robot/imu/gyro", rr.Scalars(sample["imu_gyro"]))
    rr.log("robot/imu/accel", rr.Scalars(sample["imu_accel"]))
    rr.log("robot/imu/temperature", rr.Scalars([sample["imu_temp"]]))

    hottest = [max(a, b) for a, b in zip(sample["temp_case"], sample["temp_winding"])]
    max_temp = max(hottest) if hottest else math.nan
    max_temp_motor = hottest.index(max_temp) if hottest else -1
    max_abs_tau = max((abs(x) for x in sample["tau"]), default=math.nan)
    max_abs_dq = max((abs(x) for x in sample["dq"]), default=math.nan)
    rr.log(
        "robot/health/summary",
        rr.Scalars(
            [
                max_temp,
                max_temp_motor,
                sample["imu_temp"],
                max_abs_tau,
                max_abs_dq,
                sample["dropped_samples"],
            ]
        ),
    )


def default_output_path(input_path: Path) -> Path:
    if input_path.name == "telemetry.bin":
        return input_path.with_name("recording.rrd")
    return input_path.with_suffix(".rrd")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        help="Path to telemetry.bin or a session directory. Default: latest unitree_logs session",
    )
    parser.add_argument("-o", "--output", type=Path, help="Output .rrd path")
    parser.add_argument("--max-samples", type=int, default=0, help="Convert at most this many samples")
    args = parser.parse_args()

    input_path = resolve_input_path(args.input)
    output = args.output or default_output_path(input_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open("rb") as f:
        header = read_header(f)
        motor_count = int(header["motor_count"])
        rr.init("unitree_lowstate_telemetry", spawn=False)
        rr.save(output)
        log_static_series(motor_count)

        count = 0
        for sample in iter_samples(f, motor_count):
            log_sample(sample)
            count += 1
            if args.max_samples and count >= args.max_samples:
                break

    print(f"wrote {output} ({count} samples, {motor_count} motors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
