# ANAREDE EVT format reference

This document describes ANAREDE dynamic-contingency files with the `.evt`
extension. The file contains a total simulation time followed by numbered
contingencies. Each contingency contains one or more events.

## File structure

| Record | Format | Description |
| --- | --- | --- |
| 1 | `<total simulation time> /` | Total simulation time in seconds. |
| 2 | `<N> <contingency ID> /` | Contingency number and quoted identifier. The identifier may contain up to 60 characters. |
| 3 | Event records | One or more events belonging to the current contingency. |
| 4 | `-99 /` | Ends the current contingency. |
| 5 | More contingency records | The next contingency begins after the `-99` marker. |
| 6 | `-999 /` | Ends the list of contingencies and the file. |

`N` is the sequential contingency number. Event records are free-format and
contain the following common fields:

| Position | Field | Type | Description |
| ---: | --- | --- | --- |
| 1 | Type | Integer | Event type number. |
| 2 | Bus 1 | Integer or text | Bus 1 number or branch name. A bus name is used when the number is zero. |
| 3 | Bus 2 | Integer or zero | Bus 2 number. Use zero when the event identifies the branch by name or does not require a second bus. |
| 4 | Circuit ID | Character(2) | Parallel circuit identifier. |
| 5 | Parameter 1 | Real | Event-specific real parameter. |
| 6 | Parameter 2 | Real | Event-specific real parameter. |
| 7 | Parameter 3 | Real | Event-specific real parameter. |
| 8 | Bus 1 name | Character(12) | Bus 1 name, used when Bus 1 is zero. |
| 9 | Bus 2 name | Character(12) | Bus 2 name, used when Bus 2 is zero. |
| 10 | Parameter 4 | Real | Event-specific real parameter. |

Branches can be identified by Bus 1, Bus 2, and Circuit ID, or by entering the
branch name as the Bus 1 value. The parser preserves both numeric and text
references.

## Event types

### Type 1: Set branch impedance

Changes the longitudinal impedance of a transmission line or series capacitor
to a specified new value `R + jX`.

| Position | Field | Type | Description |
| ---: | --- | --- | --- |
| 1 | Type | Integer | `1`. |
| 2 | Bus 1 | Integer or text | Bus 1 number or branch name. |
| 3 | Bus 2 | Integer or zero | Bus 2 number, or zero when using a branch name. |
| 4 | Circuit ID | Character(2) | Circuit identifier. |
| 5 | Resistance | Real | New resistance in pu. |
| 6 | Reactance | Real | New reactance in pu. |
| 7 | Event time | Real | Event time in seconds. |
| 8 | Bus 1 name | Character(12) | Bus 1 name when Bus 1 is zero. |
| 9 | Bus 2 name | Character(12) | Bus 2 name when Bus 2 is zero. |
| 10 | Parameter 4 | Real | Reserved; normally zero. |

### Type 2: Change branch impedance

Adds incremental impedance `dR + jdX` to the longitudinal impedance of a
transmission line or series capacitor.

| Position | Field | Type | Description |
| ---: | --- | --- | --- |
| 1 | Type | Integer | `2`. |
| 2 | Bus 1 | Integer or text | Bus 1 number or branch name. |
| 3 | Bus 2 | Integer or zero | Bus 2 number, or zero when using a branch name. |
| 4 | Circuit ID | Character(2) | Circuit identifier. |
| 5 | Incremental resistance | Real | Incremental resistance in pu. |
| 6 | Incremental reactance | Real | Incremental reactance in pu. |
| 7 | Event time | Real | Event time in seconds. |
| 8 | Bus 1 name | Character(12) | Bus 1 name when Bus 1 is zero. |
| 9 | Bus 2 name | Character(12) | Bus 2 name when Bus 2 is zero. |
| 10 | Parameter 4 | Real | Reserved; normally zero. |

### Type 3: Add admittance to a bus

Adds shunt admittance to a bus.

