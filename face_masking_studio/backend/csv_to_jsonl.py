import json
#!/usr/bin/env python3
import sys
import os
import csv
import shutil
from pathlib import Path
import re

import config
import session_manager

def rdp(pts, epsilon):
    if len(pts) < 3:
        return pts
    
    dmax = 0.0
    index = 0
    A = pts[0]
    B = pts[-1]
    
    for i in range(1, len(pts) - 1):
        P = pts[i]
        # calculate max deviation from linear interpolation
        t = (P['frame'] - A['frame']) / (B['frame'] - A['frame'])
        expected_x = A['x'] + t * (B['x'] - A['x'])
        expected_y = A['y'] + t * (B['y'] - A['y'])
        expected_w = A['w'] + t * (B['w'] - A['w'])
        expected_h = A['h'] + t * (B['h'] - A['h'])
        
        d = max(abs(P['x'] - expected_x),
                abs(P['y'] - expected_y),
                abs(P['w'] - expected_w),
                abs(P['h'] - expected_h))
                
        if d > dmax:
            index = i
            dmax = d
            
    if dmax > epsilon:
        left = rdp(pts[:index+1], epsilon)
        right = rdp(pts[index:], epsilon)
        return left[:-1] + right
    else:
        return [A, B]

def format_id(track_id):
    """Convert integer IDs to t_00x and manual M IDs to m_00x."""
    try:
        # Try if it's an integer
        i = int(track_id)
        return f"t_{i:03d}"
    except ValueError:
        # Check if it starts with 'M'
        s = str(track_id)
        if s.startswith('M') or s.startswith('m'):
            try:
                i = int(s[1:])
                return f"m_{i:03d}"
            except ValueError:
                pass
        return s

def get_iou(box1, box2):
    ix1 = max(box1['x'], box2['x'])
    iy1 = max(box1['y'], box2['y'])
    ix2 = min(box1['x'] + box1['w'], box2['x'] + box2['w'])
    iy2 = min(box1['y'] + box1['h'], box2['y'] + box2['h'])
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0: return 0
    union = box1['w']*box1['h'] + box2['w']*box2['h'] - inter
    return inter / union if union > 0 else 0

def find_next_valid_boxes(df_rows, start_index):
    for i in range(start_index + 1, len(df_rows)):
        row = df_rows[i]
        tids = json.loads(row.get('track_ids', '[]') if row.get('track_ids') and not pd_isna(row.get('track_ids')) else '[]')
        boxes = json.loads(row.get('bboxes', '[]') if row.get('bboxes') and not pd_isna(row.get('bboxes')) else '[]')
        if len(boxes) > 0:
            broken = False
            for bi in range(len(boxes)):
                if bi >= len(tids) or tids[bi] is None:
                    broken = True
                    break
            if not broken:
                return int(row['frame']) - 1, tids, boxes
    return None, [], []

