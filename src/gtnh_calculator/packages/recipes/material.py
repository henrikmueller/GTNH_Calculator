from __future__ import annotations
from typing import Dict


class Material:
    id: int
    name: str

    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name

    def __repr__(self):
        return f'{self.name}'

    def __eq__(self, other: Material) -> bool:
        return isinstance(other, Material) and self.id == other.id

    def __hash__(self):
        return self.id

    def get_abbreviation(self):
        return self.name


def get_materials(materials: Dict[str, Material], material_names: list[str]) -> list[Material]:
    return [
        materials[material_name] for material_name in material_names if material_name in materials.keys()
    ]


def get_material_dict(materials: Dict[str, Material], dict: Dict[str, float]) -> Dict[Material, float]:
    return {
        materials[material_name]: entry for material_name, entry in dict.items() if material_name in materials.keys()
    }


class MaterialList:
    materials_by_name: Dict[str, Material]
    materials_by_id: Dict[id, Material]

    def __init__(self, materials_by_name: Dict[str, Material], materials_by_id: Dict[id, Material]):
        self.materials_by_name = materials_by_name
        self.materials_by_id = materials_by_id
