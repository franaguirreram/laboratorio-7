#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Aug 24 18:08:06 2026

@author: fran
"""
import time
import numpy as np
import pandas as pd
from pipython import GCSDevice, pitools

AXIS    = 'A'
CHANNEL = 1

DAQ_CHANNEL = 8
DAQ_GAIN    = 5

PASO  = 0.01
START = 90.0
END   = 140.0

PRE_MOV_WAIT  = 0.1    # s
QUERY_WAIT    = 0.05    # s
ONTARGET_TOUT = 10.0   # s

n_points = int(round((END - START) / PASO))
forward  = [float(x) for x in np.linspace(START, END, n_points)]

with GCSDevice('E-545') as pidevice:
    pidevice.ConnectUSB("0111176619")
    print(pidevice.qIDN())

    pidevice.ONL([CHANNEL], [True])
    pidevice.SVO(AXIS, True)