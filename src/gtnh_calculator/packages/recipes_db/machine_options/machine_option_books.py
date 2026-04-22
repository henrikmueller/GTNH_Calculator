from __future__ import annotations
import yaml

from .machine_options import *
from ..material import Material
from .machine_option_types import MachineOptionType

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class MachineOptionsBook:
    coils: list[MachineOption]
    pipe_casings: list[MachineOption]
    item_pipe_casings: list[MachineOption]
    electromagnets: list[MachineOption]
    solenoid_coils: list[MachineOption]
    anvils: list[MachineOption]

    def __init__(self, machine_options: list[MachineOption]):
        self.coils = [o for o in machine_options if o.option_type == MachineOptionType.COIL]
        self.coils.sort(key=lambda o: o.tier)
        self.pipe_casings = [o for o in machine_options if o.option_type == MachineOptionType.PIPE_CASING]
        self.pipe_casings.sort(key=lambda o: o.tier)
        self.item_pipe_casings = [o for o in machine_options if o.option_type == MachineOptionType.ITEM_PIPE_CASING]
        self.item_pipe_casings.sort(key=lambda o: o.tier)
        self.electromagnets = [o for o in machine_options if o.option_type == MachineOptionType.ELECTROMAGNET]
        self.electromagnets.sort(key=lambda o: o.tier)
        self.solenoid_coils = [o for o in machine_options if o.option_type == MachineOptionType.SOLENOID_COIL]
        self.solenoid_coils.sort(key=lambda o: o.tier)
        self.anvils = [o for o in machine_options if o.option_type == MachineOptionType.ANVIL]
        self.anvils.sort(key=lambda o: o.tier)

    @property
    def all_options(self) -> list[MachineOption]:
        return (self.coils + self.pipe_casings + self.item_pipe_casings + self.electromagnets +
                self.solenoid_coils + self.anvils)

    def __str__(self):
        return f"""
Coils: {[o.__str__() for o in self.coils]}
Pipe Casings: {[o.__str__() for o in self.pipe_casings]}
Item Pipe Casings: {[o.__str__() for o in self.item_pipe_casings]}
Electromagnets: {[o.__str__() for o in self.electromagnets]}
Solenoid Coils: {[o.__str__() for o in self.solenoid_coils]}
Anvils: {[o.__str__() for o in self.anvils]}
"""

    def get_machine_option_list(
        self,
        option_type: MachineOptionType,
        minimum: MachineOption | None,
        maximum: MachineOption | None
    ) -> list[MachineOption]:
        options = getattr(self, option_type)
        if minimum is None:
            minimum = options[0]
        if maximum is None:
            maximum = options[-1]
        return [o for o in options if minimum <= o <= maximum]

    @staticmethod
    def get_machine_option(input_id: str, options: list[MachineOption]) -> MachineOption | None:
        for option in options:
            if option.material.id == input_id:
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
