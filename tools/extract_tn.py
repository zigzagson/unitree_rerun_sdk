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
    "temp_case_c",
    "temp_winding_c",
    "motor_state",
]


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
    parser.add_argument("input", type=Path, help="Path to telemetry.bin")
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

    output_dir = args.output_dir or default_output_dir(args.input)
    output_dir.mkdir(parents=True, exist_ok=True)

    with args.input.open("rb") as f:
        header = read_header(f)
        motor_count = int(header["motor_count"])
        names = motor_names(motor_count)
        motor_indices = parse_motor_filter(args.motor, motor_count)

        all_rows = []
        per_motor_rows = {names[i]: [] for i in motor_indices}
        sample_count = 0
        for sample in iter_samples(f, motor_count):
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
