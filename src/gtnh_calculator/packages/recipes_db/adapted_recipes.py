from __future__ import annotations
from dataclasses import dataclass
from frozendict import frozendict
import logging

from .material import Material, MaterialGroup
from .raw_recipes import RawRecipe, get_output_dict
from .raw_recipes import InputCombination

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


THROUGHPUT_TOLERANCE = 1e-7
THROUGHPUT_DECIMAL_PLACES = 3


class Throughput(float):
    def __new__(cls, value):
        value = float(value)
        if value < 0:
            raise ValueError("Throughput cannot not be negative.")
        return super().__new__(cls, value)


class ThroughputRatio(float):
    def __new__(cls, value):
        value = float(value)
        if value < 0:
            raise ValueError("Throughput ratio cannot be negative.")
        return super().__new__(cls, value)


@dataclass(frozen=True)
class AdaptedRecipe:
    eu_per_tick: float
    processing_time: float  # in seconds
    amperage: int
    inputs: frozendict[MaterialGroup, float]
    output_specifications: frozendict[int, tuple[Material, float, float]]
    used_parallels: int = 1

    def __repr__(self) -> str:
        return (f'AdaptedRecipe(inputs={self.inputs}, outputs={self.output_specifications}, '
                f'eu_per_tick={self.eu_per_tick}, processing_time={self.processing_time}, '
                f'amperage={self.amperage}, used_parallels={self.used_parallels})')

    @property
    def total_eu(self) -> float:
        return self.eu_per_tick * self.processing_time * 20

    @property
    def is_valid(self) -> bool:
        return True

    @property
    def output_dict(self) -> frozendict[Material, float]:
        return get_output_dict(self.output_specifications)

    def get_throughput(self, base_recipe: RawRecipe) -> Throughput:
        inputs_ratios = [self.inputs[material_group] / amount 
                         for material_group, amount in base_recipe.inputs.items() if amount != 0]
        base_output_dict = base_recipe.output_dict
        output_dict = self.output_dict
        output_ratios = [output_dict[material] / amount 
                         for material, amount in base_output_dict.items() if amount != 0]
        ratios = inputs_ratios + output_ratios
        if max(ratios) - min(ratios) <= THROUGHPUT_TOLERANCE:
            return Throughput(round(ratios[0], THROUGHPUT_DECIMAL_PLACES))
        raise ValueError(f"Inconsistent input ratios to determine throughput. Base recipe: {base_recipe}, Adapted recipe: {self}. Ratios: {ratios}")

    def get_throughput_ratio(self, adapted_recipe: AdaptedRecipe, base_recipe: RawRecipe) -> ThroughputRatio:
        throughput = self.get_throughput(base_recipe=base_recipe)
        other_throughput = adapted_recipe.get_throughput(base_recipe=base_recipe)
        return ThroughputRatio(throughput / other_throughput)

    @property
    def average_inputs(self) -> frozendict[MaterialGroup, float]:
        return self.inputs

    def input_dict(self, input_combination: InputCombination) -> frozendict[Material, float]:
        return frozendict({input_combination[g]: a for g, a in self.inputs.items()})

    @property
    def average_outputs(self) -> frozendict[Material, float]:
        return self.output_dict

    def multiply_output_specifications(self, factor: float) -> frozendict[int, tuple[Material, float, float]]:
        return frozendict({k: (v[0], v[1] * factor, v[2]) for k, v in self.output_specifications.items()})


@dataclass(frozen=True)
class InvalidAdaptedRecipe(AdaptedRecipe):
    def __init__(self) -> None:
        super().__init__(
            eu_per_tick=0.0,
            processing_time=0.0,
            amperage=0,
            inputs=frozendict(),
            output_specifications=frozendict(),
            used_parallels=1
        )

    @property
    def is_valid(self) -> bool:
        return False


@dataclass(frozen=True)
class PartiallyUtilizedRecipe:
    capacity_utilization: float
    processing_time: float
    min_total_eu: float
    max_total_eu: float
    average_inputs: frozendict[MaterialGroup, float]
    output_specifications: frozendict[int, tuple[Material, float, float]]
    parallelized: bool

    def __post_init__(self):
        if self.capacity_utilization < 0:
            raise ValueError("Capacity utilization must be non-negative.")
        if self.capacity_utilization == 0:
            _LOGGER.warning(f"Capacity utilization is zero for {self}.")

    @property
    def min_eu_per_tick(self) -> float:
        return self.min_total_eu / (self.processing_time * 20) if self.processing_time > 0 else 0.0

    @property
    def max_eu_per_tick(self) -> float:
        return self.max_total_eu / (self.processing_time * 20) if self.processing_time > 0 else 0.0

    def input_dict(self, input_combination: InputCombination) -> frozendict[Material, float]:
        return frozendict({input_combination[g]: a for g, a in self.average_inputs.items()})

    @property
    def output_dict(self) -> frozendict[Material, float]:
        return get_output_dict(self.output_specifications)
    
    @property
    def is_valid(self) -> bool:
        return True
