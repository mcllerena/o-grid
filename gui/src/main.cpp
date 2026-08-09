#include <QApplication>
#include <QIcon>

#include "MainWindow.h"

int main(int argc, char* argv[]) {
    QApplication app(argc, argv);
    // Fusion is fully palette-driven; the native Windows style ignores the
    // palette for menu popups and follows the OS theme instead, which breaks
    // light mode text visibility.
    app.setStyle("Fusion");
    app.setWindowIcon(QIcon(":/icons/o-grid.png"));
    MainWindow window;
    window.show();
    return app.exec();
}
