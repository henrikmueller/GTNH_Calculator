from __future__ import annotations
from typing import Dict
import xgi
import networkx as nx
from dataclasses import dataclass
import matplotlib.pyplot as plt

from .recipe import Recipe
from .material import Material
from .recipe_book import RecipeBook
from ..crafting_chains.crafting_chain import CraftingChain
from ..crafting_chains.crafting_chain_finder import CraftingChainFinder


@dataclass
class Node:
    item: Recipe | Material

    def __hash__(self):
        return self.item.id

    @property
    def name(self):
        return self.item.name

    @property
    def id(self):
        return self.item.id

    def is_material(self):
        return isinstance(self.item, Material)

    def is_recipe(self):
        return isinstance(self.item, Recipe)


class RecipeGraph:
    graph: nx.DiGraph
    recipe_book: RecipeBook

    def __init__(self, recipe_book: RecipeBook):
        self.recipe_book = recipe_book
        self.graph = nx.DiGraph()
        for recipe in recipe_book.recipes.values():
            for input in recipe.get_inputs():
                self.graph.add_edge(Node(input), Node(recipe))
            for output in recipe.get_outputs():
                self.graph.add_edge(Node(recipe), Node(output))

    @property
    def nodes(self):
        return self.graph.nodes

    @property
    def size(self):
        return len(self.nodes)

    @property
    def materials(self):
        return [node for node in self.nodes if node.is_material()]

    @property
    def recipes(self):
        return [node for node in self.nodes if node.is_recipe()]

    def get_node(self, item: Material | Recipe) -> Node | None:
        options = [node for node in self.nodes if node.item is item]
        if not options:
            return None
        if len(options) == 1:
            return options[0]
        raise ValueError(f'Item {item} exists multiple times in the RecipeGraph: {options}')

    def draw(self) -> None:
        material_color = (0.5, 0.5, 1)
        recipe_color = (1, 0.5, 0.5)
        node_labels = {node: (node.name if node.is_material() else node.id) for node in self.nodes}
        node_color = [(material_color if node.is_material() else recipe_color) for node in self.nodes]
        node_size = [(250 if node.is_material() else 50) for node in self.nodes]
        nx.draw_networkx(self.graph, labels=node_labels, node_color=node_color, node_size=node_size)
        plt.show()


class RecipePath:
    path: list[Recipe]

    def __init__(self, path: list[Recipe]):
        self.path = path


class RecipeHypergraph:
    graph: xgi.DiHypergraph
    recipe_book: RecipeBook

    def __init__(self, recipe_book: RecipeBook):
        self.recipe_book = recipe_book
        self.graph = xgi.DiHypergraph()
        for id, recipe in recipe_book.recipes.items():
            input_data, output_data = recipe.get_edge_data(eu=False)
            if input_data and output_data:
                self.graph.add_edge((input_data, output_data), id=recipe.id)

    @property
    def nodes(self):
        return self.graph.nodes

    @property
    def size(self):
        return len(self.nodes)

    @property
    def materials(self) -> list[Material]:
        return [self.recipe_book.material_list.materials_by_id[node] for node in self.graph.nodes]

    def material(self, id: int) -> Material:
        return self.recipe_book.material_list.materials_by_id[id]

    def draw(self) -> None:
        node_labels = {self.material(material_id).id: self.material(material_id).get_abbreviation() for material_id
                       in self.nodes if material_id >= 0}
        node_fc = {material_id: 'white' for material_id in self.nodes}
        xgi.draw_bipartite(self.graph, node_labels=node_labels, node_size=47, node_fc=node_fc,
                           aspect='auto')
        plt.show()

    def get_recipe_graph(self) -> RecipeGraph:
        return RecipeGraph(self.recipe_book)

    def get_subgraph(self, materials: list[Material]) -> RecipeHypergraph:
        return RecipeHypergraph(self.recipe_book.restrict_to(materials))
