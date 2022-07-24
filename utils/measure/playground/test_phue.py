from phue import Bridge, PhueRegistrationException


def initialize_hue_bridge() -> Bridge:
    # f = open("bridge_user.txt", "r+")

    # authenticated_user = f.read()
    # if len(authenticated_user) > 0:
    #     bridge.username = authenticated_user

    try:
        bridge = Bridge("192.168.178.44")
        # bridge.connect()
    except PhueRegistrationException:
        print("Please click the link button on the bridge, than hit enter..")
        input()
        bridge = Bridge("192.168.178.44")

    return bridge


b = initialize_hue_bridge()

lights = b.lights

# Print light names
for l in lights:
    print(l.name)
