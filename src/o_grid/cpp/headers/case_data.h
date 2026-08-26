#pragma once

#include <string>
#include <vector>

#include "definitions.h"

enum class BusType {
    PQ = 0,
    PV = 1,
    Slack = 2,
};

struct Bus {
    int id = 0;
    std::string name;
    BusType type = BusType::PQ;
    int area = 0;
    std::string base_voltage_group;
    std::string model_code;
    double base_kv = 0.0;
    bool in_service = true;
    double voltage = 1.0;
    double angle_rad = 0.0;
    double pg_mw = 0.0;
    double qg_mvar = 0.0;
    double qmin_mvar = 0.0;
    double qmax_mvar = 0.0;
    bool has_q_limits = false;
    bool zero_generation_voltage_control = false;
    bool switchable_pq_to_pv = false;
    bool switchable_pv_to_pq = false;
    double pl_mw = 0.0;
    double ql_mvar = 0.0;
    double gsh = 0.0;
    double bsh = 0.0;
    double vmax = 1.1;
    double vmin = 0.9;
};

struct OriginalBusRecord {
    Bus bus;
    bool in_service = true;
    int representative_bus = 0;
    bool collapsed = false;
};

struct Branch {
    int from = 0;
    int to = 0;
    int circuit = 1;
    double r = 0.0;
    double x = 0.0;
    double b = 0.0;
    double tap = 1.0;
    double tap_min = 0.0;
    double tap_max = 0.0;
    double phase_rad = 0.0;
    double rate_mva = 0.0;
};

struct Svc {
    int bus = 0;
    int control_bus = 0;
    double slope = 0.0;
    double q_mvar = 0.0;
    double qmin_mvar = 0.0;
    double qmax_mvar = 0.0;
    int mode = 0;
};

struct Csc {
    int from = 0;
    int to = 0;
    int circuit = 1;
    std::string operation = "A";
    std::string state = "L";
    std::string bypass = "D";
    std::string mode = "X";
    double x_pu = 0.0;
    double xmin_pu = 0.0;
    double xmax_pu = 0.0;
    int control_bus = 0;
};

struct BusShunt {
    int bus = 0;
    int owner_bus = 0;
    int remote_bus = 0;
    double q_mvar = 0.0;
    double applied_q_mvar = 0.0;
    double qmin_mvar = 0.0;
    double qmax_mvar = 0.0;
    double vmin = 0.0;
    double vmax = 0.0;
    std::string control_mode = "F";
    std::string control_type = "C";
};

struct LineShunt {
    int from = 0;
    int to = 0;
    int circuit = 1;
    double q_from_mvar = 0.0;
    double q_to_mvar = 0.0;
};

struct IndividualLoad {
    int bus = 0;
    double p_mw = 0.0;
    double q_mvar = 0.0;
};

struct Ltc {
    int from = 0;
    int to = 0;
    int circuit = 1;
    int control_bus = 0;
    int branch_index = -1;
    double r = 0.0;
    double x = 0.0;
    double tap = 1.0;
    double tap_min = 0.0;
    double tap_max = 0.0;
    double v_target = 1.0;
    bool voltage_control = false;
};

struct Pst {
    int from = 0;
    int to = 0;
    int circuit = 1;
    int control_bus = 0;
    int branch_index = -1;
    double r = 0.0;
    double x = 0.0;
    double phase_rad = 0.0;
    double phase_min_rad = -kPi / 4.0;
    double phase_max_rad = kPi / 4.0;
    double p_target_mw = 0.0;
};

struct Lcc {
    int link_id = 0;
    int rectifier_bus = 0;
    int inverter_bus = 0;
    std::string control = "P";
    double xcr = 0.0;
    double xci = 0.0;
    double bfr = 0.0;
    double bfi = 0.0;
    double rdc = 0.0;
    double pdc_mw = 0.0;
    double p_rectifier_mw = 0.0;
    double p_inverter_mw = 0.0;
    double power_base_mw = 0.0;
    double idc_a = 0.0;
    double q_rectifier_mvar = 0.0;
    double q_inverter_mvar = 0.0;
    bool rectifier_dc_slack = false;
    bool inverter_dc_slack = false;
    double alpha_deg = 0.0;
    double mu_rectifier_deg = 0.0;
    double gamma_deg = 0.0;
    double mu_inverter_deg = 0.0;
    double vdc_kv = 0.0;
    double vbase_kv = 1.0;
    double vdc_rectifier_kv = 0.0;
    double vdc_inverter_kv = 0.0;
    double rectifier_bridge_voltage_kv = 0.0;
    double inverter_bridge_voltage_kv = 0.0;
    double rectifier_nominal_mva = 0.0;
    double inverter_nominal_mva = 0.0;
    int rectifier_poles = 1;
    int inverter_poles = 1;
    double tap_rectifier = 1.0;
    double tap_inverter = 1.0;
    double tap_rectifier_min = 0.0;
    double tap_rectifier_max = 0.0;
    double tap_inverter_min = 0.0;
    double tap_inverter_max = 0.0;
    std::string tap_control_rectifier = "";
    std::string tap_control_inverter = "";
    double rectifier_voltage_setpoint_kv = 0.0;
    double inverter_voltage_setpoint_kv = 0.0;
    bool rectifier_has_voltage_setpoint = false;
    bool inverter_has_voltage_setpoint = false;
    std::string name;
};

struct CaseData {
    double base_mva = 100.0;
    bool vlim_enabled = false;
    bool bus_switching_enabled = false;
    double ac_tepa_mw = AC_ACTIVE_POWER_TOLERANCE_MW;
    double ac_tepr_mvar = AC_REACTIVE_POWER_TOLERANCE_MVAR;
    double vlim_reactive_start_tolerance = VLIM_REACTIVE_START_TOLERANCE;
    double vlim_control_tolerance = VLIM_CONTROL_TOLERANCE;
    double reactive_limit_tolerance_mvar = REACTIVE_LIMIT_TOLERANCE_MVAR;
    double area_interchange_tolerance_mw = AREA_INTERCHANGE_TOLERANCE_MW;
    double voltage_divergence_min_pu = VOLTAGE_DIVERGENCE_MIN_PU;
    double voltage_divergence_max_pu = VOLTAGE_DIVERGENCE_MAX_PU;
    double lcc_tepa_mw = LCC_INTERFACE_ACTIVE_TOLERANCE_MW;
    double lcc_tepr_mvar = LCC_INTERFACE_REACTIVE_TOLERANCE_MVAR;
    std::vector<Bus> buses;
    std::vector<OriginalBusRecord> original_buses;
    std::vector<Branch> branches;
    std::vector<BusShunt> bus_shunts;
    std::vector<LineShunt> line_shunts;
    std::vector<IndividualLoad> individual_loads;
    std::vector<Svc> svcs;
    std::vector<Csc> cscs;
    std::vector<Ltc> ltcs;
    std::vector<Pst> psts;
    std::vector<Lcc> lccs;
};

struct BusSwitchingSummary {
    int pq_to_pv_candidates = 0;
    int pv_to_pq_candidates = 0;
    int updated_q_limits = 0;
    std::string pq_to_pv_file;
    std::string pv_to_pq_file;
};

double clean_output_zero(double value);

CaseData read_case_file(const std::string& path);

BusSwitchingSummary load_anarede_bus_switching(CaseData& data,
                                               const std::string& case_path,
                                               const std::string& conversion_root = "");
