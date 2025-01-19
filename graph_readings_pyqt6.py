import serial
# import time
import re  # regex, for text processing
import numpy as np  # for fixed-size arrays
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton
# from PyQt6.QtWidgets import *
from PyQt6 import QtCore
import pyqtgraph as pg
import sys

ARDUINO_SERIAL_PORT = '/dev/ttyACM0'
ARDUINO_BAUD_RATE = 57600
TIMEOUT = 3
NUM_PD_READINGS_PER_CYCLE = 1000
NUM_BYTES_PER_READING = 4

POLLING_PERIOD_MS = 1000

MAX_READINGS = 30 # approximately corresponds to number of seconds back to display

# For reading from light sensor
ARDUINO_ADC_MAX_VOLTAGE = 5
ARDUINO_ADC_MAX_INT = 2 ** 10  # maximum changes depending on board, but defaults to 10 bits on every board

def read_values(adno: serial.Serial):
    m = None
    counter = 0
    while m == None:
        text_output = adno.readline()
        try:        # to anyone who has to maintain this code later: sorry (:
            text_output = text_output.decode("ASCII")  # wait for arduinos to send a line of text over serial, then read it in
        except:
            split_string = b'Time: '
            try:
                text_output = split_string + text_output.split(split_string, 1)[1]
                text_output = text_output.decode("ASCII")
            except:
                text_output = ""
                counter += 1
                if counter >= 20:
                    raise Exception('Too many attempts')
        m = re.search(
            'Time: (?P<current_time>[\+,\-,\d,\.,nan]+), Humidity: (?P<humidity>[\+,\-,\d,\.,nan]+)%, Temp: (?P<temperature>[\+,\-,\d,\.,nan]+)C, Pressure: (?P<pressure>[\+,\-,\d,\.,nan]+)Pa, Altitude: (?P<altitude>[\+,\-,\d,\.,nan]+)m, Temp \(BMP\): (?P<temp2>[\+,\-,\d,\.,nan]+)C, Light: (?P<light>[\+,\-,\d,\.,nan]+)lx, \(Roll: (?P<roll>[\+,\-,\d,\.,nan]+), Pitch: (?P<pitch>[\+,\-,\d,\.,nan]+), Yaw: (?P<yaw>[\+,\-,\d,\.]+)\) deg',
            text_output)
    if m:
        (current_time, humidity, temperature, pressure, altitude, temp2, light, roll, pitch, yaw) = [float(g) for g in
                                                                                                     m.groups()]
    else:
        current_time = humidity = temperature = pressure = altitude = temp2 = light = roll = pitch = yaw = None
        # In future: check for errors when noting is found

    return current_time, humidity, temperature, pressure, altitude, temp2, light, roll, pitch, yaw


def convert_serial_to_pd_reading(bytes_in: bytes) -> tuple[float, float]:
    # return time in ms since board started as an int, and voltage on the pin in volts as a float

    time_since_previous = (
                int.from_bytes(bytes_in[0:2], byteorder='little') * 1e-4)  # Time is given in intervals of 1e-4 seconds
    voltage_on_pin = int.from_bytes(bytes_in[2:4], byteorder='little') * ARDUINO_ADC_MAX_VOLTAGE / ARDUINO_ADC_MAX_INT

    return time_since_previous, voltage_on_pin

class PlotWindowDynamicSingleVariable(QMainWindow):
    def __init__(self, var_name: str, var_unit: str):
        super().__init__()

        self.var_name = var_name
        self.var_unit = var_unit

        # Initialize plot widget, set it to the center, and set the background color to be white
        self.plot_graph = pg.PlotWidget()
        self.setCentralWidget(self.plot_graph)
        self.plot_graph.setBackground("w")

        # set the color and width of the plot line
        pen = pg.mkPen(color=(255, 0, 0), width=5)  # (r, g, b), i.e., (0, 0, 255) = blue, so first plot is set to red

        # set the title name, color, and size of the plot
        self.plot_graph.setTitle(f"{self.var_name} vs Time", color='r', size='20pt')
        # styles = {"color": "red", "font-size": "18px"}

        # Axis Titles
        self.plot_graph.setLabel("left", f"{self.var_name} ({self.var_unit})", color="red")
        self.plot_graph.setLabel("bottom", "Time (sec)", color="red")

        # Legend and Gridlines
        self.plot_graph.addLegend()
        self.plot_graph.showGrid(x=True, y=True)

        # Arrays to store/update data readings from the two temperature sensors
        self.time = []
        self.value = []

        # this instruction will plot data from the 1st temperature sensor
        self.line = self.plot_graph.plot(
            self.time,
            self.value,
            name=f"{self.var_name}",  # Label for the legend
            pen=pen,
            symbol='o',
            symbolSize=5,
            symbolBrush='r'
        )

    def update_plot(self, sensor_time, value):
        self.time.append(sensor_time)
        self.value.append(value)

        lengtht = len(self.time)
        if lengtht > MAX_READINGS:
            self.time = self.time[(lengtht-MAX_READINGS):]
            self.value = self.value[(lengtht-MAX_READINGS):]
        
        # Update plot with new data
        self.line.setData(self.time, self.value)  # update plot for temperature 1


