from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Generic, Sequence, TypeVar


T = TypeVar("T")


class SortStrategy(ABC, Generic[T]):
    @abstractmethod
    def sort(
        self,
        items: Sequence[T],
        reverse: bool = False,
    ) -> list[T]:
        ...


@dataclass(frozen=True)
class KeySortStrategy(SortStrategy[T]):
    key: Callable[[T], Any]

    def sort(
        self,
        items: Sequence[T],
        reverse: bool = False,
    ) -> list[T]:
        return sorted(
            items,
            key=self.key,
            reverse=reverse,
        )


@dataclass(frozen=True)
class ListLengthSortStrategy(SortStrategy[T]):
    key: Callable[[T], Sequence[Any]]

    def sort(
        self,
        items: Sequence[T],
        reverse: bool = False,
    ) -> list[T]:
        return sorted(
            items,
            key=lambda item: len(self.key(item)),
            reverse=reverse,
        )
