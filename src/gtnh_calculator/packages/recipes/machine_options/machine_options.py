from __future__ import annotations
from dataclasses import dataclass
from abc import abstractmethod
import logging
from typing import Dict

from marshmallow import Schema, fields, post_load, validates, ValidationError

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


"""
------------------------------------------------------------------------------------------------------------------------
    Abstract Machine Options
------------------------------------------------------------------------------------------------------------------------
"""


class MachineOption:
    name: str
    slot_name: str

    def __str__(self) -> str:
        return self.name

    def fits(self, raw_option: str) -> bool:
        return raw_option == self.name

    @abstractmethod
    def __lt__(self, other: MachineOption) -> bool:
        ...

    def __le__(self, other: MachineOption) -> bool:
        return self == other or self < other

    @classmethod
    def maximum(cls, option1: MachineOption | None, option2: MachineOption | None) -> MachineOption | None:
        if option2 is None:
            return option1
        if option1 is None or option2 > option1:
            return option2
        return option1


@dataclass
class MachineOptions:
    coil: Coil | None = None
    pipe_casing: PipeCasing | None = None
    item_pipe_casing: ItemPipeCasing | None = None
    electromagnet: Electromagnet | None = None
    solenoid_coil: SolenoidCoil | None = None
    anvil: Anvil | None = None

    def set_option(self, option: MachineOption):
        attribute = option.slot_name
        old = getattr(self, attribute)
        if old:
            _LOGGER.warning(f"Overwrite {attribute}: {old} -> {option}")
        setattr(self, attribute, option)

    @classmethod
    def create_empty_options(cls) -> MachineOptions:
        return MachineOptions()

    @classmethod
    def create_options_from(cls, machine_option_list: list[MachineOption] | tuple[MachineOption, ...]) -> MachineOptions:
        machine_options = cls.create_empty_options()
        for option in machine_option_list:
            setattr(machine_options, option.slot_name, option)
        return machine_options

    @property
    def all_options(self) -> list[MachineOption]:
        return list(self.__dict__.values())

    @classmethod
    def all_option_types(cls) -> list[str]:
        return ['coils', 'pipe_casings', 'item_pipe_casings', 'electromagnets', 'solenoid_coils', 'anvils']

    @property
    def non_empty_options(self) -> list[MachineOption]:
        return [option for option in self.all_options if option is not None]

    def __repr__(self) -> str:
        return f'Machine Options: ({', '.join([option.__str__() for option in self.non_empty_options])})'

    def __str__(self) -> str:
        return f'{', '.join([option.__str__() for option in self.non_empty_options])}'

    def maximum(self, other: MachineOptions) -> MachineOptions:
        selected_options = (MachineOption.maximum(o1, o2) for o1, o2 in zip(self.all_options, other.all_options))
        machine_options = MachineOptions(*selected_options)
        return machine_options


"""
------------------------------------------------------------------------------------------------------------------------
    Coils
------------------------------------------------------------------------------------------------------------------------
"""


@dataclass
class Coil(MachineOption):
    name: str
    tier: int
    temperature: int
    slot_name = 'coil'

    def __repr__(self) -> str:
        return f'Coil: {self.name}'

    def __lt__(self, other: Coil):
        return self.tier < other.tier

    @classmethod
    def maximum(cls, option1: Coil | None, option2: Coil | None) -> Coil | None:
        if option2 is None:
            return option1
        if option1 is None or option2 > option1:
            return option2
        return option1


class CoilSchema(Schema):
    name = fields.String(required=True)
    tier = fields.Integer(required=True)
    temperature = fields.Integer(required=True)

    @post_load
    def create(self, data, **kwargs) -> Coil:
        return Coil(**data)

    @validates('name')
    def validate_name(self, name: str, data_key: str) -> None:
        if not name.endswith(' Coil'):
            raise ValidationError(f'Invalid coil name: "{name}"')

    @validates('tier')
    def validate_tier(self, tier: int, data_key: str) -> None:
        if not 1 <= tier:
            raise ValidationError(f'Invalid coil tier: "{tier}"')


"""
------------------------------------------------------------------------------------------------------------------------
    Pipe Casings
------------------------------------------------------------------------------------------------------------------------
"""


@dataclass
class PipeCasing(MachineOption):
    name: str
    tier: int
    slot_name = 'pipe_casing'

    def __lt__(self, other: PipeCasing):
        return self.tier < other.tier

    def __repr__(self) -> str:
        return f'PipeCasing: {self.name}'

    @classmethod
    def maximum(cls, option1: PipeCasing | None, option2: PipeCasing | None) -> PipeCasing | None:
        if option2 is None:
            return option1
        if option1 is None or option2 > option1:
            return option2
        return option1


class PipeCasingSchema(Schema):
    name = fields.String(required=True)
    tier = fields.Integer(required=True)

    @post_load
    def create(self, data, **kwargs) -> PipeCasing:
        return PipeCasing(**data)

    @validates('name')
    def validate_name(self, name: str, data_key: str) -> None:
        if not (name.endswith(' Pipe Casing') and not name.endswith('Item Pipe Casing')):
            raise ValidationError(f'Invalid pipe casing name: "{name}"')

    @validates('tier')
    def validate_tier(self, tier: int, data_key: str) -> None:
        if not 1 <= tier:
            raise ValidationError(f'Invalid pipe casing tier: "{tier}"')


"""
------------------------------------------------------------------------------------------------------------------------
    Electromagnets
------------------------------------------------------------------------------------------------------------------------
"""