class PlotWindowDynamicTemp(QMainWindow):
    def __init__(self):
        super().__init__()
        # Initialize plot widget, set it to the center, and set the background color to be white
        self.plot_graph = pg.PlotWidget()
        self.setCentralWidget(self.plot_graph)
        self.plot_graph.setBackground("w")

        # set the color and width of the plot line
        pen = pg.mkPen(color=(255, 0, 0), width=5)  # (r, g, b), i.e., (0, 0, 255) = blue, so first plot is set to red

        # set the title name, color, and size of the plot
        self.plot_graph.setTitle("Temperature vs Time", color='r', size='20pt')
        # styles = {"color": "red", "font-size": "18px"}

        # Axis Titles
        self.plot_graph.setLabel("left", "Temperature (ºC)", color="red")
        self.plot_graph.setLabel("bottom", "Time (sec)", color="red")

        # Legend and Gridlines
        self.plot_graph.addLegend()
        self.plot_graph.showGrid(x=True, y=True)

        # Arrays to store/update data readings from the two temperature sensors
        self.time = []
        self.temperature1 = []
        self.temperature2 = []

        # this instruction will plot data from the 1st temperature sensor
        self.line1 = self.plot_graph.plot(
            self.time,
            self.temperature2,
            name="Temperature Sensor",  # Label for the legend
            pen=pen,
            symbol='o',
            symbolSize=5,
            symbolBrush='r'
        )
        pen = pg.mkPen(color=(0, 0, 255), width=5)  # (r, g, b) – set the second plot to blue

        # this will plot the second
        self.line2 = self.plot_graph.plot(
            self.time,
            self.temperature2,
            name="Temperature Sensor (BMP)",  # Label for the legend
            pen=pen,
            symbol='o',
            symbolSize=5,
            symbolBrush='r'
        )

    def update_plot_temperatures(self, sensor_time, temp1, temp2):
        self.time.append(sensor_time)
        self.temperature1.append(temp1)
        self.temperature2.append(temp2)  # 2nd temperature value)

        lengtht = len(self.time)
        if lengtht > MAX_READINGS:
            self.time = self.time[(lengtht-MAX_READINGS):]
            self.temperature1 = self.temperature1[(lengtht-MAX_READINGS):]
            self.temperature2 = self.temperature2[(lengtht-MAX_READINGS):]
        
        # Update plot with new data
        self.line1.setData(self.time, self.temperature1)  # update plot for temperature 1
        self.line2.setData(self.time, self.temperature2)  # update plot for temperature 2

