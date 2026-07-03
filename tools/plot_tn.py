#!/usr/bin/env python3
"""Plot TN CSV scatter data against Unitree actuator torque-speed limits."""

from __future__ import annotations

import argparse
import csv
import html
import math
from dataclasses import dataclass
from pathlib import Path

from telemetry_bin import RAD_S_TO_RPM


DEFAULT_ACTUATOR = "Go2HV"
DEFAULT_ACTUATOR_MAP = Path("config/motor_actuators.conf")


@dataclass(frozen=True)
class ActuatorLimit:
    name: str
    x1_rad_s: float
    x2_rad_s: float
    y1_nm: float
    y2_nm: float

    @property
    def x1_rpm(self) -> float:
        return self.x1_rad_s * RAD_S_TO_RPM

    @property
    def x2_rpm(self) -> float:
        return self.x2_rad_s * RAD_S_TO_RPM

    def torque_limit(self, speed_rad_s: float, torque_nm: float) -> float:
        base = self.y1_nm if speed_rad_s * torque_nm > 0.0 else self.y2_nm
        abs_speed = abs(speed_rad_s)
        if abs_speed <= self.x1_rad_s:
            return base
        if abs_speed >= self.x2_rad_s:
            return 0.0
        slope = -base / (self.x2_rad_s - self.x1_rad_s)
        return max(0.0, slope * (abs_speed - self.x1_rad_s) + base)


# Values copied from UnitreeActuatorCfg classes in:
# https://github.com/unitreerobotics/unitree_rl_lab/blob/main/source/unitree_rl_lab/unitree_rl_lab/assets/robots/unitree_actuators.py
ACTUATORS: dict[str, ActuatorLimit] = {
    "M107_15": ActuatorLimit("M107_15", 14.0, 25.6, 150.0, 182.8),
    "M107_24": ActuatorLimit("M107_24", 8.8, 16.0, 240.0, 292.5),
    "Go2HV": ActuatorLimit("Go2HV", 13.5, 30.0, 20.2, 23.4),
    "N7520_14p3": ActuatorLimit("N7520_14p3", 22.63, 35.52, 71.0, 83.3),
    "N7520_22p5": ActuatorLimit("N7520_22p5", 14.5, 22.7, 111.0, 131.0),
    "N5010_16": ActuatorLimit("N5010_16", 27.0, 41.5, 9.5, 17.0),
    "N5020_16": ActuatorLimit("N5020_16", 30.86, 40.13, 24.8, 31.9),
    "W4010_25": ActuatorLimit("W4010_25", 15.3, 24.76, 4.8, 8.6),
}


WIDTH = 960
HEIGHT = 620
LEFT = 82
RIGHT = 30
TOP = 46
BOTTOM = 74
PLOT_W = WIDTH - LEFT - RIGHT
PLOT_H = HEIGHT - TOP - BOTTOM

COLORS = {
    "same": "#276EF1",
    "opposite": "#12A150",
    "over": "#D92D20",
    "grid": "#D8DEE8",
    "axis": "#293241",
    "y1": "#174EA6",
    "y2": "#0E7C59",
    "text": "#111827",
}


def default_input_csv(path: Path) -> Path:
    if path.is_dir():
        if (path / "tn_all.csv").is_file():
            return path / "tn_all.csv"
        if (path / "tn_csv" / "tn_all.csv").is_file():
            return path / "tn_csv" / "tn_all.csv"
        return path / "tn_all.csv"
    return path


def latest_tn_dir(logs_dir: Path = Path("unitree_logs")) -> Path:
    sessions = sorted(path for path in logs_dir.iterdir() if (path / "tn_csv" / "tn_all.csv").is_file())
    if not sessions:
        raise FileNotFoundError(f"no tn_csv outputs found under {logs_dir}; run tools/extract_tn.py first")
    return sessions[-1] / "tn_csv"


def resolve_input_path(input_path: Path | None) -> Path:
    if input_path is None:
        return latest_tn_dir()
    return input_path


def default_output_dir(input_path: Path, input_csv: Path) -> Path:
    if input_path.is_dir() and (input_path / "tn_csv" / "tn_all.csv").is_file():
        return input_path / "tn_plots"
    if input_csv.parent.name == "tn_csv":
        return input_csv.parent.parent / "tn_plots"
    return input_csv.parent / "tn_plots"


def parse_motor_filter(values: list[str] | None) -> set[str] | None:
    if not values:
        return None
    motors = set()
    for value in values:
        value = value.strip().lower()
        if value.startswith("m"):
            index = int(value[1:])
        else:
            index = int(value)
        motors.add(f"m{index:02d}")
    return motors


