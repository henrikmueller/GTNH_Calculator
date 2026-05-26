from __future__ import annotations
from abc import abstractmethod
from typing import Dict, Any
from dataclasses import dataclass
from math import floor, isnan
import logging

from packages.recipes_db import recipe_options

from .overclock_behaviours import OverclockBehaviour, OverclockContext
from .parallel_behaviours import ParallelBehaviour
from .energy_behaviour import EnergyBehaviour, EnergyContext
from .heat_capacity_behaviour import HeatCapacityBehaviour
from .speedup_behaviour import SpeedupBehaviour
from ..raw_recipes import RawRecipe
from ..machine_stats import MachineStats
from ..machine_options.machine_options import MachineOptions
from ..machine_options.machine_option_types import MachineOptionType
from ..voltage_tiers import VoltageTier

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass(frozen=True)
class MachineBehaviour:
    overclock_behaviour: OverclockBehaviour
    parallel_behaviour: ParallelBehaviour
    energy_behaviour: EnergyBehaviour
    heat_capacity_behaviour: HeatCapacityBehaviour
    speedup_behaviour: SpeedupBehaviour

    @abstractmethod
    def fit_recipe(
        self,
        raw_recipe: RawRecipe,
        voltage_tier: int,
        machine_stats: MachineStats,
        machine_options: MachineOptions,
        log=False
    ) -> RawRecipe | None:
        ...

    @classmethod
    def create_machine_behaviour(cls, specification: Dict[str, Any]) -> MachineBehaviour:
        overclock_behaviour = OverclockBehaviour.create_overclock_behaviour(
            specification['overclock_behaviour'] if 'overclock_behaviour' in specification.keys() else None
        )
        parallel_behaviour = ParallelBehaviour.create_parallel_behaviour(
            specification['parallel_behaviour'] if 'parallel_behaviour' in specification.keys() else None
        )
        energy_behaviour = EnergyBehaviour.create_energy_behaviour(
            specification['energy_behaviour'] if 'energy_behaviour' in specification.keys() else None
        )
        heat_capacity_behaviour = HeatCapacityBehaviour.create_heat_capacity_behaviour(
            specification['heat_capacity_behaviour'] if 'heat_capacity_behaviour' in specification.keys() else None
        )
        speedup_behaviour = SpeedupBehaviour.create_speedup_behaviour(
            specification['speedup_behaviour'] if 'speedup_behaviour' in specification.keys() else None
        )
        behaviours = [
            overclock_behaviour, parallel_behaviour, energy_behaviour, heat_capacity_behaviour, speedup_behaviour
        ]

        if 'machine_behaviour' in specification:
            match specification['machine_behaviour']['type']:
                case 'neutron_activator':
                    return NeutronActivatorBehaviour(*behaviours)
                case _:
                    return NotImplementedMachineBehaviour(*behaviours)
        else:
            return DefaultMachineBehaviour(*behaviours)


