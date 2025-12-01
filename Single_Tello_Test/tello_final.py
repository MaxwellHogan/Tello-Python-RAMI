import math
import time
from dataclasses import dataclass
from typing import List, Tuple, Optional

from tello import Tello
from datetime import datetime
import os
import socket
import sys

import numpy as np
import cv2

from checker_detect_sol4 import CheckerboardDetection

# --- your compiled decoder ---
sys.path.insert(0, r"D:/Projects/Task_1_EPM110/Project_2/Tello-Python-RAMI/Tello_Video/h264decoder/build/Release")
import h264decoder
print("[INFO] h264decoder loaded from:", h264decoder.__file__)
# h264decoder.disable_logging()  # uncomment to silence FFmpeg spew


# =========================
# Checkerboard settings
# =========================
CHECKERBOARD_INNER_CORNERS = (15, 10)   # <-- CHANGE THIS to your board inner corners (cols, rows)
STABLE_FRAMES_REQUIRED = 5
DETECT_TIMEOUT_S = 30.0

# Video / latency tuning
MAX_STREAM_BUFFER_BYTES = 250_000
MAX_DECODE_STEPS_PER_TICK = 8
SOCKET_RCVBUF = 4 * 1024 * 1024
SHOW_WINDOW = True


# =========================
# Basic 2D grid + A* planner (unchanged)
# =========================

@dataclass
class MapConfig:
    x_min: int
    x_max: int
    y_min: int
    y_max: int
    resolution: int = 10  # grid cell size in cm

@dataclass
class PlannerConfig:
    drone_radius_cm: int = 15
    safety_margin_cm: int = 20
    diag_moves: bool = True

