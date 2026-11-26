const service = require("../services/experimentService"),
      logger = require('../utils/logger');

module.exports = {
    /**
     * Get
     * 
     * Returns a list with all 'experimentos'.
     */
    get: function (req, res) {
        service.get_experiments().then(directories => res.json({ experiment: directories }));
    },

    /**
     * Post
     * 
     * Create a new experiment.
     */
    create: function (req, res) {
        if (req.body.experiment === undefined) {
            return res.status(400).json({ status: "API POST experiments: Invalid request. Missing 'experiment' value." });
        }
        
        if (service.experiment_directory_exists(req.body.experiment)) {
            return res.status(409).json({ status: "Experiment not created, experiment already exists." });
        }

        service.create_experiment(req.body.experiment)

        return res.json({ status: "success" });
    },

    /**
     * Exists
     * 
     * Returns if a experiment exists or not.
     */
    exists: function (req, res) {
        if (!req.body.experiment || !req.body.activity || !req.body.user) {
            logger.error("API experiment_exists: Invalid request");
            return res.status(400).json({ status: "Request is missing information." });
        }

        var experiment = req.body.experiment;
        var activity = req.body.activity;
        var user = req.body.user;

        // Check if experiment really exists
        if (!service.experiment_exists(experiment, activity, user)) {
            return res.status(404).json({ status: "Don't exist" });
        }

        return res.json({ status: "Success" });
    },

    /**
     * No Video
     * 
     * Mark an experiment as having no video.
     */
    no_video: function (req, res) {
        if (!req.body.directory) {
            return res.status(400).json({ status: "Missing 'directory' value." });
        }

        const directory = req.body.directory;
        logger.info("No video requested for: " + directory);

        try {
            service.mark_no_video_for_experiment(directory);
            return res.json({ status: "success" });
        } catch (e) {
            logger.error("No video failed: " + e.message);
            return res.status(500).json({ status: "Error: " + e.message });
        }
    },
}