#ifndef UNITREE_RERUN_SDK_TIME_UTILS_H
#define UNITREE_RERUN_SDK_TIME_UTILS_H

#include <cstdint>
#include <string>

namespace unitree_rerun {

uint64_t unixTimeNs();
uint64_t steadyTimeNs();
std::string timestampForPath(uint64_t unix_time_ns);
std::string isoTime(uint64_t unix_time_ns);

}  // namespace unitree_rerun

#endif  // UNITREE_RERUN_SDK_TIME_UTILS_H
