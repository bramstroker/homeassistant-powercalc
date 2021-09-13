import pyShelly


def device_added(dev, code):
    print(dev, " ", code)


shelly = pyShelly.pyShelly()
print("version:", shelly.version())

shelly.cb_device_added.append(device_added)
shelly.start()
shelly.discover()

while True:
    pass
