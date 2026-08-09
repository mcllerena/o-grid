#pragma once

#include <QString>

enum class PowerFlowMethod {
    NewtonRaphson,
    FastDecoupled,
    OptimizationACPF,
};

struct PowerFlowSettings {
    PowerFlowMethod method = PowerFlowMethod::NewtonRaphson;
    int maxIterations = 30;
    double tolerance = 1e-6;

    bool flatStart = true;
    bool enforceReactiveLimits = true;
    bool autoTapAdjustment = true;
    bool autoSwitchedShunts = true;

    bool includeDCElements = true;
    bool enableContingencyMode = false;

    QString slackPolicy = "Single slack";
};
