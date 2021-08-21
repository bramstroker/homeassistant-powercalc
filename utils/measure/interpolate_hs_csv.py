import csv
import sys
from typing import Iterator

import numpy as np
from scipy.interpolate import griddata

# default from measure.py
BRIGHTNESS_STEP=10
SATURATION_STEP=10
HUE_STEP=2000

def inclusive_range(start: int, end: int, step: int) -> Iterator[int]:
    i = start
    while i < end:
        yield i
        i += step
    yield end

def main(filename):
    grid_bri,grid_hue,grid_sat = np.mgrid[1:256:1,1:65536:1000,1:255:1]
    points = []
    values = []

    with open(filename) as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        next(reader, None)
        print("bri,hue,sat,watt")
        for row in reader:
            #print("%d,%d,%d,%.12g"%(int(row[0]),int(row[1]),int(row[2]),round(float(row[3]),2)))
            point = [row[0],int(row[1]),row[2]]
            points.append(point)
            values.append(row[3])

        fullgrid = griddata(points, values, (grid_bri,grid_hue,grid_sat), method='linear')
 
        for bri in inclusive_range(1, 255, BRIGHTNESS_STEP):
            for sat in inclusive_range(1, 254, SATURATION_STEP):
                for hue in inclusive_range(1, 65535, HUE_STEP):
                    print("%d,%d,%d,%.12g"%(bri,hue,sat,round(fullgrid[int(bri-1),int((hue-1)/1000),int(sat-1)],2)))

if __name__ == "__main__":
    main(sys.argv[1])

