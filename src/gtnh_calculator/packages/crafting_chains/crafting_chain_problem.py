from __future__ import annotations
import numpy as np
import logging
from dataclasses import dataclass
from frozendict import frozendict
from abc import ABC, abstractmethod
from enum import StrEnum

from ..recipes_db.material import Material
from ..recipes_db.instantiated_recipes import InstantiatedRecipe
from ..optimization.optimization_problem import (
    CostVector, MultiObjectiveMixedIntegerLinearProblem,
    HighsSolver, SolutionVector, MixedIntegerLinearProblem, CostConstraint, Support
)
from ..utility.general_utility import Timer

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class CostVectorType(StrEnum):
    RECIPE_COST_VECTOR = 'Recipe Cost Vector'
    EU_COST_VECTOR = 'EU Cost Vector'
    MACHINE_AMOUNT_COST_VECTOR = 'Machine Amount Cost Vector'


type GTNHConstraints = frozendict[CostVectorType, CostConstraint]


class GTNHSupport(Support):
    def __eq__(self, other: GTNHSupport) -> bool:
        return np.array_equal(np.sort(self), np.sort(other))


@dataclass(frozen=True)
class DeterminedSolution:
    name: str
    used_support: GTNHSupport
    cost_vector_type: CostVectorType
    optimal_costs: frozendict[CostVectorType, float]
    cost_constraints: GTNHConstraints
    solution_vector: SolutionVector
    integer_machine_amounts: bool
    number_of_recipes: int
    default: bool = False

    def __post_init__(self):
        if not(self.used_support.ndim == self.solution_vector.vector.ndim == 1):
            raise ValueError(f"Support ndim {self.used_support.ndim} and solution vector ndim {self.solution_vector.vector.ndim} must both be 1.")
        if self.integer_machine_amounts:
            if self.used_support.size != int(self.solution_vector.vector.size / 2):
                raise ValueError(f"Support size {self.used_support.size} must be half of solution vector size {self.solution_vector.vector.size} when integer_machine_amounts is True.")
        else:
            if self.used_support.size != self.solution_vector.vector.size:
                raise ValueError(f"Support size {self.used_support.size} and solution vector size {self.solution_vector.vector.size} must be equal.")

    @property
    def markdown_string(self) -> str:
        recipe_vector = self.solution_vector.vector[:self.number_of_recipes]
        # half_size = int(self.solution_vector.vector.size / 2)
        # infinite_materials_vector = self.solution_vector.vector[self.number_of_recipes:half_size]
        return (
            f'**Optimized Cost Vector:** {self.cost_vector_type.value}  \n'
            f'**Optimal Cost:** {", ".join(f"{t}: {self.optimal_costs[t]:.2f}" for t in self.optimal_costs.keys())}  \n'
            f'**Cost Constraints:** {", ".join(f"{k}: {v.markdown_string}" for k, v in self.cost_constraints.items()) if self.cost_constraints else "None"}  \n'
            f'**Used Recipes:** {np.count_nonzero(recipe_vector)} of {self.number_of_recipes}'
        )

    def get_number_of_recipes(self, global_q: int) -> int:
        return np.sum((self.used_support < global_q).astype(int))

    def get_number_of_infinite_materials(self, global_q: int) -> int:
        return np.sum((self.used_support >= global_q).astype(int))

    def is_compatible(self, other: DeterminedSolution) -> bool:
        is_compatible = (
            self.used_support == other.used_support and
            self.integer_machine_amounts == other.integer_machine_amounts
        ) and self.solution_vector != other.solution_vector
        if not is_compatible:
            _LOGGER.warning(f'Duplicate solution found with differing solution vectors: {self.markdown_string} vs {other.markdown_string}')
        return is_compatible


