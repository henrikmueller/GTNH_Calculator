from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Iterable
import numpy as np
import logging
from frozendict import frozendict
from scipy.sparse import hstack, vstack, csr_matrix

from .crafting_chain_problem import (
    CraftingChainProblem, ContinuousCraftingChainProblem, MixedIntegerCraftingChainProblem, CostVectorType,
    GTNHConstraints, GTNHSupport, DeterminedSolution
)
from ..recipes_db.material import Material
from ..recipes_db.instantiated_recipes import InstantiatedRecipe
from ..recipes_db.voltage_tiers import VoltageTier
from ..utility.general_utility import time_to_seconds
from ..optimization.optimization_problem import (
    CostVector, MultiObjectiveMixedIntegerLinearProblem, SolutionSpace,
    HighsSolver, SolutionVector, Support
)
from ..configs.crafting_chain_config_db import CraftingChainConfig
from ..crafting_chains.crafting_chain_db import CraftingChain
from ..utility.constants import FLUID_WEIGHT_FACTOR
from ..utility.general_utility import Timer

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass(frozen=True)
class SolutionCalculationResult:
    determined_solutions: list[DeterminedSolution]
    response: str
    expected_solutions: int = 1

    def __post_init__(self) -> None:
        if self.expected_solutions < 1:
            raise ValueError("Expected solutions must be at least 1.")

    def pick_solution(self, index: int | None = None) -> DeterminedSolution:
        return self.determined_solutions[0 if index is None else index]

    @property
    def success(self) -> bool:
        return len(self.determined_solutions) == self.expected_solutions


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


