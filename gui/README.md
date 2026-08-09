# o-grid Qt GUI Starter

This folder contains a starter C++/Qt Widgets desktop GUI to host power flow workflows.

## Goals

- Provide an operator-style desktop window for loading cases and running studies.
- Expose configurable power flow options in a dedicated settings dialog.
- Keep the architecture ready for integration with your existing power flow models.

## Current UI

- Main window with:
  - File actions (Open MATPOWER, Exit)
  - Study actions (Run Power Flow, Power Flow Settings)
  - Left-side run panel with quick controls
  - Log output panel
- Power Flow Settings dialog with configurable fields:
  - Method selection (Newton-Raphson, Fast Decoupled, Optimization ACPF)
  - Iteration and tolerance controls
  - Slack bus policy
  - Reactive limit enforcement
  - Tap and switched shunt controls
  - DC and contingency toggles

## Build and Generate Executable

Requirements:

- CMake >= 3.21
- Qt6 Widgets SDK
- Visual Studio 2022 C++ build tools (MSVC)
- C++17 compiler

### One-time setup (Windows, this repository)

If Qt is installed at `C:\Users\<your-user>\Qt\6.8.2\msvc2022_64`, configure once from `gui/`:

```powershell
cmake -S . -B build -DCMAKE_PREFIX_PATH="$env:USERPROFILE\Qt\6.8.2\msvc2022_64"
```

### After GUI code changes

From `gui/`, rebuild the executable:

```powershell
cmake --build build --config Release
```

The executable is generated at:

```text
gui/build/Release/ogrid_gui.exe
```

Qt runtime deployment is automatic on Windows via `windeployqt` (configured in `CMakeLists.txt`).

### Run

From repository root:

```powershell
.\gui\build\Release\ogrid_gui.exe
```

Or from `gui/`:

```powershell
.\build\Release\ogrid_gui.exe
```

### Clean rebuild (if build cache gets stale)

From `gui/`:

```powershell
Remove-Item -Recurse -Force .\build
cmake -S . -B build -DCMAKE_PREFIX_PATH="$env:USERPROFILE\Qt\6.8.2\msvc2022_64"
cmake --build build --config Release
```

### Troubleshooting

- `cmake` not recognized:
  - Open a new terminal after installation, then run `cmake --version`.
- Qt not found (`Qt6Config.cmake`):
  - Re-run configure with `-DCMAKE_PREFIX_PATH="...\Qt\6.8.2\msvc2022_64"`.
- App seems to not open:
  - Launch from `gui/build/Release/ogrid_gui.exe` and verify DLL/plugin folders exist in that same directory.

## Integration Notes

In this starter template, `MainWindow::runPowerFlow()` is the integration point where you can call the existing o-grid backend.
