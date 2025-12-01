from tello import Tello
import socket
import cv2
import numpy as np
import sys
import time

sys.path.insert(0, r"D:/Projects/Task_1_EPM110/Project_2/Tello-Python-RAMI/Tello_Video/h264decoder/build/Release")
import h264decoder

TELLO_VIDEO_PORT = 11111

# Tuning knobs
MAX_STREAM_BUFFER_BYTES = 250_000     # cap to prevent growing latency (lower = lower latency)
MAX_DECODE_STEPS_PER_TICK = 8         # how much we try to "catch up" per UI tick
SHOW_EVERY_NTH_FRAME = 1              # set to 2 or 3 if your CPU is struggling
SOCKET_RCVBUF = 4 * 1024 * 1024

WAIT_FOR_SPS_PPS_AND_IDR = True
INJECT_SPS_PPS_BEFORE_IDR = True

def iter_annexb_nals(buf: bytes):
    nals = []
    i = 0
    L = len(buf)

    def find_start(from_i):
        j = buf.find(b"\x00\x00\x00\x01", from_i)
        k = buf.find(b"\x00\x00\x01", from_i)
        j = j if j != -1 else 10**18
        k = k if k != -1 else 10**18
        p = min(j, k)
        if p == 10**18:
            return -1, 0
        return p, (4 if p == j else 3)

    p, sc = find_start(0)
    if p == -1:
        return nals

    while p != -1:
        next_p, next_sc = find_start(p + sc)
        end = next_p if next_p != -1 else L
        nals.append(buf[p:end])
        p, sc = next_p, next_sc

    return nals

def nal_type_from_annexb(nal: bytes):
    if nal.startswith(b"\x00\x00\x00\x01"):
        off = 4
    elif nal.startswith(b"\x00\x00\x01"):
        off = 3
    else:
        return None
    return (nal[off] & 0x1F) if len(nal) > off else None

def frame_bytes_to_bgr(frame_bytes: bytes, w: int, h: int, stride: int):
    raw = np.frombuffer(frame_bytes, dtype=np.uint8)
    if raw.size < h * stride:
        return None
    img = raw[:h * stride].reshape((h, stride))
    img = img[:, :w * 3].reshape((h, w, 3))  # RGB24
    return img[:, :, ::-1]  # BGR for OpenCV

def reset_decoder():
    return h264decoder.H264Decoder()

# --- Start Tello
tello = Tello()
tello.send_command("command")
tello.send_command("streamon")

# --- UDP
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('', TELLO_VIDEO_PORT))
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SOCKET_RCVBUF)
sock.setblocking(False)

decoder = reset_decoder()

sps = None
pps = None
seen_idr = False
decoder_started = not WAIT_FOR_SPS_PPS_AND_IDR

stream_buf = bytearray()
frame_count = 0
last_frame = None

print("[INFO] Running... Press 'q' to quit.")

try:
    cv2.namedWindow("Tello Video", cv2.WINDOW_NORMAL)

    while True:
        # 1) Drain all pending UDP packets quickly (prevents OS buffer overflow)
        got_any = False
        while True:
            try:
                pkt, _ = sock.recvfrom(65535)  # avoid truncation
            except BlockingIOError:
                break
            if not pkt:
                continue
            got_any = True

            # Update SPS/PPS/IDR cache
            nals = iter_annexb_nals(pkt)
            pkt_has_idr = False
            for nal in nals:
                t = nal_type_from_annexb(nal)
                if t == 7: sps = nal
                elif t == 8: pps = nal
                elif t == 5:
                    pkt_has_idr = True
                    seen_idr = True

            # Gate decoding start until SPS+PPS+IDR
            if WAIT_FOR_SPS_PPS_AND_IDR and not decoder_started:
                if (sps is not None) and (pps is not None) and seen_idr:
                    decoder_started = True
                    # Hard reset right at the moment we have the right context
                    decoder = reset_decoder()
                    stream_buf.clear()
                    print("[INFO] SPS+PPS+IDR seen -> starting decode (reset).")
                else:
                    continue

            # Inject SPS/PPS before IDR to help clean lock
            if INJECT_SPS_PPS_BEFORE_IDR and pkt_has_idr and sps and pps:
                stream_buf.extend(sps)
                stream_buf.extend(pps)

            stream_buf.extend(pkt)

            # 2) If we’re falling behind, drop buffered data and resync
            if len(stream_buf) > MAX_STREAM_BUFFER_BYTES:
                decoder = reset_decoder()
                stream_buf.clear()
                # Force waiting for a clean keyframe again
                if WAIT_FOR_SPS_PPS_AND_IDR:
                    decoder_started = False
                    # keep cached sps/pps; wait for next IDR
                    seen_idr = False
                print("[WARN] Buffer overflow -> dropping backlog and resyncing.")
                break

        # If nothing arrived, still pump UI
        if not got_any:
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            continue

        if not decoder_started:
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            continue

        # 3) Decode a limited amount per tick (keeps UI responsive / reduces latency)
        steps = 0
        while stream_buf and steps < MAX_DECODE_STEPS_PER_TICK:
            try:
                (frame_tuple, consumed) = decoder.decode_frame(bytes(stream_buf))
            except Exception:
                # If decoder chokes, resync on next IDR
                decoder = reset_decoder()
                stream_buf.clear()
                if WAIT_FOR_SPS_PPS_AND_IDR:
                    decoder_started = False
                    seen_idr = False
                print("[WARN] Decode error -> resyncing.")
                break

            if consumed <= 0:
                break

            del stream_buf[:consumed]

            (frame_bytes, w, h, stride) = frame_tuple
            if frame_bytes:
                frame_count += 1
                if (frame_count % SHOW_EVERY_NTH_FRAME) == 0:
                    last_frame = (frame_bytes, w, h, stride)

            steps += 1

        # 4) Display latest decoded frame only (prevents “playing catch-up”)
        if last_frame is not None:
            frame_bytes, w, h, stride = last_frame
            img_bgr = frame_bytes_to_bgr(frame_bytes, w, h, stride)
            if img_bgr is not None:
                cv2.imshow("Tello Video", img_bgr)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

finally:
    tello.send_command("streamoff")
    sock.close()
    cv2.destroyAllWindows()
    print("[INFO] Finished.")
