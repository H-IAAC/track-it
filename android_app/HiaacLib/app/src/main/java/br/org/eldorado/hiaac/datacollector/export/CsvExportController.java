package br.org.eldorado.hiaac.datacollector.export;

import android.app.Application;
import android.content.Context;
import androidx.lifecycle.ViewModelProvider;

import java.io.File;
import java.util.List;

import br.org.eldorado.hiaac.R;
import br.org.eldorado.hiaac.datacollector.controller.ExecutionController;
import br.org.eldorado.hiaac.datacollector.data.LabelConfigRepository;
import br.org.eldorado.hiaac.datacollector.data.LabelConfigViewModel;
import br.org.eldorado.hiaac.datacollector.data.LabeledData;
import br.org.eldorado.hiaac.datacollector.util.CsvBuilder;
import br.org.eldorado.hiaac.datacollector.util.Log;

public class CsvExportController {
    private final Log log  = new Log("CsvExportController");
    private static final int SUCCESS = 0;
    private static final int ERROR = 1;
    private static final int ON_PROGRESS = 2;
    private final CsvBuilder csvBuilder;
    private final Context mContext;
    private CsvExportListener listener;
    private final LabelConfigViewModel dbView;

    public CsvExportController(Context ctx) {
        mContext = ctx;
        dbView = ViewModelProvider.AndroidViewModelFactory.getInstance(
                (Application) ctx.getApplicationContext()).create(LabelConfigViewModel.class);
        csvBuilder = new CsvBuilder(dbView, ctx);
    }

    public void registerListener(CsvExportListener l) {
        this.listener = l;
    }

    public void exportToCSV(final String uid, long labelId) {

        new Thread(new Runnable() {
            @Override
            public void run() {
                long start = System.currentTimeMillis();
                String innerUid = uid;

                // Wait (10 secs) for the execution stops before collect from db
                int waitSecs = 0;
                while (ExecutionController.getInstance().isRunning() && waitSecs < 10) {
                    try {
                        Thread.sleep(1000);
                        waitSecs++;
                    } catch (InterruptedException e) {
                        e.printStackTrace();
                    }
                }

                if (!dbView.labeledDataExists(labelId)) {
                    log.d("exportToCSV - There is no data to export!");
                    fireListener(ERROR, mContext.getString(R.string.error_no_data_create_csc));
                    return;
                }
                log.d("exportToCSV - Starting creating csv file labelId: " + labelId + " uid: " + uid);

                if (ExecutionController.getInstance().isRunning()) {
                    log.d("exportToCSV - exporting data while execution controller still running");
                }

                if (uid == null || "0".equals(uid) || "null".equals(uid)) {
                    innerUid = dbView.getLabeledDataUidCsv(labelId);
                    log.d("exportToCSV - uid was wrong! New uid = " + innerUid);
                }

                fireListener(ON_PROGRESS, mContext.getString(R.string.creating_csv_file));

                File csvFile = csvBuilder.getCsvFile(dbView.getLabeledData(labelId),
                                                     innerUid,
                                                     true);

                List<LabeledData> labeledData;
                while ((labeledData = dbView.getLabeledData(labelId, LabelConfigRepository.TYPE_CSV, 0)).size() > 0) {
                    csvBuilder.appendData(csvFile, labeledData, false);
                }

                long end = System.currentTimeMillis();
                log.d("exportToCSV - Csv file created. Time consumed: " + ((end-start)/1000)/60 + "m" + ((end-start)/1000)%60+"s");

                dbView.deleteLabeledData(labelId);

                fireListener(SUCCESS, mContext.getString(R.string.success_csv_file));
            }
        }).start();
    }

    private void fireListener(int type, String msg) {
        if (listener != null) {
            switch (type) {
                case SUCCESS:
                case ERROR:
                    listener.onCompleted(msg);
                    break;
                case ON_PROGRESS:
                    listener.onProgress(msg);
                    break;
                default:
                    log.d("Ignoring fireListener with invalid type.");
                    break;
            }
        }
    }
}
