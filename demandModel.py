from mip import *
from pathlib import Path
import json
import pandas as pd
import math

months = [201901, 201902]


#Model Configuration
day = "0" #0-6: 0 is Monday 6 is Sunday
halfHour = "24" #0 - 47: 0 is 12 am and 47 and 11:30 pm

#Getting data

#Joco Station Data
jocoStationsPath = '../jocoSoftLaunchStations.xlsx'
jocoStationsDF = pd.read_excel(jocoStationsPath)


#Joco to Joco distance matrix
jocoDistanceMatrixPath = './jocoToJocoDistanceMatrixSoftLaunch.xlsx'
jocoDistMatrixDF = pd.read_excel(jocoDistanceMatrixPath)


#print(jocoStationsDF)
#print(jocoDistMatrixDF)

monthlyDataStart = {}
monthlyDataEnd = {}


for month in months:
	data_folder = Path("../data.nosync/{}.nosync/".format(month))
	jsonFileMonthEnd = data_folder / "{}-formated-end-data.json".format(month)
	jsonFileMonthStart = data_folder / "{}-formated-data.json".format(month)

	with open(jsonFileMonthStart) as f:
		data = json.load(f)
		monthlyDataStart[str(month)] = data

	with open(jsonFileMonthEnd) as f:
		data = json.load(f)
		monthlyDataEnd[str(month)] = data

#Data that the model will use
dataModel = {'stations': [], 'halfHour': halfHour, 'day': day, 'totalStartRides': 0, 'totalEndRides': 0 }
#keys = range(len(monthlyDataStart[str(months[0])]['stations'])) #Number of JOCO Stations
keys = [4, 5, 13, 27]

for key in keys:
	dataModel['stations'].append({"stationID": (key + 1), "startRides": 0, "startPercentRides": 0, "endRides": 0, "endPercentRides": 0})

jocoStationNames = jocoDistMatrixDF.columns.values.tolist()
jocoStationNames.pop(0)
jocoStationNames = jocoStationNames[:(len(keys)+1)]
print(jocoStationNames)
DIST = [ [0 for i in range(len(jocoStationNames)) ] for j in range(len(jocoStationNames))]

print(DIST)

count = 0
for stationKey in jocoStationNames:
	stationId = int(stationKey.split(",")[0])
	print("STATION ID: ", stationId)
	#print(jocoDistMatrixDF[stationKey])
	for i in range(len(keys)+1):
		print("DISTANCE: ", jocoDistMatrixDF[stationKey][i])
		print("OTHER STATION ID: ", int(jocoStationNames[i].split(",")[0]))
		DIST[count][i] = jocoDistMatrixDF[stationKey][i] / 250

	count = count + 1

#print(DIST)



#Variables for creating the data
numOfMonths = float(len(months))

for month in months:
	monthStr = str(month)
	#print(type(monthlyDataStart[monthStr])
	for station in dataModel['stations']:
		stationIndex = int(station['stationID']) - 1 
		startRides = float(monthlyDataStart[monthStr]['stations'][stationIndex]['daysOfWeekRides'][day][halfHour][0])/numOfMonths
		station['startRides'] += startRides
		station['startPercentRides'] += float(monthlyDataStart[monthStr]['stations'][stationIndex]['daysOfWeekRides'][day][halfHour][1])/numOfMonths
		dataModel['totalStartRides'] += startRides

		endRides = float(monthlyDataEnd[monthStr]['stations'][stationIndex]['daysOfWeekRides'][day][halfHour][0])/numOfMonths
		station['endRides'] += endRides
		station['endPercentRides'] += float(monthlyDataEnd[monthStr]['stations'][stationIndex]['daysOfWeekRides'][day][halfHour][1])/numOfMonths
		dataModel['totalEndRides'] += endRides

#Data is now collected in dataModel

numJocoStations = len(keys)

print(dataModel)

#Seconds in 30 minutes. Length of the rebalancing period. 
#30 minute is how long the interval for the data we read in is. 
#SO to change this value would require us to change the period of the intervals coming form the data.
t_period = 30 

#Constant representing the overhead time per station visit (for parking, etc). 180 is then number of seconds in 3 minutes.
t_station = 3

#Constant representing the initial time of rebalancing in seconds.
t_not = 0#int(halfHour)*30

#Constant representing the time taht is required for each bike pickup and dropoff. 60 seconds for now
t_action = 1

