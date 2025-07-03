import xgi
from xgi import DiHypergraph
from typing import Dict
import matplotlib.pyplot as plt
from scipy.optimize import linprog
import numpy as np
import logging

from gtnh_calculator.packages.recipes.material import Material, MaterialList
from gtnh_calculator.packages.recipes.recipe import Recipe
from gtnh_calculator.packages.crafting_chains.crafting_chain import CraftingChain

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class CraftingChainFinder:
    recipe_hypergraph: DiHypergraph
    material_list: MaterialList
    recipes: Dict[int, Recipe]
    recipe_weights: np.ndarray

    def __init__(
        self,
        material_list: MaterialList,
        recipes: Dict[int, Recipe],
        recipe_weights: np.ndarray
    ):
        self.material_list = material_list
        self.recipes = recipes
        self.recipe_weights = recipe_weights

    def draw_optimal_crafting_chain(
            self,
            inputs: set[Material],
            output_spec: tuple[Material, float],
            weights: Dict[Material, float],
            time: str,
            time_interval: str,
            recipe_weight_factor=1,
            excluded_materials: set[Material] | None = None
    ) -> None:
        """
        :param inputs:
        :param output_spec:
        :param weights:
        :param time: Outputs are required every time seconds.
        :param time_interval: For displaying
        :param recipe_weight_factor:
        :param excluded_materials:
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

        time, _ = time_to_seconds(time)
        time_interval, time_interval_name = time_to_seconds(time_interval)

        materials = list(self.material_list.materials_by_name.values())
        p, q = len(materials), len(self.recipes)
        X = np.zeros((p, q), dtype=np.float64)
        for i, recipe in self.recipes.items():
            X[:, i] = recipe.recipe_vector(materials)

        # If a material is specified as an input: Remove it as output from every recipe.
        for material in inputs:
            X[material.id][X[material.id] > 0] = 0

        c = np.array([weights[material] if material in weights.keys() else 0 for material in materials],
                     dtype=np.float64)
        cost_summand_from_weights = recipe_weight_factor * self.recipe_weights
        cost_vector = np.matmul(c, X) + cost_summand_from_weights

        bounds = np.full((q, 2), np.nan, dtype=np.float64)
        bounds[:, 0] = 0
        b_ub = np.zeros((p,))
        A_ub = -X.copy()
        for i in range(A_ub.shape[0]):
            if materials[i] in inputs:
                A_ub[i, :] = 0
        A_eq = np.zeros((p, p))
        A_eq[0, 0] = 1
        A_eq = np.matmul(A_eq, X)
        b_eq = np.zeros((p,))
        for i in range(b_eq.size):
            if materials[i] == output_spec[0]:
                b_eq[0] = output_spec[1]

        # print(c)
        # print(X)
        # print(f'c = {np.matmul(c, X)}')
        # print(f'A_ub = {A_ub}')
        # print(f'b_ub = {b_ub}')
        # print(f'A_eq = {A_eq}')
        # print(f'b_eq = {b_eq}')
        # print(f'bounds = {bounds}')

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
                              f'be crafted via the imported recipes or are not specified as input materials.')
            elif result.status == 3:
                _LOGGER.error(f'The optimization problem is unbounded. Possibly, because there are no materials '
                              f'with negative weights.')
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
        machine_cost = np.sum(cost_summand_from_weights * recipe_vector)
        combined_cost = material_cost + machine_cost
        print(f'Material cost: {"{:.2f}%".format(100 * material_cost / combined_cost)}')
        print(f'Machine cost: {"{:.2f}%".format(100 * machine_cost / combined_cost)}')

        # print(f'recipe_vector = {recipe_vector.tolist()}')
        # print(f'material_vector = {np.matmul(X, recipe_vector).tolist()}')
        crafting_chain = CraftingChain(
            self.create_hypergraph([recipe for i, recipe in self.recipes.items() if recipe_vector[i] > 0]),
            recipe_vector,
            X
        )

        crafting_chain.draw(self.material_list.materials_by_id, self.recipes, time, time_interval / time,
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
