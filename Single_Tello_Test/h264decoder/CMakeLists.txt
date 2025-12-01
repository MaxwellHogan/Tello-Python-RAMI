cmake_minimum_required(VERSION 3.20)
project(python_h264decoder LANGUAGES CXX)

# CMake 4.2+ note: legacy FindBoost is removed; prefer BoostConfig.cmake
if(POLICY CMP0167)
  cmake_policy(SET CMP0167 NEW)
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# -------------------------------
# Python 3 setup (building a Python extension module)
# -------------------------------
find_package(Python3 REQUIRED COMPONENTS Interpreter Development.Module)
message(STATUS "Using Python include dir: ${Python3_INCLUDE_DIRS}")
message(STATUS "Using Python libraries  : ${Python3_LIBRARIES}")

# -------------------------------
# Boost (Python bindings) via BoostConfig (vcpkg-friendly)
# -------------------------------
set(_boost_py "python${Python3_VERSION_MAJOR}${Python3_VERSION_MINOR}")
find_package(Boost CONFIG REQUIRED COMPONENTS ${_boost_py})
message(STATUS "Using Boost component   : ${_boost_py}")

# -------------------------------
# FFmpeg (avcodec/avutil/swscale)
# If you installed ffmpeg via vcpkg, the toolchain will make these searchable.
# -------------------------------
find_path(FFMPEG_INCLUDE_DIR
  NAMES libavcodec/avcodec.h
)

find_library(AVCODEC_LIB NAMES avcodec)
find_library(AVUTIL_LIB  NAMES avutil)
find_library(SWSCALE_LIB NAMES swscale)

if(NOT FFMPEG_INCLUDE_DIR OR NOT AVCODEC_LIB OR NOT AVUTIL_LIB OR NOT SWSCALE_LIB)
  message(FATAL_ERROR
    "FFmpeg not found.\n"
    "  FFMPEG_INCLUDE_DIR=${FFMPEG_INCLUDE_DIR}\n"
    "  AVCODEC_LIB=${AVCODEC_LIB}\n"
    "  AVUTIL_LIB=${AVUTIL_LIB}\n"
    "  SWSCALE_LIB=${SWSCALE_LIB}\n"
    "If using vcpkg: vcpkg install ffmpeg:x64-windows (or your triplet)."
  )
endif()

# -------------------------------
# Build the Python extension module
# -------------------------------
add_library(h264decoder MODULE
  h264decoder.cpp
  h264decoder_python.cpp
)

# Python extension modules should not be prefixed with "lib"
set_target_properties(h264decoder PROPERTIES PREFIX "")

# On Windows, make sure the extension is .pyd
if(WIN32)
  set_target_properties(h264decoder PROPERTIES SUFFIX ".pyd")
endif()

target_include_directories(h264decoder
  PRIVATE
    ${FFMPEG_INCLUDE_DIR}
)

target_link_libraries(h264decoder
  PRIVATE
    Python3::Module
    Boost::${_boost_py}
    ${AVCODEC_LIB}
    ${SWSCALE_LIB}
    ${AVUTIL_LIB}
)

# -------------------------------
# Copy built module next to source after build (cross-platform)
# -------------------------------
add_custom_command(TARGET h264decoder POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E copy_if_different
          "$<TARGET_FILE:h264decoder>"
          "${CMAKE_SOURCE_DIR}/$<TARGET_FILE_NAME:h264decoder>"
)

# -------------------------------
# Install target (covers Windows + Linux)
# -------------------------------
install(TARGETS h264decoder
  RUNTIME DESTINATION .
  LIBRARY DESTINATION .
  ARCHIVE DESTINATION .
)