import numpy as np

from corrosion_sim import ga


# 对应 stage_moni.m。遗传算法计算量很大，建议先把 w/l/n/F/nind/maxgen 调小试跑。
w = 100
l = 100
n = 100
data_x_values = np.array([1063], dtype=float)
data = np.array([[1063, 459, 1.23, 6.23, 0.55, 0.29]], dtype=float)

space = 25
F = 2000
stage_number = 1
parameter_single = 10

a_input = None
d_input = None
cl_input = None

perfect_result_sd = np.zeros((len(data_x_values), data.shape[1] - 2))
perfect_parameter_sd = np.zeros((len(data_x_values), parameter_single))
a_sd = []

for i, data_x in enumerate(data_x_values):
    perfect_result, perfect_parameter, a_output, d_output, cl_output = ga(
        w,
        l,
        n,
        data_x,
        data[i, :],
        a_input,
        F,
        stage_number,
        space,
        d_input,
        cl_input,
        nind=300,
        maxgen=100,
    )
    perfect_result_sd[i, :] = perfect_result
    perfect_parameter_sd[i, :] = perfect_parameter
    a_sd.append(a_output)
    a_input, d_input, cl_input = a_output, d_output, cl_output
    stage_number += 1

np.savez_compressed(
    "stage_moni_result.npz",
    perfect_result_sd=perfect_result_sd,
    perfect_parameter_sd=perfect_parameter_sd,
)
print("perfect_result_sd =")
print(perfect_result_sd)
print("perfect_parameter_sd =")
print(perfect_parameter_sd)
