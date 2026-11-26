package br.org.eldorado.hiaac.datacollector.model;

import com.google.gson.annotations.SerializedName;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class SessionManifest {
    @SerializedName("session_id")
    public String sessionId;

    @SerializedName("metadata")
    public Metadata metadata;

    @SerializedName("artifacts")
    public Artifacts artifacts;

    @SerializedName("pipeline_status")
    public PipelineStatus pipelineStatus;

    public SessionManifest() {
        this.sessionId = UUID.randomUUID().toString();
        this.metadata = new Metadata();
        this.artifacts = new Artifacts();
        this.pipelineStatus = new PipelineStatus();
    }

    public static class Metadata {
        @SerializedName("experiment")
        public String experiment;

        @SerializedName("subject")
        public String subject;

        @SerializedName("initial_activity")
        public String initialActivity;

        @SerializedName("timestamp_start")
        public long timestampStart;
    }

    public static class Artifacts {
        @SerializedName("raw_video")
        public String rawVideo = null;

        @SerializedName("raw_sensors")
        public List<String> rawSensors = new ArrayList<>();

        @SerializedName("clean_sensors")
        public String cleanSensors = null;

        @SerializedName("anonymized_video")
        public String anonymizedVideo = null;

        @SerializedName("annotation_file")
        public String annotationFile = null;
    }

    public static class PipelineStatus {
        @SerializedName("server_processed")
        public boolean serverProcessed = false;

        @SerializedName("face_masked")
        public boolean faceMasked = false;

        @SerializedName("annotated")
        public boolean annotated = false;
    }
}
