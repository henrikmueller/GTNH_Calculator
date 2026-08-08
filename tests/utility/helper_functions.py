from typing import Dict
from frozendict import frozendict
import pytest
from typing import Any

from packages.recipes_db.behaviours.machine_behaviours import (
    MachineBehaviour, DefaultMachineBehaviour
)
from packages.recipes_db.behaviours.overclock_behaviours import (
    DefaultOverclockBehaviour, InfiniteOverclockBehaviour, CoilTemperatureOverclockBehaviour, FusionOverclockBehaviour
)
from packages.recipes_db.behaviours.parallel_behaviours import DefaultParallelBehaviour, EICParallelBehaviour
from packages.recipes_db.behaviours.energy_behaviour import CoilTemperatureEnergyBehaviour, DefaultEnergyBehaviour, CoilTierEnergyBehaviour
from packages.recipes_db.behaviours.heat_capacity_behaviour import (
    DefaultHeatCapacityBehaviour, EBFHeatCapacityBehaviour)
from packages.recipes_db.behaviours.speedup_behaviour import DefaultSpeedupBehaviour, CoilTemperatureSpeedupBehaviour
from packages.recipes_db.raw_recipes import RawRecipe
from packages.recipes_db.machine_stats import MachineStats, MachineStatType
from packages.recipes_db.material import ExtractedFluid, Material, MaterialGroup
from packages.recipes_db.recipe_options import RecipeOptions
from packages.recipes_db.machine_options.machine_options import MachineOptions, MachineOption
from packages.recipes_db.machine_options.machine_option_types import MachineOptionType


def get_test_material(name: str) -> Material:
    return ExtractedFluid(
        id=f"id_{name}",
        image_file_path="",
        name=name,
        mod="test",
        nbt="",
        tooltip="",
    )


def raw_recipe(
    eu_per_tick: float,
    processing_time: float,
    voltage_tier: int,
    inputs: Dict[MaterialGroup, float],
    output_specifications: Dict[int, tuple[Material, float, float]],
    amperage: int = 1,
    recipe_options: RecipeOptions | None = None
) -> RawRecipe:
    recipe_options = RecipeOptions(options=frozendict({})) if recipe_options is None else recipe_options
    return RawRecipe(
        category="",
        eu_per_tick=eu_per_tick,
        processing_time=processing_time,
        amperage=amperage,
        voltage_tier=voltage_tier,
        inputs=frozendict(inputs),
        output_specifications=frozendict(output_specifications),
        recipe_options=recipe_options,
    )


def machine_option(
    option_type: MachineOptionType,
    tier: int = 0,
    temperature: float | None = None,
    extra_options: dict[str, float] | None = None,
) -> MachineOption:
    materials = {"Test Machine Option": get_test_material("Test Machine Option")}
    opts: dict[str, float] = {"tier": float(tier)}
    if temperature is not None:
        opts["temperature"] = float(temperature)
    if extra_options:
        opts.update(extra_options)
    return MachineOption(
        extracted_materials=materials,
        name="Test Machine Option",
        option_type=option_type,
        options=opts,
    )


def machine_options_for_test(
    *options: tuple[MachineOptionType, MachineOption],
) -> MachineOptions:
    valid = tuple(t for t, _ in options)
    return MachineOptions(
        valid, {t: opt for t, opt in options},
        min_tier={t: -1 for t in valid}
    )

    
def empty_machine_options() -> MachineOptions:
    return MachineOptions((), {}, {})


def coil_only_machine_options(temperature: float = 3600.0, tier: int = 1) -> MachineOptions:
    return machine_options_for_test(
        (
            MachineOptionType.COIL,
            machine_option(MachineOptionType.COIL, tier=tier, temperature=temperature),
        ),
    )


def default_behaviour() -> MachineBehaviour:
    return DefaultMachineBehaviour(
        DefaultOverclockBehaviour(),
        DefaultParallelBehaviour(base_parallels=1, parallels_per_voltage_tier=0),
        DefaultEnergyBehaviour(energy_multiplier=1),
        DefaultHeatCapacityBehaviour(),
        DefaultSpeedupBehaviour()
    )


