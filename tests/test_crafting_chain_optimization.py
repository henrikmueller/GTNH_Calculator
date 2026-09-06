from frozendict import frozendict
import pytest

from packages.crafting_chains.crafting_chain_optimizer import CraftingChainFinder, CostVectorType
from packages.configs.crafting_chain_config_db import CraftingChainConfig
from packages.recipes_db.material import MaterialGroup
from packages.recipes_db.adapted_recipes import AdaptedRecipe
from packages.recipes_db.voltage_tiers import VoltageTier
from utility.helper_functions import (
	get_test_material,
	instantiated_recipe,
	create_test_machine,
)


def test_get_linear_default_solution_maximizes_output_with_bounded_input():
	input_material = get_test_material("Input")
	infinite_material = get_test_material("Infinite")
	intermediate_material_left = get_test_material("Intermediate Left")
	intermediate_material_right = get_test_material("Intermediate Right")
	output_material = get_test_material("Output")
	machine = create_test_machine()

	recipes = [
		instantiated_recipe(
			"recipe_1==",
			AdaptedRecipe(
				eu_per_tick=-8,
				processing_time=10,
				amperage=1,
				inputs=frozendict({MaterialGroup([input_material]): -1, MaterialGroup([infinite_material]): -1}),
				output_specifications=frozendict({0: (intermediate_material_left, 1, 1)}),
			),
			machine
		),
		instantiated_recipe(
			"recipe_2==",
			AdaptedRecipe(
				eu_per_tick=-6,
				processing_time=3,
				amperage=1,
				inputs=frozendict({MaterialGroup([input_material]): -1, MaterialGroup([infinite_material]): -1}),
				output_specifications=frozendict({0: (intermediate_material_right, 1, 1)}),
			),
			machine
		),
		instantiated_recipe(
			"recipe_3==",
			AdaptedRecipe(
				eu_per_tick=-2,
				processing_time=2,
				amperage=1,
				inputs=frozendict({MaterialGroup([intermediate_material_left]): -1}),
				output_specifications=frozendict({0: (output_material, 1, 1)}),
			),
			machine
		),
		instantiated_recipe(
			"recipe_4==",
			AdaptedRecipe(
				eu_per_tick=-30,
				processing_time=15,
				amperage=1,
				inputs=frozendict({MaterialGroup([intermediate_material_right]): -1}),
				output_specifications=frozendict({0: (output_material, 2, 1)}),
			),
			machine
		),
	]
	config = CraftingChainConfig.__new__(CraftingChainConfig)
	config.inputs = {input_material}
	config.outputs = {output_material}
	config.infinite_materials = {infinite_material}
	config.weights = {output_material: 1}
	config.infinite_production_weights = {infinite_material: 0.0}
	config.lower_bounds = {input_material: -10.0}
	config.upper_bounds = {}
	config.equalities = {}
	config.time = "60s"
	config.max_voltage_tier = VoltageTier.LV
	config.machine_limit = 100

	finder = CraftingChainFinder(
		instantiated_recipes=recipes,
		materials=[
			input_material, intermediate_material_left, intermediate_material_right, output_material, 
			infinite_material
		],
		config=config,
		machine_limit=100,
	)
	optimization_response = finder.get_linear_default_solution()
	assert optimization_response.success
	assert len(optimization_response.determined_solutions) == 1

	solution = optimization_response.pick_solution()
	crafting_chain = finder.create_crafting_chain(solution)
	assert crafting_chain.total_material_needs[input_material] == pytest.approx(-10)
	assert crafting_chain.total_material_needs[infinite_material] == pytest.approx(-10)
	assert crafting_chain.total_material_needs[intermediate_material_left] == pytest.approx(0)
	assert crafting_chain.total_material_needs[intermediate_material_right] == pytest.approx(0)
	assert crafting_chain.total_material_needs[output_material] == pytest.approx(20)

	assert crafting_chain.get_machine_amount("recipe_1==0") == pytest.approx(0)
	assert crafting_chain.get_machine_amount("recipe_2==0") == pytest.approx(0.5)
	assert crafting_chain.get_machine_amount("recipe_3==0") == pytest.approx(0)
	assert crafting_chain.get_machine_amount("recipe_4==0") == pytest.approx(2.5)


