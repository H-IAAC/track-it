import os
import sys
import glob

# Add postprocessor to sys.path so its internal imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
post_processor_dir = os.path.join(current_dir, 'postprocessor')
sys.path.append(post_processor_dir)

from ProcessFile import ProcessFile

def process_directory(pre_dir, pos_dir):
    os.makedirs(pos_dir, exist_ok=True)
    
    if not os.path.exists(pre_dir):
        print(f"Directory {pre_dir} does not exist.")
        return

    # Iterate over all experiment folders in pre_dir
    for experiment_name in os.listdir(pre_dir):
        exp_path = os.path.join(pre_dir, experiment_name)
        if not os.path.isdir(exp_path):
            continue
            
        print(f"=====================================")
        print(f"Processing experiment: {experiment_name}")
        
        # 1. Process .video files first
        # This copies the video so the CSVs won't be put into the 'waiting' state
        for fname in os.listdir(exp_path):
            if fname.endswith('.video'):
                v = os.path.join(exp_path, fname)
                print(f"  Handling video file: {v}")
                process = ProcessFile(v, pos_dir.strip(os.sep))
                process.check_event()
            
        # 2. Process .zip files
        for fname in os.listdir(exp_path):
            if fname.endswith('.zip'):
                z = os.path.join(exp_path, fname)
                print(f"  Handling zip file: {z}")
                process = ProcessFile(z, pos_dir.strip(os.sep))
                process.check_event()
            
        # 3. Process .csv files
        for fname in os.listdir(exp_path):
            if fname.endswith('.csv'):
                c = os.path.join(exp_path, fname)
                print(f"  Handling csv file: {c}")
                process = ProcessFile(c, pos_dir.strip(os.sep))
                process.check_event()

if __name__ == "__main__":
    pre_dir = os.path.join(current_dir, 'files', 'pre')
    pos_dir = os.path.join(current_dir, 'files', 'pos')
    
    print(f"Starting batch process...")
    print(f"PRE: {pre_dir}")
    print(f"POS: {pos_dir}")
    
    process_directory(pre_dir, pos_dir)
    print("=====================================")
    print("Finished processing all files.")
