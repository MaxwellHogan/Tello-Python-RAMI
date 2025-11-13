cmake_minimum_required(VERSION 3.12)
project(python_h264decoder)

# Detect platform
if(UNIX AND NOT APPLE)
    set(LINUX TRUE)
endif()

# -------------------------------
# Python 3 setup
# -------------------------------
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)
message(STATUS "Using Python include dir: ${Python3_INCLUDE_DIRS}")
message(STATUS "Using Python libraries  : ${Python3_LIBRARIES}")

# -------------------------------
# Boost (Python bindings)
# -------------------------------
# You have libboost_python38, so we use that component
find_package(Boost REQUIRED COMPONENTS python38)
message(STATUS "Using Boost include dir : ${Boost_INCLUDE_DIRS}")
message(STATUS "Using Boost libraries   : ${Boost_LIBRARIES}")

# -------------------------------
# Include and link directories
# -------------------------------
include_directories(${Python3_INCLUDE_DIRS})
include_directories(${Boost_INCLUDE_DIRS})
link_directories(${Boost_LIBRARY_DIRS})

# -------------------------------
# Compiler setup
# -------------------------------
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# -------------------------------
# Build the shared library
# -------------------------------
add_library(h264decoder SHARED
    h264decoder.cpp
    h264decoder_python.cpp
)

# -------------------------------
# Link the necessary libraries
# -------------------------------
target_link_libraries(h264decoder
    avcodec
    swscale
    avutil
    ${Boost_LIBRARIES}
    ${Python3_LIBRARIES}
)

# -------------------------------
# Create symbolic link after build
# -------------------------------
add_custom_command(TARGET h264decoder POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E create_symlink
    ${CMAKE_BINARY_DIR}/libh264decoder.so
    ${CMAKE_SOURCE_DIR}/libh264decoder.so
)

# -------------------------------
# Install target
# -------------------------------
install(TARGETS h264decoder LIBRARY DESTINATION .)
