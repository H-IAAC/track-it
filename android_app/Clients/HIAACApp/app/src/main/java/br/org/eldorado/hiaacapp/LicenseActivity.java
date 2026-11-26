package br.org.eldorado.hiaacapp;

import br.org.eldorado.hiaac.datacollector.util.ThemeMode;

import androidx.appcompat.app.AppCompatActivity;
import androidx.appcompat.app.AppCompatDelegate;
import androidx.core.text.HtmlCompat;

import android.os.Bundle;

import br.org.eldorado.hiaacapp.databinding.ActivityLicenseBinding;

public class LicenseActivity extends AppCompatActivity {

    private ActivityLicenseBinding binding;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        ThemeMode.apply(this);
        super.onCreate(savedInstanceState);

        if (getSupportActionBar() != null) {
            getSupportActionBar().setDisplayHomeAsUpEnabled(true);
            getSupportActionBar().setTitle("Open source licenses");
        }

        binding = ActivityLicenseBinding.inflate(getLayoutInflater());
        setContentView(binding.getRoot());

        binding.licenses.setText(HtmlCompat.fromHtml(
                "<h2>Track-It App</h2>"
                        + "<p><b>Version:</b> 2.0 (Track-It)</p>"
                        + "<p><b>Copyright &copy; 2026 H.IAAC Hub &mdash; Universidade Estadual de Campinas (Unicamp)</b><br>"
                        + "Released under the <b>MIT License</b>.</p>"
                        + "<h3>Project Credits &amp; Origin</h3>"
                        + "<p>Based on the open-source <i>sensor-toolkit</i> (v3.0.1) developed by <b>H.IAAC</b> and "
                        + "<b>Instituto de Pesquisas Eldorado</b> (Felipe Augusto, Saulo A. Moraes, Daniel Adam Miranda, and contributors). "
                        + "Extended and maintained at Unicamp for multimodal data collection, video synchronization, face anonymization, "
                        + "and HAR sensor labeling workflows.</p>"
                        + "<h3>Third-Party Open Source Libraries</h3>"
                        + "<p><b>AndroidX &amp; Jetpack</b><br>"
                        + "AppCompat, CameraX, ConstraintLayout, Navigation, Preference, Room, Core<br>"
                        + "<i>License: Apache License 2.0</i></p>"
                        + "<p><b>Material Components for Android</b><br>"
                        + "Google LLC &mdash; <i>Apache License 2.0</i></p>"
                        + "<p><b>Google Play Services</b><br>"
                        + "Location and Sensor APIs &mdash; <i>Android Software Development Kit License</i></p>"
                        + "<p><b>Gson</b><br>"
                        + "Google LLC &mdash; <i>Apache License 2.0</i></p>"
                        + "<p><b>OkHttp &amp; Retrofit</b><br>"
                        + "Square, Inc. &mdash; <i>Apache License 2.0</i></p>"
                        + "<p><b>OpenCSV</b><br>"
                        + "Glen Smith &amp; Bytecode Pty Ltd &mdash; <i>Apache License 2.0</i></p>"
                        + "<p><b>RxJava &amp; RxAndroid</b><br>"
                        + "ReactiveX Contributors &mdash; <i>Apache License 2.0</i></p>"
                        + "<p><b>JetBrains Mono Font</b><br>"
                        + "JetBrains s.r.o. &mdash; <i>SIL Open Font License 1.1</i></p>"
                        + "<h3>The MIT License (MIT)</h3>"
                        + "<p>Permission is hereby granted, free of charge, to any person obtaining a copy "
                        + "of this software and associated documentation files (the &quot;Software&quot;), to deal "
                        + "in the Software without restriction, including without limitation the rights "
                        + "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell "
                        + "copies of the Software, and to permit persons to whom the Software is "
                        + "furnished to do so, subject to the following conditions:</p>"
                        + "<p>The above copyright notice and this permission notice shall be included in all "
                        + "copies or substantial portions of the Software.</p>"
                        + "<p>THE SOFTWARE IS PROVIDED &quot;AS IS&quot;, WITHOUT WARRANTY OF ANY KIND, "
                        + "EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF "
                        + "MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.</p>",
                HtmlCompat.FROM_HTML_MODE_LEGACY));

    }

    @Override
    public boolean onSupportNavigateUp() {
        finish();
        return true;
    }
}