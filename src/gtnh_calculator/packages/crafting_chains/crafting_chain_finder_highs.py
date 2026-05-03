from typing import Dict
import numpy as np
import logging
from dataclasses import dataclass
from scipy.sparse import coo_matrix, hstack, vstack, csr_matrix
from itertools import product
from highspy import Highs, HighsModelStatus

from ..recipes_db.material import Material
from ..recipes_db.recipes import Recipe
from ..recipes_db.voltage_tiers import VoltageTier
from ..utility.general_utility import time_to_seconds
from ..configs.crafting_chain_config_db import CraftingChainConfig
from ..crafting_chains.crafting_chain_db import CraftingChain
from ..crafting_chains.crafting_chain_database import CraftingChainDatabase
from ..utility.constants import FLUID_WEIGHT_FACTOR
from ..utility.general_utility import Timer

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


def validate_config_parameters(config: CraftingChainConfig) -> None:
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


@dataclass
class CostVector:
    name: str
    vector: np.ndarray
    normalization_scalar: float

    @property
    def normalized_vector(self) -> np.ndarray:
        return self.vector / self.normalization_scalar

    def __repr__(self):
        return f'CostVector({self.name})'


@dataclass
class CostVectorCollection:
    recipe_cost_vector: CostVector
    eu_cost_vector: CostVector
    machine_amount_cost_vector: CostVector
    other_cost_vectors: list[CostVector]

    @property
    def cost_vector_list(self) -> list[CostVector]:
        return [self.recipe_cost_vector, self.eu_cost_vector, self.machine_amount_cost_vector] + self.other_cost_vectors

    def __len__(self) -> int:
        return len(self.cost_vector_list)

    def __iter__(self):
        return iter(self.cost_vector_list)

    def __getitem__(self, index) -> CostVector:
        return self.cost_vector_list[index]

    @property
    def recipe_index(self) -> int:
        for i, c in enumerate(self.cost_vector_list):
            if c.name == 'Recipe Cost Vector':
                return i
        raise ValueError('Recipe Cost Vector not found in collection.')

    @property
    def eu_index(self) -> int:
        for i, c in enumerate(self.cost_vector_list):
            if c.name == 'EU Cost Vector':
                return i
        raise ValueError('EU Cost Vector not found in collection.')

    @property
    def machine_amount_index(self) -> int:
        for i, c in enumerate(self.cost_vector_list):
            if c.name == 'Machine Amount Cost Vector':
                return i
        raise ValueError('Machine Amount Cost Vector not found in collection.')

    def standard_weighting(self) -> list[tuple[CostVector, float]]:
        return [
            (self.recipe_cost_vector, 1.0),
            (self.eu_cost_vector, 0.0),
            (self.machine_amount_cost_vector, 0.0)
        ] + [(c, 0.0) for c in self.other_cost_vectors]


@dataclass
class CostConstraints:
    eu_per_tick_constraint: float | None = None
    machine_amount_constraint: float | None = None

    def __repr__(self):
        return (f'CostConstraints(EU/t <= {self.eu_per_tick_constraint}, '
                f'Machine Amount <= {self.machine_amount_constraint})')


@dataclass
class OptimalSolution:
    recipe_vector: np.ndarray
    optimal_cost: float


