# ANAREDE NTW format reference

This document describes the component blocks and field order used by ANAREDE
`.NTW` files. Fields are listed in record order. Version-specific layouts are
identified where the format differs between versions.

## Bus data

| # | Description |
| ---: | --- |
| 1 | Bus identification in the form `nnnnnn.ii`. |
| 2 | Bus name (up to 12 characters). |
| 3 | Base voltage in kV. |
| 4 | Bus type: `0` = load; `1` = load with voltage limits; `2` = generation; `3` = swing; `4` = de-energized. |
| 5 | Bus shunt `(Gsht + jBsht)` status: `0` = off; `1` = on. |
| 6 | `Gsht`: real part of the shunt element in MW for the base voltage. |
| 7 | `Bsht`: imaginary part of the shunt element in Mvar for the base voltage. |
| 8 | Bus area number. |
| 9 | Bus zone number. |
| 10 | Bus voltage magnitude in pu. |
| 11 | Bus voltage angle in degrees. |
| 12 | Voltage threshold for overvoltage detection in pu. |
| 13 | Voltage threshold for undervoltage detection in pu. |
| 14 | Voltage threshold for emergency overvoltage detection in pu. |
| 15 | Voltage threshold for emergency undervoltage detection in pu. |
| 16 | Bus owner number. |
| 17 | Substation number. |
| 18 | Bus scheme: `0` = not defined; `1` = single; `2` = main and auxiliary; `3` = double bus single breaker; `4` = double bus double breaker; `5` = ring bus; `6` = breaker and half. |

## Load data

| # | Description |
| ---: | --- |
| 1 | Bus identification in the form `nnnnnn.ii`. |
| 2 | Load identifier (2 characters). |
| 3 | Load status: `0` = off; `1` = on. |
| 4 | MW considered as constant power in the ZIP model. |
| 5 | Mvar considered as constant power in the ZIP model. |
| 6 | MW considered as constant current in the ZIP model. |
| 7 | Mvar considered as constant current in the ZIP model. |
| 8 | MW considered as constant impedance in the ZIP model. |
| 9 | Mvar considered as constant impedance in the ZIP model. |
| 10 | Load owner number. |
| 11 | Zero-sequence resistance (pu). |
| 12 | Zero-sequence reactance (pu). |
| 13 | Load name. |

## Generator data

### Version 5

| # | Description |
| ---: | --- |
| 1 | Bus identification in the form `nnnnnn.ii`. |
| 2 | Generator identifier (2 characters). |
| 3 | Generation in MW. |
| 4 | Generation in Mvar. |
| 5 | Maximum generation in Mvar. |
| 6 | Minimum generation in Mvar. |
| 7 | Specified controlled voltage in pu. |
| 8 | Controlled bus identification in the form `nnnnnn.ii`. |
| 9 | Generator power base in MVA. |
| 10 | Step-up transformer resistance in pu (system MVA base). |
| 11 | Step-up transformer reactance in pu (system MVA base). |
| 12 | Step-up transformer tap. |
| 13 | Generator status: `0` = off; `1` = on. |
| 14 | Participation factor for remote bus voltage control in %. |
| 15 | Maximum generation in MW. |
| 16 | Minimum generation in MW. |
| 17 | Group number identifying similar machines in the same power plant. |
| 18 | Unavailable: `0` = available for dispatch; `1` = unavailable. |
| 19 | Owner number. |
| 20 | Connection to ground: `1` = grounded star; `2` = star; `3` = delta. |
| 21 | Positive-sequence resistance in pu of the system MVA base. |
| 22 | Positive-sequence reactance in pu of the system MVA base. |
| 23 | Zero-sequence resistance in pu of the system MVA base. |
| 24 | Zero-sequence reactance in pu of the system MVA base. |
| 25 | Grounding resistance in pu of the system MVA base. |
| 26 | Grounding reactance in pu of the system MVA base. |
| 27 | Generator unit name (up to 20 characters). |
| 28 | Generator quadrature reactance in pu of the system MVA base. |
| 29 | Stator current service factor (`1` to `1.4`). |
| 30 | Maximum loading angle in degrees (`60` to `85`). |

### Version 6

