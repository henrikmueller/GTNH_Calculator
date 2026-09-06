from __future__ import annotations
import logging
from dataclasses import dataclass
import numpy as np
import pandas as pd
from typing import Dict
from math import ceil

from ..recipes_db.material import Material
from ..recipes_db.machines import Machine
from ..recipes_db.instantiated_recipes import InstantiatedRecipe, InstantiatedPartialRecipe
from .crafting_chain_utility import calculate_gradings
from ..utility.general_utility import format_float

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass
class CraftingChainStatistics:
    time_interval: str
    total_inputs_per_time_interval: dict[Material, float]
    total_outputs_per_time_interval: dict[Material, float]
    total_eu_per_tick: float

    def markdown_inputs(self) -> str:
        return f"""
#### **Total inputs per {self.time_interval}**:

{', \n'.join(f'- {"{:.3f}".format(a)} {m}' for m, a in self.total_inputs_per_time_interval.items())}
"""

    def markdown_outputs(self) -> str:
        return f"""
#### **Total outputs per {self.time_interval}**:

{', \n'.join(f'- {"{:.3f}".format(a)} {m}' for m, a in self.total_outputs_per_time_interval.items())}
"""

    def markdown_eu(self) -> str:
        return f"""
#### **Total EU/t**: {"{:.3f}".format(self.total_eu_per_tick)}
"""


