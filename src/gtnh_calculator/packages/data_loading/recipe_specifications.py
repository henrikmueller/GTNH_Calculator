import logging
from typing import Dict

from ..recipes.material import Material, MaterialList
from ..recipes.machine_type_books import MachineTypeBook, MachineType
from ..recipes.recipe_options.recipe_options import RecipeOptions
from ..utility.general_utility import str_to_float

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class RecipeSpecification:
    id: int
    exclude: bool
    base_machine_type: MachineType
    recipe_materials: Dict[Material, float]
    eu_per_tick: float
    processing_time: float
    total_eu: float
    recipe_options: RecipeOptions
    tag: str
    chance_based: list[Material]
    cap: float | None

    def __init__(
            self,
            material_list: MaterialList,
            machine_type_book: MachineTypeBook,
            id: str,
            exclude: str,
            base_machine_type_name: str,
            inputs: str,
            outputs: str,
            eu_per_tick: str,
            processing_time: str,
            total_eu: str,
            recipe_options: str,
            tag: str,
            chance_based: str,
            cap: str
    ):
        materials = material_list.materials_by_name
        self.id = int(id)
        self.exclude = exclude != ''

        processing_time = str_to_float(processing_time)
        eu_per_tick = str_to_float(eu_per_tick)
        total_eu = str_to_float(total_eu)

        missing_information = sum([processing_time is None, eu_per_tick is None, total_eu is None])
        if missing_information != 1:
            raise ValueError(f'Cannot import recipe with ID={id}. '
                             f'Fill exactly 2 of the following three: Processing Time, EU/t, Total EU')
        if processing_time is None:
            processing_time = total_eu / (20 * eu_per_tick)
        if eu_per_tick is None:
            eu_per_tick = total_eu / (20 * processing_time)
        if total_eu is None:
            total_eu = 20 * processing_time * eu_per_tick

        self.processing_time = processing_time
        self.eu_per_tick = eu_per_tick
        self.total_eu = total_eu

        inputs = {materials[name]: -amount for name, amount in RecipeSpecification.get_material_data(inputs)}
        outputs = {materials[name]: amount for name, amount in RecipeSpecification.get_material_data(outputs)}
        recipe_materials = inputs | {materials['EU']: -self.total_eu}
        for material, amount in outputs.items():
            if material in recipe_materials:
                # to not overwrite the input material
                recipe_materials[material] += amount
            else:
                recipe_materials[material] = amount
        self.chance_based = RecipeSpecification._get_materials(chance_based, materials)

        # This following for-loop is used to modify the amount of chance based materials, such that they will probably
        # never appear with total amount 0 in a recipe chain
        for material in self.chance_based:
            if material not in recipe_materials.keys():
                _LOGGER.warning(f'Chance based material {material} not specified as input or output '
                                f'for recipe with ID {id}')
                continue
            if recipe_materials[material] > 0:  # output
                recipe_materials[material] *= 0.9999999
            elif recipe_materials[material] < 0:  # input
                recipe_materials[material] *= 1.0000001
            else:
                _LOGGER.warning(f'Chance based material {material} has amount 0 in recipe with ID {id}')

        self.recipe_materials = recipe_materials
        self.base_machine_type = machine_type_book.get_machine_type(base_machine_type_name)
        if self.base_machine_type is None:
            raise ValueError(f'Machine type not found: "{base_machine_type_name}". '
                             f'Please specify in machine_types.yaml')

        self.recipe_options = RecipeOptions.get_recipe_options(recipe_options)
        self.tag = tag
        self.cap = str_to_float(cap)

    @classmethod
    def get_material_data(cls, data: str) -> list[tuple[str, float]]:
        data_list = [entry.strip() for entry in data.split(',')]
        material_data = []
        for entry in data_list:
            index = entry.find(' ')
            try:
                material_data.append((entry[index + 1:].replace(',', '.'), float(entry[:index])))
            except ValueError:
                continue
        return material_data

    @classmethod
    def _get_materials(cls, data: str, materials: Dict[str, Material]) -> list[Material]:
        material_names = [m.strip() for m in data.split(',') if m and not m.isspace()]
        for name in material_names:
            if name not in materials.keys():
                raise ValueError(f'{name} is not a valid material.')
        return [materials[name] for name in material_names]
