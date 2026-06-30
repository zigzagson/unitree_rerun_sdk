cmake_minimum_required(VERSION 3.14)
project(unitree_rerun_sdk LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(unitree_sdk2 REQUIRED)

add_library(unitree_rerun_sdk
    src/config.cpp
    src/recorder.cpp
    src/telemetry_writer.cpp
    src/time_utils.cpp
)

target_include_directories(unitree_rerun_sdk
    PUBLIC
        ${PROJECT_SOURCE_DIR}/include
)

target_link_libraries(unitree_rerun_sdk
    PUBLIC
        unitree_sdk2
)

target_compile_options(unitree_rerun_sdk PRIVATE -Wall -Wextra -Wpedantic)

add_executable(unitree_rerun_recorder src/main.cpp)
target_link_libraries(unitree_rerun_recorder PRIVATE unitree_rerun_sdk)

install(TARGETS unitree_rerun_sdk unitree_rerun_recorder
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION bin
)

install(DIRECTORY include/ DESTINATION include)
install(DIRECTORY examples/ DESTINATION share/unitree_rerun_sdk/examples)
install(DIRECTORY tools/ DESTINATION share/unitree_rerun_sdk/tools)
