#ifndef UNITREE_RERUN_SDK_TELEMETRY_SAMPLE_H
#define UNITREE_RERUN_SDK_TELEMETRY_SAMPLE_H

#include "unitree_rerun_sdk/config.h"

#include <array>
#include <cstdint>

namespace unitree_rerun {

struct TelemetrySample {
    uint64_t unix_time_ns = 0;
    uint64_t steady_time_ns = 0;
    uint64_t sequence = 0;
    uint64_t dropped_samples = 0;
    uint32_t source_tick = 0;
    uint8_t mode_pr = 0;
    uint8_t mode_machine = 0;

    std::array<float, kMaxMotorCount> q{};
    std::array<float, kMaxMotorCount> dq{};
    std::array<float, kMaxMotorCount> tau_est{};
    std::array<int16_t, kMaxMotorCount> temp_case{};
    std::array<int16_t, kMaxMotorCount> temp_winding{};
    std::array<uint32_t, kMaxMotorCount> motor_state{};

    std::array<float, 4> imu_quat{};
    std::array<float, 3> imu_gyro{};
    std::array<float, 3> imu_accel{};
    std::array<float, 3> imu_rpy{};
    int16_t imu_temp = 0;
};

}  // namespace unitree_rerun

#endif  // UNITREE_RERUN_SDK_TELEMETRY_SAMPLE_H
