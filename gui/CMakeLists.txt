cmake_minimum_required(VERSION 3.21)

project(ogrid_gui VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)

find_package(Qt6 REQUIRED COMPONENTS Widgets)

add_executable(ogrid_gui
    src/main.cpp
    src/MainWindow.h
    src/MainWindow.cpp
    src/PowerFlowSettings.h
    src/PowerFlowSettingsDialog.h
    src/PowerFlowSettingsDialog.cpp
    src/resources.qrc
)

target_link_libraries(ogrid_gui PRIVATE Qt6::Widgets)

if(WIN32)
    set_target_properties(ogrid_gui PROPERTIES WIN32_EXECUTABLE TRUE)

    get_target_property(QT_QMAKE_EXECUTABLE Qt6::qmake IMPORTED_LOCATION)
    get_filename_component(QT_BIN_DIR "${QT_QMAKE_EXECUTABLE}" DIRECTORY)
    find_program(WINDEPLOYQT_EXECUTABLE windeployqt HINTS "${QT_BIN_DIR}")

    if(WINDEPLOYQT_EXECUTABLE)
        add_custom_command(TARGET ogrid_gui POST_BUILD
            COMMAND "${WINDEPLOYQT_EXECUTABLE}" --verbose 0 --no-compiler-runtime "$<TARGET_FILE:ogrid_gui>"
            COMMENT "Deploying Qt runtime with windeployqt"
        )
    else()
        message(WARNING "windeployqt not found; ogrid_gui may fail to start outside a Qt environment.")
    endif()
endif()