def parse_actuator_map(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}

    out = {}
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            if "=" not in line:
                raise ValueError(f"invalid actuator map line {line_no}: {line}")
            motor, actuator = [part.strip() for part in line.split("=", 1)]
            motor_filter = parse_motor_filter([motor])
            if not motor_filter:
                raise ValueError(f"invalid motor on actuator map line {line_no}: {motor}")
            motor_name = next(iter(motor_filter))
            if actuator not in ACTUATORS:
                raise ValueError(f"unknown actuator on line {line_no}: {actuator}")
            out[motor_name] = actuator
    return out


def actuator_for_motor(motor: str, actuator_map: dict[str, str], fallback: str) -> ActuatorLimit:
    return ACTUATORS[actuator_map.get(motor, fallback)]


def read_rows(path: Path, motors: set[str] | None) -> list[dict]:
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"motor", "speed_rad_s", "speed_rpm", "torque_nm", "abs_speed_rpm", "abs_torque_nm"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} is missing columns: {', '.join(sorted(missing))}")

        for row in reader:
            motor = row["motor"].strip().lower()
            if motors is not None and motor not in motors:
                continue
            speed_rad_s = float(row["speed_rad_s"])
            torque_nm = float(row["torque_nm"])
            rows.append(
                {
                    "motor": motor,
                    "speed_rad_s": speed_rad_s,
                    "speed_rpm": float(row["speed_rpm"]),
                    "torque_nm": torque_nm,
                    "abs_speed_rpm": abs(float(row["abs_speed_rpm"])),
                    "abs_torque_nm": abs(float(row["abs_torque_nm"])),
                    "same_direction": speed_rad_s * torque_nm > 0.0,
                }
            )
    return rows


def grouped_by_motor(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["motor"], []).append(row)
    return dict(sorted(grouped.items()))


def downsample(rows: list[dict], max_points: int) -> list[dict]:
    if max_points <= 0 or len(rows) <= max_points:
        return rows
    step = len(rows) / max_points
    return [rows[min(len(rows) - 1, math.floor(i * step))] for i in range(max_points)]


def nice_ticks(max_value: float, count: int = 6) -> list[float]:
    if max_value <= 0.0:
        return [0.0]
    raw_step = max_value / max(1, count - 1)
    magnitude = 10 ** math.floor(math.log10(raw_step))
    normalized = raw_step / magnitude
    if normalized <= 1.0:
        step = magnitude
    elif normalized <= 2.0:
        step = 2.0 * magnitude
    elif normalized <= 5.0:
        step = 5.0 * magnitude
    else:
        step = 10.0 * magnitude
    upper = math.ceil(max_value / step) * step
    ticks = []
    value = 0.0
    while value <= upper + step * 0.5:
        ticks.append(value)
        value += step
    return ticks


def scale_x(value: float, max_x: float) -> float:
    return LEFT + (value / max_x) * PLOT_W


def scale_y(value: float, max_y: float) -> float:
    return TOP + PLOT_H - (value / max_y) * PLOT_H


def fmt(value: float) -> str:
    if abs(value) >= 100.0:
        return f"{value:.0f}"
    if abs(value) >= 10.0:
        return f"{value:.1f}"
    return f"{value:.2f}"


def limit_polyline(limit: ActuatorLimit, y_nm: float, max_x: float, max_y: float) -> str:
    points = [
        (0.0, y_nm),
        (limit.x1_rpm, y_nm),
        (limit.x2_rpm, 0.0),
    ]
    return " ".join(f"{scale_x(x, max_x):.1f},{scale_y(y, max_y):.1f}" for x, y in points)