| Position | Field | Type | Description |
| ---: | --- | --- | --- |
| 1 | Type | Integer | `3`. |
| 2 | Bus 1 | Integer or text | Bus number or bus name. |
| 3 | Bus 2 | Integer | `0`. |
| 4 | Circuit ID | Character(2) | `0`. |
| 5 | Conductance | Real | Conductance in pu. |
| 6 | Susceptance | Real | Susceptance in pu. |
| 7 | Event time | Real | Event time in seconds. |
| 8 | Bus 1 name | Character(12) | Bus name when Bus 1 is zero. |
| 9 | Bus 2 name | Character(12) | `0`. |
| 10 | Parameter 4 | Real | `0`. |

### Type 4: Add impedance to a bus

Adds impedance to a bus. The source documentation labels the second electrical
parameter as inductance; the event record stores it in the same real-valued
parameter position.

| Position | Field | Type | Description |
| ---: | --- | --- | --- |
| 1 | Type | Integer | `4`. |
| 2 | Bus 1 | Integer or text | Bus number or bus name. |
| 3 | Bus 2 | Integer | `0`. |
| 4 | Circuit ID | Character(2) | `0`. |
| 5 | Resistance | Real | Resistance in pu. |
| 6 | Inductance | Real | Inductance parameter in pu. |
| 7 | Event time | Real | Event time in seconds. |
| 8 | Bus 1 name | Character(12) | Bus name when Bus 1 is zero. |
| 9 | Bus 2 name | Character(12) | `0`. |
| 10 | Parameter 4 | Real | `0`. |

### Type 5: Remove admittance from a bus

Removes shunt admittance from a bus.

| Position | Field | Type | Description |
| ---: | --- | --- | --- |
| 1 | Type | Integer | `5`. |
| 2 | Bus 1 | Integer or text | Bus number or bus name. |
| 3 | Bus 2 | Integer | `0`. |
| 4 | Circuit ID | Character(2) | `0`. |
| 5 | Conductance | Real | Conductance in pu. |
| 6 | Susceptance | Real | Susceptance in pu. |
| 7 | Event time | Real | Event time in seconds. |
| 8 | Bus 1 name | Character(12) | Bus name when Bus 1 is zero. |
| 9 | Bus 2 name | Character(12) | `0`. |
| 10 | Parameter 4 | Real | `0`. |

### Type 6: Remove impedance from a bus

Removes impedance from a bus.

| Position | Field | Type | Description |
| ---: | --- | --- | --- |
| 1 | Type | Integer | `6`. |
| 2 | Bus 1 | Integer or text | Bus number or bus name. |
| 3 | Bus 2 | Integer | `0`. |
| 4 | Circuit ID | Character(2) | `0`. |
| 5 | Resistance | Real | Resistance in pu. |
| 6 | Inductance | Real | Inductance parameter in pu. |
| 7 | Event time | Real | Event time in seconds. |
| 8 | Bus 1 name | Character(12) | Bus name when Bus 1 is zero. |
| 9 | Bus 2 name | Character(12) | `0`. |
| 10 | Parameter 4 | Real | `0`. |

### Type 7: Open branch

Opens a transmission line or series capacitor.

| Position | Field | Type | Description |
| ---: | --- | --- | --- |
| 1 | Type | Integer | `7`. |
| 2 | Bus 1 | Integer or text | Bus 1 number or branch name. |
| 3 | Bus 2 | Integer or zero | Bus 2 number, or zero when using a branch name. |
| 4 | Circuit ID | Character(2) | Circuit identifier. |
| 5 | Parameter 1 | Real | `0`. |
| 6 | Parameter 2 | Real | `0`. |
| 7 | Event time | Real | Event time in seconds. |
| 8 | Bus 1 name | Character(12) | Used when Bus 1 is zero. |
| 9 | Bus 2 name | Character(12) | Used when Bus 2 is zero. |
| 10 | Parameter 4 | Real | `0`. |

