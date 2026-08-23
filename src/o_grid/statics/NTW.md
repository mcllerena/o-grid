# Bus Data 

Bus identification in the form nnnnnn.ii 
Bus name (up to 12 characters) 
Base voltage in kV 
Bus type (0=load; 1=load with voltage limits; 2=generation, 3=swing or 4=de-energized) 
Bus shunt (Gsht+jBsht) status (0 = off, 1 = on) 
Gsht (real part of shunt element in MW for base voltage) 
Bsht (imaginary part of shunt element in Mvar for base voltage) 
Bus area number 
Bus zone number 
Bus voltage module in pu 
Bus voltage angle in degrees 
Voltage threshold for overvoltage detection in pu 
Voltage threshold for under voltage detection in pu 
Voltage threshold for emergency overvoltage detection in pu 
Voltage threshold for emergency under voltage detection in pu 
Bus owner number 
Substation number 
Bus Scheme (0 = not defined; 1 = single; 2 = main and auxiliary; 3 = double bus single 
breaker; 4 = double bus double breaker; 5 = ring bus; 6 = breaker and half)

# Load Data 

Bus identification in the form nnnnnn.ii 
Load identifier (2 characters) 
Load status (0=off; 1=on) 
MW to be considered as constant power in the ZIP model
Mvar to be considered as constant power in the ZIP model 
MW to be considered as constant current in the ZIP model 
Mvar to be considered as constant current in the ZIP model 
MW to be considered as constant impedance in the ZIP model 
Mvar to be considered as constant impedance in the ZIP model 
Load owner number 
Zero sequence resistance (pu) 
Zero sequence resistance (pu) 
Load name

# Generator Data 

## Version 5 

Bus identification in the form nnnnnn.ii 
Generator identifier (2 characters) 
Generation in MW 
Generation in Mvar 
Maximum generation in Mvar 
Minimum generation in Mvar 
Specified controlled voltage in pu 
Controlled bus identification in the form nnnnnn.ii 
Generator power base in MVA 
Step-up transformer resistance in pu (system MVA base) 
Step-up transformer reactance in pu (system MVA base) 
Step-up transformer tap 
Generator status (0=off; 1=on) 
Participation factor for remote bus voltage control in %
Maximum generation in MW 
Minimum generation in MW 
Group number (identify similar machines in the same power plant) 
Unavailable (0 = available to be dispatched or 1 = unavailable) 
Owner number 
Connection to ground (1 = grounded star; 2 = star; 3 = delta) 
Positive sequence resistance (pu of system MVA base) 
Positive sequence reactance (pu of system MVA base) 
Zero sequence resistance (pu of system MVA base) 
Zero sequence reactance (pu of system MVA base) 
Grounding resistance (pu of system MVA base) 
Grounding reactance (pu of system MVA base) 
Generator unit name (up to 20 characters) 
Generator quadrature reactance (pu of system MVA base) 
Stator current service factor (>= 1, <= 1.4) 
Maximum loading angle in degree (>= 60., <= 85)

# Version 6

Bus identification in the form nnnnnn.ii 
Generator identifier (2 characters) 
Generation in MW 
Generation in Mvar 
Maximum generation in Mvar 
Minimum generation in Mvar 
Specified controlled voltage in pu 
Controlled bus identification in the form nnnnnn.ii
Generator power base in MVA 
Step-up transformer resistance in pu 
Step-up transformer reactance in pu 
Step-up transformer tap 
Generator status (0=off; 1=on) 
Participation factor for remote bus voltage control in % 
Maximum generation in MW 
Minimum generation in MW 
Group number (identify similar machines in the same power plant) 
Unavailable (0 = available to be dispatched or 1 = unavailable) 
Owner number 
Connection to ground (1 = grounded star; 2 = star; 3 = delta) 
Positive sequence resistance (pu) for non-full converter sources. Recommended: stator resistance. Or the maximum short circuit current for full converter sources. 
Positive sequence reactance (pu) for non-full converter sources. Recommended: x”d. Or the short-circuit power factor for full converter sources. 
Negative sequence resistance (pu): Recommended: stator resistance 
Negative sequence reactance (pu): Recommended: (x”d + x”q)/2 
Zero sequence resistance (pu) 
Zero sequence reactance (pu) 
Grounding resistance (pu) 
Grounding reactance (pu) 
Quadrature reactance (pu) – used for capability computation option 
Stator current service factor (>= 1, <= 1.4) – used capability computation 
Maximum loadng angle in degree (>= 60., <= 85) – used for capability computation 
Generator type: (0 = hydro; 1 = Steam; 2 = Gas; 3 = Wind Type 1; 4 = Wind Type 2; 5 
= Wind Type 3; 6 = Wind Type 4; 7 = PV)
Generator unit name (up to 20 characters)

