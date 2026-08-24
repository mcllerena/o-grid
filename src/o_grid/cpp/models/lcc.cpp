#include "../headers/models/lcc.h"

#include <algorithm>
#include <cmath>

namespace {

std::size_t bus_index_for_id(const CaseData& data, int bus_id) {
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        if (data.buses[i].id == bus_id) {
            return i;
        }
    }
    return data.buses.size();
}

double solved_bus_voltage(const CaseData& data, const PowerFlowResult& result, int bus_id) {
    const std::size_t bus_index = bus_index_for_id(data, bus_id);
    return bus_index < result.vm.size() ? result.vm[bus_index] : 1.0;
}

double lcc_reactive_from_power_factor(double pdc_mw, double angle_deg, double commutation_angle_deg) {
    if (std::abs(pdc_mw) <= TOLERANCE) {
        return 0.0;
    }
    const double phi_rad = (angle_deg + 0.5 * commutation_angle_deg) * kPi / 180.0;
    return std::abs(pdc_mw) * std::tan(phi_rad);
}

double clamp_lcc_tap(double tap, double tap_min, double tap_max) {
    if (tap_min > 0.0 && tap_max > tap_min) {
        return std::max(tap_min, std::min(tap_max, tap));
    }
    return tap;
}

double lcc_target_tap(double pdc_mw,
                      double vdc_kv,
                      double angle_deg,
                      double commutation_angle_deg,
                      double bridge_voltage_kv,
                      int poles,
                      double ac_voltage_pu,
                      double tap_min,
                      double tap_max) {
    if (std::abs(pdc_mw) <= TOLERANCE || std::abs(vdc_kv) <= TOLERANCE || bridge_voltage_kv <= TOLERANCE || ac_voltage_pu <= TOLERANCE) {
        return 1.0;
    }
    const double converter_open_voltage_kv = 0.995 * 3.0 * std::sqrt(2.0) / kPi *
        std::max(1, poles) * bridge_voltage_kv * ac_voltage_pu;
    const double effective_angle_rad = (angle_deg + 0.5 * commutation_angle_deg) * kPi / 180.0;
    const double tap = converter_open_voltage_kv * std::cos(effective_angle_rad) / std::abs(vdc_kv);
    return clamp_lcc_tap(std::max(0.0, tap), tap_min, tap_max);
}

double lcc_converter_base_mu_deg(const Lcc& lcc, bool rectifier, double ac_voltage_pu) {
    const double vdc_kv = rectifier ? lcc.vdc_rectifier_kv : lcc.vdc_inverter_kv;
    const double x_comm_percent = rectifier ? lcc.xcr : lcc.xci;
    const double bridge_voltage_kv = rectifier ? lcc.rectifier_bridge_voltage_kv : lcc.inverter_bridge_voltage_kv;
    const double nominal_mva = rectifier ? lcc.rectifier_nominal_mva : lcc.inverter_nominal_mva;
    const double tap = rectifier ? lcc.tap_rectifier : lcc.tap_inverter;
    const double angle_deg = rectifier ? lcc.alpha_deg : lcc.gamma_deg;
    if (std::abs(lcc.pdc_mw) <= TOLERANCE || std::abs(vdc_kv) <= TOLERANCE || x_comm_percent <= TOLERANCE ||
        bridge_voltage_kv <= TOLERANCE || nominal_mva <= TOLERANCE || tap <= TOLERANCE || ac_voltage_pu <= TOLERANCE) {
        return rectifier ? lcc.mu_rectifier_deg : lcc.mu_inverter_deg;
    }

    const double transformer_x_ohm = (x_comm_percent / 100.0) * bridge_voltage_kv * bridge_voltage_kv / nominal_mva;
    const double dc_current_ka = lcc.idc_a > DISPLAY_TOLERANCE ? std::abs(lcc.idc_a) / 1000.0 : std::abs(lcc.pdc_mw / vdc_kv);
    const double terminal_voltage_kv = tap * bridge_voltage_kv * ac_voltage_pu;
    const double angle_rad = angle_deg * kPi / 180.0;
    const double overlap_drop = std::sqrt(2.0) * transformer_x_ohm * dc_current_ka / terminal_voltage_kv;
    const double clamped_argument = std::max(-1.0, std::min(1.0, std::cos(angle_rad) - overlap_drop));
    return std::max(0.0, (std::acos(clamped_argument) - angle_rad) * 180.0 / kPi);
}

} // namespace

