## Software
* PhotoBooth_3Img_mariage.py : PhotoBooth main daemon. handle taking picture and upload to google drive
* listen-for-shutdown.py : management software :
  * starting/stopping camera_btn.py (short press)
  * powering off RPi (long press)
* *.service : systemctl services definition

## Install

Based on [Raspbian](https://www.raspberrypi.org/downloads/raspbian/)

Install shutdown service

    sudo cp listen-for-shutdown.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable listen-for-shutdown.service
    sudo systemctl start listen-for-shutdown.service

Install Photobooth service

    sudo cp photobooth.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable photobooth.service
    sudo systemctl start photobooth.service

Install needed python modules

    pip install --upgrade google-api-python-client

get api ID clients OAuth 2.0 client_id.json and put in current directory. See https://console.developers.google.com/apis/credentials

## Customization
There's some images displayed by the PhotoBooth service. They are overlayed on top of the live image.
The documentation explains how to change these images

