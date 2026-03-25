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
from ..configs.crafting_chain_config import CraftingChainConfig
from ..crafting_chains.crafting_chain import CraftingChain
from ..recipes.voltage_tiers import VoltageTier

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class CraftingChainFinder:
    recipe_book: RecipeBook
    machine_limit: int
    use_individual_limits: bool

    def __init__(self, recipe_book: RecipeBook, machine_limit: int, use_individual_limits: bool = True):
        self.recipe_book = recipe_book
        self.machine_limit = machine_limit
        self.use_individual_limits = use_individual_limits

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
        config: CraftingChainConfig,
        recipe_weight_factor: float = 1,
        update_machine_types: bool = True
    ) -> CraftingChain | None:
        def _select_higher_machine(recipe_id: int) -> None:
            recipe = self.recipes[recipe_id]
            if recipe.processing_time <= 0:
                return

            machine_amount = crafting_chain.machine_amounts[recipe_id]
            if recipe.cap is not None and machine_amount > recipe.cap:
                _LOGGER.info(f'Updating {recipe}...')
                if not recipe.machine.machine_type.multiblock:
                    _LOGGER.debug('Update singleblock')
                    recipe.select_suitable_voltage_tier(
                        max_voltage_tier=config.default_voltage_tier,
                        machine_amount=machine_amount,
                        max_machine_amount=config.max_singleblock_machines,
                        default_voltage_tier=0,
                        maximal_energy_increase=None  # as we only update to the default voltage tier
                    )
                    # Now: Default voltage tier is not enough. Try to upgrade to a parallel machine type next.
                    # This time up to the maximal voltage tier

                old_throughput = machine_amount * recipe.base_recipe_count() / recipe.processing_time
                new_machine_type = machine_type_book.get_parallel_option(recipe.base_machine_type)
                if new_machine_type != recipe.machine.machine_type:
                    _LOGGER.debug(f'Update machine type for recipe {recipe}. Old: {recipe.machine.machine_type} '
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
                    default_voltage_tier=config.default_voltage_tier,
                    maximal_energy_increase=config.maximal_energy_increase
                )

        # ---------------- START OF METHOD  ----------------

        crafting_chain = self._optimal_crafting_chain(
            config=config,
            recipe_weight_factor=recipe_weight_factor,
            use_individual_limits=self.use_individual_limits and not update_machine_types
        )
        if crafting_chain is not None: _LOGGER.info('First crafting chain determined successfully!')
        if crafting_chain is None or not update_machine_types:
            return crafting_chain
        _LOGGER.info('Trying to update machine types...')

        # Try to increase machine types and voltage tier to stick to the machine limits
        for recipe_id in crafting_chain.recipes.keys():
            _select_higher_machine(recipe_id)

        crafting_chain = self._optimal_crafting_chain(
            config=config,
            recipe_weight_factor=recipe_weight_factor,
            use_individual_limits=self.use_individual_limits
        )
        if crafting_chain is not None:
            _LOGGER.info('Second crafting chain determined successfully!')
        else:
            _LOGGER.info('Second crafting chain could not be determined!')
        return crafting_chain

    def _optimal_crafting_chain(
        self,
        config: CraftingChainConfig,
        recipe_weight_factor: float = 1,
        use_individual_limits: bool = False
    ) -> CraftingChain | None:
        """
        :param config:
        :param recipe_weight_factor:
        :param use_individual_limits: If True, add additional constraints to limit the number of machines for each recipe
        :return:
        """
        self._validate_parameters(config)

        inputs, outputs = config.inputs, config.outputs
        infinite_materials = config.infinite_materials
        material_weights = config.weights
        infinite_production_weights = config.infinite_production_weights
        lower_bounds, upper_bounds, equalities = config.lower_bounds, config.upper_bounds, config.equalities
        time, display_interval = config.time, config.display_interval
        self._fill_missing_material_weights(material_weights, infinite_materials, infinite_production_weights)

        time, _ = time_to_seconds(time)
        materials = list(self.materials_by_name.values())
        recipes = self.recipes
        p, q = len(materials), len(recipes)
        X = np.zeros((p, q), dtype=np.float64)
        for i, recipe in enumerate(recipes.values()):
            X[:, i] = recipe.recipe_vector(materials)
        recipe_matrix = X.copy()
        recipe_weights = np.array([r.weight for r in recipes.values()])

        # Remove infinite materials with weight zero from outputs
        zero_weight_infinites = {m for m in infinite_materials if m.is_eu() or m not in material_weights.keys() or material_weights[m] == 0}
        for material in zero_weight_infinites:
            X[material.id][X[material.id] > 0] = 0

        # Infinite Production
        infinite_material_list = list(m for m in infinite_materials)
        X_infinite = np.zeros((p, len(infinite_material_list)), dtype=np.float64)
        for i, material in enumerate(infinite_material_list):
            X_infinite[:, i] = [(1 if m == material else 0) for m in materials]
        X = np.concatenate([X, X_infinite], axis=1)

        # Convert to optimization problem
        c = np.array(
            [material_weights[material] if material in material_weights.keys() else 0 for material in
             materials], dtype=np.float64)
        cost_summand_from_weights = recipe_weight_factor * recipe_weights
        cost_summand_from_weights = np.concatenate([
            cost_summand_from_weights, [infinite_production_weights[m] for m in infinite_material_list]
        ])
        cost_vector = - np.matmul(c, X[:, :]) + cost_summand_from_weights  # this will be minimized

        # for material in materials:
        #     if material in material_weights.keys():
        #         _LOGGER.info(f'Weight of {material}: {material_weights[material]}')
        # for i, recipe in enumerate(recipes.values()):
        #     if cost_vector[i] >= 0:
        #         continue
        #     _LOGGER.info(f'Cost of {recipe.id}: {cost_vector[i]}. Inputs {recipe.get_inputs()}. '
        #                     f'Outputs. {recipe.get_outputs()}')
        # for i, recipe in enumerate(recipes.values()):
        #     _LOGGER.info(f'Cost {cost_vector[i]}.'
        #                     f'{[(m, j, X[j, i]) for j, m in enumerate(materials) if X[j, i] != 0]}. Recipe {recipe}.')
        # for i, material in enumerate(infinite_material_list):
        #     _LOGGER.info(f'Cost {cost_vector[q+i]}, {np.nonzero(X[:, q+i])[0]}'
        #                     f'{[(m, j, X[j, q+i]) for j, m in enumerate(materials) if X[j, q+i] != 0]}')

        bounds = []
        for recipe in recipes.values():
            bounds.append((0, self.machine_amount_cap(recipe, time, use_individual_limits)))
        bounds += [(0, None) for m in infinite_material_list]

        A_ub, b_ub = [], []
        A_eq, b_eq = [], []
        for i in range(X.shape[0]):
            if materials[i] not in inputs:
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

        for i, x in enumerate(recipe_vector):
            if bounds[i][1] is not None and x >= bounds[i][1]:
                _LOGGER.warning(f'Machine Limit reached for recipe with ID {i}: {x} = {bounds[i][1]}')

        # material_cost = np.sum(np.matmul(c, X) * recipe_vector)
        # machine_cost = np.sum(cost_summand_from_weights[:q] * recipe_vector[:q] / recipe_weight_factor)

        infinite_material_dict = {m: False for m in self.recipe_book.material_list.materials_by_id.values()}
        for material in infinite_materials:
            infinite_material_dict[material] = True

        crafting_chain = CraftingChain(
            hypergraph=self.create_hypergraph([recipe for i, recipe in enumerate(recipes.values()) if recipe_vector[i] > 0]),
            recipe_amounts={recipe.id: amount for amount, recipe in zip(recipe_vector, recipes.values())},
            recipe_matrix=recipe_matrix,
            materials=self.recipe_book.material_list.materials_by_id,
            infinite_materials=infinite_material_dict,
            recipes=self.recipe_book.recipes,
            time=time,
        )
        return crafting_chain

    def machine_amount_cap(self, recipe: Recipe, time: float, use_individual_limits: bool) -> float | None:
        if recipe.processing_time == 0:
            return None
        if not use_individual_limits or recipe.cap is None:
            return self.machine_limit * time / recipe.processing_time
        return min(recipe.cap * time / recipe.processing_time, self.machine_limit * time / recipe.processing_time)

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

    def _validate_parameters(self, config: CraftingChainConfig) -> None:
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
    def _fill_missing_material_weights(material_weights, infinite_materials, infinite_production_weights) -> None:
        for material in infinite_materials:
            if material not in material_weights.keys():
                material_weights[material] = 0
            if material not in infinite_production_weights.keys():
                infinite_production_weights[material] = 0

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
                    _LOGGER.warning(f'Cost of {recipe.id}: {cost_vector[i]}. Inputs {recipe.get_inputs()}. '
                                 f'Outputs. {recipe.get_outputs()}')
            hypergraph = self.create_hypergraph(negative_cost_recipes, start=False)
            node_labels = {materials[material_id].id: materials[material_id].get_abbreviation() for material_id
                           in hypergraph.nodes}
            xgi.draw_bipartite(hypergraph, node_labels=node_labels, node_size=47, aspect='auto')
            plt.show()
            return False
        return True
