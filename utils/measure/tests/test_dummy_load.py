import hashlib

from measure.dummy_load import power_meter_fingerprint
from measure.powermeter.spec import ShellyPowerMeterSpec


def test_shelly_automatic_channel_preserves_existing_calibration_identity() -> None:
    legacy_spec = '{"type":"shelly","device_ip":"192.168.1.50","username":"admin","timeout":5}'
    spec = ShellyPowerMeterSpec(device_ip="192.168.1.50")

    assert power_meter_fingerprint(spec) == hashlib.sha256(legacy_spec.encode()).hexdigest()


def test_shelly_outlets_have_distinct_calibration_identities() -> None:
    spec = ShellyPowerMeterSpec(device_ip="192.168.1.50")
    fingerprints = [power_meter_fingerprint(spec.model_copy(update={"channel": channel})) for channel in [None, 0, 1]]

    assert len(set(fingerprints)) == 3
