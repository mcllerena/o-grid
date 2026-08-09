#include "MainWindow.h"

#include <QAction>
#include <QActionGroup>
#include <QApplication>
#include <QColor>
#include <QDateTime>
#include <QFileDialog>
#include <QFormLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QIcon>
#include <QLabel>
#include <QMenu>
#include <QMenuBar>
#include <QMessageBox>
#include <QPalette>
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

    statusBar()->showMessage("Ready");
    appendLog("Application started.");
}

void MainWindow::createActions() {
    openCaseAction_ = new QAction("Open MATPOWER Case...", this);
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
        "Open MATPOWER Case",
        QString(),
        "MATPOWER Case (*.m);;All Files (*.*)"
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
        QMessageBox::warning(this, "No case loaded", "Open a MATPOWER case before running power flow.");
        return;
    }

    appendLog("Running power flow...");
    appendLog("Case: " + currentCasePath_);
    appendLog("Method: " + methodName(settings_.method));
    appendLog("Max iterations: " + QString::number(settings_.maxIterations));
    appendLog("Tolerance: " + QString::number(settings_.tolerance, 'g', 9));

    // Integration point:
    // Replace this stub with calls into o-grid backend services.
    appendLog("[stub] Backend execution is not wired yet.");

    statusBar()->showMessage("Run completed (stub)", 3000);
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
    qApp->setPalette(style()->standardPalette());
    qApp->setStyleSheet(QString());
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
    qApp->setPalette(palette);
}
