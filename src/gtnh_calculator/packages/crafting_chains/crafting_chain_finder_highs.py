from typing import Dict
import numpy as np
import logging

from scipy.sparse import coo_matrix, hstack, vstack, csr_matrix
from highspy import Highs, HighsModelStatus

from ..recipes_db.material import Material
from ..recipes_db.recipes import Recipe
from ..utility.general_utility import time_to_seconds
from ..configs.crafting_chain_config_db import CraftingChainConfig
from ..crafting_chains.crafting_chain_db import CraftingChain
from ..crafting_chains.crafting_chain_database import CraftingChainDatabase

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


NEGATIVE_RANK_RECIPE_PENALTY = 1000


class CraftingChainFinder:
    crafting_chain_database: CraftingChainDatabase
    machine_limit: int
    use_individual_limits: bool

    def __init__(self, crafting_chain_database: CraftingChainDatabase, machine_limit: int,
                 use_individual_limits: bool = True):
        self.crafting_chain_database = crafting_chain_database
        self.machine_limit = machine_limit
        self.use_individual_limits = use_individual_limits

    @property
    def recipes(self) -> Dict[str, Recipe]:
        return self.crafting_chain_database.recipes

    @property
    def materials_by_id(self) -> Dict[str, Material]:
        return self.crafting_chain_database.database.extracted_materials

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

        materials = list(self.materials_by_id.values())
        index_by_material = {m: i for i, m in enumerate(materials)}
        zero_weight_infinites = {m for m in infinite_materials if
                                 m not in material_weights.keys() or material_weights[m] == 0}
        is_zero_weight_infinite = {m: False for m in materials}
        for material in zero_weight_infinites:
            is_zero_weight_infinite[material] = True
        # recipes = list([r for r in self.recipes.values() if self.crafting_chain_database.recipe_grading[r] >= 0])
        recipes = list(self.recipes.values())
        p, q = len(materials), len(recipes)

        rows, cols, data = [], [], []
        for i, recipe in enumerate(recipes):
            for material, amount in recipe.material_dict.items():
                if is_zero_weight_infinite[material] or amount == 0:
                    continue
                cols.append(i)
                rows.append(index_by_material[material])
                data.append(amount)
        X_q = coo_matrix((data, (rows, cols)), shape=(p, q)).tocsr()

        # Infinite Production
        infinite_material_list = list(infinite_materials)
        r = len(infinite_material_list)
        rows, cols, data = [], [], []
        for i, material in enumerate(infinite_material_list):
            cols.append(i)
            rows.append(index_by_material[material])
            data.append(1)
        X_infinite = coo_matrix((data, (rows, cols)), shape=(p, r)).tocsr()
        X = hstack([X_q, X_infinite])

        recipe_weights = np.array([1 for r in recipes])  # TODO: not yet implemented

        # Convert to optimization problem
        c = np.array(
            [material_weights[material] if material in material_weights.keys() else 0 for material in
             materials], dtype=np.float64)
        cost_summand_from_weights = recipe_weight_factor * recipe_weights
        cost_summand_from_weights = np.concatenate([
            cost_summand_from_weights, [infinite_production_weights[m] for m in infinite_material_list]
        ])
        _LOGGER.info(f'MinMax c: {np.min(np.abs(c))}, {np.max(np.abs(c))}')
        _LOGGER.info(f'MinMax X: {np.min(np.abs(X))}, {np.max(np.abs(X))}')
        cost_vector = - (c @ X) + cost_summand_from_weights  # this will be minimized TODO
        cost_vector /= np.mean(np.abs(cost_vector))
        _LOGGER.info(f'MinMax cost_vector: {np.min(np.abs(cost_vector))}, {np.max(np.abs(cost_vector))}')
        _LOGGER.info(f'Number of positive cost values: {np.sum(cost_vector > 0)}')
        _LOGGER.info(f'Number of negative cost values: {np.sum(cost_vector < 0)}')

        lb = np.zeros(shape=(q + r,))
        # ub = np.array([
        #     (self.machine_amount_cap(recipe, time, use_individual_limits)
        #      if self.crafting_chain_database.recipe_grading[recipe] >= 0 else 0) for recipe in recipes
        # ])
        ub = np.array([
            self.machine_amount_cap(recipe, time, use_individual_limits) for recipe in recipes
        ])
        ub = np.concatenate([ub, np.full(r, np.inf)])

        A_mat = X[[index_by_material[m] for m in materials if m not in inputs]]
        b_mat = np.zeros((A_mat.shape[0],))
        A_lb = X[[index_by_material[m] for m in lower_bounds.keys()]]
        b_lb = np.array([b for m, b in lower_bounds.items()])
        A_ub = X[[index_by_material[m] for m in upper_bounds.keys()]]
        b_ub = np.array([b for m, b in upper_bounds.items()])
        A_eq = X[[index_by_material[m] for m in equalities.keys()]]
        b_eq = np.array([a for m, a in equalities.items()])
        A_machine_limit = np.array([
            r.processing_time for r in recipes
        ])
        A_machine_limit = np.concatenate([A_machine_limit, np.zeros(r)]) / time

        # Combine constraints
        A = vstack(
            [A_mat, A_lb, A_ub, A_eq, A_machine_limit]
        ).tocsr()
        b_lower = np.concatenate(
            [b_mat, b_lb, np.full_like(b_ub, -np.inf), b_eq, np.zeros(1)]
        )
        b_upper = np.concatenate(
            [np.full_like(b_mat, np.inf), np.full_like(b_lb, np.inf), b_ub, b_eq, np.array([config.machine_limit])]
        )

        """
            -------------------------- First Highs --------------------------
        """

        highs_solver = HighsSolver(
            name='Initial solver',
            constraint_matrix=A,
            b_lower=b_lower,
            b_upper=b_upper,
            lb=lb,
            ub=ub,
            cost_vector=cost_vector
        )
        solution = highs_solver.solve()
        if solution is None:
            _LOGGER.error(f'HiGHS solver {highs_solver.name} failed to find an optimal solution.')
            return None
        highs_solver.print_solution_statistics(solution, X, cost_vector)
        last_optimal_value: float = float(highs_solver.optimal_value)

        # """
        #     -------------------------- Negative Recipe Rank Penalty --------------------------
        # """
        #
        # # recipe_penalty = np.array([
        # #     NEGATIVE_RANK_RECIPE_PENALTY * abs(last_optimal_value)
        # #     if self.crafting_chain_database.recipe_grading[recipe] < 0 else 0 for recipe in recipes
        # # ])
        # # _LOGGER.info(f'Penalties: {np.sum(recipe_penalty > 0)}. Penalty size: {np.max(np.abs(recipe_penalty))}')
        # # recipe_penalty = np.concatenate([recipe_penalty, np.zeros(r)])
        # _LOGGER.info(f'PENALTY!')
        # ub_penalty = np.array([
        #     0 if self.crafting_chain_database.recipe_grading[recipe] < 0
        #     else self.machine_amount_cap(recipe, time, use_individual_limits) for recipe in recipes
        # ])
        # ub_penalty = np.concatenate([ub_penalty, ub[q:]])
        #
        # highs_solver = HighsSolver(
        #     name='Negative recipe rank penalty solver',
        #     constraint_matrix=A,
        #     b_lower=b_lower,
        #     b_upper=b_upper,
        #     lb=lb,
        #     ub=ub_penalty,
        #     cost_vector=cost_vector
        # )
        # solution = highs_solver.solve()
        # if solution is None:
        #     _LOGGER.error(f'HiGHS solver {highs_solver.name} failed to find an optimal solution.')
        #     return None
        # highs_solver.print_solution_statistics(solution, X, cost_vector)
        # last_optimal_value = float(highs_solver.optimal_value)

        """
            -------------------------- Machine amount reduction --------------------------
        """

        delta = 0  # 10 * abs(last_optimal_value)  # 0.3 * np.mean(cost_vector[cost_vector != 0])
        _LOGGER.info(f'last_optimal_value: {last_optimal_value}')
        _LOGGER.info(f'{np.sum(cost_vector != 0)} non zero cost_vector costs')
        _LOGGER.info(f'delta: {delta}')
        c1 = np.array([r.processing_time / time if r.positive_processing_time() else 1 / time for r in recipes])
        c2 = np.zeros(shape=(r,))
        secondary_cost = np.concatenate([c1, c2])
        highs_solver = HighsSolver(
            name='Machine amount reduction solver',
            constraint_matrix=A,
            b_lower=b_lower,
            b_upper=b_upper,
            lb=lb,
            ub=ub,
            cost_vector=secondary_cost
        )

        # sparse row for cost function
        cost_indices = np.arange(q + r, dtype=np.int32)
        highs_solver.highs.addRows(
            1,
            -np.inf,
            last_optimal_value + delta,
            len(cost_indices),
            np.array([0, len(cost_indices)], dtype=np.int32),
            cost_indices,
            cost_vector
        )
        solution = highs_solver.solve()
        if solution is None:
            _LOGGER.error(f'HiGHS solver {highs_solver.name} failed to find an optimal solution.')
            return None
        highs_solver.print_solution_statistics(solution, X, cost_vector)

        recipe_vector = solution
        recipe_amounts = {r: a for r, a in zip(recipes, recipe_vector[:q]) if a != 0}
        material_vector = X @ recipe_vector
        material_amounts = {m: a for m, a in zip(materials, material_vector)}
        # for i, x in enumerate(recipe_vector[:q]):
        #     if not np.isinf(ub[i]) and x >= ub[i]:
        #         _LOGGER.warning(f'Machine Limit reached for recipe {recipes[i]}: {x} = {ub[i]}')

        crafting_chain = CraftingChain(
            recipe_amounts=recipe_amounts,
            total_material_needs=material_amounts,
            input_materials=inputs,
            infinite_materials=infinite_materials,
            time=time
        )
        return crafting_chain

    def machine_amount_cap(self, recipe: Recipe, time: float, use_individual_limits: bool) -> float:
        if use_individual_limits and recipe.cap is not None and recipe.positive_processing_time():
            return min(recipe.cap * time / recipe.processing_time, self.machine_limit * time / recipe.processing_time)
        return np.inf

    def _validate_parameters(self, config: CraftingChainConfig) -> None:
        for material in config.inputs.intersection(config.infinite_materials):
            _LOGGER.warning(f'Material {material} was specified both as input and infinite.')

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


