from .powermeter import PowerMeter

class KasaPowerMeter(PowerMeter):
    def get_power(self) -> float:
        return 0
