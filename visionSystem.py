#boot pathing
import sys
sys.path.append(".")
sys.path.append("/usr/local/lib")
sys.path.append("/usr/local/lib/python3.8/pyrealsense2")

import pyrealsense2 as rs
import numpy as np
import cv2
import time
import torch
import math
import edge


class VisionSystem:
    def __init__(self, directoryOfNNWeights='/home/herbie/OVision2022/yolov5',
                 nameOfWeights="/home/herbie/OVision2022/yolov5/last.pt"):
        self.model = torch.hub.load(directoryOfNNWeights, 'custom',
                                    path=nameOfWeights,
                                    source='local')
        self.pipeline = rs.pipeline()
        self.config = rs.config()
        
       
        self.config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
        self.config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

    def processOneFrame(self):
        '''
        Processes a frame and returns the x, y, depth, orientation
        3 possible outputs
            int, int, int, int -> found a tube and all relevant info
            int, int, 0, int -> found a tube but couldnt get depth info
            -1, -1, -1, -1 -> no tube found
        '''
        color_frame, depth_frame = self.captureImage()
        results = self.checkForTube(color_frame)
        return self.getTubeData(color_frame, depth_frame, results)

    def captureImage(self):
        self.pipeline.start(self.config)
        frames = self.pipeline.wait_for_frames()
        depth_frame = frames.get_depth_frame()
        color_frame = frames.get_color_frame()
        self.pipeline.stop()
        return color_frame, depth_frame 

    def checkForTube(self, color_frame):
        color_image = np.asanyarray(color_frame.get_data())
        results = self.model(color_image)
        results.render()
        highestConf = -1
        bestResults = None
        #print(results.xyxy)
        if not results.xyxy:
            return None

        for i in results.xyxy[0]:
            if i[5] > highestConf:
                bestResults = i

        return bestResults

    def getTubeData(self, color_frame, depth_frame, tubeResults):
        if tubeResults is not None:
            centerx, centery = self.getTubePixelCoordinates(tubeResults)
            realx, realy, depth = self.translatePixelsToReal(centerx, centery, depth_frame)
            orientation = self.getTubeOrientation(color_frame, tubeResults, centerx, centery)
            return realx, realy, depth, orientation
        return -1, -1, -1, -1

    def getTubePixelCoordinates(self, tubeResults):
        centerx = int((tubeResults[0] + tubeResults[2]) / 2)
        centery = int((tubeResults[1] + tubeResults[3]) / 2)
        return centerx, centery

    def translatePixelsToReal(self, centerx, centery, depth_frame):
        depth = depth_frame.get_distance(centerx, centery) * 100
        realx = (centerx - 320) * depth / 386
        realy = (centery - 240) * depth / 386
        return realx, realy, depth

    def getTubeOrientation(self, color_frame, tubeResults, centerx, centery):
        xdist = (tubeResults[0] - tubeResults[2])
        ydist = (tubeResults[1] - tubeResults[3])
        ratio = xdist / ydist

        if ratio > 3:
            return 90
        elif ratio < .55:
            return 0

        color_image = np.asanyarray(color_frame.get_data())
        return int(edge.get_degrees(
            (int(tubeResults[0]), int(tubeResults[1])),
            (int(tubeResults[2]), int(tubeResults[3])),
            (centerx, centery),
            color_image)
        )


#vs = VisionSystem()
#while(True):
 #   print(vs.processOneFrame())
  #  time.sleep(1)