def to_grid_coords(x_cm: float, y_cm: float, cfg: MapConfig) -> Tuple[int, int]:
    gx = int((x_cm - cfg.x_min) // cfg.resolution)
    gy = int((y_cm - cfg.y_min) // cfg.resolution)
    return gx, gy

def to_world_coords(gx: int, gy: int, cfg: MapConfig) -> Tuple[int, int]:
    x = cfg.x_min + gx * cfg.resolution + cfg.resolution // 2
    y = cfg.y_min + gy * cfg.resolution + cfg.resolution // 2
    return x, y

def build_occupancy_grid(obstacles_xy_cm: List[Tuple[float, float]],
                         mcfg: MapConfig,
                         pcfg: PlannerConfig) -> np.ndarray:
    width = int(math.ceil((mcfg.x_max - mcfg.x_min) / mcfg.resolution))
    height = int(math.ceil((mcfg.y_max - mcfg.y_min) / mcfg.resolution))
    grid = np.zeros((height, width), dtype=np.uint8)

    inflate_r = int(math.ceil((pcfg.drone_radius_cm + pcfg.safety_margin_cm) / mcfg.resolution))

    for ox, oy in obstacles_xy_cm:
        ogx, ogy = to_grid_coords(ox, oy, mcfg)
        for dy in range(-inflate_r, inflate_r + 1):
            for dx in range(-inflate_r, inflate_r + 1):
                if 0 <= ogx + dx < width and 0 <= ogy + dy < height:
                    if dx*dx + dy*dy <= inflate_r*inflate_r:
                        grid[ogy + dy, ogx + dx] = 1
    return grid

def bresenham_line(g0: Tuple[int, int], g1: Tuple[int, int]) -> List[Tuple[int, int]]:
    x0, y0 = g0
    x1, y1 = g1
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    cells = []
    while True:
        cells.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return cells

def line_of_sight_free(g0: Tuple[int, int], g1: Tuple[int, int], occ: np.ndarray) -> bool:
    for (x, y) in bresenham_line(g0, g1):
        if y < 0 or y >= occ.shape[0] or x < 0 or x >= occ.shape[1]:
            return False
        if occ[y, x] == 1:
            return False
    return True

def a_star(occ: np.ndarray, start_g: Tuple[int, int], goal_g: Tuple[int, int],
           allow_diag=True) -> Optional[List[Tuple[int, int]]]:
    H, W = occ.shape
    if not (0 <= start_g[0] < W and 0 <= start_g[1] < H and 0 <= goal_g[0] < W and 0 <= goal_g[1] < H):
        return None
    if occ[start_g[1], start_g[0]] == 1 or occ[goal_g[1], goal_g[0]] == 1:
        return None

    neighbors = [(1,0,1.0), (-1,0,1.0), (0,1,1.0), (0,-1,1.0)]
    if allow_diag:
        diag_c = math.sqrt(2)
        neighbors += [(1,1,diag_c), (1,-1,diag_c), (-1,1,diag_c), (-1,-1,diag_c)]

    import heapq
    open_set = []
    heapq.heappush(open_set, (0.0, start_g))
    came_from = {}
    gscore = {start_g: 0.0}

    def h(a, b):
        dx = abs(a[0]-b[0]); dy = abs(a[1]-b[1])
        return (dx + dy) if not allow_diag else math.hypot(dx, dy)

    closed = set()

    while open_set:
        _, current = heapq.heappop(open_set)
        if current == goal_g:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path

        if current in closed:
            continue
        closed.add(current)

        for dx, dy, cost in neighbors:
            nx, ny = current[0] + dx, current[1] + dy
            if not (0 <= nx < W and 0 <= ny < H):
                continue
            if occ[ny, nx] == 1:
                continue
            ng = gscore[current] + cost
            n = (nx, ny)
            if ng < gscore.get(n, float('inf')):
                came_from[n] = current
                gscore[n] = ng
                heapq.heappush(open_set, (ng + h(n, goal_g), n))
    return None

def smooth_path(grid_path: List[Tuple[int,int]], occ: np.ndarray) -> List[Tuple[int,int]]:
    if not grid_path:
        return grid_path
    smoothed = [grid_path[0]]
    i = 0
    while i < len(grid_path)-1:
        j = len(grid_path)-1
        while j > i+1:
            if line_of_sight_free(grid_path[i], grid_path[j], occ):
                break
            j -= 1
        smoothed.append(grid_path[j])
        i = j
    return smoothed

def plan_path(obstacles_xy_cm, start_xy_cm, goal_xy_cm, map_cfg, planner_cfg):
    occ = build_occupancy_grid(obstacles_xy_cm, map_cfg, planner_cfg)
    s_g = to_grid_coords(*start_xy_cm, map_cfg)
    g_g = to_grid_coords(*goal_xy_cm, map_cfg)

    raw = a_star(occ, s_g, g_g, allow_diag=planner_cfg.diag_moves)
    if raw is None:
        raise RuntimeError("No path found.")
    smooth = smooth_path(raw, occ)
    path_xy = [to_world_coords(gx, gy, map_cfg) for (gx, gy) in smooth]
    return path_xy, occ


# =========================
# Video decode + checkerboard (post-path)
# =========================

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
    return img[:, :, ::-1]  # BGR

def hover_and_detect_checkerboard(tello: Tello, chk: CheckerboardDetection):
    print("[INFO] Starting stream for checkerboard detection...")
    tello.send_command("streamon")
    time.sleep(0.3)

    # Silence FFmpeg spam (optional but reduces overhead)
    # h264decoder.disable_logging()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', 11111))
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
    sock.setblocking(False)

    def reset_decoder():
        return h264decoder.H264Decoder()

    decoder = reset_decoder()

    stream_buf = bytearray()
    MAX_STREAM_BUFFER_BYTES = 120_000        # smaller cap = less latency (and less time to fall behind)
    MAX_DECODE_STEPS_PER_TICK = 4            # don’t burn the CPU trying to catch up

    # resync gating
    need_idr = True
    sps = None
    pps = None
    seen_idr = False
    buffered_after_idr = 0
    MIN_BYTES_AFTER_IDR = 20_000             # helps avoid decoding on a partial keyframe

    # detection throttling
    detect_interval = 0.2                   # seconds (5 Hz)
    last_detect_time = 0.0
    downscale = 0.3                          # detect on half-res
    stable = 0

    t0 = time.time()
    last_frame = None

    if SHOW_WINDOW:
        cv2.namedWindow("Checkerboard", cv2.WINDOW_NORMAL)

    try:
        while True:
            if (time.time() - t0) > DETECT_TIMEOUT_S:
                print("[WARN] Detection timed out.")
                break

            # 1) Drain UDP as fast as possible
            got_any = False
            while True:
                try:
                    pkt, _ = sock.recvfrom(65535)
                except BlockingIOError:
                    break
                if not pkt:
                    continue
                got_any = True

                # Track SPS/PPS/IDR roughly (best-effort)
                for nal in iter_annexb_nals(pkt):
                    t = nal_type_from_annexb(nal)
                    if t == 7: sps = nal
                    elif t == 8: pps = nal
                    elif t == 5:
                        seen_idr = True
                        if need_idr:
                            buffered_after_idr = 0  # start counting bytes after the IDR appeared

                # If we’re resyncing, only start buffering once we’ve seen SPS+PPS+IDR
                if need_idr:
                    if sps is not None and pps is not None and seen_idr:
                        # inject SPS/PPS to help lock-on
                        stream_buf.extend(sps)
                        stream_buf.extend(pps)
                        stream_buf.extend(pkt)
                        buffered_after_idr += len(pkt)
                    else:
                        continue
                else:
                    stream_buf.extend(pkt)

                # Hard cap backlog (prevents delay, but implies drops)
                if len(stream_buf) > MAX_STREAM_BUFFER_BYTES:
                    print("[WARN] Buffer overflow -> drop + wait for next IDR.")
                    decoder = reset_decoder()
                    stream_buf.clear()
                    need_idr = True
                    seen_idr = False
                    buffered_after_idr = 0
                    stable = 0
                    break

            if not got_any:
                if SHOW_WINDOW and (cv2.waitKey(1) & 0xFF) == ord('q'):
                    break
                continue

            # If resyncing, wait until we have “enough” bytes after IDR before decoding
            if need_idr:
                if buffered_after_idr < MIN_BYTES_AFTER_IDR:
                    if SHOW_WINDOW and (cv2.waitKey(1) & 0xFF) == ord('q'):
                        break
                    continue
                print("[INFO] Resync: enough bytes after IDR -> start decoding.")
                need_idr = False  # start decoding normally

            # 2) Decode a few steps per tick; keep only the latest frame
            steps = 0
            while stream_buf and steps < MAX_DECODE_STEPS_PER_TICK:
                try:
                    (frame_tuple, consumed) = decoder.decode_frame(bytes(stream_buf))
                except Exception:
                    print("[WARN] Decode error -> drop + wait for next IDR.")
                    decoder = reset_decoder()
                    stream_buf.clear()
                    need_idr = True
                    seen_idr = False
                    buffered_after_idr = 0
                    stable = 0
                    break

                if consumed <= 0:
                    break
                del stream_buf[:consumed]

                (frame_bytes, w, h, stride) = frame_tuple
                if frame_bytes:
                    last_frame = (frame_bytes, w, h, stride)

                steps += 1

            if last_frame is None:
                continue

            frame_bytes, w, h, stride = last_frame
            img_bgr = frame_bytes_to_bgr(frame_bytes, w, h, stride)
            if img_bgr is None:
                continue

            # 3) Always show live video (cheap)
            view = img_bgr.copy()
            H, W = view.shape[:2]
            cx_img, cy_img = W // 2, H // 2
            cv2.drawMarker(view, (cx_img, cy_img), (255, 255, 255),
                           markerType=cv2.MARKER_CROSS, markerSize=20, thickness=2)

            # 4) Checkerboard detection: throttled + downscaled (much cheaper)
            now = time.time()
            do_detect = (now - last_detect_time) >= detect_interval
            if do_detect:
                last_detect_time = now

                small = cv2.resize(img_bgr, (0, 0), fx=downscale, fy=downscale, interpolation=cv2.INTER_AREA)
                chk.process_image(small)
                #gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

                #found, corners = cv2.findChessboardCorners(
                #    gray,
                #    CHECKERBOARD_INNER_CORNERS,
                #    flags=cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
                #)

                #if found and corners is not None and len(corners) > 0:
                    # centre in small image coords
                    #centre = corners.mean(axis=0).ravel()
                    #cx_s, cy_s = float(centre[0]), float(centre[1])

                    # scale back to full image coords
                    #cx = int(round(cx_s / downscale))
                    #cy = int(round(cy_s / downscale))

                    #cv2.circle(view, (cx, cy), 7, (0, 255, 0), -1)
                    #cv2.line(view, (cx_img, cy_img), (cx, cy), (0, 255, 0), 2)

                    #dx, dy = cx - cx_img, cy - cy_img
                    #cv2.putText(view, f"centre=({cx},{cy}) offset=({dx},{dy})",
                                #(10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                    #stable += 1
                    #if stable >= STABLE_FRAMES_REQUIRED:
                        #print(f"[OK] Checkerboard locked. centre=({cx},{cy}) offset=({dx},{dy})")
                        #break
                #else:
                    #stable = 0
                    #cv2.putText(view, "Searching for checkerboard...",
                                #(10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            if SHOW_WINDOW:
                cv2.imshow("Checkerboard", view)
                if (cv2.waitKey(1) & 0xFF) == ord('q'):
                    break

    finally:
        try:
            tello.send_command("streamoff")
        except Exception:
            pass
        sock.close()
        if SHOW_WINDOW:
            cv2.destroyWindow("Checkerboard")


# =========================
# Main (your pathplanning kept; only post-path part added)
# =========================

def main():
    map_cfg = MapConfig(x_min=-200, x_max=900, y_min=-200, y_max=400, resolution=10)
    planner_cfg = PlannerConfig(drone_radius_cm=15, safety_margin_cm=40, diag_moves=True)
    chk = CheckerboardDetection()

    obstacles_xy_cm = [
        (300, -100), (310, -90), (320, -80), (330, -70), (340, -60), (350, -50), (360, -40), (370, -30),
        (380, -20), (390, -10), (400, 0), (410, 10), (420, 20), (430, 30), (440, 40), (450, 50),
        (460, 60), (470, 70), (480, 80), (490, 90), (500, 100), (510, 110), (520, 120), (530, 130),
        (540, 140), (550, 150), (560, 160), (570, 170), (580, 180), (590, 190), (600, 200),

        (300, 200), (310, 190), (320, 180), (330, 170), (340, 160), (350, 150), (360, 140), (370, 130),
        (380, 120), (390, 110), (400, 100), (410, 90), (420, 80), (430, 70), (440, 60)
    ]

    start_xy_cm = (0, 0)
    goal_xy_cm = (150, 0)

    path_xy, occ = plan_path(obstacles_xy_cm, start_xy_cm, goal_xy_cm, map_cfg, planner_cfg)

    # --- build your command list (unchanged style) ---
    commands = ["command", "takeoff"]
    current_yaw = 0.0

    for i in range(len(path_xy)):
        if i == 0:
            x0, y0 = start_xy_cm
        else:
            x0, y0 = path_xy[i-1]
        x1, y1 = path_xy[i]

        dist = math.hypot(x1 - x0, y1 - y0)
        angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
        turn = angle - current_yaw
        current_yaw += turn

        commands.append("cw {:.4f}".format(turn))
        commands.append("forward {:.4f}".format(dist))

    # Return to take-off yaw
    commands.append("cw {:.4f}".format(-current_yaw))

    # IMPORTANT: do NOT land in commands; we land after checkerboard hover
    # commands.append("land")

    print("Tello commands:")
    print(commands)

    tello = Tello()
    start_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    try:
        # Execute commands
        for command in commands:
            command = command.strip()
            if not command:
                continue
            if "delay" in command:
                sec = float(command.partition("delay")[2])
                time.sleep(sec)
            else:
                tello.send_command(command)
                time.sleep(0.2)

        # --- Now hover, start stream, detect checkerboard and show centre ---
        hover_and_detect_checkerboard(tello, chk)

    finally:
        # Land at the end
        try:
            tello.send_command("land")
        except Exception:
            pass

        # Save log
        log = tello.get_log()
        os.makedirs("log", exist_ok=True)
        log_filename = f"log/{start_time}.txt"
        with open(log_filename, "w") as out:
            for stat in log:
                stat.print_stats()
                out.write(stat.return_stats())
        print(f"[INFO] Log saved to {log_filename}")

if __name__ == "__main__":
    main()