# Shunt Data 

Bus identification in the form nnnnnn.ii 
Control mode (0=fixed; 1=discrete; 2=continuous or SVC) 
Voltage control range upper bound (for discrete mode) or specified voltage (for continuous mode) in pu 
Voltage control range lower bound (for discrete mode) in pu. Not used for continuous control mode. 
Controlled bus identification in the form nnnnnn.ii 
Initial shunt admittance Mvar (considering 1 p.u. bus voltage) 
Global status (0 or 1) 
Status of elements (0 = maintenance; 1 = available) (These entry can be repeated up to 8 times)
Number of elements (These entry can be repeated up to 8 times)
Size of the elements in Mvar (These entry can be repeated up to 8 times)
Zero sequence impedance (pu) (These entry can be repeated up to 8 times)

# Transmission Line Data 

## Version 5 

Bus From identification in the form nnnnnn.ii 
Bus To identification in the form nnnnnn.ii 
Circuit identifier (2 characters) 
Series resistance in pu 
Series reactance in pu 
Total line charging in Mvar 
Limit 1 in MVA 
Limit 2 in MVA 
Limit 3 in MVA 
Bus From line shunt status (0 or 1)
GshtF (real part of shunt element connected to Bus From in pu) 
BshtF (imaginary part of shunt element connected to Bus From in pu) 
Bus To line shunt status (0 or 1) 
GshtT (real part of shunt element connected to Bus To in pu) 
BshtT (imaginary part of shunt element connected to Bus To in pu) 
"Bus From" Line breaker status (0=off; 1=on; 2=off for maintenance) 
"Bus To" Line breaker status (0=off; 1=on; 2=off for maintenance) 
Line length (km) 
Area number 
Owner number 
Zero sequence resistance (pu) 
Zero Sequence reactance (pu) 
Branch name (up to 23 characters) 
Bus (nnnnnn.ii) controlled by Line shunt at From terminal 
Control status of the Line shunt at From terminal (0 or 1) 
Bus (nnnnnn.ii) controlled by Line shunt at To terminal 
Control status of the Line shunt at To terminal (0 or 1) 

## Version 6 

Bus From identification in the form nnnnnn.ii 
Bus To identification in the form nnnnnn.ii 
Circuit identifier (2 characters) 
Series resistance in pu 
Series reactance in pu 
Total line charging in Mvar 
Limit 1 in MVA
Limit 2 in MVA 
Limit 3 in MVA 
“Bus From” Line breaker status (0=off; 1=on; 2=off for maintenance) 
“Bus To” Line breaker status (0=off; 1=on; 2=off for maintenance) 
Line length (km) 
Area number 
Owner number 
Zero sequence resistance (pu) 
Zero Sequence reactance (pu) 
Zero Sequence chargind (pu) 
Branch name (up to 23 characters) 
Bus (nnnnnn.ii) controlled by Line shunt at From terminal 
Control status of the Line shunt at From terminal (0 or 1) 
Bus (nnnnnn.ii) controlled by Line shunt at To terminal 
Control status of the Line shunt at To terminal (0 or 1) 
Bus From line shunt1 status (0 or 1) 
GshtF1 (real part of shunt1 element connected to Bus From in pu) 
BshtF1 (imaginary part of shunt1 element connected to Bus From in pu) 
Bus To line shunt1 status (0 or 1) 
GshtT1 (real part of shunt1 element connected to Bus To in pu) 
BshtT1 (imaginary part of shunt1 element connected to Bus To in pu) 
Bus From line shunt2 status (0 or 1) 
GshtF2 (real part of shunt2 element connected to Bus From in pu) 
BshtF2 (imaginary part of shunt2 element connected to Bus From in pu) 
Bus To line shunt2 status (0 or 1) 
GshtT2 (real part of shun2t element connected to Bus To in pu)
BshtT2 (imaginary part of shun2t element connected to Bus To in pu) 
Bus From line shunt3 status (0 or 1) 
GshtF3 (real part of shunt3 element connected to Bus From in pu) 
BshtF3 (imaginary part of shunt3 element connected to Bus From in pu) 
Bus To line shunt3 status (0 or 1) 
GshtT3 (real part of shunt element connected to Bus To in pu) 
BshtT3 (imaginary part of shunt element connected to Bus To in pu)

# Additional Line Shunt Data

## Version 5 

