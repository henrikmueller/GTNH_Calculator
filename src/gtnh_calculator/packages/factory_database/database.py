from __future__ import annotations
import sys
from collections import defaultdict
from typing import Mapping
import logging
from frozendict import frozendict
from dataclasses import dataclass
from abc import ABC, abstractmethod

from .factories import Factory, ProductiveChain, TextCondition, ProductiveMachine
from .sheet_entries import SheetEntry, MaterialEntry, FactoryEntry
from .sheets import SheetType, Sheet
from ..database_extraction.gtnh_database import GTNHDatabase


logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass(frozen=True)
class AbstractFactoryDatabase(ABC):
    @property
    @abstractmethod
    def entries(self) -> frozendict[SheetType, Sheet]:
        ...

    @abstractmethod
    def get_entries(self, sheet_type: SheetType) -> tuple[SheetEntry, ...]:
        ...

    @abstractmethod
    def get_factories(self, database: GTNHDatabase) -> list[Factory]:
        ...


@dataclass(frozen=True)
class FactoryDatabase(AbstractFactoryDatabase):
    sheets: frozendict[SheetType, Sheet]

    @property
    def entries(self) -> frozendict[SheetType, Sheet]:
        return self.sheets

    def get_entries(self, sheet_type: SheetType) -> tuple[SheetEntry, ...]:
        return self.entries[sheet_type].entries

    def get_factories(self, database: GTNHDatabase) -> list[Factory]:
        database_materials = database.extracted_materials
        database_machines = database.extracted_machines
        factory_entries: tuple[FactoryEntry, ...] = self.sheets[SheetType.FACTORIES].entries
        material_entries: tuple[MaterialEntry, ...] = self.sheets[SheetType.MATERIALS].entries
        material_entries_by_factory = defaultdict(list)
        for material_entry in material_entries:
            material_entries_by_factory[material_entry.factory_id].append(material_entry)

        factories: list[Factory] = []
        for factory_entry in factory_entries:
            material_entries_for_factory = material_entries_by_factory[factory_entry.factory_id]
            material_amounts = defaultdict(float)
            for material_entry in material_entries_for_factory:
                if material_entry.material_id not in database_materials.keys():
                    raise KeyError(f'Material ID "{material_entry.material_id}" not found in database materials.')
                material_amounts[database_materials[material_entry.material_id]] += material_entry.amount

            machine = database_machines.get(factory_entry.factory_medium_id, None)
            if machine is None:
                factory = ProductiveChain(
                    factory_id=factory_entry.factory_id,
                    factory_medium_id=factory_entry.factory_medium_id,
                    inputs=frozendict({m: a for m, a in material_amounts.items() if a < 0}),
                    outputs=frozendict({m: a for m, a in material_amounts.items() if a > 0}),
                    processing_time=factory_entry.processing_time,
                    average_eu_per_tick=factory_entry.average_eu_per_tick,
                    conditions={TextCondition(factory_entry.conditions)},
                    location=factory_entry.location,
                    comment=factory_entry.comment
                )
            else:
                factory = ProductiveMachine(
                    factory_id=factory_entry.factory_id,
                    factory_medium_id=factory_entry.factory_medium_id,
                    machine=machine,
                    inputs=frozendict({m: a for m, a in material_amounts.items() if a < 0}),
                    outputs=frozendict({m: a for m, a in material_amounts.items() if a > 0}),
                    processing_time=factory_entry.processing_time,
                    average_eu_per_tick=factory_entry.average_eu_per_tick,
                    conditions={TextCondition(factory_entry.conditions)},
                    location=factory_entry.location,
                    comment=factory_entry.comment
                )
            factories.append(factory)
        return factories


@dataclass(frozen=True)
class EmptyFactoryDatabase(AbstractFactoryDatabase):
    @property
    def entries(self) -> frozendict[SheetType, Sheet]:
        return frozendict({})

    def get_entries(self, sheet_type: SheetType) -> tuple[SheetEntry, ...]:
        return tuple()

    def get_factories(self, database: GTNHDatabase) -> list[Factory]:
        return []
    