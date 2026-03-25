import logging
from io import BytesIO

from ..data_loading.base_data_loader import load_base_data
from ..data_loading.recipe_loader import load_recipe_book
from ..configs.crafting_chain_config import load_config, CraftingChainConfig
from ..recipes.machine_options.machine_option_books import MachineOptionsBook
from ..recipes.machine_type_books import MachineTypeBook
from ..recipes.recipe_book import RecipeBook
from ..exceptions import DataLoadingException
from ..utility.general_utility import load_file

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


def load_data(
    file_or_filepath: BytesIO | str, machine_options_book: MachineOptionsBook
) -> tuple[CraftingChainConfig, RecipeBook, MachineTypeBook]:
    try:
        yaml_data = load_file(file_or_filepath)
        table_gid = yaml_data['table_gid']
        material_list, machine_type_book, recipe_specifications = load_base_data(table_gid)

        del yaml_data['table_gid']
        config = load_config(yaml_data, material_list, machine_options_book)

        recipe_book = load_recipe_book(
            material_list, machine_type_book, machine_options_book, recipe_specifications, config)
        return config, recipe_book, machine_type_book
    except Exception as e:
        raise DataLoadingException(e)
