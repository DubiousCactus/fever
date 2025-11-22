import random
import signal
from time import sleep

from fever import FeverWatcher

running = True


def run():
    watcher = FeverWatcher()
    global running

    def stop(*args):
        print("Stopping watcher...")
        global running
        watcher.stop()
        running = False

    signal.signal(signal.SIGINT, stop)
    watcher.watch()
    # Remember that only imports executed *after* fever setup are tracked!
    from example_module import example_function

    words = ["fever", "world", "programmer", "GitHub", "my friend"]

    # FIXME: Hot reloading doesn't work for the module where it's setup! This should be
    # a simple fix since I track the calling module upon setup.
    while running:
        example_function(random.choice(words))
        sleep(0.1)

    # watcher.fever.plot_dependency_graph()
    watcher.fever.plot_call_graph()


if __name__ == "__main__":
    run()
