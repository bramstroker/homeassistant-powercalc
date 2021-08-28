from .powermeter import PowerMeter

class TasmotaPowerMeter(PowerMeter):
    def get_power(self) -> float:
        return 0
