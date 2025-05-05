#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bolt Fairness Experiment Visualization Script

这个脚本从Bolt公平性实验中读取输出文件，并创建可视化图表来分析拥塞窗口大小、
队列长度和PRU令牌随时间的变化，并清晰标记流的开始和结束时间。
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import sys

# =============== 用户配置参数（您可以在这里直接更改参数）===============
# 数据文件路径（不含扩展名）。如果设置为None，则使用base_dir中最近的文件
DATA_FILE = None

# 包含输出文件的目录
BASE_DIR = '../outputs/bolt-fairness'

# 保存生成图表的目录
OUTPUT_DIR = '../plots'

# 模拟指数（如果设置了这个值，将查找具有此指数的文件）
SIM_IDX = None

# 图表X轴的时间范围（单位：秒）
START_TIME = None  # 开始时间，例如1.0
END_TIME = None    # 结束时间，例如1.05

# 流参数
NEW_FLOW_TIME = 0.002  # 新流加入/离开的时间间隔
N_FLOWS = 2           # 拓扑中的流数量
# ====================================================================

def extract_cc_mode(filename):
    """
    从文件名中提取拥塞控制模式。
    查找文件名中的_DEFAULT_或_SWIFT_。
    """
    filename = filename.upper()
    if "_DEFAULT_" in filename:
        return "DEFAULT"
    elif "_SWIFT_" in filename:
        return "SWIFT"
    
    # 如果没有匹配，尝试查找其他CC模式标识符
    cc_modes = ["DEFAULT", "SWIFT", "BOLT", "TCP"]
    for mode in cc_modes:
        if f"_{mode}_" in filename or filename.endswith(f"_{mode}"):
            return mode
    
    # 默认回退
    return "DEFAULT"

def extract_features(filename):
    """
    从文件名中提取启用的功能（BTS, PRU, ABS等）
    """
    features = []
    if "_BTS" in filename:
        features.append("BTS")
    if "_PRU" in filename:
        features.append("PRU")
    if "_ABS" in filename:
        features.append("ABS")
    if "_MSGAGG" in filename:
        features.append("MSG_AGG")
    if "_PERHOP" in filename:
        features.append("PER_HOP")
    
    return features