| # | Description |
| ---: | --- |
| 1 | Bus identification in the form `nnnnnn.ii`. |
| 2 | Generator identifier (2 characters). |
| 3 | Generation in MW. |
| 4 | Generation in Mvar. |
| 5 | Maximum generation in Mvar. |
| 6 | Minimum generation in Mvar. |
| 7 | Specified controlled voltage in pu. |
| 8 | Controlled bus identification in the form `nnnnnn.ii`. |
| 9 | Generator power base in MVA. |
| 10 | Step-up transformer resistance in pu. |
| 11 | Step-up transformer reactance in pu. |
| 12 | Step-up transformer tap. |
| 13 | Generator status: `0` = off; `1` = on. |
| 14 | Participation factor for remote bus voltage control in %. |
| 15 | Maximum generation in MW. |
| 16 | Minimum generation in MW. |
| 17 | Group number identifying similar machines in the same power plant. |
| 18 | Unavailable: `0` = available for dispatch; `1` = unavailable. |
| 19 | Owner number. |
| 20 | Connection to ground: `1` = grounded star; `2` = star; `3` = delta. |
| 21 | Positive-sequence resistance (pu) for non-full-converter sources. Recommended: stator resistance. For full-converter sources, this is the maximum short-circuit current. |
| 22 | Positive-sequence reactance (pu) for non-full-converter sources. Recommended: `x''d`. For full-converter sources, this is the short-circuit power factor. |
| 23 | Negative-sequence resistance (pu). Recommended: stator resistance. |
| 24 | Negative-sequence reactance (pu). Recommended: `(x''d + x''q) / 2`. |
| 25 | Zero-sequence resistance (pu). |
| 26 | Zero-sequence reactance (pu). |
| 27 | Grounding resistance (pu). |
| 28 | Grounding reactance (pu). |
| 29 | Quadrature reactance (pu), used for capability computation. |
| 30 | Stator current service factor (`1` to `1.4`), used for capability computation. |
| 31 | Maximum loading angle in degrees (`60` to `85`), used for capability computation. |
| 32 | Generator type: `0` = hydro; `1` = steam; `2` = gas; `3` = wind type 1; `4` = wind type 2; `5` = wind type 3; `6` = wind type 4; `7` = PV. |
| 33 | Generator unit name (up to 20 characters). |

## Shunt data

| # | Description |
| ---: | --- |
| 1 | Bus identification in the form `nnnnnn.ii`. |
| 2 | Control mode: `0` = fixed; `1` = discrete; `2` = continuous or SVC. |
| 3 | Voltage-control range upper bound for discrete mode, or specified voltage for continuous mode, in pu. |
| 4 | Voltage-control range lower bound for discrete mode in pu. Not used for continuous control mode. |
| 5 | Controlled bus identification in the form `nnnnnn.ii`. |
| 6 | Initial shunt admittance in Mvar, considering a 1 pu bus voltage. |
| 7 | Global status (`0` or `1`). |
| 8 | Element status: `0` = maintenance; `1` = available. Repeated up to 8 times. |
| 9 | Number of elements. Repeated up to 8 times. |
| 10 | Element size in Mvar. Repeated up to 8 times. |
| 11 | Zero-sequence impedance (pu). Repeated up to 8 times. |

## Transmission line data

### Version 5

| # | Description |
| ---: | --- |
| 1 | From-bus identification in the form `nnnnnn.ii`. |
| 2 | To-bus identification in the form `nnnnnn.ii`. |
| 3 | Circuit identifier (2 characters). |
| 4 | Series resistance in pu. |
| 5 | Series reactance in pu. |
| 6 | Total line charging in Mvar. |
| 7 | Limit 1 in MVA. |
| 8 | Limit 2 in MVA. |
| 9 | Limit 3 in MVA. |
| 10 | From-bus line shunt status (`0` or `1`). |
| 11 | `GshtF`: real part of the shunt element connected to the from bus in pu. |
| 12 | `BshtF`: imaginary part of the shunt element connected to the from bus in pu. |
| 13 | To-bus line shunt status (`0` or `1`). |
| 14 | `GshtT`: real part of the shunt element connected to the to bus in pu. |
| 15 | `BshtT`: imaginary part of the shunt element connected to the to bus in pu. |
| 16 | From-bus line breaker status: `0` = off; `1` = on; `2` = off for maintenance. |
| 17 | To-bus line breaker status: `0` = off; `1` = on; `2` = off for maintenance. |
| 18 | Line length in km. |
| 19 | Area number. |
| 20 | Owner number. |
| 21 | Zero-sequence resistance in pu. |
| 22 | Zero-sequence reactance in pu. |
| 23 | Branch name (up to 23 characters). |
| 24 | Bus controlled by the line shunt at the from terminal. |
| 25 | Control status of the line shunt at the from terminal (`0` or `1`). |
| 26 | Bus controlled by the line shunt at the to terminal. |
| 27 | Control status of the line shunt at the to terminal (`0` or `1`). |

