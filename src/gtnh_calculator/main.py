import logging

from packages.recipes.recipe_graph import RecipeHypergraph
from packages.recipes.material import get_materials, get_material_dict
from packages.crafting_chains.crafting_chain_finder import CraftingChainFinder
from packages.data_loader import load_data

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


"""
------------------------------------------------------------------------------------------------------------------------
    Initialization Code
------------------------------------------------------------------------------------------------------------------------
"""

default_gid = 0
hog_gid = 1514208585
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
# infinite_materials = ['Water', 'Wood Log', 'Salt Comb']
# mode = 'Fixed_Input'
# inputs = ['Oil Comb']
# outputs = ['EU']
# fixed_amount = 9.8  # 130.909 / 60
# material_weights = {
#     'EU': 1
# }
# time = '60s'
# time_interval = '1s'
# recipe_weight_factor = 0.0001

"""
------------------------------------------------------------------------------------------------------------------------
    Mode Fixed_Output
------------------------------------------------------------------------------------------------------------------------
"""

mode = 'Fixed_Output'
infinite_materials = ['Water', 'Oxygen', 'Hydrogen', 'Nitrogen', 'EU']
inputs = ['Palladium Enriched Ammonia', 'Carbon Dust', 'Ammonia', 'Sulfuric Acid', 'Sodium Hydroxide Dust']
outputs = ['Palladium Dust']
fixed_amount = 1
material_weights = {
    'Palladium Enriched Ammonia': -1000,
    'Carbon Dust': -1,
    'Ammonia': -1,
    'Sulfuric Acid': -1,
    'Sodium Hydroxide Dust': -1,
}
material_caps = {

}
time = '10s'
time_interval = '1s'
recipe_weight_factor = 0.00001

# mode = 'Fixed_Output'
# infinite_materials = ['Water', 'Sulfur Dust']
# inputs = ['Wood Log']
# outputs = ['EU']
# fixed_amount = 4000  # 9400
# material_weights = {
#     'Wood Log': -1,
# }
# time = '1t'
# time_interval = '1t'
# recipe_weight_factor = 0.00001

"""
------------------------------------------------------------------------------------------------------------------------
    Recipe Chain Calculation
------------------------------------------------------------------------------------------------------------------------
"""

infinite_materials = set(get_materials(materials, infinite_materials))
inputs = set(get_materials(materials, inputs))
outputs = set(get_materials(materials, outputs))
material_weights = get_material_dict(materials, material_weights)
material_caps = get_material_dict(materials, material_caps)
crafting_chain_finder = CraftingChainFinder(recipe_book)
crafting_chain_finder.draw_optimal_crafting_chain(
    inputs=inputs, outputs=outputs, fixed_amount=fixed_amount, time=time, time_interval=time_interval,
    material_weights=material_weights, recipe_weight_factor=recipe_weight_factor, mode=mode,
    infinite_materials=infinite_materials, material_caps=material_caps
)
