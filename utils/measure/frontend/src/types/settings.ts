import type { AppMeasurementDefaults, PowerMeterType } from "./measurement";

export type SettingsSection = "power_meter" | "profile" | "measure_tuning" | "github";

export interface AppSettings {
  default_power_entity_id: string | null;
  default_measure_device: string | null;
  default_measure_device_firmware?: string | null;
  default_contributor_name?: string | null;
  default_contributor_github?: string | null;
  default_contributor_email?: string | null;
  power_meter: PowerMeterType | null;
  shelly_ip: string | null;
  shelly_username?: string;
  shelly_password_configured?: boolean;
  kasa_ip: string | null;
  fast_test_mode: boolean;
  measurement_defaults: AppMeasurementDefaults;
}

export interface AppSettingsUpdate extends AppSettings {
  shelly_password?: string | null;
  clear_shelly_password?: boolean;
}
