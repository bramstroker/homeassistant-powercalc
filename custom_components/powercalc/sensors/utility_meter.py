from homeassistant.components.utility_meter import DEFAULT_OFFSET
from homeassistant.components.utility_meter.sensor import UtilityMeterSensor


class VirtualUtilityMeterSensor(UtilityMeterSensor):
    """Utility meter resets on each cycle (daily, hourly etc)"""

    def __init__(self, source_entity, name, meter_type, entity_id):
        super().__init__(source_entity, name, meter_type, DEFAULT_OFFSET, False)
        self.entity_id = entity_id
