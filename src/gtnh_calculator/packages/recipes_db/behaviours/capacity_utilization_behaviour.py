from __future__ import annotations
from abc import abstractmethod
from dataclasses import dataclass
from typing import Dict, Any
import numpy as np
from scipy.optimize import linprog
from frozendict import frozendict
import logging

from ..adapted_recipes import AdaptedRecipe, PartiallyUtilizedRecipe
from .machine_behaviours import MachineBehaviour, FittingContext

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass(frozen=True)
class CapacityUtilizationBehaviour:
    @abstractmethod
    def fit_to_capacity_utilization(
        self, adapted_recipe: AdaptedRecipe, capacity_utilization: float, machine_behaviour: MachineBehaviour, 
        fitting_context: FittingContext, log: bool = False
    ) -> PartiallyUtilizedRecipe:
        ...

    @classmethod
    def create_capacity_utilization_behaviour(cls, specification: Dict[str, Any] | None = None) -> CapacityUtilizationBehaviour:
        if specification is None:
            return DefaultCapacityUtilizationBehaviour()
        match specification['type']:
            case 'default':
                return DefaultCapacityUtilizationBehaviour()
            case _:
                return NotImplementedCapacityUtilizationBehaviour()


@dataclass(frozen=True)
class DefaultCapacityUtilizationBehaviour(CapacityUtilizationBehaviour):
    def fit_to_capacity_utilization(
        self, adapted_recipe: AdaptedRecipe, capacity_utilization: float, machine_behaviour: MachineBehaviour, 
        fitting_context: FittingContext, log: bool = False
    ) -> PartiallyUtilizedRecipe:
        if capacity_utilization < 0:
            raise ValueError('Capacity utilization must be greater than 0')
        if capacity_utilization.is_integer():
            return PartiallyUtilizedRecipe(
                capacity_utilization=capacity_utilization,
                min_total_eu=capacity_utilization * adapted_recipe.total_eu,
                max_total_eu=capacity_utilization * adapted_recipe.total_eu,
                processing_time=adapted_recipe.processing_time,
                average_inputs=frozendict(
                {g: capacity_utilization * a for g, a in adapted_recipe.inputs.items()}),
                output_specifications=adapted_recipe.multiply_output_specifications(capacity_utilization),
                parallelized=adapted_recipe.used_parallels > 1
            )

        full_throughput = adapted_recipe.get_throughput(fitting_context.raw_recipe)
        adapted_recipes: Dict[int, AdaptedRecipe] = {}
        for parallels in range(1, adapted_recipe.used_parallels + 1):
            recipe = machine_behaviour.fit_recipe(
                fitting_context=fitting_context, parallel_cap=parallels
            )
            if recipe is not None:
                adapted_recipes[parallels] = recipe

        trivial_constraint = np.ones(len(adapted_recipes))
        throughput_constraint = np.array([[
            a.get_throughput(fitting_context.raw_recipe) / a.processing_time for p, a in adapted_recipes.items()
        ]])
        throughput_target = capacity_utilization * full_throughput / adapted_recipe.processing_time
        cost_vector = np.array([
            a.eu_per_tick / a.processing_time for a in adapted_recipes.values()
        ])

        bounds = np.full((len(adapted_recipes), 2), np.nan, dtype=np.float64)
        bounds[:, 0] = 0
        result = linprog(
            c=cost_vector,
            A_ub=np.array([trivial_constraint]),
            b_ub=np.array([np.ceil(capacity_utilization)]),
            A_eq=throughput_constraint,
            b_eq=throughput_target,
            bounds=bounds,
            method='highs'
        )
        if result.status != 0:
            raise ValueError(f'Linear programming failed with status {result.status}: {result.message}')
        max_eu_per_tick = np.dot(result.x, np.array([a.eu_per_tick for a in adapted_recipes.values()]))

        if log:
            _LOGGER.info(f'Adapted recipe: {adapted_recipe}. Capacity utilization: {capacity_utilization}. '
                        f'Fitting Context: {fitting_context}')
            for parallels, recipe in adapted_recipes.items():
                _LOGGER.info(f'{parallels} parallels: {recipe}, throughput: {recipe.get_throughput(fitting_context.raw_recipe)}')
            _LOGGER.info(f'full_throughput: {full_throughput}')
            _LOGGER.info(f'throughput_constraint: {throughput_constraint}')
            _LOGGER.info(f'throughput_target: {throughput_target}')
            _LOGGER.info(f'cost_vector: {cost_vector}')
            _LOGGER.info(f'result.x: {result.x}')

        partially_utilized_recipe = PartiallyUtilizedRecipe(
            capacity_utilization=capacity_utilization,
            min_total_eu=capacity_utilization * adapted_recipe.total_eu,
            max_total_eu=20 * max_eu_per_tick * adapted_recipe.processing_time,
            processing_time=adapted_recipe.processing_time,
            average_inputs=frozendict(
                {g: capacity_utilization * a for g, a in adapted_recipe.inputs.items()}),
            output_specifications=adapted_recipe.multiply_output_specifications(capacity_utilization),
            parallelized=adapted_recipe.used_parallels > 1
        )
        return partially_utilized_recipe


@dataclass(frozen=True)
class NotImplementedCapacityUtilizationBehaviour(CapacityUtilizationBehaviour):
    def fit_to_capacity_utilization(
        self, adapted_recipe: AdaptedRecipe, capacity_utilization: float, machine_behaviour: MachineBehaviour, 
        fitting_context: FittingContext, log: bool = False
    ) -> PartiallyUtilizedRecipe:
        raise NotImplementedError('Capacity Utilization Behaviour not implemented')
