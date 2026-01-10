import copy

import xgi
from typing import Dict
import matplotlib.pyplot as plt
from scipy.optimize import linprog
import numpy as np
import logging
from copy import deepcopy

from ..recipes.recipe_book import RecipeBook
from ..recipes.material import Material
from ..recipes.recipe import Recipe
from ..recipes.machine_type_books import MachineTypeBook
from ..recipes.machine_options.machine_option_books import MachineOptionsBook
from ..utility.general_utility import time_to_seconds
from ..configs.config import Config
from ..crafting_chains.crafting_chain import CraftingChain
from ..recipes.voltage_tiers import VoltageTier

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

    def optimal_crafting_chain(
        self,
        machine_type_book: MachineTypeBook,
        machine_options_book: MachineOptionsBook,
        config: Config,
        recipe_weight_factor: float = 1,
        use_machine_limits: bool = False,
        update_machine_types: bool = True
    ) -> CraftingChain | None:
        def _select_higher_machine(recipe_id: int) -> None:
            recipe = self.recipes[recipe_id]
            if recipe.processing_time <= 0:
                return

            machine_amount = crafting_chain.machine_amounts[recipe_id]
            if recipe.cap is not None and machine_amount > recipe.cap:
                _LOGGER.info(f'\n\nUpdating {recipe}...')
                if not recipe.machine.machine_type.multiblock:
                    _LOGGER.info('Update singleblock')
                    recipe.select_suitable_voltage_tier(
                        max_voltage_tier=config.default_voltage_tier,
                        machine_amount=machine_amount,
                        max_machine_amount=config.max_singleblock_machines,
                        maximal_energy_increase=None  # as we only update to the default voltage tier
                    )
                    # Now: Default voltage tier is not enough. Try to upgrade to a parallel machine type next.
                    # This time up to the maximal voltage tier

                old_throughput = machine_amount * recipe.base_recipe_count() / recipe.processing_time
                new_machine_type = machine_type_book.get_parallel_option(recipe.base_machine_type)
                if new_machine_type != recipe.machine.machine_type:
                    _LOGGER.info(f'Update machine type for recipe {recipe}. Old: {recipe.machine.machine_type} '
                                 f'New: {new_machine_type}. \nReason: Machine amount {machine_amount} '
                                 f'exceeds limit {recipe.cap}')
                    recipe.update(
                        config=config, machine_options_book=machine_options_book, machine_type=new_machine_type
                    )

                new_machine_amount = old_throughput * recipe.processing_time / recipe.base_recipe_count()
                if new_machine_amount <= config.max_machines(multiblock=new_machine_type.multiblock):
                    return
                recipe.select_suitable_voltage_tier(
                    max_voltage_tier=config.max_voltage_tier,
                    machine_amount=new_machine_amount,
                    max_machine_amount=config.max_machines(multiblock=new_machine_type.multiblock),
                    maximal_energy_increase=config.maximal_energy_increase
                )

        # ---------------- START OF METHOD  ----------------

        crafting_chain = self._optimal_crafting_chain(
            config=config,
            recipe_weight_factor=recipe_weight_factor,
            use_machine_limits=use_machine_limits and not update_machine_types
        )
        if not update_machine_types:
            return crafting_chain

        # Try to increase machine types and voltage tier to stick to the machine limits
        for recipe_id in crafting_chain.recipes.keys():
            _select_higher_machine(recipe_id)

        return self._optimal_crafting_chain(
            config=config,
            recipe_weight_factor=recipe_weight_factor,
            use_machine_limits=use_machine_limits
        )

    def _optimal_crafting_chain(
        self,
        config: Config,
        recipe_weight_factor: float = 1,
        use_machine_limits: bool = False
    ) -> CraftingChain | None:
        """
        :param config:
        :param recipe_weight_factor:
        :param use_machine_limits: If True, add additional constraints to limit the number of machines for each recipe
        :return:
        """
        self._validate_parameters(config)

        inputs, outputs = config.inputs, config.outputs
        infinite_materials = config.infinite_materials
        material_weights = config.weights
        lower_bounds, upper_bounds, equalities = config.lower_bounds, config.upper_bounds, config.equalities
        time, display_interval, mode = config.time, config.display_interval, config.mode
        self._fill_missing_material_weights(material_weights, infinite_materials)

        time, _ = time_to_seconds(time)
        materials = list(self.materials_by_name.values())
        recipes = self.recipes
        p, q = len(materials), len(recipes)
        X = np.zeros((p, q), dtype=np.float64)
        for i, recipe in enumerate(recipes.values()):
            X[:, i] = recipe.recipe_vector(materials)
        recipe_matrix = X.copy()
        recipe_weights = np.array([r.weight for r in recipes.values()])

        for material in infinite_materials:
            X[material.id][X[material.id] > 0] = 0

        # Convert to optimization problem
        c = np.array(
            [material_weights[material] if material in material_weights.keys() else 0 for material in
             materials], dtype=np.float64)
        cost_summand_from_weights = recipe_weight_factor * recipe_weights

        match mode:
            case 'Min':
                cost_vector = np.matmul(c, X) + cost_summand_from_weights
            case 'Max':
                cost_vector = - (np.matmul(c, X) - cost_summand_from_weights)
            case _:
                raise ValueError(f'Please specify a valid mode: Min or Max')

        bounds = [
            (0, None if not use_machine_limits or recipe.cap is None or recipe.processing_time == 0
             else recipe.cap * time / recipe.processing_time) for recipe in recipes.values()
        ]
        A_ub, b_ub = [], []
        A_eq, b_eq = [], []
        unrestricted_materials = inputs.union(infinite_materials)
        for i in range(X.shape[0]):
            if materials[i] not in unrestricted_materials:
                A_ub.append(-X[i, :])
                b_ub.append(0)
            if materials[i] in lower_bounds.keys():
                A_ub.append(-X[i, :])
                b_ub.append(-lower_bounds[materials[i]])
            if materials[i] in upper_bounds.keys():
                A_ub.append(X[i, :])
                b_ub.append(upper_bounds[materials[i]])
            if materials[i] in equalities.keys():
                A_eq.append(X[i, :])
                b_eq.append(equalities[materials[i]])
        A_ub = np.array(A_ub)
        b_ub = np.array(b_ub)
        A_eq = np.array(A_eq)
        b_eq = np.array(b_eq)

        if not (A_ub.shape[0] == b_ub.shape[0] > 0):
            A_ub = np.zeros((1, q))
            b_ub = np.zeros((1,))
        if not (A_eq.shape[0] == b_eq.shape[0] > 0):
            A_eq = np.zeros((1, q))
            b_eq = np.zeros((1,))

        # Optimize via lin prog
        result = linprog(
            c=cost_vector,
            A_ub=A_ub,
            b_ub=b_ub,
            A_eq=A_eq,
            b_eq=b_eq,
            bounds=bounds,
            method='highs'
        )

        # Handle errors
        if not self._handle_errors(result, materials, cost_vector, recipes):
            return None
        recipe_vector = result.x

        material_cost = np.sum(np.matmul(c, X) * recipe_vector)
        machine_cost = np.sum(cost_summand_from_weights * recipe_vector / recipe_weight_factor)
        combined_cost = material_cost + machine_cost
        # if combined_cost != 0:
        #     print(f'Material cost: {"{:.2f}%".format(100 * material_cost / combined_cost)}')
        #     print(f'Machine cost: {"{:.2f}%".format(100 * machine_cost / combined_cost)}')
        # else:
        #     print(f'Material cost = Machine cost = 0.')

        infinite_material_dict = {m: False for m in self.recipe_book.material_list.materials_by_id.values()}
        for material in infinite_materials:
            infinite_material_dict[material] = True

        crafting_chain = CraftingChain(
            hypergraph=self.create_hypergraph([recipe for i, recipe in enumerate(recipes.values()) if recipe_vector[i] > 0]),
            recipe_amounts={recipe.id: amount for amount, recipe in zip(result.x, recipes.values())},
            recipe_matrix=recipe_matrix,
            materials=self.recipe_book.material_list.materials_by_id,
            infinite_materials=infinite_material_dict,
            recipes=self.recipe_book.recipes,
            time=time,
        )
        return crafting_chain

    @staticmethod
    def create_hypergraph(recipes: list[Recipe], start=False) -> xgi.DiHypergraph:
        hypergraph = xgi.DiHypergraph()
        for recipe in recipes:
            input_data, output_data = recipe.get_edge_data(eu=False)
            if input_data and output_data:
                hypergraph.add_edge((input_data, output_data), idx=recipe.id)
        in_degrees = hypergraph.nodes.in_degree.asdict()
        if start:
            for node, in_degree in in_degrees.items():
                if in_degree == 0:
                    hypergraph.add_edge([[-1], [node]], id=-1)
        return hypergraph

    def _validate_parameters(self, config: Config) -> None:
        for material in config.inputs.intersection(config.infinite_materials):
            _LOGGER.warning(f'Material {material} was specified both as input and infinite.')
        if self.materials_by_name['EU'] not in config.outputs.union(config.infinite_materials):
            _LOGGER.warning(f'Did you forget to add EU to infinite_materials?')

        _LOGGER.debug('Materials which cannot be produced from recipes and are not specified as input or '
                     'infinite materials:')
        for material in self.materials_by_name.values():
            if any([material in recipe.get_outputs() for recipe in self.recipes.values()]):
                continue
            if material in config.infinite_materials or material in config.inputs:
                continue
            _LOGGER.debug(material)

        for material in config.infinite_materials:
            if material in config.lower_bounds.keys():
                _LOGGER.warning(f'A restriction was specified for an infinite material: '
                                f'{material.name} >= {config.lower_bounds[material]}')
            if material in config.upper_bounds.keys():
                _LOGGER.warning(f'A restriction was specified for an infinite material: '
                                f'{material.name} <= {config.upper_bounds[material]}')
            if material in config.equalities.keys():
                _LOGGER.warning(f'A restriction was specified for an infinite material: '
                                f'{material.name} = {config.equalities[material]}')

    @staticmethod
    def _fill_missing_material_weights(material_weights, infinite_materials) -> None:
        for material in infinite_materials:
            if material not in material_weights.keys():
                material_weights[material] = 0
            else:
                if material_weights[material] != 0:
                    _LOGGER.info(f'A weight was specified for the infinite material {material.name}. '
                                 f'Using the specified weight {material_weights[material]} instead of 0.')

    def _handle_errors(self, optimization_result, materials, cost_vector, recipes) -> bool:
        """
        Returns False, if an error occurred.
        :param optimization_result:
        :param materials:
        :param cost_vector:
        :return:
        """
        if optimization_result.status != 0:
            if optimization_result.status == 2:
                _LOGGER.error(f'The optimization problem is infeasible. Possibly, because a required material cannot '
                              f'be crafted via the imported recipes or is not specified as an input material.')
            elif optimization_result.status == 3:
                _LOGGER.error(f'The optimization problem is unbounded. Possibly, because there is a recipe with '
                              f'negative cost.')
            else:
                _LOGGER.error(f'An unknown error occurred: {optimization_result.status}')

            _LOGGER.error(f'Plotting all recipes with negative cost')
            negative_cost_recipes = []
            for i, recipe in enumerate(recipes.values()):
                if cost_vector[i] < 0:
                    negative_cost_recipes.append(recipe)
                    _LOGGER.info(f'Cost of {recipe.id}: {cost_vector[i]}. Inputs {recipe.get_inputs()}. '
                                 f'Outputs. {recipe.get_outputs()}')
            hypergraph = self.create_hypergraph(negative_cost_recipes, start=False)
            node_labels = {materials[material_id].id: materials[material_id].get_abbreviation() for material_id
                           in hypergraph.nodes}
            xgi.draw_bipartite(hypergraph, node_labels=node_labels, node_size=47, aspect='auto')
            plt.show()
            return False
        return True
