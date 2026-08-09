#include "MainWindow.h"

#include <QAction>
#include <QActionGroup>
#include <QApplication>
#include <QColor>
#include <QCoreApplication>
#include <QDateTime>
#include <QDir>
#include <QFileInfo>
#include <QFileDialog>
#include <QFormLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QIcon>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QMenu>
#include <QMenuBar>
#include <QMessageBox>
#include <QPalette>
#include <QProcess>
#include <QPushButton>
#include <QSplitter>
#include <QStatusBar>
#include <QStyle>
#include <QTextEdit>
#include <QVBoxLayout>
#include <QWidget>

#include "PowerFlowSettingsDialog.h"

namespace {
QString methodName(PowerFlowMethod method) {
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
} // namespace

MainWindow::MainWindow(QWidget* parent)
    : QMainWindow(parent) {
    setWindowTitle("o-grid Studio");
    setWindowIcon(QIcon(":/icons/o-grid.png"));
    resize(1180, 740);

    createActions();
    createMenus();
    createCentralUi();

    applyLightPalette();
    statusBar()->showMessage("Ready");
    appendLog("Application started.");
}

void MainWindow::createActions() {
    openCaseAction_ = new QAction("Load Case...", this);
    connect(openCaseAction_, &QAction::triggered, this, &MainWindow::openCase);

    exitAction_ = new QAction("Exit", this);
    connect(exitAction_, &QAction::triggered, this, &QWidget::close);

    runPowerFlowAction_ = new QAction("Run Power Flow", this);
    connect(runPowerFlowAction_, &QAction::triggered, this, &MainWindow::runPowerFlow);

    settingsAction_ = new QAction("Power Flow Settings...", this);
    connect(settingsAction_, &QAction::triggered, this, &MainWindow::openPowerFlowSettings);

    lightModeAction_ = new QAction("Light mode", this);
    lightModeAction_->setCheckable(true);
    connect(lightModeAction_, &QAction::triggered, this, &MainWindow::setLightMode);

    darkModeAction_ = new QAction("Dark mode", this);
    darkModeAction_->setCheckable(true);
    connect(darkModeAction_, &QAction::triggered, this, &MainWindow::setDarkMode);

    auto* modeGroup = new QActionGroup(this);
    modeGroup->addAction(lightModeAction_);
    modeGroup->addAction(darkModeAction_);
    modeGroup->setExclusive(true);
    lightModeAction_->setChecked(true);
}

void MainWindow::createMenus() {
    QMenu* fileMenu = menuBar()->addMenu("File");
    fileMenu->addAction(openCaseAction_);
    fileMenu->addSeparator();
    fileMenu->addAction(exitAction_);

    QMenu* studyMenu = menuBar()->addMenu("Study");
    studyMenu->addAction(settingsAction_);
    studyMenu->addAction(runPowerFlowAction_);

    QMenu* settingsMenu = menuBar()->addMenu("Settings");
    QMenu* appearanceMenu = settingsMenu->addMenu("Appearance");
    appearanceMenu->addAction(lightModeAction_);
    appearanceMenu->addAction(darkModeAction_);
}

void MainWindow::createCentralUi() {
    auto* container = new QWidget(this);
    auto* root = new QHBoxLayout(container);

    auto* splitter = new QSplitter(container);

    auto* leftPanel = new QWidget(splitter);
    auto* leftLayout = new QVBoxLayout(leftPanel);

    auto* caseGroup = new QGroupBox("Case", leftPanel);
    auto* caseLayout = new QVBoxLayout(caseGroup);
    loadedCaseLabel_ = new QLabel("No case loaded.", caseGroup);
    loadedCaseLabel_->setWordWrap(true);
    caseLayout->addWidget(loadedCaseLabel_);

    auto* runGroup = new QGroupBox("Power Flow Run", leftPanel);
    auto* runLayout = new QVBoxLayout(runGroup);

    settingsButton_ = new QPushButton("Settings...", runGroup);
    runButton_ = new QPushButton("Run Power Flow", runGroup);

    connect(settingsButton_, &QPushButton::clicked, this, &MainWindow::openPowerFlowSettings);
    connect(runButton_, &QPushButton::clicked, this, &MainWindow::runPowerFlow);

    runLayout->addWidget(settingsButton_);
    runLayout->addWidget(runButton_);
    runLayout->addStretch();

    auto* summaryGroup = new QGroupBox("Current Numerical Profile", leftPanel);
    auto* summaryLayout = new QFormLayout(summaryGroup);
    summaryLayout->addRow("Method", new QLabel(methodName(settings_.method), summaryGroup));
    summaryLayout->addRow("Iterations", new QLabel(QString::number(settings_.maxIterations), summaryGroup));
    summaryLayout->addRow("Tolerance", new QLabel(QString::number(settings_.tolerance, 'g', 9), summaryGroup));

    leftLayout->addWidget(caseGroup);
    leftLayout->addWidget(runGroup);
    leftLayout->addWidget(summaryGroup);
    leftLayout->addStretch();

    auto* rightPanel = new QWidget(splitter);
    auto* rightLayout = new QVBoxLayout(rightPanel);

    auto* logTitle = new QLabel("Simulation Log", rightPanel);
    logView_ = new QTextEdit(rightPanel);
    logView_->setReadOnly(true);

    rightLayout->addWidget(logTitle);
    rightLayout->addWidget(logView_);

    splitter->addWidget(leftPanel);
    splitter->addWidget(rightPanel);
    splitter->setStretchFactor(0, 0);
    splitter->setStretchFactor(1, 1);

    root->addWidget(splitter);
    setCentralWidget(container);
}

void MainWindow::openCase() {
    const QString filePath = QFileDialog::getOpenFileName(
        this,
        "Load Power Flow Case",
        QString(),
        "Power Flow Cases (*.m *.pwf);;MATPOWER Cases (*.m);;ANAREDE Cases (*.pwf);;All Files (*.*)"
    );

    if (filePath.isEmpty()) {
        return;
    }

    currentCasePath_ = filePath;
    loadedCaseLabel_->setText(currentCasePath_);
    statusBar()->showMessage("Case loaded", 3000);
    appendLog("Loaded case: " + currentCasePath_);
}

void MainWindow::openPowerFlowSettings() {
    PowerFlowSettingsDialog dialog(settings_, this);
    if (dialog.exec() != QDialog::Accepted) {
        return;
    }

    settings_ = dialog.settings();
    appendLog(
        "Updated settings: method=" + methodName(settings_.method)
        + ", maxIter=" + QString::number(settings_.maxIterations)
        + ", tol=" + QString::number(settings_.tolerance, 'g', 9)
    );
}

void MainWindow::runPowerFlow() {
    if (currentCasePath_.isEmpty()) {
        QMessageBox::warning(this, "No case loaded", "Load a power-flow case before running power flow.");
        return;
    }

    if (backendProcess_ != nullptr && backendProcess_->state() != QProcess::NotRunning) {
        QMessageBox::information(this, "Power flow in progress", "A power flow is already running.");
        return;
    }

    appendLog("Running power flow...");
    appendLog("Case: " + currentCasePath_);
    appendLog("Method: " + methodName(settings_.method));
    appendLog("Max iterations: " + QString::number(settings_.maxIterations));
    appendLog("Tolerance: " + QString::number(settings_.tolerance, 'g', 9));

    launchBackend();
}

QString MainWindow::backendMethodArg() const {
    switch (settings_.method) {
    case PowerFlowMethod::NewtonRaphson:
        return "newton-raphson";
    case PowerFlowMethod::FastDecoupled:
        return "fast-decoupled";
    case PowerFlowMethod::OptimizationACPF:
        return "optimization";
    }
    return "newton-raphson";
}

QString MainWindow::backendScriptPath() const {
    QDir dir(QCoreApplication::applicationDirPath());
    while (dir.exists()) {
        if (dir.exists("gui/backend/run_power_flow.py")) {
            return dir.filePath("gui/backend/run_power_flow.py");
        }
        if (!dir.cdUp()) {
            break;
        }
    }
    return QString();
}

QString MainWindow::pythonExecutable() const {
    const QString script = backendScriptPath();
    if (script.isEmpty()) {
        return QString();
    }
    QDir repoRoot(QFileInfo(script).absolutePath());
    repoRoot.cdUp();
    repoRoot.cdUp();
    const QStringList candidates = {
        repoRoot.filePath(".venv/Scripts/python.exe"),
        repoRoot.filePath(".venv/bin/python"),
        "python",
    };
    for (const QString& candidate : candidates) {
        if (QFileInfo(candidate).isFile() || candidate == "python") {
            return candidate;
        }
    }
    return "python";
}

void MainWindow::launchBackend() {
    const QString script = backendScriptPath();
    const QString python = pythonExecutable();
    QDir repoRoot(QFileInfo(script).absolutePath());
    repoRoot.cdUp();
    repoRoot.cdUp();

    if (script.isEmpty() || (!QFileInfo(python).isFile() && python != "python")) {
        const QString message = script.isEmpty()
            ? "Could not locate the backend script (gui/backend/run_power_flow.py)."
            : "Could not locate the Python interpreter (.venv). "
              "Run the GUI from the o-grid repository and ensure a virtual environment exists.";
        appendLog("[error] " + message);
        statusBar()->showMessage("Backend not found", 5000);
        return;
    }

    const bool controlsEnabled = settings_.autoTapAdjustment
        || settings_.autoSwitchedShunts
        || settings_.enforceReactiveLimits;

    const QStringList arguments = {
        script,
        "--case", currentCasePath_,
        "--method", backendMethodArg(),
        "--max-iterations", QString::number(settings_.maxIterations),
        "--tolerance", QString::number(settings_.tolerance, 'g', 9),
        "--max-control-passes", QString::number(controlsEnabled ? 12 : 0),
    };

    if (backendProcess_ == nullptr) {
        backendProcess_ = new QProcess(this);
        connect(backendProcess_, &QProcess::readyReadStandardOutput,
                this, &MainWindow::onBackendOutput);
        connect(backendProcess_, &QProcess::readyReadStandardError,
                this, &MainWindow::onBackendError);
        connect(backendProcess_, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
                this, &MainWindow::onBackendFinished);
    }

    backendStdoutBuffer_.clear();
    backendProcess_->setWorkingDirectory(repoRoot.absolutePath());
    backendProcess_->start(python, arguments);

    runButton_->setEnabled(false);
    runPowerFlowAction_->setEnabled(false);
    statusBar()->showMessage("Power flow running...");
}

void MainWindow::onBackendOutput() {
    backendStdoutBuffer_.append(QString::fromUtf8(backendProcess_->readAllStandardOutput()));
}

void MainWindow::onBackendError() {
    const QString data = QString::fromUtf8(backendProcess_->readAllStandardError());
    for (const QString& line : data.split('\n')) {
        if (!line.trimmed().isEmpty()) {
            appendLog(line);
        }
    }
}

void MainWindow::onBackendFinished(int exitCode, QProcess::ExitStatus exitStatus) {
    runButton_->setEnabled(true);
    runPowerFlowAction_->setEnabled(true);

    onBackendOutput();

    const int firstBrace = backendStdoutBuffer_.indexOf('{');
    const int lastBrace = backendStdoutBuffer_.lastIndexOf('}');
    QJsonDocument doc;
    if (firstBrace != -1 && lastBrace > firstBrace) {
        doc = QJsonDocument::fromJson(
            backendStdoutBuffer_.mid(firstBrace, lastBrace - firstBrace + 1).toUtf8());
    }

    if (doc.isObject()) {
        const QJsonObject report = doc.object();
        const bool converged = report.value("converged").toBool();
        appendLog(
            QString("Power flow %1 in %2 iteration(s); max mismatch %3 pu")
                .arg(converged ? "converged" : "did not converge")
                .arg(report.value("iterations").toInt())
                .arg(report.value("max_mismatch_pu").toDouble(), 0, 'e', 4));
        appendLog(
            QString("Generation: %1 MW solved / %2 MW scheduled; Load: %3 MW; Losses: %4 MW")
                .arg(report.value("solved_generation_mw").toDouble(), 0, 'f', 2)
                .arg(report.value("scheduled_generation_mw").toDouble(), 0, 'f', 2)
                .arg(report.value("total_load_mw").toDouble(), 0, 'f', 2)
                .arg(report.value("branch_active_losses_mw").toDouble(), 0, 'f', 2));
        appendLog(
            QString("Buses: %1 (after reduction %2); Branches: %3 (after reduction %4); Elapsed: %5 s")
                .arg(report.value("bus_count").toInt())
                .arg(report.value("bus_count_after_reduction").toInt())
                .arg(report.value("branch_count").toInt())
                .arg(report.value("branch_count_after_reduction").toInt())
                .arg(report.value("elapsed_seconds").toDouble(), 0, 'f', 3));
        statusBar()->showMessage(converged ? "Power flow converged" : "Power flow did not converge", 5000);
    } else if (exitStatus == QProcess::CrashExit) {
        appendLog("[error] Backend process crashed (exit code " + QString::number(exitCode) + ").");
        statusBar()->showMessage("Backend crashed", 5000);
    } else {
        appendLog("[error] Backend produced no parseable report (exit code "
                  + QString::number(exitCode) + ").");
        statusBar()->showMessage("Backend failed", 5000);
    }

    backendStdoutBuffer_.clear();
    backendProcess_->closeReadChannel(QProcess::StandardOutput);
    backendProcess_->closeReadChannel(QProcess::StandardError);
}

void MainWindow::appendLog(const QString& line) {
    const QString timestamp = QDateTime::currentDateTime().toString("yyyy-MM-dd hh:mm:ss");
    logView_->append("[" + timestamp + "] " + line);
}

void MainWindow::setLightMode() {
    applyLightPalette();
    appendLog("Appearance changed: light mode.");
}

void MainWindow::setDarkMode() {
    applyDarkPalette();
    appendLog("Appearance changed: dark mode.");
}

void MainWindow::applyLightPalette() {
    QPalette palette;
    palette.setColor(QPalette::Window, QColor(250, 250, 250));
    palette.setColor(QPalette::WindowText, QColor(20, 20, 20));
    palette.setColor(QPalette::Base, QColor(255, 255, 255));
    palette.setColor(QPalette::AlternateBase, QColor(240, 240, 240));
    palette.setColor(QPalette::ToolTipBase, QColor(255, 255, 255));
    palette.setColor(QPalette::ToolTipText, QColor(20, 20, 20));
    palette.setColor(QPalette::Text, QColor(20, 20, 20));
    palette.setColor(QPalette::Button, QColor(240, 240, 240));
    palette.setColor(QPalette::ButtonText, QColor(20, 20, 20));
    palette.setColor(QPalette::BrightText, QColor(200, 0, 0));
    palette.setColor(QPalette::Link, QColor(0, 90, 200));
    palette.setColor(QPalette::Highlight, QColor(0, 120, 212));
    palette.setColor(QPalette::HighlightedText, QColor(255, 255, 255));
    palette.setColor(QPalette::Disabled, QPalette::WindowText, QColor(120, 120, 120));
    palette.setColor(QPalette::Disabled, QPalette::Text, QColor(120, 120, 120));
    palette.setColor(QPalette::Disabled, QPalette::ButtonText, QColor(120, 120, 120));
    setAppPalette(palette);
}

void MainWindow::applyDarkPalette() {
    QPalette palette;
    palette.setColor(QPalette::Window, QColor(37, 37, 38));
    palette.setColor(QPalette::WindowText, QColor(240, 240, 240));
    palette.setColor(QPalette::Base, QColor(30, 30, 30));
    palette.setColor(QPalette::AlternateBase, QColor(45, 45, 45));
    palette.setColor(QPalette::ToolTipBase, QColor(240, 240, 240));
    palette.setColor(QPalette::ToolTipText, QColor(240, 240, 240));
    palette.setColor(QPalette::Text, QColor(240, 240, 240));
    palette.setColor(QPalette::Button, QColor(45, 45, 45));
    palette.setColor(QPalette::ButtonText, QColor(240, 240, 240));
    palette.setColor(QPalette::BrightText, QColor(255, 85, 85));
    palette.setColor(QPalette::Highlight, QColor(0, 120, 212));
    palette.setColor(QPalette::HighlightedText, QColor(255, 255, 255));
    palette.setColor(QPalette::Disabled, QPalette::WindowText, QColor(120, 120, 120));
    palette.setColor(QPalette::Disabled, QPalette::Text, QColor(120, 120, 120));
    palette.setColor(QPalette::Disabled, QPalette::ButtonText, QColor(120, 120, 120));
    setAppPalette(palette);
}

void MainWindow::setAppPalette(const QPalette& palette) {
    qApp->setPalette(palette);
    qApp->setStyleSheet(QString());
    const QWidgetList widgets = qApp->allWidgets();
    for (QWidget* widget : widgets) {
        widget->setPalette(palette);
        widget->update();
    }
}