class CraftingChainFinder:
    crafting_chain_database: CraftingChainDatabase
    machine_limit: int
    use_individual_limits: bool
    materials: list[Material]
    recipes: list[Recipe]
    infinite_material_list: list[Material]
    index_by_material: Dict[Material, int]
    p: int
    q: int
    r: int
    zero_weight_infinites: set[Material]
    is_zero_weight_infinite: Dict[Material, bool]
    config: CraftingChainConfig
    time: float
    recipe_matrix: csr_matrix
    infinite_production_matrix: csr_matrix
    total_recipe_matrix: csr_matrix

    def __init__(
        self, crafting_chain_database: CraftingChainDatabase, config: CraftingChainConfig,
        machine_limit: int, use_individual_limits: bool = True
    ):
        self.crafting_chain_database = crafting_chain_database
        self.machine_limit = machine_limit
        self.use_individual_limits = use_individual_limits
        self.materials = list(self.crafting_chain_database.database.extracted_materials.values())
        self.index_by_material = {m: i for i, m in enumerate(self.materials)}
        self.recipes = list(self.crafting_chain_database.recipes.values())
        self.p, self.q = len(self.materials), len(self.recipes)

        validate_config_parameters(config)
        self.config = config
        self.time, _ = time_to_seconds(config.time)

        self.zero_weight_infinites = {m for m in config.infinite_materials if
                                 m not in self.material_weights.keys() or self.material_weights[m] == 0}
        self.is_zero_weight_infinite = {m: False for m in self.materials}
        for material in self.zero_weight_infinites:
            self.is_zero_weight_infinite[material] = True

        # Recipe Matrix
        rows, cols, data = [], [], []
        for i, recipe in enumerate(self.recipes):
            for material, amount in recipe.material_dict.items():
                if amount == 0 or (self.is_zero_weight_infinite[material] and amount > 0):
                    continue
                cols.append(i)
                rows.append(self.index_by_material[material])
                data.append(amount)
        self.recipe_matrix = coo_matrix((data, (rows, cols)), shape=(self.p, self.q)).tocsr()

        # Infinite Production Matrix
        self.infinite_material_list = list(config.infinite_materials)
        self.r = len(self.infinite_material_list)
        rows, cols, data = [], [], []
        for i, material in enumerate(self.infinite_material_list):
            cols.append(i)
            rows.append(self.index_by_material[material])
            data.append(1)
        self.infinite_production_matrix = coo_matrix((data, (rows, cols)), shape=(self.p, self.r)).tocsr()
        self.total_recipe_matrix = hstack([self.recipe_matrix, self.infinite_production_matrix])

    @property
    def inputs(self) -> set[Material]:
        return self.config.inputs

    @property
    def outputs(self) -> set[Material]:
        return self.config.outputs

    @property
    def material_weights(self) -> dict[Material, float]:
        return self.config.weights

    @property
    def infinite_production_weights(self) -> dict[Material, float]:
        return self.config.infinite_production_weights

    @property
    def lower_bounds(self) -> dict[Material, float]:
        return self.config.lower_bounds

    @property
    def upper_bounds(self) -> dict[Material, float]:
        return self.config.upper_bounds

    @property
    def equalities(self) -> dict[Material, float]:
        return self.config.equalities

    def get_default_cost_vectors(self) -> CostVectorCollection:
        # Recipe Cost Vector
        cost_normalization = np.array(
            [(FLUID_WEIGHT_FACTOR if material.is_fluid() else 1) for material in self.materials]
        )
        c = np.array(
            [self.material_weights[material] if material in self.material_weights.keys() else 0 for material in
             self.materials], dtype=np.float64
        ) * cost_normalization
        infinite_production_weights = np.concatenate([
            np.zeros(self.q), [self.infinite_production_weights[m] for m in self.infinite_material_list]
        ])
        cost_vector = - (c @ self.total_recipe_matrix) + infinite_production_weights  # this will be minimized TODO
        _LOGGER.info(f'MinMax cost_vector: {np.min(np.abs(cost_vector))}, {np.max(np.abs(cost_vector))}')
        _LOGGER.info(f'Number of positive cost values: {np.sum(cost_vector > 0)}')
        _LOGGER.info(f'Number of negative cost values: {np.sum(cost_vector < 0)}')
        # restrictions = self.config.lower_bounds
        # d = np.array(
        #     [self.material_weights[material] if material in self.material_weights.keys() else 0 for material in
        #      self.materials]
        # )
        estimation = np.abs(cost_vector[cost_vector != 0]).mean()
        recipe_cost_vector = CostVector('Recipe Cost Vector', cost_vector, normalization_scalar=estimation)

        # EU Cost Vector
        eu_cost_vector = np.array([r.eu_per_tick for r in self.recipes])
        eu_cost_vector = - np.concatenate([eu_cost_vector, np.zeros(self.r)])
        _LOGGER.info(f'MinMax eu_cost_vector: {np.min(np.abs(eu_cost_vector))}, {np.max(np.abs(eu_cost_vector))}')
        _LOGGER.info(f'Number of positive cost values: {np.sum(eu_cost_vector > 0)}')
        _LOGGER.info(f'Number of negative cost values: {np.sum(eu_cost_vector < 0)}')
        estimation = VoltageTier.eu_per_tick(self.config.max_voltage_tier)
        eu_cost_vector = CostVector('EU Cost Vector', eu_cost_vector, normalization_scalar=estimation)

        # Machine Amount Cost Vector
        c1 = np.array(
            [r.processing_time / self.time if r.positive_processing_time() else 1 / self.time for r in self.recipes]
        )
        c2 = np.zeros(shape=(self.r,))
        cost_vector = np.concatenate([c1, c2])
        _LOGGER.info(f'MinMax machine_amount_cost_vector: {np.min(np.abs(cost_vector))}, {np.max(np.abs(cost_vector))}')
        _LOGGER.info(f'Number of positive cost values: {np.sum(cost_vector > 0)}')
        _LOGGER.info(f'Number of negative cost values: {np.sum(cost_vector < 0)}')
        estimation = 0.5 * self.config.machine_limit
        machine_amount_cost_vector = CostVector('Machine Amount Cost Vector', cost_vector,
                                                normalization_scalar=estimation)

        return CostVectorCollection(
            recipe_cost_vector=recipe_cost_vector,
            eu_cost_vector=eu_cost_vector,
            machine_amount_cost_vector=machine_amount_cost_vector,
            other_cost_vectors=[]
        )

    # def normalize_cost_vectors(self, cost_vectors: list[CostVector]) -> list[tuple[CostVector, float]]:
    #     normalization_estimations = np.array([c.normalization_scalar for c in cost_vectors])
    #     n = len(cost_vectors)
    #     weights = []
    #     for i, c in enumerate(cost_vectors):
    #         weights.append(np.eye(n)[i])
    #         weights.append(0.25 + np.eye(n)[i] * 0.25)
    #
    #     optimal_solutions = [
    #         self._optimal_solution(
    #             weighted_cost_vectors=[(c, w) for c, w in zip(cost_vectors, w.astype(float))],
    #             use_individual_limits=False
    #         ) for w in weights
    #     ]
    #     for solution, w in zip(optimal_solutions, weights):
    #         if solution is None:
    #             _LOGGER.warning(f'No optimal solution found for weight {w}.')
    #
    #     optimal_solution_costs = [
    #         (s, w, [np.dot(c.normalized_vector, s.recipe_vector) for c in cost_vectors],
    #          self.get_eu_per_tick(s), self.get_machine_amount(s))
    #         for s, w in zip(optimal_solutions, weights) if s is not None
    #     ]
    #     _LOGGER.info(f'Optimal solution costs for different weights:')
    #     for _, w, costs, eu_per_tick, machine_amount in optimal_solution_costs:
    #         _LOGGER.info(f'  Weights: {w}, Costs: {costs}, EU/t: {eu_per_tick}, Machine Amount: {machine_amount}')
    #
    #     return []

    def pareto_front(self, cost_vectors: CostVectorCollection) -> list[tuple[OptimalSolution, CostConstraints]]:
        n = len(cost_vectors)
        weights = []
        for i, c in enumerate(cost_vectors):
            weights.append(np.eye(n)[i])

        optimal_solutions = [
            self._optimal_solution(
                weighted_cost_vectors=[(c, w) for c, w in zip(cost_vectors, w.astype(float))],
                use_individual_limits=False
            ) for w in weights
        ]
        for solution, w in zip(optimal_solutions, weights):
            if solution is None:
                _LOGGER.warning(f'No optimal solution found for weight {w}.')
        if any([s is None for s in optimal_solutions]):
            return []

        min_recipe_cost = np.dot(cost_vectors.recipe_cost_vector.vector,
                                 optimal_solutions[cost_vectors.recipe_index].recipe_vector)
        max_eu_per_tick = np.dot(cost_vectors.eu_cost_vector.vector,
                                 optimal_solutions[cost_vectors.recipe_index].recipe_vector)
        max_machines = np.dot(cost_vectors.machine_amount_cost_vector.vector,
                              optimal_solutions[cost_vectors.recipe_index].recipe_vector)

        _LOGGER.info(f'Min Recipe Cost: {min_recipe_cost}, Max EU/t: {max_eu_per_tick}, Max Machines: {max_machines}')

        optimal_solution_costs = [
            (s, w, [np.dot(c.normalized_vector, s.recipe_vector) for c in cost_vectors],
             self.get_eu_per_tick(s), self.get_machine_amount(s))
            for s, w in zip(optimal_solutions, weights)
        ]
        _LOGGER.info(f'Optimal solution costs for different weights:')
        for _, w, costs, eu_per_tick, machine_amount in optimal_solution_costs:
            _LOGGER.info(f'  Weights: {w}, Costs: {costs}, EU/t: {eu_per_tick}, Machine Amount: {machine_amount}')

        eu_per_tick_constraints = np.linspace(0.4 * max_eu_per_tick, max_eu_per_tick, num=4).tolist()
        machine_amount_constraints = np.linspace(0.3 * max_machines, max_machines, num=4).tolist()
        constraint_list = [
            CostConstraints(eu_per_tick_constraint=max_eu, machine_amount_constraint=max_machines)
            for max_eu, max_machines in product(eu_per_tick_constraints, machine_amount_constraints)
        ]

        _LOGGER.info(f'Sampling Pareto front...')
        pareto_solutions = [
            self._optimal_solution(
                weighted_cost_vectors=cost_vectors.standard_weighting(),
                use_individual_limits=False,
                eu_per_tick_constraint=constraints.eu_per_tick_constraint,
                machine_amount_constraint=constraints.machine_amount_constraint
            ) for constraints in constraint_list
        ]
        for s, constraints in zip(pareto_solutions, constraint_list):
            if s is None:
                _LOGGER.warning(f'No pareto solution found for {constraints}.')
        pareto_solution_costs = [
            (s, constraints, [np.dot(c.vector, s.recipe_vector) for c in cost_vectors],
             self.get_eu_per_tick(s), self.get_machine_amount(s))
            for s, constraints in zip(pareto_solutions, constraint_list)
            if s is not None
        ]
        _LOGGER.info(f'Optimal solution costs for different weights:')
        for _, constraints, costs, eu_per_tick, machine_amount in pareto_solution_costs:
            _LOGGER.info(f'  {constraints}, Non-normalized Costs: {costs}, '
                         f'EU/t: {eu_per_tick}, Machine Amount: {machine_amount}')

        pareto_results = [
            (s, constraints) for s, constraints in zip(pareto_solutions, constraint_list) if s is not None
        ]
        return pareto_results

    def get_machine_amount(self, solution: OptimalSolution) -> float:
        return np.sum(np.ceil(np.array([
            a * r.processing_time / self.time if r.positive_processing_time() else (1 if a > 0 else 0)
            for r, a in zip(self.recipes, solution.recipe_vector[:self.q])
        ])))

    def get_eu_per_tick(self, solution: OptimalSolution) -> float:
        return np.sum(np.array([
            -r.eu_per_tick * a for r, a in zip(self.recipes, solution.recipe_vector[:self.q])
        ]))

    def _optimal_solution(
        self,
        weighted_cost_vectors: list[tuple[CostVector, float]],
        use_individual_limits: bool = False,
        eu_per_tick_constraint: float | None = None,
        machine_amount_constraint: float | None = None
    ) -> OptimalSolution | None:
        """
        :param weighted_cost_vectors:
        :param use_individual_limits: If True, add additional constraints to limit the number of machines for each recipe
        :return:
        """
        _LOGGER.info(f'Calling _optimal_solution with weighted_cost_vectors: {weighted_cost_vectors}, '
                     f'eu_per_tick_constraint: {eu_per_tick_constraint}, '
                     f'machine_amount_constraint: {machine_amount_constraint}')
        cost_vector = np.zeros(shape=(self.q + self.r,), dtype=np.float64)
        if weighted_cost_vectors:
            for c, w in weighted_cost_vectors:
                cost_vector += c.normalized_vector * w
            cost_vector /= np.mean(np.abs(cost_vector))
        else:
            _LOGGER.warning('No cost vectors provided, defaulting to zero cost vector '
                            '(will find any feasible solution).')

        eu_cost_vector = [c for c, _ in weighted_cost_vectors if c.name == 'EU Cost Vector'][0]
        machine_amount_cost_vector = [c for c, _ in weighted_cost_vectors if c.name == 'Machine Amount Cost Vector'][0]

        # for r, c in (list(zip(self.recipes[:self.q], cost_vector[:self.q])) +
        #              list(zip(self.infinite_material_list, cost_vector[self.q:]))):
        #     if c > 0:
        #         _LOGGER.info(f'Positive cost for recipe {r}: {c}')
        #     elif c < 0:
        #         _LOGGER.info(f'Negative cost for recipe {r}: {c}')

        lb = np.zeros(shape=(self.q + self.r,))
        ub = np.array([
            self.machine_amount_cap(recipe, self.time, use_individual_limits) for recipe in self.recipes
        ])
        ub = np.concatenate([ub, np.full(self.r, np.inf)])

        A_mat = self.total_recipe_matrix[[self.index_by_material[m] for m in self.materials if m not in self.inputs]]
        b_mat = np.zeros((A_mat.shape[0],))
        A_lb = self.total_recipe_matrix[[self.index_by_material[m] for m in self.lower_bounds.keys()]]
        b_lb = np.array([b for m, b in self.lower_bounds.items()])
        A_ub = self.total_recipe_matrix[[self.index_by_material[m] for m in self.upper_bounds.keys()]]
        b_ub = np.array([b for m, b in self.upper_bounds.items()])
        A_eq = self.total_recipe_matrix[[self.index_by_material[m] for m in self.equalities.keys()]]
        b_eq = np.array([a for m, a in self.equalities.items()])

        # Combine constraints
        A = vstack(
            [A_mat, A_lb, A_ub, A_eq, eu_cost_vector.vector, machine_amount_cost_vector.vector]
        ).tocsr()
        b_lower = np.concatenate(
            [b_mat, b_lb, np.full_like(b_ub, -np.inf), b_eq, -np.full((1,), np.inf), np.zeros(1)]
        )
        eu_per_tick_ub = np.array([eu_per_tick_constraint]) if eu_per_tick_constraint is not None \
            else np.full((1,), np.inf)
        machine_amount_ub = np.array([min(machine_amount_constraint, self.config.machine_limit)]) \
            if machine_amount_constraint is not None else np.full((1,), self.config.machine_limit)
        b_upper = np.concatenate(
            [np.full_like(b_mat, np.inf), np.full_like(b_lb, np.inf), b_ub, b_eq, eu_per_tick_ub, machine_amount_ub]
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
        # highs_solver.print_solution_statistics(solution, self.total_recipe_matrix, cost_vector)
        last_optimal_value = float(highs_solver.optimal_value)

        """
            -------------------------- Machine amount reduction --------------------------
        """

        delta = 0  # 10 * abs(last_optimal_value)
        c1 = np.array(
            [r.processing_time / self.time if r.positive_processing_time() else 1 / self.time for r in self.recipes]
        )
        c2 = np.zeros(shape=(self.r,))
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
        cost_indices = np.arange(self.q + self.r, dtype=np.int32)
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
        # highs_solver.print_solution_statistics(solution, self.total_recipe_matrix, cost_vector)
        # for c, _ in weighted_cost_vectors:
        #     _LOGGER.info(f'Non-normalized cost for {c.name}: {np.dot(c.vector, solution)}')
        last_optimal_value = float(highs_solver.optimal_value)

        return OptimalSolution(
            recipe_vector=solution, optimal_cost=last_optimal_value
        )

    def _optimal_crafting_chain(
        self,
        weighted_cost_vectors: list[tuple[CostVector, float]],
        use_individual_limits: bool = False,
        eu_per_tick_constraint: float | None = None,
        machine_amount_constraint: float | None = None
    ) -> CraftingChain | None:
        """
        :param weighted_cost_vectors:
        :param use_individual_limits: If True, add additional constraints to limit the number of machines for each recipe
        :return:
        """
        with Timer('_optimal_crafting_chain', active=True):
            optimal_solution = self._optimal_solution(
                weighted_cost_vectors, use_individual_limits=use_individual_limits,
                eu_per_tick_constraint=eu_per_tick_constraint, machine_amount_constraint=machine_amount_constraint
            )
            if optimal_solution is None:
                return None

            recipe_vector = optimal_solution.recipe_vector
            recipe_amounts = {r: a for r, a in zip(self.recipes, recipe_vector[:self.q]) if a != 0}
            material_vector = self.total_recipe_matrix @ recipe_vector
            material_amounts = {m: a for m, a in zip(self.materials, material_vector)}
            # for i, x in enumerate(recipe_vector[:q]):
            #     if not np.isinf(ub[i]) and x >= ub[i]:
            #         _LOGGER.warning(f'Machine Limit reached for recipe {recipes[i]}: {x} = {ub[i]}')

            crafting_chain = CraftingChain(
                recipe_amounts=recipe_amounts,
                total_material_needs=material_amounts,
                input_materials=self.inputs,
                infinite_materials=set(self.infinite_material_list),
                time=self.time
            )
            return crafting_chain

    def machine_amount_cap(self, recipe: Recipe, time: float, use_individual_limits: bool) -> float:
        if use_individual_limits and recipe.cap is not None and recipe.positive_processing_time():
            return min(recipe.cap * time / recipe.processing_time, self.machine_limit * time / recipe.processing_time)
        return np.inf


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
            self, recipe_vector: np.ndarray, total_recipe_matrix: csr_matrix, cost_vector: np.ndarray) -> None:
        _LOGGER.info(f'Solution statistics for HiGHS solver {self.name}:')
        material_vector = total_recipe_matrix @ recipe_vector
        # _LOGGER.info(f'Non zeros: {np.sum(recipe_vector != 0)}')
        # _LOGGER.info(f'MinMax: {np.min(np.abs(recipe_vector))}, {np.max(np.abs(recipe_vector))}')
        # _LOGGER.info(f'Positive materials: {np.sum(material_vector > 0)}')
        # _LOGGER.info(f'Negative materials: {np.sum(material_vector < 0)}')
        _LOGGER.info(f'Optimal (material) cost: {cost_vector @ recipe_vector}')

    @property
    def optimal_value(self) -> float:
        return self.highs.getObjectiveValue()
