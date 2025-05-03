#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bolt Congestion Control Visualization Script.
This script reads the output files from the NS-3 simulation and creates visualizations
of congestion window sizes and queue lengths over time, marking flow start and end times.
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import argparse
from pathlib import Path
import re

# 确保这个函数被保留 - 这正是你原始代码里的
def extract_cc_mode(filename):
    """
    Extract the congestion control mode from the filename.
    Look for _DEFAULT_ or _SWIFT_ in the filename.
    """
    filename = filename.upper()
    if "_DEFAULT_" in filename:
        return "DEFAULT"
    elif "_SWIFT_" in filename:
        return "SWIFT"
    
    # If no match, try to find other CC mode identifiers
    cc_modes = ["DEFAULT", "SWIFT", "BOLT", "TCP"]
    for mode in cc_modes:
        if f"_{mode}_" in filename or filename.endswith(f"_{mode}"):
            return mode
    
    # Default fallback
    return "DEFAULT"


def read_flow_stats(filename):
    """
    Read the flow statistics file (.log) containing congestion window sizes.
    
    Format: timestamp source_ip:port dest_ip:port tx_msg_id cwnd rtt
    
    Returns: DataFrame with timestamp, source, destination, cwnd, rtt
    """
    if not os.path.exists(filename):
        print(f"Error: File {filename} does not exist")
        return None
    
    # Read the file
    data = []
    with open(filename, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 6:
                # Extract timestamp, source, destination, msgId, cwnd, rtt
                timestamp = int(parts[0]) / 1e9  # Convert ns to seconds
                source = parts[1]
                dest = parts[2]
                msg_id = parts[3]
                cwnd = int(parts[4])
                rtt = int(parts[5])
                
                data.append({
                    'timestamp': timestamp,
                    'source': source,
                    'destination': dest,
                    'msg_id': msg_id,
                    'cwnd': cwnd,
                    'rtt': rtt
                })
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    return df

def read_message_traces(filename):
    """
    Read the message trace file (.tr) containing message start and end events.
    
    Format: 
    + timestamp size source:port dest:port msg_id    (message start)
    - timestamp size source:port dest:port msg_id    (message end)
    
    Returns: DataFrame with message start and end times
    """
    if not os.path.exists(filename):
        print(f"Error: File {filename} does not exist")
        return None, None
    
    # Read the file
    starts = []
    ends = []
    
    with open(filename, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 6:
                event_type = parts[0]  # + for start, - for end
                timestamp = int(parts[1]) / 1e9  # Convert ns to seconds
                size = int(parts[2])
                source = parts[3]
                dest = parts[4]
                msg_id = parts[5]
                
                data_point = {
                    'timestamp': timestamp,
                    'size': size,
                    'source': source,
                    'destination': dest,
                    'msg_id': msg_id
                }
                
                if event_type == '+':
                    starts.append(data_point)
                elif event_type == '-':
                    ends.append(data_point)
    
    # Create DataFrames
    starts_df = pd.DataFrame(starts) if starts else None
    ends_df = pd.DataFrame(ends) if ends else None
    
    return starts_df, ends_df

def read_queue_lengths(filename):
    """
    Read the queue length file (.qlen) containing switch queue sizes.
    
    Format: que timestamp switch_id queue_size
    
    Returns: DataFrame with timestamp, switch_id, queue_size
    """
    if not os.path.exists(filename):
        print(f"Error: File {filename} does not exist")
        return None
    
    # Read the file
    data = []
    with open(filename, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 4 and parts[0] == 'que':
                # Extract timestamp, switch_id, queue_size
                timestamp = int(parts[1]) / 1e9  # Convert ns to seconds
                switch_id = parts[2]
                queue_size = int(parts[3])
                
                data.append({
                    'timestamp': timestamp,
                    'switch_id': switch_id,
                    'queue_size': queue_size
                })
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    return df

def get_global_start_time(dfs):
    """
    Find the minimum timestamp across all DataFrames to use as a global start time.
    """
    min_timestamps = []
    for df in dfs:
        if df is not None and not df.empty and 'timestamp' in df.columns:
            min_timestamps.append(df['timestamp'].min())
    
    if min_timestamps:
        return min(min_timestamps)
    return 0

def normalize_timestamps(dfs, start_time):
    """
    Normalize timestamps in all DataFrames by subtracting the global start time.
    """
    normalized_dfs = []
    for df in dfs:
        if df is not None and not df.empty and 'timestamp' in df.columns:
            df_copy = df.copy()
            df_copy['elapsed_time'] = df_copy['timestamp'] - start_time
            normalized_dfs.append(df_copy)
        else:
            normalized_dfs.append(df)
    
    return normalized_dfs

def get_flow_timings(msg_starts, msg_ends, flow_stats):
    """
    Calculate the precise start and end times for each flow based on message traces 
    and flow statistics.
    
    Returns a dictionary with flow info including start and end times.
    """
    if msg_starts is None or msg_starts.empty:
        return {}
    
    flow_info = {}
    
    # Define flows by unique source-destination pairs
    flows = set()
    
    # Add flows from message starts
    if msg_starts is not None and not msg_starts.empty:
        for _, row in msg_starts.iterrows():
            flow_key = (row['source'], row['destination'])
            flows.add(flow_key)
    
    # Add flows from flow statistics
    if flow_stats is not None and not flow_stats.empty:
        for _, row in flow_stats.iterrows():
            flow_key = (row['source'], row['destination'])
            flows.add(flow_key)
    
    # Initialize flow information
    for source, dest in flows:
        flow_key = f"{source}→{dest}"
        flow_info[flow_key] = {'start_time': None, 'end_time': None}
    
    # Get precise start times from message starts
    if msg_starts is not None and not msg_starts.empty:
        for flow_key_tuple in flows:
            source, dest = flow_key_tuple
            flow_key = f"{source}→{dest}"
            
            # Get messages for this flow
            flow_msgs = msg_starts[(msg_starts['source'] == source) & 
                                   (msg_starts['destination'] == dest)]
            
            if not flow_msgs.empty:
                first_msg_time = flow_msgs['elapsed_time'].min()
                flow_info[flow_key]['start_time'] = first_msg_time
    
    # Get precise end times from message ends
    if msg_ends is not None and not msg_ends.empty:
        for flow_key_tuple in flows:
            source, dest = flow_key_tuple
            flow_key = f"{source}→{dest}"
            
            # Get messages for this flow
            flow_msgs = msg_ends[(msg_ends['source'] == source) & 
                                 (msg_ends['destination'] == dest)]
            
            if not flow_msgs.empty:
                last_msg_time = flow_msgs['elapsed_time'].max()
                flow_info[flow_key]['end_time'] = last_msg_time
    
    # If we don't have end times, try to get them from flow statistics
    if flow_stats is not None and not flow_stats.empty:
        for flow_key_tuple in flows:
            source, dest = flow_key_tuple
            flow_key = f"{source}→{dest}"
            
            if flow_info[flow_key]['end_time'] is None:
                # Get stats for this flow
                flow_data = flow_stats[(flow_stats['source'] == source) & 
                                       (flow_stats['destination'] == dest)]
                
                if not flow_data.empty:
                    # Use the last timestamp where cwnd is non-zero
                    non_zero_cwnd = flow_data[flow_data['cwnd'] > 0]
                    if not non_zero_cwnd.empty:
                        last_active_time = non_zero_cwnd['elapsed_time'].max()
                        flow_info[flow_key]['end_time'] = last_active_time
    
    return flow_info
def plot_cwnd(flow_stats, flow_timings, output_dir, cc_mode, start_time=None, end_time=None):
    """
    Plot congestion window sizes over time for all flows,
    marking the start and end times of each flow.
    
    Args:
        flow_stats: DataFrame containing flow statistics
        flow_timings: Dictionary with flow timing information
        output_dir: Directory to save the output plot
        cc_mode: Congestion control mode name
        start_time: Optional manual start time for x-axis (seconds)
        end_time: Optional manual end time for x-axis (seconds)
    """
    if flow_stats is None or flow_stats.empty:
        print("No flow statistics data to plot")
        return
    
    # Check if we have multiple flows
    flows = flow_stats.groupby(['source', 'destination'])
    num_flows = len(flows)
    
    print(f"Found {num_flows} unique flows:")
    for (source, dest), _ in flows:
        print(f"  {source} → {dest}")
    
    plt.figure(figsize=(12, 6))
    
    # Use a colormap for different flows
    colors = plt.cm.tab10(np.linspace(0, 1, num_flows))
    
    # Plot each flow's congestion window with thinner lines
    for i, ((source, dest), group) in enumerate(flows):
        flow_key = f"{source}→{dest}"
        label = f"{flow_key}"
        
        # Add timing info to label if available
        if flow_key in flow_timings:
            flow_start_time = flow_timings[flow_key]['start_time']
            flow_end_time = flow_timings[flow_key]['end_time']
            
            if flow_start_time is not None and flow_end_time is not None:
                duration = flow_end_time - flow_start_time
                label = f"{flow_key} (Start: {flow_start_time:.6f}s, End: {flow_end_time:.6f}s, Duration: {duration:.6f}s)"
            
            # Draw vertical lines for start and end times (thinner)
            if flow_start_time is not None:
                plt.axvline(x=flow_start_time, color=colors[i], linestyle='--', alpha=0.5, linewidth=0.8)
            
            if flow_end_time is not None:
                plt.axvline(x=flow_end_time, color=colors[i], linestyle=':', alpha=0.5, linewidth=0.8)
        
        # Plot cwnd over time with thinner lines
        plt.plot(group['elapsed_time'], group['cwnd'] / 1000,  # Convert to KB
                 label=label, 
                 color=colors[i], linewidth=1.0)
    
    plt.xlabel('Time (seconds)')
    plt.ylabel('Congestion Window Size (KB)')
    plt.title(f'Congestion Window Size Over Time\nAlgorithm: {cc_mode}')
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    # Set x-axis limits based on provided arguments
    if start_time is not None or end_time is not None:
        xlim_args = []
        if start_time is not None:
            xlim_args.append(start_time)
        else:
            xlim_args.append(plt.xlim()[0])  # Use current lower limit
            
        if end_time is not None:
            xlim_args.append(end_time)
        else:
            xlim_args.append(plt.xlim()[1])  # Use current upper limit
            
        plt.xlim(*xlim_args)
    
    # Save the figure
    plt.tight_layout()
    out_file = os.path.join(output_dir, f'congestion_window_{cc_mode}.png')
    plt.savefig(out_file, dpi=300)
    print(f"Saved congestion window plot to {out_file}")
    
    # Also create a version with log y-axis scale
    plt.yscale('log')
    plt.title(f'Congestion Window Size Over Time\nAlgorithm: {cc_mode} (Log Scale)')
    log_out_file = os.path.join(output_dir, f'congestion_window_log_{cc_mode}.png')
    plt.savefig(log_out_file, dpi=300)
    print(f"Saved log-scale congestion window plot to {log_out_file}")
    
    plt.close()

def plot_rtt(flow_stats, flow_timings, output_dir, cc_mode, start_time=None, end_time=None):
    """
    Plot RTT over time for all flows,
    marking the start and end times of each flow.
    
    Args:
        flow_stats: DataFrame containing flow statistics
        flow_timings: Dictionary with flow timing information
        output_dir: Directory to save the output plot
        cc_mode: Congestion control mode name
        start_time: Optional manual start time for x-axis (seconds)
        end_time: Optional manual end time for x-axis (seconds)
    """
    if flow_stats is None or flow_stats.empty:
        print("No flow statistics data to plot")
        return
    
    plt.figure(figsize=(12, 6))
    
    # Identify unique flows
    flows = flow_stats.groupby(['source', 'destination'])
    
    # Use a colormap for different flows
    colors = plt.cm.tab10(np.linspace(0, 1, len(flows)))
    
    # Plot each flow's RTT with thinner lines
    for i, ((source, dest), group) in enumerate(flows):
        flow_key = f"{source}→{dest}"
        label = f"{flow_key}"
        
        # Add timing info to label if available
        if flow_key in flow_timings:
            flow_start_time = flow_timings[flow_key]['start_time']
            flow_end_time = flow_timings[flow_key]['end_time']
            
            if flow_start_time is not None and flow_end_time is not None:
                duration = flow_end_time - flow_start_time
                label = f"{flow_key} (Start: {flow_start_time:.6f}s, End: {flow_end_time:.6f}s, Duration: {duration:.6f}s)"
            
            # Draw vertical lines for start and end times (thinner)
            if flow_start_time is not None:
                plt.axvline(x=flow_start_time, color=colors[i], linestyle='--', alpha=0.5, linewidth=0.8)
            
            if flow_end_time is not None:
                plt.axvline(x=flow_end_time, color=colors[i], linestyle=':', alpha=0.5, linewidth=0.8)
        
        # Plot RTT over time with thinner lines
        plt.plot(group['elapsed_time'], group['rtt'] / 1000,  # Convert to µs
                 label=label, 
                 color=colors[i], linewidth=1.0)
    
    plt.xlabel('Time (seconds)')
    plt.ylabel('RTT (µs)')
    plt.title(f'Round Trip Time Over Time\nAlgorithm: {cc_mode}')
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    # Set x-axis limits based on provided arguments
    if start_time is not None or end_time is not None:
        xlim_args = []
        if start_time is not None:
            xlim_args.append(start_time)
        else:
            xlim_args.append(plt.xlim()[0])  # Use current lower limit
            
        if end_time is not None:
            xlim_args.append(end_time)
        else:
            xlim_args.append(plt.xlim()[1])  # Use current upper limit
            
        plt.xlim(*xlim_args)
    
    # Save the figure
    plt.tight_layout()
    out_file = os.path.join(output_dir, f'rtt_{cc_mode}.png')
    plt.savefig(out_file, dpi=300)
    print(f"Saved RTT plot to {out_file}")
    plt.close()

def plot_queue_lengths(queue_data, flow_timings, output_dir, cc_mode, start_time=None, end_time=None):
    """
    Plot queue lengths over time for each switch,
    marking the start and end times of each flow.
    
    Args:
        queue_data: DataFrame containing queue length data
        flow_timings: Dictionary with flow timing information
        output_dir: Directory to save the output plot
        cc_mode: Congestion control mode name
        start_time: Optional manual start time for x-axis (seconds)
        end_time: Optional manual end time for x-axis (seconds)
    """
    if queue_data is None or queue_data.empty:
        print("No queue length data to plot")
        return
    
    plt.figure(figsize=(12, 6))
    
    # Identify unique switches
    switches = queue_data['switch_id'].unique()
    
    # Use a colormap for different switches
    switch_colors = plt.cm.tab10(np.linspace(0, 1, len(switches)))
    
    # Plot queue lengths for each switch with thinner lines
    for i, switch in enumerate(switches):
        switch_data = queue_data[queue_data['switch_id'] == switch]
        
        # Plot queue length over time with thinner lines
        plt.plot(switch_data['elapsed_time'], switch_data['queue_size'] / 1000,  # Convert to KB
                 label=f"Switch {switch}", 
                 color=switch_colors[i], linewidth=1.0)
    
    # Generate different colors for flow markers
    flow_colors = plt.cm.Set2(np.linspace(0, 1, len(flow_timings)))
    
    # Add vertical lines for flow start and end times (thinner)
    for i, (flow_key, timing) in enumerate(flow_timings.items()):
        flow_start_time = timing['start_time']
        flow_end_time = timing['end_time']
        
        if flow_start_time is not None:
            plt.axvline(x=flow_start_time, color=flow_colors[i], linestyle='--', alpha=0.5,
                        label=f"{flow_key} start", linewidth=0.8)
        
        if flow_end_time is not None:
            plt.axvline(x=flow_end_time, color=flow_colors[i], linestyle=':', alpha=0.5,
                        label=f"{flow_key} end", linewidth=0.8)
    
    plt.xlabel('Time (seconds)')
    plt.ylabel('Queue Size (KB)')
    plt.title(f'Switch Queue Size Over Time\nAlgorithm: {cc_mode}')
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    # Set x-axis limits based on provided arguments
    if start_time is not None or end_time is not None:
        xlim_args = []
        if start_time is not None:
            xlim_args.append(start_time)
        else:
            xlim_args.append(plt.xlim()[0])  # Use current lower limit
            
        if end_time is not None:
            xlim_args.append(end_time)
        else:
            xlim_args.append(plt.xlim()[1])  # Use current upper limit
            
        plt.xlim(*xlim_args)
    
    # Save the figure
    plt.tight_layout()
    out_file = os.path.join(output_dir, f'queue_length_{cc_mode}.png')
    plt.savefig(out_file, dpi=300)
    print(f"Saved queue length plot to {out_file}")
    plt.close()

def read_pru_tokens(filename):
    """
    Read the PRU token file (.pru) containing PRU token changes.
    
    Format: pru timestamp switch_id token_count
    
    Returns: DataFrame with timestamp, switch_id, token_count
    """
    if not os.path.exists(filename):
        print(f"Error: File {filename} does not exist")
        return None
    
    # Read the file
    data = []
    with open(filename, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 4 and parts[0] == 'pru':
                # Extract timestamp, switch_id, token_count
                timestamp = int(parts[1]) / 1e9  # Convert ns to seconds
                switch_id = parts[2]
                token_count = int(parts[3])
                
                data.append({
                    'timestamp': timestamp,
                    'switch_id': switch_id,
                    'token_count': token_count
                })
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    return df

def plot_pru_tokens(pru_data, flow_timings, output_dir, cc_mode, start_time=None, end_time=None):
    """
    Plot PRU tokens over time for each switch,
    marking the start and end times of each flow.
    
    Args:
        pru_data: DataFrame containing PRU token data
        flow_timings: Dictionary with flow timing information
        output_dir: Directory to save the output plot
        cc_mode: Congestion control mode name
        start_time: Optional manual start time for x-axis (seconds)
        end_time: Optional manual end time for x-axis (seconds)
    """
    if pru_data is None or pru_data.empty:
        print("No PRU token data to plot")
        return
    
    plt.figure(figsize=(12, 6))
    
    # Identify unique switches
    switches = pru_data['switch_id'].unique()
    
    # Use a colormap for different switches
    switch_colors = plt.cm.tab10(np.linspace(0, 1, len(switches)))
    
    # Plot PRU tokens for each switch
    for i, switch in enumerate(switches):
        if switch != "S1-S2":continue
        switch_data = pru_data[pru_data['switch_id'] == switch]
        
        # Plot PRU tokens over time
        plt.plot(switch_data['elapsed_time'], switch_data['token_count'],
                 label=f"Switch {switch}", 
                 color=switch_colors[i], linewidth=1.0)
    
    # Generate different colors for flow markers
    flow_colors = plt.cm.Set2(np.linspace(0, 1, len(flow_timings)))
    
    # Add vertical lines for flow start and end times
    for i, (flow_key, timing) in enumerate(flow_timings.items()):
        flow_start_time = timing['start_time']
        flow_end_time = timing['end_time']
        
        if flow_start_time is not None:
            plt.axvline(x=flow_start_time, color=flow_colors[i], linestyle='--', alpha=0.5,
                        label=f"{flow_key} start", linewidth=0.8)
        
        if flow_end_time is not None:
            plt.axvline(x=flow_end_time, color=flow_colors[i], linestyle=':', alpha=0.5,
                        label=f"{flow_key} end", linewidth=0.8)
    
    plt.xlabel('Time (seconds)')
    plt.ylabel('PRU Token Count')
    plt.title(f'PRU Token Count Over Time\nAlgorithm: {cc_mode}')
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    # Set x-axis limits based on provided arguments
    if start_time is not None or end_time is not None:
        xlim_args = []
        if start_time is not None:
            xlim_args.append(start_time)
        else:
            xlim_args.append(plt.xlim()[0])  # Use current lower limit
            
        if end_time is not None:
            xlim_args.append(end_time)
        else:
            xlim_args.append(plt.xlim()[1])  # Use current upper limit
            
        plt.xlim(*xlim_args)
    
    # Save the figure
    plt.tight_layout()
    out_file = os.path.join(output_dir, f'pru_tokens_{cc_mode}.png')
    plt.savefig(out_file, dpi=300)
    print(f"Saved PRU tokens plot to {out_file}")
    plt.close()

def create_plots(data_file=None, base_dir='outputs', output_dir='plots', file_prefix='bolt-simple-dumbbell', 
                 start_time=None, end_time=None):
    """
    Main function to create all plots.
    
    Args:
        data_file: Optional direct path to data file (without extension)
        base_dir: Directory containing the simulation output files (used if data_file not provided)
        output_dir: Directory to save the generated plots
        file_prefix: Prefix of the simulation output files (used if data_file not provided)
        start_time: Optional manual start time for x-axis (seconds)
        end_time: Optional manual end time for x-axis (seconds)
    """
    # Create output directory if it doesn't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Determine file paths
    if data_file:
        flow_stats_file = f"{data_file}.log"
        queue_file = f"{data_file}.qlen"
        msg_trace_file = f"{data_file}.tr"
        pru_file = f"{data_file}.pru"  # 添加PRU文件
        cc_mode = extract_cc_mode(data_file)
    else:
        # Find the most recent files that match the pattern
        flow_stats_files = sorted([f for f in os.listdir(base_dir) if f.startswith(file_prefix) and f.endswith('.log')])
        queue_files = sorted([f for f in os.listdir(base_dir) if f.startswith(file_prefix) and f.endswith('.qlen')])
        msg_trace_files = sorted([f for f in os.listdir(base_dir) if f.startswith(file_prefix) and f.endswith('.tr')])
        pru_files = sorted([f for f in os.listdir(base_dir) if f.startswith(file_prefix) and f.endswith('.pru')])
        
        if not flow_stats_files:
            print(f"No flow statistics files found in {base_dir} with prefix {file_prefix}")
            return
        
        # Get the most recent files
        flow_stats_file = os.path.join(base_dir, flow_stats_files[-1])
        queue_file = os.path.join(base_dir, queue_files[-1]) if queue_files else None
        msg_trace_file = os.path.join(base_dir, msg_trace_files[-1]) if msg_trace_files else None
        pru_file = os.path.join(base_dir, pru_files[-1]) if pru_files else None
        cc_mode = extract_cc_mode(flow_stats_files[-1])
    
    print(f"Detected congestion control mode: {cc_mode}")
    print(f"Reading flow statistics from {flow_stats_file}")
    flow_stats = read_flow_stats(flow_stats_file)
    
    print(f"Reading message traces from {msg_trace_file}")
    msg_starts, msg_ends = read_message_traces(msg_trace_file)
    
    print(f"Reading queue lengths from {queue_file}")
    queue_data = read_queue_lengths(queue_file)
    
    print(f"Reading PRU token data from {pru_file}")
    pru_data = read_pru_tokens(pru_file) if pru_file else None
    
    # Normalize timestamps for consistent timing across all data sources
    all_dfs = [flow_stats, msg_starts, msg_ends, queue_data, pru_data]
    global_start_time = get_global_start_time(all_dfs)
    flow_stats, msg_starts, msg_ends, queue_data, pru_data = normalize_timestamps(all_dfs, global_start_time)
    
    # Get precise flow timings
    flow_timings = get_flow_timings(msg_starts, msg_ends, flow_stats)
    
    # Print the flow timings for debugging
    print("Flow timings:")
    for flow_key, timing in flow_timings.items():
        print(f"  {flow_key}: Start={timing['start_time']:.9f}s, End={timing['end_time']:.9f}s")
    
    # Create plots with all flows on single graphs
    plot_cwnd(flow_stats, flow_timings, output_dir, cc_mode, start_time, end_time)
    plot_rtt(flow_stats, flow_timings, output_dir, cc_mode, start_time, end_time)
    plot_queue_lengths(queue_data, flow_timings, output_dir, cc_mode, start_time, end_time)
    
    # Plot PRU tokens if data is available
    if pru_data is not None:
        plot_pru_tokens(pru_data, flow_timings, output_dir, cc_mode, start_time, end_time)
    
    print("Plotting complete!")

# 在文件顶部定义这些变量（替换原来的命令行解析部分）
# 可以根据需要修改这些值
DATA_FILE = None              # 数据文件路径（不含扩展名）
BASE_DIR = 'outputs'          # 包含模拟输出文件的目录
OUTPUT_DIR = 'plots'          # 保存生成图表的目录
FILE_PREFIX = 'bolt-simple-dumbbell'  # 模拟输出文件的前缀
START_TIME = None             # 图表x轴的起始时间（秒）
END_TIME = None               # 图表x轴的结束时间（秒）

# 将主程序部分修改为使用这些变量
if __name__ == "__main__":
    # 你可以在这里根据需要修改上面的变量值
    # 例如：
    #START_TIME = 0.0046
    #END_TIME = 0.0048
    
    create_plots(
        DATA_FILE,
        BASE_DIR,
        OUTPUT_DIR,
        FILE_PREFIX,
        START_TIME,
        END_TIME
    )