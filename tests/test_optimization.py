import numpy as np
import pytest
from scipy.sparse import csr_matrix
from frozendict import frozendict

from packages.optimization.optimization_problem import (
	CostVector, HighsSolver, MixedIntegerLinearProblem, SolutionSpace, MultiObjectiveMixedIntegerLinearProblem,
	CostConstraint, CostConstraints, SolutionVector, Support)


def _problem(
	objective: np.ndarray,
	minimize: bool,
	constraint_matrix: np.ndarray,
	constraint_bounds: np.ndarray,
	lower_bounds: np.ndarray,
	upper_bounds: np.ndarray,
	integer_indices: np.ndarray,
	normalization_scalar: float = 1.0,
) -> MixedIntegerLinearProblem:
	return MixedIntegerLinearProblem(
		cost_vector=CostVector(
			vector=np.asarray(objective, dtype=np.float64),
			normalization_scalar=normalization_scalar,
			minimize=minimize,
		),
		solution_space=SolutionSpace(
			constraint_matrix=csr_matrix(np.asarray(constraint_matrix, dtype=np.float64)),
			constraint_bounds=np.asarray(constraint_bounds, dtype=np.float64),
			lower_bounds=np.asarray(lower_bounds, dtype=np.float64),
			upper_bounds=np.asarray(upper_bounds, dtype=np.float64),
			integer_indices=np.asarray(integer_indices, dtype=np.int32),
		),
	)


def test_solution_space_restrict_to_support_preserves_order_and_remaps_integer_indices():
	solution_space = SolutionSpace(
		constraint_matrix=csr_matrix(np.array([[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0]], dtype=np.float64)),
		constraint_bounds=np.array([[0.0, 1.0], [10.0, 11.0]], dtype=np.float64),
		lower_bounds=np.array([10.0, 20.0, 30.0, 40.0], dtype=np.float64),
		upper_bounds=np.array([11.0, 21.0, 31.0, 41.0], dtype=np.float64),
		integer_indices=np.array([2, 0, 3], dtype=np.int32),
	)

	restricted = solution_space.restrict_to_support(Support(np.array([2, 0], dtype=np.int32)))

	assert restricted.constraint_matrix.toarray() == pytest.approx(np.array([[3.0, 1.0], [7.0, 5.0]]))
	assert restricted.constraint_bounds == pytest.approx(solution_space.constraint_bounds)
	assert restricted.lower_bounds == pytest.approx(np.array([30.0, 10.0]))
	assert restricted.upper_bounds == pytest.approx(np.array([31.0, 11.0]))
	assert restricted.integer_indices.tolist() == [0, 1]


def test_highs_solver_respects_continuous_indices():
	problem = _problem(
		objective=np.array([1.0]),
		minimize=False,
		constraint_matrix=np.array([[1.0]]),
		constraint_bounds=np.array([[-np.inf], [1.5]]),
		lower_bounds=np.array([0.0]),
		upper_bounds=np.array([10.0]),
		integer_indices=np.array([], dtype=np.int32),
	)

	solution = HighsSolver(time_limit=5.0).solve(problem)
	assert solution is not None
	assert solution.vector[0] == pytest.approx(1.5)


def test_highs_solver_respects_integer_indices():
	problem = _problem(
		objective=np.array([1.0]),
		minimize=False,
		constraint_matrix=np.array([[1.0]]),
		constraint_bounds=np.array([[-np.inf], [1.5]]),
		lower_bounds=np.array([0.0]),
		upper_bounds=np.array([10.0]),
		integer_indices=np.array([0]),
	)

	solution = HighsSolver(time_limit=5.0).solve(problem)
	assert solution is not None
	assert solution.vector[0] == pytest.approx(1.0)


