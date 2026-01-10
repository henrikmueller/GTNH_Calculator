import pandas as pd
from math import isnan
import logging
from typing import Dict

from .recipes.recipe_book import RecipeBook
from .recipes.recipe import Recipe, RawRecipe
from .recipes.material import Material, MaterialList
from .recipes.machine import Machine
from .recipes.machine_type_books import MachineTypeBook
from .recipes.voltage_tiers import VoltageTier
from .recipes.machine_options.machine_option_books import MachineOptionsBook
from .recipes.recipe_options.recipe_options import RecipeOptions

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


def _get_material_data(data: str) -> list[tuple[str, float]]:
    data_list = [entry.strip() for entry in data.split(',')]
    material_data = []
    for entry in data_list:
        index = entry.find(' ')
        try:
            material_data.append((entry[index + 1:].replace(',', '.'), float(entry[:index])))
        except ValueError:
            continue
    return material_data


def _get_materials(data: str, materials: Dict[str, Material]) -> list[Material]:
    material_names = [m.strip() for m in data.split(',') if m and not m.isspace()]
    for name in material_names:
        if name not in materials.keys():
            raise ValueError(f'{name} is not a valid material.')
    return [materials[name] for name in material_names]


def load_materials(gid: int) -> MaterialList:
    sheet_id = "1OSog0iIKua5T7ms0Iv9OZxCR1Qw45QSPtZd7EDP-FK4"
    df = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?gid={gid}&format=csv")

    def fix_cell(entry) -> str:
        if isinstance(entry, float) and isnan(entry):
            return ''
        return entry

    df = df.map(fix_cell)

    materials = {'EU': Material(0, 'EU')}
    count = 1
    for _, row in df.iterrows():
        material_data = _get_material_data(row['Inputs']) + _get_material_data(row['Outputs'])
        for name, _ in material_data:
            if name not in materials.keys():
                materials[name] = Material(count, name)
                count += 1
    materials_by_id = {}
    for material in materials.values():
        materials_by_id[material.id] = material
    return MaterialList(materials_by_name=materials, materials_by_id=materials_by_id)


def load_data(
        gid: int,
        material_list: MaterialList,
        machine_options_book: MachineOptionsBook,
        config
) -> tuple[RecipeBook, MachineTypeBook]:
    sheet_id = "1OSog0iIKua5T7ms0Iv9OZxCR1Qw45QSPtZd7EDP-FK4"
    df = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?gid={gid}&format=csv")

    def fix_cell(entry) -> str:
        if isinstance(entry, float) and isnan(entry):
            return ''
        return entry

    df = df.map(fix_cell)
    materials = material_list.materials_by_name
    machine_type_book = MachineTypeBook.load_machine_type_book('config/fixed_settings/machine_types.yaml')

    def create_recipe_from(row) -> Recipe | None:
        def str_to_float(text: str) -> float | None:
            if text == '':
                return None
            if isinstance(text, str):
                text = text.replace(',', '.')
            return float(text)

        if row['Exclude'] != '':
            return None

        processing_time = str_to_float(row['Processing Time'])
        eu_per_tick = str_to_float(row['EU/t'])
        total_eu = str_to_float(row['Total EU'])

        missing_information = sum([processing_time is None, eu_per_tick is None, total_eu is None])
        if missing_information != 1:
            _LOGGER.warning(f'Cannot import recipe with ID={row['Recipe ID']}. '
                            f'Fill exactly 2 of the following three: Processing Time, EU/t, Total EU')
            return None
        if processing_time is None:
            processing_time = total_eu / (20 * eu_per_tick)
        if eu_per_tick is None:
            eu_per_tick = total_eu / (20 * processing_time)
        if total_eu is None:
            total_eu = 20 * processing_time * eu_per_tick

        inputs = {materials[name]: -amount for name, amount in _get_material_data(row['Inputs'])}
        outputs = {materials[name]: amount for name, amount in _get_material_data(row['Outputs'])}
        recipe_materials = inputs | {materials['EU']: -total_eu}
        for material, amount in outputs.items():
            if material in recipe_materials:
                # to not overwrite the input material
                recipe_materials[material] += amount
            else:
                recipe_materials[material] = amount
        chance_based = _get_materials(row['Chance Based'], materials)

        # This following for-loop is used to modify the amount of chance based materials, such that they will probably
        # never appear with total amount 0 in a recipe chain
        for material in chance_based:
            if material not in recipe_materials.keys():
                _LOGGER.warning(f'Chance based material {material} not specified as input or output '
                                f'for recipe with ID {row['Recipe ID']}')
                continue
            if recipe_materials[material] > 0:  # output
                recipe_materials[material] *= 0.9999999
            elif recipe_materials[material] < 0:  # input
                recipe_materials[material] *= 1.0000001
            else:
                _LOGGER.warning(f'Chance based material {material} has amount 0 in recipe with ID {row['Recipe ID']}')

        voltage_tier = VoltageTier.voltage_tier_by_eu(eu_per_tick)
        recipe_options = RecipeOptions.get_recipe_options(row['Recipe Options'])
        base_recipe = RawRecipe(
            materials=recipe_materials,
            processing_time=processing_time,
            recipe_options=recipe_options,
            chance_based=chance_based
        )

        base_machine_type = machine_type_book.get_machine_type(row['Machine'])
        if base_machine_type is None:
            raise ValueError(f'Machine type not found: "{row['Machine']}". Please specify in machine_types.yaml')
        if base_machine_type.avoid_to_use:
            parallel_machine_type = machine_type_book.get_parallel_option(base_machine_type)
            if config.unlocked_voltage_tier >= parallel_machine_type.unlock_tier:
                base_machine_type = parallel_machine_type
        machine_type = base_machine_type

        # parallel_voltage_tier = VoltageTier.to_voltage_tier(row['Parallel Voltage'])
        # if parallel_voltage_tier >= 1:
        #     machine_type = machine_type_book.get_parallel_option(base_machine_type)
        #     voltage_tier = parallel_voltage_tier
        # else:
        #     machine_type = base_machine_type

        specified_options = machine_options_book.get_machine_options_from_string(row['Machine Options'])
        default_options = machine_options_book.get_default_options(
            base_recipe, machine_type, config.default_machine_options
        )
        machine = Machine(
            machine_type=machine_type, voltage_tier=voltage_tier,
            machine_options=specified_options.maximum(default_options)
        )

        """
            Create recipe
        """

        # Adapt recipe based on machine and its setting (e.g. EBF coils)
        raw_recipe = machine.fit_recipe(base_recipe)
        cap = str_to_float(row['Cap']) if row['Cap'] != '' else (
            config.max_multiblock_machines if machine.machine_type.multiblock else config.max_singleblock_machines
        )

        return Recipe(
            id=row['Recipe ID'],
            base_recipe=base_recipe,
            raw_recipe=raw_recipe,
            base_machine_type=base_machine_type,
            machine=machine,
            cap=cap,
            cap_specified=row['Cap'] != ''
        )

    recipes = {}
    for _, row in df.iterrows():
        recipe = create_recipe_from(row)
        if recipe is not None:
            recipes[row['Recipe ID']] = recipe

    return RecipeBook(recipes, material_list), machine_type_book
