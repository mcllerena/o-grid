#pragma once

#include <QMainWindow>
#include <QPalette>
#include <QProcess>
#include <QString>

#include "PowerFlowSettings.h"

class QAction;
class QLabel;
class QPushButton;
class QTextEdit;

class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    explicit MainWindow(QWidget* parent = nullptr);

private slots:
    void openCase();
    void openPowerFlowSettings();
    void runPowerFlow();
    void setLightMode();
    void setDarkMode();
    void onBackendOutput();
    void onBackendError();
    void onBackendFinished(int exitCode, QProcess::ExitStatus exitStatus);

private:
    void createActions();
    void createMenus();
    void createCentralUi();
    void appendLog(const QString& line);
    void applyLightPalette();
    void applyDarkPalette();
    void setAppPalette(const QPalette& palette);
    QString backendMethodArg() const;
    QString backendScriptPath() const;
    QString pythonExecutable() const;
    void launchBackend();

    PowerFlowSettings settings_;
    QString currentCasePath_;

    QAction* openCaseAction_ = nullptr;
    QAction* exitAction_ = nullptr;
    QAction* runPowerFlowAction_ = nullptr;
    QAction* settingsAction_ = nullptr;
    QAction* lightModeAction_ = nullptr;
    QAction* darkModeAction_ = nullptr;

    QLabel* loadedCaseLabel_ = nullptr;
    QTextEdit* logView_ = nullptr;
    QPushButton* runButton_ = nullptr;
    QPushButton* settingsButton_ = nullptr;

    QProcess* backendProcess_ = nullptr;
    QString backendStdoutBuffer_;
};
