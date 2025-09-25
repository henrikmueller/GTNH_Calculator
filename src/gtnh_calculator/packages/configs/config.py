import logging
import yaml
from marshmallow import Schema, fields, post_load, validates, ValidationError
from typing import Dict

from ..recipes.material import Material
from ..utility.general_utility import str_to_float
from ..data_loader import load_data, load_materials
from ..recipes.recipe_book import RecipeBook
from ..recipes.machine_options.machine_option_books import MachineOptionsBook
from ..recipes.machine_options.machine_options import Coil

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class Config:
    inputs: set[Material]
    outputs: set[Material]
    infinite_materials: set[Material]
    weights: Dict[Material, float]
    lower_bounds: Dict[Material, float]
    upper_bounds: Dict[Material, float]
    equalities: Dict[Material, float]
    time: str
    display_interval: str
    mode: str
    default_coil: Coil | None

    def __init__(
        self,
        materials: Dict[str, Material],
        machine_options_book: MachineOptionsBook,
        inputs: list[str],
        outputs: list[str],
        infinite_materials: list[str],
        restrictions: list[str] | None,
        weights: Dict[str, float],
        time: str,
        display_interval: str,
        mode: str,
        default_coil: str
    ):
        input_specifications = [extract_substrings(input_string, materials) for input_string in inputs]
        self.inputs = set()
        for result in input_specifications:
            if result is None:
                continue
            if isinstance(result, Material):
                self.inputs.add(result)
            else:
                self.inputs.add(result[0])

        output_specifications = [extract_substrings(output_string, materials) for output_string in outputs]
        self.outputs = set()
        for result in output_specifications:
            if result is None:
                continue
            if isinstance(result, Material):
                self.outputs.add(result)
            else:
                self.outputs.add(result[0])

        self.infinite_materials = set(materials[m] for m in infinite_materials)
        self.weights = {
            materials[material_name]: weight for material_name, weight in weights.items()
        }
        self.time = time
        self.display_interval = display_interval
        self.mode = mode
        self.default_coil = machine_options_book.get_coil(default_coil)

        material_specifications = [t for t in input_specifications + output_specifications if isinstance(t, tuple)]
        if restrictions is not None:
            material_specifications += [extract_substrings(s, materials) for s in restrictions]
        self.lower_bounds = {}
        self.upper_bounds = {}
        self.equalities = {}
        for material, comparator, bound in material_specifications:
            match comparator:
                case '<=':
                    self.upper_bounds[material] = bound
                case '>=':
                    self.lower_bounds[material] = bound
                case '=':
                    self.equalities[material] = bound
                case _:
                    pass

    def __repr__(self) -> str:
        return f"""Config Object:
    inputs: {self.inputs}
    outputs: {self.outputs}
    infinite_materials: {self.infinite_materials}
    weights: {self.weights}
    lower_bounds: {self.lower_bounds}
    upper_bounds: {self.upper_bounds}
    equalities: {self.equalities}
    time: {self.time}
    display_interval: {self.display_interval}
    mode: {self.mode}
    default_coil: {self.default_coil}
        """


def load_config(path: str, machine_options_book: MachineOptionsBook) -> tuple[Config, RecipeBook]:
    class ConfigSchema(Schema):
        inputs = fields.List(fields.String(), required=True)
        outputs = fields.List(fields.String(), required=True)
        infinite_materials = fields.List(fields.String(), required=True)
        restrictions = fields.List(fields.String(), required=False, allow_none=True)
        weights = fields.Dict(keys=fields.String(), values=fields.Float())
        time = fields.String(required=True)
        display_interval = fields.String(required=True)
        mode = fields.String(required=True)
        default_coil = fields.String(required=True)

        @post_load
        def create_config(self, data, **kwargs) -> Config:
            return Config(materials, machine_options_book, **data)

        @validates('inputs')
        def validate_inputs(self, inputs: list[str], data_key: str) -> None:
            for input in inputs:
                if extract_substrings(input, materials) is None:
                    raise ValidationError(f'Invalid material specification: "{input}"')

        @validates('outputs')
        def validate_outputs(self, outputs: list[str], data_key: str) -> None:
            for output in outputs:
                if extract_substrings(output, materials) is None:
                    raise ValidationError(f'Invalid material specification: "{output}"')

        @validates('infinite_materials')
        def validate_infinite_materials(self, infinite_materials: list[str], data_key: str) -> None:
            for material_name in infinite_materials:
                if material_name not in materials.keys():
                    raise ValidationError(f'Unknown material in weights dictionary: "{material_name}"')

        @validates('restrictions')
        def validate_restrictions(self, restrictions: list[str] | None, data_key: str) -> None:
            if restrictions is None:
                return
            for r in restrictions:
                if not isinstance(extract_substrings(r, materials), tuple):
                    raise ValidationError(f'Unknown material restriction: "{r}"')

        @validates('weights')
        def validate_weights(self, weights: Dict[str, float], data_key: str) -> None:
            for key in weights.keys():
                if key not in materials.keys():
                    raise ValidationError(f'Unknown material in weights dictionary: "{key}"')

        @validates('mode')
        def validate_mode(self, mode: str, data_key: str) -> None:
            if mode not in ['Min', 'Max']:
                raise ValidationError(f'Invalid mode: "{mode}"')

        @validates('default_coil')
        def validate_default_coil(self, default_coil: str, data_key: str) -> None:
            if default_coil not in [c.name for c in machine_options_book.coils]:
                raise ValidationError(f'Invalid maximal coil: "{default_coil}"')

    with open(path, 'r') as f:
        yaml_data = yaml.load(f, Loader=yaml.SafeLoader)
        table_gid = yaml_data['table_gid']

        material_list = load_materials(table_gid)
        materials = material_list.materials_by_name

        del yaml_data['table_gid']
        schema = ConfigSchema()
        config = schema.load(yaml_data)

        recipe_book = load_data(table_gid, material_list, machine_options_book, config)
        return config, recipe_book


def extract_substrings(text: str, materials: Dict[str, Material]) -> tuple[Material, str, float] | Material | None:
    equals = [i for i, c in enumerate(text) if c == '=']
    less_than = [i for i, c in enumerate(text) if c == '<']
    greater_than = [i for i, c in enumerate(text) if c == '>']
    if len(less_than) > 1 or len(greater_than) > 1 or len(equals) > 1:
        return None
    if not (equals or less_than or greater_than):
        if text in materials.keys():
            return materials[text]
        return None
    equals = equals[0] if equals else -1
    less_than = less_than[0] if less_than else -1
    greater_than = greater_than[0] if greater_than else -1
    if less_than >= 0 and greater_than >= 0:
        return None
    if equals < 0 or not (less_than in [-1, equals - 1] and greater_than in [-1, equals - 1]):
        return None
    comparator_index = equals if equals >= 0 else (less_than if less_than >= 0 else greater_than)
    if comparator_index <= 1 or len(text) <= comparator_index + 2:
        return None
    suffix = text[comparator_index + 1:].strip()
    prefix = text[:comparator_index - (less_than >= 0 or greater_than >= 0)].strip()
    if len(prefix) >= 1 and len(suffix) >= 1 and str_to_float(suffix) is not None:
        if prefix in materials.keys():
            return (
                materials[prefix],
                text[comparator_index - (less_than >= 0 or greater_than >= 0):comparator_index + 1],
                str_to_float(suffix)
            )
        return None
    return None
