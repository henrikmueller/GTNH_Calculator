from dataclasses import dataclass
import numpy as np
from typing import Dict
from frozendict import frozendict
from abc import ABC, abstractmethod


type OptimizationParameters = frozendict[str, float]


@dataclass(frozen=True)
class ParameterSpace:
    lower_bounds: Dict[str, float]
    upper_bounds: Dict[str, float]

    @property
    def parameter_types(self) -> set[str]:
        return set(self.lower_bounds.keys()) | set(self.upper_bounds.keys())

    def __repr__(self):
        return f'ParameterSpace(Lower: {self.lower_bounds}, Upper: {self.upper_bounds})'


@dataclass(frozen=True)
class OptimalSolution:
    solution_vector: np.ndarray
    optimal_cost: float


@dataclass(frozen=True)
class CostVector:
    name: str
    vector: np.ndarray
    normalization_scalar: float

    @property
    def normalized_vector(self) -> np.ndarray:
        return self.vector / self.normalization_scalar

    def __repr__(self):
        return f'CostVector({self.name})'


@dataclass(frozen=True)
class CostVectorCollection:
    cost_vectors: Dict[str, CostVector]

    @property
    def parameter_types(self) -> set[str]:
        return set(self.cost_vectors.keys())

    @property
    def cost_vector_list(self) -> list[CostVector]:
        return list(self.cost_vectors.values())

    def __len__(self) -> int:
        return len(self.cost_vector_list)

    def __iter__(self):
        return iter(self.cost_vector_list)

    def __getitem__(self, index) -> CostVector:
        return self.cost_vector_list[index]


@dataclass(frozen=True)
class CostConstraints:
    lower_constraints: Dict[str, float]
    upper_constraints: Dict[str, float]

    @property
    def parameter_types(self) -> set[str]:
        return set(self.lower_constraints.keys()) | set(self.upper_constraints.keys())

    def __repr__(self):
        return f'CostConstraints(Lower: {self.lower_constraints}, Upper: {self.upper_constraints})'


@dataclass(frozen=True)
class MultiObjectiveOptimizationProblem(ABC):
    parameter_types: tuple[str, ...]
    cost_vectors: CostVectorCollection
    cost_constraints: CostConstraints

    def __post_init__(self):
        if len(self.parameter_types) == 0:
            raise ValueError('Parameter names cannot be empty')
        if len(self.cost_vectors) == 0:
            raise ValueError('Cost vectors cannot be empty')
        if set(self.parameter_types) != set(self.cost_vectors.parameter_types):
            raise ValueError(f'Parameter names {self.parameter_types} do not match cost vector names {self.cost_vectors.parameter_types}')
        if not set(self.cost_constraints.parameter_types).issubset(set(self.parameter_types)):
            raise ValueError(f'Parameter names {self.parameter_types} do not match constraint names {self.cost_constraints.parameter_types}')
    
    @property
    def n_parameters(self) -> int:
        return len(self.parameter_types)
    
    def validate_parameters(self, parameters: OptimizationParameters) -> None:
        if set(parameters.keys()) != set(self.parameter_types):
            raise ValueError(f'Parameters must have keys {self.parameter_types}, got {parameters.keys()}')

    def solve(self, parameters: OptimizationParameters) -> OptimalSolution:
        self.validate_parameters(parameters)
        return self._solve(parameters)

    @abstractmethod
    def _solve(self, parameters: OptimizationParameters) -> OptimalSolution:
        pass


@dataclass(frozen=True)
class ParetoFront:
    solutions: frozendict[OptimizationParameters, OptimalSolution]


class ParetoFrontVisualizer(ABC):
    @abstractmethod
    def visualize(self, pareto_front: ParetoFront) -> None:
        pass


@dataclass(frozen=True)
class MultiObjectiveOptimizationSolver(ABC):
    parameter_space: ParameterSpace
    optimization_problem: MultiObjectiveOptimizationProblem

    def pareto_front(self, parameter_list: list[OptimizationParameters]) -> ParetoFront:
        solutions = {}
        for parameters in parameter_list:
            solution = self.optimization_problem.solve(parameters)
            solutions[parameters] = solution
        return ParetoFront(solutions=frozendict(solutions))
    
    @abstractmethod
    def choose_parameter_list(self) -> list[OptimizationParameters]:
        pass