@dataclass
class Electromagnet(MachineOption):
    name: str
    tier: int
    speed: float
    eu_usage: float
    parallels: int
    slot_name = 'electromagnet'

    def __lt__(self, other: Electromagnet):
        return self.tier < other.tier

    def __repr__(self) -> str:
        return f'Electromagnet: {self.name}'

    @classmethod
    def maximum(cls, option1: Electromagnet | None, option2: Electromagnet | None) -> Electromagnet | None:
        if option2 is None:
            return option1
        if option1 is None or option2 > option1:
            return option2
        return option1


class ElectromagnetSchema(Schema):
    name = fields.String(required=True)
    tier = fields.Integer(required=True)
    speed = fields.Float(required=True)
    eu_usage = fields.Float(required=True)
    parallels = fields.Integer(required=True)

    @post_load
    def create(self, data, **kwargs) -> Electromagnet:
        return Electromagnet(**data)

    @validates('name')
    def validate_name(self, name: str, data_key: str) -> None:
        if not name.endswith(' Electromagnet'):
            raise ValidationError(f'Invalid electromagnet name: "{name}"')

    @validates('tier')
    def validate_tier(self, tier: int, data_key: str) -> None:
        if not 1 <= tier:
            raise ValidationError(f'Invalid electromagnet tier: "{tier}"')

    @validates('speed')
    def validate_speed(self, speed: int, data_key: str) -> None:
        if speed <= 0:
            raise ValidationError(f'Invalid electromagnet speed: "{speed}"')

    @validates('eu_usage')
    def validate_eu_usage(self, eu_usage: int, data_key: str) -> None:
        if eu_usage <= 0:
            raise ValidationError(f'Invalid electromagnet eu_usage: "{eu_usage}"')

    @validates('parallels')
    def validate_parallels(self, parallels: int, data_key: str) -> None:
        if parallels <= 0:
            raise ValidationError(f'Invalid electromagnet parallels: "{parallels}"')


"""
------------------------------------------------------------------------------------------------------------------------
    Item Pipe Casings
------------------------------------------------------------------------------------------------------------------------
"""


@dataclass
class ItemPipeCasing(MachineOption):
    name: str
    tier: int
    slot_name = 'item_pipe_casing'

    def __lt__(self, other: ItemPipeCasing):
        return self.tier < other.tier

    def __repr__(self) -> str:
        return f'ItemPipeCasing: {self.name}'

    @classmethod
    def maximum(cls, option1: ItemPipeCasing | None, option2: ItemPipeCasing | None) -> ItemPipeCasing | None:
        if option2 is None:
            return option1
        if option1 is None or option2 > option1:
            return option2
        return option1


class ItemPipeCasingSchema(Schema):
    name = fields.String(required=True)
    tier = fields.Integer(required=True)

    @post_load
    def create(self, data, **kwargs) -> ItemPipeCasing:
        return ItemPipeCasing(**data)

    @validates('name')
    def validate_name(self, name: str, data_key: str) -> None:
        if not name.endswith(' Item Pipe Casing'):
            raise ValidationError(f'Invalid item pipe casing name: "{name}"')

    @validates('tier')
    def validate_tier(self, tier: int, data_key: str) -> None:
        if not 1 <= tier:
            raise ValidationError(f'Invalid item pipe casing tier: "{tier}"')


"""
------------------------------------------------------------------------------------------------------------------------
    Solenoid Coils
------------------------------------------------------------------------------------------------------------------------
"""


@dataclass
class SolenoidCoil(MachineOption):
    name: str
    tier: int
    slot_name = 'solenoid_coil'

    def __lt__(self, other: SolenoidCoil):
        return self.tier < other.tier

    def __repr__(self) -> str:
        return f'SolenoidCoil: {self.name}'

    @classmethod
    def maximum(cls, option1: SolenoidCoil | None, option2: SolenoidCoil | None) -> SolenoidCoil | None:
        if option2 is None:
            return option1
        if option1 is None or option2 > option1:
            return option2
        return option1


class SolenoidCoilSchema(Schema):
    name = fields.String(required=True)
    tier = fields.Integer(required=True)

    @post_load
    def create(self, data, **kwargs) -> SolenoidCoil:
        return SolenoidCoil(**data)

    @validates('name')
    def validate_name(self, name: str, data_key: str) -> None:
        if 'Solenoid' not in name or not name.endswith(' Coil'):
            raise ValidationError(f'Invalid solenoid coil name: "{name}"')

    @validates('tier')
    def validate_tier(self, tier: int, data_key: str) -> None:
        if not 1 <= tier:
            raise ValidationError(f'Invalid solenoid coil tier: "{tier}"')


"""
------------------------------------------------------------------------------------------------------------------------
    Anvils
------------------------------------------------------------------------------------------------------------------------
"""


@dataclass
class Anvil(MachineOption):
    name: str
    tier: int
    slot_name = 'anvil'

    def __lt__(self, other: Anvil):
        return self.tier < other.tier

    def __repr__(self) -> str:
        return f'Anvil: {self.name}'

    @classmethod
    def maximum(cls, option1: Anvil | None, option2: Anvil | None) -> Anvil | None:
        if option2 is None:
            return option1
        if option1 is None or option2 > option1:
            return option2
        return option1


class AnvilSchema(Schema):
    name = fields.String(required=True)
    tier = fields.Integer(required=True)

    @post_load
    def create(self, data, **kwargs) -> Anvil:
        return Anvil(**data)

    @validates('name')
    def validate_name(self, name: str, data_key: str) -> None:
        if not name.endswith('Anvil'):
            raise ValidationError(f'Invalid anvil name: "{name}"')

    @validates('tier')
    def validate_tier(self, tier: int, data_key: str) -> None:
        if not 1 <= tier:
            raise ValidationError(f'Invalid anvil tier: "{tier}"')