class CraftingChainFinder:
    machine_limit: int
    use_individual_limits: bool
    materials: list[Material]
    recipes: list[InstantiatedRecipe]
    infinite_material_list: list[Material]
    index_by_material: Dict[Material, int]
    p: int
    q: int
    r: int
    zero_weight_infinites: set[Material]
    is_zero_weight_infinite: Dict[Material, bool]
    config: CraftingChainConfig
    time: float
    total_recipe_matrix: csr_matrix
    constraint_matrix: csr_matrix
    continuous_problem: ContinuousCraftingChainProblem
    mixed_integer_problem: MixedIntegerCraftingChainProblem

    def __init__(
        self, 
        instantiated_recipes: list[InstantiatedRecipe], 
        materials: list[Material],
        config: CraftingChainConfig,
        machine_limit: int, use_individual_limits: bool = True
    ):
        self.machine_limit = machine_limit
        self.use_individual_limits = use_individual_limits
        self.materials = materials
        self.index_by_material = {m: i for i, m in enumerate(self.materials)}
        self.recipes = instantiated_recipes
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
        rows_constraints, cols_constraints, data_constraints = [], [], []
        for i, recipe in enumerate(self.recipes):
            for material, amount in recipe.material_dict.items():
                if amount == 0:
                    continue
                cols.append(i)
                rows.append(self.index_by_material[material])
                data.append(amount)
                if self.is_zero_weight_infinite[material] and amount > 0:
                    continue
                cols_constraints.append(i)
                rows_constraints.append(self.index_by_material[material])
                data_constraints.append(amount)
        recipe_matrix = csr_matrix((data, (rows, cols)), shape=(self.p, self.q))
        constraint_matrix = csr_matrix((data_constraints, (rows_constraints, cols_constraints)), shape=(self.p, self.q))

        # Infinite Production Matrix
        infinite_material_list = list(config.infinite_materials)
        self.infinite_material_list = infinite_material_list
        self.r = len(self.infinite_material_list)
        rows, cols, data = [], [], []
        for i, material in enumerate(self.infinite_material_list):
            cols.append(i)
            rows.append(self.index_by_material[material])
            data.append(1)
        infinite_production_matrix = csr_matrix((data, (rows, cols)), shape=(self.p, self.r))
        self.total_recipe_matrix = csr_matrix(hstack([recipe_matrix, infinite_production_matrix]))
        self.constraint_matrix = csr_matrix(hstack([constraint_matrix, infinite_production_matrix]))

        cost_vectors = frozendict({
            CostVectorType.RECIPE_COST_VECTOR: self._get_recipe_cost_vector(),
            CostVectorType.EU_COST_VECTOR: self._get_eu_cost_vector(),
            CostVectorType.MACHINE_AMOUNT_COST_VECTOR: self._get_machine_amount_cost_vector()
        })
        self.continuous_problem = self.get_continuous_problem(
            cost_vectors=cost_vectors,
            use_individual_limits=self.use_individual_limits
        )
        self.mixed_integer_problem = self.get_mixed_integer_problem(self.continuous_problem)

    # -----------------------------------------------------------------------------------------------------------------
    # Basic properties
    # -----------------------------------------------------------------------------------------------------------------

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
    
    # -----------------------------------------------------------------------------------------------------------------
    # Cost vectors
    # -----------------------------------------------------------------------------------------------------------------

    def _get_recipe_cost_vector(self) -> CostVector:
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
        cost_vector = - (c @ self.constraint_matrix) + infinite_production_weights
        _LOGGER.debug(f'MinMax cost_vector: {np.min(np.abs(cost_vector))}, {np.max(np.abs(cost_vector))}')
        _LOGGER.debug(f'Nan in Max cost_vector: {np.isnan(cost_vector).sum()}')
        _LOGGER.debug(f'Number of positive cost values: {np.sum(cost_vector > 0)}')
        _LOGGER.debug(f'Number of negative cost values: {np.sum(cost_vector < 0)}')
        estimation = np.abs(cost_vector[cost_vector != 0]).mean()
        return CostVector(
            vector=-cost_vector, 
            normalization_scalar=estimation,
            minimize=False
        )

    def _get_eu_cost_vector(self) -> CostVector:
        eu_cost_vector = np.array([r.total_eu for r in self.recipes])
        eu_cost_vector = - np.concatenate([eu_cost_vector, np.zeros(self.r)])
        _LOGGER.debug(f'MinMax eu_cost_vector: {np.min(np.abs(eu_cost_vector))}, {np.max(np.abs(eu_cost_vector))}')
        _LOGGER.debug(f'Nan in Max eu_cost_vector: {np.isnan(eu_cost_vector).sum()}')
        _LOGGER.debug(f'Number of positive cost values: {np.sum(eu_cost_vector > 0)}')
        _LOGGER.debug(f'Number of negative cost values: {np.sum(eu_cost_vector < 0)}')
        estimation = VoltageTier.eu_per_tick(self.config.max_voltage_tier) * 20 * self.time
        return CostVector(
            vector=eu_cost_vector, 
            normalization_scalar=estimation,
            minimize=True
        )

    def _get_machine_amount_cost_vector(self) -> CostVector:
        c1 = np.array(
            [r.processing_time / self.time if r.positive_processing_time() else 1 / self.time for r in self.recipes]
        )
        c2 = np.zeros(shape=(self.r,))
        cost_vector = np.concatenate([c1, c2])
        _LOGGER.debug(f'MinMax machine_amount_cost_vector: {np.min(np.abs(cost_vector))}, {np.max(np.abs(cost_vector))}')
        _LOGGER.debug(f'Nan in Max machine_amount_cost_vector: {np.isnan(cost_vector).sum()}')
        _LOGGER.debug(f'Number of positive cost values: {np.sum(cost_vector > 0)}')
        _LOGGER.debug(f'Number of negative cost values: {np.sum(cost_vector < 0)}')
        estimation = 0.5 * self.config.machine_limit
        return CostVector(
            vector=cost_vector, 
            normalization_scalar=estimation,
            minimize=True
        )

    def get_default_cost_vectors(self) -> frozendict[str, CostVector]:
        return frozendict({
            CostVectorType.RECIPE_COST_VECTOR: self._get_recipe_cost_vector(),
            CostVectorType.EU_COST_VECTOR: self._get_eu_cost_vector(),
            CostVectorType.MACHINE_AMOUNT_COST_VECTOR: self._get_machine_amount_cost_vector()
        })

    def get_default_bounds(self, default_solutions: Iterable[DeterminedSolution]) -> frozendict[CostVectorType, float]:
        recipe_costs = []
        eu_per_tick = []
        machine_amount = []
        for default_solution in default_solutions:
            recipe_costs.append(default_solution.optimal_costs[CostVectorType.RECIPE_COST_VECTOR])
            eu_per_tick.append(default_solution.optimal_costs[CostVectorType.EU_COST_VECTOR])
            machine_amount.append(default_solution.optimal_costs[CostVectorType.MACHINE_AMOUNT_COST_VECTOR])

        default_bounds = {
            CostVectorType.RECIPE_COST_VECTOR: min(recipe_costs) / 2,
            CostVectorType.EU_COST_VECTOR: max(eu_per_tick),
            CostVectorType.MACHINE_AMOUNT_COST_VECTOR: max(machine_amount)
        }
        return frozendict(default_bounds)

    # -----------------------------------------------------------------------------------------------------------------
    # Creation of GTNHSupports
    # -----------------------------------------------------------------------------------------------------------------

    def _create_support(self, support_array: np.ndarray) -> GTNHSupport:
        if np.max(support_array) >= self.q + self.r or np.min(support_array) < 0:
            raise ValueError(f"Support array values must be in the range [0, {self.q + self.r - 1}]")
        return GTNHSupport(support_array.astype(np.int32))

    def _create_support_from_enabled_recipes(self, enabled_recipe_ids: set[str]) -> GTNHSupport:
        support = self._create_support(np.concatenate([
            np.array([i for i, r in enumerate(self.recipes) if r.id in enabled_recipe_ids], dtype=np.int32),
            np.arange(self.mixed_integer_problem.q, self.mixed_integer_problem.q + self.mixed_integer_problem.r, dtype=np.int32)
        ]))
        _LOGGER.info(f'Determined support size: {support.size} out of {self.continuous_problem.problem.num_variables} variables.')
        return support
    
    @property
    def full_support(self) -> GTNHSupport:
        return self._create_support(np.arange(self.q + self.r, dtype=np.int32))

    # -----------------------------------------------------------------------------------------------------------------
    # Calculation of optimization problems
    # -----------------------------------------------------------------------------------------------------------------

    def machine_amount_cap(self, recipe: InstantiatedRecipe, use_individual_limits: bool) -> float:
        if use_individual_limits and recipe.cap is not None and recipe.positive_processing_time():
            return min(recipe.cap * self.time / recipe.processing_time, self.machine_limit * self.time / recipe.processing_time)
        return np.inf
    
    def get_continuous_problem(
        self,
        cost_vectors: frozendict[str, CostVector],
        use_individual_limits: bool = False,
    ) -> ContinuousCraftingChainProblem:
        lb = np.zeros(shape=(self.q + self.r,))
        ub = np.array([
            self.machine_amount_cap(recipe, use_individual_limits) for recipe in self.recipes
        ])
        ub = np.concatenate([ub, np.full(self.r, np.inf)])

        A_mat = self.constraint_matrix[[self.index_by_material[m] for m in self.materials if m not in self.inputs]]
        constraint_info = [f"Material {m}" for m in self.materials if m not in self.inputs]
        b_mat = np.zeros((A_mat.shape[0],))
        A_lb = self.constraint_matrix[[self.index_by_material[m] for m in self.lower_bounds.keys()]]
        constraint_info += [f"{m} >= {b}" for m, b in self.lower_bounds.items()]
        b_lb = np.array([b for m, b in self.lower_bounds.items()])
        A_ub = self.constraint_matrix[[self.index_by_material[m] for m in self.upper_bounds.keys()]]
        constraint_info += [f"{m} <= {b}" for m, b in self.upper_bounds.items()]
        b_ub = np.array([b for m, b in self.upper_bounds.items()])
        A_eq = self.constraint_matrix[[self.index_by_material[m] for m in self.equalities.keys()]]
        constraint_info += [f"{m} = {a}" for m, a in self.equalities.items()]
        b_eq = np.array([a for m, a in self.equalities.items()])

        # Combine constraints
        A = csr_matrix(vstack(
            [A_mat, A_lb, A_ub, A_eq, cost_vectors[CostVectorType.MACHINE_AMOUNT_COST_VECTOR].vector]
        ))
        constraint_info += ["Machine amount constraint"]
        b_lower = np.concatenate(
            [b_mat, b_lb, np.full_like(b_ub, -np.inf), b_eq, np.zeros(1)]
        )
        machine_amount_ub = np.full((1,), self.config.machine_limit)
        b_upper = np.concatenate(
            [np.full_like(b_mat, np.inf), np.full_like(b_lb, np.inf), b_ub, b_eq, machine_amount_ub]
        )
        b = np.vstack([b_lower, b_upper])

        solution_space = SolutionSpace(
            constraint_matrix=A,
            constraint_bounds=b,
            lower_bounds=lb,
            upper_bounds=ub,
            integer_indices=np.array([], dtype=np.int32)
        )
        optimization_problem = MultiObjectiveMixedIntegerLinearProblem(
            cost_vectors=cost_vectors,
            solution_space=solution_space
        )
        return ContinuousCraftingChainProblem.create(
            problem=optimization_problem,
            recipes=self.recipes,
            infinite_material_list=self.infinite_material_list,
            constraint_info=tuple(constraint_info)
        )

    def get_mixed_integer_problem(
        self,
        continuous_problem: ContinuousCraftingChainProblem,
        machine_limit: int | None = None,
    ) -> MixedIntegerCraftingChainProblem:
        multiple_objective_problem = continuous_problem.problem
        num_variables = multiple_objective_problem.num_variables
        num_constraints = multiple_objective_problem.solution_space.num_constraints
        rows, cols, data = [], [], []
        constraint_info = list(continuous_problem.constraint_info)
        for i, recipe_index in enumerate(range(continuous_problem.q)):
            cols.append(i)
            rows.append(i)
            recipe = continuous_problem.recipes[recipe_index]
            data.append(-recipe.processing_time / self.time if recipe.positive_processing_time() else -1)
            cols.append(num_variables + i)
            rows.append(i)
            data.append(1)
            constraint_info.append(f"Integer machine amount for {recipe}")
        new_constraints = csr_matrix((data, (rows, cols)), shape=(continuous_problem.q, 2 * num_variables))
        constraint_matrix = multiple_objective_problem.solution_space.constraint_matrix
        constraint_matrix = csr_matrix(
            hstack([constraint_matrix, csr_matrix((num_constraints, num_variables), dtype=constraint_matrix.dtype)])
        )
        machine_amount_constraint = np.hstack([
            np.zeros((num_variables,)),
            np.ones((continuous_problem.q,)),
            np.zeros((continuous_problem.r,))
        ])
        constraint_info.append("Machine amount constraint")
        constraint_matrix = csr_matrix(
            vstack([constraint_matrix, new_constraints, csr_matrix(machine_amount_constraint)], dtype=constraint_matrix.dtype)
        )
        constraint_bounds = np.vstack([
            np.zeros((continuous_problem.q,)),
            np.full((continuous_problem.q,), np.inf)
        ])
        machine_limit = self.config.machine_limit if machine_limit is None else machine_limit
        constraint_bounds = np.hstack([
            multiple_objective_problem.solution_space.constraint_bounds, 
            constraint_bounds, 
            np.array([[0], [machine_limit]])
        ])
        lower_bounds = np.hstack([multiple_objective_problem.solution_space.lower_bounds, np.zeros((num_variables,))])
        upper_bounds = np.hstack([multiple_objective_problem.solution_space.upper_bounds, np.full((num_variables,), np.inf)])
        solution_space = SolutionSpace(
            constraint_matrix=constraint_matrix,
            constraint_bounds=constraint_bounds,
            lower_bounds=lower_bounds,
            upper_bounds=upper_bounds,
            integer_indices=np.arange(start=num_variables, stop=2*num_variables, dtype=np.int32)
        )
        recipe_cost_vector = multiple_objective_problem.cost_vectors[CostVectorType.RECIPE_COST_VECTOR].append(np.zeros((num_variables,)))
        eu_cost_vector = multiple_objective_problem.cost_vectors[CostVectorType.EU_COST_VECTOR].append(np.zeros((num_variables,)))
        machine_amount_cost_vector = CostVector(
            vector=machine_amount_constraint,
            normalization_scalar=1.0,
            minimize=True
        )

        mixed_problem = MultiObjectiveMixedIntegerLinearProblem(
            solution_space=solution_space,
            cost_vectors=frozendict({
                CostVectorType.RECIPE_COST_VECTOR: recipe_cost_vector,
                CostVectorType.EU_COST_VECTOR: eu_cost_vector,
                CostVectorType.MACHINE_AMOUNT_COST_VECTOR: machine_amount_cost_vector
            })
        )
        return MixedIntegerCraftingChainProblem.create(
            problem=mixed_problem,
            recipes=continuous_problem.recipes,
            infinite_material_list=continuous_problem.infinite_material_list,
            constraint_info=tuple(constraint_info)
        )

    def restrict_to_support_continuous(
        self, support: GTNHSupport
    ) -> ContinuousCraftingChainProblem:
        restricted_recipes = [self.recipes[i] for i in support if i < self.q]
        restricted_infinite_material_list = [self.infinite_material_list[i - self.q] for i in support if i >= self.q]
        restricted_problem = self.continuous_problem.problem.restrict_to_support(support)
        _LOGGER.debug(
            f'Restricted solution space: {self.continuous_problem.problem.solution_space.constraint_matrix.shape} '
            f'to {restricted_problem.solution_space.constraint_matrix.shape}'
        )
        return ContinuousCraftingChainProblem.create(
            problem=restricted_problem,
            recipes=restricted_recipes,
            infinite_material_list=restricted_infinite_material_list,
            constraint_info=self.continuous_problem.constraint_info
        )

    def restrict_to_support_mixed(
        self, support: GTNHSupport
    ) -> MixedIntegerCraftingChainProblem:
        # _LOGGER.info(f"self.q={self.q}, self.r={self.r}")
        # _LOGGER.info(f"support={support.tolist()}. Length={len(support)}")
        restricted_recipes = [self.recipes[i] for i in support if i < self.q]
        restricted_infinite_material_list = [
            self.infinite_material_list[i - self.q] for i in support if self.q + self.r > i >= self.q
        ]
        extended_support = Support(np.concatenate([support, self.q + self.r + support]))
        restricted_problem = self.mixed_integer_problem.problem.restrict_to_support(extended_support)
        _LOGGER.debug(
            f'Restricted solution space: {self.mixed_integer_problem.problem.solution_space.constraint_matrix.shape} '
            f'to {restricted_problem.solution_space.constraint_matrix.shape}'
        )
        return MixedIntegerCraftingChainProblem.create(
            problem=restricted_problem,
            recipes=restricted_recipes,
            infinite_material_list=restricted_infinite_material_list,
            constraint_info=self.mixed_integer_problem.constraint_info
        )

    # -----------------------------------------------------------------------------------------------------------------
    # Pipeline for crafting chain calculation from optimization results
    # -----------------------------------------------------------------------------------------------------------------

    def _get_recipe_vector(self, determined_solution: DeterminedSolution) -> SolutionVector:
        recipe_vector = determined_solution.solution_vector.vector
        if not determined_solution.integer_machine_amounts:
            return SolutionVector(vector=recipe_vector)
        
        half_size = determined_solution.used_support.size
        if recipe_vector.size != 2 * determined_solution.used_support.size:
            raise ValueError(f"Expected recipe_vector size to be {2 * half_size}, got {recipe_vector.size}")
        
        recipe_vector = recipe_vector[:half_size]
        result = np.zeros((self.q + self.r,), dtype=recipe_vector.dtype)
        result[determined_solution.used_support] = recipe_vector
        return SolutionVector(vector=result)

    def _recipe_cost_from_recipe_vector(self, recipe_vector: SolutionVector) -> float:
        recipe_cost_vector = self.continuous_problem.cost_vectors[CostVectorType.RECIPE_COST_VECTOR]
        return recipe_vector.cost(recipe_cost_vector, normalize=False)

    def _eu_from_recipe_vector(self, recipe_vector: SolutionVector) -> float:
        eu_cost_vector = self.continuous_problem.cost_vectors[CostVectorType.EU_COST_VECTOR]
        return recipe_vector.cost(eu_cost_vector, normalize=False)

    def _machine_amount_from_recipe_vector(self, recipe_vector: SolutionVector) -> float:
        machine_amount_cost_vector = self.continuous_problem.cost_vectors[CostVectorType.MACHINE_AMOUNT_COST_VECTOR]
        return np.sum(np.ceil(recipe_vector.vector[:self.q] * machine_amount_cost_vector.vector[:self.q]))

    def _all_costs_from_full_recipe_vector(
        self, recipe_vector: SolutionVector
    ) -> frozendict[CostVectorType, float]:
        if recipe_vector.size != self.q + self.r:
            raise ValueError(f"Expected recipe_vector size to be {self.q + self.r}, got {recipe_vector.size}")
        
        recipe_cost = self._recipe_cost_from_recipe_vector(recipe_vector)
        eu_per_tick = self._eu_from_recipe_vector(recipe_vector)
        machine_amounts = self._machine_amount_from_recipe_vector(recipe_vector)
        return frozendict({
            CostVectorType.RECIPE_COST_VECTOR: recipe_cost,
            CostVectorType.EU_COST_VECTOR: eu_per_tick,
            CostVectorType.MACHINE_AMOUNT_COST_VECTOR: machine_amounts
        })

    def _all_costs_from_partial_solution(
        self, recipe_vector: SolutionVector, crafting_chain_problem: CraftingChainProblem
    ) -> frozendict[CostVectorType, float]:
        if recipe_vector.size != crafting_chain_problem.number_of_variables:
            raise ValueError(f"Expected recipe_vector size to be {crafting_chain_problem.number_of_variables}, got {recipe_vector.size}")
        recipe_cost = recipe_vector.cost(crafting_chain_problem.cost_vectors[CostVectorType.RECIPE_COST_VECTOR])
        eu_per_tick = recipe_vector.cost(crafting_chain_problem.cost_vectors[CostVectorType.EU_COST_VECTOR])
        machine_amounts = recipe_vector.cost(crafting_chain_problem.cost_vectors[CostVectorType.MACHINE_AMOUNT_COST_VECTOR])
        return frozendict({
            CostVectorType.RECIPE_COST_VECTOR: recipe_cost,
            CostVectorType.EU_COST_VECTOR: eu_per_tick,
            CostVectorType.MACHINE_AMOUNT_COST_VECTOR: machine_amounts
        })

    def _linear_to_mixed_integer_solution(self, linear_solution: SolutionVector) -> SolutionVector:
        machine_amounts = np.ceil([
            x * (self.recipes[i].processing_time / self.time if self.recipes[i].positive_processing_time() else 1) 
            for i, x in enumerate(linear_solution.vector[:self.q])
        ], dtype=linear_solution.vector.dtype)
        mixed_solution = np.concatenate([
            linear_solution.vector,
            machine_amounts,
            np.zeros((self.r,), dtype=linear_solution.vector.dtype)
        ])
        return SolutionVector(vector=mixed_solution)

    def _is_contained_in_solution_space(self, point: np.ndarray, crafting_chain_problem: CraftingChainProblem) -> bool:
        def get_recipe_info(index: int) -> str:
            if index >= self.q + self.r:
                index = index - (self.q + self.r)
            if index < self.q:
                return f"Recipe: {self.recipes[index]}"
            if index < self.q + self.r:
                return f"Infinite Material: {self.infinite_material_list[index - self.q]}"
            raise ValueError(f"Index {index} is out of bounds for recipe info retrieval. q = {self.q}, r = {self.r}")

        solution_space = crafting_chain_problem.problem.solution_space
        if point.size != solution_space.num_variables:
            raise ValueError(f"Point must have size {solution_space.num_variables} but has size {point.size}")
        contains = True
        if np.any(point < solution_space.lower_bounds):
            indices = np.flatnonzero(point < solution_space.lower_bounds)
            # TODO: Write debugging for constraint violations: Which materials are in it
            for i in indices:
                _LOGGER.info(f'Point is below the lower bounds: {point[i]} < {solution_space.lower_bounds[i]} (recipe: {get_recipe_info(i)})')
            contains = False
        if np.any(point > solution_space.upper_bounds):
            indices = np.flatnonzero(point > solution_space.upper_bounds)
            for i in indices:
                _LOGGER.info(f'Point is above the upper bounds: {point[i]} > {solution_space.upper_bounds[i]} (recipe: {get_recipe_info(i)})')
            contains = False
        constraint_values = solution_space.constraint_matrix @ point
        if np.any(constraint_values < solution_space.lower_constraint_bounds):
            indices = np.flatnonzero(constraint_values < solution_space.lower_constraint_bounds)
            for i in indices:
                _LOGGER.info(
                    f'Point violates lower constraint bounds: {constraint_values[i]} < {solution_space.lower_constraint_bounds[i]} '
                    f'(constraint {crafting_chain_problem.constraint_info[i]})'
                )
            contains = False
        if np.any(constraint_values > solution_space.upper_constraint_bounds):
            indices = np.flatnonzero(constraint_values > solution_space.upper_constraint_bounds)
            for i in indices:
                _LOGGER.info(
                    f'Point violates upper constraint bounds: {constraint_values[i]} > {solution_space.upper_constraint_bounds[i]} '
                    f'(constraint {crafting_chain_problem.constraint_info[i]})'
                )
            contains = False
        integer_values = point[solution_space.integer_indices]
        if np.any(np.abs(np.rint(integer_values) - integer_values) > 1e-8):
            indices = np.flatnonzero(np.abs(np.rint(integer_values) - integer_values) > 1e-8)
            for i in indices:
                _LOGGER.info(f'Point violates integer constraints: {integer_values[i]} is not an integer (recipe: {get_recipe_info(int(solution_space.integer_indices[i]))})')
            contains = False
        return contains

    def _determine_solution_vector(
        self,
        crafting_chain_problem: CraftingChainProblem,
        cost_vector_type: CostVectorType,
        support: GTNHSupport | None = None,
        cost_constraints: GTNHConstraints = frozendict(),
        log: bool = False
    ) -> SolutionVector | None:
        with Timer('determine_solution_vector', active=True):
            highs_solver = HighsSolver(time_limit=60.0)
            linear_problem = crafting_chain_problem.problem.get_mixed_integer_linear_problem(
                cost_vector_type, 
                epsilon_constraints=frozendict({t: v for t, v in cost_constraints.items()})
            )
            _LOGGER.info(f'LP: {linear_problem.problem_statistics_string()}')
            optimal_solution = highs_solver.solve(linear_problem)

            if optimal_solution is None:
                _LOGGER.warning('No solution found for the linear problem.')
                return None
            optimal_cost = optimal_solution.cost(linear_problem.cost_vector, normalize=False)

            if log:
                if support is not None:
                    determined_solution = DeterminedSolution(
                        name='Test Solution',
                        used_support=support,
                        cost_vector_type=CostVectorType.RECIPE_COST_VECTOR,
                        optimal_costs=frozendict({CostVectorType.RECIPE_COST_VECTOR: optimal_cost}),
                        cost_constraints=cost_constraints,
                        solution_vector=optimal_solution,
                        integer_machine_amounts=True,
                        number_of_recipes=crafting_chain_problem.number_of_recipes
                    )
                    recipe_vector = self._get_recipe_vector(determined_solution).vector
                    _LOGGER.info(f'Valid for global problem: {self._is_contained_in_solution_space(recipe_vector, self.continuous_problem)}')
                    _LOGGER.info(f'Global cost: {np.dot(self.continuous_problem.problem.cost_vectors[CostVectorType.RECIPE_COST_VECTOR].vector, recipe_vector)}')

                machine_amount_cost_vector = crafting_chain_problem.problem.cost_vectors[CostVectorType.MACHINE_AMOUNT_COST_VECTOR].vector
                machine_amount = crafting_chain_problem.get_continuous_machine_amount(optimal_solution)
                machine_amount_int = crafting_chain_problem.get_machine_amount(optimal_solution)
                _LOGGER.info(f'Max Material Weight Solution:')
                _LOGGER.info(f'Recipe vector: {optimal_solution.vector}')
                _LOGGER.info(f'Optimal machine amount: {machine_amount}')
                _LOGGER.info(f'Optimal integer machine amount: {machine_amount_int}')
                _LOGGER.info(f'Machine amount constraint: {machine_amount_cost_vector}')
                _LOGGER.info(f'Number of non-zero recipes: {crafting_chain_problem.get_non_zero_recipe_count(optimal_solution)} out of {crafting_chain_problem.number_of_recipes}')
                _LOGGER.info(f'LP cost vector: {linear_problem.cost_vector.vector}')
                _LOGGER.info(f'LP cost vector number of non-zero entries: {np.count_nonzero(linear_problem.cost_vector.vector)}')
                _LOGGER.info(f'LP optimal cost (non-normalized): {optimal_cost}')

            optimal_cost_constraint = linear_problem.cost_vector.vector.reshape(1, -1)
            reduce_machine_amount_problem = crafting_chain_problem.problem.get_mixed_integer_linear_problem(
                objective_key=CostVectorType.MACHINE_AMOUNT_COST_VECTOR,
                epsilon_constraints=frozendict({t: c for t, c in cost_constraints.items()}),
                additional_constraint_matrix=optimal_cost_constraint,
                additional_constraint_bounds=np.array([[optimal_cost], [np.inf]])
            )
            optimal_solution = highs_solver.solve(reduce_machine_amount_problem)
            if optimal_solution is None:
                _LOGGER.warning('No solution found for the machine amount reduction problem.')
                return None
            recipe_vector = optimal_solution.vector

            if log:
                machine_amount = crafting_chain_problem.get_continuous_machine_amount(optimal_solution)
                machine_amount_int = crafting_chain_problem.get_machine_amount(optimal_solution)
                _LOGGER.info(f'Min Machine Amount Solution:')
                _LOGGER.info(f'Recipe vector: {optimal_solution.vector}')
                _LOGGER.info(f'Optimal machine amount: {machine_amount}')
                _LOGGER.info(f'Optimal integer machine amount: {machine_amount_int}')
                _LOGGER.info(f'Optimal machine weight constraint: {optimal_cost_constraint}')
                _LOGGER.info(f'Optimal machine weight: {optimal_cost_constraint @ recipe_vector}')
                _LOGGER.info(f'Number of non-zero recipes: {crafting_chain_problem.get_non_zero_recipe_count(optimal_solution)} out of {crafting_chain_problem.number_of_recipes}')
                _LOGGER.info(f'Machine cost vector: {reduce_machine_amount_problem.cost_vector}')
                _LOGGER.info(f'Machine cost vector number of non-zero entries: {np.count_nonzero(reduce_machine_amount_problem.cost_vector.vector)}')
                _LOGGER.info(f'Optimal cost (non-normalized): {optimal_solution.cost(reduce_machine_amount_problem.cost_vector, normalize=False)}')
                # _LOGGER.info(f'Non-zero recipes with amount: {[(self.recipes[i], recipe_vector[i]) for i in np.flatnonzero(recipe_vector[:self.q])]}')
        return SolutionVector(vector=recipe_vector)

    def create_crafting_chain(
        self,
        determined_solution: DeterminedSolution,
    ) -> CraftingChain:
        recipe_vector = self._get_recipe_vector(determined_solution).vector
        recipe_amounts = {r: a for r, a in zip(self.recipes, recipe_vector[:self.q]) if a != 0}
        material_vector = self.total_recipe_matrix[:, :self.q] @ recipe_vector[:self.q]
        material_amounts = {m: float(a) for m, a in zip(self.materials, material_vector)}
        # for i, x in enumerate(recipe_vector[:q]):
        #     if not np.isinf(ub[i]) and x >= ub[i]:
        #         _LOGGER.warning(f'Machine Limit reached for recipe {recipes[i]}: {x} = {ub[i]}')

        crafting_chain = CraftingChain.create_crafting_chain(
            recipe_amounts=recipe_amounts,
            total_material_needs=material_amounts,
            input_materials=self.inputs,
            infinite_materials=set(self.infinite_material_list),
            time=self.time
        )
        return crafting_chain

    # -----------------------------------------------------------------------------------------------------------------
    # Calculation of default solutions
    # -----------------------------------------------------------------------------------------------------------------

    def get_linear_default_solution(self) -> SolutionCalculationResult:
        solution_vector = self._determine_solution_vector(
            self.continuous_problem, CostVectorType.RECIPE_COST_VECTOR
        )
        if solution_vector is None:
            _LOGGER.warning('No solution found for the linear problem.')
            return SolutionCalculationResult(
                determined_solutions=[],
                response='No default linear solution found for the linear problem.'
            )
        support = self._create_support(np.arange(self.continuous_problem.q + self.continuous_problem.r, dtype=np.int32))
        determined_solution = DeterminedSolution(
            name='Default Linear Solution',
            used_support=support,
            cost_vector_type=CostVectorType.RECIPE_COST_VECTOR,
            optimal_costs=self._all_costs_from_full_recipe_vector(solution_vector),
            cost_constraints=frozendict({}),
            solution_vector=solution_vector,
            integer_machine_amounts=False,
            number_of_recipes=self.continuous_problem.number_of_recipes,
            default=True
        )
        return SolutionCalculationResult(
            determined_solutions=[determined_solution],
            response=f'Determined {len([determined_solution])} default linear solution.'
        )

    def get_default_mixed_integer_solution(
        self,
    ) -> SolutionCalculationResult:
        restricted_solution_vector = self._determine_solution_vector(
            self.mixed_integer_problem,
            cost_vector_type=CostVectorType.RECIPE_COST_VECTOR
        )
        if restricted_solution_vector is None:
            _LOGGER.warning('No solution found for the MILP problem.')
            return SolutionCalculationResult(
                determined_solutions=[],
                response='No default mixed integer solution found for the unrestricted MILP.'
            )
        determined_solution = DeterminedSolution(
            name='Default Mixed Integer Solution',
            used_support=self.full_support,
            cost_vector_type=CostVectorType.RECIPE_COST_VECTOR,
            optimal_costs=self._all_costs_from_full_recipe_vector(restricted_solution_vector),
            cost_constraints=frozendict({}),
            solution_vector=restricted_solution_vector,
            integer_machine_amounts=True,
            number_of_recipes=self.mixed_integer_problem.number_of_recipes,
            default=True
        )
        return SolutionCalculationResult(
            determined_solutions=[determined_solution],
            response=f'Determined {len([determined_solution])} default mixed integer solution.'
        )

    def get_default_restricted_mixed_integer_solutions(
        self,
        enabled_recipe_ids: set[str],
    ) -> SolutionCalculationResult:
        determined_solutions = []
        support = self._create_support_from_enabled_recipes(enabled_recipe_ids)
        restricted_mixed_problem = self.restrict_to_support_mixed(support=support)

        non_trivial_solution = restricted_mixed_problem.get_non_trivial_solution()
        if non_trivial_solution is None:
            _LOGGER.warning('No non-trivial default solution found for the restricted MILP problem.')

        _LOGGER.info('Calculating mixed integer default solution ...')
        restricted_solution_vector = self._determine_solution_vector(
            restricted_mixed_problem,
            cost_vector_type=CostVectorType.RECIPE_COST_VECTOR,
            support=support
        )
        if restricted_solution_vector is None:
            _LOGGER.warning('No solution found for the MILP problem.')
            return SolutionCalculationResult(
                determined_solutions=[],
                response='No Pareto-optimal default solutions found.'
            )
        determined_solution = DeterminedSolution(
            name='Default Solution',
            used_support=support,
            cost_vector_type=CostVectorType.RECIPE_COST_VECTOR,
            optimal_costs=self._all_costs_from_partial_solution(restricted_solution_vector, restricted_mixed_problem),
            cost_constraints=frozendict({}),
            solution_vector=restricted_solution_vector,
            integer_machine_amounts=True,
            number_of_recipes=restricted_mixed_problem.number_of_recipes,
            default=True
        )

        determined_solutions.append(determined_solution)
        return SolutionCalculationResult(
            determined_solutions=[determined_solution],
            response=f'Determined {len([determined_solution])} Pareto-optimal default solutions.'
        )

    # -----------------------------------------------------------------------------------------------------------------
    # Calculation of constrainted solutions
    # -----------------------------------------------------------------------------------------------------------------

    def get_restricted_mixed_integer_solutions(
        self,
        enabled_recipe_ids: set[str],
        optimized_cost_vector_type: CostVectorType = CostVectorType.RECIPE_COST_VECTOR,
        cost_constraints: GTNHConstraints = frozendict(),
        solution_name: str = 'Additional Solution',
    ) -> SolutionCalculationResult:
        determined_solutions: list[DeterminedSolution] = []
        support = self._create_support_from_enabled_recipes(enabled_recipe_ids)
        restricted_mixed_problem = self.restrict_to_support_mixed(support=support)

        non_trivial_solution = restricted_mixed_problem.get_non_trivial_solution()
        if non_trivial_solution is None:
            _LOGGER.warning(
                f'No non-trivial solution found for the restricted constrainted MILP problem with '
                f'cost_vector_type {optimized_cost_vector_type} and constraints {cost_constraints}'
            )

        restricted_constrainted_problem = restricted_mixed_problem.apply_constraints(
            cost_vector_type=optimized_cost_vector_type,
            cost_constraints=cost_constraints
        )
        highs_solver = HighsSolver(time_limit=60.0)
        optimal_solution = highs_solver.solve(restricted_constrainted_problem)
        if optimal_solution is None:
            _LOGGER.warning('No solution found for the restricted_constrainted_problem')
            return SolutionCalculationResult(
                determined_solutions=[],
                response='No Pareto-optimal solutions found.'
            )
        determined_solution = DeterminedSolution(
            name=f'{solution_name} {len(determined_solutions) + 1}',
            used_support=support,
            cost_vector_type=optimized_cost_vector_type,
            optimal_costs=self._all_costs_from_partial_solution(optimal_solution, restricted_mixed_problem),
            cost_constraints=cost_constraints,
            solution_vector=optimal_solution,
            integer_machine_amounts=True,
            number_of_recipes=restricted_mixed_problem.number_of_recipes
        )
        determined_solutions.append(determined_solution)
        return SolutionCalculationResult(
            determined_solutions=[determined_solution],
            response=f'Determined {len([determined_solution])} Pareto-optimal solutions.'
        )
