import numpy as np

# parameters to modify 
filename="/home/ubuntu/CWM-FDI/assignment2/time_py.txt"

## load data from input file
t = np.loadtxt(filename, delimiter=" ", dtype="float")

print([val for val in t if val > 4000])
