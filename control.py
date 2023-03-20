import math
import cv2
import numpy as np
from Nano_I2C import *
from visionSystem import VisionSystem

#Old Offset in centimeters
#offset_x = 2.9
#offset_y = 4.9
#offset_z = 23.544

# New Offset in centimeters
offset_x = 7.9
offset_y = 6.1
offset_z = 23.544
camera_angle = math.radians(60)

def get3Dlocation(realWorldCords):
    return (realWorldCords[0] ** 2 + realWorldCords[1] ** 2 + realWorldCords[2] ** 2) ** 0.5

def translateCoordinates(x, y, depth):
        #print(f'X: {x} Y: {y} depth: {depth}')
        camera_hyp = (x ** 2 + y ** 2) ** 0.5
        center_depth = (depth ** 2 - camera_hyp ** 2) ** 0.5
        #real_z = depth * math.cos(camera_angle + math.atan(y/center_depth))
        groundhyp = depth * math.sin(camera_angle + math.atan(-y/center_depth))
        
        real_z = (depth**2 - groundhyp ** 2) ** .5
        #print(math.atan(y/center_depth))
        #print(groundhyp)
        real_y = (groundhyp ** 2 - x ** 2) ** .5
        return x + offset_x, real_y + offset_y, real_z - offset_z

def checkTubeLocationValidity(realWorldCords):
    match = [0] * 5
    threshold = 10
    matchAmount = 0
    result = (0, 0, 0, 0)
    for i in range(5):
        for j in range(5):
            if j != i :
                if abs(get3Dlocation(realWorldCords[i]) - get3Dlocation(realWorldCords[j])) < threshold:
                    match[j] = 1
        for k in range(5):
            if match[k] == 1:
                result = tuple(sum(x) for x in zip(result, realWorldCords[k]))
                matchAmount+=1
                match[k] = 0
        if matchAmount >= 3:
            result = tuple(sum(x) for x in zip(result, realWorldCords[i]))
            result = tuple(x/(matchAmount+1) for x in result)
            result = result[:2] + (-result[2],) + result[3:]
            return result
        else:
            matchAmount = 0
            result = (0, 0, 0, 0)
    return -2

def collectTubeLocation(vis):
    consecutiveBad = 0
    consecutiveNone = 0
    good = 0
    cameraCords = 0
    realWorldCords = []
    while(good < 5 and consecutiveBad < 10 and consecutiveNone < 10):
        data = vis.processOneFrame()
        if(data[2] == - 1):
            consecutiveNone+=1
        elif(data[2] == 0):
            consecutiveBad+=1
            cameraCords+=data[0]/10
        else:
            realWorldCords.append(translateCoordinates(data[0], data[1], data[2]) + (data[3],))
            #print(realWorldCords[good])
            #realWorldCords.append(translateCoordinates(data[0],data[1],data[2]) + tuple(0))
            good+=1
            consecutiveBad = 0
            consecutiveNone = 0
    if(consecutiveNone >= 10):
        return -1
    elif(consecutiveBad >= 10):
        return cameraCords
    else:
        return checkTubeLocationValidity(realWorldCords)#tuple(x/5 for x in realWorldCords)

def main():
    # Initialize the I2C bus
    i2c = Nano_I2CBus()
    # Initialize the Vision System
    vis = VisionSystem()
    
    # Send ready command to Pi
    i2c.write_pkt('Ready'.encode(), 'd', 0)

    while True:
        # wait for packet to be recieved
        pkt = i2c.wait_response()

        if not pkt:
            continue

        # If the packet isn't the target ID (pi) and it isn't a command
        if (pkt[I2CPacket.id_index].decode() != i2c.pkt_targ_id) or (pkt[I2CPacket.stat_index] != b'c'):
            continue

        print('Command received:')

        data = pkt[I2CPacket.data_index].decode().strip('\0')
        print(data)
        
        # Read command and respond back to Pi
        if data == 'cord':
            result = collectTubeLocation(vis)
            if result == -2:
                response = 'error'.encode()
            elif result == -1:
                response = 'none'.encode()
            elif not isinstance(result, tuple):
                response = (f'turn: {"left" if result < 0 else "right"}').encode()
            else:
                s = "x{:.1f}y{:.1f}z{:.1f}a{:.1f}"
                response = s.format(*result)
            
            # Reply back to the Pi with a given response
            i2c.write_pkt(response.encode(), 'd', 0)
            print(response)
                
        elif data ==  'img':
            result = vis.captureImage()
            
            # timestamp the filename and create the image
            filename = time.strftime("%Y%m%d-%H%M%S") + '.JPG'
            cv2.imwrite(filename, np.asanyarray(result[0].get_data()))
            
            # send image to Pi
            i2c.file_send(filename)
                
        else: #Unkown Command
            response = 'Command not recognized'.encode()
            i2c.write_pkt(response, 'd', 0)

        time.sleep(2)

if __name__ == '__main__':
    main()
