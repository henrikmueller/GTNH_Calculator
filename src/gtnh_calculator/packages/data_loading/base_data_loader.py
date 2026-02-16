import pandas as pd
from math import isnan
import logging
from typing import Dict

from ..recipes.material import Material, MaterialList
from ..recipes.machine_type_books import MachineTypeBook
from ..data_loading.recipe_specifications import RecipeSpecification

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


def load_base_data(gid: int) -> tuple[MaterialList, MachineTypeBook, Dict[int, RecipeSpecification]]:
    def load_materials(df: pd.DataFrame) -> MaterialList:
        materials = {'EU': Material(0, 'EU')}
        count = 1
        for _, row in df.iterrows():
            material_data = (RecipeSpecification.get_material_data(row['Inputs']) +
                             RecipeSpecification.get_material_data(row['Outputs']))
            for name, _ in material_data:
                if name not in materials.keys():
                    materials[name] = Material(count, name)
                    count += 1
        materials_by_id = {material.id: material for material in materials.values()}
        return MaterialList(materials_by_name=materials, materials_by_id=materials_by_id)

    sheet_id = "1OSog0iIKua5T7ms0Iv9OZxCR1Qw45QSPtZd7EDP-FK4"
    df = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?gid={gid}&format=csv")

    def fix_cell(entry) -> str:
        if isinstance(entry, float) and isnan(entry):
            return ''
        return entry

    df = df.map(fix_cell)
    material_list = load_materials(df)
    machine_type_book = MachineTypeBook.load_machine_type_book('config/fixed_settings/machine_types.yaml')

    recipe_specifications = {}
    for _, row in df.iterrows():
        recipe_specification = RecipeSpecification(
            material_list,
            machine_type_book,
            id=row['Recipe ID'],
            exclude=row['Exclude'],
            base_machine_type_name=row['Machine'],
            inputs=row['Inputs'],
            outputs=row['Outputs'],
            eu_per_tick=row['EU/t'],
            processing_time=row['Processing Time'],
            total_eu=row['Total EU'],
            recipe_options=row['Recipe Options'],
            tag=row['Tag'],
            chance_based=row['Chance Based'],
            cap=row['Cap']
        )
        recipe_specifications[recipe_specification.id] = recipe_specification
    return material_list, machine_type_book, recipe_specifications
