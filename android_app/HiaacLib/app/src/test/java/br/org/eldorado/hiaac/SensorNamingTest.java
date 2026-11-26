package br.org.eldorado.hiaac;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

import br.org.eldorado.hiaac.datacollector.util.SensorLabels;
import br.org.eldorado.sensoragent.model.LinearAccelerometer;
import br.org.eldorado.sensoragent.model.Luminosity;
import br.org.eldorado.sensoragent.model.MagneticField;

/**
 * Guards the sensor-naming contract: the UI shows the figure-aligned labels while
 * the collected data keeps the already-validated internal names. This makes sure a
 * label change never silently changes what is stored/collected, and that nobody
 * reverts the labels without noticing.
 */
public class SensorNamingTest {

    @Test
    public void collectedNamesAreUnchanged() {
        // Raw CSV "Sensor Name" (getName()) and postprocessor file names come from
        // these TAGs. They must NOT change.
        assertEquals("MagneticField", MagneticField.TAG);
        assertEquals("LinearAccelerometer", LinearAccelerometer.TAG);
        assertEquals("Luminosity", Luminosity.TAG);
    }

    @Test
    public void uiLabelsMatchTheFigure() {
        assertEquals("Magnetometer", SensorLabels.displayLabel(MagneticField.TAG));
        assertEquals("Linear Acceleration", SensorLabels.displayLabel(LinearAccelerometer.TAG));
        assertEquals("Ambient Light", SensorLabels.displayLabel(Luminosity.TAG));
    }

    @Test
    public void sensorsWithoutAnAliasAreNotRelabeled() {
        assertEquals("Accelerometer", SensorLabels.displayLabel("Accelerometer"));
        assertEquals("Gyroscope", SensorLabels.displayLabel("Gyroscope"));
        assertEquals("Gravity", SensorLabels.displayLabel("Gravity"));
    }
}
