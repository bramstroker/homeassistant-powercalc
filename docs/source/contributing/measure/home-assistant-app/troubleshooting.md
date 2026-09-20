# App troubleshooting

## A device or sensor is not listed

Confirm that the entity is available in Home Assistant and belongs to the required domain for the selected measurement. Power sensors must report `W`; optional voltage sensors must report `V`. Correct the source integration or unit, then reload the app.

## Power-meter validation warns about quality

Watch the sensor in Home Assistant Developer Tools while changing the load. The source should expose at least one decimal place and publish a new reading every two seconds or faster where possible. Increase the source integration's update rate or use a faster meter before starting the full measurement.

## Dummy-load calibration is unavailable or unstable

Confirm that the configured meter provides voltage readings. Home Assistant voltage sensors must report `V`; a Shelly, Kasa, or Tapo plug must expose voltage through its device API. The synthetic test meter does not support calibration.

If resistance does not stabilize, allow the load to warm up longer and ensure no other load behind the meter is changing. Recalibrate after correcting the setup. Do not continue with a stored calibration when the physical load, meter, or wiring has changed.

## Shelly discovery does not find the plug

Confirm that Home Assistant and the Shelly are on a network where mDNS discovery is available. IPv6-only and non-private addresses are not accepted. You can enter the device's private IPv4 address manually when discovery is unavailable.

## Ingress disconnected

Reload the app. Browser and ingress connections do not control the worker, and the UI restores the authoritative session snapshot. Review app logs if reconnecting continues to fail.

## An interrupted run cannot resume

Resume is rejected when output is incomplete or settings that determine the measurement sequence changed. Preserve the existing files for diagnosis, then duplicate the session configuration and start a new measurement when appropriate.

## Storage errors

Check free disk space and the app log, then restart the app. Do not remove files from app data while a measurement is active. Restore the app data from a Home Assistant backup if needed.

## Reporting a problem

Enable debug logging in the app configuration and restart the app before reproducing the issue. After the session, download its diagnostics from the result view and attach that file to the issue together with the app log. Disable debug logging again after collecting the information.
