from __future__ import annotations
from abc import abstractmethod
from typing import Dict, Any
from dataclasses import dataclass
from math import floor
import logging

from .overclock_behaviours import OverclockBehaviour
from .parallel_behaviours import ParallelBehaviour
from .energy_behaviour import EnergyBehaviour
from ..raw_recipes import RawRecipe
from ..machine_stats import MachineStats
from ..machine_options.machine_options import MachineOption
from ..voltage_tiers import VoltageTier

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass
class MachineBehaviour:
    overclock_behaviour: OverclockBehaviour
    parallel_behaviour: ParallelBehaviour
    energy_behaviour: EnergyBehaviour

    @abstractmethod
    def fit_recipe(
        self,
        raw_recipe: RawRecipe,
        voltage_tier: int,
        machine_stats: MachineStats,
        machine_options: list[MachineOption] | None,
        log=False
    ) -> RawRecipe:
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
        behaviours = [overclock_behaviour, parallel_behaviour, energy_behaviour]

        if 'machine_behaviour' in specification:
            match specification['machine_behaviour']['type']:
                case 'neutron_activator':
                    return NeutronActivatorBehaviour(*behaviours)
                case _:
                    return NotImplementedMachineBehaviour(*behaviours)
        else:
            return DefaultMachineBehaviour(*behaviours)


@dataclass
class DefaultMachineBehaviour(MachineBehaviour):
    def fit_recipe(
        self,
        raw_recipe: RawRecipe,
        voltage_tier: int,
        machine_stats: MachineStats,
        machine_options: list[MachineOption] | None,
        log=False
    ) -> RawRecipe:
        if raw_recipe.total_eu > 0:
            # EU Generators cannot be overclocked
            return raw_recipe

        # EU Generator efficiency missing
        speedup = machine_stats.speedup
        energy_multiplier = self.energy_behaviour.get_energy_multiplier(
            voltage_tier=voltage_tier,
            machine_options=machine_options
        )
        max_parallels = self.parallel_behaviour.get_parallels(
            voltage_tier=voltage_tier,
            machine_options=machine_options
        )

        max_eu_per_tick = VoltageTier.eu_per_tick(voltage_tier) * raw_recipe.amperage
        reduced_eu_per_tick = abs(energy_multiplier * raw_recipe.eu_per_tick)  # eu_per_tick is before parallels
        used_parallels = min(floor(max_eu_per_tick // reduced_eu_per_tick), max_parallels) if reduced_eu_per_tick > 0 \
            else max_parallels

        non_perfect_overclocks, perfect_overclocks = self.overclock_behaviour.get_overclocks(
            current_eu_per_tick=used_parallels * reduced_eu_per_tick,
            max_eu_per_tick=max_eu_per_tick
        )

        total_eu = (raw_recipe.total_eu * energy_multiplier * used_parallels *
                    2 ** non_perfect_overclocks / speedup)
        processing_time = (raw_recipe.processing_time / speedup /
                           (4 ** perfect_overclocks * 2 ** non_perfect_overclocks))
        eu_per_tick = total_eu / processing_time / 20 if processing_time > 0 else 0
        voltage_tier = VoltageTier.voltage_tier_by_eu(abs(eu_per_tick) / raw_recipe.amperage) \
            if eu_per_tick != 0 else VoltageTier.NO_REQUIREMENT
        inputs = {
            m: used_parallels * a for m, a in raw_recipe.inputs.items()
        }
        output_specifications = {
            index: (m, used_parallels * a, p) for index, (m, a, p) in raw_recipe.output_specifications.items()
        }

        if log:
            _LOGGER.warning(raw_recipe)
            _LOGGER.warning(self)
            _LOGGER.warning(f'max_parallels: {max_parallels}')
            _LOGGER.warning(f'max_eu_per_tick: {max_eu_per_tick}')
            _LOGGER.warning(f'reduced_eu_per_tick: {reduced_eu_per_tick}')
            _LOGGER.warning(f'used_parallels: {used_parallels}')
            _LOGGER.warning(f'non_perfect_overclocks: {non_perfect_overclocks}')
            _LOGGER.warning(f'perfect_overclocks: {perfect_overclocks}')
            _LOGGER.warning(f'energy_multiplier: {energy_multiplier}')
            _LOGGER.warning(f'total_eu: {total_eu}')
            _LOGGER.warning(f'processing_time: {processing_time}')
            _LOGGER.warning(f'eu_per_tick: {eu_per_tick}')
            _LOGGER.warning(f'voltage_tier: {voltage_tier}')
            _LOGGER.warning('')

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


class NeutronActivatorBehaviour(MachineBehaviour):
    def fit_recipe(
        self,
        raw_recipe: RawRecipe,
        voltage_tier: int,
        machine_stats: MachineStats,
        machine_options: list[MachineOption] | None,
        log=False
    ) -> RawRecipe:
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


class NotImplementedMachineBehaviour(MachineBehaviour):
    def fit_recipe(
        self,
        raw_recipe: RawRecipe,
        voltage_tier: int,
        machine_stats: MachineStats,
        machine_options: list[MachineOption] | None,
        log=False
    ) -> RawRecipe:
        raise NotImplementedError('Machine Behaviour not implemented')
