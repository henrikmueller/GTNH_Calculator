import numpy as np
from dataclasses import dataclass
from colorsys import hsv_to_rgb


@dataclass
class RGBColor:
    value: tuple[float, float, float]  # entries between 0 and 1

    @property
    def integer_value(self) -> tuple[int, int, int]:
        return int(255 * self.value[0]), int(255 * self.value[1]), int(255 * self.value[2])

    @property
    def hex(self) -> str:
        return '#%02x%02x%02x' % self.integer_value


@dataclass
class HSVColor:
    value: tuple[float, float, float]  # entries between 0 and 1

    @property
    def integer_value(self) -> tuple[int, int, int]:
        return int(255 * self.value[0]), int(255 * self.value[1]), int(255 * self.value[2])

    def to_rgb(self) -> RGBColor:
        return RGBColor(hsv_to_rgb(*self.value))


def contains_at_least_one(text: str, characters: str) -> bool:
    for c in text:
        if c in characters:
            return True
    return False


def get_n_colors(n: int, saturation=0.8) -> list[RGBColor]:
    if n <= 0:
        return []
    if n == 1:
        return [RGBColor((0, 0, 0))]
    colors = []
    for h in range(n):
        colors.append(HSVColor((h / n, 1, saturation)).to_rgb())
    return colors


def str_to_float(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def time_to_seconds(time_string: str) -> tuple[float, str]:
    tmp = str_to_float(time_string[:-1])
    if time_string.endswith('t'):
        return 0.05 * tmp, 'tick'
    elif time_string.endswith('s'):
        return tmp, 'second'
    else:
        raise ValueError('time and display_interval need to end with s or t')