class CraftingChainProblem(ABC):
    problem: MultiObjectiveMixedIntegerLinearProblem
    constraint_info: tuple[str, ...]

    @property
    def number_of_variables(self) -> int:
        return self.problem.num_variables

    @property
    @abstractmethod
    def number_of_recipes(self) -> int:
        ...

    @property
    @abstractmethod
    def number_of_infinite_materials(self) -> int:
        ...

    @abstractmethod
    def get_non_trivial_solution(self) -> SolutionVector | None:
        ...

    @abstractmethod
    def supported_recipes(self, solution_vector: SolutionVector) -> list[InstantiatedRecipe]:
        ...

    def cost_vector(self, cost_vector_type: CostVectorType) -> CostVector:
        return self.problem.cost_vectors[cost_vector_type]

    @property
    def cost_vectors(self) -> frozendict[CostVectorType, CostVector]:
        return self.problem.cost_vectors  # type: ignore

    def get_continuous_machine_amount(self, solution_vector: SolutionVector) -> float:
        machine_amount_cost_vector = self.cost_vector(CostVectorType.MACHINE_AMOUNT_COST_VECTOR)
        machine_amount = solution_vector.cost(machine_amount_cost_vector, normalize=False)
        return machine_amount

    def get_machine_amount(self, solution_vector: SolutionVector) -> float:
        machine_amount_cost_vector = self.cost_vector(CostVectorType.MACHINE_AMOUNT_COST_VECTOR)
        machine_amount = np.sum(np.ceil(solution_vector.vector * machine_amount_cost_vector.vector))
        return machine_amount

    @abstractmethod
    def get_non_zero_recipe_count(self, solution_vector: SolutionVector) -> int:
        ...

    def apply_constraints(self, cost_vector_type: CostVectorType, cost_constraints: GTNHConstraints) -> MixedIntegerLinearProblem:
        modified_problem = self.problem.get_mixed_integer_linear_problem(
            objective_key=cost_vector_type,
            epsilon_constraints=frozendict({t: c for t, c in cost_constraints.items()})
        )
        return modified_problem
    

@dataclass(frozen=True)
class ContinuousCraftingChainProblem(CraftingChainProblem):
    problem: MultiObjectiveMixedIntegerLinearProblem
    recipes: list[InstantiatedRecipe]
    infinite_material_list: list[Material]
    q: int
    r: int
    constraint_info: tuple[str, ...]

    @property
    def number_of_recipes(self) -> int:
        return self.q

    @property
    def number_of_infinite_materials(self) -> int:
        return self.r

    def get_non_trivial_solution(self) -> SolutionVector | None:
        with Timer('get_non_trivial_solution', active=True):
            highs_solver = HighsSolver(time_limit=25.0)
            trivial_cost_vector = CostVector(np.zeros(self.problem.num_variables), normalization_scalar=1, minimize=True)
            additional_constraint_matrix = np.concatenate([
                np.ones((self.q,)),
                np.zeros((self.r,)),
            ])
            additional_constraint_matrix = np.vstack([
                additional_constraint_matrix,
                self.cost_vectors[CostVectorType.RECIPE_COST_VECTOR].vector
            ])
            solution_space = self.problem.solution_space.add_constraints(
                additional_constraint_matrix=additional_constraint_matrix,
                additional_constraint_bounds=np.array([[0.001, 0.1], [np.inf, np.inf]])
            )
            problem = MixedIntegerLinearProblem(
                solution_space=solution_space,
                cost_vector=trivial_cost_vector
            )
            _LOGGER.info(f'Problem for finding non-trivial solution: {problem.problem_statistics_string()}')
            optimal_solution = highs_solver.solve(problem)

            if optimal_solution is None:
                _LOGGER.warning(f'Problem has no non-trivial solutions (q={self.q}, r={self.r})')
                return None
            return optimal_solution

    def supported_recipes(self, solution_vector: SolutionVector) -> list[InstantiatedRecipe]:
        if solution_vector.vector.size != self.number_of_variables:
            raise ValueError(
                f"Expected solution vector of size {self.number_of_variables}, got {solution_vector.vector.size}"
            )
        non_zero_indices = np.flatnonzero(solution_vector.vector[:self.q])
        return [self.recipes[i] for i in non_zero_indices]

    def get_non_zero_recipe_count(self, solution_vector: SolutionVector) -> int:
        return np.count_nonzero(solution_vector.vector[:self.q]).astype(int)

    @classmethod
    def create(
        cls, problem: MultiObjectiveMixedIntegerLinearProblem, recipes: list[InstantiatedRecipe], 
        infinite_material_list: list[Material], constraint_info: tuple[str, ...]
    ) -> ContinuousCraftingChainProblem:
        q = len(recipes)
        r = len(infinite_material_list)
        if q + r != problem.num_variables:
            raise ValueError(
                f"Expected problem.num_variables to be {q + r}, got {problem.num_variables} (q={q}, r={r})"
            )
        if len(constraint_info) != problem.num_constraints:
            raise ValueError(
                f"Expected constraint_info to have length {problem.num_constraints}, got {len(constraint_info)}"
            )
        return cls(problem=problem, recipes=recipes, infinite_material_list=infinite_material_list, q=q, r=r, constraint_info=constraint_info)


