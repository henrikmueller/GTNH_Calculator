from dataclasses import dataclass
import streamlit as st
from typing import Iterable

from ..recipes_db.material import Material
from ..recipes_db.machines import Machine
from ..recipes_db.voltage_tiers import VoltageTier
from ..utility.constants import DEFAULT_MAX_DISPLAYED_RECIPES


@dataclass
class RecipeFilters:
    selected_recipe_id: str
    selected_machine_names: set[str]
    selected_inputs: set[Material]
    selected_outputs: set[Material]
    selected_voltage_tiers: set[int]
    only_enabled: bool
    max_displayed_recipes: int


def get_recipe_filters(
    st_key: str, used_machines: Iterable[Machine], used_materials: Iterable[Material],
    default_max_displayed_recipes: int = DEFAULT_MAX_DISPLAYED_RECIPES,
    only_enabled_checkbox: bool = True, separate_input_output: bool = True, 
) -> RecipeFilters:
    a, b, c = st.columns(3)
    with a:
        selected_recipe_id = st.text_input("Filter by Recipe ID", key=f"{st_key}_select_rid")
        selected_machine_names = set(st.multiselect(
            "Filter recipes by machines",
            options=[m.name for m in used_machines],
            default=None,
            key=f"{st_key}_machine_select",
        ))
        if only_enabled_checkbox:
            only_enabled = st.checkbox(
                "Only show enabled recipes",
                key=f"{st_key}_only_enabled"
            )
        else:
            only_enabled = False
    with b:
        materials = {m.id: m for m in used_materials}
        options = {
            id: m.name for id, m in materials.items()
        }

        if separate_input_output:
            selected_input_ids = st.multiselect(
                'Filter by Input Materials',
                options=options.keys(),
                key=f"{st_key}_input_select",
                format_func=lambda index: options[index]
            )
            selected_inputs = {
                materials[id] for id in selected_input_ids
            }

            selected_output_ids = st.multiselect(
                'Filter by Output Materials',
                options=options.keys(),
                key=f"{st_key}_output_select",
                format_func=lambda index: options[index]
            )
            selected_outputs = {
                materials[id] for id in selected_output_ids
            }
        else:
            selected_material_ids = st.multiselect(
                'Filter by Materials',
                options=options.keys(),
                key=f"{st_key}_material_select",
                format_func=lambda index: options[index]
            )
            selected_inputs = {
                materials[id] for id in selected_material_ids
            }
            selected_outputs = selected_inputs
    with c:
        selected_voltage_tiers = set(VoltageTier.to_voltage_tier(v) for v in st.multiselect(
            "Filter recipes by voltage tiers",
            options=[VoltageTier.voltage_tier_name(v) for v in VoltageTier.valid_voltage_tiers()],
            default=[VoltageTier.voltage_tier_name(v) for v in VoltageTier.valid_voltage_tiers()],
            key=f"{st_key}_voltage_select",
        ))
        max_displayed_recipes = st.number_input(
            "Maximum number of displayed recipes",
            min_value=1,
            value=default_max_displayed_recipes,
            key=f"{st_key}_max_displayed_recipes"
        )
    return RecipeFilters(
        selected_recipe_id=selected_recipe_id,
        selected_machine_names=selected_machine_names,
        selected_inputs=selected_inputs,
        selected_outputs=selected_outputs,
        selected_voltage_tiers=selected_voltage_tiers,
        only_enabled=only_enabled,
        max_displayed_recipes=max_displayed_recipes
    )
