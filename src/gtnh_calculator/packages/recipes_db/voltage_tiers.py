from math import log, ceil


class VoltageTier:
    NO_REQUIREMENT: int = -1
    ULV: int = 0
    LV: int = 1
    MV: int = 2
    HV: int = 3
    EV: int = 4
    IV: int = 5
    LUV: int = 6
    ZPM: int = 7
    UV: int = 8
    UHV: int = 9
    UEV: int = 10
    UIV: int = 11
    UMV: int = 12
    UXV: int = 13
    MAX: int = 14

    @classmethod
    def valid_voltage_tiers(cls) -> list[int]:
        return [-1] + cls.voltage_tiers_int()

    @classmethod
    def number_of_voltage_tiers(cls) -> int:
        return 15

    @classmethod
    def int_to_voltage_tier(cls, voltage_tier_number: int) -> int:
        if voltage_tier_number < cls.NO_REQUIREMENT:
            return cls.NO_REQUIREMENT
        if voltage_tier_number > cls.MAX:
            return cls.MAX
        return voltage_tier_number

    @classmethod
    def to_voltage_tier(cls, name: str) -> int:
        match name:
            case 'ULV': return VoltageTier.ULV
            case 'LV': return VoltageTier.LV
            case 'MV': return VoltageTier.MV
            case 'HV': return VoltageTier.HV
            case 'EV': return VoltageTier.EV
            case 'IV': return VoltageTier.IV
            case 'LuV': return VoltageTier.LUV
            case 'ZPM': return VoltageTier.ZPM
            case 'UV': return VoltageTier.UV
            case 'UHV': return VoltageTier.UHV
            case 'UEV': return VoltageTier.UEV
            case 'UIV': return VoltageTier.UIV
            case 'UMV': return VoltageTier.UMV
            case 'UXV': return VoltageTier.UXV
            case 'MAX': return VoltageTier.MAX
            case _: return VoltageTier.NO_REQUIREMENT

    @classmethod
    def voltage_tier_name(cls, voltage_tier) -> str:
        match voltage_tier:
            case -1:
                return '-'
            case 0:
                return 'ULV'
            case 1:
                return 'LV'
            case 2:
                return 'MV'
            case 3:
                return 'HV'
            case 4:
                return 'EV'
            case 5:
                return 'IV'
            case 6:
                return 'LuV'
            case 7:
                return 'ZPM'
            case 8:
                return 'UV'
            case 9:
                return 'UHV'
            case 10:
                return 'UEV'
            case 11:
                return 'UIV'
            case 12:
                return 'UMV'
            case 13:
                return 'UXV'
            case 14:
                return 'MAX'

    @classmethod
    def eu_per_tick(cls, voltage_tier: int) -> int:
        if voltage_tier < 0:
            return 0
        return 8 * 4**voltage_tier

    @classmethod
    def voltage_tier_by_eu(cls, eu_per_tick: float | None) -> int:
        if eu_per_tick is None or eu_per_tick <= 0:
            return VoltageTier.NO_REQUIREMENT
        return max(ceil((log(abs(eu_per_tick), 2) - 1) / 2) - 1, 0)

    @classmethod
    def max_overclocks(cls, base_voltage_tier: int, actual_voltage_tier: int) -> int:
        if base_voltage_tier >= VoltageTier.LV:
            return max(actual_voltage_tier - base_voltage_tier, 0)
        if base_voltage_tier == VoltageTier.ULV:
            return max(actual_voltage_tier - base_voltage_tier - 1, 0)
        return 0

    @classmethod
    def voltage_tiers(cls, minimum: int | None = None) -> list[str]:
        """
        List does not include the "No Requirement"-Voltage Tier
        :return:
        """
        if minimum is None:
            return [VoltageTier.voltage_tier_name(v) for v in range(VoltageTier.number_of_voltage_tiers())]
        return [VoltageTier.voltage_tier_name(v) for v in range(minimum, VoltageTier.number_of_voltage_tiers())]

    @classmethod
    def voltage_tiers_int(cls, minimum: int | None = None) -> list[int]:
        """
        List does not include the "No Requirement"-Voltage Tier
        :return:
        """
        if minimum is None:
            return list(range(VoltageTier.number_of_voltage_tiers()))
        return list(range(minimum, VoltageTier.number_of_voltage_tiers()))
