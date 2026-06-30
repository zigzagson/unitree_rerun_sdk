#ifndef UNITREE_RERUN_SDK_RECORDER_H
#define UNITREE_RERUN_SDK_RECORDER_H

#include "unitree_rerun_sdk/config.h"
#include "unitree_rerun_sdk/telemetry_writer.h"

#include <atomic>
#include <chrono>
#include <cstdint>
#include <mutex>
#include <string>

#include <unitree/idl/hg/LowState_.hpp>
#include <unitree/robot/channel/channel_subscriber.hpp>

namespace unitree_rerun {

class Recorder {
public:
    Recorder();
    ~Recorder();

    Recorder(const Recorder&) = delete;
    Recorder& operator=(const Recorder&) = delete;

    bool start(const RecorderConfig& config, std::string& error);
    void stop();
    void waitUntilStopped();
    void requestStop();

    const std::string& sessionDir() const { return writer_.sessionDir(); }

private:
    void lowStateHandler(const void* message);
    bool shouldSample(uint64_t steady_time_ns);
    bool validateCrc(const unitree_hg::msg::dds_::LowState_& low_state) const;
    TelemetrySample makeSample(const unitree_hg::msg::dds_::LowState_& low_state);

    RecorderConfig config_;
    TelemetryWriter writer_;
    unitree::robot::ChannelSubscriberPtr<unitree_hg::msg::dds_::LowState_> subscriber_;

    std::atomic<bool> running_;
    std::atomic<uint64_t> sequence_;
    std::atomic<uint64_t> crc_errors_;
    std::mutex sample_mutex_;
    uint64_t last_sample_steady_ns_;
};

}  // namespace unitree_rerun

#endif  // UNITREE_RERUN_SDK_RECORDER_H
