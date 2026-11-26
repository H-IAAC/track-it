import re
configs={}
configs['line_chekpoint_color']='#5d7f4c'

def update_shapes(df_protocol, min_x=None, max_x=None, min_y=0, max_y=10):
    # Create and filter shapes based on the x and y ranges, or return all shapes if no range is specified
    updated_shapes = [
        dict(
            type='line',
            x0=row['timestamp'],
            x1=row['timestamp'],
            y0=0,
            y1=1,
            yref='paper',
            line=dict(color=configs['line_chekpoint_color'], width=2, dash='dash'),
            name=generate_label(row)  # Add a name to the shape based on timestamp and other information
        )
        for _, row in df_protocol.iterrows()
        if (min_x is None or row['timestamp'] >= min_x) and (max_x is None or row['timestamp'] <= max_x)
        # The above condition ensures that if min_x or max_x is not provided, all shapes are included
    ]
    return updated_shapes

def update_annotation(df_protocol,min_x=None, max_x=None, min_y=0, max_y=10):
    # Vertical annotations df_protocol['change_point_name'].unique() for each green line
    annotations = [
        dict(
            x=row['timestamp'],
            y=0.5,  # Vertically align to the middle of the line
            xref='x',
            yref='paper',
            text=generate_label(row),
            showarrow=False,
            xshift=5,
            xanchor='left',
            font=dict(size=14, color=configs['line_chekpoint_color']),
            textangle=-90  # Rotate the text so it's vertical
        )
        for _, row in df_protocol.iterrows()
        if (min_x is None or row['timestamp'] >= min_x) and (max_x is None or row['timestamp'] <= max_x)
    ]
    return annotations

def update__line_timestamp(timestamp,y0,y1):
    return [dict(
                type='line',
                x0=timestamp,
                x1=timestamp,
                y0=0,
                y1=1,
                xref='x',
                yref='paper',
                line=dict(color='#ff9d1c', width=4, dash='dash'),
                name='timestamp_id'
            )]


def update_line_color(matching_line,updated_figure):
    name=get_name(matching_line['left_label'],
                            matching_line['change_point_name'],
                            matching_line['change_point_time'],"x")
    shapes=updated_figure['layout']['shapes']
    annotations=[]#updated_figure['layout']['annotations']
    #shapes[index]=dict(color=configs['line_chekpoint_select_color'],dash='dash')
    for shape in shapes:
        
        if shape.get('name') == name:
            if(matching_line['timestamp']!= shape.get('x0')):
                # Update the shape's color
                shape['line'] = dict(color=configs['line_chekpoint_select_color'],dash='dash')
                line_found = True
                for annotation in annotations:
                    if annotation['text'] == name:
                        # Update the annotation's x position
                        annotation['x'] = shape['x0']+1  # Assuming x0 is the new x position of the shape
                        annotation['font'] = dict(color=configs['line_chekpoint_select_color'])
                        break


        # Update the shapes in the figure's layout
    updated_figure['layout']['shapes'] = shapes
    updated_figure['layout']['annotations'] =annotations
    
    

    return updated_figure

def get_name(left_label,change_point_name,change_point_time,sensor_ref):
        name = f"{left_label}__{change_point_name}__{change_point_time}__{sensor_ref}"
        return name

def generate_label(row):
    return f"{row['left_label']}__{row['change_point_name']}__{row['change_point_time']}__{row['sensor_ref']}"

def get_columns_df_protocol():
    return ["timestamp","left_label","change_point_name","change_point_time","sensor_ref"]

def extract_index_from_key(key):
    match = re.search(r'shapes\[(\d+)\]', key)
    if match:
        return int(match.group(1))
    return None

import pandas as pd
import os

def save_and_resequence_protocol(df_protocol, protocol_file_name, is_compare_mode=False):
    """
    Sorts the dataframe by timestamp, resequences the change_point_name,
    and saves it to the CSV file.
    """
    if df_protocol is None or df_protocol.empty:
        return df_protocol
        
    # Sort
    if not is_compare_mode:
        df_protocol = df_protocol.sort_values(by='timestamp').reset_index(drop=True)
        # Resequence
        df_protocol['change_point_name'] = [f'change_point_{i+1}' for i in range(len(df_protocol))]
    else:
        df_protocol = df_protocol.sort_values(by=['sensor_ref', 'timestamp']).reset_index(drop=True)
        # Resequence per sensor_ref
        df_protocol['change_point_name'] = df_protocol.groupby('sensor_ref').cumcount() + 1
        df_protocol['change_point_name'] = 'change_point_' + df_protocol['change_point_name'].astype(str)

    # Save to CSV
    if protocol_file_name:
        try:
            # Ensure index=False to not write row numbers
            df_protocol.to_csv(protocol_file_name, index=False)
            
            # Dual-Mode: Update session_manifest.json if it exists
            folder_path = os.path.dirname(protocol_file_name)
            manifest_path = os.path.join(folder_path, "session_manifest.json")
            if not os.path.exists(manifest_path):
                manifest_path = os.path.join(folder_path, "..", "session_manifest.json")
                
            if os.path.exists(manifest_path):
                import json
                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)
                
                # We can store a list of annotation files in the manifest
                artifacts = manifest.setdefault('artifacts', {})
                artifacts['annotations_dir'] = 'annotations'
                
                ann_list = artifacts.get('annotation_files', [])
                ann_rel_path = f"annotations/{os.path.basename(protocol_file_name)}"
                if ann_rel_path not in ann_list:
                    ann_list.append(ann_rel_path)
                artifacts['annotation_files'] = ann_list
                
                # Also update pipeline_status to annotated = true
                if 'pipeline_status' in manifest:
                    manifest['pipeline_status']['annotated'] = True
                
                with open(manifest_path, 'w') as f:
                    json.dump(manifest, f, indent=4)
                    
        except Exception as e:
            print(f"Error saving protocol to {protocol_file_name}: {e}")
            
    return df_protocol