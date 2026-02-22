# Matter Device Identification Limitations

PowerCalc relies on model identifiers to match devices to power profiles.
When devices are added via Matter, the model information is replaced with a non-unique product ID, which is not unique for physical devices.

This prevents automatic profile matching.

## Affected Devices

| Vendor  | Reported Model                                                             | Matter Product ID | Problem |
|---------|----------------------------------------------------------------------------|-------------------|----------|
| Signify | [LCA014](https://github.com/bramstroker/homeassistant-powercalc/pull/4010) | 297               | Product ID shared across variants |
| Signify | [LCA015](https://github.com/bramstroker/homeassistant-powercalc/pull/4011) | 297               | Product ID shared across variants |

## Root Cause

Matter does not expose the original manufacturer model string.
Instead it exposes a product ID which is not unique enough for correct profile matching.

## Impact

- Auto discovery fails
- Users must configure manually
