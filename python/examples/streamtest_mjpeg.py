#!/usr/bin/env python3

'''
Streamtest is a simple utility to demonstrate streaming the frames from a tCam-Mini to a canvas real time.

author: bitreaper
'''

import base64
import argparse
import time
import numpy as np
from tcam import TCam
from io import BytesIO
from array import array
from PIL import Image
from threading import Event
from palettes import ironblack_palette
from http.server import BaseHTTPRequestHandler, HTTPServer
import socket

def request_headers():
    return {
        'Cache-Control': 'no-store, no-cache, must-revalidate, pre-check=0, post-check=0, max-age=0',
        'Connection': 'close',
        'Content-Type': 'multipart/x-mixed-replace;boundary=--boundarydonotcross',
        'Expires': 'Mon, 3 Jan 2000 12:34:56 GMT',
        'Pragma': 'no-cache',
    }

def image_headers(size):
    return {
        'X-Timestamp': time.time(),
        'Content-Length': size,
        #FIXME: mime-type must be set according file content
        'Content-Type': 'image/jpeg',
    }

class MyHandler(BaseHTTPRequestHandler):
    clientsConnected = 0

    def handle(self):
        """Handles a request ignoring dropped connections."""
        try:
            return BaseHTTPRequestHandler.handle(self)
        except (socket.error, socket.timeout) as e:
            self.clientsConnected = self.clientsConnected - 1
            print(f"handle: clients connected {self.clientsConnected} => {e}")

    def do_GET(self):
        self.clientsConnected = self.clientsConnected + 1

        print(f"GET: clients connected {self.clientsConnected} => {self.connection}")

        self.send_response(200)

        for k, v in request_headers().items():
            self.send_header(k, v)

        while self.clientsConnected > 0:
            if tcam.frameQueue.empty():
                evt.wait(.05)
            else:
                self.end_headers()
                self.wfile.write('--boundarydonotcross'.encode())
                self.end_headers()

                image = convert(tcam.get_frame())
                frame_image = Image.fromarray(image)
                f = BytesIO()
                frame_image.save(f, "jpeg")
                f.seek(0)

                for k, v in image_headers(f.tell()).items():
                    self.send_header(k, v)

                self.end_headers()

                for chunk in f:
                    countWritten = self.wfile.write(chunk)
                    print(f"GET: written {countWritten} => {self.connection}")

    def log_message(self, format, *args):
        return


def convert(img):

    dimg = base64.b64decode(img["radiometric"])
    ra = array('H', dimg)

    imgmin = 65535
    imgmax = 0
    for i in ra:
        if i < imgmin:
            imgmin = i
        if i > imgmax:
            imgmax = i

    ## setting min and max
    imgmin = 28915
    imgmax = 31615
    ###
    delta = imgmax - imgmin
    # print(f"Max val is {imgmax}, Min val is {imgmin}, Delta is {delta}")
    a = np.zeros((120,160,3), np.uint8)

    for r in range(0, 120):
        for c in range(0, 160):
            currVal = ra[(r * 160) + c]
            #t = (currVal / 100) - 273.15
            #print(f"({c}, {r}): {t}")
            val = int((currVal - imgmin) * 255 / delta)
            if val > 255:
                a[r, c] = ironblack_palette[255]
            else:
                a[r, c] = ironblack_palette[val]
    return a

def update():
    if tcam.frameQueue.empty():
        evt.wait(.05)
    else:
        image = convert(tcam.get_frame())
        frame_image = Image.fromarray(image)
        f = BytesIO()
        frame_image.save(f, "jpeg")
        f.seek(0)


########### Main Program ############
# https://stackoverflow.com/questions/21197638/create-a-mjpeg-stream-from-jpeg-images-in-python

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.prog = "streamtest"
    parser.description = f"{parser.prog} - an example program to stream images from tCam-mini and display as video\n"
    parser.usage = "streamtest.py --ip=<ip address of camera>"
    parser.add_argument("-i", "--ip", help="IP address of the camera")

    args = parser.parse_args()

    if not args.ip:
        args.ip = "192.168.1.139"
        print(f"Using default of {args.ip}")

    tcam = TCam()
    tcam.connect(args.ip)


    evt = Event()

    try:
        # prime the frame with the first image, avoids a strange shaped window showing up due to drawing the
        # first frame before an image is in the queue
        image = convert(tcam.get_image())
        frame_image = Image.fromarray(image)

        ret = tcam.start_stream()

        update()

        httpd = HTTPServer(('', 8001), MyHandler)
        httpd.serve_forever()

    except KeyboardInterrupt:
        evt.set()
        httpd.server_close()
        tcam.shutdown()