def test_highs_solver_solves_linear_minimization_problem():
	problem = _problem(
		objective=np.array([2.0, 2.0]),
		minimize=False,
		constraint_matrix=np.array([[0.0, 1.0], [3.0, 1.0]]),
		constraint_bounds=np.array([[-np.inf, -np.inf], [1.5, 6]]),
		lower_bounds=np.array([0.0, 0.0]),
		upper_bounds=np.array([np.inf, np.inf]),
		integer_indices=np.array([], dtype=np.int32),
		normalization_scalar=0.5,
	)

	solution = HighsSolver(time_limit=5.0).solve(problem)
	assert solution is not None
	assert solution.vector == pytest.approx(np.array([1.5, 1.5]))
	assert solution.cost(problem.cost_vector) == pytest.approx(6.0)


def test_highs_solver_solves_mixed_integer_minimization_problem():
	problem = _problem(
		objective=np.array([2.0, 2.0]),
		minimize=False,
		constraint_matrix=np.array([[0.0, 1.0], [3.0, 1.0]]),
		constraint_bounds=np.array([[-np.inf, -np.inf], [1.5, 6]]),
		lower_bounds=np.array([0.0, 0.0]),
		upper_bounds=np.array([np.inf, np.inf]),
		integer_indices=np.array([1], dtype=np.int32),
		normalization_scalar=0.5,
	)

	solution = HighsSolver(time_limit=5.0).solve(problem)
	assert solution is not None
	assert solution.vector == pytest.approx(np.array([5/3, 1.0]))
	assert solution.cost(problem.cost_vector) == pytest.approx(5 + 1/3)


def test_highs_solver_solves_mixed_integer_minimization_problem_2():
	problem = _problem(
		objective=np.array([2.0, 2.0]),
		minimize=False,
		constraint_matrix=np.array([[0.0, 1.0], [3.0, 1.0]]),
		constraint_bounds=np.array([[-np.inf, -np.inf], [1.5, 6]]),
		lower_bounds=np.array([0.0, 0.0]),
		upper_bounds=np.array([np.inf, np.inf]),
		integer_indices=np.array([0], dtype=np.int32),
		normalization_scalar=0.5,
	)

	solution = HighsSolver(time_limit=5.0).solve(problem)
	assert solution is not None
	assert solution.vector == pytest.approx(np.array([1.0, 1.5]))
	assert solution.cost(problem.cost_vector) == pytest.approx(5.0)

@pytest.mark.parametrize(
    "lower",
    [
    1.0, 1.5
])
def test_epsilon_constraint_problem_construction(lower: float):
	problem = _problem(
		objective=np.array([2.0, 2.0]),
		minimize=False,
		constraint_matrix=np.array([[0.0, 1.0], [3.0, 1.0]]),
		constraint_bounds=np.array([[-np.inf, -np.inf], [1.5, 6]]),
		lower_bounds=np.array([0.0, 0.0]),
		upper_bounds=np.array([np.inf, np.inf]),
		integer_indices=np.array([1], dtype=np.int32),
		normalization_scalar=0.5,
	)
	mo_problem = MultiObjectiveMixedIntegerLinearProblem(
		cost_vectors=frozendict({
			"objective_1": problem.cost_vector,
			"objective_2": CostVector(
				vector=np.array([1.0, 0.0]),
				normalization_scalar=2.0,
				minimize=False,
			),
		}),
		solution_space=problem.solution_space,
	)
	epsilon_constraints = frozendict({
		"objective_2": CostConstraint(lower=lower, upper=None)
	})
	matrix_constraints = mo_problem.convert_cost_constraints_to_matrices(epsilon_constraints=epsilon_constraints)
	new_solution_space = mo_problem.solution_space.add_constraints(*matrix_constraints)

	assert new_solution_space.constraint_matrix.toarray() == pytest.approx(
		np.array([
			[0.0, 1.0],
			[3.0, 1.0],
			[1.0, 0.0],
		], dtype=np.float64)
	)
	assert new_solution_space.constraint_bounds == pytest.approx(
		np.array([
			[-np.inf, -np.inf, lower],
			[1.5, 6.0, np.inf],
		], dtype=np.float64)
	)
