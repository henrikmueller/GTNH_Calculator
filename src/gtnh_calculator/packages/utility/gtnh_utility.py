

def get_recipe_id_from_str(text: str) -> str:
    recipe_id = text.split("==")[0]  # strip instance number of instantiated recipe
    return recipe_id + '==' if recipe_id else ''


def get_instance_number_from_str(text: str) -> int:
    parts = text.split('==')
    if len(parts) > 1 and parts[1].isdigit():
        return int(parts[1])
    return 0