#Constant representing the number of bikes initially in the truck
C_not = 0

#Constant represetning carying capacity of the truck
CT = 8

#Large Constant
M = 1000

#Number of bikes in the JOCO system
NUMBIKES = 40

#Small constants
GAMMA = .001
SIGMA = .001

m = Model(solver_name=CBC)
#m = Model(sense=MAXIMIZE, solver_name=CBC)

#MODEL VARIABLES

#Decision Variables expressing whether the truck visits station j right after station i. 
#+1 because the truck is a dummy node 
#(think about starting at the truck and going to the first station of the rebalancing period)
#indexed x[i][j]
x = [ [ m.add_var(name = 'x_{}{}'.format(i, j), var_type=BINARY) for i in range(numJocoStations + 1)] for j in range(numJocoStations + 1) ] 


#Decision Variables expressing the truck arrivlal times at at station i
t = [ m.add_var(name = 't_{}'.format(i + 1), var_type=CONTINUOUS, lb=t_not, ub= t_not + t_period) for i in range(numJocoStations) ] 

#Decision Variables expressing how long a visit to a station will be
dur = [m.add_var(name = 'dur_{}'.format(i + 1), var_type=CONTINUOUS, lb=0, ub=t_period) for i in range(numJocoStations)]

#Decision Variables expressing how many bikes are in the truck upon arrival at station i
bT = [m.add_var(name = 'bT_{}'.format(i + 1), var_type=INTEGER, lb=0, ub=CT) for i in range(numJocoStations)]

#Decision Variables expressing the total number of bikes picked up at station i
PU = [m.add_var(name = 'PU_{}'.format(i + 1), var_type=INTEGER, lb=0, ub=CT) for i in range(numJocoStations)]

#Decision Variables expressing the total number of bikes droped off at station i
DO = [m.add_var(name = 'DO_{}'.format(i + 1), var_type=INTEGER, lb=0, ub=CT) for i in range(numJocoStations)]

#Decision Variables expressing the number of bikes Picked up at station i that add immediate value to the rebalancing 
#as they vacate docks for customers to use
PU_plus = [m.add_var(name = 'PU_plus_{}'.format(i + 1),var_type=INTEGER, lb=0, ub=CT) for i in range(numJocoStations)]

#Decision Variables expressing the number of bikes droped off at station i that add immediate value to the rebalancing 
#as they add bikes for customers to use
DO_plus = [m.add_var(name = 'DO_plus_{}'.format(i + 1), var_type=INTEGER, lb=0, ub=CT) for i in range(numJocoStations)]

#Decision Variables expressing the number of bikes Picked up at station i that do not immediate value to the rebalancing 
#but will be utilized at some future point
PU_neutral = [m.add_var(name = 'PU_neutral_{}'.format(i + 1), var_type=INTEGER, lb=0, ub=CT) for i in range(numJocoStations)]

#Decision Variables expressing the number of bikes droped off at station i that do not add immediate value to the rebalancing 
#but will be utilized at some future point
DO_neutral = [m.add_var(name = 'DO_neutral_{}'.format(i  + 1), var_type=INTEGER, lb=0, ub=CT) for i in range(numJocoStations)]

#MODEL EQUATIONS

#S is the set of joco stations
S_size = numJocoStations

#S_o include the truck dummy node
S_o_Size = numJocoStations + 1


#(30)

for i in range(S_o_Size):
	m += xsum(x[i][j] for j in range(S_o_Size)) == 1 

#(31)
for i in range(S_o_Size):
	m += xsum(x[j][i] for j in range(S_o_Size)) == 1

#(32)
for i in range(S_size):
	for j in range(S_size):
		if i != j:
			m += t[j] >= t[i] + dur[i] + DIST[i+1][j+1] * x[i+1][j+1] - M*(1-x[i+1][j+1])

#(33)
for i in range(S_size):
	m += t[i] >= DIST[0][i+1]*x[0][i+1] + t_not

#(34)
for i in range(S_size):
	m += t[i] <= t_period 

#(35)
for i in range(S_size):
	m += dur[i] >= t_station * (1-x[i+1][i+1]) + t_action * PU[i] + t_action * DO[i]


#(36)
for i in range(S_size):
	for j in range(S_size):
		if i != j:
			m += bT[j] >= bT[i] + PU[i] - DO[i] - M * (1-x[i+1][j+1])

