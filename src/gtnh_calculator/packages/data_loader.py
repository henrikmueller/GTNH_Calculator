import pandas as pd
from math import ceil, log, isnan, nan
import logging

from .recipes.recipe_book import RecipeBook
from .recipes.recipe import Recipe
from .recipes.material import Material, MaterialList
from .recipes.machine import Machine
from .recipes.parallel_machine_data import parallel_machine_data
from .recipes.voltage_tiers import VoltageTier

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


def load_data(gid: int) -> RecipeBook:
    sheet_id = "1OSog0iIKua5T7ms0Iv9OZxCR1Qw45QSPtZd7EDP-FK4"
    df = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?gid={gid}&format=csv")

    def fix_cell(entry) -> str:
        if isinstance(entry, float) and isnan(entry):
            return ''
        return entry

    df = df.map(fix_cell)

    def get_material_data(data: str) -> list[tuple[str, float]]:
        data_list = [entry.strip() for entry in data.split(',')]
        material_data = []
        for entry in data_list:
            index = entry.find(' ')
            try:
                material_data.append((entry[index+1:].replace(',', '.'), float(entry[:index])))
            except ValueError:
                continue
        return material_data

    materials = {'EU': Material(0, 'EU')}
    count = 1
    for _, row in df.iterrows():
        material_data = get_material_data(row['Inputs']) + get_material_data(row['Outputs'])
        for name, _ in material_data:
            if name not in materials.keys():
                materials[name] = Material(count, name)
                count += 1
    materials_by_id = {}
    for material in materials.values():
        materials_by_id[material.id] = material
    material_list = MaterialList(materials_by_name=materials, materials_by_id=materials_by_id)

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

        log_term = log(abs(eu_per_tick), 2) - 1 if abs(eu_per_tick) > 1 else 0
        voltage_tier = max(ceil(log_term / 2) - 1, 0) if eu_per_tick != 0 else -1
        inputs = {materials[name]: -amount for name, amount in get_material_data(row['Inputs'])}
        outputs = {materials[name]: amount for name, amount in get_material_data(row['Outputs'])}

        parallel_voltage_tier = VoltageTier.to_voltage_tier(row['Parallel Voltage'])
        if parallel_voltage_tier >= 1:
            parallel_data = parallel_machine_data(row['Machine'])
            machine = Machine(name=parallel_data.name, parallels=parallel_data.get_parallels(parallel_voltage_tier),
                              voltage_tier=parallel_voltage_tier)
            effective_parallels, overclocks = parallel_data.effective_parallels_and_overclocks(eu_per_tick,
                                                                                               parallel_voltage_tier)
            perfect_overclocks = min(overclocks, parallel_data.perfect_overclocks)
            total_eu *= parallel_data.energy_multiplier * effective_parallels * 2**(overclocks - perfect_overclocks)
            processing_time /= 4**perfect_overclocks * 2**(overclocks - perfect_overclocks)
            recipe_materials = ({n: effective_parallels * a for n, a in inputs.items()} |
                                {n: effective_parallels * a for n, a in outputs.items()} | {materials['EU']: -total_eu})
        else:
            machine = Machine(name=row['Machine'], parallels=1, voltage_tier=voltage_tier)
            recipe_materials = inputs | outputs | {materials['EU']: -total_eu}

        return Recipe(
            id=row['Recipe ID'],
            materials=recipe_materials,
            machine=machine,
            processing_time=processing_time,
            weight=float(row['Weight']) if row['Weight'] != '' else 1,
            cap=float(row['Machine Cap']) if row['Machine Cap'] != '' else nan
        )

    recipes = {}
    for _, row in df.iterrows():
        recipe = create_recipe_from(row)
        if recipe is not None:
            recipes[row['Recipe ID']] = recipe

    return RecipeBook(recipes, material_list)
