# !/usr/bin/python3
import numpy as np
import matplotlib.pyplot as plt

# parameters to modify 
fname1="/home/ubuntu/CWM-FDI/assignment2/ping0-01.txt"
fname2="/home/ubuntu/CWM-FDI/assignment2/ping0-001.txt"
fname3="/home/ubuntu/CWM-FDI/assignment2/ping0-0001.txt"

files = [fname1, fname2, fname3]

label=''
xlabel = 'time'
ylabel = 'CDF probability'
bins=100 #adjust the number of bins to your plot

## load data from input file
for file in files:
    t = []
    with open(file, 'r') as f:
        for line in f:
            if 'time=' in line:
                parts = line.split("time=")
                if len(parts) > 1:
                    time_str = parts[1].split()[0]
                    try:
                        t.append(float(time_str.replace('ms', '')))

                    except ValueError:
                        pass
    interval = file.split("-")[-1].split(".")[0]
    fig_name = interval + "ping.png"

    title = f"Ping with an interval of 0.{interval}s"
    n = np.arange(1,len(t)+1) / float(len(t))
    ts = np.sort(t)
    fig, ax = plt.subplots()
    ax.step(ts,n)

    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.savefig(fig_name)
    plt.show()
