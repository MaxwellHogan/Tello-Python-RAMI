#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <cassert>

// Python C-API
extern "C" {
  #include <Python.h>
}

#include <boost/python.hpp>
namespace py = boost::python;

#include "h264decoder.hpp"

using ubyte = unsigned char;

class GILScopedReverseLock
{
public:
  GILScopedReverseLock()
    : state(nullptr)
  {
    unlock();
  }

  ~GILScopedReverseLock()
  {
    lock();
  }

  void lock()
  {
    if (state != nullptr)
    {
      PyEval_RestoreThread(state);
      state = nullptr;
    }
  }

  void unlock()
  {
    assert(state == nullptr);
    state = PyEval_SaveThread();
  }

  GILScopedReverseLock(const GILScopedReverseLock&) = delete;
  GILScopedReverseLock(GILScopedReverseLock&&) = delete;
  GILScopedReverseLock& operator=(const GILScopedReverseLock&) = delete;
  GILScopedReverseLock& operator=(GILScopedReverseLock&&) = delete;

private:
  PyThreadState* state;
};

/* Wrapped via boost::python */
class PyH264Decoder
{
  H264Decoder decoder;
  ConverterRGB24 converter;

  py::tuple decode_frame_impl(
    const ubyte* data,
    Py_ssize_t len,
    Py_ssize_t& num_consumed,
    bool& is_frame_available
  );

public:
  py::tuple decode_frame(const py::object& data_in); // expects bytes
  py::list  decode(const py::object& data_in);       // expects bytes
};

py::tuple PyH264Decoder::decode_frame_impl(const ubyte* data_in,
                                           Py_ssize_t len,
                                           Py_ssize_t& num_consumed,
                                           bool& is_frame_available)
{
  GILScopedReverseLock gilguard;

  // H264Decoder::parse uses ssize_t; cast safely.
  const ssize_t consumed = decoder.parse(reinterpret_cast<const ubyte*>(data_in),
                                         static_cast<ssize_t>(len));
  num_consumed = static_cast<Py_ssize_t>(consumed);

  is_frame_available = decoder.is_frame_available();
  if (is_frame_available)
  {
    const auto& frame = decoder.decode_frame();
    int w, h;
    std::tie(w, h) = width_height(frame);

    const Py_ssize_t out_size = static_cast<Py_ssize_t>(converter.predict_size(w, h));

    gilguard.lock();
    py::object py_out_bytes(py::handle<>(PyBytes_FromStringAndSize(nullptr, out_size)));
    char* out_buffer = PyBytes_AsString(py_out_bytes.ptr());
    gilguard.unlock();

    const auto& rgbframe = converter.convert(frame, reinterpret_cast<ubyte*>(out_buffer));

    gilguard.lock();
    return py::make_tuple(py_out_bytes, w, h, row_size(rgbframe));
  }

  gilguard.lock();
  return py::make_tuple(py::object(), 0, 0, 0);
}

py::tuple PyH264Decoder::decode_frame(const py::object& data_in)
{
  if (!PyBytes_Check(data_in.ptr()))
    throw std::runtime_error("decode_frame expects a 'bytes' object");

  char* buf = nullptr;
  Py_ssize_t len = 0;
  if (PyBytes_AsStringAndSize(data_in.ptr(), &buf, &len) != 0)
    throw std::runtime_error("Failed to read bytes buffer");

  Py_ssize_t num_consumed = 0;
  bool is_frame_available = false;

  const auto frame = decode_frame_impl(reinterpret_cast<const ubyte*>(buf),
                                       len, num_consumed, is_frame_available);

  return py::make_tuple(frame, num_consumed);
}

py::list PyH264Decoder::decode(const py::object& data_in)
{
  if (!PyBytes_Check(data_in.ptr()))
    throw std::runtime_error("decode expects a 'bytes' object");

  char* buf = nullptr;
  Py_ssize_t len = 0;
  if (PyBytes_AsStringAndSize(data_in.ptr(), &buf, &len) != 0)
    throw std::runtime_error("Failed to read bytes buffer");

  const ubyte* data = reinterpret_cast<const ubyte*>(buf);
  py::list out;

  try {
    while (len > 0) {
      Py_ssize_t num_consumed = 0;
      bool is_frame_available = false;

      try {
        const auto frame = decode_frame_impl(data, len, num_consumed, is_frame_available);
        if (is_frame_available) out.append(frame);
      } catch (const H264DecodeFailure&) {
        if (num_consumed <= 0) throw;
      }

      len -= num_consumed;
      data += num_consumed;
    }
  } catch (const H264DecodeFailure&) {
    // swallow partial
  }

  return out;
}

// IMPORTANT: module name must match the built .pyd name.
// If your output file is h264decoder.pyd, use BOOST_PYTHON_MODULE(h264decoder).
BOOST_PYTHON_MODULE(h264decoder)
{
#if PY_VERSION_HEX < 0x03070000
  PyEval_InitThreads();
#endif

  py::class_<PyH264Decoder>("H264Decoder")
    .def("decode_frame", &PyH264Decoder::decode_frame)
    .def("decode", &PyH264Decoder::decode);

  py::def("disable_logging", disable_logging);
}