LccInterfaceDeviation update_lcc_from_dc_solution(CaseData& data, const PowerFlowResult& result, double damping) {
    LccInterfaceDeviation deviation;
    for (Lcc& lcc : data.lccs) {
        if (std::abs(lcc.pdc_mw) <= TOLERANCE || std::abs(lcc.vdc_rectifier_kv) <= TOLERANCE) {
            continue;
        }

        const double dc_current_ka = std::abs(lcc.pdc_mw / lcc.vdc_rectifier_kv);
        const double dc_loss_mw = dc_current_ka * dc_current_ka * std::max(0.0, lcc.rdc);
        const double inverter_vdc_abs = std::max(0.0, std::abs(lcc.vdc_rectifier_kv) - dc_current_ka * std::max(0.0, lcc.rdc));
        const double target_p_rectifier_mw = std::abs(lcc.pdc_mw);
        const double target_p_inverter_mw = std::max(0.0, std::abs(lcc.pdc_mw) - dc_loss_mw);
        const double next_p_rectifier_mw = (1.0 - damping) * lcc.p_rectifier_mw + damping * target_p_rectifier_mw;
        const double next_p_inverter_mw = (1.0 - damping) * lcc.p_inverter_mw + damping * target_p_inverter_mw;
        const double rectifier_voltage = solved_bus_voltage(data, result, lcc.rectifier_bus);
        const double inverter_voltage = solved_bus_voltage(data, result, lcc.inverter_bus);
        lcc.vdc_inverter_kv = inverter_vdc_abs;
        lcc.idc_a = dc_current_ka * 1000.0;
        deviation.max_active_mw = std::max(deviation.max_active_mw, std::abs(next_p_rectifier_mw - lcc.p_rectifier_mw));
        deviation.max_active_mw = std::max(deviation.max_active_mw, std::abs(next_p_inverter_mw - lcc.p_inverter_mw));
        lcc.p_rectifier_mw = next_p_rectifier_mw;
        lcc.p_inverter_mw = next_p_inverter_mw;

        const bool low_voltage_lcc = lcc.vbase_kv <= 10.0;
        if (low_voltage_lcc) {
            const double target_tap_rectifier = lcc_target_tap(lcc.pdc_mw, lcc.vdc_rectifier_kv,
                lcc.alpha_deg, lcc.mu_rectifier_deg, lcc.rectifier_bridge_voltage_kv, lcc.rectifier_poles,
                1.0, lcc.tap_rectifier_min, lcc.tap_rectifier_max);
            const double target_tap_inverter = lcc_target_tap(lcc.pdc_mw, lcc.vdc_inverter_kv,
                lcc.gamma_deg, lcc.mu_inverter_deg, lcc.inverter_bridge_voltage_kv, lcc.inverter_poles,
                1.0, lcc.tap_inverter_min, lcc.tap_inverter_max);
            const double target_q_rectifier_mvar = lcc.q_rectifier_mvar;
            const double target_q_inverter_mvar = lcc.q_inverter_mvar;
            const double next_q_rectifier_mvar = (1.0 - damping) * lcc.q_rectifier_mvar + damping * target_q_rectifier_mvar;
            const double next_q_inverter_mvar = (1.0 - damping) * lcc.q_inverter_mvar + damping * target_q_inverter_mvar;
            const double next_tap_rectifier = (1.0 - damping) * lcc.tap_rectifier + damping * target_tap_rectifier;
            const double next_tap_inverter = (1.0 - damping) * lcc.tap_inverter + damping * target_tap_inverter;
            deviation.max_reactive_mvar = std::max(deviation.max_reactive_mvar, std::abs(next_q_rectifier_mvar - lcc.q_rectifier_mvar));
            deviation.max_reactive_mvar = std::max(deviation.max_reactive_mvar, std::abs(next_q_inverter_mvar - lcc.q_inverter_mvar));
            deviation.max_tap_equivalent_mvar = std::max(deviation.max_tap_equivalent_mvar, data.base_mva * std::abs(next_tap_rectifier - lcc.tap_rectifier));
            deviation.max_tap_equivalent_mvar = std::max(deviation.max_tap_equivalent_mvar, data.base_mva * std::abs(next_tap_inverter - lcc.tap_inverter));
            lcc.tap_rectifier = clamp_lcc_tap(next_tap_rectifier, lcc.tap_rectifier_min, lcc.tap_rectifier_max);
            lcc.tap_inverter = clamp_lcc_tap(next_tap_inverter, lcc.tap_inverter_min, lcc.tap_inverter_max);
            lcc.q_rectifier_mvar = next_q_rectifier_mvar;
            lcc.q_inverter_mvar = next_q_inverter_mvar;
            continue;
        }

        const double target_tap_rectifier = lcc_target_tap(lcc.pdc_mw, lcc.vdc_rectifier_kv,
            lcc.alpha_deg, lcc.mu_rectifier_deg, lcc.rectifier_bridge_voltage_kv, lcc.rectifier_poles,
            rectifier_voltage, lcc.tap_rectifier_min, lcc.tap_rectifier_max);
        const double target_tap_inverter = lcc_target_tap(lcc.pdc_mw, lcc.vdc_inverter_kv,
            lcc.gamma_deg, lcc.mu_inverter_deg, lcc.inverter_bridge_voltage_kv, lcc.inverter_poles,
            inverter_voltage, lcc.tap_inverter_min, lcc.tap_inverter_max);

        const bool transmission_lcc = lcc.vbase_kv >= 200.0 && lcc.vbase_kv < 750.0;
        const double rectifier_power_mw = transmission_lcc ? std::abs(lcc.pdc_mw) + dc_loss_mw : std::abs(lcc.pdc_mw);
        const double inverter_power_mw = std::abs(lcc.pdc_mw);
        const double target_q_rectifier_mvar = lcc_reactive_from_power_factor(rectifier_power_mw, lcc.alpha_deg, lcc.mu_rectifier_deg);
        const double target_q_inverter_mvar = lcc_reactive_from_power_factor(inverter_power_mw, lcc.gamma_deg, lcc.mu_inverter_deg);

        const double next_q_rectifier_mvar = (1.0 - damping) * lcc.q_rectifier_mvar + damping * target_q_rectifier_mvar;
        const double next_q_inverter_mvar = (1.0 - damping) * lcc.q_inverter_mvar + damping * target_q_inverter_mvar;
        const double next_tap_rectifier = (1.0 - damping) * lcc.tap_rectifier + damping * target_tap_rectifier;
        const double next_tap_inverter = (1.0 - damping) * lcc.tap_inverter + damping * target_tap_inverter;
        deviation.max_reactive_mvar = std::max(deviation.max_reactive_mvar, std::abs(next_q_rectifier_mvar - lcc.q_rectifier_mvar));
        deviation.max_reactive_mvar = std::max(deviation.max_reactive_mvar, std::abs(next_q_inverter_mvar - lcc.q_inverter_mvar));
        deviation.max_tap_equivalent_mvar = std::max(deviation.max_tap_equivalent_mvar, data.base_mva * std::abs(next_tap_rectifier - lcc.tap_rectifier));
        deviation.max_tap_equivalent_mvar = std::max(deviation.max_tap_equivalent_mvar, data.base_mva * std::abs(next_tap_inverter - lcc.tap_inverter));
        lcc.tap_rectifier = clamp_lcc_tap(next_tap_rectifier, lcc.tap_rectifier_min, lcc.tap_rectifier_max);
        lcc.tap_inverter = clamp_lcc_tap(next_tap_inverter, lcc.tap_inverter_min, lcc.tap_inverter_max);
        lcc.mu_rectifier_deg = lcc_converter_base_mu_deg(lcc, true, rectifier_voltage);
        lcc.mu_inverter_deg = lcc_converter_base_mu_deg(lcc, false, inverter_voltage);
        lcc.q_rectifier_mvar = next_q_rectifier_mvar;
        lcc.q_inverter_mvar = next_q_inverter_mvar;
    }
    return deviation;
}
