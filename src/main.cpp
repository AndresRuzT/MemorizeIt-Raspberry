#include "raylib.h"
#include "GameEngine.hpp"
#include <iostream>
#include <string>

int main(int argc, char* argv[]) {
    int cameraIndex = -1; // -1 = autodetección inteligente (prioriza cámara USB)

    if (argc > 1) {
        try {
            cameraIndex = std::stoi(argv[1]);
            std::cout << "[Main] Índice de cámara forzado por argumento: " << cameraIndex << std::endl;
        } catch (...) {
            std::cout << "[Main] Uso: " << argv[0] << " [indice_camara_opcional]" << std::endl;
        }
    }

    const int screenWidth = 800;
    const int screenHeight = 600;

    SetConfigFlags(FLAG_VSYNC_HINT | FLAG_MSAA_4X_HINT);
    InitWindow(screenWidth, screenHeight, "MemorizeIt - Among Us Reactor (Raspberry Pi 4)");
    SetTargetFPS(60);

    GameEngine game(screenWidth, screenHeight, cameraIndex);
    game.initialize();

    while (!WindowShouldClose()) {
        float dt = GetFrameTime();

        game.update(dt);

        BeginDrawing();
        game.draw();
        DrawFPS(screenWidth - 85, screenHeight - 28);
        EndDrawing();
    }

    CloseWindow();
    return 0;
}
