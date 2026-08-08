from __future__ import annotations
import logging
from dataclasses import dataclass


from .machines import Machine
from .machine_options.machine_options import MachineOptions

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


@dataclass(frozen=True)
class RecipeEnvironment:
    """
    Holds all information about the environment in which a recipe is executed, i.e. the machine, 
    voltage tier and machine options.
    """
    machine: Machine
    voltage_tier: int
    machine_options: MachineOptions

    def copy(
        self,
        machine: Machine | None = None,
        voltage_tier: int | None = None,
        machine_options: MachineOptions | None = None
    ) -> RecipeEnvironment:
        return RecipeEnvironment(
            machine=self.machine if machine is None else machine,
            voltage_tier=self.voltage_tier if voltage_tier is None else voltage_tier,
            machine_options=self.machine_options if machine_options is None else machine_options
        )