Bus From identification in the form nnnnnn.ii 
Bus To identification in the form nnnnnn.ii 
Circuit identifier (2 characters) 
Bus From line shunt status (0 or 1) 
GshtF (real part of shunt element connected to Bus From in pu) 
BshtF (imaginary part of shunt element connected to Bus From in pu) 
Bus To line shunt status (0 or 1) 
GshtT (real part of shunt element connected to Bus To in pu) 
BshtT (imaginary part of shunt element connected to Bus To in pu) 

# Transformer Data

## Version 5 

Bus From identification in the form nnnnnn.ii 
Bus To identification in the form nnnnnn.ii 
Circuit identifier 
Transformer type (1=fixed tap; 2=OLTC; 3=SOLTC) 
Resistance in pu 
Reactance in pu 
Limit 1 in MVA 
Limit 2 in MVA 
Limit 3 in MVA 
Tap in pu 
Phase shift in degrees 
Controlled bus identification in the form nnnnnn.ii 
Remote controlled bus side (1=Bus From side; 2=Bus To side) 
Upper limit of tap range 
Lower limit of tap range 
Upper limit of controlled voltage (or MW) range in pu (or MW) 
Lower limit of controlled voltage (or MW) range in pu (or MW) 
Tap step in pu 
Transformer "Bus From" breaker status (0=off; 1=on; 2=off for maintenance) 
Transformer "Bus To" breaker status (0=off; 1=on; 2=off for maintenance) 
Control status (0=off; 1=on) 
Area number 
Owner number
Connection type (00 = not defined; 11 = ground star – ground star; 12 = ground star – star; 13 = ground star – delta; 21 = star – ground star; 22 = star – star; 23 = star – delta; 31 = delta – ground star;32 = delta – star; 33 = delta - delta) 
Branch name (up to 23 characters)

## Version 6 

Version 6 uses on record for transformer identification and one additional record for two winding 
transformer or three additional records for each winding 

### First Record 

Bus 1 identification in the form nnnnnn.ii 
Bus 2 identification in the form nnnnnn.ii 
Bus 3 identification in the form nnnnnn.ii or zero for two winding transformer 
Circuit identifier (2 characters) 
Magnetizing conductance (pu on system base) 
Magnetizing susceptance (pu on system base) 
Winding 1 status (0 or 1) 
Winding 2 status (0 or 1) 
Winding 3 status (0 or 1) 
Voltage at the star point for three winding transformers (pu) 
Angle at the star point for three winding transformers (deg) 
Area number 
Owner number  
Transformer name (up to 23 characters) 

### Additional Records (1 for 2-winding or 3 for 3-winding transformer) 

Transformer type (0 = fixed tap; 1 = OLTC; 2 = PHSHFT) 
Rp - Positive sequence resistance in pu (star equivalent for 3-winding transformer)
Xp - Positive sequence reactance in pu (star equivalent for 3-winding transformer) 
Tap in pu 
Phase shift (in degrees) 
Limit 1 in MVA 
Limit 2 in MVA 
Limit 3 in MVA 
Control status (0 = off;  1 = on) 
Controlled bus identification in the form nnnnnn.ii 
Remote controlled bus side (1=Bus From side; 2=Bus To side) 
Upper limit of tap range 
Lower limit of tap range 
Upper limit of controlled voltage (or MW) range in pu (or MW) 
Lower limit of controlled voltage (or MW) range in pu (or MW) 
Tap step in pu 
NCT (number of Impedance Correction Table)
Connection type (00 = not defined; 11 = ground star – ground star; 12 = ground star – star; 13 = ground star – delta; 21 = star – ground star; 22 = star – star; 23 = star – delta; 31 = delta – ground star; 32 = delta – star; 33 = delta – delta; 14 = ground star – delta with grounding transformer; 41 – delta with grounding transformer – ground star; 55 – ground star – ground star with grounding resistance) 
Rn - Zero sequence resistance (pu) – If null, Rn = Rp 
Xn - Zero sequence reactance (pu) – If null, Xn = Xp 
From side zero sequence grounding conductance (pu)1 
From side zero sequence grounding susceptance (pu)1 
To (or star point) zero sequence grounding conductance (pu)1 
To (or star point) zero sequence grounding susceptance (pu)1 
1 – It is used according to the connection type. 

# Series Capacitor Data