@dataclass(frozen=True)
class DefaultMachineBehaviour(MachineBehaviour):
    def fit_recipe(
        self,
        raw_recipe: RawRecipe,
        voltage_tier: int,  # of the machine
        machine_stats: MachineStats,
        machine_options: MachineOptions,
        log=False
    ) -> RawRecipe | None:
        if raw_recipe.total_eu > 0:
            # EU Generators cannot be overclocked
            return raw_recipe
        if voltage_tier not in machine_stats.voltage_tiers:
            raise ValueError(f'Voltage tier {voltage_tier} is invalid for machine stats {machine_stats}.')
        
        heat_capacity = self.heat_capacity_behaviour.get_heat_capacity(
            machine_voltage_tier=voltage_tier,
            machine_options=machine_options
        )
        if not isnan(raw_recipe.recipe_options.coil_heat) and heat_capacity < raw_recipe.recipe_options.coil_heat:
            return None  # Cannot fit the recipe to the machine due to insufficient heat capacity
        if not isnan(raw_recipe.recipe_options.fusion_tier) and machine_stats.fusion_tier < raw_recipe.recipe_options.fusion_tier:
            return None  # Cannot fit the recipe to the machine due to insufficient fusion tier
        

        # EU Generator efficiency missing
        speedup = self.speedup_behaviour.get_speedup_multiplier(machine_options=machine_options)

        recipe_min_temperature = raw_recipe.recipe_options.coil_heat
        if not isnan(recipe_min_temperature) and heat_capacity < recipe_min_temperature:
            raise ValueError(
                f'Heat Capacity {heat_capacity} not sufficient for the recipe temperature {recipe_min_temperature}')

        energy_context = EnergyContext(
            machine_options=machine_options,
            recipe_options=raw_recipe.recipe_options,
            machine_heat_capacity=heat_capacity,
        )
        energy_multiplier = self.energy_behaviour.get_energy_multiplier(energy_context)
        max_parallels = self.parallel_behaviour.get_parallels(
            voltage_tier=voltage_tier,
            machine_options=machine_options
        )

        max_eu_per_tick = VoltageTier.eu_per_tick(voltage_tier) * raw_recipe.amperage
        reduced_eu_per_tick = abs(energy_multiplier * raw_recipe.eu_per_tick)  # eu_per_tick is before parallels
        used_parallels = min(floor(max_eu_per_tick // reduced_eu_per_tick), max_parallels) if reduced_eu_per_tick > 0 \
            else max_parallels

        max_overclocks = self.overclock_behaviour.get_max_overclocks(voltage_tier)
        overclock_context = OverclockContext(
            current_eu_per_tick=used_parallels * reduced_eu_per_tick,
            max_eu_per_tick=max_eu_per_tick,
            max_overclocks=max_overclocks,
            machine_stats=machine_stats,
            recipe_options=raw_recipe.recipe_options,
            machine_heat_capacity=heat_capacity
        )
        non_perfect_overclocks, perfect_overclocks = self.overclock_behaviour.get_overclocks(overclock_context)

        total_eu = (raw_recipe.total_eu * energy_multiplier * used_parallels *
                    2 ** non_perfect_overclocks / speedup)
        processing_time = (raw_recipe.processing_time / speedup /
                           (4 ** perfect_overclocks * 2 ** non_perfect_overclocks))
        eu_per_tick = total_eu / processing_time / 20 if processing_time > 0 else 0
        inputs = {
            m: used_parallels * a for m, a in raw_recipe.inputs.items()
        }
        output_specifications = {
            index: (m, used_parallels * a, p) for index, (m, a, p) in raw_recipe.output_specifications.items()
        }

        def print_logs():
            _LOGGER.warning(raw_recipe)
            _LOGGER.warning(self)
            _LOGGER.warning(f'energy_context: {energy_context}')
            _LOGGER.warning(f'overclock_context: {overclock_context}')
            _LOGGER.warning(f'max_parallels: {max_parallels}')
            _LOGGER.warning(f'max_eu_per_tick: {max_eu_per_tick}')
            _LOGGER.warning(f'reduced_eu_per_tick: {reduced_eu_per_tick}')
            _LOGGER.warning(f'used_parallels: {used_parallels}')
            _LOGGER.warning(f'max_overclocks: {max_overclocks}')
            _LOGGER.warning(f'non_perfect_overclocks: {non_perfect_overclocks}')
            _LOGGER.warning(f'perfect_overclocks: {perfect_overclocks}')
            _LOGGER.warning(f'energy_multiplier: {energy_multiplier}')
            _LOGGER.warning(f'total_eu: {total_eu}')
            _LOGGER.warning(f'processing_time: {processing_time}')
            _LOGGER.warning(f'eu_per_tick: {eu_per_tick}')
            _LOGGER.warning('')

        if log:
            print_logs()

        new_raw_recipe = RawRecipe(
            eu_per_tick=eu_per_tick,
            processing_time=processing_time,
            amperage=raw_recipe.amperage,
            voltage_tier=voltage_tier,
            inputs=inputs,
            output_specifications=output_specifications,
            recipe_options=raw_recipe.recipe_options,
            used_parallels=used_parallels
        )
        return new_raw_recipe


@dataclass(frozen=True)
class NeutronActivatorBehaviour(MachineBehaviour):
    def fit_recipe(
        self,
        raw_recipe: RawRecipe,
        voltage_tier: int,
        machine_stats: MachineStats,
        machine_options: MachineOptions,
        log=False
    ) -> RawRecipe | None:
        speedup = 1
        processing_time = (raw_recipe.processing_time / speedup)
        eu_per_tick = -6  # As if ULV Accelerator is used
        voltage_tier = VoltageTier.voltage_tier_by_eu(abs(eu_per_tick))

        new_raw_recipe = RawRecipe(
            eu_per_tick=eu_per_tick,
            processing_time=processing_time,
            amperage=raw_recipe.amperage,
            voltage_tier=voltage_tier,
            inputs=raw_recipe.inputs,
            output_specifications=raw_recipe.output_specifications,
            recipe_options=raw_recipe.recipe_options,
            used_parallels=1
        )
        return new_raw_recipe


@dataclass(frozen=True)
class NotImplementedMachineBehaviour(MachineBehaviour):
    def fit_recipe(
        self,
        raw_recipe: RawRecipe,
        voltage_tier: int,
        machine_stats: MachineStats,
        machine_options: MachineOptions,
        log=False
    ) -> RawRecipe | None:
        raise NotImplementedError('Machine Behaviour not implemented')
