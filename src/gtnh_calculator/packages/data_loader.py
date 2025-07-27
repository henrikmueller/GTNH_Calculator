import pandas as pd
from math import floor, log, isnan
import logging

from .recipes.recipe_book import RecipeBook
from .recipes.recipe import Recipe
from .recipes.material import Material, MaterialList
from .recipes.machine import Machine

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

    machines = {}
    for _, row in df.iterrows():
        name = row['Machine']
        machines[name] = Machine(name)

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
        def convert_entry(entry):
            if isinstance(entry, str):
                return entry.replace(',', '.')
            return entry

        if row['Exclude'] != '':
            return None

        processing_time = float(convert_entry(row['Processing Time'])) if row['Processing Time'] else None
        eu_per_tick = float(convert_entry(row['EU/t'])) if row['EU/t'] else None
        total_eu = float(convert_entry(row['Total EU'])) if row['Total EU'] else None

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

        voltage_tier = max(floor(log(abs(eu_per_tick), 2) / 2) - 1, 0)
        inputs = {materials[name]: -amount for name, amount in get_material_data(row['Inputs'])}
        outputs = {materials[name]: amount for name, amount in get_material_data(row['Outputs'])}
        return Recipe(
            id=row['Recipe ID'],
            materials=inputs | outputs | {materials['EU']: -total_eu},
            machine=machines[row['Machine']],
            voltage_tier=voltage_tier,
            processing_time=processing_time,
            weight=float(row['Weight']) if row['Weight'] != '' else 1
        )

    recipes = {}
    for _, row in df.iterrows():
        recipe = create_recipe_from(row)
        if recipe is not None:
            recipes[row['Recipe ID']] = recipe

    return RecipeBook(recipes, material_list)