class HighsSolver:
    def __init__(
        self,
        name: str,
        constraint_matrix: csr_matrix,
        b_lower: np.ndarray,
        b_upper: np.ndarray,
        lb: np.ndarray,
        ub: np.ndarray,
        cost_vector: np.ndarray
    ):
        highs = Highs()
        highs.setOptionValue("output_flag", False)
        highs.setOptionValue("solver", "ipm")
        highs.setOptionValue("presolve", "on")
        highs.setOptionValue("parallel", "on")
        highs.setOptionValue("time_limit", 25.0)
        self.highs = highs
        self.name = name
        self.constraint_matrix = constraint_matrix
        self.b_lower = b_lower
        self.b_upper = b_upper
        self.lb = lb
        self.ub = ub
        self.cost_vector = cost_vector

        self.highs.addCols(
            self.cost_vector.size,
            self.cost_vector,
            self.lb,
            self.ub,
            0,
            [], [], []
        )
        self.highs.addRows(
            self.constraint_matrix.shape[0],
            self.b_lower,
            self.b_upper,
            self.constraint_matrix.nnz,
            self.constraint_matrix.indptr,
            self.constraint_matrix.indices,
            self.constraint_matrix.data
        )

    def solve(self) -> np.ndarray | None:
        self.highs.run()
        status = self.highs.getModelStatus()

        match status:
            case HighsModelStatus.kOptimal:
                pass
            case _:
                _LOGGER.error(f'HiGHS failed with status {status}.')
                return None

        solution = self.highs.getSolution()
        return np.array(solution.col_value)

    def sanity_checks(self):
        _LOGGER.info(f'Sanity checks for HiGHS solver {self.name}:')
        _LOGGER.info("  A nnz:", self.constraint_matrix.nnz)
        _LOGGER.info("  Any NaN in A.data:", np.isnan(self.constraint_matrix.data).any())
        _LOGGER.info(f'OPTIMAL cost: {self.optimal_value}')

    def print_solution_statistics(
            self, recipe_vector: np.ndarray, recipe_matrix: np.ndarray, cost_vector: np.ndarray) -> None:
        _LOGGER.info(f'Solution statistics for HiGHS solver {self.name}:')
        material_vector = recipe_matrix @ recipe_vector
        _LOGGER.info(f'Non zeros: {np.sum(recipe_vector != 0)}')
        _LOGGER.info(f'MinMax: {np.min(np.abs(recipe_vector))}, {np.max(np.abs(recipe_vector))}')
        _LOGGER.info(f'Positive materials: {np.sum(material_vector > 0)}')
        _LOGGER.info(f'Negative materials: {np.sum(material_vector < 0)}')
        _LOGGER.info(f'Optimal (material) cost: {cost_vector @ recipe_vector}')

    @property
    def optimal_value(self) -> float:
        return self.highs.getObjectiveValue()
