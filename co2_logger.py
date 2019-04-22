import asyncio
import csv
import datetime
import json
import time
import os

import hid

PRINT_USB_DEVICES = False
key = [0xc4, 0xc6, 0xc0, 0x92, 0x40, 0x23, 0xdc, 0x96]
MANUFACTURER_STRING = "Holtek"
# enumerate USB devices
if PRINT_USB_DEVICES:
    for d in hid.enumerate():
        keys = list(d.keys())
        keys.sort()
        for key in keys:
            print("%s : %s" % (key, d[key]))
        print()


def decrypt(key, data):
    # from https://github.com/KristofRobot/openhab-config/blob/master/co2mon/co2mon.py
    cstate = [0x48, 0x74, 0x65, 0x6D, 0x70, 0x39, 0x39, 0x65]
    shuffle = [2, 4, 0, 7, 1, 6, 5, 3]

    phase1 = [0] * 8
    for i, o in enumerate(shuffle):
        phase1[o] = data[i]

    phase2 = [0] * 8
    for i in range(8):
        # import pdb; pdb.set_trace()
        phase2[i] = phase1[i] ^ key[i]

    phase3 = [0] * 8
    for i in range(8):
        phase3[i] = ((phase2[i] >> 3) | (phase2[(i - 1 + 8) % 8] << 5)) & 0xff

    ctmp = [0] * 8
    for i in range(8):
        ctmp[i] = ((cstate[i] >> 4) | (cstate[i] << 4)) & 0xff

    out = [0] * 8
    for i in range(8):
        out[i] = (0x100 + phase3[i] - ctmp[i]) & 0xff

    return out


def hd(d):
    return " ".join("%02X" % e for e in d)


async def get_data(h):
    data = list(e for e in h.read(8))
    if data:
        return data
    await asyncio.sleep(0.5)


async def get_co2_temp_data(h, values={}, lastTemp=0, lastCO2=0):
    try:
        # read back the answer
        prev_CO2 = lastCO2
        while True:
            data = await get_data(h)
            if data:
                decrypted = decrypt(key, data)
                if decrypted[4] != 0x0d or (
                        sum(decrypted[:3]) & 0xff) != decrypted[3]:
                    print(hd(data), " => ", hd(decrypted), "Checksum error")
                else:
                    op = decrypted[0]
                    val = decrypted[1] << 8 | decrypted[2]

                    values[op] = val

                    if 0x50 in values and lastCO2 != values[0x50]:
                        print("CO2: %4i" % values[0x50])
                        lastCO2 = values[0x50]
                    if 0x42 in values and lastTemp != values[0x42]:
                        temperature = values[0x42] / 16.0 - 273.15
                        print("T: %2.2f" % (temperature))
                        lastTemp = round(temperature, 1)
                    if lastCO2:  # don't send empty values
                        return lastCO2, lastTemp
            else:
                print(f"no data {data}")
        print("Closing the device")
        h.close()

    except IOError as ex:
        print(ex)
        print(
            "You probably don't have the hard coded device. Update the hid.device line"
        )
        print(
            "in this script with one from the enumeration list output above and try again."
        )

    print("Done")


def init_holtek_device():
    print("Opening the device")
    # holtek (co2 logger brand) information
    holtek = [
        x for x in hid.enumerate()
        if x["manufacturer_string"] == MANUFACTURER_STRING
    ][0]
    h = hid.device()
    h.open_path(holtek["path"])

    print("Manufacturer: %s" % h.get_manufacturer_string())
    print("Product: %s" % h.get_product_string())
    print("Serial No: %s" % h.get_serial_number_string())

    # enable non-blocking mode TODO: check if this is required
    h.set_nonblocking(1)
    # set feature report
    feature_report = h.send_feature_report([0x0] + key)
    return h


async def main(loop):
    # Write data to file
    h = init_holtek_device()
    todays_date = datetime.datetime.today().strftime('%Y%m%d')
    with open(f"{todays_date}_co2_data.csv", 'w') as f:
        # write headers
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "CO2", "Temperature"])
        while True:
            co2, temp = await get_co2_temp_data(h)
            ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            writer.writerow([ts, co2, temp])
            f.flush()
            await asyncio.sleep(5)
            # print(gen)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main(loop))
