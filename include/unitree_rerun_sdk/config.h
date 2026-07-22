#ifndef UNITREE_RERUN_SDK_CONFIG_H
#define UNITREE_RERUN_SDK_CONFIG_H

#include <cstddef>
#include <cstdint>
#include <string>

namespace unitree_rerun {

constexpr uint32_t kDefaultMotorCount = 29;
constexpr uint32_t kMaxMotorCount = 35;

struct RecorderConfig {
    int network_mode = 0;
    std::string network_interface = "eno1";
    std::string topic = "rt/lowstate";
    std::string lowcmd_topic = "rt/lowcmd";

    std::string output_dir = "./unitree_logs";
    uint32_t motor_count = kDefaultMotorCount;
    double sample_hz = 20.0;
    double summary_hz = 1.0;
    size_t max_queue_samples = 4096;
    bool validate_crc = true;
};

bool loadConfigFile(const std::string& path, RecorderConfig& config, std::string& error);
bool parseBool(const std::string& value, bool& out);

}  // namespace unitree_rerun

#endif  // UNITREE_RERUN_SDK_CONFIG_H
