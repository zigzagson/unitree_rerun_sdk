#include "unitree_rerun_sdk/recorder.h"
#include "unitree_rerun_sdk/time_utils.h"

#include <algorithm>
#include <chrono>
#include <cstring>
#include <functional>
#include <iostream>
#include <thread>

#include <unitree/robot/channel/channel_factory.hpp>

namespace unitree_rerun {
namespace {

uint32_t crc32Core(uint32_t* ptr, uint32_t len)
{
    uint32_t xbit = 0;
    uint32_t data = 0;
    uint32_t crc32 = 0xFFFFFFFF;
    const uint32_t polynomial = 0x04c11db7;
    for (uint32_t i = 0; i < len; i++) {
        xbit = 1u << 31;
        data = ptr[i];
        for (uint32_t bits = 0; bits < 32; bits++) {
            if (crc32 & 0x80000000) {
                crc32 <<= 1;
                crc32 ^= polynomial;
            } else {
                crc32 <<= 1;
            }
            if (data & xbit) {
                crc32 ^= polynomial;
            }
            xbit >>= 1;
        }
    }
    return crc32;
}

}  // namespace

Recorder::Recorder()
    : running_(false)
    , sequence_(0)
    , crc_errors_(0)
    , lowcmd_sequence_(0)
    , lowcmd_crc_errors_(0)
    , last_sample_steady_ns_(0)
{
}

Recorder::~Recorder()
{
    stop();
}

bool Recorder::start(const RecorderConfig& config, std::string& error)
{
    config_ = config;
    if (config_.motor_count == 0 || config_.motor_count > kMaxMotorCount) {
        error = "invalid motor_count";
        return false;
    }

    const uint64_t start_ns = unixTimeNs();
    if (!writer_.start(config_, start_ns, error)) {
        return false;
    }

    running_.store(false);
    sequence_.store(0);
    crc_errors_.store(0);
    lowcmd_sequence_.store(0);
    lowcmd_crc_errors_.store(0);
    last_sample_steady_ns_ = 0;
    {
        std::lock_guard<std::mutex> lock(lowcmd_mutex_);
        latest_lowcmd_ = TelemetrySample{};
    }

    try {
        unitree::robot::ChannelFactory::Instance()->Init(
            config_.network_mode, config_.network_interface.c_str());

        lowcmd_subscriber_.reset(
            new unitree::robot::ChannelSubscriber<unitree_hg::msg::dds_::LowCmd_>(
                config_.lowcmd_topic));
        lowcmd_subscriber_->InitChannel(
            std::bind(&Recorder::lowCmdHandler, this, std::placeholders::_1),
            1);

        subscriber_.reset(
            new unitree::robot::ChannelSubscriber<unitree_hg::msg::dds_::LowState_>(
                config_.topic));
        subscriber_->InitChannel(
            std::bind(&Recorder::lowStateHandler, this, std::placeholders::_1),
            1);
    } catch (const std::exception& e) {
        error = std::string("failed to initialize Unitree subscriber: ") + e.what();
        subscriber_.reset();
        lowcmd_subscriber_.reset();
        writer_.stop();
        return false;
    }

    running_.store(true);
    std::cout << "[unitree_rerun] recording to " << writer_.sessionDir() << std::endl;
    return true;
}

void Recorder::stop()
{
    running_.store(false);
    subscriber_.reset();
    lowcmd_subscriber_.reset();
    writer_.stop();
}

void Recorder::requestStop()
{
    running_.store(false);
}

void Recorder::waitUntilStopped()
{
    while (running_.load()) {
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    stop();
}

void Recorder::lowStateHandler(const void* message)
{
    if (!running_.load()) return;

    const auto& low_state = *static_cast<const unitree_hg::msg::dds_::LowState_*>(message);
    if (config_.validate_crc && !validateCrc(low_state)) {
        crc_errors_.fetch_add(1);
        return;
    }

    const uint64_t now_steady = steadyTimeNs();
    if (!shouldSample(now_steady)) return;

    TelemetrySample sample = makeSample(low_state);
    copyLatestLowCmd(sample);
    sample.steady_time_ns = steadyTimeNs();
    sample.unix_time_ns = unixTimeNs();
    sample.sequence = sequence_.fetch_add(1);
    writer_.enqueue(sample);
}

void Recorder::lowCmdHandler(const void* message)
{
    if (!running_.load()) return;

    const auto& low_cmd = *static_cast<const unitree_hg::msg::dds_::LowCmd_*>(message);
    if (config_.validate_crc && !validateCrc(low_cmd)) {
        lowcmd_crc_errors_.fetch_add(1);
        return;
    }

    TelemetrySample snapshot;
    snapshot.lowcmd_received = true;
    snapshot.lowcmd_steady_time_ns = steadyTimeNs();
    snapshot.lowcmd_sequence = lowcmd_sequence_.fetch_add(1);
    snapshot.lowcmd_mode_pr = low_cmd.mode_pr();
    snapshot.lowcmd_mode_machine = low_cmd.mode_machine();
    snapshot.lowcmd_reserve = low_cmd.reserve();
    snapshot.lowcmd_crc = low_cmd.crc();

    const auto& motors = low_cmd.motor_cmd();
    const uint32_t count = std::min<uint32_t>(config_.motor_count, motors.size());
    for (uint32_t i = 0; i < count; ++i) {
        const auto& motor = motors[i];
        snapshot.cmd_mode[i] = motor.mode();
        snapshot.cmd_q[i] = motor.q();
        snapshot.cmd_dq[i] = motor.dq();
        snapshot.cmd_tau[i] = motor.tau();
        snapshot.cmd_kp[i] = motor.kp();
        snapshot.cmd_kd[i] = motor.kd();
        snapshot.cmd_reserve[i] = motor.reserve();
    }

    std::lock_guard<std::mutex> lock(lowcmd_mutex_);
    latest_lowcmd_ = snapshot;
}

bool Recorder::shouldSample(uint64_t steady_time_ns)
{
    const uint64_t interval_ns = static_cast<uint64_t>((1.0 / config_.sample_hz) * 1000000000.0);
    std::lock_guard<std::mutex> lock(sample_mutex_);
    if (last_sample_steady_ns_ == 0) {
        last_sample_steady_ns_ = steady_time_ns;
        return true;
    }
    if (steady_time_ns - last_sample_steady_ns_ < interval_ns) {
        return false;
    }
    last_sample_steady_ns_ = steady_time_ns;
    return true;
}

bool Recorder::validateCrc(const unitree_hg::msg::dds_::LowState_& low_state) const
{
    auto copy = low_state;
    return copy.crc() == crc32Core(reinterpret_cast<uint32_t*>(&copy), (sizeof(copy) >> 2) - 1);
}

bool Recorder::validateCrc(const unitree_hg::msg::dds_::LowCmd_& low_cmd) const
{
    auto copy = low_cmd;
    return copy.crc() == crc32Core(reinterpret_cast<uint32_t*>(&copy), (sizeof(copy) >> 2) - 1);
}

void Recorder::copyLatestLowCmd(TelemetrySample& sample)
{
    std::lock_guard<std::mutex> lock(lowcmd_mutex_);
    sample.lowcmd_steady_time_ns = latest_lowcmd_.lowcmd_steady_time_ns;
    sample.lowcmd_sequence = latest_lowcmd_.lowcmd_sequence;
    sample.lowcmd_received = latest_lowcmd_.lowcmd_received;
    sample.lowcmd_mode_pr = latest_lowcmd_.lowcmd_mode_pr;
    sample.lowcmd_mode_machine = latest_lowcmd_.lowcmd_mode_machine;
    sample.lowcmd_reserve = latest_lowcmd_.lowcmd_reserve;
    sample.lowcmd_crc = latest_lowcmd_.lowcmd_crc;
    sample.cmd_mode = latest_lowcmd_.cmd_mode;
    sample.cmd_q = latest_lowcmd_.cmd_q;
    sample.cmd_dq = latest_lowcmd_.cmd_dq;
    sample.cmd_tau = latest_lowcmd_.cmd_tau;
    sample.cmd_kp = latest_lowcmd_.cmd_kp;
    sample.cmd_kd = latest_lowcmd_.cmd_kd;
    sample.cmd_reserve = latest_lowcmd_.cmd_reserve;
}

TelemetrySample Recorder::makeSample(const unitree_hg::msg::dds_::LowState_& low_state)
{
    TelemetrySample sample;
    sample.source_tick = low_state.tick();
    sample.mode_pr = low_state.mode_pr();
    sample.mode_machine = low_state.mode_machine();

    const auto& motors = low_state.motor_state();
    const uint32_t count = std::min<uint32_t>(config_.motor_count, motors.size());
    for (uint32_t i = 0; i < count; ++i) {
        const auto& motor = motors[i];
        const auto& temps = motor.temperature();
        sample.q[i] = motor.q();
        sample.dq[i] = motor.dq();
        sample.tau_est[i] = motor.tau_est();
        sample.temp_case[i] = temps[0];
        sample.temp_winding[i] = temps[1];
        sample.motor_state[i] = motor.motorstate();
    }

    const auto& imu = low_state.imu_state();
    const auto& quat = imu.quaternion();
    const auto& gyro = imu.gyroscope();
    const auto& accel = imu.accelerometer();
    const auto& rpy = imu.rpy();
    std::copy(quat.begin(), quat.end(), sample.imu_quat.begin());
    std::copy(gyro.begin(), gyro.end(), sample.imu_gyro.begin());
    std::copy(accel.begin(), accel.end(), sample.imu_accel.begin());
    std::copy(rpy.begin(), rpy.end(), sample.imu_rpy.begin());
    sample.imu_temp = imu.temperature();

    return sample;
}

}  // namespace unitree_rerun