#(37)
for i in range(S_size):
	for j in range(S_size):
		if i != j:
			m += bT[j] <= bT[i] + PU[i] - DO[i] + M * (1-x[i+1][j+1])

#(38)
for i in range(S_size):
	m += bT[i] >= C_not*x[0][i+1]

#(39)
for i in range(S_size):
	m += bT[i] <= CT - (CT - C_not)*x[0][i+1]

#(40)
for i in range(S_size):
	m += bT[i] <= CT

#(41)
for i in range(S_size):
	m += bT[i] + PU[i] - DO[i] <= CT

#(42)
for i in range(S_size):
	m += bT[i] + PU[i] - DO[i] >= 0

#(43) UNUSED BIKES
for i in range(S_size):
	startDemandComparedToCiti = min(1, dataModel['totalStartRides'] / (500/34)*4 )
	endDemandComparedToCiti = min(1, dataModel['totalEndRides'] / (500/34)*4 )
	m += ( PU[i] <= NUMBIKES - NUMBIKES * ( startDemandComparedToCiti * dataModel['stations'][i]['startPercentRides']) 
+ NUMBIKES * ( endDemandComparedToCiti * dataModel['stations'][i]['endPercentRides']) )

#(44) DOCKS NEEDED
for i in range(S_size):
	endDemandComparedToCiti = min(1, dataModel['totalEndRides'] / (500/34)*4 )
	print(dataModel['totalEndRides'])
	print(endDemandComparedToCiti)
	print(NUMBIKES * ( endDemandComparedToCiti * dataModel['stations'][i]['endPercentRides']))
	m += ( PU_plus[i] <= NUMBIKES * ( endDemandComparedToCiti * dataModel['stations'][i]['endPercentRides']) )

#(45)
for i in range(S_size):
	m += PU[i] == PU_plus[i] + PU_neutral[i] - DO[i]

#(46)
for i in range(S_size):
	m += PU[i] <= M*(1-x[i+1][i+1])

#(47) UNUSED DOCKS
for i in range(S_size):
	DT_i = jocoStationsDF['Bike Capacity Total'][i]
	m += DO[i] <= DT_i +  NUMBIKES * ( startDemandComparedToCiti * dataModel['stations'][i]['startPercentRides']) 
- NUMBIKES * ( endDemandComparedToCiti * dataModel['stations'][i]['endPercentRides']) 
  
#(48) BIKES NEEDED
for i in range(S_size):
	m +=  DO_plus[i] <= NUMBIKES * ( startDemandComparedToCiti * dataModel['stations'][i]['startPercentRides']) 

#(49) 
for i in range(S_size):
	m += DO[i] == DO_plus[i] + DO_neutral[i] - PU[i]

#(50)
for i in range(S_size):
	m += DO[i] <= M * (1-x[i+1][i+1])



m.objective = maximize( (xsum(PU_plus[i] for i in range(S_size))) 
+ (xsum(DO_plus[i] for i in range(S_size))) 
- GAMMA * (xsum( (xsum( (DIST[i][j] * x[i][j]) for i in range(S_o_Size))) for j in range(S_size)))
- SIGMA * (xsum( (PU[i] + DO[i]) for i in range(S_size))) )


print(jocoStationsDF['Bike Capacity Total'][0])
print(jocoStationsDF)

print(m)
#m.write('model.lp')

m.max_gap = 0.05
status = m.optimize(max_seconds=30)
print(status)
if status == OptimizationStatus.OPTIMAL:
    print('optimal solution cost {} found'.format(m.objective_value))
elif status == OptimizationStatus.FEASIBLE:
    print('sol.cost {} found, best possible: {}'.format(m.objective_value, m.objective_bound))
elif status == OptimizationStatus.NO_SOLUTION_FOUND:
	for v in m.vars:
		print('{} : {}'.format(v.name, v.x))
		print(x)
		print(PU)
		print(DO)
	print('no feasible solution found, lower bound is: {}'.format(m.objective_bound))


if status == OptimizationStatus.OPTIMAL or status == OptimizationStatus.FEASIBLE:
	print('solution:')
	for v in m.vars:
		#if abs(v.x) > 1e-6: # only printing non-zeros
		print('{} : {}'.format(v.name, v.x))

#print(dataModel)

print("ben")