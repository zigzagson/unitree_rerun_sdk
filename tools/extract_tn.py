#!/usr/bin/env python3
"""Extract motor torque-speed demand data from telemetry.bin to CSV."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from telemetry_bin import RAD_S_TO_RPM, iter_samples, motor_names, read_header


FIELDNAMES = [
    "unix_time_ns",
    "sequence",
    "motor",
    "speed_rad_s",
    "speed_rpm",
    "torque_nm",
    "abs_speed_rpm",
    "abs_torque_nm",
    "q_rad",
    "cmd_received",
    "cmd_age_ms",
    "cmd_sequence",
    "cmd_mode_pr",
    "cmd_mode_machine",
    "cmd_mode",
    "cmd_q_rad",
    "cmd_dq_rad_s",
    "cmd_tau_nm",
    "cmd_kp",
    "cmd_kd",
    "cmd_motor_reserve",
    "cmd_reserve_0",
    "cmd_reserve_1",
    "cmd_reserve_2",
    "cmd_reserve_3",
    "cmd_crc",
    "q_error_rad",
    "dq_error_rad_s",
    "tau_error_nm",
    "temp_case_c",
    "temp_winding_c",
    "motor_state",
]


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


def default_output_dir(input_path: Path) -> Path:
    if input_path.name == "telemetry.bin":
        return input_path.parent / "tn_csv"
    return input_path.with_suffix("") / "tn_csv"


def parse_motor_filter(values: list[str] | None, motor_count: int) -> list[int]:
    if not values:
        return list(range(motor_count))

    out = []
    for value in values:
        value = value.strip().lower()
        if value.startswith("m"):
            value = value[1:]
        index = int(value)
        if index < 0 or index >= motor_count:
            raise ValueError(f"motor index out of range: {index}")
        out.append(index)
    return sorted(set(out))


def sample_rows(sample: dict, motor_indices: list[int], names: list[str]) -> list[dict]:
    rows = []
    for i in motor_indices:
        speed_rad_s = float(sample["dq"][i])
        speed_rpm = speed_rad_s * RAD_S_TO_RPM
        torque_nm = float(sample["tau"][i])
        has_cmd = bool(sample["lowcmd_received"])
        rows.append(
            {
                "unix_time_ns": sample["unix_time_ns"],
                "sequence": sample["sequence"],
                "motor": names[i],
                "speed_rad_s": speed_rad_s,
                "speed_rpm": speed_rpm,
                "torque_nm": torque_nm,
                "abs_speed_rpm": abs(speed_rpm),
                "abs_torque_nm": abs(torque_nm),
                "q_rad": float(sample["q"][i]),
                "cmd_received": int(sample["lowcmd_received"]),
                "cmd_age_ms": (
                    float(sample["lowcmd_age_ns"]) / 1_000_000.0
                    if sample["lowcmd_age_ns"] is not None
                    else -1.0
                ),
                "cmd_sequence": int(sample["lowcmd_sequence"]) if has_cmd else "",
                "cmd_mode_pr": int(sample["lowcmd_mode_pr"]) if has_cmd else "",
                "cmd_mode_machine": int(sample["lowcmd_mode_machine"]) if has_cmd else "",
                "cmd_mode": int(sample["cmd_mode"][i]) if has_cmd else "",
                "cmd_q_rad": float(sample["cmd_q"][i]) if has_cmd else "",
                "cmd_dq_rad_s": float(sample["cmd_dq"][i]) if has_cmd else "",
                "cmd_tau_nm": float(sample["cmd_tau"][i]) if has_cmd else "",
                "cmd_kp": float(sample["cmd_kp"][i]) if has_cmd else "",
                "cmd_kd": float(sample["cmd_kd"][i]) if has_cmd else "",
                "cmd_motor_reserve": int(sample["cmd_reserve"][i]) if has_cmd else "",
                "cmd_reserve_0": int(sample["lowcmd_reserve"][0]) if has_cmd else "",
                "cmd_reserve_1": int(sample["lowcmd_reserve"][1]) if has_cmd else "",
                "cmd_reserve_2": int(sample["lowcmd_reserve"][2]) if has_cmd else "",
                "cmd_reserve_3": int(sample["lowcmd_reserve"][3]) if has_cmd else "",
                "cmd_crc": int(sample["lowcmd_crc"]) if has_cmd else "",
                "q_error_rad": float(sample["cmd_q"][i] - sample["q"][i]) if has_cmd else "",
                "dq_error_rad_s": (
                    float(sample["cmd_dq"][i] - sample["dq"][i]) if has_cmd else ""
                ),
                "tau_error_nm": (
                    float(sample["cmd_tau"][i] - sample["tau"][i]) if has_cmd else ""
                ),
                "temp_case_c": int(sample["temp_case"][i]),
                "temp_winding_c": int(sample["temp_winding"][i]),
                "motor_state": int(sample["motor_state"][i]),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        help="Path to telemetry.bin or a session directory. Default: latest unitree_logs session",
    )
    parser.add_argument("-o", "--output-dir", type=Path, help="Directory for TN CSV files")
    parser.add_argument(
        "--motor",
        action="append",
        help="Motor to export, e.g. 0 or m00. Can be used multiple times. Default: all motors",
    )
    parser.add_argument("--max-samples", type=int, default=0, help="Read at most this many samples")
    parser.add_argument(
        "--no-per-motor",
        action="store_true",
        help="Only write tn_all.csv, without per-motor CSV files",
    )
    args = parser.parse_args()

    input_path = resolve_input_path(args.input)
    output_dir = args.output_dir or default_output_dir(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    with input_path.open("rb") as f:
        header = read_header(f)
        motor_count = int(header["motor_count"])
        names = motor_names(motor_count)
        motor_indices = parse_motor_filter(args.motor, motor_count)

        all_rows = []
        per_motor_rows = {names[i]: [] for i in motor_indices}
        sample_count = 0
        for sample in iter_samples(f, motor_count, int(header["version"])):
            rows = sample_rows(sample, motor_indices, names)
            all_rows.extend(rows)
            for row in rows:
                per_motor_rows[row["motor"]].append(row)

            sample_count += 1
            if args.max_samples and sample_count >= args.max_samples:
                break

    write_csv(output_dir / "tn_all.csv", all_rows)
    if not args.no_per_motor:
        for motor_name, rows in per_motor_rows.items():
            write_csv(output_dir / f"{motor_name}.csv", rows)

    print(
        f"wrote {output_dir} ({sample_count} samples, "
        f"{len(motor_indices)} motors, {len(all_rows)} rows)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
