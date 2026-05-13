import numpy as np
import pandas as pd
from dataclasses import dataclass
from colorsys import hsv_to_rgb
from typing import Any
import yaml
from io import BytesIO
import time
import base64
import pandas as pd


class Timer:
    def __init__(self, name='Block', active: bool = True):
        self.name = name
        self.active = active

    def __enter__(self):
        if self.active:
            self.start = time.perf_counter()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.active:
            end = time.perf_counter()
            print(f'{self.name} took {end - self.start:.6f} seconds')


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


def str_to_int(text: str) -> int | None:
    try:
        return int(text)
    except ValueError:
        return None


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


def load_file(file_or_filepath: BytesIO | str) -> Any:
    if isinstance(file_or_filepath, BytesIO):
        return yaml.load(file_or_filepath, Loader=yaml.SafeLoader)
    elif isinstance(file_or_filepath, str):
        with open(file_or_filepath, 'r') as f:
            return yaml.load(f, Loader=yaml.SafeLoader)
    else:
        raise ValueError(f'CraftingChainConfig file not valid.')


def get_base64_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def print_df(df: pd.DataFrame, limit_rows: bool = True, max_rows: int | None = None):
    if limit_rows:
        with pd.option_context(
            "display.max_columns", None,
            "display.width", None,
            "display.max_colwidth", None
        ):
            print(df if max_rows is None else df.head(max_rows))
    else:
        with pd.option_context(
            "display.max_rows", None,
            "display.max_columns", None,
            "display.width", None,
            "display.max_colwidth", None
        ):
            print(df if max_rows is None else df.head(max_rows))


def is_contained_in(text: str, text_list: list[str], case_sensitive=True) -> bool:
    if case_sensitive:
        return any(text in s for s in text_list)
    lowercase_text = text.lower()
    return any(lowercase_text in s.lower() for s in text_list)


def format_float(x):
    s = f"{x:.20f}".rstrip("0")
    if "." not in s:
        return s + ".0"

    whole, frac = s.split(".")
    for i, ch in enumerate(frac):
        if ch != "0":
            return whole + "." + frac[:i+2]
    return whole + ".0"
