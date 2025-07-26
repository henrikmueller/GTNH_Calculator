import logging

from packages.recipes.recipe_graph import RecipeGraph, RecipeHypergraph
from packages.recipes.recipe_book import RecipeBook
from packages.crafting_chains.crafting_chain_finder import CraftingChainFinder
from packages.data_loader import load_data

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


recipes, material_list, machines, recipe_weights = load_data()
recipe_book = RecipeBook(recipes, material_list)
materials = material_list.materials_by_name
recipe_hypergraph = RecipeHypergraph(recipe_book)
recipe_graph = recipe_hypergraph.get_recipe_graph()

# infinite_materials = {
#     materials['Water'], materials['Sodium Dust'], materials['Zinc Dust'], materials['Chlorine'],
#     materials['Hydrofluoric Acid'], materials['Saltpeter Dust'],
#     materials['Sulfuric Acid'], materials['Calcium Dust'],
#     materials['Potassium Dust'], materials['Hydrogen'], materials['Oxygen'], materials['Nitrogen'],
#     materials['Fluorine'], materials['Hydrogen Sulfide'], materials['Salt'],
#     materials['Carbon Dust'], materials['Sulfur Dust']
# }
infinite_materials = {
    materials['Water'], materials['Salt']
}
inputs = {
    materials['Oil Drone'], materials['Wood Log'],  # materials['Sulfur Dust'], materials['Rape'],
    # materials['Oil'], materials['Heavy Oil'], materials['Carbon Dust']
}.union(infinite_materials)
output = (materials['High Octane Gasoline'], 10)
time = '1t'
time_interval = '1t'
recipe_weight_factor = 0.000001
weights = {
    materials['Oil Drone']: -1,
    materials['Wood Log']: -1
}
excluded_materials = set(
    # not implemented yet
)
excluded_recipes = set()
for material in infinite_materials:
    weights[material] = 0

print('Materials which cannot be produced from recipes and are not specified as input or infinite materials:')
for material in materials.values():
    if any([material in recipe.get_outputs() for recipe in recipes.values()]):
        continue
    if material in infinite_materials or material in inputs:
        continue
    print(material)
crafting_chain_finder = CraftingChainFinder(material_list, recipes, recipe_weights)
crafting_chain_finder.draw_optimal_crafting_chain(
    inputs=inputs, output_spec=output, time=time, time_interval=time_interval, weights=weights,
    recipe_weight_factor=recipe_weight_factor, excluded_materials=excluded_materials,
    excluded_recipes=excluded_recipes
)

input_spec = (materials['Platinum Comb'], 1)
weights = {
    materials['Platinum Dust']: 1,
    # materials['Rhodium Dust']: 1,
    # materials['Palladium Dust']: 1,
    # materials['Iridium Dust']: 1,
    # materials['Ruthenium Dust']: 1,
    # materials['Osmium Dust']: 1
}
# input_spec = (materials['Platinum Residue Dust'], 1)
# # weights specify the outputs
# weights = {
#     materials['Leach Residue Dust']: 1,
#     materials['Rhodium Dust']: 1
# }


for material in infinite_materials:
    weights[material] = 0

print('Materials which cannot be produced from recipes and are not specified as input or infinite materials:')
for material in materials.values():
    if any([material in recipe.get_outputs() for recipe in recipes.values()]):
        continue
    if material in infinite_materials or material == input_spec[0]:
        continue
    print(material)
crafting_chain_finder.output_maximizer(
    input_spec=input_spec, time=time, time_interval=time_interval, weights=weights,
    recipe_weight_factor=recipe_weight_factor, excluded_materials=excluded_materials,
    excluded_recipes=excluded_recipes, infinite_materials=infinite_materials
)

# recipe_hypergraph.get_crafting_chains(
#     start=[materials['Wood Log']],
#     end=[materials['Benzene']],
#     crafting_chain_finder=crafting_chain_finder
# )