From Bus identification in the form nnnnnn.ii 
To Bus identification in the form nnnnnn.ii 
Circuit identifier 
Resistance in pu 
Reactance in pu 
Limit 1 in MVA 
Limit 2 in MVA 
Limit 3 in MVA 
Bus From shunt status (0 or 1) 
GshtF (real part of shunt element connected to Bus From in pu) 
BshtF (imaginary part of shunt element connected to Bus From in pu) 
Bus To shunt status (0 or 1) 
GshtT (real part of shunt element connected to Bus To in pu) 
BshtT (imaginary part of shunt element connected to Bus To in pu) 
"From" bus breaker status (0=off; 1=on; 2=off for maintenance) 
"To" bus breaker status (0=off; 1=on; 2=off for maintenance) 
Owner number 
Branch name (up to 23 characters) 

" If the From or To bus breaker (or both) status is off (0 or 2), it means that the series capacitor is 
bypassed, instead of open circuit."

# DC Link Data 

HVDC CONTROL 

## Version 5 

Pole ID (number) 
Area number 
Zone number 
Control mode (0= off; 1=Power at inverter; 2=Current at inverter; 3=Power at rectifier; 
4=Current at rectifier) 
DC line resistance in ohms 
DC control set value (power in MW or current in A, zero means out of service) 
Scheduled voltage (kV) 
Voltage threshold to convert control mode from power to current in kV 
Current margin for inverter control in pu 
Compounding resistance 
Nominal DC Voltage (kV) 
Nominal DC Power (MW) 
Pole name (up to 23 characters)

## Version 6

Pole ID (number) 
Area number 
Zone number 
Control mode (1=Power at inverter; 2=Current at inverter; 3=Power at rectifier; 
4=Current at rectifier) 
DC line resistance in ohms 
DC control set value (power in MW or current in A, zero means out of service) 
Scheduled voltage (kV) 
Voltage threshold to convert control mode from power to current in kV
Current margin for inverter control in pu 
Status (0 or 1) 
Nominal DC Voltage (kV) 
Nominal DC Power (MW) 
Pole name (up to 23 characters)

### RECTIFIER 

Bus identification in the form nnnnnn.ii 
Number of converters in series connection 
Specified firing angle in degrees 
Minimum firing angle in degrees 
Commutation transformer resistance in ohms 
Commutation transformer reactance in ohms 
Base voltage phase-phase of converter transformer secondary side in kV (in this case 
the transformer turns ration must be 1), or Base voltage phase-phase of converter 
transformer primary side in kV (in this case the transformer turns ratio is secondary 
kV divided by primary kV) 
Transformer turns ratio 
Transformer Tap 
Upper limit of transformer tap range 
Lower limit of transformer tap range 
Transformer tap step (positive) 
Commutating capacitor reactance per bridge in ohms 
Converter name 

### INVERTER 

Bus identification in the form nnnnnn.ii 
Number of converters in series connection 
Specified extinction angle in degrees 
Minimum extinction angle in degrees 
Commutation transformer resistance in ohms 
Commutation transformer reactance in ohms 
Base voltage phase-phase of converter transformer secondary side in kV 
Transformer turns ratio 
Transformer Tap 
Upper limit of inverter transformer tap range 
Lower limit of inverter transformer tap range 
Transformer tap step (positive) 
Commutating capacitor reactance per bridge in ohms 
Converter name 

# Multiterminal VSC Link Data 

The following records are required per VSC link.. 
- One header record. 
- One record per convertor. 
- One record with a 0 (zero) entry to indicate end of converter records. 
-One record per DC transmission line. 
- One record with a 0 (zero) entry to indicate end of DC transmission line records. 

# Area Data 

Area Number 
Area swing bus identification in the form nnnnnn.ii 
Net interchange in MW 
Area name (up to 30 characters)

# Zone Data 

Zone number 
Zone name (up to 12 characters) 

# Owner number 

Owner Data 
Owner name (up to 9 characters) 

# Substation number 

Substation Data 
Substation name (up to12 characters) 
Latitude (dd.mm.ss) 
Longitude (dd.mm.ss)

# Transformer Impedance Correction Table 

Transformer correction table number  
Tap (phase shift) value
Correction factor (>= 0) (Can be repeated up to 11 times)

# Transmission Line Mutual Impedances 

From bus of transmission line 1 (nnnnnn.ii) 
To bus of transmission line 1 (nnnnnn.ii) 
ID of transmission line 1 (Up to 2 characters) 
Start distance of mutual section from From bus of transmission line 1 (%) 
Final distance of mutual section from From bus of transmission line 1 (%) 
From bus of transmission line 1 (nnnnnn.ii) 
To bus of transmission line 1 (nnnnnn.ii) 
ID of transmission line 1 (Up to 2 characters) 
Start distance of mutual section from From bus of transmission line 2 (%) 
Final distance of mutual section from From bus of transmission line 2 (%) 
Mutual resistance (pu) 
Mutual reactance (pu)

