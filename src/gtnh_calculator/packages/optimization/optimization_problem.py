from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from typing import Callable
import logging
from frozendict import frozendict
from numpy.typing import NDArray
from scipy.sparse import hstack, vstack, csr_matrix
from highspy import Highs, HighsModelStatus, HighsVarType

from ..utility.constants import SUPPORT_THRESHOLD

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class Support(np.ndarray):
    def __new__(cls, input_array: np.ndarray):
        obj = np.asarray(input_array).view(cls)
        if obj.ndim != 1:
            raise ValueError(f"Support must be 1-dimensional but has shape {obj.shape}")
        if obj.dtype != np.int32:
            raise ValueError(f"Support must be of dtype np.int32 but has dtype {obj.dtype}")
        if np.unique(obj).size != obj.size:
            raise ValueError(f"Support must contain unique elements but got {obj}")
        return obj

    @classmethod
    def empty(cls) -> Support:
        return cls(np.empty(0, dtype=np.int32))


@dataclass(frozen=True)
class CostVector:
    vector: np.ndarray
    normalization_scalar: float
    minimize: bool

    def __post_init__(self):
        if self.vector.ndim != 1:
            raise ValueError(f"Cost vector must be 1-dimensional but has shape {self.vector.shape}")
        if self.normalization_scalar <= 0:
            raise ValueError(f"Normalization scalar must be positive but got {self.normalization_scalar}")

    @property
    def num_variables(self) -> int:
        return self.vector.size

    @property
    def normalized_vector(self) -> np.ndarray:
        return self.vector / self.normalization_scalar

    def apply(self, solution_vector: SolutionVector, normalize: bool = False) -> float:
        if normalize:
            return np.dot(self.normalized_vector, solution_vector.vector)
        return np.dot(self.vector, solution_vector.vector)

    def restrict_to_support(self, support: Support, extend_by_zeros: int = 0) -> CostVector:
        return CostVector(
            vector=np.concatenate([self.vector[support], np.zeros(extend_by_zeros, dtype=self.vector.dtype)]),
            normalization_scalar=self.normalization_scalar,
            minimize=self.minimize
        )

    def append(self, vector: np.ndarray) -> CostVector:
        if vector.ndim != 1:
            raise ValueError(f"Appended vector must be 1-dimensional but has shape {vector.shape}")
        return CostVector(
            vector=np.concatenate([self.vector, vector]),
            normalization_scalar=self.normalization_scalar,
            minimize=self.minimize
        )

@dataclass(frozen=True)
class CostConstraint:
    lower: float | None = None
    upper: float | None = None

    def lower_le(self, value: float) -> bool:
        return self.lower is None or self.lower <= value

    @property
    def markdown_string(self) -> str:
        lower_str = "Lower bound: " + (f"{self.lower}" if self.lower is not None else "−∞")
        upper_str = "Upper bound: " + (f"{self.upper}" if self.upper is not None else "∞")
        return f"{lower_str}, {upper_str}"


type CostConstraints = frozendict[str, CostConstraint]


