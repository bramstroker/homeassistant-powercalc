import ShellyPy

device = ShellyPy.Shelly("192.168.178.254")

# device.relay(0, turn=True)
while True:
    emeter = device.emeter("power")
    pass
