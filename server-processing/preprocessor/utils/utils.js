const fs = require('fs'),
    logger = require('../utils/logger'),
    consts = require('../utils/consts'),
    { parse } = require("csv-parse"),
    readLastLines = require('read-last-lines'),
    path = require('path'),
    os = require('os');

module.exports = {
    /**
     * @return {json}           Return content from ./config/config.json
     */
    get_config: function () {

        logger.info("Config file: " + consts.CONFIG_FILE_PATH);

        if (fs.existsSync(consts.CONFIG_FILE_PATH)) {
            let config = JSON.parse(fs.readFileSync(consts.CONFIG_FILE_PATH));
            // The JWT signing key is never stored in the repository.
            config.jwtKey = process.env.JWT_KEY || config.jwtKey || require('crypto').randomBytes(64).toString('base64url');
            return config;
        }

        logger.error("ERROR! Missing config file: " + consts.CONFIG_FILE_PATH);
        return {};
    },

    /**
     * @param {type} dir_path   Path from the directory to be created.
     * @return {type}           Return true if directory created, false if fails or already exists.
     */
    create_directory: function (dir_path) {
        if (!fs.existsSync(dir_path)) {
            // .. if not, create it.
            logger.info("Creating directory: " + dir_path);
            fs.mkdirSync(dir_path, { recursive: true });
        } else {
            return false;
        }

        return true;
    },

    /**
     * Validate csv format and name.
     * 
     * @param {type} file_path   Path to the csv file.
     * @param {type} file_name   Csv file name, note that file_path param may not use the original file name.
     */
    async validate_csv(file_path, file_name) {

        // Filename format must be "<user>_<activity>_<on-BodyPosition>__20230110.232916.csv"
        if (file_name.split("_").length !== 5)
            return "fail";

        if (!file_name.split("_")[0] || !file_name.split("_")[1] || !file_name.split("_")[2])
            return "fail";

        // Check if csv content is consistent, this verification is not checking
        // if rows have the correct columns, it is a generic verification.
        return new Promise(function (resolve, reject) {
            fs.createReadStream(file_path)
                .pipe(parse({ delimiter: ";" }))
                .on("data", function (row) {
                    //console.log(row);
                })
                .on("end", function () {
                    //logger.info("CSV file " + file_path + " is valid.");
                    resolve("success");
                })
                .on("error", function (error) {
                    logger.error("CSV file " + file_path + " is invalid. (" + error.message + ")");
                    resolve("fail");
                });
        })
    },

    extract_experiment_from_directory(directory) {
        let idx = directory.indexOf(" [");
        if (idx === -1) return directory;
        return directory.substring(0, idx);
    },

    extract_user_from_directory(directory) {
        let lastStart = directory.lastIndexOf(" [");
        if (lastStart === -1 || lastStart === directory.indexOf(" [")) return "---";
        let lastEnd = directory.lastIndexOf("]");
        return directory.substring(lastStart + 2, lastEnd !== -1 ? lastEnd : directory.length);
    },

    extract_activity_from_directory(directory) {
        let start = directory.indexOf(" [");
        if (start === -1) return "---";
        let end = directory.indexOf("] ", start);
        if (end === -1) end = directory.indexOf("]", start);
        return directory.substring(start + 2, end !== -1 ? end : directory.length);
    },

    number_of_csv_files_in_directory(directory) {

        if (!fs.existsSync(directory)) return 0;

        let count = 0;
        var files = fs.readdirSync(directory);

        files.forEach(file => {
            if (file.toLowerCase().includes('.csv'))
                count++;
        });

        return count;
    },

    get_directory_video(directory) {

        let ret = 'none';

        if (!fs.existsSync(directory)) return ret;

        var files = fs.readdirSync(directory);        

        files.forEach(file => {
            if (file.toLowerCase().includes('.mp4'))
                ret = file;
        });

        return ret;
    },

    get_template(directory) {

        var content = '{}';

        if (!fs.existsSync(directory)) return content;

        var files = fs.readdirSync(directory);        

        files.forEach(file => {
            if (file.toLowerCase().includes('.json')) {
                content = fs.readFileSync(directory + path.sep + file);
            }
        });

        return content;
    }
}
