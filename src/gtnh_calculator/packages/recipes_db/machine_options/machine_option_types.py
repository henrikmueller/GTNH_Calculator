from enum import StrEnum


class MachineOptionType(StrEnum):
    COIL = 'coil'
    PIPE_CASING = 'pipe_casing'
    ITEM_PIPE_CASING = 'item_pipe_casing'
    ELECTROMAGNET = 'electromagnet'
    SOLENOID_COIL = 'solenoid_coil'
    ANVIL = 'anvil'
    COKE_OVEN_CASING = 'coke_oven_casing'
    WIDTH = 'width'
    MACERATION_UPGRADE = 'maceration_upgrade'
