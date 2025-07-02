from .material import Material


class Machine:
    name: str
    requirements: list[Material]

    def __init__(self, name):
        self.name = name

    def __repr__(self) -> str:
        return self.name