def write_svg(
    path: Path,
    title: str,
    rows: list[dict],
    limits_by_motor: dict[str, ActuatorLimit],
    fallback_limit: ActuatorLimit,
    max_points: int,
) -> dict:
    plotted = downsample(rows, max_points)
    checked = []
    for row in rows:
        limit = limits_by_motor.get(row["motor"], fallback_limit)
        limit_nm = limit.torque_limit(row["speed_rad_s"], row["torque_nm"])
        checked.append({**row, "limit_nm": limit_nm, "over_limit": row["abs_torque_nm"] > limit_nm})

    over_count = sum(1 for row in checked if row["over_limit"])
    limits = list(limits_by_motor.values()) or [fallback_limit]
    max_abs_speed = max([row["abs_speed_rpm"] for row in rows] + [limit.x2_rpm for limit in limits])
    max_abs_torque = max(
        [row["abs_torque_nm"] for row in rows]
        + [value for limit in limits for value in (limit.y1_nm, limit.y2_nm)]
    )
    max_x = nice_ticks(max_abs_speed * 1.06)[-1]
    max_y = nice_ticks(max_abs_torque * 1.10)[-1]
    x_ticks = nice_ticks(max_x)
    y_ticks = nice_ticks(max_y)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        "<style>text{font-family:Arial,Helvetica,sans-serif;fill:#111827}.small{font-size:13px}.label{font-size:15px}.title{font-size:22px;font-weight:700}.legend{font-size:14px}</style>",
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        f'<text class="title" x="{LEFT}" y="30">{html.escape(title)}</text>',
        f'<text class="small" x="{WIDTH - RIGHT}" y="30" text-anchor="end">actuator: {html.escape(actuator_label(limits_by_motor, fallback_limit))}</text>',
    ]

    for tick in x_ticks:
        x = scale_x(tick, max_x)
        parts.append(f'<line x1="{x:.1f}" y1="{TOP}" x2="{x:.1f}" y2="{TOP + PLOT_H}" stroke="{COLORS["grid"]}" stroke-width="1"/>')
        parts.append(f'<text class="small" x="{x:.1f}" y="{TOP + PLOT_H + 24}" text-anchor="middle">{fmt(tick)}</text>')
    for tick in y_ticks:
        y = scale_y(tick, max_y)
        parts.append(f'<line x1="{LEFT}" y1="{y:.1f}" x2="{LEFT + PLOT_W}" y2="{y:.1f}" stroke="{COLORS["grid"]}" stroke-width="1"/>')
        parts.append(f'<text class="small" x="{LEFT - 10}" y="{y + 4:.1f}" text-anchor="end">{fmt(tick)}</text>')

    parts.append(f'<line x1="{LEFT}" y1="{TOP + PLOT_H}" x2="{LEFT + PLOT_W}" y2="{TOP + PLOT_H}" stroke="{COLORS["axis"]}" stroke-width="1.5"/>')
    parts.append(f'<line x1="{LEFT}" y1="{TOP}" x2="{LEFT}" y2="{TOP + PLOT_H}" stroke="{COLORS["axis"]}" stroke-width="1.5"/>')
    parts.append(f'<text class="label" x="{LEFT + PLOT_W / 2:.1f}" y="{HEIGHT - 22}" text-anchor="middle">absolute speed (rpm)</text>')
    parts.append(f'<text class="label" x="22" y="{TOP + PLOT_H / 2:.1f}" text-anchor="middle" transform="rotate(-90 22 {TOP + PLOT_H / 2:.1f})">absolute torque (N*m)</text>')

    if len({limit.name for limit in limits}) == 1:
        limit = limits[0]
        parts.append(f'<polyline points="{limit_polyline(limit, limit.y1_nm, max_x, max_y)}" fill="none" stroke="{COLORS["y1"]}" stroke-width="3"/>')
        parts.append(f'<polyline points="{limit_polyline(limit, limit.y2_nm, max_x, max_y)}" fill="none" stroke="{COLORS["y2"]}" stroke-width="3" stroke-dasharray="8 5"/>')

    for row in plotted:
        limit = limits_by_motor.get(row["motor"], fallback_limit)
        limit_nm = limit.torque_limit(row["speed_rad_s"], row["torque_nm"])
        over = row["abs_torque_nm"] > limit_nm
        color = COLORS["over"] if over else COLORS["same" if row["same_direction"] else "opposite"]
        radius = 3.0 if over else 2.2
        x = scale_x(row["abs_speed_rpm"], max_x)
        y = scale_y(row["abs_torque_nm"], max_y)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{color}" fill-opacity="0.58"/>')

    legend_y = TOP + 18
    legend_x = LEFT + 18
    legend_items = [
        (COLORS["same"], "same direction sample"),
        (COLORS["opposite"], "opposite direction sample"),
        (COLORS["over"], "over limit sample"),
    ]
    if len({limit.name for limit in limits}) == 1:
        limit = limits[0]
        legend_items += [
            (COLORS["y1"], f"Y1 same dir {limit.y1_nm:g} N*m"),
            (COLORS["y2"], f"Y2 opposite {limit.y2_nm:g} N*m"),
        ]
    else:
        legend_items.append((COLORS["y1"], "per-motor actuator limits"))
    for i, (color, text) in enumerate(legend_items):
        y = legend_y + i * 21
        if i < 3:
            parts.append(f'<circle cx="{legend_x}" cy="{y - 4}" r="4" fill="{color}" fill-opacity="0.75"/>')
        else:
            dash = ' stroke-dasharray="8 5"' if i == 4 else ""
            parts.append(f'<line x1="{legend_x - 6}" y1="{y - 4}" x2="{legend_x + 8}" y2="{y - 4}" stroke="{color}" stroke-width="3"{dash}/>')
        parts.append(f'<text class="legend" x="{legend_x + 16}" y="{y}">{html.escape(text)}</text>')

    summary = f"samples {len(rows)}, plotted {len(plotted)}, over limit {over_count}"
    parts.append(f'<text class="small" x="{WIDTH - RIGHT}" y="{HEIGHT - 22}" text-anchor="end">{html.escape(summary)}</text>')
    parts.append("</svg>")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return {
        "rows": len(rows),
        "plotted": len(plotted),
        "over_limit": over_count,
        "actuator": actuator_label(limits_by_motor, fallback_limit),
        "max_abs_speed_rpm": max(row["abs_speed_rpm"] for row in rows),
        "max_abs_torque_nm": max(row["abs_torque_nm"] for row in rows),
    }


