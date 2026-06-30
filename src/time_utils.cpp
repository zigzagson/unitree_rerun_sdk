#include "unitree_rerun_sdk/time_utils.h"

#include <chrono>
#include <ctime>
#include <iomanip>
#include <sstream>

namespace unitree_rerun {

uint64_t unixTimeNs()
{
    const auto now = std::chrono::system_clock::now().time_since_epoch();
    return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(now).count());
}

uint64_t steadyTimeNs()
{
    const auto now = std::chrono::steady_clock::now().time_since_epoch();
    return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(now).count());
}

std::string timestampForPath(uint64_t unix_time_ns)
{
    const std::time_t tt = static_cast<std::time_t>(unix_time_ns / 1000000000ULL);
    std::tm tm_buf;
    localtime_r(&tt, &tm_buf);

    std::ostringstream oss;
    oss << std::put_time(&tm_buf, "%Y%m%d_%H%M%S");
    return oss.str();
}

std::string isoTime(uint64_t unix_time_ns)
{
    const std::time_t tt = static_cast<std::time_t>(unix_time_ns / 1000000000ULL);
    const uint64_t ns = unix_time_ns % 1000000000ULL;
    std::tm tm_buf;
    localtime_r(&tt, &tm_buf);

    std::ostringstream oss;
    oss << std::put_time(&tm_buf, "%Y-%m-%d %H:%M:%S")
        << "." << std::setw(9) << std::setfill('0') << ns;
    return oss.str();
}

}  // namespace unitree_rerun