def large_chemical_reactor_behaviour() -> MachineBehaviour:
    return DefaultMachineBehaviour(
        InfiniteOverclockBehaviour(),
        DefaultParallelBehaviour(base_parallels=1, parallels_per_voltage_tier=0),
        DefaultEnergyBehaviour(energy_multiplier=1),
        DefaultHeatCapacityBehaviour(),
        DefaultSpeedupBehaviour()
    )


def industrial_electrolyzer_behaviour() -> MachineBehaviour:
    return DefaultMachineBehaviour(
        DefaultOverclockBehaviour(),
        DefaultParallelBehaviour(base_parallels=0, parallels_per_voltage_tier=2),
        DefaultEnergyBehaviour(energy_multiplier=0.9),
        DefaultHeatCapacityBehaviour(),
        DefaultSpeedupBehaviour(speedup_multiplier=2.8)
    )


def mega_ebf_behaviour() -> MachineBehaviour:
    return DefaultMachineBehaviour(
        CoilTemperatureOverclockBehaviour(),
        DefaultParallelBehaviour(base_parallels=256),
        CoilTemperatureEnergyBehaviour(),
        EBFHeatCapacityBehaviour(),
        DefaultSpeedupBehaviour()
    )


def mega_vacuum_freezer_behaviour() -> MachineBehaviour:
    return DefaultMachineBehaviour(
        DefaultOverclockBehaviour(),
        DefaultParallelBehaviour(base_parallels=256),
        DefaultEnergyBehaviour(energy_multiplier=1),
        DefaultHeatCapacityBehaviour(),
        DefaultSpeedupBehaviour()
    )


def pyrolyse_oven_behaviour() -> MachineBehaviour:
    return DefaultMachineBehaviour(
        DefaultOverclockBehaviour(),
        DefaultParallelBehaviour(base_parallels=1, parallels_per_voltage_tier=0),
        DefaultEnergyBehaviour(),
        DefaultHeatCapacityBehaviour(),
        CoilTemperatureSpeedupBehaviour(base_speed=0, speed_per_coil_tier=0.5)
    )


def oil_cracker_behaviour() -> MachineBehaviour:
    return DefaultMachineBehaviour(
        DefaultOverclockBehaviour(),
        DefaultParallelBehaviour(base_parallels=1, parallels_per_voltage_tier=0),
        CoilTierEnergyBehaviour(minimal_multiplier=0.5, multiplier_per_coil_tier=0.1),
        DefaultHeatCapacityBehaviour(),
        DefaultSpeedupBehaviour()
    )


def fusion_reactor_behaviour(fusion_mk: int) -> MachineBehaviour:
    return DefaultMachineBehaviour(
        FusionOverclockBehaviour(perfect_overclocks=fusion_mk >= 4),
        DefaultParallelBehaviour(base_parallels=1, parallels_per_voltage_tier=0),
        DefaultEnergyBehaviour(),
        DefaultHeatCapacityBehaviour(),
        DefaultSpeedupBehaviour()
    )


def eic_behaviour() -> MachineBehaviour:
    return DefaultMachineBehaviour(
        DefaultOverclockBehaviour(),
        EICParallelBehaviour(),
        DefaultEnergyBehaviour(),
        DefaultHeatCapacityBehaviour(),
        DefaultSpeedupBehaviour()
    )


def machine_stats(
    voltage_tiers: tuple[int, ...], additional_stats: Dict[MachineStatType, float] | None = None
) -> MachineStats:
    return MachineStats(
        voltage_tiers=voltage_tiers,
        additional_stats=frozendict({}) if additional_stats is None else frozendict(additional_stats)
    )


def assert_approximate_dict_equality(
    dict1: Dict[Any, Any] | frozendict[Any, Any],
    dict2: Dict[Any, Any] | frozendict[Any, Any],
    rel_tol: float = 1e-9,
    abs_tol: float = 0.0
) -> None:
    if dict1.keys() != dict2.keys():
        assert False, f"Keys do not match: {dict1.keys()} != {dict2.keys()}"
    for key in dict1.keys():
        assert dict1[key] == pytest.approx(dict2[key], rel=rel_tol, abs=abs_tol), f"Values for key {key} do not match: {dict1[key]} != {dict2[key]}"
