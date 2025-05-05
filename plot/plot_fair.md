# Bolt 公平性实验可视化工具

这个工具可以可视化 Bolt 公平性实验的输出数据，生成全面的图表来帮助分析拥塞控制性能。

## 主要功能

- 可视化拥塞窗口（cwnd）大小随时间的变化
- 绘制往返时间（RTT）测量值
- 显示瓶颈处的队列长度
- 显示 PRU 令牌计数（如果启用）
- 计算并绘制吞吐量
- 使用 Jain 公平性指数分析公平性
- 自动检测拥塞控制模式和启用的功能

## 使用要求

- Python 3.6+
- pandas
- matplotlib
- numpy

## 安装方法

1. 将 `bolt_fairness_plot_no_args.py` 脚本保存到您的计算机
2. 安装所需的包：

```bash
pip install pandas matplotlib numpy
```

## 使用方法

与使用命令行参数不同，这个版本的脚本使用脚本顶部的变量来配置所有选项。您可以直接编辑这些变量来自定义分析：

```python
# =============== 用户配置参数（您可以在这里直接更改参数）===============
# 数据文件路径（不含扩展名）。如果设置为None，则使用base_dir中最近的文件
DATA_FILE = None

# 包含输出文件的目录
BASE_DIR = 'outputs/bolt-fairness'

# 保存生成图表的目录
OUTPUT_DIR = 'plots'

# 模拟指数（如果设置了这个值，将查找具有此指数的文件）
SIM_IDX = None

# 图表X轴的时间范围（单位：秒）
START_TIME = None  # 开始时间，例如1.0
END_TIME = None    # 结束时间，例如1.05

# 流参数
NEW_FLOW_TIME = 0.002  # 新流加入/离开的时间间隔
N_FLOWS = 2           # 拓扑中的流数量
# ====================================================================
```

### 基本用法示例

1. **使用默认设置**：
   直接运行脚本，它将自动查找 `outputs/bolt-fairness` 目录中最新的模拟文件并生成图表：

   ```bash
   python bolt_fairness_plot_no_args.py
   ```

2. **指定模拟索引**：
   编辑脚本，设置 `SIM_IDX = "0"`，然后运行：

   ```bash
   python bolt_fairness_plot_no_args.py
   ```

3. **自定义时间范围**：
   编辑脚本，设置 `START_TIME = 1.0` 和 `END_TIME = 1.02`，然后运行：

   ```bash
   python bolt_fairness_plot_no_args.py
   ```

4. **自定义目录**：
   编辑脚本，设置 `BASE_DIR = "/path/to/simulation/data"` 和 `OUTPUT_DIR = "/path/to/save/plots"`，然后运行：

   ```bash
   python bolt_fairness_plot_no_args.py
   ```

5. **使用不同的流参数**：
   编辑脚本，设置 `NEW_FLOW_TIME = 0.005` 和 `N_FLOWS = 4`，然后运行：

   ```bash
   python bolt_fairness_plot_no_args.py
   ```

## 生成的图表

对于每个分析的模拟，将生成以下图表：

1. **拥塞窗口大小图** - 显示每个流的cwnd大小随时间的变化
2. **拥塞窗口大小（对数刻度）图** - 与上图相同但使用对数y轴
3. **往返时间图** - 显示RTT测量值随时间的变化
4. **队列长度图** - 显示瓶颈队列占用随时间的变化
5. **PRU令牌图** - 显示PRU令牌计数随时间的变化（如果启用）
6. **吞吐量图** - 显示计算得出的吞吐量（Gbps）
7. **公平性图** - 显示Jain公平性指数随时间的变化

每个图表都会保存为PNG文件在指定的输出目录中。

## 理解Bolt公平性实验

Bolt公平性实验模拟了多个流在瓶颈链路上竞争带宽的情况。模拟创建了一个哑铃拓扑，其中多个发送者连接到100 Gbps的瓶颈链路，RTT为8μs。

图表中需要观察的关键特性：
- 带宽在流之间的公平分配情况
- 流对拥塞的反应速度
- 瓶颈处的队列堆积
- BTS（返回发送者）和PRU（主动加速）等功能的效果