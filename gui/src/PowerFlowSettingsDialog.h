#pragma once

#include <QDialog>

#include "PowerFlowSettings.h"

class QCheckBox;
class QComboBox;
class QDialogButtonBox;
class QDoubleSpinBox;
class QFormLayout;
class QSpinBox;

class PowerFlowSettingsDialog : public QDialog {
    Q_OBJECT

public:
    explicit PowerFlowSettingsDialog(const PowerFlowSettings& initial, QWidget* parent = nullptr);

    PowerFlowSettings settings() const;

private:
    void buildUi();
    void applyInitialValues();

    PowerFlowSettings initial_;

    QComboBox* methodCombo_ = nullptr;
    QSpinBox* maxIterationsSpin_ = nullptr;
    QDoubleSpinBox* toleranceSpin_ = nullptr;
    QComboBox* slackPolicyCombo_ = nullptr;

    QCheckBox* flatStartCheck_ = nullptr;
    QCheckBox* enforceReactiveLimitsCheck_ = nullptr;
    QCheckBox* autoTapCheck_ = nullptr;
    QCheckBox* autoShuntCheck_ = nullptr;
    QCheckBox* includeDCCheck_ = nullptr;
    QCheckBox* contingencyCheck_ = nullptr;

    QDialogButtonBox* buttons_ = nullptr;
};
