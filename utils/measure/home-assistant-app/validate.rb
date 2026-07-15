# frozen_string_literal: true

require "yaml"
require "json"

root = File.expand_path(__dir__)
repository = YAML.safe_load(File.read(File.join(root, "repository.yaml")))
config = YAML.safe_load(File.read(File.join(root, "powercalc_measure", "config.yaml")))
frontend_path = File.join(root, "..", "frontend", "package.json")
frontend = JSON.parse(File.read(frontend_path)) if File.file?(frontend_path)

required_repository_keys = %w[name]
required_config_keys = %w[name version slug description arch]

missing_repository = required_repository_keys.reject { |key| repository.key?(key) }
missing_config = required_config_keys.reject { |key| config.key?(key) }
abort "Missing repository keys: #{missing_repository.join(', ')}" unless missing_repository.empty?
abort "Missing app keys: #{missing_config.join(', ')}" unless missing_config.empty?

abort "Unsupported architecture" unless config.fetch("arch").sort == %w[aarch64 amd64]
abort "App version must be a container tag" unless config.fetch("version").match?(/\A[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?\z/)
abort "App and frontend versions differ" if frontend && config.fetch("version") != frontend.fetch("version")
abort "App image must not include a tag" if config.fetch("image").include?("@") || config.fetch("image").split("/").last.include?(":")
abort "Ingress configuration is incomplete" unless config["ingress"] && config["ingress_stream"]
abort "Home Assistant API access is required" unless config["homeassistant_api"]
abort "Ingress source checks must remain enabled" unless config.dig("environment", "MEASURE_TRUSTED_INGRESS_ONLY") == "true"
abort "App must remain admin-only" if config["panel_admin"] == false
abort "App must remain experimental" unless config["stage"] == "experimental"
abort "Host ports must not be exposed" if config.key?("ports") || config["host_network"]
abort "App must not request privileged access" if config["full_access"] || config.key?("privileged")

%w[README.md DOCS.md CHANGELOG.md icon.png logo.png].each do |filename|
  abort "Missing #{filename}" unless File.file?(File.join(root, "powercalc_measure", filename))
end

icon = File.binread(File.join(root, "powercalc_measure", "icon.png"), 24)
logo = File.binread(File.join(root, "powercalc_measure", "logo.png"), 24)
png_signature = "\x89PNG\r\n\x1A\n".b
abort "icon.png must be a PNG" unless icon.start_with?(png_signature)
abort "logo.png must be a PNG" unless logo.start_with?(png_signature)
icon_width, icon_height = icon.unpack("@16N2")
abort "icon.png must be square" unless icon_width == icon_height
abort "icon.png must be at least 128px" unless icon_width >= 128

puts "Home Assistant app metadata is valid"