class PlotWindowDynamicRollPitchYaw(QMainWindow):
    def __init__(self):
        super().__init__()
        # Initialize plot widget, set it to the center, and set the background color to be white
        self.plot_graph = pg.PlotWidget()
        self.setCentralWidget(self.plot_graph)
        self.plot_graph.setBackground("w")

        # set the title name, color, and size of the plot
        self.plot_graph.setTitle("Rotation vs Time", color='r', size='20pt')
        # styles = {"color": "red", "font-size": "18px"}

        # Axis Titles
        self.plot_graph.setLabel("left", "Rotation (º)", color="red")
        self.plot_graph.setLabel("bottom", "Time (sec)", color="red")

        # Legend and Gridlines
        self.plot_graph.addLegend()
        self.plot_graph.showGrid(x=True, y=True)

        # Arrays to store/update data readings from the two temperature sensors
        self.time = []
        self.roll = []
        self.pitch = []
        self.yaw = []

        # set the color and width of the plot line
        pen = pg.mkPen(color=(255, 0, 0), width=5)  # (r, g, b) - set roll to red
        self.line_r = self.plot_graph.plot(
            self.time,
            self.roll,
            name="roll",  # Label for the legend
            pen=pen,
            symbol='o',
            symbolSize=5,
            symbolBrush='r'
        )

        pen = pg.mkPen(color=(0, 0, 255), width=5)  # (r, g, b) – set pitch to blue
        self.line_p = self.plot_graph.plot(
            self.time,
            self.pitch,
            name="pitch",  # Label for the legend
            pen=pen,
            symbol='o',
            symbolSize=5,
            symbolBrush='r'
        )

        pen = pg.mkPen(color=(0, 255, 0), width=5)  # (r, g, b) – set yaw to green
        self.line_y = self.plot_graph.plot(
            self.time,
            self.yaw,
            name="yaw",  # Label for the legend
            pen=pen,
            symbol='o',
            symbolSize=5,
            symbolBrush='r'
        )

    def update_plot(self, sensor_time, roll, pitch, yaw):
        self.time.append(sensor_time)
        self.roll.append(roll)
        self.pitch.append(pitch)
        self.yaw.append(yaw)

        lengtht = len(self.time)
        if lengtht > MAX_READINGS:
            self.time = self.time[(lengtht-MAX_READINGS):]
            self.roll = self.roll[(lengtht-MAX_READINGS):]
            self.pitch = self.pitch[(lengtht-MAX_READINGS):]
            self.yaw = self.yaw[(lengtht-MAX_READINGS):]
        
        # Update plot with new data
        self.line_r.setData(self.time, self.roll)
        self.line_p.setData(self.time, self.pitch)
        self.line_y.setData(self.time, self.yaw)


class PlotWindowOptical(QMainWindow):
    def __init__(self):
        super().__init__()
        # initialize graph, center it, and set background colour
        self.plot_graph = pg.PlotWidget()
        self.setCentralWidget(self.plot_graph)
        self.plot_graph.setBackground("w")
        # set colour and thickness of plot line
        pen = pg.mkPen(color=(255, 255, 0), width=5)  # (r, g, b), i.e., (0, 255, 0) = green
        # set graph title, and axis titles
        self.plot_graph.setTitle("Voltage from photodiode vs Time", color='k', size='20pt')
        self.plot_graph.setLabel('left', 'Voltage (V)', color='black')
        self.plot_graph.setLabel('bottom', 'Time (s)', color='black')

        # Legend and Gridlines
        self.plot_graph.addLegend()
        self.plot_graph.showGrid(x=True, y=True)

        self.time = np.empty(0,'f')
        self.voltage = np.empty(0,'f')

        self.line = self.plot_graph.plot(
            self.time,
            self.voltage,
            name="Optical Power Reading",  # Label for the legend
            pen=pen,
            symbol='o',
            symbolSize=5,
            symbolBrush='b'
        )

    def update_plot_optical(self, times_in, voltages_in):
        # Update plot data for temperature
        # self.time.append(self.time[-1] + 1) if self.time else self.time.append(0)
        self.time = np.append(self.time,times_in)
        self.voltage = np.append(self.voltage, voltages_in)

        lengtht = len(self.time)
        if lengtht > MAX_READINGS*NUM_PD_READINGS_PER_CYCLE:
            self.time = self.time[(lengtht-MAX_READINGS*NUM_PD_READINGS_PER_CYCLE):]
            self.voltage = self.voltage[(lengtht-MAX_READINGS*NUM_PD_READINGS_PER_CYCLE):]

        # Update plot with new data
        self.line.setData(self.time, self.voltage)

