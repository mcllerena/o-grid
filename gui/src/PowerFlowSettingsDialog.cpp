#include "PowerFlowSettingsDialog.h"

#include <QCheckBox>
#include <QComboBox>
#include <QDialogButtonBox>
#include <QDoubleSpinBox>
#include <QFormLayout>
#include <QGroupBox>
#include <QLabel>
#include <QSpinBox>
#include <QVBoxLayout>

namespace {
QString methodToString(PowerFlowMethod method) {
    switch (method) {
    case PowerFlowMethod::NewtonRaphson:
        return "Newton-Raphson";
    case PowerFlowMethod::FastDecoupled:
        return "Fast Decoupled";
    case PowerFlowMethod::OptimizationACPF:
        return "Optimization ACPF";
    }
    return "Newton-Raphson";
}

PowerFlowMethod methodFromString(const QString& value) {
    if (value == "Fast Decoupled") {
        return PowerFlowMethod::FastDecoupled;
    }
    if (value == "Optimization ACPF") {
        return PowerFlowMethod::OptimizationACPF;
    }
    return PowerFlowMethod::NewtonRaphson;
}
} // namespace

PowerFlowSettingsDialog::PowerFlowSettingsDialog(const PowerFlowSettings& initial, QWidget* parent)
    : QDialog(parent), initial_(initial) {
    setWindowTitle("Power Flow Settings");
    setMinimumWidth(460);
    buildUi();
    applyInitialValues();
}

PowerFlowSettings PowerFlowSettingsDialog::settings() const {
    PowerFlowSettings out;
    out.method = methodFromString(methodCombo_->currentText());
    out.maxIterations = maxIterationsSpin_->value();
    out.tolerance = toleranceSpin_->value();
    out.slackPolicy = slackPolicyCombo_->currentText();

    out.flatStart = flatStartCheck_->isChecked();
    out.enforceReactiveLimits = enforceReactiveLimitsCheck_->isChecked();
    out.autoTapAdjustment = autoTapCheck_->isChecked();
    out.autoSwitchedShunts = autoShuntCheck_->isChecked();
    out.includeDCElements = includeDCCheck_->isChecked();
    out.enableContingencyMode = contingencyCheck_->isChecked();
    return out;
}

void PowerFlowSettingsDialog::buildUi() {
    auto* root = new QVBoxLayout(this);

    auto* numericGroup = new QGroupBox("Numerical Solver", this);
    auto* numericLayout = new QFormLayout(numericGroup);

    methodCombo_ = new QComboBox(numericGroup);
    methodCombo_->addItems({"Newton-Raphson", "Fast Decoupled", "Optimization ACPF"});

    maxIterationsSpin_ = new QSpinBox(numericGroup);
    maxIterationsSpin_->setRange(1, 500);

    toleranceSpin_ = new QDoubleSpinBox(numericGroup);
    toleranceSpin_->setDecimals(9);
    toleranceSpin_->setRange(1e-12, 1.0);
    toleranceSpin_->setSingleStep(1e-5);
    toleranceSpin_->setValue(1e-6);
    toleranceSpin_->setToolTip("Power mismatch tolerance in per-unit.");

    slackPolicyCombo_ = new QComboBox(numericGroup);
    slackPolicyCombo_->addItems({"Single slack", "Distributed slack"});

    numericLayout->addRow("Method", methodCombo_);
    numericLayout->addRow("Max iterations", maxIterationsSpin_);
    numericLayout->addRow("Tolerance (pu)", toleranceSpin_);
    numericLayout->addRow("Slack policy", slackPolicyCombo_);

    auto* controlsGroup = new QGroupBox("Network Control Options", this);
    auto* controlsLayout = new QVBoxLayout(controlsGroup);

    flatStartCheck_ = new QCheckBox("Flat start", controlsGroup);
    enforceReactiveLimitsCheck_ = new QCheckBox("Enforce generator reactive limits", controlsGroup);
    autoTapCheck_ = new QCheckBox("Enable automatic LTC/PST tap adjustment", controlsGroup);
    autoShuntCheck_ = new QCheckBox("Enable switched shunt control", controlsGroup);
    includeDCCheck_ = new QCheckBox("Include AC/DC converter and LCC controls", controlsGroup);
    contingencyCheck_ = new QCheckBox("Contingency mode (single outage assumptions)", controlsGroup);

    controlsLayout->addWidget(flatStartCheck_);
    controlsLayout->addWidget(enforceReactiveLimitsCheck_);
    controlsLayout->addWidget(autoTapCheck_);
    controlsLayout->addWidget(autoShuntCheck_);
    controlsLayout->addWidget(includeDCCheck_);
    controlsLayout->addWidget(contingencyCheck_);

    auto* infoLabel = new QLabel(
        "This starter dialog mirrors the operator workflow of desktop study tools: "
        "define run options first, then execute and review logs/results.",
        this
    );
    infoLabel->setWordWrap(true);

    buttons_ = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, this);
    connect(buttons_, &QDialogButtonBox::accepted, this, &QDialog::accept);
    connect(buttons_, &QDialogButtonBox::rejected, this, &QDialog::reject);

    root->addWidget(numericGroup);
    root->addWidget(controlsGroup);
    root->addWidget(infoLabel);
    root->addWidget(buttons_);
}

void PowerFlowSettingsDialog::applyInitialValues() {
    methodCombo_->setCurrentText(methodToString(initial_.method));
    maxIterationsSpin_->setValue(initial_.maxIterations);
    toleranceSpin_->setValue(initial_.tolerance);
    slackPolicyCombo_->setCurrentText(initial_.slackPolicy);

    flatStartCheck_->setChecked(initial_.flatStart);
    enforceReactiveLimitsCheck_->setChecked(initial_.enforceReactiveLimits);
    autoTapCheck_->setChecked(initial_.autoTapAdjustment);
    autoShuntCheck_->setChecked(initial_.autoSwitchedShunts);
    includeDCCheck_->setChecked(initial_.includeDCElements);
    contingencyCheck_->setChecked(initial_.enableContingencyMode);
}
