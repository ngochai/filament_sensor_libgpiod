$(function () {
    function filamentsensorlibgpiodViewModel(parameters) {
        var self = this;

        self.validPinsBoard = [3,5,7,11,13,15,19,21,23,27,29,31,33,35,37,8,10,12,16,18,22,24,26,28,32,36,38,40];
        self.settingsViewModel = parameters[0];
        self.testSensorResult = ko.observable(null);
        self.gpio_mode_disabled = ko.observable(false);
        self.printing = ko.observable(false);
        self.gpio_mode_disabled_by_3rd = ko.computed(function() {
            return this.gpio_mode_disabled() && !this.printing();
        }, this);

        self.onDataUpdaterPluginMessage = function (plugin, data) {
            if (plugin !== "filamentsensorlibgpiod") {
                return;
            }

            new PNotify({
                title: 'Filament sensor libgpiod',
                text: data.msg,
                type: data.type,
                hide: data.autoClose
            });

        }

        self.testSensor = function () {
            // Cleanup
            $("#filamentsensorlibgpiod_settings_testResult").removeClass("text-warning text-error text-info text-success");
            // Make api callback
            $.ajax({
                    url: "/api/plugin/filamentsensorlibgpiod",
                    type: "post",
                    dataType: "json",
                    contentType: "application/json",
                    headers: {"X-Api-Key": UI_API_KEY},
                    data: JSON.stringify({
                        "command": "testSensor",
                        "pin": $("#filamentsensorlibgpiod_settings_pinInput").val(),
                        "power": $("#filamentsensorlibgpiod_settings_powerInput").val(),
                        "mode": $("#filamentsensorlibgpiod_settings_gpioMode").val(),
                        "triggered": $("#filamentsensorlibgpiod_settings_triggeredInput").val()
                    }),
                    statusCode: {
                        500: function () {
                            $("#filamentsensorlibgpiod_settings_testResult").addClass("text-error");
                            self.testSensorResult('<i class="fas icon-warning-sign fa-exclamation-triangle"></i> OctoPrint experienced a problem. Check octoprint.log for further info.');
                        },
                        555: function () {
                            $("#filamentsensorlibgpiod_settings_testResult").addClass("text-error");
                            self.testSensorResult('<i class="fas icon-warning-sign fa-exclamation-triangle"></i> This pin is already in use, choose other pin.');
                        },
                        556: function () {
                            $("#filamentsensorlibgpiod_settings_testResult").addClass("text-error");
                            self.testSensorResult('<i class="fas icon-warning-sign fa-exclamation-triangle"></i> The pin selected is power, ground or out of range pin number, choose other pin');
                        }
                    },
                    error: function () {
                        $("#filamentsensorlibgpiod_settings_testResult").addClass("text-error");
                        self.testSensorResult('<i class="fas icon-warning-sign fa-exclamation-triangle"></i> There was an error :(');
                    },
                    success: function (result) {
                        // triggered when open
                        if ($("#filamentsensorlibgpiod_settings_triggeredInput").val() === "0") {
                            if (result.triggered === true) {
                                $("#filamentsensorlibgpiod_settings_testResult").addClass("text-success");
                                self.testSensorResult('<i class="fas icon-ok fa-check"></i> Sensor detected filament!');
                            } else {
                                $("#filamentsensorlibgpiod_settings_testResult").addClass("text-info");
                                self.testSensorResult('<i class="icon-stop"></i> Sensor triggered!')
                            }
                        // triggered when closed
                        } else {
                            if (result.triggered === true) {
                                $("#filamentsensorlibgpiod_settings_testResult").addClass("text-success");
                                self.testSensorResult('<i class="fas icon-ok fa-check"></i> Sensor triggered!');
                            } else {
                                $("#filamentsensorlibgpiod_settings_testResult").addClass("text-info");
                                self.testSensorResult('<i class="icon-stop"></i> Sensor detected filament or not working!')
                            }
                        }
                    }
                }
            );
        }
        self.checkWarningPullUp = function(event){
            // Which mode are we using
            var gpioNumber = parseInt($('#filamentsensorlibgpiod_settings_gpioNumber').val(),10);
            // What pin is the sensor connected to
            var gpioOffset = parseInt($('#filamentsensorlibgpiod_settings_gpioOffset').val(),10);
            /*
            // What is the sensor connected to - ground or 3.3v
            var sensorCon = parseInt($('#filamentsensorlibgpiod_settings_powerInput').val(),10);

            // Show alerts
            if (
                sensorCon == 1 && (
                    (mode == 10 && (pin==3 || pin == 5))
                    ||
                    (mode == 11 && (pin == 2 || pin == 3))
                )
            ){
                $('#filamentsensorlibgpiod_settings_pullupwarn').removeClass('hidden pulsAlert').addClass('pulsAlert');
            }else{
                $('#filamentsensorlibgpiod_settings_pullupwarn').addClass('hidden').removeClass('pulsAlert');
            }
            */
        }

        self.getDisabled = function (item) {
            $.ajax({
                type: "GET",
                dataType: "json",
                url: "plugin/filamentsensorlibgpiod/disable",
                success: function (result) {
                    self.gpio_mode_disabled(result.gpio_mode_disabled)
                    self.printing(result.printing)
                }
            });
        };

        self.onSettingsShown = function () {
            self.testSensorResult("");
            self.getDisabled();
             // Check for broken settings
            //$('#filamentsensorlibgpiod_settings_gpioNumber, #filamentsensorlibgpiod_settings_gpioOffset, #filamentsensorlibgpiod_settings_powerInput').off('change.fsensor').on('change.fsensor',self.checkWarningPullUp);
            //$('#filamentsensorlibgpiod_settings_gpioNumber').trigger('change.fsensor');
        }
    }

    // This is how our plugin registers itself with the application, by adding some configuration
    // information to the global variable OCTOPRINT_VIEWMODELS
    ADDITIONAL_VIEWMODELS.push({
        construct: filamentsensorlibgpiodViewModel,
        dependencies: ["settingsViewModel"],
        elements: ["#settings_plugin_filamentsensorlibgpiod"]
    })
})