### Version 6

| # | Description |
| ---: | --- |
| 1 | From-bus identification in the form `nnnnnn.ii`. |
| 2 | To-bus identification in the form `nnnnnn.ii`. |
| 3 | Circuit identifier (2 characters). |
| 4 | Series resistance in pu. |
| 5 | Series reactance in pu. |
| 6 | Total line charging in Mvar. |
| 7 | Limit 1 in MVA. |
| 8 | Limit 2 in MVA. |
| 9 | Limit 3 in MVA. |
| 10 | From-bus line breaker status: `0` = off; `1` = on; `2` = off for maintenance. |
| 11 | To-bus line breaker status: `0` = off; `1` = on; `2` = off for maintenance. |
| 12 | Line length in km. |
| 13 | Area number. |
| 14 | Owner number. |
| 15 | Zero-sequence resistance in pu. |
| 16 | Zero-sequence reactance in pu. |
| 17 | Zero-sequence charging in pu. |
| 18 | Branch name (up to 23 characters). |
| 19 | Bus controlled by the line shunt at the from terminal. |
| 20 | Control status of the line shunt at the from terminal (`0` or `1`). |
| 21 | Bus controlled by the line shunt at the to terminal. |
| 22 | Control status of the line shunt at the to terminal (`0` or `1`). |
| 23 | From-bus line shunt 1 status (`0` or `1`). |
| 24 | `GshtF1`: real part of shunt 1 connected to the from bus in pu. |
| 25 | `BshtF1`: imaginary part of shunt 1 connected to the from bus in pu. |
| 26 | To-bus line shunt 1 status (`0` or `1`). |
| 27 | `GshtT1`: real part of shunt 1 connected to the to bus in pu. |
| 28 | `BshtT1`: imaginary part of shunt 1 connected to the to bus in pu. |
| 29 | From-bus line shunt 2 status (`0` or `1`). |
| 30 | `GshtF2`: real part of shunt 2 connected to the from bus in pu. |
| 31 | `BshtF2`: imaginary part of shunt 2 connected to the from bus in pu. |
| 32 | To-bus line shunt 2 status (`0` or `1`). |
| 33 | `GshtT2`: real part of shunt 2 connected to the to bus in pu. |
| 34 | `BshtT2`: imaginary part of shunt 2 connected to the to bus in pu. |
| 35 | From-bus line shunt 3 status (`0` or `1`). |
| 36 | `GshtF3`: real part of shunt 3 connected to the from bus in pu. |
| 37 | `BshtF3`: imaginary part of shunt 3 connected to the from bus in pu. |
| 38 | To-bus line shunt 3 status (`0` or `1`). |
| 39 | `GshtT3`: real part of shunt 3 connected to the to bus in pu. |
| 40 | `BshtT3`: imaginary part of shunt 3 connected to the to bus in pu. |

## Additional line shunt data

### Version 5

| # | Description |
| ---: | --- |
| 1 | From-bus identification in the form `nnnnnn.ii`. |
| 2 | To-bus identification in the form `nnnnnn.ii`. |
| 3 | Circuit identifier (2 characters). |
| 4 | From-bus line shunt status (`0` or `1`). |
| 5 | `GshtF`: real part of the shunt element connected to the from bus in pu. |
| 6 | `BshtF`: imaginary part of the shunt element connected to the from bus in pu. |
| 7 | To-bus line shunt status (`0` or `1`). |
| 8 | `GshtT`: real part of the shunt element connected to the to bus in pu. |
| 9 | `BshtT`: imaginary part of the shunt element connected to the to bus in pu. |

## Transformer data

### Version 5

