import pyrealsense2 as rs
import numpy as np
import cv2
import time
import torch
import math
import edge

#MAIN

HEIGHT_OF_CAMERA = 45.0

# Build Neural Net
model = torch.hub.load('/home/herbie/OVision2022/pyrealsense/librealsense-2.51.1/build/', 'custom', path='best.pt', source='local')

# Set up pipeline
pipeline = rs.pipeline()
config = rs.config()

config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

# Start streaming
pipeline.start(config)

try:
    while True:

        # Wait for a coherent pair of frames: depth and color
        frames = pipeline.wait_for_frames()
        depth_frame = frames.get_depth_frame()
        color_frame = frames.get_color_frame()
        if not depth_frame or not color_frame:
            continue

        # Convert images to numpy arrays
        depth_image = np.asanyarray(depth_frame.get_data())
        color_image = np.asanyarray(color_frame.get_data())

        # Apply colormap on depth image (image must be converted to 8-bit per pixel first)
        depth_colormap = cv2.applyColorMap(cv2.convertScaleAbs(depth_image, alpha=0.03), cv2.COLORMAP_JET)

        image = color_image.copy()
        results = model(image)
        results.render()
        print(image.shape)
        print(color_image.shape)
        if len(results.xyxy) > 0 and len(results.xyxy[0]) > 0:
            centery = int((results.xyxy[0][0][1] + results.xyxy[0][0][3])/2)
            centerx = int((results.xyxy[0][0][0] + results.xyxy[0][0][2])/2)
            depth = depth_frame.get_distance(centerx, centery) * 100
            
            if (depth > 0): 
                real_x = (centerx - 320) * depth / 386
                groundhyp = (depth ** 2 - HEIGHT_OF_CAMERA ** 2) ** .5
                real_y = (groundhyp ** 2 - real_x ** 2) ** .5
                #real_y = (centery - 240) * depth_frame.get_distance(centerx, centery) /386
                #real_z = math.sqrt(pow(real_x, 2) + pow(real_y, 2))
                #real_depth_angle = math.asin(real_z / depth_frame.get_distance(centerx, centery))
                #real_xy_angle = math.atan(-real_y/real_x)

                xdist = (results.xyxy[0][0][0] - results.xyxy[0][0][2])
                ydist = (results.xyxy[0][0][1] - results.xyxy[0][0][3])
                ratio = xdist / ydist
                if (ratio > 3):
                    orient = "Orientation: 90.00"
                elif (ratio < .55):
                    orient = "Orientation: 0.00"
                else:
                    print("EDGE!! \n")
                    print(results.xyxy[0][0])
                    orient = "Orientation: " + str(round(edge.get_degrees((int(results.xyxy[0][0][0]), int(results.xyxy[0][0][1])), (int(results.xyxy[0][0][2]), int(results.xyxy[0][0][3])), (centerx, centery), color_image), 2))
                    
                print("Ratio: " + str(ratio) + "\n")
                cv2.putText(results.ims[0],
                        "X-Coord: " + str(round(real_x, 2)),
                        (10, 410),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        .5,
                        (0, 0, 255),
                        1)
                if (not isinstance(real_y, complex)): 
                    cv2.putText(results.ims[0],
                        "Y-Coord: " + str(round(real_y, 2)),
                        (10, 430),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        .5,
                        (0, 0, 255),
                        1)       
                cv2.putText(results.ims[0],
                        "   Depth: " + str(round(depth, 2)),
                        (10, 450),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        .5,
                        (0, 0, 255),
                        1)       
                cv2.putText(results.ims[0],
                        orient,
                        (10, 470),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        .5,
                        (0, 0, 255),
                        1)       
                #print("\nreal coords:", real_x, real_y, depth, "\n\n")
                cv2.circle(results.ims[0], (centerx, centery), 5, (0,0,255), 2)
                
                #print("x coordinate: " + str((centerx - 320) * depth_frame.get_distance(centerx, centery) /386))
                #print("y coordinate: " + str((centery - 240) * depth_frame.get_distance(centerx, centery) /386))
                #print("Tube is " + str(depth_frame.get_distance(centerx, centery)) + " m away")
                #print("Rotate " + str(real_xy_angle * 180 / math.pi) + " degrees in the xy plane and " + str(real_depth_angle * 180 / math.pi) + "degrees in the z plane")
            
        
        images = np.hstack((image, depth_colormap))
        # Show images
        cv2.namedWindow('RealSense', cv2.WINDOW_AUTOSIZE)
        cv2.imshow('RealSense', results.ims[0])

        cv2.waitKey(1)
finally:

    # Stop streaming
    pipeline.stop()