@dataclass(frozen=True)
class SolutionSpace:
    constraint_matrix: csr_matrix
    constraint_bounds: np.ndarray
    lower_bounds: np.ndarray
    upper_bounds: np.ndarray
    integer_indices: np.ndarray

    @property
    def num_constraints(self) -> int:
        return self.constraint_matrix.get_shape()[0]

    @property
    def num_variables(self) -> int:
        return self.constraint_matrix.get_shape()[1]

    @property
    def lower_constraint_bounds(self) -> np.ndarray:
        return self.constraint_bounds[0, :]
    
    @property
    def upper_constraint_bounds(self) -> np.ndarray:
        return self.constraint_bounds[1, :]

    @property
    def is_continuous(self) -> bool:
        return self.integer_indices.size == 0
    
    def __post_init__(self):
        num_constraints, num_variables = self.constraint_matrix.get_shape()
        constraint_bounds = np.asarray(self.constraint_bounds, dtype=np.float64)
        lower_bounds = np.asarray(self.lower_bounds, dtype=np.float64)
        upper_bounds = np.asarray(self.upper_bounds, dtype=np.float64)
    
        if constraint_bounds.ndim != 2 or constraint_bounds.shape[0] != 2:
            raise ValueError(f"constraint_bounds must have shape (2, num_constraints) but has shape {constraint_bounds.shape}")

        if lower_bounds.size != num_variables or upper_bounds.size != num_variables:
            raise ValueError(f"Variable bounds must match number of variables {num_variables} but got lower_bounds size {lower_bounds.size} and upper_bounds size {upper_bounds.size}")

        if num_constraints != constraint_bounds.shape[1]:
            raise ValueError(f"constraint_bounds column count must match constraint matrix row count {num_constraints} but has {constraint_bounds.shape[1]}")

    def restrict_to_support(self, support: Support, full_integer: bool = False) -> SolutionSpace:
        if np.any(support < 0) or np.any(support >= self.num_variables):
            raise ValueError(f"Support indices must be in the range [0, {self.num_variables}) but got {support}")

        restricted_constraint_matrix = self.constraint_matrix[:, support]
        restricted_lower_bounds = self.lower_bounds[support]
        restricted_upper_bounds = self.upper_bounds[support]

        if full_integer:
            restricted_integer_indices = np.arange(len(support), dtype=np.int32)
        else:
            restricted_integer_indices = np.flatnonzero(np.isin(support, self.integer_indices)).astype(np.int32)

        return SolutionSpace(
            constraint_matrix=restricted_constraint_matrix,
            constraint_bounds=self.constraint_bounds,
            lower_bounds=restricted_lower_bounds,
            upper_bounds=restricted_upper_bounds,
            integer_indices=restricted_integer_indices
        )

    def add_constraints(
        self, additional_constraint_matrix: np.ndarray, additional_constraint_bounds: np.ndarray
    ) -> SolutionSpace:
        if additional_constraint_matrix.ndim != 2:
            raise ValueError(f"Additional constraint matrix must be 2-dimensional but has shape {additional_constraint_matrix.shape}")
        if additional_constraint_bounds.ndim != 2 or additional_constraint_bounds.shape[0] != 2:
            raise ValueError(f"Additional constraint bounds must have shape (2, num_additional_constraints) but has shape {additional_constraint_bounds.shape}")
        if additional_constraint_matrix.shape[0] != additional_constraint_bounds.shape[1]:
            raise ValueError(f"Number of rows in additional constraint matrix {additional_constraint_matrix.shape[0]} must match number of columns in additional constraint bounds {additional_constraint_bounds.shape[1]}")

        new_constraint_matrix = csr_matrix(vstack([self.constraint_matrix, csr_matrix(additional_constraint_matrix)], format='csr'))
        new_constraint_bounds = np.hstack([self.constraint_bounds, additional_constraint_bounds])

        return SolutionSpace(
            constraint_matrix=new_constraint_matrix,
            constraint_bounds=new_constraint_bounds,
            lower_bounds=self.lower_bounds,
            upper_bounds=self.upper_bounds,
            integer_indices=self.integer_indices
        )


@dataclass(frozen=True)
class MixedIntegerLinearProblem:
    cost_vector: CostVector
    solution_space: SolutionSpace

    @property
    def num_constraints(self) -> int:
        return self.solution_space.num_constraints

    @property
    def num_variables(self) -> int:
        return self.solution_space.num_variables

    @property
    def is_continuous(self) -> bool:
        return self.solution_space.is_continuous

    def __post_init__(self):
        if self.cost_vector.num_variables != self.solution_space.num_variables:
            raise ValueError(f"Cost vector length {self.cost_vector.num_variables} must match number of variables {self.solution_space.num_variables}")

    def restrict_to_support(self, support: Support, full_integer: bool = False) -> MixedIntegerLinearProblem:
        restricted_solution_space = self.solution_space.restrict_to_support(support, full_integer=full_integer)
        restricted_cost_vector = self.cost_vector.restrict_to_support(support)
        return MixedIntegerLinearProblem(
            cost_vector=restricted_cost_vector,
            solution_space=restricted_solution_space
        )

    def problem_statistics_string(self) -> str:
        return (
            f"MixedIntegerLinearProblem with {self.num_variables} variables and {self.num_constraints} constraints. "
            f"Cost vector minimize: {self.cost_vector.minimize}, "
            f"Normalization scalar: {self.cost_vector.normalization_scalar}. "
            f"Integer indices: {self.solution_space.integer_indices.size}"
        )


