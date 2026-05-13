import logging
from marshmallow import Schema, fields, post_load, validates, ValidationError
from typing import Dict, Any
from io import BytesIO
from ..exceptions import DataLoadingException

from ..recipes_db.material import Material
from ..recipes_db.voltage_tiers import VoltageTier
from ..recipes_db.machine_options.machine_options import MachineOption
from ..recipes_db.machine_options.machine_option_books import MachineOptionsBook
from ..database_extraction.database_extractor import GTNHDatabase
from ..utility.general_utility import str_to_float, load_file
from ..utility.constants import COMMENT_CHARACTER, DEFAULT_MACHINE_LIMIT

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class CraftingChainConfig:
    inputs: set[Material]
    outputs: set[Material]
    infinite_materials: set[Material]
    weights: Dict[Material, float]
    infinite_production_weights: Dict[Material, float]
    lower_bounds: Dict[Material, float]
    upper_bounds: Dict[Material, float]
    equalities: Dict[Material, float]
    time: str
    display_interval: str
    max_voltage_tier: int
    unlocked_voltage_tier: int
    default_voltage_tier: int
    maximal_energy_increase: float
    max_singleblock_machines: int | None
    max_multiblock_machines: int | None
    default_machine_options: Dict[str, MachineOption]
    machine_limit: int

    def __init__(
        self,
        materials: Dict[str, Material],
        machine_options_book: MachineOptionsBook,
        inputs: list[str],
        outputs: list[str],
        infinite_materials: list[str] | None,
        restrictions: list[str] | None,
        weights: Dict[str, float],
        time: str,
        display_interval: str,
        default_coil: str,
        default_pipe_casing: str,
        default_item_pipe_casing: str,
        default_solenoid_coil: str,
        default_electromagnet: str,
        default_anvil: str,
        unlocked_voltage_tier: str,
        default_voltage_tier: str,
        max_voltage_tier: str | None,
        maximal_energy_increase: float,
        machine_limit: int,
        max_singleblock_machines: int | None = None,
        max_multiblock_machines: int | None = None,
        infinite_production_weights: Dict[str, float] | None = None
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
            elif isinstance(result, tuple):
                self.outputs.add(result[0])
            else:
                _LOGGER.warning(f'Unexpected result from output specification: "{result}".'
                                f'Type: {type(result)}. Skipping output specification.')

        self.infinite_materials = set(materials[m] for m in infinite_materials) \
            if infinite_materials is not None else set()
        self.weights = {
            materials[material_name]: weight for material_name, weight in weights.items()
        }

        # Calculate Infinite Production Weights (weights for the production of infinite materials)
        zero_weight_infinites = {m for m in self.infinite_materials if
                                 m not in self.weights.keys() or self.weights[m] == 0}
        if infinite_production_weights is None:
            infinite_production_weights = {}
        self.infinite_production_weights = {}
        for material in self.infinite_materials:
            if material.name in infinite_production_weights.keys():
                self.infinite_production_weights[material] = infinite_production_weights[material.name]
            else:
                self.infinite_production_weights[material] = \
                    0 if material in zero_weight_infinites else self.weights[material] + 0.0001

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

        self.time = time
        self.display_interval = display_interval
        self.unlocked_voltage_tier = VoltageTier.to_voltage_tier(unlocked_voltage_tier)
        self.max_voltage_tier = min(VoltageTier.to_voltage_tier(max_voltage_tier) if max_voltage_tier is not None
                                    else VoltageTier.MAX, self.unlocked_voltage_tier)
        self.default_voltage_tier = VoltageTier.to_voltage_tier(default_voltage_tier)
        self.maximal_energy_increase = maximal_energy_increase
        self.max_singleblock_machines = max_singleblock_machines
        self.max_multiblock_machines = max_multiblock_machines
        self.machine_limit = machine_limit

        self.default_machine_options = {
            'coil': machine_options_book.get_machine_option(default_coil, machine_options_book.coil),
            'pipe_casing': machine_options_book.get_machine_option(default_pipe_casing, machine_options_book.pipe_casing),
            'item_pipe_casing': machine_options_book.get_machine_option(default_item_pipe_casing, machine_options_book.item_pipe_casing),
            'electromagnet': machine_options_book.get_machine_option(default_electromagnet, machine_options_book.electromagnet),
            'solenoid_coil': machine_options_book.get_machine_option(default_solenoid_coil, machine_options_book.solenoid_coil),
            'anvil': machine_options_book.get_machine_option(default_anvil, machine_options_book.anvil)
        }

    def __repr__(self) -> str:
        def value_string(attr: str, value: Any) -> Any:
            match attr:
                case 'max_voltage_tier':
                    return VoltageTier.voltage_tier_name(value)
                case 'default_voltage_tier':
                    return VoltageTier.voltage_tier_name(value)
                case 'unlocked_voltage_tier':
                    return VoltageTier.voltage_tier_name(value)
                case 'default_machine_options':
                    return ', '.join([f"{k}: {v.__str__()}" for k, v in self.default_machine_options.items()])
                case _:
                    return value

        variable_string = '\n'.join([f'{attr}: {value_string(attr, value)}' for attr, value in vars(self).items()])
        return f'CraftingChainConfig:\n{variable_string}'

    def max_machines(self, multiblock: bool) -> int:
        return self.max_multiblock_machines if multiblock else self.max_singleblock_machines


def load_config(
    file_or_filepath: BytesIO | str,
    database: GTNHDatabase
) -> CraftingChainConfig:
    materials = database.extracted_materials
    machine_options_book = database.machine_options_book

    class CraftingChainConfigSchema(Schema):
        inputs = fields.List(fields.String(), required=True)
        outputs = fields.List(fields.String(), required=True)
        infinite_materials = fields.List(fields.String(), required=True, allow_none=True)
        restrictions = fields.List(fields.String(), required=False, allow_none=True)
        weights = fields.Dict(keys=fields.String(), values=fields.Float())
        time = fields.String(required=True)
        display_interval = fields.String(required=True)
        unlocked_voltage_tier = fields.String(required=True)
        default_voltage_tier = fields.String(required=True)
        max_voltage_tier = fields.String(required=False, allow_none=True, load_default=None)
        max_singleblock_machines = fields.Integer(required=False, allow_none=True, load_default=None)
        max_multiblock_machines = fields.Integer(required=False, allow_none=True, load_default=None)
        maximal_energy_increase = fields.Float(required=True)
        machine_limit = fields.Integer(required=False, load_default=DEFAULT_MACHINE_LIMIT)
        infinite_production_weights = fields.Dict(keys=fields.String(), values=fields.Float(), required=False)

        default_coil = fields.String(required=False, load_default=machine_options_book.coil[0].material.id)
        default_pipe_casing = fields.String(required=False, load_default=machine_options_book.pipe_casing[0].material.id)
        default_item_pipe_casing = fields.String(required=False,
                                                 load_default=machine_options_book.item_pipe_casing[0].material.id)
        default_solenoid_coil = fields.String(required=False, load_default=machine_options_book.solenoid_coil[0].material.id)
        default_electromagnet = fields.String(required=False, load_default=machine_options_book.electromagnet[0].material.id)
        default_anvil = fields.String(required=False, load_default=machine_options_book.anvil[0].material.id)

        @post_load
        def create_config(self, data, **kwargs) -> CraftingChainConfig:
            return CraftingChainConfig(materials, machine_options_book, **data)

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
        def validate_infinite_materials(self, infinite_materials: list[str] | None, data_key: str) -> None:
            if infinite_materials is None:
                return
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

        @validates('default_coil')
        def validate_default_coil(self, default_coil: str, data_key: str) -> None:
            if default_coil not in [c.material.id for c in machine_options_book.coil]:
                raise ValidationError(f'Invalid default coil: "{default_coil}"')

        @validates('default_pipe_casing')
        def validate_default_pipe_casing(self, default_pipe_casing: str, data_key: str) -> None:
            if default_pipe_casing not in [c.material.id for c in machine_options_book.pipe_casing]:
                raise ValidationError(f'Invalid default pipe casing: "{default_pipe_casing}"')

        @validates('default_item_pipe_casing')
        def validate_default_item_pipe_casing(self, default_item_pipe_casing: str, data_key: str) -> None:
            if default_item_pipe_casing not in [c.material.id for c in machine_options_book.item_pipe_casing]:
                raise ValidationError(f'Invalid default item pipe casing: "{default_item_pipe_casing}"')

        @validates('default_solenoid_coil')
        def validate_default_solenoid_coil(self, default_solenoid_coil: str, data_key: str) -> None:
            if default_solenoid_coil not in [c.material.id for c in machine_options_book.solenoid_coil]:
                raise ValidationError(f'Invalid default solenoid coil: "{default_solenoid_coil}"')

        @validates('default_electromagnet')
        def validate_default_electromagnet(self, default_electromagnet: str, data_key: str) -> None:
            if default_electromagnet not in [c.material.id for c in machine_options_book.electromagnet]:
                raise ValidationError(f'Invalid default electromagnet: "{default_electromagnet}"')

        @validates('default_anvil')
        def validate_default_anvil(self, default_anvil: str, data_key: str) -> None:
            if default_anvil not in [c.material.id for c in machine_options_book.anvil]:
                raise ValidationError(f'Invalid default anvil: "{default_anvil}"')

        @validates('max_singleblock_machines')
        def validate_max_singleblock_machines(self, max_singleblock_machines: int | None, data_key: str) -> None:
            if max_singleblock_machines is not None and max_singleblock_machines < 1:
                raise ValidationError(f'Invalid maximum of singleblock machines: "{max_singleblock_machines}"')

        @validates('max_multiblock_machines')
        def validate_max_multiblock_machines(self, max_multiblock_machines: int | None, data_key: str) -> None:
            if max_multiblock_machines is not None and max_multiblock_machines < 1:
                raise ValidationError(f'Invalid maximum of multiblock machines: "{max_multiblock_machines}"')

        @validates('unlocked_voltage_tier')
        def validate_unlocked_voltage_tier(self, unlocked_voltage_tier: str, data_key: str) -> None:
            if unlocked_voltage_tier not in VoltageTier.voltage_tiers(minimum=0):
                raise ValidationError(f'Invalid unlocked voltage tier: "{unlocked_voltage_tier}"')

        @validates('default_voltage_tier')
        def validate_default_voltage_tier(self, default_voltage_tier: str, data_key: str) -> None:
            if default_voltage_tier not in VoltageTier.voltage_tiers(minimum=0):
                raise ValidationError(f'Invalid default voltage tier: "{default_voltage_tier}"')

        @validates('max_voltage_tier')
        def validate_max_voltage_tier(self, max_voltage_tier: str, data_key: str) -> None:
            if max_voltage_tier is not None and max_voltage_tier not in VoltageTier.voltage_tiers(minimum=0):
                raise ValidationError(f'Invalid maximal voltage tier: "{max_voltage_tier}"')

        @validates('maximal_energy_increase')
        def validate_maximal_energy_increase(self, maximal_energy_increase: float, data_key: str) -> None:
            if maximal_energy_increase < 1:
                raise ValidationError(f'Invalid maximal energy increase: "{maximal_energy_increase}"')

        @validates('machine_limit')
        def validate_machine_limit(self, machine_limit: int, data_key: str) -> None:
            if machine_limit < 0:
                raise ValidationError(f'Invalid machine_limit: "{machine_limit}"')

    if any('#' in k for k in database.extracted_materials.keys()):
        raise AssertionError(f'Material keys must not contain the comment character "{COMMENT_CHARACTER}"')

    try:
        yaml_data = load_file(file_or_filepath)
    except Exception as e:
        raise DataLoadingException(e)

    schema = CraftingChainConfigSchema()
    return schema.load(yaml_data)


def extract_substrings(text: str, materials: Dict[str, Material]) -> tuple[Material, str, float] | Material | None:
    comment_index = text.find(COMMENT_CHARACTER)
    if comment_index >= 0:
        text = text[:comment_index].strip()

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
