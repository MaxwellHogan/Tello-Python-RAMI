from tello import Tello
import socket
import cv2
import os 
from datetime import datetime
import numpy as np
import h264decoder

TELLO_IP = '192.168.10.1'
TELLO_CMD_PORT = 8889
TELLO_VIDEO_PORT = 11111

# 1. Tell Tello to enter SDK mode and start video stream
tello = Tello(local_ip = '', local_port = 8889)
start_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

tello.send_command("command")
tello.send_command("takeoff")
tello.send_command("streamon")

# 2. Open socket for video stream
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('', TELLO_VIDEO_PORT))
decoder = h264decoder.H264Decoder()

print("[INFO] Waiting for Tello video stream... Press 'q' to quit.")
try:
    while True:
        res, _ = sock.recvfrom(2048)
        if not res:
            continue
        frames = decoder.decode(res)
        for framedata in frames:
            (frame, w, h, _) = framedata
            if frame is not None:
                img = np.frombuffer(frame, dtype=np.uint8).reshape((h, w, 3))
                cv2.imshow('Tello Video', img)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

finally:
    tello.send_command("streamoff")
    tello.send_command("land")

        # Save log
    log = tello.get_log()
    os.makedirs("log", exist_ok=True)
    log_filename = f"log/{start_time}.txt"

    with open(log_filename, "w") as out:
        for stat in log:
            stat.print_stats()
            out.write(stat.return_stats())

sock.close()
cv2.destroyAllWindows()