def test_get_mixed_integer_default_solution_maximizes_output_with_bounded_input():
	input_material = get_test_material("Input")
	infinite_material = get_test_material("Infinite")
	intermediate_material_left = get_test_material("Intermediate Left")
	intermediate_material_right = get_test_material("Intermediate Right")
	output_material = get_test_material("Output")
	machine = create_test_machine()

	recipes = [
		instantiated_recipe(
			"recipe_1==",
			AdaptedRecipe(
				eu_per_tick=-8,
				processing_time=10,
				amperage=1,
				inputs=frozendict({MaterialGroup([input_material]): -1, MaterialGroup([infinite_material]): -1}),
				output_specifications=frozendict({0: (intermediate_material_left, 1, 1)}),
			),
			machine
		),
		instantiated_recipe(
			"recipe_2==",
			AdaptedRecipe(
				eu_per_tick=-6,
				processing_time=3,
				amperage=1,
				inputs=frozendict({MaterialGroup([input_material]): -1, MaterialGroup([infinite_material]): -1}),
				output_specifications=frozendict({0: (intermediate_material_right, 1, 1)}),
			),
			machine
		),
		instantiated_recipe(
			"recipe_3==",
			AdaptedRecipe(
				eu_per_tick=-2,
				processing_time=2,
				amperage=1,
				inputs=frozendict({MaterialGroup([intermediate_material_left]): -1}),
				output_specifications=frozendict({0: (output_material, 1, 1)}),
			),
			machine
		),
		instantiated_recipe(
			"recipe_4==",
			AdaptedRecipe(
				eu_per_tick=-30,
				processing_time=15,
				amperage=1,
				inputs=frozendict({MaterialGroup([intermediate_material_right]): -1}),
				output_specifications=frozendict({0: (output_material, 2, 1)}),
			),
			machine
		),
	]
	config = CraftingChainConfig.__new__(CraftingChainConfig)
	config.inputs = {input_material}
	config.outputs = {output_material}
	config.infinite_materials = {infinite_material}
	config.weights = {output_material: 1}
	config.infinite_production_weights = {infinite_material: 0.0}
	config.lower_bounds = {input_material: -10.0}
	config.upper_bounds = {}
	config.equalities = {}
	config.time = "60s"
	config.max_voltage_tier = VoltageTier.LV
	config.machine_limit = 100

	finder = CraftingChainFinder(
		instantiated_recipes=recipes,
		materials=[
			input_material, intermediate_material_left, intermediate_material_right, output_material, 
			infinite_material
		],
		config=config,
		machine_limit=100,
	)

	
	optimization_response = finder.get_default_mixed_integer_solution()
	assert optimization_response.success
	assert len(optimization_response.determined_solutions) == 1
	solution = optimization_response.pick_solution()

	# print((finder.p, finder.q, finder.r))
	# print(solution.solution_vector.vector)
	# print()
	# for row in finder.mixed_integer_objective_problem.solution_space.constraint_matrix.toarray():
	# 	print(row)
	# print()
	# print(finder.mixed_integer_objective_problem.solution_space.constraint_bounds)
	# print(finder.mixed_integer_objective_problem.solution_space.lower_bounds)
	# print(finder.mixed_integer_objective_problem.solution_space.upper_bounds)
	# print(finder.mixed_integer_objective_problem.solution_space.integer_indices)
	# print(finder.mixed_integer_objective_problem.cost_vectors[CostVectorType.RECIPE_COST_VECTOR])
	# print(finder.mixed_integer_objective_problem.cost_vectors[CostVectorType.EU_COST_VECTOR])
	# print(finder.mixed_integer_objective_problem.cost_vectors[CostVectorType.MACHINE_AMOUNT_COST_VECTOR])

	assert solution.solution_vector.vector == pytest.approx([0, 10, 0, 10, 10, 0, 1, 0, 3, 0])

	crafting_chain = finder.create_crafting_chain(solution)
	assert crafting_chain.total_material_needs[input_material] == pytest.approx(-10)
	assert crafting_chain.total_material_needs[infinite_material] == pytest.approx(-10)
	assert crafting_chain.total_material_needs[intermediate_material_left] == pytest.approx(0)
	assert crafting_chain.total_material_needs[intermediate_material_right] == pytest.approx(0)
	assert crafting_chain.total_material_needs[output_material] == pytest.approx(20)

	assert crafting_chain.get_machine_amount("recipe_1==0") == pytest.approx(0)
	assert crafting_chain.get_machine_amount("recipe_2==0") == pytest.approx(0.5)
	assert crafting_chain.get_machine_amount("recipe_3==0") == pytest.approx(0)
	assert crafting_chain.get_machine_amount("recipe_4==0") == pytest.approx(2.5)
	