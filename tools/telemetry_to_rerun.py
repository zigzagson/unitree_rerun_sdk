#!/usr/bin/env python3
"""Convert unitree_rerun telemetry.bin files to Rerun time-series .rrd recordings."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import rerun as rr
import rerun.blueprint as rrb

from telemetry_bin import iter_samples, motor_names, read_header


_BLUEPRINT_TABS = (
    (
        "Position",
        (
            ("Actual position q", "/robot/motors/q"),
            ("Commanded position q", "/robot/commands/q"),
            ("Position error (command - actual)", "/robot/comparison/q_error"),
        ),
    ),
    (
        "Velocity",
        (
            ("Actual velocity dq", "/robot/motors/dq"),
            ("Commanded velocity dq", "/robot/commands/dq"),
            ("Velocity error (command - actual)", "/robot/comparison/dq_error"),
        ),
    ),
    (
        "Torque",
        (
            ("Estimated torque", "/robot/motors/tau_est"),
            ("Feed-forward torque command", "/robot/commands/tau"),
            ("Torque error (command - estimate)", "/robot/comparison/tau_error"),
        ),
    ),
    (
        "LowCmd",
        (
            ("Position gain kp", "/robot/commands/kp"),
            ("Damping gain kd", "/robot/commands/kd"),
            ("Motor command mode", "/robot/commands/mode"),
            ("LowCmd header", "/robot/commands/header"),
            ("Motor command reserve", "/robot/commands/motor_reserve"),
            ("LowCmd reserve", "/robot/commands/reserve"),
        ),
    ),
    (
        "Health",
        (
            ("Motor case temperature", "/robot/motors/temp_case"),
            ("Motor winding temperature", "/robot/motors/temp_winding"),
            ("Motor state", "/robot/motors/state"),
            ("Robot health summary", "/robot/health/summary"),
        ),
    ),
    (
        "IMU",
        (
            ("IMU roll / pitch / yaw", "/robot/imu/rpy"),
            ("IMU gyroscope", "/robot/imu/gyro"),
            ("IMU accelerometer", "/robot/imu/accel"),
            ("IMU temperature", "/robot/imu/temperature"),
        ),
    ),
)


def _time_series_view(name: str, path: str) -> rrb.TimeSeriesView:
    return rrb.TimeSeriesView(
        name=name,
        origin=path,
        contents=[path],
        plot_legend=rrb.PlotLegend(visible=True),
    )


def default_blueprint() -> rrb.Blueprint:
    tabs = [
        rrb.Vertical(
            *(_time_series_view(view_name, path) for view_name, path in views),
            name=tab_name,
        )
        for tab_name, views in _BLUEPRINT_TABS
    ]
    return rrb.Blueprint(
        rrb.Tabs(contents=tabs, active_tab=0, name="Unitree telemetry"),
        rrb.BlueprintPanel(expanded=True),
        rrb.SelectionPanel(expanded=True),
        rrb.TimePanel(expanded=True, timeline="unix_time"),
        auto_layout=False,
        auto_views=False,
        collapse_panels=False,
    )


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
        "robot/commands/q",
        "robot/commands/dq",
        "robot/commands/tau",
        "robot/commands/kp",
        "robot/commands/kd",
        "robot/commands/mode",
        "robot/commands/motor_reserve",
        "robot/comparison/q_error",
        "robot/comparison/dq_error",
        "robot/comparison/tau_error",
    ):
        rr.log(path, rr.SeriesLines(names=names), static=True)

    rr.log("robot/imu/rpy", rr.SeriesLines(names=["roll", "pitch", "yaw"]), static=True)
    rr.log("robot/imu/gyro", rr.SeriesLines(names=["gx", "gy", "gz"]), static=True)
    rr.log("robot/imu/accel", rr.SeriesLines(names=["ax", "ay", "az"]), static=True)
    rr.log(
        "robot/commands/header",
        rr.SeriesLines(names=["mode_pr", "mode_machine", "sequence", "age_ms", "crc"]),
        static=True,
    )
    rr.log(
        "robot/commands/reserve",
        rr.SeriesLines(names=["reserve_0", "reserve_1", "reserve_2", "reserve_3"]),
        static=True,
    )
    rr.log(
        "robot/health/summary",
        rr.SeriesLines(
            names=[
                "max_temp",
                "max_temp_motor",
                "imu_temp",
                "max_abs_tau",
                "max_abs_dq",
                "dropped",
                "lowcmd_age_ms",
                "lowcmd_received",
            ]
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

    if sample["lowcmd_received"]:
        rr.log("robot/commands/q", rr.Scalars(sample["cmd_q"]))
        rr.log("robot/commands/dq", rr.Scalars(sample["cmd_dq"]))
        rr.log("robot/commands/tau", rr.Scalars(sample["cmd_tau"]))
        rr.log("robot/commands/kp", rr.Scalars(sample["cmd_kp"]))
        rr.log("robot/commands/kd", rr.Scalars(sample["cmd_kd"]))
        rr.log("robot/commands/mode", rr.Scalars(sample["cmd_mode"]))
        rr.log("robot/commands/motor_reserve", rr.Scalars(sample["cmd_reserve"]))
        rr.log(
            "robot/commands/header",
            rr.Scalars(
                [
                    sample["lowcmd_mode_pr"],
                    sample["lowcmd_mode_machine"],
                    sample["lowcmd_sequence"],
                    sample["lowcmd_age_ns"] / 1_000_000.0,
                    sample["lowcmd_crc"],
                ]
            ),
        )
        rr.log("robot/commands/reserve", rr.Scalars(sample["lowcmd_reserve"]))
        rr.log(
            "robot/comparison/q_error",
            rr.Scalars([cmd - actual for cmd, actual in zip(sample["cmd_q"], sample["q"])]),
        )
        rr.log(
            "robot/comparison/dq_error",
            rr.Scalars([cmd - actual for cmd, actual in zip(sample["cmd_dq"], sample["dq"])]),
        )
        rr.log(
            "robot/comparison/tau_error",
            rr.Scalars([cmd - actual for cmd, actual in zip(sample["cmd_tau"], sample["tau"])]),
        )

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
                sample["lowcmd_age_ns"] / 1_000_000.0
                if sample["lowcmd_age_ns"] is not None
                else -1.0,
                1.0 if sample["lowcmd_received"] else 0.0,
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
        rr.send_blueprint(default_blueprint())
        log_static_series(motor_count)

        count = 0
        for sample in iter_samples(f, motor_count, int(header["version"])):
            log_sample(sample)
            count += 1
            if args.max_samples and count >= args.max_samples:
                break

    print(f"wrote {output} ({count} samples, {motor_count} motors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
