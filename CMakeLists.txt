cmake_minimum_required(VERSION 3.16)
project(VoiceDJ CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ─── SoundTouch sources ───────────────────────────────────────────────────────
set(ST_SRC_DIR ${CMAKE_SOURCE_DIR}/libs/soundtouch/source/SoundTouch)
file(GLOB ST_SOURCES ${ST_SRC_DIR}/*.cpp)

# ─── ImGui sources ────────────────────────────────────────────────────────────
set(IMGUI_DIR ${CMAKE_SOURCE_DIR}/libs/imgui)
set(IMGUI_SOURCES
    ${IMGUI_DIR}/imgui.cpp
    ${IMGUI_DIR}/imgui_draw.cpp
    ${IMGUI_DIR}/imgui_tables.cpp
    ${IMGUI_DIR}/imgui_widgets.cpp
    ${IMGUI_DIR}/backends/imgui_impl_win32.cpp
    ${IMGUI_DIR}/backends/imgui_impl_dx11.cpp
)

# ─── Main executable ─────────────────────────────────────────────────────────
add_executable(VoiceDJ WIN32
    src/main.cpp
    src/resources.rc
    ${ST_SOURCES}
    ${IMGUI_SOURCES}
)

# ─── Include directories ──────────────────────────────────────────────────────
target_include_directories(VoiceDJ PRIVATE
    src/
    libs/
    libs/imgui/
    libs/imgui/backends/
    libs/soundtouch/include/
)

# ─── Compile definitions ──────────────────────────────────────────────────────
target_compile_definitions(VoiceDJ PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    SOUNDTOUCH_FLOAT_SAMPLES
    _WIN32_WINNT=0x0601
)

# ─── Compiler flags ───────────────────────────────────────────────────────────
target_compile_options(VoiceDJ PRIVATE
    -O2
    -msse2
    -mfpmath=sse
    -Wall
    -Wno-unused-variable
    -Wno-unused-function
    -Wno-sign-compare
    -Wno-deprecated-declarations
)

# ─── Link libraries ───────────────────────────────────────────────────────────
target_link_libraries(VoiceDJ PRIVATE
    d3d11
    dxgi
    d3dcompiler
    ole32
    oleaut32
    uuid
    sapi
    winmm
    ksuser
    avrt
    shell32
    comctl32
    comdlg32
    dwmapi
    -static-libgcc
    -static-libstdc++
    -static
)

# ─── Strip debug symbols for release ─────────────────────────────────────────
set_target_properties(VoiceDJ PROPERTIES
    LINK_FLAGS "-Wl,--strip-all"
)
