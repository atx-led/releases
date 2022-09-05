#!/usr/bin/python3

PORT = 33

def main():
    print('Initializing hat LED...')
    # Initialize GPIO
    import RPi.GPIO as GPIO
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(PORT, GPIO.OUT)
    # Turn on the green LED on the hat
    GPIO.output(PORT, 1)

if __name__ == '__main__':
    main()
