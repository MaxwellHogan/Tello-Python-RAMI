extern "C" {
#include <libavcodec/avcodec.h>
#include <libavutil/avutil.h>
#include <libavutil/mem.h>
#include <libavutil/imgutils.h>
#include <libswscale/swscale.h>
}

#include "h264decoder.hpp"

#include <cstring>   // std::memcpy
#include <utility>

typedef unsigned char ubyte;

#ifndef PIX_FMT_RGB24
#define PIX_FMT_RGB24 AV_PIX_FMT_RGB24
#endif

/* For backward compatibility with very old LibAV/FFmpeg */
#if (LIBAVCODEC_VERSION_MAJOR <= 54)
#  define av_frame_alloc avcodec_alloc_frame
#  define av_frame_free  avcodec_free_frame
#endif

H264Decoder::H264Decoder()
{
  // Modern FFmpeg: no need to call avcodec_register_all()

  codec = avcodec_find_decoder(AV_CODEC_ID_H264);
  if (!codec)
    throw H264InitFailure("cannot find H.264 decoder");

  context = avcodec_alloc_context3(codec);
  if (!context)
    throw H264InitFailure("cannot allocate codec context");

  if (avcodec_open2(context, codec, nullptr) < 0)
    throw H264InitFailure("cannot open codec context");

  parser = av_parser_init(AV_CODEC_ID_H264);
  if (!parser)
    throw H264InitFailure("cannot init H.264 parser");

  frame = av_frame_alloc();
  if (!frame)
    throw H264InitFailure("cannot allocate frame");

  pkt = av_packet_alloc();
  if (!pkt)
    throw H264InitFailure("cannot allocate packet");
}

H264Decoder::~H264Decoder()
{
  if (parser) {
    av_parser_close(parser);
    parser = nullptr;
  }

  if (context) {
    avcodec_free_context(&context); // frees + nulls pointer
  }

  if (frame) {
    av_frame_free(&frame);
  }

  if (pkt) {
    av_packet_free(&pkt);
  }
}

ssize_t H264Decoder::parse(const ubyte* in_data, ssize_t in_size)
{
  if (!in_data || in_size <= 0) {
    if (pkt) av_packet_unref(pkt);
    return 0;
  }

  uint8_t* out_data = nullptr;
  int out_size = 0;

  int nread = av_parser_parse2(
    parser,
    context,
    &out_data,
    &out_size,
    reinterpret_cast<const uint8_t*>(in_data),
    static_cast<int>(in_size),
    AV_NOPTS_VALUE,
    AV_NOPTS_VALUE,
    0
  );

  if (nread < 0)
    throw H264DecodeFailure("error parsing H.264 stream");

  // Own the packet bytes so decode_frame() can be called later safely.
  av_packet_unref(pkt);

  if (out_size > 0 && out_data) {
    // Allocate packet buffer and copy payload into pkt->data
    if (av_new_packet(pkt, out_size) < 0)
      throw H264InitFailure("cannot allocate packet payload");
    std::memcpy(pkt->data, out_data, static_cast<size_t>(out_size));
  }

  return static_cast<ssize_t>(nread);
}

bool H264Decoder::is_frame_available() const
{
  return pkt && pkt->size > 0;
}

const AVFrame& H264Decoder::decode_frame()
{
  if (!pkt || pkt->size <= 0)
    throw H264DecodeFailure("no packet available for decoding");

  // Send packet to decoder
  int ret = avcodec_send_packet(context, pkt);
  if (ret < 0)
    throw H264DecodeFailure("error sending packet to decoder");

  // Receive decoded frame
  ret = avcodec_receive_frame(context, frame);
  if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF) {
    // No frame produced yet (needs more data)
    throw H264DecodeFailure("no frame produced yet");
  }
  if (ret < 0)
    throw H264DecodeFailure("error receiving decoded frame");

  return *frame;
}

ConverterRGB24::ConverterRGB24()
{
  framergb = av_frame_alloc();
  if (!framergb)
    throw H264DecodeFailure("cannot allocate RGB frame");

  context = nullptr;
}

ConverterRGB24::~ConverterRGB24()
{
  if (context) {
    sws_freeContext(context);
    context = nullptr;
  }
  if (framergb) {
    av_frame_free(&framergb);
  }
}

const AVFrame& ConverterRGB24::convert(const AVFrame& frame_in, ubyte* out_rgb)
{
  if (!out_rgb)
    throw H264DecodeFailure("RGB output buffer is null");

  const int w = frame_in.width;
  const int h = frame_in.height;
  const AVPixelFormat src_fmt = static_cast<AVPixelFormat>(frame_in.format);

  context = sws_getCachedContext(
    context,
    w, h, src_fmt,
    w, h, AV_PIX_FMT_RGB24,
    SWS_BILINEAR,
    nullptr, nullptr, nullptr
  );
  if (!context)
    throw H264DecodeFailure("cannot allocate swscale context");

  // Point framergb at external buffer out_rgb
  framergb->format = AV_PIX_FMT_RGB24;
  framergb->width  = w;
  framergb->height = h;

  int fill_ok = av_image_fill_arrays(
    framergb->data,
    framergb->linesize,
    out_rgb,
    AV_PIX_FMT_RGB24,
    w, h, 1
  );
  if (fill_ok < 0)
    throw H264DecodeFailure("av_image_fill_arrays failed");

  sws_scale(
    context,
    frame_in.data,
    frame_in.linesize,
    0, h,
    framergb->data,
    framergb->linesize
  );

  return *framergb;
}

int ConverterRGB24::predict_size(int w, int h)
{
  int sz = av_image_get_buffer_size(AV_PIX_FMT_RGB24, w, h, 1);
  if (sz < 0)
    throw H264DecodeFailure("av_image_get_buffer_size failed");
  return sz;
}

std::pair<int, int> width_height(const AVFrame& f)
{
  return std::make_pair(f.width, f.height);
}

int row_size(const AVFrame& f)
{
  return f.linesize[0];
}

void disable_logging()
{
  av_log_set_level(AV_LOG_QUIET);
}