# Induction Motor 

Bus (nnnnnn.ii) 
To bus of transmission line 1 (nnnnnn.ii) 
ID (Up to 2 characters) 
Status (0 = off, 1 = on) 
Count: number o units 
MVA of 1 unit 
MW: active power consumption (negative for generation) 
Mvar: reactive power consumption (positive is inductive)
Rs: stator resistance (pu in machine MVA) 
Xs: stator reactance (pu in machine MVA 
Xm: magnetizing reactance (pu in machine MVA) 
Rr1: rotor resistance (pu in machine MVA) 
Xr1: rotor reactance (pu in machine MVA) 
Rr2: rotor resistance (pu in machine MVA) 
Xr2: rotor reactance (pu in machine MVA) 
S10: saturation at 1.0 p.u. 
S12: saturation at 1.2 p.u. 
Grnd: use ‘G’ for grounded star stator winding, or ‘0’ otherwise 
Standard (0: custom, A-E: NEMA, N or H: IEC) – used for setting default parameters 
Owner number 
Motor name (up to 12 characters) 

"Notes: 1) The current program version accepts only one aggregated model per bus. 2)For single cage representation, Rr2 and Xr2 are zero."

# Breaker Configuration 

Bus number (nnnnnn)  
First Node ID (ii)  
Second Node ID (ii) 
Third Node ID (ii)  
Fourth Node ID (ii)  

"Each record contains the node IDs corresponding to the series connected breaker’s terminals."

# FACTS Data 

## Version 6 

Name (up to 20 characters)  
Send bus number (nnnnnn.nn)  
Terminal bus number (nnnnnn.nn)  
Type number (STATCOM, SSSC, UPFC, TCSC, etc.) 
Pref (MW)  
Qref (Mvar)  
Vref (p.u.)  
Ishtmax (MVA at 1. P.u.) maximum shunt current  
Ptrmax (MW) maximum power transfer between shunt and series converter  
Vtmin (p.u.) minimum terminal bus voltage or Xcmin (p.u.) <=0 for TCSC  
Vtmax (p.u.) maximum terminal bus voltage or Xcmax (p.u.) >=0 for TCSC  
Vcmax (p.u.) maximum series converter voltage  
Icmax (p.u.) maximum series current  
Xc (p.u.) series reactance  
Status (0 or 1)   
Owner number  
Types supported: 
    2 - STATCOM 
    3 - SSSC in active power control 
    4 - UPFC 
    5 - UPFC2 (combination of STATCOM and SSSC; no power transfer) 
    6 - TCSC 

"Pref is considered for all FACTS but STATCOM."
"Qref is considered for UPFC only."
"Vref is considered for STATCOM, UPFC and UPFC2."

## Version 7 
Name (up to 20 characters)  
Send bus number (nnnnnn.nn)  
Terminal bus number (nnnnnn.nn)  
Circuit ID 
Type number (STATCOM, SSSC, UPFC, TCSC, etc.) 
Pref (MW)  
Qref (Mvar)  
Vref (p.u.)  
Ishtmax (MVA at 1. P.u.) maximum shunt current  
Ptrmax (MW) maximum power transfer between shunt and series converter  
Vtmin (p.u.) minimum terminal bus voltage or Xcmin (p.u.) <=0 for TCSC  
Vtmax (p.u.) maximum terminal bus voltage or Xcmax (p.u.) >=0 for TCSC  
Vcmax (p.u.) maximum series converter voltage  
Vcmin (p.u.) minimum series converter voltage  
Icmax (p.u.) maximum series current  
Icemr (p.u.) emergency series current  
Icmin (p.u.) maximum series current  
Xc (p.u.) series reactance  
Droop (p.u.) volt / amper ratio  
Status (0 or 1)   
Owner number  
Inductive entry current control mode threshold  
Inductive exit current-control threshold  
Capacitive entry current control mode threshold  
Capacitive exit current-control threshold 
Types supported:
    2 - STATCOM 
    3 - SSSC in active power control 
    4 - UPFC 
    5 - UPFC2 (combination of STATCOM and SSSC; no power transfer) 
    6 - TCSC
    7 - SSSC in active current control
    8 - SV in reactance control
    9 - SV in voltage control 
    10 - SV in current control 
    11 - SV in monitoring mode

"Pref is considered for all FACTS but STATCOM."
"Qref is considered for UPFC only."
"Vref is considered for STATCOM, UPFC and UPFC2."