| # | Description |
| ---: | --- |
| 1 | From-bus identification in the form `nnnnnn.ii`. |
| 2 | To-bus identification in the form `nnnnnn.ii`. |
| 3 | Circuit identifier. |
| 4 | Transformer type: `1` = fixed tap; `2` = OLTC; `3` = SOLTC. |
| 5 | Resistance in pu. |
| 6 | Reactance in pu. |
| 7 | Limit 1 in MVA. |
| 8 | Limit 2 in MVA. |
| 9 | Limit 3 in MVA. |
| 10 | Tap in pu. |
| 11 | Phase shift in degrees. |
| 12 | Controlled bus identification in the form `nnnnnn.ii`. |
| 13 | Remote controlled bus side: `1` = from-bus side; `2` = to-bus side. |
| 14 | Upper limit of the tap range. |
| 15 | Lower limit of the tap range. |
| 16 | Upper limit of the controlled voltage or MW range in pu or MW. |
| 17 | Lower limit of the controlled voltage or MW range in pu or MW. |
| 18 | Tap step in pu. |
| 19 | Transformer from-bus breaker status: `0` = off; `1` = on; `2` = off for maintenance. |
| 20 | Transformer to-bus breaker status: `0` = off; `1` = on; `2` = off for maintenance. |
| 21 | Control status: `0` = off; `1` = on. |
| 22 | Area number. |
| 23 | Owner number. |
| 24 | Connection type: `00` = not defined; `11` = grounded star–grounded star; `12` = grounded star–star; `13` = grounded star–delta; `21` = star–grounded star; `22` = star–star; `23` = star–delta; `31` = delta–grounded star; `32` = delta–star; `33` = delta–delta. |
| 25 | Branch name (up to 23 characters). |

### Version 6

Version 6 uses one identification record and one additional record for a
 two-winding transformer, or three additional records for a three-winding
 transformer.

#### First record

| # | Description |
| ---: | --- |
| 1 | Bus 1 identification in the form `nnnnnn.ii`. |
| 2 | Bus 2 identification in the form `nnnnnn.ii`. |
| 3 | Bus 3 identification in the form `nnnnnn.ii`, or zero for a two-winding transformer. |
| 4 | Circuit identifier (2 characters). |
| 5 | Magnetizing conductance in pu on the system base. |
| 6 | Magnetizing susceptance in pu on the system base. |
| 7 | Winding 1 status (`0` or `1`). |
| 8 | Winding 2 status (`0` or `1`). |
| 9 | Winding 3 status (`0` or `1`). |
| 10 | Voltage at the star point for three-winding transformers in pu. |
| 11 | Angle at the star point for three-winding transformers in degrees. |
| 12 | Area number. |
| 13 | Owner number. |
| 14 | Transformer name (up to 23 characters). |

#### Additional records

One additional record is used for a two-winding transformer and three for a
three-winding transformer.

| # | Description |
| ---: | --- |
| 1 | Transformer type: `0` = fixed tap; `1` = OLTC; `2` = PHSHFT. |
| 2 | `Rp`: positive-sequence resistance in pu (star equivalent for a three-winding transformer). |
| 3 | `Xp`: positive-sequence reactance in pu (star equivalent for a three-winding transformer). |
| 4 | Tap in pu. |
| 5 | Phase shift in degrees. |
| 6 | Limit 1 in MVA. |
| 7 | Limit 2 in MVA. |
| 8 | Limit 3 in MVA. |
| 9 | Control status: `0` = off; `1` = on. |
| 10 | Controlled bus identification in the form `nnnnnn.ii`. |
| 11 | Remote controlled bus side: `1` = from-bus side; `2` = to-bus side. |
| 12 | Upper limit of the tap range. |
| 13 | Lower limit of the tap range. |
| 14 | Upper limit of the controlled voltage or MW range in pu or MW. |
| 15 | Lower limit of the controlled voltage or MW range in pu or MW. |
| 16 | Tap step in pu. |
| 17 | NCT: number of the impedance correction table. |
| 18 | Connection type: `00` = not defined; `11` = grounded star–grounded star; `12` = grounded star–star; `13` = grounded star–delta; `21` = star–grounded star; `22` = star–star; `23` = star–delta; `31` = delta–grounded star; `32` = delta–star; `33` = delta–delta; `14` = grounded star–delta with grounding transformer; `41` = delta with grounding transformer–grounded star; `55` = grounded star–grounded star with grounding resistance. |
| 19 | `Rn`: zero-sequence resistance in pu. If null, `Rn = Rp`. |
| 20 | `Xn`: zero-sequence reactance in pu. If null, `Xn = Xp`. |
| 21 | From-side zero-sequence grounding conductance in pu. |
| 22 | From-side zero-sequence grounding susceptance in pu. |
| 23 | To-side or star-point zero-sequence grounding conductance in pu. |
| 24 | To-side or star-point zero-sequence grounding susceptance in pu. |

