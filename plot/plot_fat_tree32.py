import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import argparse
import os

def parse_traces(trace_file):
    """
    解析NS-3生成的消息跟踪文件
    格式假设为: 
    + [时间戳] [消息大小] [源地址:端口] [目标地址:端口] [消息ID]
    - [时间戳] [消息大小] [源地址:端口] [目标地址:端口] [消息ID]
    """
    # 初始化存储开始和结束记录的字典
    start_records = {}
    end_records = {}
    
    # 读取跟踪文件
    with open(trace_file, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 6:
                continue
                
            record_type = parts[0]
            timestamp = float(parts[1]) / 1e9  # 纳秒转为秒
            msg_size = int(parts[2])
            src_addr = parts[3]
            dst_addr = parts[4]
            msg_id = int(parts[5])
            
            flow_id = f"{src_addr}_{dst_addr}_{msg_id}"
            
            if record_type == "+":
                # 消息开始记录
                start_records[flow_id] = (timestamp, msg_size)
            elif record_type == "-":
                # 消息结束记录
                end_records[flow_id] = timestamp
    
    # 计算FCT和理想FCT
    flow_data = []
    
    for flow_id, (start_time, flow_size) in start_records.items():
        if flow_id in end_records:
            end_time = end_records[flow_id]
            fct = end_time - start_time
            
            # 计算理想FCT (假设带宽为100Gbps，延迟为10us)
            bandwidth = 100e9  # 比特/秒
            base_rtt = 20e-6   # 秒 (往返)
            ideal_fct = base_rtt + (flow_size * 8) / bandwidth
            
            # 计算FCT Slowdown
            fct_slowdown = fct / ideal_fct
            
            flow_data.append({
                'flow_id': flow_id,
                'flow_size': flow_size,
                'fct': fct,
                'ideal_fct': ideal_fct,
                'fct_slowdown': fct_slowdown
            })
    
    return pd.DataFrame(flow_data)

def plot_fct_slowdown_vs_flowsize(df, output_file=None):
    """
    绘制FCT Slowdown与Flow Size的关系图
    """
    plt.figure(figsize=(10, 6))
    
    # 散点图，使用对数刻度
    plt.scatter(df['flow_size'], df['fct_slowdown'], alpha=0.6, s=20)
    
    # 可选：添加LOWESS平滑曲线来显示趋势
    try:
        from statsmodels.nonparametric.smoothers_lowess import lowess
        lowess_data = lowess(df['fct_slowdown'], df['flow_size'], frac=0.3)
        plt.plot(lowess_data[:, 0], lowess_data[:, 1], 'r-', linewidth=2, label='趋势线')
        plt.legend()
    except ImportError:
        print("statsmodels未安装，跳过趋势线绘制")
    
    # 设置为对数刻度
    plt.xscale('log')
    plt.yscale('log')
    
    # 设置标签和标题
    plt.xlabel('Flow Size (bytes)', fontsize=12)
    plt.ylabel('FCT Slowdown', fontsize=12)
    plt.title('FCT Slowdown vs Flow Size', fontsize=14)
    
    # 添加网格
    plt.grid(True, which="both", ls="--", alpha=0.3)
    
    # 可以添加一条y=1的参考线，表示理想情况
    plt.axhline(y=1, color='g', linestyle='--', alpha=0.5, label='理想FCT')
    
    plt.tight_layout()
    
    # 保存图表
    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"图表已保存至: {output_file}")
    
    plt.show()

def create_flow_size_categories(df):
    """
    创建流大小类别以便于分析
    """
    bins = [0, 1000, 10000, 100000, 1000000, float('inf')]
    labels = ['<1KB', '1KB-10KB', '10KB-100KB', '100KB-1MB', '>1MB']
    
    df['size_category'] = pd.cut(df['flow_size'], bins=bins, labels=labels)
    return df

def analyze_by_flow_size(df):
    """
    按流大小类别分析FCT Slowdown
    """
    df = create_flow_size_categories(df)
    
    # 按类别分组并计算统计数据
    stats = df.groupby('size_category')['fct_slowdown'].agg([
        'count', 'mean', 'median', 'min', 'max',
        lambda x: np.percentile(x, 95),
        lambda x: np.percentile(x, 99)
    ])
    
    stats = stats.rename(columns={
        'count': '数量',
        'mean': '平均值',
        'median': '中位数',
        'min': '最小值',
        'max': '最大值',
        '<lambda_0>': '95百分位',
        '<lambda_1>': '99百分位'
    })
    
    return stats

def main():
    parser = argparse.ArgumentParser(description='分析FCT Slowdown与Flow Size的关系')
    parser.add_argument('trace_file', help='NS-3跟踪文件路径')
    parser.add_argument('--output', '-o', help='输出图表文件路径 (例如 output.png)')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.trace_file):
        print(f"错误: 找不到文件 {args.trace_file}")
        return
    
    print(f"正在解析文件: {args.trace_file}")
    df = parse_traces(args.trace_file)
    
    if df.empty:
        print("未找到有效数据。请检查跟踪文件格式。")
        return
    
    print(f"共找到 {len(df)} 条流记录")
    
    # 打印流大小类别的统计信息
    stats = analyze_by_flow_size(df)
    print("\n按流大小类别的FCT Slowdown统计:")
    print(stats)
    
    # 绘制图表
    plot_fct_slowdown_vs_flowsize(df, args.output)

if __name__ == "__main__":
    main()