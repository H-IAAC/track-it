import os
import shutil
from CsvUtils import CsvUtils
from Logger import Logger

from pathlib import Path
from zipfile import ZipFile
from configparser import ConfigParser
import tempfile

class ProcessFile:
    def __init__(self, fullpath, postprocessor_path):
        experiment_name = Path(fullpath).parts
        self.experiment = str(experiment_name[-2])
        self.fullpath = fullpath
        self.filename = Path(fullpath).stem
        self.extension = Path(fullpath).suffix
        self.postprocessor_path = postprocessor_path

    def _finalize_manifest(self, postprocessor_directory):
        import json
        manifest_path = os.path.join(postprocessor_directory, "session_manifest.json")
        if not os.path.exists(manifest_path):
            return
        try:
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            artifacts = manifest.setdefault('artifacts', {})
            raw_sensors_dir = os.path.join(postprocessor_directory, 'raw_sensors')
            if os.path.isdir(raw_sensors_dir):
                artifacts['raw_sensors'] = sorted(
                    f"raw_sensors/{f}" for f in os.listdir(raw_sensors_dir) if f.endswith('.csv'))
                artifacts['raw_sensors_dir'] = 'raw_sensors'
            if artifacts.get('clean_sensors'):
                manifest.setdefault('pipeline_status', {})['server_processed'] = True
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f, indent=4)
            Logger.log("  Finalized session_manifest.json (raw_sensors paths, server_processed)")
        except Exception as e:
            Logger.log_error(postprocessor_directory, f"Failed to finalize manifest: {e}")

    def _trigger_auto_anonymize(self, postprocessor_directory):
        import requests
        import threading
        
        # The Face Masking Studio finds the video through the manifest, so wait
        # until both the manifest and its raw_video are in place.
        import json
        manifest_path = os.path.join(postprocessor_directory, 'session_manifest.json')
        if not os.path.exists(manifest_path):
            return
        try:
            with open(manifest_path, 'r') as f:
                raw_video = json.load(f).get('artifacts', {}).get('raw_video')
        except (OSError, ValueError):
            return
        if not raw_video or not os.path.exists(os.path.join(postprocessor_directory, raw_video)):
            return

        def _fire():
            try:
                url = f"http://localhost:8000/api/video/dataset:{self.experiment}/auto-anonymize"
                Logger.log(f"  Triggering face masking auto-anonymize: {url}")
                res = requests.post(url, timeout=5)
                if res.status_code == 409:
                    Logger.log(f"  Face masking already running for {self.experiment}.")
                elif res.status_code == 200:
                    Logger.log(f"  Face masking started successfully for {self.experiment}.")
                else:
                    Logger.log_error(postprocessor_directory, f"Face masking trigger returned {res.status_code}: {res.text}")
            except requests.exceptions.RequestException:
                Logger.log(f"  Face Masking Studio offline or unreachable. Skipping auto-anonymization.")
                
        threading.Thread(target=_fire, daemon=True).start()

    def __str__(self):
        return f"filename: {self.fullpath} extension: {self.extension} experiment: {self.experiment}"

    def check_event(self):
        # Create new directory based on 'experiment' value
        postprocessor_directory = f"{os.sep}{self.postprocessor_path}{os.sep}{self.experiment}{os.sep}"
        if not os.path.exists(postprocessor_directory):
            Logger.log(f"Create new directory:  {postprocessor_directory}")
            os.makedirs(postprocessor_directory, exist_ok=True)

        manifest_path = os.path.join(postprocessor_directory, "session_manifest.json")
        if os.path.exists(manifest_path):
            try:
                import json
                with open(manifest_path, 'r') as f:
                    m = json.load(f)
                if m.get('pipeline_status', {}).get('server_processed', False):
                    Logger.log(f"Session {self.experiment} is already server_processed. Skipping {self.filename}{self.extension}")
                    return
            except Exception:
                pass

        try:
            # Check what action to take based on file extesion
            if self.extension == '.csv'.lower() or self.extension == '.zip'.lower():

                if self.extension == '.zip'.lower():
                    with ZipFile(self.fullpath, 'r') as zObject:
                        uncompressed_filename = Path(self.fullpath).stem + '.csv'
                        Logger.log(f"Uncompressing {self.fullpath}")
                        Logger.log(f"  Extracting file {uncompressed_filename} from zip")

                        zObject.extract(uncompressed_filename,
                                        path=tempfile.gettempdir())
                        Logger.log(f"File {uncompressed_filename} extracted with success")
                    zObject.close()

                    self.fullpath = tempfile.gettempdir() + os.sep + uncompressed_filename
                    self.filename = Path(self.fullpath).stem
                    self.extension = Path(self.fullpath).suffix

                Logger.log(f"Processing csv file {self.filename}")

                has_video = self.has_video_files(postprocessor_directory)
                is_subsequent = os.path.exists(os.path.join(postprocessor_directory, 'raw_sensors'))

                if not has_video and not is_subsequent:
                    self.handle_csv_when_no_video(postprocessor_directory)
                    return

                video_metadata_path = has_video if os.path.isabs(has_video) else f"{postprocessor_directory}{has_video}" if has_video else None
                self.handle_csv(self.fullpath, postprocessor_directory, video_metadata_path, is_subsequent)
                if is_subsequent:
                    self._finalize_manifest(postprocessor_directory)
                
                # os.remove(self.fullpath) # Commented out to preserve raw files

            elif self.extension == '.video'.lower():
                Logger.log(f"{self.filename} processing video metadata file")
                self.handle_video(postprocessor_directory)
                return

            elif self.extension == '.no_video':
                Logger.log(f"{self.filename} processing no video flag")
                self.handle_no_video(postprocessor_directory)
                return

            elif self.extension == '.json' and self.filename == 'session_manifest':
                Logger.log(f"{self.filename} processing session manifest")
                self.handle_session_manifest(postprocessor_directory)
                return

            else:
                Logger.log("No action for file " + self.filename + self.extension)
                return
        except Exception as e:
            Logger.log_error(postprocessor_directory, f"Failed when processing: [{self.filename}]. {e}")
            Logger.log_error(postprocessor_directory, f"Check if video was correctly uploaded.")


    def handle_csv_when_no_video(self, postprocessor_directory):
        # Without the video we cant process the file, as we dont have timestamps values
        # Need to create a copy in 'waiting' directory
        waiting_dir = f"{postprocessor_directory}waiting"
        waiting_file = f"{waiting_dir}{os.sep}{Path(self.fullpath).name}"

        os.makedirs(waiting_dir, exist_ok=True)            
        shutil.copyfile(self.fullpath, waiting_file)
        
        Logger.log(f"  {self.filename} file waiting for video, copied to: {waiting_file}")
        
    def handle_csv(self, csv_fullpath, postprocessor_directory, video_metadata, is_subsequent=False):
        CsvUtils.checkFile(postprocessor_directory, csv_fullpath)

        try:
            sensors_dir = os.path.join(postprocessor_directory, "sensors")
            os.makedirs(sensors_dir, exist_ok=True)
            sensors_dest = sensors_dir + os.sep

            if is_subsequent:
                video_metadata = None
                raw_sensors_dir = os.path.join(postprocessor_directory, 'raw_sensors')
                os.makedirs(raw_sensors_dir, exist_ok=True)
                raw_dest = os.path.join(raw_sensors_dir, os.path.basename(csv_fullpath))
                Logger.log(f"Subsequent collection: Copying {os.path.basename(csv_fullpath)} directly to raw_sensors")
                shutil.copyfile(csv_fullpath, raw_dest)
            
            if video_metadata:
                metadata = self.get_video_metadata(video_metadata)
                
                # Remove rows before and after the video timestamps
                if not CsvUtils.drop_row_lower_than(csv_fullpath, int(metadata['startTimestamp'])):
                    Logger.log_error(postprocessor_directory, f"{self.filename} is invalid! need to check {[csv_fullpath]} timestamp after drop rows lower than initial timestamp. (Data were collected before recording the video.)")
                    return
                    
                if not CsvUtils.drop_row_bigger_than(csv_fullpath, int(metadata['endTimestamp'])):
                    Logger.log_error(postprocessor_directory, f"{self.filename} is invalid! need to check {[csv_fullpath]} timestamp after drop rows bigger than initial timestamp. (Data were collected after recording the video.)")
                    return
                
                processed_files = CsvUtils.split(csv_fullpath, sensors_dest, int(metadata['startTimestamp']))
            else:
                # No video metadata, process as is
                from datetime import datetime
                suffix = datetime.now().strftime("_new_%Y%m%d_%H%M%S") if is_subsequent else ""
                processed_files = CsvUtils.split(csv_fullpath, sensors_dest, None, suffix)

        except Exception as e:
            Logger.log_error(postprocessor_directory, f"Something went wrong with file [{self.filename}] and {csv_fullpath}. {e}")
            return

        clean_sensor_names = []
        for filename in processed_files:
            if ".csv" in filename:
                Logger.log("-> " + filename)
                Logger.log("-> " + postprocessor_directory)
                # Appending "sensors/" to the basename for the manifest
                clean_sensor_names.append(f"sensors/{os.path.basename(filename)}")

        if not is_subsequent:
            # Update session_manifest.json with clean_sensors
            manifest_path = os.path.join(postprocessor_directory, "session_manifest.json")
            if os.path.exists(manifest_path) and clean_sensor_names:
                import json
                try:
                    with open(manifest_path, 'r') as f:
                        manifest = json.load(f)
                    
                    # Append to existing list or create new one
                    existing_clean = manifest.setdefault('artifacts', {}).get('clean_sensors', [])
                    for name in clean_sensor_names:
                        if name not in existing_clean:
                            existing_clean.append(name)
                    manifest['artifacts']['clean_sensors'] = existing_clean
                    manifest['artifacts']['sensors_dir'] = 'sensors'
                    
                    with open(manifest_path, 'w') as f:
                        json.dump(manifest, f, indent=4)
                    Logger.log(f"Updated session_manifest.json with clean_sensors: {clean_sensor_names}")
                except Exception as e:
                    Logger.log_error(postprocessor_directory, f"Failed to update manifest: {e}")

        self._finalize_manifest(postprocessor_directory)


    def handle_video(self, postprocessor_directory):
        # Create videos directory
        videos_dir = os.path.join(postprocessor_directory, 'videos')
        os.makedirs(videos_dir, exist_ok=True)
        
        # Copy .video metadata to videos directory
        metadata_file = self.filename + self.extension
        dest_metadata_file = os.path.join(videos_dir, metadata_file)
        Logger.log(f"  Copy from: {self.fullpath} to: {dest_metadata_file}")
        shutil.copyfile(self.fullpath, dest_metadata_file)
        
        # Copy raw .mp4 to postprocessor directory (NO masking applied)
        # Face masking is now handled separately by the Face Masking Studio tool.
        mp4_file = self.filename + ".mp4"
        preprocessor_mp4_fullpath = self.fullpath.replace(".video", ".mp4")
        postprocessor_mp4_fullpath = os.path.join(videos_dir, mp4_file)
        if os.path.exists(preprocessor_mp4_fullpath):
            Logger.log(f"  Copy raw video (no masking): {preprocessor_mp4_fullpath} to: {postprocessor_mp4_fullpath}")
            shutil.copyfile(preprocessor_mp4_fullpath, postprocessor_mp4_fullpath)
            
            # Update session_manifest.json with raw_video if it exists
            manifest_post = os.path.join(postprocessor_directory, "session_manifest.json")
            if os.path.exists(manifest_post):
                import json
                try:
                    with open(manifest_post, "r") as f:
                        manifest = json.load(f)
                    manifest.setdefault("artifacts", {})["raw_video"] = f"videos/{mp4_file}"
                    manifest["artifacts"]["videos_dir"] = "videos"
                    with open(manifest_post, "w") as f:
                        json.dump(manifest, f, indent=4)
                    Logger.log(f"  Updated manifest with raw_video: videos/{mp4_file}")
                except Exception as e:
                    Logger.log_error(postprocessor_directory, f"Failed to update manifest with raw_video: {e}")
        else:
            Logger.log(f"  No .mp4 found at {preprocessor_mp4_fullpath}, skipping video copy.")

        # Check for session_manifest.json in case it was missed (do this FIRST so handle_csv can update it)
        preprocessor_dir = os.path.dirname(self.fullpath)
        manifest_path = os.path.join(preprocessor_dir, "session_manifest.json")
        if os.path.exists(manifest_path):
            dest_path = f"{postprocessor_directory}session_manifest.json"
            if not os.path.exists(dest_path):
                Logger.log(f"  Copy missed session manifest: {manifest_path} to {dest_path}")
                shutil.copyfile(manifest_path, dest_path)

        # Need to check if there are .csv files, in the 'waiting' directory
        waiting_dir = f"{postprocessor_directory}waiting{os.sep}"
        
        if os.path.exists(waiting_dir):        
            for csv_file in os.listdir(waiting_dir):
                csv_file_fullpath = f"{waiting_dir}{csv_file}"
                Logger.log(f"  Checking for csv in waiting directory: {csv_file_fullpath}")
                self.handle_csv(csv_file_fullpath, postprocessor_directory, dest_metadata_file)
                
            raw_sensors_dir = os.path.join(postprocessor_directory, 'raw_sensors')
            if os.path.exists(raw_sensors_dir):
                shutil.rmtree(raw_sensors_dir)
            if os.path.exists(waiting_dir):
                try:
                    os.rename(waiting_dir, raw_sensors_dir)
                except OSError:
                    pass
            self._finalize_manifest(postprocessor_directory)
        
        self._trigger_auto_anonymize(postprocessor_directory)


    def handle_no_video(self, postprocessor_directory):
        Logger.log(f"  No video flag detected for experiment: {self.experiment}")
        
        # Check for session_manifest.json in case it was missed (do this FIRST so handle_csv can update it)
        preprocessor_dir = os.path.dirname(self.fullpath)
        manifest_path = os.path.join(preprocessor_dir, "session_manifest.json")
        if os.path.exists(manifest_path):
            dest_path = f"{postprocessor_directory}session_manifest.json"
            if not os.path.exists(dest_path):
                Logger.log(f"  Copy missed session manifest: {manifest_path} to {dest_path}")
                shutil.copyfile(manifest_path, dest_path)

        processed_csvs = set()

        # Need to check if there are .csv files, in the 'waiting' directory
        waiting_dir = f"{postprocessor_directory}waiting{os.sep}"
        
        if os.path.exists(waiting_dir):        
            for csv_file in os.listdir(waiting_dir):
                csv_file_fullpath = f"{waiting_dir}{csv_file}"
                Logger.log(f"  Checking for csv in waiting directory: {csv_file_fullpath}")
                self.handle_csv(csv_file_fullpath, postprocessor_directory, None)
                processed_csvs.add(csv_file)
                
            raw_sensors_dir = os.path.join(postprocessor_directory, 'raw_sensors')
            if os.path.exists(raw_sensors_dir):
                shutil.rmtree(raw_sensors_dir)
            if os.path.exists(waiting_dir):
                try:
                    os.rename(waiting_dir, raw_sensors_dir)
                except OSError:
                    pass
            self._finalize_manifest(postprocessor_directory)

        # Also check preprocessor directory in case CSVs were missed by watchdog (e.g. restart)
        preprocessor_dir = os.path.dirname(self.fullpath)
        if os.path.exists(preprocessor_dir):
            for fname in os.listdir(preprocessor_dir):
                if fname.endswith(".csv") and fname not in processed_csvs:
                    csv_file_fullpath = os.path.join(preprocessor_dir, fname)
                    Logger.log(f"  Checking for missed csv in preprocessor directory: {csv_file_fullpath}")
                    self.handle_csv(csv_file_fullpath, postprocessor_directory, None)
                    processed_csvs.add(fname)

        
    def handle_session_manifest(self, postprocessor_directory):
        # Copy session_manifest.json to the output directory
        manifest_file = self.filename + self.extension
        dest_path = f"{postprocessor_directory}{manifest_file}"
        Logger.log(f"  Copy session manifest: {self.fullpath} to: {dest_path}")
        shutil.copyfile(self.fullpath, dest_path)

        # Ensure that any already processed clean sensors are added to the manifest
        # This handles the case where CSV files were processed before the manifest arrived.
        clean_sensors = []
        raw_video = None
        
        sensors_dir = os.path.join(postprocessor_directory, 'sensors')
        if os.path.exists(sensors_dir):
            for fname in os.listdir(sensors_dir):
                if fname.endswith('.csv') and not fname.startswith('raw_') and not fname.endswith('_Ann.csv'):
                    clean_sensors.append(f"sensors/{fname}")
                    
        videos_dir = os.path.join(postprocessor_directory, 'videos')
        if os.path.exists(videos_dir):
            for fname in os.listdir(videos_dir):
                if fname.endswith('.mp4'):
                    raw_video = f"videos/{fname}"
        
        if clean_sensors or raw_video:
            import json
            try:
                with open(dest_path, 'r') as f:
                    manifest = json.load(f)
                
                if clean_sensors:
                    existing_clean = manifest.setdefault('artifacts', {}).get('clean_sensors', [])
                    for name in clean_sensors:
                        if name not in existing_clean:
                            existing_clean.append(name)
                    manifest['artifacts']['clean_sensors'] = existing_clean
                
                if raw_video:
                    manifest.setdefault('artifacts', {})['raw_video'] = raw_video
                
                with open(dest_path, 'w') as f:
                    json.dump(manifest, f, indent=4)
                Logger.log(f"  Updated newly copied manifest with existing clean_sensors/raw_video")
            except Exception as e:
                Logger.log_error(postprocessor_directory, f"Failed to update manifest with clean_sensors/raw_video: {e}")

        self._finalize_manifest(postprocessor_directory)
        self._trigger_auto_anonymize(postprocessor_directory)

    def has_video_files(self, postprocessor_directory):
        if not os.path.exists(postprocessor_directory):
            return False
        
        # Check in both root and videos/ directory
        dirs_to_check = [postprocessor_directory, os.path.join(postprocessor_directory, 'videos')]
        
        for d in dirs_to_check:
            if not os.path.exists(d):
                continue
            for fname in os.listdir(d):
                Logger.log(f"  Checking if has video files in {d} checking {fname} file")
                if fname.endswith('.video') and not fname.endswith('.mp4.video') and not fname.endswith('.no_video'):
                    Logger.log(f"    found! {fname}")
                    return os.path.join(d, fname) if d != postprocessor_directory else fname
        
        Logger.log(f"  No video related file found in {postprocessor_directory}")
        return False

    def get_video_metadata(self, video_file):
        config = ConfigParser()
        
        if not os.path.exists(video_file):
            Logger.log(f"File {video_file} not exists!")
            
        # parse existing file
        config.read(video_file, encoding="cp1251")

        # read values from a section
        startTimestamp = config.get('Metadata', 'startTimestamp')
        endTimestamp = config.get('Metadata', 'endTimestamp')
        
        return dict(startTimestamp = startTimestamp, endTimestamp = endTimestamp)
