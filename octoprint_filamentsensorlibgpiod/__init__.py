# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import re
from octoprint.events import Events
from time import sleep
import flask
import threading
import time

class Filament_sensor_libgpiod(octoprint.plugin.StartupPlugin,
									   octoprint.plugin.EventHandlerPlugin,
									   octoprint.plugin.TemplatePlugin,
									   octoprint.plugin.SettingsPlugin,
									   octoprint.plugin.SimpleApiPlugin,
									   octoprint.plugin.BlueprintPlugin,
									   octoprint.plugin.AssetPlugin):
	# bounce time for sensing
	bounce_time = 250

	# pin number used as plugin disabled
	pin_num_disabled = 0

	# default gcode
	default_gcode = 'M600 X0 Y0'

	# printing flag
	printing = False

	# detection active
	detectionOn = False

	def initialize(self):
		
		# flag telling that we are expecting M603 response
		self.checking_M600 = False
		# flag defining if printer supports M600
		self.M600_supported = True
		# flag defining that the filament change command has been sent to printer, this does not however mean that
		# filament change sequence has been started
		self.changing_filament_initiated = False
		# flag defining that the filament change sequence has been started and the M600 command has been se to printer
		self.changing_filament_command_sent = False
		# flag defining that the filament change sequence has been started and the printer is waiting for user
		# to put in new filament
		self.paused_for_user = False
		# flag for determining if the gcode starts with M600
		self.M600_gcode = True
		# flag to prevent double detection
		self.changing_filament_started = False
		# stop the gpio polling thread
		self.stop_thread = False

	@property
	def gpio_number(self):
		return int(self._settings.get(["gpio_number"]))

	@property
	def gpio_offset(self):
		return int(self._settings.get(["gpio_offset"]))

	@property
	def g_code(self):
		return self._settings.get(["g_code"])

	@property
	def triggered(self):
		return int(self._settings.get(["triggered"]))

	# AssetPlugin hook
	def get_assets(self):
		return dict(js=["js/filamentsensorlibgpiod.js"], css=["css/filamentsensorlibgpiod.css"])

	# Template hooks
	def get_template_configs(self):
		return [dict(type="settings", custom_bindings=True)]

	# Settings hook
	def get_settings_defaults(self):
		return dict(
			gpio_number=-1,
			gpio_offset=-1,			
			g_code=self.default_gcode,
			triggered=0
		)

	# simpleApiPlugin
	def get_api_commands(self):
		return dict(testSensor=["gpio_number", "gpio_offset"])

	@octoprint.plugin.BlueprintPlugin.route("/disable", methods=["GET"])
	def get_disable(self):
		self._logger.debug("getting disabled info")
		if self.printing:
			self._logger.debug("printing")
			gpio_mode_disabled = True
		else:
			self._logger.debug("not printing")
			gpio_mode_disabled = self.gpio_mode_disabled

		return flask.jsonify(gpio_mode_disabled=gpio_mode_disabled, printing=self.printing)

	# test pin value, power pin or if its used by someone else
	def on_api_command(self, command, data):
		try:
			triggered_bool = self.sen.get_value() 
			self._logger.debug("triggered value %s" % triggered_bool)
			return flask.jsonify(triggered=triggered_bool)
		except ValueError as e:
			self._logger.error(str(e))
			# ValueError occurs when reading from power, ground or out of range pins
			return "", 556

	def on_after_startup(self):
		self._logger.info("Filament Sensor Simplified started")
		gpio_number = self.gpio_number

		# Fix old -1 settings to 0
		if self.gpio_offset is -1:
			self._logger.info("Fixing old settings from -1 to 0")
			self._settings.set(["gpio_offset"], 0)
			self.gpio_offset = 0
		if gpio_number is not None:
			self._settings.set(["gpio_number"], gpio_number)
			self.gpio_mode_disabled = True


	def on_settings_save(self, data):
		# Retrieve any settings not changed in order to validate that the combination of new and old settings end up in a bad combination
		offset_to_save = self._settings.get_int(["gpio_offset"])
		number_to_save = self._settings.get_int(["gpio_number"])

		if "gpio_offset" in data:
			offset_to_save = int(data.get("gpio_offset"))

		if "gpio_number" in data:
			number_to_save = int(data.get("gpio_number"))


		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)

	def checkM600Enabled(self):
		sleep(1)
		self.checking_M600 = True
		self._printer.commands("M603")

	# this method is called before the gcode is sent to printer
	def sending_gcode(self, comm_instance, phase, cmd, cmd_type, gcode, subcode=None, tags=None, *args, **kwargs):
		if self.changing_filament_initiated and self.M600_supported:
			if self.changing_filament_command_sent and self.changing_filament_started:
				# M113 - host keepalive message, ignore this message
				if not re.search("^M113", cmd):
					self.changing_filament_initiated = False
					self.changing_filament_command_sent = False
					self.changing_filament_started = False
					if self.no_filament():
						self.send_out_of_filament()
			if cmd == self.g_code:
				self.changing_filament_command_sent = True

		# deliberate change
		if self.M600_supported and re.search("^M600", cmd):
			self.changing_filament_initiated = True
			self.changing_filament_command_sent = True

	# this method is called on gcode response
	def gcode_response_received(self, comm, line, *args, **kwargs):
		if self.changing_filament_command_sent:
			if re.search("busy: paused for user", line):
				self._logger.debug("received busy paused for user")
				if not self.paused_for_user:
					self._plugin_manager.send_plugin_message(self._identifier, dict(type="info", autoClose=False,
																					msg="Filament change: printer is waiting for user input."))
					self.paused_for_user = True
					self.changing_filament_started = True
			elif re.search("echo:busy: processing", line):
				self._logger.debug("received busy processing")
				if self.paused_for_user:
					self.paused_for_user = False

		# waiting for M603 command response
		if self.checking_M600:
			if re.search("^ok", line):
				self._logger.debug("Printer supports M600")
				self.M600_supported = True
				self.checking_M600 = False
			elif re.search("^echo:Unknown command: \"M603\"", line):
				self._logger.debug("Printer doesn't support M600")
				self.M600_supported = False
				self.checking_M600 = False
				self._plugin_manager.send_plugin_message(self._identifier, dict(type="info", autoClose=True,
																				msg="M600 gcode command is not enabled on this printer! This plugin won't work."))
			else:
				self._logger.debug("M600 check unsuccessful, trying again")
				self.checkM600Enabled()
		return line

	# plugin disabled if pin set to -1
	def sensor_enabled(self):
		return self.pin != self.pin_num_disabled

	# read sensor input value
	def no_filament(self):
		return self.sen.get_value() == 1

	# method invoked on event
	def on_event(self, event, payload):
		# octoprint connects to 3D printer
		if event is Events.CONNECTED:
			# if the command starts with M600, check if printer supports M600
			if re.search("^M600", self.g_code):
				self.M600_gcode = True
				self.checkM600Enabled()

		# octoprint disconnects from 3D printer, reset M600 enabled variable
		elif event is Events.DISCONNECTED:
			self.M600_supported = True

		# if user has logged in show appropriate popup
		elif event is Events.CLIENT_OPENED:
			if self.changing_filament_initiated and not self.changing_filament_command_sent:
				self.show_printer_runout_popup()
			elif self.changing_filament_command_sent and not self.paused_for_user:
				self.show_printer_runout_popup()
			# printer is waiting for user to put in new filament
			elif self.changing_filament_command_sent and self.paused_for_user:
				self._plugin_manager.send_plugin_message(self._identifier, dict(type="info", autoClose=False,
																				msg="Printer ran out of filament! It's waiting for user input"))
			# if the plugin hasn't been initialized
			if not self.sensor_enabled():
				self._plugin_manager.send_plugin_message(self._identifier, dict(type="info", autoClose=True,
																				msg="Don't forget to configure this plugin."))

		if not (self.M600_gcode and not self.M600_supported):
			# Enable sensor
			if event in (
					Events.PRINT_STARTED,
					Events.PRINT_RESUMED
			):
				self._logger.info("%s: Enabling filament sensor." % (event))
				if self.sensor_enabled():

					# 0 = sensor is grounded, react to rising edge pulled up by pull up resistor
					self.turnOffDetection(event)
					self.detectionOn = True
					gpio_thread = threading.Thread(target = run_gpio_polling, args = (lambda : self.stop_thread, ))
					gpio_thread.start()
					
					# print started with no filament present
					if self.no_filament():
						self._logger.info("Printing aborted: no filament detected!")
						self._printer.cancel_print()
						self._plugin_manager.send_plugin_message(self._identifier,
																 dict(type="error", autoClose=True,
																	  msg="No filament detected! Print cancelled."))
					# print started
					else:
						self.printing = True

				# print started without plugin configuration
				else:
					self._plugin_manager.send_plugin_message(self._identifier,
															 dict(type="info", autoClose=True,
																  msg="You may have forgotten to configure this plugin."))

			# Disable sensor
			elif event in (
					Events.PRINT_DONE,
					Events.PRINT_FAILED,
					Events.PRINT_CANCELLED,
					Events.ERROR
			):
				self.turnOffDetection(event)
				self.changing_filament_initiated = False
				self.changing_filament_command_sent = False
				self.paused_for_user = False
				self.printing = False

	def stop_thread(self):
		return self.detectionOn != True


	# turn off detection if on
	def turnOffDetection(self,event):
		if self.detectionOn:
			self._logger.info("%s: Disabling filament sensor." % (event))
			self.detectionOn = False			

	def sensor_callback(self, _):
		trigger = True
		for x in range(0, 5):
			sleep(0.05)
			if not self.no_filament():
				trigger = False

		if trigger:
			self._logger.info("Sensor was triggered")
			if not self.changing_filament_initiated:
				self.send_out_of_filament()

	def send_out_of_filament(self):
		self.show_printer_runout_popup()
		self._logger.info("Sending out of filament GCODE: %s" % (self.g_code))
		self._printer.commands(self.g_code)
		self.changing_filament_initiated = True

	def show_printer_runout_popup(self):
		self._plugin_manager.send_plugin_message(self._identifier,
												 dict(type="info", autoClose=False, msg="Printer ran out of filament!"))

	def get_update_information(self):
		# Define the configuration for your plugin to use with the Software Update
		# Plugin here. See https://docs.octoprint.org/en/master/bundledplugins/softwareupdate.html
		# for details.
		return dict(
			filamentsensorsimplified=dict(
				displayName="Filament sensor libgpiod",
				displayVersion=self._plugin_version,

				# version check: github repository
				type="github_release",
				user="ngochai",
				repo="Filament_sensor_libgpiod",
				current=self._plugin_version,

				# update method: pip
				pip="https://github.com/ngochai/Filament_sensor_libgpiod/archive/{target_version}.zip"
			)
		)
	
	def run_gpio_polling(self, stopfunc):
		lastval = self.sen.get_value()
		while True:
			if stopfunc():
				break
			newval = self.sen.get_value()
			if newval != lastval:
				self._plugin_manager.send_plugin_message(self._identifier, dict(type="info", autoClose=False, msg="Filament sensor value changed: " + newval))
				self.sensor_callback()
				lastval = newval
			time.sleep(0.1)	


# Starting with OctoPrint 1.4.0 OctoPrint will also support to run under Python 3 in addition to the deprecated
# Python 2. New plugins should make sure to run under both versions for now. Uncomment one of the following
# compatibility flags according to what Python versions your plugin supports!
# __plugin_pythoncompat__ = ">=2.7,<3" # only python 2
# __plugin_pythoncompat__ = ">=3,<4" # only python 3
__plugin_pythoncompat__ = ">=2.7,<4"  # python 2 and 3

__plugin_name__ = "Filament Sensor libgpiod"
__plugin_version__ = "0.1.0"


def __plugin_check__():
	try:
		import gpiod		
	except ImportError:
		return False
	return True


def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = Filament_sensor_libgpiod()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
		"octoprint.comm.protocol.gcode.received": __plugin_implementation__.gcode_response_received,
		"octoprint.comm.protocol.gcode.sending": __plugin_implementation__.sending_gcode
	}