def read_flow_stats(filename):
    """
    读取流统计文件（.log），包含拥塞窗口大小和RTT。
    
    格式：timestamp source_ip:port dest_ip:port tx_msg_id cwnd rtt
    
    返回：包含timestamp, source, destination, cwnd, rtt的DataFrame
    """
    if not os.path.exists(filename):
        print(f"错误: 文件 {filename} 不存在")
        return None
    
    # 读取文件
    data = []
    with open(filename, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 6:
                # 提取timestamp, source, destination, msgId, cwnd, rtt
                timestamp = int(parts[0]) / 1e9  # 将纳秒转换为秒
                source = parts[1]
                destination = parts[2]
                msg_id = parts[3]
                cwnd = int(parts[4])
                rtt = int(parts[5])
                
                data.append({
                    'timestamp': timestamp,
                    'source': source,
                    'destination': destination,
                    'msg_id': msg_id,
                    'cwnd': cwnd,
                    'rtt': rtt
                })
    
    # 创建DataFrame
    df = pd.DataFrame(data)
    
    return df

def read_queue_lengths(filename):
    """
    读取队列长度文件（.qlen），包含交换机队列大小。
    
    格式：timestamp queue_size
    
    返回：包含timestamp, queue_size的DataFrame
    """
    if not os.path.exists(filename):
        print(f"错误: 文件 {filename} 不存在")
        return None
    
    # 读取文件
    data = []
    with open(filename, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                # 提取timestamp, queue_size
                timestamp = int(parts[0]) / 1e9  # 将纳秒转换为秒
                queue_size = int(parts[1])
                
                data.append({
                    'timestamp': timestamp,
                    'queue_size': queue_size
                })
    
    # 创建DataFrame
    df = pd.DataFrame(data)
    
    return df

def read_throughput(filename):
    """
    读取吞吐量文件（.tpt），包含吞吐量测量。
    
    格式：timestamp bytes_dequeued
    
    返回：包含timestamp, bytes_dequeued的DataFrame
    """
    if not os.path.exists(filename):
        print(f"错误: 文件 {filename} 不存在")
        return None
    
    # 读取文件
    data = []
    with open(filename, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                # 提取timestamp, bytes_dequeued
                timestamp = int(parts[0]) / 1e9  # 将纳秒转换为秒
                bytes_dequeued = int(parts[1])
                
                data.append({
                    'timestamp': timestamp,
                    'bytes_dequeued': bytes_dequeued
                })
    
    # 创建DataFrame
    df = pd.DataFrame(data)
    
    return df

def read_pru_tokens(filename):
    """
    读取PRU令牌文件（.pru），包含PRU令牌变化。
    
    格式：timestamp token_count
    
    返回：包含timestamp, token_count的DataFrame
    """
    if not os.path.exists(filename):
        print(f"错误: 文件 {filename} 不存在")
        return None
    
    # 读取文件
    data = []
    with open(filename, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                # 提取timestamp, token_count
                timestamp = int(parts[0]) / 1e9  # 将纳秒转换为秒
                token_count = int(parts[1])
                
                data.append({
                    'timestamp': timestamp,
                    'token_count': token_count
                })
    
    # 创建DataFrame
    df = pd.DataFrame(data)
    
    return df

def calculate_throughput(tpt_data, window_size=1e-3):
    """
    基于出队字节计算吞吐量。
    
    参数:
        tpt_data: 包含timestamp和bytes_dequeued的DataFrame
        window_size: 计算吞吐量的时间窗口大小（秒）
    
    返回: 包含timestamp和throughput_gbps的DataFrame
    """
    if tpt_data is None or tpt_data.empty:
        return None
    
    # 创建数据副本
    df = tpt_data.copy()
    
    # 按时间戳排序
    df = df.sort_values('timestamp')
    
    # 计算吞吐量
    throughput_data = []
    
    # 使用滑动窗口方法
    for i in range(len(df) - 1):
        current_time = df.iloc[i]['timestamp']
        window_end = current_time + window_size
        
        # 获取时间窗口内的所有记录
        window_data = df[(df['timestamp'] >= current_time) & (df['timestamp'] < window_end)]
        
        if not window_data.empty:
            bytes_in_window = window_data['bytes_dequeued'].sum()
            time_diff = window_size  # 使用固定窗口大小
            
            # 计算Gbps吞吐量
            if time_diff > 0:
                throughput_gbps = (bytes_in_window * 8) / (time_diff * 1e9)
                
                throughput_data.append({
                    'timestamp': current_time,
                    'throughput_gbps': throughput_gbps
                })
    
    return pd.DataFrame(throughput_data)

def get_flow_start_end_times(flow_stats, new_flow_time=0.002, nFlows=2):
    """
    基于模拟参数，计算每个流的开始和结束时间。
    
    参数:
        flow_stats: 包含流统计数据的DataFrame
        new_flow_time: 新流加入/离开的时间间隔
        nFlows: 拓扑中的流数量
    
    返回: 包含流开始和结束时间的字典
    """
    if flow_stats is None or flow_stats.empty:
        return {}
    
    flow_info = {}
    
    # 获取唯一流标识（源-目标对）
    flows = flow_stats.groupby(['source', 'destination'])
    
    # 对于每个流，找到第一个和最后一个时间戳
    for (source, dest), flow_data in flows:
        flow_key = f"{source}→{dest}"
        
        # 获取开始时间（第一个非零cwnd的时间戳）
        start_time = flow_data[flow_data['cwnd'] > 0]['timestamp'].min()
        
        # 获取结束时间（最后一个非零cwnd的时间戳）
        end_time = flow_data[flow_data['cwnd'] > 0]['timestamp'].max()
        
        flow_info[flow_key] = {
            'start_time': start_time,
            'end_time': end_time
        }
    
    return flow_info

def plot_cwnd(flow_stats, flow_timings, output_dir, cc_mode, features, 
              start_time=None, end_time=None):
    """
    绘制所有流的拥塞窗口大小随时间的变化，
    标记每个流的开始和结束时间。
    """
    if flow_stats is None or flow_stats.empty:
        print("没有流统计数据可绘制")
        return
    
    # 检查我们是否有多个流
    flows = flow_stats.groupby(['source', 'destination'])
    num_flows = len(flows)
    
    print(f"发现 {num_flows} 个唯一流:")
    for (source, dest), _ in flows:
        print(f"  {source} → {dest}")
    
    plt.figure(figsize=(12, 6))
    
    # 为不同的流使用颜色映射
    colors = plt.cm.tab10(np.linspace(0, 1, num_flows))
    
    # 绘制每个流的拥塞窗口
    for i, ((source, dest), group) in enumerate(flows):
        flow_key = f"{source}→{dest}"
        label = f"{flow_key}"
        
        # 如果可用，将计时信息添加到标签
        if flow_key in flow_timings:
            flow_start_time = flow_timings[flow_key]['start_time']
            flow_end_time = flow_timings[flow_key]['end_time']
            
            if flow_start_time is not None and flow_end_time is not None:
                duration = flow_end_time - flow_start_time
                label = f"{flow_key} (last time: {duration:.3f}s)"
            
            # 绘制开始和结束时间的垂直线
            if flow_start_time is not None:
                plt.axvline(x=flow_start_time, color=colors[i], linestyle='--', 
                           alpha=0.5, linewidth=0.8)
            
            if flow_end_time is not None:
                plt.axvline(x=flow_end_time, color=colors[i], linestyle=':', 
                           alpha=0.5, linewidth=0.8)
        
        # 绘制cwnd随时间的变化
        plt.plot(group['timestamp'], group['cwnd'] / 1000,  # 转换为KB
                 label=label, 
                 color=colors[i], linewidth=1.5)
    
    plt.xlabel('time(s)')
    plt.ylabel('cwnd(KB)')
    
    # 如果可用，将功能添加到标题
    features_str = ", ".join(features) if features else ""
    title = f'cwnd_time\nal: {cc_mode}'
    if features_str:
        title += f' ({features_str})'
    plt.title(title)
    
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    # 根据提供的参数设置x轴限制
    if start_time is not None or end_time is not None:
        xlim_args = []
        if start_time is not None:
            xlim_args.append(start_time)
        else:
            xlim_args.append(plt.xlim()[0])
            
        if end_time is not None:
            xlim_args.append(end_time)
        else:
            xlim_args.append(plt.xlim()[1])
            
        plt.xlim(*xlim_args)
    
    # 保存图表
    output_filename = f'congestion_window_{cc_mode}'
    if features:
        output_filename += f'_{"_".join(features)}'
    
    plt.tight_layout()
    out_file = os.path.join(output_dir, f'{output_filename}.png')
    plt.savefig(out_file, dpi=300)
    print(f"拥塞窗口图表已保存至 {out_file}")
    
    # 同时创建一个带对数y轴的版本
    plt.yscale('log')
    plt.title(title + " (log)")
    log_out_file = os.path.join(output_dir, f'{output_filename}_log.png')
    plt.savefig(log_out_file, dpi=300)
    print(f"对数刻度拥塞窗口图表已保存至 {log_out_file}")
    
    plt.close()

def plot_rtt(flow_stats, flow_timings, output_dir, cc_mode, features, 
            start_time=None, end_time=None):
    """
    绘制所有流的RTT随时间的变化，
    标记每个流的开始和结束时间。
    """
    if flow_stats is None or flow_stats.empty:
        print("没有流统计数据可绘制")
        return
    
    plt.figure(figsize=(12, 6))
    
    # 检查我们是否有多个流
    flows = flow_stats.groupby(['source', 'destination'])
    num_flows = len(flows)
    
    # 为不同的流使用颜色映射
    colors = plt.cm.tab10(np.linspace(0, 1, num_flows))
    
    # 绘制每个流的RTT
    for i, ((source, dest), group) in enumerate(flows):
        flow_key = f"{source}→{dest}"
        label = f"{flow_key}"
        
        # 如果可用，将计时信息添加到标签
        if flow_key in flow_timings:
            flow_start_time = flow_timings[flow_key]['start_time']
            flow_end_time = flow_timings[flow_key]['end_time']
            
            if flow_start_time is not None and flow_end_time is not None:
                duration = flow_end_time - flow_start_time
                label = f"{flow_key} (持续时间: {duration:.3f}s)"
            
            # 绘制开始和结束时间的垂直线
            if flow_start_time is not None:
                plt.axvline(x=flow_start_time, color=colors[i], linestyle='--', 
                           alpha=0.5, linewidth=0.8)
            
            if flow_end_time is not None:
                plt.axvline(x=flow_end_time, color=colors[i], linestyle=':', 
                           alpha=0.5, linewidth=0.8)
        
        # 绘制RTT随时间的变化，转换为微秒
        plt.plot(group['timestamp'], group['rtt'] / 1000,  # 转换为µs
                 label=label, 
                 color=colors[i], linewidth=1.5)
    
    plt.xlabel('time(s)')
    plt.ylabel('RTT (µs)')
    
    # 如果可用，将功能添加到标题
    features_str = ", ".join(features) if features else ""
    title = f'RTT-time\nalgrithm: {cc_mode}'
    if features_str:
        title += f' ({features_str})'
    plt.title(title)
    
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    # 根据提供的参数设置x轴限制
    if start_time is not None or end_time is not None:
        xlim_args = []
        if start_time is not None:
            xlim_args.append(start_time)
        else:
            xlim_args.append(plt.xlim()[0])
            
        if end_time is not None:
            xlim_args.append(end_time)
        else:
            xlim_args.append(plt.xlim()[1])
            
        plt.xlim(*xlim_args)
    
    # 保存图表
    output_filename = f'rtt_{cc_mode}'
    if features:
        output_filename += f'_{"_".join(features)}'
    
    plt.tight_layout()
    out_file = os.path.join(output_dir, f'{output_filename}.png')
    plt.savefig(out_file, dpi=300)
    print(f"RTT图表已保存至 {out_file}")
    
    plt.close()

def plot_queue_lengths(queue_data, flow_timings, output_dir, cc_mode, features, 
                      start_time=None, end_time=None):
    """
    绘制队列长度随时间的变化，标记每个流的开始和结束时间。
    """
    if queue_data is None or queue_data.empty:
        print("没有队列长度数据可绘制")
        return
    
    plt.figure(figsize=(12, 6))
    
    # 绘制队列长度
    plt.plot(queue_data['timestamp'], queue_data['queue_size'] / 1000,  # 转换为KB
             label="队列大小", color='blue', linewidth=1.5)
    
    # 为流标记生成不同的颜色
    flow_colors = plt.cm.Set2(np.linspace(0, 1, len(flow_timings)))
    
    # 添加流开始和结束时间的垂直线
    for i, (flow_key, timing) in enumerate(flow_timings.items()):
        flow_start_time = timing['start_time']
        flow_end_time = timing['end_time']
        
        if flow_start_time is not None:
            plt.axvline(x=flow_start_time, color=flow_colors[i], linestyle='--', 
                       alpha=0.5, label=f"{flow_key} 开始", linewidth=0.8)
        
        if flow_end_time is not None:
            plt.axvline(x=flow_end_time, color=flow_colors[i], linestyle=':', 
                       alpha=0.5, label=f"{flow_key} 结束", linewidth=0.8)
    
    plt.xlabel('time(s)')
    plt.ylabel('queuesize(KB)')
    
    # 如果可用，将功能添加到标题
    features_str = ", ".join(features) if features else ""
    title = f'queue-time\nal: {cc_mode}'
    if features_str:
        title += f' ({features_str})'
    plt.title(title)
    
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    # 根据提供的参数设置x轴限制
    if start_time is not None or end_time is not None:
        xlim_args = []
        if start_time is not None:
            xlim_args.append(start_time)
        else:
            xlim_args.append(plt.xlim()[0])
            
        if end_time is not None:
            xlim_args.append(end_time)
        else:
            xlim_args.append(plt.xlim()[1])
            
        plt.xlim(*xlim_args)
    
    # 保存图表
    output_filename = f'queue_length_{cc_mode}'
    if features:
        output_filename += f'_{"_".join(features)}'
    
    plt.tight_layout()
    out_file = os.path.join(output_dir, f'{output_filename}.png')
    plt.savefig(out_file, dpi=300)
    print(f"队列长度图表已保存至 {out_file}")
    
    plt.close()

def plot_pru_tokens(pru_data, flow_timings, output_dir, cc_mode, features, 
                   start_time=None, end_time=None):
    """
    绘制PRU令牌随时间的变化，标记每个流的开始和结束时间。
    """
    if pru_data is None or pru_data.empty:
        print("没有PRU令牌数据可绘制")
        return
    
    plt.figure(figsize=(12, 6))
    
    # 绘制PRU令牌
    plt.plot(pru_data['timestamp'], pru_data['token_count'],
             label="PRU token", color='purple', linewidth=1.5)
    
    # 为流标记生成不同的颜色
    flow_colors = plt.cm.Set2(np.linspace(0, 1, len(flow_timings)))
    
    # 添加流开始和结束时间的垂直线
    for i, (flow_key, timing) in enumerate(flow_timings.items()):
        flow_start_time = timing['start_time']
        flow_end_time = timing['end_time']
        
        if flow_start_time is not None:
            plt.axvline(x=flow_start_time, color=flow_colors[i], linestyle='--', 
                       alpha=0.5, label=f"{flow_key} 开始", linewidth=0.8)
        
        if flow_end_time is not None:
            plt.axvline(x=flow_end_time, color=flow_colors[i], linestyle=':', 
                       alpha=0.5, label=f"{flow_key} 结束", linewidth=0.8)
    
    plt.xlabel('time(s)')
    plt.ylabel('PRUtokens')
    
    # 如果可用，将功能添加到标题
    features_str = ", ".join(features) if features else ""
    title = f'PRU-times\nal: {cc_mode}'
    if features_str:
        title += f' ({features_str})'
    plt.title(title)
    
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    # 根据提供的参数设置x轴限制
    if start_time is not None or end_time is not None:
        xlim_args = []
        if start_time is not None:
            xlim_args.append(start_time)
        else:
            xlim_args.append(plt.xlim()[0])
            
        if end_time is not None:
            xlim_args.append(end_time)
        else:
            xlim_args.append(plt.xlim()[1])
            
        plt.xlim(*xlim_args)
    
    # 保存图表
    output_filename = f'pru_tokens_{cc_mode}'
    if features:
        output_filename += f'_{"_".join(features)}'
    
    plt.tight_layout()
    out_file = os.path.join(output_dir, f'{output_filename}.png')
    plt.savefig(out_file, dpi=300)
    print(f"PRU令牌图表已保存至 {out_file}")
    
    plt.close()

def plot_throughput(throughput_data, flow_timings, output_dir, cc_mode, features, 
                   start_time=None, end_time=None):
    """
    绘制吞吐量随时间的变化，标记每个流的开始和结束时间。
    """
    if throughput_data is None or throughput_data.empty:
        print("没有吞吐量数据可绘制")
        return
    
    plt.figure(figsize=(12, 6))
    
    # 绘制吞吐量
    plt.plot(throughput_data['timestamp'], throughput_data['throughput_gbps'],
             label="吞吐量", color='green', linewidth=1.5)
    
    # 在100 Gbps处（瓶颈容量）绘制一条水平线
    plt.axhline(y=100, color='red', linestyle='-', alpha=0.5, 
               label="cap(100 Gbps)")
    
    # 为流标记生成不同的颜色
    flow_colors = plt.cm.Set2(np.linspace(0, 1, len(flow_timings)))
    
    # 添加流开始和结束时间的垂直线
    for i, (flow_key, timing) in enumerate(flow_timings.items()):
        flow_start_time = timing['start_time']
        flow_end_time = timing['end_time']
        
        if flow_start_time is not None:
            plt.axvline(x=flow_start_time, color=flow_colors[i], linestyle='--', 
                       alpha=0.5, label=f"{flow_key} 开始", linewidth=0.8)
        
        if flow_end_time is not None:
            plt.axvline(x=flow_end_time, color=flow_colors[i], linestyle=':', 
                       alpha=0.5, label=f"{flow_key} 结束", linewidth=0.8)
    
    plt.xlabel('time(s)')
    plt.ylabel('throghtoutput (Gbps)')
    
    # 如果可用，将功能添加到标题
    features_str = ", ".join(features) if features else ""
    title = f'吞吐量随时间变化\n算法: {cc_mode}'
    if features_str:
        title += f' ({features_str})'
    plt.title(title)
    
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    # 根据提供的参数设置x轴限制
    if start_time is not None or end_time is not None:
        xlim_args = []
        if start_time is not None:
            xlim_args.append(start_time)
        else:
            xlim_args.append(plt.xlim()[0])
            
        if end_time is not None:
            xlim_args.append(end_time)
        else:
            xlim_args.append(plt.xlim()[1])
            
        plt.xlim(*xlim_args)
    
    # 设置y轴从0开始
    plt.ylim(bottom=0)
    
    # 保存图表
    output_filename = f'throughput_{cc_mode}'
    if features:
        output_filename += f'_{"_".join(features)}'
    
    plt.tight_layout()
    out_file = os.path.join(output_dir, f'{output_filename}.png')
    plt.savefig(out_file, dpi=300)
    print(f"吞吐量图表已保存至 {out_file}")
    
    plt.close()

def calculate_jains_fairness(values):
    """
    计算Jain公平性指数。
    
    公式: (sum(x_i))^2 / (n * sum(x_i^2))
    
    返回介于0和1之间的值，其中1表示完美公平。
    """
    if not values.any():
        return 0
    
    n = len(values)
    if n <= 1:
        return 1.0  # 单个值总是公平的
    
    sum_values = np.sum(values)
    sum_squared = np.sum(np.square(values))
    
    fairness = (sum_values ** 2) / (n * sum_squared)
    return fairness

def plot_fairness(flow_stats, output_dir, cc_mode, features, 
                 start_time=None, end_time=None):
    """
    绘制Jain公平性指数随时间的变化。
    """
    if flow_stats is None or flow_stats.empty:
        print("没有流统计数据可绘制公平性")
        return
    
    # 创建新图表
    plt.figure(figsize=(12, 6))
    
    # 按时间戳对流统计数据进行分组
    timestamps = sorted(flow_stats['timestamp'].unique())
    fairness_data = []
    
    for ts in timestamps:
        # 获取此时间戳下所有流的cwnd值
        ts_data = flow_stats[flow_stats['timestamp'] == ts]
        
        # 计算cwnd的Jain公平性指数
        cwnd_values = ts_data['cwnd'].values
        if len(cwnd_values) > 1:  # 需要至少2个流来计算公平性
            fairness_index = calculate_jains_fairness(cwnd_values)
            fairness_data.append({'timestamp': ts, 'fairness': fairness_index})
    
    if not fairness_data:
        print("没有足够的数据来计算公平性")
        plt.close()
        return
    
    # 转换为DataFrame
    fairness_df = pd.DataFrame(fairness_data)
    
    # 绘制公平性指数
    plt.plot(fairness_df['timestamp'], fairness_df['fairness'], 
             color='orange', linewidth=1.5)
    
    plt.xlabel('时间 (秒)')
    plt.ylabel('Jain公平性指数')
    
    # 如果可用，将功能添加到标题
    features_str = ", ".join(features) if features else ""
    title = f'公平性随时间变化\n算法: {cc_mode}'
    if features_str:
        title += f' ({features_str})'
    plt.title(title)
    
    plt.grid(True, alpha=0.3)
    
    # 设置公平性指数的y轴限制（0到1）
    plt.ylim(0, 1.05)
    
    # 根据提供的参数设置x轴限制
    if start_time is not None or end_time is not None:
        xlim_args = []
        if start_time is not None:
            xlim_args.append(start_time)
        else:
            xlim_args.append(plt.xlim()[0])
            
        if end_time is not None:
            xlim_args.append(end_time)
        else:
            xlim_args.append(plt.xlim()[1])
            
        plt.xlim(*xlim_args)
    
    # 保存图表
    output_filename = f'fairness_{cc_mode}'
    if features:
        output_filename += f'_{"_".join(features)}'
    
    plt.tight_layout()
    out_file = os.path.join(output_dir, f'{output_filename}.png')
    plt.savefig(out_file, dpi=300)
    print(f"公平性图表已保存至 {out_file}")
    
    plt.close()

def main():
    """
    主函数，用于创建所有图表。
    """
    global OUTPUT_DIR
    OUTPUT_DIR += '/'
    OUTPUT_DIR += sys.argv[1]
    OUTPUT_DIR += '/'
    print("Bolt 公平性实验可视化工具")
    print("============================")
    
    # 创建输出目录（如果不存在）
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 根据参数确定文件路径
    if DATA_FILE:
        base_filename = DATA_FILE
        cc_mode = extract_cc_mode(base_filename)
        features = extract_features(base_filename)
    elif SIM_IDX:
        # 查找具有给定模拟索引的所有文件
        files = [f for f in os.listdir(BASE_DIR) 
                if f.startswith(SIM_IDX) and f.endswith('.log')]
        
        if not files:
            print(f"未找到模拟索引为 {SIM_IDX} 的文件")
            return
        
        # 使用第一个文件确定基本文件名
        base_filename = os.path.join(BASE_DIR, files[0].rsplit('.', 1)[0])
        cc_mode = extract_cc_mode(files[0])
        features = extract_features(files[0])
    else:
        # 查找最新的模拟文件
        log_files = sorted([f for f in os.listdir(BASE_DIR) if f.endswith('.log')])
        
        if not log_files:
            print(f"在 {BASE_DIR} 中未找到日志文件")
            return
        
        # 使用最新的文件
        base_filename = os.path.join(BASE_DIR, log_files[-1].rsplit('.', 1)[0])
        cc_mode = extract_cc_mode(log_files[-1])
        features = extract_features(log_files[-1])
    
    print(f"分析来自: {base_filename} 的数据")
    print(f"检测到的拥塞控制模式: {cc_mode}")
    print(f"检测到的功能: {', '.join(features) if features else '无'}")
    
    # 定义文件路径
    flow_stats_file = f"{base_filename}.log"
    queue_file = f"{base_filename}.qlen"
    tpt_file = f"{base_filename}.tpt"
    pru_file = f"{base_filename}.pru"
    
    # 读取数据
    print(f"从 {flow_stats_file} 读取流统计数据")
    flow_stats = read_flow_stats(flow_stats_file)
    
    print(f"从 {queue_file} 读取队列长度数据")
    queue_data = read_queue_lengths(queue_file)
    
    print(f"从 {tpt_file} 读取吞吐量数据")
    tpt_data = read_throughput(tpt_file)
    
    print(f"从 {pru_file} 读取PRU令牌数据")
    pru_data = read_pru_tokens(pru_file)
    
    # 获取流时序
    flow_timings = get_flow_start_end_times(flow_stats, NEW_FLOW_TIME, N_FLOWS)
    
    # 根据出队字节计算吞吐量
    if tpt_data is not None and not tpt_data.empty:
        throughput_data = calculate_throughput(tpt_data)
    else:
        throughput_data = None
    
    # 打印流时序
    print("流时序:")
    for flow_key, timing in flow_timings.items():
        print(f"  {flow_key}: 开始={timing['start_time']:.6f}s, 结束={timing['end_time']:.6f}s")
    
    # 创建图表
    plot_cwnd(flow_stats, flow_timings, OUTPUT_DIR, cc_mode, features, 
              START_TIME, END_TIME)
    
    plot_rtt(flow_stats, flow_timings, OUTPUT_DIR, cc_mode, features,
            START_TIME, END_TIME)
    
    plot_queue_lengths(queue_data, flow_timings, OUTPUT_DIR, cc_mode, features,
                      START_TIME, END_TIME)
    
    if pru_data is not None and not pru_data.empty:
        plot_pru_tokens(pru_data, flow_timings, OUTPUT_DIR, cc_mode, features,
                       START_TIME, END_TIME)
    
    if throughput_data is not None and not throughput_data.empty:
        plot_throughput(throughput_data, flow_timings, OUTPUT_DIR, cc_mode, features,
                       START_TIME, END_TIME)
    
    # 计算并绘制公平性
    #plot_fairness(flow_stats, OUTPUT_DIR, cc_mode, features,
    #             START_TIME, END_TIME)
    
    print("绘图完成！")

if __name__ == "__main__":
    main()