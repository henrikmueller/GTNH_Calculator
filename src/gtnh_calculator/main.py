import logging

from packages.recipes.recipe_graph import RecipeHypergraph
from packages.recipes.material import get_materials, get_material_dict
from packages.crafting_chains.crafting_chain_finder import CraftingChainFinder
from packages.data_loader import load_data

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


"""
------------------------------------------------------------------------------------------------------------------------
    Initialization Code
------------------------------------------------------------------------------------------------------------------------
"""

default_gid = 0
gid_rocket_fuel = 23007754
gid_nitrobenzene = 172535012
recipe_book = load_data(default_gid)
materials = recipe_book.material_list.materials_by_name
recipe_hypergraph = RecipeHypergraph(recipe_book)
recipe_graph = recipe_hypergraph.get_recipe_graph()


"""
------------------------------------------------------------------------------------------------------------------------
    Mode Fixed_Input
------------------------------------------------------------------------------------------------------------------------
"""

# infinite_materials = [
#     'Water', 'Sodium Dust', 'Zinc Dust', 'Chlorine', 'Hydrofluoric Acid', 'Saltpeter Dust', 'Sulfuric Acid',
#     'Calcium Dust', 'Potassium Dust', 'Hydrogen', 'Oxygen', 'Nitrogen', 'Fluorine', 'Hydrogen Sulfide', 'Salt',
#     'Carbon Dust', 'Sulfur Dust'
# ]
# mode = 'Fixed_Input'
# inputs = ['Platinum Comb']
# outputs = ['Platinum Dust, Ruthenium Dust, Iridium Dust, Palladium Dust, Rhodium Dust']
# fixed_amount = 1
# material_weights = {
#     'Platinum Comb': -1,
#     'Platinum Dust': 1,
#     'Ruthenium Dust': 1,
#     'Iridium Dust': 1,
#     'Palladium Dust': 1,
#     'Rhodium Dust': 1
# }
# time = '1s'
# time_interval = '1s'
# recipe_weight_factor = 0.00001

"""
------------------------------------------------------------------------------------------------------------------------
    Mode Fixed_Input
------------------------------------------------------------------------------------------------------------------------
"""

mode = 'Fixed_Output'
infinite_materials = ['Water']
inputs = ['Oil Drone', 'Wood Log', 'Salt Drone']
outputs = ['EU']
fixed_amount = 32000
material_weights = {
    'Oil Drone': -1,
    'Salt Drone': -1,
    'Wood Log': -1,
}
time = '1t'
time_interval = '1t'
recipe_weight_factor = 0.00001

"""
------------------------------------------------------------------------------------------------------------------------
    Recipe Chain Calculation
------------------------------------------------------------------------------------------------------------------------
"""

infinite_materials = set(get_materials(materials, infinite_materials))
inputs = set(get_materials(materials, inputs))
outputs = set(get_materials(materials, outputs))
material_weights = get_material_dict(materials, material_weights)
crafting_chain_finder = CraftingChainFinder(recipe_book)
crafting_chain_finder.draw_optimal_crafting_chain(
    inputs=inputs, outputs=outputs, fixed_amount=fixed_amount, time=time, time_interval=time_interval,
    material_weights=material_weights, recipe_weight_factor=recipe_weight_factor, mode=mode,
    infinite_materials=infinite_materials
)
