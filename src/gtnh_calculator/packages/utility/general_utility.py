import numpy as np
import pandas as pd
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
    if text == '':
        return None
    if isinstance(text, str):
        text = text.replace(',', '.')
    try:
        return float(text)
    except ValueError:
        return None


def str_to_float_with_exception(text: str) -> float:
    if isinstance(text, str):
        text = text.replace(',', '.')
    return float(text)


def time_to_seconds(time_string: str) -> tuple[float, str]:
    tmp = str_to_float(time_string[:-1])
    if time_string.endswith('t'):
        return 0.05 * tmp, 'tick'
    elif time_string.endswith('s'):
        return tmp, 'second'
    else:
        raise ValueError('time and display_interval need to end with s or t')


def is_empty(text: str) -> bool:
    return text == '' or text.isspace()


def get_differences(df1: pd.DataFrame, df2: pd.DataFrame) -> pd.DataFrame:
    diff = df1.compare(df2, keep_shape=True)
    result = pd.DataFrame(index=df1.index, columns=df1.columns)
    for col in df1.columns:
        if col in diff.columns.levels[0]:
            old_vals = diff[(col, "self")]
            new_vals = diff[(col, "other")]

            result[col] = [
                (old, new) if not pd.isna(old) or not pd.isna(new) else np.nan
                for old, new in zip(old_vals, new_vals)
            ]
        else:
            result[col] = np.nan
    return result