@dataclass(frozen=True)
class MultiObjectiveMixedIntegerLinearProblem:
    cost_vectors: frozendict[str, CostVector]
    solution_space: SolutionSpace

    @property
    def num_constraints(self) -> int:
        return self.solution_space.num_constraints

    @property
    def num_variables(self) -> int:
        return self.solution_space.num_variables

    def __post_init__(self):
        for cost_vector in self.cost_vectors.values():
            if cost_vector.num_variables != self.solution_space.num_variables:
                raise ValueError(f"Cost vector length {cost_vector.num_variables} must match number of variables {self.solution_space.num_variables}")

    def restrict_to_support(self, support: Support, full_integer: bool = False) -> MultiObjectiveMixedIntegerLinearProblem:
        restricted_solution_space = self.solution_space.restrict_to_support(support, full_integer=full_integer)
        restricted_cost_vectors = frozendict({
            key: cost_vector.restrict_to_support(support)
            for key, cost_vector in self.cost_vectors.items()
        })
        return MultiObjectiveMixedIntegerLinearProblem(
            cost_vectors=restricted_cost_vectors,
            solution_space=restricted_solution_space
        )

    def convert_cost_constraints_to_matrices(
        self, epsilon_constraints: CostConstraints
    ) -> tuple[np.ndarray, np.ndarray]:
        additional_constraint_matrix = []
        additional_constraint_bounds = []
        for key, constraint in epsilon_constraints.items():
            if key not in self.cost_vectors:
                raise ValueError(f"Epsilon constraint key {key} not found in cost vectors {set(self.cost_vectors.keys())}")

            additional_constraint_matrix.append(self.cost_vectors[key].vector)
            additional_constraint_bounds.append([
                constraint.lower if constraint.lower is not None else -np.inf, 
                constraint.upper if constraint.upper is not None else np.inf
            ])
        additional_constraint_matrix = np.vstack(additional_constraint_matrix)
        additional_constraint_bounds = np.transpose(np.array(additional_constraint_bounds))
        return additional_constraint_matrix, additional_constraint_bounds

    def get_mixed_integer_linear_problem(
        self, objective_key: str, epsilon_constraints: CostConstraints = frozendict(),
        additional_constraint_matrix: np.ndarray | None = None,
        additional_constraint_bounds: np.ndarray | None = None,
    ) -> MixedIntegerLinearProblem:
        if objective_key not in self.cost_vectors:
            raise ValueError(f"Objective key {objective_key} not found in cost vectors {set(self.cost_vectors.keys())}")
        if epsilon_constraints and {objective_key}.union(epsilon_constraints.keys()) != set(self.cost_vectors.keys()):
            raise ValueError(
                f"Epsilon constraints keys {set(epsilon_constraints.keys())} together with objective key {objective_key} "
                f"must cover all cost vector keys {set(self.cost_vectors.keys())}"
            )

        additional_constraint_matrix = np.empty((0, self.num_variables)) if additional_constraint_matrix is None else additional_constraint_matrix
        additional_constraint_bounds = np.empty((2, 0)) if additional_constraint_bounds is None else additional_constraint_bounds

        if epsilon_constraints:
            epsilon_constraint_matrix, epsilon_constraint_bounds = self.convert_cost_constraints_to_matrices(epsilon_constraints)
            additional_constraint_matrix = np.vstack(
                [additional_constraint_matrix, epsilon_constraint_matrix]
            ) if additional_constraint_matrix is not None else epsilon_constraint_matrix
            additional_constraint_bounds = np.hstack(
                [additional_constraint_bounds, epsilon_constraint_bounds]
            ) if additional_constraint_bounds is not None else epsilon_constraint_bounds
        
        if additional_constraint_matrix.shape[0] > 0:
            solution_space = self.solution_space.add_constraints(additional_constraint_matrix, additional_constraint_bounds)
        else:
            solution_space = self.solution_space

        cost_vector = self.cost_vectors[objective_key]
        return MixedIntegerLinearProblem(
            cost_vector=cost_vector,
            solution_space=solution_space
        )
    
    def problem_statistics_string(self) -> str:
        cost_vector_stats = ", ".join([f"{key}: minimize={cv.minimize}, normalization_scalar={cv.normalization_scalar}" for key, cv in self.cost_vectors.items()])
        return (
            f"MultiObjectiveMixedIntegerLinearProblem with {self.num_variables} variables and {self.num_constraints} constraints. "
            f"Cost vectors: {cost_vector_stats}. "
            f"Integer indices: {self.solution_space.integer_indices}"
        )