@dataclass(frozen=True)
class CraftingChain:
    partial_recipes: Dict[str, InstantiatedPartialRecipe]
    total_material_needs: Dict[Material, float]
    infinite_materials: set[Material]
    recipe_grading: Dict[str, int]
    material_grading: Dict[Material, int]
    infinite_recipes: Dict[str, bool]
    time: float

    @classmethod
    def create_crafting_chain(
        cls,
        recipe_amounts: Dict[InstantiatedRecipe, float],
        total_material_needs: Dict[Material, float],
        input_materials: set[Material],
        infinite_materials: set[Material],
        time: float
    ) -> CraftingChain:
        recipe_amounts = {r: a for r, a in recipe_amounts.items() if a > 0}
        capacity_utilizations = {
            r: a * (r.processing_time / time if r.positive_processing_time() else 1)
            for r, a in recipe_amounts.items()
        }
        partial_recipes = {
            r.id: r.fit_to_capacity_utilization(capacity_utilizations[r])
            for r in recipe_amounts.keys()
        }

        recipe_grading, material_grading = calculate_gradings(
            instantiated_recipe_list=[recipe for recipe, amount in recipe_amounts.items() if amount > 0],
            materials={m.id: m for m in total_material_needs.keys()},
            starting_materials=input_materials | infinite_materials,
            ignore_unreachable=True
        )

        # TODO
        # def calculate_infinites() -> None:
        #     recipe_vector = np.array([amount for _, amount in self.recipe_amounts.items()])
        #     total_material_needs = np.matmul(self.recipe_matrix, recipe_vector)
        #     total_material_amounts = {m: a for a, m in zip(total_material_needs, self.materials.values())}
        #     for material, infinite in self.infinite_materials.items():
        #         if infinite and total_material_amounts[material] == 0:
        #             # This case probably does not occur for chance based materials
        #             self.infinite_materials[material] = False
        #
        #     remaining_recipes: list[Recipe] = list(self.recipes.values())
        #     detected_infinites = []
        #     infinite_recipes = {recipe: False for recipe in self.recipes.values()}
        #
        #     while True:
        #         for recipe in remaining_recipes:
        #             if all(self.infinite_materials[m] for m in recipe.get_inputs()):
        #                 for material in recipe.get_outputs():
        #                     self.infinite_materials[material] = True
        #                 infinite_recipes[recipe] = True
        #                 detected_infinites.append(recipe)
        #         if not detected_infinites:
        #             break
        #         for recipe in detected_infinites:
        #             remaining_recipes.remove(recipe)
        #         detected_infinites = []
        #     self.infinite_recipes = infinite_recipes
        #
        # calculate_infinites()
        infinite_recipes = {p.id: False for p in partial_recipes.values()}

        return cls(
            partial_recipes=partial_recipes,
            total_material_needs=total_material_needs,
            infinite_materials=infinite_materials,
            recipe_grading=recipe_grading,
            material_grading=material_grading,
            infinite_recipes=infinite_recipes,
            time=time
        )

    @property
    def inputs(self) -> Dict[Material, float]:
        return {m: a for m, a in self.total_material_needs.items() if a < 0}

    @property
    def outputs(self) -> Dict[Material, float]:
        return {m: a for m, a in self.total_material_needs.items() if a > 0}

    def get_machine_amount(self, recipe_id: str) -> float:
        if recipe_id not in self.partial_recipes:
            return 0.0
        return self.partial_recipes[recipe_id].capacity_utilization

    @property
    def machine_amounts(self) -> Dict[str, float]:
        return {
            partial_recipe_id: self.get_machine_amount(partial_recipe_id)
            for partial_recipe_id in self.partial_recipes.keys()
        }

    @property
    def number_of_distinct_machines(self) -> int:
        return len([a for a in self.machine_amounts.values() if a > 0])

    @property
    def number_of_machines(self) -> int:
        return sum(ceil(a) for a in self.machine_amounts.values())

    @property
    def used_machines(self) -> set[Machine]:
        return {p.machine for p in self.partial_recipes.values() if p.capacity_utilization > 0}

    @property
    def used_materials(self) -> set[Material]:
        materials = []
        for partial_recipe in self.partial_recipes.values():
            if partial_recipe.capacity_utilization > 0:
                materials.extend(partial_recipe.used_materials)
        return set(materials)

    @property
    def min_total_eu_per_tick(self) -> float:
        return sum(p.min_eu_per_tick for p in self.partial_recipes.values())

    @property
    def max_total_eu_per_tick(self) -> float:
        return sum(p.max_eu_per_tick for p in self.partial_recipes.values())

    def get_partial_recipe(self, instantiated_recipe: InstantiatedRecipe) -> InstantiatedPartialRecipe:
        return self.partial_recipes[instantiated_recipe.id]

    def to_dataframe(self, time_factor, display_interval_string: str):
        columns = ['Recipe Grading', 'Machine Amount', 'Machine', 'Voltage', f'Inputs per {display_interval_string}',
                   f'Outputs per {display_interval_string}',
                   'Min EU/t', 'Max EU/t', 'Infinite', 'Recipe ID']
        machine_amounts = self.machine_amounts
        partial_recipes = list(self.partial_recipes.values())
        n, q = len(columns), len(partial_recipes)
        data = np.zeros((q, n), dtype=object)
        data[:, 0] = [self.recipe_grading[p.id] for p in partial_recipes]
        data[:, 1] = [machine_amounts[p.id] for p in partial_recipes]
        data[:, 2] = [p.machine.__str__() for p in partial_recipes]
        data[:, 3] = [p.voltage_tier_name for p in partial_recipes]
        data[:, 4] = [p.input_string(time_factor) for p in partial_recipes]
        data[:, 5] = [p.output_string(time_factor) for p in partial_recipes]
        data[:, 6] = [round(abs(p.min_eu_per_tick), 3) for p in partial_recipes]
        data[:, 7] = [round(abs(p.max_eu_per_tick), 3) for p in partial_recipes]
        data[:, 8] = [self.infinite_recipes[p.id] for p in partial_recipes]
        data[:, 9] = [p.id for p in partial_recipes]
        df = pd.DataFrame(data=data, columns=columns)
        df = df.sort_values(by='Recipe Grading', ascending=True)
        return df

    def markdown_inputs(self, display_interval_string: str, threshold=1e-10) -> str:
        return f"""
#### **Total inputs per {display_interval_string}**:

{', \n'.join(f'- {format_float(abs(a))} {m}' for m, a in self.inputs.items() if -a >= threshold)}
"""

    def markdown_outputs(self, display_interval_string: str, threshold=1e-10) -> str:
        return f"""
#### **Total outputs per {display_interval_string}**:
    
{', \n'.join(f'- {format_float(a)} {m}' for m, a in self.outputs.items() if a >= threshold)}
"""

    def markdown_eu(self) -> str:
        min_total_eu_per_tick = self.min_total_eu_per_tick
        max_total_eu_per_tick = self.max_total_eu_per_tick
        if min_total_eu_per_tick == max_total_eu_per_tick:
            return f"#### **Total EU/t**: {format_float(abs(self.min_total_eu_per_tick), decimal_places=2, separate_thousands=True)}"
        return (f"#### **Total EU/t**: {format_float(abs(self.min_total_eu_per_tick), decimal_places=2, separate_thousands=True)} – "
                f"{format_float(abs(self.max_total_eu_per_tick), decimal_places=2, separate_thousands=True)}  "
                f"(depending on parallelization)")
