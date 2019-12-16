#!/usr/bin/env python

# press/release quickly button for start/stop photobooth service
# hold button for >2s for shutdown


from gpiozero import Button, LED
from subprocess import check_call, CalledProcessError, STDOUT
from signal import pause
import os

shutdown_btn = Button(5, hold_time=3)
ledRunning = LED(6)
FNULL = open(os.devnull, 'w')

def shutdown():
	#print ("btn held")
	ledRunning.blink(0.5, 0.5, 5, 0);
	check_call(['poweroff'])

def stop_start():
	#print ("btn released")
	try:
		check_call(['systemctl', 'status', 'photobooth.service'])
		# no error, service is running, stop it
		#print("Stopping photobooth")
		check_call(['systemctl', 'stop', 'photobooth.service'])
		ledRunning.off()
	except CalledProcessError:
		# error, service is not running, start it
		#print("Starting photobooth")
		check_call(['systemctl', 'start', 'photobooth.service'])
		ledRunning.on()

shutdown_btn.when_held = shutdown
shutdown_btn.when_released = stop_start
ledRunning.on()

pause()