def actuator_label(limits_by_motor: dict[str, ActuatorLimit], fallback_limit: ActuatorLimit) -> str:
    names = sorted({limit.name for limit in limits_by_motor.values()})
    if not names:
        return fallback_limit.name
    if len(names) == 1:
        return names[0]
    return "mixed"


def write_summary(path: Path, stats: dict[str, dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "motor",
                "actuator",
                "rows",
                "plotted",
                "over_limit",
                "over_limit_pct",
                "max_abs_speed_rpm",
                "max_abs_torque_nm",
            ],
        )
        writer.writeheader()
        for motor, item in sorted(stats.items()):
            rows = item["rows"]
            writer.writerow(
                {
                    "motor": motor,
                    "actuator": item["actuator"],
                    "rows": rows,
                    "plotted": item["plotted"],
                    "over_limit": item["over_limit"],
                    "over_limit_pct": f"{(item['over_limit'] / rows * 100.0) if rows else 0.0:.3f}",
                    "max_abs_speed_rpm": f"{item['max_abs_speed_rpm']:.6g}",
                    "max_abs_torque_nm": f"{item['max_abs_torque_nm']:.6g}",
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        help="Path to tn_all.csv, tn_csv, or a session directory. Default: latest unitree_logs TN output",
    )
    parser.add_argument("-o", "--output-dir", type=Path, help="Directory for SVG plots")
    parser.add_argument(
        "--actuator",
        choices=sorted(ACTUATORS),
        default=DEFAULT_ACTUATOR,
        help="Fallback actuator when a motor is not present in --actuator-map",
    )
    parser.add_argument(
        "--actuator-map",
        type=Path,
        default=DEFAULT_ACTUATOR_MAP,
        help="Motor-to-actuator config file. Default: config/motor_actuators.conf",
    )
    parser.add_argument(
        "--motor",
        action="append",
        help="Motor to plot, e.g. 0 or m00. Can be used multiple times. Default: all motors",
    )
    parser.add_argument("--max-points", type=int, default=6000, help="Maximum scatter points per SVG")
    parser.add_argument("--no-per-motor", action="store_true", help="Only write tn_all.svg")
    args = parser.parse_args()

    input_path = resolve_input_path(args.input)
    input_csv = default_input_csv(input_path)
    output_dir = args.output_dir or default_output_dir(input_path, input_csv)
    motors = parse_motor_filter(args.motor)
    actuator_map = parse_actuator_map(args.actuator_map)
    fallback_limit = ACTUATORS[args.actuator]
    rows = read_rows(input_csv, motors)
    if not rows:
        raise ValueError("no TN rows matched the input filters")

    output_dir.mkdir(parents=True, exist_ok=True)
    grouped = grouped_by_motor(rows)
    limits_by_motor = {
        motor: actuator_for_motor(motor, actuator_map, args.actuator)
        for motor in grouped
    }
    stats = {
        "all": write_svg(
            output_dir / "tn_all.svg",
            "TN scatter - all selected motors",
            rows,
            limits_by_motor,
            fallback_limit,
            args.max_points,
        )
    }

    if not args.no_per_motor:
        for motor, motor_rows in grouped.items():
            stats[motor] = write_svg(
                output_dir / f"{motor}.svg",
                f"TN scatter - {motor}",
                motor_rows,
                {motor: limits_by_motor[motor]},
                fallback_limit,
                args.max_points,
            )

    write_summary(output_dir / "summary.csv", stats)
    print(f"wrote {output_dir} ({len(rows)} rows, actuator={actuator_label(limits_by_motor, fallback_limit)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