class MainWindow(QMainWindow):  #this main window should show all the buttons that can be pressed for the different plots
    # *rn there is only buttons for the Temperature and Photodiode plots
    arduino = serial.Serial(port=ARDUINO_SERIAL_PORT, baudrate=ARDUINO_BAUD_RATE, timeout=TIMEOUT)
    PD_overall_time = 0

    def __init__(self):
        super().__init__()

        self.temperature_window = PlotWindowDynamicTemp()
        self.optical_window = PlotWindowOptical()
        self.rollpitchyaw_window = PlotWindowDynamicRollPitchYaw()
        self.humidity_window = PlotWindowDynamicSingleVariable("humidity", "%")
        self.pressure_window = PlotWindowDynamicSingleVariable("pressure", "Pa")
        self.altitude_window = PlotWindowDynamicSingleVariable("altitude", "m")
        self.light_window = PlotWindowDynamicSingleVariable("light", "lx")

        self.setWindowTitle('Buttons')

        main_layout = QVBoxLayout()
        button_temp = QPushButton("Temperature vs. Time")
        button_temp.clicked.connect(lambda: self.toggle_window(self.temperature_window))
        main_layout.addWidget(button_temp)

        button_opt = QPushButton("Voltage vs. Time")
        button_opt.clicked.connect(lambda: self.toggle_window(self.optical_window))
        main_layout.addWidget(button_opt)

        button_rpy = QPushButton("Orientation vs time")
        button_rpy.clicked.connect(lambda: self.toggle_window(self.rollpitchyaw_window))
        main_layout.addWidget(button_rpy)

        button_humidity = QPushButton("Humidity vs. Time")
        button_humidity.clicked.connect(lambda: self.toggle_window(self.humidity_window))
        main_layout.addWidget(button_humidity)

        button_pressure = QPushButton("Pressure vs. Time")
        button_pressure.clicked.connect(lambda: self.toggle_window(self.pressure_window))
        main_layout.addWidget(button_pressure)

        button_altitude = QPushButton("Altitude vs. Time")
        button_altitude.clicked.connect(lambda: self.toggle_window(self.altitude_window))
        main_layout.addWidget(button_altitude)

        button_light = QPushButton("Light vs. Time")
        button_light.clicked.connect(lambda: self.toggle_window(self.light_window))
        main_layout.addWidget(button_light)

        w = QWidget()
        w.setLayout(main_layout)
        self.setCentralWidget(w)

        # future = QtConcurrent.run(self.read_and_update_plots, self.arduino, self.PD_overall_time)
        # future = QtConcurrent.run(self.plots_loop)
        self.timer = QtCore.QTimer()
        self.timer.setInterval(POLLING_PERIOD_MS)
        self.timer.timeout.connect(self.read_and_update_plots)  # once the timer times out, call the 'update_plot' function
        self.timer.start()

    def toggle_window(self, window_to_check):
        if window_to_check.isVisible():
            window_to_check.hide()
        else:
            window_to_check.show()

    # def plots_loop(self):
    #     with serial.Serial(port=ARDUINO_SERIAL_PORT, baudrate=ARDUINO_BAUD_RATE, timeout=TIMEOUT) as arduino:
    #         PD_time = 0
    #         self.read_and_update_plots(arduino, PD_time)

    def read_and_update_plots(self):
        arduino = self.arduino
        
        sensor_time, humidity, temperature, pressure, altitude, temp2, light, roll, pitch, yaw = read_values(arduino)
        sensor_time = sensor_time * 1e-3  # convert from miliseconds to seconds

        pd_times = np.empty(NUM_PD_READINGS_PER_CYCLE, 'f')
        pd_voltages = np.empty(NUM_PD_READINGS_PER_CYCLE, 'f')
        arduino.reset_input_buffer()
        arduino.reset_output_buffer()
        for c in range(NUM_PD_READINGS_PER_CYCLE):
            pd_delta_time, pd_voltages[c] = convert_serial_to_pd_reading(arduino.read(NUM_BYTES_PER_READING))
            pd_times[c] = self.PD_overall_time = pd_delta_time + self.PD_overall_time

        print(f"Average PD time: {np.average(pd_times)}; average PD value: {np.average(pd_voltages)}")
        print(
            f"Time: {sensor_time}, Humidity: {humidity}%, Temp:{temperature}C, Pressure: {pressure}Pa,  Altitude: {altitude}m,  Temp (BMP) = {temp2}C, Light: {light}lx, (Roll: {roll}, Pitch: {pitch}, Yaw: {yaw}) deg")

        self.optical_window.update_plot_optical(pd_times, pd_voltages)
        self.temperature_window.update_plot_temperatures(sensor_time, temperature, temp2)
        self.rollpitchyaw_window.update_plot(sensor_time, roll, pitch, yaw)
        self.humidity_window.update_plot(sensor_time, humidity)
        self.pressure_window.update_plot(sensor_time, pressure)
        self.altitude_window.update_plot(sensor_time, altitude)
        self.light_window.update_plot(sensor_time, light)

# beginning of program
app = QApplication(sys.argv)
window = MainWindow()
window.show()
app.exec()

# static variables (https://stackoverflow.com/a/279597)
# def myfunc():
#   if not hasattr(myfunc, "counter"):
#      myfunc.counter = 0  # it doesn't exist yet, so initialize it
#   myfunc.counter += 1
