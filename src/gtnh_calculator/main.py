import logging

from packages.recipes.recipe_hypergraph import build_recipe_hypergraph
from packages.crafting_chains.crafting_chain_finder import CraftingChainFinder
from packages.data_loader import load_data

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


recipes, material_list, machines = load_data()
materials = material_list.materials_by_name
recipe_hypergraph = build_recipe_hypergraph(recipes)

infinite_materials = {
    materials['Water']
}
inputs = {
    materials['Wood Log'], materials['Sulfur Dust'],
}.union(infinite_materials)
output = (materials['EU'], 8000)
time = '1t'
time_interval = '1s'
weights = {
    materials['Wood Log']: -1,
}
for material in infinite_materials:
    weights[material] = 0
excluded_materials = set(
    # not implemented yet
)

crafting_chain_finder = CraftingChainFinder(material_list, recipes)
crafting_chain_finder.draw_optimal_crafting_chain(
    inputs=inputs, output_spec=output, time=time, time_interval=time_interval, weights=weights,
    excluded_materials=excluded_materials
)

