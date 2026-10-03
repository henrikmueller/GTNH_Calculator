from __future__ import annotations
from dataclasses import dataclass
from typing import Generic, TypeVar

from .sorting_strategies import (
    SortStrategy, KeySortStrategy, ListLengthSortStrategy
)
from ..factory_database.factories import Factory


T = TypeVar("T")


@dataclass(frozen=True)
class SortField(Generic[T]):
    id: str
    label: str
    strategy: SortStrategy[T]


FACTORY_SORT_FIELDS: list[SortField[Factory]] = [
    SortField[Factory](
        id="id",
        label="ID",
        strategy=KeySortStrategy[Factory](
            key=lambda factory: factory.factory_id,
        ),
    ),
    SortField[Factory](
        id="average_eu_per_tick",
        label="Average EU/t",
        strategy=KeySortStrategy[Factory](
            key=lambda factory: factory.average_eu_per_tick,
        ),
    ),
    SortField[Factory](
        id="average_total_eu",
        label="Average Total EU",
        strategy=KeySortStrategy[Factory](
            key=lambda factory: factory.average_total_eu,
        ),
    ),
    SortField[Factory](
        id="material_count",
        label="Number of Materials",
        strategy=ListLengthSortStrategy[Factory](
            key=lambda factory: tuple(factory.input_materials | factory.output_materials),
        ),
    ),
]
