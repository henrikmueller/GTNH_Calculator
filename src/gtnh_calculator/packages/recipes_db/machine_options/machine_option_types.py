from enum import StrEnum
from frozendict import frozendict


class MachineOptionType(StrEnum):
    COIL = 'coil'
    PIPE_CASING = 'pipe_casing'
    ITEM_PIPE_CASING = 'item_pipe_casing'
    ELECTROMAGNET = 'electromagnet'
    SOLENOID_COIL = 'solenoid_coil'
    ANVIL = 'anvil'
    COKE_OVEN_CASING = 'coke_oven_casing'
    WIDTH_EXPANSION = 'width_expansion'
    MACERATION_UPGRADE = 'maceration_upgrade'
    CONTAINMENT_BLOCK = 'containment_block'


class MachineOptionDataType(StrEnum):
    INTEGER = 'integer'
    BLOCK = 'block'


MACHINE_OPTION_DATA_TYPES: frozendict[MachineOptionType, MachineOptionDataType] = frozendict({
    MachineOptionType.COIL: MachineOptionDataType.BLOCK,
    MachineOptionType.PIPE_CASING: MachineOptionDataType.BLOCK,
    MachineOptionType.ITEM_PIPE_CASING: MachineOptionDataType.BLOCK,
    MachineOptionType.ELECTROMAGNET: MachineOptionDataType.BLOCK,
    MachineOptionType.SOLENOID_COIL: MachineOptionDataType.BLOCK,
    MachineOptionType.ANVIL: MachineOptionDataType.BLOCK,
    MachineOptionType.COKE_OVEN_CASING: MachineOptionDataType.BLOCK,
    MachineOptionType.WIDTH_EXPANSION: MachineOptionDataType.INTEGER,
    MachineOptionType.MACERATION_UPGRADE: MachineOptionDataType.BLOCK,
    MachineOptionType.CONTAINMENT_BLOCK: MachineOptionDataType.BLOCK,
})
