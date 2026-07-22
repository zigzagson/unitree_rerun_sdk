#!/usr/bin/env python3
"""Read unitree_rerun telemetry.bin files."""

from __future__ import annotations

import math
import struct
from typing import BinaryIO, Iterator


HEADER = struct.Struct("<8sIIIQddI64s32s112s")
RECORD_PREFIX = struct.Struct("<QQQQIBB2x")
MOTOR = struct.Struct("<fffhhI")
IMU = struct.Struct("<13fh2x")
LOWCMD_PREFIX = struct.Struct("<QQBBB5x4II")
MOTOR_CMD = struct.Struct("<B3x5fI")
MAGIC = b"URLOG001"
RAD_S_TO_RPM = 60.0 / (2.0 * math.pi)


def _decode_c_string(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace")


def read_header(f: BinaryIO) -> dict:
    raw = f.read(HEADER.size)
    if len(raw) != HEADER.size:
        raise ValueError("file is too small to contain a telemetry header")

    (
        magic,
        header_size,
        version,
        motor_count,
        start_unix_time_ns,
        sample_hz,
        summary_hz,
        _reserved,
        topic,
        network_interface,
        reserved_bytes,
    ) = HEADER.unpack(raw)

    if magic != MAGIC:
        raise ValueError(f"invalid telemetry magic: {magic!r}")
    if header_size != HEADER.size:
        raise ValueError(f"unsupported header size: {header_size}")
    if version not in (1, 2):
        raise ValueError(f"unsupported telemetry version: {version}")

    return {
        "version": version,
        "motor_count": motor_count,
        "start_unix_time_ns": start_unix_time_ns,
        "sample_hz": sample_hz,
        "summary_hz": summary_hz,
        "topic": _decode_c_string(topic),
        "lowcmd_topic": _decode_c_string(reserved_bytes[:64]) if version >= 2 else "",
        "network_interface": _decode_c_string(network_interface),
    }


def iter_samples(f: BinaryIO, motor_count: int, version: int = 1) -> Iterator[dict]:
    if version not in (1, 2):
        raise ValueError(f"unsupported telemetry version: {version}")

    record_size = RECORD_PREFIX.size + motor_count * MOTOR.size + IMU.size
    if version >= 2:
        record_size += LOWCMD_PREFIX.size + motor_count * MOTOR_CMD.size
    while True:
        raw = f.read(record_size)
        if not raw:
            return
        if len(raw) != record_size:
            raise ValueError(f"truncated record: got {len(raw)} bytes, expected {record_size}")

        offset = 0
        (
            unix_time_ns,
            steady_time_ns,
            sequence,
            dropped_samples,
            source_tick,
            mode_pr,
            mode_machine,
        ) = RECORD_PREFIX.unpack_from(raw, offset)
        offset += RECORD_PREFIX.size

        q = []
        dq = []
        tau = []
        temp_case = []
        temp_winding = []
        motor_state = []
        for _ in range(motor_count):
            q_i, dq_i, tau_i, temp_case_i, temp_winding_i, state_i = MOTOR.unpack_from(raw, offset)
            offset += MOTOR.size
            q.append(q_i)
            dq.append(dq_i)
            tau.append(tau_i)
            temp_case.append(temp_case_i)
            temp_winding.append(temp_winding_i)
            motor_state.append(state_i)

        imu_values = IMU.unpack_from(raw, offset)
        offset += IMU.size

        lowcmd_steady_time_ns = 0
        lowcmd_sequence = 0
        lowcmd_received = False
        lowcmd_mode_pr = 0
        lowcmd_mode_machine = 0
        lowcmd_reserve = [0] * 4
        lowcmd_crc = 0
        cmd_mode = [0] * motor_count
        cmd_q = [0.0] * motor_count
        cmd_dq = [0.0] * motor_count
        cmd_tau = [0.0] * motor_count
        cmd_kp = [0.0] * motor_count
        cmd_kd = [0.0] * motor_count
        cmd_reserve = [0] * motor_count
        if version >= 2:
            (
                lowcmd_steady_time_ns,
                lowcmd_sequence,
                lowcmd_received_raw,
                lowcmd_mode_pr,
                lowcmd_mode_machine,
                *lowcmd_tail,
            ) = LOWCMD_PREFIX.unpack_from(raw, offset)
            offset += LOWCMD_PREFIX.size
            lowcmd_received = bool(lowcmd_received_raw)
            lowcmd_reserve = list(lowcmd_tail[:4])
            lowcmd_crc = lowcmd_tail[4]

            cmd_mode = []
            cmd_q = []
            cmd_dq = []
            cmd_tau = []
            cmd_kp = []
            cmd_kd = []
            cmd_reserve = []
            for _ in range(motor_count):
                mode_i, q_i, dq_i, tau_i, kp_i, kd_i, reserve_i = MOTOR_CMD.unpack_from(raw, offset)
                offset += MOTOR_CMD.size
                cmd_mode.append(mode_i)
                cmd_q.append(q_i)
                cmd_dq.append(dq_i)
                cmd_tau.append(tau_i)
                cmd_kp.append(kp_i)
                cmd_kd.append(kd_i)
                cmd_reserve.append(reserve_i)

        lowcmd_age_ns = (
            max(0, steady_time_ns - lowcmd_steady_time_ns) if lowcmd_received else None
        )
        yield {
            "unix_time_ns": unix_time_ns,
            "steady_time_ns": steady_time_ns,
            "sequence": sequence,
            "dropped_samples": dropped_samples,
            "source_tick": source_tick,
            "mode_pr": mode_pr,
            "mode_machine": mode_machine,
            "lowcmd_received": lowcmd_received,
            "lowcmd_steady_time_ns": lowcmd_steady_time_ns,
            "lowcmd_sequence": lowcmd_sequence,
            "lowcmd_age_ns": lowcmd_age_ns,
            "lowcmd_mode_pr": lowcmd_mode_pr,
            "lowcmd_mode_machine": lowcmd_mode_machine,
            "lowcmd_reserve": lowcmd_reserve,
            "lowcmd_crc": lowcmd_crc,
            "q": q,
            "dq": dq,
            "tau": tau,
            "temp_case": temp_case,
            "temp_winding": temp_winding,
            "motor_state": motor_state,
            "cmd_mode": cmd_mode,
            "cmd_q": cmd_q,
            "cmd_dq": cmd_dq,
            "cmd_tau": cmd_tau,
            "cmd_kp": cmd_kp,
            "cmd_kd": cmd_kd,
            "cmd_reserve": cmd_reserve,
            "imu_quat": list(imu_values[0:4]),
            "imu_gyro": list(imu_values[4:7]),
            "imu_accel": list(imu_values[7:10]),
            "imu_rpy": list(imu_values[10:13]),
            "imu_temp": imu_values[13],
        }


def motor_names(motor_count: int) -> list[str]:
    return [f"m{i:02d}" for i in range(motor_count)]
