import cv2
from math import atan, degrees
#top left (x,y) representing top left corner of tube box
#bottom right (x,y) same as above
#center (x,y) same as above
def get_degrees(top_left, bottom_right, center, img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    img_out = cv2.Canny(gray, 100, 150)
    first_white_col, first_white_row = top_left[1], top_left[0]
    done = 0
    for row in range(top_left[0], bottom_right[0]):
        for col in range(top_left[1], bottom_right[1]):
            if img_out[col][row] > 0:
                first_white_col, first_white_row = col, row
                done = 1
                break
        if done:
            break
    
    tan_triangle = abs(center[1] - first_white_col) / abs(center[0] - first_white_row)
    degrees_off_axis =  90 - degrees(atan(tan_triangle))
    if(first_white_col > center[1]):
        degrees_off_axis = 180 - degrees_off_axis
    print(f"First white pixel: {first_white_col} {first_white_row}")
    print(f"Center: {center[0]}, {center[1]}")
    print(f"Degrees from y-axis = {degrees_off_axis} and {done}")
    return(degrees_off_axis)
