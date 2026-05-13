from __future__ import annotations
import yaml
from typing import Callable

from .machine_options import *
from ..material import Material
from .machine_option_types import MachineOptionType

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class MachineOptionsBook:
    coil: list[MachineOption]
    pipe_casing: list[MachineOption]
    item_pipe_casing: list[MachineOption]
    electromagnet: list[MachineOption]
    solenoid_coil: list[MachineOption]
    anvil: list[MachineOption]
    coke_oven_casing: list[MachineOption]
    width: list[MachineOption]
    maceration_upgrade: list[MachineOption]
    containment_block: list[MachineOption]

    def __init__(self, machine_options: list[MachineOption]):
        self.coil = [o for o in machine_options if o.option_type == MachineOptionType.COIL]
        self.coil.sort(key=lambda o: o.tier)
        self.pipe_casing = [o for o in machine_options if o.option_type == MachineOptionType.PIPE_CASING]
        self.pipe_casing.sort(key=lambda o: o.tier)
        self.item_pipe_casing = [o for o in machine_options if o.option_type == MachineOptionType.ITEM_PIPE_CASING]
        self.item_pipe_casing.sort(key=lambda o: o.tier)
        self.electromagnet = [o for o in machine_options if o.option_type == MachineOptionType.ELECTROMAGNET]
        self.electromagnet.sort(key=lambda o: o.tier)
        self.solenoid_coil = [o for o in machine_options if o.option_type == MachineOptionType.SOLENOID_COIL]
        self.solenoid_coil.sort(key=lambda o: o.tier)
        self.anvil = [o for o in machine_options if o.option_type == MachineOptionType.ANVIL]
        self.anvil.sort(key=lambda o: o.tier)
        self.containment_block = [o for o in machine_options if o.option_type == MachineOptionType.CONTAINMENT_BLOCK]
        self.containment_block.sort(key=lambda o: o.tier)

        self.coke_oven_casing = []
        self.width = []
        self.maceration_upgrade = []

    @property
    def all_options(self) -> list[MachineOption]:
        return (self.coil + self.pipe_casing + self.item_pipe_casing + self.electromagnet +
                self.solenoid_coil + self.anvil + self.containment_block)

    def get_machine_option_list(
        self,
        option_type: MachineOptionType,
        rank: Callable[[MachineOption], int | float] | None = None,
        minimum: MachineOption | None = None,
        maximum: MachineOption | None = None
    ) -> list[MachineOption]:
        options: list[MachineOption] = getattr(self, option_type)
        if rank is None:
            return options
        minimum = options[0] if minimum is None else minimum
        maximum = options[-1] if maximum is None else maximum
        return [o for o in options if rank(minimum) <= rank(o) <= rank(maximum)]

    @staticmethod
    def get_machine_option(input_id: str, options: list[MachineOption]) -> MachineOption | None:
        for option in options:
            if option.material is not None and option.material.id == input_id:
                return option
        _LOGGER.warning(f'No Machine Option to the ID "{input_id}" found.')
        return None


class MachineOptionsBookSchema(Schema):
    machine_options = fields.List(fields.Nested(MachineOptionSchema(), required=True), required=True)

    def __init__(self, *args, extracted_materials=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["machine_options"].inner = fields.Nested(
            MachineOptionSchema(extracted_materials=extracted_materials)
        )

    @post_load
    def create(self, data, **kwargs) -> MachineOptionsBook:
        machine_options_book = MachineOptionsBook(**data)
        return machine_options_book


def load_possible_machine_options(path: str, extracted_materials: Dict[str, Material]) -> MachineOptionsBook:
    with open(path, 'r') as f:
        yaml_data = yaml.load(f, Loader=yaml.SafeLoader)
        schema = MachineOptionsBookSchema(extracted_materials=extracted_materials)
        return schema.load(yaml_data)
