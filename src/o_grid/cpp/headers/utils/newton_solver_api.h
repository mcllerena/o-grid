#pragma once

#include <iosfwd>

#include "../case_data.h"
#include "power_flow_types.h"

PowerFlowResult solve_power_flow_newton_with_outer_controls(CaseData& data,
                                                            double tolerance,
                                                            int max_iterations,
                                                            std::ostream* live_trace_output = nullptr);

PowerFlowResult solve_power_flow_fd_with_outer_controls(CaseData& data,
                                                        double tolerance,
                                                        int max_iterations,
                                                        std::ostream* live_trace_output = nullptr);
