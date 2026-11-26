package br.org.eldorado.hiaac.datacollector.util;

import android.content.Context;

import androidx.appcompat.app.AppCompatDelegate;
import androidx.preference.PreferenceManager;

import br.org.eldorado.hiaac.R;

public final class ThemeMode {
    private ThemeMode() {}

    public static void apply(Context ctx) {
        String mode = PreferenceManager.getDefaultSharedPreferences(ctx.getApplicationContext())
                .getString(ctx.getString(R.string.settings_theme_key), "light");
        apply(mode);
    }

    public static void apply(String mode) {
        int night;
        if ("dark".equals(mode)) {
            night = AppCompatDelegate.MODE_NIGHT_YES;
        } else if ("system".equals(mode)) {
            night = AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM;
        } else {
            night = AppCompatDelegate.MODE_NIGHT_NO;
        }
        if (AppCompatDelegate.getDefaultNightMode() != night) {
            AppCompatDelegate.setDefaultNightMode(night);
        }
    }
}
