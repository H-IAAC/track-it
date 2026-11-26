package br.org.eldorado.hiaac.datacollector.util;

import br.org.eldorado.sensoragent.model.LinearAccelerometer;
import br.org.eldorado.sensoragent.model.Luminosity;
import br.org.eldorado.sensoragent.model.MagneticField;

/**
 * UI-only sensor display labels, aligned with the sensor taxonomy figure.
 *
 * These change ONLY what the user sees in the sensor list. The collected data is
 * untouched and already validated: the raw CSV "Sensor Name" (from getName()), the
 * postprocessor file names, and the DB key (class simple name) keep the internal
 * names ("MagneticField", "LinearAccelerometer", "Luminosity"). Changing a label
 * here never changes what is collected.
 */
public final class SensorLabels {

    public static final String MAGNETOMETER = "Magnetometer";
    public static final String LINEAR_ACCELERATION = "Linear Acceleration";
    public static final String AMBIENT_LIGHT = "Ambient Light";

    private SensorLabels() {
    }

    /** Returns the label to show in the UI for a given internal sensor name. */
    public static String displayLabel(String sensorName) {
        if (MagneticField.TAG.equals(sensorName)) {
            return MAGNETOMETER;                 // the device, not the quantity
        }
        if (LinearAccelerometer.TAG.equals(sensorName)) {
            return LINEAR_ACCELERATION;          // the measured quantity (virtual sensor)
        }
        if (Luminosity.TAG.equals(sensorName)) {
            return AMBIENT_LIGHT;
        }
        return sensorName;
    }
}
