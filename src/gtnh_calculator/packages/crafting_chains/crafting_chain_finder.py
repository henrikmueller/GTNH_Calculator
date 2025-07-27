import xgi
from typing import Dict
import matplotlib.pyplot as plt
from scipy.optimize import linprog
import numpy as np
import logging

from ..recipes.recipe_book import RecipeBook
from ..recipes.material import Material
from ..recipes.recipe import Recipe
from ..crafting_chains.crafting_chain import CraftingChain

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class CraftingChainFinder:
    recipe_book: RecipeBook

    def __init__(self, recipe_book: RecipeBook):
        self.recipe_book = recipe_book

    @property
    def recipes(self) -> Dict[int, Recipe]:
        return self.recipe_book.recipes

    @property
    def materials_by_name(self) -> Dict[str, Material]:
        return self.recipe_book.material_list.materials_by_name

    @property
    def materials_by_id(self) -> Dict[int, Material]:
        return self.recipe_book.material_list.materials_by_id

    def draw_optimal_crafting_chain(
            self,
            inputs: set[Material],
            outputs: set[Material],
            fixed_amount: float,
            material_weights: Dict[Material, float],
            time: str,
            time_interval: str,
            mode: str,
            infinite_materials: set[Material],
            recipe_weight_factor=1,
    ) -> None:
        """
        :param inputs:
        :param output_spec:
        :param material_weights:
        :param time: Outputs are required every time seconds.
        :param time_interval: For displaying
        :param mode: One of the following: 'Fixed_Input' or 'Fixed_Output'
        :param infinite_materials:
        :param recipe_weight_factor:
        :return:
        """
        def time_to_seconds(time_string: str) -> tuple[float, str]:
            def str_to_float(text: str) -> float:
                try:
                    float_number = float(text)
                    return float_number
                except ValueError:
                    raise ValueError('time and time_interval need to end with s or t')

            tmp = str_to_float(time_string[:-1])
            if time_string.endswith('t'):
                return 0.05 * tmp, 'tick'
            elif time_string.endswith('s'):
                return tmp, 'second'
            else:
                raise ValueError('time and time_interval need to end with s or t')

        if len(inputs) != 1 and mode == 'Fixed_Input':
            raise ValueError(f'Only one input material allowed in mode Fixed_Input')
        if len(outputs) != 1 and mode == 'Fixed_Output':
            raise ValueError(f'Only one output material allowed in mode Fixed_Output')

        if not (mode == 'Fixed_Output' and list(outputs)[0] == self.materials_by_name['EU']):
            infinite_materials.add(self.materials_by_name['EU'])

        print('Materials which cannot be produced from recipes and are not specified as input or infinite materials:')
        for material in self.materials_by_name.values():
            if any([material in recipe.get_outputs() for recipe in self.recipes.values()]):
                continue
            if material in infinite_materials or material in inputs:
                continue
            print(material)

        time, _ = time_to_seconds(time)
        time_interval, time_interval_name = time_to_seconds(time_interval)

        materials = list(self.materials_by_name.values())
        p, q = len(materials), len(self.recipes)
        X = np.zeros((p, q), dtype=np.float64)
        for i, recipe in enumerate(self.recipes.values()):
            X[:, i] = recipe.recipe_vector(materials)

        recipe_matrix = X.copy()
        recipe_weights = np.array([r.weight for r in self.recipes.values()])
        for material in infinite_materials:
            material_weights[material] = 0

        match mode:
            case 'Fixed_Output':
                output_material = list(outputs)[0]
                inputs = inputs.union(infinite_materials)

                # If a material is specified as an input: Remove it as output from every recipe.
                for material in inputs:
                    X[material.id][X[material.id] > 0] = 0

                c = np.array(
                    [material_weights[material] if material in material_weights.keys() else 0 for material in
                     materials], dtype=np.float64)
                cost_summand_from_weights = recipe_weight_factor * recipe_weights
                cost_vector = np.matmul(c, X) + cost_summand_from_weights
                bounds = np.full((q, 2), np.nan, dtype=np.float64)
                bounds[:, 0] = 0
                b_ub = np.zeros((p,))
                A_ub = -X.copy()
                for i in range(A_ub.shape[0]):
                    if materials[i] in inputs:
                        A_ub[i, :] = 0
                A_eq = np.zeros((1, q))
                A_eq[0, :] = X[output_material.id, :]
                b_eq = np.zeros((A_eq.shape[0],))
                b_eq[0] = fixed_amount
            case 'Fixed_Input':
                input_material = list(inputs)[0]

                inputs = inputs.union(infinite_materials)
                # If a material is specified as an input: Remove it as output from every recipe.
                for material in inputs:
                    X[material.id][X[material.id] > 0] = 0

                c = np.array([material_weights[material] if material in material_weights.keys() else 0 for material
                              in materials], dtype=np.float64)
                cost_summand_from_weights = recipe_weight_factor * recipe_weights
                cost_vector = - (np.matmul(c, X) - cost_summand_from_weights)

                bounds = np.full((q, 2), np.nan, dtype=np.float64)
                bounds[:, 0] = 0
                b_ub = np.zeros((p,))
                A_ub = -X.copy()
                A_ub[input_material.id, :] = 0
                if infinite_materials is not None:
                    for material in infinite_materials:
                        A_ub[material.id, :] = 0
                A_eq = np.zeros((1, q))
                A_eq[0, :] = X[input_material.id, :]
                b_eq = np.zeros((A_eq.shape[0],))
                b_eq[0] = -fixed_amount
            case _:
                raise ValueError(f'The mode parameter must be one of the following: Fixed_Input or Fixed_Output')

        result = linprog(
            c=cost_vector,
            A_ub=A_ub,
            b_ub=b_ub,
            A_eq=A_eq,
            b_eq=b_eq,
            bounds=bounds,
            method='highs'
        )
        if result.status != 0:
            if result.status == 2:
                _LOGGER.error(f'The optimization problem is infeasible. Possibly, because a required material cannot '
                              f'be crafted via the imported recipes or is not specified as an input material.')
            elif result.status == 3:
                _LOGGER.error(f'The optimization problem is unbounded. Possibly, because there is an input material'
                              f'with positive weight')
            else:
                _LOGGER.error(f'An unknown error occurred: {result.status}')
        if result.status != 0:
            _LOGGER.error(f'Plotting all recipes with negative cost')
            negative_cost_recipes = []
            for recipe in self.recipes.values():
                if cost_vector[recipe.id] < 0:
                    negative_cost_recipes.append(recipe)
                    print(f'Cost of {recipe.id}: {cost_vector[recipe.id]}. Inputs {recipe.get_inputs()}. '
                          f'Outputs. {recipe.get_outputs()}')
            hypergraph = self.create_hypergraph(negative_cost_recipes, start=False)
            node_labels = {materials[material_id].id: materials[material_id].get_abbreviation() for material_id
                           in hypergraph.nodes}
            xgi.draw_bipartite(hypergraph, node_labels=node_labels, node_size=47, aspect='auto')
            plt.show()
            return None

        recipe_vector = result.x

        print('\n+---------+')
        print('| Results |')
        print('+---------+\n')
        material_cost = np.sum(np.matmul(c, X) * recipe_vector)
        machine_cost = np.sum(cost_summand_from_weights * recipe_vector / recipe_weight_factor)
        combined_cost = material_cost + machine_cost
        print(f'Material cost: {"{:.2f}%".format(100 * material_cost / combined_cost)}')
        print(f'Machine cost: {"{:.2f}%".format(100 * machine_cost / combined_cost)}')

        crafting_chain = CraftingChain(
            self.create_hypergraph([recipe for i, recipe in enumerate(self.recipes.values()) if recipe_vector[i] > 0]),
            {recipe.id: amount for amount, recipe in zip(result.x, self.recipes.values())},
            recipe_matrix
        )

        crafting_chain.draw(self.materials_by_id, self.recipes, time, time_interval / time,
                            time_interval_name)

    def create_hypergraph(self, recipes: list[Recipe], start=True) -> xgi.DiHypergraph:
        hypergraph = xgi.DiHypergraph()
        for recipe in recipes:
            input_data, output_data = recipe.get_edge_data(eu=False)
            if input_data and output_data:
                hypergraph.add_edge((input_data, output_data), id=recipe.id)
        in_degrees = hypergraph.nodes.in_degree.asdict()
        if start:
            for node, in_degree in in_degrees.items():
                if in_degree == 0:
                    hypergraph.add_edge([[-1], [node]], id=-1)
        return hypergraph
