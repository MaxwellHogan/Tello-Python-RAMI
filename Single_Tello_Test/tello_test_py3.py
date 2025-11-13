from tello import Tello
from datetime import datetime
import time
import os
import time
import threading

class KeepAlive:
    def __init__(self, tello):
        self.alive = True
        self.lock = threading.Lock()
        self.tello = tello

    def __call__(self):

        ## get alive status
        with self.lock:
            alive = self.alive

        while alive:
            print("Living")
            self.tello.send_command("command")
            time.sleep(3)
            
            ## check if I need to keep living 
            with self.lock:
                alive = self.alive

        print("You killed me")

    def shutdown(self):
        print("Received Shutdown")
        with self.lock:
            self.alive = False



def main():
    
    # Define your commands here
    commands = [
        "command",
        "takeoff",
        "battery?",
        "streamon",
        "forward 100",
        "ccw 180",
        "forward 100",
        "ccw 180",
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

    # keepAlive = KeepAlive(tello)
    # keepAlive_thread = threading.Thread(target=keepAlive)
    # keepAlive_thread.start()

    # input("HIT Enter to Quit")

    # keepAlive.shutdown()
    # keepAlive_thread.join()

    tello.send_command("land")

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
