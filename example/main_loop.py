import random
from time import sleep

from example_module import example_function

if __name__ == "__main__":
    words = ["fever", "world", "programmer", "GitHub", "my friend"]
    while True:
        example_function(random.choice(words))
        sleep(1)
