from __future__ import annotations
from typing import Sequence
from dataclasses import dataclass
import streamlit as st

from ..sorting.sort_fields import SortField, T


@dataclass(frozen=True)
class SortControls[T]:
    sort_field: SortField[T]
    reverse: bool


def get_sort_controls(
    sort_fields: Sequence[SortField[T]],
    *,
    key_prefix: str = "sort",
) -> SortControls[T]:
    if not sort_fields:
        raise ValueError("No sort fields provided.")

    field_labels = [
        field.label
        for field in sort_fields
    ]
    selected_index = st.selectbox(
        "Sort by",
        options=range(len(sort_fields)),
        format_func=lambda index: field_labels[index],
        key=f"{key_prefix}_field",
    )
    reverse = st.checkbox(
        "Reverse order",
        key=f"{key_prefix}_reverse",
    )

    selected_field = sort_fields[selected_index]
    return SortControls(
        sort_field=selected_field,
        reverse=reverse,
    )


def apply_sorting(
    items: Sequence[T],
    sort_controls: SortControls[T],
) -> list[T]:
    return sort_controls.sort_field.strategy.sort(
        items,
        reverse=sort_controls.reverse,
    )