> The grounding fields are used according to the connection type.

## Series capacitor data

| # | Description |
| ---: | --- |
| 1 | From-bus identification in the form `nnnnnn.ii`. |
| 2 | To-bus identification in the form `nnnnnn.ii`. |
| 3 | Circuit identifier. |
| 4 | Resistance in pu. |
| 5 | Reactance in pu. |
| 6 | Limit 1 in MVA. |
| 7 | Limit 2 in MVA. |
| 8 | Limit 3 in MVA. |
| 9 | From-bus shunt status (`0` or `1`). |
| 10 | `GshtF`: real part of the shunt element connected to the from bus in pu. |
| 11 | `BshtF`: imaginary part of the shunt element connected to the from bus in pu. |
| 12 | To-bus shunt status (`0` or `1`). |
| 13 | `GshtT`: real part of the shunt element connected to the to bus in pu. |
| 14 | `BshtT`: imaginary part of the shunt element connected to the to bus in pu. |
| 15 | From-bus breaker status: `0` = off; `1` = on; `2` = off for maintenance. |
| 16 | To-bus breaker status: `0` = off; `1` = on; `2` = off for maintenance. |
| 17 | Owner number. |
| 18 | Branch name (up to 23 characters). |

> If the from-bus or to-bus breaker status (or both) is off (`0` or `2`), the
> series capacitor is bypassed rather than treated as an open circuit.

## DC link data

### HVDC control

#### Version 5

| # | Description |
| ---: | --- |
| 1 | Pole ID (number). |
| 2 | Area number. |
| 3 | Zone number. |
| 4 | Control mode: `0` = off; `1` = power at inverter; `2` = current at inverter; `3` = power at rectifier; `4` = current at rectifier. |
| 5 | DC line resistance in ohms. |
| 6 | DC control set value (power in MW or current in A; zero means out of service). |
| 7 | Scheduled voltage in kV. |
| 8 | Voltage threshold for converting control mode from power to current in kV. |
| 9 | Current margin for inverter control in pu. |
| 10 | Compounding resistance. |
| 11 | Nominal DC voltage in kV. |
| 12 | Nominal DC power in MW. |
| 13 | Pole name (up to 23 characters). |

#### Version 6

| # | Description |
| ---: | --- |
| 1 | Pole ID (number). |
| 2 | Area number. |
| 3 | Zone number. |
| 4 | Control mode: `1` = power at inverter; `2` = current at inverter; `3` = power at rectifier; `4` = current at rectifier. |
| 5 | DC line resistance in ohms. |
| 6 | DC control set value (power in MW or current in A; zero means out of service). |
| 7 | Scheduled voltage in kV. |
| 8 | Voltage threshold for converting control mode from power to current in kV. |
| 9 | Current margin for inverter control in pu. |
| 10 | Status (`0` or `1`). |
| 11 | Nominal DC voltage in kV. |
| 12 | Nominal DC power in MW. |
| 13 | Pole name (up to 23 characters). |

### Rectifier

| # | Description |
| ---: | --- |
| 1 | Bus identification in the form `nnnnnn.ii`. |
| 2 | Number of converters in series connection. |
| 3 | Specified firing angle in degrees. |
| 4 | Minimum firing angle in degrees. |
| 5 | Commutation transformer resistance in ohms. |
| 6 | Commutation transformer reactance in ohms. |
| 7 | Base phase-to-phase voltage of the converter transformer secondary side in kV. If this is the transformer base, the turns ratio must be 1; otherwise it is the primary-side base and the turns ratio is secondary kV divided by primary kV. |
| 8 | Transformer turns ratio. |
| 9 | Transformer tap. |
| 10 | Upper limit of the transformer tap range. |
| 11 | Lower limit of the transformer tap range. |
| 12 | Transformer tap step (positive). |
| 13 | Commuting capacitor reactance per bridge in ohms. |
| 14 | Converter name. |

### Inverter