def process_csv(csv_path, jsonl_path, prev_jsonl_path=None):
    """Convert a single CSV file to JSONL."""
    print(f"Reading CSV: {csv_path}")
    if not os.path.exists(csv_path):
        print(f"Warning: CSV not found: {csv_path}")
        return False

    prev_state = {}
    if prev_jsonl_path and os.path.exists(prev_jsonl_path):
        with open(prev_jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                rec = json.loads(line)
                prev_state[rec['frame']] = rec.get('masks', [])

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = list(csv.DictReader(f))
        frames_data = {}
        consecutive_broken = 0
        
        for idx, row in enumerate(reader):
            try:
                # frame in CSV is usually 1-indexed, JSONL is 0-indexed
                # But let's check if the first frame is 0 or 1.
                # Actually, the tracker uses frame directly from OpenCV. Let's just use it as is but subtract 1 if we want it 0-indexed.
                # The easiest is to just use frame - 1 if it starts at 1, but if it starts at 0, leave it.
                # Let's just use int(row['frame']) - 1? The original video converter used `frame_count += 1` then wrote it. So it's 1-indexed.
                frame_idx = max(0, int(row['frame']) - 1)
                
                ts = float(row['timestamp_s'])
                
                bboxes_str = row.get('bboxes', '[]')
                if not bboxes_str or pd_isna(bboxes_str): bboxes_str = '[]'
                bboxes = json.loads(bboxes_str)
                
                track_ids_str = row.get('track_ids', '[]')
                if not track_ids_str or pd_isna(track_ids_str): track_ids_str = '[]'
                track_ids = json.loads(track_ids_str)
                
                face_ratios_str = row.get('face_ratios', '[]')
                if not face_ratios_str or pd_isna(face_ratios_str): face_ratios_str = '[]'
                face_ratios = json.loads(face_ratios_str)
                
                source_pass_kind = row.get('source_pass_kind', 'track')
                
                is_broken = False
                if len(bboxes) > 0:
                    for i in range(len(bboxes)):
                        if i >= len(track_ids) or track_ids[i] is None:
                            is_broken = True
                            break

                if is_broken:
                    consecutive_broken += 1
                    if consecutive_broken > 5:
                        print(f"Error: Too many consecutive broken frames (>5) starting at frame {frame_idx}.")
                        return False
                else:
                    consecutive_broken = 0
                
                masks = []
                assigned_tids = [None] * len(bboxes)
                parsed_boxes = []
                
                # 1. Parse all
                for i, box in enumerate(bboxes):
                    if len(box) >= 4:
                        xmin, ymin, xmax, ymax = box[:4]
                        ratio = 1.0
                        if i < len(face_ratios):
                            try: ratio = float(face_ratios[i])
                            except: pass
                        w = xmax - xmin
                        h = (ymax - ymin) * ratio
                        parsed_boxes.append({'i': i, 'x': round(xmin, 2), 'y': round(ymin, 2), 'w': round(w, 2), 'h': round(h, 2)})
                        
                        if i < len(track_ids) and track_ids[i] is not None:
                            assigned_tids[i] = track_ids[i]
                            
                # 2. If broken, run matching algorithms
                if is_broken:
                    expected_boxes = []
                    if len(frames_data) > 0:
                        last_out_key = max(frames_data.keys())
                        last_out = frames_data[last_out_key]
                        for pm in last_out.get('masks', []):
                            expected_boxes.append(pm)
                            
                    future_frame, f_tids, f_boxes = find_next_valid_boxes(reader, idx)
                    used_ids = set()
                    
                    # Pass 1: Strict Temporal Interpolation
                    for i, pb in enumerate(parsed_boxes):
                        if assigned_tids[i] is None:
                            best_iou = 0.5
                            best_id = None
                            
                            if len(expected_boxes) > 0 and future_frame is not None:
                                for past_m in expected_boxes:
                                    if past_m['id'] in used_ids: continue
                                    future_m = None
                                    for fi, fbox in enumerate(f_boxes):
                                        if fi < len(f_tids) and format_id(f_tids[fi]) == past_m['id']:
                                            future_m = fbox
                                            break
                                    if future_m and len(future_m) >= 4:
                                        fx, fy, fx2, fy2 = future_m[:4]
                                        fw, fh = fx2 - fx, fy2 - fy
                                        dist_frames = future_frame - last_out['frame']
                                        curr_dist = frame_idx - last_out['frame']
                                        t = curr_dist / dist_frames if dist_frames > 0 else 0
                                        avg_box = {
                                            'id': past_m['id'],
                                            'x': past_m['x'] + (fx - past_m['x']) * t,
                                            'y': past_m['y'] + (fy - past_m['y']) * t,
                                            'w': past_m['w'] + (fw - past_m['w']) * t,
                                            'h': past_m['h'] + (fh - past_m['h']) * t
                                        }
                                        iou = get_iou(pb, avg_box)
                                        if iou > best_iou:
                                            best_iou = iou
                                            best_id = avg_box['id']
                            
                            if best_id is not None:
                                assigned_tids[i] = best_id
                                used_ids.add(best_id)
                                print(f"[FRAME {frame_idx}] STAGE 1 (Interpolation): Box {i} matched to ID {best_id} with IoU {best_iou:.2f}")
                                
                    # Pass 2: Fallback to prev_state (Strict)
                    for i, pb in enumerate(parsed_boxes):
                        if assigned_tids[i] is None:
                            best_iou = 0.5
                            best_id = None
                            if prev_state and frame_idx in prev_state:
                                for pm in prev_state[frame_idx]:
                                    if pm['id'] in used_ids: continue
                                    iou = get_iou(pb, pm)
                                    if iou > best_iou:
                                        best_iou = iou
                                        best_id = pm['id']
                            if best_id is not None:
                                assigned_tids[i] = best_id
                                used_ids.add(best_id)
                                print(f"[FRAME {frame_idx}] STAGE 2 (Prev_State): Box {i} matched to ID {best_id} with IoU {best_iou:.2f}")
                                
                    # Pass 3: Greedy Leftover Matching (Past + Future)
                    candidate_pool = []
                    for pm in expected_boxes:
                        if pm['id'] not in used_ids:
                            candidate_pool.append({'id': pm['id'], 'box': pm})
                    if future_frame is not None:
                        for fi, fbox in enumerate(f_boxes):
                            if fi < len(f_tids) and len(fbox) >= 4:
                                fid = format_id(f_tids[fi])
                                if fid not in used_ids and fid not in [c['id'] for c in candidate_pool]:
                                    candidate_pool.append({'id': fid, 'box': {'x': fbox[0], 'y': fbox[1], 'w': fbox[2]-fbox[0], 'h': fbox[3]-fbox[1]}})

                    for i, pb in enumerate(parsed_boxes):
                        if assigned_tids[i] is None:
                            best_iou = 0.0
                            best_cand = None
                            for cand in candidate_pool:
                                iou = get_iou(pb, cand['box'])
                                if iou > best_iou:
                                    best_iou = iou
                                    best_cand = cand
                            if best_cand is not None:
                                assigned_tids[i] = best_cand['id']
                                used_ids.add(best_cand['id'])
                                candidate_pool = [c for c in candidate_pool if c['id'] != best_cand['id']]
                                print(f"[FRAME {frame_idx}] STAGE 3 (Greedy): Box {i} matched to candidate {best_cand['id']} with IoU {best_iou:.2f}")
                            else:
                                assigned_tids[i] = f"orphan_{frame_idx}_{pb['i']}"
                                print(f"[FRAME {frame_idx}] STAGE 3 (Orphan): No match found. Box {i} marked as orphan {assigned_tids[i]}")

                # 3. Create final masks
                for i, pb in enumerate(parsed_boxes):
                    tid = assigned_tids[i] if assigned_tids[i] is not None else str(pb['i'])
                    
                    source = "tracked"
                    state = "active"
                    if prev_state and frame_idx in prev_state:
                        prev_mask = next((m for m in prev_state[frame_idx] if m['id'] == format_id(tid)), None)
                        if prev_mask:
                            if prev_mask['x'] != pb['x'] or prev_mask['y'] != pb['y'] or \
                               prev_mask['w'] != pb['w'] or prev_mask['h'] != pb['h']:
                                if prev_mask.get('source') == 'manual':
                                    source = "legacy_manual_anchor"
                                else:
                                    source = "legacy_manual"
                            else:
                                source = prev_mask.get('source', 'tracked')
                                state = prev_mask.get('state', 'active')
                        else:
                            source = "legacy_manual"
                    elif prev_jsonl_path is not None:
                        source = "legacy_manual"
                        
                    masks.append({
                        "id": format_id(tid),
                        "x": pb['x'],
                        "y": pb['y'],
                        "w": pb['w'],
                        "h": pb['h'],
                        "state": state,
                        "source": source
                    })
                
                line = {
                    "frame": frame_idx,
                    "ts": round(ts, 3),
                    "masks": masks
                }
                frames_data[frame_idx] = line
            except Exception as e:
                print(f"Error parsing row: {row}")
                print(e)
                continue

    # === RDP DECIMATION FOR LEGACY MANUAL PASSES ===
    from collections import defaultdict
    tracks = defaultdict(list)
    for f in sorted(frames_data.keys()):
        for m in frames_data[f]['masks']:
            if m['source'] in ('legacy_manual', 'legacy_manual_anchor'):
                tracks[m['id']].append({'frame': f, 'mask': m})

    for tid, pts in tracks.items():
        # Group into contiguous segments
        segments = []
        current_seg = []
        for p in pts:
            if not current_seg:
                current_seg.append(p)
            elif p['frame'] == current_seg[-1]['frame'] + 1:
                current_seg.append(p)
            else:
                segments.append(current_seg)
                current_seg = [p]
        if current_seg:
            segments.append(current_seg)
            
        for seg in segments:
            # Extract points for RDP algorithm
            rdp_pts = [{'frame': p['frame'], 'x': p['mask']['x'], 'y': p['mask']['y'], 'w': p['mask']['w'], 'h': p['mask']['h']} for p in seg]
            
            # Run RDP
            keep_pts = rdp(rdp_pts, epsilon=2.5)
            keep_frames = {p['frame'] for p in keep_pts}
            
            for p in seg:
                if p['frame'] in keep_frames or p['mask'].get('source') == 'legacy_manual_anchor':
                    p['mask']['source'] = 'manual'
                else:
                    p['mask']['source'] = 'interpolated'
            
            # Prevent frontend from interpolating this manual segment with the next segment
            # if there is a gap in between.
            seg[-1]['mask']['state'] = 'seg_end'
            
            # Force preserved frames adjacent to this punch-in to be manual anchors
            # to avoid diagonal distortions between the old pass and the new pass.
            start_f = seg[0]['frame']
            if start_f - 1 in frames_data:
                for m in frames_data[start_f - 1]['masks']:
                    if m['id'] == tid:
                        m['source'] = 'manual'

    out_lines = [json.dumps(frames_data[f]) for f in sorted(frames_data.keys())]

    with open(jsonl_path, 'w', encoding='utf-8') as f:
        for line in out_lines:
            f.write(line + '\n')
    print(f"Wrote JSONL: {jsonl_path}")
    return True

def pd_isna(val):
    if val is None: return True
    if isinstance(val, str) and val.strip() == '': return True
    return False

def process_passes_file(passes_file: Path):
    with open(passes_file, 'r', encoding='utf-8') as f:
        passes = json.load(f)

    if not passes:
        print(f"No passes found in file: {passes_file}")
        return

    # Infer from the first pass output_video
    first_vid = passes[0].get('output_video', '')
    base = os.path.basename(first_vid)
    if '_tracked_' in base:
        video_name = base.split('_tracked_')[0]
    elif '_manual_blur' in base:
        video_name = base.split('_manual_blur')[0]
    else:
        video_name = os.path.splitext(base)[0]
    
    # In legacy tool, ranges were added to filename e.g. l5_20__0-1033s or _0-7s
    # Let's clean up `__0-1033s` or `_0-1033s` if it exists, to make a clean video_name.
    original_video_name = re.sub(r'_+?\d+-\d+s$', '', video_name)
    
    folder_name = passes_file.parent.name
    new_video_name = f"{folder_name}_{original_video_name}"
    
    print(f"\n--- Processing video: {original_video_name} as {new_video_name} ---")
    config.ensure_dirs()

    # Find and copy raw video if it's next to the passes.json
    legacy_dir = passes_file.parent
    raw_video = None
    
    # Look for any mp4 in the same directory that isn't a tracked/manual output,
    # but MUST start with the original_video_name to avoid grabbing other videos in the same dir.
    base_prefix = original_video_name.rstrip("_")
    for cand in legacy_dir.glob(f"{base_prefix}*.mp4"):
        if "_tracked_" not in cand.name and "_manual_blur" not in cand.name and "_post_" not in cand.name:
            raw_video = cand
            if "_normalized" in cand.name:
                break # Prefer normalized since legacy tracking was run on it
                
    if raw_video:
        target_raw = config.RAW_DIR / f"{new_video_name}.mp4"
        print(f"Copying RAW video: {raw_video} -> {target_raw}")
        shutil.copy2(raw_video, target_raw)
    else:
        print(f"Warning: Could not find RAW video automatically in {legacy_dir}. Skipping this video.")
        return True

    highest_pass = 0
    for i, p in enumerate(passes):
        legacy_csv = p.get('output_csv')
        legacy_vid = p.get('output_video')
        new_pass_idx = i  # 0, 1, 2...
        
        if legacy_csv:
            csv_path = legacy_dir / os.path.basename(legacy_csv)
            jsonl_dst = session_manager.jsonl_path(new_video_name, new_pass_idx)
            prev_jsonl = session_manager.jsonl_path(new_video_name, new_pass_idx - 1) if new_pass_idx > 0 else None
            success = process_csv(str(csv_path), jsonl_dst, prev_jsonl)
            if success:
                highest_pass = new_pass_idx
            else:
                print(f"Aborting migration for {new_video_name} due to corrupted pass {new_pass_idx}.")
                return False

        if legacy_vid:
            vid_path = legacy_dir / os.path.basename(legacy_vid)
            if vid_path.exists():
                target_vid = config.OUTPUT_DIR / f"{new_video_name}_masked_{new_pass_idx}.mp4"
                print(f"Copying masked video: {vid_path} -> {target_vid}")
                shutil.copy2(vid_path, target_vid)

    # Set state
    if highest_pass == 0:
        target_state = "TRACKED"
    else:
        target_state = f"MANUAL_{highest_pass}"
        
    print(f"Setting session state for {new_video_name} to {target_state}")
    session_manager.set_state(new_video_name, target_state)
    print(f"Migration complete for {new_video_name}!\n")
    return True

def main():
    if len(sys.argv) < 2:
        print("Usage: python csv_to_jsonl.py <path_to_directory>")
        sys.exit(1)

    target_path = Path(sys.argv[1])
    if not target_path.exists():
        print(f"Error: path not found: {target_path}")
        sys.exit(1)

    if target_path.is_file() and target_path.name.endswith("_passes.json"):
        process_passes_file(target_path)
    elif target_path.is_dir():
        found = list(target_path.rglob("*_passes.json"))
        if not found:
            print(f"No _passes.json files found in {target_path} or its subdirectories.")
            sys.exit(0)
            
        # Deduplicate: if there are multiple passes.json for the same video in a folder,
        # we only want to process the one that has the most passes recorded.
        best_files = {} # (parent_dir, base_first_vid) -> (passes_file, num_passes)
        for pf in found:
            try:
                with open(pf, 'r', encoding='utf-8') as f:
                    passes_data = json.load(f)
                if passes_data:
                    base_vid = os.path.basename(passes_data[0].get('output_video', ''))
                    key = (pf.parent, base_vid)
                    if key not in best_files or len(passes_data) > best_files[key][1]:
                        best_files[key] = (pf, len(passes_data))
            except Exception:
                pass
                
        files_to_process = [v[0] for v in best_files.values()]
        print(f"Found {len(files_to_process)} unique video session(s). Processing...")
        skipped_videos = []
        for pf in files_to_process:
            if not process_passes_file(pf):
                skipped_videos.append(str(pf.parent))
                
        if skipped_videos:
            print("\n" + "="*50)
            print("WARNING: The following videos were SKIPPED because their CSVs")
            print("were too corrupted (more than 5 consecutive frames with missing IDs):")
            for sv in skipped_videos:
                print(f" - {sv}")
            print("="*50 + "\n")
    else:
        print("Error: Provide a _passes.json file or a directory containing them.")
        sys.exit(1)

if __name__ == "__main__":
    main()