@dataclass(frozen=True)
class SolutionVector:
    vector: np.ndarray

    def cost(self, cost_vector: CostVector, normalize: bool = False) -> float:
        return cost_vector.apply(self, normalize=normalize)

    def costs(self, cost_vectors: frozendict[str, CostVector], normalize: bool = False) -> frozendict[str, float]:
        return frozendict({key: cost_vector.apply(self, normalize=normalize) for key, cost_vector in cost_vectors.items()})

    @property
    def support(self) -> Support:
        return Support(np.flatnonzero(np.abs(self.vector) > SUPPORT_THRESHOLD).astype(np.int32))

    @property
    def size(self) -> int:
        return self.vector.size

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, SolutionVector):
            return False
        return np.array_equal(self.vector, value.vector)


@dataclass
class HighsSolver:
    time_limit: float
    output_flag: bool = False

    def solve(self, problem: MixedIntegerLinearProblem, cost_constraint: CostConstraint | None = None) -> SolutionVector | None:
        highs = Highs()
        highs.setOptionValue("output_flag", self.output_flag)
        highs.setOptionValue("solver", "ipm")
        highs.setOptionValue("presolve", "on")
        highs.setOptionValue("parallel", "on")
        highs.setOptionValue("time_limit", self.time_limit)

        objective_vector = np.asarray(problem.cost_vector.normalized_vector, dtype=np.float64)
        solution_space = problem.solution_space

        constraint_matrix: csr_matrix = csr_matrix(solution_space.constraint_matrix, dtype=np.float64)

        num_variables = problem.num_variables
        num_constraints = problem.num_constraints
        
        lower_bounds = np.asarray(solution_space.lower_bounds, dtype=np.float64)
        upper_bounds = np.asarray(solution_space.upper_bounds, dtype=np.float64)

        empty_starts = np.empty(0, dtype=np.int32)
        empty_indices = np.empty(0, dtype=np.int32)
        empty_values = np.empty(0, dtype=np.float64)

        highs.addCols(
            num_variables,
            objective_vector,
            lower_bounds,
            upper_bounds,
            0,
            empty_starts,
            empty_indices,
            empty_values
        )
        row_starts: NDArray[np.int32] = np.asarray(constraint_matrix.indptr, dtype=np.int32)
        row_indices: NDArray[np.int32] = np.asarray(constraint_matrix.indices, dtype=np.int32)
        row_values: NDArray[np.float64] = np.asarray(constraint_matrix.data, dtype=np.float64)
        highs.addRows(
            num_constraints,
            solution_space.lower_constraint_bounds,
            solution_space.upper_constraint_bounds,
            row_values.size,
            row_starts,
            row_indices,
            row_values
        )

        integer_indices: NDArray[np.int32] = np.asarray(solution_space.integer_indices, dtype=np.int32)
        if integer_indices.size > 0:
            highs.changeColsIntegrality(
                integer_indices.size,
                integer_indices,
                np.full(integer_indices.size, HighsVarType.kInteger, dtype=object)
            )

        if problem.cost_vector.minimize:
            highs.setMinimize()
        else:
            highs.setMaximize()

        highs.run()
        status = highs.getModelStatus()
        if status != HighsModelStatus.kOptimal:
            _LOGGER.error(f'HiGHS failed with status {status}.')
            return None

        return SolutionVector(np.array(highs.getSolution().col_value, dtype=np.float64))
