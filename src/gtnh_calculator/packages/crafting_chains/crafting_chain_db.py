import logging
from dataclasses import dataclass
import numpy as np
import pandas as pd
from typing import Dict

from ..recipes_db.material import Material
from ..recipes_db.recipes import Recipe
from .crafting_chain_utility import calculate_gradings

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


class CraftingChain:
    recipe_amounts: Dict[Recipe, float]
    total_material_needs: Dict[Material, float]
    machine_amounts: Dict[Recipe, float]
    infinite_materials: set[Material]
    recipe_grading: Dict[Recipe, int]
    material_grading: Dict[Material, int]
    eu_per_tick: Dict[Recipe, float]
    total_eu_per_tick: float
    infinite_recipes: Dict[Recipe, bool]

    def __init__(
            self,
            recipe_amounts: Dict[Recipe, float],
            total_material_needs: Dict[Material, float],
            input_materials: set[Material],
            infinite_materials: set[Material],
            time: float
    ):
        self.recipe_amounts = recipe_amounts
        self.total_material_needs = total_material_needs
        self.input_materials = input_materials
        self.infinite_materials = infinite_materials
        self.time = time
        self.machine_amounts = {
            recipe: (amount * recipe.processing_time / time if recipe.positive_processing_time() else (1 if amount > 0 else 0))
            for recipe, amount in recipe_amounts.items()
        }
        self.eu_per_tick = {
            r: (-r.total_eu * a / (20 * r.processing_time) if r.positive_processing_time() else 0)
            for r, a in recipe_amounts.items()
        }
        self.total_eu_per_tick = sum(self.eu_per_tick.values())
        self.recipe_grading, self.material_grading = calculate_gradings(
            recipes=[recipe for recipe, amount in recipe_amounts.items() if amount > 0],
            materials=list(total_material_needs.keys()),
            starting_materials=input_materials | infinite_materials
        )

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
        self.infinite_recipes = {r: False for r in recipe_amounts.keys()}

    @property
    def inputs(self) -> Dict[Material, float]:
        return {m: a for m, a in self.total_material_needs.items() if a < 0}

    @property
    def outputs(self) -> Dict[Material, float]:
        return {m: a for m, a in self.total_material_needs.items() if a > 0}

    def statistics(self, time_factor, time_interval: str, do_print=False) -> CraftingChainStatistics:
        """
        ----------------------------------------------------------------------------------------------------------------
            Prepare recipe chain data for printing and drawing
        ----------------------------------------------------------------------------------------------------------------
        """
        df = self.to_dataframe(time_factor, time_interval)
        recipe_vector = np.array([amount for _, amount in self.recipe_amounts.items()])
        total_material_needs = time_factor * np.matmul(self.recipe_matrix, recipe_vector)
        total_materials = list(zip(total_material_needs, self.materials.values()))

        """
        ----------------------------------------------------------------------------------------------------------------
            Print crafting chain to console
        ----------------------------------------------------------------------------------------------------------------
        """
        if do_print:
            print(f'\nTotal Inputs per {time_interval}:')
            print(', '.join([f'{"{:.3f}".format(-amount)} {material}' for amount, material in total_materials if
                             amount < 0]) + '\n')
            print(f'Total Outputs per {time_interval}:')
            print(', '.join(
                [f'{"{:.3f}".format(amount)} {material}' for amount, material in total_materials if amount > 0]) + '\n')
            print(f'Total EU per tick {"{:.3f}".format(self.total_eu_per_tick)}:')
            print(f'Complete Recipe List{' (ordered)' if self.ordered_recipes else ''}:')
            print(df.to_string() + '\n')

        return CraftingChainStatistics(
            time_interval=time_interval,
            total_inputs_per_time_interval={material: -amount for amount, material in total_materials if amount < 0},
            total_outputs_per_time_interval={material: amount for amount, material in total_materials if amount > 0},
            total_eu_per_tick=self.total_eu_per_tick
        )

    def to_dataframe(self, time_factor, time_interval: str):
        columns = ['Recipe Grading', 'Machine Amount', 'Machine', 'Voltage', f'Inputs per {time_interval}',
                   f'Outputs per {time_interval}',
                   'EU/t', 'Infinite', 'Recipe ID']
        recipes = [r for r, a in self.recipe_amounts.items() if a > 0]
        n, q = len(columns), len(recipes)
        data = np.zeros((q, n), dtype=object)
        data[:, 0] = [self.recipe_grading[r] for r in recipes]
        data[:, 1] = [self.machine_amounts[r] for r in recipes]
        data[:, 2] = [r.machine.__str__() for r in recipes]
        data[:, 3] = [r.voltage_tier_name for r in recipes]
        data[:, 4] = [r.input_string(time_factor * self.recipe_amounts[r]) for r in recipes]
        data[:, 5] = [r.output_string(time_factor * self.recipe_amounts[r]) for r in recipes]
        data[:, 6] = ["{:.3f}".format(self.eu_per_tick[r]) for r in recipes]
        data[:, 7] = [self.infinite_recipes[r] for r in recipes]
        data[:, 8] = [r.id for r in recipes]
        df = pd.DataFrame(data=data, columns=columns)
        df = df.sort_values(by='Recipe Grading', ascending=True)
        return df
