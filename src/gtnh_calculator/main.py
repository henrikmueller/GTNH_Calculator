import logging

from packages.recipes.recipe_graph import RecipeHypergraph
from packages.recipes.material import get_materials, get_material_dict
from packages.crafting_chains.crafting_chain_finder import CraftingChainFinder
from packages.configs.config import load_config
from packages.utility.general_utility import time_to_seconds

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


"""
------------------------------------------------------------------------------------------------------------------------
    Initialization Code
------------------------------------------------------------------------------------------------------------------------
"""

default_gid = 0
air_filter_gid = 1730504225
hog_gid = 1514208585
gid_rocket_fuel = 23007754

path_nitrobenzene = 'config/config_nitrobenzene.yaml'
path_plat_line = 'config/config_plat_line.yaml'

config, recipe_book = load_config(path_plat_line)
print(config)

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
# display_interval = '1s'
# recipe_weight_factor = 0.0001

"""
------------------------------------------------------------------------------------------------------------------------
    Mode Fixed_Output
------------------------------------------------------------------------------------------------------------------------
"""

# mode = 'Fixed_Output'
# infinite_materials = ['Water', 'Oxygen', 'Hydrogen', 'Quicklime Dust', 'Carbon Dust', 'Saltpeter Dust']
# inputs = ['Lepidolite Dust', 'Chrome Dust', 'Benzene', 'Ethylene',
#           '1.2-Dimethylbenzene', 'Anthracene', 'Sulfuric Acid']
# outputs = ['Air Filter [Tier 2]']
# fixed_amount = 1
# material_weights = {
#     'Lepidolite Dust': -1,
#     'Chrome Dust': -1,
#     'Benzene': -1,
#     'Ethylene': -1,
#     '1.2-Dimethylbenzene': -1,
#     'Anthracene': -1,
#     'Sulfuric Acid': -1
# }
# material_caps = {
#
# }
# time = '60s'
# display_interval = '1s'
# recipe_weight_factor = 0.00001

"""
------------------------------------------------------------------------------------------------------------------------
    Recipe Chain Calculation
------------------------------------------------------------------------------------------------------------------------
"""

# infinite_materials = set(get_materials(materials, infinite_materials))
# inputs = set(get_materials(materials, inputs))
# outputs = set(get_materials(materials, outputs))
# material_weights = get_material_dict(materials, material_weights)
# material_caps = get_material_dict(materials, material_caps)

crafting_chain_finder = CraftingChainFinder(recipe_book)
crafting_chain = crafting_chain_finder.draw_optimal_crafting_chain(config, recipe_weight_factor=0.00001)

if crafting_chain is not None:
    time, _ = time_to_seconds(config.time)
    display_interval, display_interval_name = time_to_seconds(config.display_interval)

    crafting_chain.draw(
        materials=recipe_book.material_list.materials_by_id,
        recipes=recipe_book.recipes,
        time=time,
        time_factor=display_interval / time,
        time_interval_name=display_interval_name,
        input_materials=config.inputs.union(config.infinite_materials)
    )
