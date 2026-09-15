# Update Library

[![Open your Home Assistant instance and show your service developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=powercalc.update_library)

Checks powercalc library for updates and updates the library.
Additionally starts discovery of new profiles.

If an updated profile requires a newer Powercalc version, Powercalc keeps using the compatible copy already downloaded
on your installation. Its model lookup and discovery information remain available after a library update or restart.
After you upgrade Powercalc, the newer profile becomes eligible for download when the profile is next loaded.

This fallback requires a usable cached profile. A fresh installation, a cleared cache, or a downgrade below the installed
profile's minimum version may require upgrading Powercalc before the profile can be used. Powercalc does not download
historical profile revisions.

Profile updates are downloaded and checked before replacing the installed files and their metadata. If an update fails,
Powercalc continues using the compatible installed copy.

## Example

```yaml
action: powercalc.update_library
data: {}
```
