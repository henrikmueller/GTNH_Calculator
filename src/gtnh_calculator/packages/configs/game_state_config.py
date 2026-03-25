from typing import Dict, Any
from marshmallow import Schema, fields, post_load, validates, ValidationError

from ..recipes.material import Material, MaterialList


class GameState:
    maintained_levels: Dict[Material, float]
    passive_production: Dict[Material, float]

    def __init__(
        self,
        maintained_levels: Dict[Material, float],
        passive_production: Dict[Material, float]
    ):
        self.maintained_levels = maintained_levels
        self.passive_production = passive_production

    def __repr__(self) -> str:
        def value_string(attr: str, value: Any) -> Any:
            match attr:
                case _:
                    return value

        variable_string = '\n'.join([f'{attr}: {value_string(attr, value)}' for attr, value in vars(self).items()])
        return f'GameState:\n{variable_string}'


def load_game_state(
    yaml_data: Any,
    material_list: MaterialList
) -> GameState:
    class GameStateSchema(Schema):
        maintained_levels = fields.Dict(keys=fields.String(), values=fields.Float())
        passive_production = fields.Dict(keys=fields.String(), values=fields.Float())

        @post_load
        def create_game_state(self, data, **kwargs) -> GameState:
            return GameState(**data)

        @validates('maintained_levels')
        def validate_maintained_levels(self, maintained_levels: Dict[str, float], data_key: str) -> None:
            for material_name in maintained_levels.keys():
                if material_name not in materials.keys():
                    raise ValidationError(f'Unknown material in maintained_levels dictionary: "{material_name}"')

        @validates('passive_production')
        def validate_passive_production(self, passive_production: Dict[str, float], data_key: str) -> None:
            for material_name in passive_production.keys():
                if material_name not in materials.keys():
                    raise ValidationError(f'Unknown material in passive_production dictionary: "{material_name}"')

    materials = material_list.materials_by_name
    schema = GameStateSchema()
    return schema.load(yaml_data)
