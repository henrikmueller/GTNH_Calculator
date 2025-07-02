from typing import Dict


class Material:
    id: int
    name: str

    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name

    def __repr__(self):
        return f'{self.name}'

    def get_abbreviation(self):
        return self.name


class MaterialList:
    materials_by_name: Dict[str, Material]
    materials_by_id: Dict[id, Material]

    def __init__(self, materials_by_name: Dict[str, Material], materials_by_id: Dict[id, Material]):
        self.materials_by_name = materials_by_name
        self.materials_by_id = materials_by_id