| # | Description |
| ---: | --- |
| 1 | Bus identification in the form `nnnnnn.ii`. |
| 2 | Number of converters in series connection. |
| 3 | Specified extinction angle in degrees. |
| 4 | Minimum extinction angle in degrees. |
| 5 | Commutation transformer resistance in ohms. |
| 6 | Commutation transformer reactance in ohms. |
| 7 | Base phase-to-phase voltage of the converter transformer secondary side in kV. |
| 8 | Transformer turns ratio. |
| 9 | Transformer tap. |
| 10 | Upper limit of the inverter transformer tap range. |
| 11 | Lower limit of the inverter transformer tap range. |
| 12 | Transformer tap step (positive). |
| 13 | Commuting capacitor reactance per bridge in ohms. |
| 14 | Converter name. |

## Multiterminal VSC link data

The following records are required for each VSC link:

1. One header record.
2. One record per converter.
3. One record containing `0` to indicate the end of converter records.
4. One record per DC transmission line.
5. One record containing `0` to indicate the end of DC transmission-line records.

## Area data

| # | Description |
| ---: | --- |
| 1 | Area number. |
| 2 | Area swing-bus identification in the form `nnnnnn.ii`. |
| 3 | Net interchange in MW. |
| 4 | Area name (up to 30 characters). |

## Zone data

| # | Description |
| ---: | --- |
| 1 | Zone number. |
| 2 | Zone name (up to 12 characters). |

## Owner data

| # | Description |
| ---: | --- |
| 1 | Owner number. |
| 2 | Owner name (up to 9 characters). |

## Substation data

| # | Description |
| ---: | --- |
| 1 | Substation number. |
| 2 | Substation name (up to 12 characters). |
| 3 | Latitude (`dd.mm.ss`). |
| 4 | Longitude (`dd.mm.ss`). |

## Transformer impedance correction table

| # | Description |
| ---: | --- |
| 1 | Transformer correction table number. |
| 2 | Tap or phase-shift value. |
| 3 | Correction factor (greater than or equal to zero). May be repeated up to 11 times. |

## Transmission-line mutual impedances

| # | Description |
| ---: | --- |
| 1 | From bus of transmission line 1 (`nnnnnn.ii`). |
| 2 | To bus of transmission line 1 (`nnnnnn.ii`). |
| 3 | ID of transmission line 1 (up to 2 characters). |
| 4 | Start distance of the mutual section from the from bus of transmission line 1 (%). |
| 5 | Final distance of the mutual section from the from bus of transmission line 1 (%). |
| 6 | From bus of transmission line 2 (`nnnnnn.ii`). |
| 7 | To bus of transmission line 2 (`nnnnnn.ii`). |
| 8 | ID of transmission line 2 (up to 2 characters). |
| 9 | Start distance of the mutual section from the from bus of transmission line 2 (%). |
| 10 | Final distance of the mutual section from the from bus of transmission line 2 (%). |
| 11 | Mutual resistance in pu. |
| 12 | Mutual reactance in pu. |

## Induction motor data

| # | Description |
| ---: | --- |
| 1 | Bus identification (`nnnnnn.ii`). |
| 2 | To bus of transmission line 1 (`nnnnnn.ii`). |
| 3 | ID (up to 2 characters). |
| 4 | Status: `0` = off; `1` = on. |
| 5 | Count: number of units. |
| 6 | MVA of one unit. |
| 7 | MW: active power consumption (negative for generation). |
| 8 | Mvar: reactive power consumption (positive is inductive). |
| 9 | `Rs`: stator resistance (pu in machine MVA). |
| 10 | `Xs`: stator reactance (pu in machine MVA). |
| 11 | `Xm`: magnetizing reactance (pu in machine MVA). |
| 12 | `Rr1`: rotor resistance (pu in machine MVA). |
| 13 | `Xr1`: rotor reactance (pu in machine MVA). |
| 14 | `Rr2`: rotor resistance (pu in machine MVA). |
| 15 | `Xr2`: rotor reactance (pu in machine MVA). |
| 16 | `S10`: saturation at 1.0 pu. |
| 17 | `S12`: saturation at 1.2 pu. |
| 18 | `Grnd`: use `G` for a grounded-star stator winding, or `0` otherwise. |
| 19 | Standard: `0` = custom; `A`–`E` = NEMA; `N` or `H` = IEC. Used for setting default parameters. |
| 20 | Owner number. |
| 21 | Motor name (up to 12 characters). |

