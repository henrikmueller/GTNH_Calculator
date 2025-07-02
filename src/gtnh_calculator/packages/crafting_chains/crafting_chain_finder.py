import xgi
from xgi import DiHypergraph
from typing import Dict
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

    def __init__(
        self,
        material_list: MaterialList,
        recipes: Dict[int, Recipe]
    ):
        self.material_list = material_list
        self.recipes = recipes

    def draw_optimal_crafting_chain(
            self,
            inputs: set[Material],
            output_spec: tuple[Material, float],
            weights: Dict[Material, float],
            time: str,
            time_interval: str,
            excluded_materials: set[Material] | None = None
    ) -> None:
        """
        :param inputs:
        :param output_spec:
        :param weights:
        :param excluded_materials:
        :param time: Outputs are required every time seconds.
        :param time_interval: For displaying
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
        c = np.array([weights[material] if material in weights.keys() else 0 for material in materials], dtype=np.float64)
        bounds = np.full((q, 2), np.nan, dtype=np.float64)
        bounds[:, 0] = 0
        b_ub = np.zeros((p,))
        A_ub = -X
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
            c=np.matmul(c, X),
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
                return None
            if result.status == 3:
                _LOGGER.error(f'The optimization problem is unbounded. Possibly, because there are no materials '
                              f'with negative weights.')
                return None
            _LOGGER.error(f'An unknown error occurred: {result.status}')


        recipe_vector = result.x
        # print(f'recipe_vector = {recipe_vector.tolist()}')
        # print(f'material_vector = {np.matmul(X, recipe_vector).tolist()}')
        crafting_chain = CraftingChain(self.create_hypergraph(recipe_vector), recipe_vector, X)

        crafting_chain.draw(self.material_list.materials_by_id, self.recipes, time, time_interval / time,
                            time_interval_name)

    def create_hypergraph(self, recipe_vector: np.ndarray) -> xgi.DiHypergraph:
        hypergraph = xgi.DiHypergraph()
        for id, recipe in self.recipes.items():
            if recipe_vector[id] <= 0:
                continue
            input_data, output_data = recipe.get_edge_data(eu=False)
            if input_data and output_data:
                hypergraph.add_edge((input_data, output_data), id=recipe.id)
        in_degrees = hypergraph.nodes.in_degree.asdict()
        for node, in_degree in in_degrees.items():
            if in_degree == 0:
                hypergraph.add_edge([[-1], [node]], id=-1)
        return hypergraph
