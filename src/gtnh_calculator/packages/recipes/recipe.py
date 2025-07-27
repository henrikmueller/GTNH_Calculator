import numpy as np
from typing import Dict

from .material import Material
from .machine import Machine


class Recipe:
    id: int
    input: Dict[Material, float]
    output: Dict[Material, float]
    machine: Machine
    voltage_tier: int
    processing_time: float  # in seconds
    weight: float

    def __init__(
        self,
        id: int,
        materials: Dict[Material, float],
        machine: Machine,
        voltage_tier: int,
        processing_time: float,
        weight: float
    ):
        self.id = id
        self.materials = materials
        self.machine = machine
        self.voltage_tier = voltage_tier
        self.processing_time = processing_time
        self.weight = weight

    def __repr__(self) -> str:
        return (f'Recipe {self.id}: {self.materials}. Machine: {self.machine}, '
                f'Processing Time = {self.processing_time}, Voltage Tier = {self.voltage_tier}')

    def get_inputs(self) -> list[Material]:
        return [material for material in self.materials.keys() if self.materials[material] < 0]

    def get_outputs(self) -> list[Material]:
        return [material for material in self.materials.keys() if self.materials[material] > 0]

    def get_edge_data(self, eu=False) -> tuple[list[int], list[int]]:
        if eu:
            return [material.id for material in self.get_inputs()], [material.id for material in self.get_outputs()]
        return ([material.id for material in self.get_inputs() if material.id > 0],
                [material.id for material in self.get_outputs()])

    def material_quantity(self, material: Material):
        return self.materials[material] if material in self.materials.keys() else 0

    def recipe_vector(self, materials: list[Material]):
        return np.array([self.material_quantity(material) for material in materials])

    def input_string(self, factor: float):
        result = []
        for material in self.get_inputs():
            if material.name == 'EU':
                continue
            result.append(f'{"{:.2f}".format(factor * (abs(self.material_quantity(material))))} {material.name}')
        return ', '.join(result)

    def output_string(self, factor: float):
        result = []
        for material in self.get_outputs():
            result.append(f'{"{:.2f}".format(factor * (abs(self.material_quantity(material))))} {material.name}')
        return ', '.join(result)

    def voltage_tier_name(self) -> str:
        match self.voltage_tier:
            case -1:
                return '-'
            case 0:
                return 'ULV'
            case 1:
                return 'LV'
            case 2:
                return 'MV'
            case 3:
                return 'HV'
            case 4:
                return 'EV'
            case 5:
                return 'IV'
            case 6:
                return 'LUV'
            case 7:
                return 'ZPM'
            case 8:
                return 'UV'
            case 9:
                return 'UHV'
