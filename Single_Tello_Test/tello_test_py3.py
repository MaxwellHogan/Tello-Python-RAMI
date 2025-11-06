from tello import Tello
from datetime import datetime
import time
import os


def main():
    
    # Define your commands here
    commands = [
        "command",
        "takeoff",
        "forward 450.6",
        "cw 90",
        "forward 100",
        "cw 90",
        "forward 100",
        "cw 90",
        "flip r",
        "forward 100",
        "ccw 90",
        "forward 300",
        "ccw 180",
        "land",
    ]

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
