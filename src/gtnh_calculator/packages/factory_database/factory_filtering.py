from dataclasses import dataclass
import streamlit as st
from typing import Iterable

from .factories import Factory
from ..recipes_db.material import Material
from ..recipes_db.machines import Machine
from ..recipes_db.voltage_tiers import VoltageTier
from ..utility.constants import DEFAULT_MAX_DISPLAYED_FACTORIES


@dataclass
class FactoryFilters:
    selected_machine_names: set[str]
    selected_materials: set[Material]
    max_displayed_factories: int


def get_factory_filters(
    st_key: str, used_machines: Iterable[Machine], used_materials: Iterable[Material],
    default_max_displayed_factories: int = DEFAULT_MAX_DISPLAYED_FACTORIES 
) -> FactoryFilters:
    a, b, c = st.columns(3)
    with a:
        selected_machine_names = set(st.multiselect(
            "Filter by machines",
            options=[m.name for m in used_machines],
            default=None,
            key=f"{st_key}_machine_select",
        ))
    with b:
        materials = {m.id: m for m in used_materials}
        options = {
            id: m.name for id, m in materials.items()
        }

        selected_material_ids = st.multiselect(
            'Filter by materials',
            options=options.keys(),
            key=f"{st_key}_material_select",
            format_func=lambda index: options[index]
        )
        selected_materials = {
            materials[id] for id in selected_material_ids
        }
    with c:
        max_displayed_factories = st.number_input(
            "Maximum number of displayed factories",
            min_value=1,
            value=default_max_displayed_factories,
            key=f"{st_key}_max_displayed_factories"
        )
    return FactoryFilters(
        selected_machine_names=selected_machine_names,
        selected_materials=selected_materials,
        max_displayed_factories=max_displayed_factories
    )


def apply_factory_filters(factories: Iterable[Factory], filters: FactoryFilters) -> list[Factory]:
    filtered_factories = []
    for factory in factories:
        if filters.selected_machine_names and factory.factory_name not in filters.selected_machine_names:
            continue
        if filters.selected_materials and not (factory.all_materials & filters.selected_materials):
            continue
        filtered_factories.append(factory)
        if len(filtered_factories) >= filters.max_displayed_factories:
            break
    return filtered_factories
