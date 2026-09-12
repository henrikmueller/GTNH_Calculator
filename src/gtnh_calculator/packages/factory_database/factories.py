from __future__ import annotations
import logging
import sys
from altex import data
from frozendict import frozendict
from dataclasses import dataclass
from abc import ABC, abstractmethod

from ..recipes_db.material import Material
from ..recipes_db.machines import Machine
from ..recipes_db.instantiated_recipes import InstantiatedRecipe
from .sheets import SheetType
from .sheet_entries import SheetEntry, MaterialEntry, FactoryEntry
from ..utility.general_utility import format_float

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


type FactoryConditions = set[FactoryCondition]


@dataclass(frozen=True)
class FactoryCondition(ABC):
    @abstractmethod
    def to_entry(self) -> str:
        ...

    def __hash__(self) -> int:
        return hash(self.to_entry())


@dataclass(frozen=True)
class MaterialCondition(FactoryCondition):
    lower_bounds: frozendict[Material, float]
    upper_bounds: frozendict[Material, float]

    def to_entry(self) -> str:
        lower_bounds_str = "; ".join(f"{m.id} >= {v}" for m, v in self.lower_bounds.items())
        upper_bounds_str = "; ".join(f"{m.id} <= {v}" for m, v in self.upper_bounds.items())
        return "; ".join(filter(None, [lower_bounds_str, upper_bounds_str]))


@dataclass(frozen=True)
class TextCondition(FactoryCondition):
    text: str

    def to_entry(self) -> str:
        return self.text


@dataclass(frozen=True)
class FactoryValidity:
    is_valid: bool
    message: str


@dataclass(frozen=True)
class Factory(ABC):
    factory_id: str
    factory_medium_id: str
    inputs: frozendict[Material, float]
    outputs: frozendict[Material, float]
    processing_time: float
    average_eu_per_tick: float
    conditions: FactoryConditions
    location: str
    comment: str

    @property
    @abstractmethod
    def validity(self) -> FactoryValidity:
        ...

    @property
    @abstractmethod
    def icon_path(self) -> str:
        ...

    @property
    @abstractmethod
    def factory_name(self) -> str:
        ...

    @property
    def average_eu_per_tick_str(self) -> str:
        return f"{format_float(abs(self.average_eu_per_tick), decimal_places=1, separate_thousands=True)} EU/t"

    @property
    def average_total_eu_str(self) -> str:
        return f"{format_float(abs(20 * self.average_eu_per_tick * self.processing_time), decimal_places=1, separate_thousands=True)} EU"

    @property
    def database_entries(self) -> frozendict[SheetType, tuple[SheetEntry, ...]]:
        factory_entry = FactoryEntry(
            factory_id=self.factory_id,
            factory_medium_id=self.factory_medium_id,
            processing_time=self.processing_time,
            average_eu_per_tick=self.average_eu_per_tick,
            conditions="; ".join(c.to_entry() for c in self.conditions),
            location=self.location,
            comment=self.comment,
        )
        material_entries = tuple(
            MaterialEntry(
                factory_id=self.factory_id,
                material_id=material.id,
                material_name=material.name,
                amount=amount,
            )
            for material, amount in self.inputs.items()
        ) + tuple(
            MaterialEntry(
                factory_id=self.factory_id,
                material_id=material.id,
                material_name=material.name,
                amount=amount,
            )
            for material, amount in self.outputs.items()
        )
        return frozendict({
            SheetType.FACTORIES: (factory_entry,),
            SheetType.MATERIALS: material_entries,
        })


@dataclass(frozen=True)
class ProductiveChain(Factory):
    pass

    @property
    def validity(self) -> FactoryValidity:
        return FactoryValidity(is_valid=True, message="")

    @property
    def icon_path(self) -> str:
        return ''

    @property
    def factory_name(self) -> str:
        return 'Productive Chain'


@dataclass(frozen=True)
class ProductiveMachine(Factory):
    machine: Machine

    @property
    def validity(self) -> FactoryValidity:
        if self.machine.unspecified:
            return FactoryValidity(is_valid=False, message="Machine is unspecified.")
        return FactoryValidity(is_valid=True, message="")

    @property
    def icon_path(self) -> str:
        return self.machine.item.image_file_path

    @property
    def factory_name(self) -> str:
        return self.machine.name


@dataclass(frozen=True)
class ProductiveRecipe:
    instantiated_recipe: InstantiatedRecipe
    amount: int
    conditions: FactoryConditions
    location: str
    comment: str

    def to_factory(self) -> Factory:
        factory = ProductiveMachine(
            factory_id=self.instantiated_recipe.id,
            factory_medium_id=self.instantiated_recipe.machine.id,
            machine=self.instantiated_recipe.machine,
            inputs=frozendict({m: self.amount * a for m, a in self.instantiated_recipe.input_dict.items()}),
            outputs=frozendict({m: self.amount * a for m, a in self.instantiated_recipe.output_dict.items()}),
            processing_time=self.instantiated_recipe.processing_time,
            average_eu_per_tick=self.instantiated_recipe.eu_per_tick,
            conditions=self.conditions,
            location=self.location,
            comment=self.comment
        )
        return factory
