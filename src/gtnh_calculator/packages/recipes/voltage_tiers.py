

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
    def to_voltage_tier(cls, name: str) -> int:
        match name:
            case 'ULV': return 0
            case 'LV': return 1
            case 'MV': return 2
            case 'HV': return 3
            case 'EV': return 4
            case 'IV': return 5
            case 'LuV': return 6
            case 'ZPM': return 7
            case 'UV': return 8
            case 'UHV': return 9
            case 'UEV': return 10
            case 'UIV': return 11
            case 'UMV': return 12
            case 'UXV': return 13
            case 'MAX': return 14
            case _: return -1

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
                return 'LUV'
            case 7:
                return 'ZPM'
            case 8:
                return 'UV'
            case 9:
                return 'UHV'

    @classmethod
    def eu_per_tick(cls, voltage_tier: int) -> int:
        if voltage_tier < 0:
            return 0
        return 8 * 4**voltage_tier
