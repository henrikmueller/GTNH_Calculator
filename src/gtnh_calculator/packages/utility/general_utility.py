

def str_to_float(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def contains_at_least_one(text: str, characters: str) -> bool:
    for c in text:
        if c in characters:
            return True
    return False


def time_to_seconds(time_string: str) -> tuple[float, str]:
    tmp = str_to_float(time_string[:-1])
    if time_string.endswith('t'):
        return 0.05 * tmp, 'tick'
    elif time_string.endswith('s'):
        return tmp, 'second'
    else:
        raise ValueError('time and display_interval need to end with s or t')
