from typing import Dict
import xgi
from .recipe import Recipe


def build_recipe_hypergraph(recipes: Dict[int, Recipe]) -> xgi.DiHypergraph:
    hypergraph = xgi.DiHypergraph()
    for id, recipe in recipes.items():
        input_data, output_data = recipe.get_edge_data(eu=False)
        if input_data and output_data:
            hypergraph.add_edge((input_data, output_data), id=recipe.id)
    return hypergraph