> The current program version accepts only one aggregated model per bus. For a
> single-cage representation, `Rr2` and `Xr2` are zero.

## Breaker configuration data

| # | Description |
| ---: | --- |
| 1 | Bus number (`nnnnnn`). |
| 2 | First node ID (`ii`). |
| 3 | Second node ID (`ii`). |
| 4 | Third node ID (`ii`). |
| 5 | Fourth node ID (`ii`). |

> Each record contains the node IDs corresponding to the terminals of the
> series-connected breaker.

## FACTS data

### Version 6

| # | Description |
| ---: | --- |
| 1 | Name (up to 20 characters). |
| 2 | Sending bus number (`nnnnnn.ii`). |
| 3 | Terminal bus number (`nnnnnn.ii`). |
| 4 | Type number: STATCOM, SSSC, UPFC, TCSC, and others. |
| 5 | `Pref` in MW. |
| 6 | `Qref` in Mvar. |
| 7 | `Vref` in pu. |
| 8 | `Ishtmax`: maximum shunt current in MVA at 1 pu. |
| 9 | `Ptrmax`: maximum power transfer between shunt and series converters in MW. |
| 10 | `Vtmin`: minimum terminal-bus voltage, or `Xcmin` in pu (less than or equal to zero for TCSC). |
| 11 | `Vtmax`: maximum terminal-bus voltage, or `Xcmax` in pu (greater than or equal to zero for TCSC). |
| 12 | `Vcmax`: maximum series-converter voltage in pu. |
| 13 | `Icmax`: maximum series current in pu. |
| 14 | `Xc`: series reactance in pu. |
| 15 | Status (`0` or `1`). |
| 16 | Owner number. |

Supported types:

| Type | Description |
| ---: | --- |
| 2 | STATCOM |
| 3 | SSSC in active-power control |
| 4 | UPFC |
| 5 | UPFC2: combination of STATCOM and SSSC with no power transfer |
| 6 | TCSC |

`Pref` is considered for all FACTS types except STATCOM. `Qref` is considered
for UPFC only. `Vref` is considered for STATCOM, UPFC, and UPFC2.

### Version 7

| # | Description |
| ---: | --- |
| 1 | Name (up to 20 characters). |
| 2 | Sending bus number (`nnnnnn.ii`). |
| 3 | Terminal bus number (`nnnnnn.ii`). |
| 4 | Circuit ID. |
| 5 | Type number: STATCOM, SSSC, UPFC, TCSC, and others. |
| 6 | `Pref` in MW. |
| 7 | `Qref` in Mvar. |
| 8 | `Vref` in pu. |
| 9 | `Ishtmax`: maximum shunt current in MVA at 1 pu. |
| 10 | `Ptrmax`: maximum power transfer between shunt and series converters in MW. |
| 11 | `Vtmin`: minimum terminal-bus voltage, or `Xcmin` in pu (less than or equal to zero for TCSC). |
| 12 | `Vtmax`: maximum terminal-bus voltage, or `Xcmax` in pu (greater than or equal to zero for TCSC). |
| 13 | `Vcmax`: maximum series-converter voltage in pu. |
| 14 | `Vcmin`: minimum series-converter voltage in pu. |
| 15 | `Icmax`: maximum series current in pu. |
| 16 | `Icemr`: emergency series current in pu. |
| 17 | `Icmin`: minimum series current in pu. |
| 18 | `Xc`: series reactance in pu. |
| 19 | `Droop`: voltage/current ratio in pu. |
| 20 | Status (`0` or `1`). |
| 21 | Owner number. |
| 22 | Inductive entry current-control-mode threshold. |
| 23 | Inductive exit current-control-mode threshold. |
| 24 | Capacitive entry current-control-mode threshold. |
| 25 | Capacitive exit current-control-mode threshold. |

Supported types:

| Type | Description |
| ---: | --- |
| 2 | STATCOM |
| 3 | SSSC in active-power control |
| 4 | UPFC |
| 5 | UPFC2: combination of STATCOM and SSSC with no power transfer |
| 6 | TCSC |
| 7 | SSSC in active-current control |
| 8 | SV in reactance control |
| 9 | SV in voltage control |
| 10 | SV in current control |
| 11 | SV in monitoring mode |

`Pref` is considered for all FACTS types except STATCOM. `Qref` is considered
for UPFC only. `Vref` is considered for STATCOM, UPFC, and UPFC2.
