package br.org.eldorado.hiaac.datacollector.export;

public interface CsvExportListener {

    public void onProgress(String message);
    public void onCompleted(String message);
}
