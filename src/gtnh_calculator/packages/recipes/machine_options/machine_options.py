from __future__ import annotations
from dataclasses import dataclass
from abc import abstractmethod
import logging

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

    def __str__(self) -> str:
        return self.name

    @abstractmethod
    def fits(self, raw_option: str) -> bool:
        ...

    @abstractmethod
    def __lt__(self, other: MachineOption) -> bool:
        ...

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

    def set_option(self, option: MachineOption):
        if isinstance(option, Coil):
            if self.coil is not None:
                _LOGGER.warning(f'Overwrite coil option: {self.coil} -> {option}')
            self.coil = option
        if isinstance(option, PipeCasing):
            if self.pipe_casing is not None:
                _LOGGER.warning(f'Overwrite pipe casing option: {self.pipe_casing} -> {option}')
            self.pipe_casing = option

    @classmethod
    def create_empty_options(cls) -> MachineOptions:
        return MachineOptions(
            coil=None,
            pipe_casing=None
        )

    @property
    def all_options(self) -> list[MachineOption]:
        return [self.coil, self.pipe_casing]

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

    def __repr__(self) -> str:
        return f'Coil = {self.name}'

    def fits(self, raw_option: str) -> bool:
        return raw_option == self.name

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
        if not 1 <= tier <= 14:
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

    def fits(self, raw_option: str) -> bool:
        return raw_option == self.name

    def __lt__(self, other: PipeCasing):
        return self.tier < other.tier

    def __repr__(self) -> str:
        return f'PipeCasing = {self.name}'

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
        if not 1 <= tier <= 4:
            raise ValidationError(f'Invalid coil tier: "{tier}"')
