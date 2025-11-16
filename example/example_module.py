# new_var = 42


# def new(value: float) -> float:
#     return value + 3.8


def called_function(value: float) -> float:
    # return new(value * 2.6 + new_var)
    # return new(value * 2.6)
    return value * 2.6


def example_function(name: str):
    print(f"Hello, {name}!!")
    print("Things will change from now on!")
    print(called_function(1.12))
