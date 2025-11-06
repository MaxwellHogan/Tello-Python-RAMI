import math
import time
from dataclasses import dataclass
from typing import List, Tuple, Optional

from tello import Tello
from datetime import datetime
import os

import numpy as np


# =========================
# Basic 2D grid + A* planner
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
    drone_radius_cm: int = 15     # ~Tello diagonal/clearance (adjust as needed)
    safety_margin_cm: int = 20    # extra buffer around obstacles
    diag_moves: bool = True       # allow 8-connected A*

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
    """1 = occupied, 0 = free"""
    width = int(math.ceil((mcfg.x_max - mcfg.x_min) / mcfg.resolution))
    height = int(math.ceil((mcfg.y_max - mcfg.y_min) / mcfg.resolution))
    grid = np.zeros((height, width), dtype=np.uint8)

    inflate_r = int(math.ceil((pcfg.drone_radius_cm + pcfg.safety_margin_cm) / mcfg.resolution))

    for ox, oy in obstacles_xy_cm:
        ogx, ogy = to_grid_coords(ox, oy, mcfg)
        # Inflate as a disk in grid space
        for dy in range(-inflate_r, inflate_r + 1):
            for dx in range(-inflate_r, inflate_r + 1):
                if 0 <= ogx + dx < width and 0 <= ogy + dy < height:
                    if dx*dx + dy*dy <= inflate_r*inflate_r:
                        grid[ogy + dy, ogx + dx] = 1
    return grid

def bresenham_line(g0: Tuple[int, int], g1: Tuple[int, int]) -> List[Tuple[int, int]]:
    """Grid cells crossed by a line (gx, gy)."""
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

    neighbors = [ (1,0,1.0), (-1,0,1.0), (0,1,1.0), (0,-1,1.0) ]
    if allow_diag:
        diag_c = math.sqrt(2)
        neighbors += [ (1,1,diag_c), (1,-1,diag_c), (-1,1,diag_c), (-1,-1,diag_c) ]

    import heapq
    open_set = []
    heapq.heappush(open_set, (0.0, start_g))
    came_from = {}
    gscore = {start_g: 0.0}

    def h(a, b):
        dx = abs(a[0]-b[0]); dy = abs(a[1]-b[1])
        return (dx + dy) if not allow_diag else math.hypot(dx, dy)

    fscore = {start_g: h(start_g, goal_g)}
    closed = set()

    while open_set:
        _, current = heapq.heappop(open_set)
        if current == goal_g:
            # reconstruct
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
                fscore[n] = ng + h(n, goal_g)
                heapq.heappush(open_set, (fscore[n], n))
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


# =========================
# Utility: build and plan
# =========================

def plan_path(
    obstacles_xy_cm: List[Tuple[float, float]],
    start_xy_cm: Tuple[int,int],
    goal_xy_cm: Tuple[int,int],
    map_cfg: MapConfig,
    planner_cfg: PlannerConfig
):
    occ = build_occupancy_grid(obstacles_xy_cm, map_cfg, planner_cfg)
    s_g = to_grid_coords(*start_xy_cm, map_cfg)
    g_g = to_grid_coords(*goal_xy_cm, map_cfg)

    raw = a_star(occ, s_g, g_g, allow_diag=planner_cfg.diag_moves)
    if raw is None:
        raise RuntimeError("No path found. Try smaller robot radius, larger map, or different start/goal.")
    smooth = smooth_path(raw, occ)
    # Convert to world cm
    path_xy = [to_world_coords(gx, gy, map_cfg) for (gx, gy) in smooth]
    return path_xy, occ

# =========================
# Demo / Main
# =========================

def main():
    # ---- Define your scenario (all units in cm) ----
    # Map bounds
    map_cfg = MapConfig(
        x_min=-200, x_max=900,  # 8 m wide
        y_min=-200, y_max=400,  # 6 m tall
        resolution=10
    )
    planner_cfg = PlannerConfig(
        drone_radius_cm=15,
        safety_margin_cm=40,
        diag_moves=True
    )

    # Obstacles (raw points)
    obstacles_xy_cm = [
        (300, -100), (310, -90), (320, -80), (330, -70), (340, -60), (350, -50), (360, -40), (370, -30), (380, -20), (390, -10), (400, 0), (410, 10), (420, 20), (430, 30), (440, 40), (450, 50), (460, 60), (470, 70), (480, 80), (490, 90), (500, 100), (510, 110), (520, 120), (530, 130), (540, 140), (550, 150), (560, 160), (570, 170), (580, 180), (590, 190), (600, 200),
        (300, 200), (310, 190), (320, 180), (330, 170), (340, 160), (350, 150), (360, 140), (370, 130), (380, 120), (390, 110), (400, 100), (410, 90), (420, 80), (430, 70), (440, 60)
    ]

    start_xy_cm = (0, 200)
    goal_xy_cm = (800, 0)

    path_xy, occ = plan_path(
        obstacles_xy_cm,
        start_xy_cm,
        goal_xy_cm,
        map_cfg,
        planner_cfg
    )

    print("Planned waypoints (cm):")
    for p in path_xy:
        print(p)

    # ---- Visualise (optional) ----
    try:
        import matplotlib.pyplot as plt
        fig = plt.figure()
        ax = fig.add_subplot(111)
        # Draw occupancy grid
        ax.imshow(occ, origin='lower', extent=[map_cfg.x_min, map_cfg.x_max, map_cfg.y_min, map_cfg.y_max], alpha=0.3)
        # Draw obstacles (raw points)
        ox = [o[0] for o in obstacles_xy_cm]
        oy = [o[1] for o in obstacles_xy_cm]
        ax.scatter(ox, oy, s=20, label="Obstacle points")

        # Draw path
        px = [p[0] for p in path_xy]
        py = [p[1] for p in path_xy]
        ax.plot(px, py, linewidth=2, label="Smoothed path")
        ax.scatter([start_xy_cm[0]], [start_xy_cm[1]], c='g', s=60, label="Start")
        ax.scatter([goal_xy_cm[0]], [goal_xy_cm[1]], c='r', s=60, label="Goal")
        ax.set_aspect('equal')
        ax.set_title("A* Path over Inflated Obstacles")
        ax.legend()
        plt.show()
    except Exception:
        pass

    commands = ["command",
                "takeoff",]
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

    return_to_yaw = True  
    if return_to_yaw:
        commands.append("cw {:.4f}".format(-current_yaw))


    commands.append("land")
    print("Tello commands:")
    print(commands)


        

    # Initialize Tello
    tello = Tello()
    start_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # Execute commands
    for command in commands:
        command = command.strip()
        if not command:
            continue

        if "delay" in command:
            sec = float(command.partition("delay")[2])
            print(f"Delay {sec} seconds")
            time.sleep(sec)
        else:
            tello.send_command(command)

    # Save log
    log = tello.get_log()
    os.makedirs("log", exist_ok=True)
    log_filename = f"log/{start_time}.txt"

    with open(log_filename, "w") as out:
        for stat in log:
            stat.print_stats()
            out.write(stat.return_stats())

    print(f"Log saved to {log_filename}")

if __name__ == "__main__":
    main()
