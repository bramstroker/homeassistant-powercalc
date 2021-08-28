from .powermeter import PowerMeter

class HassPowerMeter(PowerMeter):
    def get_power(self) -> float:
        return 0
