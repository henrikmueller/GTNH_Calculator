import logging
from typing import Dict

from ..recipes.recipe_book import RecipeBook
from ..recipes.recipe import Recipe, RawRecipe
from ..recipes.material import MaterialList
from ..recipes.machine import Machine
from ..recipes.machine_type_books import MachineTypeBook
from ..recipes.voltage_tiers import VoltageTier
from ..recipes.machine_options.machine_option_books import MachineOptionsBook
from ..data_loading.recipe_specifications import RecipeSpecification
from ..configs.crafting_chain_config import CraftingChainConfig

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


def load_recipe_book(
    material_list: MaterialList,
    machine_type_book: MachineTypeBook,
    machine_options_book: MachineOptionsBook,
    recipe_specifications: Dict[int, RecipeSpecification],
    config: CraftingChainConfig
) -> RecipeBook:
    def create_recipe_from(recipe_specification: RecipeSpecification) -> Recipe | None:
        if recipe_specification.exclude:
            return None

        voltage_tier = VoltageTier.voltage_tier_by_eu(recipe_specification.eu_per_tick)
        base_recipe = RawRecipe(
            materials=recipe_specification.recipe_materials,
            processing_time=recipe_specification.processing_time,
            recipe_options=recipe_specification.recipe_options,
            chance_based=recipe_specification.chance_based
        )

        base_machine_type = recipe_specification.base_machine_type
        if recipe_specification.base_machine_type.avoid_to_use:
            parallel_machine_type = machine_type_book.get_parallel_option(recipe_specification.base_machine_type)
            if config.unlocked_voltage_tier >= parallel_machine_type.unlock_tier:
                base_machine_type = parallel_machine_type
        machine_type = recipe_specification.base_machine_type

        default_options = machine_options_book.get_default_options(
            base_recipe, machine_type, config.default_machine_options
        )
        machine = Machine(
            machine_type=machine_type, voltage_tier=voltage_tier,
            machine_options=default_options
        )

        # Adapt recipe based on machine and its setting (e.g. EBF coils)
        raw_recipe = machine.fit_recipe(base_recipe)
        cap = recipe_specification.cap if recipe_specification.cap is not None else (
            config.max_multiblock_machines if machine.machine_type.multiblock else config.max_singleblock_machines
        )

        return Recipe(
            id=recipe_specification.id,
            base_recipe=base_recipe,
            raw_recipe=raw_recipe,
            base_machine_type=base_machine_type,
            machine=machine,
            cap=cap,
            cap_specified=recipe_specification.cap is not None
        )

    recipes = {}
    for recipe_specification in recipe_specifications.values():
        recipe = create_recipe_from(recipe_specification)
        if recipe is not None:
            recipes[recipe_specification.id] = recipe
    return RecipeBook(recipes, material_list)