@dataclass(frozen=True)
class MixedIntegerCraftingChainProblem(CraftingChainProblem):
    problem: MultiObjectiveMixedIntegerLinearProblem
    recipes: list[InstantiatedRecipe]
    infinite_material_list: list[Material]
    q: int
    r: int
    constraint_info: tuple[str, ...]

    @property
    def number_of_recipes(self) -> int:
        return self.q

    @property
    def number_of_infinite_materials(self) -> int:
        return self.r

    def get_non_zero_recipe_count(self, solution_vector: SolutionVector) -> int:
        return np.count_nonzero(solution_vector.vector[:self.q]).astype(int)

    def supported_recipes(self, solution_vector: SolutionVector) -> list[InstantiatedRecipe]:
        if solution_vector.vector.size != self.number_of_variables:
            raise ValueError(
                f"Expected solution vector of size {self.number_of_variables}, got {solution_vector.vector.size}"
            )
        non_zero_indices = np.flatnonzero(solution_vector.vector[:self.q])
        return [self.recipes[i] for i in non_zero_indices]

    def get_non_trivial_solution(self) -> SolutionVector | None:
        with Timer('get_non_trivial_solution', active=True):
            highs_solver = HighsSolver(time_limit=25.0)
            trivial_cost_vector = CostVector(np.zeros(self.problem.num_variables), normalization_scalar=1, minimize=True)
            additional_constraint_matrix = np.concatenate([
                np.ones((self.q,)),
                np.zeros((self.q + 2 * self.r)),
            ])
            additional_constraint_matrix = np.vstack([
                additional_constraint_matrix,
                self.cost_vectors[CostVectorType.RECIPE_COST_VECTOR].vector
            ])
            solution_space = self.problem.solution_space.add_constraints(
                additional_constraint_matrix=additional_constraint_matrix,
                additional_constraint_bounds=np.array([[1, 0.1], [np.inf, np.inf]])
            )
            problem = MixedIntegerLinearProblem(
                solution_space=solution_space,
                cost_vector=trivial_cost_vector
            )
            _LOGGER.info(f'Problem for finding non-trivial solution: {problem.problem_statistics_string()}')
            optimal_solution = highs_solver.solve(problem)

            if optimal_solution is None:
                _LOGGER.warning(f'Problem has no non-trivial solutions (q={self.q}, r={self.r})')
                return None
            return optimal_solution

    @classmethod
    def create(
        cls, problem: MultiObjectiveMixedIntegerLinearProblem, recipes: list[InstantiatedRecipe], 
        infinite_material_list: list[Material], constraint_info: tuple[str, ...]
    ) -> MixedIntegerCraftingChainProblem:
        q = len(recipes)
        r = len(infinite_material_list)
        if 2 * (q + r) != problem.num_variables:
            raise ValueError(
                f"Expected problem.num_variables to be {2 * (q + r)}, got {problem.num_variables} (q={q}, r={r})"
            )
        if len(constraint_info) != problem.num_constraints:
            raise ValueError(
                f"Expected constraint_info to have length {problem.num_constraints}, got {len(constraint_info)}"
            )
        return cls(problem=problem, recipes=recipes, infinite_material_list=infinite_material_list, q=q, r=r, constraint_info=constraint_info)
