import sys
import csv
import numpy as np
from scipy.interpolate import griddata
from typing import Iterator

# default from measure.py
BRIGHTNESS_STEP=5
MIRED_STEP=10
#BRIGHTNESS_STEP=30
#MIRED_STEP=30

def inclusive_range(start: int, end: int, step: int) -> Iterator[int]:
    i = start
    while i < end:
        yield i
        i += step
    yield end

def main(filename):
    # read min-max mired
    min_mired=10000
    max_mired=0
    with open(filename) as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        next(reader, None)
        for row in reader:
            mired = int(row[1])
            if mired < min_mired:
                min_mired = mired
            if mired > max_mired:
                max_mired = mired
    #print("min_mired: %d  max_mired: %d"%(min_mired,max_mired))

    grid_bri,grid_mired = np.mgrid[1:256:1,min_mired:max_mired+1:1]
    points = []
    values = []

    with open(filename) as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        next(reader, None)
        print("bri,mired,watt")
        for row in reader:
            #print("%d,%d,%d,%.12g"%(int(row[0]),int(row[1]),int(row[2]),round(float(row[3]),2)))
            point = [int(row[0]),int(row[1])]
            points.append(point)
            values.append(row[2])

        fullgrid = griddata(points, values, (grid_bri,grid_mired), method='linear')
 
        for bri in inclusive_range(1, 255, BRIGHTNESS_STEP):
            for mired in inclusive_range(min_mired, max_mired, MIRED_STEP):
                print("%d,%d,%.12g"%(bri,mired,round(fullgrid[int(bri-1),int(mired)-min_mired],2)))

if __name__ == "__main__":
    main(sys.argv[1])

