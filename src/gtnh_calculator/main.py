import logging
import sys

from packages.recipes.recipe_graph import RecipeHypergraph
from packages.crafting_chains.crafting_chain_finder import CraftingChainFinder
from packages.data_loading.data_loader import load_data
from packages.configs.game_state_config import load_game_state
from packages.utility.general_utility import time_to_seconds
from packages.recipes.machine_options.machine_option_books import load_possible_machine_options
from packages.utility.general_utility import load_file, format_float
from packages.database_extraction.database_extractor import DatabaseExtractor

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


"""
------------------------------------------------------------------------------------------------------------------------
    Recipe Database Extraction
------------------------------------------------------------------------------------------------------------------------
"""


"""
------------------------------------------------------------------------------------------------------------------------
    Initialization Code
------------------------------------------------------------------------------------------------------------------------
"""

# default_gid = 0
# air_filter_gid = 1730504225
# hog_gid = 1514208585
#
# path_plat_line = 'config/config_plat_line.yaml'
# path_bastnasite = 'config/config_bastnasite.yaml'
#
# machine_options_path = 'config/fixed_settings/machine_options.yaml'
# machine_options_book = load_possible_machine_options(machine_options_path)
# config, recipe_book, machine_type_book = load_data(path_bastnasite, machine_options_book)
#
# game_state_path = 'config/game_state/game_state.yaml'
# game_state = load_game_state(load_file(game_state_path), recipe_book.material_list)
# print(game_state)
#
# recipe_hypergraph = RecipeHypergraph(recipe_book)
# recipe_graph = recipe_hypergraph.get_recipe_graph()

"""
------------------------------------------------------------------------------------------------------------------------
    Recipe Chain Calculation
------------------------------------------------------------------------------------------------------------------------
"""

# crafting_chain_finder = CraftingChainFinder(recipe_book, machine_limit=config.machine_limit)
# crafting_chain = crafting_chain_finder.optimal_crafting_chain(
#     machine_type_book, machine_options_book, config, recipe_weight_factor=0.0000001
# )
#
# if crafting_chain is not None:
#     time, _ = time_to_seconds(config.time)
#     display_interval, display_interval_name = time_to_seconds(config.display_interval)
#     if display_interval != 1:
#         display_interval_name = display_interval_name + 's'
#
#     # crafting_chain.draw_graph(
#     #     time_factor=display_interval / time,
#     #     time_interval=f'{display_interval} {display_interval_name}',
#     #     input_materials=config.inputs.union(config.infinite_materials)
#     # )
#     crafting_chain.statistics(
#         time_factor=display_interval / time,
#         time_interval=f'{display_interval} {display_interval_name}',
#         do_print=True
#     )
