#pragma once
/*
Thin wrapper around libav/FFmpeg decoder functions to decode H.264.
Kept separate from the Python bindings for clarity.

Originally based on:
http://roxlu.com/2014/039/decoding-h264-and-yuv420p-playback
*/

#include <cstdint>
#include <cstdlib>
#include <stdexcept>
#include <utility>

// -------------------------------
// ssize_t portability (MSVC)
// -------------------------------
// MSVC doesn't define ssize_t by default. Define it so headers compile.
#if defined(_MSC_VER)
  #include <BaseTsd.h>
  typedef SSIZE_T ssize_t;
#elif defined(__unix__) || defined(__APPLE__)
  #include <sys/types.h> // ssize_t
#endif

// Forward declarations (we avoid including FFmpeg headers here)
struct AVCodecContext;
struct AVFrame;
struct AVCodec;
struct AVCodecParserContext;
struct SwsContext;
struct AVPacket;

class H264Exception : public std::runtime_error {
public:
  explicit H264Exception(const char* s) : std::runtime_error(s) {}
};

class H264InitFailure : public H264Exception {
public:
  explicit H264InitFailure(const char* s) : H264Exception(s) {}
};

class H264DecodeFailure : public H264Exception {
public:
  explicit H264DecodeFailure(const char* s) : H264Exception(s) {}
};

class H264Decoder
{
  // Persistent objects; RAII cleanup in destructor.
  AVCodecContext*       context = nullptr;
  AVFrame*              frame   = nullptr;

  // Modern FFmpeg returns const AVCodec* from avcodec_find_decoder().
  // Keep this const to avoid MSVC conversion errors.
  const AVCodec*        codec   = nullptr;

  AVCodecParserContext* parser  = nullptr;

  // Packet is kept as a pointer to preserve packet/data ownership between parse/decode,
  // depending on how your .cpp manages memory (av_packet_alloc/free, etc.).
  AVPacket*             pkt     = nullptr;

public:
  H264Decoder();
  ~H264Decoder();

  // Parse a continuous bytestream into packets.
  // Returns number of consumed bytes; stops at frame boundaries.
  ssize_t parse(const unsigned char* in_data, ssize_t in_size);

  bool is_frame_available() const;
  const AVFrame& decode_frame();
};

// TODO: Rename to OutputStage or similar
class ConverterRGB24
{
  SwsContext* context  = nullptr;
  AVFrame*    framergb = nullptr;

public:
  ConverterRGB24();
  ~ConverterRGB24();

  // Returns the number of bytes needed for an RGB24 buffer.
  int predict_size(int w, int h);

  // Convert decoded frame -> RGB24, store in out_rgb.
  // Returns an AVFrame with metadata about the RGB frame.
  const AVFrame& convert(const AVFrame& frame, unsigned char* out_rgb);
};

void disable_logging();

// Wrappers, so we don't have to include FFmpeg headers.
std::pair<int, int> width_height(const AVFrame&);
int row_size(const AVFrame&);