### Type 8: Close branch

Closes a transmission line or series capacitor.

| Position | Field | Type | Description |
| ---: | --- | --- | --- |
| 1 | Type | Integer | `8`. |
| 2 | Bus 1 | Integer or text | Bus 1 number or branch name. |
| 3 | Bus 2 | Integer or zero | Bus 2 number, or zero when using a branch name. |
| 4 | Circuit ID | Character(2) | Circuit identifier. |
| 5 | Parameter 1 | Real | `0`. |
| 6 | Parameter 2 | Real | `0`. |
| 7 | Event time | Real | Event time in seconds. |
| 8 | Bus 1 name | Character(12) | Used when Bus 1 is zero. |
| 9 | Bus 2 name | Character(12) | Used when Bus 2 is zero. |
| 10 | Parameter 4 | Real | `0`. |

### Type 9: Close branch from side, open to side

Closes the branch at the from side and opens it at the to side.

| Position | Field | Type | Description |
| ---: | --- | --- | --- |
| 1 | Type | Integer | `9`. |
| 2 | Bus 1 | Integer or text | Bus 1 number or branch name. |
| 3 | Bus 2 | Integer or zero | Bus 2 number, or zero when using a branch name. |
| 4 | Circuit ID | Character(2) | Circuit identifier. |
| 5 | Parameter 1 | Real | `0`. |
| 6 | Parameter 2 | Real | `0`. |
| 7 | Event time | Real | Event time in seconds. |
| 8 | Bus 1 name | Character(12) | Used when Bus 1 is zero. |
| 9 | Bus 2 name | Character(12) | Used when Bus 2 is zero. |
| 10 | Parameter 4 | Real | `0`. |

### Type 10: Close branch to side, open from side

Closes the branch at the to side and opens it at the from side.

| Position | Field | Type | Description |
| ---: | --- | --- | --- |
| 1 | Type | Integer | `10`. |
| 2 | Bus 1 | Integer or text | Bus 1 number or branch name. |
| 3 | Bus 2 | Integer or zero | Bus 2 number, or zero when using a branch name. |
| 4 | Circuit ID | Character(2) | Circuit identifier. |
| 5 | Parameter 1 | Real | `0`. |
| 6 | Parameter 2 | Real | `0`. |
| 7 | Event time | Real | Event time in seconds. |
| 8 | Bus 1 name | Character(12) | Used when Bus 1 is zero. |
| 9 | Bus 2 name | Character(12) | Used when Bus 2 is zero. |
| 10 | Parameter 4 | Real | `0`. |

### Type 11: Close series capacitor gap

Closes the gap of a series capacitor.

| Position | Field | Type | Description |
| ---: | --- | --- | --- |
| 1 | Type | Integer | `11`. |
| 2 | Bus 1 | Integer or text | Bus 1 number or branch name. |
| 3 | Bus 2 | Integer or zero | Bus 2 number, or zero when using a branch name. |
| 4 | Circuit ID | Character(2) | Circuit identifier. |
| 5 | Parameter 1 | Real | `0`. |
| 6 | Parameter 2 | Real | `0`. |
| 7 | Event time | Real | Event time in seconds. |
| 8 | Bus 1 name | Character(12) | Used when Bus 1 is zero. |
| 9 | Bus 2 name | Character(12) | Used when Bus 2 is zero. |
| 10 | Parameter 4 | Real | `0`. |

## Parser API

```python
from pathlib import Path

from o_grid.dynamics import EvtFileParser

evt_file = EvtFileParser(Path("tests/data/evt/9bus.evt")).file
print(evt_file.total_simulation_time)

for contingency in evt_file.contingencies:
    print(contingency.number, contingency.identifier)
    for event in contingency.events:
        print(event.event_type, event.bus_1, event.bus_2, event.parameter_3)
```

The parser preserves the event line number and original raw line. It validates
the ten-field event shape but intentionally leaves event-specific behavior to
the stability simulation layer.
